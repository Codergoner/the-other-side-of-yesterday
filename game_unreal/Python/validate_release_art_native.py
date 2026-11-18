"""Serialized full-editor desktop art apply/readback and in-memory guard probe.

Only build_all() saves the designated desktop map. The manual-edit probes call
the ownership predicate on real actors, restore the unsaved edit immediately,
and never save those edits. This is not rendered/moving-water visual approval.
"""
from pathlib import Path
import copy
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import build_release_art as art

REPORT = ROOT / 'release_art_native_validation.json'


def run():
    result = {'success': False, 'scope': 'Desktop saved native art and ownership predicates',
              'visual_acceptance': False, 'motion_aliasing_tested': False, 'device_tested': False}
    try:
        art.require(art.MAPS == ['/Game/Quest/Maps/Verdant_Desktop'], 'Only the Windows desktop map is allowed')
        first = copy.deepcopy(art.build_all())
        result['first_apply'] = {'run': first['run'], 'complete': first['native_maps_complete'],
                                 'water_compile': first['water_native_readback']}
        result['saved_readback'] = art.validate_saved()
        map_path = art.MAPS[0]
        first_record = first['maps'][map_path]
        baseline_path = Path(first_record['first_baseline_snapshot'])
        baseline_hash = art.digest(baseline_path)
        first_state = art.snapshot()
        second = art.build_all()
        result['idempotent_rerun'] = {'passed': art.snapshot() == first_state,
                                    'first_baseline_path_preserved': second['maps'][map_path]['first_baseline_snapshot'] == str(baseline_path),
                                    'first_baseline_hash_preserved': art.digest(baseline_path) == baseline_hash}
        art.require(all(result['idempotent_rerun'].values()), 'Rerun or first baseline changed')
        result['second_saved_readback'] = art.validate_saved()
        original_state = art.snapshot()
        saved_map = ROOT / 'Content/Quest/Maps/Verdant_Desktop.umap'
        saved_sha = art.digest(saved_map)
        actor = art.find_mesh('SM_DocksMain')
        original_tags = list(actor.get_editor_property('tags'))
        original_location = actor.get_actor_location()
        previous = {actor.get_name(): art.state(actor)}
        checks = []
        try:
            actor.set_editor_property('tags', original_tags + [unreal.Name(art.MANUAL)])
            record = {'baseline': {}, 'inferred_manual_names': [], 'preserved_manual': []}
            denied = not art.editable(actor, record, previous, {})
            checks.append({'test': 'Explicit manual actor preserved by predicate', 'passed': denied and bool(record['preserved_manual'])})
            actor.set_editor_property('tags', original_tags)
            actor.set_actor_location(original_location + unreal.Vector(3, 0, 0), False, False)
            record = {'baseline': {}, 'inferred_manual_names': [], 'preserved_manual': []}
            denied = not art.editable(actor, record, previous, {})
            checks.append({'test': 'Inferred transform edit preserved by predicate', 'passed': denied and actor.get_name() in record['inferred_manual_names']})
            actor.set_actor_location(original_location, False, False)
            denied_again = not art.editable(actor, record, previous, {})
            checks.append({'test': 'Detected manual status remains sticky after transform matches', 'passed': denied_again})
        finally:
            actor.set_editor_property('tags', original_tags)
            actor.set_actor_location(original_location, False, False)
        checks.append({'test': 'Unsaved probes restored every actor state', 'passed': art.snapshot() == original_state})
        checks.append({'test': 'Unsaved probes never wrote production map', 'passed': art.digest(saved_map) == saved_sha})
        checks.append({'test': 'First actor baseline preserved through guards', 'passed': art.digest(baseline_path) == baseline_hash})
        art.require(all(item['passed'] for item in checks), 'Ownership predicate probe failed')
        result['manual_guard_probes'] = checks
        # Explicitly reload saved content to discard editor dirty flags from the
        # restored in-memory probes; do not save a probe frame.
        art.require(art.LEVEL.load_level(map_path), 'Cannot discard in-memory probe state')
        result['final_saved_readback'] = art.validate_saved()
        result['success'] = True
    except Exception:
        result['error'] = traceback.format_exc()
        unreal.log_error(result['error'])
    REPORT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    try:
        run()
    finally:
        unreal.SystemLibrary.quit_editor()
