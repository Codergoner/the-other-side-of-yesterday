"""Stage an organic opaque olive tree; never imports into Unreal or edits maps.

Run only in the root-granted Blender queue. The existing FBX is a read-only
source for the exact pot/soil and convex collision. All new branches and closed
3D leaves remain inside the original asset's maximum bounds. No alpha materials.
"""
from pathlib import Path
from datetime import datetime, timezone
import bpy,bmesh,math,random,json,hashlib
from mathutils import Vector

ROOT=Path(__file__).resolve().parent
if not (ROOT/'quest_baseline_manifest.json').exists():raise RuntimeError('Protected Quest copy only')
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
OUT=ROOT/'output'/'premium_foliage';BUILD=OUT/'builds'/STAMP
for path in [BUILD/'meshes',BUILD/'previews']:path.mkdir(parents=True,exist_ok=False)
REFERENCE_ROOT=ROOT/'output'/'quest_district'
REFERENCE=json.loads((REFERENCE_ROOT/'manifest.json').read_text(encoding='utf-8'))
ENTRY=next(a for a in REFERENCE['assets'] if a['name']=='SM_QuestDistrict_PottedTree')
REFERENCE_FBX=REFERENCE_ROOT/ENTRY['file']
NAME='SM_QuestPremium_PottedOlive'
R=random.Random(251031)
bpy.ops.wm.read_factory_settings(use_empty=True)
SC=bpy.context.scene;SC.name='EDIT · opaque Mediterranean olive'
SC.unit_settings.system='METRIC';SC.unit_settings.scale_length=1
bpy.ops.import_scene.fbx(filepath=str(REFERENCE_FBX))
imported=list(bpy.context.selected_objects)
old=next(o for o in imported if o.type=='MESH' and not o.name.startswith(('UCX_','UBX_')))
old_proxy=next(o for o in imported if o.type=='MESH' and o.name.startswith(('UCX_','UBX_')))

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def q(value):
    value=round(float(value),6)
    return 0.0 if value==0 else value
def vector_hash(vertices):
    values=sorted(set(tuple(q(v[i]) for i in range(3)) for v in vertices))
    return hashlib.sha256(json.dumps(values,separators=(',',':')).encode()).hexdigest()
def world_vertices(obj):return [obj.matrix_world@v.co for v in obj.data.vertices]
def bounds(vertices):return {'min':[min(v[i] for v in vertices) for i in range(3)],'max':[max(v[i] for v in vertices) for i in range(3)]}
def pot_surface_hash(obj):
    rows=[];uv=obj.data.uv_layers.active
    for face in obj.data.polygons:
        material=obj.data.materials[face.material_index].name
        vv=[obj.matrix_world@obj.data.vertices[obj.data.loops[li].vertex_index].co for li in face.loop_indices]
        stone=material=='M_QuestDistrict_Stone'
        soil=material=='M_QuestDistrict_Wood' and all(min(abs(v.z-.37),abs(v.z-.43))<1e-5 for v in vv)
        if not (stone or soil):continue
        corners=[]
        for li,v in zip(face.loop_indices,vv):
            corners.append(tuple(q(v[i]) for i in range(3))+tuple(q(uv.data[li].uv[i]) for i in range(2)))
        rows.append((material,sorted(corners)))
    return hashlib.sha256(json.dumps(sorted(rows),separators=(',',':')).encode()).hexdigest(),len(rows)

old_bounds=bounds(world_vertices(old));expected=ENTRY['bounds_m']
if any(abs(old_bounds[k][i]-expected[k][i])>1e-4 for k in ['min','max'] for i in range(3)):
    raise RuntimeError('Reference FBX units/axes do not match the existing asset')
M={}
for key in ['Stone','Wood','Leaf']:
    name='M_QuestDistrict_'+key
    mat=bpy.data.materials.get(name)
    if mat is None:raise RuntimeError('Missing existing material '+name)
    definition=REFERENCE['material_definitions'][name]
    mat.use_nodes=True;shader=mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(*(c/255 for c in definition['rgb']),1)
    shader.inputs['Roughness'].default_value=definition['roughness'];M[key]=mat

