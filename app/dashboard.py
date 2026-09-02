"""Tablero Payment Integrity — carga de datos, métricas, resultados y reportería.

Ejecutar:  streamlit run app/dashboard.py
"""
from __future__ import annotations

import dataclasses
import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from payment_integrity import run_pipeline, generate_synthetic, DEFAULT_CONFIG  # noqa: E402
from payment_integrity.config import RuleThresholds, ScoringConfig, PeerConfig  # noqa: E402
from payment_integrity.features import REQUIRED, OPTIONAL, validate_inputs  # noqa: E402
from payment_integrity.layers.rules import RULES  # noqa: E402
from payment_integrity.reporting import build_report, LEVEL_ACTIONS  # noqa: E402
from payment_integrity.scoring import DIMENSIONS, DIMENSION_LABELS  # noqa: E402
from app import charts  # noqa: E402

st.set_page_config(page_title="Payment Integrity", page_icon="🩺", layout="wide")

TABLE_HELP = {
    "doctors": "Maestro de médicos: doctor_id, peer_group, expected_rate (pac/h), hourly_rate",
    "contracts": "Bloques contratados por día: doctor_id, date, contract_start, contract_end, contracted_hours",
    "encounters": "Atenciones efectivas: encounter_id, doctor_id, patient_id, date, start_ts, end_ts (+ has_clinical_record, record_created_ts)",
    "payments": "Pagos por día: payment_id, doctor_id, date, paid_hours, amount",
    "schedule": "Opcional. Agenda: doctor_id, date, status (atendido / ausente / cancelado)",
    "sessions": "Opcional. Sesiones del sistema clínico: doctor_id, date, login_ts, logout_ts",
}


def fmt_clp(x: float) -> str:
    return f"${x:,.0f}".replace(",", ".")


# --------------------------------------------------------------------------- estado
if "data" not in st.session_state:
    st.session_state.data = None
    st.session_state.data_source = None
    st.session_state.result = None
    st.session_state.cfg = DEFAULT_CONFIG


def build_cfg_from_sidebar():
    base = DEFAULT_CONFIG
    with st.sidebar.expander("Parámetros del modelo", expanded=False):
        st.caption("Umbrales clave y pesos. Los cambios aplican al volver a ejecutar el modelo.")
        idle = st.slider("R01 · máx. horas sin actividad", 0.10, 0.70, base.rules.max_idle_hours_ratio, 0.05, format="%.2f")
        perf = st.slider("R02 · mín. rendimiento vs esperado", 0.20, 0.90, base.rules.min_performance_ratio, 0.05, format="%.2f")
        rec = st.slider("R12 · máx. atenciones sin registro", 0.0, 0.50, base.rules.max_missing_record_ratio, 0.05, format="%.2f")
        peer_min = st.slider("Mínimo de pares por grupo", 3, 15, base.peer.min_peer_size, 1)
        st.markdown("**Pesos del Risk Score**")
        w = {}
        for k, v in base.scoring.weights.items():
            w[k] = st.slider(DIMENSION_LABELS[k], 0.0, 0.5, v, 0.05, key=f"w_{k}")
        tot = sum(w.values()) or 1.0
        w = {k: v / tot for k, v in w.items()}
        st.caption("Pesos normalizados a 1: " + ", ".join(f"{DIMENSION_LABELS[k].split(' ')[0]} {v:.2f}" for k, v in w.items()))
    rules = dataclasses.replace(base.rules, max_idle_hours_ratio=idle, min_performance_ratio=perf, max_missing_record_ratio=rec)
    peer = dataclasses.replace(base.peer, min_peer_size=peer_min)
    scoring = ScoringConfig(weights=w)
    return dataclasses.replace(base, rules=rules, peer=peer, scoring=scoring)


# --------------------------------------------------------------------------- sidebar
st.sidebar.title("Payment Integrity")
st.sidebar.caption("Detección de anomalías en pagos médicos por hora")
page = st.sidebar.radio("Sección", ["1 · Carga de datos", "2 · Resumen ejecutivo", "3 · Métricas", "4 · Ficha por médico", "5 · Reportería"], label_visibility="collapsed")
cfg = build_cfg_from_sidebar()

if st.session_state.result is not None:
    r = st.session_state.result
    st.sidebar.success(f"Modelo ejecutado · {r.doctor_scores['doctor_id'].nunique()} médicos · "
                       f"{r.scored_periods['period'].min()} → {r.scored_periods['period'].max()}")
    st.sidebar.caption(f"Fuente: {st.session_state.data_source}")
else:
    st.sidebar.info("Sin resultados. Cargue datos o use la demostración en la sección 1.")


