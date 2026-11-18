YOUR HARBOR HOME - UNREAL ENGINE 5.8

PlayHomeFirstPerson.bat and PlayHomeThirdPerson.bat open the new home in
first-person or third-person mode. WASD walks, the mouse looks, Space jumps.
The Home maps include the supplied Chapters 1–2 opening. Read
OPENING_CHAPTERS_1_2.txt for dialogue, watch, quest and journal controls.

The playable levels are:
  /Game/Home/Maps/House_FirstPerson
  /Game/Home/Maps/House_ThirdPerson

The home follows the supplied reference: cream plaster, teal tile roof and
awnings, wooden balcony, open ground-floor entrance, and a ruined right wing.
The house is a real 3D game mesh with separate custom collision; it does not
project the photograph. Hidden sides and the room layout were reconstructed.

The Blender source and individual FBX kit pieces are in ../output/house.
BuildHome.ps1 imports that manifest and rebuilds the Home levels using the
existing harbor as context. It leaves the original Harbor levels available.

Local house coordinates in metres are transformed into the harbor site by
Blender Z rotation +90 degrees and translation (-8,-13,8.96). Unreal placement
is (-800,1300,896) centimetres, actor yaw -90 degrees.

house_import_report.json records mesh/material/collision and route queries.
house_runtime_validation.json records real native-character PIE movement.
house_render_report.json records the native Unreal render exports.