SRC=bpy.data.collections.new('AUTHORING · editable stems and leaf shoots');SC.collection.children.link(SRC)
GAME=bpy.data.collections.new('GAME · one semantic mesh and original collision');SC.collection.children.link(GAME)
REF=bpy.data.collections.new('REFERENCE · original mesh read only');SC.collection.children.link(REF)
for obj in imported:
    for collection in list(obj.users_collection):collection.objects.unlink(obj)
    REF.objects.link(obj);obj.hide_render=True;obj.hide_set(True)
REF.hide_render=True;REF.hide_viewport=True
PARTS=[]

def mesh(label,verts,faces,key='Wood',smooth=False,uvs=None):
    data=bpy.data.meshes.new(label);data.from_pydata(verts,[],faces);data.update()
    data.materials.append(M[key]);layer=data.uv_layers.new(name='UV0_Metric')
    for face in data.polygons:
        face.use_smooth=smooth
        axis=max(range(3),key=lambda i:abs(face.normal[i]));axes=((1,2),(0,2),(0,1))[axis]
        for li in face.loop_indices:
            co=data.vertices[data.loops[li].vertex_index].co
            layer.data[li].uv=uvs[li] if uvs else (co[axes[0]],co[axes[1]])
    obj=bpy.data.objects.new(label,data);SRC.objects.link(obj);PARTS.append(obj);return obj

# Copy the pot triangles and soil surface directly from the original imported
# semantic mesh, including coordinates, material assignment and UVs.
base_vertices=[];base_faces=[];base_materials=[];base_uvs=[]
old_uv=old.data.uv_layers.active
for face in old.data.polygons:
    material=old.data.materials[face.material_index].name
    vv=[old.matrix_world@old.data.vertices[old.data.loops[li].vertex_index].co for li in face.loop_indices]
    stone=material=='M_QuestDistrict_Stone'
    soil=material=='M_QuestDistrict_Wood' and all(min(abs(v.z-.37),abs(v.z-.43))<1e-5 for v in vv)
    if not (stone or soil):continue
    offset=len(base_vertices);base_vertices.extend(vv);base_faces.append(tuple(range(offset,offset+len(vv))))
    base_materials.append('Stone' if stone else 'Wood')
    base_uvs.extend(tuple(old_uv.data[li].uv) if old_uv else (0,0) for li in face.loop_indices)
if len(base_faces)!=36:raise RuntimeError('Exact original pot+soil selection did not contain36 triangles')
pot=mesh('Original pot and soil · exact copied vertices',base_vertices,base_faces,'Stone',uvs=base_uvs)
pot.data.materials.append(M['Wood'])
for face,key in zip(pot.data.polygons,base_materials):face.material_index=0 if key=='Stone' else 1
base_hash=vector_hash(base_vertices)

def branch(label,points,radii,n=6):
    vv=[]
    for j,point in enumerate(points):
        p=Vector(point)
        direction=Vector(points[min(j+1,len(points)-1)])-Vector(points[max(0,j-1)])
        rotation=direction.to_track_quat('Z','Y').to_matrix()
        for i in range(n):
            angle=i*math.tau/n
            vv.append(p+rotation@Vector((radii[j]*math.cos(angle),radii[j]*math.sin(angle),0)))
    ff=[tuple(reversed(range(n))),tuple((len(points)-1)*n+i for i in range(n))]
    ff.extend((j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i) for j in range(len(points)-1) for i in range(n))
    return mesh(label,vv,ff,'Wood',True)

def leaf(vv,ff,base,direction,length,width,normal):
    base=Vector(base);d=Vector(direction).normalized();normal=Vector(normal)
    normal=(normal-d*normal.dot(d)).normalized();side=d.cross(normal).normalized()
    mid=base+d*(length*.46);offset=len(vv)
    # Closed thin lanceolate tetrahedron: four vertices/four triangles, no
    # two-sided planes, transparency, masked edges or duplicated backfaces.
    vv.extend([base,base+d*length,mid-side*width*.5+normal*.0022,mid+side*width*.5-normal*.0018])
    ff.extend(tuple(offset+i for i in face) for face in [(0,2,3),(1,3,2),(0,1,2),(0,3,1)])

