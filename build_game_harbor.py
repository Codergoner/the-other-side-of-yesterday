"""Build the independent, metric Unreal harbor level and portable static meshes."""
import bpy, bmesh, math, random, json, sys
from pathlib import Path
from collections import defaultdict
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'/'game'
sys.path.insert(0,str(ROOT))
random.seed(730)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene; scene.name='Yesterday Harbor · Game Environment'
scene.unit_settings.system='METRIC'; scene.unit_settings.scale_length=1
scene['Purpose']='Freestanding game environment in meters; native PBR materials; no reference projection'
scene['Engine']='Unreal Engine 5.8 · First and Third Person'

def coll(name):
    c=bpy.data.collections.new(name); scene.collection.children.link(c); return c
source_coll=coll('AUTHORING · editable components')
game_coll=coll('EXPORT · district static meshes')
collision_coll=coll('COLLISION · UBX and UCX proxies')
scene_coll=coll('CAMERAS · lights · gameplay markers')
parts=defaultdict(list); colliders=defaultdict(list)

tex_specs=json.loads((OUT/'textures'/'materials.json').read_text())
materials={}
key_names={'plaster':'M_Plaster','stone':'M_Stone','rock':'M_Rock','cobble':'M_Cobble','wood':'M_Wood','roof':'M_Roof','dark':'M_Dark','metal':'M_Metal','leaf':'M_Leaf','fabric':'M_Fabric','water':'M_Water','terracotta':'M_Terracotta','canvas_blue':'M_CanvasBlue','canvas_rust':'M_CanvasRust','fruit_gold':'M_FruitGold','fruit_red':'M_FruitRed','fruit_green':'M_FruitGreen'}
for key,name in key_names.items():
    spec=tex_specs[name]
    material=bpy.data.materials.new(name); material.use_nodes=True
    n=material.node_tree.nodes; l=material.node_tree.links
    p=n.get('Principled BSDF'); p.inputs['Metallic'].default_value=spec['metallic']
    for suffix,socket,noncolor in [('base_color','Base Color',False),('roughness','Roughness',True),('normal','Normal',True)]:
        node=n.new('ShaderNodeTexImage'); node.image=bpy.data.images.load(str(OUT/'textures'/spec[suffix])); node.image.pack()
        if noncolor: node.image.colorspace_settings.name='Non-Color'
        if suffix=='normal':
            normal=n.new('ShaderNodeNormalMap'); normal.inputs['Strength'].default_value=.65
            l.new(node.outputs['Color'],normal.inputs['Color']); l.new(normal.outputs[0],p.inputs[socket])
        else:l.new(node.outputs['Color'],p.inputs[socket])
    material.diffuse_color=(.55,.5,.4,1)
    materials[key]=material

def metric_uv(obj):
    data=obj.data; data.update()
    uv=data.uv_layers.new(name='UV0_MetricTiling')
    for face in data.polygons:
        axis=max(range(3),key=lambda a:abs(face.normal[a]))
        axes=((1,2),(0,2),(0,1))[axis]
        for li in face.loop_indices:
            v=data.vertices[data.loops[li].vertex_index].co
            uv.data[li].uv=(v[axes[0]]*.5,v[axes[1]]*.5)

skip_collision=('cornice','tile','mullion','shutter','sill','lintel','jamb','finial','ridge','eave','rib','louvre','slit frame','bell','gallery rail','lantern pane')
def collision_copy(obj,group,kind='UCX'):
    if any(word in obj.name.lower() for word in skip_collision) and 'collision' not in obj.name.lower():return
    data=obj.data.copy(); proxy=bpy.data.objects.new('%s_%s_%03d'%(kind,group,len(colliders[group])),data)
    collision_coll.objects.link(proxy); proxy.hide_render=True; proxy.display_type='WIRE'; proxy['Collision']=kind
    colliders[group].append(proxy)

def mesh(name,verts,faces,material,group='SM_Environment',collision=False):
    data=bpy.data.meshes.new(name); data.from_pydata(verts,[],faces); data.update()
    obj=bpy.data.objects.new(name,data); source_coll.objects.link(obj)
    if material:data.materials.append(material)
    metric_uv(obj); parts[group].append(obj)
    if collision:collision_copy(obj,group)
    return obj

