"""Queued visible timber door and full stair-side enclosure; source only.

Creates one editable semantic mesh with7 explicit convex proxies matching
visible solid bodies. The closed door/return is a separate intentional new
collision scope. No existing house, character, collider or blend is opened.
Native floor/ceiling/ray/Mother-route/side-jump proof is still required.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import bpy
import bmesh

ROOT=Path(__file__).resolve().parent
if ROOT.name!='Release_20261026':raise RuntimeError('Closure authoring is restricted to the Release copy')
PLAN_FILE=ROOT/'game_unreal/ContentData/release_upstairs_closure_plan.json'
PLAN=json.loads(PLAN_FILE.read_text(encoding='utf-8'))
if hashlib.sha256((ROOT/'build_player_house.py').read_bytes()).hexdigest()!=PLAN['source_guard']['house_sha256']:
    raise RuntimeError('House source changed; review closure fit before export')
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
OUT=ROOT/'output/release_upstairs_closure'
BUILD=OUT/'builds'/STAMP
(BUILD/'meshes').mkdir(parents=True,exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
SC=bpy.context.scene
SC.name='Release visible upstairs closure - native fit pending'
SC.unit_settings.system='METRIC'
SC.unit_settings.scale_length=1
AUTH=bpy.data.collections.new('AUTHORING - editable door and real solid return')
EXP=bpy.data.collections.new('EXPORT - one render mesh')
COL=bpy.data.collections.new('COLLISION -7 matching visible body proxies')
for value in [AUTH,EXP,COL]:SC.collection.children.link(value)
M={}
for role,color in [('wood',(.20,.105,.045)),('plaster',(.61,.53,.40)),('metal',(.045,.039,.032))]:
    mat=bpy.data.materials.new('M_ReleaseClosure_'+role.title())
    mat.diffuse_color=(*color,1)
    M[role]=mat


def cm_to_blender(p):return (p[0]/100,-p[1]/100,p[2]/100)


def box(name,center,size,role,collection=AUTH,bevel_cm=0):
    vertices=[]
    for sx,sy,sz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]:
        vertices.append(cm_to_blender([center[0]+sx*size[0]/2,center[1]+sy*size[1]/2,center[2]+sz*size[2]/2]))
    data=bpy.data.meshes.new(name)
    data.from_pydata(vertices,[],[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)])
    data.update()
    value=bpy.data.objects.new(name,data)
    collection.objects.link(value)
    if role:data.materials.append(M[role])
    bm=bmesh.new();bm.from_mesh(data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free();data.update()
    uv=data.uv_layers.new(name='UV0_Metric')
    for face in data.polygons:
        axis=max(range(3),key=lambda i:abs(face.normal[i]));axes=((1,2),(0,2),(0,1))[axis]
        for li in face.loop_indices:
            p=data.vertices[data.loops[li].vertex_index].co
            uv.data[li].uv=(p[axes[0]]*.5,p[axes[1]]*.5)
    if bevel_cm:
        mod=value.modifiers.new('Restrained worn edge','BEVEL');mod.width=bevel_cm/100;mod.segments=2
    return value


sources=[];proxies=[]
for index,entry in enumerate(PLAN['blocking_visible_solids']):
    sources.append(box('Visible '+entry['id'],entry['center_ue_cm'],entry['size_ue_cm'],entry['material']))
    proxy=box('UCX_SM_ReleaseUpstairsClosure_%02d'%index,entry['center_ue_cm'],entry['size_ue_cm'],None,COL)
    proxy.hide_render=True;proxy.display_type='WIRE';proxies.append(proxy)

# Front face shows real plank seams against its solid timber backing.
for i in range(8):
    sources.append(box('Door vertical board %02d'%i,[-508.9,1515+(i+.5)*17.5,1123],[1.2,17.1,223.4],'wood',bevel_cm=.2))
for z in [1050,1203]:sources.append(box('Door reinforcing rail',[-507.8,1585,z],[1.2,138,8],'wood',bevel_cm=.25))
sources.append(box('Visible iron latch backplate',[-506.7,1545,1120],[1,5,14],'metal',bevel_cm=.2))
sources.append(box('Visible iron latch handle',[-504.5,1545,1120],[3.5,2,3],'metal',bevel_cm=.2))
# One continuous visible plaster return with coherent oak studs/caps, not
# invisible collision geometry or isolated bands that can be walked around.
for x in [-1052,-963,-850,-738,-626,-514]:sources.append(box('Return visible timber stud',[x,1503,1156.5],[9,15,291],'wood',bevel_cm=.25))
for z in [1016,1297]:sources.append(box('Return visible timber cap',[-784,1503,z],[544,15,10],'wood',bevel_cm=.25))
sources.append(box('North infill visible end post',[-512,1701.5,1156.5],[15,9,291],'wood',bevel_cm=.25))

copies=[]
for source in sources:
    value=source.copy();value.data=source.data.copy();EXP.objects.link(value)
    bpy.ops.object.select_all(action='DESELECT');value.select_set(True);bpy.context.view_layer.objects.active=value
    for mod in list(value.modifiers):bpy.ops.object.modifier_apply(modifier=mod.name)
    copies.append(value)
bpy.ops.object.select_all(action='DESELECT')
for value in copies:value.select_set(True)
bpy.context.view_layer.objects.active=copies[0]
bpy.ops.object.join()
mesh=bpy.context.object
mesh.name='SM_ReleaseUpstairsClosure'
bm=bmesh.new();bm.from_mesh(mesh.data);bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.to_mesh(mesh.data);bm.free();mesh.data.update()
triangles=len(mesh.data.polygons)
assert triangles<=PLAN['design']['triangles_cap'] and len(proxies)==7
for value in proxies:value.select_set(True)
file=BUILD/'meshes/SM_ReleaseUpstairsClosure.fbx'
bpy.ops.export_scene.fbx(filepath=str(file),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',
    global_scale=1,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',use_mesh_modifiers=True,
    add_leaf_bones=False,bake_anim=False,path_mode='RELATIVE',embed_textures=False,mesh_smooth_type='FACE')
AUTH.hide_render=True;AUTH.hide_viewport=True
SC['Owner']=PLAN['owner']
SC['Intentional new collision scope']='Door/visible return only; not part of floor material no-collision claims'
SC['Native proof']='Pending actual floor/ceiling fit, Mother bounds/routes,20 rays, normal exit walking, both-side/jump/crouch bypass'
blend=BUILD/'Release_Upstairs_Closure.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
manifest={'schema':1,'build_stamp':STAMP,'owner':PLAN['owner'],'stable_id':PLAN['stable_id'],
    'plan_sha256':hashlib.sha256(PLAN_FILE.read_bytes()).hexdigest(),
    'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'file':str(file.relative_to(OUT)).replace('\\','/'),'file_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
    'blend_file':str(blend.relative_to(OUT)).replace('\\','/'),'blend_sha256':hashlib.sha256(blend.read_bytes()).hexdigest(),
    'mesh_name':mesh.name,'triangles':triangles,'materials':[m.name for m in mesh.data.materials],
    'semantic_meshes':1,'ucx_boxes':7,'collision_matches_visible_solid_bodies':True,
    'collision_body_specs_ue_cm':PLAN['blocking_visible_solids'],'origin_actor_ue_cm':[0,0,0],
    'native_unit_and_fit_proven':False,'side_or_jump_bypass_proven':False,'native_mother_ray_or_walking_proven':False,
    'native_imported':False,'closure_applied':False,'visual_accepted':False}
text=json.dumps(manifest,indent=2)+'\n'
(BUILD/'manifest.json').write_text(text,encoding='utf-8');(OUT/'manifest.json').write_text(text,encoding='utf-8')
print('RELEASE_UPSTAIRS_CLOSURE_BUILT',json.dumps({'manifest':str(OUT/'manifest.json'),'triangles':triangles,'ucx_boxes':7}),flush=True)
