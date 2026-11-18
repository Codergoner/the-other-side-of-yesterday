"""Queued, read-only desktop PIE probe of ordinary interior-stair access.

Start with a dedicated short -UserDir and -ReleaseUpstairsProbe. A fresh native
HUD New Game supplies the initial checkpoint; only AddMovementInput moves the
character afterwards. No setup teleport, story-flag setter, camera steering,
collision change, asset save or upstairs closure is performed by this fixture.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import time
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
DEV = ROOT.parent
MAP = '/Game/Quest/Maps/Verdant_Desktop'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
PROFILE = 'YRU_' + STAMP
PREFIX = PROFILE + '_'
PLAN_FILE = ROOT / 'ContentData/release_upstairs_probe_plan.json'
OUTPUT = ROOT / 'validation/release_upstairs_walk' / STAMP
REPORT_FILE = ROOT / 'release_upstairs_walk_probe.json'
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
S = {'phase': 'preflight', 'start': time.monotonic(), 'phase_wall': time.monotonic(),
     'index': 0, 'world': None, 'pawn': None, 'manager': None, 'pc': None,
     'override': None, 'closing': False, 'callback': None, 'last_write': 0,
     'last_sample': -100, 'fall_since': None}
REPORT = {'success': False, 'run': STAMP, 'map': MAP, 'checks': [],
          'scope': 'Native editor PIE, ordinary walking from a fresh menu New Game to the interior stair, upper room, balcony and return to the ground-floor gate.',
          'input_method': 'Native HUD New Game / SkipRecollections, then Pawn.AddMovementInput(direction, scale, force=False).',
          'route_teleports': 0, 'initial_setup_relocation': False,
          'collision_changed': False, 'movement_mode_forced': False,
          'direct_story_flag_writes': False, 'closure_authored': False,
          'physical_keyboard_tested': False, 'packaged_playtested': False,
          'headset_tested': False, 'closure_needed_under_brief': None,
          'qa_profile': PROFILE, 'qa_campaign_prefix': PREFIX,
          'waypoints': [], 'samples': [], 'actions': []}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def xyz(vector):
    return [round(float(vector.x), 3), round(float(vector.y), 3), round(float(vector.z), 3)]


def write():
    REPORT['active_phase'] = S['phase']
    REPORT['active_waypoint'] = ROUTE[min(S['index'], len(ROUTE) - 1)]['id'] if ROUTE else None
    OUTPUT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(REPORT, indent=2, default=str) + '\n'
    REPORT_FILE.write_text(text, encoding='utf-8')
    (OUTPUT / 'report.json').write_text(text, encoding='utf-8')
    S['last_write'] = time.monotonic()


def check(name, passed, details=None):
    REPORT['checks'].append({'name': name, 'passed': bool(passed), 'details': details})
    write()
    if not passed:
        raise RuntimeError(name + ': ' + str(details))


def phase(name, game_time=0):
    S.update(phase=name, phase_wall=time.monotonic(), phase_game=game_time)
    write()


def protected_files():
    paths = set((ROOT / 'Content').rglob('*.uasset')) | set((ROOT / 'Content').rglob('*.umap'))
    paths.update((ROOT / 'Config').rglob('*.ini'))
    paths.update(ROOT.glob('*.uproject'))
    for directory in SAVE_DIRECTORIES:
        if directory.exists():
            paths.update(p for p in directory.rglob('*') if p.is_file())
    return {str(p): sha(p) for p in sorted(paths, key=str)}


def manager_for(world):
    actors = unreal.GameplayStatics.get_all_actors_with_tag(world, 'Opening.Manager')
    if len(actors) != 1:
        raise RuntimeError('Expected exactly one Opening.Manager, got ' + str(len(actors)))
    return actors[0]


def prop(name):
    return S['manager'].get_editor_property(name)


def action(name):
    S['manager'].call_method(name, args=())
    REPORT['actions'].append({'action': name, 'wall_seconds': round(time.monotonic() - S['start'], 3)})


def restore_editor_override():
    if S['override']:
        actor, values = S['override']
        for key, value in values.items():
            actor.set_editor_property(key, value)
        S['override'] = None


def footpoint():
    location = S['pawn'].get_actor_location()
    return unreal.Vector(location.x, location.y, location.z - S['half_height'])


def sample(game_time, target=None):
    foot, move = footpoint(), S['move']
    row = {'game_seconds': round(game_time, 3), 'foot_cm': xyz(foot),
           'velocity_cm_s': xyz(S['pawn'].get_velocity()),
           'grounded': bool(move.is_moving_on_ground()), 'falling': bool(move.is_falling()),
           'movement_mode': str(move.get_editor_property('movement_mode')),
           'story_mode': int(prop('Mode'))}
    if target:
        row['distance_to_waypoint_cm'] = round(math.hypot(target[0] - foot.x, target[1] - foot.y), 3)
    ignored = [S['pawn']] + list(unreal.GameplayStatics.get_all_actors_with_tag(S['world'], 'Quest.NavigationNode'))
    hit = unreal.SystemLibrary.line_trace_single(S['world'], foot + unreal.Vector(0, 0, 25),
        foot - unreal.Vector(0, 0, 180), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False,
        ignored, unreal.DrawDebugTrace.NONE, True)
    values = hit.to_tuple() if hit is not None else None
    row['floor_visibility_trace'] = {'blocking': bool(values[0]), 'impact_cm': xyz(values[5]),
        'actor': values[9].get_path_name() if values[9] else None} if values else {'blocking': False}
    return row


def request_finish(error=None):
    if S['closing']:
        return
    if error:
        REPORT['error'] = error
    S.update(closing=True, close_wall=time.monotonic())
    phase('ending_pie')
    if LEVEL.is_in_play_in_editor():
        LEVEL.editor_request_end_play()


def finish():
    try:
        restore_editor_override()
        if not LEVEL.load_level(MAP):
            raise RuntimeError('Could not discard transient PIE/profile changes by reloading the saved desktop map')
    except Exception:
        REPORT['cleanup_error'] = traceback.format_exc()
    after = protected_files()
    REPORT['protected_digests_after'] = after
    changed = [p for p, digest in PROTECTED.items() if after.get(p) != digest]
    REPORT['protected_files_unchanged'] = not changed
    REPORT['protected_files_changed'] = changed
    additions = [p for p in after if p not in PROTECTED]
    allowed = []
    unexpected = []
    for value in additions:
        path = Path(value)
        if path.is_relative_to(SAVED / 'SaveGames') and path.name.startswith(PROFILE):
            allowed.append(value)
        else:
            unexpected.append(value)
    REPORT['isolated_qa_save_files'] = allowed
    REPORT['unexpected_native_or_save_files'] = unexpected
    REPORT['ordinary_upper_landing_reached'] = any(p['id'] == 'upper_landing' and p['passed'] for p in REPORT['waypoints'])
    REPORT['ordinary_upper_room_reached'] = any(p['id'] == 'upper_hall' and p['passed'] for p in REPORT['waypoints'])
    REPORT['complete_route_walked'] = len(REPORT['waypoints']) == len(ROUTE) and all(p['passed'] for p in REPORT['waypoints'])
    if REPORT['ordinary_upper_landing_reached']:
        REPORT['closure_needed_under_brief'] = True
        REPORT['finding'] = 'The upstairs landing was reached by ordinary native walking; the brief requires it to be closed.'
    else:
        REPORT['finding'] = 'Upstairs access remains unresolved. A failed route is not evidence of an authored visible upstairs closure.'
    REPORT['success'] = (REPORT['complete_route_walked'] and not changed and not unexpected
                         and not any(key in REPORT for key in ['error', 'cleanup_error', 'shutdown_error']))
    REPORT['wall_seconds'] = round(time.monotonic() - S['start'], 3)
    S['phase'] = 'complete'
    write()
    if S['callback'] is not None:
        unreal.unregister_slate_post_tick_callback(S['callback'])
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.log('RELEASE_UPSTAIRS_WALK_PROBE ' + json.dumps({k: REPORT[k] for k in
        ['success', 'ordinary_upper_landing_reached', 'complete_route_walked', 'closure_needed_under_brief']}))
    unreal.SystemLibrary.quit_editor()


def begin_segment(game_time):
    foot = footpoint()
    target = ROUTE[S['index']]['floor_cm']
    S.update(segment_game=game_time, progress_game=game_time,
             progress_distance=math.hypot(target[0] - foot.x, target[1] - foot.y),
             segment_start=xyz(foot), fall_since=None)


def walk(game_time):
    foot, move = footpoint(), S['move']
    waypoint = ROUTE[S['index']]
    target = waypoint['floor_cm']
    dx, dy = target[0] - foot.x, target[1] - foot.y
    distance = math.hypot(dx, dy)
    if int(prop('Mode')) != 0 or prop('ReleaseMenuActive') or prop('IntroActive'):
        raise RuntimeError('Ordinary input is blocked by native menu/story state; the fixture does not bypass it')
    if S['pc'].is_move_input_ignored():
        raise RuntimeError('Native controller is ignoring movement input; force=False is preserved')
    if game_time - S['last_sample'] >= .25:
        REPORT['samples'].append(sample(game_time, target))
        S['last_sample'] = game_time
    if move.is_falling():
        if S['fall_since'] is None:
            S['fall_since'] = game_time
        if game_time - S['fall_since'] > 1:
            raise RuntimeError('Native capsule remained falling for over one second at ' + waypoint['id'])
    else:
        S['fall_since'] = None
    previous = S['segment_start']
    vx, vy = target[0] - previous[0], target[1] - previous[1]
    length2 = vx * vx + vy * vy
    along = max(0, min(1, ((foot.x - previous[0]) * vx + (foot.y - previous[1]) * vy) / length2)) if length2 else 1
    expected_z = previous[2] + (target[2] - previous[2]) * along
    if foot.z < expected_z - 75:
        raise RuntimeError('Capsule fell more than 75 cm below the authored route at ' + waypoint['id'])
    if distance <= 14:
        if not move.is_moving_on_ground():
            return
        z_error = abs(foot.z - target[2])
        row = {'id': waypoint['id'], 'phase': waypoint['phase'], 'expected_floor_cm': target,
               'actual_foot_cm': xyz(foot), 'xy_error_cm': round(distance, 3),
               'floor_error_cm': round(z_error, 3), 'grounded': True,
               'segment_game_seconds': round(game_time - S['segment_game'], 3), 'passed': z_error <= 30}
        REPORT['waypoints'].append(row)
        write()
        if not row['passed']:
            raise RuntimeError('Reached the wrong floor at ' + waypoint['id'] + ': ' + str(row))
        S['index'] += 1
        if S['index'] == len(ROUTE):
            request_finish()
        else:
            begin_segment(game_time)
        return
    if distance < S['progress_distance'] - 7:
        S.update(progress_distance=distance, progress_game=game_time)
    if game_time - S['progress_game'] > 2.5 or game_time - S['segment_game'] > 22:
        REPORT['stall_diagnostic'] = sample(game_time, target)
        REPORT['stall_diagnostic']['interpretation'] = 'Native walking stopped; Visibility floor tracing is diagnostic, not a Pawn collision proof.'
        raise RuntimeError('Native collision/input stall at ' + waypoint['id'] + ', remaining cm=' + str(round(distance, 2)))
    S['pawn'].add_movement_input(unreal.Vector(dx / distance, dy / distance, 0), min(1, distance / 90), False)
    if time.monotonic() - S['last_write'] > .75:
        write()


def inspect_stairs(world):
    result = []
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor):
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        mesh = comp.get_editor_property('static_mesh') if comp else None
        if mesh and mesh.get_name() == 'SM_Home_Staircase':
            result.append({'actor': actor.get_path_name(), 'mesh': mesh.get_path_name(),
                'actor_collision_enabled': bool(actor.get_actor_enable_collision()),
                'component_collision': str(comp.get_collision_enabled()),
                'pawn_response': str(comp.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)),
                'location_cm': xyz(actor.get_actor_location()),
                'rotation': str(actor.get_actor_rotation()), 'scale': xyz(actor.get_actor_scale3d())})
    check('Exactly one native home staircase is present', len(result) == 1, result)
    REPORT['native_staircase'] = result[0]


def tick(delta):
    try:
        if S['closing']:
            if not LEVEL.is_in_play_in_editor():
                finish()
            elif time.monotonic() - S['close_wall'] > 20:
                raise RuntimeError('PIE shutdown timed out')
            return
        if time.monotonic() - S['start'] > 300:
            raise RuntimeError('Upstairs walking fixture wall-time watchdog')
        if S['phase'] == 'waiting_for_menu' and time.monotonic() - S['phase_wall'] > 90:
            raise RuntimeError('Native release menu did not become ready')
        if S['phase'] == 'waiting_for_new_game' and time.monotonic() - S['phase_wall'] > 25:
            raise RuntimeError('Normal HUD New Game did not begin a session')
        if S['phase'] == 'load':
            check('Desktop map loads', LEVEL.load_level(MAP))
            edit = manager_for(EDITOR.get_editor_world())
            S['override'] = (edit, {key: edit.get_editor_property(key) for key in ['ReleaseProfileSlot', 'ReleaseSavePrefix']})
            edit.set_editor_property('ReleaseProfileSlot', PROFILE)
            edit.set_editor_property('ReleaseSavePrefix', PREFIX)
            LEVEL.editor_request_begin_play()
            phase('waiting_for_menu')
            return
        world = EDITOR.get_game_world()
        if S['phase'] == 'waiting_for_menu':
            if not world:
                return
            manager = manager_for(world)
            pawn = unreal.GameplayStatics.get_player_character(world, 0)
            pc = unreal.GameplayStatics.get_player_controller(world, 0)
            if not (pawn and pc and manager.get_editor_property('ReleaseBooted') and manager.get_editor_property('ReleaseMenuActive')):
                return
            S.update(world=world, manager=manager, pawn=pawn, pc=pc)
            restore_editor_override()
            for command in ['t.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0']:
                unreal.SystemLibrary.execute_console_command(world, command)
            check('Fresh QA profile is isolated', str(prop('ReleaseProfileSlot')) == PROFILE and not prop('ReleaseContinueAvailable'))
            check('Native title row is New Game', str(prop('ReleaseRow0')) == 'New Game', str(prop('ReleaseRow0')))
            inspect_stairs(world)
            pc.get_hud().call_method('ReceiveHitBoxClick', args=(unreal.Name('ReleaseRow0'),))
            REPORT['actions'].append({'action': 'HUD.ReceiveHitBoxClick(ReleaseRow0)', 'meaning': 'Normal New Game'})
            phase('waiting_for_new_game')
            return
        game_time = unreal.GameplayStatics.get_time_seconds(world)
        if S['phase'] == 'waiting_for_new_game':
            if prop('ReleaseMenuActive') or not prop('ReleaseSessionStarted'):
                return
            campaign = str(prop('SaveSlot'))
            check('New Game chose only a new QA campaign', campaign.startswith(PREFIX) and len(campaign) > len(PREFIX), campaign)
            REPORT['qa_campaign'] = campaign
            check('Normal New Game created its isolated checkpoint', (SAVED / 'SaveGames' / (campaign + '.sav')).is_file())
            check('New Game is in the Present house', int(prop('EraIndex')) == 0 and not prop('HasDeparted'))
            if prop('IntroActive'):
                action('SkipRecollections')
            capsule = S['pawn'].get_component_by_class(unreal.CapsuleComponent)
            move = S['pawn'].get_component_by_class(unreal.CharacterMovementComponent)
            check('Native character has capsule and CharacterMovement', bool(capsule and move))
            S.update(move=move, half_height=float(capsule.get_scaled_capsule_half_height()))
            REPORT['native_character'] = {'class': S['pawn'].get_class().get_path_name(),
                'capsule_radius_cm': float(capsule.get_scaled_capsule_radius()),
                'capsule_half_height_cm': S['half_height'],
                'max_step_height_cm': float(move.get_editor_property('max_step_height')),
                'walkable_floor_angle_degrees': float(move.get_walkable_floor_angle()),
                'jump_z_velocity_cm_s': float(move.get_editor_property('jump_z_velocity'))}
            phase('settling_new_game', game_time)
            return
        if S['phase'] == 'settling_new_game':
            if game_time - S['phase_game'] < .8:
                return
            check('Normal intro skip released movement', not prop('IntroActive') and int(prop('Mode')) == 0 and not S['pc'].is_move_input_ignored())
            foot, target = footpoint(), ROUTE[0]['floor_cm']
            REPORT['natural_fresh_spawn_foot_cm'] = xyz(foot)
            check('Ordinary New Game starts at the home; no setup placement', math.hypot(foot.x - target[0], foot.y - target[1]) <= 80 and abs(foot.z - target[2]) <= 45, xyz(foot))
            begin_segment(game_time)
            phase('walking', game_time)
            return
        if S['phase'] == 'walking':
            walk(game_time)
    except Exception:
        if S['closing']:
            REPORT['shutdown_error'] = traceback.format_exc()
            finish()
        else:
            request_finish(traceback.format_exc())


ROUTE = []
PROTECTED = {}
SAVED = Path(unreal.Paths.project_saved_dir()).resolve()
SAVE_DIRECTORIES = [SAVED / 'SaveGames', ROOT / 'Saved/SaveGames',
    DEV.parent / 'Quest_20261025/game_unreal/Saved/SaveGames',
    DEV.parent / 'Brief_20261025/game_unreal/Saved/SaveGames',
    DEV.parent.parent / 'game_unreal/Saved/SaveGames',
    Path.home() / 'AppData/Local/YesterdayHarbor/Saved/SaveGames']


def main():
    if DEV.name != 'Release_20261026':
        raise RuntimeError('This probe refuses protected project copies')
    baseline = json.loads((DEV / 'release_baseline_manifest.json').read_text(encoding='utf-8'))
    if Path(baseline['target']).resolve() != DEV:
        raise RuntimeError('Release baseline does not match the current project')
    if '-run=' in unreal.SystemLibrary.get_command_line().lower() or LEVEL is None or EDITOR is None:
        raise RuntimeError('Use a full editor Python entry point, not a commandlet')
    if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseUpstairsProbe'):
        raise RuntimeError('Root queue and -ReleaseUpstairsProbe are required')
    # Leave room for the native SaveGuard .bak.tmp_GUID transaction suffix.
    if SAVED == (ROOT / 'Saved').resolve() or len(str(SAVED / 'SaveGames' / (PREFIX + '0' * 36 + '.sav'))) >= 200:
        raise RuntimeError('A dedicated short -UserDir is required; no player save/config directory is used')
    plan = json.loads(PLAN_FILE.read_text(encoding='utf-8'))
    if plan['map'] != MAP or plan['status'] != 'source_prepared_native_probe_pending':
        raise RuntimeError('Unexpected upstairs probe plan')
    for relative, digest in plan['generator_source_sha256'].items():
        if sha(DEV / relative) != digest:
            raise RuntimeError('House source changed; review the route first: ' + relative)
    ROUTE.extend(plan['ordinary_walk']['route'])
    PROTECTED.update(protected_files())
    if any(p.name.startswith(PROFILE) for p in (SAVED / 'SaveGames').glob('*')):
        raise RuntimeError('Refusing to reuse a QA profile')
    REPORT['plan_sha256'] = sha(PLAN_FILE)
    REPORT['fixture_sha256'] = sha(Path(__file__))
    REPORT['project_saved_directory'] = str(SAVED)
    REPORT['authored_route'] = ROUTE
    REPORT['protected_digests_before'] = PROTECTED
    REPORT['source_geometry'] = plan['source_geometry']
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
    phase('load')
    S['callback'] = unreal.register_slate_post_tick_callback(tick)


try:
    main()
except Exception:
    REPORT['error'] = traceback.format_exc()
    REPORT['finding'] = 'Preflight failed; no upstairs-access conclusion is available.'
    write()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.quit_editor()
