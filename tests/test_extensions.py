"""Calidad de datos, gestión de casos, capa supervisada y capa de grafos."""
import dataclasses

import pandas as pd
import pytest

from payment_integrity import run_pipeline, generate_synthetic, DEFAULT_CONFIG
from payment_integrity.config import SyntheticConfig
from payment_integrity.quality import assess, blocking, ERROR
from payment_integrity.casework import CaseStore, simulate_labels_from_scenarios, POSITIVE_OUTCOMES
from payment_integrity.pipeline import apply_supervised
from payment_integrity.layers.graph import ego_network
from payment_integrity.reporting import build_report, to_excel_bytes


@pytest.fixture(scope="module")
def cfg():
    return dataclasses.replace(DEFAULT_CONFIG, synthetic=SyntheticConfig(n_doctors=40, n_weeks=16, seed=11))


@pytest.fixture(scope="module")
def data(cfg):
    return generate_synthetic(cfg.synthetic).as_dict()


@pytest.fixture(scope="module")
def result(data, cfg):
    return run_pipeline(data=data, cfg=cfg, output_dir=None)


def test_quality_clean_and_blocking(data):
    q = assess(data)
    assert not blocking(q)
    broken = {k: v.copy() for k, v in data.items()}
    broken["encounters"].loc[:5, "doctor_id"] = "NOEXISTE"
    q2 = assess(broken)
    assert blocking(q2)
    assert (q2[q2["severidad"] == ERROR]["check"].str.contains("doctor_id no existe")).any()


def test_graph_layer_detects_network(result, data):
    truth = data["doctors"]
    net = set(truth.loc[truth["scenario"] == "network_billing", "doctor_id"])
    assert len(net) == 2
    gm = result.graph_metrics
    top = gm.groupby("doctor_id")["graph_risk"].max().sort_values(ascending=False)
    assert net.issubset(set(top.head(2).index))
    assert (gm[gm["doctor_id"].isin(net)]["simultaneous_encounters"] > 0).any()
    normal = gm[~gm["doctor_id"].isin(set(truth.loc[truth["scenario"] != "normal", "doctor_id"]))]
    assert normal["graph_risk"].median() < 15
    nodes, edges = ego_network(result.graph, next(iter(net)), gm["period"].max())
    assert len(nodes) >= 2 and len(edges) >= 1
    assert "graph_risk" in result.scored_periods.columns
    esc = result.scored_periods[result.scored_periods["doctor_id"].isin(net)]["escalated_by"]
    assert esc.str.contains("G01").any()


def test_casework_and_supervised(result, data, tmp_path):
    store = CaseStore(tmp_path / "cases.db")
    run_id = store.record_run(result, DEFAULT_CONFIG, source="test")
    assert len(store.runs()) == 1 and store.runs().iloc[0]["run_id"] == run_id
    store.record_decision("MED0001", "2026-03", "EN_REVISION", auditor="qa")
    with pytest.raises(ValueError):
        store.record_decision("MED0001", "2026-03", "CERRADO")
    store.record_decision("MED0001", "2026-03", "CERRADO", "NORMAL", auditor="qa")
    assert len(store.history()) == 2 and len(store.decisions()) == 1
    assert store.labels().iloc[0]["label"] == 0

    sup0 = apply_supervised(result.scored_periods, result.doctor_scores, store.labels())
    assert not sup0.enabled

    sim = simulate_labels_from_scenarios(result.doctor_scores, data["doctors"], top_n=30)
    sim = pd.concat([sim, pd.DataFrame({  # más negativos desde médicos normales de la cola
        "doctor_id": result.doctor_scores["doctor_id"].tail(10), "period": result.doctor_scores["worst_period"].tail(10),
        "outcome": "NORMAL", "comment": "simulado"})])
    store.import_labels(sim)
    lab = store.labels()
    assert lab["label"].sum() >= 5 and (lab["label"] == 0).sum() >= 5
    sup = apply_supervised(result.scored_periods, result.doctor_scores, lab)
    assert sup.enabled and sup.cv_auc is not None and 0 <= sup.cv_auc <= 1
    assert "supervised_prob" in result.scored_periods.columns
    assert result.doctor_scores["supervised_prob_max"].between(0, 1).all()
    assert len(sup.importances) > 5


def test_report_with_graph_and_excel(result):
    b = build_report(result, DEFAULT_CONFIG, min_level=2, top_n=15)
    assert "pacientes_compartidos_ratio" in b.findings.columns
    assert "<svg" in b.html
    x = to_excel_bytes(b, result)
    assert x[:2] == b"PK" and len(x) > 10_000
