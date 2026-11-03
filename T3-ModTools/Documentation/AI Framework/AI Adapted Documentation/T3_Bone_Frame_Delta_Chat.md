# Conversación: Bone Frame Delta & Transform Tool

Desarrollo de un add-on de Blender para analizar, exportar e importar transformaciones de huesos y diferencias entre frames.

Período cubierto: 2 al 9 de agosto de 2026

Idioma: español

Formato: transcripción limpia del chat

## Usuario 2026-08-02 04:13:57Z

Podrias hacer un plugin de blender que me de la diferencia de entre frame y frame del movimiento (transformacion) de los huesos?

quiero que por ejemplo funcione arrojando resultados como en la parte que dice \"hombro w F0 a F3\":

hombro w F0 a F3:

```text
******************
0,988686 (frame 0) menos -- 0,000027 = frame1
0,988659 (frame 1) mas ------ 0,000014 = frame 2
0,988673 (frame 2) mas ------ 0,000012 = frame 3
0,988685 (frame 3)
```

hombro x F0 a F3:

```text
*****************
-1.09419e-08 frame 0
0.008084 frame 1
0.005988 frame 2
0.002096 frame 3
```

hombro y F0 a F3:

```text
*****************
0.0 frame 0
0.000093 frame 1
0.000069 frame 2
0.000024 frame 3
```

hombro z F0 a F3:

```text
*****************
0.150002 frame 0
0.149958 frame 1
0.149968 frame 2
0.14999 frame 3
```

## Asistente

Sí. Lo haría como un add-on que recorra los frames seleccionados, lea la transformación de cada hueso y muestre tanto el valor absoluto de cada frame como la diferencia contra el frame anterior, con signos más/menos como en tu ejemplo. También puedo hacer que exporte el resultado a un .txt.

## Asistente

Veo además un detalle importante para que el resultado sea útil: W/X/Y/Z son componentes de un quaternion. El plugin va a corregir automáticamente los cambios equivalentes q ↔ -q, porque de lo contrario Blender puede mostrar una “diferencia” enorme entre dos frames aunque el hueso prácticamente no haya rotado.

## Asistente

Sí. Hice una primera versión funcional del add-on.

Archivos generados:

- Bone_Frame_Delta_Analyzer.py

- Bone_Frame_Delta_Analyzer.zip

El plugin está pensado específicamente para casos como tu ejemplo. Blender maneja las rotaciones quaternion como WXYZ, así que analiza esos cuatro componentes frame por frame.

Por ejemplo, puede producir algo de este estilo:

hombro w F0 a F3:

```text
******************
0,988686 (frame 0) menos 0,000027 = frame 1
0,988659 (frame 1) más 0,000014 = frame 2
0,988673 (frame 2) más 0,000012 = frame 3
0,988685 (frame 3)
```

Incluí estas funciones:

- Elegir Start, End y Step.

- Analizar: hueso activo, huesos seleccionados o todos los huesos.

- Quaternion: W, X, Y, Z.

- Opcionalmente también Location XYZ y Scale XYZ.

- Elegir cantidad de decimales.

- Punto o coma decimal.

- Resultado en español o inglés.

- Copiar resultado al portapapeles.

- Exportarlo como .txt.

- Genera automáticamente un Text Block de Blender llamado Bone_Frame_Deltas.txt.

- Restaura el frame original después del análisis.

También agregué dos formas de medir la rotación:

Rotation Channel es la que usaría para tu caso. Lee la rotación propia del hueso y es la más cercana a los valores W/X/Y/Z que ves en una animación.

Evaluated Pose obtiene la orientación final del hueso después de que Blender haya aplicado padres, constraints, etc.

Hay además una opción importante llamada Prevent Quaternion Sign Flips. Está activa por defecto y evita que una rotación pase artificialmente de:

```text
(0.988, 0.008, 0.005, 0.150)
```

a:

```text
(-0.988, -0.008, -0.005, -0.150)
```

porque ambos quaternions pueden representar la misma orientación, pero una resta normal mostraría falsamente un cambio gigantesco.

Cómo usarlo

Instalás el .py o .zip desde Blender, activás Bone Frame Delta Analyzer, seleccionás el Armature y luego el hueso.

En el viewport:

N → Animation → Bone Frame Delta

Por ejemplo:

```text
Start: 0
End: 3
Step: 1
Bones: Active Bone
Rotation Source: Rotation Channel
Quaternion WXYZ: ✓
Decimals: 6
Report Language: Español
```

y presionás Analyze Frame Deltas.

