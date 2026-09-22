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
| **Rumbo y paso** | «Volante» lineal y **simétrico** sobre 1.536 neuronas que no reciben entrada sensorial directa: 512 descendentes, las neuronas de proyección del lóbulo antenal, las MBON y otras centrales. El giro sale solo de diferencias izquierda − derecha de neuronas homólogas. Única pieza entrenada. | Con el mismo volante sobre el cerebro mezclado no encuentra ni una gota. |
| **Retroceder al chocar** | El mismo volante, a partir de lo que el tacto antenal provoca en la población, con participación de MDN. | 100 %; sin MDN, 31 %. Sobrevive al cableado mezclado. |
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
en moscas alimentadas. En alimentación libre, la mosca bebe 8,1 s el primer minuto y 1,7 s el
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
| 0 | 37,6 | 0,036 | 0 % | 0 % | 96 % |
| 0,15 | 41,6 | 0,028 | 0 % | 0 % | 88 % |
| 0,3 | **64,3** | 0,034 | 0 % | 0 % | 0 % |
| 0,45 | 57,3 | 0,035 | 0 % | 0 % | 25 % |
| 0,6 | 48,5 | 0,044 | 0 % | 0 % | 13 % |
| 0,75 | 1,4 | 0,071 | **96 %** | **89 %** | 0 % |
| 0,9 | 0,1 | – | 99 % | 92 % | 0 % |
| 1,0 | 0,1 | – | 99 % | 92 % | 0 % |

Tono medio de las patas (× sobrio, 8 moscas, 30 s): 1,01 a 0 · 1,00 a 0,3 · 0,84 a 0,5 · 0,76 a 0,6 ·
0,66 a 0,64 · 0,58 a 0,67 · **0,21 a 0,7** · 0,17 a 0,75. (El tono depende algo del volante, porque
los propioceptores de las patas codifican la velocidad a la que anda.)

- **Hiperactividad** de 0,15 a 0,6, con el máximo a 0,3 (+71 %).
- **Pérdida de tono** progresiva de las patas desde 0,5, y **colapso** entre 0,67 y 0,7: caída y
  pérdida del reflejo de enderezamiento.
- **La búsqueda de comida se degrada** desde 0,15 (88 % → 0-25 %).
- **Diferencia con la versión de 8.000:** allí el giro por distancia se multiplicaba por 2-4 entre
  0,45 y 0,6 («ataxia de giro»). Con 20.000 neuronas y el volante simétrico **no aparece**. Tras el
  fallo de las vueltas (abajo), aquel aumento de giro era probablemente un artefacto del volante sin
  simetría, no una ataxia real. No se han retocado las curvas del etanol para forzarlo.
- **Bebiendo, la mosca se sacia antes de emborracharse.** En el protocolo solo con bebidas, la mitad
  de las moscas se quedaba en 0,06. Por eso el protocolo automático tiene dos fases: ingesta
  voluntaria (0-60 s) y pulsos de vapor de 20 s (70-245 s). Con él, 8 de 8 moscas llegan a LORR
  (entre 180 y 235 s).

## Prueba final (semillas que el modelo no ha visto)

`scripts/evaluate.py tasks --test`: 40 pruebas por tarea.

| Tarea | 20.000 real | 20.000 mezclado | 8.000 real | 8.000 mezclado |
|---|---:|---:|---:|---:|
| Encuentra una gota por el olor y bebe (≤ 25 s) | **95 %** | **0 %** | 92,5 % | 0 % |
| Rechaza el garrafón | **100 %** | **0 %** | 100 % | 0 % |
| Retrocede al chocar con el borde | 100 % | 100 % | 100 % | 100 % |
| Acepta la cerveza | 100 % | 100 % | 100 % | 100 % |
| Escapa al golpe | 100 % | 100 % | 100 % | 100 % |
| Se cae estando sobria | 0 % | 0 % | 0 % | 0 % |
| Anda (fracción del tiempo) | 88 % | 94 % | 92 % | 100 % |

