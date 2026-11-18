"""Queued import of the Mother human into a NEW isolated native art-review map.

Creates only /Game/Release/CharacterReview/Mother_<source signature>. No stable
NPC replacement, gameplay map save, story flag change or user-save operation.
Full UnrealEditor -ExecutePythonScript is required; not a Python commandlet.
"""
from pathlib import Path
import hashlib
import json
import sys
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
ROOT = PROJECT.parent
sys.path.insert(0, str(PROJECT / 'Python'))
import quest_scenery as graph

ASSETS = unreal.AssetToolsHelpers.get_asset_tools()
LIB = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
OWNER = 'TOSOY.ReleaseCharacterArtGateOwned'
REPORT = PROJECT / 'release_character_import_report.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(test, message):
    if not test:
        raise RuntimeError(message)


def protected_files(excluded):
    files = list((PROJECT / 'Content').rglob('*.uasset')) + list((PROJECT / 'Content').rglob('*.umap'))
    files += list((PROJECT / 'Config').glob('*.ini')) + list(PROJECT.glob('*.uproject'))
    return {str(p): sha(p) for p in files if not p.resolve().is_relative_to(excluded.resolve())}


def owned(asset, signature):
    LIB.set_metadata_tag(asset, 'TOSOY.ReleaseCharacter.Owner', OWNER)
    LIB.set_metadata_tag(asset, 'TOSOY.ReleaseCharacter.Signature', signature)


def assert_owned(asset, signature):
    require(LIB.get_metadata_tag(asset, 'TOSOY.ReleaseCharacter.Owner') == OWNER, 'Preserving an unowned asset: ' + asset.get_path_name())
    require(LIB.get_metadata_tag(asset, 'TOSOY.ReleaseCharacter.Signature') == signature, 'Preserving changed asset provenance: ' + asset.get_path_name())


def texture(path, folder, signature, alpha=False):
    file = Path(path)
    name = 'T_Mother_' + file.stem
    asset_path = folder + '/Textures/' + name
    result = unreal.load_asset(asset_path)
    if result:
        assert_owned(result, signature)
        return result
    task = unreal.AssetImportTask()
    for key, value in {'filename': str(file), 'destination_path': folder + '/Textures',
                       'destination_name': name, 'automated': True, 'replace_existing': False, 'save': False}.items():
        task.set_editor_property(key, value)
    ASSETS.import_asset_tasks([task])
    imported = [unreal.load_asset(str(p)) for p in task.get_editor_property('imported_object_paths')]
    result = next((a for a in imported if isinstance(a, unreal.Texture2D)), None)
    require(result, 'Texture import failed: ' + str(file))
    result.set_editor_property('srgb', True)
    result.set_editor_property('max_texture_size', 2048 if 'diffuse' in file.stem else 1024)
    result.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
    owned(result, signature)
    return result


def material(name, recipe, folder, signature):
    path = folder + '/Materials/' + name
    mat = unreal.load_asset(path)
    if mat:
        assert_owned(mat, signature)
        graph.check_material_compile(mat)
        return mat
    mat = ASSETS.create_asset(name, folder + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    require(mat, 'Cannot create character material ' + path)
    owned(mat, signature)
    mat.set_editor_property('two_sided', bool(recipe.get('two_sided')))
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED if recipe.get('blend_mode') == 'masked' else unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('opacity_mask_clip_value', float(recipe.get('opacity_mask_clip_value', 0.33)))
    MEL.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
    MEL.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS)
    require(bool(mat.get_editor_property('used_with_skeletal_mesh')), 'Skeletal material usage was not enabled')
    if recipe.get('base_color_texture'):
        file = Path(recipe['base_color_texture'])
        require(sha(file) == recipe['texture_sha256'], 'Texture source changed: ' + str(file))
        tex = texture(file, folder, signature, recipe.get('blend_mode') == 'masked')
        sampled = graph.sample(mat, tex)
        gain = graph.node(mat, 'Multiply')
        graph.connect(sampled, gain, 'A', 'RGB')
        graph.connect(graph.color(mat, recipe.get('linear_gain', [1, 1, 1])), gain, 'B')
        graph.output(gain, mat, unreal.MaterialProperty.MP_BASE_COLOR)
        if recipe.get('blend_mode') == 'masked':
            graph.output(sampled, mat, unreal.MaterialProperty.MP_OPACITY_MASK, 'A')
    else:
        graph.output(graph.color(mat, recipe['base_color_linear']), mat, unreal.MaterialProperty.MP_BASE_COLOR)
    for key, property in [('roughness', unreal.MaterialProperty.MP_ROUGHNESS), ('specular', unreal.MaterialProperty.MP_SPECULAR), ('metallic', unreal.MaterialProperty.MP_METALLIC)]:
        graph.output(graph.scalar(mat, recipe[key]), mat, property)
    graph.check_material_compile(mat)
    return mat


