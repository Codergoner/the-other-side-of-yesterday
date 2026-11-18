"""PIE walk along the playable story route of the merged Verdant_Desktop map, in one era.

Enters through the real release front end (New Game on an isolated QA profile, recollections skipped),
then drives the native character with AddMovementInput (force = false) only: no teleport inside the
route, no collision or movement-mode override. The present walk starts at the New Game spawn in the
family room; the past walk sets EraIndex = 1 through an unsaved /Temp fixture Blueprint, calls the
manager's own ApplyWorldState (the story's era presentation, which now also switches the Verdant
city) and makes one reported initial placement at the story's own past checkpoint, the gate.

Flags: -VerdantStoryWalk -VerdantEra=Past|Present [-VerdantMergeStamp=<stamp>]  plus a fresh short -UserDir.
Report: validation/verdant_merge/<stamp>/walk_<Era>.json with PIE screenshots beside it.
"""
import hashlib
import json
import math
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal

unreal.EditorPythonScripting.set_keep_python_script_alive(True)
try:
    unreal.get_default_object(unreal.EditorPerformanceSettings).set_editor_property('throttle_cpu_when_not_foreground', False)
except Exception:
    pass

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc
import opening_graph as og

MAP = '/Game/Quest/Maps/Verdant_Desktop'
MANAGER_PATH = '/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C'
OWNER = 'Verdant.StoryOwned'
PAST, PRESENT = 'Opening.PastOnly', 'Opening.PresentOnly'
CMD = unreal.SystemLibrary.get_command_line()
vc.require(unreal.SystemLibrary.parse_param(CMD, 'VerdantStoryWalk'), 'Explicit -VerdantStoryWalk required')
ERA = 'Present' if '-verdantera=present' in CMD.lower() else 'Past'
found = re.search(r'-VerdantMergeStamp=(\S+)', CMD)
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
OUT = vc.PROJECT / 'validation' / 'verdant_merge' / (found.group(1) if found else STAMP)
OUT.mkdir(parents=True, exist_ok=True)
REPORT_PATH = OUT / ('walk_%s.json' % ERA)
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
NAMESPACE = 'YVWK_' + STAMP
PROFILE_SLOT = NAMESPACE + '_Profile'
CAMPAIGN_PREFIX = NAMESPACE + '_'


def z_street(y_cm):
    return 1020.0 - 0.1 * y_cm


# Route in Unreal centimetres with the floor the Verdant plan offers at each point.
HOME = [('home_room', (-620, 1240, 1011)), ('inside_front_door', (-480, 1240, 1011)), ('entry_threshold', (-420, 1240, 1011)),
        ('front_porch', (-285, 1240, 1011)), ('approach_stair_top', (-230, 1240, 1011)), ('approach_stair_middle', (-115, 1240, 953.5)),
        ('approach_stair_foot', (-5, 1240, 896))]
STREET = [('courtyard_gate', (50, 1240, 896)), ('street_below_clinic', (50, 950, 925)), ('clinic_street', (50, 740, 946)),
          ('clinic_bay', (-75, 730, 947)), ('clinic_healer_approach', (-120, 600, 960)), ('clinic_return', (50, 690, 951)),
          ('market_approach', (50, 400, 980)), ('market_street', (30, 0, 1020)), ('alley_mouth', (-240, -200, 1040)),
          ('alley_arch', (-340, -350, 1058)), ('alley', (-700, -350, 1062)), ('square_east', (-1300, -600, 1070)),
          ('alley_return', (-700, -350, 1062)), ('street_return', (-240, -300, 1050)), ('sela_approach', (60, -300, 1050)),
          ('canopy_approach', (-45, -535, 1073.5)), ('shelter_fixing', (60, -535, 1073.5)), ('sea_pause', (50, -900, 1110)),
          ('upper_street', (50, -1400, 1160)), ('shore_opening', (275, -1400, 1160)), ('overlook', (450, -1400, 1160))]
ROUTE = (HOME if ERA == 'Present' else []) + STREET
PLACEMENT = None if ERA == 'Present' else (120, 1240, 991)   # the story's own past checkpoint (RestorePlayerCheckpoint)
SHOTS = {'courtyard_gate': (50, 300, 1100), 'clinic_healer_approach': (-700, -200, 1150), 'sela_approach': (-400, 300, 1200),
         'shelter_fixing': (300, -700, 1200), 'overlook': (4400, -2600, 550), 'home_room': (-915, 1412, 1130),
         'square_east': (-2400, -800, 1200)}

