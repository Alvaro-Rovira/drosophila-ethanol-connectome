"""Crop and haemolymph sugar: how hungry the fly is.

The hunger signal reaches the brain as a GAIN on the sweet (up) and bitter (down) gustatory
receptors, which is how starvation acts in real flies (Inagaki et al. 2012, 2014). There is no
synaptic path from the enteric or nutrient-sensing neurons to MN9 in the connectome: this is a
hormonal pathway, modelled as such and declared.
"""
from __future__ import annotations


class Gut:
    def __init__(self, cfg: dict):
        c = cfg["estomago"]
        self.per_drop = float(c["buche_por_gota"])
        self.k_empty = float(c["vaciado"])
        self.k_met = float(c["metabolismo"])
        self.ref = float(c["azucar_ref"])
        self.init = float(c["azucar_inicial"])
        self.sweet_x = [float(x) for x in c["dulce_x"]]
        self.bitter_x = [float(x) for x in c["amargo_x"]]
        self.stretch = float(c["estiramiento"])
        self.frozen = None
        self.reset()

    def reset(self):
        self.crop = 0.0           # 0 empty .. 1 full
        self.crop_sugar = 0.0     # sugar content of what is in the crop
        self.sugar = self.init    # haemolymph sugar

    def freeze(self, hunger=None):
        self.frozen = hunger

    def drink(self, amount: float, sugar: float):
        """amount: fraction of a whole drop."""
        if amount <= 0:
            return
        add = self.per_drop * amount
        tot = self.crop + add
        self.crop_sugar = (self.crop_sugar * self.crop + sugar * add) / max(tot, 1e-9)
        self.crop = min(1.0, tot)

    def update(self, dt: float):
        flow = self.k_empty * self.crop * dt
        self.crop = max(0.0, self.crop - flow)
        self.sugar = max(0.0, self.sugar + flow * self.crop_sugar * 2.0 - self.k_met * self.sugar * dt)

    @property
    def hunger(self) -> float:
        if self.frozen is not None:
            return float(self.frozen)
        # sugar in the haemolymph and stretch of the full crop both satiate (crop stretch: Gelperin
        # 1971 in the blowfly)
        return float(min(1.0, max(0.0, 1.0 - self.sugar / self.ref - self.stretch * self.crop)))

    def gains(self) -> tuple[float, float]:
        h = self.hunger
        s0, s1 = self.sweet_x
        b0, b1 = self.bitter_x
        return s0 + (s1 - s0) * h, b0 + (b1 - b0) * h