def import_fbx(source, folder, signature):
    existing = [unreal.load_asset(p) for p in LIB.list_assets(folder + '/Meshes', recursive=True)]
    existing_mesh = next((a for a in existing if isinstance(a, unreal.SkeletalMesh)), None)
    if existing_mesh:
        for asset in existing:
            assert_owned(asset, signature)
        return existing
    options = unreal.FbxImportUI()
    for key, value in {'import_mesh': True, 'import_as_skeletal': True, 'import_animations': True,
                       'import_materials': False, 'import_textures': False, 'create_physics_asset': False,
                       'automated_import_should_detect_type': False,
                       'mesh_type_to_import': unreal.FBXImportType.FBXIT_SKELETAL_MESH}.items():
        options.set_editor_property(key, value)
    mesh_options = options.get_editor_property('skeletal_mesh_import_data')
    for key, value in {'import_morph_targets': True, 'update_skeleton_reference_pose': False,
                       'use_t0_as_ref_pose': False, 'convert_scene': True, 'convert_scene_unit': True,
                       'normal_import_method': unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS}.items():
        mesh_options.set_editor_property(key, value)
    animation_options = options.get_editor_property('anim_sequence_import_data')
    animation_options.set_editor_property('use_default_sample_rate', True)
    animation_options.set_editor_property('animation_length', unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    task = unreal.AssetImportTask()
    for key, value in {'filename': source['path'], 'destination_path': folder + '/Meshes',
                       'destination_name': 'SK_Release_Mother', 'automated': True, 'replace_existing': False,
                       'save': False, 'factory': unreal.FbxFactory(), 'options': options}.items():
        task.set_editor_property(key, value)
    ASSETS.import_asset_tasks([task])
    imported = [unreal.load_asset(str(p)) for p in task.get_editor_property('imported_object_paths')]
    # The native importer can create extra objects not listed in the top-level task.
    imported += [unreal.load_asset(p) for p in LIB.list_assets(folder + '/Meshes', recursive=True)]
    unique = {a.get_path_name(): a for a in imported if a}
    for asset in unique.values():
        owned(asset, signature)
    return list(unique.values())


def build_native():
    require(ROOT.name == 'Release_20261026', 'Character import refuses a protected source project')
    require('-run=' not in unreal.SystemLibrary.get_command_line().lower(), 'Character review requires the full editor')
    latest = json.loads((ROOT / 'output/release_characters/latest.json').read_text())
    source_manifest = Path(latest['manifest'])
    data = json.loads(source_manifest.read_text())
    require(data['success'] and data['facial_morph_count'] == 52, 'Mother source proof is incomplete')
    require(data.get('art_revision', 0) >= 4, 'Revisions1/2/3 are rejected: garment/covered-skin fixes must be proved first')
    require(data.get('verified_clothing_fit', {}).get('original_broken_garments_exported') is False, 'Failed custom garments remain in the source')
    require(data.get('covered_skin_occlusion', {}).get('shape_key_coordinates_unchanged') is True, 'Covered-skin morph-preservation guard is missing')
    require(sha(data['fbx']['path']) == data['fbx']['sha256'], 'FBX differs from the proved source')
    effective = data.get('effective_morph_measurement')
    morph_proof = str(source_manifest)
    if not effective:
        audit_file = Path(latest.get('effective_morph_audit', ''))
        require(audit_file.is_file() and audit_file.resolve().is_relative_to(source_manifest.parent.resolve()), 'Queue --audit-existing-morphs to measure the actual proved export meshes')
        require(sha(audit_file) == latest.get('effective_morph_audit_sha256'), 'Effective morph audit changed')
        effective = json.loads(audit_file.read_text())
        require(effective.get('success') and effective.get('source_manifest_sha256') == sha(source_manifest), 'Effective morph audit does not match the source manifest')
        require(effective.get('source_blend_sha256') == sha(data['blend']) and effective.get('source_fbx_sha256') == data['fbx']['sha256'], 'Effective morph audit does not match the proved geometry/export')
        morph_proof = str(audit_file)
    require(sorted(effective['source_shape_key_names']) == sorted(data['facial_morphs']), 'Measured source shape-key set differs')
    effective_names = sorted(name for name, metric in effective['metrics'].items() if metric['changed_vertices'] > 0)
    require(effective_names == sorted(effective['effective_facial_morphs']) and len(effective_names) == effective['effective_facial_morph_count'], 'Effective morph classification is inconsistent with measured vertex deltas')
    require(sorted(set(data['facial_morphs']) - set(effective_names)) == sorted(effective['non_deforming_facial_shape_keys']), 'Non-deforming source-key classification differs')
    recipes = data['material_recipes']
    signature = hashlib.sha256((data['fbx']['sha256'] + json.dumps(recipes, sort_keys=True)).encode()).hexdigest()[:16]
    folder = '/Game/Release/CharacterReview/Mother_' + signature
    disk_folder = PROJECT / 'Content/Release/CharacterReview' / ('Mother_' + signature)
    before = protected_files(disk_folder)
    if REPORT.exists():
        preceding = json.loads(REPORT.read_text())
        if preceding.get('namespace') == folder:
            for file, digest in preceding.get('owned_asset_sha256', {}).items():
                require(Path(file).is_file() and sha(file) == digest, 'Preserving a manually edited character review asset: ' + file)
    mats = {name: material(name, recipe, folder, signature) for name, recipe in recipes.items()}
    imported = import_fbx(data['fbx'], folder, signature)
    meshes = [asset for asset in imported if isinstance(asset, unreal.SkeletalMesh)]
    animations = [asset for asset in imported if isinstance(asset, unreal.AnimSequence)]
    require(len(meshes) == 1, 'Expected one combined rigged Mother mesh; found ' + str(len(meshes)))
    require(len(animations) >= 1, 'No actual skeletal listening animation imported')
    mesh = meshes[0]
    morph_names = [target.get_name() for target in mesh.call_method('GetMorphTargetsPtrConv')]
    missing = [name for name in effective_names if not any(n == name or n.endswith('_' + name) for n in morph_names)]
    require(not missing, 'Native morph targets missing: ' + ', '.join(missing))
    slots = list(mesh.get_editor_property('materials'))
    assigned = []
    for slot in slots:
        name = str(slot.get_editor_property('imported_material_slot_name'))
        match = name if name in mats else next((key for key in mats if name.replace('.', '_').endswith(key)), None)
        require(match is not None, 'Unknown imported material slot: ' + name)
        slot.set_editor_property('material_interface', mats[match])
        assigned.append({'slot': name, 'material': mats[match].get_path_name()})
    mesh.set_editor_property('materials', slots)
    animation = max(animations, key=lambda asset: asset.get_play_length())
    require(3.8 <= animation.get_play_length() <= 4.2, 'Unexpected listening animation duration')
    map_path = folder + '/L_MotherArtGate'
    require(not LIB.does_asset_exist(map_path), 'Art-review map already exists; preserving it. Use existing report or a new source version.')
    require(LEVELS.new_level(map_path), 'Could not create isolated art-review level')
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    actor = ACTORS.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0))
    actor.set_actor_label('Release art gate - Mother - not a story NPC')
    actor.set_editor_property('tags', [unreal.Name(OWNER)])
    actor.set_actor_enable_collision(False)
    component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    component.set_skeletal_mesh_asset(mesh)
    component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    component.play_animation(animation, True)
    component.set_position(0.0, False)
    origin, extent = actor.get_actor_bounds(False)
    require(125 <= extent.z * 2 <= 210, 'Imported human scale is invalid: ' + str(extent))
    sun = ACTORS.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 300), unreal.Rotator(pitch=-35, yaw=-30, roll=0))
    sun.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property('intensity', 3.5)
    sky = ACTORS.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 300))
    sky_component = sky.get_component_by_class(unreal.SkyLightComponent)
    cube = unreal.load_asset('/Game/Quest/PremiumArt/Data_c12ac589619f/T_PH_BelfastSunset_HDRCube')
    require(cube, 'Existing authorized review HDR cubemap missing')
    sky_component.set_editor_property('source_type', unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
    sky_component.set_editor_property('cubemap', cube)
    sky_component.set_editor_property('intensity', 0.105)
    for material_asset in mats.values():
        graph.check_material_compile(material_asset)
    for asset in set(imported + list(mats.values())):
        LIB.save_loaded_asset(asset)
    for path in LIB.list_assets(folder + '/Textures', recursive=True):
        LIB.save_loaded_asset(unreal.load_asset(path))
    require(LEVELS.save_current_level(), 'Could not save isolated review map')
    after = protected_files(disk_folder)
    require(before == after, 'Protected native files changed outside the new character namespace')
    result = {'success': True, 'scope': 'Imported/compiled isolated native human art gate. No story NPC swap and no captured performance claimed.',
        'source_manifest': str(source_manifest), 'source_manifest_sha256': sha(source_manifest), 'namespace': folder,
        'map': map_path, 'mesh': mesh.get_path_name(), 'native_morph_count': len(morph_names), 'native_morph_names': morph_names,
        'source_facial_shape_key_count': len(data['facial_morphs']), 'effective_source_morph_count': len(effective_names),
        'effective_source_morph_names': effective_names, 'non_deforming_source_keys': effective['non_deforming_facial_shape_keys'],
        'effective_morph_proof': morph_proof, 'effective_morph_proof_sha256': sha(morph_proof),
        'animation': animation.get_path_name(), 'animation_seconds': animation.get_play_length(), 'materials': assigned,
        'actor_bounds_cm': {'origin': [origin.x, origin.y, origin.z], 'extent': [extent.x, extent.y, extent.z]},
        'actor': actor.get_name(), 'story_npcs_replaced': False, 'gameplay_maps_saved': False, 'save_profiles_written': False,
        'protected_native_files_unchanged': before == after, 'protected_sha256': before,
        'owned_asset_sha256': {str(p): sha(p) for p in disk_folder.rglob('*') if p.is_file()},
        'captured': False, 'native_cloth_deformation_reviewed': False,
        'next_gate': 'Actual native open-eye/closed-blink/full-body and listening-motion captures before any stable NPC integration.'}
    REPORT.write_text(json.dumps(result, indent=2) + '\n')
    unreal.log('RELEASE_MOTHER_NATIVE_IMPORT_SUCCESS ' + str(REPORT))
    return result


if __name__ == '__main__':
    try:
        build_native()
    except Exception as error:
        REPORT.write_text(json.dumps({'success': False, 'error': str(error), 'traceback': traceback.format_exc(),
            'scope': 'Character review import only; inspect any partial owned namespace before retry.'}, indent=2) + '\n')
        unreal.log_error(traceback.format_exc())
    finally:
        unreal.SystemLibrary.quit_editor()
