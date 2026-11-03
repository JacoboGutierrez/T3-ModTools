# Dual WM-27 Plasma: extending the shared dual-weapon system

Documentation snapshot: 2026-11-03, for the T3-ModTools 0.6.12 project workflow. This guide describes current source contracts and the recorded 2026-10-16 integration, with later asset changes identified explicitly. No generators, builds, or game sessions were run for this documentation update.

**CONFIRMED** means directly supported by current assets/code or an existing assertion. **OBSERVED (historical)** means a recorded runtime outcome. **UNKNOWN** marks an outstanding verification gap. Existing tests are not presented as newly passed tests.

## 1. Design and dependencies

The objective was a separate Heavy Assault weapon, selectable alongside Dual WM-20, using WM27's texture and plasma behavior without replacing the single WM27 on T900 Supply.

| Layer | Identity or source |
| --- | --- |
| Project/mod ID | `T3/mods/wm27_dual` / `wm27_dual` |
| Gameplay and resource name | `WM27_DUAL` |
| Display name / menu entry ID | `Dual WM-27 Plasma` / `26` in this project's table |
| Character | `T900HeavyAssault` |
| Model, private bones, alignment, animation donor | Heavy Assault's `weapons/WM20_DUAL` |
| Texture and original option donor | Single `WM27` |
| Sound/visual subtype | `27`, deliberately reused rather than consuming a new sound slot |
| Animation family | WM20_DUAL, base `514`; not single WM20's `244` |

The [mod metadata](../../../T3/mods/wm27_dual/mod.json) requires mod IDs `wm27` and `t900_heavy_assault`, and declares `provides_weapons: ["WM27_DUAL"]`. Note that the `wm27` mod is stored in the `wm27_plasma` directory. The generator imports its shared family module from that directory and explicitly checks that both prerequisites are enabled.

The declared runtime-cache policy tracks enabled mods and the `../wm27_plasma` dependency. These cache/dependency declarations are not the same thing as visible overlay priority. The current build manager schedules declared project dependencies before dependents while keeping visible priority intact. Verify shared asset winners separately.

Sources: [runtime_patch.py](../../../T3/mods/wm27_dual/runtime_patch.py), [shared WM27 generator](../../../T3/mods/wm27_plasma/runtime_patch.py), [Heavy Assault generator](../../../T3/mods/t900_heavy_assault/runtime_patch.py), and [research chronology](../../../T3/mods/wm27_dual/RESEARCH.md).

## 2. How the independent asset package was constructed

The combat SCA, LOD, bullet SCA, idle ANM, and animation library were copied from the existing Dual WM20. Only resource-path and texture/material references were adapted to `WM27_DUAL` and `wm27.*`. The operation was not a second coordinate conversion and did not invent another dual skeleton.

The inherited contract includes the private `d3`/`d4` bones and the established dual alignment. Preserve these names and their owning model paths: the runtime uses them to distinguish a true dual asset from a single rifle that happens to share subtype 27.

WM27's DDS/material and gameplay options were copied into the new weapon directory. These are independent project assets, not live links to the single rifle. The runtime manifest generator does not automatically propagate subsequent option edits between the two weapons.

`asset_sources.json` records the original construction provenance and hashes. It is a historical source snapshot, not proof that all donor files still have those hashes after later user edits. Current asset tests compare the dual geometry/ANM against the Heavy donor with the intended string substitutions, and also compare selected gameplay fields with the single WM27. If intentionally diverging balance between single and dual, review that equality-test contract rather than assuming automatic synchronization.

Sources: [asset_sources.json](../../../T3/mods/wm27_dual/asset_sources.json), [combat assets](../../../T3/mods/wm27_dual/files/weapons/WM27_DUAL), and `test_assets_and_original_preservation` in [test_dual_wm27.py](../../../T3/mods/wm27_dual/test_dual_wm27.py).

## 3. Options and the dual marker

**CONFIRMED — current values:** [weapon1.option](../../../T3/mods/wm27_dual/files/weapons/WM27_DUAL/weapon1.option) contains `shootsPerMin 5.8`, `damage 0.16 0.16`, `speed 400`, `throw 0.5`, and `subType 27`. Older README/research passages record damage `0.14`; that is historical, not the current file value. `Gameplay.dat` uses `Automate`.

The primary option also contains:

```text
gameRadius -0.0
```

This is a technical marker, not a negative gameplay radius. IEEE-754 negative zero has bits `0x80000000`; positive zero does not. Preserve the sign and exact parsing behavior. Reformatting it as `0` would remove the shared dual detector's identifier.

