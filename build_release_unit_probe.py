"""Queued, export-only Mother unit conversion experiment. No existing saves.

Opens the approved .blend read-only with embedded scripts disabled for each
variant. Emits only NEW FBXs/reports under output/character_unit_probe/<run>.
No MPFB registration, native import, Blender save, gait or retarget claim.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import array
import hashlib
import json
import math
import sys
import traceback

ROOT = Path(__file__).resolve().parent
FRAMES = [1, 31, 46, 61, 91, 120]
EXPORTER = Path('C:/Program Files/Blender Foundation/Blender 5.2/5.2/scripts/addons_core/io_scene_fbx/export_fbx_bin.py')
UE_IMPORTER = Path('C:/Program Files/Epic Games/UE_5.8/Engine/Source/Editor/UnrealEd/Private/Fbx/FbxMainImport.cpp')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def protected():
    project = ROOT / 'game_unreal'
    files = list((project / 'Content').rglob('*.uasset')) + list((project / 'Content').rglob('*.umap'))
    files += list((project / 'Config').glob('*.ini')) + list(project.glob('*.uproject'))
    files += list(project.glob('release*.json'))
    files += [p for p in (ROOT / 'output/release_characters').rglob('*') if p.is_file()]
    files += [ROOT / 'build_release_characters.py', ROOT / 'build_release_npc_variations.py']
    return {str(p): sha(p) for p in files}


def objects_for(rig):
    return [rig] + list(rig.children_recursive)


def parent_depth(obj):
    depth, parent = 0, obj.parent
    while parent:
        depth, parent = depth + 1, parent.parent
    return depth


def basis_hash(rig):
    value = {bone.name: [list(row) for row in bone.matrix_local] for bone in rig.data.bones}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def rest_world(rig, length):
    return {bone.name: {'head_m': list((rig.matrix_world @ bone.head_local) * length),
                        'tail_m': list((rig.matrix_world @ bone.tail_local) * length)} for bone in rig.data.bones}


def rest_difference(before, after):
    assert set(before) == set(after), 'Source rest bone names/count changed'
    maximum = max(math.sqrt(sum((a-b)**2 for a,b in zip(before[name][part], after[name][part])))
                  for name in before for part in ['head_m', 'tail_m'])
    assert maximum <= 3e-5, ('Physical rest bone positions changed', maximum)
    return {'all_source_rest_bone_heads_tails_compared': True, 'max_physical_world_delta_m': maximum, 'tolerance_m': 3e-5}


def non_length_animation_hash(objects):
    owners = list(objects) + [obj.data.shape_keys for obj in objects if obj.type == 'MESH' and obj.data.shape_keys]
    records = []
    for owner in owners:
        action = owner.animation_data.action if owner.animation_data else None
        for index, curve in enumerate(curves(action)):
            if length_channel(curve.data_path):
                continue
            records.append({'owner': owner.name, 'curve_index': index, 'path': curve.data_path, 'axis': curve.array_index,
                'points': [{'co': list(p.co), 'handle_left': list(p.handle_left), 'handle_right': list(p.handle_right),
                            'interpolation': p.interpolation} for p in curve.keyframe_points]})
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


def curves(action):
    # Same Blender5.2 layered-action access used by the installed FBX exporter.
    if action:
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    yield from bag.fcurves


def length_channel(path):
    return path in ['location', 'delta_location'] or path.endswith('.location') or path.endswith('.delta_location')


def shape_coordinates(objects, length):
    result = {}
    for obj in objects:
        if obj.type != 'MESH' or not obj.data.shape_keys:
            continue
        result[obj.name] = {}
        for key in obj.data.shape_keys.key_blocks:
            values = array.array('f', [0.0]) * (len(key.data) * 3)
            key.data.foreach_get('co', values)
            for i, value in enumerate(values):
                values[i] = value * length
            result[obj.name][key.name] = values
    return result


def shape_difference(before, after):
    assert set(before) == set(after), 'Shape-key mesh set changed'
    maximum, scalars = 0.0, 0
    for mesh, keys in before.items():
        assert set(keys) == set(after[mesh]), ('Shape-key names changed', mesh)
        for name, values in keys.items():
            other = after[mesh][name]
            assert len(values) == len(other), ('Morph vertex count changed', mesh, name)
            maximum = max(maximum, max((abs(a-b) for a, b in zip(values, other)), default=0.0))
            scalars += len(values)
    assert maximum <= 2e-6, ('Physical morph coordinates changed', maximum)
    return {'all_keys_and_vertex_indices_preserved': True, 'coordinate_scalars_compared': scalars,
            'max_physical_coordinate_delta_m': maximum, 'tolerance_m': 2e-6}


def snapshot(rig, objects):
    import bpy
    length = bpy.context.scene.unit_settings.scale_length
    result = {}
    for frame in FRAMES:
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        bones = {bone.name: {'head_m': list((rig.matrix_world @ bone.head) * length),
                             'tail_m': list((rig.matrix_world @ bone.tail) * length)} for bone in rig.pose.bones}
        meshes = {}
        for obj in objects:
            if obj.type != 'MESH':
                continue
            evaluated = obj.evaluated_get(deps)
            mesh = evaluated.to_mesh()
            try:
                coordinates = array.array('f')
                for vertex in mesh.vertices:
                    coordinates.extend((evaluated.matrix_world @ vertex.co) * length)
                meshes[obj.name] = coordinates
            finally:
                evaluated.to_mesh_clear()
        values = {obj.name: {key.name: float(key.value) for key in obj.data.shape_keys.key_blocks}
                  for obj in objects if obj.type == 'MESH' and obj.data.shape_keys}
        result[frame] = {'bones': bones, 'mesh_coordinates_m': meshes, 'shape_key_values': values}
    return result


def snapshot_difference(before, after):
    bone_delta, mesh_delta, mesh_scalars = 0.0, 0.0, 0
    assert set(before) == set(after)
    for frame in before:
        a, b = before[frame], after[frame]
        assert a['shape_key_values'] == b['shape_key_values'], ('Facial weights/curve values changed', frame)
        assert set(a['bones']) == set(b['bones']), 'Source bone names/count changed'
        for name in a['bones']:
            for part in ['head_m', 'tail_m']:
                distance = math.sqrt(sum((x-y)**2 for x,y in zip(a['bones'][name][part], b['bones'][name][part])))
                bone_delta = max(bone_delta, distance)
        assert set(a['mesh_coordinates_m']) == set(b['mesh_coordinates_m'])
        for name, values in a['mesh_coordinates_m'].items():
            other = b['mesh_coordinates_m'][name]
            assert len(values) == len(other), 'Evaluated mesh topology changed'
            mesh_delta = max(mesh_delta, max((abs(x-y) for x,y in zip(values, other)), default=0.0))
            mesh_scalars += len(values)
    assert bone_delta <= 3e-5 and mesh_delta <= 3e-5, ('Physical world shape/animation changed', bone_delta, mesh_delta)
    return {'frames_compared': FRAMES, 'all_source_bone_heads_tails_compared': True,
        'all_evaluated_mesh_vertices_compared': True, 'mesh_coordinate_scalars_compared': mesh_scalars,
        'shape_key_curve_values_identical_at_all_samples': True,
        'max_bone_head_tail_delta_m': bone_delta, 'max_deformed_vertex_coordinate_delta_m': mesh_delta, 'tolerance_m': 3e-5}


def normalize_centimeter_data(rig, objects):
    import bpy
    from mathutils import Matrix
    scene = bpy.context.scene
    old_length, new_length = float(scene.unit_settings.scale_length), 0.01
    factor = old_length / new_length
    assert math.isfinite(factor) and factor > 0
    scale, inverse = Matrix.Scale(factor, 4), Matrix.Scale(1.0 / factor, 4)
    scene.frame_set(1)
    transforms = {obj.name: (obj.matrix_basis.copy(), obj.matrix_parent_inverse.copy()) for obj in objects}
    for obj in objects:
        assert not obj.constraints, ('Unit probe requires unconstrained export objects', obj.name)
        assert obj.delta_location.length < 1e-8 and max(abs(v-1) for v in obj.delta_scale) < 1e-8, 'Unexpected delta transform needs explicit conversion'
        assert obj.animation_data is None or not obj.animation_data.drivers, 'Do not silently change driven transforms'
    assert all(not bone.constraints for bone in rig.pose.bones), 'Unit probe requires the proved FK export rig'
    mesh_data_done = set()
    for obj in objects:
        if obj.type == 'MESH' and obj.data.as_pointer() not in mesh_data_done:
            obj.data.transform(scale, shape_keys=True)
            mesh_data_done.add(obj.data.as_pointer())
    rig.data.transform(scale)
    for bone in rig.pose.bones:
        bone.location *= factor
    # Convert true length channels, never rotation/scale/morph values or time.
    action_done, adjusted = set(), []
    for obj in objects:
        action = obj.animation_data.action if obj.animation_data else None
        if not action or action.as_pointer() in action_done:
            continue
        action_done.add(action.as_pointer())
        for curve in curves(action):
            if length_channel(curve.data_path):
                assert not curve.modifiers, 'Translation F-curve modifier needs explicit physical conversion'
                for point in curve.keyframe_points:
                    point.co.y *= factor
                    point.handle_left.y *= factor
                    point.handle_right.y *= factor
                adjusted.append({'action': action.name, 'path': curve.data_path, 'axis': curve.array_index})
    # Uniform coordinate change M' = S M S^-1. Object/bone scale is unchanged.
    for obj in sorted(objects, key=parent_depth):
        basis, parent_inverse = transforms[obj.name]
        obj.matrix_parent_inverse = scale @ parent_inverse @ inverse
        obj.matrix_basis = scale @ basis @ inverse
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = new_length
    scene.frame_set(1)
    bpy.context.view_layer.update()
    return {'old_meters_per_blender_unit': old_length, 'new_meters_per_blender_unit': new_length,
        'uniform_coordinate_factor': factor, 'matrix_conversion': "M'=S M S^-1; mesh/Basis/all shape coordinates/rest bones/length animation channels scaled uniformly",
        'adjusted_translation_curves': adjusted, 'animation_time_rotations_scales_morph_weights_unchanged': True}


def build():
    import bpy
    latest_path = ROOT / 'output/release_characters/latest.json'
    latest = json.loads(latest_path.read_text())
    manifest_path = Path(latest['manifest'])
    mother = json.loads(manifest_path.read_text())
    assert mother['success'] and mother['art_revision'] >= 4
    original_blend = Path(mother['blend'])
    assert original_blend.is_file() and sha(mother['fbx']['path']) == mother['fbx']['sha256']
    before_files = protected()
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    output = ROOT / 'output/character_unit_probe' / run
    output.mkdir(parents=True)
    report = {'success': False, 'run': run, 'scope': 'New export-only coordinate-unit candidates; no existing .blend/FBX/native asset/report is modified.',
        'source_manifest': str(manifest_path), 'source_manifest_sha256': sha(manifest_path),
        'source_blend': str(original_blend), 'source_blend_sha256': sha(original_blend), 'variants': [],
        'blender_version': bpy.app.version_string, 'exporter_source': str(EXPORTER), 'exporter_sha256': sha(EXPORTER),
        'ue_importer_source': str(UE_IMPORTER), 'ue_importer_sha256': sha(UE_IMPORTER),
        'equivalent_option_note': 'At global_scale1, FBX_SCALE_UNITS and FBX_SCALE_ALL take equivalent exporter math; changing that enum alone is not a unit-normalization fix.',
        'native_imported': False, 'native_unit_root_scale_verified': False, 'Manny_retarget_verified': False,
        'native_required_gate': ['Import into a new namespace with unchanged tested FBX options.',
            'Measure actual native bone names/count, first/root local scales and world human height125–210cm; no assumed53-bone count.',
            'Require native first/root scale1, preserved51 effective targets and ticking visible blink/listening before new Manny retarget.',
            'Compare native reference/animated head/foot/pelvis positions to the original human in centimeters; reject scale100 or hip explosions.']}
    recipes = [('Meter_UNITS_Control', False, 'FBX_SCALE_UNITS', False),
               ('Meter_NONE_Control', False, 'FBX_SCALE_NONE', False),
               ('CentimeterData_UNITS', True, 'FBX_SCALE_UNITS', False),
               ('CentimeterData_ArmatureName', True, 'FBX_SCALE_UNITS', True)]
    try:
        for label, normalize, option, rename in recipes:
            bpy.ops.wm.open_mainfile(filepath=str(original_blend), load_ui=False, use_scripts=False)
            bpy.context.preferences.use_preferences_save = False
            rigs = [obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE' and obj.name == 'SK_Release_Mother']
            assert len(rigs) == 1, 'Expected the exact proved export rig'
            rig = rigs[0]
            objects = objects_for(rig)
            scene = bpy.context.scene
            scene.frame_set(1)
            source_length = float(scene.unit_settings.scale_length)
            bones = sorted(b.name for b in rig.data.bones)
            source_basis_hash = basis_hash(rig)
            source_rest = rest_world(rig, source_length)
            non_length_before = non_length_animation_hash(objects)
            shapes = shape_coordinates(objects, source_length)
            source_pose = snapshot(rig, objects)
            conversion = normalize_centimeter_data(rig, objects) if normalize else {'uniform_coordinate_factor': 1.0, 'coordinate_conversion_applied': False}
            candidate_pose = snapshot(rig, objects)
            pose_proof = snapshot_difference(source_pose, candidate_pose)
            shape_proof = shape_difference(shapes, shape_coordinates(objects, scene.unit_settings.scale_length))
            scene.frame_set(1)
            bpy.context.view_layer.update()
            candidate_rest = rest_world(rig, scene.unit_settings.scale_length)
            rest_proof = rest_difference(source_rest, candidate_rest)
            non_length_after = non_length_animation_hash(objects)
            assert non_length_before == non_length_after, 'Non-length animation/face F-curve keys or times changed'
            original_rig_name = rig.name
            if rename:
                # UE5.8 FbxMainImport.cpp2619–2624 explicitly ignores this Blender null parent.
                assert bpy.data.objects.get('Armature') in [None, rig], 'Preserving a pre-existing Armature-named object; inspect this optional candidate before retry'
                rig.name = 'Armature'
                assert rig.name == 'Armature', 'The optional importer-recognized object name was not assigned exactly'
            bpy.ops.object.select_all(action='DESELECT')
            for obj in objects:
                obj.hide_set(False)
                obj.select_set(True)
            bpy.context.view_layer.objects.active = rig
            scene.frame_set(1)
            fbx = output / ('SK_Release_Mother_' + label + '.fbx')
            bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'ARMATURE', 'MESH'}, add_leaf_bones=False,
                armature_nodetype='NULL',
                global_scale=1.0, apply_unit_scale=True, apply_scale_options=option, axis_forward='-Y', axis_up='Z',
                use_mesh_modifiers=False, mesh_smooth_type='FACE', bake_anim=True, bake_anim_use_nla_strips=False,
                bake_anim_use_all_actions=False, bake_anim_simplify_factor=0.0, path_mode='COPY', embed_textures=False)
            assert fbx.is_file() and fbx.stat().st_size > 10000
            report['variants'].append({'id': label, 'fbx': str(fbx), 'fbx_sha256': sha(fbx), 'bytes': fbx.stat().st_size,
                'source_bone_count': len(bones), 'source_bone_names': bones, 'native_bone_count_not_assumed': True,
                'original_export_object_name': original_rig_name, 'export_object_name': rig.name,
                'object_world_scale': list(rig.matrix_world.to_scale()), 'scene_meters_per_unit': scene.unit_settings.scale_length,
                'fbx_apply_scale_options': option, 'global_scale': 1.0, 'conversion': conversion,
                'unit_representation_changed': normalize, 'old_local_rest_basis_sha256': source_basis_hash,
                'candidate_local_rest_basis_sha256': basis_hash(rig),
                'local_rest_matrix_equality_not_claimed': True,
                'physical_rest_position_preservation': rest_proof, 'physical_world_rest_bones_m': candidate_rest,
                'non_length_animation_and_face_curve_keys_unchanged': non_length_before == non_length_after,
                'non_length_animation_curve_sha256': non_length_after,
                'physical_pose_preservation': pose_proof, 'physical_morph_coordinate_preservation': shape_proof,
                'physical_world_bones_by_frame': {str(frame): row['bones'] for frame,row in candidate_pose.items()},
                'shape_key_names_by_mesh': {name: sorted(keys) for name,keys in shapes.items()},
                'native_root_scale_expected_but_unproven': [1, 1, 1] if normalize else None})
            (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
        after_files = protected()
        assert before_files == after_files, 'Existing Mother/native assets or reports changed'
        report.update(success=True, protected_old_assets_reports_unchanged=True, protected_sha256=before_files)
    except Exception:
        report['error'] = traceback.format_exc()
        report['protected_old_assets_reports_unchanged'] = before_files == protected()
        raise
    finally:
        (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
        print('RELEASE_UNIT_PROBE_REPORT ' + str(output / 'manifest.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-probes', action='store_true', required=True)
    parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    build()