REPORT = {'success': False, 'run': STAMP, 'era': ERA, 'map': MAP, 'waypoints': [], 'samples': [], 'screenshots': [], 'checks': [],
          'input_method': 'Pawn.AddMovementInput(direction, scale, force=False)', 'route_teleports': 0, 'collision_disabled': False,
          'movement_mode_forced': False, 'physical_input_tested': False, 'packaged_tested': False, 'performance_measured': False,
          'entry_policy': 'Real release menu New Game on an isolated QA profile; recollections skipped; '
                          + ('no fixture (present is the New Game era)' if ERA == 'Present' else
                             'EraIndex=1 fixture through an unsaved /Temp Blueprint, then the manager\'s own ApplyWorldState; '
                             'one initial placement at the past checkpoint (120, 1240, 991) reported, not counted as walking'),
          'authored_route_cm': [{'id': n, 'floor_cm': list(p)} for n, p in ROUTE], 'qa_namespace': NAMESPACE}
S = {'world': None, 'manager': None, 'pawn': None, 'controller': None, 'camera': None, 'override': None, 'step': 'startup',
     'menu_entry': None, 'movement': None, 'half_height': 0.0}
handle = None
pending = None
deadline = 0.0
closing = False
saved_dir = Path(unreal.Paths.project_saved_dir()).resolve()
if saved_dir == (vc.PROJECT / 'Saved').resolve():
    raise RuntimeError('Use a dedicated -UserDir so the player save directory is never touched')
SAVE_DIR = saved_dir / 'SaveGames'
PROTECTED = [vc.PROJECT / 'Content/Opening/Blueprints/BP_OpeningActions.uasset', vc.PROJECT / 'Content/Quest/Maps/Verdant_Desktop.umap',
             vc.PROJECT / 'Content/Verdant/Maps/Verdant_City.umap']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


REPORT['protected_before'] = {str(p): sha(p) for p in PROTECTED}

FIXTURE_BP = og.blueprint('/Temp/BP_VerdantWalkFixture', unreal.Actor)
_graph = og.function(FIXTURE_BP, 'SetEra', inputs={'Target': og.object_type(MANAGER_PATH), 'Era': 'int'})
_era = _graph.set('EraIndex', _graph.input('Era'), owner=_graph.input('Target'), class_path=MANAGER_PATH)
og.link(_graph.entry, og.pin_in(_era))
og.compile_bp(FIXTURE_BP, save=False)
FIXTURE = unreal.get_default_object(og.L.generated_class(FIXTURE_BP))


def prop(name):
    return S['manager'].get_editor_property(name)


def action(name, *args):
    return S['manager'].call_method(name, args=tuple(args))


def wait(seconds=.06):
    return {'seconds': seconds}


def until(test, description, timeout=60):
    return {'predicate': test, 'description': description, 'timeout': timeout}


def write():
    REPORT['active_step'] = S['step']
    REPORT_PATH.write_text(json.dumps(REPORT, indent=2, ensure_ascii=False, default=str), encoding='utf-8')


def check(name, passed, details=None):
    row = {'name': name, 'passed': bool(passed)}
    if details is not None:
        row['details'] = details
    REPORT['checks'].append(row)
    write()
    if not passed:
        raise AssertionError(name + ': ' + str(details))


def xyz(v):
    return [round(v.x, 2), round(v.y, 2), round(v.z, 2)]


def foot():
    p = S['pawn'].get_actor_location()
    return unreal.Vector(p.x, p.y, p.z - S['half_height'])


def floor_under_foot():
    f = foot()
    hit = unreal.SystemLibrary.line_trace_single(S['world'], unreal.Vector(f.x, f.y, f.z + 60), unreal.Vector(f.x, f.y, f.z - 200),
                                                 unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [S['pawn']], unreal.DrawDebugTrace.NONE, True)
    if isinstance(hit, tuple):
        hit = next((h for h in hit if isinstance(h, unreal.HitResult)), None)
    if hit is None:
        return None
    parts = hit.to_tuple()
    if not bool(parts[0]) or parts[4] is None:
        return None
    actor = parts[9]
    return {'z': round(float(parts[4].z), 2), 'actor': actor.get_actor_label() if actor else None}


