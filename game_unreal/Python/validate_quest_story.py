"""Run the established four-route story acceptance on Verdant_Desktop.

The existing tested harness is reused with explicit map/save/report substitutions.
This is a native desktop PIE regression; XR controls, headset comfort, hardware
input and device performance are covered separately. No story flags are seeded.
"""
from pathlib import Path
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
xr_mode = '-queststoryxr' in unreal.SystemLibrary.get_command_line().lower()
if root.parent.name != 'Quest_20261025':
    raise RuntimeError('Quest regression refuses a different project')
source = (root/'Python/validate_brief_m2.py').read_text(encoding='utf-8')
old_guard = """BASELINE_PATH=ROOT.parent/'baseline_manifest.json'
if not BASELINE_PATH.exists():raise RuntimeError('Run this harness only in the isolated illustrated-brief development copy')
BASELINE=json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
if Path(BASELINE['development_copy']).resolve()!=ROOT.parent:raise RuntimeError('Development-copy location does not match its baseline manifest')
ORIGINAL_ROOT=Path(BASELINE['original_workspace'])"""
new_guard = """BASELINE_PATH=ROOT.parent/'quest_baseline_manifest.json'
BASELINE=json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
if Path(BASELINE['quest_copy']).resolve()!=ROOT.parent:raise RuntimeError('Quest baseline mismatch')
ORIGINAL_ROOT=Path(BASELINE['original_workspace'])"""
if source.count(old_guard) != 1:
    raise RuntimeError('Acceptance harness guard changed; review adaptation before running')
source = source.replace(old_guard,new_guard)
replacements = {
    "MAP_ROOT='/Game/BriefTest/Maps/'": "MAP_ROOT='/Game/Quest/Maps/'",
    "'Quarter_FirstPerson'": "'Verdant_Desktop'",
    "'Quarter_ThirdPerson'": "'Verdant_Desktop'",
    'Yesterday_Brief_20261025': 'Yesterday_Quest_20261025',
    'Yesterday_Brief_M2_QA_': 'Yesterday_Quest_Story_QA_',
    'brief_m2_runtime_validation.json': 'quest_story_runtime_validation.json',
    "'brief_m2'": "'quest_story'",
    'brief_m2_qa.log': 'quest_story_qa.log',
    'Native PIE illustrated-brief M2 and four-route regression':
        'Native desktop PIE Quest-map four-route story regression',
    'runner=scenario()': 'QuestTickGuard=False\nrunner=scenario()',
    'global pending,deadline':
        'global pending,deadline,QuestTickGuard\n    if QuestTickGuard:return\n    QuestTickGuard=True',
    'except Exception:finish(traceback.format_exc())':
        'except Exception:finish(traceback.format_exc())\n    finally:QuestTickGuard=False',
    "fixture=ROOT/'Saved/SaveGames/Yesterday_Automation_A_v1_20261024T151953_576332_FirstPerson.sav'":
        "fixture=ROOT.parent.parent/'Brief_20261025/game_unreal/Saved/SaveGames/Yesterday_Automation_A_v1_20261024T151953_576332_FirstPerson.sav'",
}
for old,new in replacements.items():
    if old not in source:
        raise RuntimeError('Acceptance harness adaptation no longer matches: '+old)
    source=source.replace(old,new)
if xr_mode:
    # Test-only camera aiming is explicit: physical HMD tracking is never
    # simulated by controller rotation. Focus placements remain setup fixtures,
    # not evidence that the authored teleport network reaches every object.
    old_aim = """def aim(actor):
    S['controller'].set_control_rotation(unreal.MathLibrary.find_look_at_rotation(S['camera'].get_camera_location(),point(actor)))"""
    new_aim = """def aim(actor):
    camera=S['pawn'].get_component_by_class(unreal.CameraComponent)
    look=unreal.MathLibrary.find_look_at_rotation(camera.get_world_location(),point(actor))
    relative=unreal.MathLibrary.inverse_transform_rotation(S['pawn'].get_actor_transform(),look)
    camera.set_editor_property('relative_rotation',relative)"""
    if source.count(old_aim)!=1:
        raise RuntimeError('XR camera fixture no longer matches the acceptance harness')
    source=source.replace(old_aim,new_aim)
    for old,new in {
        'Verdant_Desktop':'Verdant_VR',
        'quest_story_runtime_validation.json':'quest_xr_story_runtime_validation.json',
        "'quest_story'":"'quest_xr_story'",
        'quest_story_qa.log':'quest_xr_story_qa.log',
        'Yesterday_Quest_Story_QA_':'Yesterday_Quest_XR_Story_QA_',
        'Native desktop PIE Quest-map four-route story regression':
            'Native XR Character PIE four-route story regression; simulated aim and setup placements',
    }.items():source=source.replace(old,new)
exec(compile(source,str(root/'Python/validate_brief_m2.py'),'exec'),globals())
