"""Ingesta tolerante de archivos: acepta la data en cualquier formato razonable.

Resuelve la fricción real de conectar data institucional:

- **Formatos**: CSV, TSV, TXT, Excel (.xlsx/.xlsm/.xls), JSON, NDJSON, Parquet y ZIP
  que contenga cualquiera de los anteriores.
- **Separador**: detecta coma, punto y coma, tabulador o barra vertical.
- **Codificación**: prueba UTF-8, UTF-8 con BOM, Latin-1 y CP1252 (habitual en
  exportaciones de sistemas clínicos en español).
- **Nombres de columna**: mapea automáticamente nombres en español a los del
  contrato de datos (``rut_medico`` → ``doctor_id``, ``fecha`` → ``date``, etc.),
  ignorando acentos, mayúsculas, espacios y guiones.
- **Números**: interpreta el formato chileno ``$1.234.567,89`` además del anglosajón.
- **Fechas**: interpreta DD/MM/AAAA (estándar local) además de ISO-8601.
- **Libro único**: un solo Excel con una hoja por tabla se reparte automáticamente.

Toda transformación queda registrada en un informe de ingesta para trazabilidad.
"""
from __future__ import annotations

import io
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .features import OPTIONAL, REQUIRED

TABLES = ("doctors", "contracts", "encounters", "payments", "schedule", "sessions")
ENCODINGS = ("utf-8-sig", "utf-8", "latin-1", "cp1252")
DELIMITERS = (";", ",", "\t", "|")

# ---------------------------------------------------------------- nombres de columna
# canónico -> variantes aceptadas (se comparan ya normalizadas: sin acentos, minúsculas, sin separadores)
ALIASES: dict[str, tuple[str, ...]] = {
    "doctor_id": ("doctorid", "medicoid", "idmedico", "rutmedico", "rut", "medico", "profesional",
                  "idprofesional", "codigomedico", "cod_medico", "prestador", "idprestador"),
    "patient_id": ("patientid", "pacienteid", "idpaciente", "rutpaciente", "paciente", "ficha",
                   "numeroficha", "nroficha", "idpersona"),
    "encounter_id": ("encounterid", "atencionid", "idatencion", "idconsulta", "consultaid",
                     "numeroatencion", "nroatencion", "folio"),
    "payment_id": ("paymentid", "pagoid", "idpago", "liquidacion", "idliquidacion", "folio_pago",
                   "numeropago", "nropago", "npago", "npag", "numliquidacion", "nliquidacion",
                   "correlativopago", "idtransaccion"),
    "appointment_id": ("appointmentid", "citaid", "idcita", "agendaid", "idagenda", "horaid"),
    "date": ("date", "fecha", "fechaatencion", "fechaconsulta", "fechapago", "fechaturno", "dia", "fecha_dia"),
    "contract_start": ("contractstart", "horainicio", "inicioturno", "horainiciocontrato", "desde",
                       "inicio", "fechainicio", "horaentrada"),
    "contract_end": ("contractend", "horatermino", "finturno", "horaterminocontrato", "hasta",
                     "termino", "fechatermino", "horasalida", "fin"),
    "contracted_hours": ("contractedhours", "horascontratadas", "horaspactadas", "horasturno",
                         "horascontrato", "jornada", "horas"),
    "paid_hours": ("paidhours", "horaspagadas", "horasremuneradas", "horaspagas", "horascanceladas",
                   "horasliquidadas"),
    "hourly_rate": ("hourlyrate", "valorhora", "tarifahora", "preciohora", "valor_hora", "vhora"),
    "amount": ("amount", "monto", "montopagado", "totalpagado", "total", "montobruto", "importe", "pago"),
    "start_ts": ("startts", "horainicioatencion", "inicioatencion", "horainicio", "fechahorainicio",
                 "timestampinicio", "inicio"),
    "end_ts": ("endts", "horaterminoatencion", "terminoatencion", "horatermino", "fechahoratermino",
               "timestamptermino", "termino", "fin"),
    "login_ts": ("logints", "horalogin", "ingreso", "fechahoraingreso", "inicio_sesion", "iniciosesion", "login"),
    "logout_ts": ("logoutts", "horalogout", "salida", "fechahorasalida", "cierre_sesion", "cierresesion", "logout"),
    "record_created_ts": ("recordcreatedts", "fecharegistro", "fecharegistroclinico", "fechacreacionficha",
                          "creacionregistro", "fechafirma"),
    "has_clinical_record": ("hasclinicalrecord", "registroclinico", "tieneregistro", "conregistro",
                            "fichacompletada", "evolucionregistrada"),
    "status": ("status", "estado", "estadocita", "estadoagenda", "estadoatencion", "condicion"),
    "slot_start": ("slotstart", "horaagendada", "horacita", "horaagenda", "horabloque"),
    "peer_group": ("peergroup", "grupocomparacion", "grupopares", "grupo"),
    "expected_rate": ("expectedrate", "rendimientoesperado", "pacientesesperados", "pacienteshoraesperados",
                      "estandar", "meta", "rendimientoestandar"),
    "specialty": ("specialty", "especialidad", "subespecialidad"),
    "modality": ("modality", "modalidad", "tipoatencion", "canal"),
    "shift": ("shift", "turno", "jornadaturno", "horario"),
    "service_type": ("servicetype", "tipoprestacion", "prestacion", "tipoconsulta", "tipoatencionclinica"),
}

