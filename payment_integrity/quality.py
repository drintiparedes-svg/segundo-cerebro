"""Control de calidad de datos de entrada.

Se ejecuta antes del modelo. Cada check produce una fila con tabla, nombre,
severidad (ERROR bloquea la ejecución; ADVERTENCIA degrada la confianza de
alguna capa; INFO es contexto), conteo y detalle. La idea es que quien conecta
data real vea de inmediato qué fuente está incompleta o inconsistente.
"""
from __future__ import annotations

import pandas as pd

from .features import REQUIRED, OPTIONAL

ERROR, WARN, INFO = "ERROR", "ADVERTENCIA", "INFO"

DATE_COLUMNS = {
    "contracts": ["date", "contract_start", "contract_end"],
    "encounters": ["date", "start_ts", "end_ts", "record_created_ts"],
    "payments": ["date"],
    "schedule": ["date", "slot_start"],
    "sessions": ["date", "login_ts", "logout_ts"],
}
PRIMARY_KEYS = {
    "doctors": ["doctor_id"],
    "encounters": ["encounter_id"],
    "payments": ["payment_id"],
    "contracts": ["doctor_id", "date", "contract_start"],
}


def _row(table, check, severity, count, detail=""):
    return {"tabla": table, "check": check, "severidad": severity, "n": int(count), "detalle": detail}


def _bad_dates(df: pd.DataFrame, col: str) -> int:
    s = df[col]
    parsed = pd.to_datetime(s, errors="coerce")
    return int((parsed.isna() & s.notna()).sum())


