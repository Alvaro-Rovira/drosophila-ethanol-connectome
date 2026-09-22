# Quién decide lo que hace la mosca

Todo lo que hace la mosca sale de sus 20.000 neuronas reales. No hay intenciones programadas, ni
eventos al azar, ni efectos del alcohol sobre el cuerpo. Este documento dice, para cada conducta,
qué neuronas la producen y cómo se ha comprobado. (La versión anterior, de 8.000 neuronas, está en
la historia del repositorio; sus números se comparan al final.)

## Qué se añadió al pasar de 8.000 a 20.000

| Bloque | Neuronas | Para qué |
|---|---:|---|
| Todos los receptores olfativos (53 glomérulos) | 2.635 | Cada sustancia huele distinto: su mezcla de glomérulos |
| Lóbulo antenal (proyección y locales) | 1.142 | Segundo relevo del olor; conserva la diferencia izquierda/derecha |
| Cuerno lateral | 900 | Olor innato |
| Cuerpo fungiforme: células de Kenyon, APL, MBON, dopaminérgicas | 2.000 + 101 (+ dopaminérgicas en su cupo) | Aprendizaje |
| Complejo central | 1.500 | Brújula y control del rumbo |
| Neurosecretoras, entéricas y sus socias | 571 | Estado interno |
| Propioceptores de patas y halterios | 700 | Sustituyen a la propiocepción arbitraria de la versión de 8.000 |
| Todas las monoaminérgicas del cerebro central | 507 | Más dianas reales para el etanol |
| Socios de las identificadas, vías y premotoras, ampliados | +2.000 | MDN, patas, fibra gigante |

1.319.744 conexiones de ≥ 3 sinapsis; un paso del cerebro tarda ~0,9 ms. La red sigue estable con la
misma ganancia (G = 1,25; 0,08 % de neuronas saturadas sin entrada).

## Cada conducta y sus neuronas

| Conducta | Neuronas que la producen | Cómo se ha comprobado |
|---|---|---|
| **Beber** | MN9 (motoneurona de la probóscide). Si supera el umbral, extiende la probóscide; mientras está sobre la gota, no anda. | Silenciar MN9 → no bebe nunca (test). |
| **Aceptar o rechazar** | Gustativas del labelo y la faringe. Las «dulces» excitan a MN9 y las «amargas» la frenan, en el propio cableado. | Cerveza: MN9 a 3,0 veces su reposo → bebe. Garrafón: 0,48 → rechaza. Umbral 1,21. |
| **Hambre y saciedad** | Las mismas gustativas, con su ganancia cambiada por el hambre (ver abajo). MN9 decide. | Hambrienta: 5,7 s de sorbo en 6 s. Saciada: 0 s (test). |
| **Escapar** | Órgano de Johnston → fibra gigante (DNp01). | Un golpe sube la fibra gigante de 0 a ~330 veces su media. Silenciarla → no escapa (test). |
| **Mantenerse en pie** | Motoneuronas de las seis patas: si su tono medio baja del 55 % del sobrio durante 0,3 s, cae. | Silenciarlas → cae y no se levanta (test). Sobria, el tono nunca baja del 86 %. |
| **Sedación (LORR)** | Las mismas: en el suelo sin poder enderezarse durante 3 s. | Aparece sola a partir de ~0,7 de etanol. |
| **Velocidad** | El tono de las patas limita la velocidad real. | Cerebro en silencio → no se mueve (test). |
| **Rumbo y paso** | «Volante» lineal sobre 1.536 neuronas que no reciben entrada sensorial directa: 512 descendentes, las neuronas de proyección del lóbulo antenal, las MBON y otras centrales. Única pieza entrenada. | Con el mismo volante sobre el cerebro mezclado no encuentra ni una gota. |
| **Retroceder al chocar** | El mismo volante, a partir de lo que el tacto antenal provoca en la población. | 100 %, y ahora **se pierde al mezclar el cableado** (0 %). |
| **Aprender** | Sinapsis célula de Kenyon → MBON, deprimidas por la dopamina de su compartimento. | La respuesta de las MBON al olor entrenado baja un 17 % (test: solo cambian esas sinapsis). |

