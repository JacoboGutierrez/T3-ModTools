# T900S F1 Request Ammo: restoring native AI delivery

Date: 2026-10-07

This document records the working repair for Skynet T900 Supply ammunition requests in `t3_enhanced_units`, including the required interaction with the `wm27` mod. It is intended as evidence and implementation guidance for future human and AI-assisted T3 modding.

## Verified outcome and scope

**OBSERVED — user verification:** after the final build, T900S bots approach the requesting player, switch to `T_AMMO`, and dispense **two ammunition boxes**. Human Tech-Com Supply bots also dispense two boxes. The user explicitly accepted this behavior.

The trigger is the in-game F1 voice-command menu, using its ammunition request option. It is not a chat command or a newly introduced key binding.

The repair enables the existing native delivery workflow for Skynet. It does not add a custom three-shot sequence or explicitly set the box count to two. Earlier notes, test descriptions, and patch descriptions referring to a “one-box” repair describe the initial intention; **two boxes is the final reported in-game result**. The exact cause of that count was not separately traced.

**UNKNOWN / not separately verified:** behavior after exhausting the dispenser, exact nearest-bot selection in every situation, whether the speaking bot always matches the delivering bot, and restoration of the primary weapon after delivery were not individually confirmed in the final user report. The native selection, stock checks, and weapon-restoration logic were retained.

## Source files and responsibilities

Paths below are relative to the `T3-ModdingGPT` workspace root. The `wm27_plasma` directory contains the mod whose manifest ID is `wm27`.

| File | Responsibility |
| --- | --- |
| [supply_request.py](../../../T3/mods/t3_enhanced_units/supply_request.py) | Generates the AI hooks for team eligibility, Supply recognition, and the Skynet dispenser name alias. |
| [Enhanced Units runtime_patch.py](../../../T3/mods/t3_enhanced_units/runtime_patch.py) | Validates original AI bytes and generates the declarative patches. |
| [Enhanced Units executable.json](../../../T3/mods/t3_enhanced_units/executable.json) | Generated manifest targeting `Ai.Dll`, alongside other Enhanced Units patches. |
| [WM27 runtime_patch.py](../../../T3/mods/wm27_plasma/runtime_patch.py) | `bot_loadout()` repairs the default T900S bot inventory in the executable. |
| [WM27 executable.json](../../../T3/mods/wm27_plasma/patches/executable.json) | Generated executable patches, including the bot inventory adapter. |
| [test_supply_request.py](../../../T3/mods/t3_enhanced_units/test_supply_request.py) | AI hook, relocation, native registry lookup, and patch compatibility tests. |
| [test_adapters.py](../../../T3/mods/wm27_plasma/test_adapters.py) | Executes the generated inventory adapter and native weapon lookup in Unicorn. |
| [test_wm27.py](../../../T3/mods/wm27_plasma/test_wm27.py) | Additional WM27 validation. |
| [Supply research notes](../../../T3/mods/t3_enhanced_units/research/supply_request.md) | Detailed investigation history and runtime evidence. |

Both the AI-side repair and the executable-side inventory repair were needed in this mod configuration. Copying only the AI hook does not repair a bot inventory that lacks the dispenser.

## Diagnosis: four separate conditions had to work

1. **Team eligibility:** native ammunition request branches accepted Tech-Com, but excluded Skynet.
2. **Supply identity:** native filters recognized the human cast `Supply`, but did not recognize `T900S`.
3. **Dispenser lookup:** the native job requested `AMMOPACK`; Skynet needs `T_AMMO`.
4. **Actual bot inventory:** the WM27 default-loadout adapter kept one plasma weapon and removed the second local entry. A player-controlled T900S having the dispenser did not prove that the bot had it.

These conditions explain the successive symptoms: no acknowledgement, acknowledgement followed by approach, and approach followed by a stalled or incorrect weapon selection.

**CONFIRMED:** `aiAgent::SelectWeapon` searches the agent's equipped slots for the requested gameplay weapon ID. A valid job request cannot select a dispenser that is absent from those slots.

## Critical distinction: three different weapon identifiers

Never infer the gameplay weapon ID from a menu number or an animation-table position.

