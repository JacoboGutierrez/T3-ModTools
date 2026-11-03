# T3CleverTools — transparencia (2026-10-12)

## Uso

T3CleverTools 0.2.0 incorpora **Transparency** en ambos paneles de material.
Al activarla aparece **Amount (%)**, editable numéricamente: 0 conserva la
opacidad y 100 hace invisible la superficie. El valor inicial es 50. Se puede
combinar con Autoiluminación. Los ajustes se guardan en el `.blend`.

La vista previa funciona en Material Preview/Rendered mediante una mezcla con
Transparent BSDF. Conserva el grafo original y restaura los nodos/configuración
de render al desactivar la opción. La autoiluminación se aplica dentro de esa
mezcla, y no se duplican nodos al actualizar.

Para el juego, exportar con SCA 0.8.0 / LOD 0.3.0 y compilar con la versión
actualizada de ModTools. El generador de WM32 toma el ajuste directamente del
Blender guardado. ModTools detecta materiales marcados en los SCA/LOD ganadores
del orden de carga y añade automáticamente soporte al ejecutable generado.
Reiniciar Blender y ModTools si estaban abiertos al instalar esta actualización.

LOD Importer 0.2.0 y la conversión SCA/LOD a glTF preservan el ajuste. Los
complementos instalados en Blender 5.2 fueron actualizados; copias anteriores
en `output/clever_transparency_20261012/installed_backup`.

## Contrato de exportación

- `t3_transparency_enabled`: booleano independiente de la emisión.
- `t3_transparency_amount`: porcentaje flotante 0–100 (50 por defecto).
- Dentro de `Shader`, `T3Transparency N`, donde N = round(porcentaje × 255/100).
  Es una extensión de ModTools, **no un campo nativo de T3 vanilla**.
- Shaders soportados: BASE, DIFFUSE, DIFFUSE_SPECULAR. Otros shaders o valores
  inválidos se rechazan antes de generar el parche.
- La textura original se conserva. Alfa efectivo = alfa de textura ×
  (255−N)/255. No se hornean texturas nuevas ni se cambian UV/coordenadas.
- Los exportadores colocan las submallas transparentes después de las opacas
  dentro de cada malla. Esto no es ordenación global por profundidad: cristales
  superpuestos/intersectados pueden necesitar ajustes del modelo.
- Es transparencia alfa simple; no implementa refracción ni espesor físico.

## Evidencia del motor

**CONFIRMADO por PDB y desensamblado** del T3.exe SHA-256
`52f68d5df4912aba662f0371a06ae0b1ec447ef4b7338460224b20904eb0f061`:

- `ShaderLoader` en 0x554F80 no reconoce transparencia gradual. El hook se
  instala en 0x554FFC y conserva la ruta original para todos los demás tokens.
- `cShaderData`: Shader +0, ShaderSave +4, basetexture +8, basetexture_uvset +12,
  lightmap +16, lightmap_uvset +20, detailtexture +24, macrotexture +28,
  Uadd +32, Vadd +36, Color +40. El cargador inicializa Color a cero.
- BASE/DIFFUSE/DIFFUSE_SPECULAR deshabilitan ALPHABLENDENABLE. BASE y DIFFUSE
  usan prueba alfa con umbral 120; bajar el alfa de una imagen no aporta la
  transparencia gradual solicitada.
- Las llamadas DrawIndexedPrimitive de esas tres rutas están en 0x517F53,
  0x5182CE y 0x5184DB. EDI conserva el puntero cShaderData en las tres.
- Color no se usa en esos tres draws, pero sí lo sobrescribe el renderizado de
  sombras. **No sirve para persistir la transparencia** (ver corrección debajo).
  La extensión usa el padding +13..+15 del shader: opacidad en +13, firma
  `0x5433` en +14..+15. Conserva el byte UV en +12 y todos los campos nombrados.
- La extensión compara tokens byte a byte, limita 0–255 y no altera la ruta de
  materiales sin marcador. Opacidad 255 sigue el renderizado nativo.

`t3_material_runtime.py` genera código en la sección exclusiva `.t3ldr`, después
de la extensión ANM si existe. Valida hash completo, bytes originales y anclas
únicas. No usa huecos/globals del ejecutable ni modifica T3.exe/Ai.dll originales.

El wrapper guarda seis render states y cinco texture-stage states, configura
SRCALPHA/INVSRCALPHA, desactiva escritura de profundidad/prueba alfa y multiplica
alfa de textura por opacidad mediante TFACTOR. Restaura todos los estados después
del draw, también su HRESULT, pila y registros no volátiles. Si falla una
consulta de estado, usa la ruta nativa antes de modificar estados.

## Pruebas y alcance

- Ocho pruebas de CleverTools en Blender 5.2.2 LTS: persistencia, nodos,
  coexistencia con emisión, importación/exportación SCA/glTF/LOD.
- Dos pruebas del generador WM32: submalla adicional transparente, menú,
  cuatro LOD, textura y geometría preservadas, Blender fuente intacto.