Umbrales: ninguno está puesto a mano. `scripts/calibrate_motor.py` los coloca entre dos respuestas
neuronales medidas en la mosca sobria y los guarda en `artifacts/motor.json` junto a las medidas.
Cada vez que se recalculan las normas (`train.py norms`) hay que recalibrar.

## Entradas

- **Olfato por glomérulo.** Cada sustancia tiene su mezcla (`configs/alcohol.yaml`): un componente
  común de fruta fermentada / vinagre (DM1, DM4, VA2, DP1m; Semmelhack y Wang 2009) y uno propio
  inventado. El garrafón huele además por DA2 (geosmina; Stensmyr et al. 2012) y V (CO2; Suh et
  al. 2004). La concentración en cada antena activa los receptores de ese lado; los de lado
  desconocido reciben la media.
- **Gusto.** Qué tipos gustativos son dulces y cuáles amargos se decide con el propio cableado, por
  su efecto neto sobre MN9 (`artifacts/taste_split.json`).
- **Propiocepción** por propioceptores reales: los de las patas (cordotonales, campaniformes, placas
  de pelos) codifican la velocidad de marcha solo mientras la mosca pisa el suelo; los de los
  halterios, el giro.
- **Brújula**: la orientación entra por las E-PG como un bulto sobre su glomérulo del puente
  protocerebral. SIMPLIFICACIÓN: sin visión, se inyecta ahí directamente.
- **Vigilia**: una corriente tónica constante a las monoaminérgicas (ARBITRARIO, declarado).

## Hambre

Se comprobó en el conectoma: las neuronas entéricas y las sensoras de nutrientes (IPC, DH44) **no
tienen camino sináptico a MN9** (efecto medido: 0 %). En la mosca real el hambre actúa por hormonas y
neuromoduladores que suben la sensibilidad de las gustativas dulces y bajan la de las amargas
(Inagaki et al. 2012, 2014). Así se modela (`src/mosca/gut.py`):

- beber llena el buche; el buche se vacía y sube el azúcar en hemolinfa; el azúcar se consume
  (acelerado, como el etanol);
- saciedad = azúcar en hemolinfa + estiramiento del buche (Gelperin 1971, en la moscarda);
- ganancia de las gustativas dulces: ×1,4 hambrienta, ×0,2 saciada; amargas: ×0,8 y ×1,2.

El extremo saciado se colocó midiendo MN9: con ganancia 0,2, MN9 con cerveza queda por debajo de su
umbral (0,48 frente a 0,68 antes de recalibrar), como la extensión de la probóscide a azúcar medio
en moscas alimentadas. En alimentación libre, la mosca bebe 13,9 s el primer minuto y 2,3 s el
segundo.

## Células de Kenyon y aprendizaje

- Las células de Kenyon tienen un umbral alto (reciben −0,9 de corriente basal): solo disparan con
  varias entradas a la vez (Turner et al. 2008). Así responde ~9 % a cada olor, como en la mosca
  real (con umbral 0 respondía el 98 %).
- Aprendizaje (`Brain.enable_plasticity`): una sinapsis célula de Kenyon → MBON se deprime cuando la
  célula de Kenyon está activa **y** las dopaminérgicas que inervan esa MBON disparan por encima de
  su propio nivel reciente; se recupera en ~10 min (Hige et al. 2015). Es el único cambio de cableado
  permitido y solo está activo en la consola en directo.
- Medido (`scripts/evaluate.py extra`): tras tres emparejamientos del olor de la cerveza con azúcar
  y una subida de etanol, la respuesta de las MBON al olor de la cerveza baja un 17 %, y la de los
  demás olores un 15 %: **generaliza**, porque todos comparten el componente fermentado. No se ha
  demostrado un cambio de preferencia en la conducta.

## Qué hace el alcohol

Entra bebiendo (buche → hemolinfa) o por **vapor**, como en el inebriómetro o el ensayo de LORR del
laboratorio. **Solo** cambia cómo transmiten las neuronas, por neurotransmisor
(`configs/alcohol.yaml`, curvas sin cambios respecto a la versión de 8.000).

Nivel congelado, 24 moscas por nivel, 40 s:

| Etanol | Velocidad | Giro por distancia | En el suelo | LORR | Encuentra y bebe |
|---:|---:|---:|---:|---:|---:|
| 0 | 34,9 | 0,052 | 0 % | 0 % | 100 % |
| 0,15 | 41,2 | 0,036 | 0 % | 0 % | 100 % |
| 0,3 | 40,3 | 0,036 | 0 % | 0 % | 79 % |
| 0,45 | **52,8** | 0,043 | 0 % | 0 % | 33 % |
| 0,6 | 50,1 | 0,052 | 0 % | 0 % | 13 % |
| 0,75 | 1,5 | 0,048 | **95 %** | **88 %** | 0 % |
| 0,9 | 0,2 | – | 99 % | 92 % | 0 % |
| 1,0 | 0,1 | – | 99 % | 92 % | 0 % |

Tono medio de las patas (× sobrio, 8 moscas, 30 s): 1,07 a 0 · 1,16 a 0,3 · 0,79 a 0,5 · 0,73 a 0,6 ·
0,64 a 0,67 · **0,49 a 0,7** · 0,31 a 0,72 · 0,19 a 0,75.

- **Hiperactividad** de 0,15 a 0,6, con el máximo a 0,45 (+51 %).
- **Pérdida de tono** progresiva de las patas desde 0,5, y **colapso** entre 0,67 y 0,7: caída y
  pérdida del reflejo de enderezamiento.
- **La búsqueda de comida se degrada** desde 0,3 (79 % → 0 %).
- **Diferencia con la versión de 8.000:** allí el giro por distancia se multiplicaba por 2-4 entre
  0,45 y 0,6 (ataxia de giro). Con 20.000 neuronas **no aparece**: el giro apenas cambia. No se han
  retocado las curvas del etanol para forzarlo.
- **Bebiendo, la mosca se sacia antes de emborracharse.** En el protocolo solo con bebidas, la mitad
  de las moscas se quedaba en 0,06. Por eso el protocolo automático tiene dos fases: ingesta
  voluntaria (0-60 s) y pulsos de vapor de 20 s (70-245 s). Con él, 8 de 8 moscas llegan a LORR
  (entre 130 y 240 s).

## Prueba final (semillas que el modelo no ha visto)

`scripts/evaluate.py tasks --test`: 40 pruebas por tarea.

| Tarea | 20.000 real | 20.000 mezclado | 8.000 real | 8.000 mezclado |
|---|---:|---:|---:|---:|
| Encuentra una gota por el olor y bebe (≤ 25 s) | **100 %** | **0 %** | 92,5 % | 0 % |
| Rechaza el garrafón | **100 %** | **0 %** | 100 % | 0 % |
| Retrocede al chocar con el borde | **100 %** | **0 %** | 100 % | 100 % |
| Acepta la cerveza | 100 % | 100 % | 100 % | 100 % |
| Escapa al golpe | 100 % | 100 % | 100 % | 100 % |
| Se cae estando sobria | 0 % | 0 % | 0 % | 0 % |
| Anda (fracción del tiempo) | 89 % | 100 % | 92 % | 100 % |

El cerebro mezclado conserva cuántas conexiones tiene cada neurona, su peso y su signo; solo baraja
quién conecta con quién. Con 20.000 neuronas, tres conductas dependen de la topología (antes, dos).
Aceptar lo dulce y escapar siguen sin demostrar nada sobre el conectoma.

## Lo que no sale bien y por qué

- **MDN** responde algo más al choque (0,98 → 1,18 veces su media; antes 1,01 → 1,09), pero
  silenciarla no impide retroceder: la marcha atrás la sigue produciendo el volante.
- **Sin vuelo sostenido.** Las motoneuronas de potencia del vuelo no suben tras el escape (1,06
  frente a 1,12 en reposo), así que el despegue es un salto.
- **Lateralización olfativa débil.** La diferencia izquierda/derecha llega a las neuronas de
  proyección (~5 %) pero casi no a las descendentes de giro. Con los 1.024 rasgos de la versión de
  8.000 el volante solo encontraba la comida el 58 % de las veces; por eso lee también las neuronas
  de proyección y las MBON.
- **MN9 sube con el tacto antenal** en este subcircuito. Sin gota debajo no hay sorbo, pero la traza
  lo muestra.
- El aprendizaje **generaliza** entre olores parecidos y no se ha demostrado un cambio de conducta.

## Ficción

La arena, las sustancias, sus olores y recetas, la velocidad de eliminación del etanol y del azúcar,
la escala del vapor y el lavado.
