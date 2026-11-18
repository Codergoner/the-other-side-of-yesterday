"""Refresh finalized Blender exports without rebuilding unchanged chunks."""
from pathlib import Path
import json
import runpy
import traceback
import time
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
api = runpy.run_path(str(root / "Python/import_harbor.py"), run_name="harbor_utils")
report = api["report"]
report.update(json.loads((root / "import_report.json").read_text(encoding="utf-8")))
try:
    manifest = json.loads((root.parent / "output/game/manifest.json").read_text(encoding="utf-8"))
    changed = []
    native_paths = {row["name"]:row["path"].split(".")[0] for row in report["meshes"]}
    refresh_directory = "/Game/Harbor/Meshes/Refresh_"+str(int(time.time()))
    for entry in manifest["assets"]:
        source = root.parent / "output/game" / entry["file"]
        native_package = native_paths.get(entry["name"],"/Game/Harbor/Meshes/"+entry["name"])
        native = root/"Content"/(native_package.removeprefix("/Game/")+".uasset")
        if not native.exists() or source.stat().st_mtime > native.stat().st_mtime:
            entry["destination_path"] = refresh_directory
            changed.append(entry)
    report["materials"] = []
    materials = api["prepare_materials"]()
    changed_names = {entry["name"] for entry in changed}
    report["meshes"] = [row for row in report["meshes"] if row["name"] not in changed_names]
    new_meshes = api["import_meshes"]({"assets":changed}, materials) if changed else []
    replacement = {entry["name"]:mesh for mesh,entry in new_meshes}
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for map_name in ["Harbor_ThirdPerson", "Harbor_FirstPerson"]:
        level.load_level("/Game/Harbor/Maps/" + map_name)
        for actor in actors.get_all_level_actors():
            updated_mesh = replacement.get(actor.get_actor_label())
            if updated_mesh and isinstance(actor,unreal.StaticMeshActor):
                actor.get_component_by_class(unreal.StaticMeshComponent).set_static_mesh(updated_mesh)
        # Keep the native overview aligned with the Blender review camera.
        camera = next((actor for actor in actors.get_all_level_actors() if isinstance(actor,unreal.CameraActor)),None)
        if camera:
            position = unreal.Vector(300,3500,1700)
            rotation = unreal.MathLibrary.find_look_at_rotation(position,unreal.Vector(1400,-4500,1500))
            camera.set_actor_location(position,False,False)
            camera.set_actor_rotation(rotation,False)
            camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(65.47)
            level.set_level_viewport_camera_info(position,rotation,unreal.Name("None"))
        level.save_current_level()
    level.load_level("/Game/Harbor/Maps/Harbor_ThirdPerson")
    api["validate_route"](unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(),manifest)
    report["refreshed_assets"] = sorted(changed_names)
    report["success"] = True
    report.pop("error",None)
    api["save_report"]()
    unreal.log("HARBOR_FINAL_REFRESH_SUCCESS " + json.dumps(sorted(changed_names)))
except Exception:
    report["success"] = False
    report["refresh_error"] = traceback.format_exc()
    api["save_report"]()
    raise