def box(name,center,size,material,group='SM_Environment',collision=True,bevel=.03):
    c=Vector(center); x,y,z=[float(a)/2 for a in size]
    verts=[c+Vector(v) for v in [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    obj=mesh(name,verts,faces,material,group,False)
    if collision:collision_copy(obj,group,'UBX')
    if bevel and min(size)>.12:
        mod=obj.modifiers.new('Worn edge bevel','BEVEL'); mod.width=min(bevel,min(size)*.12); mod.segments=1
    return obj

def beam(name,a,b,radius,material,group='SM_Environment',collision=False):
    a,b=Vector(a),Vector(b); axis=b-a
    if axis.length<.00001:return None
    rotation=axis.to_track_quat('Z','Y').to_matrix()
    mid=(a+b)/2; n=8
    verts=[mid+rotation@Vector((radius*math.cos(i*math.tau/n),radius*math.sin(i*math.tau/n),z)) for z in (-axis.length/2,axis.length/2) for i in range(n)]
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,n*2))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    return mesh(name,verts,faces,material,group,collision)

def ramp(name,a,b,width,material,group,base=-2,collision=True):
    a,b=Vector(a),Vector(b); delta=b-a
    side=Vector((-delta.y,delta.x,0)).normalized()*width/2
    top=[a-side,a+side,b+side,b-side]
    bottom=[Vector((p.x,p.y,base)) for p in top]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    return mesh(name,top+bottom,faces,material,group,collision)

def steps(name,a,b,width,group,count,base=-2):
    a,b=Vector(a),Vector(b); delta=b-a; flat=Vector((delta.x,delta.y,0)); step=flat.length/count
    for i in range(count):
        p=a.lerp(b,(i+.5)/count)
        dims=(width,step+.012,.18) if abs(delta.y)>abs(delta.x) else (step+.012,width,.18)
        box(name+' tread %02d'%i,p-Vector((0,0,.09)),dims,materials['stone'],group,False,.025)
    ramp(name+' continuous walkable ramp',a,b,width,materials['stone'],group,base,True)

def floor(y):return 8+(y+22)*.10

# Connected main street: a closed solid wedge, uninterrupted capsule collision.
ramp('Left town continuous bedrock',(-9.525,-30,floor(-30)-.12),(-9.525,36,floor(36)-.12),12.95,materials['stone'],'SM_LeftTownFoundation',-3)
ramp('Market street continuous foundation',(0,-26,floor(-26)),(0,35,floor(35)),6.1,materials['stone'],'SM_StreetFoundation',-2)
ramp('Market street cobbled surface',(0,-26,floor(-26)+.02),(0,35,floor(35)+.02),5.5,materials['cobble'],'SM_StreetSurface',7.1,False)
for side in (-1,1):
    for i in range(30):
        y=-25+i*2;z=floor(y)
        box('Street edge limestone kerb',(side*2.95,y,z+.10),(.28,1.96,.28),materials['stone'],'SM_StreetDetails',False,.03)
# Stone guardrail opens onto the switchback stair route at y14.
for y in range(-24,32,2):
    if 11<y<17:continue
    z=floor(y)
    box('Limestone promenade pier',(3.1,y,z+.65),(.55,.55,1.3),materials['plaster'],'SM_PromenadeRail',False)
    box('Promenade pier cap',(3.1,y,z+1.34),(.72,.72,.17),materials['stone'],'SM_PromenadeRail',False)
    if y+2<12 or y>=17:
        beam('Promenade oak top rail',(3.1,y,z+1.07),(3.1,y+2,floor(y+2)+1.07),.10,materials['wood'],'SM_PromenadeRail')
        for j in range(1,5):
            yy=y+j*.4
            beam('Promenade baluster',(3.1,yy,floor(yy)+.22),(3.1,yy,floor(yy)+1.0),.055,materials['wood'],'SM_PromenadeRail')
        box('Guardrail collision',(3.12,y+1,z+.68),(.22,2.0,1.1),materials['dark'],'SM_GuardrailCollision',True,0)
parts['SM_GuardrailCollision'][-1].hide_render=True

