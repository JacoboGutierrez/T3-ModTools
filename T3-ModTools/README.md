# T3-ModTools

**Version 0.6.9**
Experimental asset extraction, conversion, and mod management tool for **Terminator 3: War of the Machines (PC)**.

[Español](#español)

## What is T3-ModTools?

T3-ModTools is a Windows application designed to make the game's files easier to inspect and to provide a safer, organized way to install and combine mods.

The application has two main modes:

- **Asset Extraction** reads the game's ZIP-compatible COD archives and extracts selected content such as characters, vehicles, weapons, maps, menu models, effects, audio, and animations. It can also create working conversions of supported models, including OBJ/MTL files for static geometry and glTF 2.0 files for compatible rigged models.
- **Modding** manages independent mod projects, their enabled state, and their load order. It combines the files from enabled projects into `modtools_data/Mods.Cod` and creates a separate `T3_Modded.exe` that loads the compiled package before the original game archives.

The original `T3.exe` is not modified. Each build recreates `T3_Modded.exe` from the original executable, allowing the unmodified game to remain available.

## Live technical debug

In **Modding → Live debug**, set the duration and leave the panel open (ModTools
can be minimized). In a running match, **Ctrl+Shift+F9** starts or stops capture.
The default is 120 seconds with 100 ms polling. Alternative keys: F8/F10/F11.
Reports are saved in `<game>/modtools_data/debug/<timestamp-id>/`, including
sampled weapons, ammo, fire requests, sound state, build context and errors.
The capture reads memory without modifying the game or changing its focus.
Polling may miss brief events; assigned audio channels do not prove audibility.
See [README.txt](README.txt) for supported builds, limits and report details.

**Español:** En **Modding → Debug en vivo**, elegí la duración y dejá el panel
abierto. **Ctrl+Shift+F9** inicia o detiene el registro desde la partida. Podés
minimizar ModTools. Los informes quedan en `modtools_data/debug/` dentro del juego;
el botón «Abrir carpeta del registro» abre la última captura. Solo registra datos
técnicos, sin video ni grabación de audio. Cerrar el panel detiene la captura.

## Main capabilities

- Reads `Game.cod`, patch COD archives, installed game folders, and compatible backup archives.
- Extracts raw game assets by category.
- Converts supported SCA, LOD, and DET geometry to OBJ and MTL.
- Exports compatible rigged character, weapon, and vehicle models to glTF 2.0.
- Extracts native ANM animation files and produces animation metadata.
- Includes experimental Blender import and export plug-ins for supported T3 model and animation workflows.
- Includes T3 Transform Converter for editable pose-transform TXT export, import, time reversal, and optional X mirroring.
- Provides an interface and console messages in English, Spanish, Russian, and Portuguese, with persistent language selection.
- Saves raw runtime-generator output and technical error details in `modtools_data/logs/`
  for Modding mode, or `logs/` inside the extraction output folder. The console points to
  the diagnostic file; original third-party prose and technical values are preserved.
- Creates and manages separate mod projects.
- Creates a standalone mod pack from enabled projects with **Generate mod pack**, directly
  below **Create mod**. Preserves top-first priority and executable targets, validates
  patch compatibility, and records source files and conflicts in a merge report.
- Enables the completed pack and disables its source mods while retaining their folders.
  Use **Build Mods + Modded EXE** to compile the new pack.
- Enables, disables, and reorders mods through a load-order system.
- Resolves duplicate asset paths in favor of the enabled mod highest in the visible load order.
- Compiles enabled project files into `modtools_data/Mods.Cod`.
- Stores `load_order.json` and `.compiled/` build reports in the same `modtools_data/` folder
  inside the game installation, keeping the mods folder for mod projects.
- Keeps a separate load order for each custom mods folder under
  `modtools_data/load_orders/<folder hash>/load_order.json`.
- Builds `T3_Modded.exe` without overwriting the original executable.
- Stores the loader code and package path in a dedicated `.t3ldr` executable section,
  correcting the menu crash caused by the initial 0.6.5 loader placement.
- Supports optional, conservative `T3.exe` and `Ai.Dll` patch manifests and stops the build when incompatible patch writes conflict.
- Builds patched AI code as `A2.Dll`, redirects only `T3_Modded.exe` to it, and preserves the original `Ai.Dll`.
- Uses anchored native byte searches for substantially faster AOB validation across multiple binaries.
- Before compiling, automatically runs `runtime_patch.py --write` for enabled projects that provide that root-level generator, then validates the generated `executable.json`.
- Asset-generating mods can declare `"generates_assets": true`: Rebuild Modded EXE also rebuilds Mods.Cod. The shared `t3_generated_assets` publisher updates staged models, textures, locators and manifests without renaming locked Windows directories, with rollback on publication failure.
- A runtime generator failure stops before the previous `Mods.Cod` and `T3_Modded.exe` are staged; runtime scripts are executable local code and should only be used from trusted projects.

Existing `load_order.json`, `Mods.Cod`, and `.compiled/` files are migrated out of the mods
folder, preserving mod order and enabled states, with backups in
`modtools_data/legacy_backup/<migration ID>/` and rollback on failure. Existing data in the
new location takes priority; older duplicates remain in the backup. For a verified older
`T3_Modded.exe`, migration restores the old loader's original storage and installs the
corrected loader in its dedicated section, preserving the last build's mod patches.
Launching requires the corrected loader. If an older executable cannot be migrated, use
**Build Mods + Modded EXE** with the intended mods enabled before launching. The old archive
is retained until a successful build retires it. This correction remains version 0.6.5.

## Purpose and scope

T3-ModTools is intended for personal modding, preservation, and interoperability research using a legally owned copy of the game. It does not bypass DRM, encryption, online authentication, or anti-cheat systems.

This project is experimental. Some assets or workflows may require target-specific testing, and adding entirely new game content can require configuration or engine research beyond ordinary file replacement.

This README describes the role of the application only. For installation instructions and modding tutorials, see the included [T3 Modding Guide](Documentation/T3-Modding-Guide.pdf).

The source code is distributed under the MIT License. This license applies to T3-ModTools itself, not to extracted game assets. Game assets remain the property of their respective rights holders.

---

# Español

**Versión 0.6.5**
Herramienta experimental de extracción, conversión y gestión de mods para **Terminator 3: War of the Machines (PC)**.

## ¿Qué es T3-ModTools?

T3-ModTools es una aplicación para Windows diseñada para facilitar la inspección de los archivos del juego y proporcionar una forma más segura y organizada de instalar y combinar mods.

La aplicación posee dos modos principales:

- **Extracción de assets** lee directamente los archivos COD del juego, compatibles con ZIP, y extrae el contenido seleccionado, como personajes, vehículos, armas, mapas, modelos de menú, efectos, audio y animaciones. También puede crear conversiones de trabajo de modelos compatibles, incluidos archivos OBJ/MTL para geometría estática y archivos glTF 2.0 para modelos riggeados compatibles.
- **Modding** administra proyectos de mods independientes, su estado de activación y su orden de carga. Combina los archivos de los proyectos activados en `modtools_data/Mods.Cod` y crea un `T3_Modded.exe` separado que carga el paquete compilado antes que los archivos originales del juego.

El archivo `T3.exe` original no es modificado. Cada compilación vuelve a crear `T3_Modded.exe` a partir del ejecutable original, por lo que el juego sin modificaciones continúa disponible.

## Funciones principales

- Lee `Game.cod`, archivos COD de parches, carpetas de instalación del juego y copias de seguridad compatibles.
- Extrae assets originales del juego por categorías.
- Convierte geometría SCA, LOD y DET compatible a OBJ y MTL.
- Exporta modelos riggeados compatibles de personajes, armas y vehículos a glTF 2.0.
- Extrae animaciones ANM originales y genera información sobre ellas.
- Incluye complementos experimentales de Blender para procesos compatibles de importación y exportación de modelos y animaciones de T3.
- Incluye T3 Transform Converter para exportar e importar transformaciones editables mediante TXT, invertir el tiempo y aplicar mirror en X opcional.
- Ofrece la interfaz y los mensajes de consola en inglés, español, ruso y portugués, y recuerda el idioma seleccionado.
- Guarda la salida original de los generadores y los detalles técnicos de los errores en
  `modtools_data/logs/` en el modo Modding, o en `logs/` dentro de la carpeta de extracción.
  La consola indica el archivo de diagnóstico; los textos de terceros y los valores
  técnicos conservan su forma original.
- Crea y administra proyectos de mods separados.
- Crea un paquete independiente con los proyectos habilitados mediante **Generar paquete de
  mods**, debajo de **Crear mod**. Conserva la prioridad de arriba hacia abajo y el destino
  de los parches, valida su compatibilidad y registra archivos y conflictos en un informe.
- Activa el paquete terminado y desactiva sus mods de origen conservando sus carpetas.
  Usá **Compilar Mods + EXE modificado** para compilar el nuevo paquete.
- Permite activar, desactivar y ordenar mods mediante un sistema de orden de carga.
- Resuelve rutas de assets duplicadas a favor del mod habilitado que está más arriba en el orden de carga visible.
- Compila los archivos de los proyectos activados en `modtools_data/Mods.Cod`.
- Guarda `load_order.json` y los informes de compilación de `.compiled/` en la misma carpeta
  `modtools_data/`, dentro de la instalación del juego, dejando la carpeta de mods para los proyectos.
- Mantiene un orden de carga separado para cada carpeta de mods personalizada en
  `modtools_data/load_orders/<hash de carpeta>/load_order.json`.
- Genera `T3_Modded.exe` sin sobrescribir el ejecutable original.
- Guarda el código del cargador y la ruta del paquete en una sección ejecutable `.t3ldr`
  propia, corrigiendo el cierre del menú causado por la ubicación inicial del cargador en 0.6.5.
- Admite manifiestos opcionales y conservadores para `T3.exe` y `Ai.Dll`, y detiene la compilación cuando dos modificaciones incompatibles intentan escribir sobre la misma zona.
- Genera el código de IA modificado como `A2.Dll`, redirige únicamente `T3_Modded.exe` a esa copia y conserva intacto el `Ai.Dll` original.
- Usa búsquedas nativas ancladas para acelerar la validación AOB cuando intervienen varios binarios.
- Antes de compilar, ejecuta automáticamente `runtime_patch.py --write` en los proyectos habilitados que incluyan ese generador en su raíz y valida el `executable.json` resultante.
- Los mods que generan recursos pueden declarar `"generates_assets": true`: reconstruir el ejecutable también recompila Mods.Cod. El publicador compartido `t3_generated_assets` actualiza modelos, texturas, locators y manifiestos sin renombrar carpetas bloqueadas en Windows, y restaura los archivos anteriores si falla la publicación.
- Si un generador falla, la compilación se detiene antes de mover los `Mods.Cod` y `T3_Modded.exe` anteriores; estos scripts ejecutan código local y sólo deben usarse en proyectos confiables.

Los archivos existentes `load_order.json`, `Mods.Cod` y `.compiled/` se trasladan fuera de
la carpeta de mods, conservando el orden y los estados de activación, con respaldos en
`modtools_data/legacy_backup/<ID de migración>/` y recuperación ante fallos. Los datos que
ya existan en la ubicación nueva tienen prioridad; los duplicados anteriores se conservan
en el respaldo. Si se verifica el `T3_Modded.exe` anterior, la migración restaura los bytes
originales donde estaba su cargador e instala el cargador corregido en una sección propia,
conservando los últimos parches compilados. Para iniciar el juego se exige el cargador
corregido. Si no se puede migrar el ejecutable anterior, usá **Compilar Mods + EXE modificado**
con los mods deseados habilitados antes de iniciar. El archivo antiguo se conserva hasta
que una compilación exitosa lo retire. Esta corrección mantiene la versión 0.6.5.

## Propósito y alcance

T3-ModTools está destinado al modding personal, la preservación y la investigación de interoperabilidad con una copia legal del juego. No evade DRM, cifrado, autenticación en línea ni sistemas antitrampas.

Este proyecto es experimental. Algunos assets o procesos pueden necesitar pruebas específicas, y agregar contenido completamente nuevo puede requerir configuración o investigación del motor más allá del reemplazo normal de archivos.

Este README solamente describe la función de la aplicación. Para consultar las instrucciones de instalación y los tutoriales de modding, revisa la [Guía de modding de T3](Documentation/T3-Modding-Guide.pdf) incluida.

El código fuente se distribuye bajo la licencia MIT. Esta licencia se aplica a T3-ModTools, no a los assets extraídos del juego. Los assets del juego continúan siendo propiedad de sus respectivos titulares de derechos.
