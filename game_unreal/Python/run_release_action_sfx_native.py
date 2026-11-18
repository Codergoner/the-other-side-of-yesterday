"""Root-queued, additive action cue authoring with an immutable local backup.

Full editor only. This script does not provide runtime or perceptual QA.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import release_file_io as io
import install_release_action_sfx as installer


def native_files():
    paths = io.files(ROOT / 'Content', '*.uasset') + io.files(ROOT / 'Content', '*.umap')
    paths += io.files(ROOT / 'Config', '*.ini') + list(ROOT.glob('*.uproject'))
    paths += io.files(ROOT / 'Saved/SaveGames', '*.sav')
    return {str(path): io.sha(path) for path in paths}


def run():
    installer.hero.guard()
    installer.require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseActionSfxWrite'),
                      'Explicit root native writer flag required')
    out = ROOT.parent / 'output/action_sfx_native_runs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    out.mkdir(parents=True, exist_ok=False)
    result = {'success': False, 'run': str(out), 'runtime_qa': False, 'perceptual_audio_approved': False}
    installer.sha = io.sha
    installer.hero.sha = io.sha
    installer.hero.files = native_files
    installer.hero.base.digest = lambda p: io.sha(p) if io.is_file(p) else None
    try:
        backup = {}
        for relative in ['Content/Opening/Blueprints/BP_OpeningActions.uasset', 'Content/Quest/Maps/Verdant_Desktop.umap']:
            source = ROOT / relative
            target = out / 'before' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(io.io_path(source), io.io_path(target))
            installer.require(io.sha(source) == io.sha(target), 'Local native backup did not verify')
            backup[relative] = {'source': str(source), 'backup': str(target), 'sha256': io.sha(source)}
        result['before'] = backup
        (out / 'before.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        first = installer.install()
        result['installation_report'] = str(installer.REPORT)
        result['first_success'] = first.get('success', False)
        after_first = native_files()
        (out / 'after_first_native_sha256.json').write_text(json.dumps(after_first, indent=2), encoding='utf-8')
        repeated = installer.install()
        after_repeat = native_files()
        changed = sorted(p for p in set(after_first) | set(after_repeat) if after_first.get(p) != after_repeat.get(p))
        allowed = {str(ROOT / 'Content/Opening/Blueprints/BP_OpeningActions.uasset'), str(installer.hero.MAP_FILE)}
        installer.require(set(changed).issubset(allowed), 'Repeat changed an unrelated native asset or save')
        installer.require(first['actor_after'] == repeated['actor_after'] and first['helpers_after'] == repeated['helpers_after']
                          and first['hooks'] == repeated['hooks'] and first['guard_calls_before'] == repeated['guard_calls_before'],
                          'Repeated owned actor/graph/save-guard state differs')
        result.update(success=bool(repeated.get('success')), repeated_native_files_identical=not changed,
                      repeated_owned_scene_and_graph_identical=True, repeated_reserialized_files=changed,
                      namespace=repeated.get('namespace'), existing_native_files_verified=len(after_first),
                      all13_native_guard_calls_unchanged=repeated.get('all13_native_guard_calls_unchanged'),
                      original_node_guids_preserved=repeated.get('original_node_guids_preserved'))
    except Exception:
        result['error'] = traceback.format_exc()
        unreal.log_error(result['error'])
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        (ROOT / 'release_action_sfx_native_run.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    try:
        run()
    finally:
        unreal.SystemLibrary.quit_editor()
