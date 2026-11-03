# WM-20 Dual: how the two-rifle implementation was built

Documentation snapshot: 2026-11-03. Tool context: T3-ModTools 0.6.12. Current owner: [t900_heavy_assault](../../../T3/mods/t900_heavy_assault/mod.json), mod version 0.11.30.

**CONFIRMED** means backed by the inspected implementation/assets or an enforced static test contract. Historical gameplay findings are not new verification runs. No generator, patch, live-memory calibration or game session was executed for this document.

## 1. Current identity versus the prototype

`WM20_DUAL` is now packaged inside `t900_heavy_assault`; it is not necessary to recreate the old standalone `wm20_dual` mod. The [historical prototype README](../../../info%20y%20documentacoin%20previa/dual_gun_mod/README.md) describes an earlier Supply loadout, single-rifle placeholder and second-instance renderer. Those statements were superseded by the two-rifle mesh/private-bone implementation and the separate Heavy Assault unit.

| Layer | Current identity or resource |
| --- | --- |
| Runtime weapon directory | `weapons/WM20_DUAL` |
| Menu display name | `DUAL WM-20 PLASMA` |
| Menu ID in the project's own Weapons.dat | `23` |
| Character animation family | `HAND_WM20_DUAL_*` |
| Registered family base in current manifest | `514` |
| Right weapon bones | `|root|b1` and `|root|b1|b2` |
| Private left weapon bones | `|root|b1|d3` and `|root|b1|d3|d4` |
| Carrier in the base package | `T900HeavyAssault` |
| Menu preview | `MenuDatas/3DModells/wm20_dual_menu.sca` |

The numbers above describe this implementation, not free IDs for a new mod. Check every enabled project's tables before allocating another family or menu slot.

## 2. Clone the weapon assets, then connect every registry

The private [weapon directory](../../../T3/mods/t900_heavy_assault/files/weapons/WM20_DUAL) contains `model.lod`, `model.sca`, materials/textures, `bullets.sca`, `Gameplay.dat`, both option files, `anim.lib` and `WM20_idle.anm`. Its gameplay category remains `Automate`.

We registered the new name in the menu, cast inventory, native weapon graphics precache, animation family and all three sound-quality banks. Merely adding the menu row originally allowed selection of an unprecached weapon and produced a null-weapon failure. The current Heavy cast and weapon precache are distinct from the display label.

The [manifest](../../../T3/mods/t900_heavy_assault/executable.json) includes:

- `precache_wm20_dual_weapon_*` for model, weapon animation library and projectile resource loading;
- `register_wm20_dual_animation_family_entry` and `move_weapon_animation_table_sentinel` for the shared animation-family table;
- `wm20_dual_exact_family_prefix_guard_*` to prevent a premature `WM20` substring match when the exact requested name is `WM20_DUAL`.

That last guard matters: a new name containing an old family name can still resolve to the old family if the native lookup is substring-based. The guard is narrowly scoped; it is not a global replacement of every native substring comparison. Some manifest IDs retain historical `b3/b4` wording even though the actual bone names are now `d3/d4`.

## 3. Two visible rifles are not automatically two hand attachments

The native character draws its active weapon on `right_wrist`. Duplicating geometry inside a LOD does not make half of it follow `left_wrist`; both pieces initially inherit the same weapon-object transform.

The retained solution uses two rifle submeshes, with the left rifle weighted to a private `d3/d4` branch. The [archived asset builder](../../../info%20y%20documentacoin%20previa/dual_gun_mod/build_dual_wm20.py) contains the reconstruction functions `prepare_authored_dual_lod` and `prepare_dual_weapon_animation`: preserve authored geometry/weights, create or preserve the left branch, and reset that branch through the weapon animation before applying the live hand adjustment. It is evidence of the construction method, **not** a safe command to regenerate today's project without review; its relocation also makes its original default-path assumptions stale.

The current [runtime generator](../../../T3/mods/t900_heavy_assault/runtime_patch.py) updates the private branch immediately before the relevant draw. Conceptually the relative transform is:

```text
left_wrist * inverse(right_wrist) * view_calibration
```

The validated path uses row-vector matrices. Both global bone pose and final skinning matrix are updated; writing the pose alone left the renderer using an unchanged `inverseBind * currentPose` result. Bone lookup is by individual name, not guessed neighboring memory offsets.

### Why d3/d4, not b3/b4?

Several vanilla weapons already have `b3` or `b4` for moving parts. Using those names as a dual signature deformed unrelated models. The private, same-length names `d3/d4` were introduced to keep the hook narrowly identifiable without resizing existing code/data layouts. Current validation rejects the old `|root|b1|b3` branch in the dual LOD and weapon ANM.

### FPS, TPS and shadows are separate consumers

