# Variantes de locomoción para jugador y NPC T900S

Fecha: 2026-10-11.

## Comportamiento

Enhanced Units declara estos tres pares independientes en su archivo raíz
`T3/mods/t3_enhanced_units/anm_variants.json`:

| Estado | Original | Alternativa |
| --- | --- | --- |
| Idle | `t900_idle_wm20.anm` | `t900_idle_wm20_alt01.anm` |
| Run | `t900_run_wm20.anm` | `t900_run_wm20_alt01.anm` |
| Walk | `t900_walk_wm20.anm` | `t900_walk_wm20_alt01.anm` |

**Regla vigente, por decisión del usuario:** el jugador y los NPC **sin alerta**
pueden usar alternativas. Los NPC que detectan un enemigo regresan al original de su mismo
estado, incluso si una alternativa ya estaba reproduciéndose. La transición
usa CrossFade del motor; idle, walk y run no se intercambian.

**CONFIRMED por pruebas nativas:** al entrar en caminar o correr, un actor elegible
selecciona su original o su alternativa con probabilidad aproximada de 50 %.
La elección se conserva mientras siga en el mismo estado, incluidos sus loops.
Puede repetirse la misma elección en varias entradas consecutivas. Idle, walk
y run conservan sus identificadores y nunca se intercambian entre sí. Al detenerse,
idle hereda la elección de la animación de caminar/correr: alternativa → idle_alt01;
normal → idle normal. Si no hay una locomoción previa vinculada, idle usa el sorteo.
Durante un CrossFade se toma su destino. Para NPC, la alerta prevalece sobre
esta continuidad y exige el original.

Después de un disparo primario o secundario, el regreso a idle siempre selecciona
el normal, apuntando al frente. No se sortea una nueva postura entre disparos.
Una nueva secuencia de caminar/correr y detenerse puede volver a heredar alternativas.

El selector comprueba pertenencia al array de actores y un human válido. Si hay
un agente AI asociado, consulta su alerta; un actor sin agente AI también puede
seleccionar alternativas, lo que incluye al jugador. No cambia el control vertical
del jugador. Multijugador no está validado: sin una IA local no hay una señal
de alerta remota disponible para este selector.

## Compilación y alcance

Usar **Compilar Mods + EXE modificado**. Reabrir ModTools si estaba abierto
antes de actualizar sus módulos Python. El paquete y el ejecutable se generan
juntos mediante la transacción existente de `build_all`.

El compilador toma la biblioteca ganadora `ca/casts/t900s/tps/anim.lib`, copia
las entradas de cada archivo base y añade una entrada por alternativa con el
**mismo Name, Len y demás metadatos**, cambiando únicamente File. Conserva las
entradas originales primero y actualiza AnimNum. El motor admite varias entradas
con el mismo estado; su búsqueda normal sigue devolviendo la primera.

Con el orden actual de mods, WM32 aporta la biblioteca de 57 entradas. Sus
funciones WM20, WM27 y WM32 reutilizan los mismos archivos base WM20. Por ello
se generan nueve entradas adicionales, 66 en total: cada arma mantiene sus
propios estados idle/walk/run y recibe los tres pares. No se cambia la biblioteca
fuente de ningún mod; el resultado se escribe únicamente en Mods.Cod.

Las alternativas participan también en el análisis automático de joints. Las
variantes run/walk reciben las reglas de composición de apuntado correspondientes
a spinebone2, spinebone3 y head; la variante idle conserva los joints originales.
No se reescriben los ANM. Si una variante no cumple el perfil compatible, la
compilación falla antes de instalar un conjunto incompleto.

Para desactivar las variantes, retirar `anm_variants.json` y recompilar, o
deshabilitar Enhanced Units y recompilar. No basta con retirar el archivo de
configuración después de generar el ejecutable.

## Configuración

Formato 1; actualmente se admite la biblioteca T900S TPS verificada. Cada par
contiene rutas internas completas `base` y `alternative`. Debe existir el ANM
alternativo entre los archivos ganadores de los mods habilitados, y el base
debe estar referenciado por funciones HAND_*_IDLE, HAND_*_WALK o HAND_*_RUNNING.
Los pares son explícitos: el sufijo `_alt01` por sí solo no registra nada.

