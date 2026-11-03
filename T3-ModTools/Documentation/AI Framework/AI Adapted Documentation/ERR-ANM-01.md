# ERR-ANM-01 — T900 Supply: apuntado y joints añadidos al overlay WM20

Fecha: 2026-10-05. Estado: corrección implementada y compilada; pruebas x86
aisladas aprobadas; pendiente de comprobación con NPC en partida.

## Síntomas y procedencia

- **OBSERVED — usuario, chat T3-ModTools (2):** NPC T900S apunta brevemente al
  cielo al comenzar una ráfaga y presenta saltos de apuntado al moverse/girar.
  El usuario aisló el síntoma al habilitar `t3_enhanced_t_units`.
- **OBSERVED — usuario, chat Plugin Stuff:** `t900_walk_wm20.anm` es una copia
  de `t900_run_wm20.anm` renombrada. Ambas son las nuevas animaciones custom.
  Se añadieron manualmente `spinebone2`, `spinebone3` y `head`.
- Diagnóstico anterior: `output/t900s_aim_20261005/DIAGNOSIS.md`.
  Captura: `output/t900s_aim_20261005/capture_1791172764610826800.jsonl`.
  Su contenido y resultados se consultaron; esta actualización no efectuó una
  nueva captura de memoria ni observación de una partida.

## Verificación de archivos de esta actualización

**CONFIRMED:** en `T3/mods/t3_enhanced_t_units/files/CA/tps_skynet/`, run y walk
son idénticos byte por byte y coinciden con sus entradas en Mods.Cod. SHA-256 de
ambos: `b2c7cecb5ade8b63a5d1bb7d1e1a3a1a74955596c82d52cc41819e3ff0aea6ea`.
Cada archivo contiene 33 frames y 22 joints; los originales tienen 19 joints.
Las únicas incorporaciones al conjunto original son:

- `|human_root|body_root|root|spinebone1|spinebone2`
- `|human_root|body_root|root|spinebone1|spinebone2|spinebone3`
- `|human_root|body_root|root|spinebone1|spinebone2|spinebone3|head`

## Mecanismo establecido por el diagnóstico anterior

El canal 1 aplica `UPDOWN` para orientar verticalmente al personaje. Después,
el canal 2 del arma, con peso 1, reemplaza los joints que tenga activos.
Las pistas añadidas en run/walk reemplazan la pose de apuntado, aunque una
pista sea constante. Idle/fire WM20 conservan el subconjunto original de 19
joints: al cambiar hacia ellos, los tres joints dejan de estar activos en el
canal del arma y reaparece la orientación acumulada del canal de apuntado.

**OBSERVED — captura previa:** para un NPC, al cambiar run -> idle, el pitch
del arma pasó de -0.70 a +52.72 grados mientras la orden de apuntado se mantenía
cerca de +53 grados. En run, las correcciones alcanzaban +/-72 grados mientras
el arma permanecía cerca de horizontal. Consultar el diagnóstico y la captura
original para direcciones, funciones y límites de muestreo.

**HYPOTHESIS:** esa acumulación y liberación explica también el primer disparo
desviado. La captura anterior no registró directamente la emisión y dirección
del primer proyectil; esa parte aún requiere comprobación.

## Relación con la corrección anterior

El parche de matrices locales de `ANM_TRANSITION_FIX.md` permanece aplicado en
el ejecutable actual (raw 0x1232EA). El usuario confirmó en Plugin Stuff que ese
parche resolvió el giro al iniciar la carrera. Ese resultado corresponde al
defecto de inicialización de joints ausentes. ERR-ANM-01 involucra además la
prioridad de los canales y la respuesta del apuntado de los NPC.

Copiar run como walk replica el mismo conjunto de pistas activas en ambas
acciones. La investigación debe centrarse en la convivencia de esas pistas con
UPDOWN y la liberación de su control durante las transiciones.

## Criterios para continuar

- Mantener el registro explícito de joints solicitado por el usuario; tener
  keyframes en otro hueso no autoriza incorporarlo automáticamente al ANM.
- Conservar las animaciones originales del usuario como referencia al preparar
  cualquier variante de prueba.
