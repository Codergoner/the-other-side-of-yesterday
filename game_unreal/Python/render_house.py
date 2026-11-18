"""Capture native Unreal renders through a viewport-independent render target."""
from pathlib import Path
import json
import time
import traceback
import sys
import unreal

unreal.EditorPythonScripting.set_keep_python_script_alive(True)
try:
    unreal.get_default_object(unreal.EditorPerformanceSettings).set_editor_property("throttle_cpu_when_not_foreground",False)
except Exception:
    pass
ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/"Python"))
import harbor_lighting
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for name in []:
    LEVEL.load_level("/Game/Harbor/Maps/"+name)
    harbor_lighting.configure(ACTORS.get_all_level_actors())
    LEVEL.save_current_level()
LEVEL.load_level("/Game/Home/Maps/House_ThirdPerson")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
for command in ["r.Streaming.PoolSize 1500", "r.ScreenPercentage 100", "t.IdleWhenNotForeground 0", "Slate.bAllowThrottling 0"]:
    unreal.SystemLibrary.execute_console_command(world,command)
capture = ACTORS.spawn_actor_from_class(unreal.SceneCapture2D,unreal.Vector(0,0,0),unreal.Rotator(pitch=0,yaw=0,roll=0),True)
component = capture.get_component_by_class(unreal.SceneCaptureComponent2D)
target = unreal.RenderingLibrary.create_render_target2d(world,1600,1000,unreal.TextureRenderTargetFormat.RTF_RGBA8,unreal.LinearColor(1,0,1,1),False,False)
# RGBA8 render targets default to linear display gamma. Match Unreal's game
# viewport display encoding so exported PNGs do not appear artificially dark.
target.set_editor_property("target_gamma",2.2)
component.set_editor_property("texture_target",target)
component.set_editor_property("capture_source",unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
component.set_editor_property("capture_every_frame",False)
component.set_editor_property("capture_on_movement",False)
component.set_editor_property("always_persist_rendering_state",True)
settings = harbor_lighting.exposure(component.get_editor_property("post_process_settings"))
component.set_editor_property("post_process_settings",settings)
component.set_editor_property("post_process_blend_weight",1.0)
VIEWS = [
    {"name":"House_Unreal_Overview","position":[1100,0,1896],"target":[-720,1300,1306],"fov":51},
    {"name":"House_Unreal_Entrance","position":[900,800,1496],"target":[-600,1300,1296],"fov":54},
    {"name":"House_Unreal_Interior","position":[-560,1240,1166],"target":[-860,1530,1176],"fov":82},
    {"name":"House_Unreal_Bedroom","position":[-590,1455,1476],"target":[-900,1235,1406],"fov":82},
]
state = {"index":0,"phase":"warmup","time":time.monotonic(),"frames":0}
report = {"success":False,"renderer":"Native Unreal SceneCapture2D, FinalColorLDR -> RGBA8 render target","images":[],"pixel_samples":[]}
handle = None


def finish(error=None):
    if error:
        report["error"] = error
    report["success"] = error is None and len(report["images"]) == len(VIEWS)
    (ROOT/"house_render_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    try:
        elapsed = time.monotonic()-state["time"]
        if state["phase"] == "warmup" and elapsed > 3:
            view = VIEWS[state["index"]]
            position,target_point = unreal.Vector(*view["position"]),unreal.Vector(*view["target"])
            capture.set_actor_location(position,False,False)
            capture.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(position,target_point),False)
            component.set_editor_property("fov_angle",view["fov"])
            unreal.AutomationLibrary.finish_loading_before_screenshot()
            component.capture_scene()
            state.update(phase="capture",time=time.monotonic(),frames=0)
        elif state["phase"] == "capture":
            state["frames"] += 1
            if state["frames"] < 24:
                component.capture_scene()
            elif elapsed > 2:
                samples = []
                colors = []
                for y in [100,300,500,700,900]:
                    for x in [100,400,800,1200,1500]:
                        color = unreal.RenderingLibrary.read_render_target_pixel(world,target,x,y)
                        samples.extend([int(color.r),int(color.g),int(color.b)])
                        colors.append((int(color.r),int(color.g),int(color.b)))
                minimum,maximum = min(samples),max(samples)
                mean = sum(samples)/len(samples)
                variance = sum((value-mean)**2 for value in samples)/len(samples)
                unique_colors = len(set(colors))
                report["pixel_samples"].append({"view":VIEWS[state["index"]]["name"],"min":minimum,"max":maximum,"mean":mean,"variance":variance,"unique_colors":unique_colors})
                if maximum < 8 or variance < 2 or unique_colors < 4:
                    raise RuntimeError("Scene capture has no usable image content: " + str(report["pixel_samples"][-1]))
                if any(word in VIEWS[state["index"]]["name"] for word in ["Interior","Bedroom"]) and (mean < 25 or maximum < 70):
                    raise RuntimeError("Saved room lighting is too dark for gameplay: "+str(report["pixel_samples"][-1]))
                filename = VIEWS[state["index"]]["name"]+".png"
                unreal.RenderingLibrary.export_render_target(world,target,str(ROOT),filename)
                output = ROOT/filename
                if not output.exists() or output.stat().st_size < 50000:
                    raise RuntimeError("Render target PNG export failed: " + str(output))
                report["images"].append(str(output))
                state["index"] += 1
                if state["index"] >= len(VIEWS):
                    finish()
                else:
                    state.update(phase="warmup",time=time.monotonic())
            elif elapsed > 120:
                raise RuntimeError("Scene capture timeout")
    except Exception:
        finish(traceback.format_exc())


handle = unreal.register_slate_post_tick_callback(tick)

