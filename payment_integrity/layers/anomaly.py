"""CAPA 4 — Detección de anomalías no supervisada.

Isolation Forest (anomalías globales, combinaciones raras de variables) +
Local Outlier Factor (anomalías respecto de los vecinos más parecidos).
Trabaja sobre z-scores robustos intra-peer-group más variables de integridad.
Ambos scores se llevan a 0-1 con umbrales robustos (mediana + k·MAD) y se
combinan 0.6 / 0.4.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler

from ..config import AnomalyConfig


def _robust_unit(raw: np.ndarray, k_low: float, k_high: float) -> np.ndarray:
    """Mapea un score crudo a 0-1 con umbrales robustos (mediana + k·MAD), sin fijar una fracción de anómalos."""
    med = np.median(raw)
    mad = np.median(np.abs(raw - med)) / 0.6745
    if not np.isfinite(mad) or mad <= 0:
        mad = np.std(raw) if np.std(raw) > 0 else 1.0
    return np.clip((raw - (med + k_low * mad)) / ((k_high - k_low) * mad), 0, 1)


def detect_anomalies(period: pd.DataFrame, cfg: AnomalyConfig) -> pd.DataFrame:
    feats = [f for f in cfg.features if f in period.columns and period[f].notna().any()]
    X = period[feats].copy()
    X = X.fillna(X.median(numeric_only=True)).fillna(0.0)
    Xs = RobustScaler().fit_transform(X)

    n = len(X)
    out = period[["doctor_id", "period"]].copy()
    if n < 10:
        out["iforest_score"] = 0.0
        out["lof_score"] = 0.0
        out["anomaly_risk"] = 0.0
        out["anomaly_top_features"] = ""
        return out

    iso = IsolationForest(
        n_estimators=cfg.n_estimators,
        contamination=cfg.contamination,
        random_state=cfg.random_state,
    ).fit(Xs)
    iso_raw = -iso.score_samples(Xs)            # mayor = más anómalo
    lof = LocalOutlierFactor(n_neighbors=min(cfg.lof_neighbors, n - 1), contamination=cfg.contamination)
    lof.fit_predict(Xs)
    lof_raw = -lof.negative_outlier_factor_      # mayor = más anómalo

    out["iforest_raw"] = iso_raw
    out["lof_raw"] = lof_raw
    out["iforest_score"] = _robust_unit(iso_raw, cfg.mad_k_low, cfg.mad_k_high)
    out["lof_score"] = _robust_unit(lof_raw, cfg.mad_k_low, cfg.mad_k_high)
    out["iforest_flag"] = iso.predict(Xs) == -1
    out["anomaly_risk"] = (100 * (0.6 * out["iforest_score"] + 0.4 * out["lof_score"])).round(2)

    # explicabilidad ligera: las 3 variables más alejadas del centro robusto por observación
    dev = np.abs(Xs)
    order = np.argsort(-dev, axis=1)[:, :3]
    out["anomaly_top_features"] = [
        ", ".join(f"{feats[j]} ({Xs[i, j]:+.1f})" for j in order[i]) for i in range(n)
    ]
    return out
