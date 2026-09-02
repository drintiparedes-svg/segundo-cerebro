"""Prueba headless del tablero Streamlit con AppTest: demo → ejecutar → recorrer secciones."""
import pytest
from pathlib import Path

st = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from payment_integrity import run_pipeline, DEFAULT_CONFIG  # noqa: E402
from payment_integrity.reporting import build_report  # noqa: E402


def test_report_bundle():
    res = run_pipeline(output_dir=None)
    b = build_report(res, DEFAULT_CONFIG, min_level=3, top_n=10)
    assert 0 < len(b.findings) <= 10
    assert (b.findings["nivel"] >= 3).all()
    assert "<html" in b.html and "Resumen ejecutivo" in b.markdown
    empty = build_report(res, DEFAULT_CONFIG, min_level=4, top_n=5, peer_groups=["inexistente"])
    assert len(empty.findings) == 0 and "<html" in empty.html


def test_dashboard_runs_headless():
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app" / "dashboard.py"), default_timeout=180)
    at.run()
    assert not at.exception
    at.button(key="btn_demo").click().run()
    assert not at.exception
    at.button(key="btn_run").click().run()
    assert not at.exception
    assert at.session_state["result"] is not None
    for label in ["2 · Resumen ejecutivo", "3 · Métricas", "4 · Ficha por médico", "5 · Reportería"]:
        at.radio[0].set_value(label).run()
        assert not at.exception, f"excepción en {label}: {at.exception}"
