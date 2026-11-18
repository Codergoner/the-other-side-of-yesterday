"""Queued isolated v02 wardrobe import on each role's EXISTING exact skeleton.

Explicit -ReferenceWardrobeManifest="absolute source manifest" is mandatory.
Full editor only. Creates a new owned namespace/review map, never loads a story
map, patches a Blueprint, saves a reused skeleton, or replaces a production NPC.
Root owns the native writer queue. No process is launched by importing this file.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
import traceback
import types
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
ROOT = PROJECT.parent
SOURCE = Path(__file__).resolve()
sys.path.insert(0, str(PROJECT / 'Python'))
sys.path.insert(0, str(ROOT / 'tools'))
import windows_file_guards as io
import import_release_characters as character
import import_release_unit_probe as unit
import release_mother_integration as native_rig
import retarget_release_characters as retarget

LIB = unreal.EditorAssetLibrary
ASSETS = unreal.AssetToolsHelpers.get_asset_tools()
require = character.require
BASELINES = {'Mother': PROJECT / 'release_mother_rev11_import_report.json',
             'Healer': PROJECT / 'release_healer_import_report.json'}


def read(path):
    with open(io.io_path(path), encoding='utf-8') as stream:
        return json.load(stream)


def write(path, value):
    with open(io.io_path(path), 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def existing_reports():
    return {str(p): io.sha(p) for p in PROJECT.glob('release*.json')}


def import_on_existing_skeleton(source, folder, signature, skeleton, role):
    """Same proved FBX options, with explicit matching skeleton and no overwrite."""
    require(not LIB.list_assets(folder + '/Meshes', recursive=True), 'Preserving a partial/existing native candidate')
    options = unreal.FbxImportUI()
    for key, value in {'import_mesh': True, 'import_as_skeletal': True, 'import_animations': True,
        'import_materials': False, 'import_textures': False, 'create_physics_asset': False,
        'automated_import_should_detect_type': False,
        'mesh_type_to_import': unreal.FBXImportType.FBXIT_SKELETAL_MESH, 'skeleton': skeleton}.items():
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
        'destination_name': 'SK_ReleaseV02_' + role, 'automated': True, 'replace_existing': False,
        'save': False, 'factory': unreal.FbxFactory(), 'options': options}.items():
        task.set_editor_property(key, value)
    ASSETS.import_asset_tasks([task])
    imported = [unreal.load_asset(str(p)) for p in task.get_editor_property('imported_object_paths')]
    imported += [unreal.load_asset(p) for p in LIB.list_assets(folder + '/Meshes', recursive=True)]
    unique = {a.get_path_name(): a for a in imported if a and a.get_path_name().startswith(folder + '/')}
    require(unique, 'Native FBX import produced no owned assets')
    for asset in unique.values():
        character.owned(asset, signature)
    return list(unique.values())


def main():
    require(PROJECT == SOURCE.parents[1] and ROOT.name == 'Release_20261026', 'Exact Release copy required')
    command = unreal.SystemLibrary.get_command_line()
    require('-run=' not in command.lower() and not unit.LEVELS.is_in_play_in_editor(), 'Queued full editor outside PIE required')
    match = re.search(r'(?i)(?:^|\s)-ReferenceWardrobeManifest=(?:"([^"]+)"|(\S+))', command)
    require(match, 'Explicit -ReferenceWardrobeManifest path required')
    path = Path(match.group(1) or match.group(2)).resolve()
    require(path.is_relative_to(ROOT / 'output/reference_wardrobe_v02'), 'Source must belong to the new v02 wardrobe output')
    data = read(path)
    role = data['character']
    require(role in BASELINES and data['success'] and data['export_performed'], 'Successful exported role candidate required')
    require(data['protected_old_source_and_native_unchanged'] and data['existing_geometry_topology_uv_weights_unchanged']
        and data['existing_bones_rest_basis_unchanged'] and data['existing_action_keys_unchanged'], 'Source preservation proof incomplete')
    require(data['source_core_bone_count'] == 53 and data['new_bones'] == 0, 'Existing 53-bone source required')
    require(io.sha(data['fbx']['path']) == data['fbx']['sha256'], 'Candidate FBX changed')
    baseline = read(BASELINES[role])
    require(baseline['success'] and baseline['native_executed'], 'Existing actual per-role import proof required')
    old_mesh = unreal.load_asset(baseline['mesh'])
    require(old_mesh, 'Existing per-role native mesh unavailable')
    skeleton = old_mesh.get_editor_property('skeleton')
    source_reference = native_rig.unit_reference(old_mesh)
    require(source_reference['native_bone_count'] == 53, 'Existing per-role skeleton has changed')
    source_names = sorted(data['rest_bone_names'])
    native_pose = unreal.AnimPoseExtensions.get_reference_pose(skeleton)
    require(sorted(str(n) for n in unreal.AnimPoseExtensions.get_bone_names(native_pose)) == source_names,
        'Source bone set differs from the exact existing role skeleton')
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    signature = hashlib.sha256((io.sha(path) + json.dumps(data['material_recipes'], sort_keys=True)).encode()).hexdigest()[:16]
    parent = '/Game/Release/V02/ReferenceWardrobe/' + role + '_' + signature
    disk = PROJECT / 'Content' / parent.removeprefix('/Game/')
    require(not io.files(disk), 'Preserving a previous/partial v02 namespace; use a new source candidate')
    history = ROOT / 'output/reference_wardrobe_v02' / role / 'native' / run
    history.mkdir(parents=True, exist_ok=False)
    before, saves, reports = io.native(PROJECT, disk), unit.saved_games(), existing_reports()
    report = {'success': False, 'native_executed': True, 'character': role, 'run': run,
        'scope': 'New isolated v02 wardrobe native import/data proof. No current NPC/motion/floor/story/save bindings changed.',
        'source_manifest': str(path), 'source_manifest_sha256': io.sha(path),
        'source_builder': data['builder_source_sha256'], 'native_importer_sha256': io.sha(SOURCE),
        'baseline_import_report': str(BASELINES[role]), 'baseline_import_report_sha256': io.sha(BASELINES[role]),
        'existing53_bone_skeleton_reused': skeleton.get_path_name(),
        'production_npcs_replaced': False, 'story_npcs_replaced': False, 'floor_bindings_changed': False,
        'motion_bindings_changed': False, 'save_schema_changed': False, 'asset_adoption_performed': False,
        'visual_approved': False, 'gait_visually_approved': False, 'exact_reference_likeness_claimed': False,
        'remaining_reference_gaps': data['remaining_reference_gaps'], 'candidate': None}
    try:
        materials = {name: character.material(name, recipe, parent, signature)
                     for name, recipe in data['material_recipes'].items()}
        # Clone the reviewed helper's globals for this invocation. Its Python
        # module, old source files, and normal import function are never changed.
        shim = types.SimpleNamespace(**character.__dict__)
        shim.import_fbx = lambda source, folder, sig: import_on_existing_skeleton(source, folder, sig, skeleton, role)
        isolated_case = types.FunctionType(unit.import_case.__code__, dict(unit.__dict__, mother=shim),
                                           name='isolated_reference_wardrobe_case')
        case = {'id': 'ReferenceWardrobeV02', 'fbx': data['fbx']['path'], 'fbx_sha256': data['fbx']['sha256'],
            'physical_morph_coordinate_preservation': data['physical_morph_coordinate_preservation'],
            'physical_pose_preservation': data['physical_pose_preservation'],
            'source_bone_names': source_names, 'source_bone_count': 53, 'unit_representation_changed': False}
        candidate = isolated_case(case, parent, data['effective_morph_measurement']['effective_facial_morphs'], materials, None)
        mesh = unreal.load_asset(candidate['mesh'])
        listening = unreal.load_asset(candidate['animation'])
        require(mesh.get_editor_property('skeleton') == skeleton and listening.get_editor_property('skeleton') == skeleton,
            'Exact existing per-role skeleton was not reused')
        require(candidate['native_bone_count'] == 53 and candidate['native_extra_bones'] == [], 'Native import added or lost bones')
        require(candidate['native_morph_count'] == 51 and candidate['unit_gate_passed'], 'Native facial/unit gate failed')
        require(candidate['native_unit_scale']['all_reference_bone_local_scales_are_one'], 'Reference local scale changed')
        candidate.update(character=role, source_manifest=str(path), source_manifest_sha256=io.sha(path),
            exact_existing_skeleton=skeleton.get_path_name(), art_revision='reference_wardrobe_v02',
            native_imported=True, existing_role_mesh_unchanged=True, native_executed=True,
            story_npcs_replaced=False, visual_approved=False, gait_visually_approved=False,
            remaining_reference_gaps=data['remaining_reference_gaps'])
        # The existing matching Mother walk is read/evaluated against the new
        # mesh, never duplicated, retargeted, edited, or assigned to a story actor.
        if role == 'Mother':
            walk_report = PROJECT / 'release_mother_rev11_compatible_bake.json'
            walk_data = read(walk_report)
            require(walk_data['success'] and walk_data['native_executed'], 'Actual existing Mother compatible gait required')
            walk = unreal.load_asset(walk_data['baked']['walk'])
            require(walk and walk.get_editor_property('skeleton') == skeleton, 'Existing Mother walk skeleton differs')
            candidate['walk'] = walk.get_path_name()
            candidate['walk_report'] = str(walk_report)
            candidate['walk_report_sha256'] = io.sha(walk_report)
            candidate['existing_walk_data_evaluation'] = retarget.sample(walk, mesh, 'walk', True)
            candidate['walk_motion_or_floor_bindings_modified'] = False
        else:
            candidate['walk'] = None
            candidate['walk_scope'] = 'Stationary role retains its own existing Listening; no borrowed gait invented.'
        for asset in materials.values():
            require(asset.get_path_name().startswith(parent + '/'), 'Only new candidate materials may be saved')
            LIB.save_loaded_asset(asset)
        for item in LIB.list_assets(parent + '/Textures', recursive=True):
            asset = unreal.load_asset(item)
            require(asset.get_path_name().startswith(parent + '/'), 'Only new candidate textures may be saved')
            LIB.save_loaded_asset(asset)
        report['candidate'] = candidate
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        guards = {'all_previous_native_assets_config_and_maps_unchanged': before == io.native(PROJECT, disk),
            'known_saved_games_unchanged': saves == unit.saved_games(),
            'previous_release_reports_unchanged': reports == existing_reports(),
            'source_manifest_unchanged': report['source_manifest_sha256'] == io.sha(path)}
        report['guards'] = guards
        report['success'] = bool(report['success'] and all(guards.values()))
        report['owned_asset_sha256'] = {str(p): io.sha(p) for p in io.files(disk)}
        if report['candidate']:
            report['candidate']['owned_asset_sha256'] = report['owned_asset_sha256']
        write(history / 'manifest.json', report)
        if report['success']:
            write(ROOT / 'output/reference_wardrobe_v02' / role / 'native_latest.json',
                {'run': run, 'manifest': str(history / 'manifest.json')})
        unreal.log('REFERENCE_WARDROBE_V02_NATIVE_REPORT ' + str(history / 'manifest.json'))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        unreal.log_error(traceback.format_exc())
    finally:
        unreal.SystemLibrary.quit_editor()
