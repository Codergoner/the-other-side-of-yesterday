"""Queued isolated Healer/Sela/Neri human art gates using the proved MPFB pipeline.

One role per private Blender process, never a Mother rebuild or a game-NPC swap:
blender --background --factory-startup --python this_file -- --character Healer
Use the same private BLENDER_USER_RESOURCES documented by the Mother builder.
All ages below are visual generator controls, not new canonical story ages.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib
import json
import math
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_release_characters as base
import build_release_unit_probe as units
sys.path.insert(0, str(ROOT / 'tools'))
import windows_file_guards as file_guards

SUITS = base.SOURCES / 'extracted/suits02_cc0'
ROLES = {
    'Healer': {
        'brief_identity': 'Healer; attentive, occupied with practical care. No private identity or family relationship is exposed.',
        'visual_age': 'Mature adult; no exact story age assigned',
        'macros': {'gender': 1.0, 'age': 0.64, 'muscle': 0.42, 'weight': 0.44, 'height': 0.55,
                   'race': {'caucasian': 0.60, 'asian': 0.20, 'african': 0.20}},
        'face_targets': {'chin-width-incr': 0.22, 'nose-curve-convex': 0.22, 'nose-width1-incr': 0.12},
        'skin': 'middleage_caucasian_male', 'skin_gain': (0.88, 0.84, 0.78),
        'hair': 'short02', 'hair_gain': (0.42, 0.34, 0.28), 'eyes': 'grey_eye.png',
        'garments': [('suits', 'donitz_monk_robe')],
        'colors': {'donitz_monk_robe': (0.34, 0.29, 0.20)},
        'silhouette': 'Open face, short dark/gray hair, unhooded plain work robe and closed leather shoes. No religious symbol or dramatic cowl.',
        'height_review_range_m': (1.55, 1.95),
    },
    'Sela': {
        'brief_identity': 'Sela; direct, observant storekeeper, practical within limited supplies.',
        'visual_age': 'Adult; no exact story age assigned',
        'macros': {'gender': 0.0, 'age': 0.38, 'muscle': 0.47, 'weight': 0.47, 'height': 0.54,
                   'race': {'caucasian': 0.30, 'asian': 0.40, 'african': 0.30}},
        'face_targets': {'head-scale-horiz-incr': 0.10, 'chin-height-decr': 0.12, 'nose-width1-incr': 0.16},
        'skin': 'middleage_asian_female', 'skin_gain': (0.92, 0.88, 0.82),
        'hair': 'ponytail01', 'hair_gain': (0.64, 0.48, 0.33), 'eyes': 'brown_eye.png',
        'garments': [('suits', 'rehmanpolanski_viking_pants'), ('suits', 'rehmanpolanski_viking_tunic')],
        'colors': {'rehmanpolanski_viking_pants': (0.12, 0.07, 0.10), 'rehmanpolanski_viking_tunic': (0.24, 0.20, 0.13)},
        'silhouette': 'Tied-back brown hair, plain long-sleeve belted linen tunic and fitted plum work trousers; no chainmail texture.',
        'height_review_range_m': (1.45, 1.85),
    },
    'Neri': {
        'brief_identity': 'Neri; young local resident, curious, with one visibly wrapped ankle. No exact age or new backstory assigned.',
        'visual_age': 'Young resident; generator settings are not a canonical age',
        'macros': {'gender': 1.0, 'age': 0.24, 'muscle': 0.37, 'weight': 0.43, 'height': 0.30,
                   'race': {'caucasian': 0.40, 'asian': 0.25, 'african': 0.35}},
        'face_targets': {'chin-width-decr': 0.18, 'nose-volume-decr': 0.20, 'l-eye-height1-incr': 0.08, 'r-eye-height1-incr': 0.08},
        'skin': 'young_african_male', 'skin_gain': (1.00, 0.94, 0.86),
        'hair': 'short04', 'hair_gain': (0.36, 0.27, 0.18), 'eyes': 'brownlight_eye.png',
        'garments': [('suits', 'rehmanpolanski_viking_pants'), ('suits', 'rehmanpolanski_viking_tunic')],
        'colors': {'rehmanpolanski_viking_pants': (0.11, 0.075, 0.045), 'rehmanpolanski_viking_tunic': (0.075, 0.17, 0.19)},
        'silhouette': 'Short tousled hair, teal plain tunic, brown trousers, closed shoes, one pale ankle wrap. No armor or running animation implied.',
        'height_review_range_m': (1.20, 1.70),
    },
}


def asset(pack, relative, kind='Clothes'):
    roots = {'system': base.SYSTEM, 'dress': base.DRESSES, 'suits': SUITS}
    path = roots[pack] / relative
    assert path.is_file(), path
    header = '\n'.join(path.read_text(errors='replace').splitlines()[:25])
    assert 'CC0' in header and 'AGPL' not in header, ('Unresolved selected-asset license', path)
    return {'path': str(path), 'type': kind, 'sha256': base.sha(path), 'license_header': header, 'pack': pack}


def protected_mother():
    latest = ROOT / 'output/release_characters/latest.json'
    data = json.loads(latest.read_text())
    manifest = Path(data['manifest'])
    mother = json.loads(manifest.read_text())
    paths = [latest, manifest, Path(mother['fbx']['path']), Path(mother['blend'])]
    paths += file_guards.matches(ROOT / 'game_unreal/Content/Release/CharacterReview', '*.uasset')
    paths += file_guards.matches(ROOT / 'game_unreal/Content/Release/CharacterReview', '*.umap')
    return {file_guards.canonical(p): file_guards.sha(p) for p in paths}


def protected_release():
    project = ROOT / 'game_unreal'
    result = file_guards.native(project)
    paths = file_guards.files(ROOT / 'output/release_characters')
    paths += [Path(file_guards.canonical(p)) for p in Path(file_guards.io_path(project)).glob('release*.json')]
    paths += [ROOT / 'build_release_characters.py', ROOT / 'build_release_npc_variations.py',
              ROOT / 'build_release_unit_probe.py', Path(file_guards.__file__)]
    result.update({file_guards.canonical(p): file_guards.sha(p) for p in paths})
    return result


def measured_body_height(body):
    group = body.vertex_groups.get('body')
    if group:
        points = [v.co.z for v in body.data.vertices if any(g.group == group.index and g.weight > 0.5 for g in v.groups)]
    else:
        points = [v.co.z for v in body.data.vertices]
    return max(points) - min(points)


def fabric_material(name, color, roughness=0.91):
    material = base.plain_material(name, color, roughness)
    material.use_backface_culling = False
    base.MATERIAL_RECIPES[name]['two_sided'] = True
    return material


def prepare_sela_skirt(dress, tunic, rig):
    """Subset only the dress hidden by this fitted longer tunic, with overlap."""
    import bmesh
    center = [v.co.z for v in tunic.data.vertices if abs(v.co.x) < 0.14]
    assert center, 'No central fitted tunic surface'
    hem = min(center)
    ankle = max(rig.data.bones['foot_l'].head_local.z, rig.data.bones['foot_r'].head_local.z)
    pelvis = rig.data.bones['pelvis'].head_local.z
    assert ankle + 0.08 < hem < pelvis + 0.08, ('Unexpected long-tunic hem relative to source bones', hem, ankle, pelvis)
    cutoff = hem + 0.04
    mesh = bmesh.new()
    mesh.from_mesh(dress.data)
    before = len(mesh.faces)
    remove = [face for face in mesh.faces if face.calc_center_median().z > cutoff]
    retained = [face for face in mesh.faces if face.calc_center_median().z <= cutoff]
    retained_z = [vertex.co.z for face in retained for vertex in face.verts]
    assert remove and len(retained) >= 500 and len(retained) >= before * 0.10, ('Insufficient retained skirt topology', len(retained), before)
    assert min(retained_z) < hem - 0.08 and max(retained_z) > hem + 0.015, ('Retained skirt lacks visible span/overlap', min(retained_z), max(retained_z), hem)
    bmesh.ops.delete(mesh, geom=remove, context='FACES')
    loose = [v for v in mesh.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(mesh, geom=loose, context='VERTS')
    mesh.to_mesh(dress.data)
    mesh.free()
    dress.data.update()
    return {'method': 'Original fitted CC0 tunic plus dress skirt; remove covered dress only with40mm overlap.',
            'tunic_hem_z_m': hem, 'dress_cutoff_z_m': cutoff, 'ankle_z_m': ankle, 'pelvis_z_m': pelvis,
            'retained_skirt_z_m': [min(retained_z), max(retained_z)], 'retained_skirt_faces': len(retained),
            'dress_faces_before': before, 'dress_faces_removed': len(remove), 'original_broken_garments_exported': False}


def ankle_wrap(shoe, rig, role):
    """A thin band taken from the already fitted sock surface, not new footwear.

    Retains original weights/UVs. The original shoe stays intact beneath it.
    Its edge/fit must pass the actual full-body and moving-foot review.
    """
    import bpy
    import bmesh
    copy = shoe.copy()
    copy.data = shoe.data.copy()
    copy.name = role + '_AnkleWrap_ArtCandidate'
    bpy.context.scene.collection.objects.link(copy)
    foot = rig.data.bones['foot_r'].head_local
    low, high = foot.z + 0.025, foot.z + 0.115
    mesh = bmesh.new()
    mesh.from_mesh(copy.data)
    discard = [face for face in mesh.faces if not (low < face.calc_center_median().z < high and face.calc_center_median().x < 0)]
    bmesh.ops.delete(mesh, geom=discard, context='FACES')
    assert 4 <= len(mesh.faces) <= 800, 'No safe fitted ankle surface for the wrap'
    mesh.normal_update()
    for vertex in mesh.verts:
        vertex.co += vertex.normal * 0.003
    mesh.to_mesh(copy.data)
    mesh.free()
    copy.data.materials.clear()
    copy.data.materials.append(fabric_material('M_Release_' + role + '_AnkleLinen', (0.48, 0.43, 0.34), 0.95))
    for face in copy.data.polygons:
        face.material_index = 0
    return copy


def build(role):
    import bpy
    recipe = ROLES[role]
    base.verify_sources()
    mother_before = protected_mother()
    native_before = protected_release()
    normalization_reference = ROOT / 'game_unreal/release_character_unit_probe_report.json'
    proved_units = json.loads(normalization_reference.read_text())
    preferred_units = proved_units.get('preferred_candidate')
    assert (proved_units['success'] and proved_units['native_executed'] and preferred_units
            and preferred_units['id'] == 'CentimeterData_ArmatureName'
            and preferred_units['native_unit_scale']['unit_root_scale_passed']
            and preferred_units['human_height_passed']), 'First prove the centimeter-data/Armature native pipeline'
    vendor, svc = base.load_private_addon()
    base.MATERIAL_RECIPES.clear()
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    parent = ROOT / 'output/release_npc_variations' / role
    output = parent / 'builds' / run
    output.mkdir(parents=True)
    macros = svc.TargetService.get_default_macro_info_dict()
    macros.update(recipe['macros'])
    body = svc.HumanService.create_human(scale=0.1, macro_detail_dict=macros)
    body.name = role + '_SourceBody'
    targets = []
    for name, value in recipe['face_targets'].items():
        found = list((base.VENDOR / 'data/targets').rglob(name + '.target.gz'))
        assert len(found) == 1, (name, found)
        svc.TargetService.load_target(body, str(found[0]), weight=value)
        targets.append({'name': name, 'weight': value, 'path': str(found[0]), 'sha256': base.sha(found[0])})
    skin = base.SYSTEM / 'skins' / recipe['skin'] / (recipe['skin'] + '.mhmat')
    assert skin.is_file()
    skin_header = skin.read_text(errors='replace')
    assert 'CC0' in skin_header
    diffuse_line = next(line for line in skin_header.splitlines() if line.startswith('diffuseTexture '))
    skin_image = skin.parent / diffuse_line.split(maxsplit=1)[1].strip()
    body.data.materials.clear()
    body.data.materials.append(base.textured_material('M_Release_' + role + '_Skin', skin_image, recipe['skin_gain'], 0.64))
    rig = svc.HumanService.add_builtin_rig(body, 'game_engine')
    rest = {bone.name: [list(row) for row in bone.matrix_local] for bone in rig.data.bones}
    selected = [asset('system', 'eyes/low-poly/low-poly.mhclo', 'Eyes'),
        asset('system', 'eyebrows/eyebrow002/eyebrow002.mhclo', 'Eyebrows'),
        asset('system', 'eyelashes/eyelashes01/eyelashes01.mhclo', 'Eyelashes'),
        asset('system', 'hair/' + recipe['hair'] + '/' + recipe['hair'] + '.mhclo', 'Hair')]
    selected += [asset(pack, 'clothes/' + name + '/' + name + '.mhclo') for pack, name in recipe['garments']]
    selected.append(asset('system', 'clothes/shoes01/shoes01.mhclo'))
    for item in selected:
        obj = svc.HumanService.add_mhclo_asset(item['path'], body, asset_type=item['type'], subdiv_levels=0, material_type='GAMEENGINE')
        assert obj and obj.type == 'MESH'
        obj.data.materials.clear()
        folder_name = Path(item['path']).parent.name
        if item['type'] == 'Hair':
            obj.data.materials.append(base.textured_material('M_Release_' + role + '_Hair',
                base.SYSTEM / 'hair' / recipe['hair'] / (recipe['hair'] + '_diffuse.png'), recipe['hair_gain'], 0.84, True))
        elif item['type'] == 'Eyes':
            obj.data.materials.append(base.textured_material('M_Release_' + role + '_Eyes', base.SYSTEM / 'eyes/materials' / recipe['eyes'], (1, 1, 1), 0.30))
        elif item['type'] in ['Eyebrows', 'Eyelashes']:
            part = 'eyebrows/eyebrow002/eyebrow002.png' if item['type'] == 'Eyebrows' else 'eyelashes/eyelashes01/eyelashes01.png'
            obj.data.materials.append(base.textured_material('M_Release_' + role + '_' + item['type'], base.SYSTEM / part, (0.65, 0.53, 0.40), 0.88, True))
        elif folder_name == 'shoes01':
            obj.data.materials.append(base.plain_material('M_Release_' + role + '_LeatherShoe', (0.055, 0.032, 0.018), 0.80))
            obj.data.materials.append(fabric_material('M_Release_' + role + '_Stocking', (0.06, 0.05, 0.035), 0.95))
            threshold = max(rig.data.bones['foot_l'].head_local.z, rig.data.bones['foot_r'].head_local.z) + 0.045
            for face in obj.data.polygons:
                face.material_index = 1 if face.center.z > threshold else 0
        else:
            obj.data.materials.append(fabric_material('M_Release_' + role + '_' + folder_name, recipe['colors'][folder_name], 0.91))
    export_rig = svc.ExportService.create_character_copy(body, name_suffix='_Export')
    export_body = svc.ObjectService.find_object_of_type_amongst_nearest_relatives(export_rig)
    svc.TargetService.bake_targets(export_body)
    # Measure the full shaped body before covered-skin masks remove hidden feet/torso.
    height = measured_body_height(export_body)
    svc.FaceService.load_targets(export_body, load_microsoft_visemes=False, load_meta_visemes=False, load_arkit_faceunits=True)
    svc.FaceService.interpolate_targets(export_body)
    export_rig.name = 'SK_Release_' + role
    export_body.name = 'SK_Release_' + role + '_Body'
    related = base.descendants(export_rig)
    fit = None
    if role == 'Neri':
        shoe = next(obj for obj in related if obj.type == 'MESH' and 'shoes01' in obj.name)
        ankle_wrap(shoe, export_rig, role)
    svc.ExportService.bake_modifiers_remove_helpers(export_body, bake_masks=True, bake_subdiv=False, remove_helpers=True)
    coverage = None
    if role in ['Sela', 'Neri']:
        # Tunic/pants have no delete_verts. The proved export-only mask protects
        # all facial morph vertices, neckline and hands and preserves key data.
        reference = next(obj for obj in base.descendants(export_rig) if obj.type == 'MESH' and 'viking_pants' in obj.name)
        coverage = base.occlude_sweater_covered_skin(export_body, reference, export_rig)
    for obj in base.descendants(rig):
        obj.hide_render = True
        obj.hide_set(True)
    exported = base.descendants(export_rig)
    required = importlib.import_module(base.PACKAGE + '.services.faceservice').ARKIT_FACEUNITS
    keys = base.canonical_morphs(exported, required)
    metrics = base.effective_morph_metrics(exported, keys)
    assert recipe['height_review_range_m'][0] <= height <= recipe['height_review_range_m'][1], ('Review generated role height', role, height)
    for obj in exported:
        if obj.type == 'MESH':
            for modifier in list(obj.modifiers):
                if modifier.type == 'SUBSURF':
                    obj.modifiers.remove(modifier)
            for face in obj.data.polygons:
                face.use_smooth = True
    base.listening_animation(export_rig, exported)
    export_rig.animation_data.action.name = 'A_Release_' + role + '_Listen'
    assert rest == {bone.name: [list(row) for row in bone.matrix_local] for bone in export_rig.data.bones}, 'Pre-conversion source rig basis changed'
    # Render meter-representation previews before changing coordinate units.
    # The full physical conversion below proves these represent the same art.
    head = export_rig.pose.bones['head']
    previews = base.studio_preview(exported, output, float((export_rig.matrix_world @ head.head).z) + 0.08)
    renamed = []
    for old in previews:
        original = Path(old)
        target = original.with_name(original.name.replace('Mother_', role + '_', 1))
        original.rename(target)
        renamed.append(str(target))
    scene = bpy.context.scene
    scene.frame_set(1)
    source_unit = float(scene.unit_settings.scale_length)
    assert abs(source_unit - 1.0) < 1e-8, 'The source morph metric is measured in meter-representation coordinates'
    source_basis_sha = units.basis_hash(export_rig)
    source_rest_world = units.rest_world(export_rig, source_unit)
    source_shape_coords = units.shape_coordinates(exported, source_unit)
    source_poses = units.snapshot(export_rig, exported)
    face_curve_sha_before = units.non_length_animation_hash(exported)
    conversion = units.normalize_centimeter_data(export_rig, exported)
    converted_poses = units.snapshot(export_rig, exported)
    pose_proof = units.snapshot_difference(source_poses, converted_poses)
    morph_proof = units.shape_difference(source_shape_coords, units.shape_coordinates(exported, scene.unit_settings.scale_length))
    scene.frame_set(1)
    bpy.context.view_layer.update()
    converted_rest_world = units.rest_world(export_rig, scene.unit_settings.scale_length)
    rest_proof = units.rest_difference(source_rest_world, converted_rest_world)
    face_curve_sha_after = units.non_length_animation_hash(exported)
    assert face_curve_sha_before == face_curve_sha_after, 'Non-length and facial animation keys changed'
    converted_rest = {bone.name: [list(row) for row in bone.matrix_local] for bone in export_rig.data.bones}
    converted_basis_sha = hashlib.sha256(json.dumps(converted_rest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert bpy.data.objects.get('Armature') in [None, export_rig], 'Unexpected pre-existing Armature-named object'
    export_rig.name = 'Armature'
    assert export_rig.name == 'Armature'
    # Studio camera/lights were authored in meter coordinates. Remove only those
    # temporary review objects instead of saving an incorrectly scaled camera.
    scene.camera = None
    for obj in list(scene.objects):
        if obj.type in ['CAMERA', 'LIGHT']:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in exported:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = export_rig
    fbx = output / ('SK_Release_' + role + '.fbx')
    bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'ARMATURE', 'MESH'}, add_leaf_bones=False,
        armature_nodetype='NULL', global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Y', axis_up='Z',
        use_mesh_modifiers=False, mesh_smooth_type='FACE', bake_anim=True, bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=False, bake_anim_simplify_factor=0.0, path_mode='COPY', embed_textures=False)
    blend = output / (role + '_ArtGate.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    assert protected_mother() == mother_before, 'Proved Mother artifacts changed'
    assert protected_release() == native_before, 'Old native assets/Mother outputs/reports changed'
    meshes = [{'name': obj.name, 'vertices': len(obj.data.vertices), 'triangles': sum(len(p.vertices) - 2 for p in obj.data.polygons),
               'materials': [material.name for material in obj.data.materials if material]} for obj in exported if obj.type == 'MESH']
    result = {'success': True, 'character': role, 'run': run, 'scope': 'Isolated Blender character candidate; no native import, story-NPC replacement or finished-performance claim.',
        'identity': recipe['brief_identity'], 'visual_age_description': recipe['visual_age'], 'generator_parameters_not_canonical_age_or_biography': macros,
        'genuine_facial_target_changes': targets, 'costume_silhouette': recipe['silhouette'], 'measured_body_height_m': height,
        'height_is_art_authoring_measurement_not_story_canon': True, 'selected_assets': selected,
        'source_facial_shape_key_count': len(keys), 'effective_morph_measurement': metrics,
        'effective_morph_measurement_representation': 'Measured in original meter-data representation; every physical morph coordinate is verified unchanged after conversion.',
        'rest_bone_names': sorted(rest), 'source_core_bone_count': len(rest), 'expected_native_core_bone_count': len(rest),
        'pre_conversion_source_rest_basis_preserved': True, 'pre_conversion_local_rest_basis_sha256': source_basis_sha,
        'normalized_rest_bone_matrices_local': converted_rest, 'normalized_rest_bone_basis_sha256': converted_basis_sha,
        'local_rest_matrix_equality_not_claimed': True,
        'coordinate_representation': 'CentimeterData_ArmatureName', 'unit_representation_changed': True,
        'scene_meters_per_unit': scene.unit_settings.scale_length, 'export_armature_object_name': export_rig.name,
        'unit_conversion': conversion, 'physical_rest_position_preservation': rest_proof,
        'physical_world_rest_bones_m': converted_rest_world, 'physical_pose_preservation': pose_proof,
        'physical_morph_coordinate_preservation': morph_proof,
        'physical_world_bones_by_frame': {str(frame): row['bones'] for frame,row in converted_poses.items()},
        'non_length_animation_and_face_curve_keys_unchanged': face_curve_sha_before == face_curve_sha_after,
        'non_length_animation_curve_sha256': face_curve_sha_after,
        'normalization_reference_report': str(normalization_reference), 'normalization_reference_sha256': base.sha(normalization_reference),
        'source_builder_sha256': base.sha(__file__), 'mother_helper_source_sha256': base.sha(base.__file__),
        'unit_helper_source_sha256': base.sha(units.__file__),
        'long_path_guard_source_sha256': file_guards.sha(file_guards.__file__),
        'material_recipes': base.MATERIAL_RECIPES, 'garment_fit': fit, 'covered_skin_occlusion': coverage,
        'meshes': meshes, 'total_triangles': sum(item['triangles'] for item in meshes),
        'fbx': {'path': str(fbx), 'sha256': base.sha(fbx)}, 'blend': str(blend), 'previews': renamed,
        'preview_representation': 'Rendered before coordinate conversion; physical rest/deformed/morph preservation proves equivalent art. Normalized blend/FBX uses centimeter data and Armature null name.',
        'native_imported': False, 'native_animation_verified': False, 'mother_artifacts_unchanged': True, 'native_project_unchanged': True,
        'proof_plan': ['Inspect actual full-body/open/blink Blender images for this distinct role, including hands/cloth/footwear.',
            'Measure nonzero facial targets across every exported mesh; do not require zero-delta keys natively.',
            'Import into a new role-specific namespace and isolated review map; compile skeletal/morph materials.',
            'Capture four actual native cardinal views, then selected-front open/blink and bone/morph readbacks at0/1/2/3seconds.',
            'Prove walking/turning and role-specific interaction deformation before any existing story NPC mesh/animation swap.',
            'Neri ankle wrap must stay fitted and readable through deliberate walking; no running claim.']}
    manifest = output / 'manifest.json'
    manifest.write_text(json.dumps(result, indent=2) + '\n')
    (parent / 'latest.json').write_text(json.dumps({'run': run, 'manifest': str(manifest)}, indent=2) + '\n')
    print('RELEASE_NPC_VARIANT_ART_GATE ' + str(manifest), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--character', choices=sorted(ROLES), required=True)
    arguments = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    build(arguments.character)
