"""Native PIE checks of the supporting cast, the register-consent scene and v0.2 persistence.

Run with -SupportingCastQA and a dedicated -UserDir (saves never touch the player's slots).
Enters through the real release front end: New Game on a fresh isolated QA profile, then
Continue (after ReleaseReadProfile/ReleaseCheckContinue) for the restart/persistence check,
exactly as the release story harness does; only the profile slot and save prefix are
overridden on the editor manager and restored afterwards.
Uses the shipped Blueprint actions and real camera-ray selection (UpdateTarget/Interact),
real dialogue advance/choice functions and a real guarded save + PIE restart/load.
Controlled fixtures, stated in the report: era (EraIndex) and shelter (StormCover) are set
directly so every NPC can be reached without replaying Chapters 1-2; the dialogue minimum
hold is shortened for bulk reading. Not a main-route, packaged, input-device or art test.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import sys
import time
import traceback
import unreal

unreal.EditorPythonScripting.set_keep_python_script_alive(True)
try:
    unreal.get_default_object(unreal.EditorPerformanceSettings).set_editor_property('throttle_cpu_when_not_foreground', False)
except Exception:
    pass

ROOT = Path(unreal.Paths.project_dir()).resolve()
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
REPORT_PATH = ROOT / 'supporting_cast_runtime_validation.json'
MAP = '/Game/Quest/Maps/Verdant_Desktop'
MANAGER_PATH = '/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C'
CAST = json.loads((ROOT / 'ContentData/supporting_cast_v1.json').read_text(encoding='utf-8'))
IDENT = json.loads((ROOT / 'ContentData/quest_identity_v02.json').read_text(encoding='utf-8'))
INTEGRATION = json.loads((ROOT / 'supporting_cast_integration_report.json').read_text(encoding='utf-8'))
MARKERS = INTEGRATION['markers']
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
NAMESPACE = 'YSCQA_' + STAMP
PROFILE_SLOT = NAMESPACE + '_Profile'
CAMPAIGN_PREFIX = NAMESPACE + '_'
REPORT = {'success': False, 'run': STAMP, 'checks': [], 'conversations': [], 'selections': [], 'menu_entries': [],
          'qa_namespace': NAMESPACE, 'profile_slot': PROFILE_SLOT, 'campaign_prefix': CAMPAIGN_PREFIX,
          'entry_policy': 'Actual release menu New Game / Continue through the real front-end handlers; '
                          'only ReleaseProfileSlot and ReleaseSavePrefix are overridden on the editor manager. '
                          'No story flags are seeded except the stated era/shelter fixtures.',
          'fixtures': ['EraIndex and StormCover set directly to reach both eras and the clinic shelter',
                       'MinimumLineSeconds shortened on the PIE instance for bulk reading'],
          'scope': 'Native PIE: real menu entry, real ray selection, prompts, Interact, dialogue advance/choice, '
                   'guarded save + menu Continue after a PIE restart. '
                   'Not a full Chapter 1-2 route, packaged build, physical input or art approval.'}
S = {'world': None, 'manager': None, 'pawn': None, 'controller': None, 'camera': None, 'override': None,
     'step': 'startup', 'menu_entry': None}
handle = None
pending = None
deadline = 0.0
closing = False
saved_dir = Path(unreal.Paths.project_saved_dir()).resolve()
if saved_dir == (ROOT / 'Saved').resolve():
    raise RuntimeError('Use a dedicated -UserDir so the player save directory is never touched')
SAVE_DIR = saved_dir / 'SaveGames'
REPORT['save_directory'] = str(SAVE_DIR)
REPORT['native_save_guard_active'] = unreal.load_class(None, '/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary') is not None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


# Protected bytes: the story assets this QA exercises and every pre-existing save in the
# project and QA save directories. All of them must be byte-identical afterwards.
PROTECTED = [ROOT / 'Content/Opening/Blueprints/BP_OpeningActions.uasset',
             ROOT / 'Content/Opening/Blueprints/BP_OpeningSave.uasset',
             ROOT / 'Content/Release/Blueprints/BP_ReleaseProfile.uasset',
             ROOT / 'Content/Quest/Maps/Verdant_Desktop.umap']
for folder in [ROOT / 'Saved/SaveGames', SAVE_DIR]:
    if folder.exists():
        PROTECTED.extend(p for p in folder.iterdir() if p.is_file() and '.sav' in p.name)
PROTECTED = list(dict.fromkeys(PROTECTED))
REPORT['protected_before'] = {str(p): sha(p) for p in PROTECTED}

# EraIndex/StormCover are not instance-editable from Python. The stated fixtures are applied
# through an unsaved transient /Temp Blueprint function (never saved or cooked), exactly as the
# release story harness applies its QA profile pointer. No other story field is written.
sys.path.insert(0, str(ROOT / 'Python'))
import opening_graph as og
FIXTURE_BP = og.blueprint('/Temp/BP_SupportingCastFixture', unreal.Actor)
_graph = og.function(FIXTURE_BP, 'SetEraAndCover', inputs={'Target': og.object_type(MANAGER_PATH), 'Era': 'int', 'Cover': 'int', 'Linen': 'int'})
_era = _graph.set('EraIndex', _graph.input('Era'), owner=_graph.input('Target'), class_path=MANAGER_PATH)
_cover = _graph.set('StormCover', _graph.input('Cover'), owner=_graph.input('Target'), class_path=MANAGER_PATH)
_linen = _graph.set('LinenState', _graph.input('Linen'), owner=_graph.input('Target'), class_path=MANAGER_PATH)
og.link(_graph.entry, og.pin_in(_era))
og.link(og.pin_out(_era), og.pin_in(_cover))
og.link(og.pin_out(_cover), og.pin_in(_linen))
og.compile_bp(FIXTURE_BP, save=False)
FIXTURE = unreal.get_default_object(og.L.generated_class(FIXTURE_BP))
REPORT['fixture_helper'] = {'blueprint': FIXTURE_BP.get_path_name(), 'saved_or_cooked': False, 'writes': ['EraIndex', 'StormCover', 'LinenState']}
REPORT['fixtures'].append('LinenState=3 accompanies StormCover=1 so the saved fixture campaign satisfies the front end\'s '
                          'installed-cover invariant (a committed shelter implies delivered linen); Era and the past.gate '
                          'checkpoint are derived from EraIndex by the real _SaveCopy')


def fixture(era, cover, linen):
    FIXTURE.call_method('SetEraAndCover', args=(S['manager'], era, cover, linen))


def prop(name):
    return S['manager'].get_editor_property(name)


def setp(name, value):
    S['manager'].set_editor_property(name, value)


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
    if not passed:
        try:
            row['state'] = {k: str(prop(k)) for k in ['Mode', 'EraIndex', 'StormCover', 'DialogueNodeId', 'DialogueRoot',
                                                      'DialogueActive', 'DialogueWaitingChoice', 'Prompt', 'PanelText', 'Notice']}
        except Exception:
            row['state_error'] = traceback.format_exc()
    REPORT['checks'].append(row)
    write()
    if not passed:
        raise AssertionError(name + ': ' + str(details))


def visible(actor):
    try:
        return not bool(actor.get_editor_property('hidden'))
    except Exception:
        return not bool(actor.get_editor_property('bHidden'))


def tagged(tag):
    return list(unreal.GameplayStatics.get_all_actors_with_tag(S['world'], tag))


def ready():
    """PIE world, manager and player exist; then the real release menu is driven once.

    'new' presses the actual New Game handler on a fresh profile; 'continue' re-reads the
    profile pointer and candidate (ReleaseReadProfile/ReleaseCheckContinue) and presses the
    actual Continue handler. Ready only once the front end reports a started session.
    """
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
    S.update(world=world, pawn=pawn, controller=pawn.get_controller(),
             camera=unreal.GameplayStatics.get_player_camera_manager(world, 0), manager=found[0])
    if prop('Player') is None or S['camera'] is None or not bool(prop('ReleaseBooted')):
        return False
    requested = S.get('menu_entry')
    if requested:
        if not bool(prop('ReleaseMenuActive')) or int(prop('ReleaseMenuScreen')) != 0:
            return False
        if requested == 'continue':
            action('ReleaseReadProfile')
            action('ReleaseCheckContinue')
            if not bool(prop('ReleaseContinueAvailable')):
                raise RuntimeError('Actual Continue is unavailable for isolated profile ' + PROFILE_SLOT
                                   + ': ' + str(prop('ReleaseMenuStatus')))
        elif bool(prop('ReleaseContinueAvailable')):
            raise RuntimeError('A supposedly fresh QA profile already has progress')
        if str(prop('ReleaseProfileSlot')) != PROFILE_SLOT:
            raise RuntimeError('Front end is not using the isolated QA profile: ' + str(prop('ReleaseProfileSlot')))
        action('ReleaseNewGame' if requested == 'new' else 'ReleaseContinue')
        S['menu_entry'] = None
        slot = str(prop('SaveSlot'))
        if not slot.startswith(CAMPAIGN_PREFIX):
            raise RuntimeError('Front end selected a slot outside the QA namespace: ' + slot)
        REPORT['menu_entries'].append({'action': requested, 'slot': slot, 'profile': str(prop('ReleaseProfileSlot'))})
        write()
    return bool(prop('ReleaseSessionStarted'))


def xyz(v):
    return [round(v.x, 1), round(v.y, 1), round(v.z, 1)]


def position(location):
    S['pawn'].get_component_by_class(unreal.CharacterMovementComponent).stop_movement_immediately()
    S['pawn'].set_actor_location(location, False, True)


def aim_at(point):
    S['controller'].set_control_rotation(unreal.MathLibrary.find_look_at_rotation(S['camera'].get_camera_location(), point))


def cast_actor(tag):
    found = [a for a in tagged(tag) if a.actor_has_tag('cast.npc')]
    check('Exactly one placed actor for ' + tag, len(found) == 1, len(found))
    return found[0]


def focus(actor, label):
    """Real camera ray selection from standing points in front of / beside the NPC."""
    if int(prop('Mode')) != 0:
        action('CloseModal')
        yield wait(.05)
    base = actor.get_actor_location()
    yaw = math.radians(actor.get_actor_rotation().yaw + REPORT.get('mesh_forward_deg', 90.0))
    chest = actor.get_actor_bounds(False)[0]
    attempts = []
    for offset in [0.0, 0.6, -0.6, 1.2, -1.2, math.pi]:
        a = yaw + offset
        stand = unreal.Vector(base.x + math.cos(a) * 165, base.y + math.sin(a) * 165, base.z + 98)
        position(stand)
        yield wait(.10)
        for repeat in range(10):
            aim_at(chest)
            yield wait(.035)
            action('UpdateTarget')
            if prop('Target') == actor:
                break
        chosen = prop('Target')
        if chosen == actor:
            # The prompt is written by the per-frame UpdateStep hook after its own UpdateTarget;
            # give the game a couple of frames so the real prompt (not this tick's) is read.
            yield wait(.15)
        attempts.append({'stand': xyz(stand), 'target': chosen.get_name() if chosen else None, 'prompt': str(prop('Prompt'))})
        if chosen == actor:
            REPORT['selections'].append({'npc': label, 'attempts': attempts})
            write()
            return True
    REPORT['selections'].append({'npc': label, 'attempts': attempts, 'selected': False})
    check('Real camera ray selects ' + label, False, attempts)


def read_dialogue(label, choose=None):
    """Advance with the real AdvanceDialogue/ChooseDialogue functions; returns spoken (speaker, line)."""
    spoken, last, guard = [], None, 0
    while bool(prop('DialogueActive')) and guard < 60:
        guard += 1
        if bool(prop('DialogueWaitingChoice')):
            if choose is None:
                break
            action('ChooseDialogue', choose)
            choose = None
            yield wait(.05)
            continue
        line = (str(prop('DialogueSpeaker')), str(prop('DialogueLine')))
        if line != last and line[1]:
            spoken.append(line)
            last = line
        # LineElapsed is not instance-editable; honour the (shortened) real minimum hold instead.
        yield until(lambda: float(prop('LineElapsed')) >= float(prop('MinimumLineSeconds')), 'readable minimum line hold', 5)
        action('AdvanceDialogue')
        yield wait(.05)
    REPORT['conversations'].append({'npc': label, 'lines': spoken})
    write()
    return spoken


def talk_to(role, expect_node, expect_lines, label=None):
    row = CAST['roles'][role]
    actor = cast_actor(row['tag'])
    label = label or role
    check(label + ' is visible with query collision in its era', visible(actor) and bool(actor.get_actor_enable_collision()))
    yield from focus(actor, label)
    prompt = str(prop('Prompt'))
    action('Interact')
    yield wait(.05)
    node = str(prop('DialogueNodeId'))
    check(label + ' conversation opens its own node', node == expect_node and int(prop('Mode')) == 3,
          {'node': node, 'prompt': prompt})
    spoken = yield from read_dialogue(label)
    texts = [t for _, t in spoken]
    check(label + ' speaks exactly its authored lines', texts == [t for _, t in expect_lines], {'spoken': spoken})
    check(label + ' conversation closes back to play', not bool(prop('DialogueActive')) and int(prop('Mode')) == 0)
    return prompt


def scenario():
    S['step'] = 'load map'
    if not LEVEL.load_level(MAP):
        raise RuntimeError('Cannot load ' + MAP)
    cls = unreal.load_class(None, MANAGER_PATH)
    editor_manager = unreal.GameplayStatics.get_all_actors_of_class(EDITOR.get_editor_world(), cls)[0]
    if any((SAVE_DIR / (PROFILE_SLOT + suffix)).exists() for suffix in ['.sav', '.sav.bak']):
        raise RuntimeError('QA profile already occupied: ' + PROFILE_SLOT)
    S['override'] = (editor_manager, {name: editor_manager.get_editor_property(name)
                                      for name in ['ReleaseProfileSlot', 'ReleaseSavePrefix']})
    editor_manager.set_editor_property('ReleaseProfileSlot', PROFILE_SLOT)
    editor_manager.set_editor_property('ReleaseSavePrefix', CAMPAIGN_PREFIX)
    REPORT['mesh_forward_deg'] = float(INTEGRATION.get('mesh_forward_deg', 90.0))
    S['menu_entry'] = 'new'
    LEVEL.editor_request_begin_play()
    yield until(ready, 'release menu New Game into a fresh isolated QA campaign', 180)
    for command in ['t.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0', 'DisableAllScreenMessages']:
        unreal.SystemLibrary.execute_console_command(S['world'], command)
    yield wait(.5)
    check('Real menu New Game started a session in the isolated QA namespace',
          bool(prop('ReleaseSessionStarted')) and not bool(prop('ReleaseMenuActive'))
          and str(prop('SaveSlot')).startswith(CAMPAIGN_PREFIX), REPORT['menu_entries'])
    S['step'] = 'new game intro'
    if bool(prop('IntroActive')):
        action('SkipRecollections')
        yield wait(.2)
    if int(prop('Mode')) != 0:
        action('CloseModal')
        yield wait(.1)
    setp('MinimumLineSeconds', 0.01)
    check('Fresh test campaign starts in the present with no v0.2 knowledge',
          int(prop('EraIndex')) == 0 and not prop('PublicChronologyObserved') and int(prop('IdentityRecordMethod')) == 0)
    trust_before = int(prop('HealerTrust'))

    S['step'] = 'present cast'
    for role, row in CAST['roles'].items():
        actor = cast_actor(row['tag'])
        expected = row['era'] == 'present'
        check(role + ' era visibility in the present', visible(actor) == expected and bool(actor.get_actor_enable_collision()) == expected)
    for role in ['ShrineKeeper', 'LanternKeeper', 'Archivist']:
        row = CAST['roles'][role]
        prompt = yield from talk_to(role, 'SC.' + role, row['lines'])
        check(role + ' prompt names the person', prompt == row['prompt'], prompt)

    S['step'] = 'public chronology'
    board = [a for a in tagged('present.chronology')]
    check('One public chronology board', len(board) == 1, len(board))
    yield from focus(board[0], 'chronology board')
    check('Chronology prompt', 'public chronology' in str(prop('Prompt')).lower(), str(prop('Prompt')))
    action('Interact')
    yield wait(.05)
    check('Chronology opens Order V-17 and records only its observation',
          'Order V-17' in str(prop('PanelText')) and bool(prop('PublicChronologyObserved'))
          and MARKERS['chronology'] in [str(x) for x in prop('TrustEventIds')] and int(prop('HealerTrust')) == trust_before)
    action('CloseDocument')
    yield wait(.05)
    if int(prop('Mode')) != 0:
        action('CloseModal')
        yield wait(.05)
    row = CAST['roles']['Archivist']
    yield from talk_to('Archivist', 'SC.Archivist.chronology', row['lines_chronology'], 'Archivist after the chronology')

    S['step'] = 'past cast (fixture)'
    fixture(1, int(prop('StormCover')), int(prop('LinenState')))
    check('Era fixture applied through the transient helper', int(prop('EraIndex')) == 1)
    action('ApplyWorldState')
    yield wait(.1)
    for role, row in CAST['roles'].items():
        actor = cast_actor(row['tag'])
        expected = row['era'] == 'past'
        check(role + ' era visibility in the past', visible(actor) == expected and bool(actor.get_actor_enable_collision()) == expected)
    for role in ['Baker', 'Carpenter', 'Boatwright', 'Fisherwoman', 'HarborClerk', 'Tavi']:
        row = CAST['roles'][role]
        prompt = yield from talk_to(role, 'SC.' + role, row['lines'])
        check(role + ' prompt names the person', prompt == row['prompt'], prompt)

    # The identity suite approaches the harbour clerk from fixed offsets around her; on the Verdant street some of
    # those points lie beyond the street edge. This block proves the approach a player can actually make: the
    # clerk and the worker at the harbour shelter, selected by the suite's own front-of-the-NPC camera rays
    # (the first point is 165 cm in front of each, on the street), with the register prompt.
    S['step'] = 'harbour shelter approach (fixture: harbour shelter)'
    fixture(1, 2, 3)
    check('Harbour shelter fixture applied through the transient helper',
          int(prop('StormCover')) == 2 and int(prop('EraIndex')) == 1 and int(prop('LinenState')) == 3)
    action('ApplyWorldState')
    yield wait(.1)
    enna = cast_actor('cast.clerk')
    tavi = cast_actor('cast.dockworker')
    points = INTEGRATION['identity_points']
    for actor, key in [(enna, 'QuestIdentityClerkActor:harbor'), (tavi, 'QuestIdentityWorkerActor:harbor')]:
        p = points[key]['point']
        loc = actor.get_actor_location()
        check(actor.get_actor_label() + ' moves to the harbour shelter', abs(loc.x - p[0]) < 2 and abs(loc.y - p[1]) < 2 and abs(loc.z - p[2]) < 2,
              {'actual': xyz(loc), 'expected': p})
    yield from focus(enna, 'Enna at the harbour shelter')
    check('Register prompt offers the optional conversation at the harbour shelter', 'register' in str(prop('Prompt')).lower(), str(prop('Prompt')))
    yield from focus(tavi, 'Tavi at the harbour shelter')

    S['step'] = 'register consent scene (fixture: clinic shelter)'
    fixture(1, 1, 3)
    check('Clinic shelter fixture applied through the transient helper',
          int(prop('StormCover')) == 1 and int(prop('EraIndex')) == 1 and int(prop('LinenState')) == 3)
    action('ApplyWorldState')
    yield wait(.1)
    enna = cast_actor('cast.clerk')
    tavi = cast_actor('cast.dockworker')
    points = INTEGRATION['identity_points']
    for actor, key in [(enna, 'QuestIdentityClerkActor:clinic'), (tavi, 'QuestIdentityWorkerActor:clinic')]:
        p = points[key]['point']
        loc = actor.get_actor_location()
        check(actor.get_actor_label() + ' moves to the clinic shelter', abs(loc.x - p[0]) < 2 and abs(loc.y - p[1]) < 2 and abs(loc.z - p[2]) < 2,
              {'actual': xyz(loc), 'expected': p})
    yield from focus(enna, 'Enna at the clinic')
    check('Register prompt offers the optional conversation', 'register' in str(prop('Prompt')).lower(), str(prop('Prompt')))
    action('Interact')
    yield wait(.05)
    check('Register scene starts with the authored opening', str(prop('DialogueNodeId')) == IDENT['scene'] + '.start'
          and bool(prop('IdentitySceneSeen')) and MARKERS['identity_seen'] in [str(x) for x in prop('TrustEventIds')])
    opening = yield from read_dialogue('Register scene opening')
    check('Opening lines match the authored scene', [t for _, t in opening] == [t for _, t in IDENT['start']], opening)
    check('Three consent options are offered', bool(prop('DialogueWaitingChoice')) and int(prop('DialogueChoiceCount')) == 3)
    action('ChooseDialogue', 2)
    yield wait(.05)
    sealed = yield from read_dialogue('Register scene: initials and sealed note')
    check('Sealed-note lines match', [t for _, t in sealed] == [t for _, t in IDENT['choices'][1]['lines']], sealed)
    check('Only the explicit sealed-note agreement is committed',
          int(prop('IdentityRecordMethod')) == 2 and bool(prop('IdentityCustodianAccepted'))
          and MARKERS['identity'] + '2' in [str(x) for x in prop('TrustEventIds')] and int(prop('Mode')) == 0
          and int(prop('HealerTrust')) == trust_before)
    yield from focus(tavi, 'Tavi at the clinic')
    action('Interact')
    yield wait(.05)
    check('Tavi repeats the agreed handling', str(prop('DialogueNodeId')) == IDENT['scene'] + '.repeat_2')
    yield from read_dialogue('Tavi repeat')

    S['step'] = 'save and restart'
    action('SaveProgress')
    yield wait(.3)
    campaign_slot = str(prop('SaveSlot'))
    save_file = SAVE_DIR / (campaign_slot + '.sav')
    check('Save succeeded through the guarded native save', bool(prop('SaveSucceeded')) and save_file.exists()
          and save_file.read_bytes()[:8] == b'YDAYSG01', {'slot': campaign_slot, 'file': str(save_file)})
    REPORT['campaign_save'] = {'slot': campaign_slot, 'bytes': save_file.stat().st_size, 'sha256': sha(save_file)}
    LEVEL.editor_request_end_play()
    yield until(lambda: not LEVEL.is_in_play_in_editor(), 'end PIE before restart')
    S['menu_entry'] = 'continue'
    LEVEL.editor_request_begin_play()
    yield until(ready, 'release menu Continue into the saved QA campaign after a PIE restart', 180)
    yield wait(.8)
    if int(prop('Mode')) != 0:
        action('CloseModal')
        yield wait(.1)
    setp('MinimumLineSeconds', 0.01)
    check('Real menu Continue reopened the same guarded campaign',
          bool(prop('ReleaseSessionStarted')) and not bool(prop('ReleaseMenuActive'))
          and str(prop('SaveSlot')) == campaign_slot, REPORT['menu_entries'])
    check('Restart restores v0.2 observations from TrustEventIds markers',
          bool(prop('PublicChronologyObserved')) and bool(prop('IdentitySceneSeen'))
          and int(prop('IdentityRecordMethod')) == 2 and bool(prop('IdentityCustodianAccepted'))
          and not bool(prop('OrderRegisterObserved')) and int(prop('MotherJourneyIntention')) == 0,
          {k: str(prop(k)) for k in ['PublicChronologyObserved', 'IdentitySceneSeen', 'IdentityRecordMethod', 'TrustEventIds', 'EraIndex', 'StormCover']})
    check('Restart restores the committed era and shelter', int(prop('EraIndex')) == 1 and int(prop('StormCover')) == 1)
    loc = cast_actor('cast.clerk').get_actor_location()
    p = points['QuestIdentityClerkActor:clinic']['point']
    check('Enna is back at the clinic shelter after load', abs(loc.x - p[0]) < 2 and abs(loc.y - p[1]) < 2, xyz(loc))
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
    REPORT['qa_files_written'] = sorted(p.name for p in SAVE_DIR.iterdir() if p.is_file() and p.name.startswith(NAMESPACE)) if SAVE_DIR.exists() else []
    REPORT['success'] = ('error' not in REPORT and REPORT.get('passed', False) and all(c['passed'] for c in REPORT['checks'])
                         and REPORT['protected_unchanged'] and 'cleanup_error' not in REPORT)
    write()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.log('SUPPORTING_CAST_RUNTIME_VALIDATION ' + str(REPORT['success']))
    unreal.SystemLibrary.quit_editor()


runner = scenario()


def tick(delta):
    global pending, deadline
    try:
        if closing:
            if not LEVEL.is_in_play_in_editor():
                complete_finish()
            return
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
            pending = None
        pending = next(runner)
        deadline = now + pending.get('seconds', pending.get('timeout', 60))
        write()
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())


if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'SupportingCastQA'):
    raise RuntimeError('Explicit -SupportingCastQA required')
write()
handle = unreal.register_slate_post_tick_callback(tick)
