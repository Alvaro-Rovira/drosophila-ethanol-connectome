"""Ethanol kinetics and its neural effects. Ethanol never touches the body directly."""
import numpy as np
import pytest

from mosca.alcohol import Alcohol
from mosca.config import load_yaml
from mosca.world import DT

CFG = load_yaml("alcohol.yaml")


def test_level_always_in_unit_interval():
    rng = np.random.default_rng(0)
    al = Alcohol(CFG)
    for _ in range(20000):
        if rng.random() < 0.05:
            al.drink(float(rng.uniform(0, 0.5)))
        al.update(DT)
        assert 0.0 <= al.a <= 1.0 and al.S >= 0.0 and 0.0 <= al.r <= 1.0


def test_decays_to_zero_without_drinking():
    al = Alcohol(CFG)
    al.drink(0.9)
    for _ in range(int(3000 / DT)):
        al.update(DT)
    assert al.S < 1e-6 and al.a == 0.0


def test_drinking_never_lowers_the_level():
    a1, a2 = Alcohol(CFG), Alcohol(CFG)
    for al in (a1, a2):
        al.drink(0.3)
    for _ in range(300):
        a1.drink(0.01)
        a1.update(DT)
        a2.update(DT)
        assert a1.a >= a2.a - 1e-12


def test_sober_means_no_neural_effect():
    n = Alcohol(CFG).neural()
    assert n["mono_x"] == n["exc_x"] == n["inh_x"] == n["olf_x"] == 1.0
    assert n["noise"] == 0.0 and n["delay_ms"] == 0.0


@pytest.mark.parametrize("key,sign", [("excitacion_x", -1), ("ruido", 1), ("retardo_ms", 1), ("olfato_x", -1)])
def test_curves_monotone(key, sign):
    ys = np.asarray(CFG["neural"][key], float)
    assert np.all(np.diff(ys) * sign >= 0), key


def test_biphasic_monoamines_and_late_gaba_potentiation():
    mono = np.asarray(CFG["neural"]["monoamina_x"])
    inh = np.asarray(CFG["neural"]["inhibicion_x"])
    assert mono.argmax() not in (0, len(mono) - 1) and mono[-1] < 1.0     # up, then down
    assert inh[1] < 1.0 < inh[-1]                                            # disinhibition, then sedation


def test_stages_are_only_labels():
    al = Alcohol(CFG)
    seen = []
    for a in (0.0, 0.1, 0.4, 0.7, 0.95):
        al.freeze(a)
        al.update(DT)
        seen.append(al.stage())
    assert seen == ["sobria", "piripi", "pedo", "borracha", "ko"]
    # there is nothing in the engine that could move the fly: only numbers for the neurons
    assert set(al.neural()) == {"mono_x", "exc_x", "inh_x", "noise", "delay_ms", "olf_x"}