No hay un ajuste de probabilidad en este formato: el selector usa una decisión
binaria aproximadamente uniforme cuando no está heredando el idle.
`chance_percent: 50` en el informe describe ese sorteo, no las transiciones de
idle con continuidad. Se admiten hasta 32 pares; las rutas deben ser ASCII y caber
en el campo nativo de nombre del ANM.

El informe `T3/modtools_data/.compiled/anm_compatibility.json` registra los pares,
las entradas de configuración con sus hashes, las bibliotecas generadas y las
reglas de joints. Cambios en las entradas durante la compilación provocan
rollback del conjunto generado.

## Evidencia nativa y ABI

Referencias: símbolos de T3.pdb y Ai.pdb, desensamblado de los binarios originales
y pruebas con Unicorn que ejecutan las funciones originales de T3.exe.

| Punto | Dirección virtual | Uso |
| --- | --- | --- |
| cBoneController::LoadLib | `0x542D20` | Registros de 0xA8 bytes; Name se resuelve a estado |
| SearchAnimByState | `0x543440` | Devuelve la primera entrada del estado solicitado |
| CrossFade lookup | `0x54382A` | CALL sustituido; continuación `0x54382F` |
| StartPlay lookup | `0x5432F0` | CALL sustituido; continuación `0x5432F5` |
| Animate_UpperBody | `0x489CFB` | Evita reseleccionar cuando el estado no cambia |
| Llamada de locomoción | `0x489D15` | Retorno `0x489D1A`, canal 2 |

Anchors completos conservan las instrucciones después de cada CALL:

- CrossFade: `E8 11 FC FF FF 8B D0 83 FA FF`.
- StartPlay: `E8 4B 01 00 00 8B F8 83 FF FF`.

El wrapper ejecuta primero SearchAnimByState original. Filtra por la llamada de
locomoción, canal 2, esqueleto de 32 huesos y pertenencia exacta al array de
actores (64 slots, stride 0x14108, bones en actor+0xD0). CrossFade de duración cero
delega a StartPlay: esa ruta solo se acepta con retorno padre 0x54381B y retorno
exterior 0x489D1A. Las otras llamadas permanecen en la ruta normal.

Se busca A2.dll y, si no está cargada, Ai.dll mediante GetModuleHandleA de la IAT
0x62F1B4. La raíz AI en módulo+0x160BD0 conduce a equipos (+0x788) y agentes;
playerinfo+0x48 debe coincidir con el human del actor (+0x1405C). Las listas tienen
comprobaciones de null y un presupuesto conjunto de 128 nodos.

La alternativa debe coincidir en **ruta configurada y estado nativo**. La decisión
usa un hash entero del tiempo del motor, identidad del actor y estado; no altera
el RNG del juego. Preserva registros, flags y la limpieza de pila `ret 4`, y
solo cambia el índice devuelto. No escribe en registros de animaciones ni en
variables del controlador.

Código, tabla y cadenas residen en la sección RX `.t3ldr`, propiedad del loader.
No se reserva estado mutable ni se buscan huecos libres en el binario original.
Se validan hashes completos, anchors únicos y propiedad de cada escritura antes
de aplicar el parche. Perfiles originales:

- T3.exe: `52f68d5df4912aba662f0371a06ae0b1ec447ef4b7338460224b20904eb0f061`.
- Ai.dll: `817ba995212c4daed24c5205bfbbe575ff9f28a6ddcc4fc494141d73934d66ae`.

## Verificación

Suite completa: **243 pruebas, sin fallos, 11 omitidas**. Las nueve pruebas de
`test_anm_npc_variants.py` cubren separación de estados, jugador, canales ajenos,
llamadas ajenas, alternativa ausente o de otro estado, ABI, persistencia de la
elección, rutas nativas CrossFade/StartPlay, compilación, desactivación y rollback.
En 400 selecciones por estado se eligieron 207, 200 y 207 alternativas.

