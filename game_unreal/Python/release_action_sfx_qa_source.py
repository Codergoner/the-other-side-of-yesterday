"""Pure source expansion for a separate action-SFX native QA scope.

Never imports Unreal, launches a process or executes the assembled game test.
"""
from pathlib import Path
import ast


def expand(source, helper_file=None):
    helper_file = Path(__file__).with_name('release_action_sfx_qa_helpers.py') if helper_file is None else Path(helper_file)
    helpers = helper_file.read_text(encoding='utf-8')
    ast.parse(helpers)
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise RuntimeError('Review changed SFX acceptance point: '+old[:140])
        source = source.replace(old, new)
    replace("def action(name,*args):return S['manager'].call_method(name,args=tuple(args))",
            helpers+"\n\ndef action(name,*args):return sfx_action(name,*args)")
    replace("    yield from audio_settled('Continue: '+label, expected['EraIndex'])",
            "    yield from audio_settled('Continue: '+label, expected['EraIndex'])\n    yield from sfx_boot_silence('Continue: '+label)")
    replace("    yield from audio_settled('pinned legacy Continue')",
            "    yield from audio_settled('pinned legacy Continue')\n    yield from sfx_boot_silence('pinned legacy Continue')\n    sfx_finite_assets()")
    replace("        yield from audio_settled('fresh New Game')",
            "        yield from audio_settled('fresh New Game')\n        yield from sfx_boot_silence('fresh New Game')\n        sfx_finite_assets()")
    replace("    before_audio=audio_state()\n    action('ConfirmWatch')",
            "    before_audio=audio_state()\n    before_sfx=sfx_state()\n    action('ConfirmWatch')")
    replace("    yield from settle_transition(expected_era)\n    after_audio=",
            "    yield from settle_transition(expected_era)\n    yield from sfx_transition_after(before_sfx,str(expected_era))\n    after_audio=")
    replace("        for number in [1,2]:\n            yield from interact('BenchActor')",
            "        for number in [1,2]:\n            calibration_audio_before=sfx_state()\n            yield from interact('BenchActor')")
    replace("            check('Calibration stable test '+str(number)+' completes',int(prop('CalibrationTests'))>=number)",
            """            check('Calibration stable test '+str(number)+' completes',int(prop('CalibrationTests'))>=number)
            calibration_audio_after=sfx_state()
            check('Only the second stable test produces calibration success audio',
                  calibration_audio_after['plays']-calibration_audio_before['plays']==(1 if number==2 else 0) and
                  calibration_audio_after['suppressed']==calibration_audio_before['suppressed'],
                  {'number':number,'before':calibration_audio_before,'after':calibration_audio_after})
            if number==2: yield from sfx_finite_tail(calibration_audio_before,3.1,'real calibration success')""")
    replace("    action('Interact');yield wait(.04)\n    check_channels()",
            """    cloth_before=sfx_state()
    action('Interact');yield wait(.04)
    cloth_after=sfx_state()
    if cloth_after['plays']==cloth_before['plays']+1 and cloth_after['cue']=='cloth':
        yield from sfx_finite_tail(cloth_before,1.5,'real cloth producer '+ref)
    check_channels()""")
    replace("        action('RotateDial',-1)\n        check('Anticlockwise dial selects the authored earlier era only'",
            "        if case is CASES[0]: yield from sfx_watch_pcm_suite()\n        action('RotateDial',-1)\n        check('Anticlockwise dial selects the authored earlier era only'")
    replace("        check('Blocked return explains the pending task',len(str(prop('Notice'))+str(prop('Objective')))>12)",
            "        check('Blocked return explains the pending task',len(str(prop('Notice'))+str(prop('Objective')))>12)\n        yield from sfx_rejected_confirm_settled()")
    replace("log_path=Path(unreal.Paths.project_log_dir())/'YesterdayHarbor.log'",
            """log_match=__import__('re').search(r'(?i)(?:^|\\s)-abslog=(?:\"([^\"]+)\"|(\\S+))',unreal.SystemLibrary.get_command_line())
    log_path=Path(log_match.group(1) or log_match.group(2)) if log_match else Path(unreal.Paths.project_log_dir())/'YesterdayHarbor.log'""")
    replace("        REPORT['graphics_log_path']=str(log_path)",
            """        REPORT['graphics_log_path']=str(log_path)
    REPORT['action_sfx_actual_d3d11']=any('D3D11' in line for line in REPORT.get('graphics_log_evidence',[]))""")
    replace("and not REPORT.get('cleanup_errors')\n    write()",
            "and not REPORT.get('cleanup_errors') and REPORT.get('action_sfx_actual_d3d11',False)\n    write()")
    for old, new in {'release_story_audio_validation.json': 'release_action_sfx_validation.json',
                     "'release_story_audio'": "'release_action_sfx'", 'YRAudioStoryQA_': 'YRSfxQA_',
                     'RELEASE_STORY_AUDIO_VALIDATION': 'RELEASE_ACTION_SFX_VALIDATION'}.items():
        if old not in source:
            raise RuntimeError('Missing additive SFX report label '+old)
        source = source.replace(old, new)
    replace("REPORT['native_save_guard_active']=", """REPORT['action_sfx_qa_scope']='Actual native producer commits/counters, NewGame/Continue/ApplyWorldState silence, finite waves/tails and actual Master0/pause mixer PCM; synthetic native action/HUD callbacks. No direct quest-flag writes, packaged, physical-input, loudspeaker or headset claim.'
REPORT['action_sfx_helper_sha256']=hashlib.sha256((ROOT/'Python/release_action_sfx_qa_helpers.py').read_bytes()).hexdigest()
REPORT['native_save_guard_active']=""")
    ast.parse(source)
    return source
