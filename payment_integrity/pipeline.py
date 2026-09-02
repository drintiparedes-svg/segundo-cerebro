"""Orquestación del Payment Integrity Engine.

    from payment_integrity import run_pipeline
    result = run_pipeline()                     # data proxy sintética
    result = run_pipeline(data=my_tables)       # data real (dict de DataFrames)

Cada corrida deja trazabilidad completa en ``output/``: features, alertas por
regla, conciliación, perfiles de pares, scores de anomalía, series de cambio,
scores finales y reporte de auditoría.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

from .config import DEFAULT_CONFIG, EngineConfig
from .features import build_day_features, build_period_features, PERIOD_FEATURE_DICTIONARY
from .layers.reconciliation import reconcile
from .layers.rules import apply_rules, dimension_scores
from .layers.peer import profile_peers
from .layers.anomaly import detect_anomalies
from .layers.change import detect_change
from .scoring import assemble, doctor_summary, DIMENSIONS, DIMENSION_LABELS
from . import synthetic


@dataclass
class PipelineResult:
    day_features: pd.DataFrame
    period_features: pd.DataFrame
    reconciliation: pd.DataFrame
    alerts: pd.DataFrame
    peer_profiles: pd.DataFrame
    anomalies: pd.DataFrame
    change_weekly: pd.DataFrame
    scored_periods: pd.DataFrame
    doctor_scores: pd.DataFrame
    validation: dict | None

    def tables(self) -> dict[str, pd.DataFrame]:
        return {k: v for k, v in asdict(self).items() if isinstance(v, pd.DataFrame)}


def run_pipeline(data: dict[str, pd.DataFrame] | None = None, cfg: EngineConfig = DEFAULT_CONFIG,
                 output_dir: str | Path | None = "output") -> PipelineResult:
    if data is None:
        data = synthetic.generate(cfg.synthetic).as_dict()

    day = build_day_features(data, cfg.rules.improbable_duration_min, cfg.rules.retro_record_hours)
    period = build_period_features(day)

    recon = reconcile(period)                                   # capa 1
    peer = profile_peers(period, cfg.peer)                      # capa 3 (antes que la 4: alimenta peer_deviation)
    z_cols = [c for c in peer.columns if c.endswith("_z")] + ["peer_deviation"]
    period_anom = period.merge(peer[["doctor_id", "period"] + z_cols], on=["doctor_id", "period"])
    rule_matrix, alerts = apply_rules(period, cfg.rules)        # capa 2
    rule_dims = dimension_scores(rule_matrix)
    anomalies = detect_anomalies(period_anom, cfg.anomaly)      # capa 4
    change, change_weekly = detect_change(day, cfg.change)      # capa E
    scored = assemble(period, recon, rule_matrix, rule_dims, peer, anomalies, change, cfg.scoring)  # capa 5
    doctors = doctor_summary(scored, cfg.scoring)

    validation = None
    if "scenario" in data["doctors"].columns:
        validation = validate(doctors, data["doctors"])

    result = PipelineResult(day, period, recon, alerts, peer, anomalies, change_weekly, scored, doctors, validation)
    if output_dir is not None:
        export(result, Path(output_dir), cfg)
    return result


def validate(doctors: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """Evalúa contra los escenarios inyectados (solo posible con data sintética o auditorías cerradas)."""
    d = doctors.merge(truth[["doctor_id", "scenario"]], on="doctor_id")
    d["injected"] = d["scenario"] != "normal"
    k = int(d["injected"].sum())
    top_k = d.head(k)
    out = {
        "n_doctors": int(len(d)),
        "n_injected": k,
        "precision_at_k": float(top_k["injected"].mean()) if k else None,
        "recall_at_k": float(top_k["injected"].sum() / k) if k else None,
        "injected_in_level_ge3": float(d.loc[d["injected"], "doctor_risk_level"].ge(3).mean()) if k else None,
        "normal_in_level_ge3": float(d.loc[~d["injected"], "doctor_risk_level"].ge(3).mean()),
        "normal_in_level_ge2": float(d.loc[~d["injected"], "doctor_risk_level"].ge(2).mean()),
        "normal_in_level_ge1": float(d.loc[~d["injected"], "doctor_risk_level"].ge(1).mean()),
        "rank_by_scenario": {
            s: [int(r) for r in (d.index[d["scenario"] == s] + 1)] for s in sorted(d["scenario"].unique()) if s != "normal"
        },
        "mean_score_injected": float(d.loc[d["injected"], "doctor_risk_score"].mean()) if k else None,
        "mean_score_normal": float(d.loc[~d["injected"], "doctor_risk_score"].mean()),
    }
    return out


def export(result: PipelineResult, out: Path, cfg: EngineConfig) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, df in result.tables().items():
        df.to_csv(out / f"{name}.csv", index=False)
    (out / "feature_dictionary.json").write_text(
        json.dumps(PERIOD_FEATURE_DICTIONARY, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "config_used.json").write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if result.validation is not None:
        (out / "validation.json").write_text(
            json.dumps(result.validation, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "audit_report.md").write_text(audit_report(result, cfg), encoding="utf-8")


def audit_report(result: PipelineResult, cfg: EngineConfig, top_n: int = 15) -> str:
    d = result.doctor_scores
    s = result.scored_periods
    lines = ["# Payment Integrity — Reporte de priorización de auditoría", ""]
    lines.append(f"Períodos analizados: {s['period'].min()} → {s['period'].max()} | "
                 f"Médicos: {d['doctor_id'].nunique()} | Médico-períodos: {len(s)}")
    lines.append("")
    lines.append("## Distribución por nivel (consolidado por médico)")
    lines.append("")
    lines.append("| Nivel | Etiqueta | Médicos |")
    lines.append("|---|---|---:|")
    counts = d["doctor_risk_level"].value_counts()
    for lvl, label in cfg.scoring.level_labels.items():
        lines.append(f"| {lvl} | {label} | {int(counts.get(lvl, 0))} |")
    lines.append("")
    lines.append(f"## Top {top_n} médicos priorizados")
    lines.append("")
    for i, row in d.head(top_n).iterrows():
        worst = s[(s["doctor_id"] == row["doctor_id"]) & (s["period"] == row["worst_period"])].iloc[0]
        lines.append(f"### {i + 1}. {row['doctor_id']} — {row['doctor_risk_score']:.0f}/100 · "
                     f"Nivel {row['doctor_risk_level']} ({row['doctor_risk_level_label']})")
        lines.append("")
        lines.append(f"Peer group: {row['peer_group']} · Peor período: {row['worst_period']} · "
                     f"Pagado total: ${row['total_paid']:,.0f} · Sin respaldo de actividad: ${row['idle_amount']:,.0f} · "
                     f"Sobre contrato/duplicado: ${row['amount_at_risk']:,.0f}")
        lines.append("")
        lines.append("| Dimensión | Score |")
        lines.append("|---|---:|")
        for dim in DIMENSIONS:
            lines.append(f"| {DIMENSION_LABELS[dim]} | {worst[dim]:.0f}/100 |")
        lines.append(f"| **Risk Score ({row['worst_period']})** | **{worst['risk_score']:.0f}/100** |")
        lines.append("")
        lines.append(f"> {worst['explanation']}")
        lines.append("")
    if result.validation:
        v = result.validation
        lines.append("## Validación contra escenarios inyectados (solo data sintética)")
        lines.append("")
        lines.append(f"- Precision@k (k={v['n_injected']}): {v['precision_at_k']:.2f}")
        lines.append(f"- Médicos inyectados en nivel ≥ 3: {v['injected_in_level_ge3']:.0%}")
        lines.append(f"- Médicos normales en nivel ≥ 3 (falsos positivos): {v['normal_in_level_ge3']:.1%}")
        lines.append(f"- Médicos normales en nivel ≥ 2 / ≥ 1: {v['normal_in_level_ge2']:.1%} / {v['normal_in_level_ge1']:.1%}")
        lines.append(f"- Score medio inyectados vs normales: {v['mean_score_injected']:.1f} vs {v['mean_score_normal']:.1f}")
        lines.append("- Ranking por escenario: " + "; ".join(f"{k} → {vv}" for k, vv in v["rank_by_scenario"].items()))
        lines.append("")
    return "\n".join(lines)
