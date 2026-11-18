"""Build the first clothed, rigged Mother art gate from pinned official CC0 assets.

Run only in a queued private Blender background process, with --factory-startup
and BLENDER_USER_RESOURCES=<Release>/output/character_sources/private_runtime/blender_user.
No addon installation, user-preference save, Unreal access or native asset write.
Example: blender --background --factory-startup --python this_file -- --build-mother
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib
import importlib.util
import json
import math
import os
import shutil
import sys
import types
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / 'output/character_sources'
VENDOR = SOURCES / 'extracted/mpfb_2_0_18'
SYSTEM = SOURCES / 'extracted/system_assets_cc0'
DRESSES = SOURCES / 'extracted/dress01_cc0'
SHIRTS = SOURCES / 'extracted/shirts01_cc0'
PRIVATE = SOURCES / 'private_runtime'
PACKAGE = 'bl_ext.tosoy_private.mpfb'
OFFICIAL_SHA = 'c075b3e9b94b8e5556a5f03f4653602d02ea306de08126e8f55ed6dee28a2dad'
MATERIAL_RECIPES = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_sources():
    manifest = json.loads((SOURCES / 'source_manifest.json').read_text())
    assert manifest['success'] and manifest['version'] == 'MPFB2.0.18'
    for item in manifest['sources']:
        assert sha(item['path']) == item['sha256'], item['id']
    assert sha(SOURCES / 'add-on-mpfb-v2.0.18.zip') == OFFICIAL_SHA
    assert 'CC0 1.0 Universal' in (SOURCES / 'LICENSE.ASSETS.md').read_text()
    # Execute only byte-identical source files from the pinned official ZIP.
    with zipfile.ZipFile(SOURCES / 'add-on-mpfb-v2.0.18.zip') as archive:
        code = {n for n in archive.namelist() if n.endswith('.py')}
        actual = {str(p.relative_to(VENDOR)).replace('\\', '/') for p in VENDOR.rglob('*.py')}
        assert code == actual, 'Unexpected or missing executable vendor files'
        for name in code:
            assert (VENDOR / name).read_bytes() == archive.read(name), name
    return manifest


def protected_native_hashes():
    native = ROOT / 'game_unreal'
    files = list((native / 'Config').glob('*.ini'))
    files += list((native / 'Content/Quest/Maps').glob('*.umap'))
    files += list((native / 'Content/Opening/Blueprints').glob('*.uasset'))
    files += list(native.glob('*.uproject'))
    return {str(p): sha(p) for p in files}


def load_private_addon():
    import bpy
    sys.dont_write_bytecode = True
    expected = (PRIVATE / 'blender_user').resolve()
    configured = Path(os.environ.get('BLENDER_USER_RESOURCES', '')).resolve()
    assert configured == expected, 'Set the documented private BLENDER_USER_RESOURCES before launch'
    expected.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.use_preferences_save = False
    private_home = PRIVATE / 'mpfb_home'
    private_home.mkdir(parents=True, exist_ok=True)
    # Only the face targets need asset discovery. Other assets use explicit paths.
    shutil.copytree(SOURCES / 'extracted/faceunits01_cc0/targets', private_home / 'data/targets', dirs_exist_ok=True)
    for package in ['bl_ext', 'bl_ext.tosoy_private']:
        if package not in sys.modules:
            module = types.ModuleType(package)
            module.__path__ = []
            sys.modules[package] = module
    spec = importlib.util.spec_from_file_location(PACKAGE, VENDOR / '__init__.py', submodule_search_locations=[str(VENDOR)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    preferences_class = importlib.import_module(PACKAGE + '._preferences').MpfbPreferences
    bpy.utils.register_class(preferences_class)
    entry = bpy.context.preferences.addons.new()
    entry.module = PACKAGE
    entry.preferences.mpfb_user_data = str(private_home)
    entry.preferences.mh_auto_user_data = False
    module.register()
    services = importlib.import_module(PACKAGE + '.services')
    assert Path(services.LocationService.get_user_home()).resolve() == private_home.resolve()
    assert services.FaceService.is_faceunits01_installed(force_recheck=True)
    return module, services


def approved_asset(relative, asset_type):
    candidates = [root / relative for root in [SYSTEM, DRESSES, SHIRTS] if (root / relative).is_file()]
    assert len(candidates) == 1, (relative, candidates)
    path = candidates[0]
    assert path.is_file(), path
    header = '\n'.join(path.read_text(errors='replace').splitlines()[:24])
    assert 'CC0' in header and 'AGPL' not in header, 'Unresolved per-asset license: ' + str(path)
    return {'path': str(path), 'type': asset_type, 'sha256': sha(path), 'license_header': header}


def plain_material(name, color, roughness=0.85):
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1.0)
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Specular IOR Level'].default_value = 0.24
    mat.diffuse_color = (*color, 1.0)
    MATERIAL_RECIPES[name] = {'base_color_linear': list(color), 'roughness': roughness, 'specular': 0.24, 'metallic': 0.0, 'two_sided': False, 'blend_mode': 'opaque'}
    return mat


def textured_material(name, image_file, tint=(1, 1, 1), roughness=0.65, alpha=False):
    """Use explicit image nodes so the game material does not depend on Blender groups."""
    import bpy
    path = Path(image_file)
    assert path.is_file(), path
    mat = plain_material(name, tint, roughness)
    tree = mat.node_tree
    shader = tree.nodes.get('Principled BSDF')
    tex = tree.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(path), check_existing=True)
    mix = tree.nodes.new('ShaderNodeMixRGB')
    mix.blend_type, mix.inputs[0].default_value = 'MULTIPLY', 1.0
    mix.inputs[2].default_value = (*tint, 1.0)
    tree.links.new(tex.outputs['Color'], mix.inputs[1])
    tree.links.new(mix.outputs['Color'], shader.inputs['Base Color'])
    if alpha:
        tree.links.new(tex.outputs['Alpha'], shader.inputs['Alpha'])
        mat.surface_render_method = 'DITHERED'
        mat.use_backface_culling = False
    MATERIAL_RECIPES[name].update(base_color_texture=str(path), texture_sha256=sha(path), linear_gain=list(tint),
        blend_mode='masked' if alpha else 'opaque', opacity_mask_clip_value=0.33, two_sided=alpha)
    return mat


def prepare_verified_clothing(dress, sweater):
    """Keep the fitted CC0 sweater; retain the skirt under its overlapping hem.

    Removes the now-covered dress bodice to prevent two fitted torso surfaces
    from crossing. Does not alter any body, face morph or rig data. Original
    apron, body-derived blouse and boots are intentionally absent.
    """
    import bmesh
    center_vertices = [v.co for v in sweater.data.vertices if abs(v.co.x) < 0.14]
    assert center_vertices, 'No sweater torso fitting vertices'
    hem_z = min(v.z for v in center_vertices)
    cutoff = hem_z + 0.035
    assert 0.60 < cutoff < 1.25, ('Unexpected sweater hem height', cutoff)
    mesh = bmesh.new()
    mesh.from_mesh(dress.data)
    before = len(mesh.faces)
    remove = [face for face in mesh.faces if face.calc_center_median().z > cutoff]
    assert 0 < len(remove) < before * 0.8, ('Unsafe dress bodice subset', len(remove), before)
    bmesh.ops.delete(mesh, geom=remove, context='FACES')
    loose = [vertex for vertex in mesh.verts if not vertex.link_faces]
    if loose:
        bmesh.ops.delete(mesh, geom=loose, context='VERTS')
    mesh.to_mesh(dress.data)
    mesh.free()
    dress.data.update()
    return {'method': 'Fitted CC0 MHCLO garments. Subset only the covered dress bodice.',
            'sweater_hem_z_m': hem_z, 'dress_cutoff_z_m': cutoff,
            'dress_faces_before': before, 'dress_faces_removed': len(remove),
            'original_broken_garments_exported': False,
            'visual_overlap_and_deformation_verified': False}


def occlude_sweater_covered_skin(body, sweater, rig):
    """Export-only face occlusion for the sweater, whose MHCLO has no delete_verts.

    Remove only torso/arm skin faces fully inside the closed sweater coverage.
    Do not delete/reorder vertices or modify shape-key coordinates. Protect every
    face/head morph vertex, the neckline and weighted hand/finger vertices.
    """
    import array
    import bmesh

    def shape_hashes():
        result = {}
        for key in body.data.shape_keys.key_blocks:
            values = array.array('f', [0.0]) * (len(key.data) * 3)
            key.data.foreach_get('co', values)
            result[key.name] = hashlib.sha256(values.tobytes()).hexdigest()
        return result

    vertex_count = len(body.data.vertices)
    before_keys = shape_hashes()
    basis = body.data.shape_keys.key_blocks[0]
    facial = set()
    for key in body.data.shape_keys.key_blocks:
        if key == basis:
            continue
        facial.update(i for i in range(vertex_count) if (key.data[i].co - basis.data[i].co).length_squared > 1e-14)
    hand_bones = set()
    for bone in rig.data.bones:
        parent = bone
        while parent:
            if parent.name in ['hand_l', 'hand_r']:
                hand_bones.add(bone.name)
                break
            parent = parent.parent
    names = {group.index: group.name for group in body.vertex_groups}
    hem_vertices = [v.co.z for v in sweater.data.vertices if abs(v.co.x) < 0.14]
    lower = min(hem_vertices) + 0.02
    upper = rig.data.bones['neck_01'].head_local.z - 0.03
    assert lower < upper
    protected = set(facial)
    for vertex in body.data.vertices:
        hand_weight = sum(g.weight for g in vertex.groups if names[g.group] in hand_bones)
        if vertex.co.z >= upper or hand_weight > 0.025:
            protected.add(vertex.index)
    eligible = {v.index for v in body.data.vertices if lower < v.co.z < upper and v.index not in protected}
    protected_faces = {tuple(sorted(face.vertices)) for face in body.data.polygons if any(i in protected for i in face.vertices)}
    selected_faces = [face.index for face in body.data.polygons if all(i in eligible for i in face.vertices)]
    assert 100 < len(selected_faces) < len(body.data.polygons) * 0.70, ('Unsafe coverage selection', len(selected_faces))
    group = body.vertex_groups.get('ExportCovered.FishermanSweater') or body.vertex_groups.new(name='ExportCovered.FishermanSweater')
    group.add(sorted(eligible), 1.0, 'REPLACE')
    mesh = bmesh.new()
    mesh.from_mesh(body.data)
    mesh.faces.ensure_lookup_table()
    removal = [mesh.faces[index] for index in selected_faces]
    bmesh.ops.delete(mesh, geom=removal, context='FACES_ONLY')
    mesh.to_mesh(body.data)
    mesh.free()
    body.data.update()
    after_keys = shape_hashes()
    remaining_faces = {tuple(sorted(face.vertices)) for face in body.data.polygons}
    assert len(body.data.vertices) == vertex_count, 'Coverage edit changed vertex count'
    assert before_keys == after_keys, 'Coverage edit changed/reordered morph coordinates'
    assert protected_faces.issubset(remaining_faces), 'A protected face/neck/hand polygon was removed'
    return {'method': 'Export-only covered-body group and FACES_ONLY occlusion; sweater source has no delete_verts section.',
            'removed_skin_faces': len(selected_faces), 'coverage_z_m': [lower, upper],
            'protected_facial_morph_vertices': len(facial), 'protected_head_neck_hand_faces': len(protected_faces),
            'vertex_count_before_after': [vertex_count, len(body.data.vertices)],
            'shape_key_coordinates_unchanged': before_keys == after_keys,
            'protected_faces_retained': True, 'shape_key_sha256': after_keys,
            'visual_poke_through_reviewed': False}


def descendants(root):
    return [root] + list(root.children_recursive)


def canonical_morphs(objects, required):
    found = set()
    for obj in objects:
        if obj.type != 'MESH' or not obj.data.shape_keys:
            continue
        for key in obj.data.shape_keys.key_blocks:
            if key.name.startswith('!ex-'):
                key.name = key.name[4:]
            if key.name in required:
                found.add(key.name)
    assert set(required).issubset(found), sorted(set(required) - found)
    return sorted(found)


def effective_morph_metrics(objects, source_names):
    """Measure actual vertex deltas across every exported mesh, not key names."""
    epsilon_m = 1e-10
    metrics = {name: {'changed_vertices': 0, 'max_delta_m': 0.0, 'meshes': []} for name in source_names}
    for obj in objects:
        if obj.type != 'MESH' or not obj.data.shape_keys:
            continue
        keys = obj.data.shape_keys.key_blocks
        basis = keys[0]
        for name in source_names:
            key = keys.get(name) or keys.get('!ex-' + name)
            if not key:
                continue
            changed, maximum_squared = 0, 0.0
            for index in range(len(basis.data)):
                squared = (key.data[index].co - basis.data[index].co).length_squared
                maximum_squared = max(maximum_squared, squared)
                if squared > epsilon_m * epsilon_m:
                    changed += 1
            row = metrics[name]
            row['changed_vertices'] += changed
            row['max_delta_m'] = max(row['max_delta_m'], math.sqrt(maximum_squared))
            row['meshes'].append({'mesh': obj.name, 'changed_vertices': changed, 'max_delta_m': math.sqrt(maximum_squared)})
    effective = sorted(name for name, row in metrics.items() if row['changed_vertices'] > 0)
    zero_delta = sorted(set(source_names) - set(effective))
    return {'source_shape_key_count': len(source_names), 'source_shape_key_names': sorted(source_names),
            'effective_facial_morph_count': len(effective), 'effective_facial_morphs': effective,
            'non_deforming_facial_shape_keys': zero_delta, 'delta_epsilon_m': epsilon_m,
            'measurement_scope': 'All actual meshes in the exported rig hierarchy; retained source keys are distinct from deforming native targets.',
            'metrics': metrics}


def audit_existing_morphs():
    """Fast queued read of the proved .blend; no regeneration or rendering needed."""
    import bpy
    latest_file = ROOT / 'output/release_characters/latest.json'
    latest = json.loads(latest_file.read_text())
    manifest_file = Path(latest['manifest'])
    data = json.loads(manifest_file.read_text())
    blend = Path(data['blend'])
    assert blend.resolve().is_relative_to((ROOT / 'output/release_characters/builds').resolve())
    assert sha(data['fbx']['path']) == data['fbx']['sha256']
    original_manifest_sha = sha(manifest_file)
    original_blend_sha = sha(blend)
    before = protected_native_hashes()
    bpy.context.preferences.use_preferences_save = False
    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False, use_scripts=False)
    rig = bpy.data.objects.get('SK_Release_Mother')
    assert rig and rig.type == 'ARMATURE'
    result = effective_morph_metrics(descendants(rig), data['facial_morphs'])
    result.update(success=True, scope='Actual existing Blender mesh-delta audit only; no geometry, animation, export or render modification.',
        source_manifest=str(manifest_file), source_manifest_sha256=original_manifest_sha,
        source_blend=str(blend), source_blend_sha256=original_blend_sha, source_fbx_sha256=data['fbx']['sha256'])
    assert sha(manifest_file) == original_manifest_sha and sha(blend) == original_blend_sha
    assert protected_native_hashes() == before
    out = manifest_file.parent / 'effective_morph_audit.json'
    out.write_text(json.dumps(result, indent=2) + '\n')
    latest.update(effective_morph_audit=str(out), effective_morph_audit_sha256=sha(out))
    latest_file.write_text(json.dumps(latest, indent=2) + '\n')
    print('RELEASE_MOTHER_EFFECTIVE_MORPH_AUDIT ' + str(out), flush=True)
    return result


def listening_animation(rig, meshes):
    import bpy
    from mathutils import Vector, Matrix, Quaternion
    rig.animation_data_create()
    rig.animation_data.action = bpy.data.actions.new('A_Release_Mother_Listen')
    for bone in rig.pose.bones:
        bone.rotation_mode = 'QUATERNION'
    # Use a real relaxed FK pose rather than displaying the reference T pose.
    for side, sign in [('l', 1), ('r', -1)]:
        bone = rig.pose.bones.get('upperarm_' + side)
        assert bone, 'GameEngine upper-arm bone missing'
        rest = bone.bone.matrix_local.copy()
        direction = rest.to_quaternion() @ Vector((0, 1, 0))
        rotation = direction.rotation_difference(Vector((0.13 * sign, -0.045, -0.99)).normalized())
        head = bone.bone.head_local
        bone.matrix = Matrix.Translation(head) @ rotation.to_matrix().to_4x4() @ Matrix.Translation(-head) @ rest
        bpy.context.view_layer.update()
    pose = {b.name: b.rotation_quaternion.copy() for b in rig.pose.bones}
    for frame in [1, 31, 61, 91, 121]:
        phase = (frame - 1) / 120 * math.tau
        for bone in rig.pose.bones:
            bone.rotation_mode = 'QUATERNION'
            base = pose[bone.name]
            amount = 0.006 * math.sin(phase) if bone.name in ['spine_02', 'spine_03', 'neck_01'] else 0.0
            bone.rotation_quaternion = base @ Quaternion((1, 0, 0), amount)
            bone.keyframe_insert('rotation_quaternion', frame=frame, group=bone.name)
    for obj in meshes:
        if obj.type != 'MESH' or not obj.data.shape_keys:
            continue
        for name in ['eyeBlinkLeft', 'eyeBlinkRight']:
            key = obj.data.shape_keys.key_blocks.get(name)
            if key:
                for frame, value in [(1, 0), (43, 0), (46, 1), (49, 0), (121, 0)]:
                    key.value = value
                    key.keyframe_insert('value', frame=frame)
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 120
    bpy.context.scene.render.fps = 30
    bpy.context.scene.frame_set(1)


def studio_preview(objects, build_dir, head_height):
    import bpy
    from mathutils import Vector
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.world.color = (0.10, 0.10, 0.10)
    scene.view_settings.view_transform = 'AgX'
    for name, location, energy, size in [('Key', (-2.2, -3.2, 3.4), 380, 3), ('Fill', (2.4, -1.4, 2.1), 170, 3), ('Rim', (0.5, 1.6, 2.8), 270, 2)]:
        light = bpy.data.lights.new(name, 'AREA')
        light.energy, light.shape, light.size = energy, 'DISK', size
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = location
        obj.rotation_euler = (Vector((0, 0, 1.1)) - obj.location).to_track_quat('-Z', 'Y').to_euler()
    data = bpy.data.cameras.new('MotherArtReviewCamera')
    camera = bpy.data.objects.new('MotherArtReviewCamera', data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    paths = []
    for label, location, target, lens, frame in [
        ('Mother_FullBody', (2.0, -4.2, 1.65), (0, 0, 0.95), 60, 1),
        ('Mother_FaceOpen', (0.10, -1.35, head_height), (0, 0, head_height - 0.04), 75, 1),
        ('Mother_FaceBlink', (0.10, -1.35, head_height), (0, 0, head_height - 0.04), 75, 46),
    ]:
        scene.frame_set(frame)
        camera.location = location
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat('-Z', 'Y').to_euler()
        data.lens = lens
        out = build_dir / (label + '.png')
        scene.render.filepath = str(out)
        bpy.ops.render.render(write_still=True)
        paths.append(str(out))
    scene.frame_set(1)
    return paths


def main():
    args = argparse.ArgumentParser()
    mode = args.add_mutually_exclusive_group(required=True)
    mode.add_argument('--build-mother', action='store_true')
    mode.add_argument('--audit-existing-morphs', action='store_true')
    options = args.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    if options.audit_existing_morphs:
        return audit_existing_morphs()
    assert options.build_mother, 'Explicit queued --build-mother required'
    sources = verify_sources()
    before = protected_native_hashes()
    import bpy
    vendor, svc = load_private_addon()
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    build_dir = ROOT / 'output/release_characters/builds' / run
    build_dir.mkdir(parents=True)
    macros = svc.TargetService.get_default_macro_info_dict()
    macros.update(gender=0.0, age=0.62, muscle=0.42, weight=0.52, height=0.48)
    body = svc.HumanService.create_human(scale=0.1, macro_detail_dict=macros)
    body.name = 'Mother_SourceBody'
    skin = SYSTEM / 'skins/middleage_caucasian_female/middleage_caucasian_female.mhmat'
    assert skin.exists()
    svc.HumanService.set_character_skin(str(skin), body, skin_type='GAMEENGINE')
    body.data.materials.clear()
    body.data.materials.append(textured_material('M_Release_Mother_Skin',
        skin.parent / 'middleage_lightskinned_female_diffuse.png', tint=(0.80, 0.75, 0.71), roughness=0.62))
    rig = svc.HumanService.add_builtin_rig(body, 'game_engine')
    rest_bones = {bone.name: [list(row) for row in bone.matrix_local] for bone in rig.data.bones}
    assets = [
        approved_asset('eyes/low-poly/low-poly.mhclo', 'Eyes'),
        approved_asset('eyebrows/eyebrow002/eyebrow002.mhclo', 'Eyebrows'),
        approved_asset('eyelashes/eyelashes01/eyelashes01.mhclo', 'Eyelashes'),
        approved_asset('hair/braid01/braid01.mhclo', 'Hair'),
        approved_asset('clothes/toigo_camisole_dress_with_full_skirt/toigo_camisole_dress_with_full_skirt.mhclo', 'Clothes'),
        approved_asset('clothes/toigo_fisherman_sweater/toigo_fisherman_sweater.mhclo', 'Clothes'),
        approved_asset('clothes/shoes01/shoes01.mhclo', 'Clothes'),
    ]
    loaded = []
    for item in assets:
        obj = svc.HumanService.add_mhclo_asset(item['path'], body, asset_type=item['type'], subdiv_levels=0, material_type='GAMEENGINE')
        assert obj and obj.type == 'MESH'
        loaded.append(obj)
        role = item['type']
        image_materials = {
            'Hair': ('M_Release_Mother_Hair', SYSTEM / 'hair/braid01/braid01_diffuse.png', (0.56, 0.43, 0.32), 0.83, True),
            'Eyes': ('M_Release_Mother_Eyes', SYSTEM / 'eyes/materials/brown_eye.png', (1, 1, 1), 0.30, False),
            'Eyebrows': ('M_Release_Mother_Brows', SYSTEM / 'eyebrows/eyebrow002/eyebrow002.png', (0.65, 0.52, 0.40), 0.85, True),
            'Eyelashes': ('M_Release_Mother_Lashes', SYSTEM / 'eyelashes/eyelashes01/eyelashes01.png', (0.40, 0.30, 0.22), 0.90, True),
        }
        if role in image_materials:
            obj.data.materials.clear()
            obj.data.materials.append(textured_material(*image_materials[role]))
        if 'toigo_camisole' in item['path']:
            obj.data.materials.clear()
            obj.data.materials.append(plain_material('M_Release_Mother_LinenDress', (0.15, 0.205, 0.175)))
        if 'toigo_fisherman_sweater' in item['path']:
            obj.data.materials.clear()
            obj.data.materials.append(textured_material('M_Release_Mother_FishermanKnit',
                SHIRTS / 'clothes/toigo_fisherman_sweater/shirt-knit.png', tint=(0.75, 1.4, 0.95), roughness=0.92))
        if 'clothes/shoes01/' in item['path'].replace('\\', '/'):
            obj.data.materials.clear()
            obj.data.materials.append(plain_material('M_Release_Mother_LeatherShoe', (0.065, 0.038, 0.020), 0.78))
            obj.data.materials.append(plain_material('M_Release_Mother_DarkStocking', (0.070, 0.060, 0.045), 0.94))
            sock_start = max(rig.data.bones['foot_l'].head_local.z, rig.data.bones['foot_r'].head_local.z) + 0.045
            for face in obj.data.polygons:
                face.material_index = 1 if face.center.z > sock_start else 0
    export_rig = svc.ExportService.create_character_copy(body, name_suffix='_Export')
    export_body = svc.ObjectService.find_object_of_type_amongst_nearest_relatives(export_rig)
    svc.TargetService.bake_targets(export_body)
    svc.FaceService.load_targets(export_body, load_microsoft_visemes=False, load_meta_visemes=False, load_arkit_faceunits=True)
    svc.FaceService.interpolate_targets(export_body)
    export_dress = next(obj for obj in descendants(export_rig) if obj.type == 'MESH' and 'toigo_camisole' in obj.name)
    for vertex in export_dress.data.vertices:
        if vertex.co.z < 0.60:
            vertex.co.z -= 0.075 * min(1.0, max(0.0, (0.60 - vertex.co.z) / 0.25))
    export_dress.data.update()
    export_sweater = next(obj for obj in descendants(export_rig) if obj.type == 'MESH' and 'toigo_fisherman_sweater' in obj.name)
    garment_fit = prepare_verified_clothing(export_dress, export_sweater)
    svc.ExportService.bake_modifiers_remove_helpers(export_body, bake_masks=True, bake_subdiv=False, remove_helpers=True)
    covered_skin = occlude_sweater_covered_skin(export_body, export_sweater, export_rig)
    export_rig.name = 'SK_Release_Mother'
    export_body.name = 'SK_Release_Mother_Body'
    for obj in descendants(rig):
        obj.hide_render = True
        obj.hide_set(True)
    exported = descendants(export_rig)
    required = importlib.import_module(PACKAGE + '.services.faceservice').ARKIT_FACEUNITS
    morphs = canonical_morphs(exported, required)
    assert len(morphs) == 52
    effective_morphs = effective_morph_metrics(exported, morphs)
    for obj in exported:
        if obj.type == 'MESH':
            for modifier in list(obj.modifiers):
                if modifier.type == 'SUBSURF':
                    obj.modifiers.remove(modifier)
            for face in obj.data.polygons:
                face.use_smooth = True
    listening_animation(export_rig, exported)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in exported:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = export_rig
    fbx = build_dir / 'SK_Release_Mother.fbx'
    bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'ARMATURE', 'MESH'}, add_leaf_bones=False,
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Y', axis_up='Z',
        use_mesh_modifiers=False, mesh_smooth_type='FACE', bake_anim=True, bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=False, bake_anim_simplify_factor=0.0, path_mode='COPY', embed_textures=False)
    head = export_rig.pose.bones.get('head')
    head_height = float((export_rig.matrix_world @ head.head).z) + 0.08 if head else 1.53
    previews = studio_preview(exported, build_dir, head_height)
    blend = build_dir / 'Mother_ArtGate.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    after = protected_native_hashes()
    assert before == after, 'Unexpected native project modification'
    assert rest_bones == {bone.name: [list(row) for row in bone.matrix_local] for bone in export_rig.data.bones}, 'Rest skeleton changed'
    rows = []
    textures = {}
    for obj in exported:
        if obj.type != 'MESH':
            continue
        row = {'name': obj.name, 'vertices': len(obj.data.vertices), 'triangles': sum(len(p.vertices) - 2 for p in obj.data.polygons),
               'materials': [m.name for m in obj.data.materials if m], 'morphs': list(obj.data.shape_keys.key_blocks.keys()) if obj.data.shape_keys else [],
               'armature_modifiers': [m.object.name if m.object else None for m in obj.modifiers if m.type == 'ARMATURE']}
        rows.append(row)
        for mat in obj.data.materials:
            if mat and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        path = Path(bpy.path.abspath(node.image.filepath))
                        if path.is_file():
                            textures[str(path)] = {'sha256': sha(path), 'pixels': list(node.image.size), 'colorspace': node.image.colorspace_settings.name}
    report = {'success': True, 'scope': 'First clothed human Blender art gate only; not a finished character or native Unreal verification.',
        'run': run, 'vendor_version': list(vendor.VERSION), 'vendor_zip_sha256': OFFICIAL_SHA, 'sources_manifest_sha256': sha(SOURCES / 'source_manifest.json'),
        'character': 'Mother', 'art_revision': 4, 'visual_macro_parameters_are_not_story_age_or_identity': macros, 'rig': 'MPFB GameEngine',
        'rest_skeleton_unchanged': True, 'rest_bone_matrices': rest_bones, 'material_recipes': MATERIAL_RECIPES,
        'verified_clothing_fit': garment_fit,
        'covered_skin_occlusion': covered_skin,
        'clothing': ['Explicit CC0 fitted fisherman sweater', 'Explicit CC0 dress retained as skirt under sweater', 'Original CC0 fitted closed shoes and dark stockings'],
        'selected_assets': assets, 'facial_morph_count': len(morphs), 'facial_morphs': morphs,
        'effective_morph_measurement': effective_morphs,
        'animation': 'Authored relaxed listening loop and actual eyelid morph blink. No voice or lip synchronization claimed.',
        'meshes': rows, 'total_triangles': sum(r['triangles'] for r in rows), 'textures': textures,
        'fbx': {'path': str(fbx), 'sha256': sha(fbx)}, 'blend': str(blend), 'previews': previews,
        'native_imported': False, 'native_animation_verified': False, 'native_project_unchanged': before == after, 'protected_sha256': before,
        'next_gate': 'Import a new namespaced skeletal mesh with morphs and its listening animation; native full-body/open/blink comparison and clothing-deformation review before replacing any stable NPC actor.'}
    (build_dir / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    (ROOT / 'output/release_characters/latest.json').write_text(json.dumps({'run': run, 'manifest': str(build_dir / 'manifest.json')}, indent=2) + '\n')
    print('RELEASE_MOTHER_ART_GATE_SUCCESS ' + str(build_dir / 'manifest.json'), flush=True)


if __name__ == '__main__':
    main()
