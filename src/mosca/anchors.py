"""Identified neurons and motor pools of MaleCNS v1.0, looked up by annotation (never invented).

Side: somaSide; if missing, the `_L`/`_R` suffix of `instance`; if missing, rootSide; else U.
Output: {group: {"L": [bodyId], "R": [...], "U": [...], "how": str, "confidence": str, "note": str}}
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow.ipc as ipc

ROOT = Path(__file__).resolve().parents[2]
ANN = ROOT / "data" / "body-annotations-male-cns-v1.0-minconf-0.5.feather"
COLS = ["bodyId", "superclass", "type", "instance", "class", "subclass", "somaSide", "rootSide",
        "entryNerve", "exitNerve", "somaLocation"]

# descending neurons with a published function
DN_TYPES = {
    "DNp09": ("marcha adelante con giro ipsilateral (P9; Bidaye et al. 2020)", "alta"),
    "DNa01": ("giro fino (Rayshubskiy et al. 2024)", "alta"),
    "DNa02": ("giro (Rayshubskiy et al. 2024)", "alta"),
    "DNg13": ("giro (candidata)", "media"),
    "MDN": ("marcha atrás (Bidaye et al. 2014)", "alta"),
    "DNp01": ("fibra gigante: escape y despegue (von Reyn et al. 2014)", "alta"),
    "DNp07": ("aterrizaje (Ache et al. 2019)", "media"),
    "DNp10": ("aterrizaje (Ache et al. 2019)", "media"),
    "DNp15": ("vuelo / cuello", "media"),
    "pIP10": ("canto de cortejo", "alta"),
    "DNg11": ("acicalado antenal (candidata)", "media"),
}
MOTOR_POOLS = ["MN_leg_T1", "MN_leg_T2", "MN_leg_T3", "MN_wing_power", "MN_wing_steer",
               "MN_haltere", "MN_neck", "MN9", "MN_feeding"]
SENSORY_POOLS = ["ORN", "JO_AB", "antennal_mech", "GRN_labellar", "GRN_pharyngeal", "GRN_leg"]
ANCHOR_GROUPS = list(DN_TYPES) + ["DNg12"] + MOTOR_POOLS


def load_annotations():
    df = ipc.open_file(ANN).read_all().select(COLS).to_pandas()
    df = df[df["superclass"].notna()].reset_index(drop=True)
    for c in COLS[1:-1]:
        df[c] = df[c].fillna("")
    side = df["somaSide"].where(df["somaSide"].isin(["L", "R"]), "")
    suffix = df["instance"].str.extract(r"_(L|R)\b", expand=False).fillna("")
    side = side.where(side != "", suffix)
    side = side.where(side != "", df["rootSide"].where(df["rootSide"].isin(["L", "R"]), ""))
    df["side"] = side.replace("", "U")
    return df


def _sel(df, mask, how, confidence, note=""):
    s = df[mask]
    g = {"how": how, "confidence": confidence, "note": note, "n": int(len(s))}
    for k in ("L", "R", "U"):
        g[k] = [int(b) for b in s.loc[s["side"] == k, "bodyId"]]
    return g


def build(df) -> dict:
    a = {}
    t, sc, cl, sub = df["type"], df["superclass"], df["class"], df["subclass"]
    for ty, (note, conf) in DN_TYPES.items():
        a[ty] = _sel(df, t == ty, f"type == '{ty}'", conf, note)
    a["DNg12"] = _sel(df, t.str.startswith("DNg12"), "type empieza por 'DNg12'", "media",
                      "acicalado anterior (candidata)")
    a["DN_all"] = _sel(df, sc == "descending_neuron", "superclass == descending_neuron", "alta", "")
    vm = sc == "vnc_motor"
    for s, seg in (("fl", "T1"), ("ml", "T2"), ("hl", "T3")):
        a[f"MN_leg_{seg}"] = _sel(df, vm & (sub == s), f"vnc_motor, subclass '{s}'", "alta",
                                  f"motoneuronas de la pata {seg}")
    wing = vm & (sub == "wm")
    power = t.str.contains(r"^(?:DLMn|DVMn|TTMn)", regex=True)
    a["MN_wing_power"] = _sel(df, wing & power, "vnc_motor wm, DLMn/DVMn/TTMn", "alta", "potencia del vuelo")
    a["MN_wing_steer"] = _sel(df, wing & ~power, "vnc_motor wm, resto", "alta", "dirección del ala")
    a["MN_haltere"] = _sel(df, vm & (sub == "hm"), "vnc_motor, subclass 'hm'", "alta", "halterios")
    a["MN_neck"] = _sel(df, (vm & (sub == "nm")) | ((sc == "cb_motor") & (df["exitNerve"] == "CvN")),
                        "vnc_motor nm + cb_motor CvN", "alta", "cuello")
    a["MN9"] = _sel(df, t == "MN9", "type == 'MN9'", "alta", "extensión de la probóscide")
    a["MN_feeding"] = _sel(df, (sc == "cb_motor") & df["exitNerve"].isin(["MxLbN", "PhN"]),
                           "cb_motor MxLbN/PhN", "alta", "alimentación")
    a["MN_all"] = _sel(df, sc.isin(["vnc_motor", "cb_motor"]), "superclass motor", "alta", "")
    a["ORN"] = _sel(df, t.str.startswith("ORN"), "type empieza por 'ORN'", "alta", "receptoras olfativas")
    a["JO_AB"] = _sel(df, t.str.match(r"JO-[AB]"), "type JO-A*/JO-B*", "alta", "órgano de Johnston (vibración)")
    a["antennal_mech"] = _sel(df, cl.str.contains("mechano") & (df["entryNerve"] == "AN")
                              & ~t.str.startswith("JO-"), "mecano, nervio AN, sin JO", "media", "tacto antenal")
    grn = cl == "gustatory"
    a["GRN_labellar"] = _sel(df, grn & sub.isin(["labellar bristle", "taste peg"]),
                             "gustatory, labelo", "alta", "gusto del labelo")
    a["GRN_pharyngeal"] = _sel(df, grn & (sub == "pharyngeal sensillum"), "gustatory, faringe", "alta", "")
    a["GRN_leg"] = _sel(df, grn & (sub == "leg bristle"), "gustatory, pata", "alta", "gusto tarsal")
    a["MBON"] = _sel(df, t.str.startswith("MBON"), "type MBON*", "alta", "salida del cuerpo fungiforme")
    a["DAN"] = _sel(df, t.str.match(r"(?:PAM|PPL|PPM)\d"), "type PAM/PPL/PPM", "alta", "dopaminérgicas")
    # 20.000: complete olfactory pathway, mushroom body, central complex, internal state
    a["ALPN"] = _sel(df, cl == "ALPN", "class ALPN", "alta", "neuronas de proyección del lóbulo antenal")
    a["ALLN"] = _sel(df, cl.isin(["ALLN", "ALIN", "ALON"]), "class ALLN/ALIN/ALON", "alta",
                     "interneuronas locales y de salida del lóbulo antenal")
    a["LH"] = _sel(df, t.str.match(r"^LH"), "type LH*", "alta", "cuerno lateral (olor innato)")
    a["KC"] = _sel(df, cl == "Kenyon_Cell", "class Kenyon_Cell", "alta", "células de Kenyon")
    a["APL"] = _sel(df, t == "APL", "type == 'APL'", "alta", "inhibición global del cuerpo fungiforme")
    a["CX"] = _sel(df, cl == "CX", "class CX", "alta", "complejo central")
    a["EPG"] = _sel(df, t.str.startswith("EPG"), "type EPG*", "alta", "brújula (E-PG)")
    a["ENDO"] = _sel(df, sc.isin(["cb_endocrine", "vnc_endocrine"]), "superclass endocrine", "alta",
                     "neurosecretoras (IPC, DH44, Hugin, CAPA, LK...)")
    a["NUTRIENT"] = _sel(df, t.isin(["IPC", "DH44"]), "type IPC / DH44", "media",
                         "sensoras de nutrientes en hemolinfa (azúcar)")
    a["ENS"] = _sel(df, sc == "ENS", "superclass ENS", "media", "sistema nervioso entérico (llenado del buche)")
    a["SEZPN"] = _sel(df, cl == "SEZPN", "class SEZPN", "media", "proyección desde el ganglio subesofágico")
    prop = cl == "mechanosensory_proprioceptive"
    a["PROP_leg"] = _sel(df, prop & sub.isin(["leg", "chordotonal organ", "campaniform sensilla", "hair plate"])
                         & (sc == "vnc_sensory"), "proprioceptivas de patas (VNC)", "alta",
                         "propioceptores de las patas")
    a["PROP_haltere"] = _sel(df, prop & (sub == "haltere"), "proprioceptivas del halterio", "alta",
                             "halterios (giro del cuerpo)")
    return a


def ids_of(a: dict, *groups) -> np.ndarray:
    out = []
    for g in groups:
        for k in ("L", "R", "U"):
            out += a[g][k]
    return np.unique(np.array(out, np.int64))


def save(a: dict, path: Path):
    path.write_text(json.dumps(a))
