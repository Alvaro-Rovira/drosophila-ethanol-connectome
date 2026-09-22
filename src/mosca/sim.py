"""One fly: senses -> real neurons of MaleCNS -> motor neurons -> body -> world. No script anywhere.

Order of a body tick (30 Hz; the brain runs at 15 Hz and its commands are interpolated):
  1. ethanol kinetics
  2. brain tick when due: senses (with the ethanol sensory delay) -> neurons (with ethanol acting
     on synapses by class) -> identified-neuron rates -> body (posture, proboscis, take-off...)
     and the steering readout
  3. walking command scaled by the leg motor-neuron tone
  4. world physics, then the sip (only if MN9 extended the proboscis)

`teacher` (training only) lets the sensory expert drive a fraction of the ticks (DAgger).
"""
from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path

import numpy as np

from .alcohol import Alcohol
from .body import Body, MotorCfg, Pools
from .brain import Brain, BrainParams
from .config import ARTIFACTS, load_yaml
from .expert import Expert
from .gut import Gut
from .readout import Readout, feature_index
from .senses import Senses
from .world import DT, FLY_Z, World

BRAIN_FILE = ARTIFACTS / "brain.npz"
READOUT_FILE = ARTIFACTS / "readout.npz"
REGIME = {"G": 1.25, "b": 0.003, "I0": 4.0, "arousal": 1.0, "f_brain": 15.0}


def load_regime() -> dict:
    p = ARTIFACTS / "regime.json"
    return {**REGIME, **(json.loads(p.read_text()) if p.exists() else {})}


def load_brain(path=None, reg=None) -> Brain:
    reg = reg or load_regime()
    return Brain(path or BRAIN_FILE, BrainParams(G=reg["G"], b=reg["b"], f_brain=reg["f_brain"]))


