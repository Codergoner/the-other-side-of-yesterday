"""Persist only the reviewed existing skylight intensity in Release Desktop.

Root selected SkyScale020 (.21 actual intensity) after native nine-image A/B.
The .105 first baseline remains immutable. No actor, tag, light, cubemap,
material, sun, renderer, story or other property is added/changed. Retention
reads the saved choice on later bounded art generation; manual edits survive.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy
import hashlib
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import build_release_art as art

MAP = '/Game/Quest/Maps/Verdant_Desktop'
POLICY = ROOT / 'ContentData/release_lighting_selection.json'
REPORT = ROOT / 'release_skylight_selection_report.json'
MAP_FILE = ROOT / 'Content/Quest/Maps/Verdant_Desktop.umap'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def guard(write=False):
    art.guard()
    require(ROOT.parent.name == 'Release_20261026', 'Skylight writer refuses another project')
    if write:
        require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseSkylightWrite'),
                'Serialized root writer queue and -ReleaseSkylightWrite are required')


def policy():
    data = json.loads(POLICY.read_text(encoding='utf-8'))
    require(data['map'] == MAP and data['selected_profile'] == 'SkyScale020', 'Unexpected selected lighting policy')
    require(data['selected_intensity'] == .21 and data['baseline_intensity'] == .105, 'Unexpected selected intensities')
    evidence = ROOT / data['capture_report_relative']
    require(sha(evidence) == data['capture_report_sha256'], 'Reviewed A/B evidence changed; do not silently adopt another run')
    captured = json.loads(evidence.read_text(encoding='utf-8'))
    require(captured['success'] and captured['saved_lights_restored'] and captured['protected_inputs_unchanged'], 'A/B evidence was not clean')
    return data


def read_report():
    return json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {'schema': 1}


def save_report(data):
    REPORT.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def protected():
    paths = list((ROOT / 'Content').rglob('*.uasset')) + list((ROOT / 'Content').rglob('*.umap'))
    paths += list((ROOT / 'Config').glob('*.ini')) + list(ROOT.glob('*.uproject')) + list((ROOT / 'Saved/SaveGames').glob('*.sav'))
    return {str(path): sha(path) for path in paths}


def open_selected(data):
    require(art.LEVEL.load_level(MAP), 'Cannot open the selected desktop map')
    matches = [actor for actor in art.actors() if isinstance(actor, unreal.SkyLight)]
    require(len(matches) == 1, 'Skylight identity is ambiguous; preserve the scene')
    actor = matches[0]
    require(actor.get_path_name() == data['actor_path'], 'Saved skylight identity differs from the reviewed actor')
    return actor, actor.get_component_by_class(unreal.SkyLightComponent)


def preserve_reason(actor, data, previous, current):
    if actor.actor_has_tag('TOSOY.ManualOverride'):
        return 'Explicit TOSOY.ManualOverride'
    if actor.get_name() in previous.get('inferred_manual_names', []):
        return 'Previously detected manual lighting edit'
    expected = previous['after'] if previous.get('success') and not previous.get('reverted') else data['baseline_light_state']
    if current != expected:
        return 'Skylight differs from the last generated choice or reviewed first baseline'
    if previous.get('baseline_actor_state') and art.state(actor) != previous['baseline_actor_state']:
        return 'Skylight actor transform/tags/collision/identity were manually changed'
    return None


def persist(revert=False):
    guard(write=True)
    data = policy()
    before_files = protected()
    actor, component = open_selected(data)
    before_actors = art.snapshot()
    before_story = art.story_refs()
    before_lights = art.lighting()
    name = actor.get_name()
    current = before_lights[name]
    old = read_report()
    if revert:
        require(old.get('success') and old.get('after') and not old.get('reverted'), 'No current generated selection to revert')
    reason = preserve_reason(actor, data, old, current)
    if reason:
        old.setdefault('inferred_manual_names', []).append(name)
        old['inferred_manual_names'] = sorted(set(old['inferred_manual_names']))
        old['preserved_manual'] = {'actor': actor.get_path_name(), 'reason': reason, 'map_saved': False}
        save_report(old)
        return {'success': False, 'preserved_manual': old['preserved_manual']}
    if not old.get('baseline'):
        old['baseline'] = copy.deepcopy(current)
        old['baseline_actor_state'] = copy.deepcopy(art.state(actor))
        folder = ROOT / 'validation/release_sky_selection'
        folder.mkdir(parents=True, exist_ok=True)
        first = folder / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f') + '_first_baseline.json')
        first.write_text(json.dumps({'sky': current, 'actor': art.state(actor), 'map_sha256': sha(MAP_FILE)}, indent=2), encoding='utf-8')
        old['first_baseline_file'] = str(first)
        old['first_baseline_sha256'] = sha(first)
    require(sha(old['first_baseline_file']) == old['first_baseline_sha256'], 'Immutable first baseline changed')
    target = old['baseline']['intensity'] if revert else data['selected_intensity']
    changed = abs(float(component.get_editor_property('intensity')) - target) > 1e-6
    if changed:
        component.set_intensity(target)
    actual = float(component.get_editor_property('intensity'))
    require(abs(actual - target) < 1e-6, 'Skylight intensity readback failed')
    expected_lights = copy.deepcopy(before_lights)
    expected_lights[name]['intensity'] = actual
    require(art.lighting() == expected_lights, 'A different light field changed')
    require(art.snapshot() == before_actors, 'Actor/geometry/material/transform/tag/collision state changed')
    require(art.story_refs() == before_story, 'Story reference or era array changed')
    if changed:
        require(art.LEVEL.save_current_level(), 'Could not save the one-property desktop selection')
    after_files = protected()
    for path, digest in before_files.items():
        require((changed and Path(path) == MAP_FILE) or after_files.get(path) == digest, 'Protected file changed: ' + path)
    require(set(after_files) == set(before_files), 'A native asset/config/save file was created or removed')
    require(art.LEVEL.load_level(MAP), 'Could not reload the saved selected map')
    require(art.lighting() == expected_lights and art.story_refs() == before_story, 'Saved native light/story readback differs')
    require(art.snapshot() == before_actors, 'Reloaded actor state differs')
    result = {'success': True, 'map': MAP, 'actor': data['actor_path'], 'selected_intensity': data['selected_intensity'],
              'actual_intensity': actual, 'baseline_intensity': old['baseline']['intensity'], 'saved': changed,
              'idempotent_no_map_save': not changed, 'only_property': 'Existing SkyLightComponent.Intensity',
              'sun_unchanged': True, 'other_lights_and_story_unchanged': True, 'native_reloaded': True,
              'protected_files_unchanged_except_authorized_map': True, 'visual_quality_accepted': False,
              'headset_or_runtime_performance_tested': False, 'reverted': revert}
    old.update(success=True, map=MAP, actor_path=data['actor_path'], selected_profile=data['selected_profile'],
               policy_sha256=sha(POLICY), after=copy.deepcopy(expected_lights[name]), reverted=revert,
               last_result=result, updated_utc=datetime.now(timezone.utc).isoformat())
    save_report(old)
    return result


def apply():
    return persist(revert=False)


def revert():
    return persist(revert=True)


def retain_selected():
    """Read-only retention hook for bounded release art reruns.

    Never overwrites an unexpected intensity and never recreates a reverted
    selection. A separate explicit apply() is the only native lighting writer.
    """
    guard()
    old = read_report()
    if not old.get('success') or old.get('reverted'):
        return {'configured': False, 'changed': False, 'reason': 'Selection has not been applied or was explicitly reverted'}
    data = policy()
    actor, component = open_selected(data)
    reason = preserve_reason(actor, data, old, art.lighting()[actor.get_name()])
    if reason:
        return {'configured': True, 'retained': False, 'changed': False, 'preserved_manual': reason}
    require(abs(component.get_editor_property('intensity') - data['selected_intensity']) < 1e-6, 'Selected intensity is not retained')
    require(sha(old['first_baseline_file']) == old['first_baseline_sha256'], 'First baseline changed')
    return {'configured': True, 'retained': True, 'changed': False, 'actual_intensity': float(component.get_editor_property('intensity')),
            'first_baseline_sha256': old['first_baseline_sha256']}


if __name__ == '__main__':
    try:
        result = revert() if unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'RevertReleaseSkylight') else apply()
        unreal.log('RELEASE_SKYLIGHT_RESULT ' + json.dumps(result))
    except Exception:
        (ROOT / 'release_skylight_selection_failure.json').write_text(json.dumps({'success': False, 'error': traceback.format_exc()}, indent=2), encoding='utf-8')
        raise
    finally:
        unreal.SystemLibrary.quit_editor()
