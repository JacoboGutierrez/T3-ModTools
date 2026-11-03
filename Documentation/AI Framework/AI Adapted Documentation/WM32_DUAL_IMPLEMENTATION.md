# Dual WM-32 Plasma: implementation and maintenance

Reviewed against repository sources on 2026-11-03. Tool baseline: **T3-ModTools 0.6.12**. Current mod metadata: `wm32_dual`, version `1.0.5`; registered weapon: `WM32_DUAL`.

This guide reconstructs the current implementation and its important corrections. **CONFIRMED** means supported by current code/assertions or existing tests; **OBSERVED** identifies recorded user/capture results; **UNKNOWN** marks missing runtime verification. The tests and historical captures cited here were not rerun while writing this documentation.

## 1. Scope and prerequisites

Dual WM32 is an independent T900 Heavy Assault weapon alongside `WM20_DUAL` and `WM27_DUAL`. It preserves WM32's primary and secondary modes, firing a pair of rifles per accepted firing cycle. It is not a global replacement of the single Supply weapon.

[mod.json](../../../T3/mods/wm32_dual/mod.json) requires these enabled IDs: `wm32_plasma`, `wm27_dual`, `wm27`, and `t900_heavy_assault`. Note that ID `wm27` lives in folder `wm27_plasma`. The declared generator dependencies use folder paths, while the runtime prerequisite check uses mod IDs. Keep Dual WM32 above its lower menu/Heavy providers in visible load order; the compiler runs prerequisite generators first without changing that visible priority.

The authoritative model remains the single weapon's [WM-32 Plasma.blend](<../../../T3/mods/wm32_plasma/files/weapons/WM32/WM-32 Plasma.blend>). There is no separate dual blend to maintain. First export the single through its own generator, then derive the dual from those current exported files. See [the single-WM32 guide](WM32_IMPLEMENTATION.md) for its materials, texture containment, donor and locator contracts.

| Module | Responsibility |
| --- | --- |
| [runtime_patch.py](../../../T3/mods/wm32_dual/runtime_patch.py) | Dependency checks, composed menu/cast, staging, publication and concurrent-edit guards |
| [assets.py](../../../T3/mods/wm32_dual/assets.py) | Duplicate model/animation branches, preserve options, produce menu model, correct primary physics locator |
| [registration.py](../../../T3/mods/wm32_dual/registration.py) | Exact weapon precache, shared aliases and bounded HUD preview capacity |
| [attachment.py](../../../T3/mods/wm32_dual/attachment.py) | Live wrist-based left-rifle attachment and mirrored locator displacement |
| [combat.py](../../../T3/mods/wm32_dual/combat.py) | Both rifles' visual muzzle nodes and tracking |
| [fire.py](../../../T3/mods/wm32_dual/fire.py) | Separate player/AI primary and secondary firing integration |
| [run_pose.py](../../../T3/mods/wm32_dual/run_pose.py) | Private TPS run clip and exact animation selector |
| [fps_calibration.py](../../../T3/mods/wm32_dual/fps_calibration.py) / [calibrate_fps_live.py](../../../T3/mods/wm32_dual/calibrate_fps_live.py) | Saved FPS placement and optional standalone live calibration |

## 2. Deriving two rifles without damaging the source

`assets.dual_model()` requires the exact single rig and weights, then duplicates each source submesh and adds a private branch:

| Branch | Frame bone | Trigger bone |
| --- | --- | --- |
| Original right | `|root|b1` | `|root|b1|b2` |
| Added left | `|root|b1|w3` | `|root|b1|w3|w4` |

The private `w3/w4` names identify this implementation; they are not a general dual-weapon convention. Both model copies initially occupy the same bind coordinates. Runtime attachment performs the placement. The left submesh remaps exact quoted full bone paths and reverses triangle winding to compensate the runtime reflection, while retaining source material data, coordinates, UVs and normals.

