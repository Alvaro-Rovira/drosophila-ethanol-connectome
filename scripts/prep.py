"""The 20.000-neuron subcircuit, chosen by FUNCTION so that the brain can actually move the fly.

The previous selection (sensory inputs -> descending neurons in <= 3 hops) had no motor neuron at
all, no MDN, no giant fibre, no DNp09 and no olfactory receptor: those neurons could not drive the
legs, so a script had to. Here the quotas put inside, in this order:

  anclas       identified descending neurons (DNp09, DNa01/02, MDN, giant fibre...) and every motor pool
  descendentes every descending neuron
  sensoriales  olfactory, gustatory, Johnston organ and antennal touch receptors
  socios       strongest presynaptic partners (1 and 2 hops) of the anchors: without them an anchor is mute
  vias         for each sensory -> anchor pathway, the neurons with the most path flow between them
  premotoras   VNC neurons that receive from descending neurons and reach the motor neurons
  relleno      the rest, by path flow sensors -> descending/motor in <= 4 hops

The 20.000 version adds, before the partners: every olfactory receptor, leg taste and
proprioceptors, every central monoaminergic neuron, the antennal lobe, the lateral horn, the mushroom
body (Kenyon cells by input from the projection neurons), the central complex and the internal-state
neurons (neurosecretory, enteric) with their partners.

  uv run python scripts/prep.py            # -> artifacts/brain.npz + docs/subcircuit-report.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.ipc as ipc
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mosca.anchors import ANCHOR_GROUPS, build as build_anchors, ids_of, load_annotations  # noqa: E402

DATA, ART, DOCS = ROOT / "data", ROOT / "artifacts", ROOT / "docs"
NT_FILE = DATA / "body-neurotransmitters-male-cns-v1.0.feather"
EDGES = DATA / "edges_w2.npz"
INH = {"gaba", "glutamate", "histamine"}
MONO = {"octopamine", "dopamine", "serotonin"}

CAP_SENSORY = 4600
CAP_GRN_LEG = 300
CAP_PROP_LEG = 600
CAP_PROP_HALTERE = 100
CAP_LH = 900
CAP_KC = 2000
CAP_CX = 1500
CAP_STATE = 400
CAP_PARTNERS = 2000
CAP_PATHWAY = 300
CAP_PREMOTOR = 2000
PATHWAYS = {
    "olfato_giro": (["ORN"], ["DNa01", "DNa02", "DNg13", "DNp09"]),
    "gusto_MN9": (["GRN_labellar", "GRN_pharyngeal"], ["MN9", "MN_feeding"]),
    "gusto_pata": (["GRN_leg"], ["MN9", "DNp09"]),
    "tacto_MDN": (["antennal_mech"], ["MDN", "DNa02"]),
    "vibracion_GF": (["JO_AB"], ["DNp01", "DNg11", "DNg12"]),
    "descendentes_patas": (["DNp09", "MDN", "DNa02"], ["MN_leg_T1", "MN_leg_T2", "MN_leg_T3"]),
}
SENSORY_ALL = ["ORN", "JO_AB", "antennal_mech", "GRN_labellar", "GRN_pharyngeal", "GRN_leg",
               "PROP_leg", "PROP_haltere"]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def neuron_table():
    df = load_annotations().sort_values("bodyId").reset_index(drop=True)
    nt = ipc.open_file(NT_FILE).read_all().select(["body", "consensus_nt"]).to_pandas()
    df["nt"] = df["bodyId"].map(nt.set_index("body")["consensus_nt"]).fillna("unclear")
    df["sign"] = np.where(df["nt"].isin(INH), -1, 1).astype(np.int8)
    return df


def klass_of(sc, nt):
    sc = np.asarray(sc, str)
    out = np.full(len(sc), "inter", dtype="<U11")
    out[np.char.find(sc, "sensory") >= 0] = "sensory"
    out[sc == "descending_neuron"] = "descending"
    out[np.isin(sc, ["vnc_motor", "cb_motor", "vnc_efferent", "cb_efferent"])] = "motor"
    out[np.isin(np.asarray(nt, str), list(MONO)) & (out == "inter")] = "modulatory"
    return out


def spread(P, seeds, hops):
    f = np.zeros(P.shape[0], np.float32)
    f[seeds] = 1.0
    acc = np.zeros_like(f)
    for _ in range(hops):
        f = P @ f
        acc += f
    return acc


def topk(src, dst, w, n, targets, k):
    m = np.zeros(n, bool)
    m[targets] = True
    c = np.where(m[src])[0]
    if not len(c):
        return np.array([], np.int64)
    o = c[np.lexsort((-w[c].astype(np.int64), src[c]))]
    g = src[o]
    first = np.r_[True, g[1:] != g[:-1]]
    rank = np.arange(len(g)) - np.maximum.accumulate(np.where(first, np.arange(len(g)), 0))
    return dst[o[rank < k]]


def select(df, a, pre, post, w, target):
    n = len(df)
    ids = df["bodyId"].to_numpy()
    sc = df["superclass"].to_numpy().astype(str)
    nt = df["nt"].to_numpy().astype(str)
    pos = lambda b: np.searchsorted(ids, np.asarray(b, np.int64))
    M = sp.csr_matrix((w.astype(np.float32), (post, pre)), shape=(n, n))
    P = (sp.diags(1.0 / np.maximum(np.asarray(M.sum(1)).ravel(), 1.0)).astype(np.float32) @ M).tocsr()
    PT = P.T.tocsr()
    anchors = pos(ids_of(a, *ANCHOR_GROUPS))
    sens = pos(ids_of(a, *SENSORY_ALL))
    dn = pos(ids_of(a, "DN_all"))
    mn = pos(ids_of(a, "MN_all"))
    score = spread(P, sens, 4) * (spread(PT, anchors, 4) + 0.25 * spread(PT, np.union1d(dn, mn), 4))
    reach_dn = spread(PT, dn, 4)
    taken = np.zeros(n, bool)
    chosen = {}

    def take(name, cand, cap=None, key=None):
        cand = np.unique(np.asarray(cand, np.int64))
        cand = cand[~taken[cand]]
        if cap is not None and len(cand) > cap:
            cand = cand[np.argsort(-(score if key is None else key)[cand], kind="stable")[:cap]]
        cap_left = target - int(taken.sum())
        cand = cand[:max(cap_left, 0)]
        taken[cand] = True
        chosen[name] = cand
        log(f"  {name:22s} {len(cand):5d}   (total {int(taken.sum()):5d})")

    def inflow(src):
        """Synapses each neuron receives from the set src (1 hop)."""
        m = np.zeros(n, bool)
        m[src] = True
        return np.bincount(post[m[pre]], weights=w[m[pre]], minlength=n)

    take("anclas", np.concatenate([anchors, pos(ids_of(a, "APL", "EPG"))]))
    take("descendentes", dn)
    # sensory: taste, touch, vibration and every olfactory receptor first; then the leg taste and
    # proprioceptive neurons that reach the descending neurons the most
    prio = pos(ids_of(a, "GRN_labellar", "GRN_pharyngeal", "antennal_mech", "JO_AB", "ORN"))
    key = np.where(np.isin(np.arange(n), prio), 1e9, reach_dn)
    take("sensoriales", prio, None)
    take("gusto_pata", pos(ids_of(a, "GRN_leg")), CAP_GRN_LEG, key)
    take("propioceptores_pata", pos(ids_of(a, "PROP_leg")), CAP_PROP_LEG, key)
    take("propioceptores_halterio", pos(ids_of(a, "PROP_haltere")), CAP_PROP_HALTERE, key)
    mono = np.where(np.isin(nt, list(MONO)) & ~np.isin(sc, ["visual_centrifugal", "ol_intrinsic"]))[0]
    take("monoaminergicas", mono)
    take("lobulo_antenal", pos(ids_of(a, "ALPN", "ALLN")))
    pn = pos(ids_of(a, "ALPN"))
    from_pn = inflow(pn)
    take("cuerno_lateral", pos(ids_of(a, "LH")), CAP_LH, from_pn)
    take("cuerpo_fungiforme", pos(ids_of(a, "MBON", "DAN")))
    take("celulas_de_Kenyon", pos(ids_of(a, "KC")), CAP_KC, from_pn)
    take("complejo_central", pos(ids_of(a, "CX")), CAP_CX, reach_dn)
    state = pos(ids_of(a, "ENDO", "ENS", "SEZPN"))
    take("estado_interno", state)
    to_state = spread(P, pos(ids_of(a, "NUTRIENT", "ENS")), 1) + spread(PT, pos(ids_of(a, "ENDO")), 1)
    take("socios_estado_interno", np.where(to_state > 0)[0], CAP_STATE, to_state)
    h1 = topk(post, pre, w, n, anchors, 60)
    h2 = topk(post, pre, w, n, np.unique(h1), 16)
    take("socios_de_anclas", np.concatenate([h1, h2]), CAP_PARTNERS)
    for name, (src, dst) in PATHWAYS.items():
        k = spread(P, pos(ids_of(a, *src)), 4) * spread(PT, pos(ids_of(a, *dst)), 4)
        take(f"via_{name}", np.where(~taken & (k > 0))[0], CAP_PATHWAY, k)
    vnc = np.where(np.isin(sc, ["vnc_intrinsic", "ascending_neuron"]))[0]
    pk = spread(P, dn, 2) * spread(PT, mn, 2)
    take("premotoras", vnc[pk[vnc] > 0], CAP_PREMOTOR, pk)
    take("relleno", np.where(~taken & (score > 0))[0], target - int(taken.sum()))
    return chosen, taken


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=20000)
    ap.add_argument("--min-w", type=int, default=3)
    ap.add_argument("--out", default=str(ART / "brain.npz"))
    a_ = ap.parse_args()
    df = neuron_table()
    anchors = build_anchors(df)
    z = np.load(EDGES)
    assert int(z["n"]) == len(df)
    pre2, post2, w2 = z["pre"], z["post"], z["w"]
    s3 = w2 >= a_.min_w
    log(f"neuronas {len(df):,} · aristas >= {a_.min_w} sinapsis {int(s3.sum()):,}")
    chosen, taken = select(df, anchors, pre2[s3], post2[s3], w2[s3], a_.target)
    keep = np.where(taken)[0]
    n = len(keep)
    remap = np.full(len(df), -1, np.int64)
    remap[keep] = np.arange(n)
    m = (remap[pre2] >= 0) & (remap[post2] >= 0)
    p, q, w = remap[pre2[m]], remap[post2[m]], w2[m]
    ok = p != q
    p, q, w = p[ok], q[ok], w[ok]
    strong = w >= a_.min_w
    # a mandatory neuron with no strong edge inside would be isolated: give it back its strongest
    # real edges from the >= 2 synapse pool (documented in the report)
    mand = np.zeros(n, bool)
    mand[remap[np.concatenate([v for k, v in chosen.items() if k != "relleno"])]] = True
    deg = np.bincount(q[strong], minlength=n) + np.bincount(p[strong], minlength=n)
    dead = np.where(mand & (deg == 0))[0]
    add = np.zeros(len(w), bool)
    if len(dead):
        add[np.isin(q, dead) | np.isin(p, dead)] = True
    keepe = strong | add
    p, q, w = p[keepe], q[keepe], w[keepe]
    o = np.argsort(q, kind="stable")
    p, q, w = p[o].astype(np.int32), q[o], w[o].astype(np.uint16)
    indptr = np.zeros(n + 1, np.int64)
    np.add.at(indptr, q + 1, 1)
    indptr = np.cumsum(indptr)
    rs = np.zeros(n)
    np.add.at(rs, q, w.astype(np.float64))
    sub = df.iloc[keep]
    nt = sub["nt"].to_numpy().astype(str)
    klass = klass_of(sub["superclass"].to_numpy(), nt)
    ids = df["bodyId"].to_numpy()
    groups = {}
    for gname, g in anchors.items():
        for side in ("L", "R", "U"):
            if g[side]:
                loc = remap[np.searchsorted(ids, np.array(g[side], np.int64))]
                loc = loc[loc >= 0]
                if len(loc):
                    groups[f"grp_{gname}|{side}"] = loc.astype(np.int32)
    soma = np.full((n, 3), np.nan, np.float32)
    for i, v in enumerate(sub["somaLocation"].to_numpy()):
        if v is not None and len(v) == 3:
            soma[i] = v
    # checks
    A = sp.csr_matrix((np.ones(len(w), np.int8), (q, p)), shape=(n, n))
    seen = np.zeros(n, bool)
    sens_local = remap[np.searchsorted(ids, ids_of(anchors, *SENSORY_ALL))]
    sens_local = sens_local[sens_local >= 0]
    seen[sens_local] = True
    front = seen.copy()
    for _ in range(4):
        nxt = (A @ front.astype(np.int8)) > 0
        nxt &= ~seen
        seen |= nxt
        front = nxt
    ncomp, lbl = sp.csgraph.connected_components(A, directed=True, connection="weak")
    degf = np.bincount(q, minlength=n) + np.bincount(p, minlength=n)
    anc_local = remap[np.searchsorted(ids, ids_of(anchors, *ANCHOR_GROUPS))]
    anc_local = anc_local[anc_local >= 0]
    checks = {"descendentes_alcanzadas": round(float(seen[klass == "descending"].mean()), 4),
              "motoras_alcanzadas": round(float(seen[klass == "motor"].mean()), 4),
              "componente_mayor": round(float(np.bincount(lbl).max() / n), 4),
              "anclas_aisladas": int((degf[anc_local] == 0).sum()),
              "rescatadas": int(len(dead))}
    np.savez_compressed(
        a_.out, indptr=indptr, indices=p, w=w, row_scale=(1.0 / np.maximum(rs, 1.0)).astype(np.float32),
        sign=sub["sign"].to_numpy().astype(np.int8), klass=klass, body_id=sub["bodyId"].to_numpy(),
        superclass=sub["superclass"].to_numpy().astype(str), cell_type=sub["type"].to_numpy().astype(str),
        side=sub["side"].to_numpy().astype(str), instance=sub["instance"].to_numpy().astype(str), nt=nt, soma_xyz=soma, n=np.int64(n), **groups)
    counts = {k: int((klass == k).sum()) for k in np.unique(klass)}
    info = {"N": n, "aristas": int(len(w)), "cupos": {k: int(len(v)) for k, v in chosen.items()},
            "clases": counts, "inhibitorias": round(float((sub["sign"] < 0).mean()), 4), "checks": checks,
            "anclas_dentro": {g: int(sum(len(v) for k, v in groups.items() if k[4:].split("|")[0] == g))
                              for g in list(anchors)}}
    (ART / "brain_info.json").write_text(json.dumps(info, indent=1, ensure_ascii=False))
    DOCS.mkdir(exist_ok=True)
    (DOCS / "subcircuit-report.md").write_text(report(info))
    log(json.dumps({k: info[k] for k in ("N", "aristas", "clases", "checks")}, ensure_ascii=False))


def report(info):
    L = [f"# Subcircuito de {info['N']:,} neuronas".replace(",", "."), "",
         f"**N = {info['N']:,}** neuronas reales de MaleCNS v1.0 · **{info['aristas']:,} conexiones** (>= 3 sinapsis).",
         "", "## Por qué se eligieron así", "",
         "La selección anterior (entradas sensoriales -> descendentes en <= 3 saltos) no tenía **ninguna**",
         "motoneurona, ni MDN, ni la fibra gigante, ni DNp09, ni receptores olfativos. Esas neuronas no",
         "podían mover las patas, así que un guion tenía que hacerlo. Ahora se eligen por cupos de función",
         "para que estén las que perciben, las que deciden y las que mueven, y los circuitos completos del",
         "olfato, el cuerpo fungiforme, el complejo central y el estado interno.", "",
         "| Cupo | Neuronas |", "|---|---:|"]
    L += [f"| {k} | {v:,} |" for k, v in info["cupos"].items()]
    L += ["", "| Clase | Neuronas |", "|---|---:|"]
    L += [f"| {k} | {v:,} |" for k, v in info["clases"].items()]
    c = info["checks"]
    L += ["", f"Inhibitorias (GABA, glutamato, histamina): {info['inhibitorias']*100:.1f}%.", "",
          "## Comprobaciones", "",
          f"- Descendentes que reciben señal de los sensores en <= 4 saltos: **{c['descendentes_alcanzadas']*100:.1f}%**.",
          f"- Motoneuronas que la reciben: **{c['motoras_alcanzadas']*100:.1f}%**.",
          f"- Componente conexa dominante: **{c['componente_mayor']*100:.1f}%** de las neuronas.",
          f"- Neuronas identificadas aisladas: **{c['anclas_aisladas']}**.",
          f"- {c['rescatadas']} neuronas obligatorias sin ninguna arista de >= 3 sinapsis dentro recuperan sus"
          " aristas reales de >= 2 sinapsis (no se inventa ninguna).", "",
          "## Neuronas identificadas dentro", "", "| Grupo | Neuronas |", "|---|---:|"]
    L += [f"| {k} | {v} |" for k, v in info["anclas_dentro"].items() if v]
    L += ["", "Signos: acetilcolina, dopamina, serotonina y octopamina excitan; GABA, glutamato e histamina",
          "inhiben; desconocido excita (simplificación de nfly). **El cableado no se modifica nunca.**", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
