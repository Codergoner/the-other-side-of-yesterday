"""Queued Blender source export only. Never opens an existing scene.

Eight triangles extend the finite old sea, with its centre left empty. Run this
only in the root's native-writer queue; importing this module is side-effect free.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'game_unreal/Python'))
import release_coast_contract as contract


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    import bpy
    if ROOT.name != 'Release_20261026':
        raise RuntimeError('Coast authoring is restricted to the Release copy')
    plan = contract.policy()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    out = ROOT/'output/release_coast_extension'
    folder = out/'builds'/stamp
    (folder/'meshes').mkdir(parents=True, exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = 'Release coast extension - original sea footprint kept empty'
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    vertices, triangles = contract.geometry(plan)
    data = bpy.data.meshes.new(plan['extension']['mesh'])
    data.from_pydata(vertices, [], triangles)
    data.update()
    material = bpy.data.materials.new('M_ReleaseCoastPlaceholder')
    material.diffuse_color = (.031, .10, .13, 1)
    data.materials.append(material)
    uv = data.uv_layers.new(name='UV0_Metric')
    for face in data.polygons:
        # Same metric UV basis as the old sea top, for compatible tangent axes.
        assert face.normal.z > .9999
        for li in face.loop_indices:
            p = data.vertices[data.loops[li].vertex_index].co
            uv.data[li].uv = (p.x*.5, p.y*.5)
    obj = bpy.data.objects.new(plan['extension']['mesh'], data)
    scene.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    file = folder/'meshes'/(obj.name+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(file), use_selection=True, object_types={'MESH'},
        axis_forward='-Y', axis_up='Z', global_scale=1, apply_unit_scale=True,
        apply_scale_options='FBX_SCALE_UNITS', use_mesh_modifiers=True, add_leaf_bones=False,
        bake_anim=False, path_mode='RELATIVE', embed_textures=False, mesh_smooth_type='FACE')
    blend = folder/'Release_Coast_Extension.blend'
    scene['Owner'] = plan['owner']
    scene['Scope'] = 'One visual-only ring; existing city, sea, sky, story and physics untouched'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    manifest = {'schema': 1, 'build_stamp': stamp, 'owner': plan['owner'],
        'source_sha256': sha(__file__), 'contract_sha256': sha(contract.__file__),
        'policy_sha256': sha(contract.PLAN), 'mesh_name': obj.name,
        'mesh_file': file.relative_to(out).as_posix(), 'mesh_sha256': sha(file),
        'blend_file': blend.relative_to(out).as_posix(), 'blend_sha256': sha(blend),
        'triangles': len(triangles), 'vertices': len(vertices), 'material_slots': 1,
        'collision_shapes': 0, 'expected_native_bounds_cm': contract.bounds_cm(plan),
        'original_inner_perimeter_blender_m': vertices[:4],
        'native_imported': False, 'visual_accepted': False, 'performance_measured': False}
    text = json.dumps(manifest, indent=2)+'\n'
    (folder/'manifest.json').write_text(text, encoding='utf-8')
    (out/'manifest.json').write_text(text, encoding='utf-8')
    print('RELEASE_COAST_SOURCE_EXPORTED '+str(out/'manifest.json'), flush=True)
    return manifest


if __name__ == '__main__':
    build()