# =========================================================================== 1. carga
def page_load():
    st.header("Carga de datos")
    st.markdown("Suba las tablas del modelo de datos en CSV. Cuatro son obligatorias; agenda y sesiones son opcionales "
                "(las reglas que dependen de ellas se omiten automáticamente). También puede usar la data de demostración sintética.")

    c1, c2 = st.columns([3, 2])
    with c1:
        uploads = {}
        st.subheader("Tablas obligatorias")
        for t in REQUIRED:
            uploads[t] = st.file_uploader(f"{t}.csv", type=["csv"], key=f"up_{t}", help=TABLE_HELP[t])
        st.subheader("Tablas opcionales")
        for t in OPTIONAL:
            uploads[t] = st.file_uploader(f"{t}.csv", type=["csv"], key=f"up_{t}", help=TABLE_HELP[t])

        if st.button("Validar y cargar archivos", type="primary", key="btn_load"):
            data = {}
            for t, f in uploads.items():
                if f is not None:
                    data[t] = pd.read_csv(f)
            try:
                validate_inputs(data)
                st.session_state.data = data
                st.session_state.data_source = "archivos cargados"
                st.session_state.result = None
                st.success("Tablas válidas. Ejecute el modelo.")
            except ValueError as e:
                st.error(f"Contrato de datos no cumplido: {e}")

    with c2:
        st.subheader("Demostración")
        st.markdown("Genera 60 médicos, 26 semanas y 5 escenarios de riesgo inyectados (15 % de los médicos). "
                    "Útil para validar el modelo antes de conectar data real.")
        if st.button("Usar data de demostración", key="btn_demo"):
            ds = generate_synthetic(cfg.synthetic)
            st.session_state.data = ds.as_dict()
            st.session_state.data_source = "data sintética de demostración"
            st.session_state.result = None
            st.success("Data de demostración generada. Ejecute el modelo.")
        st.subheader("Contrato de datos")
        rows = [{"tabla": t, "obligatoria": "sí", "columnas requeridas": ", ".join(sorted(c))} for t, c in REQUIRED.items()]
        rows += [{"tabla": t, "obligatoria": "no", "columnas requeridas": ", ".join(sorted(c))} for t, c in OPTIONAL.items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    if st.session_state.data is not None:
        st.divider()
        st.subheader("Vista previa")
        st.caption(f"Fuente: {st.session_state.data_source}")
        counts = {t: len(df) for t, df in st.session_state.data.items()}
        cols = st.columns(len(counts))
        for c, (t, n) in zip(cols, counts.items()):
            c.metric(t, f"{n:,}".replace(",", "."))
        t = st.selectbox("Tabla", list(st.session_state.data), key="preview_table")
        st.dataframe(st.session_state.data[t].head(50), hide_index=True, use_container_width=True)

        if st.button("Ejecutar modelo", type="primary", key="btn_run"):
            with st.spinner("Calculando features, reglas, pares, anomalías y scores…"):
                st.session_state.result = run_pipeline(data=st.session_state.data, cfg=cfg, output_dir=None)
                st.session_state.cfg = cfg
            st.success("Modelo ejecutado. Revise el resumen ejecutivo.")


# =========================================================================== helpers
def need_result():
    if st.session_state.result is None:
        st.warning("Primero cargue datos y ejecute el modelo en la sección 1.")
        st.stop()
    return st.session_state.result, st.session_state.cfg


def table_view(df: pd.DataFrame, label: str = "Ver tabla"):
    with st.expander(label):
        st.dataframe(df, hide_index=True, use_container_width=True)


# =========================================================================== 2. resumen
def page_summary():
    res, cfg = need_result()
    d, s = res.doctor_scores, res.scored_periods
    st.header("Resumen ejecutivo")

    k = st.columns(6)
    k[0].metric("Médicos evaluados", d["doctor_id"].nunique())
    k[1].metric("Médico-períodos", len(s))
    k[2].metric("Pago total", fmt_clp(d["total_paid"].sum()))
    k[3].metric("Sin respaldo de actividad", fmt_clp(d["idle_amount"].sum()),
                help="Horas pagadas sin actividad clínica registrada × valor hora. Es un monto a revisar, no una pérdida confirmada.")
    k[4].metric("Sobre contrato o duplicado", fmt_clp(d["amount_at_risk"].sum()),
                help="Horas pagadas por sobre las contratadas y pagos duplicados. Evidencia directa de la conciliación contractual.")
    k[5].metric("Médicos nivel ≥ 3", int((d["doctor_risk_level"] >= 3).sum()),
                help="Posible pago indebido o requiere auditoría. Requieren revisión humana.")

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.level_distribution(d, cfg.scoring.level_labels), use_container_width=True)
        lvl_tbl = d["doctor_risk_level"].value_counts().reindex(range(5), fill_value=0).rename("médicos").reset_index()
        lvl_tbl.columns = ["nivel", "médicos"]
        lvl_tbl["etiqueta"] = lvl_tbl["nivel"].map(cfg.scoring.level_labels)
        lvl_tbl["acción"] = lvl_tbl["nivel"].map(LEVEL_ACTIONS)
        table_view(lvl_tbl, "Ver tabla · niveles")
    with c2:
        st.plotly_chart(charts.score_histogram(d, cfg.scoring.level_cuts), use_container_width=True)
        table_view(d[["doctor_id", "peer_group", "doctor_risk_score", "doctor_risk_level_label"]], "Ver tabla · scores")

    c3, c4 = st.columns([3, 2])
    with c3:
        n = st.slider("Médicos a mostrar", 5, min(40, len(d)), min(15, len(d)), key="topn")
        st.plotly_chart(charts.top_doctors(d, n), use_container_width=True)
    with c4:
        st.plotly_chart(charts.score_over_time(s), use_container_width=True)
        st.plotly_chart(charts.level3_over_time(s), use_container_width=True)

    st.subheader("Ranking consolidado por médico")
    show = d[["doctor_id", "peer_group", "doctor_risk_score", "doctor_risk_level", "doctor_risk_level_label", "worst_period",
              "total_paid", "idle_amount", "amount_at_risk", "rules_triggered_total", "top_drivers"]].copy()
    st.dataframe(show, hide_index=True, use_container_width=True,
                 column_config={
                     "doctor_risk_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
                     "doctor_risk_level": st.column_config.NumberColumn("Nivel"),
                     "doctor_risk_level_label": "Etiqueta", "worst_period": "Peor período",
                     "total_paid": st.column_config.NumberColumn("Pagado", format="$%d"),
                     "idle_amount": st.column_config.NumberColumn("Sin respaldo", format="$%d"),
                     "amount_at_risk": st.column_config.NumberColumn("Sobre contrato", format="$%d"),
                     "rules_triggered_total": "Reglas", "top_drivers": "Principales impulsores",
                 })

    if res.validation:
        v = res.validation
        with st.expander("Validación contra escenarios inyectados (solo data sintética)"):
            c = st.columns(4)
            c[0].metric(f"Precision@{v['n_injected']}", f"{v['precision_at_k']:.2f}")
            c[1].metric("Inyectados en nivel ≥ 3", f"{v['injected_in_level_ge3']:.0%}")
            c[2].metric("Normales en nivel ≥ 3", f"{v['normal_in_level_ge3']:.1%}")
            c[3].metric("Score medio inyectados / normales", f"{v['mean_score_injected']:.0f} / {v['mean_score_normal']:.0f}")
            st.json(v["rank_by_scenario"])