- Una variante controlada de 19 joints permitiría aislar el conflicto, pero
  elimina el movimiento nuevo de torso/cabeza. No equivale por sí sola a una
  solución que preserve la intención de las animaciones custom.
- Para conservar ese movimiento, investigar su composición con el apuntado,
  las máscaras y la prioridad de canales antes de elegir un parche.
- Verificar por separado transiciones de movimiento y el primer proyectil de
  una ráfaga iniciada tras permanecer quieto.

Esta actualización solo documenta la aclaración del usuario y verifica archivos.
No modifica ANM, plugins, parches, ejecutables ni el orden de carga.

## Implementación posterior: composición de apuntado (2026-10-05)

El usuario pidió corregir ERR-ANM-01 conservando la intención de sus animaciones.
Se añadió `T3/mods/t3_enhanced_t_units/aim_compositor.py`, integrado por el
generador `runtime_patch.py`. Los dos ANM conservan sus 22 joints, matrices y
hashes anteriores. El registro manual del exportador sigue igual.

El compositor interviene únicamente en la mezcla de rotación local del canal 2
para el esqueleto TPS de 32 huesos, índices 2, 3 y 23, si el canal 1 está activo,
habilita ese hueso y su clip es `CA/TPS_SKYNET/t900_updown.anm`. El clip actual
del arma (o destino del crossfade) debe ser exactamente `t900_run_wm20.anm` o
`t900_walk_wm20.anm` bajo esa misma ruta. La comparación acepta mayúsculas y
minúsculas, pero requiere el nombre completo terminado en NUL.

Antes del Slerp, su objetivo pasa a ser:

`q_ajustada = q_acumulada * inversa(q_bind_local) * q_custom`

Es el producto de cuaterniones nativo, equivalente en matrices de fila a
`R_custom * inversa(R_bind_local) * R_apuntado`. El bind local de estos tres
joints coincide con UPDOWN neutro (frame 12). Se mantiene el peso original del
Slerp. Las traslaciones, pistas cacheadas y máscaras no se reescriben. El caso
fuera de esos filtros vuelve al Slerp original. La dirección real del arma
puede así responder al apuntado mientras conserva la rotación custom.

### Evidencia y seguridad

- **CONFIRMED por emulación:** se ejecutaron las funciones x86 originales
  ToQuaternion (0x502530), operator* (0x5021C0), ToMatrix (0x502400) y Slerp
  (0x5026C0) bajo Unicorn. El thunk CRT de acos se implementó con instrucciones
  x87 equivalentes solo dentro del emulador; el ejecutable entregado usa su CRT.
- 2.475 combinaciones reales (25 poses UPDOWN x 33 frames custom x 3 joints)
  coincidieron con una referencia independiente de matrices, tolerancia 4e-5.
- 450 llamadas al hook comprobaron salida, peso, destino en crossfade, rutas,
  pila, registros preservados, profundidad x87 y ausencia de escrituras en los
  datos del controlador. Se comprobaron también los caminos de exclusión.
- Se ejecutó el bucle nativo completo de ocho canales (0x5426B5–0x542B05):
  el código original reproduce la sobrescritura por custom; el corregido
  conserva la composición esperada. Esto es emulación, no una prueba de partida.
- Se verificaron índices/nombres y bind neutro contra el LOD T900S original.
- La reserva está en VA 0x11AF600, raw 0x289600; 535 bytes hasta 0x11AF817.
  Queda fuera del template TLS [0x11AF000,0x11AF040), VirtualSize 0x44 y la
  reserva third_person [0x11AF100,0x11AF580). Se valida el layout PE, hash
  completo, bytes originales y tamaño. El manifiesto marca ejecutable la página.
- Se reemplaza solo el destino del CALL a Slerp en 0x542781; la continuación
  permanece en 0x542786. Se preservan la convención cdecl y los registros de
  Update. No se cambia Ai.dll ni se parchea un proceso en vivo.