`dual_animation()` preserves the existing b1/b2 track bytes. It appends an identity local track for w3 and a remapped trigger track for w4. Copying b1's root translation into its child would apply that offset twice; this is why the identity local frame matters. The same structural process covers the SCA and all four source LOD levels.

Texture files and available matching `.mat` files are copied from the single weapon's referenced assets; unsafe relative paths are rejected. Source files are hashed before use and checked again before return to detect accidental mutation or concurrent edits. `asset_report.json` records the generated files, sources, private branch names and placement contract.

## 3. Why placement uses live wrists, not a fixed sideways offset

The final attachment derives left-minus-right wrist displacement from the current animated character pose, transforms it into the right weapon's frame, and applies that displacement to the private left branch. The left rifle is also reflected laterally about its attachment origin. In this verified native weapon frame, **X runs along the barrel and Y is lateral**; reflecting Y preserves forward X.

The reflection includes the model's lateral offset, not an arbitrary center-of-geometry pivot. Skin matrices are regenerated from inverse bind and current pose. Left winding compensates the negative determinant so the visible face does not become the back face. This attachment is shared by FPS, TPS and shadow drawing; missing private bones or unrelated native callers fall back to native behavior.

The static menu is a separate case. `dual_menu()` measures wrist separation from the Heavy TPS idle pose and creates two static copies. The dedicated single-WM32 menu transform maps weapon Y=0 to menu Z=0.031179, so the left menu copy reflects around that plane. This constant is verified for this donor/export path, not a universal menu coordinate rule.

The detailed native ABI and matrix evidence is retained in [RESEARCH.md](../../../T3/mods/wm32_dual/RESEARCH.md). Avoid replacing this with a screenshot-derived world-space offset: it would not follow animation or arbitrary actor orientation.

## 4. Muzzles, lights and physical projectiles are separate paths

The dual uses the single WM32's private audiovisual banks and subtypes 28/29. Both `f_primary` and `f_secondary` remain authored in the single blend. For visual effects, the code creates/tracks two nodes: actor and actor-plus-stride. It matches the incoming native pose to the active FPS/TPS controller and applies both the live wrist displacement and the mode-specific reflected locator correction.

The native reflected position correction includes `-2 * locator.y * rightWristWorld.rowY`; direction receives the corresponding directional correction but no wrist translation. Current authored locator values are consumed from the WM32 export. The existing Heavy light loop already visits both nodes, so adding another light call would duplicate lights. The combat regression checks exactly two lights for either firing mode.

Physical firing is duplicated **after** the native public ammunition/cooldown decision. The code preserves the original right shot, invokes the left internal shot with the mirrored displacement in the physical-object frame, and restores all three locator float bit patterns afterward. Native aim is preserved. Player and AI implementations are distinct; the AI continuation derives from the actual internal function pointer so module rebasing does not invalidate the return target.

Both authored option files must retain `gameRadius -0.0`. The negative-zero float bit pattern is the dual-fire marker, not a nonzero damage radius. Formatting it as ordinary `0.0` removes the marker even though arithmetic compares the values as equal. Missing or nonmatching identities follow the existing native/other-dual paths.

### Primary origin follow-up

The user reported correct models but a primary projectile origin too far to one side. Native tracing separated visual locator **0** from primary physics locator **2**, while secondary uses visual **1** / physics **3**. The inherited WM20 primary physics Y did not line up with the new authored WM32 barrel.

`assets.align_primary_physics_locator()` now derives **only locator 2 Position.Y from locator 0 Position.Y** in generated dual SCA/LOD. It preserves locator 2 X/Z and direction, and every secondary coordinate. Moving `f_primary` laterally therefore updates the dual primary muzzle and projectile line together. This correction is asset-only; it did not require another executable hook. See [research_primary_locator.md](../../../T3/mods/wm32_dual/research_primary_locator.md) for the captured symptom, competing explanation, native reproduction and remaining visual-verification limit.

## 5. Registration, menu and Heavy inventory

