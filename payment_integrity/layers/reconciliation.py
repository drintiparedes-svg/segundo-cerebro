"""CAPA 1 — Conciliación contractual.

Cruza contrato ↔ horas pagadas ↔ actividad clínica y cuantifica en CLP el
monto sin respaldo. Es la capa más explicable y la primera que un auditor
revisa; su salida alimenta ``contract_risk``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def reconcile(period: pd.DataFrame) -> pd.DataFrame:
    r = period[["doctor_id", "period", "peer_group", "days_worked", "hourly_rate",
                "contracted_hours", "paid_hours", "active_hours", "idle_hours",
                "total_paid", "expected_paid", "duplicate_payments",
                "paid_without_contract_days", "overpaid_hours"]].copy()

    r["hours_gap"] = r["paid_hours"] - r["contracted_hours"]
    r["amount_gap"] = r["total_paid"] - r["expected_paid"]
    r["overpaid_amount"] = r["overpaid_hours"] * r["hourly_rate"]
    r["idle_amount"] = r["idle_hours"] * r["hourly_rate"]           # pagado sin actividad registrada
    r["duplicate_amount"] = r["duplicate_payments"] * r["hourly_rate"] * (
        r["paid_hours"] / r["days_worked"].replace(0, np.nan)).fillna(0)
    r["amount_at_risk"] = r["overpaid_amount"] + r["duplicate_amount"]
    r["amount_at_risk_ratio"] = (r["amount_at_risk"] / r["total_paid"].replace(0, np.nan)).fillna(0)
    r["idle_amount_ratio"] = (r["idle_amount"] / r["total_paid"].replace(0, np.nan)).fillna(0)

    r["status"] = np.select(
        [r["amount_at_risk"] > 0, r["idle_amount_ratio"] > 0.35],
        ["INCONSISTENTE", "REVISAR_ACTIVIDAD"],
        default="CONCILIADO",
    )
    # intensidad 0-1: satura cuando el monto en riesgo directo alcanza 15 % del pago
    r["contract_intensity"] = (r["amount_at_risk_ratio"] / 0.15).clip(0, 1)
    return r