# Root-to-harbor switchback: 0.15m visible risers over continuous ramp collision.
box('Upper stair landing',(5.2,14,11.45),(5.9,2.8,.3),materials['stone'],'SM_HarborStairs',True)
steps('Harbor stair west flight',(7,14,11.6),(7,1,6.4),2.8,'SM_HarborStairs',36)
box('Switchback lower landing',(9,1,6.25),(6.6,2.8,.3),materials['stone'],'SM_HarborStairs',True)
steps('Harbor stair east flight',(11,1,6.4),(11,14,1.2),2.8,'SM_HarborStairs',36)
box('Dock access landing',(11.6,13.4,1.04),(4,3.2,.32),materials['stone'],'SM_HarborStairs',True)
for xx in (5.5,8.5):
    beam('Switchback handrail upper',(xx,14,12.55),(xx,1,7.35),.065,materials['wood'],'SM_HarborStairs')
for xx in (9.5,12.5):
    beam('Switchback handrail lower',(xx,1,7.35),(xx,14,2.15),.065,materials['wood'],'SM_HarborStairs')

# Upper route to the campanile and cathedral plaza, all below 44 degrees.
steps('Campanile approach',(0,35,13.7),(0,44,17.5),5.5,'SM_UpperRoute',26)
box('Campanile forecourt',(-1,45,17.27),(9,2,.45),materials['stone'],'SM_UpperRoute',True)
steps('Cathedral ceremonial stair',(0,45,17.5),(0,57,25),5.5,'SM_UpperRoute',50)
box('Cathedral plaza',(11,70,24.7),(26,26,.6),materials['stone'],'SM_CathedralPlaza',True)
box('Cathedral front apron',(13.5,54,24.7),(21,6,.6),materials['stone'],'SM_CathedralPlaza',True)

def rock_mass(name,outline,height,group,bottom=-3):
    n=len(outline); verts=[]
    for z,expand in [(bottom,1.12),(height*.48,1.05),(height,1)]:
        cx=sum(p[0] for p in outline)/n;cy=sum(p[1] for p in outline)/n
        for i,(x,y) in enumerate(outline):
            verts.append((cx+(x-cx)*expand,cy+(y-cy)*expand,z+(0 if z in (bottom,height) else random.uniform(-1,1))))
    faces=[tuple(range(n-1,-1,-1)),tuple(range(2*n,3*n))]
    for level in range(2):
        for i in range(n):
            a=level*n+i;b=level*n+(i+1)%n
            faces.extend([(a,b,b+n),(a,b+n,a+n)])
    return mesh(name,verts,faces,materials['rock'],group,False)

rock_mass('Cathedral weathered limestone headland',[(3,47),(15,45),(27,49),(33,61),(32,76),(22,85),(3,84),(-7,70),(-3,57),(3,57)],24.7,'SM_CathedralCliff')
rock_mass('Lighthouse rocky island',[(52,27),(54,24),(60,24),(64,28),(64,34),(61,37),(54,36),(51,32)],2,'SM_LighthouseIsland')
rock_mass('South waterfront cliff',[(3.0,-25),(7,-25),(9,-17),(8,-3),(3.0,-3)],8.0,'SM_LowCliffs')
rock_mass('North waterfront cliff',[(3.0,18),(10,19),(13,29),(9,36),(3.0,35)],11.0,'SM_LowCliffs')
# Villa footings connect to land rather than hovering above the shoreline.
box('Lower villa quay',(8,25,2.8),(11,13,5.6),materials['stone'],'SM_VillaQuays',True)
box('Second villa quay',(14,33,1.7),(8,10,3.4),materials['stone'],'SM_VillaQuays',True)

api={'box':box,'mesh':mesh,'beam':beam,'materials':materials}
import game_architecture,game_props
game_architecture.add_architecture(api)
game_props.add_props(api)
print('Metric architecture and props created',sum(map(len,parts.values())),flush=True)