- Los 134 parches de T3.exe en todos los manifiestos disponibles, incluso mods
  deshabilitados, se aplicaron en memoria sin conflictos de escritura. El único
  patrón de 4 bytes encontrado hacia la reserva amplia era el opcode/desplazamiento
  de un CALL en 0x4450BE a 0x456BC0, no una referencia absoluta a esa reserva.
- La revisión automática inicialmente rechazó integrar código nativo sin pruebas.
  Tras comprobar el prototipo aislado y su ABI, la integración fue aceptada.
- Suite completa con las primeras cuatro pruebas nuevas: 176 pruebas, OK, 11
  omitidas. Después se agregaron las dos comprobaciones de bucle/contrato; las
  seis pruebas específicas pasaron juntas. No se afirma prueba visual todavía.

### Build entregado

T3_Modded.exe SHA-256:
`8a543f9834197700df6a36984a29f6407036ba99a289b0e01813c53a4e97c6b7`.
A2.dll SHA-256 (sin cambios por esta corrección):
`6e2eef766c5280529f912c9c353f6ef78a0993287367003ba83af1749fb4643d`.

Se conservaron las selecciones actuales: t900_heavy_assault, t3_enhanced_t_units
y fixed_weapons habilitados. Binarios/archivos originales y los 23 ANM del mod
mantuvieron sus hashes. Se verificaron los bytes del compositor, hook y arreglo
anterior de bind local en el ejecutable generado, y ambos ANM en Mods.Cod.

El lector `output/t900s_aim_20261005/probe_t900s.py` quedó preparado para este
hash y verifica también los bytes del hook/compositor antes de una nueva captura.
La captura anterior conserva su metadata/hash y no fue modificada.

### Primera captura después del parche

**OBSERVED — lectura de memoria:** proceso 20012, ejecutable del build anterior
verificado en disco y memoria; 35 segundos, 3.350 muestras, cero descartadas,
archivo `output/t900s_aim_20261005/capture_1791174347098265600.jsonl`.
No hubo objetivos válidos, solicitudes de disparo ni flags de disparo durante
ese intervalo. Hubo 2.012 muestras de locomoción con reloj estable y sin
crossfade, pero ninguna con solicitud de pitch mayor a 5 grados. Esta captura
no confirma todavía la corrección del apuntado en combate ni del primer tiro.
Se solicitó al usuario provocar un encuentro con enemigos para completar la
verificación. El lector usa únicamente PROCESS_VM_READ.

### Segunda captura: combate después del parche

**OBSERVED — lectura de memoria, 2026-10-05:** mismo proceso 20012 y build
verificado; captura de 55 segundos en
`output/t900s_aim_20261005/capture_1791174497539151200.jsonl` (17.153.076 bytes).
SHA-256: `07b9d40dc73bc5be48cdd342d9dcd9e84ebe9a028a52c57dfea1a4c2b70adb2e`.
Se obtuvieron 5.070 muestras y se descartaron 1.268 intentos por las
comprobaciones del lector. Hubo 2.953 muestras con objetivo válido, 1.605 con
solicitud de disparo y 617 con algún flag de disparo activo.

Para los errores de pitch se usaron muestras con reloj del juego igual antes
y después de la lectura, localizador disponible y `dual_marker == false`:
3.483 muestras. Se comparó el pitch solicitado por la IA (`look_pitch_yaw[0]`,
convertido a grados) con el pitch del localizador de arma de slot 0. No es
una comparación con la trayectoria del proyectil ni con la posición del blanco.

| Medición | Antes del parche | Después del parche |
| --- | ---: | ---: |
| Muestras run/walk WM20 sin crossfade | 1.068 | 2.311 |
| Error absoluto mediano | 7,862° | 0,0078° |
| Percentil 95 del error absoluto | 50,389° | 1,102° |
| Máximo error absoluto | 71,526° | 1,678° |
| Máximo pitch solicitado absoluto en esas muestras | 72,000° | 9,043° |

La referencia anterior es `capture_1791172764610826800.jsonl`, SHA-256
`f20eed9ac58f1ead762fbdf7fd67cee264a307e319204e3c73e610d8d20f77c5`.
Son encuentros distintos, no una repetición determinista del mismo combate.
El rango de elevación en marcha fue menor después del parche; las elevaciones
extremas siguen cubiertas por emulación, no por esta captura de partida.