The shared support was changed to inspect the **primary** option at `control + 0x84`, then its `gameRadius` field at `+0x40`. Previously the detector depended on the secondary option at `control + 0x88`, which failed for a primary-only dual weapon. Dual WM20's primary received the same marker while retaining its own secondary-grenade behavior.

Dual WM27's [weapon2.option](../../../T3/mods/wm27_dual/files/weapons/WM27_DUAL/weapon2.option) is comment-only: there is no registered secondary firing option. Setting secondary ammunition to zero would not express the same contract.

The target behavior is two projectiles per primary cycle. The native cadence code still controls cycles; `5.8` requests approximately 0.1724 seconds between cycles, not 5.8 rounds per minute. Do not double the configured rate just to account for two barrels.

## 4. Registration, animation, and bot selection

The project adds `WM27_DUAL` to the shared menu table and to the Heavy Assault cast's alternatives while keeping `WM20_DUAL`. Its graphics precache hook inserts the new resource and preserves the prior loader call, `this`, and arguments.

The shared WM27 module performs exact-name family recognition against the WM20_DUAL family entry. A name such as `WM27_DUALX` must not match, and the dual must not accidentally take family 244 used by the single WM27/WM32. The current shared adapter also handles WM32_DUAL; do not overwrite that support when maintaining this earlier weapon.

The default Heavy bot loadout chooses **one** complete rifle alternative for slot 0. Equipping both alternatives simultaneously would recreate the native `option weapon 0` collision that previously mixed WM27/WM20 behavior. The source cast remains a catalog of available alternatives; only the local respawn inventory is reduced. Explicit player selections do not use this randomization path.

For the original two-choice setup, the selector produces approximately equal Dual WM20/Dual WM27 choices. The current shared `heavy_bot_loadout()` also accepts the three-choice layout with WM32_DUAL and uses rejection sampling for equal three-way odds. This weapon-selection probability is separate from Heavy Assault's overall spawn share.

Sources: [cast descriptor](../../../T3/mods/wm27_dual/files/CA/casts/T900HeavyAssault.dat), [menu table](../../../T3/mods/wm27_dual/files/MenuDatas/Weapons.dat), `precache()` in the [dual generator](../../../T3/mods/wm27_dual/runtime_patch.py), and `dual_animation_alias()` / `heavy_bot_loadout()` in the [shared generator](../../../T3/mods/wm27_plasma/runtime_patch.py).

## 5. Player, bots, and muzzle effects are separate validation paths

The weapon-specific generator targets `T3.exe`. Shared projectile and muzzle support lives in Heavy Assault and includes distinct player and AI paths. A working player rifle is not proof that the bot implementation works.

The integration exposed two AI relocation bugs: a fixed internal-routine pointer and a jump coupling Ai.dll execution to a T3.exe marker. The corrected AI stubs resolve the internal routine relative to their actual execution address and use a local Ai.dll primary marker. Existing emulation tests cover both the preferred DLL base `0x10000000` and an alternate base `0x08000000`.

For muzzle duplication, subtype 27 is admitted by the shared prefilter, but the runtime also verifies the private `d3` bone on the visible model belonging to the actor. This additional ownership/asset check is essential: single WM27 uses the same subtype and must still receive only one muzzle effect. The dual reuses WM27's existing sound/tracer/impact routes and does not append a new sound-bank entry.

The research records an initially overlapping Ai.dll code-cave allocation that the compiler rejected. The correction moved the blocks; it did not disable conflict detection. Treat this as a reason to retain strict cross-mod write checks, not as a template to reuse those absolute addresses in another executable.

Sources: Heavy's `build_ai_position_independent_stub()` and `build_ai_local_primary_marker()`, the shared detector/dual-fire functions in [runtime_patch.py](../../../T3/mods/t900_heavy_assault/runtime_patch.py), and `test_two_projectiles_player_and_relocated_ai` in [test_dual_wm27.py](../../../T3/mods/wm27_dual/test_dual_wm27.py).

## 6. Menu preview: asset presentation and engine capacity

These are two distinct changes.

### Static two-rifle preview

The current `wm27_dual_menu.sca` is a static, unrigged `BASE`-shader preview using the unique `wm27_dual_menu.tga` texture. It contains two parallel rifles; the left copy is laterally reflected. The separation is approximately `0.5448958523`, taken from the Heavy TPS idle wrist spacing, while each rifle's scale is preserved.