# Real ground plane, distant crag silhouettes and scattered ivy in metric space.
box('Harbor sea',(25,42,-.12),(360,360,.20),materials['water'],'SM_Sea',False,0)
for i,(cx,cy,r,h) in enumerate([(-22,154,38,38),(6,188,45,65),(70,190,46,42),(117,174,33,49)]):
    verts=[];faces=[];n=23
    for j in range(n):
        yy=(j/(n-1)*2-1)
        for k in range(n):
            xx=(k/(n-1)*2-1)
            envelope=max(0,1-xx*xx-yy*yy)**.75
            ridge=.72+.16*math.sin(xx*12+yy*8+i)+.12*math.cos(xx*18-yy*15)
            height=h*envelope*ridge+random.uniform(-1.4,1.4)*envelope
            verts.append((cx+xx*r,cy+yy*r,height-1))
    for j in range(n-1):
        for k in range(n-1):
            a=j*n+k;faces.extend([(a,a+1,a+n+1),(a,a+n+1,a+n)])
    mesh('Distant rugged mountain %d'%i,verts,faces,materials['rock'],'SM_DistantMountains',False)
# Ivy is attached to actual building corners, with modeled climbing stems.
for cy in (-13,2,18):
    for anchor in (cy-4.25,cy+4.25):
        z0=floor(cy)+.1
        stem=[(-3.965,anchor+.08*math.sin(j),z0+j*.8) for j in range(11)]
        for j in range(10):beam('Climbing ivy woody stem',stem[j],stem[j+1],.014,materials['wood'],'SM_Ivy')
        for k in range(90):
            z=z0+random.uniform(0,7.9);yy=anchor+random.uniform(-.24,.24)
            p=Vector((-3.945,yy,z));r=random.uniform(.045,.12)
            mesh('Wall attached ivy leaf',[p+Vector((0,-r,0)),p+Vector((.018,0,r*.75)),p+Vector((0,r,0)),p+Vector((-.012,0,-r*.75))],[(0,1,2,3)],materials['leaf'],'SM_Ivy',False)

