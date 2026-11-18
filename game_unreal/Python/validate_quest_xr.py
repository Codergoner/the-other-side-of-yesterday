"""Async full-editor PIE regression of the Quest native adapter, without an HMD.

Run after the city and XR writers finish, in a dedicated full-editor process
with -ExecutePythonScript. Never run via -run=pythonscript: it needs Slate/PIE.
This tests native callable actions and controlled camera fixtures, not physical
controller input, continuous walking, an APK, headset comfort or frame rate.
"""
from pathlib import Path
import datetime
import hashlib
import json
import math
import re
import time
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Quest_20261025', 'Quest regression requires the isolated copy'
BASELINE = json.loads((ROOT.parent / 'quest_baseline_manifest.json').read_text(encoding='utf-8'))
assert Path(BASELINE['quest_copy']).resolve() == ROOT.parent
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
try:
    unreal.get_default_object(unreal.EditorPerformanceSettings).set_editor_property('throttle_cpu_when_not_foreground', False)
except Exception:
    pass
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
SLOT = 'Yesterday_Quest_AdapterQA_' + STAMP
MAP = '/Game/Quest/Maps/Verdant_VR'
MANAGER_CLASS = '/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C'
REPORT_PATH = ROOT / 'quest_xr_runtime_validation.json'
CONTRAST_ONLY = unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'QuestHandsContrastOnly')
if CONTRAST_ONLY:
    REPORT_PATH = ROOT / 'quest_hands_contrast_validation.json'
SCREENS = ROOT / 'validation/quest_xr' / STAMP
SCREENS.mkdir(parents=True, exist_ok=True)
REPORT = {'success': False, 'run': STAMP, 'map': MAP, 'save_slot': SLOT, 'checks': [],
          'screenshots': [],
          'headset_tested': False, 'physical_controller_input_tested': False,
          'apk_tested': False, 'performance_benchmarked': False, 'full_story_acceptance': False,
          'scope': 'Native Quest Blueprint adapter, controlled desktop camera/pose fixtures, real scene rays and Unreal SaveGame'}
S = {'world': None, 'pawn': None, 'manager': None, 'controller': None, 'override': None,
     'step': 'startup', 'original_map': None, 'components': {}}
pending = None
deadline = 0
handle = None
closing = False
ticking = False
SOURCE_GLOVE = unreal.load_asset('/Game/Quest/XR/Hands/Materials/M_QuestMatteGlove')
# EditorAssetLibrary rejects metadata queries during PIE. Read the persisted
# package tag now; actual render graph values are still checked on the PIE mesh.
SOURCE_GLOVE_VERSION = unreal.EditorAssetLibrary.get_metadata_tag(SOURCE_GLOVE, 'Quest.HandMaterialVersion') if SOURCE_GLOVE else ''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


protected = []
concurrent_match = re.search(r'(?:^|\s)-ConcurrentQuestQAPrefix=([A-Za-z0-9_]+)', unreal.SystemLibrary.get_command_line())
CONCURRENT_QA_PREFIX = concurrent_match.group(1) if concurrent_match else None
if CONCURRENT_QA_PREFIX:
    assert CONCURRENT_QA_PREFIX.startswith('Yesterday_Quest_XR_Story_QA_') and CONCURRENT_QA_PREFIX.endswith('_')
external_qa = []
for folder in [ROOT / 'Saved/SaveGames',
               Path(BASELINE['source_development_copy']) / 'game_unreal/Saved/SaveGames',
               Path(BASELINE['original_workspace']) / 'game_unreal/Saved/SaveGames',
               Path.home() / 'AppData/Local/YesterdayHarbor/Saved/SaveGames']:
    if folder.exists():
        for path in folder.glob('*.sav'):
            if CONCURRENT_QA_PREFIX and path.name.startswith(CONCURRENT_QA_PREFIX):
                external_qa.append(path)
            else:
                protected.append(path)
REPORT['protected_saves_before'] = {str(p): digest(p) for p in protected}
REPORT['concurrent_external_qa_prefix'] = CONCURRENT_QA_PREFIX
REPORT['concurrent_external_qa_saves_before'] = {str(p): digest(p) for p in external_qa}


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
    name = S.get('screenshot_prefix', '') + name
    path = SCREENS / (name + '.png')
    unreal.AutomationLibrary.take_high_res_screenshot(1400, 900, str(path))
    REPORT['screenshots'].append(str(path))
    return until(lambda: path.exists() and path.stat().st_size > 15000,
                 'native PIE viewport screenshot ' + name, timeout=30)


