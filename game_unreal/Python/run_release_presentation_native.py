"""Serialized queued skylight proof, then audio import/director authoring.

Manual probes alter only unsaved in-memory fields, call the actual preservation
predicate, restore those fields and reload. No profile/HUD/gameplay graph edit.
"""
from pathlib import Path
import copy
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import apply_release_skylight as sky


def run():
    result = {'success': False, 'skylight_success': False, 'audio_success': False,
              'audio_runtime_playtested': False, 'device_tested': False}
    try:
        first = sky.apply()
        sky.require(first['success'], 'Skylight application was preserved or failed')
        result['skylight_apply'] = first
        current_map_sha = sky.sha(sky.MAP_FILE)
        baseline_sha = sky.read_report()['first_baseline_sha256']
        repeat = sky.apply()
        sky.require(repeat['success'] and repeat['idempotent_no_map_save'] and sky.sha(sky.MAP_FILE) == current_map_sha,
                    'Skylight repeated apply wrote or changed the map')
        result['skylight_idempotent'] = repeat
        # Exercise the documented reversal, ending on the selected .21 value.
        reversed_result = sky.revert()
        sky.require(reversed_result['success'] and abs(reversed_result['actual_intensity'] - .105) < 1e-6,
                    'Skylight did not restore first baseline')
        reapplied = sky.apply()
        sky.require(reapplied['success'] and abs(reapplied['actual_intensity'] - .21) < 1e-6,
                    'Skylight selection did not reapply')
        sky.require(sky.read_report()['first_baseline_sha256'] == baseline_sha, 'Immutable first baseline changed')
        result['skylight_revert_roundtrip'] = {'reverted': reversed_result, 'reapplied': reapplied}
        data = sky.policy()
        actor, component = sky.open_selected(data)
        saved = sky.read_report()
        original_tags = list(actor.get_editor_property('tags'))
        original_intensity = float(component.get_editor_property('intensity'))
        original_state = sky.art.snapshot()
        original_lights = sky.art.lighting()
        map_sha = sky.sha(sky.MAP_FILE)
        checks = []
        try:
            actor.set_editor_property('tags', original_tags + [unreal.Name('TOSOY.ManualOverride')])
            reason = sky.preserve_reason(actor, data, saved, sky.art.lighting()[actor.get_name()])
            checks.append({'test': 'Explicit manual tag rejected by real ownership predicate', 'passed': bool(reason)})
            actor.set_editor_property('tags', original_tags)
            component.set_intensity(.22)
            reason = sky.preserve_reason(actor, data, saved, sky.art.lighting()[actor.get_name()])
            checks.append({'test': 'Unexpected native intensity preserved by real ownership predicate', 'passed': bool(reason)})
            component.set_intensity(original_intensity)
            sticky = copy.deepcopy(saved)
            sticky['inferred_manual_names'] = [actor.get_name()]
            reason = sky.preserve_reason(actor, data, sticky, sky.art.lighting()[actor.get_name()])
            checks.append({'test': 'Inferred manual state remains sticky', 'passed': bool(reason)})
        finally:
            actor.set_editor_property('tags', original_tags)
            component.set_intensity(original_intensity)
        checks.append({'test': 'Unsaved manual probes fully restored lights/actors',
                       'passed': sky.art.snapshot() == original_state and sky.art.lighting() == original_lights})
        checks.append({'test': 'Manual probes never saved the map', 'passed': sky.sha(sky.MAP_FILE) == map_sha})
        sky.require(all(item['passed'] for item in checks), 'Skylight manual preservation probe failed')
        result['skylight_manual_predicate_probes'] = checks
        result['skylight_generator_retention'] = sky.retain_selected()
        sky.require(result['skylight_generator_retention']['retained'], 'Selected light did not survive saved reload')
        result['skylight_success'] = True
        # Queue's second stage starts only after the first stage is clean.
        import import_release_audio as audio
        imported = audio.apply()
        sky.require(imported['success'], 'Audio authoring was preserved or failed')
        result['audio_import'] = {key: imported[key] for key in ['namespace', 'wav_readback', 'class_paths',
                                'runtime_compiled', 'runtime_playtested', 'event_sfx_hooked', 'music_playback_enabled']}
        result['audio_saved_readback'] = audio.validate_saved()
        result['audio_success'] = True
        result['success'] = True
    except Exception:
        result['error'] = traceback.format_exc()
        unreal.log_error(result['error'])
    (ROOT / 'release_presentation_native_report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    try:
        run()
    finally:
        unreal.SystemLibrary.quit_editor()