branch('Gently twisting main olive trunk',[(0,0,.40),(-.018,.012,.70),(.012,.018,.98),(.025,-.01,1.22),(-.005,.012,1.48)],[.038,.035,.030,.024,.012],7)
primaries=[
    [(-.005,.012,1.12),(-.16,-.015,1.42),(-.31,-.025,1.66),(-.40,-.02,1.95)],
    [(.02,0,1.27),(.12,.04,1.58),(.24,.055,1.93),(.31,.075,2.21)],
    [(.018,0,1.36),(.005,-.13,1.70),(-.12,-.23,2.11),(-.18,-.22,2.48)],
    [(-.005,.012,1.45),(.025,.14,1.79),(.055,.24,2.17),(.10,.26,2.55)],
    [(.005,.005,1.35),(-.035,.015,1.77),(-.015,.03,2.27),(-.04,.035,2.88)],
]
leaf_count=0
for primary_index,points in enumerate(primaries):
    branch('Asymmetric primary branch '+str(primary_index+1),points,[.022,.017,.011,.004],6)
    # Four offset terminal shoots per primary, with paired alternate leaves.
    for shoot_index in range(4):
        t=.35+.19*shoot_index;segment=1 if t<.67 else 2;u=(t-.33)/.34 if segment==1 else (t-.67)/.33
        u=max(0,min(1,u));root=Vector(points[segment]).lerp(Vector(points[segment+1]),u)
        angle=(primary_index*1.67+shoot_index*2.13)+R.uniform(-.20,.20)
        spread=.18+R.uniform(.025,.080)
        tip=root+Vector((math.cos(angle)*spread,math.sin(angle)*spread,.08+R.uniform(.02,.09)))
        tip.x=max(-.43,min(.43,tip.x));tip.y=max(-.31,min(.36,tip.y));tip.z=min(2.93,tip.z)
        middle=root.lerp(tip,.5)+Vector((.014*math.sin(angle),.014*math.cos(angle),.018))
        shoot=[root,middle,tip]
        branch('Fine woody leaf shoot '+str(primary_index+1)+'.'+str(shoot_index+1),shoot,[.0055,.0031,.0008],4)
        vv=[];ff=[];axis=(tip-root).normalized();side=Vector((math.cos(angle+.7),math.sin(angle+.7),.14)).normalized()
        for pair in range(17):
            t=(pair+.35)/17
            at=root.lerp(middle,t*2) if t<.5 else middle.lerp(tip,(t-.5)*2)
            for sign in (-1,1):
                direction=(side*sign+axis*.40+Vector((0,0,R.uniform(-.15,.35)))).normalized()
                normal=Vector((R.uniform(-.9,.9),R.uniform(-.9,.9),R.uniform(.2,.8)))
                leaf(vv,ff,at,direction,R.uniform(.115,.155),R.uniform(.036,.052),normal);leaf_count+=1
        mesh('Opaque olive leaves '+str(primary_index+1)+'.'+str(shoot_index+1),vv,ff,'Leaf')

# Strict bounds guard: only new woody/leaf parts may be constrained. The pot and
# copied collision are never transformed or scaled to make them fit.
for obj in PARTS:
    if obj==pot:continue
    for vertex in obj.data.vertices:
        for i in range(3):
            vertex.co[i]=max(expected['min'][i]+.005,min(expected['max'][i]-.005,vertex.co[i]))

# Merge semantic game mesh while retaining all separate authoring components.
bpy.context.view_layer.update();vv=[];ff=[];uvs=[];face_mats=[];face_smooth=[];materials=[]
for obj in PARTS:
    data=obj.data;offset=len(vv);vv.extend(obj.matrix_world@v.co for v in data.vertices);layer=data.uv_layers.active;remap=[]
    for mat in data.materials:
        if mat not in materials:materials.append(mat)
        remap.append(materials.index(mat))
    for face in data.polygons:
        ff.append(tuple(offset+data.loops[li].vertex_index for li in face.loop_indices))
        uvs.extend(tuple(layer.data[li].uv) for li in face.loop_indices);face_mats.append(remap[face.material_index]);face_smooth.append(face.use_smooth)
