# WM-32 Plasma: implementation and maintenance

Reviewed against repository sources on 2026-11-03. Tool baseline: **T3-ModTools 0.6.12**. Mod folder and ID: `wm32_plasma`; registered weapon name: `WM32`.

This is a reconstruction of how this project was implemented, not a universal weapon-format specification. **CONFIRMED** below means supported by current source assertions or existing regression tests; **OBSERVED** means a recorded user/game result; **UNKNOWN** means not established by that evidence. No generator, Blender export, compilation or game test was run while writing this document.

## 1. What we built

WM32 is a separate selectable T900 Supply weapon, not a replacement of the WM20 registration. We used WM20 as the compatible weapon rig, animation and native-file donor, retained its two-bone structure, and substituted an authored model with its own textures and muzzle locators. Separate registration adapters connect the new name to the existing animation family. Private audiovisual banks keep the weapon's two firing modes independent of the native particle array limits.

| Responsibility | Current source of truth |
| --- | --- |
| Editable geometry, materials, rig and muzzle empties | [WM-32 Plasma.blend](<../../../T3/mods/wm32_plasma/files/weapons/WM32/WM-32 Plasma.blend>) |
| Blender export and coordinate checks | [asset_build.py](../../../T3/mods/wm32_plasma/asset_build.py), especially `reference_transform`, `submeshes`, `export_asset` |
| Registration, source overlays and staged publishing | [runtime_patch.py](../../../T3/mods/wm32_plasma/runtime_patch.py) |
| Native audiovisual adapters | [effects_patch.py](../../../T3/mods/wm32_plasma/effects_patch.py) |
| Gameplay values | [weapon1.option](../../../T3/mods/wm32_plasma/files/weapons/WM32/weapon1.option) and [weapon2.option](../../../T3/mods/wm32_plasma/files/weapons/WM32/weapon2.option) |
| Blender executable location | [build_config.json](../../../T3/mods/wm32_plasma/build_config.json) |
| Generated geometry/material/locator provenance | [asset_report.json](../../../T3/mods/wm32_plasma/asset_report.json) |

## 2. Establishing the source model and donor contract

The initial preparation code imports `plasma gun2.glb` and uses its embedded `T3_Global_Mirror_X_Z_Up` armature and vanilla `westinghaus` mesh as a calibration fixture. `prepare()` refuses to overwrite an existing editable `.blend`; it is an initial setup procedure, not a routine rebuild command.

The five exported objects are `BBL01__008`, `COUNT01__003`, `COUNT02__004`, `PLEX01__002`, and `TRIGGER__005`. Every vertex of the first four belongs to `b1` with weight 1; the trigger belongs to `b2` with weight 1. The exact native paths are `|root|b1` and `|root|b1|b2`. This allows the trigger to animate independently without inventing a new weapon skeleton. The hidden `westinghaus` reference is excluded from the exported weapon; preserve its geometry and its calibration role.

`original()` resolves the reference through `Game.cod`, `Language.cod`, then `Patch116.Cod`, with later archive matches winning. The current exporter preserves the WM20 model templates' bones and other native structure while replacing mesh blocks, texture library, bounds, and visual locator blocks. All four donor LOD levels receive the exported geometry. This is template preservation, not automatic polygon reduction.

Do not hard-code the historical triangle or submesh count in a new exporter. The editable model has evolved. `asset_report.json` supplies the current counts, and runtime validation compares generated SCA/LOD geometry and materials with that same export report.

## 3. Coordinate, material and texture conversion

**CONFIRMED in `asset_build.py`:** the Blender-to-native transform is calibrated from the embedded vanilla reference. The round-trip check compares reference vertices, normals and UVs against pristine WM20 data before exporting the custom model. Normals use an inverse-transpose matrix; singular transforms fail; triangle winding is corrected for negative determinants. The exporter writes rest geometry rather than baking the current armature pose. These are weapon-specific rules; do not transfer the signs to a character, map or unrelated menu asset without its own fixture.

Material export reads `t3_shader_type`, defaulting to `DIFFUSE_SPECULAR`. It resolves a material's color texture rather than assuming the material name identifies the image. Ambiguous image choices fail. Supported constant colors become deterministic 1-by-1 TGA textures. `t3_transparency_enabled` and `t3_transparency_amount` are translated to `T3Transparency` for the supported shader types, with opaque submeshes emitted before transparent ones. This does not implement an animated ammunition counter or prove support for arbitrary Blender node graphs.

