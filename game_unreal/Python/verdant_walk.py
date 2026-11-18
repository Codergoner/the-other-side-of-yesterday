"""PIE walking check for Verdant_City: the native character is driven along an authored route
with AddMovementInput only (force=False). No teleport inside a route, no collision or movement
mode override. One initial placement is allowed and reported when a route does not start at
the player start. Launch flags: -VerdantRoute=A|B  -VerdantEra=Past|Present
"""
import json
import math
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc


def z_street(y):
    return 8 + (y + 22) * .10


SQUARE = 10.7
ROUTES = {
    'A': [('street_start', (0, -18, z_street(-18))), ('street_mid', (0, -4, z_street(-4))), ('walk_arcade', (-3.4, 3.5, z_street(3.5))),
          ('alley', (-8, 3.5, SQUARE)), ('square_east', (-14, 6, SQUARE)), ('square_south', (-24, 3.5, SQUARE)), ('square_west', (-31, 8, SQUARE)),
          ('square_north', (-21.5, 12.0, SQUARE)), ('square_mid', (-19.5, 9.5, SQUARE)), ('square_exit', (-13.5, 9.5, SQUARE)),
          ('lane_mouth', (-12.8, 13.8, SQUARE)), ('market_lane', (-8, 14, 11.15)), ('street_upper', (0, 14, z_street(14))),
          ('stair_landing', (5, 14, 11.6)), ('west_flight_mid', (7, 7.5, 9.0)), ('overlook', (7, .5, 6.4)), ('cross_landing', (11, .5, 6.4)),
          ('east_flight_mid', (11, 7.5, 3.8)), ('stair_foot', (11, 13.6, 1.36)), ('quay', (15, 14, 1.2)), ('quay_end', (22, 12, 1.2))],
    'B': [('street_top', (0, 34, z_street(34))), ('campanile_stair', (1.65, 39.5, 15.6)), ('forecourt', (0, 45, 17.5)),
          ('cathedral_stair', (0, 51, 21.1)), ('plaza_west', (0, 58, 25)), ('plaza_north_side', (0, 72, 25)), ('plaza_rear', (0, 81, 25)),
          ('rear_mid', (12, 81, 25)), ('rear_east', (19.5, 81, 25)), ('cloister_passage', (19.5, 60, 25)), ('apron', (19.5, 54, 25)),
          ('portal_outside', (11, 52.5, 25)), ('portal', (11, 57.5, 25)), ('nave', (11, 66, 25))],
}
PLACEMENT = {'A': None, 'B': (0, 30, z_street(30))}

cmd = unreal.SystemLibrary.get_command_line()
route_id = next((part.split('=')[1].upper() for part in cmd.split() if part.lower().startswith('-verdantroute=')), 'A')
ERA = 'Present' if '-verdantera=present' in cmd.lower() else 'Past'
ROUTE = [(name, [p[0] * 100, -p[1] * 100, p[2] * 100]) for name, p in ROUTES[route_id]]
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
REPORT = {'success': False, 'route': route_id, 'era': ERA, 'map': vc.MAP, 'run': STAMP, 'waypoints': [], 'samples': [],
          'input_method': 'Pawn.AddMovementInput(direction, scale, force=False)', 'route_teleports': 0, 'collision_disabled': False,
          'movement_mode_forced': False, 'physical_input_tested': False, 'packaged_tested': False, 'performance_measured': False,
          'authored_route_cm': [{'id': n, 'floor_cm': p} for n, p in ROUTE]}
STATE = {'phase': 'load', 'wall_start': time.monotonic(), 'index': 0, 'closing': False, 'handle': None, 'fall_since': None,
         'last_sample': -100.0, 'last_write': 0.0}
OUT = vc.EVIDENCE / ('walk_%s_%s.json' % (route_id, ERA))


def xyz(v):
    return [round(v.x, 2), round(v.y, 2), round(v.z, 2)]


def write():
    REPORT['phase'] = STATE['phase']
    vc.write_json(OUT, REPORT)
    STATE['last_write'] = time.monotonic()