def manager(world):
    klass = unreal.load_class(None, MANAGER_CLASS)
    found = unreal.GameplayStatics.get_all_actors_of_class(world, klass)
    if len(found) != 1:
        raise RuntimeError('Expected one copied Opening manager: ' + str(len(found)))
    return found[0]


def prop(name):
    return S['manager'].get_editor_property(name)


def action(name, *args):
    return S['manager'].call_method(name, args=tuple(args))


def qa(name, *args):
    return S['pawn'].call_method(name, args=tuple(args))


def comp(name):
    return S['pawn'].get_editor_property(name)


def ready():
    world = EDITOR.get_game_world()
    if world is None:
        return False
    pawn = unreal.GameplayStatics.get_player_character(world, 0)
    if pawn is None or pawn.get_controller() is None:
        return False
    S.update(world=world, pawn=pawn, controller=pawn.get_controller(), manager=manager(world))
    return prop('Player') == pawn and pawn.get_editor_property('QuestManager') == S['manager']


def restore_override():
    if S['override']:
        actor, slot = S['override']
        actor.set_editor_property('SaveSlot', slot)
        S['override'] = None


def aim_camera_at(point):
    camera = comp('QuestCamera')
    world_rotation = unreal.MathLibrary.find_look_at_rotation(camera.get_world_location(), point)
    root_rotation = S['pawn'].get_actor_rotation()
    camera.set_relative_rotation(unreal.Rotator(pitch=world_rotation.pitch - root_rotation.pitch,
                                 yaw=world_rotation.yaw - root_rotation.yaw, roll=0), False, True)


def quat_values(transform):
    q = transform.rotation
    return [float(q.x), float(q.y), float(q.z), float(q.w)]


def rotation_difference(a, b):
    dot = min(1.0, max(0.0, abs(sum(x * y for x, y in zip(a, b)))))
    return math.degrees(2 * math.acos(dot))


def hand_pose_snapshot():
    result = {}
    for side, suffix in [('Left', 'l'), ('Right', 'r')]:
        mesh = comp('QuestHandMesh' + side)
        bones = {str(mesh.get_bone_name(i)) for i in range(mesh.get_num_bones())}
        wanted = ['hand_' + suffix, 'index_03_' + suffix, 'middle_03_' + suffix]
        check('Hand skeleton contains wrist/index/middle: ' + side, all(b in bones for b in wanted), wanted)
        result[side] = {bone: quat_values(mesh.get_socket_transform(bone, unreal.RelativeTransformSpace.RTS_COMPONENT))
                        for bone in wanted}
    return result


def hand_frame_snapshot():
    result = {}
    for side, suffix in [('Left', 'l'), ('Right', 'r')]:
        mesh = comp('QuestHandMesh' + side)
        result[side] = {bone: xyz(mesh.get_socket_location(bone + '_' + suffix))
                        for bone in ['hand', 'index_03', 'middle_03']}
    return result


