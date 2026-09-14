"""Fase D — lente financiera: presupuesto desde la hoja «Presupuesto»,
ejecución, unidades económicas, impacto, alertas e informe."""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro import finance
from segundo_cerebro.models import KnowledgeObject
from segundo_cerebro.projects import Project, load_projects
from segundo_cerebro.store import BrainStore
from segundo_cerebro.webapi import dispatch

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def store(tmp_path):
    s = BrainStore(tmp_path / "b.db")
    yield s
    s.close()


def _budget_xlsx(path: Path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Portada"
    ws.append(["", "PLAN DE TRABAJO"])
    ws = wb.create_sheet("Presupuesto")
    ws.append(["", "PRESUPUESTO ESTIMADO DEL PROYECTO"])
    ws.append(["", "Fase", "Ítem", "Unidad/Detalle", "Costo Unit. (CLP)", "Cantidad", "Total (CLP)"])
    ws.append(["", "F1", "Incentivos entrevistas", "Voucher × 14", 5000, 14, 70000])
    ws.append(["", "F1", "Software transcripción", "1 mes", 30000, 1, 30000])
    ws.append(["", "F2", "Materiales prototipos", "Lote de 4", 30000, 4, None])   # total se calcula
    ws.append(["", "F3", "Impresión informe", "Por copia", 8500, 3, 25500])
    ws.append(["", "Subtotal antes de contingencia", "", "", "", "", 245500])
    ws.append(["", "Contingencia (10%)", "", "", "", "", 24550])
    ws.append(["", "TOTAL ESTIMADO DEL PROYECTO", "", "", "", "", 270050])
    wb.save(path)


def test_parse_budget_sheet_and_totals(tmp_path):
    xlsx = tmp_path / "plan.xlsx"
    _budget_xlsx(xlsx)
    b = finance.parse_budget_xlsx(xlsx)
    assert b["sheet"] == "Presupuesto" and len(b["items"]) == 4
    assert b["items"][2]["total"] == 120000.0, "unit × qty cuando falta el total"
    assert b["subtotal"] == 245500 and b["contingency"] == 24550 and b["total"] == 270050
    assert finance._num("$1.234.567") == 1234567.0 and finance._num("1,234,567.5") == 1234567.5
    assert finance._num("30000,50") == 30000.5 and finance._num("x") is None


def test_unit_economics_impact_alerts_and_report(store, tmp_path):
    xlsx = tmp_path / "plan.xlsx"
    _budget_xlsx(xlsx)
    project = Project(id="tesis", name="MSc Thesis", area="academia",
                      units=[{"name": "kit", "volume": 100}, {"name": "tamizada", "volume": 50, "price": 8000, "fixed_cost": 100000, "variable_cost": 5000}],
                      benefits=[{"name": "ahorro", "value_clp": 40000, "per": "month", "basis": "test"}])
    budget = finance.import_budget(tmp_path, "tesis", xlsx)
    assert (tmp_path / "finance" / "tesis" / "budget.json").exists()
    actuals_csv = tmp_path / "gasto.csv"
    actuals_csv.write_text("fecha,item,fase,monto\n2026-05-01,Incentivos,F1,95000\n2026-06-01,Software,F1,1000\n2026-07-01,Materiales,F2,20000\n", encoding="utf-8")
    actuals = finance.import_actuals(tmp_path, "tesis", actuals_csv)
    assert actuals["total"] == 116000.0 and len(actuals["rows"]) == 3

    indicators = {"values": {"dolar": {"value": 1000.0}, "uf": {"value": 40000.0}}}
    ue = finance.unit_economics(project, budget, actuals, indicators)
    assert ue["execution_pct"] == 43 and ue["remaining"] == 154050.0
    assert ue["by_phase"]["F1"]["execution_pct"] == 96 and ue["by_phase"]["F3"]["execution_pct"] == 0
    kit = ue["units"][0]
    assert kit["cost_planned"] == 2700.5 and kit["cost_real"] == 1160.0 and kit["deviation_pct"] == -57
    tam = ue["units"][1]
    assert tam["breakeven_units"] == 33 and tam["margin_pct"] == 38
    assert ue["budget_usd"] == 270.05 and ue["budget_uf"] == 6.75

    imp = finance.impact(project, budget)
    assert imp["annual_benefit"] == 480000 and imp["net"] == 209950 and imp["roi_pct"] == 78
    assert imp["payback_months"] == 6.8 and len(imp["sensitivity"]) == 4
    assert imp["sensitivity"][2]["scenario"] == "costo +20 %" and imp["sensitivity"][2]["cost"] == 324060

    store.add_knowledge_object(KnowledgeObject(id="ko-fund-1", ko_type="opportunity", title="Fondecyt",
                                               statement="x", date="2026-09-01", project="MSc Thesis",
                                               valid_to="2026-09-20", tags=["proyecto:tesis"]))
    al = finance.alerts(project, ue, store.list_knowledge_objects(ko_type="opportunity", limit=5), today=date(2026, 9, 14))
    kinds = [a["kind"] for a in al]
    assert kinds == ["ejecución", "costo unitario", "costo unitario", "financiamiento"]

    result = finance.project_finance(store, tmp_path, project, indicators, today=date(2026, 9, 14))
    md = result["markdown"]
    assert md.startswith("# Lente financiera · MSc Thesis") and "## Unidades económicas" in md
    assert "Punto de equilibrio: 33" in md and "ROI 78 %" in md and "⚠ [financiamiento] Cierra 2026-09-20" in md
    assert result["has_budget"] and result["opportunities"][0]["title"] == "Fondecyt"

    empty = finance.project_finance(store, tmp_path, Project(id="otro", name="Otro"), None)
    assert not empty["has_budget"] and "Sin presupuesto" in empty["markdown"]


def test_seed_projects_finance_fields_and_api(store, tmp_path, monkeypatch):
    projects = load_projects(REPO / "brain" / "self" / "projects.md")
    tesis = projects[0]
    assert tesis.units and tesis.units[0]["volume"] == 500 and tesis.benefits[0]["per"] == "year"
    monkeypatch.setenv("SB_PROJECTS", str(REPO / "brain" / "self" / "projects.md"))
    st, res = dispatch(store, "/api/finance", {"project": "tesis"})
    assert st == 200 and res["projects"][0]["project"]["id"] == "tesis"
    assert res["projects"][0]["has_budget"] is False and res["indicators"] == {}