External textures and linked Blender libraries must resolve **inside this mod directory**. Packed images are allowed. `validate_mod_resources()` resolves paths before testing containment, so a relative path or filesystem link cannot silently introduce an external cache dependency. Missing external images fail with their authored path.

`export_texture()` loads/reloads the source before saving the exported copy. External TGA files are copied byte-for-byte; other supported image formats are saved as TGA. The original Blender image path is not repointed to the staging directory. This fixes the lazy-loading failure that packed images had previously hidden.

**Current-code clarification:** older README wording promises only `wm32.tga` and `wm32_alpha.tga`. The current `material_export_info()` derives a sanitized `wm32...tga` name from each image, detects output-name collisions, and also supports hashed solid-color textures. Inspect the export report and model texture references rather than relying on the earlier two-name description. Native `.mat` values copied from the donor are not documented PBR parameters.

## 4. Visual muzzle locators and the secondary-mode correction

The source empties `f_primary` and `f_secondary` define visual locator IDs 0 and 1. Their local X axes define forward direction. The exporter applies its verified mesh-to-locator X/Z sign conversion and records the resulting positions and directions in the report.

The native single-weapon path caches locator 0 for muzzle effects. Merely exporting locator 1 did **not** make secondary effects use it. The follow-up adapter therefore recognizes WM32 secondary subtype 29, identifies the matching active FPS/TPS weapon controller, transforms the authored secondary locator through the live weapon/actor matrices, and applies it both when creating the effect and during per-frame updates. Invalid or unmatched events keep their native inputs.

An important build-order correction was to generate those constants from the **fresh staged Blender report**, not the last published report. A saved empty move therefore takes effect in one build, not two. The primary remains on the native path. See [secondary locator tests](../../../T3/mods/wm32_plasma/test_secondary_locator.py) and the detailed [effects investigation](../../../T3/mods/wm32_plasma/research/effects.md).

Visual locators are not interchangeable with physics locators. The additional primary physics-Y correction documented for [Dual WM32](WM32_DUAL_IMPLEMENTATION.md) belongs to its generated dual assets; do not silently apply that history to single-WM32 assets.

## 5. Registering a new selectable weapon

`runtime_patch.generate()` imports the shared WM27 family code. Exact WM27/WM32 names map to the native WM20 animation family (base ID 244), while unrelated names retain native lookup. WM32 also receives its own graphics precache call and name strings. Adding an asset directory or menu line alone would not perform that registration.

`Sources` composes effective assets from enabled mods in visible priority order, then archive fallback. It excludes this mod and its downstream dual consumers to avoid feeding generated output back into its own inputs. `author_files()` performs these distinct jobs:

1. Copy compatible WM20 weapon support files under `weapons/WM32`, rewrite their internal paths, and retain the donor secondary projectile model.
2. Add the WM32 menu row, display-name entry and T900S selection entry. The current menu row uses ID **25** and `MenuDatas/3DModells/wm32_menu.sca`; occupied IDs are rejected rather than reused.
3. Construct the supported Supply inventory, retaining WM20 and an existing WM27 choice before adding WM32.
4. Add WM32 roles to both FPS and TPS Supply animation libraries by cloning compatible non-dual WM20 roles, then recompute `AnimNum`.
5. Reuse the shared default-loadout adapter so bots choose one weapon alternative and retain the `T_AMMO` dispenser resolved by gameplay identity.

The generated menu preview has its own static geometry conversion. It strips bones, weights and locators, applies the WM20 gameplay-to-menu affine transform checked against pristine paired vertices, and writes menu textures separately. A weapon model should not simply be copied into the menu path with its gameplay rig intact.

## 6. Independent effects without overflowing native tables

The implementation history and target-specific addresses are in [research/effects.md](../../../T3/mods/wm32_plasma/research/effects.md). Its native findings identify 23-preset muzzle/tracer arrays and a 32-entry sound registry. We did not append WM32 subtypes directly as out-of-range array indices.

| Connection | Current contract |
| --- | --- |
| Primary weapon option | `subType 28` |
| Secondary weapon option | `subType 29`; its existing physical `type granade` is independent of its red visual appearance |
| Private muzzle/tracer banks | `Particles/WM32MuzzleFire.dat` and `Particles/WM32FiredBullet.dat` |
| Slots inside those banks | Native names `Weapon_RSB80` and `Weapon_Wm20` represent the two WM32 presets only within the private objects |
| Sound lookup | Translate only the local WM32 lookup subtype to existing RSB80; do not duplicate or enlarge the sound registry |
| Primary impact | Native plasma material bank |
| Secondary impact | Separate red bank sourced from `Particles/BulletHitPlasmaRed.dat`, retaining twelve material variants |

