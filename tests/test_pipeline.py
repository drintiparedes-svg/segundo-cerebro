"""Pruebas de integridad del Payment Integrity Engine sobre data sintética reducida."""
import dataclasses

import pandas as pd
import pytest

from payment_integrity import run_pipeline, generate_synthetic, DEFAULT_CONFIG
from payment_integrity.config import SyntheticConfig
from payment_integrity.features import build_day_features, build_period_features
from payment_integrity.layers.rules import RULES, apply_rules


@pytest.fixture(scope="module")
def small_cfg():
    return dataclasses.replace(DEFAULT_CONFIG, synthetic=SyntheticConfig(n_doctors=40, n_weeks=16, seed=7))


@pytest.fixture(scope="module")
def result(small_cfg):
    return run_pipeline(cfg=small_cfg, output_dir=None)


def test_outputs_have_expected_shape(result):
    assert len(result.doctor_scores) == 40
    assert set(["risk_score", "risk_level", "explanation"]).issubset(result.scored_periods.columns)
    assert result.scored_periods["risk_score"].between(0, 100).all()
    assert result.scored_periods["risk_level"].between(0, 4).all()


def test_injected_scenarios_rank_first(result):
    v = result.validation
    assert v is not None
    assert v["precision_at_k"] >= 0.8
    assert v["normal_in_level_ge3"] == 0.0


def test_rules_matrix_covers_all_rules(result):
    cols = set(result.scored_periods.columns)
    for r in RULES:
        assert f"{r.code}_flag" in cols and f"{r.code}_intensity" in cols


def test_reconciliation_amounts_consistent(result):
    r = result.reconciliation
    assert (r["amount_at_risk"] >= 0).all()
    assert (r["idle_hours"] <= r["paid_hours"] + 1e-9).all()


def test_optional_tables_can_be_missing(small_cfg):
    data = generate_synthetic(small_cfg.synthetic).as_dict()
    data.pop("sessions")
    data.pop("schedule")
    day = build_day_features(data)
    period = build_period_features(day)
    matrix, alerts = apply_rules(period, small_cfg.rules)
    assert matrix["R05_intensity"].isna().all()          # sin login no hay R05
    assert period["no_show_ratio"].isna().all()           # sin agenda no hay no-show
    res = run_pipeline(data=data, cfg=small_cfg, output_dir=None)
    assert len(res.doctor_scores) == 40


def test_missing_required_table_raises(small_cfg):
    data = generate_synthetic(small_cfg.synthetic).as_dict()
    data.pop("payments")
    with pytest.raises(ValueError):
        build_day_features(data)


def test_explanations_are_actionable(result):
    top = result.doctor_scores.iloc[0]
    assert "Riesgo" in top["explanation"]
    assert "/100" in top["explanation"]
