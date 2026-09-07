"""CAPA 3 — Provider Profiling (médico vs pares clínicamente equivalentes).

Usa z-score robusto basado en MAD (Median Absolute Deviation) dentro de cada
``peer_group`` y período, más percentiles dentro del grupo para la narrativa.
Se prefiere MAD/percentiles frente al z-score clásico porque las
distribuciones de productividad clínica son sesgadas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import PeerConfig

MAD_CONST = 0.6745  # hace el MAD comparable a la desviación estándar bajo normalidad


def _robust_z(x: pd.Series) -> pd.Series:
    med = x.median()
    mad = (x - med).abs().median()
    if not np.isfinite(mad) or mad == 0:
        # MAD nulo (grupo homogéneo): recurre al IQR; si también es nulo, sin desviación
        q1, q3 = x.quantile(0.25), x.quantile(0.75)
        iqr = q3 - q1
        if not np.isfinite(iqr) or iqr == 0:
            return pd.Series(0.0, index=x.index)
        return (x - med) / (iqr / 1.349)
    return MAD_CONST * (x - med) / mad


def profile_peers(period: pd.DataFrame, cfg: PeerConfig) -> pd.DataFrame:
    out = period[["doctor_id", "period", "peer_group"]].copy()
    grp = period.groupby(["peer_group", "period"])
    out["peer_size"] = grp["doctor_id"].transform("count")

    risk_cols = []
    for m in cfg.metrics:
        if m not in period.columns or period[m].isna().all():
            continue
        z = grp[m].transform(_robust_z)
        pct = grp[m].rank(pct=True)
        out[f"{m}_z"] = z
        out[f"{m}_pct"] = pct
        # desviación en la dirección de riesgo, saturada
        directional = (z * cfg.risk_direction.get(m, 1)).clip(lower=0) / cfg.z_saturation
        out[f"{m}_risk"] = directional.clip(0, 1).fillna(0)
        risk_cols.append(f"{m}_risk")

    if risk_cols:
        r = out[risk_cols]
        out["peer_deviation"] = out[[c for c in out.columns if c.endswith("_z")]].abs().mean(axis=1).fillna(0)
        out["peer_risk"] = 100 * (0.6 * r.max(axis=1) + 0.4 * r.mean(axis=1))
    else:
        out["peer_deviation"] = 0.0
        out["peer_risk"] = 0.0
    # con pocos pares la comparación no es confiable: se atenúa y se marca
    small = out["peer_size"] < cfg.min_peer_size
    out["peer_reliable"] = ~small
    out.loc[small, "peer_risk"] *= 0.5
    return out