def validate_hands():
    S['step'] = 'simulated articulated hand presentation'
    yield until(lambda: bool(S['pawn'].get_editor_property('QuestHandsReady')), 'native hand anim instances ready', 8)
    check('Only the four existing motion controllers track the Character',
          len(S['pawn'].get_components_by_class(unreal.MotionControllerComponent)) == 4)
    for side in ['Left', 'Right']:
        mesh = comp('QuestHandMesh' + side)
        parent = mesh.get_attach_parent()
        check('Skeletal hand uses the existing single Grip frame: ' + side, parent == comp(side + 'Grip'),
              {'mesh': mesh.get_class().get_path_name(), 'parent': parent.get_name() if parent else None})
        expected = json.loads((ROOT / 'Python/quest_hand_attachment_calibration.json').read_text(encoding='utf-8'))['attachments']['Hand' + side]
        location = mesh.get_editor_property('relative_location')
        rotation = mesh.get_editor_property('relative_rotation')
        er = expected['rotation_degrees']
        angles = [(rotation.pitch, er['pitch']), (rotation.yaw, er['yaw']), (rotation.roll, er['roll'])]
        check('Hand attachment matches the inspected Epic owning Pawn: ' + side,
              distance(location, unreal.Vector(*expected['location_cm'])) < .01 and
              all(abs((a - b + 180) % 360 - 180) < .01 for a, b in angles),
              {'relative_location_cm': xyz(location), 'relative_rotation': str(rotation), 'source': 'Installed Epic XRFramework/BP_XRPawn'})
        check('Hand render component belongs to the possessed Character: ' + side, mesh.get_owner() == S['pawn'])
        check('Hands are non-physics presentation: ' + side,
              mesh.get_collision_enabled() == unreal.CollisionEnabled.NO_COLLISION and mesh.get_num_materials() == 1)
        glove = mesh.get_material(0)
        check('Owned glove has cooked skeletal material usage: ' + side, glove and
              glove.get_path_name().startswith('/Game/Quest/XR/Hands/Materials/M_QuestMatteGlove') and
              bool(glove.get_editor_property('used_with_skeletal_mesh')))
        if side == 'Left':
            material_lib = unreal.MaterialEditingLibrary
            color = material_lib.get_material_property_input_node(glove, unreal.MaterialProperty.MP_BASE_COLOR).get_editor_property('constant')
            scalars = {name: material_lib.get_material_property_input_node(glove, value).get_editor_property('r')
                       for name, value in [('roughness', unreal.MaterialProperty.MP_ROUGHNESS),
                                           ('metallic', unreal.MaterialProperty.MP_METALLIC),
                                           ('specular', unreal.MaterialProperty.MP_SPECULAR)]}
            version = SOURCE_GLOVE_VERSION
            check('Final glove material version retains exact chestnut albedo', version == 'Chestnut1p6_20261025' and
                  all(abs(a - b) < .0001 for a, b in zip((color.r, color.g, color.b), (.152, .0928, .0512))),
                  {'metadata_version': version, 'actual_albedo': [color.r, color.g, color.b], 'material_path': glove.get_path_name()})
            check('Glove remains matte without an emissive connection',
                  abs(scalars['roughness'] - .9) < .0001 and abs(scalars['metallic']) < .0001 and
                  abs(scalars['specular'] - .18) < .0001 and
                  material_lib.get_material_property_input_node(glove, unreal.MaterialProperty.MP_EMISSIVE_COLOR) is None)
            REPORT['hand_material'] = {'version': version, 'base_color_linear': [color.r, color.g, color.b], **scalars, 'emissive_connected': False}
        check('Untracked hands stay hidden and do not tick outside simulation: ' + side,
              not mesh.is_visible() and not mesh.is_component_tick_enabled())
        check('Anim rig is the bundled Epic hand blueprint: ' + side,
              mesh.get_anim_instance().get_class().get_path_name() == '/Game/XRMannequins/Meshes/ABP_MannequinsXR.ABP_MannequinsXR_C')
        check('Hand mirror is correct: ' + side,
              bool(mesh.get_anim_instance().get_editor_property('bMirror')) == (side == 'Left'))
    movement = S['pawn'].get_component_by_class(unreal.CharacterMovementComponent)
    movement.stop_movement_immediately()
    movement.disable_movement()
    camera = comp('QuestCamera')
    old = camera.get_editor_property('relative_rotation')
    old_rotation = unreal.Rotator(pitch=old.pitch, yaw=old.yaw, roll=old.roll)
    # A player looks down to inspect their hands. This is an explicit desktop
    # camera fixture only, before the preservation assertion captures its pose.
    camera.set_relative_rotation(unreal.Rotator(pitch=-28), False, True)
    eye = camera.get_world_location()
    qa('QuestSetHandsPreview', True, 0.0, 0.0, 0.0, 0.0)
    yield wait(.35)
    check('Explicit desktop hand simulation is enabled', bool(S['pawn'].get_editor_property('QuestHandsPreview')))
    for side, suffix in [('Left', 'l'), ('Right', 'r')]:
        mesh = comp('QuestHandMesh' + side)
        check('Simulated hand is visible and animates: ' + side, mesh.is_visible() and mesh.is_component_tick_enabled())
        wrist = mesh.get_socket_location('hand_' + suffix)
        grip = comp(side + 'Grip').get_world_location()
        check('Wrist remains within the controller grip basis: ' + side, distance(wrist, grip) < 30,
              {'wrist_cm': xyz(wrist), 'grip_cm': xyz(grip), 'distance_cm': distance(wrist, grip)})
    opened = hand_pose_snapshot()
    open_frame = hand_frame_snapshot()
    yield screenshot('SimulatedHands_Open')
    qa('QuestSetHandsPreview', True, 1.0, 1.0, 1.0, 1.0)
    yield wait(.35)
    closed = hand_pose_snapshot()
    closed_frame = hand_frame_snapshot()
    for side, suffix in [('Left', 'l'), ('Right', 'r')]:
        index = 'index_03_' + suffix
        middle = 'middle_03_' + suffix
        index_delta = rotation_difference(opened[side][index], closed[side][index])
        middle_delta = rotation_difference(opened[side][middle], closed[side][middle])
        check('Native trigger changes index bone pose: ' + side, index_delta > 10,
              {'degrees': index_delta, 'simulated_input': True})
        check('Native grip changes middle finger pose: ' + side, middle_delta > 10,
              {'degrees': middle_delta, 'simulated_input': True})
    yield screenshot('SimulatedHands_Closed')
    grip = comp('LeftGrip')
    mesh = comp('QuestHandMeshLeft')
    grip_before = grip.get_world_location()
    wrist_before = mesh.get_socket_location('hand_l')
    local = grip.get_editor_property('relative_location')
    grip.set_relative_location(unreal.Vector(local.x + 10, local.y, local.z), False, True)
    yield wait(.15)
    grip_after = grip.get_world_location()
    wrist_after = mesh.get_socket_location('hand_l')
    grip_delta = grip_after - grip_before
    wrist_delta = wrist_after - wrist_before
    check('Grip translation is applied once to the skeletal wrist', distance(grip_delta, wrist_delta) < .3 and
          9.5 <= distance(grip_before, grip_after) <= 10.5,
          {'grip_delta_cm': xyz(grip_delta), 'wrist_delta_cm': xyz(wrist_delta), 'simulated': True})
    check('Hand preview never moves the camera', distance(eye, camera.get_world_location()) < .2)
    REPORT['hand_pose_evidence'] = {'open': opened, 'closed': closed,
                                   'open_bones_world_cm': open_frame, 'closed_bones_world_cm': closed_frame,
                                   'scope': 'Simulated controller floats and actual native bone transforms; no physical tracking test'}
    qa('QuestSetHandsPreview', False, 0.0, 0.0, 0.0, 0.0)
    yield wait(.15)
    check('Hands hide and stop ticking when untracked simulation is disabled',
          all(not comp('QuestHandMesh' + side).is_visible() and not comp('QuestHandMesh' + side).is_component_tick_enabled()
              for side in ['Left', 'Right']))
    camera.set_relative_rotation(old_rotation, False, True)
    movement.set_movement_mode(unreal.MovementMode.MOVE_WALKING)


