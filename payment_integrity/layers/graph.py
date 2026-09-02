"""CAPA F — Graph Analytics (relaciones médico ↔ paciente ↔ tiempo).

Construye un grafo bipartito médico–paciente ponderado por atenciones y su
proyección médico–médico (peso = pacientes compartidos). A partir de él
detecta patrones que las métricas por médico no ven:

- pacientes compartidos con otros médicos muy por sobre lo habitual del grupo;
- el mismo paciente atendido por dos médicos en el mismo instante (físicamente imposible);
- concentración de la actividad en pocos pacientes (índice Herfindahl-Hirschman);
- pacientes con frecuencia de visitas implausible dentro del período;
- comunidades de médicos que comparten un pool de pacientes (posible red de facturación).

Devuelve métricas por médico-período, aristas de la proyección, comunidades y
una explicación narrativa por médico para el auditor.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import pandas as pd

from ..config import GraphConfig


@dataclass
class GraphResult:
    metrics: pd.DataFrame                       # doctor_id, period, métricas + graph_risk + graph_explanation
    edges: pd.DataFrame                         # proyección médico–médico por período (shared_patients, jaccard)
    communities: pd.DataFrame                   # doctor_id, period, community, community_size
    simultaneous: pd.DataFrame                  # detalle: paciente atendido por dos médicos al mismo tiempo
    doctor_graph: dict = field(default_factory=dict)   # period -> nx.Graph (proyección) para visualización


def _robust_z(x: pd.Series) -> pd.Series:
    med = x.median()
    mad = (x - med).abs().median()
    if not np.isfinite(mad) or mad == 0:
        sd = x.std()
        return (x - med) / sd if sd and np.isfinite(sd) and sd > 0 else pd.Series(0.0, index=x.index)
    return 0.6745 * (x - med) / mad


def _simultaneous_pairs(enc: pd.DataFrame, tolerance_min: float) -> pd.DataFrame:
    """Mismo paciente con dos médicos distintos cuyas atenciones se solapan en el tiempo.

    Solo pueden solaparse atenciones del mismo paciente vistas por más de un médico, así que
    se descarta el resto antes del barrido; dentro de lo que queda, las marcas de tiempo se
    comparan como enteros (nanosegundos), que es donde estaba el costo.
    """
    cols = ["encounter_id", "doctor_id", "patient_id", "period", "start_ts", "end_ts"]
    empty = pd.DataFrame(columns=["patient_id", "period", "doctor_a", "doctor_b",
                                  "encounter_a", "encounter_b", "start_a", "start_b"])
    if enc.empty:
        return empty

    e = enc[cols]
    multi = e.groupby("patient_id")["doctor_id"].transform("nunique") > 1
    e = e[multi].sort_values(["patient_id", "start_ts"], kind="stable")
    if e.empty:
        return empty

    pat = e["patient_id"].to_numpy()
    docs = e["doctor_id"].to_numpy()
    starts = e["start_ts"].to_numpy("datetime64[ns]").astype("int64")
    ends = e["end_ts"].to_numpy("datetime64[ns]").astype("int64")
    tol = int(tolerance_min * 60 * 1_000_000_000)

    left, right = [], []
    n = len(e)
    for i in range(n):
        limit = ends[i] + tol
        j = i + 1
        while j < n and pat[j] == pat[i] and starts[j] < limit:
            if docs[j] != docs[i]:
                left.append(i)
                right.append(j)
            j += 1
    if not left:
        return empty

    li, ri = np.asarray(left), np.asarray(right)
    ids = e["encounter_id"].to_numpy()
    per = e["period"].to_numpy()
    st = e["start_ts"].to_numpy()
    return pd.DataFrame({"patient_id": pat[li], "period": per[li], "doctor_a": docs[li], "doctor_b": docs[ri],
                         "encounter_a": ids[li], "encounter_b": ids[ri], "start_a": st[li], "start_b": st[ri]})


def _doctor_pairs(w: pd.DataFrame) -> pd.DataFrame:
    """Pares de médicos con pacientes en común, por auto-unión sobre el paciente.

    Evita recorrer las D·(D−1)/2 combinaciones posibles: solo se generan los pares que
    realmente comparten al menos un paciente.
    """
    dp = w[["doctor_id", "patient_id"]].drop_duplicates()
    shared_pat = dp.groupby("patient_id")["doctor_id"].transform("size") > 1
    dp = dp[shared_pat]
    if dp.empty:
        return pd.DataFrame(columns=["doctor_a", "doctor_b", "shared_patients"])
    m = dp.merge(dp, on="patient_id", suffixes=("_a", "_b"))
    m = m[m["doctor_id_a"] < m["doctor_id_b"]]
    if m.empty:
        return pd.DataFrame(columns=["doctor_a", "doctor_b", "shared_patients"])
    out = m.groupby(["doctor_id_a", "doctor_id_b"]).size().rename("shared_patients").reset_index()
    return out.rename(columns={"doctor_id_a": "doctor_a", "doctor_id_b": "doctor_b"})


def _edges_frame(parts: list[pd.DataFrame]) -> pd.DataFrame:
    cols = ["period", "doctor_a", "doctor_b", "shared_patients", "jaccard", "same_peer_group"]
    return pd.concat(parts, ignore_index=True)[cols] if parts else pd.DataFrame(columns=cols)


def analyze_graph(encounters: pd.DataFrame, doctors: pd.DataFrame, cfg: GraphConfig) -> GraphResult:
    enc = encounters.copy()
    enc["start_ts"] = pd.to_datetime(enc["start_ts"])
    enc["end_ts"] = pd.to_datetime(enc["end_ts"])
    enc["period"] = pd.to_datetime(enc["date"]).dt.to_period("M").astype(str)
    peer = doctors.set_index("doctor_id")["peer_group"]

    sim = _simultaneous_pairs(enc, cfg.simultaneous_tolerance_min)

    metrics_parts, edge_parts, comm_rows, graphs = [], [], [], {}
    for period, ep in enc.groupby("period", sort=True):
        # ---- aristas médico–médico (pacientes en común) -----------------------------
        w = ep.groupby(["doctor_id", "patient_id"]).size().rename("n").reset_index()
        n_pat_by_doc = w.groupby("doctor_id")["patient_id"].size()
        pairs = _doctor_pairs(w)
        if not pairs.empty:
            union = (pairs["doctor_a"].map(n_pat_by_doc).to_numpy()
                     + pairs["doctor_b"].map(n_pat_by_doc).to_numpy()
                     - pairs["shared_patients"].to_numpy())
            pairs["jaccard"] = (pairs["shared_patients"] / np.where(union > 0, union, 1)).round(4)
            pairs["same_peer_group"] = (pairs["doctor_a"].map(peer).to_numpy()
                                        == pairs["doctor_b"].map(peer).to_numpy())
            pairs.insert(0, "period", period)
            edge_parts.append(pairs)

        doc_nodes = w["doctor_id"].unique().tolist()
        G = nx.Graph()
        G.add_nodes_from(doc_nodes)
        if not pairs.empty:
            G.add_edges_from((r.doctor_a, r.doctor_b, {"shared_patients": int(r.shared_patients),
                                                       "jaccard": float(r.jaccard)})
                             for r in pairs.itertuples(index=False))
        graphs[period] = G

        # ---- comunidades (solo aristas con peso relevante) -------------------------
        H = nx.Graph()
        H.add_nodes_from(doc_nodes)
        H.add_edges_from((a, b, d) for a, b, d in G.edges(data=True)
                         if d["shared_patients"] >= cfg.community_min_shared)
        comms = list(nx.community.greedy_modularity_communities(H, weight="shared_patients")) if H.number_of_edges() else []
        comm_of = {d: (k, len(c)) for k, c in enumerate(comms) for d in c}
        comm_rows.extend({"doctor_id": d, "period": period,
                          "community": comm_of.get(d, (-1, 1))[0],
                          "community_size": comm_of.get(d, (-1, 1))[1]} for d in doc_nodes)

        # ---- concentración de cartera (agregados vectorizados) ---------------------
        total = w.groupby("doctor_id")["n"].transform("sum")
        w["share"] = w["n"] / total
        w["share2"] = w["share"] ** 2
        w["rank"] = w.groupby("doctor_id")["share"].rank(method="first", ascending=False)
        g = w.groupby("doctor_id")
        m = pd.DataFrame({
            "encounters": g["n"].sum(),
            "unique_patients": g["patient_id"].size(),
            "patient_hhi": g["share2"].sum(),
            "top5_patient_share": w[w["rank"] <= 5].groupby("doctor_id")["share"].sum(),
            "frequent_patients": g["n"].apply(lambda s: int((s >= cfg.max_visits_per_patient).sum())),
        })
        m["encounters_per_patient"] = m["encounters"] / m["unique_patients"].replace(0, np.nan)

        # ---- vínculos: pacientes compartidos y enlace más fuerte -------------------
        if pairs.empty:
            m["shared_patients"] = 0
            m["n_linked_doctors"] = 0
            m["strongest_link"] = None
            m["strongest_link_shared"] = 0
            m["strongest_link_jaccard"] = 0.0
        else:
            both = pd.concat([
                pairs.rename(columns={"doctor_a": "doctor_id", "doctor_b": "other"}),
                pairs.rename(columns={"doctor_b": "doctor_id", "doctor_a": "other"}),
            ], ignore_index=True)
            # pacientes distintos compartidos con cualquier otro médico
            dp = w[["doctor_id", "patient_id"]].drop_duplicates()
            n_docs_per_patient = dp.groupby("patient_id")["doctor_id"].transform("size")
            shared_counts = dp[n_docs_per_patient > 1].groupby("doctor_id").size()
            m["shared_patients"] = shared_counts.reindex(m.index).fillna(0).astype(int)
            m["n_linked_doctors"] = both.groupby("doctor_id").size().reindex(m.index).fillna(0).astype(int)
            best = both.loc[both.groupby("doctor_id")["shared_patients"].idxmax()].set_index("doctor_id")
            m["strongest_link"] = best["other"].reindex(m.index)
            m["strongest_link_shared"] = best["shared_patients"].reindex(m.index).fillna(0).astype(int)
            m["strongest_link_jaccard"] = best["jaccard"].reindex(m.index).fillna(0.0)
        m["shared_patient_ratio"] = m["shared_patients"] / m["unique_patients"].replace(0, np.nan)

        # ---- coincidencias temporales ------------------------------------------------
        sim_p = sim[sim["period"] == period] if len(sim) else sim
        if len(sim_p):
            long = pd.concat([sim_p[["doctor_a", "patient_id"]].rename(columns={"doctor_a": "doctor_id"}),
                              sim_p[["doctor_b", "patient_id"]].rename(columns={"doctor_b": "doctor_id"})],
                             ignore_index=True)
            m["simultaneous_encounters"] = long.groupby("doctor_id").size().reindex(m.index).fillna(0).astype(int)
            m["simultaneous_patients"] = (long.drop_duplicates().groupby("doctor_id").size()
                                          .reindex(m.index).fillna(0).astype(int))
        else:
            m["simultaneous_encounters"] = 0
            m["simultaneous_patients"] = 0

        m["community"] = [comm_of.get(d, (-1, 1))[0] for d in m.index]
        m["community_size"] = [comm_of.get(d, (-1, 1))[1] for d in m.index]
        m["period"] = period
        m["peer_group"] = m.index.map(peer)
        metrics_parts.append(m.reset_index())

    metrics = pd.concat(metrics_parts, ignore_index=True) if metrics_parts else pd.DataFrame()
    if metrics.empty:
        return GraphResult(metrics, _edges_frame(edge_parts), pd.DataFrame(comm_rows), sim, graphs)

    # ---- desviación frente a pares y score --------------------------------------------
    grp = metrics.groupby(["peer_group", "period"])
    for m in ("shared_patient_ratio", "patient_hhi", "encounters_per_patient", "strongest_link_jaccard"):
        metrics[f"{m}_z"] = grp[m].transform(_robust_z).fillna(0)
        metrics[f"{m}_peer_median"] = grp[m].transform("median")
    # Riesgos con umbral absoluto y compuerta relativa a pares: evita que la variación
    # normal del grupo (p. ej. más horas → más visitas por paciente) se lea como red.
    shared_gate = np.maximum(2 * metrics["shared_patient_ratio_peer_median"], 0.25)
    metrics["r_shared"] = ((metrics["shared_patient_ratio"] - shared_gate) / cfg.shared_ratio_saturation).clip(0, 1)
    epp_ratio = metrics["encounters_per_patient"] / metrics["encounters_per_patient_peer_median"].clip(lower=0.1)
    metrics["r_concentration"] = ((epp_ratio - cfg.concentration_gate) / cfg.concentration_gate).clip(0, 1)
    metrics["r_simultaneous"] = (metrics["simultaneous_encounters"] / cfg.simultaneous_saturation).clip(0, 1)
    metrics["frequent_patient_ratio"] = (metrics["frequent_patients"] / metrics["unique_patients"].clip(lower=1))
    metrics["r_frequent"] = (metrics["frequent_patient_ratio"] / cfg.frequent_ratio_saturation).clip(0, 1)
    r = metrics[["r_shared", "r_concentration", "r_simultaneous", "r_frequent"]]
    metrics["graph_risk"] = (100 * (0.6 * r.max(axis=1) + 0.4 * r.mean(axis=1))).round(2)
    metrics["graph_explanation"] = metrics.apply(_explain, axis=1)
    return GraphResult(metrics, _edges_frame(edge_parts), pd.DataFrame(comm_rows), sim, graphs)


def _explain(row: pd.Series) -> str:
    parts = []
    if row["simultaneous_encounters"] > 0:
        parts.append(f"{int(row['simultaneous_encounters'])} atenciones a {int(row['simultaneous_patients'])} pacientes coinciden en el tiempo "
                     f"con atenciones de otro médico al mismo paciente (físicamente incompatible).")
    if row["r_shared"] >= 0.3 and row["strongest_link"]:
        parts.append(f"Comparte {row['shared_patient_ratio']:.0%} de sus pacientes con otros médicos (mediana del grupo "
                     f"{row['shared_patient_ratio_peer_median']:.0%}); vínculo más fuerte con {row['strongest_link']} "
                     f"({int(row['strongest_link_shared'])} pacientes en común, Jaccard {row['strongest_link_jaccard']:.2f}).")
    if row["r_concentration"] > 0:
        parts.append(f"Actividad concentrada: 5 pacientes reúnen {row['top5_patient_share']:.0%} de las atenciones "
                     f"({row['encounters_per_patient']:.1f} atenciones por paciente vs {row['encounters_per_patient_peer_median']:.1f} del grupo).")
    if row["r_frequent"] > 0:
        parts.append(f"{int(row['frequent_patients'])} pacientes ({row['frequent_patient_ratio']:.0%} de su cartera) con frecuencia de visitas implausible en el mes.")
    if row["community"] >= 0 and row["community_size"] >= 2 and row["r_shared"] >= 0.3:
        parts.append(f"Pertenece a una comunidad de {int(row['community_size'])} médicos que comparten un pool de pacientes.")
    return " ".join(parts)


def ego_network(result: GraphResult, doctor_id: str, period: str, min_shared: int = 1) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Nodos y aristas del vecindario de un médico para visualización."""
    G = result.doctor_graph.get(period)
    if G is None or doctor_id not in G:
        return pd.DataFrame(columns=["doctor_id"]), pd.DataFrame(columns=["doctor_a", "doctor_b", "shared_patients"])
    nbrs = [o for o in G.neighbors(doctor_id) if G[doctor_id][o]["shared_patients"] >= min_shared]
    nodes = [doctor_id] + nbrs
    sub = G.subgraph(nodes)
    edges = pd.DataFrame([{"doctor_a": a, "doctor_b": b, "shared_patients": d["shared_patients"], "jaccard": d["jaccard"]}
                          for a, b, d in sub.edges(data=True)])
    return pd.DataFrame({"doctor_id": nodes}), edges
