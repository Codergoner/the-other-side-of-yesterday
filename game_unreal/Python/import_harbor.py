"""Build the native Unreal harbor maps from the Blender game export.

Run with UnrealEditor-Cmd YesterdayHarbor.uproject -run=pythonscript
  -script="C:/.../game_unreal/Python/import_harbor.py" -unattended -nullrhi
The source meshes contain baked world coordinates in metres; FBX converts them
to Unreal centimetres. Both maps use Epic's actual animated Character template.
"""
from pathlib import Path
import json
import math
import traceback
import time
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
SOURCE = PROJECT.parent / "output" / "game"
MANIFEST = SOURCE / "manifest.json"
REPORT = PROJECT / "import_report.json"
report = {"success": False, "engine": unreal.SystemLibrary.get_engine_version(),
          "meshes": [], "materials": [], "maps": [], "warnings": []}
ASSETS = unreal.AssetToolsHelpers.get_asset_tools()
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
# StaticMeshEditor is lazy-loaded in commandlets; its stateless mesh utility
# methods can also be called on the reflected class default object.
STATIC = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem) or unreal.get_default_object(unreal.StaticMeshEditorSubsystem)


def vector_list(v):
    return [round(v.x, 5), round(v.y, 5), round(v.z, 5)]


def save_report():
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")


def optional_property(obj, name, value):
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as exc:
        report["warnings"].append("%s.%s: %s" % (obj.get_name(), name, exc))
        return False


def import_file(filename, destination, name, options=None, factory=None):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(filename))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("replace_existing_settings", True)
    task.set_editor_property("save", True)
    if options is not None:
        task.set_editor_property("options", options)
    if factory is not None:
        task.set_editor_property("factory", factory)
    ASSETS.import_asset_tasks([task])
    imported = [unreal.load_asset(p) for p in task.get_editor_property("imported_object_paths")]
    if not imported:
        existing = unreal.load_asset(destination + "/" + name)
        if existing:
            imported = [existing]
    if not imported:
        raise RuntimeError("Import produced no asset: " + str(filename))
    return imported


def make_material(name, textures, definition=None):
    definition = definition or {}
    path = "/Game/Harbor/Materials/" + name
    mat = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    if mat is None:
        mat = ASSETS.create_asset(name, "/Game/Harbor/Materials", unreal.Material, unreal.MaterialFactoryNew())
    unreal.MaterialEditingLibrary.delete_all_material_expressions(mat)
    two_sided = any(token in name.lower() for token in ["fabric", "canvas", "sail", "leaf", "foliage"])
    mat.set_editor_property("two_sided", two_sided)
    for suffix, prop, y in [("BaseColor", unreal.MaterialProperty.MP_BASE_COLOR, -220),
                            ("Roughness", unreal.MaterialProperty.MP_ROUGHNESS, 50),
                            ("Normal", unreal.MaterialProperty.MP_NORMAL, 300)]:
        texture = textures.get(suffix)
        if texture is None:
            continue
        sample = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -500, y)
        sample.set_editor_property("texture", texture)
        if suffix == "Normal":
            sample.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        elif suffix == "Roughness":
            sample.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
        unreal.MaterialEditingLibrary.connect_material_property(sample, "R" if suffix == "Roughness" else "RGB", prop)
    if "BaseColor" not in textures:
        color = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -500, -220)
        color.set_editor_property("constant", unreal.LinearColor(0.5, 0.4, 0.3, 1))
        unreal.MaterialEditingLibrary.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    if "Roughness" not in textures:
        rough = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant, -300, 50)
        rough.set_editor_property("r", 0.17 if "water" in name.lower() else 0.8)
        unreal.MaterialEditingLibrary.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    metallic = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant, -300, 450)
    metallic.set_editor_property("r", float(definition.get("metallic", 0.0)))
    unreal.MaterialEditingLibrary.connect_material_property(metallic, "", unreal.MaterialProperty.MP_METALLIC)
    unreal.MaterialEditingLibrary.layout_material_expressions(mat)
    unreal.MaterialEditingLibrary.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    report["materials"].append({"name": name, "path": path, "textures": sorted(textures), "two_sided": two_sided})
    return mat