def hand_contrast_scenario():
    """Read-only hand fixtures under existing shade/direct sun; no light edits."""
    REPORT['scope'] = 'Simulated native hand poses in existing lit and shaded scene fixtures; no lighting changes or hardware test'
    S['step'] = 'load isolated VR map for hand contrast review'
    old_world = EDITOR.get_editor_world()
    if old_world:
        S['original_map'] = old_world.get_outer().get_name()
    check('VR map loads', LEVEL.load_level(MAP))
    edit_manager = manager(EDITOR.get_editor_world())
    S['override'] = (edit_manager, edit_manager.get_editor_property('SaveSlot'))
    edit_manager.set_editor_property('SaveSlot', SLOT)
    LEVEL.editor_request_begin_play()
    yield until(ready, 'possessed native Quest Character and manager references')
    restore_override()
    for command in ['r.ScreenPercentage 100', 't.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0']:
        unreal.SystemLibrary.execute_console_command(S['world'], command)
    yield wait(.35)
    if bool(prop('IntroActive')):
        action('SkipRecollections')
    action('CloseModal')
    yield from validate_workshop_nodes()
    pawn = S['pawn']
    movement = pawn.get_component_by_class(unreal.CharacterMovementComponent)
    actors = unreal.GameplayStatics.get_all_actors_of_class(S['world'], unreal.Actor)
    sun = unreal.GameplayStatics.get_all_actors_of_class(S['world'], unreal.DirectionalLight)[0]
    light_direction = sun.get_actor_forward_vector()
    sun_yaw = math.degrees(math.atan2(light_direction.y, light_direction.x))
    REPORT['fixtures'] = []
    for label, node_id, yaw in [('Shaded', 'home_porch', 180.0), ('Lit', 'market_street', sun_yaw)]:
        S['screenshot_prefix'] = label + '_'
        landing = next(a for a in actors if a.actor_has_tag('quest.nav.' + node_id))
        movement.stop_movement_immediately()
        movement.disable_movement()
        pawn.set_actor_location(landing.get_actor_location() + unreal.Vector(0, 0, 88), False, True)
        pawn.set_actor_rotation(unreal.Rotator(yaw=yaw), True)
        comp('QuestCamera').set_relative_location(unreal.Vector(0, 0, 160), False, True)
        comp('QuestCamera').set_relative_rotation(unreal.Rotator(), False, True)
        yield wait(.2)
        yield from validate_hands()
        REPORT['fixtures'].append({'label': label, 'node': node_id,
                                   'pose': REPORT['hand_pose_evidence'], 'simulated': True,
                                   'fixture_placement': 'Direct PIE-only authored-node position; separate core validation tests real teleport'})
    S['step'] = 'complete'