data=bpy.data.meshes.new(NAME);data.from_pydata(vv,[],ff);data.update();tree=bpy.data.objects.new(NAME,data);GAME.objects.link(tree)
for mat in materials:data.materials.append(mat)
layer=data.uv_layers.new(name='UV0_Metric')
for i,uv in enumerate(uvs):layer.data[i].uv=uv
for face,mi,smooth in zip(data.polygons,face_mats,face_smooth):face.material_index=mi;face.use_smooth=smooth
bm=bmesh.new();bm.from_mesh(data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000001)
bmesh.ops.triangulate(bm,faces=list(bm.faces));bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free();data.update()
triangles=len(data.polygons)
if triangles>3500:raise RuntimeError('Premium foliage exceeds3500tri budget: '+str(triangles))
proxy_data=bpy.data.meshes.new('Original convex footprint · copied without modification')
old_collision=world_vertices(old_proxy)
proxy_data.from_pydata(old_collision,[],[tuple(face.vertices) for face in old_proxy.data.polygons]);proxy_data.update()
proxy=bpy.data.objects.new('UCX_'+NAME+'_000',proxy_data);GAME.objects.link(proxy);proxy.hide_render=True
collision_hash=vector_hash(world_vertices(proxy))
if collision_hash!=vector_hash(old_collision):raise RuntimeError('Copied collision changed')
if vector_hash(world_vertices(pot))!=base_hash:raise RuntimeError('Original pot+soil geometry changed')
surface_before,pot_tri_before=pot_surface_hash(old);surface_after,pot_tri_after=pot_surface_hash(tree)
if surface_before!=surface_after or pot_tri_before!=36 or pot_tri_after!=36:
    raise RuntimeError('Final semantic mesh changed original pot/soil triangles, material IDs or UVs')
new_bounds=bounds(world_vertices(tree))
if any(new_bounds['min'][i]<expected['min'][i]-1e-5 or new_bounds['max'][i]>expected['max'][i]+1e-5 for i in range(3)):
    raise RuntimeError('New tree exceeds original maximum bounds')
bpy.ops.object.select_all(action='DESELECT');tree.select_set(True);proxy.select_set(True);bpy.context.view_layer.objects.active=tree
fbx=BUILD/'meshes'/(NAME+'.fbx')
bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',global_scale=1,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',use_mesh_modifiers=True,add_leaf_bones=False,bake_anim=False,path_mode='RELATIVE',embed_textures=False,mesh_smooth_type='FACE')
SRC.hide_viewport=True;SRC.hide_render=True;proxy.hide_set(True)

# Same illumination / camera comparison; materials are identical on old/new.
compare=bpy.data.scenes.new('PREVIEW · old topiary versus opaque olive')
compare.unit_settings.system='METRIC';compare.unit_settings.scale_length=1
compare.render.engine='CYCLES';compare.cycles.device='CPU';compare.cycles.samples=24
compare.cycles.use_denoising=True;compare.render.resolution_x=1600;compare.render.resolution_y=1000;compare.render.resolution_percentage=100
compare.world=bpy.data.worlds.new('Neutral soft outdoor preview');compare.world.use_nodes=True
compare.world.node_tree.nodes['Background'].inputs[0].default_value=(.52,.65,.82,1)
compare.world.node_tree.nodes['Background'].inputs[1].default_value=.35
for source,x in [(old,-.90),(tree,.90)]:
    clone=source.copy();clone.data=source.data;compare.collection.objects.link(clone);clone.hide_render=False;clone.hide_viewport=False
    clone.location.x+=x
ground_material=bpy.data.materials.new('PREVIEW ONLY · warm stone floor');ground_material.diffuse_color=(.32,.30,.25,1)
ground_data=bpy.data.meshes.new('preview floor');ground_data.from_pydata([(-200,-200,-.002),(200,-200,-.002),(200,200,-.002),(-200,200,-.002)],[],[(0,1,2,3)]);ground_data.materials.append(ground_material)
ground=bpy.data.objects.new('PREVIEW ONLY ground',ground_data);compare.collection.objects.link(ground)
def light(name,at,energy,size,color):
    data=bpy.data.lights.new(name,'AREA');data.energy=energy;data.shape='DISK';data.size=size;data.color=color
    obj=bpy.data.objects.new(name,data);compare.collection.objects.link(obj);obj.location=at
    obj.rotation_euler=(Vector((0,0,1.3))-obj.location).to_track_quat('-Z','Y').to_euler()