def prepare_materials():
    groups = {}
    definitions_file = SOURCE / "textures/materials.json"
    definitions = json.loads(definitions_file.read_text(encoding="utf-8")) if definitions_file.exists() else {}
    for file in sorted((SOURCE / "textures").glob("*.png")):
        stem = file.stem
        suffix = next((x for x in ["BaseColor", "Roughness", "Normal"] if stem.endswith("_" + x)), None)
        if not suffix:
            continue
        name = stem[:-(len(suffix) + 1)]
        texture = import_file(file, "/Game/Harbor/Textures", stem)[0]
        if suffix == "Normal":
            texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            texture.set_editor_property("srgb", False)
            # Blender tangent normal textures use OpenGL +Y; Unreal expects -Y.
            texture.set_editor_property("flip_green_channel", True)
        elif suffix == "Roughness":
            texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
            texture.set_editor_property("srgb", False)
        else:
            texture.set_editor_property("srgb", True)
        unreal.EditorAssetLibrary.save_loaded_asset(texture)
        groups.setdefault(name, {})[suffix] = texture
    return {name: make_material(name, textures, definitions.get(name)) for name, textures in groups.items()}


def source_path(entry):
    value = entry.get("file", entry.get("fbx", entry.get("path")))
    file = Path(value)
    if file.is_absolute():
        return file
    for candidate in [SOURCE / file, PROJECT.parent / file, SOURCE / "meshes" / file.name]:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(value)


def import_meshes(manifest, materials):
    imported = []
    entries = manifest.get("assets", manifest.get("meshes", []))
    if isinstance(entries, dict):
        entries = [dict(value, name=name) for name, value in entries.items()]
    for entry in entries:
        name = entry["name"]
        if name == "SM_AxisProbe":
            continue
        file = source_path(entry)
        options = unreal.FbxImportUI()
        options.set_editor_property("import_mesh", True)
        options.set_editor_property("import_as_skeletal", False)
        options.set_editor_property("import_materials", False)
        options.set_editor_property("import_textures", False)
        options.set_editor_property("automated_import_should_detect_type", False)
        options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
        data = options.get_editor_property("static_mesh_import_data")
        for prop, value in [("combine_meshes", True), ("transform_vertex_to_absolute", True),
                            ("convert_scene", True), ("force_front_x_axis", False),
                            ("convert_scene_unit", True), ("auto_generate_collision", False),
                            ("one_convex_hull_per_ucx", True), ("generate_lightmap_u_vs", True),
                            ("build_nanite", False), ("remove_degenerates", True)]:
            optional_property(data, prop, value)
        data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        destination = entry.get("destination_path", "/Game/Harbor/Meshes")
        meshes = [obj for obj in import_file(file, destination, name, options, unreal.FbxFactory()) if isinstance(obj, unreal.StaticMesh)]
        if len(meshes) != 1:
            raise RuntimeError("Expected one combined mesh for %s, got %d" % (name, len(meshes)))
        mesh = meshes[0]
        slot_names = []
        for index, slot in enumerate(mesh.get_editor_property("static_materials")):
            slot_name = str(slot.get_editor_property("material_slot_name"))
            slot_names.append(slot_name)
            matched = materials.get(slot_name)
            if not matched:
                matched = next((material for key, material in materials.items() if slot_name.startswith(key)), None)
            if matched:
                mesh.set_material(index, matched)
            else:
                report["warnings"].append("Unmatched material slot: %s / %s" % (name, slot_name))
        body = mesh.get_editor_property("body_setup")
        if body:
            optional_property(body, "double_sided_geometry", True)
        if int(entry.get("triangles", 0)) > 20000 and "water" not in name.lower():
            reductions = []
            for fraction, screen in [(1.0, 1.0), (0.55, 0.35), (0.25, 0.15)]:
                reduction = unreal.StaticMeshReductionSettings()
                reduction.set_editor_property("percent_triangles", fraction)
                reduction.set_editor_property("screen_size", screen)
                reductions.append(reduction)
            reduction_options = unreal.StaticMeshReductionOptions()
            reduction_options.set_editor_property("auto_compute_lod_screen_size", False)
            reduction_options.set_editor_property("reduction_settings", reductions)
            STATIC.set_lods(mesh, reduction_options)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
        bounds = mesh.get_bounds()
        record = {"name": name, "path": mesh.get_path_name(), "bounds_origin_cm": vector_list(bounds.origin),
                  "bounds_extent_cm": vector_list(bounds.box_extent), "material_slots": slot_names,
                  "simple_collision_count": STATIC.get_simple_collision_count(mesh),
                  "convex_collision_count": STATIC.get_convex_collision_count(mesh),
                  "vertices_lod0": STATIC.get_number_verts(mesh, 0), "lod_count": STATIC.get_lod_count(mesh)}
        record["collision_count"] = record["simple_collision_count"] + record["convex_collision_count"]
        report["meshes"].append(record)
        if int(entry.get("collision_count", 0)) > 0 and record["collision_count"] == 0:
            raise RuntimeError("FBX lost custom collision for " + name)
        imported.append((mesh, entry))
        unreal.log("HARBOR_IMPORTED " + json.dumps(record))
        save_report()
    if not imported:
        raise RuntimeError("Manifest contains no game meshes")
    return imported


