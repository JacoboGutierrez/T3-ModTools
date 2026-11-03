# T-900 Heavy Assault: how the additional unit was implemented

Documentation snapshot: 2026-11-03. Tool context: T3-ModTools 0.6.12. The inspected mod declares version **0.11.30**; that is a mod version, not the tool version.

This is a reconstruction from the current assets, generator, patch manifest, tests and retained development notes. **CONFIRMED** below means the cited implementation or static contract is present; it does not mean a new in-game session was tested for this document. Historical observations and unresolved runtime questions are identified separately.

## 1. What we added, and what we deliberately did not replace

The current project is [t900_heavy_assault](../../../T3/mods/t900_heavy_assault/mod.json). It adds a cast with internal ID `T900HeavyAssault`, displayed as `T-900 Heavy Assault`, and packages the `WM20_DUAL` weapon. The base Heavy Assault cast definition gives it one weapon slot containing `WM20_DUAL`. Other enabled projects can extend that loadout; do not confuse their effective merged result with this project's own definition.

The implementation does not rename the original `T900S` into the new unit. Earlier WM20 dual prototypes used the Supply as a test carrier, but the new cast moved to private paths and restored the original Supply definition. See [the weapon implementation](WM20_DUAL_IMPLEMENTATION.md) for that separate development track.

| Identity | Current meaning |
| --- | --- |
| `t900_heavy_assault` | ModTools project ID and mod folder |
| `T900HeavyAssault` | Engine cast ID; also the required cast asset directory name |
| `CA/casts/T900HeavyAssault.dat` | Health, views, weapon slots and damage zones |
| `CA/casts/T900HeavyAssault/fps` and `/tps` | First- and third-person character resources |
| `CA/Bone/T900HeavyAssault.bon` | Ragdoll mapping selected by the cast ID |
| `MenuDatas/3DModells/t900_heavy_assault.sca` | Menu presentation model, not the in-game TPS model |

## 2. Build the asset package before registering the cast

**CONFIRMED — current files and generator assertions.** The working package has four connected layers:

1. [Cast definition](../../../T3/mods/t900_heavy_assault/files/CA/casts/T900HeavyAssault.dat): exact `Name`, `FpsView`, `TpsView`, `WeaponNumber`, numbered `Slot` entries and weapon names.
2. [TPS resources](../../../T3/mods/t900_heavy_assault/files/CA/casts/T900HeavyAssault/tps): `model.lod`, `model.sca`, `Anim.lib` and `soldier.human`; the FPS directory contains its own `model.sca` and `anim.lib`.
3. Character animations under `CA/tps_skynet` and `CA/fps_skynet`, material/texture references under `CA/textures`, and a separate menu model.
4. [Ragdoll configuration](../../../T3/mods/t900_heavy_assault/files/CA/Bone/T900HeavyAssault.bon), cast sound registration and menu registration.

The native precache routine constructs `CA/Casts/<cast ID>/Fps` and `.../Tps` directly. It does not use the custom view strings to discover arbitrary directory names. The old `t900-heavy-assault` directory therefore was not equivalent to `T900HeavyAssault`, even when a later view load could find its model. The current `runtime_patch.py::main` rejects that obsolete directory and checks the canonical files and view references.

### Keep the animated instance identity

The TPS LOD preserved the original animation-compatible identity:

```text
instance: |t900
mesh:     |t900|t900Shape
root:     |human_root|body_root|root
```

An earlier Blender SCA export changed the instance to `|model_rigged|model_riggedShape`. We rebuilt the TPS SCA from the canonical LOD0 instead of treating an arbitrary renamed mesh as interchangeable. The [reconstruction helper](../../../T3/mods/t900_heavy_assault/rebuild_tps_model_sca_from_lod.py) preserves the canonical instance, bone hierarchy, targets and root, removes LOD-distance properties from the single SCA mesh, and includes the character SCA's `Ital` terminator.

The `Ital` block is structural; it does **not** create an animation controller. Controller creation is a separate precache step described below. This is also why the fact that a visible model comes from `model.lod` does not make every `model.sca` disposable.

### Preserve collision targets and death behavior

The original Heavy export lost 19 bone `Target` volumes even though it retained the skeleton and weights. [repair_tps_collision_targets.py](../../../T3/mods/t900_heavy_assault/repair_tps_collision_targets.py) documents the repair: copy only the physical target blocks from matching T900S bones, preserving the new mesh, materials, matrices and weights.

