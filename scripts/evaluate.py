"""Does the brain really drive the fly? Closed-loop tasks, alcohol dose-response and shuffled control.

  uv run python scripts/evaluate.py tasks                     # sober tasks (validation seeds)
  uv run python scripts/evaluate.py tasks --test              # the same on the test seeds, once
  uv run python scripts/evaluate.py tasks --brain shuffled    # same readout, shuffled wiring
  uv run python scripts/evaluate.py alcohol                   # behaviour vs ethanol level

Shuffled brain: every edge keeps its presynaptic neuron, weight and sign, but its target is permuted
(out- and in-degree preserved). Only "who connects to whom" is destroyed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mosca.readout import Readout                     # noqa: E402
from mosca.sim import BRAIN_FILE, READOUT_FILE, Sim, load_brain  # noqa: E402
from mosca.world import DT, TABLE_W                   # noqa: E402

ART = ROOT / "artifacts"
SHUF = ART / "brain_shuffled.npz"
_C = {}


def shuffle_brain(seed=1):
    z = dict(np.load(BRAIN_FILE, allow_pickle=False))
    n = int(z["n"])
    post = np.repeat(np.arange(n, dtype=np.int32), np.diff(z["indptr"]))
    pre, w = z["indices"], z["w"]
    new = np.random.default_rng(seed).permutation(post)
    ok = new != pre
    pre, new, w = pre[ok], new[ok], w[ok]
    o = np.argsort(new, kind="stable")
    pre, new, w = pre[o], new[o], w[o]
    ip = np.zeros(n + 1, np.int64)
    np.add.at(ip, new.astype(np.int64) + 1, 1)
    rs = np.zeros(n)
    np.add.at(rs, new, w.astype(np.float64))
    z.update(indptr=np.cumsum(ip), indices=pre.astype(np.int32), w=w,
             row_scale=(1.0 / np.maximum(rs, 1.0)).astype(np.float32))
    np.savez_compressed(SHUF, **z)


def ctx():
    if not _C:
        path = SHUF if os.environ.get("MOSCA_BRAIN") == "shuffled" else BRAIN_FILE
        br = load_brain(path)
        norms = json.loads((ART / "norms.json").read_text())
        _C.update(brain=br, norms=norms, readout=READOUT_FILE)
    return _C


def sim(seed):
    c = ctx()
    return Sim(c["brain"], seed=seed, norms=c["norms"], readout=Readout.load(c["readout"]))


# ------------------------------------------------------------------ tasks
def t_approach(seed, a=None):
    s = sim(seed)
    if a is not None:
        s.alcohol.freeze(a)
    s.world.place_fly()
    s.order("beer", 120, 420)
    drank = 0.0
    for k in range(int(25 / DT)):
        s.step()
    return {"reach": float(s.drunk > 0), "drank": s.drunk}


def t_sip(seed, kind):
    s = sim(seed)
    s.world.place_fly(360, 270, 0.0)
    p = s.order(kind, 100, 120)
    f = s.world.fly
    p.x, p.y = f.x + 4, f.y
    x0, y0 = f.x, f.y
    n = 0
    for _ in range(int(6 / DT)):
        s.step()
        f.x, f.y, f.z = x0, y0, 0.0
        n += int(f.sipping)
    return {"sip": float(n * DT > 0.5)}


def t_backward(seed):
    """Walk the fly into the wall head-on and see whether it backs up."""
    s = sim(seed)
    for _ in range(40):
        s.step()
    f = s.world.fly
    f.x, f.y, f.th, f.v = TABLE_W - 32, 270.0, float(np.random.default_rng(seed).normal(0, 0.2)), 60.0
    bumped, back = None, 0
    for k in range(int(4 / DT)):
        s.step()
        f = s.world.fly
        if f.bumped and bumped is None:
            bumped = k
        if bumped is not None and k - bumped < 60 and f.v < -5:
            back += 1
    return {"backward": float(back > 3)}


def t_escape(seed):
    s = sim(seed)
    took = 0
    for k in range(int(4 / DT)):
        if k == 45:
            s.tap(1.0)
        s.step()
        if k > 45 and s.world.fly.z > 0.15:
            took = 1
    return {"escape": float(took)}


def t_wander(seed, a=None, secs=40.0):
    s = sim(seed)
    if a is not None:
        s.alcohol.freeze(a)
    walk = down = asleep = 0
    last, worst, path, turn = 0.0, 0.0, 0.0, 0.0
    for k in range(int(secs / DT)):
        s.step()
        f = s.world.fly
        path += abs(f.v) * DT
        turn += abs(f.w) * DT
        if abs(f.v) > 8:
            walk += 1
            last = k * DT
        worst = max(worst, k * DT - last)
        down += int(f.pose != "up")
        asleep += int(s.act() == "asleep")
    n = int(secs / DT)
    return {"walk": walk / n, "stuck": worst, "down": down / n, "asleep": asleep / n,
            "speed": path / secs, "turn_per_dist": turn / max(path, 1.0)}


TASKS = {"approach": t_approach, "sip": t_sip, "backward": t_backward, "escape": t_escape,
         "wander": t_wander}


def _run(args):
    name, seed, kw = args
    return name, kw, TASKS[name](seed, **kw)


def cmd_tasks(a):
    base = 10000 if a.test else 2000
    jobs = []
    for i in range(a.n):
        jobs += [("approach", base + i, {}), ("sip", base + 100 + i, {"kind": "beer"}),
                 ("sip", base + 200 + i, {"kind": "garrafon"}), ("backward", base + 300 + i, {}),
                 ("escape", base + 400 + i, {})]
    jobs += [("wander", base + 500 + i, {}) for i in range(max(4, a.n // 4))]
    with Pool(a.workers) as pool:
        res = pool.map(_run, jobs)
    get = lambda nm, kw=None: [r for n, k, r in res if n == nm and (kw is None or k == kw)]
    w = get("wander")
    out = {"alcance": np.mean([r["reach"] for r in get("approach")]),
           "acepta_cerveza": np.mean([r["sip"] for r in get("sip", {"kind": "beer"})]),
           "rechaza_garrafon": 1 - np.mean([r["sip"] for r in get("sip", {"kind": "garrafon"})]),
           "marcha_atras": np.mean([r["backward"] for r in get("backward")]),
           "escape": np.mean([r["escape"] for r in get("escape")]),
           "anda": np.mean([r["walk"] for r in w]), "bloqueo_max_s": float(np.max([r["stuck"] for r in w])),
           "caidas_sobria": np.mean([r["down"] for r in w])}
    out = {k: round(float(v), 3) for k, v in out.items()}
    label = f"{'test' if a.test else 'validacion'}_{os.environ.get('MOSCA_BRAIN', 'real')}"
    p = ART / "evaluation.json"
    d = json.loads(p.read_text()) if p.exists() else {}
    d[label] = {"n": a.n, **out}
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    print(label, json.dumps(out, ensure_ascii=False))


def cmd_alcohol(a):
    levels = [0.0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 1.0]
    jobs = [("wander", 20000 + i, {"a": lv}) for lv in levels for i in range(a.n)]
    jobs += [("approach", 21000 + i, {"a": lv}) for lv in levels for i in range(a.n)]
    with Pool(a.workers) as pool:
        res = pool.map(_run, jobs)
    rows = []
    for lv in levels:
        w = [r for n, k, r in res if n == "wander" and k["a"] == lv]
        ap = [r for n, k, r in res if n == "approach" and k["a"] == lv]
        rows.append({"a": lv, "velocidad": round(float(np.mean([r["speed"] for r in w])), 1),
                     "anda": round(float(np.mean([r["walk"] for r in w])), 3),
                     "giro_por_distancia": round(float(np.mean([r["turn_per_dist"] for r in w])), 4),
                     "en_el_suelo": round(float(np.mean([r["down"] for r in w])), 3),
                     "sedada": round(float(np.mean([r["asleep"] for r in w])), 3),
                     "alcanza_y_bebe": round(float(np.mean([r["reach"] for r in ap])), 3)})
        print(json.dumps(rows[-1]), flush=True)
    label = os.environ.get("MOSCA_BRAIN", "real")
    p = ART / "alcohol_response.json"
    d = json.loads(p.read_text()) if p.exists() else {}
    d[label] = rows
    p.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["tasks", "alcohol", "shuffle"])
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--brain", choices=["real", "shuffled"], default="real")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.brain == "shuffled":
        os.environ["MOSCA_BRAIN"] = "shuffled"
        if not SHUF.exists():
            shuffle_brain()
    if a.cmd == "shuffle":
        shuffle_brain()
    else:
        {"tasks": cmd_tasks, "alcohol": cmd_alcohol}[a.cmd](a)