# =========================================================================== 3. métricas
def page_metrics():
    res, cfg = need_result()
    s = res.scored_periods
    st.header("Métricas y capas del modelo")

    f1, f2, f3 = st.columns(3)
    pgs = f1.multiselect("Peer group", sorted(s["peer_group"].unique()), key="m_pg")
    periods = f2.multiselect("Período", sorted(s["period"].unique()), key="m_period")
    min_lvl = f3.select_slider("Nivel mínimo", options=[0, 1, 2, 3, 4], value=0, key="m_lvl")
    sub = s.copy()
    if pgs:
        sub = sub[sub["peer_group"].isin(pgs)]
    if periods:
        sub = sub[sub["period"].isin(periods)]
    sub = sub[sub["risk_level"] >= min_lvl]
    st.caption(f"{len(sub)} médico-períodos en la selección")
    if sub.empty:
        st.stop()

    tab_prod, tab_peer, tab_rules, tab_anom = st.tabs(["Productividad y costo", "Perfil de pares", "Reglas", "Anomalías y conciliación"])

    with tab_prod:
        st.plotly_chart(charts.scatter_productivity(sub), use_container_width=True)
        table_view(sub[["doctor_id", "period", "peer_group", "patients_per_hour", "cost_per_patient", "idle_hours_ratio", "risk_score", "risk_level"]])

    with tab_peer:
        metric_labels = {"patients_per_hour": "Pacientes por hora", "utilization": "Utilización", "cost_per_patient": "Costo por paciente",
                         "idle_hours_ratio": "Horas sin actividad (ratio)", "mean_duration_min": "Duración media (min)", "no_show_ratio": "No-show (ratio)"}
        metric = st.selectbox("Métrica", list(metric_labels), format_func=lambda m: metric_labels[m], key="m_metric")
        st.plotly_chart(charts.peer_boxplot(sub, metric, metric_labels[metric]), use_container_width=True)
        zc = [c for c in sub.columns if c.endswith("_z")]
        table_view(sub[["doctor_id", "period", "peer_group", "peer_size", "peer_reliable"] + zc].round(2), "Ver tabla · z-scores robustos por peer group")

    with tab_rules:
        alerts = res.alerts[res.alerts["doctor_id"].isin(sub["doctor_id"]) & res.alerts["period"].isin(sub["period"])]
        c1, c2 = st.columns([2, 3])
        with c1:
            st.plotly_chart(charts.rule_frequency(alerts, {r.code: r.name for r in RULES}), use_container_width=True)
            st.dataframe(pd.DataFrame([{"código": r.code, "regla": r.name, "dimensión": DIMENSION_LABELS[r.dimension].split(" /")[0], "crítica": "sí" if r.critical else "no"} for r in RULES]),
                         hide_index=True, use_container_width=True, height=380)
        with c2:
            st.plotly_chart(charts.rules_heatmap(sub, [r.code for r in RULES], n=min(20, sub["doctor_id"].nunique())), use_container_width=True)
        table_view(alerts, "Ver tabla · alertas")

    with tab_anom:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Anomalías no supervisadas (Isolation Forest + LOF)**")
            an = sub[["doctor_id", "period", "peer_group", "iforest_score", "lof_score", "anomaly_risk", "anomaly_top_features"]].sort_values("anomaly_risk", ascending=False)
            st.dataframe(an.head(30).round(3), hide_index=True, use_container_width=True, height=420)
        with c2:
            st.markdown("**Conciliación contractual (capa 1)**")
            rc = res.reconciliation.merge(sub[["doctor_id", "period"]], on=["doctor_id", "period"])
            rc = rc[["doctor_id", "period", "status", "contracted_hours", "paid_hours", "active_hours", "idle_hours", "total_paid", "idle_amount", "overpaid_amount", "duplicate_amount"]]
            rc = rc.sort_values(["status", "idle_amount"], ascending=[True, False])
            st.dataframe(rc.round(1), hide_index=True, use_container_width=True, height=420)


