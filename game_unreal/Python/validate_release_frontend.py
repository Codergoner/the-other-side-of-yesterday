"""Read-only full-editor PIE checks; campaign/profile writes stay in QA slots.

Use a dedicated -UserDir for config/save isolation. This exercises native hitbox
callbacks and controller input, not physical keyboard/mouse or a packaged game.
"""
from pathlib import Path
import datetime
import hashlib
import json
import math
import sys
import time
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Release_20261026'
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
PROFILE = 'Yesterday_Release_MenuQA_' + STAMP
PREFIX = PROFILE + '_'
OUT = ROOT / 'validation/release_frontend' / STAMP
OUT.mkdir(parents=True, exist_ok=True)
MAP = '/Game/Quest/Maps/Verdant_Desktop'
MANAGER_CLASS = '/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C'
SAVE_CLASS = '/Game/Opening/Blueprints/BP_OpeningSave.BP_OpeningSave_C'
REPORT_PATH = ROOT / 'release_frontend_validation.json'
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
try:
    unreal.get_default_object(unreal.EditorPerformanceSettings).set_editor_property('throttle_cpu_when_not_foreground', False)
except Exception:
    pass  # Optional editor module; runtime checks do not depend on it.
S = {'manager': None, 'pawn': None, 'pc': None, 'world': None, 'override': None, 'step': 'startup'}
REPORT = {'success': False, 'run': STAMP, 'checks': [], 'screenshots': [], 'qa_profile': PROFILE,
          'physical_input_tested': False, 'package_playtested': False, 'headset_tested': False,
          'scope': 'Native release frontend PIE, real HUD hit-box event callbacks and synthetic native controller input; separate QA profiles/campaigns only'}
pending = None
deadline = 0
handle = None
ticking = False
closing = False


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
protected_assets = list((ROOT / 'Config').glob('*.ini')) + list((ROOT / 'Content/Quest/Maps').glob('*.umap'))
protected_assets += [ROOT / ('Content/' + p) for p in ['Opening/Blueprints/BP_OpeningActions.uasset',
                     'Opening/Blueprints/BP_OpeningHUD.uasset', 'Release/Blueprints/BP_ReleaseProfile.uasset']]
protected_saves = []
for folder in [ROOT / 'Saved/SaveGames', ROOT.parent.parent / 'Quest_20261025/game_unreal/Saved/SaveGames',
               ROOT.parent.parent / 'Brief_20261025/game_unreal/Saved/SaveGames',
               ROOT.parent.parent.parent / 'game_unreal/Saved/SaveGames',
               Path.home() / 'AppData/Local/YesterdayHarbor/Saved/SaveGames']:
    if folder.exists(): protected_saves.extend(folder.glob('*.sav'))
REPORT['protected_assets_before'] = {str(p): sha(p) for p in protected_assets}
REPORT['protected_saves_before'] = {str(p): sha(p) for p in protected_saves}


def write():
    REPORT['step'] = S['step']
    text = json.dumps(REPORT, indent=2, default=str)
    REPORT_PATH.write_text(text, encoding='utf-8')
    (OUT / 'validation.json').write_text(text, encoding='utf-8')


def check(name, ok, details=None):
    REPORT['checks'].append({'name': name, 'passed': bool(ok), 'details': details})
    write()
    if not ok: raise AssertionError(name + ': ' + str(details))


def wait(seconds=.2): return {'seconds': seconds}
def until(fn, name, timeout=30): return {'predicate': fn, 'name': name, 'timeout': timeout}
def prop(name): return S['manager'].get_editor_property(name)
def call(name, *args): return S['manager'].call_method(name, args=tuple(args))
def save_path(slot): return Path(unreal.Paths.project_saved_dir()).resolve() / 'SaveGames' / (str(slot) + '.sav')


def manager(world):
    result = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.load_class(None, MANAGER_CLASS))
    assert len(result) == 1
    return result[0]


def ready():
    world = EDITOR.get_game_world()
    if not world: return False
    mgr = manager(world)
    pawn = unreal.GameplayStatics.get_player_character(world, 0)
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    if not (pawn and pc and mgr.get_editor_property('ReleaseBooted')): return False
    S.update(world=world, manager=mgr, pawn=pawn, pc=pc)
    return bool(mgr.get_editor_property('ReleaseMenuActive'))