Death physics needed another resource. The engine resolves `CA/Bone/<cast ID>.bon`; a new cast name does not inherit the Supply BON by implication. We added `T900HeavyAssault.bon` using the Patch 1.16 T900S mapping, retaining its 14 physical assignments under the private name. The generator checks that the file contains `cBoneSetup` and 14 `bone {` records. The [build report](../../../T3/mods/t900_heavy_assault/build_report.json) records the 19 targets and canonical mesh/instance used during that build; it is a historical report, not a fresh hash verification.

## 3. Register more than a menu label

**CONFIRMED — [runtime_patch.py](../../../T3/mods/t900_heavy_assault/runtime_patch.py) and [executable.json](../../../T3/mods/t900_heavy_assault/executable.json).** Adding a row to [MenuDatas/Weapons.dat](../../../T3/mods/t900_heavy_assault/files/MenuDatas/Weapons.dat) was necessary but insufficient. The implementation coordinates these native systems:

| System | Implementation foothold | Why it was needed |
| --- | --- | --- |
| Legal cast list | `build_cast_precache_wrapper`, `precache_t900_heavy_assault_cast_*` | Append the new future-era cast after vanilla IDs, without shifting existing identities |
| Animation/controller precache | `build_character_precache_wrapper`, `precache_t900_heavy_assault_character_*` | Create FPS/TPS controllers before a spawn calls `cPlayerController::Clone` |
| Native movement type | `t900_heavy_assault_native_t900s_type` | Route the custom cast to native type 4, as T900S, rather than the unknown-name human fallback |
| HUD family | `t900_heavy_assault_terminator_hud_classifier` | Select the Terminator circular reticle/layers instead of the human fallback |
| Sound and impacts | Private cast sound registry entries and existing manifest patches | Make the new ID use the intended mechanical voices and Terminator impact handling |

The native-type patch was introduced after `Alt` could enter a human crouch state unsupported by the T900 rig. It is a compatibility patch for this known cast and supported executable, not a general character-registration API. Do not copy its byte comparisons to an arbitrary new cast name.

### Precache every scene, and only in the correct era

The animation hook preserves the original events and adds the Heavy precache alongside the native T900S event for each scene. An earlier process-global “already loaded” flag survived map teardown, while the scene controller cache did not; that design was removed.

The physical cast-list hook additionally follows the native future/present discriminator. Heavy is appended in future maps; present maps keep the vanilla list. The client skip path also stays intact. This avoids relying on the menu's era restriction to protect a different native loading path.

Historical crash reports at `0x00487240` motivated this work. **UNKNOWN:** the retained era notes explicitly leave full real-game future → present → future acceptance pending; emulator coverage must not be presented as a completed new gameplay test. See [the era regression suite](../Automated%20Tests/test_t900_map_era.py).

## 4. Give the bot its own identity without losing the appropriate aim profile

**CONFIRMED — current generator and [aim-profile tests](../Automated%20Tests/test_t900_ai_aim_profile.py).** Merely assigning the native T900S type did not make every AI profile lookup use T900S. `build_ai_aim_profile_wrapper` runs after native `aiAgent::Respawn` initialization, recognizes the full Heavy cast name case-insensitively and copies only seven current Supply aim fields:

- aim clamp;
- best and worst aim offsets;
- sure-shot and worse-shot distances;
- error caused by movement and by time.

It resolves the Supply profile again for each respawn, after the current map/difficulty configuration is available. It does not copy combat flags, inventory or the entire profile, and does not retain profile pointers across maps. If the donor/profile is missing, native Heavy initialization remains usable.

An earlier implementation used absolute DLL data addresses. Historical live inspection found the patched AI DLL relocated away from its preferred base, so those newly injected addresses did not resolve correctly. The current helper uses runtime-relative addressing. Tests cover multiple load bases, register/flag preservation, missing profiles and map reloads.

**UNKNOWN:** copying the intended profile alone was not proven to explain or eliminate every reported upward aiming anomaly. Do not use this document as evidence that unrelated AI shaking, friendly-fire behavior or ERR-ANM-01 is solved.

### Automatic appearance is a probability, not a population quota

