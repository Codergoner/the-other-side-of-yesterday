"""Small, opaque, metric Verdant street-room kit for Quest. Blender background only.

Writes a fresh versioned output; never opens the city or changes old assets.
All visible components remain editable in the saved .blend. Native importer uses
semantic batches and simple named collision, not one actor per plank or leaf.
"""
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
import bpy, bmesh, math, json, hashlib
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
if not (ROOT / 'quest_baseline_manifest.json').exists():
    raise RuntimeError('Run only from the protected Quest development copy')
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
OUT = ROOT / 'output' / 'quest_district'
BUILD = OUT / 'builds' / STAMP
(BUILD / 'meshes').mkdir(parents=True, exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
SC = bpy.context.scene
SC.name = 'Verdant · human scale street rooms'
SC.unit_settings.system = 'METRIC'
SC.unit_settings.scale_length = 1
SRC = bpy.data.collections.new('AUTHORING · editable components')
EXP = bpy.data.collections.new('GAME · semantic batches')
COL = bpy.data.collections.new('COLLISION · convex proxies')
for collection in (SRC, EXP, COL): SC.collection.children.link(collection)
PARTS, PROXIES = defaultdict(list), defaultdict(list)
DEFS = {
    'Wood': {'rgb': [114, 79, 47], 'roughness': .82},
    'Stone': {'rgb': [181, 165, 133], 'roughness': .9},
    'Cream': {'rgb': [224, 208, 167], 'roughness': .9},
    'Teal': {'rgb': [42, 85, 79], 'roughness': .85},
    'Leaf': {'rgb': [67, 99, 48], 'roughness': .9},
}
M = {}
for key, definition in DEFS.items():
    definition['name'] = 'M_QuestDistrict_' + key
    material = bpy.data.materials.new(definition['name'])
    material.use_nodes = True
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*(c / 255 for c in definition['rgb']), 1)
    shader.inputs['Roughness'].default_value = definition['roughness']
    M[key] = material