def spawn(cls, name, location=(0, 0, 0), rotation=(0, 0, 0)):
    actor = ACTORS.spawn_actor_from_class(cls, unreal.Vector(*location), unreal.Rotator(pitch=rotation[0],yaw=rotation[1],roll=rotation[2]))
    if actor is None:
        raise RuntimeError("Could not spawn " + name)
    actor.set_actor_label(name)
    return actor


def blender_position_to_unreal(position):
    # Measured using a known exported cube before the harbor import.
    # The Blender -Y-forward FBX default converts X -> +X and Y -> -Y.
    axis = report.get("coordinate_transform", {"x_sign": 1, "y_sign": -1})
    return (position[0] * 100 * axis["x_sign"], position[1] * 100 * axis["y_sign"], position[2] * 100)


def coordinate_transform():
    probe = PROJECT / "unreal_probe.json"
    if not probe.exists():
        raise RuntimeError("Run probe_unreal.py first to verify FBX coordinate conversion")
    data = json.loads(probe.read_text(encoding="utf-8")).get("axis_probe")
    if not data:
        raise RuntimeError("Missing axis probe import result")
    origin = data["origin"]
    if abs(abs(origin[0]) - 400) > 2 or abs(abs(origin[1]) - 1000) > 2 or abs(origin[2] - 300) > 2:
        raise RuntimeError("Unexpected FBX axis conversion: " + str(origin))
    result = {"x_sign": 1 if origin[0] > 0 else -1, "y_sign": 1 if origin[1] > 0 else -1,
              "centimetres_per_metre": 100, "probe_origin_cm": origin}
    report["coordinate_transform"] = result
    return result


def describe_hit(hit):
    if hit is None:
        return {"blocking": False}
    if hasattr(hit, "to_tuple"):
        values = hit.to_tuple()
    else:
        values = unreal.GameplayStatics.break_hit_result(hit)
    actor = values[9]
    return {"blocking": bool(values[0]), "initial_overlap": bool(values[1]),
            "point_cm": vector_list(values[5]), "normal": vector_list(values[7]),
            "actor": actor.get_actor_label() if actor else None}