The regression checks reflection of the appropriate model coordinate, normal component and triangle winding, preserved UVs, canonical mesh/instance transforms, and the expanded bounding box. This is a menu-model construction rule for this asset, not a universal instruction to mirror combat LODs on a particular Blender axis. The menu SCA is stored as an authored asset and packed as saved.

Source: [test_menu_models.py](../../../T3/mods/wm27_dual/test_menu_models.py), which checks both Dual WM20 and Dual WM27 and verifies that the integrated menu tables retain the distinct single-rifle previews.

### The 40-entry HUD crash

**OBSERVED (historical):** adding the dual caused startup access violation `004A9CFF`. The original configuration had 27 weapon previews plus 14 cast previews: 41 entries in a shared array with capacity 40.

**CONFIRMED:** the original preview entry stride is `0x108` bytes. The array starts at `this + 0x13E90`; its 41st entry overwrites the count at `this + 0x167D0`. The last cast name, `Arnold`, corrupts that count before the native limit check and the subsequent scale store uses it as an index. `test_hud_preview.py` reproduces the reported EIP and corruption with the original code.

The implemented fix allocates a larger HUD object and moves the preview array to its tail at `this + 0x16830`, with capacity **64** and total allocation size `0x1AA30`. Other member offsets remain unchanged. It updates all audited table references, allocation size, initialization/cleanup, both loading branches, `AddModell`, `FindModell`, and the inlined class-selector lookups. Increasing only a loop limit would still write out of bounds.

`preview_entries()` checks the project's menu against 64 entries. This is not a conversion of all engine tables into dynamic arrays, nor a guarantee about an unrelated higher-priority overlay: always review the actual winning menu and its total previews.

Sources: `hud_preview_patches()` and `preview_entries()` in [runtime_patch.py](../../../T3/mods/wm27_dual/runtime_patch.py), [test_hud_preview.py](../../../T3/mods/wm27_dual/test_hud_preview.py), and [recorded crash analysis](../../../T3/mods/wm27_dual/RESEARCH.md).

## 7. Maintenance and verification procedure

1. Confirm both required mod IDs are enabled and that the current shared Heavy/WM27 support is present. Keep runtime dependency metadata accurate if new external inputs are introduced.
2. Edit the independent dual assets/options deliberately. Retain subtype 27, the primary negative-zero marker, the private-bone contract, and no secondary option unless intentionally redesigning those runtime contracts.
3. Review the winning shared `MenuDatas/Weapons.dat` and cast descriptor. Higher-priority combined overlays may legitimately supersede this project's copies; preserve all enabled weapon registrations rather than forcing this older table to win.
4. Validate the synchronized manifest and rerun the targeted tests in a Python environment with Unicorn and any required project dependencies. Inspect asset tests for intentionally changed donor/balance contracts instead of silently weakening them.
5. Build from pristine `T3.exe`/`Ai.dll`; review patch conflicts, capacity checks, generated resource paths, and the build manifest. Publish the generated executable, AI DLL when required, and archive as a consistent output set.
6. Restart with the generated executable and create a new game so bots receive fresh inventories. Test selection, static menu preview, FPS/TPS, movement, two projectiles/muzzle effects, WM27 audio, no secondary shot, and both Heavy alternatives. Compare the unaffected single WM27 and WM20, plus WM32 families when enabled.

The patch generators validate the exact supported T3 executable hash and original bytes, unique anchors, bounded zero padding, and branch/cave layout; the build manager rejects conflicting writes. Addresses in the research are tied to the recorded pristine binaries, not portable patch instructions.

Existing targeted suites:

- [test_dual_wm27.py](../../../T3/mods/wm27_dual/test_dual_wm27.py): donor assets/options, exact family guards, local bot inventories, two-projectile player/relocated-AI paths, and precache ABI.
- [test_hud_preview.py](../../../T3/mods/wm27_dual/test_hud_preview.py): original crash, full menu loading/lookup/cleanup, allocation, and all 64 entries with a sentinel beyond the array.
- [test_menu_models.py](../../../T3/mods/wm27_dual/test_menu_models.py): static mirrored preview geometry and cross-overlay preview registrations.

**OBSERVED (historical, 2026-10-16):** the corrected executable loaded the HUD and reached game startup without a new crash report. **UNKNOWN:** that startup evidence did not validate every visual/audio/combat scenario. The research explicitly leaves in-game review of the new dual pending; do not upgrade emulation or startup success into a blanket gameplay-validation claim.

Related foundation: [single WM-27 implementation](WM27_IMPLEMENTATION.md).