def validate_workshop_nodes():
    """Fresh-spawn real teleport loops; controlled visibility, no story seeding."""
    S['step'] = 'native home and workshop landing loops'
    pawn = S['pawn']
    movement = pawn.get_component_by_class(unreal.CharacterMovementComponent)
    movement.stop_movement_immediately()
    movement.disable_movement()
    camera = comp('QuestCamera')
    nodes = {name: next(a for a in unreal.GameplayStatics.get_all_actors_of_class(S['world'], unreal.Actor)
                       if a.actor_has_tag('quest.nav.' + name))
             for name in ['home_inside', 'home_workshop', 'home_porch']}
    REPORT['workshop_teleport_loops'] = {'fresh_spawn_cm': xyz(pawn.get_actor_location()), 'hops': [],
                                        'setup_segment_teleports': False, 'physical_headset_tested': False}
    for height in [110.0, 160.0]:
        camera.set_relative_location(unreal.Vector(0, 0, height), False, True)
        for name in ['home_inside', 'home_workshop', 'home_inside']:
            node = nodes[name]
            before = pawn.get_actor_location()
            aim_camera_at(node.get_actor_location() + unreal.Vector(0, 0, 2))
            ray_start = camera.get_world_location()
            ray_end = ray_start + camera.get_forward_vector() * 650.0
            ray = unreal.SystemLibrary.line_trace_single(S['world'], ray_start, ray_end,
                  unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [pawn], unreal.DrawDebugTrace.NONE, True)
            hit = ray.to_tuple()
            ray_target = bool(hit[0]) and hit[9] == node
            qa('QuestTeleport')
            yield wait(.08)
            after = pawn.get_actor_location()
            head = camera.get_world_location()
            target = node.get_actor_location()
            error = math.hypot(head.x - target.x, head.y - target.y)
            row = {'height_cm': height, 'to': name, 'before_cm': xyz(before), 'after_cm': xyz(after),
                   'head_xy_error_cm': error, 'native_action': 'QuestTeleport',
                   'ray_hits_target': ray_target, 'ray_actor': str(hit[9]),
                   'capsule_floor_clearance_cm': after.z - target.z - 88,
                   'floor_clearance_limit_cm': 2.5}
            REPORT['workshop_teleport_loops']['hops'].append(row)
            # CharacterMovement intentionally floats 1.9..2.4cm above floor
            # (installed UE constants). Include 0.1cm numeric tolerance.
            check('Real landing ray at %d cm reaches %s' % (height, name), ray_target and error < 2 and
                  -.1 <= after.z - target.z - 88 <= 2.5, row)
    import sys
    sys.path.insert(0, str(ROOT / 'Python'))
    import build_chapters_story
    def state():
        return {name: list(prop(name)) if isinstance(prop(name), unreal.Array) else prop(name)
                for name in build_chapters_story.STATE}
    state_before = state()
    present = list(prop('PresentActors'))
    past = list(prop('PastActors'))
    check('Both home interiors belong only to PresentActors',
          all(nodes[n] in present and nodes[n] not in past and nodes[n].actor_has_tag('Opening.PresentOnly')
              for n in ['home_inside', 'home_workshop']))
    check('Home porch landing is common across eras', nodes['home_porch'] not in present and nodes['home_porch'] not in past)
    action('SetGroupVisible', present, False)
    action('SetGroupVisible', past, True)
    check('Controlled Past visibility fixture hides and disables both interior landings',
          all(nodes[n].get_editor_property('hidden') and not nodes[n].get_actor_enable_collision()
              for n in ['home_inside', 'home_workshop']))
    check('Common porch remains visible and query-enabled in the fixture',
          not nodes['home_porch'].get_editor_property('hidden') and nodes['home_porch'].get_actor_enable_collision())
    old_location = pawn.get_actor_location()
    aim_camera_at(nodes['home_workshop'].get_actor_location() + unreal.Vector(0, 0, 2))
    qa('QuestTeleport')
    yield wait(.08)
    check('Actual teleport cannot select a query-disabled interior landing', distance(old_location, pawn.get_actor_location()) < .2)
    action('ApplyWorldState')
    check('Authoritative era restores both Present landing queries',
          all(not nodes[n].get_editor_property('hidden') and nodes[n].get_actor_enable_collision()
              for n in ['home_inside', 'home_workshop']))
    check('Controlled visibility fixture preserves all saved story state fields', state_before == state())
    REPORT['workshop_teleport_loops']['visibility_fixture_scope'] = 'Existing SetGroupVisible is called explicitly; no era or story flags seeded, not a full timeline journey'
    camera.set_relative_location(unreal.Vector(0, 0, 160), False, True)


