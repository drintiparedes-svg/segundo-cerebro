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
    """Mismo paciente con dos médicos distintos cuyas atenciones se solapan en el tiempo."""
    e = enc[["encounter_id", "doctor_id", "patient_id", "period", "start_ts", "end_ts"]].sort_values(["patient_id", "start_ts"])
    tol = pd.Timedelta(minutes=tolerance_min)
    rows = []
    for pid, g in e.groupby("patient_id", sort=False):
        if g["doctor_id"].nunique() < 2 or len(g) < 2:
            continue
        starts, ends, docs, ids, per = g["start_ts"].to_numpy(), g["end_ts"].to_numpy(), g["doctor_id"].to_numpy(), g["encounter_id"].to_numpy(), g["period"].to_numpy()
        n = len(g)
        for i in range(n):
            for j in range(i + 1, n):
                if starts[j] >= ends[i] + tol:
                    break
                if docs[i] != docs[j] and starts[j] < ends[i] + tol:
                    rows.append({"patient_id": pid, "period": per[i], "doctor_a": docs[i], "doctor_b": docs[j],
                                 "encounter_a": ids[i], "encounter_b": ids[j], "start_a": starts[i], "start_b": starts[j]})
    return pd.DataFrame(rows, columns=["patient_id", "period", "doctor_a", "doctor_b", "encounter_a", "encounter_b", "start_a", "start_b"])


def analyze_graph(encounters: pd.DataFrame, doctors: pd.DataFrame, cfg: GraphConfig) -> GraphResult:
    enc = encounters.copy()
    enc["start_ts"] = pd.to_datetime(enc["start_ts"])
    enc["end_ts"] = pd.to_datetime(enc["end_ts"])
    enc["period"] = pd.to_datetime(enc["date"]).dt.to_period("M").astype(str)
    peer = doctors.set_index("doctor_id")["peer_group"]

    sim = _simultaneous_pairs(enc, cfg.simultaneous_tolerance_min)

    metrics_rows, edge_rows, comm_rows, graphs = [], [], [], {}
    for period, ep in enc.groupby("period", sort=True):
        # ---- grafo bipartito -------------------------------------------------------
        w = ep.groupby(["doctor_id", "patient_id"]).size().rename("n").reset_index()
        B = nx.Graph()
        B.add_nodes_from(w["doctor_id"].unique(), bipartite="doctor")
        B.add_nodes_from(w["patient_id"].unique(), bipartite="patient")
        B.add_weighted_edges_from(w[["doctor_id", "patient_id", "n"]].itertuples(index=False, name=None))
        doc_nodes = [n for n, d in B.nodes(data=True) if d.get("bipartite") == "doctor"]

        # ---- proyección médico–médico (pacientes compartidos) ----------------------
        patients_of = {d: set(B.neighbors(d)) for d in doc_nodes}
        G = nx.Graph()
        G.add_nodes_from(doc_nodes)
        docs_sorted = sorted(doc_nodes)
        for i, a in enumerate(docs_sorted):
            for b in docs_sorted[i + 1:]:
                shared = patients_of[a] & patients_of[b]
                if shared:
                    union = len(patients_of[a] | patients_of[b])
                    jac = len(shared) / union if union else 0.0
                    G.add_edge(a, b, shared_patients=len(shared), jaccard=jac)
                    edge_rows.append({"period": period, "doctor_a": a, "doctor_b": b, "shared_patients": len(shared),
                                      "jaccard": round(jac, 4), "same_peer_group": peer.get(a) == peer.get(b)})
        graphs[period] = G

        # ---- comunidades (solo aristas con peso relevante) -------------------------
        H = nx.Graph()
        H.add_nodes_from(doc_nodes)
        H.add_edges_from((a, b, d) for a, b, d in G.edges(data=True) if d["shared_patients"] >= cfg.community_min_shared)
        comms = list(nx.community.greedy_modularity_communities(H, weight="shared_patients")) if H.number_of_edges() else []
        comm_of = {}
        for k, c in enumerate(comms):
            for d in c:
                comm_of[d] = (k, len(c))
        for d in doc_nodes:
            k, size = comm_of.get(d, (-1, 1))
            comm_rows.append({"doctor_id": d, "period": period, "community": k, "community_size": size})

        # ---- métricas por médico ----------------------------------------------------
        sim_p = sim[sim["period"] == period]
        sim_count = pd.concat([sim_p["doctor_a"], sim_p["doctor_b"]]).value_counts()
        sim_patients = pd.concat([sim_p[["doctor_a", "patient_id"]].rename(columns={"doctor_a": "doctor_id"}),
                                  sim_p[["doctor_b", "patient_id"]].rename(columns={"doctor_b": "doctor_id"})]).drop_duplicates()
        sim_patients = sim_patients.groupby("doctor_id").size()
        for d in doc_nodes:
            wd = w[w["doctor_id"] == d]
            n_enc = int(wd["n"].sum())
            n_pat = int(len(wd))
            shares = (wd["n"] / n_enc).to_numpy() if n_enc else np.array([])
            hhi = float((shares ** 2).sum()) if n_enc else 0.0
            top5_share = float(np.sort(shares)[::-1][:5].sum()) if n_enc else 0.0
            frequent = int((wd["n"] >= cfg.max_visits_per_patient).sum())
            shared_pat = set().union(*[patients_of[d] & patients_of[o] for o in G.neighbors(d)]) if G.degree(d) else set()
            shared_ratio = len(shared_pat) / n_pat if n_pat else 0.0
            strongest = max(((o, G[d][o]["shared_patients"], G[d][o]["jaccard"]) for o in G.neighbors(d)),
                            key=lambda t: t[1], default=(None, 0, 0.0))
            k, size = comm_of.get(d, (-1, 1))
            metrics_rows.append({
                "doctor_id": d, "period": period, "peer_group": peer.get(d),
                "unique_patients": n_pat, "encounters": n_enc,
                "encounters_per_patient": n_enc / n_pat if n_pat else 0.0,
                "patient_hhi": hhi, "top5_patient_share": top5_share,
                "frequent_patients": frequent,
                "shared_patients": len(shared_pat), "shared_patient_ratio": shared_ratio,
                "n_linked_doctors": int(G.degree(d)),
                "strongest_link": strongest[0], "strongest_link_shared": int(strongest[1]), "strongest_link_jaccard": float(strongest[2]),
                "simultaneous_encounters": int(sim_count.get(d, 0)),
                "simultaneous_patients": int(sim_patients.get(d, 0)),
                "community": k, "community_size": size,
            })

    metrics = pd.DataFrame(metrics_rows)
    if metrics.empty:
        return GraphResult(metrics, pd.DataFrame(edge_rows), pd.DataFrame(comm_rows), sim, graphs)

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
    return GraphResult(metrics, pd.DataFrame(edge_rows), pd.DataFrame(comm_rows), sim, graphs)


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