def ready():
    world = EDITOR.get_game_world()
    if world is None:
        return False
    pawn = unreal.GameplayStatics.get_player_character(world, 0)
    if pawn is None or pawn.get_controller() is None:
        return False
    cls = unreal.load_class(None, MANAGER_PATH)
    found = unreal.GameplayStatics.get_all_actors_of_class(world, cls)
    if len(found) != 1:
        return False
    S.update(world=world, pawn=pawn, controller=pawn.get_controller(), camera=unreal.GameplayStatics.get_player_camera_manager(world, 0), manager=found[0])
    if prop('Player') is None or S['camera'] is None or not bool(prop('ReleaseBooted')):
        return False
    if S.get('menu_entry'):
        if not bool(prop('ReleaseMenuActive')) or int(prop('ReleaseMenuScreen')) != 0:
            return False
        if bool(prop('ReleaseContinueAvailable')):
            raise RuntimeError('A supposedly fresh QA profile already has progress')
        if str(prop('ReleaseProfileSlot')) != PROFILE_SLOT:
            raise RuntimeError('Front end is not using the isolated QA profile: ' + str(prop('ReleaseProfileSlot')))
        action('ReleaseNewGame')
        S['menu_entry'] = None
        REPORT['menu_entry'] = {'action': 'new', 'slot': str(prop('SaveSlot')), 'profile': str(prop('ReleaseProfileSlot'))}
        write()
    return bool(prop('ReleaseSessionStarted'))


def era_snapshot(label):
    """How the story's era presentation left the Verdant actors and the old scenery in the PIE world."""
    rows = {'label': label, 'era_index': int(prop('EraIndex')), 'verdant_past': {'hidden': 0, 'shown': 0, 'colliding': 0},
            'verdant_present': {'hidden': 0, 'shown': 0, 'colliding': 0}, 'lights': {}, 'dev_scenery': {}}
    for actor in unreal.GameplayStatics.get_all_actors_with_tag(S['world'], OWNER):
        tags = [str(t) for t in actor.get_editor_property('tags')]
        key = 'verdant_past' if PAST in tags else 'verdant_present' if PRESENT in tags else None
        if key is None:
            continue
        hidden = bool(actor.get_editor_property('hidden'))
        rows[key]['hidden' if hidden else 'shown'] += 1
        rows[key]['colliding'] += int(bool(actor.get_actor_enable_collision()))
        label_ = actor.get_actor_label()
        if label_.startswith(('Verdant_Sun', 'Verdant_Fog', 'Verdant_SkyLight', 'Verdant_Sky_')):
            rows['lights'][label_] = 'hidden' if hidden else 'active'
    for actor in unreal.GameplayStatics.get_all_actors_of_class(S['world'], unreal.StaticMeshActor):
        label_ = actor.get_actor_label()
        if label_ in ('SM_StreetSurface', 'SM_LeftHouse_B', 'SM_Sea', 'SM_HarborStairs', 'Quest - coastal sky gradient and slow clouds'):
            rows['dev_scenery'][label_] = {'hidden': bool(actor.get_editor_property('hidden')), 'collision': bool(actor.get_actor_enable_collision())}
    REPORT.setdefault('era_snapshots', []).append(rows)
    write()
    return rows


def screenshot(label, look_at):
    S['controller'].set_control_rotation(unreal.MathLibrary.find_look_at_rotation(S['camera'].get_camera_location(), unreal.Vector(*look_at)))
    path = OUT / ('walk_%s_%s.png' % (ERA, label))
    unreal.SystemLibrary.execute_console_command(S['world'], 'shot showui filename="' + str(path).replace('\\', '/') + '" -nosuffix')
    return {'screenshot': path, 'label': label, 'description': 'PIE viewport ' + label, 'timeout': 30}


def walk_to(name, target):
    seg = {'name': name, 'target': target, 'start': xyz(foot()), 't0': unreal.GameplayStatics.get_time_seconds(S['world']),
           'progress': math.hypot(target[0] - foot().x, target[1] - foot().y), 'progress_t': None, 'fall_since': None, 'last_sample': -100.0}
    seg['progress_t'] = seg['t0']
    return {'walk': seg}


