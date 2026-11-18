import unreal
import json
from pathlib import Path

out = {
    "engine": unreal.SystemLibrary.get_engine_version(),
    "third_person": bool(unreal.load_class(None, "/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter.BP_ThirdPersonCharacter_C")),
    "first_person": bool(unreal.load_class(None, "/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter.BP_FirstPersonCharacter_C")),
}
classes = ["EditorLevelLibrary", "EditorActorSubsystem", "LevelEditorSubsystem", "StaticMeshEditorSubsystem", "EditorAssetLibrary", "MaterialEditingLibrary", "FbxImportUI", "FbxStaticMeshImportData", "EditorLoadingAndSavingUtils", "SystemLibrary"]
for name in classes:
    typ = getattr(unreal, name, None)
    out[name] = [x for x in dir(typ) if not x.startswith("_")] if typ else None
for path in ["/Game/ThirdPerson/Blueprints/BP_ThirdPersonGameMode.BP_ThirdPersonGameMode_C", "/Game/FirstPerson/Blueprints/BP_FirstPersonGameMode.BP_FirstPersonGameMode_C"]:
    cls = unreal.load_class(None, path)
    cdo = unreal.get_default_object(cls) if cls else None
    if cdo:
        out[path] = {p:str(cdo.get_editor_property(p)) for p in ["default_pawn_class", "player_controller_class"]}
probe_fbx = Path(unreal.Paths.project_dir()).resolve().parent / "output/game/meshes/SM_AxisProbe.fbx"
if probe_fbx.exists():
    task = unreal.AssetImportTask()
    task.filename = str(probe_fbx)
    task.destination_path = "/Game/Harbor/Diagnostics"
    task.destination_name = "SM_AxisProbe"
    task.automated = True
    task.replace_existing = True
    task.save = True
    options = unreal.FbxImportUI()
    options.import_mesh = True
    options.import_materials = False
    options.import_textures = False
    options.import_as_skeletal = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    options.automated_import_should_detect_type = False
    options.static_mesh_import_data.combine_meshes = True
    options.static_mesh_import_data.transform_vertex_to_absolute = True
    options.static_mesh_import_data.convert_scene = True
    options.static_mesh_import_data.force_front_x_axis = False
    options.static_mesh_import_data.convert_scene_unit = True
    task.options = options
    task.factory = unreal.FbxFactory()
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    meshes = [unreal.load_asset(p) for p in task.imported_object_paths if isinstance(unreal.load_asset(p), unreal.StaticMesh)]
    if meshes:
        bounds = meshes[0].get_bounds()
        out["axis_probe"] = {"origin":[bounds.origin.x,bounds.origin.y,bounds.origin.z], "extent":[bounds.box_extent.x,bounds.box_extent.y,bounds.box_extent.z], "imports":list(task.imported_object_paths)}
Path(unreal.Paths.project_dir(), "unreal_probe.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
unreal.log("HARBOR_PROBE_COMPLETE " + json.dumps({k:out[k] for k in ["engine", "third_person", "first_person"]}))