- En las 22 muestras nuevas de marcha con solicitud absoluta mayor a 5°,
  el error mediano fue 0,974° y el máximo 1,146°.
- En 426 muestras estables con flag de disparo, error mediano 0,000019°,
  máximo 1,027°; la solicitud alcanzó 20,381°.
- Se identificaron nueve flancos de inicio de disparo (flags cero a no cero,
  mismo agente, muestras consecutivas estables separadas como máximo 0,15 s).
  En los nueve, el error absoluto fue menor a 0,000035°. Esto verifica la
  orientación del arma al activarse el flag; no captura el primer proyectil.
- En seis cambios observados de run/walk a otro clip, con el mismo filtro
  temporal, el mayor cambio de pitch entre muestras fue 2,135°, acompañado
  por una variación de la solicitud de aproximadamente 2,15°.
- Ninguna de las 3.483 muestras estables alcanzó una solicitud absoluta de 70°.

Estos datos respaldan que se recuperó la respuesta de apuntado durante la
locomoción y que no apareció el salto grande en los inicios de disparo
muestreados. La lectura es asíncrona y puede omitir eventos entre muestras.
No se modificó el proceso en vivo.

**OBSERVED — usuario:** después de esta captura confirmó que ya no ve el
apuntado aleatorio hacia arriba. Informó un temblor leve izquierda/derecha al
caminar, incluso sin disparar. La confirmación visual no es una medición de
trayectorias de proyectiles.

## Seguimiento: oscilación lateral al caminar sin combate

**OBSERVED:** las capturas de marcha sin enemigo anteriores y posteriores al
compositor muestran yaw local del arma aproximadamente entre -0,3° y +3,6°.
El giro del cuerpo cambia en sentido opuesto al balanceo. En la captura neutra
posterior, la correlación entre cambios consecutivos de ambos ángulos fue
-0,494 y -0,469 para los dos NPC observados (811/840 pares filtrados, separados
entre 0,01 y 0,055 s, con cambios del cuerpo menores a 1,5°). La correlación
motivó el trazado siguiente; por sí sola no demostraría la causa.

### Trazado y reproducción

**CONFIRMED — Ai.dll original:** `aiAgent::Process` obtiene el vector mundial
del arma mediante `GetLocatorWorld` en 0x1000E78D. En 0x1000E998 lo convierte
con `Vector2Angles` (0x1000F750) a la referencia actual de apuntado. Incluso
sin objetivo, cuando agent+0x114 indica navegación activa, convierte el vector
desde agent+0xE8 hasta el destino agent+0x17C (0x1000EDB9..0x1000EDC6).
La diferencia de yaw con la referencia del arma se usa en 0x1000EE18 para
locomoción y en 0x1000F0CC para la corrección de giro enviada a Aiming.
Por ello un balanceo visual de arma puede inducir giros de todo el NPC al caminar.

**OBSERVED:** una captura adicional de 20 segundos,
`output/t900s_aim_20261005/capture_1791175004042888100.jsonl`, añadió destino
y flag de navegación al lector. Obtuvo 995 muestras (1.416 intentos rechazados),
394 con reloj estable, navegación activa y sin enemigo. Por ejemplo a 9,422 s:
rumbo del cuerpo 8,815°, arma 10,872°, destino 11,420°. La referencia del arma
estaba más cerca del destino que el propio cuerpo. Se conservó el build de
apuntado anterior durante toda esa captura.

**CONFIRMED — emulación:** con el cuerpo mirando exactamente al destino,
los fragmentos originales `Vector2Angles` y `Process` generan una corrección
variable de más de 3,8° al variar únicamente el balanceo local del arma. El
helper nuevo produce cero en ese escenario y conserva una orden de giro
de 8° cuando cambia realmente el destino.

### Corrección preparada

`navigation_heading.py`, integrado por `runtime_patch.py`, sustituye la
referencia de **yaw** por la dirección frontal del cuerpo físico solo cuando:

- el cast se llama exactamente `T900S`;
- agent+0x114 indica navegación activa;
- agent+0x117 indica que no hay objetivo válido.

