"""Stress test of the whole live program: every situation a visitor can create, looking for failures
like the fly spinning in place.

For each scenario (several seeds, the live object exactly as the server runs it) it measures:
  vueltas   longest run turning to the same side at > 4,5 rad/s (s); > 1,5 s = a full turn on the spot
  sesgo     |sum of turning| / sum of |turning| (1 = always the same side)
  bloqueo   longest time standing still while up, sober-ish and not drinking (s)
  fuera     the fly left the arena; nan: a non-finite value in the network or the body
  sat       fraction of neurons at the ceiling of the rate model
  caídas    falls with ethanol below 0,5 (must be 0), and the longest time down in that range

  uv run python scripts/stress.py            # -> artifacts/stress.json
"""
from __future__ import annotations

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
from mosca.live import Live, load_model            # noqa: E402
from mosca.world import DT, MARGIN, TABLE_H, TABLE_W  # noqa: E402

_M = {}


def model():
    if not _M:
        _M["m"] = load_model()
    return _M["m"]


def setup(name, L):
    s = L.sim
    kinds = ["beer", "wine", "shot", "tequila", "garrafon"]
    if name in kinds:
        s.order(name, 100, 300)
    elif name == "mezcla":
        for k in ("garrafon", "tequila", "shot"):
            s.order(k, 100, 300)
    elif name.startswith("etanol_"):
        s.alcohol.freeze(float(name.split("_")[1]))
        s.order("beer", 100, 300)
        s.order("garrafon", 100, 300)
    elif name == "saciada":
        s.gut.freeze(0.0)
        s.order("beer", 100, 300)
    elif name == "esquina":
        f = s.world.fly
        f.x, f.y, f.th = MARGIN + 4, MARGIN + 4, -2.3
    elif name == "protocolo":
        L.start_demo()
    elif name == "vapor":
        L.vapor(60)
    elif name == "golpes":
        pass
    elif name == "caida_y_lavado":
        s.alcohol.freeze(0.85)


def run(args):
    name, seed, secs = args
    L = Live(seed=seed, model=model())
    for _ in range(30):
        L.step()
    setup(name, L)
    s = L.sim
    W, still, longest_still = [], 0, 0
    run_, sign, longest = 0, 0.0, 0
    out = nan = False
    sat = []
    falls_sober, prev_pose, down_s, max_down_sober = 0, "up", 0, 0
    t0 = time.perf_counter()
    for k in range(int(secs / DT)):
        if name == "golpes" and k % 90 == 45:
            L.tap()
        if name == "caida_y_lavado" and k == int(12 / DT):
            s.alcohol.freeze(None)
            L.reset()
        if name == "protocolo" and k % 150 == 0 and not s.world.puddles:
            s.order("beer", 60, 120)
        L.step()
        f = s.world.fly
        W.append(f.w)
        sg = math.copysign(1.0, f.w) if abs(f.w) > 4.5 else 0.0
        run_ = run_ + 1 if (sg != 0 and sg == sign) else (1 if sg != 0 else 0)
        sign = sg
        longest = max(longest, run_)
        moving = abs(f.v) > 3 or f.z > 0.05
        if f.pose == "up" and not f.sipping and not moving and s.alcohol.a < 0.6:
            still += 1
            longest_still = max(longest_still, still)
        else:
            still = 0
        if f.pose != "up" and prev_pose == "up" and s.alcohol.a < 0.5:
            falls_sober += 1                              # a fly below 0,5 of ethanol must not fall
        down_s = down_s + 1 if f.pose != "up" else 0
        if s.alcohol.a < 0.5:
            max_down_sober = max(max_down_sober, down_s)
        prev_pose = f.pose
        if not (MARGIN - 1 <= f.x <= TABLE_W - MARGIN + 1 and MARGIN - 1 <= f.y <= TABLE_H - MARGIN + 1):
            out = True
        h = s.state["h"]
        if not (np.isfinite(h).all() and all(map(math.isfinite, (f.x, f.y, f.th, f.v, f.w, f.z)))):
            nan = True
        if k % 30 == 0:
            sat.append(float((h >= s.brain.p.h_max - 1e-3).mean()))
        L.frame(1)                                        # the server builds a frame every tick
    W = np.asarray(W)
    return {"escenario": name, "seed": seed, "vueltas_s": longest * DT,
            "sesgo": float(abs(W.sum()) / max(np.abs(W).sum(), 1e-9)),
            "bloqueo_s": longest_still * DT, "fuera": out, "nan": nan, "sat": float(np.max(sat)),
            "ms_por_paso": (time.perf_counter() - t0) / (secs / DT) * 1000,
            "memoria_kc_mbon": L._memory(), "caidas_sin_alcohol": falls_sober,
            "suelo_sin_alcohol_s": max_down_sober * DT}


SCENARIOS = ["beer", "wine", "shot", "tequila", "garrafon", "mezcla", "etanol_0.3", "etanol_0.5",
             "etanol_0.65", "saciada", "esquina", "golpes", "vapor", "caida_y_lavado", "protocolo"]


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    jobs = [(n, 4000 + i, 240.0 if n == "protocolo" else 40.0) for n in SCENARIOS for i in range(6)]
    with Pool(8) as pool:
        res = pool.map(run, jobs)
    rows = []
    for n in SCENARIOS:
        r = [x for x in res if x["escenario"] == n]
        row = {"escenario": n, "vueltas_max_s": round(max(x["vueltas_s"] for x in r), 2),
               "moscas_que_dan_vueltas": sum(x["vueltas_s"] > 1.5 for x in r),
               "sesgo_medio": round(float(np.mean([x["sesgo"] for x in r])), 2),
               "bloqueo_max_s": round(max(x["bloqueo_s"] for x in r), 1),
               "fuera": sum(x["fuera"] for x in r), "nan": sum(x["nan"] for x in r),
               "sat_max": round(max(x["sat"] for x in r), 4),
               "ms_por_paso": round(float(np.mean([x["ms_por_paso"] for x in r])), 2),
               "memoria_kc_mbon": round(max(x["memoria_kc_mbon"] for x in r), 3),
               "caidas_sin_alcohol": sum(x["caidas_sin_alcohol"] for x in r),
               "suelo_sin_alcohol_max_s": round(max(x["suelo_sin_alcohol_s"] for x in r), 1)}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    (ROOT / "artifacts" / "stress.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
