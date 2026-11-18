"""Reimport the finalized approach collision at the existing asset path."""
from pathlib import Path
import json
import runpy
import traceback
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
api = runpy.run_path(str(root / "Python/import_harbor.py"), run_name="harbor_utils")
report = api["report"]
existing = json.loads((root / "import_report.json").read_text(encoding="utf-8"))
report.update(existing)
report["meshes"] = [row for row in report["meshes"] if row["name"] != "SM_UpperRoute"]
try:
    manifest = json.loads((root.parent / "output/game/manifest.json").read_text(encoding="utf-8"))
    materials = {row["name"]:unreal.load_asset(row["path"]) for row in report["materials"]}
    entry = next(row for row in manifest["assets"] if row["name"] == "SM_UpperRoute")
    api["import_meshes"]({"assets":[entry]}, materials)
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    for map_name in ["Harbor_ThirdPerson", "Harbor_FirstPerson"]:
        level.load_level("/Game/Harbor/Maps/" + map_name)
        level.save_current_level()
    level.load_level("/Game/Harbor/Maps/Harbor_ThirdPerson")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    api["validate_route"](world, manifest)
    report["upper_route_refreshed"] = True
    api["save_report"]()
    unreal.log("HARBOR_UPPER_ROUTE_REFRESH_SUCCESS")
except Exception:
    report["refresh_error"] = traceback.format_exc()
    api["save_report"]()
    raise
