"""Headless demo check: does the demo order list get the fly through the stages?

Nothing forces the stages: the fly has to find the drinks, decide with MN9 to drink them, and the
ethanol then acts on its neurons. Records the time each stage label is first reached and when the
fly first falls and loses the righting reflex.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mosca.live import Live, load_model  # noqa: E402
from mosca.world import DT               # noqa: E402

ORDER = ["sobria", "piripi", "pedo", "borracha", "ko"]


def run(seed: int, model, limit_s: float = 360.0):
    live = Live(seed=seed, model=model)
    live.start_demo()
    reached, first_fall, first_lorr, peak = {}, None, None, 0.0
    for n in range(int(limit_s / DT)):
        live.step()
        s = live.sim
        st = s.alcohol.stage()
        peak = max(peak, s.alcohol.a)
        if st in ORDER and st not in reached:
            reached[st] = round(live.t, 1)
        act = s.act()
        if act in ("fall", "asleep") and first_fall is None:
            first_fall = round(live.t, 1)
        if act == "asleep" and first_lorr is None:
            first_lorr = round(live.t, 1)
            break
    return {"seed": seed, "etapas": reached, "primera_caida_s": first_fall, "ko_s": first_lorr,
            "pico_a": round(peak, 3), "bebido": round(live.sim.drunk, 3)}


if __name__ == "__main__":
    model = load_model()
    seeds = [int(s) for s in sys.argv[1:]] or list(range(1, 11))
    res = [run(s, model) for s in seeds]
    for r in res:
        print(json.dumps(r, ensure_ascii=False))
    ok = sum(r["ko_s"] is not None for r in res)
    print(f"llega a KO (pérdida del reflejo de enderezamiento) en {ok}/{len(res)} semillas")
    (ROOT / "artifacts" / "demo_check.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
