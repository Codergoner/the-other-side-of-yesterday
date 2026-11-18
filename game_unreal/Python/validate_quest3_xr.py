"""Async full-editor PIE regression of the Quest 3 XR adapter in the Release copy, without an HMD.

Run through verdant/run_unreal.ps1 -Script validate_quest3_xr.py -UserDir <fresh short dir> -Flags @('-Quest3XRQA').
It loads the story map with a transient world-settings game-mode fixture (BP_QuestGameMode; never saved), enters
through the real release front end on an isolated profile, and exercises the adapter with native callable actions
and controlled camera fixtures: title menu on the world panel, New Game, landings, pause panel and guarded save,
main menu from play and resume, room-scale and occlusion, snap pivot, gaze targeting of the photograph, dialogue
choice rows, teleport, end screen, restart with real Continue. Not physical controller input, not an APK, not
headset comfort or frame rate. Report: game_unreal/quest3_xr_runtime_validation.json (the Quest 3 build gate).
"""
from pathlib import Path
import datetime
import hashlib
import json
import math
import time
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Release_20261026', 'Quest 3 XR regression runs only in the Release copy'
if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3XRQA'):
    raise RuntimeError('A queued -Quest3XRQA run with a dedicated -UserDir is required')
SAVED = Path(unreal.Paths.project_saved_dir()).resolve()
if SAVED == (ROOT / 'Saved').resolve():
    raise RuntimeError('Use a dedicated -UserDir; the normal project save directory is protected')
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
try:
    unreal.get_default_object(unreal.EditorPerformanceSettings).set_editor_property('throttle_cpu_when_not_foreground', False)
except Exception:
    pass
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
MAP = '/Game/Quest/Maps/Verdant_Desktop'
MANAGER_CLASS = '/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C'
CHAR_CLASS = '/Game/Quest/XR/BP_QuestCharacter.BP_QuestCharacter_C'
GM_CLASS = '/Game/Quest/XR/BP_QuestGameMode.BP_QuestGameMode_C'
PROFILE_SLOT = 'YQ3XR_' + STAMP[:15] + '_Profile'
SAVE_PREFIX = 'YQ3XR_' + STAMP[:15] + '_'
REPORT_PATH = ROOT / 'quest3_xr_runtime_validation.json'
SCREENS = ROOT / 'validation/quest3' / (STAMP + '_xr')
SCREENS.mkdir(parents=True, exist_ok=True)
SAVE_DIR = SAVED / 'SaveGames'
REPORT = {'success': False, 'run': STAMP, 'map': MAP, 'profile_slot': PROFILE_SLOT, 'save_prefix': SAVE_PREFIX,
          'save_directory': str(SAVE_DIR), 'checks': [], 'screenshots': [],
          'headset_tested': False, 'physical_controller_input_tested': False, 'apk_tested': False,
          'performance_benchmarked': False, 'full_story_acceptance': False,
          'scope': 'Native Quest 3 Blueprint adapter on the Release story map: real release front end on an isolated profile, controlled desktop camera and pose fixtures, real scene rays, guarded SaveGame; transient game-mode fixture never saved'}
S = {'world': None, 'pawn': None, 'manager': None, 'controller': None, 'override': None, 'game_mode': None,
     'step': 'startup', 'original_map': None, 'slot': None}
pending = None
deadline = 0
handle = None
closing = False
ticking = False


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


PROTECTED_ASSETS = list((ROOT / 'Config').glob('*.ini')) + list((ROOT / 'Config/Android').glob('*.ini')) + list((ROOT / 'Content/Quest/Maps').glob('*.umap'))
PROTECTED_ASSETS += [ROOT / ('Content/' + p) for p in [
    'Opening/Blueprints/BP_OpeningActions.uasset', 'Opening/Blueprints/BP_OpeningHUD.uasset',
    'Opening/Blueprints/BP_OpeningSave.uasset', 'Release/Blueprints/BP_ReleaseProfile.uasset',
    'Quest/XR/BP_QuestCharacter.uasset', 'Quest/XR/BP_QuestGameMode.uasset']]
