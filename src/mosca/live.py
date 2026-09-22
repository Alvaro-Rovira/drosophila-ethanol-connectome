"""Live show: one continuous fly driven by its real neurons, drink orders, demo and compact frames.

Shared by the web server (asyncio loop at 30 Hz) and the headless scripts. Nothing here decides
what the fly does: orders only put puddles on the table.
"""
from __future__ import annotations

import base64
import json
import os
import time
from collections import defaultdict, deque

import numpy as np

from .body import MotorCfg
from .config import ARTIFACTS, load_yaml
from .readout import Readout
from .sim import READOUT_FILE, Sim, load_brain
from .world import DT, TABLE_H, TABLE_W

N_GROUPS = 12
# identified neurons recorded live: (key, label, how the L/R pair is combined)
CHANNELS = [
    ("MN9", "Beber · MN9", "mean"),
    ("DNp01", "Escapar · fibra gigante", "max"),
    ("MDN", "Marcha atrás · MDN", "mean"),
    ("DNp09", "Avanzar · DNp09", "mean"),
    ("DNa02|L", "Girar izq. · DNa02", "one"),
    ("DNa02|R", "Girar der. · DNa02", "one"),
    ("MN_leg_T1", "Patas delanteras", "mean"),
    ("MN_leg_T2", "Patas centrales", "mean"),
    ("MN_leg_T3", "Patas traseras", "mean"),
    ("MN_wing_power", "Alas (potencia)", "mean"),
    ("DNg12", "Acicalarse · DNg12", "max"),
    ("MBON", "Memoria · MBON", "mean"),
]
N_SCATTER = 1500
SCATTER_EVERY = 4


def load_model(artifacts=ARTIFACTS):
    brain = load_brain()
    norms = json.loads((artifacts / "norms.json").read_text())
    return brain, norms, READOUT_FILE, MotorCfg.load()


