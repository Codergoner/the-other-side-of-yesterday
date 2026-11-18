"""Queued Mother REV11 clothing A/B, preserving all REV4 and native evidence.

--inspect-registry reads the proved blend and reports hidden source meshes only.
--build-rev11 restores the full fitted CC0 dress beneath the intact sweater,
with covered-leg skin face occlusion, then uses the proved cm-data/Armature export.
Original REV7 skirt silhouette; no flare. All surviving coordinates/UV/weights
and all facial keys remain unchanged; body face topology intentionally changes.
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



def occlude_skirt_covered_skin(body, rig):
    """Same proved FACES_ONLY method as original sweater occlusion.

    Keep every vertex and shape-key index. Remove only covered skin polygons,
    so no skin triangle can emerge through the modest REV7 fitted skirt.
    """
    import bpy
    import bmesh
    length=float(bpy.context.scene.unit_settings.scale_length)
    assert body.name=='SK_Release_Mother_Body' and body.type=='MESH'
    assert body.data.shape_keys and body.data.shape_keys.key_blocks
    groups={g.index:g.name for g in body.vertex_groups}
    rig_bones={b.name for b in rig.data.bones}
    leg_bones={'pelvis','thigh_l','thigh_r','calf_l','calf_r','foot_l','foot_r','ball_l','ball_r'}
    hand_bones=set()
    for bone in rig.data.bones:
        parent=bone
        while parent:
            if parent.name in {'hand_l','hand_r'}:
                hand_bones.add(bone.name);break
            parent=parent.parent
    assert {'pelvis','thigh_l','thigh_r','calf_l','calf_r'}.issubset(set(groups.values()))
    def coordinates():
        result={}
        for key in body.data.shape_keys.key_blocks:
            values=array.array('f',[0.0])*(len(key.data)*3)
            key.data.foreach_get('co',values)
            result[key.name]=hashlib.sha256(values.tobytes()).hexdigest()
        return result
    def key_properties():
        return [(k.name,k.relative_key.name,k.vertex_group,k.interpolation,
                 float(k.slider_min),float(k.slider_max),float(k.value))
                for k in body.data.shape_keys.key_blocks]
    def per_face():
        result={}
        for face in body.data.polygons:
            result[tuple(face.vertices)]={'material_index':face.material_index,
                'uv':{layer.name:[tuple(layer.data[i].uv) for i in face.loop_indices]
                      for layer in body.data.uv_layers}}
        assert len(result)==len(body.data.polygons),'Unexpected duplicate body polygons'
        return result
    old_structure=mesh_structure(body)
    old_coordinates=coordinates();old_keys=key_properties();old_faces=per_face()
    vertex_coordinates=json_sha([list(v.co) for v in body.data.vertices])
    old_curve_hash=units.non_length_animation_hash([body])
    basis=body.data.shape_keys.key_blocks[0]
    facial=set()
    for key in body.data.shape_keys.key_blocks:
        if key!=basis:
            facial.update(i for i in range(len(basis.data))
                          if (key.data[i].co-basis.data[i].co).length_squared>1e-14)
    eligible=set();protected=set(facial);dominant_nonleg=set();height={}
    for vertex in body.data.vertices:
        p=(body.matrix_world @ vertex.co)*length
        height[vertex.index]=float(p.z)
        weights={groups[g.group]:float(g.weight) for g in vertex.groups if groups[g.group] in rig_bones}
        dominant=max(weights,key=weights.get) if weights else None
        leg_weight=sum(value for name,value in weights.items() if name in leg_bones)
        hand_weight=sum(value for name,value in weights.items() if name in hand_bones)
        if dominant not in leg_bones:dominant_nonleg.add(vertex.index)
        if p.z>=1.0 or hand_weight>.025:protected.add(vertex.index)
        if .35<=p.z<=.98 and dominant in leg_bones and leg_weight>=.65 and vertex.index not in protected:
            eligible.add(vertex.index)
    # All polygon corners must be covered/leg weighted. No hand, head,
    # lower-calf, shoe or facial-morph vertex can enter the selection.
    selected=[p for p in body.data.polygons if all(i in eligible for i in p.vertices)]
    print('COVERED_LEG_DIAGNOSTIC', {'length':length,'zrange':[min(height.values()),max(height.values())],'facial':len(facial),'eligible':len(eligible),'protected':len(protected),'bone_group_count':len(rig_bones),'dominant_nonleg':len(dominant_nonleg),'selected':len(selected)},flush=True)
    assert 50<len(selected)<len(body.data.polygons)*.70,('Unsafe covered-leg selection',len(selected))
    removed_faces={tuple(p.vertices) for p in selected}
    removed_triangles=sum(len(p.vertices)-2 for p in selected)
    protected_faces={tuple(p.vertices) for p in body.data.polygons if any(i in protected for i in p.vertices)}
    bm=bmesh.new();bm.from_mesh(body.data);bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm,geom=[bm.faces[p.index] for p in selected],context='FACES_ONLY')
    bm.to_mesh(body.data);bm.free();body.data.update()
    new_structure=mesh_structure(body);new_faces=per_face()
    assert old_structure['vertices']==new_structure['vertices'],'Coverage cull reordered/deleted vertices'
    assert vertex_coordinates==json_sha([list(v.co) for v in body.data.vertices]),'Body basis coordinates changed'
    assert old_coordinates==coordinates() and old_keys==key_properties(),'A facial key/index/property changed'
    assert old_structure['vertex_group_weights_sha256']==new_structure['vertex_group_weights_sha256'],'Body weights changed'
    assert set(new_faces)==set(old_faces)-removed_faces,'Unexpected body face removal/reordering'
    assert all(old_faces[key]==value for key,value in new_faces.items()),'Retained UVs/material assignments changed'
    assert protected_faces.issubset(new_faces),'Head/hand/facial face removed'
    assert units.non_length_animation_hash([body])==old_curve_hash,'Body facial animation curves changed'
    assert all(not any(i in protected for i in face) for face in removed_faces)
    return {'method':'BMesh FACES_ONLY covered-skin occlusion; original vertex/morph indices retained',
        'body':body.name,'world_z_band_m':[.35,.98],
        'minimum_total_leg_pelvis_weight':.65,'dominant_bones':sorted(leg_bones),
        'removed_body_polygons':len(removed_faces),'removed_body_triangles':removed_triangles,
        'body_before':old_structure,'body_after':new_structure,
        'body_face_topology_intentionally_changed':True,'deleted_or_moved_vertices':0,
        'all_vertex_coordinates_and_weights_preserved':True,
        'all_shape_key_names_properties_and_coordinate_sha256':old_coordinates,
        'all_face_and_other_morph_coordinates_preserved':True,
        'retained_face_uvs_materials_preserved':True,
        'protected_head_hand_facial_faces_preserved':True,
        'protected_facial_vertices':len(facial),'protected_head_hand_facial_faces':len(protected_faces),
        'nonleg_vertex_coordinate_signatures_preserved':len(dominant_nonleg),
        'vertices_above_one_meter_unchanged':sum(z>=1.0 for z in height.values()),
        'lower_calf_below_point35m_and_shoes_unchanged':True,
        'skirt_flare_added_m':0.0,'native_or_gait_visually_approved':False}


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
    output = ROOT / 'output/release_mother_rev11/builds' / run
    output.mkdir(parents=True)
    source_snapshot = output / 'builder_source_snapshot.py'
    source_snapshot.write_bytes(Path(__file__).read_bytes())
    report = {'success': False, 'art_revision': 11, 'run': run, 'inspect_only': inspect_only,
        'scope': 'Modest REV7 skirt silhouette with covered-leg skin polygon occlusion; no flare, native promotion, gait approval or story-NPC replacement.',
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
        new_dress.name = 'Mother_Rev11_FULL_FittedDress'
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
        # A simple skinned skirt needs shared pelvis weights: independently
        # following each leg folds the continuous hem into angular flaps.
        # This is an explicit garment-only weight revision, not a preserved-
        # clothing-weight claim. Keep body, hands, face, rig and clips intact.
        from mathutils import Vector
        pelvis_world=rig.matrix_world @ rig.data.bones['pelvis'].head_local
        selected=list(range(len(new_dress.data.vertices)))
        for group in new_dress.vertex_groups:
            group.remove(selected)
        for name,weight in [('pelvis',0.80),('thigh_l',0.10),('thigh_r',0.10)]:
            group=new_dress.vertex_groups.get(name) or new_dress.vertex_groups.new(name=name)
            group.add(selected,weight,'REPLACE')
        inverse=new_dress.matrix_world.inverted()
        adjusted=0
        for vertex in new_dress.data.vertices:
            p=new_dress.matrix_world @ vertex.co
            if p.z>0.84:
                delta=Vector((p.x-pelvis_world.x,p.y-pelvis_world.y,0))
                if delta.length>0.02:
                    p-=delta.normalized()*min(0.028,(p.z-0.84)/0.08*0.028)
                    vertex.co=inverse @ p;adjusted+=1
        new_dress.data.update()
        report['garment_weight_revision']={'pelvis':0.8,'thigh_l':0.1,'thigh_r':0.1,'body_face_rig_coordinates_unchanged':True,'waist_vertices_inset_under_sweater':adjusted,'max_inset_m':0.028,'skirt_flare_added_m':0.0}
        body = next(o for o in stable_objects if o.name == 'SK_Release_Mother_Body')
        report['covered_leg_skin_occlusion'] = occlude_skirt_covered_skin(body, rig)
        report['body_topology_intentionally_culled'] = True
        report['full_dress_copy_preserves_original_topology_uv_weights'] = False
        report['old_clipped_dress_exported'] = False
        report['new_full_dress_topology_change_is_intentional'] = True
        report['upper_bodice_visibility_zfight_strap_fit_reviewed'] = False
        for face in new_dress.data.polygons:
            face.use_smooth = True
        recipes = {name: dict(value) for name,value in source['material_recipes'].items()}
        clone_fabric_material(new_dress, 'M_Release_Mother_LinenDress', 'M_Release_MotherRev11_LinenDress', recipes)
        sweater = next(o for o in stable_objects if o.type == 'MESH' and 'toigo_fisherman_sweater' in o.name)
        clone_fabric_material(sweater, 'M_Release_Mother_FishermanKnit', 'M_Release_MotherRev11_FishermanKnit', recipes)
        assert units.basis_hash(rig) == original_rest_sha, 'Clothing replacement changed source local skeleton'
        stable_after = units.snapshot(rig, stable_objects)
        report['unchanged_body_rig_vertex_coordinates_before_unit_conversion'] = units.snapshot_difference(stable_before, stable_after)
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
        fbx = output / 'SK_MotherRev11.fbx'
        bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'ARMATURE','MESH'}, add_leaf_bones=False,
            armature_nodetype='NULL', global_scale=1.0, apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Y', axis_up='Z',
            use_mesh_modifiers=False, mesh_smooth_type='FACE', bake_anim=True, bake_anim_use_nla_strips=False,
            bake_anim_use_all_actions=False, bake_anim_simplify_factor=0.0, path_mode='COPY', embed_textures=False)
        blend = output / 'Mother_REV11_CentimeterData.blend'
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
            (ROOT / 'output/release_mother_rev11/latest.json').write_text(json.dumps({'run':run,'manifest':str(output/'manifest.json')},indent=2)+'\n')
        print('MOTHER_REV11_SOURCE_REPORT ' + str(output / 'manifest.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--inspect-registry', action='store_true')
    mode.add_argument('--build-rev11', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    build(args.inspect_registry)