def walk_step(seg):
    """One tick of movement input toward the segment target; returns True when the waypoint is reached."""
    pawn, move = S['pawn'], S['movement']
    t = unreal.GameplayStatics.get_time_seconds(S['world'])
    f = foot()
    name, target = seg['name'], seg['target']
    dx, dy = target[0] - f.x, target[1] - f.y
    distance = math.hypot(dx, dy)
    if S['controller'].is_move_input_ignored():
        raise RuntimeError('Controller ignores movement input near ' + name)
    if t - seg['last_sample'] >= .25:
        REPORT['samples'].append({'t': round(t, 2), 'foot_cm': xyz(f), 'speed_cm_s': round(pawn.get_velocity().length(), 1),
                                  'grounded': bool(move.is_moving_on_ground()), 'falling': bool(move.is_falling()), 'toward': name, 'remaining_cm': round(distance, 1)})
        seg['last_sample'] = t
    if move.is_falling():
        seg['fall_since'] = seg['fall_since'] if seg['fall_since'] is not None else t
        if t - seg['fall_since'] > 1.2:
            raise RuntimeError('Falling for more than 1.2 s near %s at %s' % (name, xyz(f)))
    else:
        seg['fall_since'] = None
    start = seg['start']
    vx, vy = target[0] - start[0], target[1] - start[1]
    denominator = vx * vx + vy * vy
    k = max(0.0, min(1.0, ((f.x - start[0]) * vx + (f.y - start[1]) * vy) / denominator)) if denominator else 1.0
    expected = start[2] + (target[2] - start[2]) * k
    if f.z < expected - 75:
        raise RuntimeError('Fell more than 75 cm below the authored route near %s at %s' % (name, xyz(f)))
    if distance <= 30:
        if not move.is_moving_on_ground():
            return False
        error = abs(f.z - target[2])
        row = {'id': name, 'expected_floor_cm': list(target), 'actual_foot_cm': xyz(f), 'floor_error_cm': round(error, 1), 'passed': error <= 30,
               'segment_seconds': round(t - seg['t0'], 2), 'floor_below': floor_under_foot()}
        REPORT['waypoints'].append(row)
        write()
        if not row['passed']:
            raise RuntimeError('Floor mismatch at %s: %s' % (name, row))
        return True
    if distance < seg['progress'] - 6:
        seg.update(progress=distance, progress_t=t)
    if t - seg['progress_t'] > 3.0:
        raise RuntimeError('Walking stalled before %s with %.0f cm remaining at %s' % (name, distance, xyz(f)))
    if t - seg['t0'] > 40:
        raise RuntimeError('Segment timeout before ' + name)
    pawn.add_movement_input(unreal.Vector(dx / distance, dy / distance, 0), min(1.0, distance / 80), False)
    return False


def scenario():
    S['step'] = 'load map'
    if not LEVEL.load_level(MAP):
        raise RuntimeError('Cannot load ' + MAP)
    cls = unreal.load_class(None, MANAGER_PATH)
    editor_manager = unreal.GameplayStatics.get_all_actors_of_class(EDITOR.get_editor_world(), cls)[0]
    S['override'] = (editor_manager, {name: editor_manager.get_editor_property(name) for name in ['ReleaseProfileSlot', 'ReleaseSavePrefix']})
    editor_manager.set_editor_property('ReleaseProfileSlot', PROFILE_SLOT)
    editor_manager.set_editor_property('ReleaseSavePrefix', CAMPAIGN_PREFIX)
    S['menu_entry'] = 'new'
    LEVEL.editor_request_begin_play()
    yield until(ready, 'release menu New Game into a fresh isolated QA campaign', 180)
    for command in ['t.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0', 'DisableAllScreenMessages']:
        unreal.SystemLibrary.execute_console_command(S['world'], command)
    yield wait(.5)
    check('Real menu New Game started a session', bool(prop('ReleaseSessionStarted')) and not bool(prop('ReleaseMenuActive')))
    if bool(prop('IntroActive')):
        action('SkipRecollections')
        yield wait(.3)
    if int(prop('Mode')) != 0:
        action('CloseModal')
        yield wait(.1)
    pawn = S['pawn']
    move = pawn.get_component_by_class(unreal.CharacterMovementComponent)
    capsule = pawn.get_component_by_class(unreal.CapsuleComponent)
    vc.require(move is not None and capsule is not None, 'Player pawn has no character movement')
    S.update(movement=move, half_height=float(capsule.get_scaled_capsule_half_height()))
    REPORT['character'] = {'class': pawn.get_class().get_path_name(), 'capsule_half_height_cm': S['half_height'],
                           'max_step_height_cm': float(move.get_editor_property('max_step_height')), 'max_walk_speed': float(move.get_editor_property('max_walk_speed'))}
    REPORT['natural_spawn_foot_cm'] = xyz(foot())
    S['step'] = 'era'
    snap = era_snapshot('after New Game (present)')
    check('New Game shows the present Verdant city and hides the past one',
          int(prop('EraIndex')) == 0 and snap['verdant_present']['hidden'] == 0 and snap['verdant_past']['shown'] == 0
          and snap['lights'].get('Verdant_Sun_Present') == 'active' and snap['lights'].get('Verdant_Sun_Past') == 'hidden', snap)
    check('Old development scenery stays hidden and non-colliding in play',
          all(v['hidden'] and not v['collision'] for v in snap['dev_scenery'].values()), snap['dev_scenery'])
    if ERA == 'Past':
        FIXTURE.call_method('SetEra', args=(S['manager'], 1))
        action('ApplyWorldState')
        action('RefreshUI')
        yield wait(.2)
        snap = era_snapshot('after EraIndex=1 fixture + ApplyWorldState')
        check('ApplyWorldState with EraIndex=1 shows the past Verdant city and hides the present one',
              int(prop('EraIndex')) == 1 and snap['verdant_past']['hidden'] == 0 and snap['verdant_present']['shown'] == 0
              and snap['lights'].get('Verdant_Sun_Past') == 'active' and snap['lights'].get('Verdant_Sun_Present') == 'hidden', snap)
        desired = unreal.Vector(*PLACEMENT)
        S['movement'].stop_movement_immediately()
        pawn.set_actor_location(desired, False, True)
        REPORT['initial_placement'] = {'to_capsule_center_cm': xyz(desired), 'counts_as_walking': False, 'reason': 'past checkpoint of the story'}
        yield wait(.8)
    S['step'] = 'walk'
    yield wait(.4)
    if ERA == 'Present':
        yield screenshot('home_room', SHOTS['home_room'])
    for name, target in ROUTE:
        yield walk_to(name, target)
        if name in SHOTS and name != 'home_room':
            yield screenshot(name, SHOTS[name])
    errors = [w['floor_error_cm'] for w in REPORT['waypoints']]
    REPORT['largest_floor_error_cm'] = max(errors) if errors else None
    REPORT['floor_actors'] = sorted({(w['floor_below'] or {}).get('actor') or 'none' for w in REPORT['waypoints']})
    REPORT['complete_route_walked'] = len(REPORT['waypoints']) == len(ROUTE) and all(w['passed'] for w in REPORT['waypoints'])
    check('Complete route walked with native movement input', REPORT['complete_route_walked'], {'waypoints': len(REPORT['waypoints']), 'route': len(ROUTE)})
    REPORT['passed'] = True


