"""Actually start PIE, verify native character grounding/motion/jump, then quit.

Run in a full editor process with -ExecutePythonScript=... (not a commandlet).
The test drives normal CharacterMovement input, not teleportation.
"""
from pathlib import Path
import json
import math
import time
import traceback
import unreal

unreal.EditorPythonScripting.set_keep_python_script_alive(True)
try:
    unreal.get_default_object(unreal.EditorPerformanceSettings).set_editor_property("throttle_cpu_when_not_foreground", False)
except Exception:
    pass

ROOT = Path(unreal.Paths.project_dir()).resolve()
OUT = ROOT / "house_runtime_validation.json"
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
MAPS = ["/Game/Home/Maps/House_ThirdPerson", "/Game/Home/Maps/House_FirstPerson"]
REPORT = {"success": False, "mode": "Actual Play In Editor: approach stairs, enter home, jump, land", "maps": []}
ROUTE = [
    ("Interior stair foot",[-2.85,-2.5,1.31]),
    ("Interior stair middle",[-2.85,-0.535,2.725]),
    ("Upper stair landing",[-2.85,2.05,4.3]),
    ("Landing turn",[-1.4,2.05,4.3]),
    ("Bedroom passage",[-1.4,0,4.3]),
    ("Balcony approach",[-1.65,-2.9,4.3]),
    ("Balcony doorway",[-1.65,-3.65,4.3]),
    ("Balcony viewpoint",[-1.65,-4.65,4.345]),
]
state = {"index": 0, "phase": "load", "time": time.monotonic(), "start": None, "max_z": -1e20}
handle = None


def xyz(v):
    return [round(v.x, 3), round(v.y, 3), round(v.z, 3)]


def placed(local):
    x,y,z = local
    return unreal.Vector((-8-y)*100,(13-x)*100,(8.96+z)*100)


def write():
    OUT.write_text(json.dumps(REPORT, indent=2), encoding="utf-8")


def transition(phase):
    state.update(phase=phase, time=time.monotonic())
    REPORT["active_phase"] = phase
    if state.get("record"):
        REPORT["active_record"] = state["record"]
    write()
    game_world = EDITOR.get_game_world()
    if game_world:
        state["game_time"] = unreal.GameplayStatics.get_time_seconds(game_world)