# Consolidate editable components into district/building static mesh chunks.
# UV0 remains metric/tileable. UV1 gets distinct, padded per-face charts.
bpy.context.view_layer.update()
deps=bpy.context.evaluated_depsgraph_get()
assets=[]
for group,objects in list(parts.items()):
    if group=='SM_GuardrailCollision':
        for obj in objects:obj.hide_render=True
        continue
    verts=[]; faces=[]; uv_values=[]; face_mats=[]; matlist=[]
    for obj in objects:
        evaluated=obj.evaluated_get(deps)
        data=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=deps)
        offset=len(verts); verts.extend(obj.matrix_world@v.co for v in data.vertices)
        uv=data.uv_layers.active
        remap=[]
        for material in data.materials:
            material=material.original if getattr(material,'is_evaluated',False) else material
            if material not in matlist:matlist.append(material)
            remap.append(matlist.index(material))
        for face in data.polygons:
            faces.append(tuple(offset+data.loops[li].vertex_index for li in face.loop_indices))
            uv_values.extend(tuple(uv.data[li].uv) if uv else (0,0) for li in face.loop_indices)
            face_mats.append(remap[face.material_index] if remap else 0)
        evaluated.to_mesh_clear()
    data=bpy.data.meshes.new(group); data.from_pydata(verts,[],faces); data.update()
    obj=bpy.data.objects.new(group,data); game_coll.objects.link(obj)
    for material in matlist:data.materials.append(material)
    uv0=data.uv_layers.new(name='UV0_MetricTiling')
    for i,uv in enumerate(uv_values):uv0.data[i].uv=uv
    for i,mi in enumerate(face_mats):data.polygons[i].material_index=mi
    uv1=data.uv_layers.new(name='UV1_UniqueLightmap')
    grid=math.ceil(math.sqrt(max(1,len(data.polygons))))
    for i,face in enumerate(data.polygons):
        axis=max(range(3),key=lambda a:abs(face.normal[a])); axes=((1,2),(0,2),(0,1))[axis]
        coords=[(data.vertices[data.loops[li].vertex_index].co[axes[0]],data.vertices[data.loops[li].vertex_index].co[axes[1]]) for li in face.loop_indices]
        lo=[min(p[j] for p in coords) for j in (0,1)]; hi=[max(p[j] for p in coords) for j in (0,1)]
        for li,p in zip(face.loop_indices,coords):
            uv1.data[li].uv=((i%grid+.08+.84*(p[0]-lo[0])/max(hi[0]-lo[0],1e-6))/grid,(i//grid+.08+.84*(p[1]-lo[1])/max(hi[1]-lo[1],1e-6))/grid)
    data.uv_layers.active_index=0
    bm=bmesh.new(); bm.from_mesh(data); bmesh.ops.triangulate(bm,faces=list(bm.faces)); bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bm.to_mesh(data); bm.free(); data.update()
    minimum=[min(v.co[i] for v in data.vertices) for i in range(3)]
    maximum=[max(v.co[i] for v in data.vertices) for i in range(3)]
    assets.append({'name':group,'file':'meshes/'+group+'.fbx','materials':[m.name for m in matlist],'bounds_m':{'min':minimum,'max':maximum},'collision_count':len(colliders[group]),'triangles':len(data.polygons),'vertices':len(data.vertices)})
    print('Batched',group,len(data.polygons),'triangles',len(colliders[group]),'collision shapes',flush=True)
source_coll.hide_render=True; source_coll.hide_viewport=True
collision_coll.hide_render=True

# Guard rails have invisible but blocking boxes in their own export asset.
if colliders.get('SM_GuardrailCollision'):
    proxy_group='SM_GuardrailCollision'
    first=parts[proxy_group][0]
    data=first.data.copy(); invisible=bpy.data.objects.new(proxy_group,data); game_coll.objects.link(invisible)
    invisible.hide_render=True
    assets.append({'name':proxy_group,'file':'meshes/'+proxy_group+'.fbx','materials':['M_Dark'],'bounds_m':{'min':[-.1,-.1,-.1],'max':[.1,.1,.1]},'collision_count':len(colliders[proxy_group]),'triangles':12,'vertices':8,'hidden_in_game':True})

route=[('Player start',(0,-20,floor(-20))),('Market lane',(0,0,floor(0))),('Harbor stair entrance',(0,14,floor(14))),('Upper landing',(7,14,11.6)),('Switchback landing',(7,1,6.4)),('Cross landing',(11,1,6.4)),('Dock stair foot',(11,14,1.2)),('Dock side exit',(13.2,14,1.2)),('Dock connector',(13.2,12,1.2)),('Main pier',(29.5,12,1.2)),('Main street upper',(0,33,floor(33))),('Campanile clear lane',(.8,35,13.7)),('Campanile approach',(.8,42,16.66)),('Cathedral staircase',(0,51,21.25)),('Cathedral plaza',(0,58,25))]
# Navigation QA against the actual exported collision triangles.
cverts=[];cfaces=[]
for proxies in colliders.values():
    for obj in proxies:
        offset=len(cverts);cverts.extend(v.co[:] for v in obj.data.vertices)
        cfaces.extend(tuple(offset+i for i in face.vertices) for face in obj.data.polygons)
tree=BVHTree.FromPolygons(cverts,cfaces,all_triangles=False)
route_report=[]
for name,p in route:
    position,normal,index,distance=tree.ray_cast(Vector((p[0],p[1],p[2]+.7)),Vector((0,0,-1)),2.0)
    route_report.append({'name':name,'position':list(p),'supported':position is not None,'hit_z':position.z if position else None,'slope_degrees':math.degrees(math.acos(min(1,abs(normal.z)))) if normal else None})

manifest={'name':'Yesterday Harbor','engine':'Unreal Engine 5.8','units':'meters','unreal_transform':{'unit_scale':100,'axes':['X','-Y','Z']},'assets':assets,'materials':'textures/materials.json','player_start':{'blender_position':[0,-20,9.25],'unreal_position_cm':[0,2000,925],'yaw_degrees':90,'unreal_yaw_degrees':-90},'route_waypoints_blender':route_report,'water_level_m':0,'world_bounds_m':{'min':[-170,-138,-3],'max':[205,222,65]},'notes':['Independent freestanding geometry with native tileable PBR textures.','Visible steps use continuous convex collision ramps for walking.','UV1 is unique/padded for portability; lighting is intended to be dynamic (Lumen).','Interiors are partial shells; the primary playable route is the exterior market and docks.']}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')

for asset in assets:
    if '--preview-only' in sys.argv and (OUT/asset['file']).exists() and ('--export='+asset['name']) not in sys.argv:continue
    obj=bpy.data.objects[asset['name']]
    bpy.ops.object.select_all(action='DESELECT')
    obj.hide_set(False); obj.select_set(True); bpy.context.view_layer.objects.active=obj
    for proxy in colliders[asset['name']]:proxy.hide_set(False);proxy.select_set(True)
    bpy.ops.export_scene.fbx(filepath=str(OUT/asset['file']),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',global_scale=1,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',use_mesh_modifiers=True,add_leaf_bones=False,bake_anim=False,path_mode='RELATIVE',embed_textures=False,mesh_smooth_type='FACE')
print('FBX EXPORTS COMPLETE',len(assets),flush=True)
(OUT/'exports_complete.json').write_text(json.dumps({'assets':len(assets),'triangles':sum(a['triangles'] for a in assets),'status':'complete'}),encoding='utf-8')
collision_coll.hide_viewport=True

# Preview from the reference-inspired composition and a true player viewpoint.
world=bpy.data.worlds.new('Mediterranean sunset sky');world.use_nodes=True; scene.world=world
bg=world.node_tree.nodes.get('Background')
sky=world.node_tree.nodes.new('ShaderNodeTexSky');sky.sky_type='MULTIPLE_SCATTERING';sky.sun_elevation=math.radians(12);sky.sun_rotation=math.radians(110);sky.altitude=.1
world.node_tree.links.new(sky.outputs[0],bg.inputs['Color']);bg.inputs['Strength'].default_value=.32
sun_data=bpy.data.lights.new('Golden hour sun','SUN');sun_data.energy=2.2;sun_data.angle=.08;sun_data.color=(1,.75,.46)
sun=bpy.data.objects.new('Golden hour sun',sun_data);scene_coll.objects.link(sun);sun.rotation_euler=(math.radians(64),math.radians(-22),math.radians(110))
area_data=bpy.data.lights.new('Soft sky fill','AREA');area_data.energy=2400;area_data.size=45;area_data.color=(.50,.7,1)
area=bpy.data.objects.new('Soft sky fill',area_data);scene_coll.objects.link(area);area.location=(0,20,50)

def camera(name,pos,target,lens):
    data=bpy.data.cameras.new(name);obj=bpy.data.objects.new(name,data);scene_coll.objects.link(obj)
    obj.location=pos;obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler();data.lens=lens;data.clip_end=1200;return obj
overview=camera('CAM_Overview',(3,-35,17),(14,45,15),28)
player=camera('CAM_Player',(0,-20,9.9),(0,10,12),24)
for name,p in route:
    obj=bpy.data.objects.new('NAV_'+name,None);scene_coll.objects.link(obj);obj.location=p;obj.empty_display_type='SPHERE';obj.empty_display_size=.22
scene.camera=overview
scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
try:
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='HIP';prefs.get_devices()
    for d in prefs.devices:d.use=d.type=='HIP' and '9070' in d.name
    if any(d.use for d in prefs.devices):scene.cycles.device='GPU'
except Exception:pass
scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX';scene.render.image_settings.file_format='PNG'
scene.render.filepath=str(OUT/'previews'/'Harbor_Game_Overview.png')
for screen in bpy.data.screens:
    for a in screen.areas:
        if a.type=='VIEW_3D':a.spaces.active.region_3d.view_perspective='CAMERA';a.spaces.active.clip_end=1200
text=bpy.data.texts.new('GAME ENVIRONMENT · READ ME');text.write('Native metric game environment, separate from the image-projected study.\nDistrict meshes have tileable UV0, unique UV1, packed PBR maps, and named collision proxies.\nAuthoring components are preserved in a hidden collection.\nMain street → switchback → docks is the primary playable route.\nUnreal project and first/third person maps are in game_unreal.\n')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Yesterday_Harbor_Game.blend'))
bpy.ops.render.render(write_still=True)
scene.camera=player;scene.render.filepath=str(OUT/'previews'/'Harbor_Game_Player.png');bpy.ops.render.render(write_still=True)
scene.camera=overview
print('GAME BUILD COMPLETE',len(assets),'assets;',sum(a['triangles'] for a in assets),'triangles; route:',route_report,flush=True)
