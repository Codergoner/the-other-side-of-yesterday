import json
from pathlib import Path
import runpy
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
api = runpy.run_path(str(root / "Python/import_harbor.py"), run_name="harbor_utils")
api["coordinate_transform"]()
materials = api["prepare_materials"]()
mesh = unreal.load_asset("/Game/Harbor/Diagnostics/SM_AxisProbe")
api["build_map"]("Harbor_IntegrationProbe", "/Game/ThirdPerson/Blueprints/BP_ThirdPersonGameMode.BP_ThirdPersonGameMode_C", [(mesh,{})], {"player_start":{"blender_position":[4,10,5.1],"yaw_degrees":90}})
(root / "level_probe.json").write_text(json.dumps(api["report"], indent=2), encoding="utf-8")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(400,-1000,600), unreal.Vector(400,-1000,0), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
(root / "trace_probe.txt").write_text(str(type(hit))+"\n"+str(hit)+"\n"+str(dir(hit))+"\n"+str(unreal.SystemLibrary.line_trace_single.__doc__), encoding="utf-8")
unreal.log("HARBOR_LEVEL_PROBE_SUCCESS")
