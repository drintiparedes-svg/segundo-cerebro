"""Reportería de hallazgos del Payment Integrity Engine.

Genera, a partir de un ``PipelineResult`` y filtros de negocio, un paquete de
reporte con tres formatos: Markdown (lectura/Git), HTML autocontenido
(imprimible / envío por correo) y una tabla plana de hallazgos (Sheets/Excel).
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from .config import EngineConfig
from .layers.rules import RULES
from .scoring import DIMENSIONS, DIMENSION_LABELS

LEVEL_ACTIONS = {
    0: "Sin acción.",
    1: "Monitoreo en el próximo ciclo de pago.",
    2: "Revisión administrativa de agenda, contrato y registro.",
    3: "Revisión de pagos y solicitud de descargos al profesional.",
    4: "Auditoría formal con reconstrucción de actividad y cruce de fuentes.",
}


@dataclass
class ReportBundle:
    title: str
    generated_at: str
    filters: dict
    summary: dict
    findings: pd.DataFrame       # una fila por médico priorizado
    alerts: pd.DataFrame         # alertas por regla de los médicos priorizados
    markdown: str
    html: str


def _fmt_clp(x: float) -> str:
    return f"${x:,.0f}".replace(",", ".")


def _pct(x: float) -> str:
    return "n/d" if pd.isna(x) else f"{x:.0%}"


def build_report(result, cfg: EngineConfig, min_level: int = 3, top_n: int = 20,
                 peer_groups: list[str] | None = None, title: str = "Payment Integrity — Informe de hallazgos") -> ReportBundle:
    d = result.doctor_scores.copy()
    s = result.scored_periods
    if peer_groups:
        d = d[d["peer_group"].isin(peer_groups)]
    d = d[d["doctor_risk_level"] >= min_level].head(top_n).reset_index(drop=True)
    ids = d["doctor_id"].tolist()
    alerts = result.alerts[result.alerts["doctor_id"].isin(ids)].sort_values(["doctor_id", "period", "rule"])

    all_docs = result.doctor_scores if not peer_groups else result.doctor_scores[result.doctor_scores["peer_group"].isin(peer_groups)]
    counts = all_docs["doctor_risk_level"].value_counts()
    summary = {
        "periodo_inicio": s["period"].min(),
        "periodo_fin": s["period"].max(),
        "medicos_evaluados": int(all_docs["doctor_id"].nunique()),
        "medicos_priorizados": int(len(d)),
        "pagado_total": float(all_docs["total_paid"].sum()),
        "monto_sin_respaldo": float(all_docs["idle_amount"].sum()),
        "monto_sobre_contrato": float(all_docs["amount_at_risk"].sum()),
        "monto_sin_respaldo_priorizados": float(d["idle_amount"].sum()),
        "monto_sobre_contrato_priorizados": float(d["amount_at_risk"].sum()),
        "por_nivel": {lvl: int(counts.get(lvl, 0)) for lvl in cfg.scoring.level_labels},
    }
    filters = {"nivel_minimo": min_level, "top_n": top_n, "peer_groups": peer_groups or "todos"}
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ---- tabla de hallazgos ---------------------------------------------------
    rows = []
    for _, r in d.iterrows():
        worst = s[(s["doctor_id"] == r["doctor_id"]) & (s["period"] == r["worst_period"])].iloc[0]
        fired = [rc.code for rc in RULES if worst.get(f"{rc.code}_flag", False)]
        rows.append({
            "prioridad": len(rows) + 1,
            "doctor_id": r["doctor_id"],
            "peer_group": r["peer_group"],
            "score": r["doctor_risk_score"],
            "nivel": int(r["doctor_risk_level"]),
            "nivel_label": r["doctor_risk_level_label"],
            "peor_periodo": r["worst_period"],
            "pagado_total": r["total_paid"],
            "monto_sin_respaldo": r["idle_amount"],
            "monto_sobre_contrato": r["amount_at_risk"],
            **{dim: round(float(worst[dim]), 0) for dim in DIMENSIONS},
            "reglas": ", ".join(fired),
            "escalado_por": worst.get("escalated_by", "") or "",
            "horas_pagadas": worst["paid_hours"],
            "horas_sin_actividad": worst["idle_hours"],
            "pac_por_hora": worst["patients_per_hour"],
            "rendimiento_vs_esperado": worst["performance_ratio"],
            "costo_por_paciente": worst["cost_per_patient"],
            "cambio_vs_historico": worst.get("rel_change"),
            "accion_sugerida": LEVEL_ACTIONS[int(r["doctor_risk_level"])],
            "explicacion": worst["explanation"],
        })
    findings = pd.DataFrame(rows)

    md = _markdown(title, generated_at, filters, summary, findings, alerts, cfg)
    htm = _html(title, generated_at, filters, summary, findings, alerts, cfg)
    return ReportBundle(title, generated_at, filters, summary, findings, alerts, md, htm)


# --------------------------------------------------------------------------- Markdown
def _markdown(title, generated_at, filters, summary, findings, alerts, cfg) -> str:
    L = [f"# {title}", "", f"Generado: {generated_at} · Períodos {summary['periodo_inicio']} → {summary['periodo_fin']} · "
         f"Filtro: nivel ≥ {filters['nivel_minimo']}, top {filters['top_n']}, peer groups: {filters['peer_groups']}", ""]
    L += ["## 1. Resumen ejecutivo", "",
          "| Indicador | Valor |", "|---|---:|",
          f"| Médicos evaluados | {summary['medicos_evaluados']} |",
          f"| Médicos priorizados en este informe | {summary['medicos_priorizados']} |",
          f"| Pago total del período | {_fmt_clp(summary['pagado_total'])} |",
          f"| Pagado sin respaldo de actividad (todos) | {_fmt_clp(summary['monto_sin_respaldo'])} |",
          f"| Pagado sobre contrato o duplicado (todos) | {_fmt_clp(summary['monto_sobre_contrato'])} |",
          f"| Sin respaldo de actividad (priorizados) | {_fmt_clp(summary['monto_sin_respaldo_priorizados'])} |",
          f"| Sobre contrato o duplicado (priorizados) | {_fmt_clp(summary['monto_sobre_contrato_priorizados'])} |", ""]
    L += ["### Distribución por nivel", "", "| Nivel | Etiqueta | Médicos | Acción |", "|---|---|---:|---|"]
    for lvl, label in cfg.scoring.level_labels.items():
        L.append(f"| {lvl} | {label} | {summary['por_nivel'][lvl]} | {LEVEL_ACTIONS[lvl]} |")
    L += ["", "## 2. Médicos priorizados", "",
          "| # | Médico | Peer group | Score | Nivel | Peor período | Sin respaldo | Sobre contrato | Reglas |",
          "|---:|---|---|---:|---|---|---:|---:|---|"]
    for _, f in findings.iterrows():
        L.append(f"| {f['prioridad']} | {f['doctor_id']} | {f['peer_group']} | {f['score']:.0f} | {f['nivel']} · {f['nivel_label']} | "
                 f"{f['peor_periodo']} | {_fmt_clp(f['monto_sin_respaldo'])} | {_fmt_clp(f['monto_sobre_contrato'])} | {f['reglas']} |")
    L += ["", "## 3. Hallazgos por médico", ""]
    for _, f in findings.iterrows():
        L += [f"### {f['prioridad']}. {f['doctor_id']} — {f['score']:.0f}/100 · Nivel {f['nivel']} ({f['nivel_label']})", "",
              f"**Peer group:** {f['peer_group']} · **Peor período:** {f['peor_periodo']} · **Acción sugerida:** {f['accion_sugerida']}", "",
              "| Dimensión | Score |", "|---|---:|"]
        for dim in DIMENSIONS:
            L.append(f"| {DIMENSION_LABELS[dim]} | {f[dim]:.0f}/100 |")
        L += ["", "| Evidencia | Valor |", "|---|---:|",
              f"| Horas pagadas / sin actividad | {f['horas_pagadas']:.0f} h / {f['horas_sin_actividad']:.1f} h |",
              f"| Pacientes por hora / vs esperado | {f['pac_por_hora']:.2f} / {_pct(f['rendimiento_vs_esperado'])} |",
              f"| Costo por paciente | {_fmt_clp(f['costo_por_paciente'])} |",
              f"| Cambio vs histórico propio | {_pct(f['cambio_vs_historico'])} |",
              f"| Monto sin respaldo / sobre contrato | {_fmt_clp(f['monto_sin_respaldo'])} / {_fmt_clp(f['monto_sobre_contrato'])} |", "",
              f"> {f['explicacion']}", ""]
        a = alerts[alerts["doctor_id"] == f["doctor_id"]]
        if len(a):
            L += ["| Período | Regla | Detalle | Intensidad |", "|---|---|---|---:|"]
            L += [f"| {x['period']} | {x['rule']} | {x['detail']} | {x['intensity']:.2f} |" for _, x in a.iterrows()]
            L.append("")
    L += ["## 4. Metodología y trazabilidad", "",
          "- Modelo híbrido de cinco capas: conciliación contractual, reglas de negocio, perfil de pares (MAD), "
          "anomalías no supervisadas (Isolation Forest + LOF) y change detection (EWMA/CUSUM).",
          "- Score = " + " + ".join(f"{w:.2f}·{DIMENSION_LABELS[k]}" for k, w in cfg.scoring.weights.items()) + ".",
          f"- Escalamiento por reglas críticas con intensidad ≥ {cfg.scoring.critical_intensity} al piso {cfg.scoring.critical_floor:.0f}.",
          "- El score mide riesgo de pago indebido y prioriza auditoría; no constituye imputación. "
          "Todo caso nivel 3–4 requiere revisión humana antes de cualquier acción.", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------- HTML
_CSS = """
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#0b0b0b;background:#f9f9f7;margin:0;padding:32px;line-height:1.45}
.wrap{max-width:1040px;margin:0 auto}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 8px;border-bottom:1px solid #e1e0d9;padding-bottom:6px}
h3{font-size:15px;margin:20px 0 6px}.meta{color:#52514e;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}
.kpi{background:#fcfcfb;border:1px solid rgba(11,11,11,.10);border-radius:8px;padding:12px 14px}
.kpi .l{font-size:12px;color:#52514e}.kpi .v{font-size:20px;margin-top:2px;word-break:break-word}
table{border-collapse:collapse;width:100%;font-size:13px;background:#fcfcfb;margin:8px 0 12px}
th,td{border-bottom:1px solid #e1e0d9;padding:6px 8px;text-align:left;vertical-align:top}
th{color:#52514e;font-weight:600;font-size:12px}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.card{background:#fcfcfb;border:1px solid rgba(11,11,11,.10);border-radius:8px;padding:14px 16px;margin:12px 0;page-break-inside:avoid}
.lvl{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;color:#fff;background:#2a78d6}
.lvl.l0{background:#86b6ef;color:#0b0b0b}.lvl.l1{background:#5598e7}.lvl.l2{background:#2a78d6}.lvl.l3{background:#1c5cab}.lvl.l4{background:#0d366b}
.bar{height:8px;background:#e1e0d9;border-radius:4px;overflow:hidden}.bar i{display:block;height:100%;background:#2a78d6}
blockquote{margin:10px 0;padding:8px 12px;border-left:3px solid #2a78d6;background:#f0efec;font-size:13px}
.note{font-size:12px;color:#52514e}
@media print{body{padding:0;background:#fff}.card{border:1px solid #ccc}}
"""


def _html(title, generated_at, filters, summary, findings, alerts, cfg) -> str:
    e = html.escape
    H = [f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>{e(title)}</title><style>{_CSS}</style></head><body><div class='wrap'>"]
    H.append(f"<h1>{e(title)}</h1><div class='meta'>Generado {e(generated_at)} · Períodos {e(str(summary['periodo_inicio']))} → "
             f"{e(str(summary['periodo_fin']))} · Filtro: nivel ≥ {filters['nivel_minimo']}, top {filters['top_n']}, "
             f"peer groups: {e(str(filters['peer_groups']))}</div>")
    H.append("<h2>1. Resumen ejecutivo</h2><div class='kpis'>")
    for lab, val in [("Médicos evaluados", summary["medicos_evaluados"]), ("Médicos priorizados", summary["medicos_priorizados"]),
                     ("Pago total", _fmt_clp(summary["pagado_total"])), ("Sin respaldo de actividad", _fmt_clp(summary["monto_sin_respaldo"])),
                     ("Sobre contrato o duplicado", _fmt_clp(summary["monto_sobre_contrato"]))]:
        H.append(f"<div class='kpi'><div class='l'>{e(lab)}</div><div class='v'>{e(str(val))}</div></div>")
    H.append("</div><table><tr><th>Nivel</th><th>Etiqueta</th><th class='n'>Médicos</th><th>Acción</th></tr>")
    for lvl, label in cfg.scoring.level_labels.items():
        H.append(f"<tr><td><span class='lvl l{lvl}'>Nivel {lvl}</span></td><td>{e(label)}</td><td class='n'>{summary['por_nivel'][lvl]}</td><td>{e(LEVEL_ACTIONS[lvl])}</td></tr>")
    H.append("</table>")

    H.append("<h2>2. Médicos priorizados</h2><table><tr><th class='n'>#</th><th>Médico</th><th>Peer group</th><th class='n'>Score</th>"
             "<th>Nivel</th><th>Peor período</th><th class='n'>Sin respaldo</th><th class='n'>Sobre contrato</th><th>Reglas</th></tr>")
    for _, f in findings.iterrows():
        H.append(f"<tr><td class='n'>{f['prioridad']}</td><td>{e(f['doctor_id'])}</td><td>{e(f['peer_group'])}</td><td class='n'>{f['score']:.0f}</td>"
                 f"<td><span class='lvl l{f['nivel']}'>Nivel {f['nivel']}</span></td><td>{e(f['peor_periodo'])}</td>"
                 f"<td class='n'>{_fmt_clp(f['monto_sin_respaldo'])}</td><td class='n'>{_fmt_clp(f['monto_sobre_contrato'])}</td><td>{e(f['reglas'])}</td></tr>")
    H.append("</table>")

    H.append("<h2>3. Hallazgos por médico</h2>")
    for _, f in findings.iterrows():
        H.append(f"<div class='card'><h3>{f['prioridad']}. {e(f['doctor_id'])} — {f['score']:.0f}/100 "
                 f"<span class='lvl l{f['nivel']}'>Nivel {f['nivel']} · {e(f['nivel_label'])}</span></h3>"
                 f"<div class='meta'>Peer group {e(f['peer_group'])} · Peor período {e(f['peor_periodo'])} · Acción sugerida: {e(f['accion_sugerida'])}</div>")
        H.append("<table><tr><th>Dimensión</th><th style='width:45%'>Score</th><th class='n'></th></tr>")
        for dim in DIMENSIONS:
            H.append(f"<tr><td>{e(DIMENSION_LABELS[dim])}</td><td><div class='bar'><i style='width:{f[dim]:.0f}%'></i></div></td><td class='n'>{f[dim]:.0f}</td></tr>")
        H.append("</table><table><tr><th>Evidencia</th><th class='n'>Valor</th></tr>"
                 f"<tr><td>Horas pagadas / sin actividad</td><td class='n'>{f['horas_pagadas']:.0f} h / {f['horas_sin_actividad']:.1f} h</td></tr>"
                 f"<tr><td>Pacientes por hora / vs esperado</td><td class='n'>{f['pac_por_hora']:.2f} / {_pct(f['rendimiento_vs_esperado'])}</td></tr>"
                 f"<tr><td>Costo por paciente</td><td class='n'>{_fmt_clp(f['costo_por_paciente'])}</td></tr>"
                 f"<tr><td>Cambio vs histórico propio</td><td class='n'>{_pct(f['cambio_vs_historico'])}</td></tr>"
                 f"<tr><td>Monto sin respaldo / sobre contrato</td><td class='n'>{_fmt_clp(f['monto_sin_respaldo'])} / {_fmt_clp(f['monto_sobre_contrato'])}</td></tr></table>")
        H.append(f"<blockquote>{e(f['explicacion'])}</blockquote>")
        a = alerts[alerts["doctor_id"] == f["doctor_id"]]
        if len(a):
            H.append("<table><tr><th>Período</th><th>Regla</th><th>Detalle</th><th class='n'>Intensidad</th></tr>")
            H += [f"<tr><td>{e(x['period'])}</td><td>{e(x['rule'])}</td><td>{e(x['detail'])}</td><td class='n'>{x['intensity']:.2f}</td></tr>" for _, x in a.iterrows()]
            H.append("</table>")
        H.append("</div>")

    H.append("<h2>4. Metodología y trazabilidad</h2><ul class='note'>"
             "<li>Modelo híbrido de cinco capas: conciliación contractual, reglas de negocio, perfil de pares (MAD), anomalías no supervisadas (Isolation Forest + LOF) y change detection (EWMA/CUSUM).</li>"
             "<li>Score = " + e(" + ".join(f"{w:.2f}·{DIMENSION_LABELS[k]}" for k, w in cfg.scoring.weights.items())) + ".</li>"
             f"<li>Escalamiento por reglas críticas con intensidad ≥ {cfg.scoring.critical_intensity} al piso {cfg.scoring.critical_floor:.0f}.</li>"
             "<li>El score mide riesgo de pago indebido y prioriza auditoría; no constituye imputación. Todo caso nivel 3–4 requiere revisión humana antes de cualquier acción.</li></ul>")
    H.append("</div></body></html>")
    return "".join(H)