def foot():
    p = STATE['pawn'].get_actor_location()
    return unreal.Vector(p.x, p.y, p.z - STATE['half_height'])


def sample(t, target=None):
    pawn, move = STATE['pawn'], STATE['movement']
    f = foot()
    row = {'t': round(t, 2), 'foot_cm': xyz(f), 'speed_cm_s': round(pawn.get_velocity().length(), 1),
           'grounded': bool(move.is_moving_on_ground()), 'falling': bool(move.is_falling())}
    if target:
        row['remaining_cm'] = round(math.hypot(target[0] - f.x, target[1] - f.y), 1)
    return row


def request_finish(error=None):
    if STATE['closing']:
        return
    if error:
        REPORT['error'] = error
    STATE['closing'] = True
    STATE['close_wall'] = time.monotonic()
    if vc.levels.is_in_play_in_editor():
        vc.levels.editor_request_end_play()


def finish():
    REPORT['complete_route_walked'] = len(REPORT['waypoints']) == len(ROUTE) and all(w['passed'] for w in REPORT['waypoints'])
    REPORT['success'] = 'error' not in REPORT and REPORT['complete_route_walked']
    REPORT['wall_seconds'] = round(time.monotonic() - STATE['wall_start'], 1)
    STATE['phase'] = 'complete'
    write()
    if STATE['handle'] is not None:
        unreal.unregister_slate_post_tick_callback(STATE['handle'])
    vc.log('walk', json.dumps({'route': route_id, 'era': ERA, 'success': REPORT['success'], 'waypoints': len(REPORT['waypoints']),
                               'error': (REPORT.get('error') or '')[-300:]}))
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.quit_editor()


def begin_segment(t):
    name, target = ROUTE[STATE['index']]
    f = foot()
    STATE.update(segment_t=t, progress_t=t, progress=math.hypot(target[0] - f.x, target[1] - f.y), segment_start=xyz(f), fall_since=None)


def walk(t):
    pawn, move = STATE['pawn'], STATE['movement']
    f = foot()
    name, target = ROUTE[STATE['index']]
    dx, dy = target[0] - f.x, target[1] - f.y
    distance = math.hypot(dx, dy)
    if STATE['controller'].is_move_input_ignored():
        raise RuntimeError('Controller ignores movement input; the game mode did not release the pawn')
    if t - STATE['last_sample'] >= .25:
        REPORT['samples'].append(sample(t, target))
        STATE['last_sample'] = t
    if move.is_falling():
        STATE['fall_since'] = STATE['fall_since'] if STATE['fall_since'] is not None else t
        if t - STATE['fall_since'] > 1.2:
            raise RuntimeError('Falling for more than 1.2 s near %s at %s' % (name, xyz(f)))
    else:
        STATE['fall_since'] = None
    start = STATE['segment_start']
    vx, vy = target[0] - start[0], target[1] - start[1]
    denominator = vx * vx + vy * vy
    k = max(0.0, min(1.0, ((f.x - start[0]) * vx + (f.y - start[1]) * vy) / denominator)) if denominator else 1.0
    expected = start[2] + (target[2] - start[2]) * k
    if f.z < expected - 75:
        raise RuntimeError('Fell more than 75 cm below the authored route near %s at %s' % (name, xyz(f)))
    if distance <= 30:
        if not move.is_moving_on_ground():
            return
        error = abs(f.z - target[2])
        row = {'id': name, 'expected_floor_cm': target, 'actual_foot_cm': xyz(f), 'floor_error_cm': round(error, 1),
               'passed': error <= 30, 'segment_seconds': round(t - STATE['segment_t'], 2)}
        REPORT['waypoints'].append(row)
        write()
        if not row['passed']:
            raise RuntimeError('Floor mismatch at %s: %s' % (name, row))
        STATE['index'] += 1
        if STATE['index'] >= len(ROUTE):
            request_finish()
            return
        begin_segment(t)
        return
    if distance < STATE['progress'] - 6:
        STATE.update(progress=distance, progress_t=t)
    if t - STATE['progress_t'] > 3.0:
        REPORT['stall'] = sample(t, target)
        raise RuntimeError('Walking stalled before %s with %.0f cm remaining at %s' % (name, distance, xyz(f)))
    if t - STATE['segment_t'] > 30:
        raise RuntimeError('Segment timeout before ' + name)
    pawn.add_movement_input(unreal.Vector(dx / distance, dy / distance, 0), min(1.0, distance / 80), False)
    if time.monotonic() - STATE['last_write'] > 1.0:
        write()


