# T3CleverTools — atributos de materiales

Fecha: 2026-10-12. Versión inicial: 0.1.0.

## Instalación

1. En Blender, abre Preferencias → Complementos → Instalar desde disco y elige
   `T3-ModTools/Blender Plugins/T3CleverTools.zip`. También puede instalarse el
   archivo independiente `T3CleverTools.py`; instala solo una de las dos versiones.
2. Activa **T3CleverTools**.
3. Actualiza también **T3 SCA Model Exporter** usando
   `T3-ModTools/Blender Plugins/T3_Blender_SCA_Exporter.py`, versión 0.7.0.
   Es necesario para guardar correctamente las casillas activadas y desactivadas.
   El exportador LOD actual ya respeta el atributo del material.

## Uso

- Importa el T900 mediante T3 Rigged glTF Importer o T3 LOD Importer.
- Abre **Propiedades → Material → T3CleverTools**, o **Vista 3D → N → T3 →
  T3CleverTools**. El segundo panel muestra los materiales de la malla activa;
  si seleccionas el armature, muestra los materiales de sus mallas asociadas.
- La casilla **Autoiluminación (sillum)** refleja el atributo que ya trae el
  material importado. Activarla lo prepara como autoiluminado; desactivarla
  devuelve la iluminación normal. No hay que renombrar materiales ni texturas.
- **Actualizar vista previa** aplica la visualización a materiales ya importados.
  Al modificar una casilla se actualiza automáticamente su vista previa.
- Exporta con **T3 Model (.sca)** o **T3 LOD (.lod)**. La propiedad queda en el
  material y se conserva en `.blend`, aunque el complemento se desactive.

La autoiluminación usa el color de la textura del material. No crea luces que
iluminen otras superficies, ni agrega un halo, bloom, color o intensidad nueva al
formato del juego. La vista previa en Blender es una aproximación de esa propiedad.

Los materiales compartidos afectan a todos sus usuarios; el panel lo indica.
Los materiales vinculados no editables requieren una copia local. Cada LOD puede
tener materiales independientes: ajusta también los niveles de distancia que
quieras cambiar. El complemento no sincroniza automáticamente materiales distintos
solo porque tengan nombres o texturas parecidas.

Los materiales sin metadatos T3 se indican como tales. Al activarlos se asigna
el atributo. La detección nunca toma la palabra `sillum` del nombre como prueba.
Para grafos personalizados que no tengan Principled conectado a la salida, el
atributo de exportación funciona, pero el complemento no reescribe su vista previa.

## Contrato y evidencia

**CONFIRMED — archivos originales:** en Game.cod, T900S TPS model.sca y sus cuatro
niveles de model.lod usan `DIFFUSE_SPECULAR` para `t900.tga` y `BASE` para
`t900_sillum.tga`. La propiedad editada reproduce ese contrato del material de
luces del T900. ShaderLoader fue localizado mediante T3.pdb en 0x554F80; no se
modificó el motor ni se añadieron nuevos shaders.

**OBSERVED — usuario:** las luces y ojos de los T900 con materiales sillum son el
efecto visual deseado. **UNKNOWN:** la comprobación visual en una partida con un
modelo editado mediante esta versión queda pendiente. No se generalizan campos
desconocidos de `.mat` como parámetros de emisión PBR.

`t3_shader_type` es la fuente de verdad, compartida por los importadores y
exportadores. `Material.t3_clever_emissive` usa un getter y setter sobre ella:

| Acción | Shader exportado |
| --- | --- |
| Autoiluminación activada | `BASE` |
| Desactivada en un BASE importado | `DIFFUSE_SPECULAR` |
| Activar y volver a desactivar un material normal | Restaura su shader anterior |
| Material nuevo sin metadatos, exportación SCA | `DIFFUSE_SPECULAR` |

El shader anterior se guarda en `t3_clever_unlit_previous_shader`. La vista previa
añade nodos identificados por `t3_clever_role`, conserva la superficie original
conectada a un wrapper y reutiliza la textura/color del Principled. Desactivar
restaura la conexión y elimina únicamente los nodos del complemento. Una conexión
de salida modificada por el artista no se reemplaza durante esa restauración.

