# ANM joints activated during a transition (2026-10-04)

## User verification update (2026-10-05)

**OBSERVED — user report in Plugin Stuff:** after the build described below,
the user confirmed that the startup backwards-turn defect was fixed. Statements
below about pending in-game verification describe the state at initial delivery.
The separate NPC aiming issue is tracked in [ERR-ANM-01.md](ERR-ANM-01.md);
its channel-priority conflict remains open.

## Diagnosis and evidence

- **OBSERVED (user):** edited `t900_run_wm20.anm` twists backwards on each
  activation; uninterrupted running loops correctly. Reordering added parents
  before children did not fix this.
- **CONFIRMED:** the deployed ANM and Mods.Cod entry were byte-identical
  (SHA-256 `46a98a49ebeba70d4592fda8a37bacf7a4415def9f84168593491c662eee7475`).
  It has 33 frames, 22 joints: vanilla's 19 plus spinebone2, spinebone3 and head.
  Joint lists, frame times, finite 4x4 matrices and braces are consistent.
- **CONFIRMED:** LoadAnim resolves names to skeleton indices at VA 0x523693–
  0x523747. Textual joint order is not the cause established by this audit.
- **CONFIRMED:** pristine T3.exe SHA-256
  `52f68d5df4912aba662f0371a06ae0b1ec447ef4b7338460224b20904eb0f061`;
  x86, image base 0x400000. Adjacent T3.pdb SHA-256
  `adf92d82278e3222fb106782106e98bcb68321c7d7b0fffd38e0d12d827ef5d7`.
  Function names below resolve with the repository's DbgHelp symbol helper.
- **CONFIRMED:** cBone::UpLoad stores SCA Matrix at bone+0x0c (VA 0x544D44).
  cBoneController::CalculateBoneMatrix computes world * inverse(parent world)
  into bone+0x98 (0x540FF6–0x54103E). Init calls it at 0x5416E5 before LoadLib.
- **CONFIRMED:** cAnimManager::LoadAnim initializes inactive records using
  bone+0x0c at 0x5232F8, converting that world matrix into the primary quaternion
  and translation. Explicit ANM matrices replace those fields at 0x5237CC–
  0x523838, but absent joints retain the world-space fallback and active=false.
- **CONFIRMED:** CrossFade snapshots every old joint record, including inactive
  records (0x543880–0x543902). CrossFadeTick copies the target record/active flag
  (0x543C24–0x543C2F), then blends its transforms with the old record without
  testing the old active flag. A newly active joint therefore mixes world and
  local transforms during the transition. At completion normal playback resumes.
- **CONFIRMED with original T900S assets:** spinebone2's fallback world rotation
  is identity but its correct local rotation is 90 degrees about X. Its world
  translation is (0, 1.230091, 0.001377); local is
  (0, 0.002692, 0.068713). Spinebone3 likewise starts over 1.2 model units away
  if its world translation is interpreted as local. The computed local matrices
  match vanilla idle and the edited run's first frame for both spine joints.
- **HYPOTHESIS with a concrete native-code mechanism:** this mixed-space fallback
  accounts for the reported startup deformation. In-game verification of the new
  patch is still required; no successful visual reproduction/fix is claimed.

## Correction

`T3/mods/t3_enhanced_t_units/runtime_patch.py` generates one in-place `.text`
patch in cAnimManager::LoadAnim. Inactive records use the already computed local
bind matrix (+0x98) instead of the world matrix (+0x0c). Explicit ANM data and
active flags are unchanged. No joints are added to any ANM automatically.

The 20-byte anchor starts at raw 0x1232EA / VA 0x5232EA. The first REP MOVSD
leaves ECX zero, allowing MOV CL,16 to replace MOV ECX,16 and provide exactly
three bytes for the larger LEA displacement. The final REP MOVSD remains at
the same address; no hooks, jumps, code caves or new memory are involved.
The generator checks full target hash, PE32/x86, .text mapping and unique bytes.
Tests decode instructions, inspect branch entries and compare real bind/ANM data.

The patch affects ANMs loaded by this native function while this mod is enabled,
including other characters; it is not limited to WM20. Full-joint clips overwrite
all primary fallback transforms with their explicit ANM data. Missing joints
remain inactive until a target animation explicitly enables them. Ai.dll is not
patched, and separate bot behavior is not asserted from player evidence.

## Runtime verification still needed

Build completed with the existing enabled load order: wm27, third_person,
t3_enhanced_sfx, t900_heavy_assault, t3_enhanced_t_units, fixed_weapons.
Generated T3_Modded.exe SHA-256:
`d93f81a546218677f82183c300a74ef31d163e666811bb54a813e3dd20bf3e59`.
The 172-test suite passed (11 Blender-dependent skips); the three new native
fallback regressions passed. Pristine T3.exe, Ai.dll, Game.cod and Patch116.Cod
hashes were unchanged. The edited run ANM is byte-identical to the pre-fix asset.

After a complete build, restart T3_Modded.exe so animations are loaded with the
new fallback. Re-exporting the ANM alone cannot apply this engine correction.
Test T900 Supply + WM20: idle -> forward run several times, continuous running,
run -> idle, walk -> run, strafe -> run, firing while moving; also check another
character and bots separately. Record the exact executable hash and observations.
To roll back only this correction, remove this mod's runtime_patch.py and
executable.json together and rebuild; the edited ANM remains intact.
