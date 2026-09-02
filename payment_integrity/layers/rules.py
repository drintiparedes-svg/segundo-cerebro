"""CAPA 2 — Rules Engine.

Trece reglas de negocio explícitas. Cada regla devuelve ``flag`` (bool) e
``intensity`` (0-1: 0 en el umbral, 1 en el punto de saturación ``saturation``,
que representa el valor a partir del cual la evidencia se considera máxima) y
se asigna a una dimensión del Risk Score. Las reglas cuya variable no existe en la
data real se omiten automáticamente (intensidad NaN).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from ..config import RuleThresholds


@dataclass(frozen=True)
class Rule:
    code: str
    name: str
    dimension: str            # contract_risk | activity_risk | productivity_risk
    feature: str
    threshold: Callable[[RuleThresholds], float]
    direction: int            # +1 = riesgo si feature > umbral ; -1 = riesgo si feature < umbral
    saturation: float = 1.0   # valor de la feature en que la intensidad llega a 1
    weight: float = 1.0       # peso relativo dentro de la dimensión
    fmt: str = "{:.2f}"
    critical: bool = False    # regla crítica: puede escalar el caso por sí sola (ver ScoringConfig)


RULES: tuple[Rule, ...] = (
    Rule("R01", "Horas pagadas sin actividad clínica", "activity_risk", "idle_hours_ratio",
         lambda t: t.max_idle_hours_ratio, +1, 0.60, 1.0, "{:.0%}", critical=True),
    Rule("R02", "Rendimiento incompatible con lo esperado", "productivity_risk", "performance_ratio",
         lambda t: t.min_performance_ratio, -1, 0.25, 1.0, "{:.2f}"),
    Rule("R03", "Atenciones fuera del horario contratado", "activity_risk", "off_schedule_encounters",
         lambda t: t.max_off_schedule_encounters, +1, 12, 0.8, "{:.0f}", critical=True),
    Rule("R04", "Consultas simultáneas (solapadas)", "activity_risk", "overlapping_encounters",
         lambda t: t.max_overlapping_encounters, +1, 6, 0.9, "{:.0f}", critical=True),
    Rule("R05", "Atención sin sesión activa del médico", "activity_risk", "encounters_without_login",
         lambda t: t.max_encounters_without_login, +1, 8, 0.9, "{:.0f}", critical=True),
    Rule("R06", "Mismo paciente contabilizado múltiples veces", "activity_risk", "duplicate_patient_days",
         lambda t: t.max_duplicate_patient_days, +1, 6, 0.7, "{:.0f}"),
    Rule("R07", "Horas pagadas superiores a contratadas", "contract_risk", "overpaid_days_ratio",
         lambda t: t.max_overpaid_days_ratio, +1, 0.30, 1.0, "{:.0%}", critical=True),
    Rule("R08", "Pagos duplicados", "contract_risk", "duplicate_payments",
         lambda t: t.max_duplicate_payments, +1, 3, 1.0, "{:.0f}", critical=True),
    Rule("R09", "Bloques pagados íntegros sin pacientes", "activity_risk", "empty_paid_blocks_ratio",
         lambda t: t.max_empty_paid_blocks_ratio, +1, 0.25, 1.0, "{:.0%}", critical=True),
    Rule("R10", "Actividad concentrada artificialmente en el turno", "activity_risk", "edge_concentration",
         lambda t: t.max_edge_concentration, +1, 0.95, 0.6, "{:.0%}"),
    Rule("R11", "Consultas con duración físicamente improbable", "activity_risk", "improbable_duration_ratio",
         lambda t: t.max_improbable_duration_ratio, +1, 0.30, 0.8, "{:.0%}"),
    Rule("R12", "Atenciones sin registro clínico", "activity_risk", "missing_record_ratio",
         lambda t: t.max_missing_record_ratio, +1, 0.30, 1.0, "{:.0%}", critical=True),
    Rule("R13", "Registro clínico creado retrospectivamente", "activity_risk", "retro_record_ratio",
         lambda t: t.max_retro_record_ratio, +1, 0.30, 0.7, "{:.0%}"),
)


def _intensity(x: pd.Series, thr: float, sat: float, direction: int) -> pd.Series:
    """0 en el umbral, 1 en el punto de saturación (lineal entre ambos)."""
    if direction > 0:
        sat = max(sat, thr + 1e-9)
        return ((x - thr) / (sat - thr)).clip(0, 1)
    sat = min(sat, thr - 1e-9)
    return ((thr - x) / (thr - sat)).clip(0, 1)


def apply_rules(period: pd.DataFrame, thresholds: RuleThresholds) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (matriz médico-período con columnas por regla, tabla larga de alertas)."""
    out = period[["doctor_id", "period"]].copy()
    alerts = []
    for rule in RULES:
        if rule.feature not in period.columns or period[rule.feature].isna().all():
            out[f"{rule.code}_flag"] = False
            out[f"{rule.code}_intensity"] = np.nan
            continue
        thr = rule.threshold(thresholds)
        x = period[rule.feature]
        inten = _intensity(x, thr, rule.saturation, rule.direction).where(x.notna(), np.nan)
        flag = (inten > 0).fillna(False)
        out[f"{rule.code}_flag"] = flag.astype(bool)
        out[f"{rule.code}_intensity"] = inten

        hit = period.loc[flag, ["doctor_id", "period"]].copy()
        hit["rule"] = rule.code
        hit["rule_name"] = rule.name
        hit["dimension"] = rule.dimension
        hit["feature"] = rule.feature
        hit["observed"] = x[flag].round(4)
        hit["threshold"] = thr
        hit["intensity"] = inten[flag].round(3)
        hit["detail"] = [f"{rule.name}: {rule.fmt.format(v)} (umbral {rule.fmt.format(thr)})"
                         for v in x[flag]]
        alerts.append(hit)

    out["rules_triggered"] = out[[f"{r.code}_flag" for r in RULES]].sum(axis=1)
    alerts_df = pd.concat(alerts, ignore_index=True) if alerts else pd.DataFrame(
        columns=["doctor_id", "period", "rule", "rule_name", "dimension", "feature",
                 "observed", "threshold", "intensity", "detail"])
    return out, alerts_df


def dimension_scores(rule_matrix: pd.DataFrame) -> pd.DataFrame:
    """Combina intensidades por dimensión: 0.6·máx + 0.4·media ponderada de reglas activas (0-100)."""
    res = rule_matrix[["doctor_id", "period"]].copy()
    for dim in ("contract_risk", "activity_risk", "productivity_risk"):
        cols, weights = [], []
        for r in RULES:
            if r.dimension == dim and rule_matrix[f"{r.code}_intensity"].notna().any():
                cols.append(f"{r.code}_intensity")
                weights.append(r.weight)
        if not cols:
            res[f"{dim}_rules"] = 0.0
            continue
        m = rule_matrix[cols].fillna(0.0)
        w = np.array(weights)
        weighted = m * w
        mx = weighted.max(axis=1) / w.max()
        active = (m > 0)
        mean_active = (weighted.sum(axis=1) / (active * w).sum(axis=1).replace(0, np.nan)).fillna(0)
        res[f"{dim}_rules"] = (100 * (0.6 * mx + 0.4 * mean_active)).clip(0, 100)
    return res