La evidencia de compilación y hashes se guarda en
`output/anm_npc_variants_20261011/release_verification.json`, junto al inventario
`inputs_before.json` y el script reproducible `build_and_verify.py`. Estos archivos
permiten comprobar las nueve entradas, las dos llamadas al selector, sus destinos
en RX y la conservación de originales, ANM, bibliotecas fuente y orden de carga.

**UNKNOWN — comprobación visual en el juego pendiente.** Probar una partida nueva
con varios NPC T900S: observar idle, hacerlos caminar/correr y volver a detenerlos
varias veces. Confirmar variedad dentro de cada estado, estabilidad mientras
permanezca activo, animación original del jugador y apuntado correcto al entrar
en combate. La emulación nativa no sustituye esa observación visual.

## Corrección de postura relajada — 2026-10-11

**Histórico con error de implementación:** el signo y el alcance de esta primera
corrección fueron incorrectos. Ver «Corrección del signo y exclusión de Heavy
Assault» al final. La antigua prueba de retorno a neutral modelaba el consumidor
con un signo erróneo; sus resultados no demostraban convergencia en el motor.

**OBSERVED — usuario:** los bots usan correctamente las alternativas y el jugador
conserva las originales, pero los bots inclinan el torso hacia abajo mientras el
rifle permanece casi horizontal. La confirmación anterior de selección aleatoria
no valida la postura visual.

**CONFIRMED — captura de solo lectura:**
`output/anm_npc_variants_20261011/pose_1791699935415451800.jsonl`, 1568 muestras
válidas y cuatro descartadas por cambios durante la captura. Proceso 16328,
T3_Modded SHA-256 `472ec9a1f7eff5ec76d2d5732ff94f2df7436cfdb0990d41030ce0a521c5281e`,
A2 SHA-256 `eacae2f8ba01ed11d22745034b131faf6daf51c90b56e4906a13eebd869620cf`,
base de A2 `0x09020000`. La captura valida contra disco los dos hooks de selección
y la sección del selector/compositor antes de leer agentes.

Sin enemigo y con navegación activa, run_alt01 produjo 308 muestras con
GetUpDown medio de -0,874 radianes (unos -50 grados), mientras el rifle tenía
pitch medio de +0,39 grados. Run normal produjo 881 muestras, GetUpDown medio
-0,007 radianes y rifle +0,09 grados. La elevación de la pose estaba siendo
cancelada por la realimentación de apuntado de la IA.

**CONFIRMED — mecanismo:** Ai.pdb resuelve aiAgent::Process (0x1000DFE0,
0x149F bytes), Vector2Angles (0x1000F750), AngleDelta (0x1000FB30) y
cHumanControl::GetUpDown (0x10052CE0, lee control+0x8E8). Process convierte la
dirección mundial del arma a ángulos en 0x1000E998. Sin enemigo, la navegación
calcula una referencia casi horizontal (0x1000EDB9..0x1000EE12) y compara el
pitch del arma mediante CALL 0x1000F0E2. El delta acaba convertido a una entrada
vertical en 0x1000F1A1..0x1000F1DF. Elevar el rifle en el ANM hace que este lazo
baje GetUpDown hasta volver a horizontalizarlo. La hipótesis competidora de un
ANM incorrecto no explica que un control inicialmente neutro reciba esta orden;
la reproducción nativa demuestra el efecto con la elevación del arma como única
diferencia.

**Implementación anterior, incorrecta:** para T900S y T900HeavyAssault exactos, sin enemigo y a pie,
la llamada de pitch compara cero con el negativo de GetUpDown convertido de
radianes a grados. Se esperaba volver a neutral, pero ese signo produce
realimentación positiva y acaba alcanzando los límites de inclinación.
Incluye reposo sin navegación, para recuperar la postura después de combatir.
Con enemigo, otros casts o la ruta montada/vehículo, se ejecuta AngleDelta
original con sus argumentos originales. El jugador no pasa por este selector AI.

La referencia horizontal anterior de navegación conserva su semántica. Ambos
helpers comparten una comprobación exacta del nombre del cast y ocupan **254 bytes**
en la reserva existente `[0x10129F00, 0x1012A000)`, sin invadir Heavy spawn.
El helper de pitch empieza en `0x10129F69`. El nuevo hook sustituye únicamente
el CALL de `0x1000F0E2`; continuación `0x1000F0E7`. Anchor único:
`E8 49 0A 00 00 8A 44 24 23 83 C4 10 D9 5C 24 14`.
El código es PIC, usa constantes en pila, devuelve el delta mediante x87 y
conserva registros no volátiles y limpieza de argumentos del caller. No escribe
directamente en controles, huesos, ANM o locators.

