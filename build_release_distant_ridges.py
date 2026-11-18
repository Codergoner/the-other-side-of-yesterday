"""Source-only queued ridge replacement: one mesh, four unchanged footprints.

Run only with the root's Blender queue. Never loads an existing blend. The old
Quest/Harbor geometry is retained. Broad asymmetric ridges replace radial caps
inside the existing footprints and actual sampled peak caps, at7200 triangles.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import bpy
import bmesh

ROOT = Path(__file__).resolve().parent
if ROOT.name != 'Release_20261026':
    raise RuntimeError('Ridge authoring is restricted to the Release copy')
PROPOSAL = ROOT / 'game_unreal/ContentData/release_distant_rock_proposal.json'
PLAN = json.loads(PROPOSAL.read_text(encoding='utf-8'))
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
OUT = ROOT / 'output/release_distant_ridges'
BUILD = OUT / 'builds' / STAMP
(BUILD / 'meshes').mkdir(parents=True, exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
SC = bpy.context.scene
SC.name = 'Release distant ridges - four original coast footprints'
SC.unit_settings.system = 'METRIC'
SC.unit_settings.scale_length = 1
AUTH = bpy.data.collections.new('AUTHORING - four editable ridge patches')
EXP = bpy.data.collections.new('EXPORT - single noncolliding distant mesh')
SC.collection.children.link(AUTH)
SC.collection.children.link(EXP)
MAT = bpy.data.materials.new('M_QuestDistantLand')
MAT.diffuse_color = (.285, .347, .381, 1)


def lerp_keys(keys, x):
    for (a, u), (b, v) in zip(keys, keys[1:]):
        if a <= x <= b:
            return u + (v-u) * (x-a) / (b-a)
    return keys[0][1] if x < keys[0][0] else keys[-1][1]


def obj(name, vertices, faces, collection):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.materials.append(MAT)
    data.update()
    uv = data.uv_layers.new(name='UV0_Metric')
    colors = data.color_attributes.new(name='QuestSceneryColor', type='FLOAT_COLOR', domain='CORNER')
    for face in data.polygons:
        face.use_smooth = True
        for li in face.loop_indices:
            p = data.vertices[data.loops[li].vertex_index].co
            variation = .92 + .055 * math.sin(p.x * .09 + p.y * .07) + .025 * min(1, max(0,p.z)/50)
            colors.data[li].color = (variation, variation, variation, 1)
            uv.data[li].uv = (p.x*.025, p.y*.025)
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    data.update()
    value = bpy.data.objects.new(name, data)
    collection.objects.link(value)
    # Split only coherent ridge/shoulder creases; broad slopes remain smooth.
    edge = value.modifiers.new('Broad rock face creases', 'EDGE_SPLIT')
    edge.split_angle = math.radians(34)
    edge.use_edge_angle = True
    edge.use_edge_sharp = True
    return value


patches, all_vertices, all_faces, proofs = [], [], [], []
for entry in PLAN['geometry']['patches']:
    i = entry['source_patch_index']
    cx, cy = entry['center_blender_metres']
    mn, mx = entry['square_footprint_bounds_blender_metres']['min'], entry['square_footprint_bounds_blender_metres']['max']
    radius = (mx[0]-mn[0])/2
    cap = entry['proposed_peak_cap_metres']
    # Each patch has a different peak/saddle order, with no micro-noise teeth.
    profiles = [
        [(-1,0),(-.78,.23),(-.52,.47),(-.24,.95),(.03,.63),(.29,.81),(.52,.41),(.77,.24),(1,0)],
        [(-1,0),(-.77,.20),(-.49,.49),(-.17,.77),(.10,.56),(.34,1),(.55,.52),(.79,.23),(1,0)],
        [(-1,0),(-.82,.19),(-.57,.61),(-.31,.43),(-.04,.89),(.24,.70),(.47,.38),(.73,.22),(1,0)],
        [(-1,0),(-.78,.17),(-.54,.39),(-.27,.78),(-.04,.52),(.23,.96),(.47,.59),(.76,.26),(1,0)],
    ]
    raw, vertices, faces = [], [], []
    for j in range(31):
        y = j/30*2-1
        for k in range(31):
            x = k/30*2-1
            centerline = .13*math.sin(x*2.3+i*.7) - .05*x
            width = max(.05, math.sqrt(max(0,1-x*x)))
            cross = max(0, 1-(abs(y-centerline)/(width*.95))**2)
            footprint = max(0,1-x*x-y*y)**.26
            shoulder = cross**(.55 if y<centerline else .80)
            raw.append(max(0,lerp_keys(profiles[i],x)*shoulder*footprint))
    scale = max(raw)
    for j in range(31):
        for k in range(31):
            x,y = k/30*2-1,j/30*2-1
            z = -1 + (cap+1)*raw[j*31+k]/scale
            vertices.append((cx+x*radius,cy+y*radius,z))
    for j in range(30):
        for k in range(30):
            a=j*31+k
            faces.extend([(a,a+1,a+32),(a,a+32,a+31)])
    patch = obj('Editable rocky ridge %02d'%i,vertices,faces,AUTH)
    patches.append(patch)
    offset=len(all_vertices)
    all_vertices.extend(vertices)
    all_faces.extend(tuple(offset+n for n in face) for face in faces)
    actual_min=[min(p[c] for p in vertices) for c in range(3)]
    actual_max=[max(p[c] for p in vertices) for c in range(3)]
    assert all(abs(actual_min[c]-mn[c])<1e-5 for c in [0,1])
    assert all(abs(actual_max[c]-mx[c])<1e-5 for c in [0,1])
    assert abs(actual_min[2]+1)<1e-5 and actual_max[2]<=cap+1e-5
    proofs.append({'index':i,'bounds_m':{'min':actual_min,'max':actual_max},
                   'peak_cap_m':cap,'xy_footprint_unchanged':True,'triangles':len(faces)})

mesh = obj('SM_ReleaseDistantRidges',all_vertices,all_faces,EXP)
assert len(all_faces)==7200
bpy.ops.object.select_all(action='DESELECT')
mesh.select_set(True)
bpy.context.view_layer.objects.active=mesh
file=BUILD/'meshes/SM_ReleaseDistantRidges.fbx'
bpy.ops.export_scene.fbx(filepath=str(file),use_selection=True,object_types={'MESH'},
    axis_forward='-Y',axis_up='Z',global_scale=1,apply_unit_scale=True,
    apply_scale_options='FBX_SCALE_UNITS',use_mesh_modifiers=True,add_leaf_bones=False,
    bake_anim=False,path_mode='RELATIVE',embed_textures=False,mesh_smooth_type='FACE')
AUTH.hide_render=True
AUTH.hide_viewport=True
blend=BUILD/'Release_Distant_Ridges.blend'
SC['Owner']='TOSOY.ReleaseDistantRockOwned'
SC['Preservation']='Same four source footprints/actual peak caps; no collision, actors, city, road or light'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
manifest={'schema':1,'build_stamp':STAMP,'owner':'TOSOY.ReleaseDistantRockOwned',
    'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'proposal_sha256':hashlib.sha256(PROPOSAL.read_bytes()).hexdigest(),
    'mesh_name':mesh.name,'mesh_file':str(file.relative_to(OUT)).replace('\\','/'),
    'mesh_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'triangles':7200,
    'semantic_meshes':1,'material_slots':['M_QuestDistantLand'],'collision_shapes':0,
    'blend_file':str(blend.relative_to(OUT)).replace('\\','/'),
    'blend_sha256':hashlib.sha256(blend.read_bytes()).hexdigest(),'patch_preservation':proofs,
    'bounds_m':{'min':[min(p[c] for p in all_vertices) for c in range(3)],
                'max':[max(p[c] for p in all_vertices) for c in range(3)]},
    'fbx_basis':'Same working axis/unit export options as original Quest distant-land builder; native bounds must independently match.',
    'native_imported':False,'visual_accepted':False}
text=json.dumps(manifest,indent=2)+'\n'
(BUILD/'manifest.json').write_text(text,encoding='utf-8')
(OUT/'manifest.json').write_text(text,encoding='utf-8')
print('RELEASE_DISTANT_RIDGES_BUILT',json.dumps({'manifest':str(OUT/'manifest.json'),'triangles':7200,'collision_shapes':0}),flush=True)