def finish(error=None):
    global closing
    if closing:
        return
    closing = True
    if error:
        REPORT['error'] = error
    if LEVEL.is_in_play_in_editor():
        LEVEL.editor_request_end_play()
    else:
        complete_finish()


def complete_finish():
    try:
        pair = S.get('override')
        if pair:
            for name, value in pair[1].items():
                pair[0].set_editor_property(name, value)
            S['override'] = None
    except Exception:
        REPORT['cleanup_error'] = traceback.format_exc()
    REPORT['protected_after'] = {str(p): sha(p) for p in PROTECTED}
    REPORT['protected_unchanged'] = REPORT['protected_after'] == REPORT['protected_before']
    REPORT['success'] = ('error' not in REPORT and REPORT.get('passed', False) and all(c['passed'] for c in REPORT['checks'])
                         and REPORT['protected_unchanged'] and 'cleanup_error' not in REPORT)
    write()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    vc.log('story walk', json.dumps({'era': ERA, 'success': REPORT['success'], 'waypoints': len(REPORT['waypoints']),
                                     'largest_floor_error_cm': REPORT.get('largest_floor_error_cm'), 'error': (REPORT.get('error') or '')[-300:]}))
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.quit_editor()


runner = scenario()
wall_start = time.monotonic()


def tick(delta):
    global pending, deadline
    try:
        if closing:
            if not LEVEL.is_in_play_in_editor():
                complete_finish()
            return
        if time.monotonic() - wall_start > 600:
            raise RuntimeError('Wall-time watchdog')
        now = time.monotonic()
        if pending:
            if 'seconds' in pending:
                if now < deadline:
                    return
            elif 'predicate' in pending:
                if not pending['predicate']():
                    if now > deadline:
                        raise TimeoutError(pending['description'])
                    return
            elif 'walk' in pending:
                if not walk_step(pending['walk']):
                    return
            elif 'screenshot' in pending:
                path = pending['screenshot']
                if not path.exists() or path.stat().st_size < 15000:
                    if now > deadline:
                        raise TimeoutError(pending['description'])
                    return
                REPORT['screenshots'].append({'label': pending['label'], 'file': str(path), 'foot_cm': xyz(foot())})
                write()
            pending = None
        pending = next(runner)
        deadline = now + pending.get('seconds', pending.get('timeout', 60))
        write()
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
