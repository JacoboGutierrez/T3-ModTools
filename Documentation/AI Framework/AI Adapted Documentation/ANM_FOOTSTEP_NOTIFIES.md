# ANM footstep notifications

The Blender ANM exporter 0.7.0 stores `Footstep_Left` / `Footstep_Right` as
Action pose markers and a per-Action `t3_walk_animation` checkbox. Assignment uses
the current timeline frame. Export uses the same time origin as the pose samples;
for the normal 0-based Action, marker frame and ANM frame are identical.

## Verified file format

**CONFIRMED from original assets:** `T3/Game.cod`, internal path
`CA/tps_skynet/t900_run.anm`, has 32 frames at 25 FPS and ends with two Notify
blocks: Left at 11 and Right at 27. Neither Language.cod nor Patch116.Cod replaces
this path in this workspace. The mod's replacement lacked AnimationNotify.

**CONFIRMED from the native loader:** after `Frame`, the parser consumes exactly
`FrameNum` integer tokens. Multiple frames must use `Frame 11 27`, not repeated
`Frame` keywords. Notify records have stride 0x98, with the count at +0x84 and
the frame array beginning at +0x88. This leaves four integer slots. Export rejects
more than four distinct frames per foot instead of overrunning this array.

Read-only evidence target:

- Binary: `D:/Users/Santi/Documents/Codex/T3-ModdingGPT/T3/T3.exe`, 2,703,360 bytes,
  x86, preferred image base 0x00400000.
- Binary SHA-256: `52F68D5DF4912ABA662F0371A06AE0B1EC447EF4B7338460224B20904EB0F061`.
- PDB: `D:/Users/Santi/Documents/Codex/T3-ModdingGPT/T3/T3.pdb`, 5,547,008 bytes.
- PDB SHA-256: `ADF92D82278E3222FB106782106E98BCB68321C7D7B0FFFD38E0D12D827EF5D7`.
- DbgHelp resolves `cAnimManager::LoadAnim` at 0x00522FC0, size 0xD60, in this
  image with its adjacent PDB. PDB identity was not separately decoded/validated.
- `FrameNum` string: VA 0x0066F4A4; reference at 0x00523B79.
- Relevant loader code: VA 0x00523B78 through 0x00523C7B (file offsets
  0x123B78 through 0x123C7B, executable code section).
- Frame count stored at 0x00523BCA; repeated integer reads at 0x00523C27–0x00523C55;
  next Notify advances by 0x98 at 0x00523C71.

Reproduce from the workspace with Python 3:

```powershell
python 'info y documentacoin previa/dual_gun_mod/pdb_symbols.py' T3/T3.pdb 'cAnimManager::LoadAnim'
python 'info y documentacoin previa/dual_gun_mod/disassemble_t3.py' --exe T3/T3.exe --capstone-path 'info y documentacoin previa/dual_gun_mod/python_deps' 0x123b78 --before 0 --after 0x110
```

The competing repeated-Frame interpretation is contradicted by the loader's
inner integer-reading loop. No executable or game archive was modified.

## Verification

`test_anm_footsteps.py` checks zero-based frame endpoints, original T900 event
times, duplicate removal, multi-frame token syntax, fixed-array bounds, and
out-of-range failures. Its Blender integration tests register the real add-on,
assign/remove events, verify Action isolation and .blend persistence, and compare
exports with events enabled/disabled to ensure pose output remains identical.

Run integration tests in a separate Blender process:

```powershell
blender --background --factory-startup --python-exit-code 1 --python "T3-ModTools/AI Framework/Automated Tests/test_anm_footsteps.py"
```

**OBSERVED:** all 12 tests passed on Blender 5.2.1 LTS.
The standard T3-ModTools suite also completed: 126 tests, 7 skipped, no failures
(the Blender integration cases run separately above; other skips require missing
GUI/fixture resources). The installed standalone Blender 5.2 add-on was updated
to the tested 0.7.0 source, preserving a `.pre_0_7_0.bak` beside it.
**UNKNOWN / pending:** audible playback of newly authored notifications in-game.
The ANM importer 0.6.1 now reads every AnimationNotify section, places its
named frames as Action pose markers, and shows them automatically in the Action
Editor. Imported footsteps enable Walk Animation
automatically, so they can be exported without assigning them again. Other notify
names are visible in the Action Editor, but the current exporter still writes only
Footstep_Left and Footstep_Right. Manual footstep assignment remains available.
