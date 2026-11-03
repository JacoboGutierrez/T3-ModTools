T3-MODTOOLS 0.6.12
================================

Experimental asset extractor, converter, mod project manager, and mod compiler for
Terminator 3: War of the Machines (PC).

The graphical interface contains two modes:

- Asset Extraction
- Modding

The extraction mode reads the game's ZIP-compatible COD archives directly. The modding
mode creates independent mod projects, compiles enabled projects into modtools_data/Mods.Cod, and
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

MOD DEPENDENCIES
----------------

mod.json may declare "requires": ["required_mod_id"]. Enabling a mod enables its
installed requirements; disabling a requirement disables its dependent mods.
Changes are shown in the log and preserve load priority. Old inconsistent
selections are repaired on Refresh. Missing requirements cannot be enabled.
This is separate from runtime_cache.dependencies, which only orders generators
and tracks changes to their source files.

Dual WM32 requires WM32, Dual WM27, WM27 and T900 Heavy Assault. Disabling only
Dual WM32 leaves WM32 active. Disabling WM32 also disables Dual WM32.

"provides_weapons": ["WM32"] declares a custom weapon's internal menu key.
When its weapon1.option is absent from the enabled overlay, compilation omits
its menu rows/default selection from Mods.Cod. Authored Weapons.dat files are
never rewritten by this filter; re-enabling the weapon restores their entries.
Enhanced SFX uses OPTIONAL_WEAPONS in runtime.py to omit audio configuration
for absent mod weapons. Present but malformed options still produce an error.

LIVE DEBUG (TECHNICAL CAPTURE)
----------------------------

In Modding, select Live debug. Set a duration (default 120 seconds) and sample
interval (default 100 ms), then leave the panel open. ModTools can be minimized.
Open a match in T3_Modded.exe or T3.exe from the configured game folder and press
Ctrl+Shift+F9 to start. Press it again to stop early, or wait for the duration.
The Start/Stop button works too. F8/F10/F11 can replace F9 if the shortcut is busy.
Closing the panel stops capture and releases its shortcut. Closing ModTools also
requests a stop and lets the writer finish the partial report. No focus is changed
when a capture starts, ends or fails. Builds are disabled while capture is active.

Reports: <game>/modtools_data/debug/<timestamp-id>/
- metadata.json: time, supported memory profile, executable hashes, capture settings.
- summary.json: completion reason, errors, observed weapons/actor IDs/ammo decreases.
- samples.jsonl: successive actor, weapon, fire-request, sound-bank, listener,
  sample-path, recent native event and assigned FMOD-channel observations.
- Available build/load-order manifests and up to 256 KiB from the game debug.log.

Audio detail version 2 also records channel volume, mute/pause flags, master
volume and software-mixer gains (only for the verified software backend).
These values help distinguish sound selection from attenuation/muting; they
still cannot prove what was audible at the speakers. Older captures do not
contain these additional fields.

Animation detail version 1 records T900HeavyAssault scene ownership, movement
state/speed, left-right/up-down controls, active/target animation IDs and clip
paths for the legs, spine and hands, and the 32 character bone matrices. This
helps compare running poses between weapons. Sound actor IDs are not treated
as scene array indices. Animation read failures are reported separately and do
not stop the audio capture. Poses are sampled across several memory reads, not
atomically at a frame boundary. Older captures cannot supply these fields.
Reopen ModTools after updating to load the new capture profile; no game rebuild
is needed. A short 20-30 second comparison is usually enough to begin diagnosis.

Requires one running game from the selected folder, the verified T3 1.16 original,
and compatible Windows privileges. An unsupported binary is rejected. Restart the
game if its live audio hooks differ from the executable on disk after rebuilding.
Limits: 1-3600 seconds, 50-2000 ms between samples, 128 MiB of sample data.
These are sampled observations: brief events may be missed; ammo decreases are
not an exact shot count; an assigned FMOD channel does not prove audible output.
Immediate-fire patches can bypass the native event queue. Loading/actor changes
may produce partial samples. The capture reads process memory only; it does not
inject code, record video/audio, or alter the game or mod files. Capture settings
reset when the panel is reopened. Use a longer interval to reduce capture overhead.

