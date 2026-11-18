"""Import the editable reference house and create two playable Home maps.

Existing Harbor maps are source context and are never saved by this script.
The Blender house remains local in metres and is placed as one reusable kit.
"""
from pathlib import Path
import json
import math
import sys
import time
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
SOURCE = ROOT.parent / "output" / "house"
sys.path.insert(0, str(ROOT / "Python"))
import import_harbor as harbor
import harbor_lighting

REPORT = {"success":False,"engine":unreal.SystemLibrary.get_engine_version(),
          "meshes":[],"materials":[],"maps":[],"warnings":[],
          "placement":{"blender_translation_m":[-8,-13,8.96],"blender_yaw_degrees":90,
                       "unreal_translation_cm":[-800,1300,896],"unreal_yaw_degrees":-90}}
OUT = ROOT / "house_import_report.json"
harbor.SOURCE,harbor.REPORT,harbor.report = SOURCE,OUT,REPORT
ASSETS,LEVEL,ACTORS,STATIC = harbor.ASSETS,harbor.LEVELS,harbor.ACTORS,harbor.STATIC


def write():
    OUT.write_text(json.dumps(REPORT,indent=2),encoding="utf-8")


def position(local):
    """Local Blender metres -> placed Unreal centimetres."""
    x,y,z = local
    return unreal.Vector((-8-y)*100,(13-x)*100,(8.96+z)*100)


def direction(local):
    x,y,z = local
    return unreal.Vector(-y,-x,z)


