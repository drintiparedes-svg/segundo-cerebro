"""CAPA D — Modelo supervisado (se habilita cuando existen auditorías cerradas).

Entrena un gradient boosting (HistGradientBoostingClassifier, tolera NaN) sobre
las variables del médico-período usando como etiqueta el resultado de auditoría
(1 = pago indebido / abuso / fraude confirmado; 0 = normal / error
administrativo). Devuelve probabilidad para todos los médico-períodos, métricas
de validación cruzada e importancias por permutación. Con pocas etiquetas el
resultado es orientativo y así se informa.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

FEATURES = (
    "paid_hours", "contracted_hours", "patients_per_hour", "performance_ratio", "utilization", "idle_hours_ratio",
    "cost_per_patient", "no_show_ratio", "mean_duration_min", "off_schedule_encounters", "overlapping_encounters",
    "encounters_without_login", "duplicate_patient_days", "overpaid_days_ratio", "duplicate_payments",
    "empty_paid_blocks_ratio", "edge_concentration", "improbable_duration_ratio", "missing_record_ratio",
    "retro_record_ratio", "paid_vs_contracted_ratio", "peer_deviation", "rel_change",
    "contract_risk", "activity_risk", "productivity_risk", "peer_risk", "anomaly_risk",
)
MIN_LABELS = 20
MIN_PER_CLASS = 5


@dataclass
class SupervisedResult:
    enabled: bool
    message: str
    n_labels: int = 0
    n_positive: int = 0
    cv_auc: float | None = None
    cv_average_precision: float | None = None
    importances: pd.DataFrame = field(default_factory=pd.DataFrame)
    predictions: pd.DataFrame = field(default_factory=pd.DataFrame)   # doctor_id, period, supervised_prob
    features_used: tuple = ()


def train_supervised(scored: pd.DataFrame, labels: pd.DataFrame, random_state: int = 42) -> SupervisedResult:
    if labels is None or len(labels) == 0:
        return SupervisedResult(False, "Sin auditorías cerradas: la capa supervisada permanece inactiva.")
    feats = [f for f in FEATURES if f in scored.columns]
    key = ["doctor_id", "period"]
    lab = labels[key + ["label"]].drop_duplicates(key)
    train = scored[key + feats].merge(lab, on=key, how="inner")
    n, npos = len(train), int(train["label"].sum())
    if n < MIN_LABELS or npos < MIN_PER_CLASS or (n - npos) < MIN_PER_CLASS:
        return SupervisedResult(False, f"Etiquetas insuficientes ({n} casos, {npos} positivos). "
                                       f"Se requieren ≥ {MIN_LABELS} casos con ≥ {MIN_PER_CLASS} por clase.", n, npos)

    X, y = train[feats].astype(float), train["label"].to_numpy()
    # hiperparámetros adaptados al tamaño de la muestra: con pocas auditorías, árboles muy
    # pequeños y hojas de pocos casos (el valor por defecto de 20 impediría cualquier partición)
    small = n < 100
    clf = HistGradientBoostingClassifier(
        max_depth=2 if small else 3, learning_rate=0.1 if small else 0.08, max_iter=60 if small else 200,
        min_samples_leaf=max(2, int(0.1 * n)), l2_regularization=1.0, early_stopping=False,
        random_state=random_state, class_weight="balanced")
    k = int(min(5, npos, n - npos))
    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=random_state)
    proba_cv = cross_val_predict(clf, X, y, cv=cv, method="predict_proba")[:, 1]
    auc = float(roc_auc_score(y, proba_cv))
    ap = float(average_precision_score(y, proba_cv))

    clf.fit(X, y)
    imp = permutation_importance(clf, X, y, n_repeats=10, random_state=random_state, scoring="roc_auc")
    importances = pd.DataFrame({"feature": feats, "importance": imp.importances_mean, "std": imp.importances_std}) \
        .sort_values("importance", ascending=False).reset_index(drop=True)

    preds = scored[key].copy()
    preds["supervised_prob"] = clf.predict_proba(scored[feats].astype(float))[:, 1]
    preds["in_training_set"] = preds.set_index(key).index.isin(train.set_index(key).index)
    msg = (f"Modelo entrenado con {n} auditorías cerradas ({npos} positivas). AUC validación cruzada {auc:.2f}, "
           f"precisión media {ap:.2f} ({k} folds). " + ("Muestra pequeña: use la probabilidad como apoyo, no como criterio." if n < 60 else ""))
    return SupervisedResult(True, msg, n, npos, auc, ap, importances, preds, tuple(feats))
