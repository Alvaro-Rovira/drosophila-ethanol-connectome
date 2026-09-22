"""YAML config loading and piecewise-linear curves."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"
ARTIFACTS = ROOT / "artifacts"


def load_yaml(name: str | Path) -> dict:
    p = Path(name)
    if not p.is_absolute():
        p = CONFIGS / p
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class Curve:
    """Piecewise-linear curve y(a) over fixed control points."""

    def __init__(self, xs, ys):
        self.xs = np.asarray(xs, float)
        self.ys = np.asarray(ys, float)
        assert self.xs.shape == self.ys.shape

    def __call__(self, a):
        return np.interp(a, self.xs, self.ys)
