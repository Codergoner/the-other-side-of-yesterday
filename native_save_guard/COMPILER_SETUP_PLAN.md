# Windows compiler prerequisite — reviewable plan, not executed

Update from root's actual authorized setup: Community17.14.42 is installed,
complete/launchable, with no restart required. Actual cl product version is
14.44.35229.0 (family directory14.44.35207) and Windows SDK22621 includes exist.
The first isolated BuildPlugin attempt stopped at RulesError **before C++
compilation** because SwarmInterface required the missing .NET Framework SDK.
Root is adding the exact catalog component `Microsoft.Net.Component.4.8.SDK`.
No successful plugin compile or activation is claimed by this document. The
initial audit/setup plan below is retained as history; the current blocker is
the verified NetFx SDK prerequisite, not an absent MSVC installation.

Audit date: 2026-10-26. Installed engine: `C:/Program Files/Epic Games/UE_5.8`,
version 5.8.3. No `cl.exe` or `clang-cl.exe` was discoverable on PATH, no
conventional `C:/Program Files/Microsoft Visual Studio` installation was found,
and `C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe` was
absent. `C:/Program Files (x86)/Windows Kits/10/Include` was also absent. A
custom unregistered toolchain elsewhere has not been exhaustively searched.

The prebuilt stock Windows game can cook without MSVC. Adding a new runtime
C++ plugin requires a compatible compiler, Windows SDK, actual UHT/UBT compile
and link; copying a stock receipt is not sufficient.

## Installed-engine requirements

Exact local source of truth:
`Engine/Config/Windows/Windows_SDK.json`.

* Main SDK: **10.0.22621.0**; minimum SDK **10.0.19041.0**.
* Preferred VS2022 compiler family **14.44.35207–14.44.99999**, but
  **14.44.0–14.44.35210 is banned**. Require actual MSVC **14.44.35211 or newer
  within 14.44**. Minimum IDE17.8 is not the preferred compiler recommendation.
* Alternative preferred VS2026 family14.50.35717–14.50.99999, with
  14.50.0–14.50.35722 banned: require14.50.35723+ if taking that route.
* 14.39 and14.40–14.43 are banned. Do not use the old17.12 LTSC toolset.

The root has selected **Visual Studio Community2022 Current17.14** for this
individual project, rather than the earlier Build Tools proposal. The root
staged a Microsoft-signed Community bootstrapper with file version
17.14.37806.7 and a reviewable `tools/InstallWindowsCpp.ps1`; installation is
pending the user's response. The reviewed component list in
`vs2022-saveguard.vsconfig` is edition-independent. No engine upgrade, game
editor extension, optional ATL, Android toolchain or driver change is needed.

Microsoft lists the official current17.14 Community and Build Tools bootstrappers on its
[VS2022 release history](https://learn.microsoft.com/en-us/visualstudio/releases/2022/release-history)
page. The Community bootstrapper is `https://aka.ms/vs/17/release/vs_community.exe`;
the previously verified Build Tools link is
`https://aka.ms/vs/17/release/vs_buildtools.exe`.
The page currently also offers fixed17.14.42 (2026-10-13). The current-channel
URL is servicing, not a byte-pinned binary; record final redirect, Authenticode
publisher, file version and SHA-256 before running a future download.

The exact compiler and SDK component IDs are documented in Microsoft's
[Build Tools component catalog](https://learn.microsoft.com/en-us/visualstudio/install/workload-component-id-vs-build-tools?view=vs-2022).
The requested component pins the14.44 family, not an exact patch; after setup,
verify its actual version against the engine's banned ranges.

## Future install invocation

This is a system toolchain setup, not a portable SDK: Microsoft Installer may
require administrator elevation and installs shared components/registration.
No installer was downloaded or run by this SaveGuard source task. The root's
signed Community staging is separate; obtain the user's setup authorization
before executing its concrete installer script.

Use the root's reviewed `tools/InstallWindowsCpp.ps1`, with its explicit
Community instance path, after authorization. Equivalent essential components
for a manually reviewed invocation are:

```powershell
& '<reviewed Microsoft-signed vs_community.exe>' `
  --passive --wait --norestart `
  --installPath '<reviewed Community instance path>' `
  --add Microsoft.Component.MSBuild `
  --add Microsoft.VisualStudio.Component.VC.14.44.17.14.x86.x64 `
  --add Microsoft.VisualStudio.Component.Windows11SDK.22621
```

These flags are described in Microsoft's
[command-line setup reference](https://learn.microsoft.com/en-us/visualstudio/install/use-command-line-parameters-to-install-visual-studio?view=vs-2022).
Use a hidden launcher if a background process is needed; do not suppress an
elevation/terms prompt or claim an install succeeded merely from its launch.
Accept exit0 only after installed-version verification;3010 means restart is
required, not permission to restart the machine automatically.

After setup, discover the actual instance with vswhere, check the compiler and
SDK directories, run a process-local developer environment, then perform
`RunUAT.bat BuildPlugin -Plugin=<this descriptor> -Package=<new isolated output>
-TargetPlatforms=Win64 -Rocket`. Inspect the real compile/link logs. Keep the
source outside game Plugins until the root grants activation/asset queue.
Native automation and game integration happen only after compile succeeds.
No C++/UHT validation, packaged crash test or save-integrity guarantee is
claimed by this plan.
