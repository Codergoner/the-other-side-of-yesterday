"""Queued additive director upgrade/readback; does not author frontend graphs."""
from pathlib import Path
import copy
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import import_release_audio as audio


def run():
    report = {'success': False, 'runtime_playtested': False, 'frontend_modified': False}
    try:
        previous = copy.deepcopy(audio.report_read())
        first = audio.apply()
        audio.require(first['success'], 'Updated director was not applied')
        report['native_readback'] = audio.validate_saved()
        first_state = audio.snapshot()
        repeated = audio.apply()
        audio.require(repeated['success'] and audio.snapshot() == first_state, 'Repeat changed persistent actor state')
        report['idempotent_actor_state'] = True
        report['second_native_readback'] = audio.validate_saved()
        if previous.get('first_baseline'):
            audio.require(previous['first_baseline'] == repeated['first_baseline'], 'First authoring baseline changed')
        report['first_baseline_preserved'] = True
        report['namespace'] = repeated['namespace']
        report['director_class'] = repeated['after']['class']
        report['mix'] = repeated['after']['mix']
        report['zero_gain_fix'] = 'Steady SetVolumeMultiplier; era FadeIn(level1) independent of gain; native playback QA still required.'
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    (ROOT / 'release_audio_native_upgrade_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    try:
        run()
    finally:
        unreal.SystemLibrary.quit_editor()