def restore():
    if S['override']:
        actor, values = S['override']
        for key, value in values.items(): actor.set_editor_property(key, value)
        S['override'] = None


def start(profile):
    edit = manager(EDITOR.get_editor_world())
    S['override'] = (edit, {name: edit.get_editor_property(name) for name in ['ReleaseProfileSlot', 'ReleaseSavePrefix']})
    edit.set_editor_property('ReleaseProfileSlot', profile)
    edit.set_editor_property('ReleaseSavePrefix', PREFIX)
    LEVEL.editor_request_begin_play()


def click(index):
    hud = S['pc'].get_hud()
    hud.call_method('ReceiveHitBoxClick', args=(unreal.Name('ReleaseRow' + str(index)),))


def screenshot(name):
    path = OUT / (name + '.png')
    # AutomationLibrary forces all editor assets/shaders to finish synchronously
    # and can block a Slate callback. Queue the ordinary native viewport command.
    unreal.SystemLibrary.execute_console_command(S['world'], 'HighResShot 1600x900 filename="' + path.as_posix() + '"')
    REPORT['screenshots'].append(str(path))
    return until(lambda: path.exists() and path.stat().st_size > 20000, 'screenshot ' + name)


def scenario():
    S['step'] = 'load and isolated boot'
    check('Desktop map loads', LEVEL.load_level(MAP))
    # Build an unsaved /Temp function before PIE solely to construct the
    # intentionally invalid save copy. Do not change SaveClass edit flags or
    # add a shipped debug function to the game manager.
    sys.path.insert(0, str(ROOT / 'Python'))
    import opening_graph as og
    fixture = og.blueprint('/Temp/BP_ReleaseVersionFixture_' + STAMP, unreal.Actor)
    version_graph = og.function(fixture, 'MakeFutureCopy', inputs={'Target': og.object_type(SAVE_CLASS)})
    setter = version_graph.set('SchemaVersion', 999, owner=version_graph.input('Target'), class_path=SAVE_CLASS)
    og.link(version_graph.entry, og.pin_in(setter))
    pointer_graph = og.function(fixture, 'PointAtTestCopy', inputs={'Target': og.object_type(MANAGER_CLASS), 'Slot': 'string'})
    pointer = pointer_graph.set('ReleaseSelectedSlot', pointer_graph.input('Slot'), owner=pointer_graph.input('Target'), class_path=MANAGER_CLASS)
    og.link(pointer_graph.entry, og.pin_in(pointer))
    og.compile_bp(fixture, save=False)
    fixture_cdo = unreal.get_default_object(og.L.generated_class(fixture))
    REPORT['fixture_saved_or_cooked'] = False
    start(PROFILE)
    yield until(ready, 'release frontend boot')
    restore()
    for command in ['t.IdleWhenNotForeground 0', 'Slate.bAllowThrottling 0', 'r.ScreenPercentage 100']:
        unreal.SystemLibrary.execute_console_command(S['world'], command)
    check('QA profile override survives initialization', str(prop('ReleaseProfileSlot')) == PROFILE)
    check('Boot is a five-option menu with Continue disabled', int(prop('ReleaseMenuCount')) == 5 and not prop('ReleaseContinueAvailable'))
    check('World movement/look are blocked while the menu is open', S['pc'].is_move_input_ignored() and S['pc'].is_look_input_ignored())
    check('Real native HUD supplies menu click and hover callbacks', S['pc'].get_hud().get_class().get_path_name().endswith('BP_OpeningHUD_C'))
    yield screenshot('TitleFresh')
    S['pc'].get_hud().call_method('ReceiveHitBoxBeginCursorOver', args=(unreal.Name('ReleaseRow3'),))
    check('Native hover event selects its visible row', int(prop('ReleaseMenuSelection')) == 3)
    click(3)
    yield wait()
    check('Native hitbox callback opens credits', int(prop('ReleaseMenuScreen')) == 2 and 'Epic Games' in str(prop('ReleaseMenuBody')))
    yield screenshot('Credits')
    click(0)
    yield wait()
    click(2)
    yield wait()
    check('Settings preserves existing rows and exposes Audio', int(prop('ReleaseMenuCount')) == 10 and str(prop('ReleaseRow8')) == 'Audio' and str(prop('ReleaseRow9')) == 'Back')
    user = unreal.GameUserSettings.get_game_user_settings()
    old_vsync = bool(prop('ReleaseVSync'))
    click(2)
    yield wait()
    check('VSync row updates the real engine setting', bool(prop('ReleaseVSync')) != old_vsync and user.is_v_sync_enabled() == prop('ReleaseVSync'))
    click(4)
    yield wait()
    yaw_scale = S['pc'].call_method('GetDeprecatedInputYawScale')
    check('Sensitivity changes the actual controller input scale', abs(yaw_scale - float(prop('ReleaseBaseYaw')) * 1.5) < .001, yaw_scale)
    click(5)
    yield wait()
    pitch_scale = S['pc'].call_method('GetDeprecatedInputPitchScale')
    check('Invert Y changes actual controller pitch scale', pitch_scale * float(prop('ReleaseBasePitch')) < 0, pitch_scale)
    click(6)
    yield wait()
    check('Large text updates the HUD scale preference', abs(float(prop('ReleaseTextScale')) - 1.15) < .001)
    yield screenshot('SettingsLargeText')
    click(9)
    yield wait()
    click(0)
    yield until(lambda: not prop('ReleaseMenuActive') and prop('IntroActive'), 'real New Game starts intro')
    first = str(prop('SaveSlot'))
    check('New Game creates a separate safe campaign slot', first.startswith(PREFIX) and save_path(first).exists(), first)
    call('SkipRecollections')
    yield wait()
    check('Skip recollections commits only the new campaign', prop('IntroSeen') and not prop('IntroActive') and prop('ReleaseWriteAllowed'))
    profile = unreal.GameplayStatics.load_game_from_slot(PROFILE, 0)
    check('Committed campaign updates the profile pointer', str(profile.get_editor_property('ActiveSlot')) == first)
    S['pc'].set_control_rotation(unreal.Rotator())
    S['pc'].add_yaw_input(2)
    S['pc'].add_pitch_input(2)
    yield wait(.1)
    actual = S['pc'].get_control_rotation()
    check('Controller yaw input uses the selected sensitivity', abs((actual.yaw - 2 * yaw_scale + 180) % 360 - 180) < .5, str(actual))
    check('Controller pitch input uses the selected inversion', abs((actual.pitch - 2 * pitch_scale + 180) % 360 - 180) < .5, str(actual))
    first_sha = sha(save_path(first))
    call('OpenPause')
    call('ReleaseShowMain')
    yield wait()
    click(0)
    yield until(lambda: str(prop('SaveSlot')) != first and prop('IntroActive'), 'second independent New Game')
    second = str(prop('SaveSlot'))
    check('Second New Game preserves the first campaign bytes', second.startswith(PREFIX) and sha(save_path(first)) == first_sha)
    call('SkipRecollections')
    yield wait()
    second_sha = sha(save_path(second))
    call('OpenPause'); call('ReleaseShowMain')
    yield wait()
    click(1)
    yield wait()
    check('Continue restores authoritative committed state', str(prop('SaveSlot')) == second and prop('IntroSeen') and not prop('ReleaseMenuActive'))
    save_class = unreal.load_class(None, SAVE_CLASS)
    future_slot = PREFIX + 'future'
    future = unreal.GameplayStatics.create_save_game_object(save_class)
    fixture_cdo.call_method('MakeFutureCopy', args=(future,))
    check('Future fixture is a real typed save with schema999', int(future.get_editor_property('SchemaVersion')) == 999)
    check('Isolated future-version fixture writes', unreal.GameplayStatics.save_game_to_slot(future, future_slot, 0))
    future_sha = sha(save_path(future_slot))
    fixture_cdo.call_method('PointAtTestCopy', args=(S['manager'], future_slot))
    call('ReleaseContinue')
    yield wait()
    check('Future-version save returns to a recovery menu', prop('ReleaseMenuActive') and not prop('ReleaseWriteAllowed') and not prop('ReleaseContinueAvailable'))
    call('SaveProgress')
    check('Rejected load cannot overwrite future or prior valid saves', sha(save_path(future_slot)) == future_sha and sha(save_path(second)) == second_sha)
    corrupt_slot = PREFIX + 'corrupt'
    save_path(corrupt_slot).write_bytes(b'Invalid isolated QA save; never a player file')
    corrupt_sha = sha(save_path(corrupt_slot))
    fixture_cdo.call_method('PointAtTestCopy', args=(S['manager'], corrupt_slot))
    call('ReleaseContinue')
    yield wait()
    call('SaveProgress')
    check('Corrupt save is preserved and does not enable Continue', sha(save_path(corrupt_slot)) == corrupt_sha and not prop('ReleaseContinueAvailable'))
    fixture_cdo.call_method('PointAtTestCopy', args=(S['manager'], second))
    call('ReleaseContinue')
    yield wait()
    check('A valid campaign can still recover after rejected loads', prop('ReleaseWriteAllowed') and not prop('ReleaseMenuActive') and prop('IntroSeen'))
    LEVEL.editor_request_end_play()
    yield until(lambda: not LEVEL.is_in_play_in_editor(), 'end first PIE')
    S['step'] = 'both unreadable profile indexes'
    bad_profile = PROFILE + '_badindexes'
    for name in [bad_profile, bad_profile + '_recovered']:
        save_path(name).write_bytes(b'Invalid isolated QA profile index')
    before = {str(p): sha(p) for p in save_path(bad_profile).parent.glob(PREFIX + '*.sav')}
    start(bad_profile)
    yield until(ready, 'corrupt-index boot')
    restore()
    check('Two unreadable indexes disable profile writes', not prop('ReleaseProfileWritable') and prop('ReleaseMenuActive'))
    click(0)
    yield wait()
    after = {str(p): sha(p) for p in save_path(bad_profile).parent.glob(PREFIX + '*.sav')}
    check('Blocked New Game creates no unreachable campaign and overwrites nothing', before == after and not prop('ReleaseSessionStarted'))
    check('Blocked New Game explains preserved profiles', 'unreadable' in str(prop('ReleaseMenuStatus')) and 'not been changed' in str(prop('ReleaseMenuStatus')))
    yield screenshot('UnreadableProfileRecovery')
    S['step'] = 'complete'