`HEAVY_ASSAULT_BOT_PERCENT` is an integer from 0 to 100. **The inspected source currently sets it to 10.** Older README text and some comments still describe a test setting of 99; use the executable constant as the current configuration.

`build_ai_spawn_share_wrapper` removes Heavy from the ordinary balancing competition; `build_ai_spawn_chance_wrapper` then performs an independent Heavy choice for each eligible Skynet respawn before weapon selection. A failed draw preserves another valid native choice. In the unusual case that Heavy is the only registered class, preserving a valid descriptor takes precedence over inventing an invalid fallback. Existing living bots and manual player choice are not changed.

The current contract is exercised in [test_t900_ai_spawn_probability.py](../Automated%20Tests/test_t900_ai_spawn_probability.py). The similarly named `test_t900_ai_spawn_share.py` belongs to the earlier share-based investigation; do not describe its old balancing behavior as the current probability algorithm.

## 5. HUD and audio integration

The retained HUD change recognizes the common `T900` prefix for the native Terminator presentation. Yellow vision, Q-selector and noise-suppression experiments from v0.11.4–v0.11.6 were removed together after death/respawn problems. The [mod history](../../../T3/mods/t900_heavy_assault/README.md) records the return to the stable classifier in v0.11.7. A screenshot or old note showing the yellow experiment is not the current feature contract.

Cast sound entries exist in `Sound11`, `Sound22` and `Sound44`, including `Sound/Casts/casts.dat` and `Sound/Casts/T900HeavyAssault/human.dat`. The implementation reuses Supply voice resources rather than duplicating all WAV files. Registration must remain consistent at every supported audio-quality setting.

## 6. How to extend this work safely

For another additional unit, reuse the **sequence**, not the binary addresses or numeric IDs:

1. Choose a unique engine cast ID and make its view directories match exactly.
2. Author the TPS/FPS models, preserve required animated instance and bone identities, and audit collision targets after export.
3. Add the cast definition, private ragdoll mapping, animation libraries, audio mappings and menu model.
4. Trace legal-cast registration, animation/controller precache, native movement type and HUD selection separately. A successful menu preview does not validate any of the others.
5. Add only the needed AI behavior, using current map/difficulty data and relocation-safe code.
6. Encode target-specific patches with unique AOB anchors, expected bytes, bounded code/data reservations and correct continuations. Preserve pristine `T3.exe` and `Ai.Dll`.
7. Review the effective overlay and manifest when combining mods. Topmost enabled mod wins ordinary asset conflicts; incompatible executable writes fail instead of following asset priority.

The historical [dual prototype builder](../../../info%20y%20documentacoin%20previa/dual_gun_mod/build_dual_wm20.py) is research material, not an automatic rebuild recipe for the current unit. Its old assumptions and relocated default paths must be reviewed before any reuse.

## 7. Validation and acceptance checklist

These are recommended checks, **not commands executed while writing this document**. Use a known Python 3.9+ interpreter, not an unverified system `python` alias.

From the workspace root, current Heavy generator validation is explicitly non-writing without `--write`:

```powershell
& "<Python 3.9+ executable>" "T3/mods/t900_heavy_assault/runtime_patch.py"
```

Inspect and run the focused unit suites with their required dependencies: `test_t900_map_era.py`, `test_t900_ai_aim_profile.py`, `test_t900_ai_spawn_probability.py` and `test_t900_muzzle_ownership.py` under `AI Framework/Automated Tests`. Several execute x86 fixtures through Unicorn; missing emulation dependencies are not a gameplay pass.

Only after an intentional implementation change, use ModTools **Build Mods + Modded EXE** to regenerate the manifest/output set. Check the winning `MenuDatas/Weapons.dat`, cast file and both `Anim.lib` files in the compiled overlay. Launch from the resulting `T3_Modded.exe`, not the pristine executable, and test:

- menu availability and spawn in future maps; no added Heavy entry in present maps;
- player and bot idle, walk, run, turn, fire, weapon change and native movement restrictions;
- death collision, ragdoll, return to selection and respawn;
- repeated map changes, including future → present → future;
- bot probability over many **respawns**, not a single population snapshot;
- original Supply, Heavy and human units as negative controls;
- combined loadouts and dual effects with the other enabled weapon projects.

Record the exact load order, original/generated hashes, selected map and difficulty with any runtime result. No game files, manifests or generated executables were changed to produce this documentation.
