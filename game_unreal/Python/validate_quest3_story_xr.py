"""The four-route v0.2 story acceptance driven with the Quest 3 XR pawn (desktop fallback, no HMD).

Run with -ReleaseStoryQA -QuestStoryV2QA -Quest3XRStoryQA and a fresh short -UserDir. It layers on
validate_quest_story_v02.py exactly as that file layers on validate_release_story.py: the established harness
text is loaded, then only these points change — the editor world's game mode is the XR game mode (a transient
World Settings fixture, restored and never saved), camera aiming rotates the HMD-locked QuestCamera instead of
the control rotation, and the report labels. Real menu New Game / Continue, native dialogue, scene rays, the
guarded saves and the four consequence routes are unchanged. Not headset, controller or packaged evidence.
"""
from pathlib import Path
import ast
import unreal

X_ROOT = Path(unreal.Paths.project_dir()).resolve()
if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3XRStoryQA'):
    raise RuntimeError('Root-queued -Quest3XRStoryQA is required')
X_GAME_MODE = '/Game/Quest/XR/BP_QuestGameMode.BP_QuestGameMode_C'
X_PAWN = '/Game/Quest/XR/BP_QuestCharacter.BP_QuestCharacter_C'
X_PARENT_FILE = X_ROOT / 'Python/validate_quest_story_v02.py'
X_PARENT = X_PARENT_FILE.read_text(encoding='utf-8')
X_TREE = ast.parse(X_PARENT)
X_ENDING = "exec(compile(source, str(V2_ROOT / 'Python/validate_brief_m2.py'), 'exec'), globals())"
if ast.get_source_segment(X_PARENT, X_TREE.body[-1]) != X_ENDING:
    raise RuntimeError('Review changed the v0.2 harness before adapting it for the XR pawn')
X_PREFIX, X_SEPARATOR, X_SUFFIX = X_PARENT.rpartition(X_ENDING)
if not X_SEPARATOR or X_SUFFIX.strip():
    raise RuntimeError('The v0.2 launch is no longer the checked final statement')
X_OLD_FILE = globals().get('__file__')
globals()['__file__'] = str(X_PARENT_FILE)
try:
    # Builds the reviewed v0.2 harness text (which itself builds the release text) and the unsaved profile
    # fixture; registers no ticker and begins no gameplay until the final exec below.
    exec(compile(X_PREFIX, str(X_PARENT_FILE), 'exec'), globals())
finally:
    globals()['__file__'] = X_OLD_FILE


def x_replace(old, new):
    global source
    if source.count(old) != 1:
        raise RuntimeError('Changed XR acceptance point: ' + old[:140])
    source = source.replace(old, new)


# 1. Transient XR game mode on the freshly loaded editor world, right before each case begins play.
x_replace("""                                  'policy':'Exact SHA-pinned trusted fixture; never arbitrary corrupt input'}
    LEVEL.editor_request_begin_play()""", """                                  'policy':'Exact SHA-pinned trusted fixture; never arbitrary corrupt input'}
    x_settings=EDITOR.get_editor_world().get_world_settings()
    S['x_game_mode_before']=(x_settings,x_settings.get_editor_property('default_game_mode'))
    x_settings.set_editor_property('default_game_mode',unreal.load_class(None,X_GAME_MODE))
    LEVEL.editor_request_begin_play()""")
x_replace("""def restore_override():
    pair=S.get('editor_override')""", """def restore_override():
    x_pair=S.get('x_game_mode_before')
    if x_pair:
        try:x_pair[0].set_editor_property('default_game_mode',x_pair[1])
        except Exception:REPORT.setdefault('cleanup_errors',[]).append(traceback.format_exc())
        S['x_game_mode_before']=None
    pair=S.get('editor_override')""")
# 2. Aim the HMD-locked camera of the XR pawn; the desktop pawn keeps the control-rotation path.
replace_function('aim', '''def aim(actor):
    target=point(actor)
    pawn=S['pawn']
    camera=pawn.get_component_by_class(unreal.CameraComponent)
    if camera is not None and camera.get_name()=='QuestCamera':
        look=unreal.MathLibrary.find_look_at_rotation(camera.get_world_location(),target)
        root=pawn.get_actor_rotation()
        camera.set_relative_rotation(unreal.Rotator(pitch=look.pitch-root.pitch,yaw=look.yaw-root.yaw,roll=0),False,True)
    else:
        S['controller'].set_control_rotation(unreal.MathLibrary.find_look_at_rotation(S['camera'].get_camera_location(),target))
''')
# 3. The release ending gates desktop world input through the controller's ignore flags; the XR adapter never
#    sets them (no joystick locomotion exists and tracked head look must stay live), so for the XR pawn the gate is
#    the menu itself plus the zero walk speed.
x_replace("""              str(prop('ReleaseMenuTitle'))=='End of Chapters I–II — Early Playable' and
              S['controller'].is_move_input_ignored() and S['controller'].is_look_input_ignored())""",
          """              str(prop('ReleaseMenuTitle'))=='End of Chapters I–II — Early Playable' and
              ((S['controller'].is_move_input_ignored() and S['controller'].is_look_input_ignored()) or x_xr_gated()))""")
x_replace("def restore_override():", """def x_xr_gated():
    pawn=S['pawn']
    movement=pawn.get_component_by_class(unreal.CharacterMovementComponent)
    return (pawn.get_class().get_path_name()==X_PAWN and movement is not None and
            float(movement.get_editor_property('max_walk_speed'))==0.0 and bool(prop('ReleaseMenuActive')))


def restore_override():""")
# 4. The possessed pawn must be the Quest Character on every fresh route.
x_replace("        check('Fresh route uses only its isolated save slot',str(prop('SaveSlot')).startswith(TEST_SLOT_PREFIX+STAMP))",
          """        check('XR game-mode fixture possesses the Quest Character',S['pawn'].get_class().get_path_name()==X_PAWN,S['pawn'].get_class().get_path_name())
        check('Fresh route uses only its isolated save slot',str(prop('SaveSlot')).startswith(TEST_SLOT_PREFIX+STAMP))""")
x_replace("REPORT['revision_scope']='Four actual routes, three explicit journey intentions, separate chronology inspection/skip/return read, optional dated-record skip, native committed reloads, uncertainty and original Tomorrow ending.'",
          """REPORT['revision_scope']='Four actual routes, three explicit journey intentions, separate chronology inspection/skip/return read, optional dated-record skip, native committed reloads, uncertainty and original Tomorrow ending.'
REPORT['xr_pawn_fixture']={'game_mode':X_GAME_MODE,'pawn':X_PAWN,'camera_aim':'QuestCamera relative rotation (HMD-locked camera, no HMD)','world_settings_saved':False,'headset_tested':False,'physical_controller_input_tested':False}""")
for old, new in [('quest_story_v02_runtime_validation.json', 'quest3_xr_story_runtime_validation.json'),
                 ("'quest_story_v02'", "'quest3_xr_story'"), ('YRV02QA_', 'YQ3XRQA_')]:
    if old not in source:
        raise RuntimeError('Runtime output label changed: ' + old)
    source = source.replace(old, new)
ast.parse(source)
exec(compile(source, str(X_ROOT / 'Python/validate_brief_m2.py'), 'exec'), globals())
