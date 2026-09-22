"""The neurons drive the fly. Each test removes or changes neurons and checks the behaviour follows.

Silencing = forcing those neurons to zero every tick. The wiring is never edited.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from mosca.config import ARTIFACTS
from mosca.readout import Readout
from mosca.sim import BRAIN_FILE, READOUT_FILE, Sim, load_brain
from mosca.world import DT, TABLE_W

NORMS = json.loads((ARTIFACTS / "norms.json").read_text())
BRAIN = load_brain()


def sim(seed=11, brain=None):
    return Sim(brain or BRAIN, seed=seed, norms=NORMS, readout=Readout.load(READOUT_FILE))


def silence(s, *groups):
    idx = np.unique(np.concatenate([s.brain.group(f"{g}|{side}") for g in groups for side in "LRU"
                                    if len(s.brain.group(f"{g}|{side}"))]))
    orig = s.brain.step

    def step(st, u, m=None, noise=0.0, rng=None):
        h = orig(st, u, m, noise, rng)
        h[idx] = 0.0
        return h
    s.brain.step = step
    return idx


def held_on(s, kind, secs=6.0):
    s.world.place_fly(360, 270, 0.0)
    p = s.order(kind, 100, 120)
    f = s.world.fly
    p.x, p.y = f.x + 4, f.y
    x0, y0 = f.x, f.y
    n = 0
    for _ in range(int(secs / DT)):
        s.step()
        f.x, f.y, f.z = x0, y0, 0.0
        n += int(f.sipping)
    return n


@pytest.fixture(autouse=True)
def fresh_brain():
    yield
    BRAIN.step = type(BRAIN).step.__get__(BRAIN)     # undo any silencing


def test_same_seed_same_trajectory():
    a, b = sim(5), sim(5)
    a.order("beer"); b.order("beer")
    for _ in range(300):
        a.step(); b.step()
    assert (a.world.fly.x, a.world.fly.y, a.world.fly.th) == (b.world.fly.x, b.world.fly.y, b.world.fly.th)


def test_the_fly_drinks_the_beer_and_refuses_the_garrafon():
    """It may take a taste of the garrafón (MN9 has an onset transient before the bitterness
    suppresses it), but it does not keep drinking: less than half a second."""
    assert held_on(sim(21), "beer") * DT > 2.0
    assert held_on(sim(22), "garrafon") * DT < 0.5


def test_without_mn9_it_cannot_drink():
    s = sim(23)
    silence(s, "MN9")
    assert held_on(s, "beer") == 0


def test_without_the_giant_fibre_it_does_not_escape():
    def trial(ablate):
        s = sim(31)
        if ablate:
            silence(s, "DNp01")
        took = False
        for k in range(int(3 / DT)):
            if k == 45:
                s.tap(1.0)
            s.step()
            took |= s.world.fly.z > 0.15
        return took
    assert trial(False) and not trial(True)


def test_without_leg_motor_neurons_it_falls_and_stays_down():
    s = sim(41)
    silence(s, "MN_leg_T1", "MN_leg_T2", "MN_leg_T3")
    for _ in range(int(6 / DT)):
        s.step()
    assert s.world.fly.pose != "up" and s.act() == "asleep"


def test_a_silent_brain_does_not_move():
    s = sim(42)
    orig = s.brain.step

    def step(st, u, m=None, noise=0.0, rng=None):
        h = orig(st, u, m, noise, rng)
        h[:] = 0.0
        return h
    s.brain.step = step
    for _ in range(int(4 / DT)):
        s.step()
    assert abs(s.world.fly.v) < 1.0


def test_sober_fly_never_falls():
    s = sim(51)
    for _ in range(int(40 / DT)):
        s.step()
        assert s.world.fly.pose == "up"


def test_ethanol_acting_only_on_synapses_makes_it_fall():
    """No body rule: at a high level the leg motor neurons lose their tone and the fly goes down."""
    s = sim(52)
    s.alcohol.freeze(1.0)
    for _ in range(int(15 / DT)):
        s.step()
    assert s.world.fly.pose != "up"


def test_low_dose_makes_it_faster():
    def speed(a):
        out = []
        for seed in range(60, 66):
            s = sim(seed)
            s.alcohol.freeze(a)
            path = 0.0
            for _ in range(int(20 / DT)):
                s.step()
                path += abs(s.world.fly.v) * DT
            out.append(path / 20)
        return float(np.mean(out))
    assert speed(0.3) > 1.2 * speed(0.0)


def test_shuffled_wiring_cannot_find_the_drinks():
    """Same readout, same inputs, same degrees and weights: only who-connects-to-whom is destroyed."""
    shuf = ARTIFACTS / "brain_shuffled.npz"
    if not shuf.exists():
        pytest.skip("scripts/evaluate.py shuffle")
    br = load_brain(shuf)

    def reach(brain):
        got = 0
        for seed in range(70, 78):
            s = sim(seed, brain)
            s.world.place_fly()
            s.order("beer", 150, 300)
            for _ in range(int(25 / DT)):
                s.step()
            got += s.drunk > 0
        return got
    assert reach(BRAIN) >= 6 and reach(br) <= 1


def test_brain_step_is_fast():
    import time
    s = sim(81)
    t0 = time.perf_counter()
    for _ in range(60):
        s.brain_tick()
    assert (time.perf_counter() - t0) / 60 < 0.005