El cerebro mezclado conserva cuántas conexiones tiene cada neurona, su peso y su signo; solo baraja
quién conecta con quién. Dos conductas dependen de la topología: buscar por el olor y rechazar el
amargo. Aceptar lo dulce, escapar y retroceder no demuestran nada sobre el conectoma. (Con el primer
volante de 20.000 la marcha atrás también se perdía al mezclar; con el volante simétrico, no.)

## El fallo de las vueltas sobre sí misma (22-09-2026)

**Síntoma.** Con garrafón, tequila o licor en la arena, o con etanol en el cuerpo, la mosca se quedaba
girando a 5 rad/s (el máximo) sin parar. Esto pasaba en la simulación, no en el dibujo 3D.

**Causas.**
1. El volante solo se había entrenado con olor a cerveza y vino. Los olores nuevos (DA2, V, DC3,
   DM2…) sacaban su salida lineal del rango de entrenamiento.
2. El etanol cambia la actividad de todo el cerebro a la vez. Un volante lineal sin restricciones
   convertía ese cambio global en un giro constante a un lado: con 0,3 de etanol, 0,68 de giro medio
   aportado por descendentes y motoneuronas que se desplazaban en bloque.
3. El subcircuito no es simétrico: 883 receptores olfativos anotados a la izquierda y 1.343 a la
   derecha. El etanol amplifica esa asimetría.

**Qué se probó y no bastó.**
- Más regularización: sin vueltas, pero la mosca solo encontraba la comida el 40-50 % de las veces.
- Acotar las entradas a ±3 DE: seguía saturado el 30-60 % del tiempo.
- Volante simétrico solo: desaparece el sesgo global, pero la asimetría del subcircuito seguía
  produciendo giros sostenidos.

**Arreglo** (`src/mosca/readout.py`, `scripts/train.py`):
- entrenamiento con las cinco sustancias, solas y mezcladas;
- volante **simétrico**: el giro sale de diferencias izquierda − derecha de 495 tipos homólogos, y la
  velocidad de las sumas;
- entradas acotadas a ±3 DE;
- **adaptación lenta del giro** (τ = 3 s), como en cualquier orden motora sostenida;
- regularización elegida por alcance − episodios con vueltas con etanol 0,3/0,5.

**Nunca se entrena con moscas borrachas**: eso enseñaría al volante a compensar el etanol.

**Revisión de todo el programa** (`scripts/stress.py` → `artifacts/stress.json`): 15 escenarios × 6
moscas, con el objeto en directo tal como lo ejecuta el servidor:
- cada sustancia, mezcla, etanol 0,3, 0,5 y 0,65;
- saciada, esquina, golpes cada 3 s, vapor 60 s, caída a 0,85 con lavado, y protocolo completo de 4 min.

| Comprobación | Resultado |
|---|---|
| Moscas que dan vueltas sobre sí (> 1,5 s girando al máximo al mismo lado) | **0 de 90** |
| Racha más larga girando al máximo | 1,1 s |
| Valores no finitos, salidas de la arena | 0 |
| Neuronas en el techo del modelo | ≤ 2,7 % |
| Bloqueo más largo de pie, sin beber y sin anestesiar | 4,2 s |
| Coste por paso del programa entero | ~1,5 ms |
| Aprendizaje extremo (sinapsis KC→MBON al 5 %) | sin vueltas |

**Coste del arreglo.** La búsqueda de comida baja del 100 % al 95 %. La marcha atrás deja de depender
de la topología, pero pasa a depender en parte de MDN (sin MDN, 31 %).

## Lo que no sale bien y por qué

- **MDN** responde poco al choque (0,98 → 1,18 veces su media; antes 1,01 → 1,09). Silenciarla baja
  la marcha atrás del 100 % al 31 %: participa, pero no es la única vía.
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