Conserva el pitch calculado desde el arma y todo el cálculo original cuando
hay enemigo, no hay navegación o es otro cast. Afecta navegación T900S sin
enemigo independientemente del arma/clip equipado; no filtra solo WM20.
Esto evita usar el balanceo visual como error de rumbo, sin eliminar keys,
joints, balanceo del torso/cabeza ni giros reales del camino. No corrige ni
oculta movimientos de combate o decisiones de evasión/colisión.

Helper PIC de 106 bytes en Ai.dll VA 0x10129F80 (raw 0x129F80), reserva hasta
0x1012A000, posterior a la reserva Heavy spawn [0x10129D00,0x10129F80).
Hook: CALL de 0x1000E998; continuación intacta en 0x1000E99D. Usa dos llamadas
nativas a Vector2Angles y cambia únicamente el yaw del resultado temporal.
No escribe el controlador, el vector del arma ni el cuerpo físico.

Se verificaron SHA completo, PE32, sección ejecutable, anclas únicas, padding
cero, destinos de saltos/calls, instrucciones completas, continuación y ausencia
de relocaciones/punteros originales hacia la reserva. El código añadido usa
CALL/JMP relativos y punteros vivos; admite la reubicación real de A2.dll.
Los 134 parches T3.exe y 16 parches Ai.dll de todos los manifiestos, incluidos
los deshabilitados, se aplicaron en memoria sin conflictos.

### Pruebas y estado de entrega

Cuatro pruebas específicas aprobadas en `test_anm_navigation.py`: 648
combinaciones de rumbo/balanceo/pitch en tres bases de carga, conservación de
pila/registros/x87/datos, exclusiones idénticas al original, reproducción del
error de navegación y contrato binario. Solo el thunk CRT asin se sustituye
por x87 equivalente dentro del emulador; el juego usa su implementación nativa.

Suite general: 182 pruebas ejecutadas, 13 omitidas; hubo un fallo de manifiesto
porque comenzó antes de sincronizar `executable.json`. Tras sincronizarlo,
las tres pruebas del módulo afectado pasaron; las cuatro nuevas también se
repitieron satisfactoriamente y el generador valida sin `--write`.

Al preparar esta corrección quedó pendiente compilar y verificar la marcha.
Los ANM run/walk conservaban SHA `b2c7cecb5ade8b63a5d1bb7d1e1a3a1a74955596c82d52cc41819e3ff0aea6ea`.

### Confirmación posterior del usuario y alcance (2026-10-05)

**OBSERVED — usuario:** confirmó «Se solucionó» después del arreglo del temblor.
La comprobación posterior de archivos en disco encontró T3_Modded.exe con SHA
`8a543f9834197700df6a36984a29f6407036ba99a289b0e01813c53a4e97c6b7` y A2.dll
con SHA `5257f9cfc06a2092d3ba594fa74237a78c905c6529b2e86bd608efe31eaf7aca`,
exactamente el hash previsto para incorporar únicamente los dos parches nuevos
de navegación al A2 anterior. Esta comprobación no fue una nueva captura de memoria.

Los defectos investigados se explicaron por inicialización/mezcla de joints en
el motor y por la referencia de rumbo usada por la IA. No se identificó un error
de sintaxis del exporter como causa de estos casos. Eso no constituye una
garantía para toda animación futura ni para cualquier selección de joints.

Alcance para autoría futura:

- El fallback de bind local actúa en LoadAnim para joints ausentes.
- La composición con UPDOWN está limitada al esqueleto TPS de 32 huesos,
  `spinebone2`, `spinebone3` y `head`, en los clips `t900_run_wm20.anm` y
  `t900_walk_wm20.anm` bajo `CA/TPS_SKYNET`, con los filtros de canal ya descritos.
  Otros nombres, joints o esqueletos no quedan cubiertos automáticamente.
- La corrección de rumbo cubre navegación sin enemigo del cast exacto T900S,
  independientemente del nombre de clip/arma; conserva la ruta de combate.
