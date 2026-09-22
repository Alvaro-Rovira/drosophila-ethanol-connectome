# Subcircuito de 20.000 neuronas

**N = 20,000** neuronas reales de MaleCNS v1.0 · **1,319,744 conexiones** (>= 3 sinapsis).

## Por qué se eligieron así

La selección anterior (entradas sensoriales -> descendentes en <= 3 saltos) no tenía **ninguna**
motoneurona, ni MDN, ni la fibra gigante, ni DNp09, ni receptores olfativos. Esas neuronas no
podían mover las patas, así que un guion tenía que hacerlo. Ahora se eligen por cupos de función
para que estén las que perciben, las que deciden y las que mueven, y los circuitos completos del
olfato, el cuerpo fungiforme, el complejo central y el estado interno.

| Cupo | Neuronas |
|---|---:|
| anclas | 696 |
| descendentes | 1,244 |
| sensoriales | 3,117 |
| gusto_pata | 300 |
| propioceptores_pata | 600 |
| propioceptores_halterio | 100 |
| monoaminergicas | 507 |
| lobulo_antenal | 1,142 |
| cuerno_lateral | 900 |
| cuerpo_fungiforme | 101 |
| celulas_de_Kenyon | 2,000 |
| complejo_central | 1,500 |
| estado_interno | 171 |
| socios_estado_interno | 400 |
| socios_de_anclas | 2,000 |
| via_olfato_giro | 300 |
| via_gusto_MN9 | 300 |
| via_gusto_pata | 300 |
| via_tacto_MDN | 300 |
| via_vibracion_GF | 300 |
| via_descendentes_patas | 300 |
| premotoras | 2,000 |
| relleno | 1,422 |

| Clase | Neuronas |
|---|---:|
| descending | 1,314 |
| inter | 13,167 |
| modulatory | 446 |
| motor | 624 |
| sensory | 4,449 |

Inhibitorias (GABA, glutamato, histamina): 29.4%.

## Comprobaciones

- Descendentes que reciben señal de los sensores en <= 4 saltos: **99.9%**.
- Motoneuronas que la reciben: **100.0%**.
- Componente conexa dominante: **99.6%** de las neuronas.
- Neuronas identificadas aisladas: **0**.
- 96 neuronas obligatorias sin ninguna arista de >= 3 sinapsis dentro recuperan sus aristas reales de >= 2 sinapsis (no se inventa ninguna).

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
| MN_all | 575 |
| ORN | 2635 |
| JO_AB | 138 |
| antennal_mech | 73 |
| GRN_labellar | 223 |
| GRN_pharyngeal | 48 |
| GRN_leg | 375 |
| MBON | 97 |
| DAN | 354 |
| ALPN | 686 |
| ALLN | 458 |
| LH | 926 |
| KC | 2000 |
| APL | 2 |
| CX | 1599 |
| EPG | 50 |
| ENDO | 94 |
| NUTRIENT | 22 |
| ENS | 50 |
| SEZPN | 27 |
| PROP_leg | 624 |
| PROP_haltere | 103 |

Signos: acetilcolina, dopamina, serotonina y octopamina excitan; GABA, glutamato e histamina
inhiben; desconocido excita (simplificación de nfly). **El cableado no se modifica nunca.**
