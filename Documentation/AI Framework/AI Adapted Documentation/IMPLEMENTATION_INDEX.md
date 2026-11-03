# T3 mod implementation guides

Documentation snapshot: 2026-11-03. Tool baseline: **T3-ModTools 0.6.12**, as declared by `APP_VERSION` in [t3_modtools.py](../../t3_modtools.py).

These English guides explain how the actual local projects were built, which files own each behavior, what failed during development, and how to validate future changes. They supplement the handbook and preserve the older transcripts in this directory. They do not rename or replace those historical records.

## Start here

| Subject | Guide | Current project location |
| --- | --- | --- |
| New character: T-900 Heavy Assault | [Implementation](T900_HEAVY_ASSAULT_IMPLEMENTATION.md) | `T3/mods/t900_heavy_assault` |
| Dual WM-20 | [Implementation](WM20_DUAL_IMPLEMENTATION.md) | Currently bundled inside `t900_heavy_assault`; historical prototype archived separately. |
| WM-27 | [Implementation](WM27_IMPLEMENTATION.md) | `T3/mods/wm27_plasma`; manifest ID `wm27`. |
| Dual WM-27 | [Implementation](WM27_DUAL_IMPLEMENTATION.md) | `T3/mods/wm27_dual`. |
| WM-32 | [Implementation](WM32_IMPLEMENTATION.md) | `T3/mods/wm32_plasma`. |
| Dual WM-32 | [Implementation](WM32_DUAL_IMPLEMENTATION.md) | `T3/mods/wm32_dual`. |
| HUD layout and native extensions | [Implementation](HUD_IMPLEMENTATION.md) | Mainly `t3_enhanced_sfx`, plus Heavy Assault classification and WM27 Dual preview storage. |

Recommended reading order: shared rules below, Heavy Assault, WM20 Dual, WM27, WM27 Dual, WM32, WM32 Dual, then the HUD guide. Each guide also stands alone as a source map for its project.

## Evidence and scope

- **CONFIRMED:** supported by current source, checked-in assets, deterministic assertions, or the specific retained binary/test evidence cited. Source inspection proves implementation intent and static structure, not a new successful game session.
- **OBSERVED:** a historical runtime or Blender result, with its original context. It is not automatically a guarantee for today's complete enabled-mod combination.
- **HYPOTHESIS:** a proposed explanation that still needs a discriminating test.
- **UNKNOWN / pending:** evidence or a requested visual check is missing.

When old prose disagrees with current code or editable assets, these guides call out the difference. For future changes, recheck the linked files: mod versions, weapon values, loadout choices and HUD settings can change independently of the ModTools application version.

This update performs documentation/source review only. It does not rerun generators, tests or game sessions, and does not modify mod assets or compiled game output. Validation sections describe existing coverage and the checks needed for a future implementation change.

## Shared implementation rules

### New identifiers need more than new files

A model, texture, or option override replaces an existing internal path. A new selectable weapon or character additionally needs registration, menu entries, model/animation identities, preload behavior and native paths that recognize the new identifier. AI support and player support must be checked separately.

Do not conflate folder names, `mod.json` IDs, native weapon IDs, numeric subtypes, cast names or display labels. `wm27_plasma` versus manifest ID `wm27` is an intentional example. The guides record these mappings explicitly.

### Priority and dependencies are different

[t3_modding.py](../../t3_modding.py) defines the current behavior:

- The **top enabled project** wins ordinary duplicate internal paths, compared case-insensitively. Moving a mod most recently does not confer priority by itself.
- Overlays replace whole files. Two mods supplying `MenuDatas/Weapons.dat` do not get an automatic record-by-record merge merely because they contain different weapons.
- `requires` expresses project enablement prerequisites. `runtime_cache.dependencies` declares generator inputs; a dependency resolving to an enabled generator's exact project directory also determines generator order through `_ordered_runtime_generators`. A dependency on an arbitrary file inside that directory is not itself a scheduling edge.
- Dependency-first generator execution does not change visible asset priority.
- Shared executable hooks must be composed/coordinated by their owning generators. Conflicting different-byte writes are errors, not a highest-mod-wins mechanism; identical compatible writes can coexist.

Read the current manifests and generator code before choosing an order. Do not convert a historical screenshot's load order into a universal requirement.

### Source files, generated files and packaged output

Typical project inputs are `mod.json`, editable `files/` assets, Python generators/configuration, and optional patch manifests. Some native assets and manifests are generated, while other files in the same tree are intentionally hand-editable. Ownership must be determined from the particular generator, not just the extension.

The game root currently contains:

```text
T3/
  mods/                         source projects
  modtools_data/
    load_order.json             enabled order
    .compiled/                  compilation reports/cache
    Mods.Cod                    combined asset overlay
  T3_Modded.exe                 generated player executable
  A2.dll                        generated AI library when needed
```

Treat `Mods.Cod`, `T3_Modded.exe` and the applicable AI output as a coherent build. Some features also require external runtime files: the current HUD outline loads its native DLL directly from the mod folder, as explained in the HUD guide. The three generated game outputs alone are not a complete distribution of that feature. Do not hand-edit the archive as the long-term source, patch a previously generated executable as the next baseline, or change pristine `T3.exe`/`Ai.dll` in place.

The incremental build can reuse validated results when relevant inputs are unchanged. Dependencies still matter: a changed shared generator, Blender source, texture, option, or enabled-mod combination can legitimately require dependent regeneration. A fast build is not evidence that a stale external dependency was declared correctly.

### Native patch safety

Native addresses and object layouts in these projects refer to particular supported x86 binaries. Use the owning generator's fingerprint, expected bytes, unique anchors, instruction continuations and reservation bounds. A copied virtual address is not a portable tutorial patch.

For an implementation change, validate player `T3.exe` and AI `Ai.dll` paths independently, review the resulting manifests, run the relevant deterministic tests, then test the final enabled combination in game. Test map exit/re-entry and death/respawn, not just first spawn.

### Blender sources and textures

The WM32 guides distinguish editable `.blend` sources from generated native geometry. Keep unpacked textures and linked libraries within the owning mod, or pack supported resources into the blend. This is the project's current self-contained asset policy; an absolute external texture path must not become a silent build dependency.

Preserve canonical mesh instances, bone paths, weights, locators and animation identity. A visually correct mesh in Blender alone does not prove its native controller, weapon muzzle or menu preview will work.

## Using the guides for the next mod

1. Choose the closest implementation as a reference, not as a folder to rename blindly.
2. List the identifiers and shared native systems that the new content will affect.
3. Separate authored sources from generator-owned output before editing.
4. Add deterministic checks for the invariants that made the existing implementation safe.
5. Build through ModTools and inspect both asset winners and patch ownership.
6. Record player, AI, menu, animation and lifecycle results separately; keep unverified behavior explicitly pending.
7. Update the corresponding guide when current code or configuration changes, preserving historical failures as warnings rather than active instructions.
