"""Root-queued native proof for exactly two desktop floor material slots.

Applies and reloads the saved floors, repeats the generator and exercises its
manual-preservation predicates on real unsaved actor edits. No detail import,
Blender run, closure, NPC, lighting, gameplay or corrupt-save action is used.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import build_release_hero as hero


def protected_saves():
    roots = [ROOT, ROOT.parent.parent / 'Quest_20261025/game_unreal',
             ROOT.parent.parent / 'Brief_20261025/game_unreal',
             ROOT.parent.parent.parent / 'game_unreal',
             Path.home() / 'AppData/Local/YesterdayHarbor']
    saved = Path(unreal.Paths.project_saved_dir()).resolve() / 'SaveGames'
    directories = [p / 'Saved/SaveGames' for p in roots] + [saved]
    return {str(p): hero.sha(p) for d in directories if d.exists() for p in d.rglob('*') if p.is_file()}


def run():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    result = {'success': False, 'run': stamp, 'scope': __doc__, 'detail_props_imported': False,
              'collision_change': False, 'closure_authored': False, 'visual_accepted': False,
              'gameplay_tested': False, 'headset_tested': False, 'checks': []}
    path = ROOT / 'release_hero_native_validation.json'
    folder = ROOT / 'validation/release_hero_native' / stamp
    folder.mkdir(parents=True, exist_ok=False)
    before_files, saves_before = {}, {}
    try:
        hero.guard(write=True)
        before_files, saves_before = hero.files(), protected_saves()
        result['protected_files_before'] = before_files
        result['protected_saves_before'] = saves_before
        hero.require(hero.base.LEVEL.load_level(hero.MAP), 'Could not open the current desktop map')
        scene_before = hero.base.snapshot()
        lights_before, story_before = hero.base.lighting(), hero.base.story_refs()
        sky_values = [r['intensity'] for r in lights_before.values() if 'SkyLight' in r['class']]
        hero.require(len(sky_values) == 1 and abs(float(sky_values[0]) - .21) < 1e-6, 'Expected the selected saved 0.21 skylight')
        result['saved_skylight_before'] = sky_values
        first = copy.deepcopy(hero.apply_floors())
        hero.require(first['floors']['complete_scope'] and len(first['floors']['assignments']) == 2, 'Exactly two reviewed floor slots must apply')
        result['first_apply'] = {'signature': first['signature'], 'namespace': first['namespace'], 'floors': first['floors']}
        result['first_saved_readback'] = hero.validate_floors()
        after_first = hero.base.snapshot()
        hero.require(set(scene_before) == set(after_first), 'Floor pass changed actor count')
        hero.require(all(hero.base.physical(row) == hero.base.physical(after_first[name]) for name, row in scene_before.items()), 'Floor pass changed physical actor state')
        hero.require(hero.base.lighting() == lights_before and hero.base.story_refs() == story_before, 'Saved floor pass changed lights or narrative references')
        baseline_file = Path(first['floors']['first_baseline_file'])
        baseline_sha, map_sha = hero.sha(baseline_file), hero.sha(hero.MAP_FILE)
        second = hero.apply_floors()
        hero.require(second['floors']['complete_scope'], 'Rerun skipped a reviewed floor')
        hero.require(hero.base.snapshot() == after_first, 'Repeat changed generated actor state')
        hero.require(second['floors']['idempotent_no_map_save'] and hero.sha(hero.MAP_FILE) == map_sha, 'Idempotent repeat saved or changed the map')
        hero.require(second['floors']['first_baseline_file'] == str(baseline_file) and hero.sha(baseline_file) == baseline_sha, 'First floor baseline changed')
        result['idempotent_rerun'] = {'actor_state_unchanged': True, 'no_map_save': True, 'map_sha256_unchanged': True,
                                     'first_baseline_preserved': True, 'baseline_sha256': baseline_sha}
        result['second_saved_readback'] = hero.validate_floors()
        previous = copy.deepcopy(hero.read_report()['floors'])
        checks = []
        for recipe in hero.config()['floor_scope']:
            actor = hero.base.find_mesh(recipe['mesh'])
            original_tags = list(actor.get_editor_property('tags'))
            original_location = actor.get_actor_location()
            comp = actor.get_component_by_class(unreal.StaticMeshComponent)
            original_material = comp.get_material(recipe['slot'])
            first_material_path = previous['baseline'][actor.get_name()]['materials'][recipe['slot']]
            try:
                actor.set_editor_property('tags', original_tags + [unreal.Name('TOSOY.ManualOverride')])
                checks.append({'test': recipe['role'] + ': explicit manual tag is rejected',
                               'passed': bool(hero.eligible(actor, previous, recipe))})
                actor.set_editor_property('tags', original_tags)
                actor.set_actor_location(original_location + unreal.Vector(3, 0, 0), False, False)
                checks.append({'test': recipe['role'] + ': artist position edit is rejected',
                               'passed': bool(hero.eligible(actor, previous, recipe))})
                actor.set_actor_location(original_location, False, False)
                comp.set_material(recipe['slot'], hero.base.load(first_material_path))
                checks.append({'test': recipe['role'] + ': artist slot edit is rejected',
                               'passed': bool(hero.eligible(actor, previous, recipe))})
                comp.set_material(recipe['slot'], original_material)
                sticky = copy.deepcopy(previous)
                sticky['inferred_manual_names'] = [actor.get_name()]
                checks.append({'test': recipe['role'] + ': inferred manual status remains sticky',
                               'passed': bool(hero.eligible(actor, sticky, recipe))})
            finally:
                actor.set_editor_property('tags', original_tags)
                actor.set_actor_location(original_location, False, False)
                comp.set_material(recipe['slot'], original_material)
        checks += [{'test': 'All unsaved manual probes restore exact actors', 'passed': hero.base.snapshot() == after_first},
                   {'test': 'Manual probes never saved the map', 'passed': hero.sha(hero.MAP_FILE) == map_sha},
                   {'test': 'Manual probes preserve first baseline bytes', 'passed': hero.sha(baseline_file) == baseline_sha}]
        hero.require(all(row['passed'] for row in checks), 'Manual preservation predicate failed')
        result['manual_predicate_checks'] = checks
        result['final_saved_readback'] = hero.validate_floors()
        hero.require(hero.base.lighting() == lights_before and hero.base.story_refs() == story_before, 'Final light/story references changed')
        result['original_geometry_collision_transforms_unchanged'] = True
        result['lights_story_references_unchanged'] = True
        result['success'] = True
    except Exception:
        result['error'] = traceback.format_exc()
        unreal.log_error(result['error'])
    finally:
        after_files, saves_after = hero.files(), protected_saves()
        result['protected_files_after'] = after_files
        result['protected_saves_after'] = saves_after
        changed = [p for p, digest in before_files.items() if p != str(hero.MAP_FILE) and after_files.get(p) != digest]
        save_changed = [p for p, digest in saves_before.items() if saves_after.get(p) != digest]
        added_saves = sorted(set(saves_after) - set(saves_before))
        result['protected_existing_files_unchanged'] = not changed
        result['existing_saves_unchanged'] = not save_changed and not added_saves
        result['changed_protected_files'] = changed
        result['changed_saves'], result['added_saves'] = save_changed, added_saves
        result['success'] = result['success'] and not changed and not save_changed and not added_saves
        text = json.dumps(result, indent=2, default=str) + '\n'
        path.write_text(text, encoding='utf-8')
        (folder / 'report.json').write_text(text, encoding='utf-8')
    return result


if __name__ == '__main__':
    try:
        run()
    finally:
        unreal.SystemLibrary.quit_editor()
