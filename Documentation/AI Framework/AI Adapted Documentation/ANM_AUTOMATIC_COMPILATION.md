# Compatibilidad ANM automática en la compilación

Fecha: 2026-10-05. Implementada en el núcleo de T3-ModTools.

## Uso

1. Añadir los joints deseados en Blender con `(T3) Add Joint to animation`.
2. Exportar el ANM a `files/` del mod usando su ruta interna de juego.
3. Si cambia el nombre/ruta, actualizar la referencia correspondiente de
   `Anim.lib` dentro del mod. Exportar un archivo nuevo no lo registra en el motor.
4. Ejecutar **Compilar Mods + EXE modificado**. Reabrir ModTools si la interfaz
   seguía abierta con los módulos Python anteriores a esta actualización.
5. Consultar el resumen de compilación y
   `T3/modtools_data/.compiled/anm_compatibility.json`.

No hace falta escribir un `runtime_patch.py` para cada nueva animación compatible.
No se agregan joints por detectar keyframes: se inspeccionan los joints que
efectivamente contiene el ANM exportado. No se modifica el exporter ni los ANM.

## Catálogo y detección

El catálogo se reconstruye desde los COD originales instalados. Se indexan sus
rutas y se registran procedencia, CRC, tamaño y SHA-256 de cada archivo COD.
Las estructuras ANM se leen bajo demanda durante esa compilación. No hay una
lista manual que deba actualizarse cuando se agregue un mod, ni una caché
persistente susceptible de quedar asociada a otros archivos originales.

Se comparan las rutas completas y jerárquicas de joints. La referencia se
obtiene del mismo archivo vanilla o del ANM que ocupaba originalmente la
misma función en la biblioteca original del cast o en el perfil T900S compatible. Esto permite reconocer un
reemplazo renombrado: `HAND_WM20_RUNNING` puede apuntar a `ca/custom/paso.anm`
y seguir comparándose con el ANM vanilla de esa función.

Se analiza únicamente el archivo ganador de los mods habilitados. La prioridad
coincide con la compilación: el primer mod habilitado de la lista tiene prioridad.
También se usan las versiones efectivas del modelo, biblioteca y UPDOWN.

**CONFIRMED — orden de archivos originales en el motor:** Language > Patch116 >
Game. En T3.exe SHA `52f68d5df4912aba662f0371a06ae0b1ec447ef4b7338460224b20904eb0f061`,
los CALL a AddPack en 0x4FBBF8, 0x4FBC15 y 0x4FBC48 registran respectivamente
Language.cod, Patch116.Cod y Game.Cod. AddPack (0x52B0B0) añade al final;
Open recorre desde índice cero (0x52B694..0x52B6C6) y usa el primer resultado.
El loader coloca Mods.Cod primero. Este análisis sigue el motor, aunque una
guía anterior describía otro orden para el explorador de recursos.

## Perfil cubierto

- T900S TPS y casts derivados, 32 huesos, nombres/orden y matrices bind compatibles con el original.
- Overlays con funciones `HAND_*` registradas en su biblioteca.
- Joints añadidos de `spinebone2`, `spinebone3` y `head` que entren en conflicto
  con UPDOWN. La tabla guarda una máscara por animación; no habilita otros joints.
- UPDOWN debe conservar el contrato original comprobado, incluidas 25 poses
  y frame 12 neutro coincidente con el bind local.
- Nuevos joints válidos que no requieran composición reciben el fallback de bind
  local cuando corresponde; el informe los marca `local_bind_only`.

El compositor conserva las operaciones nativas de cuaterniones y Slerp. Trabaja
en canal 2 con UPDOWN activo en canal 1. Comprueba la ruta efectiva del clip,
incluido el destino de crossfade, el hueso y su máscara. Acepta mayúsculas/minúsculas
y ambos separadores de ruta. Las demás mezclas usan Slerp nativo.

Cuando se necesita composición también se incluye el arreglo de navegación:
usar el rumbo corporal cuando navega sin enemigo, conservando la ruta original
de combate. Desde 2026-10-06 cubre los casts exactos T900S y T900HeavyAssault.
No se ha generalizado a otros casts.

## Variantes aleatorias de NPC