La compilación habilita estos helpers también cuando hay variantes sin joints
añadidos, como idle. `relaxed_pitch_casts` deja constancia de los casts cubiertos
en `anm_compatibility.json`. La composición de joints y los tres pares de
variantes se mantienen.

**Pruebas:** suite de 248 casos sin fallos, 11 omitidos. Cuatro pruebas nuevas
ejecutan las instrucciones reales de Process y AngleDelta en tres bases de carga;
reproducen el error anterior con rifles elevados, verifican delta cero con look
neutral, retorno desde inclinaciones de ±1,1 radianes, ABI/x87 y exclusiones de
combate, vehículos y nombres similares. Otra prueba verifica que una variante
sin joints añadidos también active la corrección. Las regresiones previas de
navegación horizontal y selección por estado siguen pasando.

Evidencia de compilación corregida:
`output/anm_npc_variants_20261011/pose_fix/installed.json`, inventario de originales
y archivos de usuario en `inputs_before_install.json`; reproducción con
`prepare_pose_fix.py --install` (cerrar el juego antes).

Build instalado verificado: T3_Modded conserva SHA-256
`472ec9a1f7eff5ec76d2d5732ff94f2df7436cfdb0990d41030ce0a521c5281e`;
A2 pasa a `38b6cdf9e8dd20070d0568f33e2cdf6935ac73a9d7954072f6144b57697a2946`;
Mods.Cod `8f9a6a6bd2bceeddf3f5edef3e931728a3416d711d11ddebe5cbc9ad68c09eb5`.
Se verificaron originales y archivos ANM/bibliotecas fuente sin cambios, orden
de mods conservado, 66 registros de biblioteca, tres pares y seis reglas de
composición. `probe_pose.py --fixed` permite capturar la nueva partida con hashes
y bytes de código verificados, mediante PROCESS_VM_READ únicamente.

**UNKNOWN — la postura del ejecutable corregido aún requiere confirmación visual.**
Observar NPC sin enemigo en idle/run/walk alternativos, su retorno a reposo tras
combatir y, por separado, el apuntado durante combate. La selección aleatoria
ya fue observada por el usuario; la corrección de postura tiene verificación
nativa automatizada.

## Ampliación a alerta sin disparo — 2026-10-11

**Propuesta reemplazada por decisión posterior del usuario.** El comportamiento
de esta sección no es la regla vigente; se conserva como historia de investigación.

**OBSERVED — usuario:** la corrección anterior permite las poses alternativas
sin alerta. Detectar un enemigo vuelve a encorvar al bot mientras corre hacia él,
aunque todavía no dispare.

**CONFIRMED — condición demasiado amplia:** la entrada de pitch usaba
`agent+0x117` (objetivo detectado) para volver al apuntado nativo. Se sustituye
por `agent+0x116` (orden de disparar). Por tanto, detectar o perseguir un enemigo
conserva el retorno del control a neutral mientras no exista orden de disparo.
Con esa orden se recupera el cálculo nativo en ese mismo tick, tanto de pie
como en movimiento. Se usa la intención actual, no el indicador de disparo
del frame anterior, para que el primer pedido reciba apuntado nativo.

El PDB mantiene `aiAgent::Process` en 0x1000DFE0. Sus instrucciones originales
0x1000F1FD..0x1000F20B requieren ambos flags, objetivo y orden, antes de entrar
en la ruta de emisión. Las pruebas ejecutan esas instrucciones para las cuatro
combinaciones. Las escrituras de la lógica AI también distinguen los estados:
0x1001857F limpia la orden y 0x10018589 mantiene objetivo; 0x10018676 escribe
la decisión de disparar y 0x1001867F mantiene objetivo.

