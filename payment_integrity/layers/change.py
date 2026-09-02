"""CAPA E — Time-Series / Change Detection (el médico contra sí mismo).

Serie semanal de pacientes/hora por médico. Línea base = mediana de las
primeras ``baseline_weeks``. Se calcula EWMA y CUSUM unilateral (detecta
caídas sostenidas). El score por período mide la caída relativa del EWMA
frente a la línea base propia, reforzada si el CUSUM disparó.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import ChangeConfig


def _doctor_series(day: pd.DataFrame) -> pd.DataFrame:
    w = day.groupby(["doctor_id", "week"]).agg(
        attended=("patients_attended", "sum"), paid_hours=("paid_hours", "sum")
    ).reset_index()
    w = w[w["paid_hours"] > 0].copy()
    w["pph"] = w["attended"] / w["paid_hours"]
    w["period"] = w["week"].dt.to_period("M").astype(str)
    return w.sort_values(["doctor_id", "week"])


def detect_change(day: pd.DataFrame, cfg: ChangeConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    weekly = _doctor_series(day)
    rows = []
    for doc, g in weekly.groupby("doctor_id", sort=False):
        pph = g["pph"].to_numpy(dtype=float)
        n = len(pph)
        nb = min(cfg.baseline_weeks, max(n // 2, 1))
        base = pph[:nb]
        baseline = float(np.median(base))
        mad = float(np.median(np.abs(base - baseline)))
        sigma = (mad / 0.6745) if mad > 0 else float(np.std(base))
        sigma = max(sigma, 0.10 * max(baseline, 1e-6))  # evita sigmas irreales en series muy estables

        ewma = np.zeros(n)
        cusum = np.zeros(n)
        alarm = np.zeros(n, dtype=bool)
        ewma[0] = pph[0]
        s = 0.0
        for i in range(n):
            if i > 0:
                ewma[i] = cfg.ewma_alpha * pph[i] + (1 - cfg.ewma_alpha) * ewma[i - 1]
            zi = (baseline - pph[i]) / sigma           # positivo cuando cae
            s = max(0.0, s + zi - cfg.cusum_drift)
            cusum[i] = s
            alarm[i] = s > cfg.cusum_threshold
        rel = (ewma - baseline) / max(baseline, 1e-6)
        gg = g.copy()
        gg["baseline_pph"] = baseline
        gg["ewma_pph"] = ewma
        gg["rel_change"] = rel
        gg["cusum"] = cusum
        gg["cusum_alarm"] = alarm
        gg["is_baseline"] = np.arange(n) < nb
        rows.append(gg)
    weekly = pd.concat(rows, ignore_index=True) if rows else weekly

    per = weekly.groupby(["doctor_id", "period"]).agg(
        baseline_pph=("baseline_pph", "first"),
        ewma_pph=("ewma_pph", "last"),
        rel_change=("rel_change", "mean"),
        cusum_alarm=("cusum_alarm", "any"),
        is_baseline=("is_baseline", "all"),
    ).reset_index()
    drop = (-per["rel_change"]).clip(lower=0) / cfg.drop_saturation
    per["change_risk"] = (100 * drop.clip(0, 1) * np.where(per["cusum_alarm"], 1.0, 0.5)).round(2)
    per.loc[per["is_baseline"], "change_risk"] = 0.0   # no se evalúa contra sí mismo durante la línea base
    return per, weekly