Desde 2026-10-11, una configuración explícita `anm_variants.json` puede registrar
pares original/alternativa en la biblioteca T900S TPS generada durante la
compilación. Cada alternativa conserva el estado de su original: idle, walk y
run no se intercambian. El análisis de joints incluye las nuevas entradas.
Ver [ANM_NPC_VARIANTS.md](ANM_NPC_VARIANTS.md) para alcance, configuración,
selección por entrada al estado, pruebas y limitaciones de verificación visual.

FPS, otros esqueletos, binds modificados, UPDOWN modificado, scale/shear/reflexión
en los joints de composición y archivos nuevos sin referencia reconocible quedan
fuera del perfil. El informe explica el motivo; no se aplica por conjetura la
corrección de apuntado. Un ANM estructuralmente inválido detiene la compilación.
Una animación nueva sin equivalente vanilla y sin función original reconocible
necesita establecer/validar su referencia antes de automatizarla.

### Ampliación Heavy Assault — 2026-10-05

**OBSERVED:** el usuario agregó `t900_run_dual_wm20.anm` y
`t900_walk_dual_wm20.anm` a Heavy Assault y observó nuevamente el primer disparo
hacia arriba. La detección inicial consultaba solamente la biblioteca T900S;
estos archivos quedaban sin regla de composición. Ambos contienen 22 joints y
33 frames. El modelo TPS Heavy Assault conserva exactamente los 32 nombres,
orden y matrices bind del perfil T900S.

**CONFIRMED por análisis y pruebas:** ahora se descubren las bibliotecas
`ca/casts/*/tps/anim.lib` efectivas, se valida el modelo de cada una y su UPDOWN.
Las siete funciones `HAND_WM20_DUAL_*` conocidas (IDLE, WALK, RUNNING, FIRE,
SECOUNDARY_FIRE, CHANGE_BACK y CHANGE_GO) usan como referencia sus funciones
WM20 originales. Esto funciona con otro nombre de archivo; no depende de que
el nombre contenga `dual`. No se infieren equivalencias para otras funciones
desconocidas. Un rol nuevo que reutiliza una ruta vanilla conserva esa referencia
directa: por ejemplo, WM27 reutiliza run/walk WM20 en la selección actual.

La selección del compositor es por pareja `(clip, UPDOWN)`. Una biblioteca no
compatible con otro UPDOWN queda excluida sin eliminar las reglas de bibliotecas
válidas que usan el mismo clip. Si comparte también UPDOWN, la pareja se excluye
conservadoramente. Referencias conocidas que discrepan sobre los joints añadidos
impiden componer ese clip. Se deduplican reglas compartidas entre bibliotecas.
El informe incluye bibliotecas, referencias y exclusiones por animación.

Las bibliotecas FPS se identifican como fuera del perfil, sin comparar sus
joints contra una referencia TPS. El helper de navegación sigue restringido
a T900S; esta ampliación modifica la selección de apuntado, no ese helper.

**Pruebas:** suite general de 206 pruebas OK, 11 omitidas; después del ajuste
de referencia por ruta vanilla para WM27, se repitieron las 18 pruebas de catálogo
y compilación, todas OK. La prueba nativa nueva ejecuta 594 combinaciones:
los 33 frames de cada clip dual, tres joints y tres poses UPDOWN; incluye el
destino de crossfade en el frame inicial y verifica cuaterniones y ABI.
La confirmación visual del primer disparo con este nuevo build sigue pendiente.

**Build Heavy Assault comprobado:** seis mods habilitados en este orden: wm27,
third_person, t3_enhanced_sfx, t900_heavy_assault, t3_enhanced_t_units y fixed_weapons.
Cuatro reglas run/walk WM20 normal y dual con máscara `0x80000C`; 11 archivos
fuera del perfil/referencia. Los 38 ANM, los cinco originales y load_order.json
conservaron sus hashes. ZIP y hashes de entradas analizadas verificados.
Evidencia completa: `output/anm_heavy_auto_20261005/build_verification.json`.

| Archivo | SHA-256 del build Heavy Assault |
| --- | --- |
| T3_Modded.exe | `2773c05c4696813878df4bf42b075317b2395ed79257970d46b47fba3aa432ae` |
| A2.dll | `5257f9cfc06a2092d3ba594fa74237a78c905c6529b2e86bd608efe31eaf7aca` |
| Mods.Cod | `7f76299b0991918091f6ac28042b48229fec39555b1b5addb29364482750f42c` |

## Implementación y migración