def finish(error=None):
    global closing
    if closing: return
    closing = True
    if error: REPORT['error'] = error
    if LEVEL.is_in_play_in_editor(): LEVEL.editor_request_end_play()
    else: complete()


def complete():
    restore()
    REPORT['protected_assets_after'] = {str(p): sha(p) for p in protected_assets}
    REPORT['protected_saves_after'] = {str(p): sha(p) for p in protected_saves}
    REPORT['assets_unchanged'] = REPORT['protected_assets_before'] == REPORT['protected_assets_after']
    REPORT['saves_unchanged'] = REPORT['protected_saves_before'] == REPORT['protected_saves_after']
    REPORT['success'] = 'error' not in REPORT and REPORT['assets_unchanged'] and REPORT['saves_unchanged'] and all(c['passed'] for c in REPORT['checks'])
    write()
    unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.quit_editor()


runner = scenario()
def tick(delta):
    global pending, deadline, ticking
    if ticking: return
    ticking = True
    try:
        if closing:
            if not LEVEL.is_in_play_in_editor(): complete()
            return
        now = time.monotonic()
        if pending:
            if 'seconds' in pending and now < deadline: return
            if 'predicate' in pending and not pending['predicate']():
                if now > deadline: raise TimeoutError(pending['name'])
                return
            pending = None
        pending = next(runner)
        deadline = now + pending.get('seconds', pending.get('timeout', 30))
        write()
    except StopIteration: finish()
    except Exception: finish(traceback.format_exc())
    finally: ticking = False


write()
handle = unreal.register_slate_post_tick_callback(tick)