REMEMBERED SETTINGS
-------------------

The interface remembers the selected language, current mode, Game.cod path, extraction
output folder, game installation folder, and mods folder.

On Windows, settings are stored in:

%APPDATA%\T3-ModTools\settings.json

The interface is available in English, Spanish, Russian, and Portuguese. English is the
default language on first launch. The selected language remains active on future launches.
The tool's console messages also use the language selected in the dropdown.
Raw runtime-generator output and technical exception details are saved under
<Game installation>/modtools_data/logs/ in Modding mode, or <extraction output>/logs/
in Asset Extraction mode. If that folder is unavailable, a diagnostic file is saved in
the system temporary folder. The console reports the result in the selected language
and points to the actual diagnostic file. Third-party prose is preserved in these files;
paths, IDs, hashes, and other technical values keep their original spelling.

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
  My_Mod/
    mod.json
    runtime_patch.py       (optional generator)
    files/
      CA/...
      weapons/...
      vehicles/...
      scene/...
      sound44/...
    patches/
      executable.json

Generated files and load-order settings are stored separately from mod projects:

<Game installation>/modtools_data/
  load_order.json          (default mods folder)
  Mods.Cod
  .build_cache/            (disposable incremental-build cache)
  .compiled/
    build_manifest.json
    loader_manifest.json
  logs/
  load_orders/
    <folder hash>/
      load_order.json     (custom mods folder)
  legacy_backup/
    <migration ID>/

The archive and build reports remain inside the selected game installation even when a
custom mods folder is selected. Each custom mods folder gets a separate load_order.json
under modtools_data/load_orders/<folder hash>/ so its order and enabled states stay separate.

When upgrading, the tool migrates the existing load_order.json, Mods.Cod, and .compiled/
out of the mods folder, preserving exact backups under
modtools_data/legacy_backup/<migration ID>/. Existing data in the new location takes
priority; older duplicates are retained in the backup. Migration preserves mod order and
enabled states and rolls back on failure.

For a recognized earlier T3_Modded.exe, migration checks the loader bytes and recorded
manifest fingerprints, restores the original bytes used by the old loader, and installs
the corrected loader in its own .t3ldr section. The last build's mod patches remain intact,
even if the current selection has changed. Launch requires the corrected loader. If the
older executable cannot be migrated, use Build Mods + Modded EXE with the intended mods
enabled before launching. The legacy archive remains available until a successful build
retires it, with its backup retained.

The files/ folder must reproduce the internal paths used by Game.Cod. For example, a skin
replacement must use the same internal model texture path as the asset it replaces.

Use Create mod to generate a new project. Use Open mod folder to add edited or new native
game files and optional executable patches. Mods can be enabled, disabled, and reordered.
The enabled mod that is highest in the visible load order wins when two projects supply
the same internal path.

GENERATING A MOD PACK
-------------------

Generate mod pack, directly below Create mod, combines every currently enabled project
into a new combined mod project. Enter a pack name; the tool copies files/ content
and combines executable manifests, preserving the visible top-first priority for
duplicate asset paths. Disabled projects are excluded.

Enabled runtime_patch.py generators are synchronized before taking the snapshot.
Their generated patches are included as a static patches/executable.json, with each
T3.exe or Ai.Dll target preserved. Patch IDs are made unique and MERGE_REPORT.json maps
them back to the source mods. Executable patches are validated together on temporary
copies of the pristine binaries. Incompatible writes stop pack creation.
Animation compatibility is analyzed against the installed original COD archives,
read-only; those large archives do not need to be copied into the temporary folder.
The validation includes automatically generated animation patches and copies the
original AI DLL when those patches need it, even without an explicit AI manifest.

