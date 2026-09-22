"""The world only does physics, smell, taste and touch: it never decides anything for the fly."""
import math

import numpy as np

from mosca.config import load_yaml
from mosca.world import DT, MARGIN, MAX_PUDDLES, TABLE_H, TABLE_W, World

DRINKS = {d["id"]: d for d in load_yaml("alcohol.yaml")["drinks"]}


def world(seed=1):
    w = World(np.random.default_rng(seed))
    w.place_fly()
    return w


def test_max_three_puddles_and_spacing():
    w = world()
    made = [w.spawn_puddle("beer", DRINKS["beer"]) for _ in range(6)]
    assert sum(p is not None for p in made) == MAX_PUDDLES
    for i, p in enumerate(w.puddles):
        assert 50 <= p.x <= TABLE_W - 50 and 50 <= p.y <= TABLE_H - 50
        for q in w.puddles[:i]:
            assert math.hypot(p.x - q.x, p.y - q.y) >= 60


def test_the_world_never_starts_a_sip():
    w = world()
    p = w.spawn_puddle("beer", DRINKS["beer"])
    w.fly.x, w.fly.y = p.x, p.y
    for _ in range(int(5 / DT)):
        assert w.sip(0.0) == 0.0 and not w.fly.sipping
    assert p.amount == 1.0


def test_sip_empties_a_puddle_in_two_and_a_half_seconds():
    w = world()
    p = w.spawn_puddle("beer", DRINKS["beer"])
    w.fly.x, w.fly.y = p.x, p.y
    total, t = 0.0, 0.0
    while w.puddles and t < 5:
        total += w.sip(1.0)
        t += DT
    assert not w.puddles and abs(t - 2.5) < 0.1 and abs(total - DRINKS["beer"]["dose"]) < 1e-6


def test_untouched_puddle_evaporates():
    w = world()
    w.spawn_puddle("wine", DRINKS["wine"])
    w.fly.x, w.fly.y = 40, 40
    for _ in range(int(41 / DT)):
        w.sip(0.0)
    assert not w.puddles


def test_wall_blocks_and_is_felt_but_does_not_turn_the_fly():
    w = world()
    w.fly.x, w.fly.y, w.fly.th = TABLE_W - MARGIN - 2, 270, 0.0
    for _ in range(10):
        w.step(0.0, 1.0, 0.0)
        if w.fly.bumped:
            break
    assert w.fly.bumped and max(w.fly.touch_l, w.fly.touch_r) > 0.3 and w.fly.th == 0.0
    assert w.fly.x <= TABLE_W - MARGIN


def test_bitterness_grows_with_abv_and_impurity():
    out = {}
    for kind in ("beer", "garrafon"):
        w = world()
        p = w.spawn_puddle(kind, DRINKS[kind])
        w.fly.x, w.fly.y = p.x, p.y
        out[kind] = w.taste()[:2]
    assert out["garrafon"][1] > out["beer"][1] and out["beer"][0] > out["garrafon"][0]


def test_fly_stays_on_the_table():
    w = world(7)
    rng = np.random.default_rng(3)
    for _ in range(int(60 / DT)):
        w.step(float(rng.uniform(-1, 1)), 1.0, float(rng.random() < 0.3))
        assert MARGIN <= w.fly.x <= TABLE_W - MARGIN and MARGIN <= w.fly.y <= TABLE_H - MARGIN
