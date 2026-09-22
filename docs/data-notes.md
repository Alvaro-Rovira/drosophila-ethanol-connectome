# Notas de datos (MaleCNS v1.0, flat-connectome, minconf 0.5)

Verificado contra los ficheros descargados (pyarrow 25.0.1) el 2026-09-19.

| Fichero | Tamaño | Filas / lotes | Columnas usadas |
|---|---|---|---|
| body-annotations-male-cns-v1.0-minconf-0.5.feather | 14 MB | 211.577 / 4 | `bodyId` (int64), `superclass`, `type`, `class`, `somaLocation` (list<int64> xyz) |
| body-neurotransmitters-male-cns-v1.0.feather | 41 MB | 1.835.518 / 29 | `body` (int64), `consensus_nt` |
| connectome-weights-male-cns-v1.0-minconf-0.5.feather | 1,0 GB | 151.856.684 / 2.318 | `body_pre`, `body_post`, `weight` (int64) |

Coinciden con lo que usa nfly salvo que la tabla de neurotransmisores se indexa por `body` (no `bodyId`).
Otras columnas de anotaciones: flywireType, instance, somaSide, statusLabel, vfbId, hemibrainType, supertype, subclass, rootSide, entryNerve, exitNerve, receptorType, status...

## superclass (211.577 cuerpos)
ol_intrinsic 89.403 · (nulo) 44.877 · cb_intrinsic 32.164 · vnc_intrinsic 13.161 · visual_projection 9.201 · vnc_sensory 6.370 ·
ol_sensory 6.098 · cb_sensory 4.868 · ascending_neuron 1.846 · **descending_neuron 1.314** · vnc_motor 708 · visual_centrifugal 563 ·
sensory_ascending 537 · cb_motor 107 · vnc_efferent 94 · cb_endocrine 72 · ENS 50 · vnc_tbc 38 · vnc_sensory_tbc 36 · vnc_endocrine 22 ·
cb_sensory_tbc 14 · sensory_descending 12 · efferent_ascending 8 · efferent_descending 4 · cb_efferent 4 · (tbc restantes) 6.
Sensoriales = superclass que contiene "sensory" (17.937 neuronas). Descendentes = `descending_neuron`.

## consensus_nt (1.835.518 cuerpos)
unclear 1.671.117 · acetylcholine 104.193 · glutamate 29.443 · gaba 22.196 · histamine 8.024 · dopamine 396 · octopamine 101 · serotonin 48.

Signo (simplificación de nfly): acetylcholine, dopamine, serotonin, octopamine -> +1; gaba, glutamate, histamine -> -1;
unclear / sin dato -> +1. (Glutamato puede ser excitador en algunas sinapsis; aquí se trata como inhibidor, como en nfly.)

## Aristas
Con `weight >= 3` y ambas neuronas con superclass no nula (fragmentos y glía fuera): **10.520.377** aristas (lectura por lotes con `ipc.open_file`, un record batch cada vez).
Caché local: `data/edges_w3.npz` (índices int32 + peso int32).

`somaLocation` existe para el 84% de las neuronas con superclass (82,5% dentro del subcircuito): el dashboard dibuja un scatter 2D (x, y).