En el helper generado, el cambio funcional es un byte del desplazamiento del
CMP: `80 BE 17 01 00 00 00` pasa a `80 BE 16 01 00 00 00` en
0x10129F69. Se conservan sus 254 bytes, la reserva, ambos hooks, los filtros de
cast/vehículo, el selector de variantes y la referencia horizontal de navegación.
El informe añade `relaxed_pitch_condition: on_foot_without_shot_request`.

Las siete pruebas de pitch incluyen ahora alerta sin disparo con objetivos a
distintas alturas en tres bases de carga, transición alerta→primera orden de
disparo→alerta sobre el mismo actor, y la distinción nativa entre ambos flags.
Las exclusiones de vehículos y otros casts siguen devolviendo el resultado
nativo. Evidencia de build en
`output/anm_npc_variants_20261011/alert_pose_fix/installed.json`.

**UNKNOWN — verificación visual de esta ampliación pendiente.** Probar un NPC
corriendo hacia un enemigo sin disparar, comienzo del disparo y vuelta a alerta.
La confirmación visual anterior corresponde solo a la versión sin enemigo.

## Regla final: alternativas deshabilitadas en alerta — 2026-10-11

**OBSERVED — preferencia explícita del usuario:** «mejor hagamos que en modo
alerta no reproduzca sus animaciones alternativas». Sustituye la propuesta de
mantener variantes durante la persecución de un enemigo.

El selector comprueba `agent+0x117` al resolver el agente AI correspondiente al
actor. Si está en alerta, devuelve la entrada original del estado solicitado.
Para una alternativa que ya estaba activa se añade un guard en Animate_UpperBody:

- Sitio `0x489CFB`; anchor original `39 AB 38 3B 01 00 74 2F`.
- Se sustituye el CMP de seis bytes por CALL de cinco bytes y NOP; el JE de
  `0x489D01` y su destino `0x489D32` se conservan.
- El helper reproduce el CMP, guarda registros y flags. Cuando el estado es
  distinto, devuelve el resultado original sin efectuar búsquedas adicionales.
- Con el mismo estado, comprueba esqueleto, pertenencia a un agente AI, alerta,
  estado nativo del registro y ruta exacta de una alternativa configurada.
- Si coincide, limpia solo ZF del resultado guardado. Así el caller ejecuta su
  CrossFade normal hacia la entrada original sin cambiar el identificador del
  estado ni escribir índices directamente.
- Durante un crossfade consulta su destino, no la animación de origen. Cuando
  el destino ya es original deja pasar el JE nativo; no reinicia la transición.

Ambas entradas comparten una búsqueda AI acotada y no añaden estado mutable.
El guard y el selector viven en `.t3ldr` RX y sus destinos se obtienen del mismo
generador, sin direcciones fijas para la sección añadida. Las bibliotecas y ANM
fuente conservan sus datos. El jugador permanece en la ruta original.

Se restaura la política de pitch anterior (`on_foot_without_alert`), porque en
alerta ahora se utilizan las animaciones originales y su apuntado nativo. El
helper de A2 vuelve al mismo contenido de la corrección de postura previa.
`variant_condition: npc_without_alert` registra la regla en el informe. Cuando
la alerta termina, las alternativas vuelven a ser elegibles en la próxima
entrada de idle/walk/run; no se sortea una nueva variante cada frame.

Pruebas nuevas: exclusión de selección en alerta para los tres estados; salida
de alternativa activa sin cambio de estado; destino alternativo durante una
transición; ausencia de reinicio si el destino ya es original; exclusión del
jugador, rutas ajenas, índices inválidos y otro estado; CrossFade real seguido
de una segunda evaluación que conserva sus datos y progreso. Se validan anchor,
continuación, flags, registros, pila y límites de la sección.

Evidencia final en
`output/anm_npc_variants_20261011/no_alert_variants/installed.json`.
Suite completa de la regla final: **254 pruebas sin fallos, 11 omitidas**.
Build instalado: T3_Modded SHA-256
`ab1d7da87fbef057177889f11b4455c417ba6b107720e7a323258e655ca59f8b`,
A2 `38b6cdf9e8dd20070d0568f33e2cdf6935ac73a9d7954072f6144b57697a2946`,
Mods.Cod `da9f3d279b92a70a785d46640759f58aced8813538f4b044afeb496bf1d4c256`.
El CALL del guard llega a `0x11BA4F8` en este build. Se comprobaron originales,
ANM y bibliotecas fuente sin cambios, 66 registros y seis reglas de composición.
**UNKNOWN — confirmación visual de la transición al entrar en alerta pendiente.**


