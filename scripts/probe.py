"""Regime probe: stability and responsiveness of the network for a few gains (development aid).

  uv run python scripts/probe.py --G 1.0 1.25
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mosca.brain import Brain, BrainParams    # noqa: E402
from mosca.senses import Senses               # noqa: E402

KEY = ["MN_leg_T1|L", "MN_leg_T2|L", "MN9|L", "MDN|L", "DNp09|L", "DNa02|L", "DNa02|R", "DNp01|L",
       "MN_wing_power|L", "KC|R", "MBON|R", "EPG|L", "LH|R", "ALPN|R"]


def run(br, se, obs, ticks=150):
    st = br.init_state(1)
    acc = []
    for k in range(ticks):
        h = br.step(st, se.encode(obs))
        if k >= ticks - 45:
            acc.append(h[:, 0].copy())
    return np.mean(acc, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--G", type=float, nargs="+", default=[1.25])
    ap.add_argument("--b", type=float, default=0.003)
    a = ap.parse_args()
    base = {"c_l": 0.0, "c_r": 0.0, "sweet": 0.0, "bitter": 0.0, "touch_l": 0.0, "touch_r": 0.0,
            "vib": 0.0, "arousal": 1.0, "v": 0.3, "w": 0.0, "z": 0.0, "th": 0.0}
    for G in a.G:
        br = Brain(ROOT / "artifacts" / "brain.npz", BrainParams(G=G, b=a.b))
        se = Senses(br, 4.0)
        conds = {"reposo": base, "olor_izq": {**base, "odor_lr": {"beer": (0.6, 0.4)}},
                 "olor_der": {**base, "odor_lr": {"beer": (0.4, 0.6)}},
                 "garrafon": {**base, "odor_lr": {"garrafon": (0.5, 0.5)}}, "dulce": {**base, "sweet": 0.6},
                 "amargo": {**base, "bitter": 0.8}, "tacto": {**base, "touch_l": 1.0, "touch_r": 1.0},
                 "vibracion": {**base, "vib": 1.0}}
        R = {k: run(br, se, o) for k, o in conds.items()}
        kc = np.concatenate([br.group("KC|L"), br.group("KC|R")])
        for k in ("olor_izq", "garrafon"):
            act = R[k][kc] > R["reposo"][kc] + 0.2
            print(f"  KC activadas por {k}: {act.mean()*100:.1f}%")
        a1 = R["olor_izq"][kc] > R["reposo"][kc] + 0.2
        a2 = R["garrafon"][kc] > R["reposo"][kc] + 0.2
        print(f"  solapamiento KC cerveza/garrafón (Jaccard): {(a1 & a2).sum() / max((a1 | a2).sum(), 1):.2f}")
        h = R["reposo"]
        print(f"\n=== G={G}  p50 {np.percentile(h,50):.4f} p99 {np.percentile(h,99):.3f} "
              f"saturadas {(h>4.9).mean()*100:.2f}%  activas>0.1 {(h>0.1).mean()*100:.1f}%")
        for k in ("sensory", "inter", "modulatory", "descending", "motor"):
            m = br.klass == k
            print(f"  {k:11s} media {h[m].mean():.4f} p99 {np.percentile(h[m],99):.3f}")
        print("  grupo            " + " ".join(f"{c[:9]:>9s}" for c in conds))
        for g in KEY:
            idx = br.group(g)
            if not len(idx):
                continue
            print(f"  {g:16s} " + " ".join(f"{R[c][idx].mean():9.4f}" for c in conds))


if __name__ == "__main__":
    main()
