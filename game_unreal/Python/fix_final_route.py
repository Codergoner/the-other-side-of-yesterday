"""Import finalized route into a fresh package and relink both maps."""
from pathlib import Path
import json
import runpy
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
api = runpy.run_path(str(root / "Python/import_harbor.py"), run_name="harbor_utils")
report = api["report"]
report.update(json.loads((root / "import_report.json").read_text(encoding="utf-8")))
manifest = json.loads((root.parent / "output/game/manifest.json").read_text(encoding="utf-8"))
entry = dict(next(row for row in manifest["assets"] if row["name"] == "SM_UpperRoute"))
entry["destination_path"] = "/Game/Harbor/Meshes/Final"
report["meshes"] = [row for row in report["meshes"] if row["name"] != entry["name"]]
materials = {row["name"]:unreal.load_asset(row["path"]) for row in report["materials"]}
new_mesh = api["import_meshes"]({"assets":[entry]},materials)[0][0]
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for map_name in ["Harbor_ThirdPerson", "Harbor_FirstPerson"]:
    level.load_level("/Game/Harbor/Maps/"+map_name)
    actor = next(actor for actor in actors.get_all_level_actors() if actor.get_actor_label() == entry["name"])
    actor.get_component_by_class(unreal.StaticMeshComponent).set_static_mesh(new_mesh)
    for post in actors.get_all_level_actors():
        if isinstance(post,unreal.PostProcessVolume):
            settings = post.get_editor_property("settings")
            settings.set_editor_property("override_auto_exposure_apply_physical_camera_exposure",True)
            settings.set_editor_property("auto_exposure_apply_physical_camera_exposure",False)
            post.set_editor_property("settings",settings)
    level.save_current_level()
level.load_level("/Game/Harbor/Maps/Harbor_ThirdPerson")
api["validate_route"](unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(),manifest)
report["route_validation_passed"] = all(row["supported"] and row["headroom_clear"] for row in report["route_validation"])
report["final_route_path"] = new_mesh.get_path_name()
api["save_report"]()
if not report["route_validation_passed"]:
    raise RuntimeError("Final route collision verification failed")
unreal.log("HARBOR_ALL_15_ROUTE_POINTS_PASSED")