def finish(error=None):
    if error:
        REPORT["error"] = error
    REPORT["success"] = error is None and len(REPORT["maps"]) == len(MAPS) and all(r.get("passed") for r in REPORT["maps"])
    write()
    if LEVEL.is_in_play_in_editor():
        LEVEL.editor_request_end_play()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.log("HARBOR_RUNTIME_VALIDATION " + json.dumps(REPORT))
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    try:
        elapsed = time.monotonic() - state["time"]
        phase = state["phase"]
        if elapsed > 90:
            raise RuntimeError("PIE validation timed out in %s; simulation seconds=%s" % (phase,state.get("game_time")))
        if phase == "load":
            if not LEVEL.load_level(MAPS[state["index"]]):
                raise RuntimeError("Could not load map")
            LEVEL.editor_request_begin_play()
            transition("wait_pawn")
            return
        world = EDITOR.get_game_world()
        pawn = unreal.GameplayStatics.get_player_character(world, 0) if world else None
        game_elapsed = unreal.GameplayStatics.get_time_seconds(world)-state.get("game_time",0) if world else 0
        if phase == "wait_pawn":
            if pawn:
                state["record"] = {"map": MAPS[state["index"]], "pawn_class": pawn.get_class().get_path_name()}
                state["record"]["controller_class"] = pawn.get_controller().get_class().get_path_name() if pawn.get_controller() else None
                control_rotation = pawn.get_controller().get_control_rotation()
                state["record"]["control_rotation"] = {"pitch":control_rotation.pitch,"yaw":control_rotation.yaw,"roll":control_rotation.roll}
                state["record"]["facing_down_lane"] = abs(control_rotation.pitch)<1 and abs((control_rotation.yaw-180+180)%360-180)<1
                state["record"]["initially_paused"] = unreal.GameplayStatics.is_game_paused(world)
                unreal.GameplayStatics.set_game_paused(world, False)
                unreal.SystemLibrary.execute_console_command(world,"t.IdleWhenNotForeground 0")
                unreal.SystemLibrary.execute_console_command(world,"Slate.bAllowThrottling 0")
                transition("settle")
            elif elapsed > 60:
                raise RuntimeError("PIE did not spawn a possessed walking Character")
        elif phase == "settle" and game_elapsed > 1.5:
            movement = pawn.get_component_by_class(unreal.CharacterMovementComponent)
            state["start"] = pawn.get_actor_location()
            state["record"]["settled_position_cm"] = xyz(state["start"])
            state["record"]["grounded_at_start"] = bool(movement.is_moving_on_ground())
            state["max_z"] = state["start"].z
            if "IntegrationProbe" in MAPS[state["index"]]:
                state["record"].update(passed=bool(movement.is_moving_on_ground()), probe_only=True)
                REPORT["maps"].append(state["record"])
                LEVEL.editor_request_end_play()
                transition("end")
            else:
                transition("walk")
        elif phase == "walk":
            pawn.add_movement_input(unreal.Vector(-1, 0, 0), 1.0, True)
            if game_elapsed > 1.4:
                pawn.get_component_by_class(unreal.CharacterMovementComponent).stop_movement_immediately()
                location = pawn.get_actor_location()
                state["record"]["after_walk_position_cm"] = xyz(location)
                displacement = math.hypot(location.x-state["start"].x, location.y-state["start"].y)
                state["record"]["walk_displacement_cm"] = round(displacement, 3)
                state["record"]["walk_simulation_seconds"] = round(game_elapsed, 3)
                state["record"]["walk_wall_seconds"] = round(elapsed, 3)
                state["record"]["grounded_after_walk"] = bool(pawn.get_component_by_class(unreal.CharacterMovementComponent).is_moving_on_ground())
                state["record"]["entered_ground_room"] = location.x < -470 and location.z > 1050
                state["jump_base_z"] = location.z
                pawn.jump()
                transition("jump")
        elif phase == "jump":
            state["max_z"] = max(state["max_z"], pawn.get_actor_location().z)
            if game_elapsed > 0.2:
                pawn.stop_jumping()
            if game_elapsed > 1.4:
                state["record"]["jump_height_cm"] = round(state["max_z"]-state["jump_base_z"], 3)
                state["record"]["grounded_after_jump"] = bool(pawn.get_component_by_class(unreal.CharacterMovementComponent).is_moving_on_ground())
                record = state["record"]
                record["passed"] = record["facing_down_lane"] and record["grounded_at_start"] and record["grounded_after_walk"] and record["entered_ground_room"] and record["grounded_after_jump"] and record["walk_displacement_cm"] > 100 and record["jump_height_cm"] > 10
                state["route_index"] = 0
                record["interior_route"] = []
                transition("navigate")
        elif phase == "navigate":
            name,local = ROUTE[state["route_index"]]
            target = placed(local)
            location = pawn.get_actor_location()
            dx,dy = target.x-location.x,target.y-location.y
            distance = math.hypot(dx,dy)
            if distance < 15:
                movement = pawn.get_component_by_class(unreal.CharacterMovementComponent)
                movement.stop_movement_immediately()
                floor_error = abs(location.z-88-target.z)
                row = {"name":name,"position_cm":xyz(location),"expected_floor_cm":xyz(target),
                       "floor_error_cm":round(floor_error,2),"grounded":bool(movement.is_moving_on_ground())}
                row["passed"] = row["grounded"] and floor_error < 40
                state["record"]["interior_route"].append(row)
                state["route_index"] += 1
                write()
                if state["route_index"] >= len(ROUTE):
                    record = state["record"]
                    record["passed"] = record["passed"] and all(point["passed"] for point in record["interior_route"])
                    REPORT["maps"].append(record)
                    write()
                    LEVEL.editor_request_end_play()
                    transition("end")
                else:
                    transition("navigate")
            else:
                pawn.add_movement_input(unreal.Vector(dx/distance,dy/distance,0),min(1,distance/90),True)
                if game_elapsed > 12:
                    raise RuntimeError("Character blocked before %s; current=%s, target=%s" % (name,xyz(location),xyz(target)))
        elif phase == "end" and elapsed > 1.5 and not LEVEL.is_in_play_in_editor():
            state["index"] += 1
            if state["index"] >= len(MAPS):
                finish()
            else:
                transition("load")
        elif elapsed > 90:
            raise RuntimeError("PIE validation timeout in " + phase)
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)