# Alias que dependen de la tabla: "hora inicio" significa inicio de turno en contratos
# y comienzo de la atención en encounters. Estos tienen prioridad sobre ALIASES.
TABLE_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "contracts": {
        "contract_start": ("horainicio", "inicio", "desde", "horaentrada", "horadesde", "startts", "fechainicio"),
        "contract_end": ("horatermino", "termino", "fin", "hasta", "horasalida", "horahasta", "endts", "fechatermino"),
    },
    "sessions": {
        "login_ts": ("horainicio", "inicio", "desde", "entrada", "startts"),
        "logout_ts": ("horatermino", "termino", "fin", "hasta", "salida", "endts"),
    },
    "encounters": {
        "start_ts": ("horainicio", "inicio", "desde", "contractstart"),
        "end_ts": ("horatermino", "termino", "fin", "hasta", "contractend"),
    },
}

# valores aceptados para schedule.status
STATUS_MAP = {
    "atendido": "atendido", "atendida": "atendido", "realizado": "atendido", "realizada": "atendido",
    "efectuado": "atendido", "completado": "atendido", "asistio": "atendido", "asiste": "atendido",
    "finalizado": "atendido", "cerrado": "atendido", "attended": "atendido",
    "ausente": "ausente", "noshow": "ausente", "noasiste": "ausente", "noasistio": "ausente",
    "inasistencia": "ausente", "falto": "ausente", "noatendido": "ausente", "absent": "ausente",
    "cancelado": "cancelado", "cancelada": "cancelado", "anulado": "cancelado", "anulada": "cancelado",
    "suspendido": "cancelado", "reagendado": "cancelado", "cancelled": "cancelado", "canceled": "cancelado",
}
TRUE_VALUES = {"1", "true", "t", "si", "sí", "s", "yes", "y", "verdadero", "v", "x"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "falso", ""}

DATE_COLUMNS = {"date", "contract_start", "contract_end", "start_ts", "end_ts", "login_ts", "logout_ts",
                "record_created_ts", "slot_start"}
NUMERIC_COLUMNS = {"contracted_hours", "paid_hours", "hourly_rate", "amount", "expected_rate"}
MONEY_COLUMNS = {"hourly_rate", "amount"}   # aquí el punto puede separar miles
BOOL_COLUMNS = {"has_clinical_record"}


