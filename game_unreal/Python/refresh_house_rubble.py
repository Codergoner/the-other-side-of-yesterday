"""Refresh only noncolliding rubble after the source cleanup."""
from pathlib import Path
import json
import sys
import time
import unreal
ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/"Python"))
import import_harbor as harbor
harbor.SOURCE = ROOT.parent/"output"/"house"
harbor.REPORT = ROOT/"house_refresh_report.json"
harbor.report = {"success":False,"materials":[],"meshes":[],"warnings":[]}
manifest = json.loads((harbor.SOURCE/"manifest.json").read_text(encoding="utf-8"))
entry = next(row for row in manifest["assets"] if row["name"]=="SM_Home_Rubble")
entry["destination_path"] = "/Game/Home/Meshes/VisualFix_"+str(int(time.time()))
materials = {name:unreal.load_asset("/Game/Harbor/Materials/"+name) for name in entry["materials"]}
mesh = harbor.import_meshes({"assets":[entry]},materials)[0][0]
for mode in ["FirstPerson","ThirdPerson"]:
    harbor.LEVELS.load_level("/Game/Home/Maps/House_"+mode)
    count = 0
    for actor in harbor.ACTORS.get_all_level_actors():
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        old = component.get_editor_property("static_mesh") if component else None
        if old and old.get_name()=="SM_Home_Rubble":
            component.set_static_mesh(mesh)
            component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            count += 1
    if count!=1:
        raise RuntimeError("Expected one rubble actor, got "+str(count))
    harbor.LEVELS.save_current_level()
old_report = json.loads((ROOT/"house_import_report.json").read_text(encoding="utf-8"))
old_report["meshes"] = [row for row in old_report["meshes"] if row["name"]!="SM_Home_Rubble"]+harbor.report["meshes"]
(ROOT/"house_import_report.json").write_text(json.dumps(old_report,indent=2),encoding="utf-8")
harbor.report["success"] = True
harbor.save_report()