| Identifier source | T_AMMO value seen during this investigation | Meaning |
| --- | --- | --- |
| `MenuDatas/Weapons.dat` | 19 | Menu metadata; not proof of the loaded gameplay ID. |
| `AnimWeapons`, executable VA `0x664018` | Index 20 | Animation-family table position; not the inventory ID. |
| Live AI gameplay registry | 9 | Registered ID in the inspected match; not a constant for future loads. |

The PDB identifies the table at `0x664018` as **`AnimWeapons`**. Its entries have stride `0x84`, with the weapon name at entry offset `+4`. Entry 19 names `TERMCANNON`; entry 20 names `T_AMMO`. Those facts describe the animation table only.

Two unsuccessful revisions hardcoded 19 and then 20. The second revision even had a test proving that animation-table entry 20 contained `T_AMMO`. That test verified the wrong assumption: it did not establish the gameplay ID. The final implementation removes both hardcoded IDs and tests the native gameplay lookup instead.

### Runtime evidence that resolved the mismatch

**OBSERVED — read-only process inspection:** the AI registry in one running match contained:

| Weapon name | Registered gameplay ID in that match |
| --- | --- |
| `T_AMMO` | 9 |
| `AMMOPACK` | 8 |
| `WM20` | 21 |
| `WM27` | 22 |
| `WM25` | 19 |

These were read from the linked list used by `aiTeam::GetWeaponID`, not inferred from visible models. This inspection used `ReadProcessMemory` only; it did not modify the running game.

For the fingerprinted AI binary:

```text
engine pointer: *(loaded_A2_base + 0x160BF0)
weapon list head: *(engine + 0xD4)

weapon descriptor:
    +0x00  registered gameplay ID
    +0x04  pointer to the weapon name
    +0x20  pointer to the next descriptor
```

The inspected DLL base was `0x08E90000`, but that address is session-specific. Always obtain the current module base and validate the binary before inspecting offsets. Traverse with bounded reads and a visited-pointer set. Do not bake observed IDs or heap pointers into a patch.

## AI-side implementation

**CONFIRMED:** team 0 is Skynet; team 1 is Tech-Com.

### Allow Skynet ammunition requests

Two native branches compare the team ID with 1 and reject it using `jne`. The patch changes that rejection to unsigned `ja`, admitting teams 0 and 1 while rejecting larger IDs.

| AI VA at preferred base `0x10000000` | Original bytes | Replacement |
| --- | --- | --- |
| `0x10029302` | `83 7E 08 01 0F 85 1C 04 00 00` | `83 7E 08 01 0F 87 1C 04 00 00` |
| `0x100294A9` | `83 7E 08 01 0F 85 75 02 00 00` | `83 7E 08 01 0F 87 75 02 00 00` |

The branch destinations and instruction lengths stay intact. See `allow_skynet_ammo_request()` for the source assertions.

### Recognize T900S throughout job selection

The helper accepts an exact `T900S` cast name in addition to an already successful native `Supply` comparison. Recognition is needed at all three stages:

| Native function | Function VA | Hook VA |
| --- | --- | --- |
| `aiTeam::FindSupply` | `0x10029F80` | `0x1002A015` |
| `aiTeamJobDropItem::CalculateCost` | `0x1001AAE0` | `0x1001AB3F` |
| `aiSquad::DropItem` | `0x100254F0` | `0x10025543` |

For these paths, `agent + 4` points to the cast descriptor, and `descriptor + 4` points to its name. The exact-name test includes the null terminator so that `T900SX` or another similarly prefixed cast is not accepted accidentally. The squad hook preserves the native list cursor and the comparison flags needed by its continuation.

### Resolve the dispenser through native GetWeaponID

`aiTeam::GetWeaponID` begins at `0x100291F0`. The hook replaces the instruction at `0x100291FD` and resumes at `0x10029203`.

At that hook, `ECX` is the team, `EBP` is the requested name, and `EAX` is the engine pointer. When the team is Skynet and the requested name is exactly `AMMOPACK`, the helper substitutes a pointer to `T_AMMO`. Other names and Tech-Com requests continue unchanged.

The original lookup then traverses the weapon registry and returns the descriptor's first DWORD. It supplies the ID actually registered in this game session.

