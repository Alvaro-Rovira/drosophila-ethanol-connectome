"""Body thresholds taken from how the real neurons respond, not set by hand.

Each threshold is placed between two measured neural responses of the SOBER fly:
  sorbo    MN9 with sugar in the mouth (beer) vs with a bitter drink (garrafón), fly held on the drop
  escape   giant fibre after a knock on the table vs its highest resting value
  vuelo    flight-power motor neurons during the escape vs at rest
  acicalado / canto   well above the highest sober resting value (they only fire on a strong drive)
  postura  the legs give way below 55% of the sober tone; sober flies must never get there

  uv run python scripts/calibrate_motor.py      # -> artifacts/motor.json
"""
from __future__ import annotations

import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from mosca.body import MotorCfg          # noqa: E402
from mosca.world import DT               # noqa: E402
import train as T                         # noqa: E402

ART = ROOT / "artifacts"


def held_on_drop(args):
    seed, kind = args
    norms = json.loads((ART / "norms.json").read_text())
    s = T.new_sim(seed, norms=norms)
    s.world.place_fly(360, 270, 0.0)
    p = s.order(kind, 100, 120)
    f = s.world.fly
    p.x, p.y = f.x + 4, f.y
    x0, y0 = f.x, f.y
    s.body.c.sip_on = 1e9                 # measuring MN9 only: nothing may drink yet
    vals = []
    for k in range(int(4 / DT)):
        s.step()
        f.x, f.y, f.z = x0, y0, 0.0
        if k > 30 and s.rel:
            vals.append(np.mean(s.body.pair(s.rel, "MN9")))
    return kind, float(np.mean(vals))


def rest_and_tap(seed):
    norms = json.loads((ART / "norms.json").read_text())
    s = T.new_sim(seed, norms=norms)
    s.body.c.gf = 1e9
    rest = {"gf": [], "power": [], "groom": [], "song": [], "P": []}
    tap = {"gf": [], "power": []}
    for k in range(int(8 / DT)):
        if k == int(5 / DT):
            s.tap(1.0)
        s.step()
        if not s.rel:
            continue
        r = s.rel
        gf = max(s.body.pair(r, "DNp01"))
        pw = float(np.mean(s.body.pair(r, "MN_wing_power")))
        if k < int(5 / DT):
            rest["gf"].append(gf)
            rest["power"].append(pw)
            rest["groom"].append(max(*s.body.pair(r, "DNg11"), *s.body.pair(r, "DNg12")))
            rest["song"].append(max(s.body.pair(r, "pIP10")))
            rest["P"].append(s.bs["P"])
        elif k < int(5.6 / DT):
            tap["gf"].append(gf)
            tap["power"].append(pw)
    return rest, tap


def main():
    with Pool(6) as pool:
        drop = pool.map(held_on_drop, [(2100 + i, k) for i in range(12) for k in ("beer", "garrafon")])
        rt = pool.map(rest_and_tap, [2200 + i for i in range(16)])
    beer = [v for k, v in drop if k == "beer"]
    garr = [v for k, v in drop if k == "garrafon"]
    rest = {k: np.concatenate([np.asarray(r[0][k]) for r in rt]) for k in rt[0][0]}
    tap_gf = np.array([max(r[1]["gf"]) for r in rt])
    tap_pw = np.array([max(r[1]["power"]) for r in rt])
    c = MotorCfg()
    # sip: halfway (geometric) between the bitter and the sweet MN9 responses
    lo, hi = float(np.percentile(garr, 90)), float(np.percentile(beer, 10))
    c.sip_on = float(np.sqrt(max(lo, 1e-3) * max(hi, 1e-3))) if hi > lo else float(np.mean(beer))
    c.sip_off = 0.7 * c.sip_on
    c.gf = float(np.sqrt(max(np.percentile(rest["gf"], 99.9), 1e-3) * max(np.percentile(tap_gf, 10), 1e-3)))
    c.fly_keep = float(0.5 * (np.percentile(rest["power"], 99) + np.percentile(tap_pw, 50)))
    c.groom = float(1.5 * np.percentile(rest["groom"], 99.9))
    c.song = float(1.5 * np.percentile(rest["song"], 99.9))
    out = {**c.__dict__,
           "_medidas": {"MN9_cerveza": [round(float(np.min(beer)), 3), round(float(np.median(beer)), 3)],
                        "MN9_garrafon": [round(float(np.median(garr)), 3), round(float(np.max(garr)), 3)],
                        "GF_reposo_p99_9": round(float(np.percentile(rest["gf"], 99.9)), 3),
                        "GF_golpe_p10": round(float(np.percentile(tap_gf, 10)), 3),
                        "potencia_ala_reposo_p99": round(float(np.percentile(rest["power"], 99)), 3),
                        "potencia_ala_golpe": round(float(np.median(tap_pw)), 3),
                        "tono_patas_sobria_min": round(float(np.min(rest["P"])), 3)}}
    (ART / "motor.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    main()