# =========================================================================== 4. ficha
def page_doctor():
    res, cfg = need_result()
    d, s = res.doctor_scores, res.scored_periods
    st.header("Ficha por médico")
    opts = d["doctor_id"].tolist()
    labels = {r.doctor_id: f"{r.doctor_id} · {r.doctor_risk_score:.0f} · N{r.doctor_risk_level} · {r.peer_group}" for r in d.itertuples()}
    doc = st.selectbox("Médico (ordenados por riesgo)", opts, format_func=lambda x: labels[x], key="doc_sel")
    row = d[d["doctor_id"] == doc].iloc[0]
    sp = s[s["doctor_id"] == doc].sort_values("period")
    period = st.select_slider("Período de detalle", options=sp["period"].tolist(), value=row["worst_period"], key="doc_period")
    pr = sp[sp["period"] == period].iloc[0]

    k = st.columns(6)
    k[0].metric("Score consolidado", f"{row['doctor_risk_score']:.0f}", help="máx(0,75·peor mes + 0,25·promedio, último mes)")
    k[1].metric("Nivel", f"{int(row['doctor_risk_level'])}", help=row["doctor_risk_level_label"])
    k[2].metric(f"Score {period}", f"{pr['risk_score']:.0f}")
    k[3].metric("Pagadas / ociosas (h)", f"{pr['paid_hours']:.0f} / {pr['idle_hours']:.1f}", help="Horas pagadas en el período / horas pagadas sin actividad clínica registrada")
    k[4].metric("Pac/h vs esperado", f"{pr['patients_per_hour']:.2f} / {pr['expected_rate']:.2f}")
    k[5].metric("Costo por paciente", fmt_clp(pr["cost_per_patient"]))

    st.info(pr["explanation"])
    st.caption(f"Acción sugerida para nivel {int(pr['risk_level'])}: {LEVEL_ACTIONS[int(pr['risk_level'])]}")

    c1, c2 = st.columns([2, 3])
    with c1:
        st.plotly_chart(charts.dimension_bars(pr, DIMENSIONS, DIMENSION_LABELS), use_container_width=True)
        zrows = [{"métrica": m, "valor": pr[m], "z robusto": pr.get(f"{m}_z"), "percentil peer": pr.get(f"{m}_pct")}
                 for m in cfg.peer.metrics if f"{m}_z" in pr.index]
        st.markdown(f"**Frente a pares** · {pr['peer_group']} · n={int(pr['peer_size'])}" + ("" if pr["peer_reliable"] else " · grupo pequeño, comparación atenuada"))
        st.dataframe(pd.DataFrame(zrows).round(2), hide_index=True, use_container_width=True)
    with c2:
        w = res.change_weekly[res.change_weekly["doctor_id"] == doc]
        st.plotly_chart(charts.weekly_series(w), use_container_width=True)
        day = res.day_features[res.day_features["doctor_id"] == doc]
        st.plotly_chart(charts.weekly_activity(day), use_container_width=True)

    st.subheader("Trayectoria mensual")
    st.dataframe(sp[["period", "risk_score", "risk_level", "escalated_by", "rules_triggered"] + list(DIMENSIONS) +
                    ["paid_hours", "idle_hours_ratio", "patients_per_hour", "cost_per_patient", "rel_change"]].round(2),
                 hide_index=True, use_container_width=True)
    st.subheader("Alertas por regla")
    a = res.alerts[res.alerts["doctor_id"] == doc].sort_values(["period", "rule"])
    st.dataframe(a[["period", "rule", "rule_name", "observed", "threshold", "intensity", "detail"]], hide_index=True, use_container_width=True) if len(a) else st.caption("Sin reglas activadas.")