Known legacy ANM patches are verified by their exact identity/digest before their
IDs can be renamed. They are replaced by current automatic compiler support, just
as in a normal build, and recorded in MERGE_REPORT.json. Modified legacy patches
still fail validation. Resolved animation alternatives are retained in a combined
anm_variants.json so compiling the pack keeps the original animation behavior.

The new project includes mod.json, files/, optional patches/executable.json, an English
README.md, and MERGE_REPORT.json with source order, file hashes, and resolved conflicts.
Only game assets, executable patches and the supported animation variant configuration
are merged; development scripts and other source-root files are not copied.
Asset contents and existing patch descriptions retain
their original text; this command does not translate third-party content.

After success, the pack is enabled and the source mods are disabled with their folders
retained. A duplicate pack name receives a unique folder ID. Copy or validation failures
leave no partial pack and preserve the previous load order and compiled game outputs.

Use Build Mods + Modded EXE to compile the new pack. Generating a pack does not rebuild
Mods.Cod, T3_Modded.exe, or A2.Dll. The pack is a snapshot: create another pack to include
later edits to the source mods.
Patches that load an external runtime DLL directly from a source mod directory
still require that file at its original path. The pack does not rewrite embedded
external paths or bundle arbitrary native DLLs; retain those source folders when
using such features. This is separate from ordinary files/ archive resources.

BUILDING MODS + MODDED EXE
--------------------------

Build Mods + Modded EXE performs the complete mod build in one operation. It merges all
enabled files/ folders into:

<Game installation>/modtools_data/Mods.Cod

and, when the build inputs or generated outputs have changed, rebuilds:

<Game installation>/T3_Modded.exe

from the original T3.exe. When an enabled manifest targets Ai.Dll, it also rebuilds:

<Game installation>/A2.Dll

from the original Ai.Dll. Neither original binary is modified. The generated
T3_Modded.exe loads modtools_data/Mods.Cod before Language.cod, Patch116.Cod, and Game.Cod and then
applies executable patch manifests from every enabled mod in load order.

Incremental compilation uses SHA-256 of file contents, not only modification dates.
Within a read-only build phase, repeated requests share the same directory snapshots
and content hashes. This avoids repeatedly reading game archives and dependency trees
for every generator. These scan results exist only in memory: they are discarded after
an executed generator, before rebuilding outputs, before the final input verification,
and when the operation ends. A new build always reads source contents again, including
edits that preserve file size and modification time. ANM consistency checks read fresh
hashes even inside a phase. The existing compressed-asset cache remains persistent.
Unchanged asset bytes reuse validated compressed entries from modtools_data/.build_cache/;
only new or changed content is compressed. The final archive is assembled in current
priority order, so enabling, disabling, reordering, renaming or deleting files cannot
leave obsolete entries or incorrect winners. Generated ANM libraries are cached by
their generated contents too. Corrupt/missing cache entries are recreated from source.

If all build inputs and all existing generated outputs still match the last successful
build, the archive and binaries are left untouched. Otherwise the common package and
executable outputs are rebuilt as needed by the existing atomic build operation; cached
assets do not bypass executable patch conflict checks. Changes to pristine inputs or
ModTools Python modules also invalidate reuse. The console reports compressed/reused
file counts in the selected language, and build_manifest.json records these counts.
The first build populates the cache. Removing only .build_cache/ is safe and forces a
cold build next time; it never contains the only copy of a source asset.

The loader code and package path are stored in a dedicated .t3ldr section appended to
T3_Modded.exe. The executable's original sections are preserved except for the six-byte
loader hook and selected mod patches; the PE headers are updated for the added section.
This corrects the initial 0.6.5 loader placement, which could overwrite a live empty-string
value and crash the menu. The version remains 0.6.5.

A2.Dll is built from the original Ai.Dll and T3_Modded.exe is redirected to the generated
copy. The original Ai.Dll is never modified. A patch may set "target": "Ai.Dll" while the
rest of the manifest continues to default to T3.exe.