def validate_route(world, manifest):
    results = []
    for waypoint in manifest.get("route_waypoints_blender", []):
        source_position = waypoint.get("position", waypoint.get("blender_position"))
        if not source_position:
            continue
        point = blender_position_to_unreal(source_position)
        hit = unreal.SystemLibrary.line_trace_single(world,
                unreal.Vector(point[0],point[1],point[2]+200), unreal.Vector(point[0],point[1],point[2]-100),
                unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
        floor = describe_hit(hit)
        row = {"name":waypoint.get("name", "Route point"), "expected_floor_cm":list(point), "floor":floor}
        if floor["blocking"]:
            diff = abs(floor["point_cm"][2]-point[2])
            row["supported"] = diff < 35
            row["floor_height_error_cm"] = round(diff,3)
            row["slope_degrees"] = round(math.degrees(math.acos(max(-1,min(1,floor["normal"][2])))),2)
            center = unreal.Vector(point[0],point[1],floor["point_cm"][2]+105)
            overhead = unreal.SystemLibrary.capsule_trace_single(world, center, center+unreal.Vector(0,0,0.1),
                    34.0, 88.0, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
            obstruction = describe_hit(overhead)
            row["headroom_clear"] = not obstruction["blocking"]
            if obstruction["blocking"]:
                row["obstruction"] = obstruction
        else:
            row["supported"] = False
            row["headroom_clear"] = False
        results.append(row)
    report["route_validation"] = results
    save_report()
    return results


def build_map(name, game_mode_path, meshes, manifest):
    map_path = "/Game/Harbor/Maps/" + name
    if unreal.EditorAssetLibrary.does_asset_exist(map_path):
        if not LEVELS.load_level(map_path):
            raise RuntimeError("Could not load " + map_path)
        for old_actor in ACTORS.get_all_level_actors():
            if not isinstance(old_actor, unreal.WorldSettings):
                ACTORS.destroy_actor(old_actor)
    elif not LEVELS.new_level(map_path):
        raise RuntimeError("Could not create " + map_path)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    game_mode = unreal.load_class(None, game_mode_path)
    if game_mode is None:
        raise RuntimeError("Missing native template game mode " + game_mode_path)
    settings = world.get_world_settings()
    settings.set_editor_property("default_game_mode", game_mode)
    settings.set_editor_property("kill_z", -3000)
    actors = []
    for mesh, entry in meshes:
        actor = spawn(unreal.StaticMeshActor, mesh.get_name())
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        component.set_static_mesh(mesh)
        component.set_mobility(unreal.ComponentMobility.STATIC)
        if "water" in mesh.get_name().lower() or entry.get("collision") is False or entry.get("collision_count") == 0:
            component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        else:
            component.set_collision_profile_name("BlockAll")
        if entry.get("hidden_in_game", False):
            actor.set_actor_hidden_in_game(True)
        actor.set_folder_path("Harbor/Environment")
        actors.append(actor)
    start_data = manifest.get("player_start", {})
    position = start_data.get("blender_position", [0, -20, 9.25])
    start = tuple(start_data.get("unreal_position_cm", blender_position_to_unreal(position)))
    source_yaw = math.radians(start_data.get("yaw_degrees", 90))
    direction = blender_position_to_unreal([math.cos(source_yaw), math.sin(source_yaw), 0])
    yaw = float(start_data.get("unreal_yaw_degrees", math.degrees(math.atan2(direction[1], direction[0]))))
    player_start = spawn(unreal.PlayerStart, "Harbor exploration start", start, (0, yaw, 0))
    player_start.set_folder_path("Harbor/Gameplay")
    sunlight = spawn(unreal.DirectionalLight, "Golden hour sun", (0, 0, 18000), (-15, 135, 0))
    light = sunlight.get_component_by_class(unreal.DirectionalLightComponent)
    light.set_mobility(unreal.ComponentMobility.MOVABLE)
    light.set_intensity(20000.0)
    light.set_light_color(unreal.LinearColor(1.0, 0.82, 0.61, 1))
    optional_property(light, "atmosphere_sun_light", True)
    optional_property(light, "light_source_angle", 1.2)
    fill = spawn(unreal.DirectionalLight,"Soft sky bounce fill",(0,0,18000),(-55,-45,0))
    fill_light = fill.get_component_by_class(unreal.DirectionalLightComponent)
    fill_light.set_mobility(unreal.ComponentMobility.MOVABLE)
    fill_light.set_intensity(2000.0)
    fill_light.set_light_color(unreal.LinearColor(0.60,0.75,1.0,1))
    fill_light.set_editor_property("cast_shadows",False)
    fill_light.set_editor_property("atmosphere_sun_light",False)
    skylight = spawn(unreal.SkyLight, "Mediterranean sky fill", (0, 0, 10000))
    sky_comp = skylight.get_component_by_class(unreal.SkyLightComponent)
    sky_comp.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky_comp.set_intensity(1.0)
    optional_property(sky_comp, "real_time_capture", False)
    optional_property(sky_comp, "lower_hemisphere_is_black", False)
    spawn(unreal.SkyAtmosphere, "Golden hour atmosphere")
    fog = spawn(unreal.ExponentialHeightFog, "Distant sea haze")
    fog_comp = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    optional_property(fog_comp, "fog_density", 0.003)
    optional_property(fog_comp, "fog_height_falloff", 0.25)
    optional_property(fog_comp, "fog_inscattering_luminance", unreal.LinearColor(0.49, 0.58, 0.68, 1))
    post = spawn(unreal.PostProcessVolume, "Harbor exposure")
    post.set_editor_property("unbound", True)
    post_settings = post.get_editor_property("settings")
    post_settings.set_editor_property("override_auto_exposure_method", True)
    post_settings.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    post_settings.set_editor_property("override_auto_exposure_bias", True)
    post_settings.set_editor_property("auto_exposure_bias", -11.5)
    for key,value in [("auto_exposure_min_brightness",7.0),("auto_exposure_max_brightness",13.0),("auto_exposure_speed_up",3.0),("auto_exposure_speed_down",3.0)]:
        post_settings.set_editor_property("override_"+key,True)
        post_settings.set_editor_property(key,value)
    post_settings.set_editor_property("override_auto_exposure_apply_physical_camera_exposure", True)
    post_settings.set_editor_property("auto_exposure_apply_physical_camera_exposure", False)
    post.set_editor_property("settings", post_settings)
    # This fixed actor provides a convenient composition review in the editor.
    overview = manifest.get("overview_camera", {})
    camera_position = overview.get("blender_position", [12, -43, 22])
    target = overview.get("blender_target", [14, 35, 16])
    camera_loc = unreal.Vector(*blender_position_to_unreal(camera_position))
    target_loc = unreal.Vector(*blender_position_to_unreal(target))
    rotation = unreal.MathLibrary.find_look_at_rotation(camera_loc, target_loc)
    camera = ACTORS.spawn_actor_from_class(unreal.CameraActor, camera_loc, rotation)
    camera.set_actor_label("Reference composition overview")
    camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(64)
    camera.set_folder_path("Harbor/Review")
    LEVELS.set_level_viewport_camera_info(camera_loc, rotation, unreal.Name("None"))
    if not LEVELS.save_current_level():
        raise RuntimeError("Could not save " + map_path)
    record = {"path": map_path, "game_mode": game_mode_path, "static_mesh_actors": len(actors),
              "player_start_cm": list(start), "player_yaw": yaw,
              "default_pawn": str(unreal.get_default_object(game_mode).get_editor_property("default_pawn_class"))}
    # A vertical collision query verifies that the spawn sits over a real floor.
    try:
        trace = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(start[0], start[1], start[2] + 100),
                unreal.Vector(start[0], start[1], start[2] - 400), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                False, [], unreal.DrawDebugTrace.NONE, True)
        record["spawn_floor_trace"] = describe_hit(trace)
        record["spawn_floor_trace_hit"] = record["spawn_floor_trace"]["blocking"]
    except Exception as exc:
        report["warnings"].append("Spawn floor query: " + str(exc))
    report["maps"].append(record)
    save_report()


def main():
    try:
        if not MANIFEST.exists():
            raise FileNotFoundError("Blender game export not ready: " + str(MANIFEST))
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        coordinate_transform()
        materials = prepare_materials()
        # A fresh package avoids the engine reimport path restoring stale
        # UCX collision or applying conversion to already converted data.
        build_directory = "/Game/Harbor/Meshes/Build_" + str(int(time.time()))
        for entry in manifest.get("assets", []):
            entry["destination_path"] = build_directory
        meshes = import_meshes(manifest, materials)
        build_map("Harbor_ThirdPerson", "/Game/ThirdPerson/Blueprints/BP_ThirdPersonGameMode.BP_ThirdPersonGameMode_C", meshes, manifest)
        validate_route(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(), manifest)
        build_map("Harbor_FirstPerson", "/Game/FirstPerson/Blueprints/BP_FirstPersonGameMode.BP_FirstPersonGameMode_C", meshes, manifest)
        LEVELS.load_level("/Game/Harbor/Maps/Harbor_ThirdPerson")
        unreal.EditorAssetLibrary.save_directory("/Game/Harbor", only_if_is_dirty=False, recursive=True)
        report["success"] = True
        save_report()
        unreal.log("HARBOR_BUILD_SUCCESS " + json.dumps({"meshes":len(meshes), "materials":len(materials), "maps":len(report["maps"])}))
    except Exception:
        report["error"] = traceback.format_exc()
        save_report()
        unreal.log_error(report["error"])
        raise


if __name__ == "__main__":
    main()
