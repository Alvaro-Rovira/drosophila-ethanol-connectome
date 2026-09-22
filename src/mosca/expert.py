"""Sensory-only teacher for the steering readout (training only, never at the controls in the show).

It sees exactly what the fly senses - the odour at each antenna, the taste at the mouth, the touch
on the antennae - and nothing about where the puddles are. The readout it trains therefore has to
find that same information inside the neurons.
"""
from __future__ import annotations

import math

import numpy as np

from .senses import log_c

TAU_DIFF, G_DIFF, TAU_C = 0.30, 90.0, 0.45
CAST_PERIOD, CAST_AMPL, LOST_S, BACK_S = 1.1, 0.75, 0.6, 0.8


class Expert:
    def __init__(self):
        self.reset()

    def reset(self):
        self.t = self.lost_t = self.diff_f = self.c_slow = self.back_t = self.back_w = 0.0

    def __call__(self, obs: dict, dt: float) -> tuple[float, float]:
        """Returns (w, v) in [-1, 1] x [-0.3, 1]."""
        self.t += dt
        ul, ur = log_c(obs["c_l"]), log_c(obs["c_r"])
        c = 0.5 * (ul + ur)
        tl, tr = obs["touch_l"], obs["touch_r"]
        if max(tl, tr) > 0.3 and self.back_t <= 0:          # bumped: back up for a few steps
            self.back_t = BACK_S
            self.back_w = float(np.clip(1.2 * (tl - tr) + 0.6 * math.copysign(1.0, tl - tr + 1e-9), -1, 1))
        if self.back_t > 0:
            self.back_t -= dt
            return self.back_w, -0.3
        if obs["contact"] and obs["sweet"] - 0.8 * obs["bitter"] > 0.15:
            return 0.0, 0.0                                   # something good under the feet: stay
        self.diff_f += (1 - math.exp(-dt / TAU_DIFF)) * ((ur - ul) - self.diff_f)
        improving = c > self.c_slow
        self.c_slow += (1 - math.exp(-dt / TAU_C)) * (c - self.c_slow)
        cast = CAST_AMPL * math.sin(2 * math.pi * self.t / CAST_PERIOD)
        if c > 0.02:
            self.lost_t = 0.0
            w = G_DIFF * self.diff_f + (0.0 if improving else cast)
            v = 0.95 - 2.0 * max(0.0, c - 0.55)                # slow down as the smell gets strong
            v = max(v, 0.30)
        else:
            self.lost_t += dt
            w = cast if self.lost_t > LOST_S else 0.0
            v = 0.55
        return float(np.clip(w, -1, 1)), float(np.clip(v, -0.3, 1.0))
