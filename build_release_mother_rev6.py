"""Queued Mother REV6 clothing A/B, preserving all REV4 and native evidence.

--inspect-registry reads the proved blend and reports hidden source meshes only.
--build-rev6 restores the full fitted CC0 dress beneath the intact sweater,
without body/rig/weight edits, then uses the proved cm-data/Armature export.
No native import/promotion, existing save, new download or addon registration.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import array
import hashlib
import json
import math
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import build_release_characters as base
import build_release_unit_probe as units
import windows_file_guards as files


def json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def protected():
    project = ROOT / 'game_unreal'
    result = files.native(project)
    paths = files.files(ROOT / 'output/release_characters')
    paths += files.files(ROOT / 'output/release_npc_variations')
    paths += [Path(files.canonical(p)) for p in Path(files.io_path(project)).glob('release*.json')]
    paths += [ROOT / 'build_release_characters.py', ROOT / 'build_release_npc_variations.py',
              ROOT / 'build_release_unit_probe.py', Path(files.__file__)]
    for root in [project / 'Saved/SaveGames', Path(os.environ.get('LOCALAPPDATA','')) / 'YesterdayHarbor/Saved/SaveGames']:
        paths += files.matches(root, '*.sav')
    result.update({files.canonical(p): files.sha(p) for p in paths})
    return result


def mesh_structure(obj):
    uv = {}
    for layer in obj.data.uv_layers:
        values = array.array('f', [0.0]) * (len(layer.data) * 2)
        layer.data.foreach_get('uv', values)
        uv[layer.name] = hashlib.sha256(values.tobytes()).hexdigest()
    return {'vertices': len(obj.data.vertices), 'faces': len(obj.data.polygons),
        'topology_sha256': json_sha([list(p.vertices) for p in obj.data.polygons]), 'uv_sha256': uv,
        'vertex_group_weights_sha256': json_sha({'groups': [g.name for g in obj.vertex_groups],
            'weights': [[[g.group,float(g.weight)] for g in v.groups] for v in obj.data.vertices]})}


def registry(scene):
    return [{'name': obj.name, 'type': obj.type, 'parent': obj.parent.name if obj.parent else None,
        'hidden_render': bool(obj.hide_render), 'hidden_view': bool(obj.hide_get()),
        'vertices': len(obj.data.vertices) if obj.type == 'MESH' else None,
        'faces': len(obj.data.polygons) if obj.type == 'MESH' else None,
        'armature_modifiers': [m.object.name if m.object else None for m in obj.modifiers if m.type == 'ARMATURE']}
        for obj in scene.objects]


def clone_fabric_material(obj, old_name, new_name, recipes):
    for i, material in enumerate(obj.data.materials):
        if material and material.name == old_name:
            clone = material.copy()
            clone.name = new_name
            clone.use_backface_culling = False
            obj.data.materials[i] = clone
            recipes[new_name] = dict(recipes[old_name], two_sided=True)
            return
    raise RuntimeError('Expected original fabric material missing: ' + old_name)


def build(inspect_only):
    import bpy
    latest = json.loads((ROOT / 'output/release_characters/latest.json').read_text())
    source_manifest = Path(latest['manifest'])
    source = json.loads(source_manifest.read_text())
    assert source['success'] and source['art_revision'] == 4, 'Use the proved REV4 source only'
    source_blend = Path(source['blend'])
    reference_path = ROOT / 'game_unreal/release_character_unit_probe_report.json'
    reference = json.loads(reference_path.read_text())
    native = reference.get('preferred_candidate')
    assert reference['success'] and reference['native_executed'] and native and native['native_bone_count'] == 53
    assert native['native_unit_scale']['unit_root_scale_passed'] and native['human_height_passed']
    before = protected()
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    output = ROOT / 'output/release_mother_rev6/builds' / run
    output.mkdir(parents=True)
    source_snapshot = output / 'builder_source_snapshot.py'
    source_snapshot.write_bytes(Path(__file__).read_bytes())
    report = {'success': False, 'art_revision': 6, 'run': run, 'inspect_only': inspect_only,
        'scope': 'New full-fitted-dress/two-sided-cloth A/B candidate only; no native promotion, gait approval or story-NPC replacement.',
        'source_manifest': str(source_manifest), 'source_manifest_sha256': files.sha(source_manifest),
        'source_blend': str(source_blend), 'source_blend_sha256': files.sha(source_blend),
        'builder_source_snapshot': str(source_snapshot), 'builder_source_sha256': files.sha(source_snapshot),
        'normalization_reference_report': str(reference_path), 'normalization_reference_sha256': files.sha(reference_path),
        'reuse_native_mesh_reference': native['mesh'], 'reuse_existing53_bone_native_skeleton_required': True,
        'body_or_face_weights_edited': False, 'native_imported': False, 'NativeGarmentApproval': False}
    try:
        bpy.ops.wm.open_mainfile(filepath=str(source_blend), load_ui=False, use_scripts=False)
        bpy.context.preferences.use_preferences_save = False
        scene = bpy.context.scene
        scene.frame_set(1)
        rig = bpy.data.objects.get('SK_Release_Mother')
        assert rig and rig.type == 'ARMATURE' and len(rig.data.bones) == 53
        original_export = base.descendants(rig)
        selected_ids = {o.as_pointer() for o in original_export}
        clipped = [o for o in original_export if o.type == 'MESH' and 'toigo_camisole' in o.name]
        full = [o for o in scene.objects if o.type == 'MESH' and 'toigo_camisole' in o.name and o.as_pointer() not in selected_ids]
        report['object_registry'] = registry(scene)
        (output / 'source_registry.json').write_text(json.dumps(report['object_registry'], indent=2) + '\n')
        assert len(clipped) == 1 and len(full) == 1, 'Inspect the actual source registry; exactly one hidden full fitted dress and one clipped export are required'
        clipped, full = clipped[0], full[0]
        assert full.parent and full.parent.type == 'ARMATURE' and full.parent != rig
        assert len(full.data.polygons) > len(clipped.data.polygons), 'Hidden candidate is not the full original dress'
        for bone in rig.data.bones:
            other = full.parent.data.bones[bone.name].matrix_local
            assert max(abs(bone.matrix_local[row][column]-other[row][column]) for row in range(4) for column in range(4)) < 1e-5, 'Original/full-dress and export rigs differ'
        report['hidden_full_dress_source'] = {'object': full.name, 'parent': full.parent.name, 'structure': mesh_structure(full)}
        report['old_clipped_dress'] = {'object': clipped.name, 'structure': mesh_structure(clipped)}
        if inspect_only:
            report.update(success=True, registry_inspected=True, export_performed=False)
            return
        stable_objects = [o for o in original_export if o != clipped]
        original_rest_sha = units.basis_hash(rig)
        original_rest = units.rest_world(rig, scene.unit_settings.scale_length)
        body_before = units.shape_coordinates(stable_objects, scene.unit_settings.scale_length)
        stable_before = units.snapshot(rig, stable_objects)
        face_sha_before = units.non_length_animation_hash(stable_objects)
        scene.frame_set(1)
        new_dress = full.copy()
        new_dress.data = full.data.copy()
        new_dress.name = 'Mother_Rev6_FULL_FittedDress'
        scene.collection.objects.link(new_dress)
        old_world = full.matrix_world.copy()
        new_dress.parent = rig
        new_dress.matrix_world = old_world
        for modifier in list(new_dress.modifiers):
            if modifier.type == 'ARMATURE':
                modifier.object = rig
            elif modifier.type == 'SUBSURF':
                new_dress.modifiers.remove(modifier)
            else:
                raise RuntimeError('Unreviewed original dress modifier: ' + modifier.type)
        assert any(m.type == 'ARMATURE' and m.object == rig for m in new_dress.modifiers)
        assert mesh_structure(new_dress) == mesh_structure(full), 'Full dress topology/UVs/weights changed during copy'
        new_dress.hide_render = False
        new_dress.hide_set(False)
        clipped.hide_render = True
        clipped.hide_set(True)
        clipped.parent = None
        # Only the hidden upper bodice is removed; retain the full hem and
        # all surviving original/interpolated CC0 garment weights and UVs.
        import bmesh
        from mathutils import Vector
        assert new_dress.data.shape_keys is None, 'Do not bisect a morph mesh'
        bm=bmesh.new(); bm.from_mesh(new_dress.data)
        world_cut=Vector((0,0,0.96))
        plane_co=new_dress.matrix_world.inverted() @ world_cut
        plane_no=new_dress.matrix_world.to_3x3().transposed() @ Vector((0,0,1))
        before_structure=mesh_structure(new_dress)
        bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),dist=1e-6,plane_co=plane_co,plane_no=plane_no,clear_outer=True,clear_inner=False)
        bm.to_mesh(new_dress.data);bm.free();new_dress.data.update()
        report['hidden_bodice_trim']={'world_cut_height_m':0.96,'before':before_structure,'after':mesh_structure(new_dress),'scope':'Upper bodice only; full original skirt hem retained, body/rig/face untouched'}
        report['full_dress_copy_preserves_original_topology_uv_weights'] = False
        report['old_clipped_dress_exported'] = False
        report['new_full_dress_topology_change_is_intentional'] = True
        report['upper_bodice_visibility_zfight_strap_fit_reviewed'] = False
        for face in new_dress.data.polygons:
            face.use_smooth = True
        recipes = {name: dict(value) for name,value in source['material_recipes'].items()}
        clone_fabric_material(new_dress, 'M_Release_Mother_LinenDress', 'M_Release_MotherRev6_LinenDress', recipes)
        sweater = next(o for o in stable_objects if o.type == 'MESH' and 'toigo_fisherman_sweater' in o.name)
        clone_fabric_material(sweater, 'M_Release_Mother_FishermanKnit', 'M_Release_MotherRev6_FishermanKnit', recipes)
        assert units.basis_hash(rig) == original_rest_sha, 'Clothing replacement changed source local skeleton'
        stable_after = units.snapshot(rig, stable_objects)
        report['unchanged_body_rig_meshes_before_unit_conversion'] = units.snapshot_difference(stable_before, stable_after)
        report['unchanged_body_face_morph_coordinates_before_unit_conversion'] = units.shape_difference(body_before, units.shape_coordinates(stable_objects, scene.unit_settings.scale_length))
        exported = stable_objects + [new_dress]
        source_names = source['facial_morphs']
        effective = base.effective_morph_metrics(exported, source_names)
        assert effective['effective_facial_morph_count'] == native['native_morph_count'], 'Effective facial set changed'
        head = rig.pose.bones['head']
        previews = base.studio_preview(exported, output, float((rig.matrix_world @ head.head).z) + 0.08)
        source_shape = units.shape_coordinates(exported, scene.unit_settings.scale_length)
        source_poses = units.snapshot(rig, exported)
        conversion = units.normalize_centimeter_data(rig, exported)
        converted_poses = units.snapshot(rig, exported)
        pose_proof = units.snapshot_difference(source_poses, converted_poses)
        morph_proof = units.shape_difference(source_shape, units.shape_coordinates(exported, scene.unit_settings.scale_length))
        scene.frame_set(1)
        bpy.context.view_layer.update()
        converted_rest = units.rest_world(rig, scene.unit_settings.scale_length)
        rest_proof = units.rest_difference(original_rest, converted_rest)
        assert units.non_length_animation_hash(stable_objects) == face_sha_before, 'Original facial/non-length animation curves changed'
        assert bpy.data.objects.get('Armature') in [None, rig]
        rig.name = 'Armature'
        scene.camera = None
        for obj in list(scene.objects):
            if obj.type in ['CAMERA','LIGHT']:
                bpy.data.objects.remove(obj, do_unlink=True)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in exported:
            obj.hide_set(False)
            obj.select_set(True)
        bpy.context.view_layer.objects.active = rig
        fbx = output / 'SK_MotherRev6.fbx'
        bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'ARMATURE','MESH'}, add_leaf_bones=False,
            armature_nodetype='NULL', global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Y', axis_up='Z',
            use_mesh_modifiers=False, mesh_smooth_type='FACE', bake_anim=True, bake_anim_use_nla_strips=False,
            bake_anim_use_all_actions=False, bake_anim_simplify_factor=0.0, path_mode='COPY', embed_textures=False)
        blend = output / 'Mother_REV6_CentimeterData.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        used = {m.name for obj in exported if obj.type == 'MESH' for m in obj.data.materials if m}
        meshes = [{'name':o.name,'vertices':len(o.data.vertices),'triangles':sum(len(p.vertices)-2 for p in o.data.polygons)} for o in exported if o.type=='MESH']
        report.update(success=True, export_performed=True, coordinate_representation='CentimeterData_ArmatureName', unit_representation_changed=True,
            local_rest_matrix_equality_across_unit_conversion_not_claimed=True, source_core_bone_count=len(rig.data.bones), rest_bone_names=sorted(b.name for b in rig.data.bones),
            pre_conversion_local_rest_basis_sha256=original_rest_sha, normalized_local_rest_basis_sha256=units.basis_hash(rig),
            physical_rest_position_preservation=rest_proof, physical_pose_preservation=pose_proof, physical_morph_coordinate_preservation=morph_proof,
            non_length_and_face_curve_keys_unchanged=True, effective_morph_measurement=effective,
            fbx={'path':str(fbx),'sha256':files.sha(fbx)}, blend=str(blend), previews=previews,
            preview_representation='Meter-data rendering before conversion; physically equivalent normalized export is separately verified.',
            material_recipes={name:recipes[name] for name in used}, meshes=meshes,total_triangles=sum(m['triangles'] for m in meshes),
            next_gate='Actual FullBody/Open/Blink clothing inspection, then NEW native mesh using the EXISTING53-bone unit skeleton and unmodified gait clips; front/back/profile walking cloth A/B before any promotion.')
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        after = protected()
        report['all_old_source_native_role_outputs_reports_saves_unchanged'] = before == after
        report['success'] = bool(report['success'] and before == after)
        report['protected_sha256'] = before
        (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
        if report['success'] and not inspect_only:
            (ROOT / 'output/release_mother_rev6/latest.json').write_text(json.dumps({'run':run,'manifest':str(output/'manifest.json')},indent=2)+'\n')
        print('MOTHER_REV6_SOURCE_REPORT ' + str(output / 'manifest.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--inspect-registry', action='store_true')
    mode.add_argument('--build-rev6', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    build(args.inspect_registry)
