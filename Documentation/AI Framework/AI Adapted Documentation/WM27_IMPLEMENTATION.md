# WM-27 Plasma: implementation and lessons learned

Documentation snapshot: 2026-11-03. Intended for the T3-ModTools 0.6.12 project workflow. This is a reconstruction from the current sources and recorded research, not a claim that a new game session or regression suite was run while writing it.

Evidence terminology: **CONFIRMED** identifies a current source contract, asset, or existing assertion; **OBSERVED (historical)** identifies behavior recorded during development; **UNKNOWN** identifies a remaining verification gap. Historical numbers are not automatically current configuration values.

## 1. What we added

WM-27 is an independently selectable plasma weapon for the T900 Supply cast, based on the original WM20 assets. It is not a global replacement of WM20. A separate directory, weapon registration, sound subtype, graphics precache, and animation-family adapter make the new identity usable by the engine.

| Identity | Current value | Meaning |
| --- | --- | --- |
| Project directory | `T3/mods/wm27_plasma` | Filesystem location; not the mod ID |
| Mod ID | `wm27` | Dependency/load-order identity in `mod.json` |
| Weapon directory/name | `WM27` | Gameplay and resource lookup identity |
| Display name | `WM-27 Plasma` | User-facing label |
| Menu ID | `24` | Entry in this project's `MenuDatas/Weapons.dat`, not a universal gameplay ID |
| Projectile/sound subtype | `27` | Independent sound identity with explicit visual routing |
| Reused animation family | WM20, base `244` | Selected by an exact-name adapter |

**CONFIRMED:** these identities are separate namespaces. In particular, a menu index or animation-family index must never be substituted for a dynamically registered gameplay weapon ID.

Primary sources: [mod.json](../../../T3/mods/wm27_plasma/mod.json), [runtime_patch.py](../../../T3/mods/wm27_plasma/runtime_patch.py), [asset_sources.json](../../../T3/mods/wm27_plasma/asset_sources.json), and [research chronology](../../../T3/mods/wm27_plasma/RESEARCH.md).

## 2. Asset construction

The original source record identifies `Game.cod` as the donor for WM20's SCA, LOD, bullet model, animation, material, options, and gameplay descriptor. The shared menu and sound lists were taken from the existing Heavy Assault overlay so that its registrations survived.

The construction sequence was:

1. Copy the donor weapon into `files/weapons/WM27/`, retaining its geometry, skeleton, weighting, and animation contract.
2. Rewrite internal resource-directory and material references to WM27. Merely renaming a folder does not rewrite strings inside SCA/LOD/material files.
3. Install `wm27.dds` and `wm27.mat` in that directory. Keep all texture references consistent across the LOD and SCA representations.
4. Retain `WM20_idle.anm` and the appropriate `anim.lib` references. A donor filename can remain unchanged when it is intentionally referenced under the new weapon directory.
5. Register the weapon in `MenuDatas/Weapons.dat`, add it to T900S's available choices, and add the cast gameplay registration in `CA/casts/T900S.dat`.
6. Add the independent sound resources, visual adapters, graphics precache, and animation-family recognition described below.

Relevant files: [weapon asset directory](../../../T3/mods/wm27_plasma/files/weapons/WM27), [menu registrations](../../../T3/mods/wm27_plasma/files/MenuDatas/Weapons.dat), [T900S descriptor](../../../T3/mods/wm27_plasma/files/CA/casts/T900S.dat), [FPS animation library](../../../T3/mods/wm27_plasma/files/CA/casts/T900S/fps/Anim.lib), and [TPS animation library](../../../T3/mods/wm27_plasma/files/CA/casts/T900S/tps/Anim.lib).

### Menu model correction

The initial menu model was a combat SCA with two bones and a `DIFFUSE_SPECULAR` shader. The corrected preview instead uses the original static `MenuDatas/3DModells/westinghouse_menu.sca` template, with no bones and a `BASE` shader. Its texture reference becomes `wm27_menu.tga`.

The distinct TGA basename matters: the recorded correction avoided the engine resolving the combat DDS instead. The source verification records preserved UVs and triangles rather than attempting to fix the preview by changing the combat mesh. The current runtime generator does not regenerate this user-edited menu asset.