La sintaxis del .py también quedó comprobada antes de entregártelo.

Creo que para el trabajo que estamos haciendo con las animaciones de T3 puede resultar especialmente útil, porque después podemos evolucionarlo para que además compare directamente dos animaciones .anm o dos Actions de Blender y nos diga exactamente qué huesos tienen diferencias y cuánto difieren frame por frame.

## Usuario 2026-08-02 04:33:58Z

esto equivale a 0? -1.09419e-08

## Asistente

Prácticamente sí.

-1.09419e-08 significa:

```text
-0.0000000109419
```

Es un valor extremadamente cercano a 0, normalmente producto de precisión de coma flotante. Para la mayoría de análisis de animación, lo podés tratar como 0.

## Usuario 2026-08-02 04:46:41Z

funciona. ahora me gustaria que las diferencias sean leidas y aplicadas por ejemplo

si yo exporto:

```text
right_wrist w F0 a F3:
**********************
0.993578 (frame 0) más 0.000452 = frame 1
0.994030 (frame 1) menos 0.000113 = frame 2
0.993917 (frame 2) menos 0.000218 = frame 3
0.993699 (frame 3)
```

Me gustaria poder editar el archivo asi:

```text
left_wrist w F0 a F3:
**********************
0.993578 (frame 0) más 0.000452 = frame 1
0.994030 (frame 1) menos 0.000113 = frame 2
0.993917 (frame 2) menos 0.000218 = frame 3
0.993699 (frame 3)
```

Cosa de que si hay un hueso llamado left_wrist por ejemplo las cifras de diferencia como \"0.000452\" por ejemplo se sumen o resten al o a los huesos marcados por el texto exportado y editado.

## Asistente

Sí, entiendo el flujo: el .txt pasa a ser una especie de “plantilla de movimiento”. Si cambiás right_wrist por left_wrist, el importador buscará left_wrist y aplicará solo las

diferencias más/menos, partiendo del valor que ese hueso ya tenga en el primer frame. Así no copia necesariamente la pose inicial del otro hueso, sino su movimiento relativo.

## Asistente

Además voy a hacer que el nombre del hueso se tome de cada encabezado, no del bloque [right_wrist]. Así podés editar solamente right_wrist w... → left_wrist w... (y lo mismo para X/Y/Z), y ese será el hueso que recibe esa componente. Si el hueso no existe, el importador lo salta y lo informa.

## Asistente

Ya está resuelta la parte delicada del formato: el lector acepta más/menos, plus/minus, punto o coma decimal y también notación científica como -1.09419e-08. El valor absoluto escrito a la izquierda se conserva como referencia, pero por defecto no se copia; se usa el valor inicial del hueso destino y se acumulan los deltas.

## Asistente

Sí. Actualicé el plugin a v1.1.0 para hacer exactamente eso.

Archivos generados:

- Bone_Frame_Delta_Analyzer_v1.1.0.zip

- Bone_Frame_Delta_Analyzer.py

Ahora el flujo puede ser:

```text
right_wrist w F0 a F3:
**********************
0.993578 (frame 0) más 0.000452 = frame 1
0.994030 (frame 1) menos 0.000113 = frame 2
0.993917 (frame 2) menos 0.000218 = frame 3
0.993699 (frame 3)
```

Lo editás a:

```text
left_wrist w F0 a F3:
**********************
0.993578 (frame 0) más 0.000452 = frame 1
0.994030 (frame 1) menos 0.000113 = frame 2
0.993917 (frame 2) menos 0.000218 = frame 3
0.993699 (frame 3)
```

Y usás el nuevo botón:

Apply Edited Delta TXT → Import / Apply Delta TXT

El plugin buscará left_wrist y, por defecto, hará conceptualmente:

```text
left_wrist frame 0 = valor que YA tiene left_wrist
```

frame 1 = frame 0 + 0.000452

frame 2 = frame 1 - 0.000113

frame 3 = frame 2 - 0.000218

Es decir, transfiere el movimiento relativo, no la pose inicial de right_wrist.

Esto funciona independientemente para Quaternion W, X, Y, Z, Location XYZ y Scale XYZ.

El nombre que manda es el de cada encabezado, así que incluso podrías hacer algo como:

```text
left_wrist w F0 a F3:
```

...

```text
left_wrist x F0 a F3:
```

...

```text
left_wrist y F0 a F3:
```

...

```text
left_wrist z F0 a F3:
```

...

y transferir todo el movimiento quaternion de right_wrist a left_wrist.

También agregué Use TXT Start Value. Está desactivado por defecto:

