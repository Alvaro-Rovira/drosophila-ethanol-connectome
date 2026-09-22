"""The body reads the motor neurons and the identified descending neurons. No timers, no dice.

  postura   mean firing of the six legs' motor neurons, relative to the sober fly. Below 55% for
            0.3 s the legs cannot hold the body and it falls (to the side or on its back, by the
            left/right imbalance); it rights itself when the tone comes back. This is biomechanics:
            a threshold on a neural quantity, not a probability.
  velocidad the walking command is scaled by that same leg tone: legs move only as much as their
            motor neurons drive them.
  sorbo     the proboscis extends when MN9 fires above threshold (with hysteresis).
  escape    the giant fibre (DNp01) above threshold -> take-off.
  vuelo     stays airborne while the flight-power motor neurons (DLM/DVM) keep firing.
  acicalado DNg11/DNg12 above threshold while the fly is still.
  canto     pIP10 above threshold -> one wing extended.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
NORMS = ROOT / "artifacts" / "norms.json"
LEGS = [f"MN_leg_{s}|{d}" for s in ("T1", "T2", "T3") for d in ("L", "R")]
GROUPS = LEGS + ["MN_wing_power|L", "MN_wing_power|R", "MN_wing_steer|L", "MN_wing_steer|R",
                 "MN_neck|L", "MN_neck|R", "MN9|L", "MN9|R", "DNp09|L", "DNp09|R", "DNa01|L",
                 "DNa01|R", "DNa02|L", "DNa02|R", "DNg13|L", "DNg13|R", "MDN|L", "MDN|R", "DNp01|L",
                 "DNp01|R", "DNg11|L", "DNg11|R", "DNg12|L", "DNg12|R", "pIP10|L", "pIP10|R",
                 "DNp15|L", "DNp15|R", "MBON|L", "MBON|R"]


class Pools:
    """Mean rate of each identified group, and the same relative to the sober fly (1 = sober)."""

    def __init__(self, brain, norms: dict | None = None):
        self.idx = {g: brain.group(g).astype(np.int64) for g in GROUPS if len(brain.group(g))}
        self.norms = norms if norms is not None else (json.loads(NORMS.read_text()) if NORMS.exists() else {})

    def raw(self, h: np.ndarray, col: int = 0) -> dict:
        return {g: float(h[i, col].mean()) for g, i in self.idx.items()}

    FLOOR = 1e-3   # a group that is almost silent when sober (the giant fibre) must not turn noise
                   # into a huge relative rate

    def rel(self, raw: dict) -> dict:
        out = {}
        for g, v in raw.items():
            n = self.norms.get(g)
            out[g] = float(v / max(n["mean"], self.FLOOR)) if isinstance(n, dict) else 1.0
        return out

    def pair(self, rel: dict, g: str) -> tuple[float, float]:
        return rel.get(f"{g}|L", 0.0), rel.get(f"{g}|R", 0.0)


@dataclass
class MotorCfg:
    fall: float = 0.55          # leg tone (relative to sober) below which the legs give way
    right: float = 0.50         # ...and above which the fly can right itself
    hyst: float = 0.05
    fall_s: float = 0.3
    right_every_s: float = 1.0
    lorr_s: float = 3.0         # fallen and unable to right itself for this long = sedated (LORR)
    sip_on: float = 2.0         # MN9 relative rate to extend the proboscis
    sip_off: float = 1.3
    gf: float = 3.0             # giant fibre relative rate for take-off
    fly_keep: float = 1.3       # flight-power motor neurons needed to stay in the air
    groom: float = 3.0
    song: float = 3.0
    tone_min: float = 0.0       # speed scaling by leg tone is clipped to [tone_min, tone_max]
    tone_max: float = 1.5

    @classmethod
    def load(cls, path: Path | None = None):
        p = path or (ROOT / "artifacts" / "motor.json")
        if p.exists():
            d = json.loads(p.read_text())
            return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        return cls()


class Body:
    """Turns neural rates into posture, proboscis, take-off, grooming and song."""

    def __init__(self, cfg: MotorCfg | None = None):
        self.c = cfg or MotorCfg.load()
        self.reset()

    def reset(self):
        self.pose = "up"
        self.low_t = 0.0
        self.try_t = 0.0
        self.down_t = 0.0
        self.sip_on = False
        self.escape_t = 0.0
        self.flying = False

    def help_up(self):
        """The experimenter turns the fly over. Only the posture changes: if its leg motor neurons have
        no tone it falls again, as a real sedated fly would."""
        self.pose = "up"
        self.low_t = self.down_t = self.try_t = 0.0

    def tone(self, rel: dict) -> tuple[float, float, float]:
        legs = [rel.get(g, 1.0) for g in LEGS]
        L = float(np.mean(legs[0::2]))
        R = float(np.mean(legs[1::2]))
        return float(np.mean(legs)), (R - L) / max(R + L, 1e-6), float(min(legs))

    def update(self, rel: dict, dt: float, still: bool, airborne: bool = False) -> dict:
        c = self.c
        P, asym, weakest = self.tone(rel)
        ev = []
        if self.pose == "up":
            # in the air the legs carry no weight: they cannot give way (falls happen on the ground)
            self.low_t = self.low_t + dt if (P < c.fall and not airborne) else 0.0
            if self.low_t >= c.fall_s:
                self.pose = "side" if abs(asym) > 0.12 else "back"
                self.down_t = self.try_t = 0.0
                self.flying = False
                ev.append("fall")
        else:
            self.down_t += dt
            self.try_t += dt
            if self.try_t >= c.right_every_s:
                self.try_t = 0.0
                if P >= c.right + c.hyst and weakest >= 0.3:
                    self.pose = "up"
                    self.low_t = 0.0
                    ev.append("wake")
        up = self.pose == "up"
        mn9 = float(np.mean(self.pair(rel, "MN9")))
        self.sip_on = up and (mn9 > c.sip_on if not self.sip_on else mn9 > c.sip_off)
        gf = max(self.pair(rel, "DNp01"))
        if up and gf > c.gf and self.escape_t <= 0:
            self.escape_t = 0.5
            self.flying = True
            ev.append("escape")
        self.escape_t = max(0.0, self.escape_t - dt)
        power = float(np.mean(self.pair(rel, "MN_wing_power")))
        if self.flying and self.escape_t <= 0 and power < c.fly_keep:
            self.flying = False
        groom = up and still and max(*self.pair(rel, "DNg11"), *self.pair(rel, "DNg12")) > c.groom
        song = up and still and max(self.pair(rel, "pIP10")) > c.song
        # sedation is the loss of the righting reflex, as it is scored in flies: down and every
        # righting attempt failing (the legs do not recover their tone)
        sedated = (not up) and self.down_t >= c.lorr_s
        return {"pose": self.pose, "P": P, "asym": asym, "pe": 1.0 if self.sip_on else 0.0,
                "lift": 1.0 if (up and self.flying) else 0.0, "groom": groom, "song": song,
                "sedated": sedated, "speed_x": float(np.clip(P, c.tone_min, c.tone_max)) if up else 0.0,
                "events": ev}

    @staticmethod
    def pair(rel, g):
        return rel.get(f"{g}|L", 0.0), rel.get(f"{g}|R", 0.0)