**Corrección de exportador:** SCA 0.6.0 escribía `Type BASE` incondicionalmente.
SCA 0.7.0 respeta `t3_shader_type`, valida que sea un token y usa
`DIFFUSE_SPECULAR` cuando no hay metadatos. No modifica transformaciones,
geometría, huesos, UV ni selección de texturas. LOD ya leía esta propiedad y no
requirió cambios. El exportador específico de modelos de menú mantiene su
contrato separado; esta integración corresponde a T3 Model SCA y T3 LOD.

## Verificación

Pruebas: `T3-ModTools/AI Framework/Automated Tests/test_t3_clever_tools.py`.
Seis pruebas ejecutadas correctamente en **Blender 5.2.2 LTS**, en un proceso
separado con configuración de fábrica:

- shaders leídos de SCA y LOD originales;
- exportación normal por defecto y rechazo de tokens inválidos;
- detección por metadatos, textura conectada a la vista previa, idempotencia y
  restauración del grafo original;
- persistencia del atributo en un `.blend`;
- T900S original → glTF de ModTools → importador Blender → SCA: detección y cambio
  de ambos materiales; los dos archivos difieren solo en los shaders;
- T900S LOD original → Blender → LOD: ocho materiales independientes de cuatro
  niveles; los archivos antes/después difieren solo en los shaders.

Mínimo declarado del complemento: Blender 3.6; prueba ejecutada en 5.2.2, no en
todas las versiones intermedias. Evidencia y hashes en
`output/t3_clever_tools_20261012/evidence.json`. Los archivos originales se leen
directamente de los COD y no se sobrescriben.

Suite completa de ModTools: **271 pruebas sin fallos, 15 omitidas**. Las cuatro
pruebas que requieren bpy se ejecutaron además con Blender real y pasaron.
El ZIP instalable fue contrastado byte por byte con el código fuente probado.

Los OBJ u otros formatos que no conserven `t3_shader_type` no permiten deducir
el atributo original con certeza. Usa el glTF rigged de ModTools o el importador
LOD para conservar esa información; en otros casos el panel permite asignarla
manualmente y señala que no había datos T3.

## Integración con el generador WM32 (2026-10-12)

**CONFIRMADO:** el `.blend` de WM32 se exporta mediante el generador específico
`T3/mods/wm32_plasma/asset_build.py`; actualizar el exportador SCA del complemento
no cambia por sí solo ese proceso.

La compilación fallaba en `runtime_patch.py` porque exigía seis submallas SCA y
24 LOD. Asignar ocho polígonos a `material_sight_reddot` crea una séptima
submalla válida. Ahora el validador usa el informe de exportación y verifica
geometría, shader, textura y existencia de cada textura en todos los niveles.

También se corrigieron dos supuestos del generador:

- Respeta `t3_shader_type`, con `DIFFUSE_SPECULAR` por defecto y `BASE` para la
  autoiluminación activada desde T3CleverTools.
- Resuelve la imagen conectada al color del Principled, incluso con el wrapper
  de vista previa. El nombre del material ya no decide qué textura usar.
  La mira conserva `wm32_alpha.tga`; antes su nombre sin «alpha» la asociaba
  incorrectamente con `wm32.tga`.

Las imágenes adicionales reciben nombres de archivo derivados de su imagen,
con prefijo WM32; se rechazan imágenes ambiguas y colisiones de nombres.
El modelo de menú conserva su contrato BASE y referencias de textura propias.
El proceso lee el Blender guardado sin volver a guardarlo.

Regresión: `AI Framework/Automated Tests/test_wm32_materials.py`, ejecutada en
Blender 5.2.2 LTS. Comprueba subdivisión adicional por material, conservación de
coordenadas/normales/UV, SCA, cuatro niveles LOD, menú y alternancia de
autoiluminación con los nodos reales de T3CleverTools.

Verificación posterior: compilación completa con el orden de mods habilitados
correcta y generador sin `--write` sincronizado. El paquete contiene siete
submallas SCA y 28 LOD; la mira usa `BASE` y `wm32_alpha.tga`. Hashes del Blender,
opciones del arma, orden de carga y archivos vanilla preservados. Evidencia:
`output/wm32_material_fix/evidence.json`. Suite general: 273 pruebas, sin fallos,
17 omitidas; las dos pruebas nuevas que requieren Blender pasaron por separado.
La apariencia final en el juego queda pendiente de comprobación visual.