def scenario():
    S['step'] = 'load isolated VR map and save override'
    old_world = EDITOR.get_editor_world()
    if old_world:
        S['original_map'] = old_world.get_outer().get_name()
    check('Quest map exists', unreal.EditorAssetLibrary.does_asset_exist(MAP))
    check('VR map loads', LEVEL.load_level(MAP))
    edit_manager = manager(EDITOR.get_editor_world())
    S['override'] = (edit_manager, edit_manager.get_editor_property('SaveSlot'))
    edit_manager.set_editor_property('SaveSlot', SLOT)
    LEVEL.editor_request_begin_play()
    yield until(ready, 'possessed native Quest Character and manager references')
    restore_override()
    for command in ['r.ScreenPercentage 100', 't.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0']:
        unreal.SystemLibrary.execute_console_command(S['world'], command)
    yield wait(.4)

    S['step'] = 'native possession and floor camera'
    pawn = S['pawn']
    check('Actual pawn is Character-derived Quest adapter', isinstance(pawn, unreal.Character) and
          pawn.get_class().get_path_name() == '/Game/Quest/XR/BP_QuestCharacter.BP_QuestCharacter_C', pawn.get_class().get_path_name())
    check('Headset-free harness is using fallback camera', not pawn.get_editor_property('QuestXRActive'))
    check('Dedicated save slot inherited by PIE', str(prop('SaveSlot')) == SLOT, str(prop('SaveSlot')))
    check('Copied story manager references possessed Character', prop('Player') == pawn)
    refs = ['PhotoActor', 'LetterActor', 'MotherActor', 'BenchActor', 'AnchorActor', 'NeriActor', 'HealerActor', 'SelaActor']
    check('Existing authored story references survive map copy', all(prop(n) for n in refs), {n: str(prop(n)) for n in refs})
    camera = comp('QuestCamera')
    origin = comp('VROrigin')
    eye = camera.get_world_location().z - origin.get_world_location().z
    check('Fallback eye is 160 cm above floor-relative rig', abs(eye - 160) < .5, eye)
    check('Tracking camera is HMD-locked without control rotation', camera.get_editor_property('lock_to_hmd') and
          not camera.get_editor_property('use_pawn_control_rotation'))
    check('No joystick jog is configured', pawn.get_component_by_class(unreal.CharacterMovementComponent).get_editor_property('max_walk_speed') == 0)
    if bool(prop('IntroActive')):
        action('SkipRecollections')
        yield wait(.2)
    action('CloseModal')

    S['step'] = 'world panel and physical head independence'
    action('OpenPause')
    qa('QuestPanelFrame')
    yield wait(.15)
    panel = comp('QuestPanelRoot')
    before = panel.get_world_location()
    before_rot = panel.get_world_rotation()
    check('Pause does not pause XR update', not unreal.GameplayStatics.is_game_paused(S['world']))
    check('Pause does not ignore physical head look', not S['controller'].is_look_input_ignored())
    check('Panel uses absolute world location and rotation', panel.get_editor_property('absolute_location') and panel.get_editor_property('absolute_rotation'))
    check('Panel is placed at comfortable authored distance', 165 <= distance(before, camera.get_world_location()) <= 195,
          {'panel': xyz(before), 'eye': xyz(camera.get_world_location())})
    material = comp('QuestPanelBack').get_material(0)
    check('Opaque dark backplate uses owned material', material and material.get_path_name().startswith('/Game/Quest/XR/Materials/M_QuestPanel'), str(material))
    font_material = comp('QuestPanelText').get_material(0)
    check('Font is emissive with owned glyph-preserving material', font_material and
          font_material.get_path_name().startswith('/Game/Quest/XR/Materials/M_QuestReadableText') and
          font_material.get_editor_property('shading_model') == unreal.MaterialShadingModel.MSM_UNLIT)
    size = comp('QuestPanelText').get_text_local_size()
    check('Modal hint is bounded above the response rows', size.z <= 14 and size.y <= 130,
          {'body_size_cm': xyz(size), 'body_top_cm': 32, 'first_row_top_cm': 16})
    r = camera.get_editor_property('relative_rotation')
    saved_rotation = unreal.Rotator(pitch=r.pitch, yaw=r.yaw, roll=r.roll)
    camera.set_relative_rotation(unreal.Rotator(pitch=0, yaw=25, roll=0), False, True)
    qa('QuestPanelFrame')
    check('Turning preview head leaves modal anchored', distance(before, panel.get_world_location()) < .1 and
          abs(before_rot.yaw - panel.get_world_rotation().yaw) < .1)
    camera.set_relative_rotation(saved_rotation, False, True)
    # Cycle to save through the same native primary adapter used by trigger.
    qa('QuestCycleChoice')
    qa('QuestPanelFrame')
    check('Pause selection feedback marks the Save row', str(comp('QuestChoiceText2').get_editor_property('text')).startswith('> Save committed progress'))
    aim_camera_at(comp('QuestChoice2').get_world_location())
    qa('QuestPointerTrace')
    yield screenshot('SpatialPausePanel_SaveSelected')
    qa('QuestPrimary')
    yield wait(.15)
    check('Pause adapter reaches native committed SaveGame', bool(prop('SaveSucceeded')) and (ROOT / 'Saved/SaveGames' / (SLOT + '.sav')).exists())
    camera.set_relative_rotation(saved_rotation, False, True)
    action('CloseModal')

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
    check('Simulated room-scale body sweep preserves physical head pose', distance(head_before, head_after) < .2,
          {'before': xyz(head_before), 'after': xyz(head_after), 'simulated': True})
    body_after = pawn.get_actor_location()
    check('Room-scale body moves toward head without virtual head clamp',
          math.hypot(body_after.x - head_before.x, body_after.y - head_before.y) <=
          math.hypot(saved_body.x - head_before.x, saved_body.y - head_before.y) + .2,
          {'before_body': xyz(saved_body), 'after_body': xyz(body_after), 'head': xyz(head_before)})
    # Borrow one PIE-only landing actor as a temporary runtime collision
    # fixture. The editor map and assets are untouched. Restore it before the
    # actual landing-ray regression; failed PIE is discarded in its entirety.
    fixture = next(a for a in unreal.GameplayStatics.get_all_actors_of_class(S['world'], unreal.StaticMeshActor)
                   if a.actor_has_tag('Quest.Teleport'))
    fixture_mesh = fixture.get_component_by_class(unreal.StaticMeshComponent)
    fixture_original = {'transform': fixture.get_actor_transform(),
                        'mesh': fixture_mesh.get_editor_property('static_mesh'),
                        'mobility': fixture_mesh.get_editor_property('mobility'),
                        'collision': fixture_mesh.get_collision_enabled(),
                        'pawn_response': fixture_mesh.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)}
    fixture_mesh.set_mobility(unreal.ComponentMobility.MOVABLE)
    fixture_mesh.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cube'))
    fixture.set_actor_location(head_after, False, True)
    fixture.set_actor_scale3d(unreal.Vector(.3, .3, .3))
    fixture_mesh.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
    fixture_mesh.set_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN, unreal.CollisionResponseType.ECR_BLOCK)
    qa('QuestHeadOcclusion')
    check('Simulated head inside Pawn-blocking solid enables opaque occluder',
          pawn.get_editor_property('QuestHeadBlocked') and comp('QuestHeadOccluder').is_visible())
    occlusion_material = comp('QuestHeadOccluder').get_material(0)
    check('Head occlusion is an owned two-sided opaque material', occlusion_material and
          occlusion_material.get_path_name().startswith('/Game/Quest/XR/Materials/M_QuestHeadOcclusion') and
          occlusion_material.get_editor_property('two_sided'))
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
    movement = pawn.get_component_by_class(unreal.CharacterMovementComponent)
    movement.stop_movement_immediately()
    movement.disable_movement()
    old_location = pawn.get_actor_location()
    old_rotation = pawn.get_actor_rotation()
    camera.set_relative_location(unreal.Vector(28, 17, 160), False, True)
    head_before = camera.get_world_location()
    qa('QuestSnap', 30.0)
    head_after = camera.get_world_location()
    check('Native snap preserves simulated physical head pivot', distance(head_before, head_after) < 1.0,
          {'before': xyz(head_before), 'after': xyz(head_after), 'fixture': '28/17 cm head offset; movement disabled during fixture'})
    pawn.set_actor_location(old_location, False, True)
    pawn.set_actor_rotation(old_rotation, True)
    camera.set_relative_location(unreal.Vector(0, 0, 160), False, True)

    S['step'] = 'native controller-ray fallback selects photograph'
    photo = prop('PhotoActor')
    target = photo.get_actor_location()
    attempts = []
    selected = False
    for dx, dy in [(150, 0), (0, 150), (-150, 0), (0, -150), (100, 100)]:
        pawn.set_actor_location(unreal.Vector(target.x + dx, target.y + dy, 1107), False, True)
        aim_camera_at(target)
        action('UpdateTarget')
        yield wait(.08)
        attempts.append({'pawn': xyz(pawn.get_actor_location()), 'selected': str(prop('Target')),
                         'start': xyz(prop('DebugTraceStart')), 'end': xyz(prop('DebugTraceEnd'))})
        if prop('Target') == photo:
            selected = True
            break
    check('XR targeting adapter selects actual existing photo collision', selected, attempts)
    qa('QuestPrimary')
    yield wait(.15)
    check('Primary adapter reaches the existing source photo conversation', int(prop('Mode')) == 3 and str(prop('DialogueRoot')) == 'C1_01',
          {'mode': int(prop('Mode')), 'dialogue_root': str(prop('DialogueRoot'))})
    for _ in range(12):
        if int(prop('Mode')) == 1:
            break
        yield wait(.8)
        qa('QuestPrimary')
    check('Source photo conversation reaches the existing inspection action', int(prop('Mode')) == 1 and prop('HeldPhoto') == photo,
          {'mode': int(prop('Mode')), 'dialogue_root': str(prop('DialogueRoot'))})
    qa('QuestPhotoPose')
    check('Fallback held photo stays in reach', 40 <= distance(photo.get_actor_location(), camera.get_world_location()) <= 70)
    action('CloseModal')

    S['step'] = 'source dialogue choice adapter'
    action('StartScene', 'C1_04')
    for _ in range(20):
        if bool(prop('DialogueWaitingChoice')):
            break
        yield wait(.8)
        qa('QuestPrimary')
    check('Existing native dialogue reaches its source choices', bool(prop('DialogueWaitingChoice')) and int(prop('DialogueChoiceCount')) >= 2)
    qa('QuestCycleChoice')
    qa('QuestPanelFrame')
    aim_camera_at(comp('QuestChoice2').get_world_location())
    qa('QuestPointerTrace')
    yield screenshot('SpatialDialogueChoices_BSelected')
    before_node = str(prop('DialogueNodeId'))
    selected_index = int(pawn.get_editor_property('QuestChoiceIndex'))
    qa('QuestPrimary')
    yield wait(.15)
    check('Primary adapter ray reaches existing ChooseDialogue for highlighted B', str(prop('DialogueNodeId')) == 'C1_04.choice_B' and
          not bool(prop('DialogueWaitingChoice')), {'selected_index': selected_index, 'new_node': str(prop('DialogueNodeId'))})
    action('CloseModal')

    S['step'] = 'authored teleport landing nodes'
    nodes = [a for a in unreal.GameplayStatics.get_all_actors_of_class(S['world'], unreal.Actor) if a.actor_has_tag('Quest.Teleport')]
    pairs = [(a, b) for a in nodes for b in nodes if a != b and
             120 < distance(a.get_actor_location(), b.get_actor_location()) < 500 and
             abs(a.get_actor_location().z - b.get_actor_location().z) < 110]
    check('City supplies reachable authored landing pairs', bool(pairs), {'nodes': len(nodes), 'pairs': len(pairs)})
    teleported = False
    attempts = []
    for start, destination in pairs[:18]:
        pawn.set_actor_location(start.get_actor_location() + unreal.Vector(0, 0, 88), False, True)
        aim_camera_at(destination.get_actor_location() + unreal.Vector(0, 0, 2))
        qa('QuestTeleport')
        yield wait(.06)
        head = camera.get_world_location()
        target = destination.get_actor_location()
        horizontal = math.hypot(head.x - target.x, head.y - target.y)
        attempts.append({'from': start.get_name(), 'to': destination.get_name(), 'head_xy_error_cm': round(horizontal, 3)})
        if horizontal < 40:
            teleported = True
            break
    check('Native teleport reaches collision-checked authored landing', teleported, attempts)
    movement.set_movement_mode(unreal.MovementMode.MOVE_WALKING)
    try:
        S['pawn'].get_editor_property('QuestHandsReady')
        hands_authored = True
    except Exception:
        hands_authored = False
    if hands_authored:
        yield from validate_hands()
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
        restore_override()
        if S['original_map']:
            LEVEL.load_level(S['original_map'])
    except Exception:
        REPORT['cleanup_error'] = traceback.format_exc()
    REPORT['protected_saves_after'] = {str(p): digest(p) for p in protected}
    REPORT['concurrent_external_qa_saves_after'] = {str(p): digest(p) for p in external_qa}
    REPORT['protected_saves_unchanged'] = REPORT['protected_saves_before'] == REPORT['protected_saves_after']
    REPORT['success'] = 'error' not in REPORT and 'cleanup_error' not in REPORT and REPORT['protected_saves_unchanged'] and bool(REPORT['checks']) and all(c['passed'] for c in REPORT['checks'])
    write()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.log('QUEST_XR_RUNTIME_VALIDATION ' + json.dumps(REPORT))
    unreal.SystemLibrary.quit_editor()


runner = hand_contrast_scenario() if CONTRAST_ONLY else scenario()


def tick(delta):
    global pending, deadline, ticking
    if ticking:
        return  # viewport screenshots may synchronously pump Slate callbacks
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
