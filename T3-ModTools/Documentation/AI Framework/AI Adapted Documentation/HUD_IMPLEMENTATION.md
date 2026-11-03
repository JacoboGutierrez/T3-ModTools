# How we edited the T3 HUD

Documentation snapshot: 2026-11-03. Tool baseline: T3-ModTools 0.6.12.

This guide reconstructs the HUD changes from the current source and retained research. It is not a claim that every feature was visually retested for this documentation update. See the [implementation index](IMPLEMENTATION_INDEX.md) for evidence labels and shared build rules.

## 1. Separate layout, native behavior, and world tint

These are different systems. Editing one does not automatically change the others.

| Goal | Source or mechanism | Important boundary |
| --- | --- | --- |
| Move or recolor a label, frame, or image | `MenuDatas/hud.dat`, referenced texture atlases and font files | The asset is a complete overlay, not a per-widget merge. |
| Select the Terminator HUD for a new unit | Native cast classification in `T3.exe` | A new cast name is not automatically recognized by the original closed list. |
| Change searching-text blink behavior | Native opacity calculation | Do not replace the target-detection logic. |
| Keep a frame attached to changing scan text | A small native wrapper immediately before menu rendering | Read the label; modify only the added frame and anchor. |
| Add a scrolling text column | Additional native `textmanager` widgets plus a wrapper | Keep original `RCE1` intact; respect each manager's row capacity. |
| Add more weapon/character menu previews | Native HUD preview storage and every access to it | Adding `Weapons.dat` entries alone can overflow the original table. |
| Change the tint of the rendered world | Gamma/profile selection, investigated separately | Recoloring a HUD image is not proof of a world-gamma change. |

### Current source map

- [Editable HUD overlay](../../../T3/mods/t3_enhanced_sfx/files/MenuDatas/hud.dat): layouts, widget names, colors, fonts, layers and visibility groups.
- [Search blink manifest](../../../T3/mods/t3_enhanced_sfx/patches/search_blink.json): the guarded native opacity patch.
- [scan_frame.py](../../../T3/mods/t3_enhanced_sfx/scan_frame.py): frame synchronization and the reference HUD fixture.
- [RCE2.txt](../../../T3/mods/t3_enhanced_sfx/files/MenuDatas/RCE2.txt) and [rce2.py](../../../T3/mods/t3_enhanced_sfx/rce2.py): editable text and scrolling behavior.
- [distant_audio.py](../../../T3/mods/t3_enhanced_sfx/distant_audio.py), especially `build_manifest`: composes the SFX mod's executable manifest, including the HUD features. The entry point is [runtime_patch.py](../../../T3/mods/t3_enhanced_sfx/runtime_patch.py).
- [Heavy Assault runtime generator](../../../T3/mods/t900_heavy_assault/runtime_patch.py): `build_hud_t900_family_classifier`.
- [WM27 Dual runtime generator](../../../T3/mods/wm27_dual/runtime_patch.py): `hud_preview_patches`.

The SFX folder's name is not an indication that it contains audio only. It currently also owns the editable HUD overlay and the scan/RCE extensions.

## 2. Start with the effective HUD, not an incomplete old copy

The scan-frame work began with the full official `Patch116.Cod:MenuDatas/hud.dat`. The reference fixture in `scan_frame.hud_asset` checks the exact official asset hash before inserting its two widgets. Preserving the full patched HUD mattered: an older/incomplete copy could discard official widgets such as additional minimaps.

For subsequent edits, the shipped `files/MenuDatas/hud.dat` is the source of truth. `hud_asset` is now a reference fixture for tests, **not a production generator**. Replacing the current file with that fixture would discard later edits such as RCE2 and user-adjusted positions. `distant_audio.main` explicitly excludes the HUD from generated output.

For a layout change:

1. Identify the winning `MenuDatas/hud.dat` in the enabled-mod list and build report. The top enabled provider wins the entire file.
2. Preserve a copy of that effective file before editing it.
3. Find the exact widget name and its enclosing menu/layer. Retain the existing spelling of parser keys, including `spaceing` where used.
4. Edit only the relevant `x_pos`, `y_pos`, `height`, `width`, `color`, font, layer, or texture-reference fields.
5. Keep every referenced atlas/font/shader available under its game-internal path. Do not assume a missing resource can be replaced by an arbitrary image extension.
6. Compile through ModTools, restart the game, and inspect both the intended view and unrelated HUD modes.