The new string is addressed using relative `call`/`pop` plus a relative offset, so the helper works when Windows relocates `A2.Dll`. The native epilogue restores the caller's saved registers.

```text
requested_name = native_request_name
if team == Skynet and requested_name == "AMMOPACK":
    requested_name = "T_AMMO"
return native_GetWeaponID_lookup(requested_name)
```

The helper starts at preferred VA `0x101299B0`. Its generated payload is 176 bytes, ending at `0x10129A60` exclusive; the reserved validated gap ends at `0x10129A80`. These locations are specific to the supported binary and existing mod layout.

## Executable-side implementation: give the bot the actual dispenser

The repair belongs in `wm27_plasma/runtime_patch.py::bot_loadout()` because that adapter owns the affected T900S default inventory in this configuration.

The hook at `T3.exe` VA `0x467C0F` runs inside `cBase::Respawn` when no explicit loadout was supplied. It constructs a local inventory copy. It does not rewrite the shared cast descriptor or the player's explicit loadout.

The special case requires all of the following:

- Exact cast name `T900S`.
- Two source entries, in slots 0 and 1.
- Exact source weapon names `WM20` and `WM27`, respectively.

The adapter retains its existing random choice of one plasma weapon in slot 0. It then resolves the dispenser using native `cBase::SearchWeaponByName` at `0x46CBF0`.

```text
local_inventory = copy(default_cast_inventory)
if this is the supported T900S WM20/WM27 default loadout:
    local_inventory[0] = (0, chosen_plasma_registered_ID)
    local_inventory[1] = (-1, 0)
    dispenser = cBase::SearchWeaponByName("T_AMMO")
    if dispenser != NULL:
        local_inventory[1] = (1, dispenser.registered_ID)
```

Each local pair means **`(slot index, gameplay weapon ID)`**, not `(weapon ID, ammunition count)`.

`SearchWeaponByName` is a cdecl function returning the descriptor pointer. Its list is rooted at `cBase::Weapons`, VA `0xF54988`, and its descriptor stores the ID at `+0`. The helper reads that field only after a non-null result. If the dispenser is unavailable, slot 1 stays empty rather than receiving an unrelated numeric ID or the unused plasma alternative.

The argument uses the existing exact `T_AMMO` string at `0x664A6C`. Reusing the string is valid; interpreting its position in `AnimWeapons` as a gameplay ID is not.

The adapter preserves registers with `pushad`/`popad`, balances the cdecl argument, and resumes at `0x467C43`. Its reserved code block is `0x659B00..0x659BF0` (end exclusive).

This is deliberately scoped to the current WM27 default-loadout shape. A different mod that changes cast entries or constructs an explicit bot loadout needs a fresh trace of that path.

## Native behavior retained and testing limits

The existing AI jobs already provide approach, weapon selection, firing, stock-change handling, and weapon restoration. The patch connects T900S to those jobs and makes the correct dispenser available. It does not implement a new delivery animation, spawn boxes directly, or add a firing loop.

Static analysis identified a native zero-stock rejection in `FindSupply`. Its practical behavior for an exhausted T900S should still be tested separately. Likewise, the acknowledgement path can speak through a squad member; an “Affirmative” line alone does not prove that the named speaker owns the assigned delivery job.

The final user report establishes successful approach, dispenser selection, and **two-box delivery for both teams**. Do not change that accepted count merely because older source comments describe a one-box intention. A future explicit request to control the count should trace the actual firing events and stock decrements first.

## Validation and reproduction

The final code passed 13 relevant tests: five adapter tests, six Supply-request tests, and two additional WM27 tests. These are test methods; several iterate over multiple scenarios.

The meaningful checks include:

- Native AI lookup execution with synthetic registered IDs 9, 41, and 103, at three DLL bases.
- Tech-Com `AMMOPACK` behavior and unrelated weapon-name preservation.
- Team gates, exact Supply identity, register/stack preservation, and instruction continuations.
- Native executable lookup execution inside the generated bot adapter with different dispenser IDs and with the dispenser absent.
- Both plasma choices and unaffected cast/loadout cases.
- Original binary fingerprints, unique anchors, reserved code space, and overlap checks against enabled AI patches and automatic navigation patches.