# =========================================================================== 5. reportería
def page_report():
    res, cfg = need_result()
    st.header("Reportería de hallazgos")
    st.markdown("Genera un informe de auditoría filtrado por nivel de riesgo, con resumen ejecutivo, tabla de priorización, "
                "ficha de hallazgos por médico y anexo metodológico. Exportable en HTML (imprimible), Markdown y datos planos.")

    f1, f2, f3, f4 = st.columns([1, 1, 2, 2])
    min_level = f1.select_slider("Nivel mínimo", options=[0, 1, 2, 3, 4], value=3, key="r_lvl")
    top_n = f2.number_input("Máximo de médicos", 1, 200, 20, key="r_top")
    pgs = f3.multiselect("Peer group", sorted(res.doctor_scores["peer_group"].unique()), key="r_pg")
    title = f4.text_input("Título", "Payment Integrity — Informe de hallazgos", key="r_title")

    bundle = build_report(res, cfg, min_level=min_level, top_n=int(top_n), peer_groups=pgs or None, title=title)
    st.caption(f"{bundle.summary['medicos_priorizados']} médicos priorizados de {bundle.summary['medicos_evaluados']} evaluados · generado {bundle.generated_at}")

    stamp = bundle.generated_at.replace(" ", "_").replace(":", "")
    b1, b2, b3, b4 = st.columns(4)
    b1.download_button("Descargar HTML", bundle.html.encode("utf-8"), f"payment_integrity_{stamp}.html", "text/html", key="dl_html")
    b2.download_button("Descargar Markdown", bundle.markdown.encode("utf-8"), f"payment_integrity_{stamp}.md", "text/markdown", key="dl_md")
    b3.download_button("Hallazgos CSV (Sheets/Excel)", bundle.findings.to_csv(index=False).encode("utf-8-sig"), f"hallazgos_{stamp}.csv", "text/csv", key="dl_csv")

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, df in res.tables().items():
            z.writestr(f"{name}.csv", df.to_csv(index=False))
        z.writestr("report.html", bundle.html)
        z.writestr("report.md", bundle.markdown)
        z.writestr("config_used.json", json.dumps(dataclasses.asdict(cfg), ensure_ascii=False, indent=2, default=str))
        if res.validation:
            z.writestr("validation.json", json.dumps(res.validation, ensure_ascii=False, indent=2))
    b4.download_button("Paquete completo (ZIP)", zbuf.getvalue(), f"payment_integrity_{stamp}.zip", "application/zip", key="dl_zip")

    tab_prev, tab_tbl, tab_md = st.tabs(["Vista previa del informe", "Tabla de hallazgos", "Markdown"])
    with tab_prev:
        st.components.v1.html(bundle.html, height=1400, scrolling=True)
    with tab_tbl:
        st.dataframe(bundle.findings, hide_index=True, use_container_width=True)
    with tab_md:
        st.markdown(bundle.markdown)


PAGES = {"1 · Carga de datos": page_load, "2 · Resumen ejecutivo": page_summary, "3 · Métricas": page_metrics,
         "4 · Ficha por médico": page_doctor, "5 · Reportería": page_report}
PAGES[page]()