The visible TPS hook, `build_visible_adapter`, updates the branch in `cSceneTask` before native rendering. FPS uses `build_fps_adapter` in `cHumanView::ShowFPSView`; the shadow pass has its own `build_shadow_adapter`.

Historically, driving the branch only from shadow rendering caused distant or newly spawned rifles to remain rigid when that pass was skipped. Updating visible rendering fixed the dependency; a later separate shadow adapter kept shadows aligned too. Therefore the current rule is not “remove shadow support,” but “do not make visible pose depend on a shadow pass.”

TPS keeps the authored mesh alignment. FPS has a separate calibration matrix because its wrist bases differ. Do not rotate the shared LOD to fix only FPS and thereby break TPS.

## 4. Character animations and weapon animation are different layers

The character's FPS and TPS libraries each expose seven family states:

```text
HAND_WM20_DUAL_IDLE
HAND_WM20_DUAL_WALK
HAND_WM20_DUAL_RUNNING
HAND_WM20_DUAL_FIRE
HAND_WM20_DUAL_SECOUNDARY_FIRE
HAND_WM20_DUAL_CHANGE_BACK
HAND_WM20_DUAL_CHANGE_GO
```

Preserve the native spelling `SECOUNDARY`. Five custom dual animation files supply idle, walk, run, fire and secondary fire; the two change states reuse the corresponding vanilla WM20 clips in this package. See the [TPS library](../../../T3/mods/t900_heavy_assault/files/CA/casts/T900HeavyAssault/tps/Anim.lib) and [FPS library](../../../T3/mods/t900_heavy_assault/files/CA/casts/T900HeavyAssault/fps/anim.lib).

The original normalization step restored canonical character joint paths and retained the upper-body overlay joint set instead of exporting an entire body pose over locomotion. The stored [build report](../../../T3/mods/t900_heavy_assault/build_report.json) records that historical normalization and frame-count corrections. Do not apply its exact joint count or frame timing blindly to another rig/animation role.

The weapon's own `anim.lib` exposes `WEAPON_IDLE` and `WEAPON_FIRE`, both referencing `WM20_idle.anm`. This weapon animation resets the private branch; the character clips move the wrists. Neither registration substitutes for the other.

## 5. Create two physical shots without charging twice

**CONFIRMED — `build_dual_fire_common` and the player/AI stubs.** The public native firing path still applies cadence and ammunition accounting once. At the internal projectile-creation call, the dual wrapper calls the appropriate implementation twice:

- primary duplicates plasma only;
- secondary duplicates the grenade/missile-mode projectile only;
- the locator's lateral component is temporarily offset symmetrically, then restored;
- the original object/controller and call arguments are preserved between calls.

The current physical separation is `DUAL_PROJECTILE_LATERAL_SEPARATION = 0.28`, represented by symmetric half-offsets. The generator explicitly checks the lateral Z locator fields, not vertical Y. These are this engine path's physical locator axes; they are not the same convention as every Blender or muzzle-calibration UI axis.

The primary option contains `gameRadius -0.0`. Negative zero is used as a binary marker while remaining numerically zero; shared dual detection now checks the primary so a dual weapon without secondary fire can participate. WM20 Dual also retains the secondary marker. Do not “clean up” the sign to `0.0` without replacing and validating the detector.

The inspected option files use primary subtype `1` and secondary subtype `101`. The primary/secondary mechanics are not selected merely by the visible rifle mesh or by how many muzzle sprites appear.

### Player and bots require separate hooks

The player executes the `cObjectControl` implementation in `T3.exe`; bots use a separate implementation in `Ai.Dll`. The manifest therefore contains both target families. ModTools generates `T3_Modded.exe` and the patched `A2.Dll` from pristine originals.

Earlier failures established important contracts: preserve `ECX` between internal method calls; obtain the physical object through the validated controller path rather than assuming `EBP` is populated; preserve exact stack offsets; return through each module's local continuation. AI stubs now resolve their module-local addresses when the DLL is relocated. A working player shot is not evidence that bot firing is correct.

## 6. Duplicate the visual muzzle separately, with the correct owner

Two physical projectiles do not automatically create two muzzle effects: scene events consolidate the visual work. The second muzzle needed its own creation, bank selection, update and lighting handling.

The retained implementation validates the event actor's **currently equipped visible model** and its private `d3` signature, together with the supported weapon preset. It does not rely on one global “last dual shooter” flag or a three-actor authorization queue. The current actor `AddNew` call-site is shared by character FPS/TPS; the other historically confused site belongs to stationary weapons.