Do not assume all coordinates are screen pixels: the native HUD has its own projected coordinates and reference-pixel conversions. Likewise, `color` and `opacity` are distinct properties in existing widgets; copy a working local contract instead of inferring a universal alpha convention from the hexadecimal color alone.

## 3. Give the new Heavy Assault the Terminator HUD

**CONFIRMED in current generator:** `cHud::StartGame` originally recognizes particular cast names. The retained patch recognizes the `T900` prefix and routes that family to the Terminator HUD classification. This covers `T900HeavyAssault`, `T900S`, and `T900Heavy`, while other names continue through the original classifier.

Implementation sequence:

1. Diagnose the wrong reticle as a cast-classification problem, rather than globally recoloring the human reticle.
2. Replace only the bounded classifier block using its original byte pattern.
3. Preserve its non-T900 fallthrough and Terminator continuation; pad to the original block length.
4. Keep this independent from native soldier-type classification. Assigning the custom character an appropriate movement type solved a different problem and is not a HUD color setting.
5. Validate character selection, spawn, Q vision, death, respawn and a second map load.

The generator checks the classifier length and the expected prefix comparison. The full character context is in [Heavy Assault implementation](T900_HEAVY_ASSAULT_IMPLEMENTATION.md).

### Retired color experiments must not be copied back

The [Heavy Assault changelog](../../../T3/mods/t900_heavy_assault/README.md) records yellow overlay, Q routing, noise suppression and finalizer experiments in versions 0.11.4–0.11.6. Version 0.11.7 removed that experimental set to restore the stable death/respawn flow. The current generator's obsolete-patch filter still lists those IDs.

**Historical observation:** changing persistent HUD/faction/timer state caused effects to survive death, inherit colors, or fail during re-entry. **Current implementation:** the Terminator classifier remains; those yellow/noise/Q patches are not an enabled feature to restore from an old paragraph.

## 4. Make the searching message blink without changing detection

The search change is deliberately narrow: keep the native sine/timer phase, but produce opacity **0 or 255** instead of its original gradual fade. The patch changes only the searching branch; the target-found branch and the detection system remain native.

The manifest uses a unique `.text` byte anchor, original expected bytes, and a 23-byte replacement. [test_search_blink.py](../Automated%20Tests/test_search_blink.py) contains checks for that scope and executes the native opacity block in x86 emulation, including the x87 stack contract and several clock values.

To adapt this feature, change the guarded patch builder/manifest and its tests, not an arbitrary timer or target counter found near the HUD code. The historical investigation is [search blink research](../../../output/search_blink_20261029/README.md).

## 5. Add a frame that follows `txtScan`

### What was added

Two widgets, placed after the existing `txtScan` label:

- `SFX_ScanFrameAnchor`: an invisible, zero-size image used only as a position/scale anchor.
- `SFX_ScanTextFrame`: a native frame parented to that anchor.

The wrapper runs after the HUD has updated the label and immediately before final menu rendering. It finds the label, frame and anchor by name, copies effective visibility and opacity, positions the anchor, and adjusts the frame to the current caption width. Missing widgets safely skip synchronization and continue rendering.

### Why an extra invisible anchor was necessary

**Historical observation plus current test contract:** parenting the frame directly to `txtScan` collapsed its edges because the label's `GetScale` was zero. The label's own drawing uses a different scale path. Giving the new anchor unit scale fixed the frame without changing the original label.

Current geometry in [scan_frame.py](../../../T3/mods/t3_enhanced_sfx/scan_frame.py):

- Frame height is authored as `20` in the current HUD.
- Width follows native caption width converted to reference pixels, plus `12` pixels of padding.
- Vertical synchronization uses `VERTICAL_OFFSET = 10.0`, accounting for the visible glyph area of the actual font atlas.
- Edge scales compensate for aspect conversion and half-line joins so the four outer corners meet.

Earlier research prose mentions a six-pixel offset; that is historical, not the current `VERTICAL_OFFSET`. Follow current code and geometry tests when changing the font or centering.