If an enabled project contains runtime_patch.py in its root, T3-ModTools synchronizes it
with --write using the same Python interpreter, then validates the generated executable.json.
Reviewed deterministic generators may declare "runtime_cache": {} in mod.json to skip
execution when their complete project tree, pristine game inputs and tool modules match.
The declaration is a dependency contract, not a hint: all additional external inputs must
be declared. For example:

    "runtime_cache": {
      "dependencies": ["../shared_mod", "D:/shared/source.dat"],
      "enabled_mods": true,
      "config_paths": {"build_config.json": ["blender"]}
    }

dependencies accepts files/directories, relative to the mod or absolute. enabled_mods
tracks other enabled projects and selection/order for generators reading the overlay.
config_paths tracks file/directory paths stored in the named JSON configuration keys.
Generated outputs are included in the fingerprint; missing/edited outputs force a rerun.
Only successful, validated generators get a cache record. Generators without this
declaration always run; their unchanged output assets can still reuse compression.
Authored Blender mods keep unpacked textures and linked resources inside their own mod
folder (packed images are also supported). Editing, adding, renaming or deleting these
files invalidates the project fingerprint, even when the .blend itself is unchanged.
WM-32 opts in with its WM-27 code, Enhanced SFX fallback assets, enabled overlay/order
and configured Blender executable as dependencies. Its exporter rejects texture/library
references outside the mod before publishing, rather than silently caching untracked
inputs. Future Blender generators must declare any additional code/tool dependencies
and enforce the same resource boundary before opting in; a .blend alone is not opt-in.
Do not opt in generators depending on untracked environment/network/clock state.

Disabled projects are never executed. A generator error or a
60-second timeout stops before the previous Mods.Cod and T3_Modded.exe are moved. Runtime
generators are executable local code; only enable projects you trust.

Generators that also export models/textures/locators can declare
"generates_assets": true in mod.json. Rebuild Modded EXE then runs a complete
package + executable build so saved Blender edits also reach Mods.Cod.

After staging and validating all assets, a generator can use the shared helper:

    from t3_generated_assets import publish_generated_assets
    publish_generated_assets(project_root, staged_files, {
        "patches/executable.json": manifest_json_bytes,
        "asset_report.json": report_json_bytes,
    })

The staged_files directory contains the intended contents of files/. This helper
preserves the existing directory and updates files individually, including the
manifest/report in the rollback set. Unchanged bytes are not rewritten. It records
owned asset paths in .generated-assets.json, removes only previously owned stale
assets, and preserves unrelated files added by the user. Keep all export/validation
work before publication; a publication failure stops compilation and restores the
prior files. If Windows also prevents rollback, the error identifies retained
backups for recovery. No Blender or muzzle conversion is built into this helper;
the mod's generator defines how its saved source produces game-native assets.

Build Mods + Modded EXE stages the previous generated outputs so they can be restored if
compilation fails. The current project order and enabled state are written to the applicable
load_order.json under modtools_data/. Build metadata is written to modtools_data/.compiled/.
If two executable patches try to write different bytes to the same location, the build
stops with a conflict instead of silently overwriting one mod with another.

EXECUTABLE PATCH MANIFESTS
--------------------------

A mod may optionally include patches/executable.json. Version 1 supports conservative
AOB replacement patches for T3.exe and Ai.Dll. Patterns are searched against the matching
pristine original so each build is reproducible and does not depend on a previous output.

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
- T3_Blender_LOD_Exporter.py
- T3_Blender_LOD_Importer.py
- T3_Blender_Menu_Model_SCA_Exporter.py
- T3_Blender_SCA_Exporter.py
- T3_Transform_Converter.py

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

T3_Transform_Converter.py converts selected pose transforms to editable TXT reports and
applies those reports to another compatible armature. It supports normal or reversed time,
single-frame poses, and optional X mirroring without changing the source scene.

RESPONSIBLE USE
---------------

The tool does not bypass encryption, DRM, online authentication, or anti-cheat systems. It is
intended for personal modding, preservation, interoperability research, and work with a legally
owned copy of the game. Extracted assets remain the property of their respective rights holders.