def custom_material(name, definition):
    path = "/Game/Home/Materials/"+name
    mat = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    if mat is None:
        mat = ASSETS.create_asset(name,"/Game/Home/Materials",unreal.Material,unreal.MaterialFactoryNew())
    unreal.MaterialEditingLibrary.delete_all_material_expressions(mat)
    base = definition.get("base_color",definition.get("color",[0.5,0.4,0.3,1]))
    if len(base)<4:
        base = list(base)+[1]
    expr = unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector,-350,-120)
    expr.set_editor_property("constant",unreal.LinearColor(*base))
    unreal.MaterialEditingLibrary.connect_material_property(expr,"",unreal.MaterialProperty.MP_BASE_COLOR)
    rough = unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant,-350,50)
    rough.set_editor_property("r",float(definition.get("roughness",0.75)))
    unreal.MaterialEditingLibrary.connect_material_property(rough,"",unreal.MaterialProperty.MP_ROUGHNESS)
    emission = definition.get("emission",definition.get("emission_color"))
    if emission or "glow" in name.lower():
        emission = list(emission or [1.0,0.44,0.10])
        # The harbor uses physical sun illuminance and EV11.5 exposure.
        # Convert the Blender authoring glow multiplier to visible luminance.
        strength = float(definition.get("emission_strength",3.0))*250.0
        light = unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector,-350,240)
        light.set_editor_property("constant",unreal.LinearColor(emission[0]*strength,emission[1]*strength,emission[2]*strength,1))
        unreal.MaterialEditingLibrary.connect_material_property(light,"",unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mat.set_editor_property("two_sided",any(word in name.lower() for word in ["flower","leaf","fabric","canvas"]))
    unreal.MaterialEditingLibrary.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    REPORT["materials"].append({"name":name,"path":path,"definition":definition})
    return mat


def materials(manifest):
    result = {}
    for path in unreal.EditorAssetLibrary.list_assets("/Game/Harbor/Materials",recursive=True,include_folder=False):
        material = unreal.load_asset(path)
        if isinstance(material,unreal.MaterialInterface):
            result[material.get_name()] = material
    definitions = manifest.get("material_definitions",manifest.get("materials",{}))
    if isinstance(definitions,list):
        definitions = {item["name"]:item for item in definitions if isinstance(item,dict) and "name" in item}
    defaults = {
        "M_HomeFlower":{"base_color":[0.8,0.65,0.4,1],"roughness":0.7},
        "M_HomeGlow":{"base_color":[1.0,0.5,0.13,1],"emission":[1.0,0.35,0.05],"emission_strength":4},
        "M_HomeTeal":{"base_color":[0.025,0.16,0.17,1],"roughness":0.72},
    }
    for name,definition in definitions.items():
        if isinstance(definition,dict):
            defaults[name] = definition
    slots = {name for entry in manifest.get("assets",[]) for name in entry.get("materials",[])}
    for name in slots:
        if name not in result or name in defaults:
            result[name] = custom_material(name,defaults.get(name,{"base_color":[0.5,0.4,0.3,1]}))
    return result


def point_light(name,local,intensity=150.0,radius=700.0):
    actor = ACTORS.spawn_actor_from_class(unreal.PointLight,position(local),unreal.Rotator(pitch=0,yaw=0,roll=0))
    actor.set_actor_label(name)
    actor.set_folder_path("Home/Lighting")
    light = actor.get_component_by_class(unreal.PointLightComponent)
    light.set_mobility(unreal.ComponentMobility.MOVABLE)
    light.set_editor_property("intensity_units",unreal.LightUnits.CANDELAS)
    light.set_intensity(intensity)
    light.set_light_color(unreal.LinearColor(1.0,0.78,0.54,1))
    light.set_editor_property("attenuation_radius",radius)
    light.set_editor_property("source_radius",22.0)
    return actor


def build_map(mode,meshes,manifest):
    source = "/Game/Harbor/Maps/Harbor_"+mode
    destination = "/Game/Home/Maps/House_"+mode
    if not LEVEL.load_level(source):
        raise RuntimeError("Cannot load source map "+source)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not unreal.EditorLoadingAndSavingUtils.save_map(world,destination):
        raise RuntimeError("Cannot create independent Home map "+destination)
    # Save Map writes a copy without switching the editor's active world.
    # Explicitly open that copy before changing actors or saving anything.
    if not LEVEL.load_level(destination):
        raise RuntimeError("Cannot open independent Home map "+destination)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    removed = []
    for actor in ACTORS.get_all_level_actors():
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        mesh = component.get_editor_property("static_mesh") if component else None
        if mesh and mesh.get_name() in ["SM_LeftHouse_A","SM_MarketStalls","SM_MarketProps","SM_Ivy"]:
            removed.append(mesh.get_name())
            ACTORS.destroy_actor(actor)
    harbor_lighting.configure(ACTORS.get_all_level_actors())
    for mesh,entry in meshes:
        actor = ACTORS.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(-800,1300,896),unreal.Rotator(pitch=0,yaw=-90,roll=0))
        actor.set_actor_label(mesh.get_name())
        actor.set_folder_path("Home/Reference house")
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        component.set_static_mesh(mesh)
        component.set_mobility(unreal.ComponentMobility.STATIC)
        if entry.get("collision_count",0)>0:
            component.set_collision_profile_name("BlockAll")
        else:
            component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    start_local = manifest.get("player_start",{}).get("blender_position",[0.6,-9.2,0.95])
    for actor in ACTORS.get_all_level_actors():
        if isinstance(actor,unreal.PlayerStart):
            actor.set_actor_label("Home entrance start")
            actor.set_actor_location(position(start_local),False,False)
            actor.set_actor_rotation(unreal.Rotator(pitch=0,yaw=180,roll=0),False)
            actor.set_folder_path("Home/Gameplay")
    point_light("Home ground floor warm fill",[0,-0.5,3.1],80000,800)
    point_light("Home upper room warm fill",[-1,-0.5,6.0],45000,750)
    point_light("Home stairwell warm fill",[-2.85,-0.5,5.8],20000,750)
    point_light("Home porch lantern spill",[1.7,-4.1,3.0],1800,400)
    camera_pos = position([13,-19,10])
    camera_target = position([0,-0.8,4.3])
    rotation = unreal.MathLibrary.find_look_at_rotation(camera_pos,camera_target)
    camera = ACTORS.spawn_actor_from_class(unreal.CameraActor,camera_pos,rotation)
    camera.set_actor_label("Player home reference overview")
    camera.set_folder_path("Home/Review")
    camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(51)
    LEVEL.set_level_viewport_camera_info(camera_pos,rotation,unreal.Name("None"))
    if not LEVEL.save_current_level():
        raise RuntimeError("Cannot save "+destination)
    # Validate the serialized level, not just the current in-memory actors.
    if not LEVEL.load_level(destination):
        raise RuntimeError("Cannot reload saved Home map "+destination)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    saved_starts = [actor for actor in ACTORS.get_all_level_actors() if isinstance(actor,unreal.PlayerStart)]
    if len(saved_starts)!=1:
        raise RuntimeError("Expected one saved PlayerStart, got "+str(len(saved_starts)))
    actual_start = saved_starts[0].get_actor_location()
    expected_start = position(start_local)
    if (actual_start-expected_start).length()>1:
        raise RuntimeError("Saved map has wrong spawn: "+str(actual_start))
    routes = manifest.get("route_waypoints_blender",manifest.get("route_waypoints",[]))
    placed = []
    for point in routes:
        local = point.get("position",point.get("blender_position"))
        if local:
            x,y,z = local
            placed.append({"name":point.get("name","Home route"),"position":[-8-y,-13+x,8.96+z]})
    harbor.validate_route(world,{"route_waypoints_blender":placed})
    validation = list(REPORT.get("route_validation",[]))
    record = {"path":destination,"source_map":source,"removed_context_meshes":removed,
              "player_start_cm":harbor.vector_list(position(start_local)),"player_yaw":180,
              "saved_player_start_cm":harbor.vector_list(actual_start),
              "route_validation":validation,
              "route_passed":bool(validation) and all(p.get("supported") and p.get("headroom_clear") for p in validation)}
    REPORT["maps"].append(record)
    write()
    return record


def main():
    try:
        manifest_path = SOURCE/"manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(str(manifest_path))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        mats = materials(manifest)
        fresh = "/Game/Home/Meshes/Build_"+str(int(time.time()))
        for entry in manifest.get("assets",[]):
            entry["destination_path"] = fresh
        meshes = harbor.import_meshes(manifest,mats)
        build_map("ThirdPerson",meshes,manifest)
        build_map("FirstPerson",meshes,manifest)
        LEVEL.load_level("/Game/Home/Maps/House_ThirdPerson")
        unreal.EditorAssetLibrary.save_directory("/Game/Home",only_if_is_dirty=False,recursive=True)
        REPORT["success"] = all(row["route_passed"] for row in REPORT["maps"])
        write()
        unreal.log("HOUSE_IMPORT_DONE "+json.dumps({"success":REPORT["success"],"meshes":len(meshes),"maps":len(REPORT["maps"])}))
        if not REPORT["success"]:
            raise RuntimeError("Home imported, but route validation needs repair")
    except Exception:
        REPORT["error"] = traceback.format_exc()
        write()
        unreal.log_error(REPORT["error"])
        raise


if __name__ == "__main__":
    main()
