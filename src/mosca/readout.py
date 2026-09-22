"""Steering readout: a linear probe on <= 1.536 neurons that do NOT receive sensory input.

The population read: the descending neurons (what the brain sends to the body), the projection
neurons of the antennal lobe and the mushroom-body output neurons (the higher olfactory centres,
where the left/right odour difference survives), and the most connected of the rest.

It is BILATERALLY SYMMETRIC, as the fly is:
  turn  = only from left - right differences of homologous neurons (same cell type, opposite sides)
  speed = only from DESCENDING neurons (left + right means and those without a homologue): walking is
          commanded by the descending neurons. When speed was read from every neuron, ethanol pushed
          the olfactory neurons out of their trained range and the fly froze near a drink.
A change that acts on both sides alike (ethanol acts on the whole brain) cannot make the fly turn;
only an asymmetry can. The earlier, unconstrained readout turned a global change of activity into a
constant turn and the fly spun in place.

It is trained once (DAgger, scripts/train.py) to imitate a teacher that only sees what the fly senses;
the wiring is never touched. A shuffled brain with the same readout cannot find the drinks: the
information has to come from the real connectome.
"""
from __future__ import annotations

import numpy as np

ZCLIP = 3.0


def feature_index(brain, senses, n_max: int = 1536) -> np.ndarray:
    used = np.zeros(brain.N, bool)
    used[senses.inputs] = True
    indeg = np.diff(brain.indptr)
    dn = np.where((brain.klass == "descending") & ~used)[0]
    dn = dn[np.argsort(-indeg[dn])[:512]]
    olf = np.concatenate([brain.group(f"{g}|{s}") for g in ("ALPN", "MBON") for s in "LRU"]).astype(np.int64)
    olf = olf[~used[olf]]
    pick = np.union1d(dn, olf)
    rest = np.where(~used & ~np.isin(np.arange(brain.N), pick))[0]
    rest = rest[np.argsort(-indeg[rest])[: max(0, n_max - len(pick))]]
    return np.sort(np.concatenate([pick, rest]))


def speed_mask(brain, feat) -> np.ndarray:
    """Features allowed to set the speed: the descending neurons."""
    return np.asarray(brain.klass, str)[feat] == "descending"


def pairing(brain, feat) -> tuple[np.ndarray, np.ndarray, int]:
    """Group id of each feature on the left (gl) and right (gr) side of its cell type, -1 if the
    type has no homologue on the other side among the features (or no type / no side)."""
    types = np.asarray(brain.cell_type, str)[feat]
    sides = np.asarray(brain.side, str)[feat]
    left = {t for t, s in zip(types, sides) if s == "L" and t}
    right = {t for t, s in zip(types, sides) if s == "R" and t}
    both = sorted(left & right)
    gid = {t: i for i, t in enumerate(both)}
    gl = np.array([gid[t] if (s == "L" and t in gid) else -1 for t, s in zip(types, sides)], np.int64)
    gr = np.array([gid[t] if (s == "R" and t in gid) else -1 for t, s in zip(types, sides)], np.int64)
    return gl, gr, len(both)


def _agg(g: np.ndarray, ng: int) -> np.ndarray:
    """(F, ng) matrix that averages the features of each group."""
    A = np.zeros((len(g), ng))
    m = g >= 0
    A[np.where(m)[0], g[m]] = 1.0
    return A / np.maximum(A.sum(0), 1.0)


def design(Z: np.ndarray, gl: np.ndarray, gr: np.ndarray, ng: int, cache: dict | None = None,
           vmask: np.ndarray | None = None):
    """Z: (T, F) clipped z-scores -> (D, V): D = left - right per homologous type (T, ng);
    V = [(left + right) / 2 of speed types, unpaired speed features, 1]."""
    Z = np.atleast_2d(Z)
    if cache is not None and "AL" in cache:
        AL, AR, un, gv = cache["AL"], cache["AR"], cache["un"], cache["gv"]
    else:
        AL, AR = _agg(gl, ng), _agg(gr, ng)
        vm = np.ones(len(gl), bool) if vmask is None else np.asarray(vmask, bool)
        un = (gl < 0) & (gr < 0) & vm
        gv = np.zeros(ng, bool)                    # a type sets the speed if its members may
        gv[gl[(gl >= 0) & vm]] = True
        gv[gr[(gr >= 0) & vm]] = True
        if cache is not None:
            cache.update(AL=AL, AR=AR, un=un, gv=gv)
    L, R = Z @ AL, Z @ AR
    return L - R, np.c_[((L + R) / 2)[:, gv], Z[:, un], np.ones(len(Z))]


class Readout:
    TAU_ADAPT = 3.0    # s: a sustained turn to one side adapts away, like any motor command

    def __init__(self, feat, mu, sd, Wd, Wv, gl, gr, ng, vmask=None, tau=0.1):
        self.feat = np.asarray(feat, np.int64)
        self.mu, self.sd = np.asarray(mu, np.float32), np.asarray(sd, np.float32)
        self.Wd, self.Wv = np.asarray(Wd, np.float64), np.asarray(Wv, np.float64)
        self.gl, self.gr, self.ng = np.asarray(gl, np.int64), np.asarray(gr, np.int64), int(ng)
        self.vmask = None if vmask is None else np.asarray(vmask, bool)
        self.tau = tau
        self.y = np.zeros(2, np.float32)
        self.bias = 0.0
        self._cache: dict = {}

    @classmethod
    def load(cls, path):
        z = np.load(path)
        return cls(z["feat"], z["mu"], z["sd"], z["Wd"], z["Wv"], z["gl"], z["gr"], int(z["ng"]),
                   z["vmask"] if "vmask" in z.files else None)

    def save(self, path, **meta):
        np.savez_compressed(path, feat=self.feat, mu=self.mu, sd=self.sd, Wd=self.Wd, Wv=self.Wv,
                            gl=self.gl, gr=self.gr, ng=np.int64(self.ng),
                            **({} if self.vmask is None else {"vmask": self.vmask}), **meta)

    def reset(self):
        self.y[:] = 0.0
        self.bias = 0.0

    def zscore(self, h_col: np.ndarray) -> np.ndarray:
        # each input is bounded to +-3 SD of what it did in training, like a saturating neuron
        return np.clip((h_col[self.feat] - self.mu) / self.sd, -ZCLIP, ZCLIP)

    def __call__(self, h_col: np.ndarray, dt: float) -> tuple[float, float]:
        D, V = design(self.zscore(h_col)[None, :], self.gl, self.gr, self.ng, self._cache, self.vmask)
        w = float(D[0] @ self.Wd)
        # slow adaptation of the turn: brief turns (towards an odour, away from a wall) pass, a
        # turn held to one side for seconds fades (the subcircuit is not perfectly symmetric:
        # 883 left and 1.343 right olfactory receptors are annotated, and ethanol amplifies that)
        self.bias += (1.0 - np.exp(-dt / self.TAU_ADAPT)) * (w - self.bias)
        out = np.array([w - self.bias, float(V[0] @ self.Wv)], np.float32)
        self.y += (1.0 - np.exp(-dt / self.tau)) * (out - self.y)
        return float(np.clip(self.y[0], -1, 1)), float(np.clip(self.y[1], -0.3, 1))
