YESTERDAY HARBOR - UNREAL ENGINE 5.8

Open YesterdayHarbor.uproject in Unreal Engine 5.8. The default level is
Content/Home/Maps/House_ThirdPerson. Press Play in the editor.
Use PlayHomeFirstPerson.bat or PlayHomeThirdPerson.bat to visit your home.
See HOME_README.txt for house source, rebuilding, and validation details.
The Home maps now contain the supplied Chapters 1–2 dialogue and quest slice.
See OPENING_CHAPTERS_1_2.txt for its controls, sequence and validation scope.

PlayThirdPerson.bat and PlayFirstPerson.bat launch the two exploration modes
directly through the locally installed Unreal Editor in game mode.

CONTROLS
W A S D       Walk
Mouse         Look / orbit
Space         Jump
Escape        Release / stop Play In Editor

The first and third person maps contain the same harbor geometry and use
Epic's animated Blueprint Character templates, including their Enhanced Input
actions and player controllers. No C++ compiler is required to open or play.

SOURCE AND REBUILD
The native Blender source and engine exchange assets are in ../output/game.
BuildHarbor.ps1 imports that folder's manifest.json and FBXs and rebuilds both
maps. It also recreates Unreal PBR materials from the base color, roughness,
and normal textures. OpenGL normal texture green channels are flipped during
the Unreal import. Custom UBX/UCX collision is preserved; missing collision
is not generated automatically.

Coordinates: Blender metres (X,Y,Z) -> Unreal centimetres (100X,-100Y,100Z).
This conversion was measured with a known exported calibration cube.

import_report.json records imported bounds, material slots, LODs, custom
collision counts, route floor support and capsule headroom checks.
runtime_validation.json records actual Play In Editor character checks.

This is an editable exploration prototype. The principal exterior route is
the market promenade and docks; building interiors are partial shells.


