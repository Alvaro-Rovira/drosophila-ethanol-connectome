"""Rate network on the real MaleCNS wiring.

    x_i = relu( G * sum_j W_ij * sign_j * out_j  + b_i + u_i - beta_i * a_i )     clipped to [0, 5]
    h_i <- h_i + (1 - exp(-dt / tau_i)) * (x_i - h_i)
    out_j = h_j * m_j                                   (m_j: what ethanol does to neuron j's synapses)

W = synapse counts normalised per postsynaptic neuron; sign per presynaptic neuron from its
neurotransmitter. **The wiring is never modified.** Ethanol never touches the body: it only changes
m_j, by neurotransmitter class, and adds synaptic noise (see configs/alcohol.yaml).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.sparse as sp

# membrane time constants per class, ms (modelling hypothesis, typical insect values)
TAU_MS = {"sensory": 15.0, "inter": 30.0, "modulatory": 30.0, "descending": 45.0, "motor": 75.0}
# spike-frequency adaptation on central neurons: gives walking bouts and pauses on its own
BETA = {"sensory": 0.0, "inter": 0.2, "modulatory": 0.2, "descending": 0.2, "motor": 0.0}
TAU_ADAPT_MS = 500.0
EXCITATORY = ("acetylcholine",)
INHIBITORY = ("gaba", "glutamate", "histamine")
MONOAMINE = ("octopamine", "dopamine", "serotonin")


@dataclass
class BrainParams:
    G: float = 1.25
    b: float = 0.003
    h_max: float = 5.0
    f_brain: float = 15.0
    adaptation: bool = True
    seed: int = 5


class Brain:
    def __init__(self, path, params: BrainParams | None = None):
        z = np.load(path, allow_pickle=False)
        self.path = str(path)
        self.N = int(z["n"])
        self.indptr = z["indptr"].astype(np.int32)
        self.indices = z["indices"].astype(np.int32)
        self.row_scale = z["row_scale"].astype(np.float32)
        self.sign = z["sign"].astype(np.int8)
        self.klass = z["klass"].astype(str)
        self.superclass = z["superclass"]
        self.cell_type = z["cell_type"]
        self.side = z["side"]
        self.nt = z["nt"].astype(str)
        self.body_id = z["body_id"]
        self.soma_xyz = z["soma_xyz"]
        self.groups = {k[4:]: z[k] for k in z.files if k.startswith("grp_")}
        self.nnz = len(self.indices)
        self.p = params or BrainParams()
        rows = np.repeat(np.arange(self.N, dtype=np.int32), np.diff(self.indptr))
        data = z["w"].astype(np.float32) * self.row_scale[rows]
        self.A = sp.csr_matrix((data, self.indices, self.indptr), shape=(self.N, self.N))
        self.signf = self.sign.astype(np.float32)
        self.inhib = self.sign < 0
        self.is_exc = np.isin(self.nt, EXCITATORY) | (~self.inhib & ~np.isin(self.nt, MONOAMINE))
        self.is_mono = np.isin(self.nt, MONOAMINE)
        rng = np.random.default_rng(self.p.seed)
        s = 0.35
        self.b = (self.p.b * np.exp(rng.normal(0, s, self.N) - s * s / 2)).astype(np.float32)
        self.tau = np.array([TAU_MS[k] for k in self.klass], np.float32)
        self.beta = (np.array([BETA[k] for k in self.klass], np.float32) if self.p.adaptation
                     else np.zeros(self.N, np.float32))
        self.set_rate(self.p.f_brain)

    def set_rate(self, f_brain: float):
        self.p.f_brain = float(f_brain)
        dt_ms = 1000.0 / self.p.f_brain
        self.k_h = (1.0 - np.exp(-dt_ms / self.tau)).astype(np.float32)
        self.k_a = np.float32(1.0 - math.exp(-dt_ms / TAU_ADAPT_MS))

    def group(self, name: str) -> np.ndarray:
        return self.groups.get(name, np.array([], np.int32))

    def init_state(self, B: int = 1) -> dict:
        return {"h": np.tile(self.b[:, None], (1, B)).astype(np.float32),
                "a": np.zeros((self.N, B), np.float32)}

    def class_multiplier(self, exc_x=1.0, inh_x=1.0, mono_x=1.0) -> np.ndarray:
        """What ethanol does to each neuron's synapses, by neurotransmitter class."""
        m = np.ones(self.N, np.float32)
        m[self.is_exc] = exc_x
        m[self.inhib] = inh_x
        m[self.is_mono] = mono_x
        return m

    def step(self, st: dict, u: np.ndarray, m: np.ndarray | None = None, noise: float = 0.0,
             rng: np.random.Generator | None = None) -> np.ndarray:
        """One tick. u, m: (N,) or (N,B). noise: multiplicative synaptic noise (zero mean)."""
        h = st["h"]
        B = h.shape[1]
        out = h.copy()
        if m is not None:
            out *= m if m.ndim == 2 else m[:, None]
        if noise > 0 and rng is not None:
            # zero-mean multiplicative noise on transmission: it scrambles the signal without
            # raising the average rate (additive noise before a relu would excite the network)
            out *= np.maximum(0.0, 1.0 + noise * rng.standard_normal((self.N, B), dtype=np.float32))
        x = self.A @ (out * self.signf[:, None])
        x *= self.p.G
        x += self.b[:, None]
        x += u if u.ndim == 2 else u[:, None]
        if self.p.adaptation:
            x -= self.beta[:, None] * st["a"]
        np.clip(x, 0.0, self.p.h_max, out=x)
        h += self.k_h[:, None] * (x - h)
        if self.p.adaptation:
            st["a"] += self.k_a * (h - st["a"])
        return h

    def info(self) -> dict:
        return {"file": Path(self.path).name, "N": self.N, "edges": self.nnz, "f_brain": self.p.f_brain}