Sources: [wm27_menu.sca](../../../T3/mods/wm27_plasma/files/MenuDatas/3DModells/wm27_menu.sca), [menu verification record](../../../T3/mods/wm27_plasma/menu_verification.json). That record describes its audited revision; it is not a fresh verification of every future edit.

## 3. Why asset registration alone was insufficient

**OBSERVED (historical):** the early implementation displayed the model but produced a low camera and missing bot walking animations. Intercepting only two public `WeaponID` functions had not covered the compiler's inlined family lookups.

**CONFIRMED:** the current generator patches the 25 audited handheld lookup calls: two public lookups plus 23 inlined searches in `Animate_UpperBody`. The adapter matches the exact name `WM27` only when the search is against the WM20 family entry. It then reuses base `244`. Other names and table entries retain the original CRT search path.

Do not broaden this into a rule to patch every string search in the controller. Stationary-weapon and library searches were deliberately excluded. Adding `HAND_WM27_*` entries to `Anim.lib` alone did not solve the family-selection problem.

The graphics `precache()` adapter separately adds WM27 to the native graphics loader and then preserves the existing WM20 call, including the `this` pointer and original arguments.

Current shared integration has grown beyond the initial WM27 revision: `animation_alias()` also recognizes WM32, `dual_animation_alias()` recognizes WM27_DUAL and WM32_DUAL against the separate WM20_DUAL family, and the same module contains Supply and Heavy bot-selection helpers. Do not replace this shared module with an old WM27-only copy.

Sources: `ANIMATION_CALLS`, `animation_alias()`, `dual_animation_alias()`, and `precache()` in [runtime_patch.py](../../../T3/mods/wm27_plasma/runtime_patch.py); exact-name and ABI assertions in [test_adapters.py](../../../T3/mods/wm27_plasma/test_adapters.py).

## 4. Gameplay, sound, and visual routing

**CONFIRMED — current asset values:** [weapon1.option](../../../T3/mods/wm27_plasma/files/weapons/WM27/weapon1.option) contains `shootsPerMin 5.8`, `subType 27`, `damage 0.16 0.16`, `speed 400`, `throw 0.5`, and `bullets 300`. [Gameplay.dat](../../../T3/mods/wm27_plasma/files/weapons/WM27/Gameplay.dat) retains `Type Automate`.

Despite the field's name, the audited primary-fire code computes the requested interval as `1 / shootsPerMin`. Thus `5.8` requests approximately 0.1724 seconds per firing cycle, or 348 cycles/minute; animation and update timing may constrain the observed rate. Do not treat the value as a literal rounds-per-minute count.

For audio, the project registers WM27 at subtype 27 in the shared `Sound11`, `Sound22`, and `Sound44` weapon lists and supplies `Sound/Weapons/WM27/weapon.dat` plus `wm27_fire.wav` in each quality directory. Update all three when replacing the sound. The current sound registry reaches the engine's 32-entry capacity; do not append further entries without auditing capacity or deliberately reusing a suitable registration.

For graphics, `visual_route()` maps subtype 27 to WM20's tracer/muzzle preset index 1. `impact_route()` runs after the native/SFX classification and selects the Enhanced SFX blue particle bank 24 if its runtime pointer exists; otherwise it falls back to native plasma bank 12. Other subtypes retain their existing route. Sharing a visual preset does not mean sharing the WM20 firing sound.

The desired current configuration has no secondary-fire definition. At this snapshot, the single WM27's `weapon2.option` is absent; the tests explicitly accept either an absent file or a comment-only file. Historical prose that says the file necessarily exists is outdated. Check the effective virtual filesystem as well: removing a project file would not erase a same-path file supplied by another enabled overlay. A defined secondary option with zero ammunition is not equivalent to having no secondary option.

Sources: [sound registry](../../../T3/mods/wm27_plasma/files/Sound11/Sound/Weapons/weapons.dat), [sound descriptor](../../../T3/mods/wm27_plasma/files/Sound11/Sound/Weapons/WM27/weapon.dat), [visual-route tests](../../../T3/mods/wm27_plasma/test_wm27.py), and `test_native_option_loading_matches_equipped_weapon` in [test_adapters.py](../../../T3/mods/wm27_plasma/test_adapters.py).

## 5. Bot inventory: the important correction

**OBSERVED (historical):** bots could visibly hold WM27 while firing with WM20's cadence and sound.

