T3 RIGGED MODEL AND ANIMATION WORKFLOW
============================================

RIGGED MODELS
-------------

The Export Rigs (glTF 2.0) option scans the selected Characters, Vehicles, and Weapons categories and creates glTF 2.0 files under their original paths, for example:

converted_rigged/ca/casts/.../model_sca/
converted_rigged/vehicles/.../model_sca/
converted_rigged/weapons/.../model_sca/

Each rigged export contains:

- model_rigged.gltf
- model_rigged.bin
- original textures copied from the game when available
- compatible PNG textures connected to the glTF materials

Import the .gltf file in Blender using File > Import > glTF 2.0.
The global X mirror is stored on a parent transform node. Characters and vehicles keep the game's native orientation and receive no fixed X-axis rotation. Rigged weapons follow the tool's optional weapon Z-up setting.

ANIMATIONS
----------

Selecting the Animations category extracts the original .anm files into:

animations/raw/

The tool also copies T3_Blender_ANM_Importer.py into the animations folder.

To install the Blender importer:

1. Open Blender.
2. Select Edit > Preferences > Add-ons.
3. Click Install from Disk.
4. Select T3_Blender_ANM_Importer.py.
5. Enable T3 ANM Animation Importer.

To import rigged models and their animations:

1. Import a compatible rigged .gltf model.
2. Select the model and invert the global Y axis.
3. Select the imported armature and invert the global Y axis.
4. Select the armature.
5. Use File > Import > T3 Animation (.anm).

The importer stores the source FPS, MaxTimeValue, complete joint paths, and exact joint
order on the generated Blender Action. T3_Blender_ANM_Exporter.py uses this metadata to
export an edited overlay without accidentally including the complete armature.

Animation compatibility depends on matching bone names. Third-person character animations generally belong to third-person character rigs, while first-person weapon/arm animations belong to first-person rigs. The importer reports unmatched bones instead of stopping the import.

LIMITATIONS
-----------

- Rigged glTF export is experimental.
- Supported DDS/TGA base textures are converted to PNG and connected to glTF materials. Unsupported texture variants remain copied beside the model and may require manual conversion.
- The Blender importer has been structurally tested outside Blender, but individual animations may require axis, root-motion, or rest-pose corrections.
- More than four influences per vertex are reduced to the four strongest weights and normalized, as required by the base glTF skinning layout.