- Los joints nuevos siguen requiriendo registro manual mediante
  `(T3) Add Joint to animation`. La presencia de keyframes no los registra.

Para otros overlays con joints que participen del apuntado, revisar la mezcla
de canales y ampliar el compositor con pruebas cuando corresponda. Un ANM
sintácticamente válido puede tener conflictos de uso entre canales del motor.

### Integración posterior en el compilador

El 2026-10-05 se incorporó la detección automática por catálogo vanilla, función
de Anim.lib y joints añadidos al núcleo de ModTools. La lista fija run/walk WM20
queda sustituida durante la compilación por una tabla generada de animaciones
compatibles. Se mantienen los límites del perfil T900S TPS y de los tres joints
validados; las rutas nuevas que reemplacen funciones conocidas se detectan por
su registro. Detalles, pruebas, migración y hashes en
[ANM_AUTOMATIC_COMPILATION.md](ANM_AUTOMATIC_COMPILATION.md).

### Recurrencia Heavy Assault / WM20_DUAL — 2026-10-05

El usuario observó el primer disparo hacia arriba después de añadir run/walk
dual de 22 joints. Se confirmó que el detector inicial sólo consultaba la
biblioteca T900S y omitía la biblioteca Heavy Assault y sus roles WM20_DUAL.
No se encontró un defecto estructural en esos dos ANM: ambos tienen 33 frames,
joints constantes y matrices de rotación válidas en los tres joints añadidos.
El esqueleto TPS Heavy Assault coincide exactamente con el perfil de 32 huesos.

El detector ahora inspecciona bibliotecas de casts, valida cada modelo/UPDOWN
y reconoce los siete roles dual WM20 comprobados. Conserva referencias por
ruta vanilla para roles nuevos que reutilizan archivos existentes, como WM27.
Las bibliotecas incompatibles se excluyen según la pareja clip/UPDOWN para no
suprimir reglas válidas de otros casts. La composición nativa no cambió.

Build verificado: cuatro reglas (run/walk WM20 normal y dual), ejecutable SHA-256
`2773c05c4696813878df4bf42b075317b2395ed79257970d46b47fba3aa432ae`.
Pruebas de detección y emulación nativa correctas; confirmación visual en juego
pendiente. No atribuir al helper de navegación una validación Heavy Assault:
ese helper continúa restringido al cast T900S.

### Balanceo cancelado y temblor en NPC Heavy Assault — 2026-10-06

**OBSERVED — usuario:** tras editar run/walk dual, el jugador muestra bien el
balanceo del torso; los NPC presentan movimiento lateral leve y no muestran
el balanceo esperado. No había un proceso T3_Modded abierto durante esta auditoría.
La verificación visual posterior de la corrección queda pendiente.

**CONFIRMED — archivos:** los dos clips contienen 22 joints y 33 frames, SHA-256
`85700395cd1a8188685bbaa650352df5dea0105e76eb815c4da22d8c1178a69d`.
Mods.Cod ya contenía esa edición. El cambio de rotación está en spinebone2
(diferencia máxima entre componentes respecto del frame inicial: 0,062791);
spinebone3 y head conservan rotación constante. El informe de compatibilidad
en disco todavía registraba los hashes anteriores, aunque el paquete ANM estaba
actualizado. La recompilación completa vuelve a sincronizar informe y paquete.

**CONFIRMED — mecanismo y reproducción nativa:** A2.dll anterior, SHA-256
`5257f9cfc06a2092d3ba594fa74237a78c905c6529b2e86bd608efe31eaf7aca`,
conservaba el filtro exacto T900S. Heavy Assault caía en Vector2Angles nativo,
usando el rumbo del arma animada como referencia para locomoción y giro.
Con destino y cuerpo alineados, el test Heavy Assault produce variación de
error mayor a 3,8 grados al variar solamente el balanceo del arma. Ese mecanismo
permite que el giro del cuerpo contrarreste el balanceo visible del torso.
La atribución completa del efecto visual informado necesita la prueba en juego.