`registration.generate()` adds an independent `WM32_DUAL` precache while preserving the original native call. Exact dual aliases map to the existing `WM20_DUAL` family **514**, not the single family 244. Shared patches intentionally have the same bytes as their prerequisite implementations; conflicting nonidentical writes must still stop compilation.

The bootstrap menu entry uses ID **27**, display name `Dual WM-32 Plasma`, and `MenuDatas/3DModells/wm32_dual_menu.sca`. The Heavy cast receives slot 2 and `WeaponNumber 3`, yielding the three dual alternatives. The shared Heavy bot adapter equips one choice per spawn rather than giving each bot three simultaneous weapons. The Heavy's general spawn probability remains a separate user-controlled setting.

Weapons and casts share the native HUD preview storage. The inherited WM27 Dual relocation increases capacity from 40 to **64** entries, and `preview_entries()` counts all three relevant menu sections, including casts. A menu line can be syntactically valid yet overflow that shared storage; capacity validation is therefore part of registration, not decorative HUD work.

**Important maintenance difference:** Dual WM32's existing `files/MenuDatas/Weapons.dat` is now fully user-authored. `default_menu()` bootstraps it from Dual WM27 only when it is missing. Later builds preserve all existing bytes, including unrelated menu entries, names, comments and formatting. Upstream menu additions do **not** automatically merge into an existing dual menu; incorporate them explicitly and recheck IDs/capacity. The generator refuses publication if the menu changes during the build rather than overwriting the saved edit.

## 6. The private TPS run correction

The October 2026 investigation found a running grip orientation issue. The solution is a private animation, not a hard-coded correction angle and not an edit to the shared WM20/WM27 clip.

`run_pose.derive_clip()` derives the idle right-wrist orientation relative to `hands`, then solves the required wrist-local orientation against each running forearm chain. It preserves wrist translation, other joint matrices, timing and joint order. Finger-local tracks continue to inherit the corrected wrist. `generate_assets()` reads the current Heavy idle/run sources and emits:

- `CA/TPS_SKYNET/t900_run_dual_wm32.anm`;
- a private `HAND_WM32_DUAL_RUNNING` entry in the generated Heavy TPS animation library.

The native role-loader hook assigns running state 516 only to the exact private role. The selector is scoped to state 516, a 32-bone scene controller and the equipped w3-signature weapon. Other states/weapons, missing records and FPS controllers retain native lookup. Normal transitions still blend the running state; the selector does not mutate controller memory. ModTools' automatic UPDOWN composition explicitly maps this private role to its WM20 reference rather than guessing arbitrary role names.

## 7. Optional FPS-only calibration

As of the 2026-11-02 correction, launch **`Calibrar FPS.pyw` in the mod directory**. This is a standalone panel, not an integrated ModTools button. Its saved configuration is [fps_calibration.json](../../../T3/mods/wm32_dual/fps_calibration.json); do not overwrite the user's values with the code's zero default.

The six controls are rotation XYZ in degrees and position XYZ in native units. They affect only the left rifle in a 38-bone FPS controller and its primary/secondary muzzles and lights. TPS, shadows, the right rifle and physical aim remain unchanged. The live wrist displacement is added after the local rotation so the rifle rotates around its left attachment rather than orbiting the right wrist.

The panel's optional in-game hotkeys use Ctrl+Alt+1 through 6 to select an axis and Ctrl+Alt+Up/Down to adjust it. Save writes the authored JSON atomically, checks concurrent edits and retains a previous-value backup; compile afterward for the next launch to use the saved values. A running game only changes when the user explicitly connects and applies the live calibration.

The live writer validates target identity/code consumers and writes only the owned parameter table. Stable even sequence snapshots prevent a render reader from consuming half-written values, and a per-process mutex excludes concurrent writers. This is a controlled data-table update, not permission to patch arbitrary process memory. Research records the visual result/hotkeys as still requiring user validation for that revision.

## 8. Staging, safety and editable ownership