protected_saves = []
for folder in [ROOT / 'Saved/SaveGames', ROOT.parent.parent / 'Quest_20261025/game_unreal/Saved/SaveGames',
               ROOT.parent.parent / 'Brief_20261025/game_unreal/Saved/SaveGames',
               ROOT.parent.parent.parent / 'game_unreal/Saved/SaveGames',
               Path.home() / 'AppData/Local/YesterdayHarbor/Saved/SaveGames']:
    if folder.exists():
        protected_saves.extend(p for p in folder.iterdir() if p.is_file() and '.sav' in p.name)
REPORT['protected_saves_before'] = {str(p): digest(p) for p in protected_saves}
REPORT['protected_assets_before'] = {str(p): digest(p) for p in PROTECTED_ASSETS}


def xyz(v):
    return [round(v.x, 3), round(v.y, 3), round(v.z, 3)]


def distance(a, b):
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def write():
    REPORT['active_step'] = S['step']
    rendered = json.dumps(REPORT, indent=2, default=str)
    REPORT_PATH.write_text(rendered, encoding='utf-8')
    (SCREENS / 'runtime_validation.json').write_text(rendered, encoding='utf-8')


def check(name, passed, details=None):
    REPORT['checks'].append({'name': name, 'passed': bool(passed), 'details': details})
    write()
    if not passed:
        raise AssertionError(name + ': ' + str(details))


def wait(seconds=.15):
    return {'seconds': seconds}


def until(predicate, name, timeout=25):
    return {'predicate': predicate, 'name': name, 'timeout': timeout}


def screenshot(name):
    path = SCREENS / (name + '.png')
    unreal.AutomationLibrary.take_high_res_screenshot(1400, 900, str(path))
    REPORT['screenshots'].append(str(path))
    return until(lambda: path.exists() and path.stat().st_size > 15000, 'native PIE viewport screenshot ' + name, timeout=30)


def manager(world):
    klass = unreal.load_class(None, MANAGER_CLASS)
    found = unreal.GameplayStatics.get_all_actors_of_class(world, klass)
    if len(found) != 1:
        raise RuntimeError('Expected one story manager: ' + str(len(found)))
    return found[0]


def prop(name):
    return S['manager'].get_editor_property(name)


def action(name, *args):
    return S['manager'].call_method(name, args=tuple(args))


def qa(name, *args):
    return S['pawn'].call_method(name, args=tuple(args))


def comp(name):
    return S['pawn'].get_editor_property(name)


def panel_text():
    qa('QuestPanelFrame')
    return str(S['pawn'].get_editor_property('QuestCachedQuestPanelText'))


def panel_title():
    qa('QuestPanelFrame')
    return str(S['pawn'].get_editor_property('QuestCachedQuestPanelTitle'))


def ready():
    world = EDITOR.get_game_world()
    if world is None:
        return False
    pawn = unreal.GameplayStatics.get_player_character(world, 0)
    if pawn is None or pawn.get_controller() is None:
        return False
    if pawn.get_class().get_path_name() != CHAR_CLASS:
        raise RuntimeError('Game-mode fixture did not spawn the Quest Character: ' + pawn.get_class().get_path_name())
    S.update(world=world, pawn=pawn, controller=pawn.get_controller(), manager=manager(world))
    try:
        quest_manager = pawn.get_editor_property('QuestManager')
    except Exception:
        return False
    return prop('Player') == pawn and quest_manager == S['manager'] and bool(prop('ReleaseBooted')) and bool(prop('ReleaseMenuActive'))


