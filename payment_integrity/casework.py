"""Gestión de casos de auditoría y trazabilidad de corridas (SQLite).

Cada médico-período priorizado puede recibir una decisión del auditor. Las
decisiones cerradas constituyen la base etiquetada que habilita la capa
supervisada (layers/supervised.py). El almacén registra además cada corrida
del modelo con su configuración, para reproducibilidad.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

STATUSES = ("PENDIENTE", "EN_REVISION", "CERRADO")
OUTCOMES = ("NORMAL", "ERROR_ADMINISTRATIVO", "PAGO_INDEBIDO_CONFIRMADO", "ABUSO", "FRAUDE_CONFIRMADO")
POSITIVE_OUTCOMES = ("PAGO_INDEBIDO_CONFIRMADO", "ABUSO", "FRAUDE_CONFIRMADO")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    doctor_id TEXT NOT NULL,
    period TEXT NOT NULL,
    status TEXT NOT NULL,
    outcome TEXT,
    auditor TEXT,
    comment TEXT,
    risk_score REAL,
    risk_level INTEGER,
    run_id TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (doctor_id, period)
);
CREATE TABLE IF NOT EXISTS decision_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id TEXT NOT NULL,
    period TEXT NOT NULL,
    status TEXT NOT NULL,
    outcome TEXT,
    auditor TEXT,
    comment TEXT,
    risk_score REAL,
    risk_level INTEGER,
    run_id TEXT,
    recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    executed_at TEXT NOT NULL,
    source TEXT,
    n_doctors INTEGER,
    n_periods INTEGER,
    period_start TEXT,
    period_end TEXT,
    n_level3plus INTEGER,
    config_json TEXT,
    validation_json TEXT
);
"""


class CaseStore:
    def __init__(self, path: str | Path = "data/audit/cases.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    # ---- decisiones -----------------------------------------------------------------
    def record_decision(self, doctor_id: str, period: str, status: str, outcome: str | None = None,
                        auditor: str = "", comment: str = "", risk_score: float | None = None,
                        risk_level: int | None = None, run_id: str | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"estado inválido: {status}")
        if outcome is not None and outcome not in OUTCOMES:
            raise ValueError(f"resultado inválido: {outcome}")
        if status == "CERRADO" and outcome is None:
            raise ValueError("un caso CERRADO requiere resultado")
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as c:
            c.execute(
                "INSERT INTO decisions (doctor_id, period, status, outcome, auditor, comment, risk_score, risk_level, run_id, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(doctor_id, period) DO UPDATE SET status=excluded.status, "
                "outcome=excluded.outcome, auditor=excluded.auditor, comment=excluded.comment, risk_score=excluded.risk_score, "
                "risk_level=excluded.risk_level, run_id=excluded.run_id, updated_at=excluded.updated_at",
                (doctor_id, period, status, outcome, auditor, comment, risk_score, risk_level, run_id, now))
            c.execute(
                "INSERT INTO decision_history (doctor_id, period, status, outcome, auditor, comment, risk_score, risk_level, run_id, recorded_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (doctor_id, period, status, outcome, auditor, comment, risk_score, risk_level, run_id, now))

    def decisions(self) -> pd.DataFrame:
        with self._conn() as c:
            return pd.read_sql_query("SELECT * FROM decisions ORDER BY updated_at DESC", c)

    def history(self) -> pd.DataFrame:
        with self._conn() as c:
            return pd.read_sql_query("SELECT * FROM decision_history ORDER BY recorded_at DESC", c)

    def labels(self) -> pd.DataFrame:
        """Etiquetas binarias para la capa supervisada: solo casos CERRADOS con resultado."""
        d = self.decisions()
        d = d[(d["status"] == "CERRADO") & d["outcome"].notna()].copy()
        d["label"] = d["outcome"].isin(POSITIVE_OUTCOMES).astype(int)
        return d[["doctor_id", "period", "outcome", "label", "auditor", "updated_at"]]

    def import_labels(self, df: pd.DataFrame, auditor: str = "import") -> int:
        """Carga masiva de auditorías cerradas (columnas: doctor_id, period, outcome[, comment])."""
        n = 0
        for r in df.itertuples(index=False):
            outcome = getattr(r, "outcome", None)
            if outcome is None or (isinstance(outcome, float) and pd.isna(outcome)):
                continue
            comment = getattr(r, "comment", "")
            comment = "" if comment is None or (isinstance(comment, float) and pd.isna(comment)) else str(comment)
            self.record_decision(str(r.doctor_id), str(r.period), "CERRADO", str(outcome).strip().upper(), auditor, comment)
            n += 1
        return n

    # ---- corridas -------------------------------------------------------------------
    def record_run(self, result, cfg, source: str = "") -> str:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        s = result.scored_periods
        with self._conn() as c:
            c.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (run_id, datetime.now().isoformat(timespec="seconds"), source, int(s["doctor_id"].nunique()),
                 int(s["period"].nunique()), str(s["period"].min()), str(s["period"].max()),
                 int((result.doctor_scores["doctor_risk_level"] >= 3).sum()),
                 json.dumps(_cfg_dict(cfg), ensure_ascii=False, default=str),
                 json.dumps(result.validation, ensure_ascii=False) if result.validation else None))
        return run_id

    def runs(self) -> pd.DataFrame:
        with self._conn() as c:
            return pd.read_sql_query("SELECT run_id, executed_at, source, n_doctors, n_periods, period_start, period_end, n_level3plus FROM runs ORDER BY executed_at DESC", c)

    def stats(self) -> dict:
        d = self.decisions()
        return {
            "total": int(len(d)),
            "por_estado": d["status"].value_counts().to_dict() if len(d) else {},
            "por_resultado": d["outcome"].dropna().value_counts().to_dict() if len(d) else {},
            "etiquetas_positivas": int(d["outcome"].isin(POSITIVE_OUTCOMES).sum()) if len(d) else 0,
            "etiquetas_negativas": int(d["outcome"].isin(("NORMAL", "ERROR_ADMINISTRATIVO")).sum()) if len(d) else 0,
        }


def _cfg_dict(cfg) -> dict:
    import dataclasses
    return dataclasses.asdict(cfg)


def simulate_labels_from_scenarios(doctor_scores: pd.DataFrame, truth: pd.DataFrame, top_n: int = 25) -> pd.DataFrame:
    """SOLO demo: convierte los escenarios inyectados del generador sintético en auditorías cerradas
    sobre los top_n médicos priorizados, para mostrar cómo opera la capa supervisada."""
    d = doctor_scores.head(top_n).merge(truth[["doctor_id", "scenario"]], on="doctor_id")
    mapping = {
        "normal": "NORMAL", "phantom_hours": "PAGO_INDEBIDO_CONFIRMADO", "hours_overbilling": "PAGO_INDEBIDO_CONFIRMADO",
        "ghost_records": "ABUSO", "off_schedule": "PAGO_INDEBIDO_CONFIRMADO", "productivity_collapse": "ERROR_ADMINISTRATIVO",
        "network_billing": "FRAUDE_CONFIRMADO",
    }
    return pd.DataFrame({"doctor_id": d["doctor_id"], "period": d["worst_period"], "outcome": d["scenario"].map(mapping),
                         "comment": "simulado desde escenario sintético"})