def assess(data: dict[str, pd.DataFrame], min_peer_size: int = 5) -> pd.DataFrame:
    rows = []
    # ---- presencia de tablas y columnas ---------------------------------------
    for t, cols in REQUIRED.items():
        if t not in data or data[t] is None:
            rows.append(_row(t, "tabla obligatoria ausente", ERROR, 1, "el modelo no puede ejecutarse"))
            continue
        missing = cols - set(data[t].columns)
        if missing:
            rows.append(_row(t, "columnas obligatorias ausentes", ERROR, len(missing), ", ".join(sorted(missing))))
        if len(data[t]) == 0:
            rows.append(_row(t, "tabla vacía", ERROR, 1))
    for t, cols in OPTIONAL.items():
        if t not in data or data[t] is None:
            rows.append(_row(t, "tabla opcional ausente", INFO, 1, "las reglas dependientes se omiten"))
        else:
            missing = cols - set(data[t].columns)
            if missing:
                rows.append(_row(t, "columnas ausentes en tabla opcional", WARN, len(missing), ", ".join(sorted(missing))))
    if any(r["severidad"] == ERROR for r in rows):
        return pd.DataFrame(rows)

    doctors, contracts, enc, pay = data["doctors"], data["contracts"], data["encounters"], data["payments"]

    # ---- nulos en columnas clave -------------------------------------------------
    for t, cols in {**REQUIRED, **{k: v for k, v in OPTIONAL.items() if k in data}}.items():
        df = data[t]
        for c in cols:
            if c in df.columns:
                n = int(df[c].isna().sum())
                if n:
                    rows.append(_row(t, f"nulos en {c}", WARN if n < len(df) else ERROR, n, f"{n / len(df):.1%} de las filas"))

    # ---- fechas no parseables ------------------------------------------------------
    for t, cols in DATE_COLUMNS.items():
        if t in data and data[t] is not None:
            for c in cols:
                if c in data[t].columns:
                    n = _bad_dates(data[t], c)
                    if n:
                        rows.append(_row(t, f"fechas no interpretables en {c}", ERROR, n, "use ISO-8601 (AAAA-MM-DD HH:MM:SS)"))

    # ---- claves duplicadas ---------------------------------------------------------
    for t, keys in PRIMARY_KEYS.items():
        df = data[t]
        if set(keys).issubset(df.columns):
            n = int(df.duplicated(keys).sum())
            if n:
                sev = WARN if t == "payments" else ERROR
                rows.append(_row(t, f"claves duplicadas ({', '.join(keys)})", sev, n,
                                 "en payments puede ser un pago duplicado real (R08)" if t == "payments" else "corrija la fuente"))

    # ---- integridad referencial ----------------------------------------------------
    ids = set(doctors["doctor_id"].astype(str))
    for t in ("contracts", "encounters", "payments", "schedule", "sessions"):
        if t in data and data[t] is not None and "doctor_id" in data[t].columns:
            n = int((~data[t]["doctor_id"].astype(str).isin(ids)).sum())
            if n:
                rows.append(_row(t, "doctor_id no existe en doctors", ERROR, n, "el médico no tendrá peer group ni rendimiento esperado"))

    # ---- coherencia de horas y tiempos ------------------------------------------
    if "contracted_hours" in contracts.columns:
        n = int((pd.to_numeric(contracts["contracted_hours"], errors="coerce") <= 0).sum())
        if n:
            rows.append(_row("contracts", "horas contratadas ≤ 0", WARN, n))
    if "paid_hours" in pay.columns:
        n = int((pd.to_numeric(pay["paid_hours"], errors="coerce") < 0).sum())
        if n:
            rows.append(_row("payments", "horas pagadas negativas", ERROR, n))
        n = int((pd.to_numeric(pay["paid_hours"], errors="coerce") > 16).sum())
        if n:
            rows.append(_row("payments", "horas pagadas > 16 en un día", WARN, n, "verifique unidad (horas vs minutos)"))
    st, en = pd.to_datetime(enc["start_ts"], errors="coerce"), pd.to_datetime(enc["end_ts"], errors="coerce")
    n = int((en < st).sum())
    if n:
        rows.append(_row("encounters", "fin anterior al inicio", ERROR, n))
    n = int(((en - st).dt.total_seconds() / 60 > 240).sum())
    if n:
        rows.append(_row("encounters", "atenciones > 4 horas", WARN, n, "posible error de registro de término"))
    if "has_clinical_record" not in enc.columns:
        rows.append(_row("encounters", "sin columna has_clinical_record", INFO, 1, "R12 y R13 se omiten"))

    # ---- cobertura contrato ↔ pago ↔ actividad -----------------------------------
    ck = contracts[["doctor_id", "date"]].astype(str).drop_duplicates()
    pk = pay[["doctor_id", "date"]].astype(str).drop_duplicates()
    ek = enc[["doctor_id", "date"]].astype(str).drop_duplicates()
    n = len(pk.merge(ck, how="left", indicator=True).query("_merge == 'left_only'"))
    if n:
        rows.append(_row("payments", "días pagados sin contrato ese día", WARN, n, "alimenta ContractRisk; verifique si son horas extraordinarias"))
    n = len(ck.merge(pk, how="left", indicator=True).query("_merge == 'left_only'"))
    if n:
        rows.append(_row("contracts", "días contratados sin pago", INFO, n, "no afectan el score; posible desfase de remuneraciones"))
    n = len(ek.merge(ck, how="left", indicator=True).query("_merge == 'left_only'"))
    if n:
        rows.append(_row("encounters", "atenciones en días sin contrato", WARN, n, "se cuentan como fuera de horario (R03)"))

    # ---- peer groups --------------------------------------------------------------
    if "peer_group" in doctors.columns:
        sizes = doctors.groupby("peer_group")["doctor_id"].nunique()
        small = sizes[sizes < min_peer_size]
        if len(small):
            rows.append(_row("doctors", f"peer groups con menos de {min_peer_size} médicos", WARN, len(small),
                             "; ".join(f"{k} ({v})" for k, v in small.items())))
    if "expected_rate" in doctors.columns:
        n = int(pd.to_numeric(doctors["expected_rate"], errors="coerce").isna().sum() + (pd.to_numeric(doctors["expected_rate"], errors="coerce") <= 0).sum())
        if n:
            rows.append(_row("doctors", "expected_rate ausente o ≤ 0", ERROR, n, "R02 y ProductivityRisk no son calculables"))

    # ---- resumen de cobertura -------------------------------------------------------
    rows.append(_row("doctors", "médicos", INFO, doctors["doctor_id"].nunique()))
    rows.append(_row("contracts", "médico-días contratados", INFO, len(ck)))
    rows.append(_row("encounters", "atenciones", INFO, len(enc)))
    rows.append(_row("payments", "registros de pago", INFO, len(pay)))
    return pd.DataFrame(rows)


def blocking(report: pd.DataFrame) -> bool:
    return bool((report["severidad"] == ERROR).any()) if len(report) else False
