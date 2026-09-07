"""CAPA 5 — Risk Scoring compuesto, clasificación por niveles y explicación.

RiskScore = w1·ContractRisk + w2·ActivityRisk + w3·ProductivityRisk + w4·PeerRisk + w5·AnomalyRisk

Cada dimensión está en 0-100. El resultado es un score de *riesgo de pago
indebido*, no una imputación de culpabilidad: la escala de niveles termina en
"requiere auditoría"; el fraude solo se confirma tras investigación.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ScoringConfig
from .layers.rules import RULES

DIMENSIONS = ("contract_risk", "activity_risk", "productivity_risk", "peer_risk", "anomaly_risk", "graph_risk")
DIMENSION_LABELS = {
    "contract_risk": "Inconsistencia contractual",
    "activity_risk": "Horas sin actividad / integridad del registro",
    "productivity_risk": "Rendimiento anómalo",
    "peer_risk": "Diferencia frente a pares",
    "anomaly_risk": "Anomaly detection (IF + LOF)",
    "graph_risk": "Relaciones médico–paciente (grafo)",
}


GRAPH_COLS = ["shared_patient_ratio", "shared_patient_ratio_peer_median", "patient_hhi", "top5_patient_share",
              "encounters_per_patient", "frequent_patients", "shared_patients", "n_linked_doctors", "strongest_link",
              "strongest_link_shared", "strongest_link_jaccard", "simultaneous_encounters", "simultaneous_patients",
              "community", "community_size", "graph_risk", "graph_explanation"]


def assemble(period: pd.DataFrame, recon: pd.DataFrame, rule_matrix: pd.DataFrame,
             rule_dims: pd.DataFrame, peer: pd.DataFrame, anomaly: pd.DataFrame,
             change: pd.DataFrame, cfg: ScoringConfig, graph: pd.DataFrame | None = None) -> pd.DataFrame:
    key = ["doctor_id", "period"]
    df = period.merge(recon[key + ["amount_at_risk", "idle_amount", "contract_intensity", "status"]], on=key)
    df = df.merge(rule_matrix, on=key).merge(rule_dims, on=key)
    df = df.merge(peer.drop(columns=["peer_group"]), on=key, how="left")
    df = df.merge(anomaly, on=key, how="left")
    df = df.merge(change[key + ["baseline_pph", "ewma_pph", "rel_change", "cusum_alarm", "change_risk"]],
                  on=key, how="left")
    if graph is not None and len(graph):
        df = df.merge(graph[key + [c for c in GRAPH_COLS if c in graph.columns]], on=key, how="left")
    else:
        df["graph_risk"] = 0.0
        df["graph_explanation"] = ""
        df["simultaneous_encounters"] = 0
    df = df.copy()

    # --- dimensiones -------------------------------------------------------------
    df["contract_risk"] = np.maximum(df["contract_risk_rules"], 100 * df["contract_intensity"]).clip(0, 100)
    df["activity_risk"] = df["activity_risk_rules"].clip(0, 100)
    change_risk = df["change_risk"].fillna(0)
    df["productivity_risk"] = np.maximum(
        df["productivity_risk_rules"], 0.7 * change_risk + 0.3 * df["productivity_risk_rules"]
    ).clip(0, 100)
    df["peer_risk"] = df["peer_risk"].fillna(0).clip(0, 100)
    df["anomaly_risk"] = df["anomaly_risk"].fillna(0).clip(0, 100)
    df["graph_risk"] = df["graph_risk"].fillna(0).clip(0, 100)
    df["graph_explanation"] = df["graph_explanation"].fillna("")
    df["simultaneous_encounters"] = df["simultaneous_encounters"].fillna(0)

    w = cfg.weights
    df["weighted_score"] = sum(df[d] * w[d] for d in DIMENSIONS).round(1)

    # escalamiento por reglas críticas (evidencia directa de pago indebido)
    crit = [r for r in RULES if r.critical]
    esc = pd.DataFrame({r.code: df[f"{r.code}_intensity"].fillna(0) >= cfg.critical_intensity for r in crit})
    esc["G01"] = df["simultaneous_encounters"] >= cfg.graph_simultaneous_critical   # mismo paciente, dos médicos, mismo instante
    df["escalated_by"] = esc.apply(lambda row: ", ".join(c for c in esc.columns if row[c]), axis=1)
    # sobre el piso, el score conserva el orden del puntaje ponderado: piso + ponderado·(100-piso)/100
    escalated = cfg.critical_floor + df["weighted_score"] * (100 - cfg.critical_floor) / 100
    df["risk_score"] = np.where(esc.any(axis=1), np.maximum(escalated, df["weighted_score"]),
                                df["weighted_score"]).round(1)
    df["risk_level"] = df["risk_score"].apply(lambda s: _level(s, cfg))
    df["risk_level_label"] = df["risk_level"].map(cfg.level_labels)
    df["top_drivers"] = df.apply(_top_drivers, axis=1)
    df["explanation"] = df.apply(_explain, axis=1)
    return df


def _level(score: float, cfg: ScoringConfig) -> int:
    for lvl, (lo, hi) in cfg.level_cuts.items():
        if lo <= score < hi:
            return lvl
    return 4


def _top_drivers(row: pd.Series) -> str:
    vals = sorted(((row[d], d) for d in DIMENSIONS), reverse=True)
    return "; ".join(f"{DIMENSION_LABELS[d]} {v:.0f}/100" for v, d in vals[:3] if v > 0)


def _pct_text(row: pd.Series, col: str) -> str | None:
    p = row.get(f"{col}_pct")
    if p is None or pd.isna(p):
        return None
    return f"percentil {min(99, int(round(p * 100)))}"


def _explain(row: pd.Series) -> str:
    parts = [f"Riesgo {row['risk_level_label'].lower()} — {row['risk_score']:.0f}/100."]

    # comparación con pares
    if row.get("peer_reliable", False):
        cpp = _pct_text(row, "cost_per_patient")
        pph = _pct_text(row, "patients_per_hour")
        if cpp and row.get("cost_per_patient_pct", 0) >= 0.90:
            parts.append(f"Médico en {cpp} de costo por paciente dentro de su peer group "
                         f"({row['peer_group']}, n={int(row['peer_size'])}).")
        elif pph and row.get("patients_per_hour_pct", 1) <= 0.10:
            parts.append(f"Rendimiento en {pph} (más bajo) de su peer group "
                         f"({row['peer_group']}, n={int(row['peer_size'])}).")

    # actividad
    if row["idle_hours_ratio"] >= 0.25:
        parts.append(f"El {row['idle_hours_ratio']:.0%} de las horas pagadas no presenta actividad clínica "
                     f"registrada ({row['idle_hours']:.1f} h; ${row['idle_amount']:,.0f} sin respaldo).")
    if row.get("empty_paid_blocks", 0) >= 1:
        parts.append(f"Se identificaron {int(row['empty_paid_blocks'])} bloques remunerados sin pacientes atendidos.")

    # cambio vs histórico propio
    rel = row.get("rel_change")
    if rel is not None and not pd.isna(rel) and rel <= -0.25 and not row.get("is_baseline", False):
        parts.append(f"El rendimiento cayó {abs(rel):.0%} respecto de su propio histórico "
                     f"({row['baseline_pph']:.1f} → {row['ewma_pph']:.1f} pac/h)"
                     + (", con señal CUSUM de cambio sostenido." if row.get("cusum_alarm") else "."))

    # contrato / pagos
    if row.get("amount_at_risk", 0) > 0:
        parts.append(f"Pagos sobre contrato o duplicados por ${row['amount_at_risk']:,.0f}.")

    # reglas activas
    if row.get("escalated_by"):
        parts.append(f"Caso escalado a nivel ≥ 3 por regla crítica ({row['escalated_by']}).")
    fired = [r for r in RULES if row.get(f"{r.code}_flag", False)]
    if fired:
        parts.append("Reglas activadas: " + ", ".join(f"{r.code} {r.name.lower()}" for r in fired) + ".")

    # grafo
    if row.get("graph_explanation"):
        parts.append(str(row["graph_explanation"]))

    # anomalía
    if row.get("anomaly_risk", 0) >= 50:
        parts.append(f"Combinación atípica de variables según Isolation Forest/LOF "
                     f"({row.get('anomaly_top_features', '')}).")
    return " ".join(parts)


def doctor_summary(scored: pd.DataFrame, cfg: ScoringConfig) -> pd.DataFrame:
    """Consolidado por médico: score máximo, medio, último nivel y monto acumulado en riesgo."""
    scored = scored.sort_values(["doctor_id", "period"])
    g = scored.groupby("doctor_id")
    s = g.agg(
        peer_group=("peer_group", "first"),
        periods=("period", "count"),
        risk_score_max=("risk_score", "max"),
        risk_score_mean=("risk_score", "mean"),
        risk_score_last=("risk_score", "last"),
        worst_period=("period", lambda p: p.iloc[int(np.argmax(scored.loc[p.index, "risk_score"].to_numpy()))]),
        total_paid=("total_paid", "sum"),
        idle_amount=("idle_amount", "sum"),
        amount_at_risk=("amount_at_risk", "sum"),
        rules_triggered_total=("rules_triggered", "sum"),
    ).reset_index()
    # score consolidado: máx(0.75·peor período + 0.25·promedio, último período).
    # La persistencia pesa (un mes aislado no condena) y la recencia manda (un cambio
    # reciente de comportamiento no se diluye en un historial largo y normal).
    s["doctor_risk_score"] = np.maximum(
        0.75 * s["risk_score_max"] + 0.25 * s["risk_score_mean"], s["risk_score_last"]
    ).round(1)
    s["doctor_risk_level"] = s["doctor_risk_score"].apply(lambda x: _level(x, cfg))
    s["doctor_risk_level_label"] = s["doctor_risk_level"].map(cfg.level_labels)
    worst = scored.loc[scored.groupby("doctor_id")["risk_score"].idxmax(), ["doctor_id", "explanation", "top_drivers"]]
    s = s.merge(worst, on="doctor_id")
    return s.sort_values("doctor_risk_score", ascending=False).reset_index(drop=True)