Run from the workspace root with Python 3. The unqualified `python` command on the development machine pointed to Python 2.7, so the verified interpreter was selected explicitly:

```powershell
$py = 'C:/Users/Santi/AppData/Local/Programs/Python/Python310/python.exe'
& $py T3/mods/wm27_plasma/runtime_patch.py --write
& $py T3/mods/t3_enhanced_units/runtime_patch.py --write
& $py T3/mods/wm27_plasma/test_adapters.py
& $py T3/mods/wm27_plasma/test_wm27.py
& $py T3/mods/t3_enhanced_units/test_supply_request.py
```

Use the local Python 3 path on another machine. The tests require their existing repository-provided Capstone/Unicorn dependencies. `--write` intentionally synchronizes the generated manifests; omitting it runs generator validation without requesting manifest synchronization.

Close T3 before replacing its generated outputs. The build used:

```powershell
@'
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path('T3-ModTools').resolve()))
tempfile.tempdir = str(Path.cwd())
from t3_modding import ModManager
result = ModManager(Path('T3').resolve()).build_all()
print(result.package.enabled_mods, result.package.files, result.package.sha256)
'@ | & $py -
```

Build from pristine inputs through T3-ModTools. `T3_Modded.exe` uses the generated `A2.Dll`; editing or testing only the pristine `Ai.Dll` does not exercise the deployed patch. Keep the required mods enabled and check load-order winners. The final build contained 315 overlay files. The generated helper bytes were also compared directly with each built binary.

Start a new match after rebuilding so newly spawned bots receive the repaired inventory. For a controlled check, request ammunition with a live allied Supply nearby, keep it in view, and avoid another request or a death before completion. Check Skynet and Tech-Com separately. Then test depleted stock and weapon restoration if those guarantees are needed.

### Fingerprints of the verified revision

Addresses and byte patterns in this document apply to these pristine binaries. Revalidate all addresses for another game build. Generated hashes describe the full enabled mod combination and will change when unrelated enabled patches change.

| File | SHA-256 |
| --- | --- |
| Pristine `T3/T3.exe` | `52f68d5df4912aba662f0371a06ae0b1ec447ef4b7338460224b20904eb0f061` |
| Pristine `T3/Ai.Dll` | `817ba995212c4daed24c5205bfbbe575ff9f28a6ddcc4fc494141d73934d66ae` |
| Generated `T3/T3_Modded.exe` | `58e2febd3a1a384cd8bc0a3789ea9ed38dce355928248aad2f726e5e76c568dc` |
| Generated `T3/A2.Dll` | `eacae2f8ba01ed11d22745034b131faf6daf51c90b56e4906a13eebd869620cf` |
| Generated `T3/modtools_data/Mods.Cod` | `33ee607feba3841790e54b113ba263b8cc7fcaf578eab09f44d15eeeb16168b2` |

## Diagnostic guidance for future modifications

| Symptom | Next evidence to collect |
| --- | --- |
| Skynet never acknowledges | Check team gates and Supply eligibility before changing movement. |
| Acknowledges and approaches but cannot select the dispenser | Compare the job's requested registered ID with the bot's actual equipped entries. |
| Selects an unrelated weapon or appears stuck during selection | Check the identifier namespace and current gameplay registry; do not infer IDs from menus or animation families. |
| Player has the dispenser but bots do not | Trace default bot spawn and explicit player loadouts separately. |
| Tech-Com breaks after enabling Skynet | Check the team predicate around the `AMMOPACK` to `T_AMMO` substitution. |
| Unit tests pass but the game still fails | Check that tests execute the real lookup semantics, then verify loaded outputs, inventory, and runtime IDs. |
| Bot remains stuck after selecting the correct dispenser | Trace native job state, weapon readiness, stock, firing transitions, and animation completion before changing timing. |

For future AI-assisted work, use symbols and disassembly to establish structure, runtime state to verify registration assumptions, and controlled play to establish the actual outcome. Preserve the distinction between **CONFIRMED** code facts, **OBSERVED** play/runtime evidence, and **UNKNOWN** behavior. A successful emulator test of a hardcoded assumption is not a substitute for identifying the correct registry.