def aim_camera_at(point):
    camera = comp('QuestCamera')
    world_rotation = unreal.MathLibrary.find_look_at_rotation(camera.get_world_location(), point)
    root_rotation = S['pawn'].get_actor_rotation()
    camera.set_relative_rotation(unreal.Rotator(pitch=world_rotation.pitch - root_rotation.pitch,
                                 yaw=world_rotation.yaw - root_rotation.yaw, roll=0), False, True)


def tagged(tag):
    return unreal.GameplayStatics.get_all_actors_with_tag(S['world'], tag)


def floor_below(location):
    hit = unreal.SystemLibrary.line_trace_single(S['world'], location + unreal.Vector(0, 0, 60), location - unreal.Vector(0, 0, 250),
                                                 unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [S['pawn']], unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return (False, None, None)
    result = hit.to_tuple()
    # HitResult tuple: (bBlockingHit, bInitialOverlap, Time, Distance, Location, ImpactPoint, Normal, ImpactNormal,
    # PhysMat, HitActor, ...); the floor height is the hit location's z.
    return (bool(result[0]), float(result[4].z) if result[0] else None, str(result[9]) if result[0] else None)


def apply_fixture():
    """Transient XR game mode on the editor world's World Settings plus isolated release profile names."""
    world = EDITOR.get_editor_world()
    settings = world.get_world_settings()
    if S['game_mode'] is None:
        S['game_mode'] = (settings, settings.get_editor_property('default_game_mode'))
    settings.set_editor_property('default_game_mode', unreal.load_class(None, GM_CLASS))
    edit_manager = manager(world)
    if S['override'] is None:
        S['override'] = (edit_manager, {n: edit_manager.get_editor_property(n) for n in ['ReleaseProfileSlot', 'ReleaseSavePrefix']})
    edit_manager.set_editor_property('ReleaseProfileSlot', PROFILE_SLOT)
    edit_manager.set_editor_property('ReleaseSavePrefix', SAVE_PREFIX)


def restore_fixture():
    if S['override']:
        actor, values = S['override']
        for name, value in values.items():
            try:
                actor.set_editor_property(name, value)
            except Exception:
                REPORT.setdefault('cleanup_errors', []).append(traceback.format_exc())
        S['override'] = None
    if S['game_mode']:
        settings, previous = S['game_mode']
        try:
            settings.set_editor_property('default_game_mode', previous)
        except Exception:
            REPORT.setdefault('cleanup_errors', []).append(traceback.format_exc())
        S['game_mode'] = None


def begin():
    LEVEL.editor_request_begin_play()
    return until(ready, 'possessed Quest Character, booted release front end on the isolated profile')


def settle():
    for command in ['r.ScreenPercentage 100', 't.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0']:
        unreal.SystemLibrary.execute_console_command(S['world'], command)


def scenario():
    S['step'] = 'load the story map with the XR game-mode fixture'
    old_world = EDITOR.get_editor_world()
    if old_world:
        S['original_map'] = old_world.get_outer().get_name()
    check('Story map exists', unreal.EditorAssetLibrary.does_asset_exist(MAP))
    check('Story map loads', LEVEL.load_level(MAP))
    apply_fixture()
    yield begin()
    settle()
    yield wait(.4)

    S['step'] = 'XR pawn possession and release title menu on the world panel'
    pawn = S['pawn']
    check('Actual pawn is the Character-derived Quest adapter', pawn.get_class().get_path_name() == CHAR_CLASS)
    check('Headset-free harness is using the fallback camera', not pawn.get_editor_property('QuestXRActive'))
    check('Story manager references the possessed Character', prop('Player') == pawn)
    camera = comp('QuestCamera')
    origin = comp('VROrigin')
    eye = camera.get_world_location().z - origin.get_world_location().z
    check('Fallback eye is 160 cm above the floor-relative rig', abs(eye - 160) < .5, eye)
    check('Tracking camera is HMD-locked without control rotation', camera.get_editor_property('lock_to_hmd') and not camera.get_editor_property('use_pawn_control_rotation'))
    check('No joystick jog is configured', pawn.get_component_by_class(unreal.CharacterMovementComponent).get_editor_property('max_walk_speed') == 0)
    check('Release front end boots the XR player into the title menu', bool(prop('ReleaseMenuActive')) and int(prop('Mode')) == 8 and int(prop('ReleaseMenuScreen')) == 0,
          {'mode': int(prop('Mode')), 'screen': int(prop('ReleaseMenuScreen'))})
    check('Isolated profile has no valid save, Continue is disabled', not prop('ReleaseContinueAvailable'))
    text = panel_text()
    check('World panel renders the title rows with the selection marker', '> New Game' in text and 'Continue - no valid save' in text and 'Quit' in text, text)
    check('World panel title is the release title', panel_title() == 'Early Playable - Chapters I-II', panel_title())
    check('Menu panel is visible and the choice rows are hidden', comp('QuestPanelRoot').is_visible() and not comp('QuestChoice1').is_visible())
    yield wait(.2)
    yield screenshot('TitleMenu_Panel')
    action('ReleaseStepSelection', 1)
    text = panel_text()
    check('Stepping the selection moves the marker to Continue', '> Continue' in text and '> New Game' not in text, text)
    action('ReleaseStepSelection', -1)
    qa('QuestMenuBack')
    yield wait(.1)
    check('Back on the title screen without a session stays on the title screen', bool(prop('ReleaseMenuActive')) and int(prop('ReleaseMenuScreen')) == 0)
    action('ReleaseSelect', 0, True)
    yield until(lambda: bool(prop('ReleaseSessionStarted')), 'real New Game started a session', 10)
    yield wait(.3)
    if bool(prop('IntroActive')):
        action('SkipRecollections')
        yield wait(.2)
    S['slot'] = str(prop('SaveSlot'))
    check('New Game selects an isolated campaign slot and enters exploration', S['slot'].startswith(SAVE_PREFIX) and int(prop('Mode')) == 0 and not prop('ReleaseMenuActive'),
          {'slot': S['slot'], 'mode': int(prop('Mode'))})

    S['step'] = 'teleport landings shown at runtime and grounded on the merged city'
    all_landings = list(tagged('Quest.Teleport'))
    check('Authored landings exist on the story map', len(all_landings) >= 10, len(all_landings))
    rows = []
    worst = 0.0
    excluded = []
    for landing in all_landings:
        loc = landing.get_actor_location()
        hit, z, actor = floor_below(loc)
        error = abs(z - loc.z) if hit else None
        shown = not bool(landing.get_editor_property('hidden'))
        colliding = bool(landing.get_actor_enable_collision())
        rows.append({'landing': landing.get_actor_label(), 'location': xyz(loc), 'floor_hit': hit, 'floor_z': z, 'floor_actor': actor, 'error_cm': error,
                     'shown': shown, 'colliding': colliding})
        if shown:
            worst = max(worst, error if error is not None else 999)
        else:
            excluded.append({'landing': landing.get_actor_label(), 'floor_actor': actor, 'error_cm': error, 'colliding': colliding})
    REPORT['landings'] = rows
    REPORT['landings_excluded_at_runtime'] = excluded
    landings = [a for a in all_landings if not bool(a.get_editor_property('hidden'))]
    check('XR pawn shows the landings that stand on free floor (at least 12 of them)', len(landings) >= 12, {'landings': len(all_landings), 'shown': len(landings), 'excluded': excluded})
    check('Every shown landing has a floor within 8 cm on the merged Verdant ground', worst <= 8.0, {'worst_cm': worst})
    check('A landing swallowed by merged geometry is hidden and cannot be selected', all(not e['colliding'] for e in excluded), excluded)

    S['step'] = 'world panel pause and guarded save'
    action('OpenPause')
    qa('QuestPanelFrame')
    yield wait(.15)
    panel = comp('QuestPanelRoot')
    before = panel.get_world_location()
    before_rot = panel.get_world_rotation()
    check('Pause does not pause XR update', not unreal.GameplayStatics.is_game_paused(S['world']))
    check('Pause does not ignore physical head look', not S['controller'].is_look_input_ignored())
    check('Panel uses absolute world location and rotation', panel.get_editor_property('absolute_location') and panel.get_editor_property('absolute_rotation'))
    panel_distance = distance(before, camera.get_world_location())
    check('Panel is placed at a comfortable authored distance (180 cm, pulled in only for line-of-sight clearance)', 85 <= panel_distance <= 195,
          {'panel': xyz(before), 'eye': xyz(camera.get_world_location()), 'distance_cm': round(panel_distance, 1), 'authored_distance': float(pawn.get_editor_property('QuestPanelDistance'))})
    sight = unreal.SystemLibrary.line_trace_single(S['world'], camera.get_world_location(), before, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [pawn], unreal.DrawDebugTrace.NONE, True)
    sight_hit = sight.to_tuple() if sight is not None else None  # None means nothing was hit: clear line of sight
    check('Panel centre has a clear line of sight from the eye', sight_hit is None or not sight_hit[0], {'blocking_actor': str(sight_hit[9]) if sight_hit and sight_hit[0] else None})
    r = camera.get_editor_property('relative_rotation')
    saved_rotation = unreal.Rotator(pitch=r.pitch, yaw=r.yaw, roll=r.roll)
    camera.set_relative_rotation(unreal.Rotator(pitch=0, yaw=25, roll=0), False, True)
    qa('QuestPanelFrame')
    check('Turning the preview head leaves the modal anchored', distance(before, panel.get_world_location()) < .1 and abs(before_rot.yaw - panel.get_world_rotation().yaw) < .1)
    camera.set_relative_rotation(saved_rotation, False, True)
    qa('QuestCycleChoice')
    qa('QuestPanelFrame')
    check('Pause selection feedback marks the Save row', str(comp('QuestChoiceText2').get_editor_property('text')).startswith('> Save committed progress'))
    aim_camera_at(comp('QuestChoice2').get_world_location())
    qa('QuestPointerTrace')
    yield screenshot('PausePanel_SaveSelected')
    qa('QuestPrimary')
    yield wait(.25)
    save_file = SAVE_DIR / (S['slot'] + '.sav')
    check('Pause adapter reaches the guarded committed save', bool(prop('SaveSucceeded')) and save_file.exists() and save_file.read_bytes()[:8] == b'YDAYSG01',
          {'file': str(save_file), 'bytes': save_file.stat().st_size if save_file.exists() else None})
    REPORT['save_file'] = {'path': str(save_file), 'bytes': save_file.stat().st_size, 'sha256': digest(save_file)}
    camera.set_relative_rotation(saved_rotation, False, True)
    action('CloseModal')
    yield wait(.1)

    S['step'] = 'main menu from play (menu button path) and resume'
    action('OpenPause')
    action('ReleaseShowMain')
    yield wait(.15)
    text = panel_text()
    check('Main menu opens from play with a valid Continue', bool(prop('ReleaseMenuActive')) and int(prop('ReleaseMenuScreen')) == 0 and '> New Game' in text and 'Continue' in text and 'no valid save' not in text, text)
    yield screenshot('MainMenu_FromPlay')
    qa('QuestMenuBack')
    yield wait(.15)
    check('B on the main menu resumes the running session', not prop('ReleaseMenuActive') and int(prop('Mode')) == 0, int(prop('Mode')))

    S['step'] = 'simulated room-scale head preservation and Pawn-filtered occlusion'
    movement = pawn.get_component_by_class(unreal.CharacterMovementComponent)
    movement.stop_movement_immediately()
    movement.disable_movement()
    saved_body = pawn.get_actor_location()
    v = origin.get_editor_property('relative_location')
    saved_rig = unreal.Vector(v.x, v.y, v.z)
    camera.set_relative_location(unreal.Vector(28, 17, 160), False, True)
    head_before = camera.get_world_location()
    qa('QuestSetComfortSimulation', True)
    qa('QuestRoomscale')
    head_after = camera.get_world_location()
    check('Simulated room-scale body sweep preserves the physical head pose', distance(head_before, head_after) < .2, {'before': xyz(head_before), 'after': xyz(head_after)})
    body_after = pawn.get_actor_location()
    check('Room-scale body moves toward the head without a virtual head clamp',
          math.hypot(body_after.x - head_before.x, body_after.y - head_before.y) <= math.hypot(saved_body.x - head_before.x, saved_body.y - head_before.y) + .2)
    fixture = next(a for a in landings if isinstance(a, unreal.StaticMeshActor))
    fixture_mesh = fixture.get_component_by_class(unreal.StaticMeshComponent)
    fixture_original = {'transform': fixture.get_actor_transform(), 'mesh': fixture_mesh.get_editor_property('static_mesh'),
                        'mobility': fixture_mesh.get_editor_property('mobility'), 'collision': fixture_mesh.get_collision_enabled(),
                        'pawn_response': fixture_mesh.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)}
    fixture_mesh.set_mobility(unreal.ComponentMobility.MOVABLE)
    fixture_mesh.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cube'))
    fixture.set_actor_location(head_after, False, True)
    fixture.set_actor_scale3d(unreal.Vector(.3, .3, .3))
    fixture_mesh.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
    fixture_mesh.set_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN, unreal.CollisionResponseType.ECR_BLOCK)
    qa('QuestHeadOcclusion')
    check('Simulated head inside a Pawn-blocking solid enables the opaque occluder', pawn.get_editor_property('QuestHeadBlocked') and comp('QuestHeadOccluder').is_visible())
    fixture_mesh.set_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN, unreal.CollisionResponseType.ECR_IGNORE)
    qa('QuestHeadOcclusion')
    check('Pawn-ignoring overlap does not occlude the simulated head', not pawn.get_editor_property('QuestHeadBlocked'))
    fixture_mesh.set_static_mesh(fixture_original['mesh'])
    fixture.set_actor_transform(fixture_original['transform'], False, True)
    fixture_mesh.set_collision_enabled(fixture_original['collision'])
    fixture_mesh.set_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN, fixture_original['pawn_response'])
    fixture_mesh.set_mobility(fixture_original['mobility'])
    qa('QuestSetComfortSimulation', False)
    qa('QuestHeadOcclusion')
    pawn.set_actor_location(saved_body, False, True)
    origin.set_relative_location(saved_rig, False, True)
    camera.set_relative_location(unreal.Vector(0, 0, 160), False, True)

    S['step'] = 'snap head pivot fixture'
    old_location = pawn.get_actor_location()
    old_rotation = pawn.get_actor_rotation()
    camera.set_relative_location(unreal.Vector(28, 17, 160), False, True)
    head_before = camera.get_world_location()
    qa('QuestSnap', 30.0)
    head_after = camera.get_world_location()
    check('Native snap preserves the simulated physical head pivot', distance(head_before, head_after) < 1.0, {'before': xyz(head_before), 'after': xyz(head_after)})
    pawn.set_actor_location(old_location, False, True)
    pawn.set_actor_rotation(old_rotation, True)
    camera.set_relative_location(unreal.Vector(0, 0, 160), False, True)

    S['step'] = 'gaze targeting selects the photograph through the manager ray'
    photo = prop('PhotoActor')
    target = photo.get_actor_location()
    attempts = []
    selected = False
    for dx, dy in [(150, 0), (0, 150), (-150, 0), (0, -150), (100, 100)]:
        pawn.set_actor_location(unreal.Vector(target.x + dx, target.y + dy, 1107), False, True)
        aim_camera_at(target)
        yield wait(.08)
        action('UpdateTarget')
        yield wait(.04)
        attempts.append({'pawn': xyz(pawn.get_actor_location()), 'selected': str(prop('Target')), 'prompt': str(prop('Prompt'))})
        if prop('Target') == photo:
            selected = True
            break
    check('Manager gaze ray selects the actual photograph collision from the tracked camera', selected, attempts)
    check('Prompt keeps the authored interaction verb', 'photograph' in str(prop('Prompt')).lower() or 'inspect' in str(prop('Prompt')).lower(), str(prop('Prompt')))
    qa('QuestPrimary')
    yield wait(.2)
    check('Primary adapter reaches the photograph conversation', int(prop('Mode')) == 3 and str(prop('DialogueRoot')) == 'C1_01', {'mode': int(prop('Mode')), 'root': str(prop('DialogueRoot'))})
    for _ in range(14):
        if int(prop('Mode')) == 1:
            break
        yield wait(.8)
        qa('QuestPrimary')
    check('Photograph conversation reaches the inspection action', int(prop('Mode')) == 1 and prop('HeldPhoto') == photo, {'mode': int(prop('Mode'))})
    qa('QuestPhotoPose')
    check('Fallback held photo stays in reach', 40 <= distance(photo.get_actor_location(), camera.get_world_location()) <= 70)
    yield screenshot('Photo_Held')
    action('CloseModal')
    yield wait(.1)

    S['step'] = 'dialogue choice adapter'
    action('StartScene', 'C1_04')
    for _ in range(20):
        if bool(prop('DialogueWaitingChoice')):
            break
        yield wait(.8)
        qa('QuestPrimary')
    check('Existing native dialogue reaches its choices', bool(prop('DialogueWaitingChoice')) and int(prop('DialogueChoiceCount')) >= 2)
    qa('QuestCycleChoice')
    qa('QuestPanelFrame')
    aim_camera_at(comp('QuestChoice2').get_world_location())
    qa('QuestPointerTrace')
    yield screenshot('DialogueChoices_BSelected')
    selected_index = int(pawn.get_editor_property('QuestChoiceIndex'))
    qa('QuestPrimary')
    yield wait(.15)
    check('Primary adapter ray reaches ChooseDialogue for the highlighted row', str(prop('DialogueNodeId')) == 'C1_04.choice_B' and not bool(prop('DialogueWaitingChoice')),
          {'selected_index': selected_index, 'node': str(prop('DialogueNodeId'))})
    action('CloseModal')
    yield wait(.1)

    S['step'] = 'authored teleport landings'
    pairs = [(a, b) for a in landings for b in landings if a != b and 120 < distance(a.get_actor_location(), b.get_actor_location()) < 500
             and abs(a.get_actor_location().z - b.get_actor_location().z) < 110]
    check('City supplies reachable authored landing pairs', bool(pairs), {'nodes': len(landings), 'pairs': len(pairs)})
    teleported = False
    attempts = []
    for start, destination in pairs[:18]:
        pawn.set_actor_location(start.get_actor_location() + unreal.Vector(0, 0, 88), False, True)
        aim_camera_at(destination.get_actor_location() + unreal.Vector(0, 0, 2))
        qa('QuestTeleport')
        yield wait(.06)
        head = camera.get_world_location()
        t = destination.get_actor_location()
        horizontal = math.hypot(head.x - t.x, head.y - t.y)
        attempts.append({'from': start.get_actor_label(), 'to': destination.get_actor_label(), 'head_xy_error_cm': round(horizontal, 3)})
        if horizontal < 40:
            teleported = True
            break
    check('Native teleport reaches a collision-checked authored landing', teleported, attempts)
    movement.set_movement_mode(unreal.MovementMode.MOVE_WALKING)

    S['step'] = 'end-of-demo screen on the world panel'
    action('EndSlice')
    yield wait(.2)
    text = panel_text()
    check('EndSlice shows the release end screen to the XR player', bool(prop('ReleaseMenuActive')) and int(prop('ReleaseMenuScreen')) == 3 and
          str(prop('ReleaseMenuTitle')).startswith('End of Chapters') and '> Return to menu' in text and 'Review journal' in text, text)
    check('End screen title is on the panel', panel_title().startswith('End of Chapters'), panel_title())
    yield screenshot('EndScreen_Panel')
    qa('QuestMenuBack')
    yield wait(.15)
    check('B on the end screen returns to the main menu', bool(prop('ReleaseMenuActive')) and int(prop('ReleaseMenuScreen')) == 0)
    action('ReleaseResume')
    yield wait(.15)
    check('Resume returns to exploration', not prop('ReleaseMenuActive') and int(prop('Mode')) == 0)

    S['step'] = 'guarded save, PIE restart and real Continue'
    action('SaveProgress')
    yield wait(.2)
    check('Guarded save succeeds before the restart', bool(prop('SaveSucceeded')) and save_file.exists())
    before_restart = digest(save_file)
    LEVEL.editor_request_end_play()
    yield until(lambda: not LEVEL.is_in_play_in_editor(), 'stop PIE before the restart')
    yield wait(.5)
    yield begin()
    settle()
    yield wait(.4)
    text = panel_text()
    check('Restarted front end offers a valid Continue for the XR profile', bool(prop('ReleaseContinueAvailable')) and 'no valid save' not in text, text)
    action('ReleaseSelect', 1, True)
    yield until(lambda: bool(prop('ReleaseSessionStarted')), 'real Continue restored the session', 10)
    yield wait(.4)
    check('Continue restores the same campaign in exploration', str(prop('SaveSlot')) == S['slot'] and int(prop('Mode')) == 0 and not prop('ReleaseMenuActive') and digest(save_file) == before_restart,
          {'slot': str(prop('SaveSlot')), 'mode': int(prop('Mode'))})
    yield screenshot('Continue_Restored')
    S['step'] = 'complete'


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
        restore_fixture()
        if S['original_map']:
            LEVEL.load_level(S['original_map'])
    except Exception:
        REPORT['cleanup_error'] = traceback.format_exc()
    REPORT['protected_saves_after'] = {str(p): digest(p) for p in protected_saves}
    REPORT['protected_assets_after'] = {str(p): digest(p) for p in PROTECTED_ASSETS}
    REPORT['protected_saves_unchanged'] = REPORT['protected_saves_before'] == REPORT['protected_saves_after']
    REPORT['protected_assets_unchanged'] = REPORT['protected_assets_before'] == REPORT['protected_assets_after']
    REPORT['success'] = ('error' not in REPORT and 'cleanup_error' not in REPORT and REPORT['protected_saves_unchanged'] and
                         REPORT['protected_assets_unchanged'] and bool(REPORT['checks']) and all(c['passed'] for c in REPORT['checks'])
                         and S['step'] == 'complete')
    write()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.log('QUEST3_XR_RUNTIME_VALIDATION ' + json.dumps({'success': REPORT['success'], 'checks': len(REPORT['checks']), 'step': S['step']}))
    unreal.SystemLibrary.quit_editor()


runner = scenario()


def tick(delta):
    global pending, deadline, ticking
    if ticking:
        return
    ticking = True
    try:
        if closing:
            if not LEVEL.is_in_play_in_editor():
                complete_finish()
            return
        now = time.monotonic()
        if pending:
            if 'seconds' in pending and now < deadline:
                return
            if 'predicate' in pending and not pending['predicate']():
                if now > deadline:
                    raise TimeoutError(pending['name'])
                return
            pending = None
        pending = next(runner)
        deadline = now + pending.get('seconds', pending.get('timeout', 25))
        write()
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())
    finally:
        ticking = False


write()
handle = unreal.register_slate_post_tick_callback(tick)