- Seis pruebas del soporte nativo: emulación x86 del parser/wrapper,
  transparencia 0/intermedia/100, materiales normales, restauración de estados,
  argumentos y registros, huellas/anclas, rechazo de formatos inválidos y
  compilación temporal combinada con ANM.
- Suite general antes del último test de rechazo: 279 pruebas sin fallos,
  19 omitidas. Las pruebas Blender se ejecutaron por separado.

Registros en `output/transparency_*tests.log`, `output/transparency_suite.log`;
símbolos y desensamblado en `output/transparency_*.txt`. Instalación y hashes en
`output/clever_transparency_20261012/installation.json`.

**OBSERVADO por el usuario:** transparencia correcta inicialmente en primera
persona. La versión inicial la perdía después de pasar a tercera persona.
La extensión solo se instala si hay materiales marcados.

## Corrección del generador WM32: material sin imagen

El diagnóstico `diagnostic_jdtb9udu.log` señaló `mat_counter`, un Principled
sin nodo de imagen, con transparencia al 70 %. `mat_gun_alpha` tenía una imagen
válida y transparencia al 80 %. El generador asumía que todos los materiales
tenían una textura y rechazaba el color uniforme del contador.

Ahora WM32 convierte el color uniforme a una TGA BGRA de 1×1, con RGB convertido
de lineal a sRGB y alfa conservado. Su nombre deriva de los bytes de color para
compartirla entre materiales idénticos. La misma textura se publica para arma y
menú; no se agregan nodos ni se guarda el Blender fuente. Los grafos ambiguos o
procedurales que requieren horneado siguen produciendo un error descriptivo.

Tres pruebas Blender de WM32 verifican el caso actual, los bytes/color/tamaño de
la textura, conservación de nodos, submallas, transparencia, geometría y fuente.
Registros: `output/wm32_material_fix/solid_color_tests.log` y
`output/wm32_material_fix/solid_color_build.log`.

Compilación completa posterior correcta: se verificaron los archivos dentro de
Mods.Cod, valores 204 (80 %) y 178 (70 %), textura uniforme publicada y extensión
de transparencia incluida en T3_Modded.exe. Hashes del Blender, opciones del arma,
orden de carga y originales preservados. Evidencia:
`output/wm32_material_fix/solid_color_evidence.json`. La comprobación visual
dentro del juego fue confirmada por el usuario en primera persona.

## Corrección: pérdida al cambiar primera/tercera persona

**OBSERVADO:** la transparencia desaparecía en tercera persona y no volvía al
regresar a primera; reaparecer la restauraba. La emisión se conservaba.

**CONFIRMADO por PDB, desensamblado y emulación:** `cPlayerShadow::Render`
(0x4EC610) escribe Color en las submallas del personaje (0x4ECA0A) y del arma
(0x4ECB73), sustituye Shader por 1 y luego restaura únicamente Shader. Los
bucles terminan en 0x4ECA65/0x4ECBD4 y restauran en 0x4ECA70..0x4ECACA y
0x4ECBFA..0x4ECC50. `cVehicleShadow::Render` también modifica Color. Por eso
la implementación inicial destruía su propio marcador al proyectar sombras.

El arreglo mueve el dato a tres bytes de padding, sin cambiar tamaño/layout del
shader ni sus campos. El inicializador 0x554FE0 pasa de `mov byte [eax+12],bl`
a `mov dword [eax+12],ebx` (EBX=0), inicializando también el padding para evitar
marcadores residuales al cargar otro material. La asignación UV nativa en
0x5554B7 sigue escribiendo un byte. `cShaderData::operator=` (0x4085C0) y
`cSubMesh::Clone` (0x514E40) copian los 44 bytes completos, incluido el padding.
Color queda disponible para las sombras; no se modifica ese renderizado.

La regresión ejecuta los bucles originales de sombras del personaje y del arma,
su restauración y la asignación nativa del shader antes de verificar el draw
transparente. Comprueba opacidad normal/intermedia/cero, datos UV, Color,
restauración D3D y coexistencia con la extensión ANM. Seis pruebas pasan.

Compilación completa realizada. Verificación posterior correcta de los bytes
de la extensión, inicialización y tres hooks de draw en T3_Modded.exe, además
de SCA/LOD/texturas en Mods.Cod. El verificador antiguo esperaba una sola
submalla BASE; el Blender actual también tiene dos contadores emisivos. Esa
aserción posterior al build se corrigió en el verificador específico para
comparar con el reporte actual, sin cambiar los materiales del usuario.
Antes de esa aserción ya se había confirmado que los hashes de originales,
Blender, opciones y orden de carga no cambiaron durante la compilación.
Evidencia: `output/wm32_material_fix/camera_transparency_build.log`,
`verify_camera_transparency.py` y `camera_transparency_evidence.json`.

**PENDIENTE:** confirmación visual en una partida nueva usando el ejecutable
recompilado, secuencia primera → tercera → primera, sin morir/reaparecer.