- OFF: conserva la posición/rotación inicial del hueso destino y copia solamente las diferencias. Es lo que describiste.

- ON: también usa el valor absoluto inicial escrito en el TXT, por lo que se acerca a copiar los valores originales completos.

Si un hueso escrito en el TXT no existe, no rompe la importación: lo omite y Blender te informa cuál faltó.

## Usuario 2026-08-02 05:00:23Z

donde esta el boton de apply edited txt

## Asistente

Está abajo de todo en el mismo panel:

Viewport 3D → N → pestaña Animation → Bone Frame Delta

Después de los botones:

- Analyze Frame Deltas

- Copy Results

- Export Results as TXT

- Show Results

debería aparecer una sección:

Apply Edited Delta TXT

y dentro el botón:

Import / Apply Delta TXT

Si no te aparece, casi seguro Blender sigue teniendo cargada la versión anterior del plugin. En ese caso:

```text
1. `Edit → Preferences → Add-ons`
2. Buscá **Bone Frame Delta Analyzer**
3. Desactivá/eliminá la versión anterior.
4. Instalá el `Bone_Frame_Delta_Analyzer_v1.1.0.zip`.
5. Volvé a activarlo.
```

No hace falta descomprimir el ZIP.

## Usuario 2026-08-02 05:42:08Z

tambien quiero que sea capaz de seleccionarse todos los huesos y exporte e importe sus transformaciones de huesos a lo seleccionado. Pero no necesariamente exporte e importe los diferencias de distancia entre cifras.

## Asistente

Sí. Voy a ampliar el add-on con un segundo flujo separado de los deltas: Transformaciones absolutas. Así podrás exportar W/X/Y/Z, Location y Scale de varios huesos y luego importarlas directamente sobre los huesos seleccionados, sin calcular diferencias entre frames.

## Asistente

Lo voy a dejar más flexible: habrá un modo Absolute Transform TXT con dos formas de importación: por nombre de hueso, o directamente sobre los huesos seleccionados. En este último, si el TXT contiene un solo hueso, su animación podrá aplicarse a todos los seleccionados; si contiene varios, se emparejan en orden.

## Asistente

Sí. Agregué ese segundo sistema sin reemplazar el de diferencias.

Archivos generados:

- Bone_Frame_Delta_Transform_Tool_v1.2.0.zip

- Bone_Frame_Delta_Transform_Tool_v1.2.0.py

Ahora hay dos secciones independientes:

Frame Delta TXT

- Sigue haciendo lo anterior.

- Exporta diferencias más/menos.

- Permite editar nombres como right_wrist → left_wrist.

- Puede volver a aplicar esos deltas.

Absolute Transform TXT

- No calcula distancias ni diferencias.

- Exporta directamente para cada frame:

- Rotation Quaternion W X Y Z

- Location X Y Z

- Scale X Y Z

- Podés usar Active Bone, Selected Bones o All Bones.

Por ejemplo el TXT absoluto se ve conceptualmente así:

```text
BEGIN_BONE right_wrist
FRAME 0
ROT 0.993578 0.034500 0.021300 0.102300
LOC 0.000000 0.000000 0.000000
SCALE 1.000000 1.000000 1.000000
```

```text
FRAME 1
ROT 0.994030 0.032100 0.022000 0.098400
LOC 0.000100 0.000000 -0.000200
SCALE 1.000000 1.000000 1.000000
END_BONE
```

Importar a huesos seleccionados

En:

Absolute Transform TXT → Import Target

tenés:

Bone Names from TXT

Busca los huesos usando sus nombres originales.

o:

Selected Bones

Este es el modo que pedías.

Si el TXT tiene un solo hueso y seleccionás, por ejemplo:

```text
left_wrist
left_hand
```

weapon_bone

la misma transformación/animación se copia a los tres.

Si el TXT contiene varios huesos:

```text
source_1
source_2
source_3
```

y seleccionás tres huesos destino:

```text
target_1
target_2
target_3
```

se emparejan:

```text
source_1 → target_1
source_2 → target_2
source_3 → target_3
```

siguiendo el orden de los huesos dentro del Armature.

También podés seleccionar todos los huesos, poner:

Bones → Selected Bones

y exportar sus transformaciones completas frame por frame.

Para importar, el plugin crea los keyframes correspondientes automáticamente. La rotación importada se establece en Quaternion, para conservar directamente W/X/Y/Z.

## Usuario 2026-08-09 01:10:13Z

dame un pdf de este chat

PDF generado a partir de la conversación solicitada.
