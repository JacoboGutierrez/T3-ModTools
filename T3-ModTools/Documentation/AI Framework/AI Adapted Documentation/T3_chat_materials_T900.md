# Chat de T3 Modding: materiales reflectivos

T900S, T900Heavy, FK y modelos FPS - conversación del 3 al 9 de agosto de 2026

Transcripción preparada en PDF. Se conservaron los valores de materiales, rutas de archivos y conclusiones técnicas del hilo.

## Usuario · 03/08/2026 00:37

como puedo hacer que el material de los T900 sea mas reflectivo y menos difuso?

## ChatGPT

Sí. En los T900 conviene tocar el specular del material, no simplemente aclarar la textura: así el metal responde más a las luces y deja de verse “mate”.

Revisando los archivos originales, el T900 usa:

```text
CA/textures/t900.mat
```

y su contenido original es:

```text
1 1 20
```

Tanto el T900S como el T900Heavy usan en el cuerpo:

```text
Shader
{
Type DIFFUSE_SPECULAR
BaseTexture "t900.tga"
}
```

El exporter SCA conserva DIFFUSE_SPECULAR, pero no exporta Roughness/Metallic de Blender. Por eso tocar Roughness en Blender no cambia realmente el material dentro de T3.

Comparando otros .mat del juego, parecía razonable interpretar el formato como Diffuse / Specular / Power. Para un T900 más metálico, una primera prueba sugerida fue:

```text
0.65 1 45
```

o algo más extremo:

```text
0.45 1 70
```

También se propuso probar distintos valores y, a futuro, agregar soporte de .mat al T3 Asset Tool.

## Usuario · 03/08/2026 00:52

no se si veo mas reflejos pero el modelo se ve oscuro con esto "0.65 1 45" y aun mas oscuro con esto "0.45 1 70"

## ChatGPT

Eso confirma bastante bien que bajar el primer número reduce la iluminación general/difusa del material, por eso el T900 se oscurece.

La recomendación pasó a ser mantener el primer valor en 1 y aislar los otros dos. Se sugirió probar:

```text
1 1 5
1 1 10
1 1 20 // original
1 1 40
```

Además, se propuso ensayar valores de specular superiores a 1:

```text
1 1.5 10
1 2 10
```

También se observó que T3.exe contiene referencias a CUBEMAP y a vectores de reflexión, por lo que el motor podría soportar un camino separado para reflejos de entorno más parecidos a cromo, distinto del brillo DIFFUSE_SPECULAR.

## Usuario · 03/08/2026 01:26

lo que estuve viendo es que solo altero el .material del t900s el t900heavy no lo estoy viendo con cambios de material. debe ser por que un mod mio tiene al t900heavy usando la textura t900_heavy.tga mientras que el t900s usa la textura t900.tga.

## ChatGPT

Sí, eso explica el comportamiento. En el juego original existe:

```text
CA/textures/t900.mat
CA/textures/t900.dds
CA/textures/t900_sillum.dds
CA/textures/t900_sillumB.dds
```

No existe originalmente t900_heavy.mat porque el T900Heavy original reutiliza t900 como textura principal.

Si el mod cambió el Heavy a:

```text
BaseTexture "t900_heavy.tga"
```

entonces lo lógico es usar un material separado:

```text
CA/textures/t900_heavy.mat
```

Así puede quedar:

```text
T900S
BaseTexture "t900.tga"
↓
t900.mat
```

```text
T900Heavy
BaseTexture "t900_heavy.tga"
↓
t900_heavy.mat
```

Esto permite experimentar con el Heavy sin alterar el T900S.

## Usuario · 03/08/2026 01:45

bien! los terminators quedan bien con la siguiente configuracion en material. 1 12 18, El 12 es el brillo y el 18 el control del diffuse. Donde esta el mat del Fk?

## ChatGPT

Quedó establecido por prueba visual que la configuración que funciona bien es:

```text
1 12 18
```

con 12 como brillo y 18 como control del diffuse.

El FK usa la textura 017.tga. En su modelo aparece:

```text
CA/casts/Fk/tps/model.sca
```

con:

```text
Shader
{
Type DIFFUSE_SPECULAR
BaseTexture "017.tga"
}
```

Por lo tanto, su material está en:

```text
CA/textures/017.mat
```

y el valor original es:

```text
1 1 20
```

La textura correspondiente es:

```text
CA/textures/017.dds
```

Para darle al FK el mismo acabado, se puede probar:

```text
1 12 18
```

## Usuario · 03/08/2026 11:20

sabes si los modelos de primera persona (las manos) que estan en CA\casts\T900S\fps\ y CA\casts\T900Heavy\ son afectados por el archivo .mat?

## ChatGPT

Sí. Se comprobó directamente en los model.sca originales. Tanto:

```text
CA/casts/T900S/fps/model.sca
```

como:

```text
CA/casts/T900Heavy/fps/model.sca
```

usan:

```text
Shader
{
Type DIFFUSE_SPECULAR
BaseTexture "t900.tga"
}
```

Los dos archivos FPS originales son idénticos byte por byte. Por lo tanto, las manos FPS de ambos Terminators son afectadas por:

```text
CA/textures/t900.mat
```

Con la configuración:

```text
1 12 18
```

se modifican simultáneamente T900S TPS, T900S FPS, T900Heavy FPS y cualquier otro modelo DIFFUSE_SPECULAR que use t900.tga.

En cambio, el T900Heavy TPS modificado queda separado al usar t900_heavy.tga y t900_heavy.mat.

Si se quiere separar también las manos del Heavy, se puede editar CA/casts/T900Heavy/fps/model.sca y cambiar BaseTexture de t900.tga a t900_heavy.tga.

## Usuario · 09/08/2026 01:09

dame un pdf de este chat

### Resumen técnico consolidado

La prueba práctica del hilo dejó como configuración visual satisfactoria para los Terminators 1 12 18, identificando 12 como brillo y 18 como control del diffuse. El T900S usa t900.mat; el T900Heavy modificado puede usar t900_heavy.mat si su BaseTexture es t900_heavy.tga. El FK usa CA/textures/017.mat. Los modelos FPS originales de T900S y T900Heavy usan t900.tga, por lo que ambos responden a CA/textures/t900.mat salvo que se cambie explícitamente el BaseTexture del Heavy FPS.
