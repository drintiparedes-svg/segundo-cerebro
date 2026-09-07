"""Ingesta en cualquier formato: separadores, codificaciones, alias en español, tipos locales."""
import io
import zipfile

import pandas as pd
import pytest

from payment_integrity import DEFAULT_CONFIG, generate_synthetic, run_pipeline
from payment_integrity.config import SyntheticConfig
from payment_integrity.features import validate_inputs
from payment_integrity.ingest import (ALIASES, canonical_column, guess_table, ingest, normalize_name,
                                      read_any, _to_number, IngestReport)


@pytest.fixture(scope="module")
def ds():
    return generate_synthetic(SyntheticConfig(n_doctors=10, n_weeks=6, seed=5)).as_dict()


def _buf(data: bytes, name: str):
    b = io.BytesIO(data)
    b.name = name
    return b


def test_normalize_and_aliases():
    assert normalize_name("RUT Médico") == normalize_name("rut_medico") == "rutmedico"
    assert canonical_column("N° Pago") == "payment_id"
    assert canonical_column("Monto Pagado") == "amount"
    # el mismo nombre significa cosas distintas según la tabla
    assert canonical_column("Hora Inicio", "contracts") == "contract_start"
    assert canonical_column("Hora Inicio", "encounters") == "start_ts"
    assert canonical_column("Hora Inicio", "sessions") == "login_ts"
    assert canonical_column("columna inventada") is None


@pytest.mark.parametrize("raw,money,expected", [
    ("$187.800", True, 187800.0),      # punto como miles en columna monetaria
    ("187.800", False, 187.8),         # fuera de dinero, el punto es decimal
    ("1.234.567,89", True, 1234567.89),
    ("1,234,567.89", True, 1234567.89),
    ("8.000", False, 8.0),             # ocho horas, no ocho mil
    ("4,5", False, 4.5),
])
def test_number_formats(raw, money, expected):
    assert _to_number(pd.Series([raw]), money=money).iloc[0] == pytest.approx(expected)


def test_csv_semicolon_latin1_spanish_dates(ds):
    p = ds["payments"].copy()
    p["date"] = pd.to_datetime(p["date"]).dt.strftime("%d/%m/%Y")
    p["amount"] = p["amount"].map(lambda v: f"${v:,.0f}".replace(",", "."))
    p = p.rename(columns={"payment_id": "N° Pago", "doctor_id": "RUT Médico", "date": "Fecha",
                          "paid_hours": "Horas Pagadas", "amount": "Monto Pagado"})
    raw = p.to_csv(sep=";", index=False).encode("latin-1")
    data, rep = ingest({"liquidaciones.csv": _buf(raw, "liquidaciones.csv")})
    assert "payments" in data
    got = data["payments"]
    assert {"payment_id", "doctor_id", "date", "paid_hours", "amount"} <= set(got.columns)
    assert pd.api.types.is_datetime64_any_dtype(got["date"])
    assert got["amount"].iloc[0] == ds["payments"]["amount"].iloc[0]
    r = rep.to_frame()
    assert (r["detalle"] == "detectado «;»").any()


def test_multisheet_excel_and_zip(ds):
    book = io.BytesIO()
    with pd.ExcelWriter(book) as xw:
        ds["doctors"].drop(columns=["scenario"]).to_excel(xw, sheet_name="Medicos", index=False)
        ds["contracts"].rename(columns={"contract_start": "Hora Inicio", "contract_end": "Hora Termino"}
                               ).to_excel(xw, sheet_name="Contratos", index=False)
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("sesiones.tsv", ds["sessions"].to_csv(sep="\t", index=False))
    data, _ = ingest({"libro.xlsx": _buf(book.getvalue(), "libro.xlsx"),
                      "logs.zip": _buf(zbuf.getvalue(), "logs.zip")})
    assert {"doctors", "contracts", "sessions"} <= set(data)
    assert {"contract_start", "contract_end"} <= set(data["contracts"].columns)
    assert len(data["sessions"]) == len(ds["sessions"])


def test_json_and_status_normalization(ds):
    e = ds["encounters"].rename(columns={"encounter_id": "folio", "doctor_id": "idMedico",
                                         "patient_id": "idPaciente", "start_ts": "inicioAtencion",
                                         "end_ts": "terminoAtencion"})
    data, _ = ingest({"atenciones.json": _buf(e.to_json(orient="records", date_format="iso").encode(), "atenciones.json")})
    assert "encounters" in data and {"start_ts", "end_ts"} <= set(data["encounters"].columns)

    sched = ds["schedule"].replace({"atendido": "ATENDIDA", "ausente": "No Asiste", "cancelado": "Anulada"})
    data2, _ = ingest({"agenda.csv": _buf(sched.to_csv(index=False).encode(), "agenda.csv")})
    assert set(data2["schedule"]["status"].unique()) <= {"atendido", "ausente", "cancelado"}


def test_guess_table_by_columns(ds):
    # nombre de archivo inútil: debe identificarse por las columnas
    raw = ds["payments"].to_csv(index=False).encode()
    tables = read_any(_buf(raw, "export_final_v2.csv"), "export_final_v2.csv", IngestReport())
    df = next(iter(tables.values()))
    assert guess_table("export_final_v2", df) == "payments"


def test_derived_columns_when_absent(ds):
    doctors = ds["doctors"].drop(columns=["peer_group", "hourly_rate", "expected_rate", "scenario"])
    files = {"medicos.csv": _buf(doctors.to_csv(index=False).encode(), "medicos.csv")}
    for t in ("contracts", "encounters", "payments"):
        files[f"{t}.csv"] = _buf(ds[t].to_csv(index=False).encode(), f"{t}.csv")
    data, rep = ingest(files)
    d = data["doctors"]
    assert {"peer_group", "hourly_rate", "expected_rate"} <= set(d.columns)
    assert d["expected_rate"].notna().all() and (d["expected_rate"] > 0).all()
    assert (rep.to_frame()["aspecto"] == "columna derivada").any()


def test_ingested_data_runs_the_model(ds):
    files = {f"{t}.csv": _buf(df.to_csv(index=False).encode(), f"{t}.csv") for t, df in ds.items()}
    data, _ = ingest(files)
    validate_inputs(data)
    res = run_pipeline(data=data, cfg=DEFAULT_CONFIG, output_dir=None)
    assert len(res.doctor_scores) == 10
    assert res.scored_periods["risk_score"].between(0, 100).all()
