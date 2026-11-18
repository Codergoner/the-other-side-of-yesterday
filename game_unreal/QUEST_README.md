This is the isolated Meta Quest 3 / 3S standalone development copy. The desktop
project in `development/Brief_20261025` keeps its own renderer and player classes.

The Quest profile uses the installed Epic OpenXR plugin, ARM64 Vulkan, mobile
forward rendering, four-sample MSAA, Mobile Multi-View, static lighting support,
and no Lumen, virtual shadow maps, motion blur or depth of field. These settings
are a starting profile, not a measured performance result. The project uses
bundled generic OpenXR; no external Meta XR plugin was downloaded. The portable
Android dependencies described below were installed with user authorization.

`Python/build_quest_xr.py` authors native Blueprint assets in `/Game/Quest/XR`
and adds tag-gated adapters to the copied Opening manager and HUD. Its runtime
has no Python dependency. `BP_QuestCharacter` derives from Character so the
existing story manager, CharacterMovement references and save class remain
compatible. Only this character suppresses the normal Canvas HUD. Dialogues
and menus use a panel placed in the world when the mode opens; turning the head
does not drag the panel along. The HMD remains locked to its physical tracking
pose. The floor-relative origin uses UE 5.8's `LocalFloor` tracking origin.
Title, body, response rows and wrist status cache their strings independently.
The font material preserves Epic's glyph mask and emits its text color directly,
so the UI remains readable in unbaked rooms. Paragraph blank lines collapse only
in rendered text to avoid TextRender's unscaled empty-line spacing; the story
manager's source strings remain intact. Pause and dialogue share actual ray-hit
response rows, with `>` marking the selected option.

Controls currently authored:

- Right controller ray + trigger: interact, advance dialogue, select a spatial
  response row, confirm the watch, or close a document.
- A: cycle dialogue response or pause option; in watch mode cycle the island;
  while inspecting the photo turn it over. Trigger confirms the selected row.
- B: close a modal; during exploration open the pause panel.
- X: open watch during exploration. Y: open journal during exploration.
- Right stick: 30-degree snap turn during exploration; select era in the watch;
  turn journal pages. Return the stick to center before another step.
- Left stick click: point at an authored `Quest.Teleport` landing medallion
  within 6.5 m and request a collision-checked teleport. No joystick translation,
  jog, head bob, automatic camera framing or forced head rotation is authored.
- Left trigger: turn held photo; during intro dialogue skip recollections.
- Keyboard fallback: E primary, 1/2/3 choices, Q watch, Tab journal, Esc close,
  R photo, T teleport, PageUp/PageDown snap turn. This uses a 160 cm preview
  camera when no HMD is enabled; it is not headset validation. Use Verdant_Desktop
  for conventional first-person traversal and city inspection.

There are 15 authored landing medallions. The interior home/workshop landings
are Present-only; the porch remains available in both eras. The workshop and
adjusted clinic approach cover all 21 mandatory/static and authored dynamic
interaction cases at seated hand80/head110 and standing hand110/head160 origins,
using the unchanged 260cm interaction ray. These are controlled spatial checks,
not measurements of physical reach or a complete headset navigation journey.

The copied manager still owns dialogue choices, state commits, watch actions,
timeline travel and saves. Existing actor references are preserved. Desktop
players use their original function bodies. The bridge intentionally uses
UE 5.8 OpenXRInput's native legacy XR key actions so the established polling
manager can read controller keys. `bEnableDefaultMappingContexts=False` applies
only in this Quest copy; a future Enhanced Input migration must replace this
bridge deliberately rather than adding a competing default context.

Room-scale following sweeps the body toward physical head XY and applies the
opposite movement to the tracking rig. It preserves the physical camera pose.
If the head overlaps query-enabled geometry from built-in collision object types whose
actual Pawn response is Block, an opaque two-sided black inner sphere hides
the scene. The tracked head is never clamped. This deliberately avoids a
postprocess fade that depends on Mobile HDR. These comfort functions still need
physical headset validation. `QuestComfortSimulation` is a test-only default-off
switch for desktop pose/collision fixtures; normal fallback preview leaves it off.

Hands use the installed Epic XRMannequins SkeletalMeshComponent Blueprint and
animation rig directly under the two existing OpenXR Grip components. They add
no tracking source or child actor. Left/right Quinn meshes use the exact hand
attachment overrides natively inspected in Epic's owning BP_XRPawn, including
its side-specific rotations and small wrist offsets. The component-class CDO's
identity transform alone does not supply this calibration. A source JSON records
the values and installed Epic package SHA-256. They retain three authored LODs
(3273/1007/612 vertices, one material
slot each). A matte brown glove material explicitly supports skeletal shaders.
The final chestnut variant uses linear albedo (.152,.0928,.0512), roughness.9,
metallic0 and specular.18 with no emissive connection. Its asset metadata is
`Quest.HandMaterialVersion=Chestnut1p6_20261025`; the prior package archive and
final SHA-256 are recorded in `quest_hands_material_report.json`.
Smoothed grip and trigger axes drive the stock grasp and index poses; mirrored
left poses use the stock mirror data table. Untracked hands are hidden and do
not tick unless an explicit headset-free test fixture is active.

