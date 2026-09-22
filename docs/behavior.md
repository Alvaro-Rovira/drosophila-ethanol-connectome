# Quién decide lo que hace la mosca

Todo lo que hace la mosca sale de sus 8.000 neuronas reales. No hay intenciones programadas, ni
eventos al azar (hipo, peonza, tropiezo…), ni efectos del alcohol sobre el cuerpo. Este documento
dice, para cada conducta, qué neuronas la producen y cómo se ha comprobado.

## Cada conducta y sus neuronas

| Conducta | Neuronas que la producen | Cómo se ha comprobado |
|---|---|---|
| **Beber** | MN9 (motoneurona de la probóscide). Si su tasa supera el umbral, extiende la probóscide; mientras la tiene sobre la gota, no anda. | Silenciar MN9 → no bebe nunca (test). |
| **Aceptar o rechazar** | Las gustativas del labelo y la faringe. Las «dulces» excitan a MN9 y las «amargas» la frenan, **en el propio cableado**. | Cerveza, vino y licor: MN9 a ~0,9 veces su reposo → bebe. Tequila y garrafón: 0,5-0,6 → rechaza tras un sorbo de prueba de <0,3 s. |
| **Escapar** | Órgano de Johnston → fibra gigante (DNp01). | Un golpe en la mesa sube la fibra gigante de ~3 a ~400 veces su reposo. Silenciarla → no escapa (test). |
| **Mantenerse en pie** | Las motoneuronas de las seis patas. Si su tono medio baja del 55% del sobrio durante 0,3 s, las patas no la sostienen y cae. | Silenciarlas → se cae y no se levanta (test). Sobria, el tono nunca baja del 73%. |
| **Sedación** | Las mismas: caída y sin tono para enderezarse durante 3 s = pérdida del reflejo de enderezamiento, como se mide en moscas de laboratorio. | Aparece sola a partir de un nivel de alcohol de ~0,75. |
| **Velocidad** | El tono de las patas limita la velocidad real: las patas solo se mueven lo que sus motoneuronas las mueven. | Cerebro en silencio → la mosca no se mueve (test). |
| **Rumbo y paso** | Un «volante» lineal que lee 1.024 neuronas que **no** reciben la entrada sensorial directa (descendentes y las más conectadas). Es la única pieza entrenada. | Con el mismo volante sobre el cerebro mezclado no encuentra ni un charco. |
| **Retroceder al chocar** | El mismo volante, a partir de lo que el tacto antenal provoca en la población. | 100%, pero **sobrevive al mezclado**: no es prueba del cableado. |

Umbrales: ninguno está puesto a mano. `scripts/calibrate_motor.py` los coloca entre dos respuestas
neuronales medidas en la mosca sobria (p. ej. MN9 con cerveza frente a MN9 con garrafón) y los
guarda en `artifacts/motor.json` junto a las medidas.

## Qué hace el alcohol

El alcohol **solo** cambia cómo transmiten las neuronas, por neurotransmisor (`configs/alcohol.yaml`):

- monoaminas (octopamina, dopamina, serotonina): suben con poca dosis y bajan con mucha;
- transmisión excitadora (acetilcolina): se deprime a dosis altas;
- transmisión inhibidora (GABA, glutamato, histamina): algo de desinhibición al principio,
  potenciación a dosis altas;
- ruido sináptico multiplicativo de media cero y retraso de los sentidos;
- el olfato pierde sensibilidad.

Lo que sale de ahí, medido con el nivel de alcohol congelado (24 moscas por nivel, 40 s):

| Alcohol | Velocidad | Giro por distancia | En el suelo | Sedada | Encuentra y bebe |
|---:|---:|---:|---:|---:|---:|
| 0 | 39,5 | 0,050 | 0% | 0% | 92% |
| 0,15 | 44,8 | 0,038 | 0% | 0% | 71% |
| 0,3 | **74,2** | 0,032 | 0% | 0% | 25% |
| 0,45 | 27,0 | **0,112** | 0% | 0% | 0% |
| 0,6 | 16,8 | **0,223** | 0% | 0% | 0% |
| 0,75 | 1,2 | 0,361 | **83%** | **69%** | 0% |
| 0,9 | 0,1 | – | 99% | 92% | 0% |
| 1,0 | 0,0 | – | 99% | 92% | 0% |

- **Hiperactividad** con poca dosis: casi el doble de velocidad a 0,3.
- **Ataxia**: el giro por distancia se multiplica por 2-4 y deja de encontrar las copas.
- **Caída y sedación**: a partir de ~0,75 las patas pierden tono, se cae y no puede levantarse.
- Efecto emergente que no se programó: **la borrachera se autolimita**. Muy bebida ya no atina con
  las copas, así que deja de beber. En la demo (`scripts/run_demo.py`, copas a 22-60 unidades),
  8 de 8 moscas llegan a «borracha» y 2 de 8 a caerse sin poder levantarse en 5 minutos.

## Prueba final (semillas que el modelo no ha visto)

`scripts/evaluate.py tasks --test`: 40 pruebas por tarea.

| Tarea | Cerebro real | Cerebro mezclado |
|---|---:|---:|
| Encuentra un charco por el olor y bebe (≤ 25 s) | **92,5%** | **0%** |
| Rechaza el garrafón | **100%** | **0%** |
| Acepta la cerveza | 100% | 100% |
| Escapa al golpe en la mesa | 100% | 100% |
| Retrocede al chocar con el borde | 100% | 100% |
| Se cae estando sobria | 0% | 0% |
| Anda (fracción del tiempo) | 92% | 100% |

El cerebro mezclado conserva exactamente cuántas conexiones tiene cada neurona, su peso y su signo;
solo baraja quién conecta con quién. Donde el real y el mezclado empatan (aceptar, escapar,
retroceder), esa conducta no demuestra nada sobre el conectoma: le basta con que llegue mucha
corriente.

## Lo que no sale bien y por qué

- **MDN** (la neurona de marcha atrás de la literatura) apenas responde al tacto de la pared en
  este subcircuito: 1,01 veces su reposo antes del choque, 1,09 después. Por eso la marcha atrás
  la saca el volante de la población, no MDN.
- La **lateralización olfativa** hacia las descendentes de giro (DNa02) es casi nula: huela por la
  antena izquierda o por la derecha, DNa02 responde parecido. Por eso el rumbo necesita el volante
  entrenado y no sale de DNa02 sola.
- **Anda casi todo el tiempo** (92%): la mosca real hace más pausas. No se ha añadido ninguna regla
  para que pare.

## Entradas arbitrarias (declaradas)

- La propia velocidad, giro y altura de la mosca entran en otras neuronas sensoriales con una
  semilla fija: no hay propioceptores identificados para ello en el subcircuito.
- Una corriente tónica constante a las neuronas monoaminérgicas la mantiene despierta.
- Qué gustativas son «dulces» y cuáles «amargas» se decide una vez con el propio cableado (por su
  efecto neto sobre MN9), porque la anotación trae el órgano pero no el sabor.

## Ficción

La mesa, las bebidas y su receta, lo rápido que se elimina el alcohol (acelerado para que se vea en
minutos) y la ducha fría.