- `t3_anm_compat.py`: catálogo, prioridades, análisis de ANM/Anim.lib/modelo y plan.
- `t3_anm_runtime.py`: compositor con tabla dinámica y parches nativos verificados.
- `t3_loader.py`: reserva código y tabla en la sección nueva RX `.t3ldr`.
  No crece sobre los antiguos espacios TLS ni sobre variables del juego.
- `t3_modding.py`: integra análisis, generación, registro de escrituras y reporte
  en `build_all`/`install_loader`.

Se reconocen los seis parches ANM antiguos de Enhanced T Units por ID, destino
y digest exacto de sus instrucciones/configuración. En la compilación se
sustituyen por los parches automáticos; los archivos del mod se conservan.
Si un parche antiguo fue alterado, se rechaza la migración automática para evitar
descartar cambios desconocidos. Las escrituras restantes siguen pasando por el
detector normal de conflictos. La función también trabaja con mods nuevos sin
ese generador histórico.

El análisis ocurre antes de retirar la compilación anterior. Después de empaquetar
se comparan los hashes de los ANM y de las dependencias del perfil leídas desde
los mods. Si una exportación concurrente cambió esos archivos, se restaura el
conjunto anterior de paquete, ejecutables e informes.

## Pruebas

**CONFIRMED por pruebas automatizadas:**

- Diez pruebas de catálogo/prioridades/roles: reemplazo renombrado, overrides de
  Patch116 y Language, mod deshabilitado, máscara parcial, huesos desconocidos,
  bind incompatible, ANM inválido, ausencia de adiciones y rollback ante exportación.
- Seis pruebas de código generado: 675 combinaciones de hueso/pose/frame/clip/peso,
  ABI y cachés; exclusiones; ejecución del bucle nativo de ocho canales; tabla de
  150 animaciones en sección ampliada; equivalencia del helper de navegación;
  migración restringida a los parches conocidos.
- Suite general: 198 pruebas, OK, 13 omitidas. Después de ampliar la comparación
  de rutas a ambos separadores y plegado ASCII de letras, se repitieron las seis
  pruebas del compositor generado: OK. El caso de 150 registros usa un límite de
  instrucciones mayor en el emulador para completar su recorrido.

## Build comprobado

**OBSERVED — archivos generados, sin nueva prueba de partida:**

- Mods habilitados: t900_heavy_assault, t3_enhanced_t_units y fixed_weapons.
- Catálogo: 678 ANM originales; dos reglas de composición detectadas automáticamente.
- Run/walk WM20: máscara `0x80000C`, correspondiente a huesos 2, 3 y 23.
- 13 ANM fuera del perfil/referencia validado: el informe los enumera. Esa
  clasificación no demuestra que esos archivos tengan un defecto.
- Seis parches antiguos sustituidos; 77 parches registrados en el build.
- Los 37 ANM de los mods, cinco archivos originales y load_order.json conservaron
  sus hashes/contenido. Mods.Cod pasó su comprobación ZIP y de entradas analizadas.
- A2.dll mantuvo exactamente el build de navegación ya confirmado por el usuario.
- La reserva antigua del compositor en raw 0x289600..0x289E00 vuelve a ser cero.
- `.t3ldr`: RVA 0xDBA000, raw 0x294000, tamaño raw 4096 bytes en esta compilación.

SHA-256:

| Archivo | Hash |
| --- | --- |
| T3_Modded.exe | `fc65deb584807cad52add60012065006a3047a7cb4e0c7c647d44ae45ece64aa` |
| A2.dll | `5257f9cfc06a2092d3ba594fa74237a78c905c6529b2e86bd608efe31eaf7aca` |
| Mods.Cod | `c1112c09ccdd2d45becf701b2d53f159cc118765ea349e136373a1d5d3b67671` |

El comportamiento de los parches previos fue confirmado por el usuario en
ERR-ANM-01. La selección automática y el nuevo dispatcher tienen pruebas nativas
por emulación; aún no se ha observado este nuevo ejecutable en una partida.

## Ampliación de navegación Heavy Assault — 2026-10-06

El informe añade `navigation_casts: ["T900S", "T900HeavyAssault"]` cuando
se activa la corrección. El compositor de apuntado ya cubría los clips dual;
el helper de rumbo todavía filtraba sólo T900S. El nuevo helper incluye Heavy
Assault para que la navegación sin enemigo deje de contrarrestar el balanceo
animado del arma/torso. Los ANM conservan todos sus joints y matrices.

