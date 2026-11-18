"""Rebuild original Harbor levels from unchanged imported source meshes."""
from pathlib import Path
import json
import sys
import unreal
ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/"Python"))
import import_harbor as harbor
import harbor_lighting
original = json.loads((ROOT/"import_report.json").read_text(encoding="utf-8"))
manifest = json.loads((ROOT.parent/"output/game/manifest.json").read_text(encoding="utf-8"))
paths = {row["name"]:row["path"] for row in original["meshes"]}
meshes = [(unreal.load_asset(paths[row["name"]]),row) for row in manifest["assets"]]
if any(mesh is None for mesh,row in meshes):
    raise RuntimeError("Original harbor asset missing")
harbor.REPORT = ROOT/"harbor_restore_report.json"
harbor.report = {"success":False,"meshes":[],"materials":[],"maps":[],"warnings":[]}
for mode in ["FirstPerson","ThirdPerson"]:
    harbor.build_map("Harbor_"+mode,"/Game/"+mode+"/Blueprints/BP_"+mode+"GameMode.BP_"+mode+"GameMode_C",meshes,manifest)
    harbor_lighting.configure(harbor.ACTORS.get_all_level_actors())
    harbor.LEVELS.save_current_level()
harbor.report["success"] = True
harbor.save_report()