## Corrección del signo y exclusión de Heavy Assault — 2026-10-11

**OBSERVED — usuario:** tras desactivar alternativas en alerta, los NPC miran
unas veces arriba y otras abajo; también se aprecia el problema en Heavy Assault.

**OBSERVED — captura de solo lectura:**
`output/anm_npc_variants_20261011/pose_1791702059422946600.jsonl`, proceso 12768,
601 muestras válidas y 52 descartadas. T900S alcanza ambos límites de GetUpDown,
±1,256637 radianes (±72 grados), incluso sin alerta. La captura concreta no
reprodujo el síntoma en Heavy Assault: sus muestras no tenían enemigo y el
control permanecía a cero. Se confirmó en código que el hook anterior sí lo
incluía. Los hashes de esta captura corresponden a `no_alert_variants/installed.json`.

**CONFIRMED — causa en el parche, no en la sintaxis ANM:** el helper anterior
negaba GetUpDown antes de medir el error. Vector2Angles y GetUpDown usan el mismo
signo de pitch. Ai::Process limita el delta a 8 grados en este perfil y lo niega
al convertirlo a radianes, pero T3 `cHumanControl::Aim` vuelve a negarlo y lo
suma a control+0x8E8. La doble inversión implica `look += radians(delta)`.
La medida anterior `-degrees(look)` producía `delta = +degrees(look)` y alejaba
la vista de cero en ambos sentidos. Ese control acumulado pasa luego a alerta.

Evidencia nativa: Ai.pdb resuelve Process en 0x1000DFE0; su bloque
0x1000F0F2..0x1000F1DE limita y convierte el delta. La llamada virtual del motor
termina en T3 `cHumanControl::Aim`, resuelto por T3.pdb en 0x5279B0. FCHS en
0x5279B7, suma en 0x5279E7 y límites de ±72 grados hasta 0x527A25. El puntero
virtual del control observado en la partida apuntaba a ese método.

**CONFIRMED — revisión:** se elimina FCHS del cálculo de GetUpDown, conservando
`AngleDelta(0, degrees(GetUpDown))`. El filtro vertical usa exclusivamente el
nombre completo T900S y se instala solo con variantes configuradas. Heavy Assault
mantiene su control vertical nativo en reposo, navegación y alerta. La corrección
horizontal previa sigue cubriendo T900S y Heavy Assault. El helper PIC ocupa
253 de 256 bytes; entrada de pitch 0x10129F69, hook 0x1000F0E2. El informe publica
`relaxed_pitch_casts: ["T900S"]` y `on_foot_without_alert`. Continúa la regla de
alternativas solo fuera de alerta y salida mediante CrossFade al original del
mismo estado cuando aparece un enemigo.

**CONFIRMED — limitación corregida de las pruebas anteriores:** la prueba antigua
paraba en AngleDelta y simulaba a mano `look -= radians(error)`. Omitía la segunda
inversión del consumidor real; por eso aprobó el signo equivocado. La regresión
actual ejecuta las instrucciones originales de Process y cHumanControl::Aim,
incluidos conversión, suma y límites, y obtiene el pitch del arma con Vector2Angles.
Solo se sustituye la actualización física de rumbo que no interviene en el pitch.
Verifica convergencia desde ambas inclinaciones, en reposo y movimiento, y demuestra
que el error anterior lleva a ambos límites. Heavy Assault debe devolver exactamente
el mismo delta que el original en todos los estados probados. Se conservan las
pruebas de selector, guard, rumbo, ABI/x87, reubicación, anclas y reserva.

