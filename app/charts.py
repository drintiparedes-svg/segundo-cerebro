"""Gráficos Plotly del tablero. Paleta validada (ver README › Front) y marcas finas.

Roles de color:
  - series-1 (#2a78d6) para toda serie única; slot 2 (#eb6834) y 3 (#1baf7a) solo cuando hay identidad.
  - rampa ordinal azul para el nivel de riesgo 0-4 (magnitud ordenada, un solo tono).
  - gris #898781 para contexto / de-énfasis.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
LEVEL_RAMP = {0: "#86b6ef", 1: "#5598e7", 2: "#2a78d6", 3: "#1c5cab", 4: "#0d366b"}
SEQ_SCALE = [[0, "#cde2fb"], [0.5, "#3987e5"], [1, "#0d366b"]]
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

LEVEL_NAMES = {0: "0 · Normal", 1: "1 · Anomalía operacional", 2: "2 · Posible error administrativo",
               3: "3 · Posible pago indebido", 4: "4 · Requiere auditoría"}


def _layout(fig: go.Figure, height: int = 320, title: str = "", **kw) -> go.Figure:
    fig.update_layout(
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font=dict(family=FONT, color=INK, size=12),
        margin=dict(l=8, r=8, t=40, b=8), height=height, hovermode=kw.pop("hovermode", "closest"),
        legend=dict(orientation="h", y=-0.18, x=0, font=dict(size=11, color=INK2), bgcolor="rgba(0,0,0,0)"),
        title=dict(text=title, font=dict(size=14, color=INK), x=0, xanchor="left"), **kw,
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickfont=dict(color=MUTED, size=11), title_font=dict(color=INK2, size=11), zeroline=False)
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, linecolor="rgba(0,0,0,0)", tickfont=dict(color=MUTED, size=11), title_font=dict(color=INK2, size=11), zeroline=False)
    return fig


def level_distribution(doctors: pd.DataFrame, labels: dict) -> go.Figure:
    counts = doctors["doctor_risk_level"].value_counts().reindex(range(5), fill_value=0)
    fig = go.Figure(go.Bar(
        x=[LEVEL_NAMES[i] for i in counts.index], y=counts.values,
        marker=dict(color=[LEVEL_RAMP[i] for i in counts.index], line=dict(width=0)), width=0.6,
        text=counts.values, textposition="outside", textfont=dict(color=INK2),
        hovertemplate="%{x}<br>%{y} médicos<extra></extra>",
    ))
    fig.update_yaxes(title="Médicos")
    return _layout(fig, title="Médicos por nivel de riesgo (consolidado)")


def score_histogram(doctors: pd.DataFrame, cuts: dict) -> go.Figure:
    fig = go.Figure(go.Histogram(
        x=doctors["doctor_risk_score"], xbins=dict(start=0, end=100, size=5),
        marker=dict(color=S1, line=dict(color=SURFACE, width=2)),
        hovertemplate="Score %{x}<br>%{y} médicos<extra></extra>",
    ))
    for lvl, (lo, _) in cuts.items():
        if lvl > 0:
            fig.add_vline(x=lo, line=dict(color=AXIS, width=1))
            fig.add_annotation(x=lo, y=1, yref="paper", text=f"N{lvl}", showarrow=False, font=dict(color=MUTED, size=10), xanchor="left", yanchor="top")
    fig.update_xaxes(title="Risk score (0-100)", range=[0, 100])
    fig.update_yaxes(title="Médicos")
    return _layout(fig, title="Distribución del risk score por médico")


def top_doctors(doctors: pd.DataFrame, n: int = 15) -> go.Figure:
    d = doctors.head(n).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d["doctor_risk_score"], y=d["doctor_id"], orientation="h",
        marker=dict(color=[LEVEL_RAMP[int(l)] for l in d["doctor_risk_level"]], line=dict(width=0)), width=0.65,
        text=[f"{v:.0f}" for v in d["doctor_risk_score"]], textposition="outside", textfont=dict(color=INK2),
        customdata=d[["peer_group", "doctor_risk_level_label", "worst_period"]].to_numpy(),
        hovertemplate="<b>%{y}</b> · %{customdata[0]}<br>Score %{x:.0f} · %{customdata[1]}<br>Peor período %{customdata[2]}<extra></extra>",
    ))
    fig.update_xaxes(title="Risk score", range=[0, 110])
    fig.update_yaxes(showgrid=False)
    return _layout(fig, height=max(320, 24 * n + 80), title=f"Top {n} médicos priorizados (color = nivel)")


def score_over_time(scored: pd.DataFrame) -> go.Figure:
    g = scored.groupby("period").agg(mean=("risk_score", "mean"), p90=("risk_score", lambda s: s.quantile(0.9)),
                                     n3=("risk_level", lambda s: int((s >= 3).sum()))).reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=g["period"], y=g["p90"], name="Percentil 90", mode="lines+markers",
                             line=dict(color=S2, width=2), marker=dict(size=8, line=dict(color=SURFACE, width=2)),
                             hovertemplate="%{x}<br>P90 %{y:.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=g["period"], y=g["mean"], name="Promedio", mode="lines+markers",
                             line=dict(color=S1, width=2), marker=dict(size=8, line=dict(color=SURFACE, width=2)),
                             hovertemplate="%{x}<br>Promedio %{y:.0f}<extra></extra>"))
    fig.update_yaxes(title="Risk score", range=[0, 100])
    fig.update_xaxes(type="category")
    return _layout(fig, hovermode="x unified", title="Evolución mensual del risk score (médico-período)")


def level3_over_time(scored: pd.DataFrame) -> go.Figure:
    g = scored.groupby("period")["risk_level"].apply(lambda s: int((s >= 3).sum())).reset_index(name="n")
    fig = go.Figure(go.Bar(x=g["period"], y=g["n"], marker=dict(color=S1, line=dict(width=0)), width=0.5,
                           text=g["n"], textposition="outside", textfont=dict(color=INK2),
                           hovertemplate="%{x}<br>%{y} médico-períodos nivel ≥ 3<extra></extra>"))
    fig.update_yaxes(title="Médico-períodos nivel ≥ 3")
    fig.update_xaxes(type="category")
    return _layout(fig, title="Casos nivel ≥ 3 por mes")


def scatter_productivity(scored: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for lvl in range(5):
        sub = scored[scored["risk_level"] == lvl]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["patients_per_hour"], y=sub["cost_per_patient"], mode="markers", name=LEVEL_NAMES[lvl],
            marker=dict(size=9, color=LEVEL_RAMP[lvl], line=dict(color=SURFACE, width=1.5), opacity=0.9),
            customdata=sub[["doctor_id", "period", "peer_group", "risk_score"]].to_numpy(),
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]}<br>%{customdata[2]}<br>"
                          "%{x:.2f} pac/h · $%{y:,.0f}/paciente · score %{customdata[3]:.0f}<extra></extra>",
        ))
    fig.update_xaxes(title="Pacientes por hora pagada")
    fig.update_yaxes(title="Costo por paciente (CLP)")
    return _layout(fig, height=380, title="Rendimiento vs costo por paciente (cada punto = médico-mes)")


def peer_boxplot(scored: pd.DataFrame, metric: str, label: str) -> go.Figure:
    fig = go.Figure()
    for pg, sub in scored.groupby("peer_group"):
        fig.add_trace(go.Box(y=sub[metric], name=pg, marker=dict(color=S1, size=4), line=dict(color=S1, width=1.5),
                             fillcolor="rgba(42,120,214,0.12)", boxpoints="outliers",
                             customdata=sub[["doctor_id", "period"]].to_numpy(),
                             hovertemplate="%{customdata[0]} · %{customdata[1]}<br>" + label + " %{y:.2f}<extra></extra>"))
    fig.update_yaxes(title=label)
    fig.update_xaxes(tickangle=-20)
    return _layout(fig, height=400, showlegend=False, title=f"{label} por peer group")


def rule_frequency(alerts: pd.DataFrame, rule_names: dict) -> go.Figure:
    g = alerts.groupby("rule").agg(n=("doctor_id", "count"), med=("doctor_id", "nunique")).reindex(sorted(rule_names)).fillna(0)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=g.index, y=g["n"], name="Alertas (médico-mes)", marker=dict(color=S1, line=dict(width=0)), width=0.35,
                         offsetgroup=0, hovertemplate="%{x}<br>%{y} alertas<extra></extra>"))
    fig.add_trace(go.Bar(x=g.index, y=g["med"], name="Médicos distintos", marker=dict(color=S2, line=dict(width=0)), width=0.35,
                         offsetgroup=1, hovertemplate="%{x}<br>%{y} médicos<extra></extra>"))
    fig.update_xaxes(tickvals=list(g.index), ticktext=[f"{r}" for r in g.index])
    fig.update_yaxes(title="Conteo")
    return _layout(fig, barmode="group", bargap=0.3, title="Frecuencia de reglas activadas")


def rules_heatmap(scored: pd.DataFrame, rule_codes: list[str], n: int = 20) -> go.Figure:
    top = scored.groupby("doctor_id")["risk_score"].max().sort_values(ascending=False).head(n).index
    cols = [f"{r}_intensity" for r in rule_codes]
    m = scored[scored["doctor_id"].isin(top)].groupby("doctor_id")[cols].max().reindex(top).fillna(0)
    fig = go.Figure(go.Heatmap(
        z=m.values, x=rule_codes, y=m.index, colorscale=SEQ_SCALE, zmin=0, zmax=1, xgap=2, ygap=2,
        colorbar=dict(title="Intensidad", thickness=10, tickfont=dict(color=MUTED)),
        hovertemplate="%{y} · %{x}<br>Intensidad máx. %{z:.2f}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return _layout(fig, height=max(320, 22 * n + 90), title=f"Intensidad máxima por regla · top {n} médicos")


def dimension_bars(row: pd.Series, dims: tuple, labels: dict) -> go.Figure:
    vals = [float(row[d]) for d in dims]
    fig = go.Figure(go.Bar(
        x=vals, y=[labels[d] for d in dims], orientation="h", marker=dict(color=S1, line=dict(width=0)), width=0.55,
        text=[f"{v:.0f}" for v in vals], textposition="outside", textfont=dict(color=INK2),
        hovertemplate="%{y}<br>%{x:.0f}/100<extra></extra>",
    ))
    fig.update_xaxes(range=[0, 125], title="Score de dimensión (0-100)")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return _layout(fig, height=260, title=f"Dimensiones del riesgo · {row['period']}")


def weekly_series(weekly: pd.DataFrame, expected_rate: float | None = None) -> go.Figure:
    w = weekly.sort_values("week")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=w["week"], y=w["baseline_pph"], name="Línea base propia", mode="lines",
                             line=dict(color=MUTED, width=1.5), hovertemplate="Línea base %{y:.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=w["week"], y=w["pph"], name="Pacientes/hora (semana)", mode="lines+markers",
                             line=dict(color=S1, width=2), marker=dict(size=7, line=dict(color=SURFACE, width=2)),
                             hovertemplate="%{x|%d %b}<br>%{y:.2f} pac/h<extra></extra>"))
    fig.add_trace(go.Scatter(x=w["week"], y=w["ewma_pph"], name="EWMA", mode="lines",
                             line=dict(color=S2, width=2), hovertemplate="EWMA %{y:.2f}<extra></extra>"))
    alarms = w[w["cusum_alarm"]]
    if len(alarms):
        fig.add_trace(go.Scatter(x=alarms["week"], y=alarms["pph"], name="Alarma CUSUM", mode="markers",
                                 marker=dict(symbol="diamond", size=11, color=S3, line=dict(color=SURFACE, width=2)),
                                 hovertemplate="Alarma CUSUM<br>%{x|%d %b}<extra></extra>"))
    fig.update_yaxes(title="Pacientes por hora", rangemode="tozero")
    return _layout(fig, hovermode="x unified", height=340, title="Rendimiento semanal vs histórico propio")


def weekly_activity(day: pd.DataFrame) -> go.Figure:
    d = day.groupby("week").agg(paid_hours=("paid_hours", "sum"), active_hours=("active_hours", "sum")).reset_index()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=d["week"], y=d["paid_hours"], name="Horas pagadas", marker=dict(color="#cde2fb", line=dict(width=0)),
                         hovertemplate="Semana %{x|%d %b}<br>Pagadas %{y:.1f} h<extra></extra>"))
    fig.add_trace(go.Bar(x=d["week"], y=d["active_hours"], name="Horas con actividad", marker=dict(color=S1, line=dict(width=0)),
                         hovertemplate="Semana %{x|%d %b}<br>Con actividad %{y:.1f} h<extra></extra>"))
    fig.update_layout(barmode="overlay", bargap=0.25)
    fig.update_yaxes(title="Horas por semana")
    return _layout(fig, hovermode="x unified", height=300, title="Horas pagadas vs horas con actividad (por semana)")
