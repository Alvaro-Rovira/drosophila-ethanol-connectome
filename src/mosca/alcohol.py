"""Ethanol: crop -> haemolymph -> elimination, and what it does to the neurons.

Nothing here touches the body. `neural()` returns multipliers per neurotransmitter class, synaptic
noise and a sensory delay; the brain applies them, and the behaviour changes because the motor
neurons change. The stages are only the name the interface gives to each level.
"""
from __future__ import annotations

from .config import Curve


class Alcohol:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.k_abs = float(cfg["k_abs"])
        self.k_elim = float(cfg["k_elim"])
        self.vapor_rate = float(cfg.get("vapor_rate", 0.0))
        hv = cfg["hangover"]
        self.h_high, self.h_low, self.h_dur = hv["high"], hv["low"], hv["duration_s"]
        pts = cfg["curve_points"]
        self.curves = {k: Curve(pts, v) for k, v in cfg["neural"].items()}
        self.stages = cfg["stages"]
        self.frozen_a = None
        self.reset()

    def reset(self):
        self.S = 0.0
        self.a = 0.0
        self.r = 0.0
        self.was_high = False
        self.peak = 0.0
        self.vapor_s = 0.0

    def freeze(self, a=None, r=None):
        self.frozen_a = a
        if r is not None:
            self.r = float(r)

    def drink(self, amount: float):
        if amount > 0:
            self.S += amount

    def update(self, dt: float):
        if self.frozen_a is None:
            flow = self.k_abs * self.S * dt
            self.S = max(0.0, self.S - flow)
            vap = self.vapor_rate * dt if self.vapor_s > 0 else 0.0
            self.vapor_s = max(0.0, self.vapor_s - dt)
            self.a = min(1.0, max(0.0, self.a + flow + vap - self.k_elim * dt))
        else:
            self.a = float(self.frozen_a)
        self.peak = max(self.peak, self.a)
        if self.a >= self.h_high:
            self.was_high = True
        if self.was_high and self.a < self.h_low:
            self.r, self.was_high = 1.0, False
        elif self.r > 0:
            self.r = max(0.0, self.r - dt / self.h_dur)

    def neural(self) -> dict:
        a = self.a
        c = self.curves
        return {"mono_x": float(c["monoamina_x"](a)), "exc_x": float(c["excitacion_x"](a)),
                "inh_x": float(c["inhibicion_x"](a)), "noise": float(c["ruido"](a)),
                "delay_ms": float(c["retardo_ms"](a)), "olf_x": float(c["olfato_x"](a))}

    def stage(self) -> str:
        if self.r > 0 and self.a < self.h_low:
            return "resaca"
        cur = "sobria"
        for s in self.stages:
            if s["min"] is not None and self.a >= s["min"]:
                cur = s["id"]
        return cur