Se volvieron a resolver los símbolos de Ai.pdb: aiAgent::Process en 0x1000DFE0
(tamaño 0x149F), Vector2Angles en 0x1000F750 (0x1D7). Se revisaron el CALL
0x1000E998 y la diferencia angular de 0x1000F0C2..0x1000F0E0. Ai.dll y Ai.pdb
mantienen respectivamente SHA-256
`817ba995212c4daed24c5205bfbbe575ff9f28a6ddcc4fc494141d73934d66ae` y
`24f3c41075abc01eb253f22b34e0221d80ac5f2320f6282f86a3e550d47cbea6`.
Ai.dll es PE32, base preferida 0x10000000, tamaño 1.499.190 bytes.

**Corrección:** el compilador genera un helper PIC de 171 bytes en
`[0x10129F00, 0x10129FAB)`, dentro de la reserva ejecutable
`[0x10129F00, 0x1012A000)`. Se aceptan exactamente `T900S` y
`T900HeavyAssault`, incluyendo terminador NUL. Mantiene las condiciones de
navegación activa y ausencia de enemigo; conserva pitch y las rutas originales
de combate, reposo y otros casts, incluido T900Heavy. No escribe matrices,
controladores ni vectors del arma/cuerpo: cambia el yaw temporal usado por IA.

El CALL original `E8 B3 0D 00 00` en 0x1000E998 se redirige al helper;
la continuación 0x1000E99D permanece intacta. Las instrucciones emitidas,
destinos, pila, registros preservados, x87 y reubicaciones se verifican por
desensamblado y emulación. SHA-256 del helper:
`16ce6b526a6058c0a62f952e2d49f2ee048fc91b2e02abe297e8279e8afc0446`.
El límite reservado del generador Heavy spawn se ajustó de 0x10129F80 a
0x10129F00: su código existente acaba en 0x10129E66 y no cambió. Validación
del generador sin --write: manifiesto sincronizado. Las reservas son disjuntas.

Los helpers históricos T900S del mod se conservan como entradas conocidas de
migración. El compilador sustituye esos parches por
`anm_automatic_navigation_heading` y `anm_automatic_navigation_hook`.
El informe identifica ambos casts bajo `navigation_casts`.

**Pruebas:** 211 pruebas OK, 11 omitidas. Hubo un diagnóstico Tcl de callback
ya destruido durante pruebas UI, sin fallos del runner. Cuatro pruebas nuevas
ejecutan ambos casts en tres bases de carga, 1.296 combinaciones de
rumbo/balanceo/pitch, exclusiones y nombres parecidos, reproducción antes/después,
giros reales de ocho grados y contrato estático de secciones/reservas/saltos.
Se compara también la equivalencia de T900S con el helper histórico. La
corrección produce cero error de giro cuando sólo oscila el arma y se mantiene
alineado el cuerpo; no sustituye una observación visual de marcha en partida.

**Build comprobado:** se conservaron los 38 ANM, siete originales (incluidos
PDB) y load_order.json. Mods habilitados: wm27, third_person, t3_enhanced_sfx,
t900_heavy_assault, t3_enhanced_t_units y fixed_weapons, en ese orden. Se
verificaron ZIP, hashes de los dos clips editados, cuatro reglas de composición,
bytes del helper instalado en A2.dll y destino/continuación del hook.

| Archivo generado | SHA-256 |
| --- | --- |
| T3_Modded.exe | `2773c05c4696813878df4bf42b075317b2395ed79257970d46b47fba3aa432ae` |
| A2.dll | `9f90650d04d03338ad45d8aba0114db7e638c7d0a3dd1f9ba9bcc1bd68d9d334` |
| Mods.Cod | `ccc7a6f9c44566959e5a1aa2a5ab03f5cbb7dbc5dc5370b4299fed953c386045` |

Evidencia: `output/anm_heavy_navigation_20261006/build_verification.json`.
Reproducción pendiente: reabrir ModTools, iniciar el ejecutable modificado y
observar Heavy Assault caminando sin enemigo; contrastar balanceo del torso y
estabilidad del rumbo con el jugador, y comprobar por separado combate y giros
reales del camino. Si el síntoma persiste sólo con enemigo, capturar esa ruta:
la referencia de apuntado en combate se conserva deliberadamente.