**CONFIRMED:** the native option-loading code traverses the inventory in descending slot order. WM20 and WM27 both declare `option weapon 0`. Equipping both alternatives caused the first primary option to remain in the primary control slot while subsequent options replaced the secondary slot. Swapping the visual inventory order was not a valid solution.

The corrected `bot_loadout()` changes only the local inventory copy on the default-respawn path:

1. Validate the exact T900S cast and the expected weapon names/slots.
2. Choose one plasma alternative and place it in slot 0.
3. Clear unused alternative slots, rather than equipping all of them simultaneously.
4. Resolve `T_AMMO` through `cBase::SearchWeaponByName` and use the returned gameplay ID for slot 1.
5. Leave that slot empty if the dispenser is absent; preserve registers, stack, and the shared cast descriptor.

Explicit player selections bypass this default-loadout hook. The original two-rifle setup gave approximately half WM20 and half WM27; current integration can include WM32, so the two-choice description is not a universal probability contract. Small samples also need not contain equal counts.

The name-based dispenser fix was required because menu ID 19 and animation index 20 were not valid substitutes for the loaded `T_AMMO` gameplay ID. **OBSERVED (historical, 2026-10-07):** the user confirmed that the corrected bot approached, equipped T_AMMO, and dispensed two boxes. This does not independently verify restoration of the primary weapon or exhausted-stock behavior.

The WM27 manifest itself targets `T3.exe`, not `Ai.dll`. Its tests nevertheless execute native option-loading and missing-secondary behavior from both binaries. This distinction prevents incorrectly inferring AI correctness from player-only tests.

See also [T900S request-ammo investigation](T900S_REQUEST_AMMO_FIX.md).

## 6. Safe changes and build integration

For ordinary tuning, edit the current option/texture/audio files and use T3-ModTools' build action. The current runtime generator only regenerates its executable manifest; it does not reset the weapon's editable values. Do not use the old one-off creation script as a tuning command: initial generators may restore obsolete defaults or overwrite later integration.

The current [mod.json](../../../T3/mods/wm27_plasma/mod.json) opts into runtime caching with an empty policy object. Descendant projects explicitly depend on this project where needed. Generator dependency order and visible mod priority are different concerns: the top enabled mod wins shared asset paths, while declared generator dependencies determine preparation order.

Shared files such as `MenuDatas/Weapons.dat`, cast descriptors, and sound registries are whole-file overlays, not automatically merged records. When integrating another weapon, ensure the winning version retains every required registration. Prefer checking the actual build manifest to repeating an old instruction to put every mod "on top."

The generator restricts support to the recorded PE32 x86 target, verifies its SHA-256, unique anchors, original calls, section bounds, unused zero padding, branch ranges, and nonoverlapping writes. Its `.rdata` tail is mapped read/execute within the existing raw section; it is not arbitrary free space for other mods. New code must also remain compatible with Heavy/WM32 cave allocations. Do not transplant recorded addresses to another executable version.

## 7. Verification checklist

The existing tests are evidence of intended coverage; they were inspected, not rerun for this documentation update.

- [test_wm27.py](../../../T3/mods/wm27_plasma/test_wm27.py): native/custom visual routes and fingerprinted manifest.
- [test_adapters.py](../../../T3/mods/wm27_plasma/test_adapters.py): native option insertion for both binaries, absent-secondary exits, impact flags/fallbacks, exact animation names, precache ABI, bot selection, and other-cast guards. Unicorn is a test dependency, not a requirement for playing the mod.
- Generator without `--write`: checks that the declarative manifest matches the generated current patch. Use a modern Python environment with required dependencies; preserve original binaries.
- Build review: confirm the effective WM27 resources, required registrations, no conflicting executable writes, and unchanged pristine inputs.
- New game session: compare WM20 and WM27 on player and bots; inspect FPS/TPS, walking/running, sustained fire, actual sound/cadence, primary impacts with and without the SFX overlay, secondary input, and Request Ammo.

**UNKNOWN:** the historical research explicitly leaves some in-game cadence/audio/impact and secondary-removal checks pending. Source inspection and x86 emulation do not establish visual quality or perceived audio in the current load order. Record fresh results with exact input hashes and enabled mods when performing those checks.

Related implementation: [WM-27 Dual](WM27_DUAL_IMPLEMENTATION.md).
