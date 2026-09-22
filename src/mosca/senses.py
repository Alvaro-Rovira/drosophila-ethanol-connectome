"""What the fly senses, injected into its real receptor neurons.

  olfato   odour of each substance at each antenna -> left / right olfactory receptor neurons, by
           glomerulus (ORN_<glomerulus>): each substance has its own blend (configs/alcohol.yaml)
  gusto    sweet / bitter at the mouthparts -> labellar and pharyngeal gustatory neurons
  tacto    antennal touch (walls) -> left / right antennal mechanosensory neurons
  vibración a knock on the table -> Johnston organ (JO-A/B)
  arousal  a constant tonic drive to the monoaminergic neurons, so the fly is awake (ARBITRARIO)
  propiocepción  own walking speed -> leg proprioceptors (chordotonal, campaniform, hair plates);
           own turning -> haltere proprioceptors
  brújula  own heading -> E-PG neurons, as a bump over their protocerebral-bridge glomerulus
           (SIMPLIFICACIÓN: without vision the heading is injected there directly)
  hambre   gain of the sweet (up) and bitter (down) receptors (see gut.py; hormonal, not synaptic)

Gustatory neurons are annotated by organ, not by taste. Which ones carry "sweet" and which "bitter"
is decided ONCE from the wiring itself: each gustatory type is stimulated alone and classified by
its net effect on MN9, the proboscis motor neuron (artifacts/taste_split.json).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPLIT = ROOT / "artifacts" / "taste_split.json"
C_REF = 0.02


def _split(idx, n, rng):
    idx = np.asarray(idx, np.int64)
    if not len(idx):
        return [np.array([], np.int64)] * n
    return [np.sort(p) for p in np.array_split(rng.permutation(idx), n)]


def _bell(x, centers, width):
    return np.exp(-0.5 * ((x - centers) / width) ** 2)


def log_c(c: float) -> float:
    return math.log1p(max(c, 0.0) / C_REF) / math.log1p(1.0 / C_REF)


def cat(*ls):
    ls = [np.asarray(x, np.int64) for x in ls if len(x)]
    return np.unique(np.concatenate(ls)) if ls else np.array([], np.int64)


def _epg_angle(instance: str):
    """'EPG(PB08)_R3' -> heading angle of its glomerulus (8 per side tile 360 degrees)."""
    import re
    m = re.search(r"_([LR])(\d)$", instance)
    if not m or int(m.group(2)) > 8:
        return None
    return (int(m.group(2)) - 1) * math.pi / 4


class Senses:
    def __init__(self, brain, I0: float = 4.0, seed: int = 21, odors: dict | None = None):
        self.brain, self.I0 = brain, float(I0)
        rng = np.random.default_rng(seed)
        g = brain.group
        types = np.asarray(brain.cell_type, str)
        if odors is None:
            from .config import load_yaml
            cfg = load_yaml("alcohol.yaml")
            odors = {k: {**cfg.get("fermentado", {}), **v} for k, v in cfg.get("olores", {}).items()}
        self.odors = odors
        # ORNs of each glomerulus on each side (U: bilateral / unknown side, gets the mean)
        self.orn = {s: {} for s in ("L", "R", "U")}
        for s in ("L", "R", "U"):
            idx = cat(g(f"ORN|{s}"))
            for t in np.unique(types[idx]):
                self.orn[s][t[4:]] = idx[types[idx] == t]
        self.gust = cat(g("GRN_labellar|L"), g("GRN_labellar|R"), g("GRN_pharyngeal|L"),
                        g("GRN_pharyngeal|R"))
        self.sweet, self.bitter = self._taste_split()
        self.touch = {s: cat(g(f"antennal_mech|{s}")) for s in ("L", "R")}
        self.vib = cat(g("JO_AB|L"), g("JO_AB|R"), g("JO_AB|U"))
        self.arousal = np.where(brain.is_mono)[0]
        legp = cat(g("PROP_leg|L"), g("PROP_leg|R"), g("PROP_leg|U"))
        halt = cat(g("PROP_haltere|L"), g("PROP_haltere|R"), g("PROP_haltere|U"))
        self.prop = [_split(legp, 12, rng), _split(halt, 12, rng)]
        self.prop_centers = [np.linspace(-0.3, 1.0, 12), np.linspace(-1, 1, 12)]
        epg = cat(g("EPG|L"), g("EPG|R"))
        inst = np.asarray(getattr(brain, "instance", np.array([""] * brain.N)), str)
        ang = [(_epg_angle(inst[i]), i) for i in epg]
        self.epg = np.array([i for a, i in ang if a is not None], np.int64)
        self.epg_angle = np.array([a for a, i in ang if a is not None], np.float32)
        allorn = [a for s in self.orn.values() for a in s.values()]
        self.inputs = cat(*allorn, self.gust, self.touch["L"], self.touch["R"], self.vib, self.arousal,
                          *[a for p in self.prop for a in p], self.epg)

    # ------------------------------------------------------------------ taste split
    def _taste_split(self):
        br = self.brain
        types = np.asarray(br.cell_type, str)
        if SPLIT.exists():
            d = json.loads(SPLIT.read_text())
            if d.get("N") == br.N:
                sw = self.gust[np.isin(types[self.gust], d["sweet"])]
                bi = self.gust[np.isin(types[self.gust], d["bitter"])]
                return sw, bi
        mn9 = cat(br.group("MN9|L"), br.group("MN9|R"))
        u0 = np.zeros(br.N, np.float32)

        def mn9_rate(u):
            st = br.init_state(1)
            acc = []
            for k in range(60):
                h = br.step(st, u)
                if k >= 40:
                    acc.append(float(h[mn9, 0].mean()))
            return float(np.mean(acc))

        base = mn9_rate(u0)
        effect = {}
        for ty in sorted(set(types[self.gust])):
            u = u0.copy()
            u[self.gust[types[self.gust] == ty]] = self.I0
            effect[ty] = mn9_rate(u) - base
        order = sorted(effect, key=lambda t: -effect[t])
        sweet = [t for t in order if effect[t] > 0][: max(1, len(order) // 2)]
        bitter = [t for t in order if t not in sweet]
        SPLIT.write_text(json.dumps({"N": br.N, "sweet": sweet, "bitter": bitter,
                                     "efecto_sobre_MN9": effect,
                                     "nota": "clasificado por su efecto neto sobre MN9 en el propio "
                                             "conectoma (la anotación no trae modalidad)"},
                                    indent=1, ensure_ascii=False))
        return (self.gust[np.isin(types[self.gust], sweet)], self.gust[np.isin(types[self.gust], bitter)])

    # ------------------------------------------------------------------ encoding
    def encode(self, obs: dict) -> np.ndarray:
        """obs: c_l, c_r, odor_lr, sweet, bitter, touch_l, touch_r, vib, arousal, v, w, z, th,
        ground, olf_x, sweet_x, bitter_x."""
        u = np.zeros(self.brain.N, np.float32)
        I0 = self.I0
        gain = obs.get("olf_x", 1.0)
        lr = obs.get("odor_lr") or {}
        if lr:
            glom = {"L": {}, "R": {}}
            for kind, (cl, cr) in lr.items():
                prof = self.odors.get(kind, {})
                for side, c in (("L", cl), ("R", cr)):
                    val = log_c(c)
                    if val <= 0.01:
                        continue
                    for gl, wgt in prof.items():
                        glom[side][gl] = glom[side].get(gl, 0.0) + wgt * val
            for side in ("L", "R", "U"):
                for gl, idx in self.orn[side].items():
                    a = (glom["L"].get(gl, 0.0) + glom["R"].get(gl, 0.0)) / 2 if side == "U" \
                        else glom[side].get(gl, 0.0)
                    if a > 0:
                        u[idx] += I0 * gain * min(a, 1.5)
        sx, bx = obs.get("sweet_x", 1.0), obs.get("bitter_x", 1.0)
        if obs["sweet"] > 1e-3 and len(self.sweet):
            u[self.sweet] += I0 * sx * obs["sweet"]
        if obs["bitter"] > 1e-3 and len(self.bitter):
            u[self.bitter] += I0 * bx * obs["bitter"]
        for side, key in (("L", "touch_l"), ("R", "touch_r")):
            if obs[key] > 1e-3 and len(self.touch[side]):
                u[self.touch[side]] += I0 * obs[key]
        if obs["vib"] > 1e-3 and len(self.vib):
            u[self.vib] += I0 * obs["vib"]
        if obs.get("arousal", 0.0) > 0:
            u[self.arousal] += I0 * 0.5 * obs["arousal"]
        # leg proprioceptors (chordotonal organs sense leg movement, not only load) report always:
        # when they went silent in the air or on the back, the leg motor neurons lost their tone and
        # a sober fly that jumped never got up again
        vals = (obs["v"], obs["w"])
        for pools, centers, val in zip(self.prop, self.prop_centers, vals):
            act = _bell(val, centers, 0.2)
            for k, idx in enumerate(pools):
                if len(idx) and act[k] > 1e-3:
                    u[idx] += I0 * 0.5 * act[k]
        if len(self.epg) and "th" in obs:
            u[self.epg] += I0 * 0.5 * np.exp(2.5 * (np.cos(obs["th"] - self.epg_angle) - 1.0))
        return u