BOXF = [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
def mesh(group, label, verts, faces, key='Wood', smooth=False):
    data = bpy.data.meshes.new(label)
    data.from_pydata(verts, [], faces); data.update(); data.materials.append(M[key])
    uv = data.uv_layers.new(name='UV0_Metric')
    for face in data.polygons:
        face.use_smooth = smooth
        axis = max(range(3), key=lambda i: abs(face.normal[i]))
        axes = ((1,2),(0,2),(0,1))[axis]
        for li in face.loop_indices:
            co = data.vertices[data.loops[li].vertex_index].co
            uv.data[li].uv = (co[axes[0]], co[axes[1]])
    obj = bpy.data.objects.new(label, data); SRC.objects.link(obj); PARTS[group].append(obj)
    return obj

def box_vertices(at, size):
    c, h = Vector(at), Vector(size) * .5
    return [c+Vector((x*h.x,y*h.y,z*h.z)) for x,y,z in
            [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]

def proxy(group, at, size, slope=0):
    vv = box_vertices(at, size)
    for v in vv: v.z += slope * v.x
    data = bpy.data.meshes.new('convex collision'); data.from_pydata(vv, [], BOXF); data.update()
    obj = bpy.data.objects.new('UCX_' + group + '_' + str(len(PROXIES[group])).zfill(3), data)
    COL.objects.link(obj); obj.hide_render = True; PROXIES[group].append(obj)

def box(group, label, at, size, key='Wood', bevel=.008, block=False, slope=0):
    vv = box_vertices(at, size)
    for v in vv: v.z += slope * v.x
    obj = mesh(group, label, vv, BOXF, key)
    if bevel:
        modifier = obj.modifiers.new('Subtle edge wear', 'BEVEL')
        modifier.width = min(bevel, min(size) * .12); modifier.segments = 1
    if block: proxy(group, at, size, slope)
    return obj

def beam(group, label, start, end, width=.06, key='Wood'):
    a, b = Vector(start), Vector(end); direction = b-a
    rotation = direction.to_track_quat('Z','Y').to_matrix()
    vv = [(a+b)*.5 + rotation@v for v in box_vertices((0,0,0),(width,width,direction.length))]
    return mesh(group, label, vv, BOXF, key)

def ellipsoid(group, label, at, radii, key='Leaf', n=12, rings=6):
    c = Vector(at); vv=[]
    for j in range(rings+1):
        p = math.pi*j/rings
        for i in range(n):
            a = math.tau*i/n
            vv.append(c+Vector((math.sin(p)*math.cos(a)*radii[0],math.sin(p)*math.sin(a)*radii[1],math.cos(p)*radii[2])))
    ff=[(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i) for j in range(rings) for i in range(n)]
    return mesh(group,label,vv,ff,key,True)

def text(group, body, at, size=.15, key='Cream'):
    curve = bpy.data.curves.new('Carved readable '+body, 'FONT')
    curve.body=body; curve.align_x='CENTER'; curve.align_y='CENTER'
    curve.size=size; curve.extrude=.0015; curve.resolution_u=1; curve.bevel_depth=0
    obj=bpy.data.objects.new('Lettering · '+body,curve);SRC.objects.link(obj)
    obj.location=at;obj.rotation_euler=(math.pi/2,0,0);curve.materials.append(M[key])
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    bpy.ops.object.convert(target='MESH');PARTS[group].append(bpy.context.object)

# Seat height 46 cm, shallow 52 cm footprint. Front faces Blender -Y.
g='SM_QuestDistrict_Bench'
for x in (-.67,.67):
    box(g,'Stone footing',(x,0,.13),(.21,.52,.26),'Stone',block=True)
    box(g,'Oak support',(x,0,.31),(.115,.42,.34),block=True)
    box(g,'Back upright',(x,.205,.72),(.08,.08,.72))
for y in (-.18,-.06,.06,.18): box(g,'Individual seat plank',(0,y,.435),(1.72,.108,.05))
for z in (.66,.82): box(g,'Back plank',(0,.205,z),(1.72,.05,.12))
proxy(g,(0,0,.43),(1.74,.52,.10));proxy(g,(0,.205,.72),(1.74,.10,.46))
# Street bench keeps a level seat while its two stone feet meet the graded road.
street='SM_QuestDistrict_BenchStreet'
for source in list(PARTS[g]):
    copy=source.copy();copy.data=source.data.copy();SRC.objects.link(copy);PARTS[street].append(copy)
    if source.name.startswith('Stone footing'):
        for vertex in copy.data.vertices:
            if vertex.co.z<.01:vertex.co.z+=.1*vertex.co.x
for source in list(PROXIES[g]):
    copy=source.copy();copy.data=source.data.copy();copy.name='UCX_'+street+'_'+str(len(PROXIES[street])).zfill(3)
    COL.objects.link(copy);PROXIES[street].append(copy)
    for vertex in copy.data.vertices:
        if vertex.co.z<.01:vertex.co.z+=.1*vertex.co.x

# Four instances fill the excess opening only. Integral 10% grade matches road.
g='SM_QuestDistrict_ShoreReturn130'
box(g,'Continuous stone toe',(0,0,.17),(1.30,.32,.34),'Stone',block=True,slope=.1)
for x in (-.59,0,.59): box(g,'Upright guard post',(x,0,.67+.1*x),(.095,.12,1.0),block=True)
for z in (.62,1.10): box(g,'Continuous timber guard rail',(0,0,z),(1.30,.10,.10),block=True,slope=.1)
# Solid query proxy prevents squeezing between decorative rails near the cliff.
proxy(g,(0,0,.62),(1.30,.12,1.12),slope=.1)

# Direction signs are real opaque geometry; no text rendering dependency at runtime.
for title, subline in [('Clinic','QUIET COURT'),('Market','COVERED ARCADE'),('Harbor','STAIRS / OVERLOOK')]:
    g='SM_QuestDistrict_Sign'+title
    box(g,'Stone sign footing',(0,0,.09),(.28,.28,.18),'Stone',block=True)
    box(g,'Hand carved timber post',(0,0,.92),(.095,.095,1.68),block=True)
    box(g,'Painted board',(0,-.035,1.62),(1.10,.065,.43),'Teal',.015)
    for z in (1.415,1.825): box(g,'Framed board edge',(0,-.075,z),(1.12,.035,.025),'Wood',.002)
    text(g,title.upper(),(0,-.073,1.68),.19)
    text(g,subline,(0,-.075,1.51),.057)

g='SM_QuestDistrict_PottedTree'
# Ringed stone container, low trunk and intentionally opaque sculpted leaf masses.
for i in range(12):
    a=math.tau*i/12;b=math.tau*(i+1)/12
    vv=[(.30*math.cos(a),.30*math.sin(a),0),(.30*math.cos(b),.30*math.sin(b),0),(.38*math.cos(b),.38*math.sin(b),.48),(.38*math.cos(a),.38*math.sin(a),.48)]
    mesh(g,'Tapered stone planter',vv,[(0,1,2,3)],'Stone')
box(g,'Planter interior soil',(0,0,.40),(.49,.49,.06),'Wood',0)
proxy(g,(0,0,.24),(.66,.66,.48))
beam(g,'Single visible trunk',(0,0,.40),(.035,0,1.65),.095)
for x,y,z,rx,ry,rz in [(-.15,0,1.80,.44,.39,.51),(.18,.10,2.06,.42,.41,.55),(-.02,-.13,2.40,.37,.32,.47),(.03,.02,2.68,.25,.24,.35)]:
    beam(g,'Visible branch',(.02,0,1.45),(x,y,z),.045)
    ellipsoid(g,'Broad opaque crown',(x,y,z),(rx,ry,rz))

g='SM_QuestDistrict_ArcadeTable'
for x in (-.58,.58):
    for y in (-.25,.25):box(g,'Table leg',(x,y,.37),(.075,.075,.74),block=True)
for y in (-.30,-.15,0,.15,.30):box(g,'Tabletop plank',(0,y,.76),(1.44,.14,.065))
proxy(g,(0,0,.76),(1.46,.76,.09))
box(g,'Stretcher',(0,0,.24),(1.24,.075,.075))

g='SM_QuestDistrict_ArcadeShelf'
for x in (-.68,.68):box(g,'Shelf upright',(x,.08,.87),(.085,.12,1.74),block=True)
for z in (.12,.65,1.18,1.71):box(g,'Shelf board',(0,0,z),(1.48,.42,.065),block=True)
for x in (-.4,0,.4):box(g,'Plain folded stores',(x,-.01,1.28),(.28,.29,.14),'Cream')

g='SM_QuestDistrict_Threshold'
# 120cm long stone threshold bridges the lower foundation strip, rising 10cm
# from the street to the existing arcade slab. Bottom reaches the -12cm bedrock.
vv=[(-1,-.60,-.12),(1,-.60,-.12),(1,.60,-.12),(-1,.60,-.12),(-1,-.60,.10),(1,-.60,.10),(1,.60,0),(-1,.60,0)]
mesh(g,'Single stone threshold bevel',vv,BOXF,'Stone')
data=bpy.data.meshes.new('Threshold convex collision');data.from_pydata(vv,[],BOXF);data.update()
obj=bpy.data.objects.new('UCX_'+g+'_000',data);COL.objects.link(obj);PROXIES[g].append(obj)

# Modest in-world stone landing medallions, ray hittable without emissive rings.
# Sloped variant follows the original 10% street; flat variant is for real slabs.
for suffix, grade in [('Flat',0),('Street',.1)]:
    g='SM_QuestDistrict_Landing'+suffix
    vv=[];n=16
    for radius,z in [(.32,-.018),(.32,.012),(.245,.012)]:
        vv.extend((radius*math.cos(i*math.tau/n),radius*math.sin(i*math.tau/n),z+grade*radius*math.cos(i*math.tau/n)) for i in range(n))
    mesh(g,'Subtle stone landing disc',vv,[(i,(i+1)%n,n+(i+1)%n,n+i) for i in range(n)]+[(n+i,n+(i+1)%n,2*n+(i+1)%n,2*n+i) for i in range(n)],'Stone')
    mesh(g,'Painted teal landing center',vv[2*n:],[tuple(range(n))],'Teal')
    proxy(g,(0,0,-.003),(.61,.61,.03),slope=grade)

bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();assets=[]
for group,objects in PARTS.items():
    vv=[];ff=[];uvs=[];face_mats=[];materials=[]
    for obj in objects:
        ev=obj.evaluated_get(deps);data=ev.to_mesh(preserve_all_data_layers=True,depsgraph=deps)
        offset=len(vv);vv.extend(obj.matrix_world@v.co for v in data.vertices);layer=data.uv_layers.active;remap=[]
        for mat in data.materials:
            mat=mat.original if getattr(mat,'is_evaluated',False) else mat
            if mat not in materials:materials.append(mat)
            remap.append(materials.index(mat))
        for face in data.polygons:
            ff.append(tuple(offset+data.loops[li].vertex_index for li in face.loop_indices))
            uvs.extend(tuple(layer.data[li].uv) if layer else (0,0) for li in face.loop_indices)
            face_mats.append(remap[face.material_index])
        ev.to_mesh_clear()
    data=bpy.data.meshes.new(group);data.from_pydata(vv,[],ff);data.update()
    obj=bpy.data.objects.new(group,data);EXP.objects.link(obj)
    for mat in materials:data.materials.append(mat)
    layer=data.uv_layers.new(name='UV0_Metric')
    for i,p in enumerate(uvs):layer.data[i].uv=p
    for face,mi in zip(data.polygons,face_mats):face.material_index=mi
    bm=bmesh.new();bm.from_mesh(data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
    bmesh.ops.triangulate(bm,faces=list(bm.faces));bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free();data.update()
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    for collider in PROXIES[group]:collider.select_set(True)
    file=BUILD/'meshes'/f'{group}.fbx'
    bpy.ops.export_scene.fbx(filepath=str(file),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',global_scale=1,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',use_mesh_modifiers=True,add_leaf_bones=False,bake_anim=False,path_mode='RELATIVE',embed_textures=False,mesh_smooth_type='FACE')
    assets.append({'name':group,'file':str(file.relative_to(OUT)).replace('\\','/'),'materials':[m.name for m in materials],'triangles':len(data.polygons),'collision_count':len(PROXIES[group]),'bounds_m':{'min':[min(v.co[i] for v in data.vertices) for i in range(3)],'max':[max(v.co[i] for v in data.vertices) for i in range(3)]}})
    print('QUEST_DISTRICT_MESH',group,len(data.polygons),flush=True)
total=sum(a['triangles'] for a in assets)
if total>20000:raise RuntimeError('District unique-geometry budget exceeded: '+str(total))
SRC.hide_render=True;SRC.hide_viewport=True;COL.hide_render=True;COL.hide_viewport=True
SC['Scope']='Additive Verdant street rooms, not a whole city';SC['BuildStamp']=STAMP
readme=bpy.data.texts.new('READ ME · Quest district kit')
readme.write('Meters. Front=-Y. Opaque crowns; no foliage cards or per-leaf actors. Every semantic mesh has its own named simple proxies. New kit only; original city was never opened. Native floor/capsule/teleport validation is separate.\n')
bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'Verdant_Quest_District_Kit.blend'))
manifest={'schema_version':1,'name':'Verdant Quest street-room kit','build_stamp':STAMP,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'units':'meters','axes':'Blender X,Y,Z -> Unreal X,-Y,Z; default yaw -90 faces street +X','assets':assets,'material_definitions':{v['name']:v for v in DEFS.values()},'blend_file':str((BUILD/'Verdant_Quest_District_Kit.blend').relative_to(OUT)).replace('\\','/'),'triangles':total,'notes':['All new opaque semantic assets; five shared materials.','Unique geometry budget <=20000 triangles; instance and draw costs are measured separately.','Floor positions, shore clearance and interaction require native validation.']}
(BUILD/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('QUEST_DISTRICT_COMPLETE',json.dumps({'assets':len(assets),'triangles':total,'manifest':str(OUT/'manifest.json')}),flush=True)
