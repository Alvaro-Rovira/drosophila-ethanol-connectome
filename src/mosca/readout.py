"""Steering readout: a linear probe on <= 1.024 neurons that do NOT receive sensory input.

It turns the population activity into a turn and a walking command. It is trained once (DAgger,
scripts/train.py) to imitate a teacher that only sees what the fly senses; the wiring is never
touched. A shuffled brain with the same readout cannot find the drinks: the information has to come
from the real connectome.
"""
from __future__ import annotations

import numpy as np


def feature_index(brain, senses, n_max: int = 1024) -> np.ndarray:
    used = np.zeros(brain.N, bool)
    used[senses.inputs] = True
    indeg = np.diff(brain.indptr)
    dn = np.where((brain.klass == "descending") & ~used)[0]
    dn = dn[np.argsort(-indeg[dn])[:512]]
    rest = np.where(~used & ~np.isin(np.arange(brain.N), dn))[0]
    rest = rest[np.argsort(-indeg[rest])[: n_max - len(dn)]]
    return np.sort(np.concatenate([dn, rest]))


class Readout:
    def __init__(self, feat, mu, sd, W, tau=0.1):
        self.feat = np.asarray(feat, np.int64)
        self.mu, self.sd = np.asarray(mu, np.float32), np.asarray(sd, np.float32)
        self.W = np.asarray(W, np.float32)
        self.tau = tau
        self.y = np.zeros(2, np.float32)

    @classmethod
    def load(cls, path):
        z = np.load(path)
        return cls(z["feat"], z["mu"], z["sd"], z["W"])

    def save(self, path, **meta):
        np.savez_compressed(path, feat=self.feat, mu=self.mu, sd=self.sd, W=self.W, **meta)

    def reset(self):
        self.y[:] = 0.0

    def __call__(self, h_col: np.ndarray, dt: float) -> tuple[float, float]:
        z = np.append((h_col[self.feat] - self.mu) / self.sd, 1.0).astype(np.float32)
        self.y += (1.0 - np.exp(-dt / self.tau)) * (z @ self.W - self.y)
        return float(np.clip(self.y[0], -1, 1)), float(np.clip(self.y[1], -0.3, 1))
