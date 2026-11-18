"""Queued native Healer/Sela/Neri candidates; new review namespaces only.

Uses the proven Mother FBX/material settings with role-specific names and
measured morph sets. Does not edit the Mother importer, its latest/report,
existing story NPCs, gameplay maps, configuration or saved games.
Full editor: -ExecutePythonScript=this_file -ReleaseRole=Healer|Sela|Neri
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
import sys
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
ROOT = PROJECT.parent
sys.path.insert(0, str(PROJECT / 'Python'))
import import_release_characters as mother
import import_release_unit_probe as unit_native
sys.path.insert(0, str(ROOT / 'tools'))
import windows_file_guards as file_guards

LIB, ASSETS, MEL, GRAPH = mother.LIB, mother.ASSETS, mother.MEL, mother.graph
LEVELS, ACTORS = mother.LEVELS, mother.ACTORS
ROLES = ('Healer', 'Sela', 'Neri')
OWNER = 'TOSOY.ReleaseNPCCandidateOwned'
sha, require = file_guards.sha, mother.require


def json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def saved_games():
    roots = [PROJECT / 'Saved/SaveGames', Path(os.environ.get('LOCALAPPDATA', '')) / 'YesterdayHarbor/Saved/SaveGames']
    return {str(p): sha(p) for root in roots if root.is_dir() for p in root.rglob('*.sav')}


def mother_artifacts():
    latest = ROOT / 'output/release_characters/latest.json'
    row = json.loads(latest.read_text())
    manifest = Path(row['manifest'])
    data = json.loads(manifest.read_text())
    paths = [latest, manifest, Path(data['fbx']['path']), Path(data['blend']),
             PROJECT / 'release_character_import_report.json', PROJECT / 'release_character_cardinals_report.json',
             PROJECT / 'release_character_face_pose_report.json']
    return {str(p): sha(p) for p in paths if Path(file_guards.io_path(p)).is_file()}


def metadata(asset, role, signature):
    LIB.set_metadata_tag(asset, 'TOSOY.ReleaseRole.Owner', OWNER)
    LIB.set_metadata_tag(asset, 'TOSOY.ReleaseRole.Character', role)
    LIB.set_metadata_tag(asset, 'TOSOY.ReleaseRole.Signature', signature)


def verify_owned(asset, role, signature):
    require(LIB.get_metadata_tag(asset, 'TOSOY.ReleaseRole.Owner') == OWNER, 'Preserving unowned candidate asset: ' + asset.get_path_name())
    require(LIB.get_metadata_tag(asset, 'TOSOY.ReleaseRole.Character') == role, 'Character ownership differs')
    require(LIB.get_metadata_tag(asset, 'TOSOY.ReleaseRole.Signature') == signature, 'Candidate provenance differs')


def import_texture(path, folder, role, signature):
    file = Path(path)
    name = 'T_' + role + '_' + re.sub(r'[^A-Za-z0-9_]', '_', file.stem) + '_' + sha(file)[:8]
    tex = unreal.load_asset(folder + '/Textures/' + name)
    if tex:
        verify_owned(tex, role, signature)
        require(LIB.get_metadata_tag(tex, 'TOSOY.ReleaseRole.SourceSha256') == sha(file), 'Candidate texture source differs')
        return tex
    task = unreal.AssetImportTask()
    for key, value in {'filename': str(file), 'destination_path': folder + '/Textures', 'destination_name': name,
        'automated': True, 'replace_existing': False, 'save': False}.items():
        task.set_editor_property(key, value)
    ASSETS.import_asset_tasks([task])
    assets = [unreal.load_asset(str(p)) for p in task.get_editor_property('imported_object_paths')]
    tex = next((a for a in assets if isinstance(a, unreal.Texture2D)), None)
    require(tex, 'Candidate texture import failed: ' + str(file))
    tex.set_editor_property('srgb', True)
    tex.set_editor_property('max_texture_size', 2048 if 'diffuse' in file.stem else 1024)
    tex.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
    metadata(tex, role, signature)
    LIB.set_metadata_tag(tex, 'TOSOY.ReleaseRole.SourceSha256', sha(file))
    return tex


def material(name, recipe, folder, role, signature):
    """Same native graph/usage settings as the proved Mother helper, new assets."""
    require(name.startswith('M_Release_' + role + '_'), 'Material name is not role-specific: ' + name)
    path = folder + '/Materials/' + name
    mat = unreal.load_asset(path)
    if mat:
        verify_owned(mat, role, signature)
        require(LIB.get_metadata_tag(mat, 'TOSOY.ReleaseRole.CompleteRecipeSha256') == json_sha(recipe),
                'Preserving an incomplete or edited candidate material: ' + path)
        GRAPH.check_material_compile(mat)
        return mat
    mat = ASSETS.create_asset(name, folder + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    require(mat, 'Cannot create candidate material: ' + path)
    metadata(mat, role, signature)
    mat.set_editor_property('two_sided', bool(recipe.get('two_sided')))
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED if recipe.get('blend_mode') == 'masked' else unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('opacity_mask_clip_value', float(recipe.get('opacity_mask_clip_value', 0.33)))
    MEL.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
    MEL.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS)
    require(mat.get_editor_property('used_with_skeletal_mesh') and mat.get_editor_property('used_with_morph_targets'), 'Required skeletal/morph usage was not enabled')
    if recipe.get('base_color_texture'):
        require(sha(recipe['base_color_texture']) == recipe['texture_sha256'], 'Candidate texture differs from the measured source')
        tex = import_texture(recipe['base_color_texture'], folder, role, signature)
        sample = GRAPH.sample(mat, tex)
        gain = GRAPH.node(mat, 'Multiply')
        GRAPH.connect(sample, gain, 'A', 'RGB')
        GRAPH.connect(GRAPH.color(mat, recipe.get('linear_gain', [1, 1, 1])), gain, 'B')
        GRAPH.output(gain, mat, unreal.MaterialProperty.MP_BASE_COLOR)
        if recipe.get('blend_mode') == 'masked':
            GRAPH.output(sample, mat, unreal.MaterialProperty.MP_OPACITY_MASK, 'A')
    else:
        GRAPH.output(GRAPH.color(mat, recipe['base_color_linear']), mat, unreal.MaterialProperty.MP_BASE_COLOR)
    for key, prop in [('roughness', unreal.MaterialProperty.MP_ROUGHNESS), ('specular', unreal.MaterialProperty.MP_SPECULAR), ('metallic', unreal.MaterialProperty.MP_METALLIC)]:
        GRAPH.output(GRAPH.scalar(mat, recipe[key]), mat, prop)
    GRAPH.check_material_compile(mat)
    LIB.set_metadata_tag(mat, 'TOSOY.ReleaseRole.CompleteRecipeSha256', json_sha(recipe))
    return mat


def import_fbx(data, folder, role, signature):
    existing = [unreal.load_asset(p) for p in LIB.list_assets(folder + '/Meshes', recursive=True)]
    existing = [a for a in existing if a]
    if existing:
        for asset in existing:
            verify_owned(asset, role, signature)
        require(any(isinstance(a, unreal.SkeletalMesh) for a in existing) and any(isinstance(a, unreal.AnimSequence) for a in existing), 'Partial imported mesh/animation namespace; inspect rather than overwrite it')
        return existing
    options = unreal.FbxImportUI()
    for key, value in {'import_mesh': True, 'import_as_skeletal': True, 'import_animations': True,
        'import_materials': False, 'import_textures': False, 'create_physics_asset': False,
        'automated_import_should_detect_type': False, 'mesh_type_to_import': unreal.FBXImportType.FBXIT_SKELETAL_MESH}.items():
        options.set_editor_property(key, value)
    for key, value in {'import_morph_targets': True, 'update_skeleton_reference_pose': False, 'use_t0_as_ref_pose': False,
        'convert_scene': True, 'convert_scene_unit': True, 'normal_import_method': unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS}.items():
        options.get_editor_property('skeletal_mesh_import_data').set_editor_property(key, value)
    anim_options = options.get_editor_property('anim_sequence_import_data')
    anim_options.set_editor_property('use_default_sample_rate', True)
    anim_options.set_editor_property('animation_length', unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    task = unreal.AssetImportTask()
    for key, value in {'filename': data['fbx']['path'], 'destination_path': folder + '/Meshes',
        'destination_name': 'SK_Release_' + role, 'automated': True, 'replace_existing': False,
        'save': False, 'factory': unreal.FbxFactory(), 'options': options}.items():
        task.set_editor_property(key, value)
    ASSETS.import_asset_tasks([task])
    assets = [unreal.load_asset(str(p)) for p in task.get_editor_property('imported_object_paths')]
    assets += [unreal.load_asset(p) for p in LIB.list_assets(folder + '/Meshes', recursive=True)]
    unique = {a.get_path_name(): a for a in assets if a}
    for asset in unique.values():
        metadata(asset, role, signature)
    return list(unique.values())


def source(role):
    latest_path = ROOT / 'output/release_npc_variations' / role / 'latest.json'
    latest = json.loads(latest_path.read_text())
    path = Path(latest['manifest']).resolve()
    require(path.is_relative_to(latest_path.parent / 'builds'), 'Variant manifest must stay in its role-specific output')
    data = json.loads(path.read_text())
    require(data['success'] and data['character'] == role and data['mother_artifacts_unchanged'] and data['native_project_unchanged'], 'Role source proof is incomplete')
    require(sha(data['fbx']['path']) == data['fbx']['sha256'], 'Role FBX changed after proof')
    require(data['coordinate_representation'] == 'CentimeterData_ArmatureName' and data['unit_representation_changed']
            and data['export_armature_object_name'] == 'Armature' and abs(data['scene_meters_per_unit']-0.01) < 1e-7,
            'Rejecting old meter-data/extra-unit-root role exports')
    require(data['local_rest_matrix_equality_not_claimed'] and data['pre_conversion_source_rest_basis_preserved'], 'Honest unit-representation metadata required')
    require(json_sha(data['normalized_rest_bone_matrices_local']) == data['normalized_rest_bone_basis_sha256'], 'Normalized local rest-bone basis hash differs')
    require(sorted(data['normalized_rest_bone_matrices_local']) == sorted(data['rest_bone_names']), 'Source bone-name set differs')
    require(data['source_core_bone_count'] == data['expected_native_core_bone_count'] == len(data['rest_bone_names']) == 53,
            'Expected the measured53-core-bone GameEngine rig; native extra armature bone is rejected')
    require(data['physical_rest_position_preservation']['max_physical_world_delta_m'] <= 3e-5
            and data['physical_pose_preservation']['max_deformed_vertex_coordinate_delta_m'] <= 3e-5
            and data['physical_pose_preservation']['max_bone_head_tail_delta_m'] <= 3e-5
            and data['physical_morph_coordinate_preservation']['max_physical_coordinate_delta_m'] <= 2e-6
            and data['physical_pose_preservation']['shape_key_curve_values_identical_at_all_samples']
            and data['non_length_animation_and_face_curve_keys_unchanged'], 'Physical rest/deformed/morph/face-curve preservation proof failed')
    builder_snapshot = path.parent / 'builder_source_snapshot.py'
    require(Path(file_guards.io_path(builder_snapshot)).is_file() and sha(builder_snapshot) == data['source_builder_sha256'],
            'Exact source snapshot for this generated role is missing or changed')
    require(sha(ROOT / 'build_release_characters.py') == data['mother_helper_source_sha256'], 'Proved helper source changed after role export')
    require(sha(ROOT / 'build_release_unit_probe.py') == data['unit_helper_source_sha256'], 'Proved unit-conversion helper changed after role export')
    require(sha(file_guards.__file__) == data['long_path_guard_source_sha256'], 'Long-path file guard changed after role export')
    unit_reference = Path(data['normalization_reference_report'])
    require(sha(unit_reference) == data['normalization_reference_sha256'], 'Native unit-reference report changed')
    reference = json.loads(unit_reference.read_text())
    require(reference['success'] and reference['native_executed'] and reference['preferred_candidate']['native_unit_scale']['unit_root_scale_passed'], 'Actual native normalization proof missing')
    require(all(Path(p).is_file() and Path(p).stat().st_size > 10000 for p in data['previews']), 'Actual role-specific preview images missing')
    art_review_path = path.parent / 'visual_review.json'
    require(art_review_path.is_file(), 'Inspect all actual role previews and record a separate visual review before import')
    art_review = json.loads(art_review_path.read_text())
    require(art_review['source_manifest_sha256'] == sha(path) and art_review['blender_static_art_review_passed']
            and all(sha(image['path']) == image['sha256'] for image in art_review['images']),
            'Role preview review is rejected, incomplete or belongs to different actual images')
    height = float(data['measured_body_height_m'])
    require(math.isfinite(height) and 1.20 <= height <= 1.95, 'Invalid measured human source height')
    for selected in data['selected_assets']:
        require(sha(selected['path']) == selected['sha256'] and 'CC0' in selected['license_header'] and 'AGPL' not in selected['license_header'], 'Selected role asset hash/license differs')
    coverage = data.get('covered_skin_occlusion')
    if coverage:
        require(coverage['shape_key_coordinates_unchanged'] and coverage['protected_faces_retained'], 'Covered-skin facial/hand preservation failed')
    measured = data['effective_morph_measurement']
    names = measured['source_shape_key_names']
    require(len(names) == len(set(names)) == data['source_facial_shape_key_count'] == measured['source_shape_key_count'], 'Source morph count/set is inconsistent')
    require(set(names) == set(measured['metrics']), 'Not every source key has a measured delta')
    effective = sorted(n for n in names if measured['metrics'][n]['changed_vertices'] > 0)
    require(effective == sorted(measured['effective_facial_morphs']) and len(effective) == measured['effective_facial_morph_count'], 'Effective morph classification differs from measured deltas')
    require(sorted(set(names) - set(effective)) == sorted(measured['non_deforming_facial_shape_keys']), 'Zero-delta classification differs')
    for name, metric in measured['metrics'].items():
        require(metric['changed_vertices'] == sum(m['changed_vertices'] for m in metric['meshes']), 'Per-mesh morph totals differ: ' + name)
        require(math.isfinite(metric['max_delta_m']) and metric['max_delta_m'] >= 0, 'Invalid measured morph delta')
    require({'eyeBlinkLeft', 'eyeBlinkRight'}.issubset(effective), 'Both real eyelid targets must deform source vertices')
    return path, data, effective


def build_native(role):
    require(role in ROLES and ROOT.name == 'Release_20261026' and PROJECT == Path(__file__).resolve().parents[1], 'Exact protected Release/role required')
    require('-run=' not in unreal.SystemLibrary.get_command_line().lower() and not LEVELS.is_in_play_in_editor(), 'Full editor outside PIE required')
    manifest, data, effective = source(role)
    signature = json_sha({'role': role, 'fbx': data['fbx']['sha256'], 'materials': data['material_recipes'], 'normalized_bone_basis': data['normalized_rest_bone_basis_sha256']})[:16]
    folder = '/Game/Release/CharacterReview/' + role + '_' + signature
    disk = PROJECT / 'Content/Release/CharacterReview' / (role + '_' + signature)
    report_path = PROJECT / ('release_' + role.lower() + '_import_report.json')
    before, saved_before, mother_before = file_guards.native(PROJECT, disk), saved_games(), mother_artifacts()
    if report_path.is_file():
        preceding = json.loads(report_path.read_text())
        if preceding.get('namespace') == folder:
            for path, digest in preceding.get('owned_asset_sha256', {}).items():
                require(Path(file_guards.io_path(path)).is_file() and sha(path) == digest, 'Preserving a manually edited role candidate: ' + path)
            if preceding.get('success'):
                require(LIB.does_asset_exist(preceding['map']), 'Previously proved role map is missing')
                return preceding  # Idempotent, no save or report/Mother mutation.
    mats = {name: material(name, recipe, folder, role, signature) for name, recipe in data['material_recipes'].items()}
    imported = import_fbx(data, folder, role, signature)
    meshes = [a for a in imported if isinstance(a, unreal.SkeletalMesh)]
    animations = [a for a in imported if isinstance(a, unreal.AnimSequence)]
    require(len(meshes) == 1 and meshes[0].get_name() == 'SK_Release_' + role, 'Unexpected role mesh name/count')
    require(animations, 'No actual skeletal listening animation imported')
    mesh, animation = meshes[0], max(animations, key=lambda a: a.get_play_length())
    morphs = [a.get_name() for a in mesh.call_method('GetMorphTargetsPtrConv')]
    mapping = {n: [m for m in morphs if m == n or m.endswith('_' + n)] for n in effective}
    require(all(len(v) == 1 for v in mapping.values()) and len(morphs) == len(effective), 'Native measured morph set/count differs; do not manufacture zero-delta targets')
    slots, assignments = list(mesh.get_editor_property('materials')), []
    for slot in slots:
        name = str(slot.get_editor_property('imported_material_slot_name'))
        matches = [k for k in mats if k == name or name.replace('.', '_').endswith(k)]
        require(len(matches) == 1, 'Unknown/ambiguous role material slot: ' + name)
        slot.set_editor_property('material_interface', mats[matches[0]])
        assignments.append({'slot': name, 'material': mats[matches[0]].get_path_name()})
    mesh.set_editor_property('materials', slots)
    require(3.8 <= animation.get_play_length() <= 4.2, 'Unexpected native listening duration')
    evaluated = unit_native.evaluate(animation, mesh, data['rest_bone_names'])
    require(all(row['bone_motion_passed'] and row['blink_curve_peak_passed'] for row in evaluated), 'Role authored native animation/face-curve data failed')
    reference = evaluated[0]['samples'][0]
    actual_names = list(reference['reference_local'])
    require(len(actual_names) == 53 and set(actual_names) == set(data['rest_bone_names']) and actual_names[0] == 'Root',
            'Native normalized role must have exactly the53 source core bones, first Root, with no extra unit parent')
    first = actual_names[0]
    native_unit_scale = {'first_bone': first, 'first_bone_local_scale': reference['reference_local'][first]['scale'],
        'core_root_bone': 'Root', 'core_root_local_scale': reference['reference_local']['Root']['scale'],
        'core_root_component_scale': reference['reference_component']['Root']['scale'],
        'all_reference_bone_local_scales_are_one': all(unit_native.scale_one(row['scale']) for row in reference['reference_local'].values())}
    native_unit_scale['unit_root_scale_passed'] = (native_unit_scale['all_reference_bone_local_scales_are_one']
        and all(unit_native.scale_one(native_unit_scale[key]) for key in ['first_bone_local_scale','core_root_local_scale','core_root_component_scale']))
    require(native_unit_scale['unit_root_scale_passed'], 'Native role retained a non-unit skeleton scale')
    map_path = folder + '/L_' + role + 'ArtGate'
    require(not LIB.does_asset_exist(map_path), 'Preserving existing unproved review map; inspect its ownership instead of overwriting')
    require(LEVELS.new_level(map_path), 'Cannot create isolated role review map')
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    world.get_world_settings().set_editor_property('default_game_mode', unreal.GameModeBase.static_class())
    actor = ACTORS.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector())
    actor.set_actor_label('Release art candidate - ' + role + ' - not a story NPC')
    actor.set_editor_property('tags', [unreal.Name(OWNER), unreal.Name('Release.Role.' + role)])
    actor.set_actor_enable_collision(False)
    component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    component.set_skeletal_mesh_asset(mesh)
    bones = [str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
    require(len(bones) == 53 and set(bones) == set(data['rest_bone_names']), 'Native mesh component source core-bone set differs')
    basis = reference['reference_component']
    origin, extent = actor.get_actor_bounds(False)
    native_height, source_height = extent.z * 2, data['measured_body_height_m'] * 100
    require(abs(native_height - source_height) <= max(12, source_height * 0.10), 'Native clothed height differs excessively from measured body height')
    require(120 <= native_height <= 210, 'Native role height is outside the explicit human art-review range')
    require(max(abs(row['translation'][2]) for row in basis.values()) > source_height * 0.5, 'Native reference-pose transforms are not populated')
    component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    component.play_animation(animation, True)
    component.set_position(0.0, False)
    sun = ACTORS.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 300), unreal.Rotator(pitch=-35, yaw=-30))
    sun.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property('intensity', 3.5)
    sky = ACTORS.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 300))
    sky_component = sky.get_component_by_class(unreal.SkyLightComponent)
    cube = unreal.load_asset('/Game/Quest/PremiumArt/Data_c12ac589619f/T_PH_BelfastSunset_HDRCube')
    require(cube, 'Existing authorized review HDR cubemap missing')
    for key, value in {'source_type': unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP, 'cubemap': cube, 'intensity': 0.105}.items():
        sky_component.set_editor_property(key, value)
    for mat in mats.values():
        GRAPH.check_material_compile(mat)
    for asset in set(imported + list(mats.values())):
        LIB.save_loaded_asset(asset)
    for path in LIB.list_assets(folder + '/Textures', recursive=True):
        LIB.save_loaded_asset(unreal.load_asset(path))
    require(LEVELS.save_current_level(), 'Cannot save isolated role review map')
    after, saved_after, mother_after = file_guards.native(PROJECT, disk), saved_games(), mother_artifacts()
    require(before == after and saved_before == saved_after and mother_before == mother_after, 'Protected native/config/save or Mother proof files changed')
    result = {'success': True, 'native_executed': True, 'character': role, 'run_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Native isolated character candidate import/compile. Not visible blink, production idle/gait, story integration or finished art proof.',
        'namespace': folder, 'map': map_path, 'mesh': mesh.get_path_name(), 'actor': actor.get_name(),
        'source_manifest': str(manifest), 'source_manifest_sha256': sha(manifest), 'source_fbx_sha256': data['fbx']['sha256'],
        'normalized_source_local_rest_basis_sha256': data['normalized_rest_bone_basis_sha256'],
        'pre_conversion_source_local_rest_basis_sha256': data['pre_conversion_local_rest_basis_sha256'],
        'unit_representation_changed': True, 'coordinate_representation': data['coordinate_representation'],
        'physical_rest_position_preservation': data['physical_rest_position_preservation'],
        'physical_pose_preservation': data['physical_pose_preservation'],
        'physical_morph_coordinate_preservation': data['physical_morph_coordinate_preservation'],
        'native_reference_bone_basis_sha256': json_sha(basis), 'native_bone_count': len(bones), 'native_unit_scale': native_unit_scale,
        'native_reference_bones_component_space': basis, 'native_bone_names': bones,
        'measured_source_body_height_cm': source_height, 'native_clothed_bounds_height_cm': native_height,
        'world_height_cm': native_height, 'human_height_passed': True,
        'actor_bounds_cm': {'origin': [origin.x, origin.y, origin.z], 'extent': [extent.x, extent.y, extent.z]},
        'source_facial_shape_key_count': data['source_facial_shape_key_count'], 'effective_source_morph_names': effective,
        'effective_source_morph_count': len(effective), 'native_morph_names': morphs, 'native_morph_count': len(morphs),
        'non_deforming_source_keys': data['effective_morph_measurement']['non_deforming_facial_shape_keys'],
        'animation': animation.get_path_name(), 'animation_seconds': animation.get_play_length(), 'materials': assignments,
        'authored_animation_evaluations': evaluated, 'authored_bone_and_curve_data_passed': True,
        'protected_native_files_unchanged': before == after, 'saved_games_unchanged': saved_before == saved_after,
        'owned_asset_sha256': {str(p): sha(p) for p in file_guards.files(disk)},
        'story_npcs_replaced': False, 'gameplay_maps_saved': False, 'physics_asset_created': False,
        'Mother_latest_report_assets_unchanged': mother_before == mother_after, 'protected_Mother_sha256': mother_before,
        'captured': False, 'visible_blink_proven': False,
        'next_gate': 'Inspect native cardinal/front art, raw animation tracks and genuinely ticking PIE cloth/face/foot motion before any stable NPC integration.'}
    report_path.write_text(json.dumps(result, indent=2) + '\n')
    unreal.log('RELEASE_ROLE_NATIVE_IMPORT_SUCCESS ' + str(report_path))
    return result


if __name__ == '__main__':
    chosen = None
    try:
        match = re.search(r'(?i)(?:^|\s)-ReleaseRole=(Healer|Sela|Neri)(?:\s|$)', unreal.SystemLibrary.get_command_line())
        chosen = next((role for role in ROLES if match and role.lower() == match.group(1).lower()), None)
        require(chosen, 'Explicit -ReleaseRole=Healer|Sela|Neri required')
        build_native(chosen)
    except Exception:
        name = 'release_' + (chosen.lower() if chosen else 'role_setup') + '_import_failure.json'
        (PROJECT / name).write_text(json.dumps({'success': False, 'character': chosen, 'error': traceback.format_exc(),
            'scope': 'New role candidate namespace only; partial assets must be inspected before retry. Mother and stable NPCs are protected.'}, indent=2) + '\n')
        unreal.log_error(traceback.format_exc())
    finally:
        unreal.SystemLibrary.quit_editor()
