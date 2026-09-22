"""What the fly senses, injected into its real receptor neurons.

  olfato   odour at each antenna -> left / right olfactory receptor neurons (ORN)
  gusto    sweet / bitter at the mouthparts -> labellar and pharyngeal gustatory neurons
  tacto    antennal touch (walls) -> left / right antennal mechanosensory neurons
  vibración a knock on the table -> Johnston organ (JO-A/B)
  arousal  a constant tonic drive to the monoaminergic neurons, so the fly is awake (ARBITRARIO)
  propiocepción  own speed, turn and height -> other sensory neurons with a fixed seed (ARBITRARIO:
           there are no identified proprioceptors for this in the subcircuit)

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
N_ODOR = 24


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


class Senses:
    def __init__(self, brain, I0: float = 4.0, seed: int = 21):
        self.brain, self.I0 = brain, float(I0)
        rng = np.random.default_rng(seed)
        g = brain.group
        self.odor = {s: _split(cat(g(f"ORN|{s}")), N_ODOR, rng) for s in ("L", "R")}
        self.odor_centers = np.linspace(0.05, 1.0, N_ODOR)
        self.gust = cat(g("GRN_labellar|L"), g("GRN_labellar|R"), g("GRN_pharyngeal|L"),
                        g("GRN_pharyngeal|R"))
        self.sweet, self.bitter = self._taste_split()
        self.touch = {s: cat(g(f"antennal_mech|{s}")) for s in ("L", "R")}
        self.vib = cat(g("JO_AB|L"), g("JO_AB|R"), g("JO_AB|U"))
        self.arousal = np.where(brain.is_mono)[0]
        used = np.zeros(brain.N, bool)
        for arr in (*self.odor["L"], *self.odor["R"], self.gust, self.touch["L"], self.touch["R"],
                    self.vib, self.arousal):
            used[arr] = True
        free = rng.permutation(np.where((brain.klass == "sensory") & ~used)[0])[:3 * 12 * 6]
        parts = np.array_split(free, 3)
        self.prop = [_split(p, 12, rng) for p in parts]
        self.prop_centers = [np.linspace(-0.3, 1.0, 12), np.linspace(-1, 1, 12), np.linspace(0, 1, 12)]
        self.inputs = cat(*self.odor["L"], *self.odor["R"], self.gust, self.touch["L"], self.touch["R"],
                          self.vib, self.arousal, *[a for p in self.prop for a in p])

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
        """obs: c_l, c_r, sweet, bitter, touch_l, touch_r, vib, arousal, v, w, z, olf_x."""
        u = np.zeros(self.brain.N, np.float32)
        I0 = self.I0
        gain = obs.get("olf_x", 1.0)
        for side, c in (("L", obs["c_l"]), ("R", obs["c_r"])):
            val = log_c(c)
            if val <= 0.01:
                continue
            # tuning curves AND a monotonic gain: a real ORN fires faster with more odorant, and
            # without that the 1% left-right difference falls inside one channel and vanishes
            act = _bell(val, self.odor_centers, 0.35) * val
            for k, idx in enumerate(self.odor[side]):
                if len(idx):
                    u[idx] += I0 * gain * act[k]
        if obs["sweet"] > 1e-3 and len(self.sweet):
            u[self.sweet] += I0 * obs["sweet"]
        if obs["bitter"] > 1e-3 and len(self.bitter):
            u[self.bitter] += I0 * obs["bitter"]
        for side, key in (("L", "touch_l"), ("R", "touch_r")):
            if obs[key] > 1e-3 and len(self.touch[side]):
                u[self.touch[side]] += I0 * obs[key]
        if obs["vib"] > 1e-3 and len(self.vib):
            u[self.vib] += I0 * obs["vib"]
        if obs.get("arousal", 0.0) > 0:
            u[self.arousal] += I0 * 0.5 * obs["arousal"]
        for pools, centers, val in zip(self.prop, self.prop_centers, (obs["v"], obs["w"], obs["z"])):
            act = _bell(val, centers, 0.2)
            for k, idx in enumerate(pools):
                if len(idx) and act[k] > 1e-3:
                    u[idx] += I0 * 0.5 * act[k]
        return u