class Sim:
    def __init__(self, brain: Brain, seed: int = 0, alc_cfg: dict | None = None,
                 readout: Readout | None = None, norms: dict | None = None, reg: dict | None = None,
                 motor: MotorCfg | None = None, senses: Senses | None = None):
        self.reg = reg or load_regime()
        self.brain = brain
        self.alc_cfg = alc_cfg or load_yaml("alcohol.yaml")
        self.drinks = {d["id"]: d for d in self.alc_cfg["drinks"]}
        self.rng = np.random.default_rng(seed)
        self.brain_rng = np.random.default_rng(seed * 7919 + 13)
        self.world = World(self.rng)
        self.world.place_fly()
        self.alcohol = Alcohol(self.alc_cfg)
        self.gut = Gut(self.alc_cfg)
        self.senses = senses or Senses(brain, self.reg["I0"])
        self.pools = Pools(brain, norms)
        self.body = Body(motor)
        if readout is None and READOUT_FILE.exists():
            readout = Readout.load(READOUT_FILE)
        self.readout = readout
        self.expert = Expert()
        self.teacher = 0.0                 # probability that the expert drives a brain tick
        self.state = brain.init_state(1)
        self.delay: deque = deque(maxlen=12)
        self.period = 1.0 / brain.p.f_brain
        self.acc = 0.0
        self.cmd = (0.0, 0.0)
        self.prev_cmd = (0.0, 0.0)
        self.interp = 1.0
        self.bs = {"pose": "up", "P": 1.0, "asym": 0.0, "pe": 0.0, "lift": 0.0, "groom": False,
                   "song": False, "sedated": False, "speed_x": 1.0, "events": []}
        self.raw, self.rel = {}, {}
        self.obs: dict = {}
        self.label = (0.0, 0.0)
        self.fx: list[str] = []
        self.t = 0.0
        self.n = 0
        self.drunk = 0.0

    # ------------------------------------------------------------------ helpers
    def order(self, kind: str, dmin=100.0, dmax=300.0):
        d = self.drinks.get(kind)
        return None if d is None else self.world.spawn_puddle(kind, d, dmin, dmax)

    def tap(self, s=1.0):
        self.world.tap(s)

    def observe(self, olf_x=1.0) -> dict:
        f = self.world.fly
        cl, cr = self.world.antennae()
        sweet, bitter, pud = self.world.taste()
        vmax = 110.0 + 130.0 * f.z
        sx, bx = self.gut.gains()
        return {"c_l": cl, "c_r": cr, "odor_lr": dict(self.world.odor_lr), "sweet": sweet, "bitter": bitter,
                "contact": pud is not None, "sweet_x": sx, "bitter_x": bx, "hunger": self.gut.hunger,
                "th": f.th, "ground": f.z <= FLY_Z and f.pose == "up",
                "touch_l": f.touch_l, "touch_r": f.touch_r, "vib": f.vib, "arousal": self.reg["arousal"],
                "v": float(np.clip(f.v / vmax, -0.3, 1)), "w": float(np.clip(f.w / 5.0, -1, 1)),
                "z": f.z, "olf_x": olf_x}

    # ------------------------------------------------------------------ brain tick
    def brain_tick(self):
        eff = self.alcohol.neural()
        self.obs = self.observe(eff["olf_x"])
        u = self.senses.encode(self.obs)
        self.delay.append(u)
        d = min(int(round(eff["delay_ms"] / 1000.0 / self.period)), len(self.delay) - 1)
        m = None
        if eff["mono_x"] != 1.0 or eff["exc_x"] != 1.0 or eff["inh_x"] != 1.0:
            m = self.brain.class_multiplier(eff["exc_x"], eff["inh_x"], eff["mono_x"])
        h = self.brain.step(self.state, self.delay[-1 - d], m, eff["noise"], self.brain_rng)
        self.raw = self.pools.raw(h)
        self.rel = self.pools.rel(self.raw)
        f = self.world.fly
        self.bs = self.body.update(self.rel, self.period, still=abs(f.v) < 8.0, airborne=f.z > FLY_Z)
        self.label = self.expert(self.obs, self.period)
        self.prev_cmd = self.cmd
        if self.readout is not None and (self.teacher <= 0 or self.rng.random() >= self.teacher):
            self.cmd = self.readout(h[:, 0], self.period)
        else:
            if self.readout is not None:
                self.readout(h[:, 0], self.period)       # keep its filter state in step
            self.cmd = self.label
        self.interp = 0.0

    # ------------------------------------------------------------------ body tick
    def step(self, dt: float = DT):
        self.fx = []
        self.alcohol.update(dt)
        self.gut.update(dt)
        self.acc += dt
        if self.acc >= self.period:
            self.acc -= self.period
            self.brain_tick()
            self.fx += self.bs["events"]
        self.interp = min(1.0, self.interp + dt / self.period)
        k = self.interp
        w = self.prev_cmd[0] + (self.cmd[0] - self.prev_cmd[0]) * k
        v = self.prev_cmd[1] + (self.cmd[1] - self.prev_cmd[1]) * k
        bs = self.bs
        f = self.world.fly
        f.pose = bs["pose"]
        if bs["pe"] > 0.5 and self.world.contact_puddle() is not None:
            v = 0.0                                   # the proboscis is on the drop: the fly stays
        v *= bs["speed_x"]
        w *= min(1.0, bs["speed_x"] + 0.2) if f.pose == "up" else 0.0
        self.world.step(w, v, bs["lift"], dt)
        got = self.world.sip(bs["pe"], dt)
        if got > 0:
            self.alcohol.drink(got)
            self.drunk += got
        if self.world.last_take[0] > 0:
            self.gut.drink(*self.world.last_take)
        self.t += dt
        self.n += 1

    # ------------------------------------------------------------------ views
    def act(self) -> str:
        f, bs = self.world.fly, self.bs
        if f.pose != "up":
            return "asleep" if bs["sedated"] else "fall"
        if f.sipping:
            return "sip"
        if f.z > FLY_Z:
            return "fly"
        if bs["song"]:
            return "sing"
        if bs["groom"]:
            return "groom"
        if f.v < -5:
            return "moonwalk"
        return "walk"

    def features(self, feat) -> np.ndarray:
        return self.state["h"][feat, 0].copy()


def make_sim(seed=0, brain=None, **kw) -> Sim:
    return Sim(brain or load_brain(), seed=seed, **kw)