`author_effects()` reads the effective `MuzzleFire.dat` and `FiredBullet.dat`. It uses `Weapon_WM32` / `Weapon_WM32_2` blocks when available, otherwise its explicit RSB80-based fallbacks. The current supplied SFX definitions determine the actual appearance. Red texture/impact fallback files may be read from `t3_enhanced_sfx` even when that mod is disabled; those files are therefore declared cache dependencies.

Private native objects receive initialization, draw, settings-change, position/light update and destruction handling. Subtype conversion is local to dispatch and does not rewrite the projectile's logical subtype. The red impact object's owner filter avoids running its lifecycle twice through the separate Enhanced SFX blue bank. Allocation failure follows the bounded fallbacks documented in the code.

Edit the authored SFX definitions, not generated `WM32MuzzleFire.dat` / `WM32FiredBullet.dat`, which are rebuilt. Changing an effect's color does not change projectile physics or damage.

## 7. Safe everyday editing and incremental compilation

1. Edit the saved `.blend` for geometry, supported materials or the two muzzle empties. Keep unpacked resources inside the mod and preserve the reference object and rig metadata.
2. Edit `weapon1.option` / `weapon2.option` for gameplay values such as damage, speed, ammunition and cadence. Keep subtypes 28/29 to retain the audiovisual routing.
3. Save changes, verify `build_config.json` points to the installed Blender executable, and compile through ModTools.
4. Inspect `asset_report.json`, the generated manifest, and the final build's winning overlay paths before testing in game.

Existing option files are preserved byte-for-byte, including comments, line endings and even an empty file. Defaults are created only when a file is absent. Preservation is not a guarantee that a deliberately empty gameplay option is valid for the intended game scenario. Direct edits to generated model SCA/LOD files are replaced by the next export.

`generates_assets: true` ensures binary rebuild workflows also account for the generated archive content. ModTools caches a successful generator result using declared inputs, including the saved blend, textures, this mod's files, enabled-mod context, WM27 code, SFX fallback content and configured Blender executable. An unchanged cached build need not launch Blender. Unsaved Blender edits are not inputs.

Publication goes through [t3_generated_assets.py](../../../T3-ModTools/t3_generated_assets.py): stage and validate first, retain authored source files, and restore the prior generated set on publication failure. Keep the single mod above lower providers of its composed menu/Supply files; when using Dual WM32, the dual must in turn win its own composed Heavy/menu paths. Generator dependency order and visible asset priority are separate concerns.

## 8. Verification and remaining limits

Existing targeted regressions to consult, not newly executed results:

- [test_wm32.py](../../../T3/mods/wm32_plasma/test_wm32.py): exact aliases, Supply-only loadout behavior, shared patch/precache ABI and current assets.
- [test_texture_export.py](../../../T3/mods/wm32_plasma/test_texture_export.py): run inside Blender; lazy external TGA, PNG conversion, packed image and missing-file cases.
- [test_editable_options.py](../../../T3/mods/wm32_plasma/test_editable_options.py): option bytes survive repeated generation and archive building.
- [test_effects.py](../../../T3/mods/wm32_plasma/test_effects.py): native x86 dispatch, lifecycle, sound comparison and authored lights.
- [test_secondary_locator.py](../../../T3/mods/wm32_plasma/test_secondary_locator.py): native matrix/effect behavior across FPS/TPS and fresh export constants.
- [test_impacts.py](../../../T3/mods/wm32_plasma/test_impacts.py): twelve material indices, owner-filtered lifecycle and unchanged earlier adapters.

The native-code tests use Unicorn; Blender-dependent tests require Blender rather than ordinary Python. Validation-mode `runtime_patch.py` still performs a staged Blender export and comparison: it is not a cheap text-only check. Use `--write` only when intentionally publishing regenerated files.

**OBSERVED, historical:** the mod README records the user's 2026-10-08 confirmation that the weapon worked, then later confirmation of the audiovisual update and both corrected muzzles. **UNKNOWN in the cited record:** final visual approval of the later normal/red impact split. Those observations do not certify every current edited material, mode, bot or load-order combination.

For a release, test menu selection, FPS/TPS appearance, both firing modes, muzzle tracking while moving, all relevant impact surfaces and Supply bots separately. Verify original archives/binaries remain unchanged and inspect conflicts across all enabled manifests. Patches target the fingerprinted pristine PE32 x86 build in the source; addresses from its research notes are not portable patch instructions for another executable.
