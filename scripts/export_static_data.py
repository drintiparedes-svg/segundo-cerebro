"""Exporta los resultados del modelo (data de demostración) a JSON para el sitio estático (web/)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from payment_integrity import run_pipeline, DEFAULT_CONFIG  # noqa: E402
from payment_integrity.layers.rules import RULES  # noqa: E402
from payment_integrity.reporting import build_report  # noqa: E402
from payment_integrity.scoring import DIMENSIONS, DIMENSION_LABELS  # noqa: E402


def main(out: Path) -> None:
    res = run_pipeline(output_dir=None)
    s = res.scored_periods
    keep = ["doctor_id", "period", "peer_group", "risk_score", "risk_level", "risk_level_label", "escalated_by", "explanation",
            "paid_hours", "contracted_hours", "idle_hours", "idle_hours_ratio", "patients_attended", "patients_per_hour",
            "expected_rate", "performance_ratio", "utilization", "cost_per_patient", "no_show_ratio", "mean_duration_min",
            "total_paid", "idle_amount", "amount_at_risk", "rel_change", "cusum_alarm", "baseline_pph", "ewma_pph",
            "peer_size", "shared_patient_ratio", "simultaneous_encounters", "strongest_link", "graph_explanation",
            "anomaly_top_features", "rules_triggered"] + list(DIMENSIONS) + [f"{r.code}_intensity" for r in RULES]
    keep = [c for c in keep if c in s.columns]
    data = {
        "generated_for": "demo sintética",
        "periods": sorted(s["period"].unique()),
        "dimensions": list(DIMENSIONS),
        "dimension_labels": DIMENSION_LABELS,
        "level_labels": DEFAULT_CONFIG.scoring.level_labels,
        "weights": DEFAULT_CONFIG.scoring.weights,
        "rules": [{"code": r.code, "name": r.name, "dimension": r.dimension, "critical": r.critical} for r in RULES],
        "doctor_scores": json.loads(res.doctor_scores.round(4).to_json(orient="records")),
        "scored_periods": json.loads(s[keep].round(4).to_json(orient="records")),
        "change_weekly": json.loads(res.change_weekly.assign(week=res.change_weekly["week"].dt.strftime("%Y-%m-%d"))
                                    [["doctor_id", "week", "pph", "baseline_pph", "ewma_pph", "cusum_alarm"]].round(3).to_json(orient="records")),
        "graph_edges": json.loads(res.graph_edges[res.graph_edges["shared_patients"] >= 2].to_json(orient="records")),
        "alerts": json.loads(res.alerts[["doctor_id", "period", "rule", "rule_name", "detail", "intensity"]].to_json(orient="records")),
        "validation": res.validation,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (out / "informe.html").write_text(build_report(res, DEFAULT_CONFIG, min_level=3, top_n=20).html, encoding="utf-8")
    print(f"data.json: {(out / 'data.json').stat().st_size / 1024:.0f} KB · registros médico-período: {len(s)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "web")
