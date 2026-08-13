T3-MODTOOLS 0.6.0
================================

Experimental asset extractor, converter, mod project manager, and mod compiler for
Terminator 3: War of the Machines (PC).

The graphical interface contains two modes:

- Asset Extraction
- Modding

The extraction mode reads the game's ZIP-compatible COD archives directly. The modding
mode creates independent mod projects, compiles enabled projects into mods/Mods.Cod, and
automatically rebuilds a separate T3_Modded.exe that loads the compiled mod package before the official
Language.cod, Patch116.Cod, and Game.Cod packages. The original T3.exe is never modified.

REQUIREMENTS
------------

- Windows 10 or Windows 11.
- Python 3.9 or newer.
- The Tkinter component included with the standard Python installer.
- A legally owned copy of the game.

No third-party Python packages are required. Blender is only required for the optional
model and animation import/export add-ons.

STARTING THE TOOL
-----------------

1. Extract the complete T3-ModTools folder.
2. Run T3-ModTools.vbs to open the graphical interface without a Command Prompt window.
3. T3-ModTools.bat may also be used; it launches the silent VBS starter and closes immediately.
4. Locate and select Game.cod in the game folder to extract the assets.
5. Select an output folder.
6. Choose the asset categories and conversion options.
7. Press Extract / Convert.

Use the mode switch at the top of the window to open Modding mode.

REMEMBERED SETTINGS
-------------------

The interface remembers the selected language, current mode, Game.cod path, extraction
output folder, game installation folder, and mods folder.

On Windows, settings are stored in:

%APPDATA%\T3-ModTools\settings.json

English is the default language on first launch. The selected language remains active on
future launches.

ASSET EXTRACTION MODE
---------------------

Categories:

- Characters
- Vehicles
- Weapons
- Maps
- Menu Models
- Effects
- Audio
- Animations

Static SCA/LOD/DET files can be converted to OBJ + MTL. The Menu Models category selects the SCA models stored under MenuDatas/3DModells/ in Game.cod. Compatible character, vehicle, and
weapon rigs can be exported to glTF 2.0. Rigged glTF files preserve UV0 as TEXCOORD_0 and
connect supported DDS/TGA base textures through generated PNG files.

All converted models receive the global X mirror. Characters, vehicles, maps, and menu models keep the
game's native Y/Z orientation. Weapons and effect models may optionally use:

Z-up (only for weapons and effects)

The OBJ UV option is displayed as:

Flip UV V coordinate (Don't use with glTF 2.0 models)

Rigged glTF exports always preserve the source UV V coordinate regardless of that OBJ option.

MODDING MODE
------------

Select the folder containing T3.exe. The default mods folder is:

<Game installation>/mods/

A mod project uses this structure:

mods/
  load_order.json
  My_Mod/
    mod.json
    files/
      CA/...
      weapons/...
      vehicles/...
      scene/...
      sound44/...
    patches/
      executable.json

The files/ folder must reproduce the internal paths used by Game.Cod. For example, a skin
replacement must use the same internal model texture path as the asset it replaces.

Use Create mod to generate a new project. Use Open mod folder to add edited or new native game files and optional executable patches. Mods can be enabled, disabled, and reordered. Later enabled mods in the visible
load order win when two projects supply the same internal path.

BUILDING MODS + MODDED EXE
--------------------------

Build Mods + Modded EXE performs the complete mod build in one operation. It merges all
enabled files/ folders into:

<Game installation>/mods/Mods.Cod

and always rebuilds:

<Game installation>/T3_Modded.exe

from the original T3.exe. The original executable is never modified. The generated
T3_Modded.exe loads mods/Mods.Cod before Language.cod, Patch116.Cod, and Game.Cod and then
applies executable patch manifests from every enabled mod in load order.

Before building, the previous Mods.Cod, mods/.compiled/, and load_order.json are removed.
The current project order and enabled state are then written to a fresh load_order.json.
Build metadata is written to mods/.compiled/. If two executable patches try to write different
bytes to the same location, the build stops with a conflict instead of silently overwriting one
mod with another.

EXECUTABLE PATCH MANIFESTS
--------------------------

A mod may optionally include patches/executable.json. Version 1 supports conservative
AOB replacement patches. Patterns are searched against the pristine original T3.exe so
each build is reproducible and does not depend on the previous T3_Modded.exe.

Example:

{
  "format_version": 1,
  "target": "T3.exe",
  "patches": [
    {
      "id": "example_patch",
      "type": "aob_replace",
      "section": ".text",
      "pattern": "8B 45 ?? 83 F8 02",
      "replacement": "8B 45 ?? 83 F8 03",
      "expected_matches": 1
    }
  ]
}

Use ?? as a wildcard in the pattern. A ?? byte in replacement preserves the original byte
at that position. Version 1 requires exactly one match for safe patching.

Use Launch T3 Modded after a successful build.

SUPPORTED MOD CONTENT
---------------------

The compiler can package any native game file while preserving its internal path, including:

- skins and textures;
- SCA/LOD/DET models;
- WAV and OGG audio;
- ANM animations;
- weapon, character, and vehicle configuration files;
- particle, effect, decal, and shader files;
- map files and related configuration.

Replacing an existing asset is simpler than registering a completely new character, weapon,
vehicle, or map. New content can require additional configuration files, identifiers, mission
references, AI definitions, collision data, menus, or executable research.

BLENDER PLUGINS
---------------

The Blender plugin folder contains:

- T3_Blender_ANM_Importer.py
- T3_Blender_ANM_Exporter.py
- T3_Blender_SCA_Exporter.py
- ANIMATION_IMPORT_README.txt
- ANIMATION_EXPORT_README.txt
- SCA_EXPORT_README.txt

T3_Blender_SCA_Exporter.py is the new experimental Blender-to-SCA exporter. A Blender plugin
is the most practical way to collect edited mesh geometry, UV maps, material texture names,
armature hierarchy, bind matrices, and vertex weights and write them back to SCA.

The main program then compiles the exported SCA into Mods.Cod; the Blender plugin does not
install or package the mod by itself.

The SCA exporter currently supports replacement-oriented static and rigged models. It does
not yet generate map binary trees, LOD files, collision targets, scene.det, scene.dyn, advanced
shaders, or gameplay registration files.

T3_Blender_ANM_Exporter.py exports the active armature Action to an experimental ANM file.
Bone names and hierarchy must match the target game rig.

RESPONSIBLE USE
---------------

The tool does not bypass encryption, DRM, online authentication, or anti-cheat systems. It is
intended for personal modding, preservation, interoperability research, and work with a legally
owned copy of the game. Extracted assets remain the property of their respective rights holders.
