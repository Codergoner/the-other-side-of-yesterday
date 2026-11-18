"""Queued native import/readback of NEW Mother unit-coordinate experiments.

Requires -ReleaseUnitProbeManifest="absolute manifest path". Full editor only.
Reuses the proved Mother's material assets without modifying/saving them. Each
case receives a separate namespace/map with exactly one Mother skeletal actor.
Does not promote/replace Mother, retarget gait, edit NPCs or touch saved games.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import sys
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
ROOT = PROJECT.parent
SOURCE_PATH = Path(__file__).resolve()
sys.path.insert(0, str(PROJECT / 'Python'))
import import_release_characters as mother
import diagnose_release_character_animation as pose_helpers
sys.path.insert(0, str(ROOT / 'tools'))
import windows_file_guards as file_guards

LIB, LEVELS, ACTORS = mother.LIB, mother.LEVELS, mother.ACTORS
sha, require = file_guards.sha, mother.require
REPORT_PATH = PROJECT / 'release_character_unit_probe_report.json'


def json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def old_proof_files():
    paths = file_guards.files(ROOT / 'output/release_characters')
    paths += [PROJECT / 'release_character_import_report.json', PROJECT / 'release_character_cardinals_report.json',
              PROJECT / 'release_character_face_pose_report.json', PROJECT / 'release_character_animation_diagnostic.json',
              PROJECT / 'release_character_pie_review_report.json']
    return {str(p): sha(p) for p in paths if p.is_file()}


def saved_games():
    roots = [PROJECT / 'Saved/SaveGames', Path(os.environ.get('LOCALAPPDATA', '')) / 'YesterdayHarbor/Saved/SaveGames']
    return {str(p): sha(p) for root in roots if root.is_dir() for p in root.rglob('*.sav')}


def effective_source_names(probe):
    path = Path(probe['source_manifest'])
    require(sha(path) == probe['source_manifest_sha256'], 'Original Mother source manifest changed')
    data = json.loads(path.read_text())
    require(sha(data['blend']) == probe['source_blend_sha256'], 'Original proved blend changed')
    measured = data.get('effective_morph_measurement')
    if not measured:
        latest = json.loads((ROOT / 'output/release_characters/latest.json').read_text())
        audit = Path(latest['effective_morph_audit'])
        require(sha(audit) == latest['effective_morph_audit_sha256'], 'Original measured morph audit changed')
        measured = json.loads(audit.read_text())
        require(measured['success'] and measured['source_manifest_sha256'] == sha(path)
                and measured['source_blend_sha256'] == sha(data['blend']) and measured['source_fbx_sha256'] == data['fbx']['sha256'], 'Measured morph audit does not match original geometry')
    names = sorted(name for name, metric in measured['metrics'].items() if metric['changed_vertices'] > 0)
    require(names == sorted(measured['effective_facial_morphs']), 'Measured effective set is inconsistent')
    require({'eyeBlinkLeft', 'eyeBlinkRight'}.issubset(names), 'Real nonzero eyelid targets required')
    return names


def evaluate(animation, mesh, source_names):
    result = []
    for label in ['RAW', 'COMPRESSED']:
        options = unreal.AnimPoseEvaluationOptions()
        for key, value in {'evaluation_type': getattr(unreal.AnimDataEvalType, label), 'optional_skeletal_mesh': mesh,
            'should_retarget': True, 'extract_root_motion': False, 'evaluate_curves': True}.items():
            options.set_editor_property(key, value)
        rows = []
        for second in [0.0, 1.0, 1.5, 2.0, 3.0]:
            pose = unreal.AnimPoseExtensions.get_anim_pose_at_time(animation, second, options)
            require(unreal.AnimPoseExtensions.is_valid(pose), 'Invalid native authored animation pose')
            names = [str(n) for n in unreal.AnimPoseExtensions.get_bone_names(pose)]
            require(set(source_names).issubset(names), 'Native pose lost source bones')
            rows.append({'time_seconds': second,
                'local': {n: pose_helpers.transform(unreal.AnimPoseExtensions.get_bone_pose(pose, unreal.Name(n), unreal.AnimPoseSpaces.LOCAL)) for n in names},
                'component': {n: pose_helpers.transform(unreal.AnimPoseExtensions.get_bone_pose(pose, unreal.Name(n), unreal.AnimPoseSpaces.WORLD)) for n in names},
                'reference_local': {n: pose_helpers.transform(unreal.AnimPoseExtensions.get_ref_bone_pose(pose, unreal.Name(n), unreal.AnimPoseSpaces.LOCAL)) for n in names},
                'reference_component': {n: pose_helpers.transform(unreal.AnimPoseExtensions.get_ref_bone_pose(pose, unreal.Name(n), unreal.AnimPoseSpaces.WORLD)) for n in names},
                'curves': {str(n): float(unreal.AnimPoseExtensions.get_curve_weight(pose, n)) for n in unreal.AnimPoseExtensions.get_curve_names(pose)}})
        changes = [pose_helpers.compare(rows[0]['local'], row['local']) for row in rows[1:]]
        changed = sorted({n for row in changes for n, delta in row.items() if delta['changed']})
        blink = {n: v for n,v in rows[2]['curves'].items() if 'blink' in n.lower()}
        result.append({'type': label, 'samples': rows, 'changed_bones': changed, 'blink_curves_at1_5s': blink,
            'bone_motion_passed': bool(changed), 'blink_curve_peak_passed': sum(v >= 0.9 for v in blink.values()) >= 2,
            'visible_deformation_not_proven_by_data': True})
    return result


def scale_one(values):
    return len(values) == 3 and max(abs(value-1.0) for value in values) <= 1e-4


def import_case(case, parent, effective, materials, prior):
    signature = json_sha({'fbx_sha256': case['fbx_sha256'], 'case': case['id'], 'unit_import_policy': 1})[:16]
    folder = parent + '/' + case['id'] + '_' + signature
    disk = PROJECT / 'Content' / Path(folder.removeprefix('/Game/'))
    if prior and prior.get('namespace') == folder and prior.get('native_executed'):
        for path, digest in prior['owned_asset_sha256'].items():
            require(Path(file_guards.io_path(path)).is_file() and sha(path) == digest, 'Preserving a manually edited unit-probe case: ' + path)
        return prior
    require(not file_guards.matches(disk, '*.uasset') and not file_guards.matches(disk, '*.umap'),
            'Preserving an unproved/partial unit namespace; inspect its files before retry')
    require(sha(case['fbx']) == case['fbx_sha256'], 'Probe FBX changed')
    require(case['physical_morph_coordinate_preservation']['all_keys_and_vertex_indices_preserved']
            and case['physical_pose_preservation']['shape_key_curve_values_identical_at_all_samples'], 'Export coordinate preservation proof incomplete')
    imported = mother.import_fbx({'path': case['fbx']}, folder, signature)
    meshes = [a for a in imported if isinstance(a, unreal.SkeletalMesh)]
    animations = [a for a in imported if isinstance(a, unreal.AnimSequence)]
    require(len(meshes) == 1 and animations, 'Each new unit case requires one mesh and an authored animation')
    mesh = meshes[0]
    animation = max(animations, key=lambda a: a.get_play_length())
    require(3.8 <= animation.get_play_length() <= 4.2, 'Authored listening duration differs')
    morphs = [target.get_name() for target in mesh.call_method('GetMorphTargetsPtrConv')]
    require(len(morphs) == len(effective) and all(sum(n == name or n.endswith('_' + name) for n in morphs) == 1 for name in effective), 'Native effective morph count/set differs')
    slots, assigned = list(mesh.get_editor_property('materials')), []
    for slot in slots:
        name = str(slot.get_editor_property('imported_material_slot_name'))
        matches = [key for key in materials if name == key or name.replace('.', '_').endswith(key)]
        require(len(matches) == 1, 'Unexpected imported material slot: ' + name)
        slot.set_editor_property('material_interface', materials[matches[0]])
        assigned.append({'slot': name, 'material': materials[matches[0]].get_path_name()})
    mesh.set_editor_property('materials', slots)
    poses = evaluate(animation, mesh, case['source_bone_names'])
    require(all(p['bone_motion_passed'] and p['blink_curve_peak_passed'] for p in poses), 'Authored native animation/curve data did not survive unit export')
    reference = poses[0]['samples'][0]
    names = list(reference['local'])
    require('Root' in names, 'The actual source CoreRoot named Root is missing')
    first = names[0]
    native_scale = {'first_bone': first, 'first_bone_local_scale': reference['reference_local'][first]['scale'],
        'core_root_bone': 'Root', 'core_root_local_scale': reference['reference_local']['Root']['scale'],
        'core_root_component_scale': reference['reference_component']['Root']['scale']}
    native_scale['unit_root_scale_passed'] = all(scale_one(native_scale[key]) for key in
        ['first_bone_local_scale', 'core_root_local_scale', 'core_root_component_scale'])
    native_scale['all_reference_bone_local_scales_are_one'] = all(scale_one(row['scale']) for row in reference['reference_local'].values())
    map_path = folder + '/L_MotherUnitReview'
    require(not LIB.does_asset_exist(map_path), 'Preserving an existing unproved unit map')
    require(LEVELS.new_level(map_path), 'Cannot create new unit-review level')
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    world.get_world_settings().set_editor_property('default_game_mode', unreal.GameModeBase.static_class())
    actor = ACTORS.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector())
    actor.set_actor_label('Mother unit probe - ' + case['id'] + ' - no story swap')
    actor.set_editor_property('tags', [unreal.Name('TOSOY.ReleaseUnitProbeOwned')])
    actor.set_actor_enable_collision(False)
    component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    component.set_skeletal_mesh_asset(mesh)
    origin, extent = actor.get_actor_bounds(False)
    height = float(extent.z * 2)
    component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    component.play_animation(animation, True)
    component.set_position(0.0, False)
    sun = ACTORS.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0,0,300), unreal.Rotator(pitch=-35,yaw=-30))
    sun.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property('intensity', 3.5)
    sky = ACTORS.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0,0,300))
    sky_component = sky.get_component_by_class(unreal.SkyLightComponent)
    cube = unreal.load_asset('/Game/Quest/PremiumArt/Data_c12ac589619f/T_PH_BelfastSunset_HDRCube')
    require(cube, 'Existing authorized review cubemap missing')
    for key, value in {'source_type': unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP, 'cubemap': cube, 'intensity': 0.105}.items():
        sky_component.set_editor_property(key, value)
    skeletal_count = sum(isinstance(a, unreal.SkeletalMeshActor) for a in ACTORS.get_all_level_actors())
    require(skeletal_count == 1, 'Each isolated unit-review map must have exactly one Mother skeletal actor')
    for asset in imported:
        require(asset.get_path_name().startswith(folder + '/'), 'Refusing to save any reused/protected asset')
        LIB.save_loaded_asset(asset)
    require(LEVELS.save_current_level(), 'Cannot save the new unit-review map')
    human_height_passed = 125 <= height <= 210
    return {'id': case['id'], 'success': True, 'native_executed': True, 'namespace': folder, 'mesh': mesh.get_path_name(),
        'animation': animation.get_path_name(), 'map': map_path, 'actor': actor.get_name(), 'skeletal_actor_count': skeletal_count,
        'source_fbx': case['fbx'], 'source_fbx_sha256': case['fbx_sha256'], 'source_bone_count': case['source_bone_count'],
        'native_bone_count': len(names), 'native_bone_names': names, 'native_extra_bones': sorted(set(names)-set(case['source_bone_names'])),
        'native_unit_scale': native_scale, 'world_height_cm': height, 'human_height_passed': human_height_passed,
        'actor_bounds_cm': {'origin': [origin.x,origin.y,origin.z], 'extent': [extent.x,extent.y,extent.z]},
        'native_morph_names': morphs, 'native_morph_count': len(morphs), 'effective_source_morph_names': effective,
        'authored_animation_evaluations': poses, 'authored_bone_and_curve_data_passed': True,
        'unit_gate_passed': native_scale['unit_root_scale_passed'] and human_height_passed,
        'materials_reused_unchanged': assigned, 'coordinate_representation_changed': case['unit_representation_changed'],
        'visible_blink_or_cloth_deformation_reverified': False, 'Manny_retarget_verified': False, 'story_npcs_replaced': False,
        'owned_asset_sha256': {str(p): sha(p) for p in file_guards.files(disk)}}


def main():
    require(PROJECT == SOURCE_PATH.parents[1] and ROOT.name == 'Release_20261026', 'Exact protected Release project required')
    command = unreal.SystemLibrary.get_command_line()
    require('-run=' not in command.lower() and not LEVELS.is_in_play_in_editor(), 'Full editor outside PIE required')
    match = re.search(r'(?i)(?:^|\s)-ReleaseUnitProbeManifest=(?:"([^"]+)"|(\S+))', command)
    require(match, 'Explicit -ReleaseUnitProbeManifest path required')
    path = Path(match.group(1) or match.group(2)).resolve()
    require(path.is_relative_to(ROOT / 'output/character_unit_probe'), 'Probe manifest must be inside the new experiment output')
    probe = json.loads(path.read_text())
    require(probe['success'] and probe['protected_old_assets_reports_unchanged'] and len(probe['variants']) == 4, 'Complete four-case export proof required')
    effective = effective_source_names(probe)
    main_mother = json.loads(mother.REPORT.read_text())
    require(main_mother['success'], 'Existing proved native Mother materials required')
    materials = {entry['slot']: unreal.load_asset(entry['material']) for entry in main_mother['materials']}
    require(all(materials.values()), 'A reused native material is missing')
    for material in set(materials.values()):
        mother.graph.check_material_compile(material)
    parent = '/Game/Release/CharacterUnitProbe/Probe_' + sha(path)[:16]
    disk_parent = PROJECT / 'Content' / Path(parent.removeprefix('/Game/'))
    before, old_before, saves_before = file_guards.native(PROJECT, disk_parent), old_proof_files(), saved_games()
    prior = json.loads(REPORT_PATH.read_text()) if REPORT_PATH.is_file() else {}
    preceding = {c['id']: c for c in prior.get('cases', [])} if prior.get('source_manifest_sha256') == sha(path) else {}
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    history = PROJECT / 'validation/release_character_units' / run
    history.mkdir(parents=True)
    report = {'success': False, 'native_executed': True, 'run': run, 'source_manifest': str(path), 'source_manifest_sha256': sha(path),
        'scope': 'Actual new native unit-coordinate import/data proof. No Mother promotion, NPC swap, visible gait or retarget proof.',
        'cases': [], 'preferred_candidate': None, 'Mother_main_report_promoted': False, 'story_npcs_replaced': False,
        'saved_games_written': False, 'reused_material_assets_saved': False}
    def write():
        text = json.dumps(report, indent=2) + '\n'
        REPORT_PATH.write_text(text)
        (history / 'report.json').write_text(text)
    try:
        for case in probe['variants']:
            report['active_case'] = case['id']; write()
            report['cases'].append(import_case(case, parent, effective, materials, preceding.get(case['id'])))
            write()
        preferred = next((c for choice in ['CentimeterData_ArmatureName','CentimeterData_UNITS'] for c in report['cases']
                          if c['id'] == choice and c['unit_gate_passed']), None)
        report['preferred_candidate'] = preferred
        report['normalized_candidate_available'] = preferred is not None
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    finally:
        after, old_after, saves_after = file_guards.native(PROJECT, disk_parent), old_proof_files(), saved_games()
        report['guards'] = {'all_existing_native_assets_config_unchanged': before == after,
            'all_old_Mother_outputs_reports_unchanged': old_before == old_after, 'saved_games_unchanged': saves_before == saves_after}
        report['success'] = report['success'] and all(report['guards'].values())
        report['protected_old_proof_sha256'] = old_before
        write()
        unreal.log('RELEASE_CHARACTER_UNIT_PROBE_REPORT ' + str(REPORT_PATH))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        (PROJECT / 'release_character_unit_probe_setup_failure.json').write_text(json.dumps({'success': False, 'native_executed': True, 'error': traceback.format_exc()}, indent=2))
        unreal.log_error(traceback.format_exc())
    finally:
        unreal.SystemLibrary.quit_editor()
