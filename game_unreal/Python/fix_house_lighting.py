"""Persist physically scaled interior fill in both playable Home maps."""
from pathlib import Path
import json
import unreal
ROOT = Path(unreal.Paths.project_dir()).resolve()
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
settings = {"Home ground floor warm fill":(80000,800),
            "Home upper room warm fill":(45000,750),
            "Home stairwell warm fill":(20000,750),
            "Home porch lantern spill":(1800,400)}
report = {"success":False,"maps":[]}
for mode in ["FirstPerson","ThirdPerson"]:
    path = "/Game/Home/Maps/House_"+mode
    LEVEL.load_level(path)
    if not any(actor.get_actor_label()=="Home stairwell warm fill" for actor in ACTORS.get_all_level_actors()):
        stair_light = ACTORS.spawn_actor_from_class(unreal.PointLight,unreal.Vector(-750,1585,1476),unreal.Rotator(pitch=0,yaw=0,roll=0))
        stair_light.set_actor_label("Home stairwell warm fill")
        stair_light.set_folder_path("Home/Lighting")
        stair_light.get_component_by_class(unreal.PointLightComponent).set_mobility(unreal.ComponentMobility.MOVABLE)
    records = []
    for actor in ACTORS.get_all_level_actors():
        label = actor.get_actor_label()
        if label in settings:
            light = actor.get_component_by_class(unreal.PointLightComponent)
            intensity,radius = settings[label]
            light.set_editor_property("intensity_units",unreal.LightUnits.CANDELAS)
            light.set_intensity(intensity)
            light.set_light_color(unreal.LinearColor(1.0,0.78,0.54,1))
            light.set_editor_property("attenuation_radius",radius)
            light.set_editor_property("source_radius",22.0)
            records.append({"name":label,"candela":intensity,"radius_cm":radius})
    if len(records)!=4:
        raise RuntimeError("Home lights missing in "+path)
    LEVEL.save_current_level()
    report["maps"].append({"path":path,"lights":records})
report["success"] = True
(ROOT/"house_lighting_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