light('Warm open-sky key',(3,-4,6),850,4,(1,.83,.64));light('Cool soft fill',(-4,-1,4),500,5,(.66,.79,1));light('Sunlit leaf rim',(1,4,5),950,3,(1,.91,.75))
camera_data=bpy.data.cameras.new('Comparison camera');camera=bpy.data.objects.new('Comparison camera',camera_data);compare.collection.objects.link(camera)
camera.location=(5,-9,4.0);camera.rotation_euler=(Vector((0,0,1.5))-camera.location).to_track_quat('-Z','Y').to_euler();camera_data.type='ORTHO';camera_data.ortho_scale=5.2;compare.camera=camera
compare.render.image_settings.file_format='PNG';compare.render.filepath=str(BUILD/'previews'/'Olive_Old_Left_New_Right.png')
bpy.ops.render.render(write_still=True,scene=compare.name)
camera.location=(3.7,-6.0,3.0);camera.rotation_euler=(Vector((.90,0,1.55))-camera.location).to_track_quat('-Z','Y').to_euler();camera_data.ortho_scale=3.6
compare.render.resolution_x=1100;compare.render.resolution_y=1200;compare.render.filepath=str(BUILD/'previews'/'Olive_Detail.png')
# Hide old only in the second render, retaining it in the comparison scene.
for obj in compare.objects:
    if obj.type=='MESH' and obj.data==old.data:obj.hide_render=True
bpy.ops.render.render(write_still=True,scene=compare.name)
bpy.context.window.scene=SC
SC['Scope']='Staged foliage source only; no Unreal import, actor or scale changes';SC['BuildStamp']=STAMP
readme=bpy.data.texts.new('READ ME · premium opaque foliage')
readme.write('One semantic game mesh; edit individual woody shoots/leaves in AUTHORING. Existing pot/soil is copied exactly. UCX collision is copied exactly. Three existing opaque materials. Original actor IDs, locations and courtyard scale0.65 must remain unchanged on any later approved import. Old/New preview uses identical materials and illumination; not a device capture.\n')
blend=BUILD/'Verdant_Opaque_Olive_Source.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
manifest={'schema_version':1,'build_stamp':STAMP,'scope':'Staged Blender art only; no Unreal imports or map edits','source_sha256':digest(Path(__file__)),'reference_fbx':str(REFERENCE_FBX),'reference_fbx_sha256':digest(REFERENCE_FBX),
 'assets':[{'name':NAME,'replacement_for':'SM_QuestDistrict_PottedTree','file':str(fbx.relative_to(OUT)).replace('\\','/'),'file_sha256':digest(fbx),'triangles':triangles,'leaf_count':leaf_count,'materials':[m.name for m in materials],'opaque_closed_leaf_geometry':True,'collision_count':1,'bounds_m':new_bounds}],
 'preservation':{'original_bounds_m':expected,'inside_original_maximum_bounds':True,'pot_soil_triangles':len(base_faces),'pot_soil_vertex_sha256_before':base_hash,'pot_soil_vertex_sha256_after':vector_hash(world_vertices(pot)),'pot_soil_vertices_identical':True,'pot_soil_surface_uv_material_sha256_before':surface_before,'pot_soil_surface_uv_material_sha256_after':surface_after,'pot_soil_triangles_uvs_materials_identical':True,'collision_vertex_sha256_before':vector_hash(old_collision),'collision_vertex_sha256_after':collision_hash,'collision_vertices_identical':True,'collision_bounds_m':bounds(old_collision),'actor_ids_positions_scales_edited':False,'courtyard_actor_scale_retained':.65},
 'blend_file':str(blend.relative_to(OUT)).replace('\\','/'),'blend_sha256':digest(blend),'previews':[str(p.relative_to(OUT)).replace('\\','/') for p in (BUILD/'previews').glob('*.png')],
 'notes':['All closed3D leaf blades; no alpha masks, translucency or two-sided foliage cards.','Branching and leaf silhouette replace the original sculpted ellipsoid crowns.','Preview is a Blender source-art comparison, not an Unreal/device visual or performance test.','Any later Unreal import must retain current actor IDs, locations, rotations, scales and simple collision.']}
(BUILD/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('QUEST_PREMIUM_FOLIAGE_COMPLETE',json.dumps({'triangles':triangles,'leaf_count':leaf_count,'manifest':str(OUT/'manifest.json')}),flush=True)