Native `AddNew` allocates by actor and bank. The original right effect uses bank `A3 = 0`, while the copied left effect uses `A3 = 1`; duplicating into bank zero simply overwrote the same effect. Live `SetPosition` handling revalidates ownership and follows movement/pitch/yaw during the effect's lifetime. `build_muzzle_dual_actor_validator`, `build_muzzle_native_add_wrapper` and `build_muzzle_live_update_wrapper` are the main reading points.

Close consecutive impacts also needed a bounded exception to the native repeated-impact visual suppression. That visual fix should not be mistaken for the physical second shot or for damage accounting.

`WM20_DUAL_SECONDARY_MUZZLE_ENABLED` is currently **False**. This hides the WM20 Dual grenade muzzle only; it does not remove either grenade, alter its damage or globally change `Particles/MuzzleFire.dat`. The filter compares incoming raw subtype **101**, before native visual conversion to index 20. Comparing 20 at that earlier hook was the historical bug. The primary retains its dual plasma effects.

See [test_t900_muzzle_ownership.py](../Automated%20Tests/test_t900_muzzle_ownership.py) for dual/vanilla player-bot permutations, multiple actors, slot changes, null models, raw-subtype conversion, register preservation and transformed tracking. The suite also covers WM27 Dual compatibility; shared support does not mean every future subtype is automatically accepted.

## 7. Calibrate appearance without changing projectile physics

The [calibration guide](../../../T3/mods/t900_heavy_assault/CALIBRAR_FPS.md) and [calibration implementation](../../../T3/mods/t900_heavy_assault/calibrate_fps_live.py) separate these settings:

| Setting | Affects |
| --- | --- |
| `FPS_LEFT_RIFLE_LOCAL_ROTATION_DEGREES` / `FPS_LEFT_RIFLE_LOCAL_OFFSET` | Left rifle presentation in FPS |
| `FPS_LEFT_MUZZLE_POSITION_OFFSET` | FPS left muzzle placement |
| `TPS_LEFT_MUZZLE_POSITION_OFFSET` / `TPS_LEFT_MUZZLE_OFFSET_ROTATION_DEGREES` | TPS left muzzle offset, including bots |

Muzzle UI axes are local lateral X, height Y and depth Z. Rotating the TPS offset rotates its displacement around the anchor, not the texture orientation or projectile direction. The guide states these calibration settings are shared with WM27 Dual, so inspect both weapons after changing them.

The panel can write two bounded data blocks into a verified running process and can save constants/manifest fields with backups. That is an intentional live-edit workflow, not a read-only diagnostic step. This documentation task did not use it. For ordinary future changes, inspect the current values instead of copying historical tuning snapshots.

## 8. Menu preview and audio

Version 0.11.30 adds a static two-rifle [menu SCA](../../../T3/mods/t900_heavy_assault/files/MenuDatas/3DModells/wm20_dual_menu.sca). The recorded layout follows the Heavy idle wrist separation and mirrors the left presentation rifle laterally, retaining the original WM20 menu scale, UVs, shader and texture. ModTools packages the saved SCA; this does not rebuild the live weapon LOD. The single WM20 retains its own `westinghouse_menu.sca` reference.

`Sound11`, `Sound22` and `Sound44` each register primary `WM20_DUAL` and secondary sound resources. A correct image or animation does not prove audio registration at every quality setting.

## 9. Regression checklist and safe rebuild boundary

Recommended checks below were not executed for this documentation update:

1. Validate `runtime_patch.py` without `--write`; this checks manifest synchronization and its static invariants without publishing changes.
2. Review the focused muzzle tests, [calibration tests](../../../T3/mods/t900_heavy_assault/test_calibrate_live.py) and the Heavy cast/AI suites before running them with their required Python/emulation dependencies.
3. After an intentional code/asset edit, compile through ModTools from pristine binaries and inspect the winning menu, cast, animation, weapon and sound files. Reject patch conflicts; do not resolve them by silently picking the last writer.
4. In game test primary and secondary separately, in FPS and TPS, for player and bots, moving and stationary, near and far, with shadows both visible and culled.
5. Mix dual and vanilla shooters, switch weapons while effects are alive, respawn and change maps. Check that vanilla weapons with `b3/b4` remain unchanged.
6. Compare ammunition consumption, cadence, two physical impacts and two visual plasma muzzles independently. A muzzle count is not a projectile-count measurement.

Record target hashes, load order and reproduction steps for every runtime acceptance result. Treat all addresses and code-cave reservations in the current generator as target-specific; verify anchors, original bytes, branch destinations and non-overlap before supporting another game executable.

Related unit-level implementation: [T-900 Heavy Assault](T900_HEAVY_ASSAULT_IMPLEMENTATION.md). Current chronological source: [Heavy Assault README](../../../T3/mods/t900_heavy_assault/README.md); read its “removed/superseded” labels before using an old experiment as a recipe.