@dataclass
class IngestReport:
    """Trazabilidad de la ingesta: qué se leyó y qué se transformó."""

    rows: list[dict] = field(default_factory=list)

    def add(self, table: str, item: str, detail: str, kind: str = "INFO") -> None:
        self.rows.append({"tabla": table, "aspecto": item, "detalle": detail, "tipo": kind})

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=["tabla", "aspecto", "detalle", "tipo"])


# ------------------------------------------------------------------ utilidades
def normalize_name(name: str) -> str:
    """minúsculas, sin acentos ni separadores: 'Rut Médico' y 'rut_medico' colapsan al mismo valor."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


_CANON = {normalize_name(k): k for k in ALIASES}
_ALIAS_INDEX = {normalize_name(a): canon for canon, variants in ALIASES.items() for a in variants}


_TABLE_INDEX = {t: {normalize_name(a): canon for canon, variants in m.items() for a in variants}
                for t, m in TABLE_ALIASES.items()}


def canonical_column(name: str, table: str | None = None) -> str | None:
    """Nombre canónico de una columna. ``table`` resuelve alias ambiguos entre tablas."""
    n = normalize_name(name)
    if table and n in _TABLE_INDEX.get(table, {}):
        return _TABLE_INDEX[table][n]
    return _CANON.get(n) or _ALIAS_INDEX.get(n)


def _read_csv_bytes(raw: bytes, report: IngestReport, label: str) -> pd.DataFrame:
    """Lee texto delimitado probando codificaciones y detectando el separador."""
    text = last_err = None
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
            if enc != "utf-8-sig":
                report.add(label, "codificación", f"leído como {enc}")
            break
        except UnicodeDecodeError as e:
            last_err = e
    if text is None:
        raise ValueError(f"no se pudo decodificar el archivo: {last_err}")

    sample = "\n".join(text.splitlines()[:20])
    counts = {d: sample.count(d) for d in DELIMITERS}
    delim = max(counts, key=counts.get)
    if counts[delim] == 0:
        delim = ","
    if delim != ",":
        report.add(label, "separador", f"detectado «{'tabulador' if delim == chr(9) else delim}»")
    return pd.read_csv(io.StringIO(text), sep=delim, dtype=str, keep_default_na=True, skip_blank_lines=True)


def read_any(source, filename: str | None = None, report: IngestReport | None = None) -> dict[str, pd.DataFrame]:
    """Lee un archivo en cualquier formato soportado.

    Devuelve ``{nombre_lógico: DataFrame}``: una entrada por archivo simple, varias
    cuando el origen es un Excel de múltiples hojas o un ZIP.
    """
    report = report or IngestReport()
    name = filename or getattr(source, "name", "archivo")
    ext = Path(str(name)).suffix.lower()
    raw = source.read() if hasattr(source, "read") else Path(source).read_bytes()
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    stem = Path(str(name)).stem

    if ext == ".zip":
        out: dict[str, pd.DataFrame] = {}
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for member in z.namelist():
                if member.endswith("/") or Path(member).suffix.lower() not in {
                        ".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls", ".json", ".ndjson", ".jsonl", ".parquet"}:
                    continue
                out.update(read_any(io.BytesIO(z.read(member)), member, report))
        report.add(stem, "formato", f"ZIP con {len(out)} tabla(s)")
        return out

    if ext in {".xlsx", ".xlsm", ".xls"}:
        book = pd.read_excel(io.BytesIO(raw), sheet_name=None, dtype=str)
        if len(book) == 1:
            only = next(iter(book))
            report.add(stem, "formato", f"Excel, hoja «{only}»")
            return {stem: next(iter(book.values()))}
        report.add(stem, "formato", f"Excel con {len(book)} hojas: {', '.join(book)}")
        return {sheet: df for sheet, df in book.items()}

    if ext == ".parquet":
        report.add(stem, "formato", "Parquet")
        return {stem: pd.read_parquet(io.BytesIO(raw))}

    if ext in {".json", ".ndjson", ".jsonl"}:
        text = next((raw.decode(e) for e in ENCODINGS if _try_decode(raw, e)), raw.decode("utf-8", "replace"))
        if ext in {".ndjson", ".jsonl"}:
            report.add(stem, "formato", "JSON por líneas")
            return {stem: pd.DataFrame([json.loads(l) for l in text.splitlines() if l.strip()])}
        obj = json.loads(text)
        if isinstance(obj, dict) and obj and all(isinstance(v, list) for v in obj.values()):
            report.add(stem, "formato", f"JSON con {len(obj)} tabla(s): {', '.join(obj)}")
            return {k: pd.DataFrame(v) for k, v in obj.items()}
        report.add(stem, "formato", "JSON")
        return {stem: pd.json_normalize(obj)}

    report.add(stem, "formato", "texto delimitado")
    return {stem: _read_csv_bytes(raw, report, stem)}


def _try_decode(raw: bytes, enc: str) -> bool:
    try:
        raw.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


# ------------------------------------------------------------------ identificación y normalización
def guess_table(name: str, df: pd.DataFrame) -> str | None:
    """Identifica a qué tabla del contrato corresponde, por nombre de archivo/hoja o por sus columnas."""
    n = normalize_name(name)
    by_name = {
        "doctors": ("doctors", "medicos", "medico", "profesionales", "maestromedicos", "dotacion", "rrhh"),
        "contracts": ("contracts", "contratos", "contrato", "turnos", "jornadas", "programacion"),
        "encounters": ("encounters", "atenciones", "atencion", "consultas", "prestaciones", "actividad"),
        "payments": ("payments", "pagos", "pago", "liquidaciones", "remuneraciones", "nomina"),
        "schedule": ("schedule", "agenda", "agendamiento", "citas", "horas", "reservas"),
        "sessions": ("sessions", "sesiones", "logins", "accesos", "logs", "conexiones"),
    }
    for table, keys in by_name.items():
        if any(k in n for k in keys):
            return table

    cols = {canonical_column(c) for c in df.columns} - {None}
    best, best_score = None, 0.0
    for table, required in {**REQUIRED, **OPTIONAL}.items():
        score = len(required & cols) / len(required)
        # desempate: columnas que solo existen en una tabla
        if table == "payments" and {"paid_hours", "amount"} & cols:
            score += 0.3
        if table == "encounters" and {"start_ts", "end_ts"} & cols:
            score += 0.3
        if table == "contracts" and {"contracted_hours", "contract_start"} & cols:
            score += 0.3
        if table == "sessions" and {"login_ts", "logout_ts"} & cols:
            score += 0.5
        if table == "schedule" and "status" in cols:
            score += 0.3
        if score > best_score:
            best, best_score = table, score
    return best if best_score >= 0.6 else None


def _to_number(s: pd.Series, money: bool = False) -> pd.Series:
    """Interpreta formato local (1.234.567,89) y anglosajón (1,234,567.89); limpia $ y espacios.

    Con ``money=True`` un punto único seguido de exactamente tres dígitos se trata como
    separador de miles ($187.800 → 187800). Fuera de columnas monetarias esa lectura sería
    peligrosa (8.000 horas no son ocho mil), así que allí solo el punto repetido separa miles.
    """
    t = s.astype(str).str.strip().str.replace(r"[^\d,.\-]", "", regex=True)
    has_comma, has_dot = t.str.contains(",", na=False), t.str.contains(r"\.", na=False)
    n_dots, n_commas = t.str.count(r"\."), t.str.count(",")
    dec_after_dot = t.str.split(".").str[-1].str.len()
    dec_after_comma = t.str.split(",").str[-1].str.len()

    # ambos separadores: el último que aparece es el decimal
    both = has_comma & has_dot
    comma_is_decimal = both & (t.str.rfind(",") > t.str.rfind("."))
    # solo comas: decimal si hay una sola y deja como máximo dos dígitos
    comma_is_decimal |= (~has_dot & has_comma & n_commas.eq(1) & dec_after_comma.le(2))
    # solo puntos: miles si se repiten o, en columnas monetarias, si dejan exactamente tres dígitos
    dot_is_thousands = (~has_comma & has_dot & n_dots.ge(2) & dec_after_dot.eq(3))
    if money:
        dot_is_thousands |= (~has_comma & has_dot & n_dots.eq(1) & dec_after_dot.eq(3))
    dot_is_thousands |= both & comma_is_decimal

    out = t.copy()
    out = out.where(~dot_is_thousands, out.str.replace(".", "", regex=False))
    out = out.where(~comma_is_decimal, out.str.replace(",", ".", regex=False))
    out = out.where(comma_is_decimal, out.str.replace(",", "", regex=False))
    return pd.to_numeric(out, errors="coerce")


def _to_datetime(s: pd.Series, label: str, col: str, report: IngestReport) -> pd.Series:
    """ISO-8601 primero; si no, DD/MM/AAAA (estándar local) y como último recurso MM/DD/AAAA."""
    iso = pd.to_datetime(s, errors="coerce", format="ISO8601")
    if iso.notna().sum() >= s.notna().sum() * 0.9:
        return iso
    day_first = pd.to_datetime(s, errors="coerce", dayfirst=True)
    month_first = pd.to_datetime(s, errors="coerce", dayfirst=False)
    if day_first.notna().sum() >= month_first.notna().sum():
        report.add(label, f"fechas · {col}", "interpretadas como DD/MM/AAAA")
        return day_first
    report.add(label, f"fechas · {col}", "interpretadas como MM/DD/AAAA")
    return month_first


def _to_bool(s: pd.Series) -> pd.Series:
    t = s.astype(str).str.strip().str.lower()
    return t.isin(TRUE_VALUES).where(t.isin(TRUE_VALUES | FALSE_VALUES) | s.isna(), np.nan)


def normalize_table(df: pd.DataFrame, table: str, report: IngestReport) -> pd.DataFrame:
    """Renombra columnas al contrato, convierte tipos y normaliza valores categóricos."""
    df = df.copy()
    mapping, unknown = {}, []
    for c in df.columns:
        canon = canonical_column(c, table)
        if canon and canon not in mapping.values():
            mapping[c] = canon
            if normalize_name(c) != normalize_name(canon):
                report.add(table, "columna", f"«{c}» → {canon}")
        else:
            unknown.append(c)
    df = df.rename(columns=mapping)
    if unknown:
        report.add(table, "columnas no reconocidas", ", ".join(map(str, unknown[:12])), "INFO")

    # fecha derivada del timestamp cuando no viene explícita
    if "date" not in df.columns:
        for src in ("start_ts", "contract_start", "login_ts", "slot_start"):
            if src in df.columns:
                df["date"] = df[src]
                report.add(table, "columna derivada", f"date obtenida de {src}")
                break

    for col in df.columns:
        if col in DATE_COLUMNS:
            df[col] = _to_datetime(df[col], table, col, report)
        elif col in NUMERIC_COLUMNS:
            before = df[col].notna().sum()
            df[col] = _to_number(df[col], money=col in MONEY_COLUMNS)
            lost = before - df[col].notna().sum()
            if lost:
                report.add(table, f"numérico · {col}", f"{lost} valores no interpretables → nulo", "ADVERTENCIA")
        elif col in BOOL_COLUMNS:
            df[col] = _to_bool(df[col])
        elif df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip().replace({"nan": np.nan, "": np.nan, "None": np.nan})

    if "date" in df.columns and pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = df["date"].dt.normalize()

    if table == "schedule" and "status" in df.columns:
        norm = df["status"].map(lambda v: STATUS_MAP.get(normalize_name(v), None) if pd.notna(v) else None)
        unmapped = df.loc[norm.isna() & df["status"].notna(), "status"].unique()
        if len(unmapped):
            report.add(table, "estados no reconocidos", ", ".join(map(str, unmapped[:8])), "ADVERTENCIA")
        df["status"] = norm.fillna(df["status"])

    # identificadores como texto, para que 12345 y "12345" no se separen
    for col in ("doctor_id", "patient_id", "encounter_id", "payment_id", "appointment_id"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

    df = df.dropna(how="all")
    return df


def _fill_derived(data: dict[str, pd.DataFrame], report: IngestReport) -> None:
    """Completa columnas obligatorias que pueden deducirse, en vez de rechazar la carga."""
    d = data.get("doctors")
    if d is None:
        return
    if "peer_group" not in d.columns:
        parts = [c for c in ("specialty", "modality") if c in d.columns]
        if parts:
            d["peer_group"] = d[parts].astype(str).agg(" | ".join, axis=1)
            report.add("doctors", "columna derivada", f"peer_group construido desde {', '.join(parts)}")
        else:
            d["peer_group"] = "General"
            report.add("doctors", "columna derivada", "peer_group = «General» (sin especialidad ni modalidad)",
                       "ADVERTENCIA")
    if "hourly_rate" not in d.columns and "payments" in data:
        p = data["payments"]
        if {"doctor_id", "amount", "paid_hours"} <= set(p.columns):
            rate = (p.groupby("doctor_id").apply(
                lambda g: g["amount"].sum() / g["paid_hours"].sum() if g["paid_hours"].sum() else np.nan,
                include_groups=False))
            d["hourly_rate"] = d["doctor_id"].map(rate)
            report.add("doctors", "columna derivada", "hourly_rate = monto pagado / horas pagadas")
    if "expected_rate" not in d.columns and "encounters" in data and "payments" in data:
        enc = data["encounters"].groupby("doctor_id").size().rename("n")
        hrs = data["payments"].groupby("doctor_id")["paid_hours"].sum()
        pph = (enc / hrs).replace([np.inf, -np.inf], np.nan)
        d["expected_rate"] = d["doctor_id"].map(
            pph.groupby(d.set_index("doctor_id")["peer_group"]).transform("median")
            if "peer_group" in d.columns else pph.median())
        d["expected_rate"] = d["expected_rate"].fillna(pph.median())
        report.add("doctors", "columna derivada",
                   "expected_rate = mediana observada de pacientes/hora del peer group (proxy inicial)",
                   "ADVERTENCIA")


def ingest(files: dict[str, object] | list, assume: dict[str, str] | None = None) -> tuple[dict[str, pd.DataFrame], IngestReport]:
    """Punto de entrada: recibe archivos en cualquier formato y devuelve las tablas del contrato.

    ``files``  lista de archivos (objetos con ``.read()`` y ``.name``) o dict ``{nombre: archivo}``.
    ``assume`` fuerza la tabla de un origen concreto: ``{"hoja1": "encounters"}``.
    """
    report = IngestReport()
    assume = assume or {}
    items = files.items() if isinstance(files, dict) else [(getattr(f, "name", f"archivo_{i}"), f)
                                                           for i, f in enumerate(files)]
    raw_tables: dict[str, pd.DataFrame] = {}
    for name, f in items:
        for key, df in read_any(f, name, report).items():
            raw_tables[key if key not in raw_tables else f"{key}_{len(raw_tables)}"] = df

    data: dict[str, pd.DataFrame] = {}
    for key, df in raw_tables.items():
        table = assume.get(key) or guess_table(key, df)
        if table is None:
            report.add(key, "sin identificar", f"{len(df)} filas, columnas: {', '.join(map(str, df.columns[:8]))}",
                       "ADVERTENCIA")
            continue
        norm = normalize_table(df, table, report)
        data[table] = pd.concat([data[table], norm], ignore_index=True) if table in data else norm
        report.add(table, "origen", f"«{key}» · {len(norm)} filas")

    _fill_derived(data, report)
    for t in TABLES:
        if t in data:
            missing = (REQUIRED.get(t, OPTIONAL.get(t, set())) - set(data[t].columns))
            if missing:
                report.add(t, "columnas faltantes", ", ".join(sorted(missing)), "ERROR")
    return data, report