def tick(_delta):
    try:
        if STATE['closing']:
            if not vc.levels.is_in_play_in_editor():
                finish()
            elif time.monotonic() - STATE['close_wall'] > 25:
                raise RuntimeError('PIE did not shut down')
            return
        if time.monotonic() - STATE['wall_start'] > 400:
            raise RuntimeError('Wall-time watchdog')
        if STATE['phase'] == 'load':
            vc.require(vc.levels.load_level(vc.MAP), 'Cannot load ' + vc.MAP)
            vc.levels.editor_request_begin_play()
            STATE['phase'] = 'waiting'
            write()
            return
        world = vc.editor.get_game_world()
        pawn = unreal.GameplayStatics.get_player_character(world, 0) if world else None
        if STATE['phase'] == 'waiting':
            if not pawn or pawn.get_controller() is None:
                return
            move = pawn.get_component_by_class(unreal.CharacterMovementComponent)
            capsule = pawn.get_component_by_class(unreal.CapsuleComponent)
            vc.require(move is not None and capsule is not None, 'Player pawn has no character movement')
            STATE.update(world=world, pawn=pawn, controller=pawn.get_controller(), movement=move,
                         half_height=float(capsule.get_scaled_capsule_half_height()))
            REPORT['character'] = {'class': pawn.get_class().get_path_name(), 'capsule_radius_cm': float(capsule.get_scaled_capsule_radius()),
                                   'capsule_half_height_cm': STATE['half_height'], 'max_step_height_cm': float(move.get_editor_property('max_step_height')),
                                   'walkable_floor_angle': float(move.get_walkable_floor_angle()), 'max_walk_speed': float(move.get_editor_property('max_walk_speed'))}
            if hasattr(unreal, 'VerdantEraLibrary'):
                REPORT['era_actors'] = unreal.VerdantEraLibrary.apply_era(world, ERA == 'Past')
            for command in ('t.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0'):
                unreal.SystemLibrary.execute_console_command(world, command)
            STATE['phase'] = 'settle'
            STATE['phase_t'] = unreal.GameplayStatics.get_time_seconds(world)
            return
        t = unreal.GameplayStatics.get_time_seconds(world)
        if STATE['phase'] == 'settle':
            if t - STATE['phase_t'] < .8:
                return
            REPORT['natural_spawn_foot_cm'] = xyz(foot())
            placement = PLACEMENT[route_id]
            if placement:
                desired = unreal.Vector(placement[0] * 100, -placement[1] * 100, placement[2] * 100 + STATE['half_height'] + 3)
                REPORT['initial_placement'] = {'to_capsule_center_cm': xyz(desired), 'counts_as_walking': False}
                pawn.set_actor_location(desired, False, True)
                STATE['phase'] = 'placed'
                STATE['phase_t'] = t
                return
            begin_segment(t)
            STATE['phase'] = 'walking'
            return
        if STATE['phase'] == 'placed':
            if t - STATE['phase_t'] < .8:
                return
            begin_segment(t)
            STATE['phase'] = 'walking'
            return
        if STATE['phase'] == 'walking':
            walk(t)
    except Exception:
        if STATE['closing']:
            REPORT['shutdown_error'] = traceback.format_exc()
            finish()
        else:
            request_finish(traceback.format_exc())


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
try:
    unreal.get_default_object(unreal.EditorPerformanceSettings).set_editor_property('throttle_cpu_when_not_foreground', False)
except Exception:
    pass
write()
STATE['handle'] = unreal.register_slate_post_tick_callback(tick)
