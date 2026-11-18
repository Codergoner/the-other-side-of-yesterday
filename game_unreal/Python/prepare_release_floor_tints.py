"""Queued warm floor candidates; preview preparation never saves the map.

Only two new versioned opaque materials are made, reusing the six exact source
textures. BaseColor is multiplied in linear space. All other recipes remain
identical. Adoption is separately gated by a completed actual comparison and
the root's explicit -ReleaseFloorTintReviewed launch argument.
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

POLICY = ROOT / 'ContentData/release_floor_tint_candidates.json'
REPORT = ROOT / 'release_floor_tint_report.json'
SELECTION = ROOT / 'release_floor_tint_selection.json'
CAPTURE = ROOT / 'release_floor_tint_capture_report.json'


def read():
    return json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {}


def write(value):
    REPORT.write_text(json.dumps(value, indent=2, default=str) + '\n', encoding='utf-8')


def policy():
    data = json.loads(POLICY.read_text(encoding='utf-8'))
    hero.require(data['map'] == hero.MAP and data['extra_gain'] == 1 and data['no_new_texture_imports'] and data['no_color_clamp_or_gamma_power'], 'Unexpected floor palette scope')
    hero.require(set(data['linear_tints']) == {'room_floor', 'street_floor'}, 'Palette must cover exactly the two floor roles')
    for tint in data['linear_tints'].values():
        hero.require(len(tint) == 3 and all(isinstance(v, (float, int)) and 0 < v <= 1 for v in tint), 'Invalid linear multiplier')
    return data


def prepared():
    data = read()
    hero.require(data.get('preview_ready') and data['policy_sha256'] == hero.sha(POLICY), 'Prepare the reviewed source candidate first')
    hero.require(data['base_plan_sha256'] == hero.sha(hero.PLAN) and
                 hero.version(hero.source(), data['resolved_plan']) == data['signature'],
                 'Source/plan changed since candidate preparation; prepare and capture again before adoption')
    for path, digest in data['asset_fingerprints'].items():
        hero.require(Path(path).is_file() and hero.sha(Path(path)) == digest, 'Preserving edited palette/source asset')
    return data


def prepare(transient=False):
    hero.guard(write=not transient)
    if transient:
        hero.require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseFloorTintTransient'), 'Root transient native queue and -ReleaseFloorTintTransient are required')
    p, previous, prior = policy(), copy.deepcopy(hero.read_report()), read()
    hero.require(previous.get('success') and previous['floors']['complete_scope'] and not previous['floors'].get('reverted'), 'Existing accepted floor pattern is required')
    hero.require(not SELECTION.exists() or not json.loads(SELECTION.read_text()).get('adopted'), 'A palette is already adopted; prepare a separately reviewed revision')
    for path, digest in prior.get('asset_fingerprints', {}).items():
        hero.require(Path(path).is_file() and hero.sha(Path(path)) == digest, 'Preserving manually edited candidate asset')
    before_files = hero.files()
    hero.require(hero.base.LEVEL.load_level(hero.MAP), 'Cannot load current floor map')
    before, lights, story = hero.base.snapshot(), hero.base.lighting(), hero.base.story_refs()
    base_recipes = hero.config()
    plan = copy.deepcopy(base_recipes)
    for recipe in plan['floor_scope']:
        recipe['base_color_tint'] = p['linear_tints'][recipe['role']]
    signature, folder, mats = hero.prepare_assets(plan, hero.source(), transient=transient)
    readback = {}
    for recipe in plan['floor_scope']:
        role = recipe['role']
        mat = mats[role]
        readback[role] = hero.material_readback(mat, recipe)
        raw_recipe = json.loads(hero.LIB.get_metadata_tag(mat, 'Release.Hero.Recipe'))
        hero.require(raw_recipe == recipe, 'Saved candidate recipe differs')
        original_recipe = next(row for row in base_recipes['floor_scope'] if row['role'] == role)
        hero.require({k: v for k, v in raw_recipe.items() if k != 'base_color_tint'} == original_recipe, 'Palette changed another material recipe field')
        current_assignment = next(row for row in previous['floors']['assignments'] if row['role'] == role)
        current = hero.base.load(current_assignment['material'])
        get_textures = lambda asset: sorted(node.get_editor_property('texture').get_path_name() for node in hero.MEL.get_material_expressions(asset) if isinstance(node, unreal.MaterialExpressionTextureSample))
        hero.require(get_textures(current) == get_textures(mat), 'Candidate reimported or replaced source textures')
    hero.require(hero.base.snapshot() == before and hero.base.lighting() == lights and hero.base.story_refs() == story, 'Preview preparation changed a map actor/light/story reference')
    hero.check_existing(before_files)
    after_files = hero.files()
    additions = [path for path in after_files if path not in before_files]
    expected = [] if transient else [str(ROOT / 'Content' / (mat.get_path_name().split('.')[0].removeprefix('/Game/') + '.uasset')) for mat in mats.values()]
    hero.require(all(path in expected for path in additions), 'Palette preparation created an unexpected asset')
    baseline = previous['floors']['first_baseline_file']
    hero.require(hero.sha(Path(baseline)) == previous['floors']['first_baseline_sha256'], 'Immutable floor baseline changed')
    result = {'schema': 1, 'run': datetime.now(timezone.utc).isoformat(), 'success': True, 'preview_ready': True,
              'adopted': False, 'map_saved': False, 'transient': transient, 'native_assets_saved': not transient,
              'candidate': p['candidate'], 'policy_sha256': hero.sha(POLICY),
              'base_plan_sha256': hero.sha(hero.PLAN), 'linear_tints': p['linear_tints'],
              'signature': signature, 'namespace': folder, 'resolved_plan': plan,
              'material_paths': {role: mat.get_path_name() for role, mat in mats.items()},
              'shader_readback': readback, 'created_assets': additions, 'new_texture_imports': 0,
              'current_floor_assignments': previous['floors']['assignments'],
              'first_floor_baseline_file': baseline, 'first_floor_baseline_sha256': previous['floors']['first_baseline_sha256'],
              'asset_fingerprints': {**previous['owned_asset_fingerprints'], **{path: hero.sha(Path(path)) for path in expected}},
              'visual_accepted': False, 'lighting_geometry_story_unchanged': True}
    write(result)
    return result


def adopt():
    hero.guard(write=True)
    hero.require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseFloorTintReviewed'), 'Actual image review and -ReleaseFloorTintReviewed are required')
    candidate = prepared()
    hero.require(not candidate.get('transient'), 'Prepare the reviewed persistent materials before map adoption; Temp materials must never be saved into a map')
    capture = json.loads(CAPTURE.read_text(encoding='utf-8'))
    hero.require(capture.get('success') and capture['candidate_signature'] == candidate['signature'] and capture['policy_sha256'] == candidate['policy_sha256'], 'A completed actual current-vs-candidate capture is required')
    review = json.loads((ROOT / 'ContentData/release_floor_tint_reviewed.json').read_text(encoding='utf-8'))
    hero.require(review['candidate_signature'] == candidate['signature'] and review['policy_sha256'] == candidate['policy_sha256'] and
                 review['hero_importer_sha256'] == hero.sha(ROOT / 'Python/build_release_hero.py'),
                 'Root-reviewed candidate/source differs; compare and review again')
    for path, digest in review['selected_image_hashes'].items():
        hero.require(Path(path).is_file() and hero.sha(Path(path)) == digest, 'Reviewed actual image changed')
    current = hero.read_report()
    hero.require(current['floors']['first_baseline_sha256'] == candidate['first_floor_baseline_sha256'], 'First floor baseline differs')
    hero.require(hero.base.LEVEL.load_level(hero.MAP), 'Cannot open current floor map before adoption')
    for recipe in hero.config()['floor_scope']:
        actor = hero.base.find_mesh(recipe['mesh'])
        hero.require(hero.eligible(actor, current['floors'], recipe) is None, 'Preserving explicit/inferred artist edit before palette adoption')
    map_sha_before = hero.sha(hero.MAP_FILE)
    selection = {'schema': 1, 'map': hero.MAP, 'adopted': True, 'candidate': candidate['candidate'],
                 'linear_tints': candidate['linear_tints'], 'base_plan_sha256': candidate['base_plan_sha256'],
                 'candidate_signature': candidate['signature'], 'capture_run': capture['run'],
                 'reviewed_launch_argument': True}
    old_selection = SELECTION.read_bytes() if SELECTION.exists() else None
    SELECTION.write_text(json.dumps(selection, indent=2) + '\n', encoding='utf-8')
    try:
        applied = hero.apply_floors()
        hero.require(applied['signature'] == candidate['signature'] and applied['floors']['complete_scope'], 'Palette adoption preserved a manual target or generated a different material')
        hero.require(applied['floors']['first_baseline_sha256'] == candidate['first_floor_baseline_sha256'], 'Palette adoption changed the first baseline')
        candidate['native_saved_readback'] = hero.validate_floors()
    except Exception:
        # Keep a failed/no-selection record, never delete or overwrite native
        # assets to conceal a partial authoring failure.
        if hero.sha(hero.MAP_FILE) != map_sha_before:
            selection['adoption_status'] = 'Map saved; later validation failed. Retain actual selected policy for explicit repair.'
            SELECTION.write_text(json.dumps(selection, indent=2) + '\n', encoding='utf-8')
        elif old_selection is not None:
            SELECTION.write_bytes(old_selection)
        else:
            SELECTION.write_text(json.dumps({'schema': 1, 'map': hero.MAP, 'adopted': False, 'failed_attempt_retained': True}, indent=2) + '\n', encoding='utf-8')
        raise
    candidate.update(adopted=True, actual_capture_run=capture['run'], visual_accepted_by_root_launch=True)
    write(candidate)
    return candidate


def revert_palette():
    """Color-only reversal keeps the accepted photo floors and first baseline."""
    hero.guard(write=True)
    selection = json.loads(SELECTION.read_text(encoding='utf-8'))
    hero.require(selection.get('adopted') and selection['map'] == hero.MAP, 'No active floor palette selection')
    old = hero.read_report()
    hero.require(hero.base.LEVEL.load_level(hero.MAP), 'Cannot open palette reversal map')
    for recipe in hero.config()['floor_scope']:
        hero.require(hero.eligible(hero.base.find_mesh(recipe['mesh']), old['floors'], recipe) is None,
                     'Preserving explicit/inferred artist edit before color reversal')
    old_selection = SELECTION.read_bytes()
    map_sha_before = hero.sha(hero.MAP_FILE)
    selection.update(candidate='UntintedPattern', linear_tints={'room_floor': [1, 1, 1], 'street_floor': [1, 1, 1]},
                     color_only_reversal=True, adoption_status='Reverting to the accepted photo pattern with neutral linear multipliers')
    SELECTION.write_text(json.dumps(selection, indent=2) + '\n', encoding='utf-8')
    try:
        data = hero.apply_floors()
        hero.require(data['floors']['complete_scope'] and data['floors']['first_baseline_sha256'] == old['floors']['first_baseline_sha256'], 'Color-only reversal lost a target or first baseline')
        readback = hero.validate_floors()
    except Exception:
        if hero.sha(hero.MAP_FILE) == map_sha_before:
            SELECTION.write_bytes(old_selection)
        else:
            selection['adoption_status'] = 'Reversal map saved; later validation failed. Retain actual policy for explicit repair.'
            SELECTION.write_text(json.dumps(selection, indent=2) + '\n', encoding='utf-8')
        raise
    result = read()
    result.update(palette_reverted_to_untinted=True, native_reversal_readback=readback)
    write(result)
    return result


if __name__ == '__main__':
    try:
        command = unreal.SystemLibrary.get_command_line()
        if unreal.SystemLibrary.parse_param(command, 'RevertReleaseFloorTint'):
            result = revert_palette()
        else:
            result = adopt() if unreal.SystemLibrary.parse_param(command, 'ReleaseFloorTintReviewed') else prepare()
    except Exception:
        value = read()
        value.setdefault('attempt_failures', []).append({'at': datetime.now(timezone.utc).isoformat(), 'error': traceback.format_exc()})
        value['last_attempt_success'] = False
        write(value)
        raise
    finally:
        unreal.SystemLibrary.quit_editor()