class Live:
    def __init__(self, seed: int | None = None, model=None, clock=time.monotonic):
        self.alc_cfg = load_yaml("alcohol.yaml")
        self.ui = load_yaml("ui.yaml")
        self.demo_cfg = load_yaml("demo.yaml")
        self.drinks = {d["id"]: d for d in self.alc_cfg["drinks"]}
        self.model = model or load_model()
        self.clock = clock
        self.seed = int(seed if seed is not None else int.from_bytes(os.urandom(4), "little"))
        self._build_sim(self.seed)
        self._build_groups()
        self.demo_queue: deque = deque()
        self.demo_t = 0.0
        self.debug_puddles = False
        self.debug_timer = 0.0
        self.order_times: dict[str, deque] = defaultdict(deque)
        self.pending_fx: list[str] = []
        self.toasts: list[str] = []

    # ------------------------------------------------------------------ setup
    def _build_sim(self, seed: int):
        brain, norms, ro_path, motor = self.model
        # the live subject learns: its KC -> MBON synapses are plastic (a new subject starts naive)
        if getattr(brain, "pl", None) is None:
            brain.enable_plasticity()
        else:
            brain.reset_learning()
        self.sim = Sim(brain, seed=seed, alc_cfg=self.alc_cfg, readout=Readout.load(ro_path),
                       norms=norms, motor=motor)
        self.agent = self.sim
        for _ in range(20):
            self.sim.step()
        self.t = 0.0

    def _build_groups(self):
        br = self.sim.brain
        sc = br.superclass.astype(str)
        names, counts = np.unique(sc, return_counts=True)
        top = [str(n) for n in names[np.argsort(-counts)][: N_GROUPS - 1]]
        gid = np.full(br.N, N_GROUPS - 1, np.int64)
        for k, n in enumerate(top):
            gid[sc == n] = k
        self.group_labels = top + ["otras"]
        self.cell = gid * 2 + br.inhib.astype(np.int64)
        self.cell_count = np.maximum(np.bincount(self.cell, minlength=2 * N_GROUPS), 1)
        self.cell_affected = [bool(i % 2 == 1 or self.group_labels[i // 2] in ("descending_neuron", "vnc_motor"))
                              for i in range(2 * N_GROUPS)]
        xyz = br.soma_xyz
        ok = np.where(np.isfinite(xyz[:, 0]))[0]
        pick = np.sort(np.random.default_rng(3).choice(ok, size=min(N_SCATTER, len(ok)), replace=False)) \
            if len(ok) else ok
        self.sc_idx = pick
        if len(pick):
            p = xyz[pick][:, [0, 2]].astype(np.float64)
            lo, hi = p.min(0), p.max(0)
            span = np.maximum(hi - lo, 1e-6)
            self.sc_xy = np.clip(np.round((p - lo) / span * 255), 0, 255).astype(np.uint8)
            self.sc_aspect = float(span[0] / span[1])
            self.sc_kind = [0 if s in ("descending_neuron", "vnc_motor", "cb_motor") else (1 if i else 2)
                            for s, i in zip(sc[pick], br.inhib[pick])]
        else:
            self.sc_xy, self.sc_aspect, self.sc_kind = np.zeros((0, 2), np.uint8), 1.0, []

    # ------------------------------------------------------------------ actions
    def order(self, kind: str, who: str) -> tuple[bool, str]:
        if kind not in self.drinks:
            return False, ""
        now = self.clock()
        q = self.order_times[who]
        while q and now - q[0] > 60:
            q.popleft()
        if q and now - q[-1] < float(self.ui["order_min_interval_s"]):
            return False, self.ui["toasts"]["too_fast"]
        if len(q) >= int(self.ui["order_max_per_min"]):
            return False, self.ui["toasts"]["too_fast"]
        if not self._spawn(kind):
            return False, self.ui["toasts"]["bar_full"]
        q.append(now)
        d = self.drinks[kind]
        return True, self.ui["toasts"]["ordered"].format(
            who=who, article=self.ui["articles"].get(kind, "un"),
            drink=f"{d['name'].lower()} ({round(d['abv'] * 100)}% EtOH)")

    def _spawn(self, kind: str, demo: bool = False) -> bool:
        lo, hi = (self.demo_cfg.get("puddle_distance", self.ui["puddle_distance"]) if demo
                  else self.ui["puddle_distance"])
        return self.sim.order(kind, lo, hi) is not None

    def tap(self):
        self.sim.tap(1.0)
        self.pending_fx.append("tap")

    def reset(self):
        """'Ducha fría': ethanol to zero. The neurons recover by themselves; the posture follows."""
        self.sim.alcohol.reset()
        self.pending_fx.append("shower")

    def vapor(self, secs: float = 20.0):
        """Ethanol vapour exposure: ethanol enters the haemolymph without drinking."""
        self.sim.alcohol.vapor_s = min(60.0, self.sim.alcohol.vapor_s + float(secs))
        self.pending_fx.append("vapor")

    def start_demo(self):
        self.demo_queue = deque(sorted(((float(o["t"]), o.get("kind") or f"vapor:{o['vapor']}")
                                        for o in self.demo_cfg["orders"])))
        self.demo_t = 0.0

    def stop_demo(self):
        self.demo_queue.clear()

    def set_debug(self, a=None, r=None, seed=None, puddles=False):
        if seed is not None:
            self._build_sim(int(seed))
        self.sim.alcohol.freeze(a, r)
        self.debug_puddles = bool(puddles)
        self.debug_timer = 0.0

    # ------------------------------------------------------------------ tick
    def step(self):
        if self.demo_queue and self.sim.act() == "asleep":
            self.demo_queue.clear()
            self.toasts.append(self.ui["toasts"]["demo_ko"])
        if self.demo_queue:
            self.demo_t += DT
            while self.demo_queue and self.demo_queue[0][0] <= self.demo_t:
                _, kind = self.demo_queue.popleft()
                if kind.startswith("vapor:"):
                    secs = float(kind.split(":")[1])
                    self.vapor(secs)
                    self.toasts.append(f"Protocolo: vapor de etanol ({secs:.0f} s)")
                elif self._spawn(kind, demo=True):
                    d = self.drinks[kind]
                    self.toasts.append(f"Protocolo: {d['name'].lower()} ({round(d['abv'] * 100)} % alcohol)")
                else:
                    self.demo_queue.appendleft((self.demo_t + 3.0, kind))
                    break
            if not self.demo_queue:
                self.toasts.append(self.ui["toasts"]["demo_off"])
        if self.debug_puddles:
            self.debug_timer -= DT
            if self.debug_timer <= 0:
                self.debug_timer = 12.0
                kinds = list(self.drinks)
                self._spawn(kinds[int(self.sim.rng.integers(len(kinds)))])
        self.sim.step()
        self.t += DT

    # ------------------------------------------------------------------ messages
    def hello(self, me: str) -> dict:
        return {
            "t": "hello", "arena": [TABLE_W, TABLE_H],
            "drinks": [{k: d[k] for k in ("id", "name", "emoji", "color", "dose")} for d in self.alc_cfg["drinks"]],
            "stages": [{k: s[k] for k in ("id", "name", "color", "min")} for s in self.alc_cfg["stages"]],
            "texts": self.ui["narration"], "me": me,
            "groups": self.group_labels, "affected": self.cell_affected,
            "scatter": {"n": int(len(self.sc_idx)), "aspect": self.sc_aspect,
                        "xy": base64.b64encode(self.sc_xy.tobytes()).decode(),
                        "kind": base64.b64encode(bytes(self.sc_kind)).decode()},
            "hmax": self.sim.brain.p.h_max,
            "demo_len": max([o["t"] + o.get("vapor", 0) for o in self.demo_cfg["orders"]] or [0]),
            "substances": [{k: d[k] for k in ("id", "name", "color", "dose", "abv", "sugar", "impurity")}
                           for d in self.alc_cfg["drinks"]],
            "channels": [{"key": k, "label": lab} for k, lab, _ in CHANNELS],
            "thresholds": {"MN9": self.sim.body.c.sip_on, "DNp01": self.sim.body.c.gf,
                           "tone_fall": self.sim.body.c.fall, "tone_right": self.sim.body.c.right},
            "model": {"N": int(self.sim.brain.N), "edges": int(self.sim.brain.nnz),
                      "f_brain": float(self.sim.brain.p.f_brain), "seed": self.seed,
                      "motor": int((self.sim.brain.klass == "motor").sum()),
                      "descending": int((self.sim.brain.klass == "descending").sum()),
                      "sensory": int((self.sim.brain.klass == "sensory").sum())},
        }

    def frame(self, viewers: int) -> dict:
        s = self.sim
        f = s.world.fly
        alc = s.alcohol
        h = s.state["h"][:, 0]
        hm = s.brain.p.h_max
        cell_mean = np.bincount(self.cell, weights=h, minlength=2 * N_GROUPS) / self.cell_count
        fx = list(s.fx) + self.pending_fx
        self.pending_fx = []
        act = s.act()
        pose = "asleep" if act == "asleep" else ("back" if f.pose != "up" else "up")
        rel = s.rel or {}
        c = s.body.c
        # the proboscis and the wing are drawn from their motor/descending neurons, graded
        mn9 = float(np.mean(s.body.pair(rel, "MN9"))) if rel else 0.0
        prob = 1.0 if f.sipping else float(np.clip(mn9 / max(c.sip_on, 1e-6), 0, 1)) * 0.6
        wing = float(np.clip(max(s.body.pair(rel, "pIP10")) / max(c.song, 1e-6), 0, 1)) if rel else 0.0
        fr = {
            "t": "frame", "n": s.n, "a": round(alc.a, 4), "stage": alc.stage(), "r": round(alc.r, 3),
            "f": {"x": round(f.x, 1), "y": round(f.y, 1), "th": round(f.th, 3), "z": round(f.z, 3),
                  "v": round(f.v, 1), "w": round(f.w, 2), "pose": pose,
                  "act": "walk" if act in ("fall", "asleep") else act,
                  "prob": round(prob, 2), "wing": round(wing, 2)},
            "puddles": [{"id": p.id, "x": round(p.x, 1), "y": round(p.y, 1), "kind": p.kind,
                         "amt": round(p.amount, 3)} for p in s.world.puddles],
            "fx": fx,
            "map": [int(v) for v in np.clip(cell_mean / hm * 255, 0, 255)],
            "viewers": viewers,
            "demo": bool(self.demo_queue),
            "tone": round(float(s.bs["P"]), 3),
            "ch": self._channels(rel),
            "eth": self._effects(),
            "lorr": bool(act == "asleep"), "down": bool(f.pose != "up"), "sip": bool(f.sipping),
            "tt": round(self.t, 2),
            "vapor": round(alc.vapor_s, 1),
            "hunger": round(s.gut.hunger, 3), "crop": round(s.gut.crop, 3),
            "mb": self._memory(),
        }
        if len(self.sc_idx) and s.n % SCATTER_EVERY == 0:
            v = np.clip(np.sqrt(np.clip(h[self.sc_idx], 0, hm) / hm) * 255, 0, 255).astype(np.uint8)
            fr["sc"] = base64.b64encode(v.tobytes()).decode()
        return fr

    def _channels(self, rel: dict) -> list[float]:
        out = []
        for key, _, how in CHANNELS:
            if how == "one":
                v = rel.get(key, 0.0)
            else:
                pair = (rel.get(f"{key}|L", 0.0), rel.get(f"{key}|R", 0.0))
                v = max(pair) if how == "max" else 0.5 * (pair[0] + pair[1])
            out.append(round(float(v), 3))
        return out

    def _memory(self) -> float:
        """Mean depression of the KC -> MBON synapses (0 = naive)."""
        pl = getattr(self.sim.brain, "pl", None)
        return round(float(1.0 - pl["f"].mean()), 4) if pl is not None else 0.0

    def _effects(self) -> dict:
        """What ethanol is doing to the synapses right now (multipliers by neurotransmitter class)."""
        e = self.sim.alcohol.neural()
        return {"mono": round(e["mono_x"], 3), "exc": round(e["exc_x"], 3), "inh": round(e["inh_x"], 3),
                "noise": round(e["noise"], 3), "delay": round(e["delay_ms"]), "olf": round(e["olf_x"], 3)}

    def take_toasts(self) -> list[str]:
        t, self.toasts = self.toasts, []
        return t
