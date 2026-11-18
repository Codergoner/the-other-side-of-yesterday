# SaveGuard — native editor verification and guarded menu integration

Latest actual status: CNG version2 (`0.1.1-cng-review`) compiled for the Editor
and linked its real DLL; Game Development/Shipping produced real object sets
and precompiled manifests, not a whole-game executable. The exact verified
package was staged and enabled in the release copy, with version1 preserved
under `output/save_guard_activation/20261025T184347_5241815/plugin_before`.
Native BoundedDecoder automation passed including SHA-256's `abc` known vector,
and44 native file-fault checks passed (`20261025T184443_839910`). Existing assets,
config/maps and preexisting saves stayed byte-identical. Native owner wiring
then replaced13 existing manager save calls, preserving their actual serialized
GUIDs/pins/defaults/links and all original node objects. The manager compiled
without warnings/errors; the native owner audit found no generic save calls.
Actual menu recovery passed35 checks (`20261025T190149_511146`), including a
blocked damaged-campaign Continue and a read-only recovered profile. Protected
assets and existing saves stayed unchanged. All four actual-menu guarded story
routes, exact pinned migration and ending/journal checks passed470 assertions
(`20261025T190310_737448`,24screenshots). A packaged test and whole-game native
link remain separate gates.

The first package's39 positive faults ended in a real assertion because the
generic platform SHA-256 function is an unimplemented Windows stub. It never
reached raw legacy deserialization. Version2 uses Windows CNG via verified
SDK `bcrypt.h`/`bcrypt.lib`; every return status and handle cleanup is checked.
See Microsoft's [BCryptCreateHash](https://learn.microsoft.com/en-us/windows/win32/api/bcrypt/nf-bcrypt-bcryptcreatehash)
and [BCryptFinishHash](https://learn.microsoft.com/en-us/windows/win32/api/bcrypt/nf-bcrypt-bcryptfinishhash)
documentation. Earlier failed reports are retained as failures.

The original source-only design and test plan below is retained as history;
its uncompiled/not-activated wording describes that earlier stage, not the
verified version2 editor module above.

This directory is deliberately outside `game_unreal/Plugins`. No project,
engine, registry, save file or Blueprint was changed to enable it. A successful
stock-engine Windows cook does not prove this new C++ module builds.

## Failure being addressed

The isolated development frontend test reached 23 positive checks, then
arbitrary-byte input caused an Unreal native assertion in the generic
`UGameplayStatics::LoadGameFromSlot` path, before Blueprint validation returned.
The recorded invalid FName length was 1,635,151,432, beyond the engine limit.
Existing saves and protected inputs remained byte-identical after that process
exited. `checkf` behavior differs by build configuration; this test proves the
Development/Editor failure, not a Shipping crash or Shipping safety.

The release frontend now uses the bounded native guard. The earlier generic
loader failure remains historical evidence; it is not an assertion that the
new guard passed packaged Development/Shipping recovery testing.

## Design and limits

The three main Blueprint functions have the same arguments and return types as
the corresponding GameplayStatics functions. The file remains a local `.sav`,
but its payload is a closed primitive snapshot of the existing authoritative
`BP_OpeningSave` or `BP_ReleaseProfile`, not an Unreal property archive. Game
state, supported schema versions and story invariants remain manager concerns.

| Offset | Bytes | Meaning |
|---|---:|---|
| 0 | 8 | ASCII `YDAYSG01` |
| 8 | 4 | little endian envelope version, exactly 1 |
| 12 | 4 | little endian payload length, 1–262144 |
| 16 | 32 | BLAKE3 of bytes 0–15 followed by the payload |
| 48 | length | UTF-8 JSON `{kind,fields}` |

The total file must be exactly header plus declared payload. JSON depth is
bounded before parsing; strings, arrays, property count and numeric values are
bounded. Only two compiled-in class paths can load. Input keys are compared as
strings against known property names; they never create FNames. Only native
bool/int32/float/double/FString/string-array properties in the reviewed schema
are supported. Schema drift rejects safely rather than losing fields silently.

BLAKE3 detects accidental damage. It is **not authentication, encryption or
anti-cheat**. A player can construct a new consistent hash. The closed bounded
decoder must remain safe even in that case; manager validation must still reject
unsupported future story schemas and inconsistent game state.

Only local Windows user index 0 is supported. Slot names are ASCII letters,
digits, `_` and `-`, 1–128 characters. Files live under the actual
`FPaths::ProjectSavedDir()/SaveGames`, respecting a dedicated `-UserDir`.
No arbitrary path, cloud save or Quest compatibility is claimed.

## Preservation and recovery

* `SafeDoesSaveGameExist` reports physical primary **or backup** occupancy,
  including damaged files. An invalid occupancy query returns occupied. New
  Game therefore cannot treat decode failure as permission to overwrite.
* Load validates primary, then `.sav.bak`. Backup success returns the actual
  SaveGame object plus `RecoveredBackup`; loading never repairs or overwrites.
* A corrupted/unknown existing primary refuses Save. The menu must allocate a
  separate recovery campaign/profile slot and commit its pointer only after
  the recovery checkpoint succeeds. It must show the recovery status.
* A write stages a same-directory GUID temp, flushes and verifies its bytes and
  schema, stages/verifies the previous valid primary as the backup, then uses
  Windows same-volume replacement with write-through. Existing invalid backup
  evidence is renamed to a unique `.rejected_<guid>` path before replacement.
* A directory-exclusive Windows file handle serializes cooperating guard
  processes. Generic GameplayStatics/external programs bypass this lock;
  integration must replace **all** runtime save/load calls for these classes.
* Error temps are deliberately preserved. There is no automatic cleanup or
  deletion. Disk-full/permission-loss and interrupted-write behavior need fault
  injection; no power-loss guarantee has been demonstrated.

`ImportPinnedLegacyFixture` is separate and explicit. It accepts only SHA-256
`0f698bb9c4a003a7aa2883af39317161a1e38290ca388626231bce5f1caf94e8`, the
protected Brief opening-v1 fixture. Only those exact trusted bytes may enter
`LoadGameFromMemory`; output is re-encoded into an unoccupied new envelope slot.
Source bytes are never replaced. Arbitrary existing raw GVAS saves remain
unsupported and preserved. Do not imply general legacy compatibility.

## Integration plan retained for review

1. Copy the reviewed plugin into the **release copy only**, explicitly enable
   it, compile for Editor and Win64 Game, and inspect UHT/link diagnostics.
2. Replace only LoadGameFromSlot/SaveGameToSlot/DoesSaveGameExist call nodes in
   the existing manager/frontend graphs. Preserve functions, variables, GUIDs,
   story IDs, save profile isolation and protected project copies. Do not
   rebuild all story graphs.
3. Propagate `RecoveredBackup` and protected write failures. A valid recovered
   object does not authorize overwriting the corrupt selected slot. If both
   profile indexes are unusable, either allocate a fresh discoverable recovery
   index or keep the existing helpful New Game block.
4. Update frontend raw-corrupt fixtures to verify null/recovery outcomes without
   ever calling the unsafe original loader. Exercise exact pinned migration
   explicitly; use guarded saves for future-version fixtures.
5. Run the matrix below and the four real story routes with actual New Game and
   Continue. Package separately and repeat a fresh-user-directory standalone
   playthrough. Only then update release acceptance evidence.

## Test matrix and remaining scope

The source includes `Yesterday.SaveGuard.BoundedDecoder` native automation.
It passed in the actual Editor module. It checks current profile roundtrip, truncation, integrity,
payload bounds, future envelope, raw GVAS rejection, depth and slot validation.
Further required integration/fault tests:

| Case | Required result |
|---|---|
| Normal profile/campaign roundtrip and both story eras | actual fields identical |
| 0-byte/random/truncated/header-only input | recoverable rejection, no native crash |
| Forged consistent hash + huge/deep/wrong-type/unknown-class JSON | bounded rejection |
| Supported envelope but future story ProfileVersion/SchemaVersion | manager recovery, writes blocked |
| Bad primary + good backup | backup state loads, primary hash unchanged |
| Bad primary + bad/missing backup | null/recovery menu, both hashes unchanged |
| Both frontend index slots damaged | clear block or discoverable separate recovery; no unreachable new campaign |
| Raw legacy fixture hash mismatch | no native archive call, source unchanged |
| Exact pinned v1 fixture | explicit separate-slot import, manager's real v1 migration |
| Second save, failed backup stage, failed replacement, disk full, lock contention | previous valid bytes/recovery retained |
| Interrupted write at each transaction boundary | valid old or new state recoverable |
| Settings, actual New Game/Continue, four story routes and ending | correct authoritative native manager behavior |
| Editor vs packaged Development and Shipping | separate crash/recovery evidence |

`source_audit.py` checks only source/schema/descriptor facts; it is not a C++
compiler, native test, save roundtrip or corruption-safety certification.