`runtime_patch.build()` checks required enabled IDs, snapshots the menu and calibration, derives assets in a temporary stage, adds the private run clip, validates both negative-zero markers, builds the patch manifest and rechecks saved inputs before publication. The common [generated-asset publisher](../../../T3-ModTools/t3_generated_assets.py) provides rollback and retains authored inputs.

Weapon options are initialized once from single WM32 with the marker inserted, then preserved byte-for-byte. Do not expect later single-WM32 balance edits to overwrite customized dual options. Empty options are not silently repaired: the full runtime build rejects missing dual markers even though the lower-level asset helper preserves the file.

New attachment, muzzle, firing and run adapters occupy owned reservations in ModTools' generated `.t3ldr` storage. The historical first integration detected an AI helper overlap with Enhanced Units; the final secondary bridge uses a bounded absolute jump to extension code. This is why checking each manifest alone is insufficient: test their combined ownership map. Do not weaken overlap checks or reuse a cave because it happens to look empty in an already generated binary.

The current generators fingerprint pristine binaries and validate hooks, expected bytes, bounds and shared writes. `T3_Modded.exe`, `A2.dll` and `Mods.Cod` are generated outputs, never the next pristine baseline. Addresses and fingerprints in the research notes describe the inspected build only.

## 9. Existing regression map and release checklist

| Test file in `T3/mods/wm32_dual` | What it checks |
| --- | --- |
| [test_assets.py](../../../T3/mods/wm32_dual/test_assets.py) | Source preservation, canonical branches, left winding, identity animation track, four LODs, menu and option markers |
| [test_attachment.py](../../../T3/mods/wm32_dual/test_attachment.py) | Actual native math/ABI, live wrists, mirrored locator deltas and scoped fallback |
| [test_combat.py](../../../T3/mods/wm32_dual/test_combat.py) | Both modes/views, real effect updates and the existing Heavy two-light loop |
| [test_fire.py](../../../T3/mods/wm32_dual/test_fire.py) | Player/AI duplication, restoration, other weapons, disabled dispatch and enabled-manifest collision checks |
| [test_physics_locators.py](../../../T3/mods/wm32_dual/test_physics_locators.py) | Primary lateral alignment through original player code and rebased AI getters |
| [test_registration.py](../../../T3/mods/wm32_dual/test_registration.py) | Exact aliases, three-choice Heavy selection, native precache continuation and shared preview capacity |
| [test_editable_menu.py](../../../T3/mods/wm32_dual/test_editable_menu.py) | Bootstrap versus complete preservation of an existing authored menu |
| [test_run_pose.py](../../../T3/mods/wm32_dual/test_run_pose.py) | Wrist-only rotation change, role loading, scoped selector and patch boundaries |
| [test_fps_calibration.py](../../../T3/mods/wm32_dual/test_fps_calibration.py) | Saved/live data safety, six controls, mesh/effect agreement and FPS-only scope |

Native-code regressions need their existing Python dependencies, including Unicorn; some also use NumPy and Windows GUI facilities. Read each test's imports/setup before choosing an interpreter. Validation-mode `runtime_patch.py` still stages generated assets and compares them; `--write` intentionally publishes them. No such command was run for this documentation update.

Before a release, save the source blend, rebuild prerequisites through ModTools, inspect the generated report and winning menu/Heavy files, then test each dual option as player and AI. Check both shots, ammunition/cadence, muzzle/light tracking, FPS/TPS/shadows, running transitions, death/ragdoll behavior and other dual weapons. Recheck calibration separately from physical projectile aim.

**OBSERVED, historical:** the primary-locator investigation records the user's confirmation that the two models looked correct in FPS/TPS before the projectile-origin follow-up. **UNKNOWN in the cited revision records:** final visual approval of the later origin correction, private run grip and live-calibration behavior. Structural tests, native x86 emulation and package checks are strong evidence for their specific invariants, not substitutes for those in-game checks.