Suite completa: **255 pruebas sin fallos, 11 omitidas**. Compilación aislada
verificada en `output/anm_npc_variants_20261011/pitch_sign_scope_fix/staged.json`.
T3_Modded conserva SHA-256
`ab1d7da87fbef057177889f11b4455c417ba6b107720e7a323258e655ca59f8b`;
A2 corregido: `8b1d0b4e42f1df5849e60215c011b76cc84997254c587bf97d904813feb7d831`.
Originales, ANM, bibliotecas fuente y orden de mods se verifican por hash antes
y después. Se conservan 66 registros, tres pares de variantes y seis reglas de
composición. Instalación terminada y verificada en `pitch_sign_scope_fix/installed.json`.
Mods.Cod instalado: `a874c33a6e1328b9fe9c5e76db5454b898edb547fdff325974c87c1dbb54e068`.
La siguiente captura debe usar `probe_pose.py --pitch-sign-fixed`, que verifica
los hashes de esta revisión y sus bytes cargados antes de leer la partida.

**UNKNOWN — validación visual del nuevo build pendiente:** iniciar una partida
nueva para no conservar el control extremo de los actores del proceso anterior.
Comprobar T900S relajado → alerta → combate → pérdida del objetivo, con enemigos
a distintas alturas; comprobar por separado Heavy Assault con sus clips dual.


## Jugador y continuidad caminar/correr → idle — 2026-10-11

**OBSERVED — usuario:** «se ve bien» confirma visualmente la revisión anterior
que corrigió el signo vertical y excluyó Heavy Assault del ajuste. Pide habilitar
alternativas para el jugador y que idle conserve la variante del movimiento previo.

**CONFIRMED — implementación:** el filtro común valida el controlador dentro del
array de 64 actores y su human. El selector permite jugadores y conserva el veto
de alerta para agentes AI asociados. El guard que retira una alternativa activa
al comenzar alerta continúa limitado a agentes AI. No se modifica la corrección
vertical ni la navegación de A2, ya confirmadas por el usuario.

El compilador construye `variant_idle_links` a partir de los roles de la biblioteca
efectiva: HAND_<arma>_IDLE se vincula a HAND_<arma>_WALK y HAND_<arma>_RUNNING
si sus archivos tienen pares registrados. No se deducen estados de los nombres
de archivo ni de índices numéricos consecutivos. Los archivos compartidos por
WM20/WM27/WM32 generan dos vínculos únicos en el paquete actual.

Antes del sorteo, el selector compara la ruta previa del canal 2 con esos vínculos.
Una ruta de movimiento normal exige idle normal; una alternativa exige idle
alternativo. Se conserva el requisito de que el registro elegido tenga el mismo
estado nativo solicitado. Durante una transición se consulta el destino; si no
existe un movimiento previo vinculado, se conserva el sorteo. No se crean flags
persistentes ni se modifican datos del actor o de los archivos ANM.

**CONFIRMED — orden de lectura:** T3.pdb resuelve Animate_UpperBody en 0x488460.
CrossFade busca el estado en 0x54382A antes de modificar el índice del canal a
partir de 0x543865; StartPlay hace lo mismo en 0x5432F0 antes de sus escrituras
en 0x54331B..0x543327. Así ambos caminos pueden consultar el movimiento anterior.
El nuevo helper y sus tablas siguen alojados en la asignación RX del loader.

Regresiones nativas: jugador con ambas variantes de cada estado; independencia
respecto a la alerta de otro agente; caminar/correr normal y alternativo → idle
para jugador y bot; destino durante CrossFade; prioridad de alerta; rutas ajenas,
índices inválidos, otras llamadas/canales/esqueletos y actores fuera del array.
Se ejecuta el caller real hasta almacenar idle con CrossFade de 150 ms y StartPlay
instantáneo, conservando pila e identificador del estado. Una prueba del compilador
usa nombres de archivo arbitrarios para verificar los vínculos por rol.

El informe registra `variant_condition: player_or_npc_without_alert` y
`variant_idle_policy: inherit_previous_locomotion_variant`. Evidencia de esta
revisión en `output/anm_npc_variants_20261011/player_idle_continuity/`.
**UNKNOWN — confirmación visual de esta ampliación pendiente.**