El código PIC ocupa 171 bytes en Ai.dll VA 0x10129F00 y sustituye el helper
anterior de 106 bytes. La reserva es de 256 bytes, hasta 0x1012A000. El límite
de la reserva anterior Heavy spawn se reduce a 0x10129F00; su código actual
finaliza en 0x10129E66, sin modificación de sus instrucciones. La compilación
mantiene validación de hash, anclas, padding y conflictos de escritura.

Pruebas: suite de 211 casos OK, 11 omitidos; cuatro casos nuevos de navegación
nativa y equivalencia T900S con la implementación anterior. Detalles y límites
en ERR-ANM-01. La comprobación visual del nuevo build continúa pendiente.

## Postura relajada de NPC — 2026-10-11

**Histórico:** la implementación de 254 bytes descrita a continuación tenía el
signo invertido y un alcance excesivo. La revisión vigente usa 253 bytes, activa
el hook vertical solo si existen variantes configuradas y lo aplica únicamente
al cast exacto T900S a pie y sin alerta. Heavy Assault conserva su apuntado
vertical nativo. Su corrección anterior de rumbo horizontal sigue activa.
El delta correcto es `AngleDelta(0, degrees(GetUpDown))`, sin negar GetUpDown.
Ver la corrección y las pruebas del consumidor completo en ANM_NPC_VARIANTS.md.

El helper actual ocupa 254 bytes en la misma reserva de 256 bytes y añade una
entrada en 0x10129F69 para el delta vertical de Process (hook 0x1000F0E2).
Fuera de combate, a pie, T900S y T900HeavyAssault retornan GetUpDown a neutral;
la IA deja de bajar el torso para cancelar una elevación del rifle escrita en
el ANM. Conserva las rutas nativas de combate y vehículo y la corrección previa
del rumbo. Se activa con composición automática o con variantes registradas,
incluso si estas solo modifican joints ya existentes.

El informe añade `relaxed_pitch_casts`. Ver evidencia de captura, prueba nativa,
compilación y límites en [ANM_NPC_VARIANTS.md](ANM_NPC_VARIANTS.md).

Propuesta intermedia del mismo día (sustituida por la regla siguiente): la condición de pitch era **sin orden de
disparo**, incluso si ya hay un enemigo detectado. Al solicitar disparo vuelve
al apuntado nativo. `relaxed_pitch_condition` registra
`on_foot_without_shot_request`; esta ampliación conserva el tamaño y las
direcciones del helper. La condición del rumbo horizontal sigue siendo la anterior.

**Regla vigente:** las variantes se seleccionan únicamente con NPC sin alerta.
Detectar un enemigo hace volver al original del mismo estado, mediante CrossFade,
incluso si el estado idle/walk/run no cambió. El informe registra
`variant_condition: npc_without_alert`. El pitch vuelve a
`relaxed_pitch_condition: on_foot_without_alert`; en alerta se conservan
animaciones originales y apuntado nativo. Ver el guard 0x489CFB y sus pruebas
en ANM_NPC_VARIANTS.md.


## Ampliación vigente: jugador e idle coherente — 2026-10-11

El jugador también participa del selector de variantes. Los NPC mantienen la
exclusión por alerta. El compilador deriva `variant_idle_links` de los roles
HAND_<arma>_IDLE/WALK/RUNNING de la biblioteca efectiva, no del nombre del ANM.
Al detenerse se conserva la elección del movimiento previo: normal → idle normal;
alternativa → idle alternativo. Durante CrossFade se consulta el destino. Sin
movimiento previo vinculado se conserva la elección aleatoria. No se añade estado
mutable por actor. El reporte describe la política y los vínculos concretos.
La corrección vertical y de navegación de A2 permanece idéntica a la revisión
que el usuario confirmó visualmente. Detalles en ANM_NPC_VARIANTS.md.


## Regreso después del disparo — 2026-10-11

Los roles HAND_<arma>_FIRE y HAND_<arma>_SECOUNDARY_FIRE de la biblioteca
efectiva generan `variant_idle_normal_sources`: al regresar desde ellos a idle,
jugador y NPC seleccionan siempre el normal. El informe registra
`variant_post_fire_idle: normal`. Se mantiene la continuidad de caminar/correr
a idle y la prioridad de alerta. No se modifica A2 ni el contenido de los ANM.