The wrapper preserves registers, flags, x87 state and the original render arguments. It does not write captions, scan timers, detection counters or the original label. [test_scan_frame.py](../Automated%20Tests/test_scan_frame.py) checks allowed writes, short/long caption widths, hidden/disabled states, alpha propagation, missing widgets and native edge geometry.

### Editable values versus runtime-controlled values

- Change the frame's authored `height` and color in `hud.dat`.
- Runtime synchronization overwrites frame width, visibility and opacity from the live label; editing their startup values alone will not change the running behavior.
- The anchor position is also synchronized. A persistent offset change belongs in the wrapper and its tests.
- `HEIGHT` in the Python reference-fixture builder does not rewrite the shipped HUD.

## 6. Add ordered scrolling text without replacing native RCE1

Native `RCE1` is a separate running-code effect. Its original selection behavior was not suitable for an ordered, complete text cycle, so we added `RCE2` and `RCE2Continuation` as ordinary native text managers and supplied a bounded wrapper.

Current sources at this snapshot:

| Setting | Where to edit | Current value/contract |
| --- | --- | --- |
| Text and blank lines | `files/MenuDatas/RCE2.txt` | All lines retain their order; rebuild to embed new text. |
| Column position | RCE2 in `hud.dat` | `x_pos -14.0`, `y_pos 3.584950`; continuation children follow the main manager. |
| Visible row count | Both textmanager blocks | 20 + 17 = 37 rows; each native manager must stay within 1–20. |
| Row spacing | Main RCE2 layout | `rowsyoffset 0.4`; both authored blocks currently match. |
| Line speed | `rce2.LINE_TIME_MS` | `100` ms per line, or 10 lines/second. |
| Empty interval | `rce2.PAUSE_MS` | `2000` ms after the text has scrolled out. |

The [research note](../../../T3/mods/t3_enhanced_sfx/research/rce2.md) records an earlier 125 ms / 8 lines-per-second setting. The current Python constant is 100 ms; this guide deliberately follows the code rather than repeating that older value.

Implementation details worth preserving:

1. `read_lines` accepts UTF-8 with optional BOM, or a CP1252 fallback, then encodes the native text as CP1252. Characters must be representable there. Lines are limited to 254 bytes; null bytes, the native color marker and leading native control markers are rejected.
2. Use two native managers to obtain 37 rows. Do not increase one manager beyond its original 20-child allocation.
3. The continuation joins the main manager's children into one column with a shared clock and spacing, but each native manager retains ownership of its original allocations.
4. Preserve the native RCE1 object. The wrapper only reads its visibility for gating and does not replace its effect.
5. Hide both new managers for native `HudScreen == 3` (FK). Other modes follow valid native RCE1 visibility. `HudScreen == 5` is Scout, **not FK**; the research records and corrects that earlier identification mistake.
6. Reset the scrolling cycle when hidden, handle clock rollback/wrap, and safely fall back if the continuation is absent or invalid.

[test_rce2.py](../Automated%20Tests/test_rce2.py) covers sequence, interpolation, pause, row limits, continuation, visibility, clock handling and the FK regression. The research records prior emulation results and distinguishes them from visual checks still pending. No new in-game verification is asserted here.

## 7. Compose HUD wrappers instead of competing for one call site

The current `distant_audio.build_manifest` composes this chain:

```text
Final native HUD menu-render call
  -> scan-frame synchronization
  -> RCE2 scrolling/visibility
  -> optional Skynet outline bootstrap
  -> original menu rendering
```

The scan wrapper owns the original call-site substitution. The other stages receive an explicit next-stage target and tail-call it after restoring calling state. This avoids several independent patches fighting for the same five bytes. The search-opacity patch is separate from this chain.

Current outline support is an adjacent feature, not a `hud.dat` texture recolor. [skynet_outline.py](../../../T3/mods/t3_enhanced_sfx/skynet_outline.py) loads the bounded native runtime in [native_outline](../../../T3/mods/t3_enhanced_sfx/native_outline). Its current settings are `ENABLED = True`, `PULSE_MS = 180`, `WIDTH_PX = 2.0`. The DLL tracks native name-visibility transitions for a Skynet player and draws a short actor silhouette pulse; it does not rewrite scan detection.