Suite completa de esta ampliación: **261 pruebas sin fallos, 11 omitidas**.
La compilación aislada conserva 66 registros, seis reglas de composición, los
ANM y bibliotecas fuente, originales y orden de mods. El guard ahora llega a
0x11BA5A8; sigue derivándose del generador, sin fijar esa dirección en el parche.
SHA-256 T3_Modded: `85162f16dc048d37ff34ccc6ff6f0f639358ced78c59922c03aca55ff8464bab`.
A2 conserva exactamente `8b1d0b4e42f1df5849e60215c011b76cc84997254c587bf97d904813feb7d831`.
La captura posterior de bots usa `probe_pose.py --player-idle-continuity`.

Instalación terminada y verificada en `player_idle_continuity/installed.json`.
Mods.Cod instalado: `b3bf79236052bfffd42f5dcbd422b65f7dae442c5eadf32556c010a7d2d4fd26`.
Los hashes de T3_Modded y A2 coinciden con los de la compilación aislada.


## Idle normal después de disparar — 2026-10-11

**OBSERVED — usuario:** las alternativas ya afectan al jugador; al disparar se
volvía a sortear el idle, alternando la postura entre disparos. Pide regresar
siempre al idle normal después del disparo, para jugador y bots.

**CONFIRMED — causa y regla:** el movimiento previo tenía vínculos explícitos
hacia idle, pero los clips de disparo caían en el sorteo de fallback. El compilador
ahora deriva `variant_idle_normal_sources` desde HAND_<arma>_FIRE y
HAND_<arma>_SECOUNDARY_FIRE de la biblioteca efectiva, asociados al idle de esa
misma arma si tiene variante configurada. SECOUNDARY conserva la grafía nativa.
Las rutas compartidas por WM20/WM27/WM32 producen dos vínculos únicos. Reload,
cambio de arma y rutas ajenas no se clasifican como disparos.

El helper reutiliza la comparación previa del canal 2, con prioridad al destino
durante CrossFade. Las nuevas filas devuelven normal antes de cualquier sorteo;
no hay flag persistente de disparo, nuevo hook ni modificación del control de IA.
Se conserva la continuidad normal/alternativa tras caminar o correr. Si el actor
continúa moviéndose, mantiene el estado de movimiento solicitado por el motor;
esta regla elige el idle cuando el motor solicita idle, sin detenerlo a la fuerza.

Evidencia nativa: Animate_UpperBody consulta GetCurrentState en 0x4890E8 y espera
el fin del canal de disparo. GetCurrentState (0x543FC0) devuelve -1 si el flag de
actividad +0x76 está desactivado; el índice previo +0x64 es un campo distinto.
StopPlay (0x5433B0) desactiva ese flag sin borrar el índice de archivo. La búsqueda
de locomoción ocurre antes de que CrossFade/StartPlay reemplace dicho índice.

Pruebas: disparos primarios y secundarios → idle normal en jugador y NPC, múltiples
ticks, transición en progreso, retorno posterior a alternativas de movimiento,
rutas de recarga ajenas y selección independiente del nombre del archivo. Se
extiende la ejecución del caller original hasta almacenar el idle, tanto con
CrossFade de 150 ms como con StartPlay instantáneo. El reporte publica
`variant_post_fire_idle: normal` junto con las rutas concretas. Evidencia de build
en `output/anm_npc_variants_20261011/post_fire_idle/`.
**UNKNOWN — validación visual del nuevo regreso de disparo pendiente.**


Suite completa: **263 pruebas sin fallos, 11 omitidas**. La compilación aislada
verifica dos vínculos de locomoción y dos de disparo, 66 registros y seis reglas
de composición, con hashes de originales y assets de usuario sin cambios.
T3_Modded SHA-256: `d8a1592e5e186a9f6986de0cc7000291dfd73a86502d46c4fdb240af31af713e`.
A2 conserva exactamente `8b1d0b4e42f1df5849e60215c011b76cc84997254c587bf97d904813feb7d831`.
Captura posterior de bots: `probe_pose.py --post-fire-idle`.

Instalación final verificada en `post_fire_idle/installed.json`.
Mods.Cod: `0b7e0773f13a3efca3335e8b6c1f96d11b7038607eaead3224ef6590a4dfca82`.
T3_Modded y A2 coinciden con la compilación aislada; la comprobación visual
del nuevo regreso a idle continúa pendiente.
