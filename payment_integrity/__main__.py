"""CLI:  python -m payment_integrity [--input DIR] [--output DIR] [--synthetic-out DIR]"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import run_pipeline, generate_synthetic
from .config import DEFAULT_CONFIG

TABLES = ("doctors", "contracts", "schedule", "encounters", "sessions", "payments")


def load_inputs(folder: Path) -> dict[str, pd.DataFrame]:
    data = {}
    for t in TABLES:
        f = folder / f"{t}.csv"
        if f.exists():
            data[t] = pd.read_csv(f)
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="Payment Integrity Engine")
    ap.add_argument("--input", help="carpeta con CSV de las tablas del modelo de datos (si se omite: data sintética)")
    ap.add_argument("--output", default="output", help="carpeta de salida")
    ap.add_argument("--synthetic-out", help="además, exporta la data sintética generada a esta carpeta")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    data = load_inputs(Path(args.input)) if args.input else None
    if data is None and args.synthetic_out:
        ds = generate_synthetic(DEFAULT_CONFIG.synthetic)
        Path(args.synthetic_out).mkdir(parents=True, exist_ok=True)
        for k, v in ds.as_dict().items():
            v.to_csv(Path(args.synthetic_out) / f"{k}.csv", index=False)
        data = ds.as_dict()

    res = run_pipeline(data=data, output_dir=args.output)
    d = res.doctor_scores
    cols = ["doctor_id", "peer_group", "doctor_risk_score", "doctor_risk_level_label", "worst_period", "amount_at_risk", "idle_amount"]
    print(d[cols].head(args.top).to_string(index=False))
    print(f"\nSalidas escritas en: {Path(args.output).resolve()}")
    if res.validation:
        v = res.validation
        print(f"Validación → precision@{v['n_injected']}: {v['precision_at_k']:.2f} | "
              f"inyectados en nivel≥3: {v['injected_in_level_ge3']:.0%} | "
              f"normales en nivel≥3: {v['normal_in_level_ge3']:.1%}")


if __name__ == "__main__":
    main()
