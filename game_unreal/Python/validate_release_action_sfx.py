"""Queued four-route native PIE action-SFX QA; no native asset writes.

Requires -ReleaseStoryQA -ReleaseStoryAudioQA -ReleaseActionSfxQA, fresh short
-UserDir, D3D11 and audio enabled. Root owns the serialized native queue.
"""
from pathlib import Path
import ast
import hashlib
import json
import sys
import traceback
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(root/'Python'))
import release_action_sfx_qa_source as sfx_source
import release_file_io as fio

try:
    command = unreal.SystemLibrary.get_command_line()
    if not unreal.SystemLibrary.parse_param(command, 'ReleaseActionSfxQA'):
        raise RuntimeError('Root queued -ReleaseActionSfxQA is required')
    if '-d3d11' not in command.lower() or '-nosound' in command.lower() or '-nullrhi' in command.lower():
        raise RuntimeError('Action SFX QA requires actual D3D11 with sound enabled')
    installed = json.loads((root/'release_action_sfx_report.json').read_text(encoding='utf-8'))
    if not installed.get('success') or installed.get('reverted'):
        raise RuntimeError('Complete the real native action SFX installation before its QA')
    wrapper_file = root/'Python/validate_release_story_audio.py'
    wrapper = wrapper_file.read_text(encoding='utf-8')
    ending = "exec(compile(source, str(root / 'Python/validate_brief_m2.py'), 'exec'), globals())"
    if wrapper.count(ending) != 1:
        raise RuntimeError('Review changed story-audio wrapper before adapting it')
    # Retain its native audio settings, unsaved profile fixture and actual
    # four-route adaptation, but defer its tick callback until we extend it.
    wrapper = wrapper.replace("'validation/release_story_audio_source'",
                              "'validation/release_action_sfx_audio_base_source'")
    outer_file = __file__
    try:
        __file__ = str(wrapper_file)
        exec(compile(wrapper.replace(ending, 'SFX_STORY_SOURCE = source'), str(wrapper_file), 'exec'), globals())
    finally:
        __file__ = outer_file
    source = sfx_source.expand(SFX_STORY_SOURCE)
    # Add the installed SFX asset/waves to the existing manager/map/config guard.
    marker = "REPORT['protected_assets_before']={str(p):hash_file(p) for p in PROTECTED_ASSETS}"
    if source.count(marker) != 1:
        raise RuntimeError('Review changed protected-asset acceptance point')
    extra = """PROTECTED_ASSETS += [Path(path) for path in ACTION_SFX_INSTALLED['asset_fingerprints']]
PROTECTED_ASSETS += [Path(path) for path in ACTION_AUDIO_IMPORTED['asset_fingerprints']]
PROTECTED_ASSETS=list(dict.fromkeys(PROTECTED_ASSETS))
"""
    imported = json.loads((root/'release_audio_import_report.json').read_text(encoding='utf-8'))
    source = source.replace(marker, extra+marker)
    ACTION_SFX_INSTALLED, ACTION_AUDIO_IMPORTED = installed, imported
    source = source.replace("REPORT['action_sfx_helper_sha256']=",
        "REPORT['action_sfx_wrapper_sha256']='"+fio.sha(__file__)+"'\nREPORT['action_sfx_expander_sha256']='"+
        fio.sha(sfx_source.__file__)+"'\nREPORT['action_sfx_helper_sha256']=", 1)
    ast.parse(source)
    folder = root/'validation/release_action_sfx_source'
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'expanded_current.py').write_text(source, encoding='utf-8')
    exec(compile(source, str(root/'Python/validate_brief_m2.py'), 'exec'), globals())
except Exception:
    for name, value in globals().get('AUDIO_PIE_SETTINGS_BEFORE', {}).items():
        AUDIO_PIE_SETTINGS.set_editor_property(name, value)
    if 'AUDIO_BACKGROUND_BEFORE' in globals():
        AUDIO_MISC_SETTINGS.set_editor_property('bAllowBackgroundAudio', AUDIO_BACKGROUND_BEFORE)
    (root/'release_action_sfx_validation.json').write_text(json.dumps(
        {'success': False, 'scope': __doc__, 'error': traceback.format_exc()}, indent=2), encoding='utf-8')
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.quit_editor()
