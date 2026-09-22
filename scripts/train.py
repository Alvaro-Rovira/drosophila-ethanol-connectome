"""Training of the only learned piece: the steering readout. The wiring is never touched.

  uv run python scripts/train.py norms        # sober reference rate of every identified group
  uv run python scripts/train.py readout      # DAgger, chosen by CLOSED-LOOP reach, not by R2

Seeds: training 0-1999, validation 2000-2999, test 10000+ (scripts/evaluate.py, once).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mosca.readout import ZCLIP, Readout, design, feature_index, pairing, speed_mask     # noqa: E402
from mosca.sim import Sim, load_brain                # noqa: E402
from mosca.world import DT                           # noqa: E402

ART = ROOT / "artifacts"
LAMBDAS = (1e-6, 1e-5, 1e-4, 1e-3, 1e-2)
# Robustness: a linear readout with too little regularisation amplifies activity it never saw in
# training (the ethanol-modulated network, the MBONs after learning) and pins the steering at its
# limit: the fly spins in place. It is NOT trained on drunk flies (that would teach it to undo the
# drug); the regularisation is chosen so that, with ethanol, the steering is not pinned.
SPIN_S = 1.5          # pinned to the same side this long = a full turn on the spot (5 rad/s)
DRUNK_VAL = (0.3, 0.5)
_C = {}


def ctx():
    if not _C:
        br = load_brain()
        s = Sim(br, seed=0, readout=None, norms={})
        feat = feature_index(br, s.senses)
        gl, gr, ng = pairing(br, feat)
        _C.update(brain=br, senses=s.senses, feat=feat, pair=(gl, gr, ng, speed_mask(br, feat)))
    return _C


def new_sim(seed, readout=None, norms=None):
    c = ctx()
    s = Sim(c["brain"], seed=seed, readout=readout, norms=norms, senses=c["senses"])
    return s


def episode(seed, beta, model, secs=25.0, collect=True, norms=None, a=None):
    c = ctx()
    ro = Readout(c["feat"], *model, *c["pair"]) if model is not None else None
    s = new_sim(seed, ro if ro is not None else None, norms)
    if ro is None:
        s.readout = None
    s.teacher = beta if ro is not None else 1.0
    if a is not None:
        s.alcohol.freeze(a)
    rng = np.random.default_rng(seed + 99)
    # every substance, alone and mixed: each one smells different (its own glomeruli), and a readout
    # trained only on beer and wine saturated (spun in place) with the odour of the others
    kinds = ["beer", "wine", "shot", "tequila", "garrafon"]
    for _ in range(1 + int(rng.integers(0, 3))):
        s.order(kinds[int(rng.integers(0, len(kinds)))], 120, 420)
    if rng.random() < 0.35:
        # start right in front of a wall: bumps are rare otherwise, and the readout would never
        # learn what the population does after an antennal touch
        from mosca.world import MARGIN, TABLE_H, TABLE_W
        side = int(rng.integers(0, 4))
        f = s.world.fly
        f.x, f.y, f.th = [(TABLE_W - MARGIN - 6, rng.uniform(80, TABLE_H - 80), 0.0),
                          (MARGIN + 6, rng.uniform(80, TABLE_H - 80), math.pi),
                          (rng.uniform(80, TABLE_W - 80), TABLE_H - MARGIN - 6, math.pi / 2),
                          (rng.uniform(80, TABLE_W - 80), MARGIN + 6, -math.pi / 2)][side]
        f.th += float(rng.normal(0, 0.3))
    X, Y, R = [], [], []
    reached, t_reach, sat, ticks = False, secs, 0, 0
    run, sign, longest = 0, 0.0, 0
    frozen = 0
    for k in range(int(secs / DT)):
        tick = s.acc + DT >= s.period
        s.step()
        if tick:
            ticks += 1
            sat += abs(s.cmd[0]) > 0.9            # steering pinned at its limit
            sg = float(np.sign(s.cmd[0])) if abs(s.cmd[0]) > 0.9 else 0.0
            run = run + 1 if (sg != 0 and sg == sign) else (1 if sg != 0 else 0)
            sign = sg
            longest = max(longest, run)
            f = s.world.fly
            frozen += f.pose == "up" and not f.sipping and abs(f.v) < 5 and f.z < 0.05
        if tick and collect:
            X.append(s.features(c["feat"]))
            Y.append(s.label)
        if norms is None and tick:
            R.append(s.raw)
        if not reached and s.world.contact_puddle() is not None:
            reached, t_reach = True, (k + 1) * DT
    return (np.asarray(X, np.float32), np.asarray(Y, np.float32),
            {"reach": float(reached), "t": t_reach, "sat": sat / max(ticks, 1),
             "spin_s": longest * s.period, "frozen": frozen / max(ticks, 1)}, R)


def _ep(args):
    return episode(*args)


# ------------------------------------------------------------------ norms
def cmd_norms(a):
    with Pool(a.workers) as pool:
        out = pool.map(_ep, [(3000 + i, 1.0, None, 25.0, False, None) for i in range(a.episodes)])
    rows = {}
    for _, _, _, R in out:
        for r in R:
            for g, v in r.items():
                rows.setdefault(g, []).append(v)
    norms = {g: {"mean": float(np.mean(v)), "std": float(np.std(v))} for g, v in rows.items()}
    (ART / "norms.json").write_text(json.dumps(norms, indent=1))
    print(f"{len(norms)} grupos -> artifacts/norms.json")
    for g in ("MN_leg_T1|L", "MN9|L", "MDN|L", "DNp01|L", "MN_wing_power|L"):
        print(f"  {g:18s} {norms[g]['mean']:.5f}")


# ------------------------------------------------------------------ readout
def cmd_readout(a):
    norms = json.loads((ART / "norms.json").read_text())
    c = ctx()
    gl, gr, ng, vmask = c["pair"]
    XtX = XtY = VtV = VtY = None
    n, mu, sd, model = 0, None, None, None
    cache: dict = {}
    best, hist, t0 = (None, -1e9), [], time.time()
    with Pool(a.workers) as pool:
        for rnd in range(a.rounds + 1):
            beta = 0.5 ** rnd
            jobs = [((rnd * 997 + i) % 2000, beta, model, 25.0, True, norms) for i in range(a.episodes)]
            out = pool.map(_ep, jobs)
            X = np.concatenate([o[0] for o in out]).astype(np.float64)
            Y = np.concatenate([o[1] for o in out]).astype(np.float64)
            if mu is None:
                mu, sd = X.mean(0), X.std(0) + 1e-6
            D, V = design(np.clip((X - mu) / sd, -ZCLIP, ZCLIP), gl, gr, ng, cache, vmask)
            if XtX is None:
                XtX, XtY = np.zeros((D.shape[1],) * 2), np.zeros(D.shape[1])
                VtV, VtY = np.zeros((V.shape[1],) * 2), np.zeros(V.shape[1])
            XtX += D.T @ D
            XtY += D.T @ Y[:, 0]                   # turn: only from left - right differences
            VtV += V.T @ V
            VtY += V.T @ Y[:, 1]                   # speed: from sums and unpaired neurons
            n += len(D)
            cands = []
            for lam in LAMBDAS:
                Wd = np.linalg.solve(XtX + lam * n * np.eye(len(XtX)), XtY)
                Wv = np.linalg.solve(VtV + lam * n * np.eye(len(VtV)), VtY)
                cands.append((lam, Wd, Wv))
            scores = []
            for lam, Wd, Wv in cands:
                m = (mu, sd, Wd, Wv)
                res = pool.map(_ep, [(2000 + i, 0.0, m, 25.0, False, norms) for i in range(a.val)])
                drunk = pool.map(_ep, [(2500 + i, 0.0, m, 20.0, False, norms, DRUNK_VAL[i % 2])
                                       for i in range(a.val // 2)])
                reach = float(np.mean([r[2]["reach"] for r in res]))
                sat = float(np.mean([r[2]["spin_s"] > SPIN_S for r in drunk]))    # episodes that spin
                frz = float(np.mean([r[2]["frozen"] for r in drunk]))              # time frozen in place
                score = reach - sat - max(0.0, frz - 0.3)
                scores.append((score, float(np.mean([r[2]["t"] for r in res])), lam, m, reach, sat, frz))
            scores.sort(key=lambda s: (-s[0], s[1]))
            score, t_mean, lam, model, reach, sat, frz = scores[0]
            row = {"ronda": rnd, "beta_experto": beta, "lambda": lam, "muestras": n,
                   "alcance_lazo_cerrado": round(reach, 3), "vueltas_sobre_si_con_etanol": round(sat, 3), "quieta_con_etanol": round(frz, 3),
                   "t_medio": round(t_mean, 1), "segundos": round(time.time() - t0)}
            hist.append(row)
            print(json.dumps(row), flush=True)
            if score > best[1]:
                best = (model, score)
    Readout(c["feat"], *best[0], gl, gr, ng, vmask).save(ART / "readout.npz")
    (ART / "train_log.json").write_text(json.dumps({"historial": hist, "alcance": best[1]}, indent=1))
    print("-> artifacts/readout.npz · alcance en lazo cerrado", best[1])


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["norms", "readout"])
    ap.add_argument("--episodes", type=int, default=96)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--val", type=int, default=24)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    {"norms": cmd_norms, "readout": cmd_readout}[a.cmd](a)
