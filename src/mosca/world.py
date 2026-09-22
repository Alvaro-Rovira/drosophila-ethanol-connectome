"""The table: physics, smell, taste and touch. Nothing here decides anything for the fly.

No rule of the world starts a sip, turns the fly at a wall or makes it walk: the world only moves
the body with the commands it gets, blocks it at the edges, and produces what the antennae smell,
what the mouthparts taste and what the antennae feel.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

DT = 1.0 / 30.0
TABLE_W, TABLE_H = 2160.0, 1620.0      # 216 x 162 mm (1 u = 0,1 mm); was 720 x 540: too small
MARGIN = 30.0
MAX_PUDDLES = 3
RAY_ANGLES = (-math.radians(40), 0.0, math.radians(40))
RAY_MAX = 200.0
W_MAX_WALK, W_MAX_FLY = 5.0, 3.5
V_MAX_WALK, V_MAX_FLY = 110.0, 240.0
TAU_V_WALK, TAU_V_FLY = 0.15, 0.4
TAU_W = 0.08
Z_RATE = 1.2
FLY_Z = 0.1
CONTACT_DIST = 14.0
SIP_RATE = 0.4               # a puddle empties in 2.5 s of sipping
EVAPORATE_S = 120.0          # FICCIÓN: a drop lasts 2 min untouched (40 s was too short for the ×3 arena)
ANTENNA_OFFSET = 10.0
ODOR_LAMBDA = 250.0


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


@dataclass
class Puddle:
    id: int
    x: float
    y: float
    kind: str
    dose: float           # ethanol delivered by the whole puddle (units of a)
    abv: float
    sugar: float
    impurity: float
    amount: float = 1.0
    idle: float = 0.0


@dataclass
class Fly:
    x: float = TABLE_W / 2
    y: float = TABLE_H / 2
    th: float = 0.0
    z: float = 0.0
    v: float = 0.0
    w: float = 0.0
    pose: str = "up"             # up | side | back   (set by the body, from leg motor tone)
    sipping: bool = False
    touch_l: float = 0.0
    touch_r: float = 0.0
    vib: float = 0.0
    bumped: bool = False


class World:
    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.fly = Fly()
        self.puddles: list[Puddle] = []
        self._next_id = 1
        self.t = 0.0
        self.odor_lr: dict = {}
        self.last_take = (0.0, 0.0)

    def place_fly(self, x=None, y=None, th=None):
        r, f = self.rng, self.fly
        f.x = float(r.uniform(80, TABLE_W - 80)) if x is None else float(x)
        f.y = float(r.uniform(80, TABLE_H - 80)) if y is None else float(y)
        f.th = float(r.uniform(-math.pi, math.pi)) if th is None else float(th)
        f.z = f.v = f.w = 0.0
        f.pose = "up"
        f.sipping = False

    def spawn_puddle(self, kind: str, drink: dict, dmin=100.0, dmax=300.0, tries=200):
        if len(self.puddles) >= MAX_PUDDLES:
            return None
        f, r = self.fly, self.rng
        for k in range(tries):
            lo = dmin if k < tries // 2 else dmin * 0.5
            hi = dmax if k < tries // 2 else dmax * 1.5
            d, a = r.uniform(lo, hi), r.uniform(-math.pi, math.pi)
            x, y = f.x + d * math.cos(a), f.y + d * math.sin(a)
            if not (50 <= x <= TABLE_W - 50 and 50 <= y <= TABLE_H - 50):
                continue
            if any(math.hypot(p.x - x, p.y - y) < 60 for p in self.puddles):
                continue
            p = Puddle(self._next_id, x, y, kind, float(drink["dose"]), float(drink["abv"]),
                       float(drink["sugar"]), float(drink.get("impurity", 0.0)))
            self._next_id += 1
            self.puddles.append(p)
            return p
        return None

    # ---------------------------------------------------------------- senses
    def odor_at(self, x, y) -> float:
        return sum(p.amount * math.exp(-math.hypot(p.x - x, p.y - y) / ODOR_LAMBDA) for p in self.puddles)

    def odor_by_kind(self, x, y) -> dict:
        out: dict = {}
        for p in self.puddles:
            out[p.kind] = out.get(p.kind, 0.0) + p.amount * math.exp(-math.hypot(p.x - x, p.y - y) / ODOR_LAMBDA)
        return out

    def antennae(self) -> tuple[float, float]:
        """Odour at the left and right antenna, with 5% multiplicative receptor noise.

        The total is returned; the odour of each substance at each antenna is left in
        `self.odor_lr` ({kind: (left, right)}), because each smells different (configs/alcohol.yaml).
        """
        f = self.fly
        hx, hy = f.x + 13 * math.cos(f.th), f.y + 13 * math.sin(f.th)
        nx, ny = -math.sin(f.th), math.cos(f.th)
        kl = self.odor_by_kind(hx - ANTENNA_OFFSET * nx, hy - ANTENNA_OFFSET * ny)
        kr = self.odor_by_kind(hx + ANTENNA_OFFSET * nx, hy + ANTENNA_OFFSET * ny)
        n = self.rng.normal(1.0, 0.05, 2)
        self.odor_lr = {k: (max(0.0, kl[k] * n[0]), max(0.0, kr[k] * n[1])) for k in kl}
        return (sum(v[0] for v in self.odor_lr.values()), sum(v[1] for v in self.odor_lr.values()))

    def rays(self) -> np.ndarray:
        f = self.fly
        out = np.empty(3, np.float32)
        for i, da in enumerate(RAY_ANGLES):
            dx, dy = math.cos(f.th + da), math.sin(f.th + da)
            t = RAY_MAX
            if dx > 1e-9:
                t = min(t, (TABLE_W - MARGIN - f.x) / dx)
            elif dx < -1e-9:
                t = min(t, (MARGIN - f.x) / dx)
            if dy > 1e-9:
                t = min(t, (TABLE_H - MARGIN - f.y) / dy)
            elif dy < -1e-9:
                t = min(t, (MARGIN - f.y) / dy)
            out[i] = max(0.0, min(t, RAY_MAX)) / RAY_MAX
        return out

    def contact_puddle(self):
        f = self.fly
        if f.pose != "up" or f.z >= FLY_Z:
            return None
        best, bd = None, CONTACT_DIST
        for p in self.puddles:
            d = math.hypot(p.x - f.x, p.y - f.y)
            if d < bd:
                best, bd = p, d
        return best

    def taste(self):
        """(sweet, bitter, puddle) at the mouthparts. Bitterness grows with ABV and impurities."""
        p = self.contact_puddle()
        if p is None:
            return 0.0, 0.0, None
        return p.sugar * (0.4 + 0.6 * p.amount), min(1.0, 1.6 * p.abv + p.impurity), p

    # ---------------------------------------------------------------- physics
    def step(self, w_cmd, v_cmd, lift_cmd, dt=DT):
        f = self.fly
        self.t += dt
        f.bumped = False
        w_cmd = min(1.0, max(-1.0, w_cmd))
        lift_cmd = 0.0 if f.pose != "up" else min(1.0, max(0.0, lift_cmd))
        dz = lift_cmd - f.z
        f.z = min(1.0, max(0.0, f.z + math.copysign(min(abs(dz), Z_RATE * dt), dz)))
        vmax = V_MAX_WALK + (V_MAX_FLY - V_MAX_WALK) * f.z
        wmax = W_MAX_WALK + (W_MAX_FLY - W_MAX_WALK) * f.z
        tau_v = TAU_V_WALK + (TAU_V_FLY - TAU_V_WALK) * f.z
        if f.pose != "up":
            v_t, w_t, tau_v = 0.0, 0.0, 0.1
        else:
            v_t, w_t = v_cmd * vmax, w_cmd * wmax
        f.v += (v_t - f.v) * min(1.0, dt / tau_v)
        f.w += (w_t - f.w) * min(1.0, dt / TAU_W)
        f.th = wrap(f.th + f.w * dt)
        nx = f.x + f.v * math.cos(f.th) * dt
        ny = f.y + f.v * math.sin(f.th) * dt
        for attr in ("touch_l", "touch_r", "vib"):
            setattr(f, attr, getattr(f, attr) * math.exp(-dt / 0.25))
        lo_x, hi_x, lo_y, hi_y = MARGIN, TABLE_W - MARGIN, MARGIN, TABLE_H - MARGIN
        hit_x, hit_y = nx < lo_x or nx > hi_x, ny < lo_y or ny > hi_y
        if hit_x or hit_y:
            nx, ny = min(hi_x, max(lo_x, nx)), min(hi_y, max(lo_y, ny))
            f.bumped = True
            # the wall is felt by the antennae; what to do about it is the brain's business
            to_wall = wrap(math.atan2(0.0, 1.0 if nx >= hi_x else -1.0) - f.th) if hit_x else \
                wrap(math.atan2(1.0 if ny >= hi_y else -1.0, 0.0) - f.th)
            side = math.sin(to_wall)
            f.touch_l = min(1.0, f.touch_l + (0.9 if side <= 0 else 0.3))
            f.touch_r = min(1.0, f.touch_r + (0.9 if side > 0 else 0.3))
            if f.z <= FLY_Z:
                f.v = min(f.v, 0.0)
        f.x, f.y = nx, ny

    def tap(self, strength=1.0):
        """Someone knocks on the table: the Johnston organ feels it."""
        self.fly.vib = min(1.0, self.fly.vib + strength)

    def sip(self, pe: float, dt=DT):
        """The proboscis (MN9) decides the sip; the world only moves the liquid. Returns dose drunk."""
        f = self.fly
        p = self.contact_puddle()
        f.sipping = bool(p is not None and pe >= 0.5)
        delivered = 0.0
        self.last_take = (0.0, 0.0)
        if f.sipping:
            take = min(p.amount, SIP_RATE * dt)
            p.amount -= take
            p.idle = 0.0
            delivered = p.dose * take
            self.last_take = (take, p.sugar)
            if p.amount <= 1e-6:
                self.puddles.remove(p)
        for q in list(self.puddles):
            if q is p and f.sipping:
                continue
            q.idle += dt
            if q.idle >= EVAPORATE_S:
                self.puddles.remove(q)
        return delivered
