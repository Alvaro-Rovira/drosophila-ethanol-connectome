# Subcircuito de 8.000 neuronas

**N = 8,000** neuronas reales de MaleCNS v1.0 · **488,753 conexiones** (>= 3 sinapsis).

## Por qué se eligieron así

La selección anterior (entradas sensoriales -> descendentes en <= 3 saltos) no tenía **ninguna**
motoneurona, ni MDN, ni la fibra gigante, ni DNp09, ni receptores olfativos. Esas neuronas no
podían mover las patas, así que un guion tenía que hacerlo. Ahora las 8.000 se eligen por cupos
de función para que estén las que perciben, las que deciden y las que mueven.

| Cupo | Neuronas |
|---|---:|
| anclas | 644 |
| descendentes | 1,244 |
| sensoriales | 1,300 |
| socios_de_anclas | 1,300 |
| via_olfato_giro | 220 |
| via_gusto_MN9 | 220 |
| via_gusto_pata | 220 |
| via_tacto_MDN | 220 |
| via_vibracion_GF | 220 |
| via_descendentes_patas | 220 |
| premotoras | 900 |
| cuerpo_fungiforme | 200 |
| relleno | 1,092 |

| Clase | Neuronas |
|---|---:|
| descending | 1,314 |
| inter | 4,431 |
| modulatory | 132 |
| motor | 576 |
| sensory | 1,547 |

Inhibitorias (GABA, glutamato, histamina): 34.7%.

## Comprobaciones

- Descendentes que reciben señal de los sensores en <= 4 saltos: **100.0%**.
- Motoneuronas que la reciben: **99.8%**.
- Componente conexa dominante: **99.5%** de las neuronas.
- Neuronas identificadas aisladas: **0**.
- 42 neuronas obligatorias sin ninguna arista de >= 3 sinapsis dentro recuperan sus aristas reales de >= 2 sinapsis (no se inventa ninguna).

## Neuronas identificadas dentro

| Grupo | Neuronas |
|---|---:|
| DNp09 | 2 |
| DNa01 | 2 |
| DNa02 | 2 |
| DNg13 | 2 |
| MDN | 4 |
| DNp01 | 2 |
| DNp07 | 2 |
| DNp10 | 2 |
| DNp15 | 2 |
| pIP10 | 2 |
| DNg11 | 6 |
| DNg12 | 42 |
| DN_all | 1314 |
| MN_leg_T1 | 135 |
| MN_leg_T2 | 116 |
| MN_leg_T3 | 130 |
| MN_wing_power | 26 |
| MN_wing_steer | 41 |
| MN_haltere | 16 |
| MN_neck | 44 |
| MN9 | 2 |
| MN_feeding | 66 |
| MN_all | 576 |
| ORN | 248 |
| JO_AB | 138 |
| antennal_mech | 73 |
| GRN_labellar | 223 |
| GRN_pharyngeal | 48 |
| GRN_leg | 570 |
| MBON | 97 |
| DAN | 124 |

Signos: acetilcolina, dopamina, serotonina y octopamina excitan; GABA, glutamato e histamina
inhiben; desconocido excita (simplificación de nfly). **El cableado no se modifica nunca.**