The strict final hand/navigation report passed 84 checks, including six real
home/workshop QuestTeleport calls at simulated 110cm and 160cm eye heights,
correct era hiding/query gating and unchanged saved story fields. Its lit and
shaded open/closed views show the current Chestnut material. They do not prove
physical controller alignment.

`Python/quest_xr_hands.py` requires the queued `-QuestHandsUpgrade` flag and
verifies the 53 staged Epic packages before importing their original
`/Game/XRMannequins` mount. Core XR regeneration retains this upgrade once its
ownership metadata exists. Staging provenance and SHA-256 values live in
`../output/staging/xr_hands/manifest.json`. This is bundled template art, not a
new human hand sculpt; physical controller alignment is still untested.

Current limits: no general physics grip pickup; no hand tracking, eye tracking,
vendor foveation or refresh-rate certification.
Physical boundary safety remains the headset runtime's responsibility. The
controller-ray rows and reach, panel size, snapping and collision need actual
seated and standing Quest tests before this can be called VR playable quality.

The saved environment now includes versioned CC0 photographic sky, timber and
limewash materials plus the approved 3442-triangle opaque olive variation.
Its original pot, UVs and UCX footprint are preserved. Native Android ES3.1
editor-preview API readback and four saved-state art views are recorded in
`quest_premium_mobile_preview_report.json`; the host renderer was Windows
D3D11, and the saved sky scale is 0.10. This is separate from the bundled hand
art and does not replace the remaining NPC/prop placeholders.

Run `QuestPreflight.ps1` for a read-only local toolchain check. It writes
`quest_apk_preflight.json` and returns a nonzero status while prerequisites are
missing. `-Devices` additionally opts into an `adb devices -l` query. The default
check does not start adb. The audit checks the actual installed engine's
`Android_SDK.json`: android-36, build-tools 36.0.0, NDK 27.2.12479018 (r27c), and
CMake 3.22.1. Both Android `UnrealGame` target receipts and SDK/JDK/adb must exist
before packaging. A passing preflight would still require a genuine UBT/UAT
build. Headset input/comfort checks and on-device profiling remain separate.

The user-authorized portable Android toolchain is installed outside OneDrive at
`C:/Users/USER/TOSOYQuestToolchain`. AppData/Local was avoided because Codex's
MSIX redirection made Google's nested archive paths too long. Official Google
CLI and Eclipse Temurin archives were checksum-verified. Actual installed
versions and archive/repository checksums are recorded in
`../tools/android_toolchain_manifest.json`; SDK package licenses and installation
logs remain inside the local toolchain directory. Setup changed no global PATH,
JAVA_HOME, registry setting or Android Studio installation.

`UseQuestToolchain.ps1` applies those paths only to the current process and its
children. Both `QuestPreflight.ps1` and `BuildQuest.ps1` import it. The latter
explicitly requests an Android native build, since the stock engine target
receipt does not include this project's OpenXR plugin. A green preflight proves
dependencies are present; a genuine UBT/UAT run must establish linking and APK
success. `quest_android_build_report.json` records the successful updated
Development ARM64 Vulkan ASTC build: 0.2.0-questdev, version code 2, completed
in 2m20s. `../output/quest_android/Android_ASTC/YesterdayHarbor-arm64.apk` is the
214.59MiB single APK, including final photographic art, animated hands and
seated-navigation corrections. `../tools/verify_quest_apk.py` verified the actual
signature, package/label, SDK32/36, ARM64-only libraries, OpenXR loader and
embedded game data. Billing permission and Android File Server components are
absent. Exact bytes/SHA-256 and certificate details are recorded in
`../output/quest_android/artifact_manifest.json`. The earlier foundation archive
is preserved separately. APK Signature Scheme v2 describes signing and is
distinct from application version code 2. No headset was queried or deployed
during this updated build. The setup script itself never packages the game.

The reference images remain visual targets. Native Blueprint compilation,
desktop preview, APK packaging and Quest testing are separate evidence levels.
`Python/validate_quest_xr.py` is an asynchronous full-editor PIE harness for
possession, save isolation, panel anchoring, simulated room-scale/solid occlusion,
snap pivot, real scene picking, native dialogue adapters and real landing-node
teleport traces. It deliberately labels camera/collision fixtures as simulated
and must not run as a Python commandlet. It does not exercise a physical controller.
Its explicit hand-preview fixture also checks actual native finger-bone changes,
single Grip inheritance, untracked hiding and camera preservation, with separate
open/closed screenshots. Those fixtures do not calibrate a physical controller.
The optional `-QuestHandsContrastOnly` QA run preserves the full XR report and
records a separate `quest_hands_contrast_validation.json`: real home/workshop
landing loops at110/160cm simulated eye heights, an explicitly controlled era
visibility fixture without story-state seeding, and open/closed hand views in
existing lit/shaded areas. All segment travel in the landing loop calls the real
QuestTeleport function; the later hand-view placements are marked as fixtures.

The separate XR Character story regression passed all four routes with 462
checks, including 10 legacy-migration checks. Its simulated aim and QA setup
placements are explicitly recorded. The desktop continuous-walk test passed
26/26 route points using force=false movement input and zero route teleports.
These results do not establish physical input, device performance or headset
comfort.

See `quest_xr_build_report.json` for native authoring results; a successful source
build report never claims an APK or measured headset performance.