The bootstrap validates native source/DLL hashes against `build_manifest.json`. Changing native C++ requires its dedicated build step before a normal mod build; changing Python settings requires rebuilding mods and restarting. [Name/actor research](../../../output/skynet_name_outline_20261103/name_target.md) and [render research](../../../output/skynet_name_outline_20261103/render_research.md) explain identity, rendering scope, state restoration and existing offline tests. They do not establish final live alignment for every animated model. Do not describe this as a fully verified visual result merely because its smoke tests passed.

The current bootstrap embeds the resolved absolute path to `native_outline/t3_skynet_outline.dll` and loads it directly with `LoadLibraryA`, not through `Mods.Cod`. Keep that DLL on disk at the embedded location. Moving or distributing the project requires retaining the native runtime and rebuilding the bootstrap/executable for the destination path; copying only `Mods.Cod` and the generated executable is insufficient for this optional feature.

## 8. Expand menu previews when new content exceeds native capacity

This is HUD storage work, separate from reticle styling. During WM27 Dual integration, adding the combined weapon/cast previews exposed a native 40-entry table overflow. The regression reproduced a crash at the original code location, with the next preview name corrupting the count.

The retained solution in `wm27_dual.hud_preview_patches` relocates/expands the table to **64 entries**, updates the allocation size, initialization, append paths, lookups and cleanup, and preserves neighboring fields. Raising a count alone would not fix the memory layout.

[test_hud_preview.py](../../../T3/mods/wm27_dual/test_hud_preview.py) covers the original crash, a complete fixture menu, lookups, cleanup, allocation size and all 64 slots with guard checks. Its 41-entry fixture is not a universal current-menu count. Before adding another weapon or cast, count the effective combined preview entries and validate them against the allocated capacity.

See [WM27 Dual implementation](WM27_DUAL_IMPLEMENTATION.md) for the owning generator and [WM32 Dual implementation](WM32_DUAL_IMPLEMENTATION.md) for its dependency on that work.

## 9. Keep the old blue-HUD experiment in its historical scope

The [August HUD transcript](T3_Modding_hud_and_changing_of_the_tool_name_for_T3-ModTools.md) and [archived package](../../../info%20y%20documentacoin%20previa/T900Heavy_Blue_HUD.zip) describe a different experiment for vanilla `T900Heavy`, not the later custom `T900HeavyAssault`.

The transcript reports an alternate `MenuDatas/hud_t900heavy.dat` selected for the Heavy, rather than replacing everyone's HUD. It also explicitly leaves world tint/gamma as a separate issue requiring visual confirmation. Earlier discussion of swapping `SkyNet_Gamma` channels was an investigation/proposal, not proof that the complete per-class blue world tint shipped.

Treat the archive as historical material to inspect, not a current dependency. Do not add its patch alongside current HUD extensions without revalidating targets, ownership and lifecycle behavior.

## 10. Validation checklist for the next HUD edit

- Save the exact enabled order and effective `hud.dat`; shared overlays are whole-file conflicts.
- Check pristine executable fingerprint and unique expected-byte anchors before native changes. Addresses in source/research are specific to that build, not portable offsets.
- Preserve every wrapper's calling convention and continuation, and keep owned extension regions non-overlapping.
- Review the relevant search/frame/RCE/preview tests; static or emulated checks do not substitute for game testing.
- Confirm the generator preserves edited `hud.dat` and `RCE2.txt` instead of recreating them from a reference fixture.
- Test short and long scan messages, searching/target-found, Q on/off, hidden HUD, map modes, FK/Scout/T900/human characters and multiple resolutions.
- Test death, respawn, return to character selection and a second map load. These specifically caught earlier HUD-state mistakes.
- For added previews, test every weapon and cast, then leave/re-enter the menu to exercise cleanup.
- For outlines, test simultaneous names, disappearance/reappearance, occlusion and animated actors; retain native rendering when unsupported geometry is rejected.
- Roll back source changes and rebuild the coherent generated output set. Restoring only an executable can leave incompatible HUD assets in `Mods.Cod`.

This documentation update inspected sources and retained evidence only. It did not compile the game, modify the mods, or execute the listed runtime regressions.
