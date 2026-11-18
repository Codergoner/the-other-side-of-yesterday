"""Build a camera-matched harbor reconstruction from the supplied reference."""
import bpy
import math
import random
import sys
import time
from pathlib import Path
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
W, H, F = 1672, 941, 1550.0
random.seed(24)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.name = '01 · Reference camera match'
scene['Reconstruction type'] = 'Camera-projected 2.5D environment with editable 3D architecture and props'
scene['Reference image'] = 'assets/harbor_reference.png · 1672 × 941'
scene['Camera note'] = 'Source view matches exactly; unseen surfaces are approximated. Switch scenes for the untextured model.'
image = bpy.data.images.load(str(ROOT / 'assets' / 'harbor_reference.png'))
image.name = 'REFERENCE · original harbor · packed'
image.pack()

def collection(name):
    coll = bpy.data.collections.new(name)
    scene.collection.children.link(coll)
    return coll

active_collection = collection('00 · Cameras and lighting')

def set_collection(coll):
    global active_collection
    active_collection = coll

def move(obj):
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    active_collection.objects.link(obj)
    return obj

def world(u, v, depth):
    return Vector(((u-W/2)*depth/F, depth, (H/2-v)*depth/F))

# Shared projection shader. Texture lookup is calculated from the actual world
# position, so it remains perspective-correct across every modeled surface.
projection = bpy.data.node_groups.new('REFERENCE PROJECTION · shared camera mapping', 'ShaderNodeTree')
projection.interface.new_socket(name='Native surface', in_out='INPUT', socket_type='NodeSocketShader')
projection.interface.new_socket(name='Surface', in_out='OUTPUT', socket_type='NodeSocketShader')
nodes, links = projection.nodes, projection.links
inp = nodes.new('NodeGroupInput'); inp.location=(-900,-300)
out = nodes.new('NodeGroupOutput'); out.location=(700,30)
geo = nodes.new('ShaderNodeNewGeometry'); geo.location=(-1100,200)
sep = nodes.new('ShaderNodeSeparateXYZ'); sep.location=(-920,200)
links.new(geo.outputs['Position'],sep.inputs[0])
def mathnode(op,a,b,x,y):
    n=nodes.new('ShaderNodeMath'); n.operation=op; n.location=(x,y)
    if hasattr(a,'node'): links.new(a,n.inputs[0])
    else: n.inputs[0].default_value=a
    if hasattr(b,'node'): links.new(b,n.inputs[1])
    else: n.inputs[1].default_value=b
    return n.outputs[0]
u=mathnode('DIVIDE',sep.outputs['X'],sep.outputs['Y'],-720,280)
v=mathnode('DIVIDE',sep.outputs['Z'],sep.outputs['Y'],-720,80)
u=mathnode('MULTIPLY',u,F/W,-540,280)
v=mathnode('MULTIPLY',v,F/H,-540,80)
u=mathnode('ADD',u,.5,-360,280)
v=mathnode('ADD',v,.5,-360,80)
combine=nodes.new('ShaderNodeCombineXYZ'); combine.location=(-160,200)
links.new(u,combine.inputs['X']); links.new(v,combine.inputs['Y'])
tex=nodes.new('ShaderNodeTexImage'); tex.image=image; tex.interpolation='Closest'; tex.extension='EXTEND'; tex.location=(40,220)
links.new(combine.outputs[0],tex.inputs['Vector'])
emission=nodes.new('ShaderNodeEmission'); emission.location=(260,160)
links.new(tex.outputs['Color'],emission.inputs['Color'])
switch=nodes.new('ShaderNodeValue'); switch.name='EXACT_REFERENCE'; switch.label='1 = source projection / 0 = native surfaces'; switch.outputs[0].default_value=1; switch.location=(60,-120)
mix=nodes.new('ShaderNodeMixShader'); mix.location=(480,30)
links.new(switch.outputs[0],mix.inputs[0]); links.new(inp.outputs[0],mix.inputs[1]); links.new(emission.outputs[0],mix.inputs[2]); links.new(mix.outputs[0],out.inputs[0])

def mat(name,color,roughness=.8):
    material=bpy.data.materials.new(name); material.diffuse_color=(*color[:3],1)
    material.use_nodes=True
    n=material.node_tree.nodes; l=material.node_tree.links
    n.clear()
    p=n.new('ShaderNodeBsdfPrincipled'); p.inputs['Base Color'].default_value=(*color[:3],1); p.inputs['Roughness'].default_value=roughness; p.location=(20,0)
    noise=n.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value=8; noise.inputs['Detail'].default_value=3; noise.location=(-420,-80)
    bump=n.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=.22; bump.inputs['Distance'].default_value=.075; bump.location=(-180,-50)
    l.new(noise.outputs['Fac'],bump.inputs['Height']); l.new(bump.outputs[0],p.inputs['Normal'])
    group=n.new('ShaderNodeGroup'); group.node_tree=projection; group.location=(340,0)
    output=n.new('ShaderNodeOutputMaterial'); output.location=(580,0)
    l.new(p.outputs[0],group.inputs[0]); l.new(group.outputs[0],output.inputs[0])
    return material

materials={
    'plaster':mat('Lime plaster · warm ivory',(.69,.57,.39)),
    'stone':mat('Weathered limestone',(.43,.37,.28)),
    'wood':mat('Aged oak',(.19,.105,.045)),
    'roof':mat('Patinated green roof tiles',(.10,.24,.23)),
    'dark':mat('Shadowed openings',(.027,.033,.03)),
    'metal':mat('Forged iron',(.075,.08,.075),.48),
    'leaf':mat('Climbing ivy',(.20,.27,.058)),
    'fabric':mat('Sun faded linen',(.58,.40,.22)),
    'water':mat('Harbor water',(.035,.15,.20),.17),
}
projection_mat=mat('SOURCE · perspective projected reference',(.56,.48,.35))

def mesh(name,verts,faces,material):
    data=bpy.data.meshes.new(name); data.from_pydata(verts,[],faces); data.update()
    obj=bpy.data.objects.new(name,data); active_collection.objects.link(obj)
    if material: data.materials.append(material)
    return obj

def box(name,center,size,material,bevel=.03):
    x,y,z=(float(s)/2 for s in size)
    verts=[(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    obj=mesh(name,verts,faces,material); obj.matrix_world=Matrix.Translation(Vector(center))
    if bevel:
        mod=obj.modifiers.new('Soft worn edges','BEVEL'); mod.width=min(bevel,min(size)*.18); mod.segments=2
        mod=obj.modifiers.new('Corner normals','WEIGHTED_NORMAL')
    return obj

def beam(name,a,b,radius,material):
    a,b=Vector(a),Vector(b); delta=b-a
    verts=[(radius*math.cos(i*math.tau/8),radius*math.sin(i*math.tau/8),z) for z in [-delta.length/2,delta.length/2] for i in range(8)]
    faces=[tuple(range(7,-1,-1)),tuple(range(8,16))]+[(i,(i+1)%8,(i+1)%8+8,i+8) for i in range(8)]
    obj=mesh(name,verts,faces,material)
    obj.matrix_world=Matrix.Translation((a+b)/2) @ delta.to_track_quat('Z','Y').to_matrix().to_4x4()
    return obj

def project_object(obj):
    if obj.type!='MESH': return obj
    uv=obj.data.uv_layers.active or obj.data.uv_layers.new(name='Reference camera UV')
    for face in obj.data.polygons:
        for index in face.loop_indices:
            p=obj.matrix_world @ obj.data.vertices[obj.data.loops[index].vertex_index].co
            d=max(.001,p.y)
            uv.data[index].uv=(.5+p.x*F/(W*d),.5+p.z*F/(H*d))
    return obj

api={key:globals()[key] for key in ['world','box','mesh','beam','mat','collection','set_collection','project_object','projection_mat','materials']}

def inside(x,y,poly):
    odd=False
    for i in range(len(poly)):
        a,b=poly[i-1],poly[i]
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]: odd=not odd
    return odd

# Disjoint semantic depth surfaces retain every source pixel, with actual
# perspective parallax. They are isolated from the independent 3D model.
regions=[
('Distant mountain silhouettes',180,[(0,95),(180,105),(260,82),(330,127),(415,145),(511,100),(575,154),(660,166),(727,121),(802,57),(848,81),(922,154),(1012,188),(1160,215),(1251,179),(1328,128),(1362,150),(1400,202),(1490,219),(1576,201),(1672,214),(1672,299),(0,299)]),
('Distant island town',126,[(1171,234),(1235,235),(1292,222),(1332,250),(1401,246),(1446,237),(1487,249),(1549,249),(1580,284),(1602,300),(1494,311),(1290,286),(1198,295)]),
('Cathedral and fortress cliff',72,[(648,216),(727,200),(801,182),(845,150),(872,128),(909,109),(914,65),(934,62),(938,43),(948,48),(955,63),(961,67),(964,106),(1040,110),(1044,82),(1057,79),(1065,107),(1071,111),(1075,173),(1130,177),(1138,144),(1150,124),(1167,146),(1174,194),(1207,238),(1256,263),(1279,331),(1296,386),(1370,399),(1338,423),(1168,416),(1100,401),(1051,377),(984,396),(942,353),(864,348),(851,302),(784,291),(739,285),(678,308)]),
('Bell tower and high bridge',47,[(577,225),(580,113),(590,108),(590,52),(600,48),(607,21),(624,10),(637,18),(650,46),(663,50),(663,118),(672,119),(670,218),(719,205),(784,206),(828,233),(836,302),(746,307),(678,280)]),
('Center villas and stone gateway',31,[(633,319),(683,328),(705,360),(746,365),(757,344),(787,318),(818,322),(846,324),(854,349),(879,351),(889,377),(915,392),(920,521),(961,551),(958,597),(915,638),(838,600),(785,569),(779,514),(702,521),(645,530)]),
('Foreground ruined houses',17,[(0,0),(271,0),(310,38),(363,66),(407,64),(444,12),(470,10),(485,152),(529,203),(587,218),(641,224),(678,258),(702,332),(699,387),(666,397),(651,476),(574,535),(502,565),(371,613),(0,601)]),
('Promenade and market street',-1,[(340,525),(529,522),(639,524),(746,503),(771,526),(729,580),(670,629),(622,691),(676,941),(0,941),(0,744),(300,694)]),
('Foreground market awnings',11,[(0,432),(156,437),(375,531),(358,599),(370,683),(339,731),(0,818)]),
('Middle awnings',24,[(399,391),(467,383),(545,407),(572,419),(603,418),(655,451),(645,497),(553,493),(514,533),(426,523)]),
('Front stone balustrade',-2,[(653,652),(708,657),(743,717),(789,716),(831,756),(904,786),(947,777),(1023,803),(1037,845),(1193,871),(1271,876),(1285,851),(1422,881),(1551,900),(1672,907),(1672,941),(665,941)]),
('Near piers and moored boats',32,[(960,624),(1144,628),(1227,640),(1250,624),(1340,645),(1430,657),(1482,716),(1520,744),(1524,799),(1584,817),(1560,879),(1455,881),(1350,835),(1250,810),(1125,746),(1000,750)]),
('Harbor bridge and middle quay',49,[(933,405),(978,390),(1050,391),(1097,400),(1181,410),(1201,468),(1246,490),(1505,497),(1521,516),(1505,552),(1410,535),(1302,530),(1210,512),(1154,495),(1080,517),(1026,541),(965,511)]),
('Middle sailboats',52,[(1232,398),(1300,389),(1321,401),(1347,470),(1370,481),(1364,502),(1264,507),(1245,486)]),
('Far sailboat',75,[(1351,391),(1390,382),(1402,414),(1437,450),(1430,464),(1364,468)]),
('Near sailboat',33,[(1415,714),(1437,632),(1469,565),(1483,668),(1508,730),(1488,765),(1430,754)]),
('Lighthouse rock and tower',67,[(1534,501),(1547,457),(1578,437),(1603,433),(1605,361),(1611,352),(1612,332),(1623,322),(1632,331),(1635,355),(1638,363),(1640,432),(1668,450),(1672,511)]),
]
surface_coll=collection('01 · Source-matched semantic depth surfaces')
set_collection(surface_coll)
groups={name:([],[]) for name in ['Sky and open sea']+[r[0] for r in regions]}
step=8
for v0 in range(0,H,step):
    for u0 in range(0,W,step):
        u1,v1=min(W,u0+step),min(H,v0+step)
        u,v=(u0+u1)/2,(v0+v1)/2
        name='Sky and open sea'; depth=260 if v<224 else min(170,11000/max(24,v-195))
        for rn,rd,poly in regions:
            if inside(u,v,poly): name,depth=rn,rd
        def at(uu,vv):
            d=depth
            if name=='Sky and open sea' and vv>=224: d=min(170,11000/max(24,vv-195))
            elif depth==-1: d=7300/max(230,vv-215)
            elif depth==-2: d=6600/max(350,vv-220)
            elif name=='Foreground ruined houses': d=14+uu*.023+vv*.002
            elif name=='Center villas and stone gateway': d=30+(uu-700)*.035
            elif name=='Cathedral and fortress cliff': d=65+(uu-850)*.035
            elif name=='Near piers and moored boats': d=9500/max(240,vv-250)
            if depth not in (-1,-2) and name!='Sky and open sea': d+=math.sin(uu*.034)*math.sin(vv*.042)*.13
            return world(uu,vv,d)
        verts,faces=groups[name]; i=len(verts)
        verts.extend([at(u0,v0),at(u1,v0),at(u1,v1),at(u0,v1)])
        faces.append((i,i+3,i+2,i+1))
for name,(verts,faces) in groups.items():
    if verts:
        obj=mesh('Depth · '+name,verts,faces,projection_mat)
        obj['Role']='Camera-projected reference surface; hide this collection to inspect independent volumes'
        project_object(obj)
print('Semantic source surfaces complete',flush=True)

import scene_architecture
scene_architecture.add_architecture(api)
print('Architecture complete',flush=True)
import scene_harbor
scene_harbor.add_harbor(api)
print('Harbor and market complete',flush=True)

set_collection(collection('40 · Street, walls and greenery'))
road_verts=[]; road_faces=[]
for row in range(30):
    v=941-row*(423/29); u=270+(941-v)*1.13
    half=(v-500)*.75+35; d=7300/(v-215)
    road_verts.extend([world(u-half,v,d),world(u+half,v,d)])
for row in range(29):
    a=row*2; road_faces.append((a,a+1,a+3,a+2))
road=mesh('Continuous ascending stone promenade',road_verts,road_faces,materials['stone'])
road.modifiers.new('Solid masonry street foundation','SOLIDIFY').thickness=1.5
stone_verts=[]; stone_faces=[]
for row in range(44):
    v=935-row*9.4; center=270+(941-v)*1.13
    half=(v-500)*.75+35; d=7300/(v-215)
    for col in range(20):
        u=center-half+(col+.5+(row%2)*.35)*(2*half/20)
        p=world(u,v,d)+Vector((0,0,.025))
        sx=(2*half/20)*d/F*.45; sy=(7300/(v-4.4-215)-7300/(v+4.4-215))*.43
        z=random.uniform(.018,.045); k=len(stone_verts)
        stone_verts.extend(p+Vector((x,y,zz)) for x,y,zz in [(-sx,-sy,-z),(sx,-sy,-z),(sx,sy,-z),(-sx,sy,-z),(-sx,-sy,z),(sx,-sy,z),(sx,sy,z),(-sx,sy,z)])
        stone_faces.extend(tuple(k+i for i in face) for face in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
cobbles=mesh('880 individual worn paving stones',stone_verts,stone_faces,materials['stone'])
bevel=cobbles.modifiers.new('Eroded cobble edges','BEVEL'); bevel.width=.012; bevel.segments=2
# Stairway follows the receding street to the arched gateway.
for i in range(23):
    v=921-i*17
    u=280+(921-v)*.7
    d=7300/(v-215)
    left=world(u-110+(921-v)*.07,v,d)
    right=world(u+145-(921-v)*.13,v,d)
    c=(left+right)/2
    box('Promenade step %02d'%i,c,(max(.15,right.x-left.x),.38,.14),materials['stone'],.025)
# Balustrade foreground perspective sequence.
for i in range(15):
    u=666+i*70; v=666+(u-666)*.36; d=6600/(v-220)
    p=world(u,v,d)
    box('Balustrade limestone pier %02d'%i,p,(.48,.55,1.0),materials['plaster'])
    box('Balustrade cap %02d'%i,p+Vector((0,0,.55)),(.66,.70,.16),materials['stone'])
    if i:
        beam('Balustrade oak top',last+Vector((0,0,.27)),p+Vector((0,0,.27)),.09,materials['wood'])
        beam('Balustrade oak bottom',last-Vector((0,0,.24)),p-Vector((0,0,.24)),.075,materials['wood'])
    last=p
# Ivy clusters are modeled leaves attached to the landmark walls.
for k in range(380):
    u,v=random.choice([(183,130),(330,290),(441,340),(620,650),(752,737),(920,533),(1012,253)])
    u+=random.gauss(0,32); v+=random.gauss(0,45)
    d=19 if u<550 else (18 if v>600 else 46)
    p=world(u,v,d)
    size=random.uniform(.035,.12)
    obj=mesh('Ivy leaf %03d'%k,[p+Vector((-size,0,0)),p+Vector((0,-.035,size*.65)),p+Vector((size,0,0)),p+Vector((0,.035,-size*.65))],[(0,1,2,3)],materials['leaf'])
    obj.rotation_euler.y=random.random()*1.1
# Sparse irregular rubble for street depth.
for k in range(100):
    v=random.uniform(590,935); u=random.uniform(40,620)
    d=7300/(v-215); p=world(u,v,d)
    s=random.uniform(.025,.14)
    obj=box('Loose worn cobble %03d'%k,p,(s*2,s*1.5,s*.65),materials['stone'],.01)
    obj.rotation_euler.z=random.random()*math.pi

# Editable water plane, with true mesh ripples in the geometric model.
set_collection(collection('50 · Water and distant terrain'))
def terrain_mass(name,outline,depth,thickness):
    front=[world(u,v,depth) for u,v in outline]
    back=[p+Vector((0,thickness,0)) for p in front]
    n=len(front)
    faces=[tuple(reversed(range(n))),tuple(range(n,n*2))]
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    return mesh(name,front+back,faces,materials['stone'])
terrain_mass('Cathedral headland · continuous cliff foundation',[(835,214),(913,200),(1022,204),(1103,211),(1194,246),(1234,281),(1261,321),(1286,365),(1301,396),(1199,419),(1107,403),(1038,401),(976,368),(885,350)],96,19)
terrain_mass('Upper market terrace · solid foundation',[(0,390),(206,441),(391,488),(521,499),(604,542),(543,588),(443,637),(266,816),(0,941)],22,10)
terrain_mass('Waterfront terraces · continuous retaining wall',[(777,514),(910,508),(991,543),(1025,581),(1080,637),(990,737),(829,684),(779,603)],42,9)
terrain_mass('Lighthouse island · rocky shoreline',[(1524,503),(1538,468),(1554,445),(1583,435),(1620,432),(1657,439),(1672,471),(1672,511),(1639,517),(1599,510),(1567,516)],58,9)
verts=[]; faces=[]
for j in range(55):
    y=20+j*16.5
    for i in range(65):
        x=-600+i*22
        level=.1182*y-13.1 if y<=130 else .1182*130-13.1+(y-130)*(H/2-195)/F
        z=level+math.sin(x*2.9+y*1.1)*.025+math.sin(y*4.5)*.018
        verts.append((x,y,z))
for j in range(54):
    for i in range(64):
        a=j*65+i; faces.append((a,a+1,a+66,a+65))
mesh('Harbor sea · rippled editable surface',verts,faces,materials['water'])
for name,ridge in [
    ('Western high mountains',[(475,143),(512,103),(553,118),(586,112),(655,136),(689,139),(730,107),(776,67),(807,57),(831,72),(856,94),(886,117),(923,162),(968,203)]),
    ('Eastern mountain island',[(1123,209),(1161,179),(1195,190),(1235,171),(1272,160),(1301,133),(1317,133),(1341,157),(1364,183),(1409,208),(1467,227),(1521,238)])
]:
    verts=[world(u,v,168) for u,v in ridge]
    verts.extend(world(u,285,168) for u,v in ridge)
    count=len(ridge); faces=[]
    for k in range(count-1): faces.append((k,k+1,k+1+count,k+count))
    mountain=mesh(name,verts,faces,materials['stone'])
    solid=mountain.modifiers.new('Mountain massif depth','SOLIDIFY'); solid.thickness=24

set_collection(bpy.data.collections['00 · Cameras and lighting'])
cam_data=bpy.data.cameras.new('Reference camera · calibrated 1672 × 941')
cam=bpy.data.objects.new('CAMERA · original composition',cam_data); active_collection.objects.link(cam)
cam.location=(0,0,0); cam.rotation_euler=Vector((0,1,0)).to_track_quat('-Z','Y').to_euler()
cam_data.type='PERSP'; cam_data.lens=F*36/W; cam_data.sensor_width=36; cam_data.clip_start=.05; cam_data.clip_end=2000
cam_data.passepartout_alpha=1
cam.lock_location=(True,True,True); cam.lock_rotation=(True,True,True)
bg=cam_data.background_images.new(); bg.image=image; bg.alpha=.35; bg.display_depth='BACK'
scene.camera=cam
world_data=bpy.data.worlds.new('Golden hour atmosphere'); world_data.use_nodes=True
world_data.node_tree.nodes['Background'].inputs[0].default_value=(.28,.38,.47,1)
world_data.node_tree.nodes['Background'].inputs[1].default_value=.5
scene.world=world_data
sun_data=bpy.data.lights.new('Low western sun','SUN'); sun_data.energy=3; sun_data.angle=.12; sun_data.color=(1,.63,.32)
sun=bpy.data.objects.new('Golden hour sun',sun_data); active_collection.objects.link(sun); sun.rotation_euler=(.75,-.4,-1.8)
area_data=bpy.data.lights.new('Sky fill','AREA'); area_data.energy=1500; area_data.size=35; area_data.color=(.52,.70,1)
area=bpy.data.objects.new('Soft sky fill',area_data); active_collection.objects.link(area); area.location=(-8,15,25)
area.rotation_euler=(Vector((0,40,0))-area.location).to_track_quat('-Z','Y').to_euler()

scene.render.engine='CYCLES'
try:
    preferences=bpy.context.preferences.addons['cycles'].preferences
    preferences.compute_device_type='HIP'; preferences.get_devices()
    for device in preferences.devices: device.use=(device.type=='HIP' and '9070' in device.name)
    if any(device.type=='HIP' and device.use for device in preferences.devices): scene.cycles.device='GPU'
except Exception as error:
    print('Using CPU rendering:',error,flush=True)
scene.cycles.samples=16
scene.cycles.pixel_filter_type='BOX'; scene.cycles.filter_width=1
scene.cycles.use_denoising=False
scene.render.resolution_x=W; scene.render.resolution_y=H; scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'; scene.render.film_transparent=False
scene.view_settings.view_transform='Standard'; scene.view_settings.look='None'; scene.view_settings.exposure=0; scene.view_settings.gamma=1
scene.render.filepath=str(ROOT/'output'/'Harbor_reference_match.png')
scene.render.use_file_extension=True

# A second scene makes the independent geometry easy to review.
model=bpy.data.scenes.new('02 · Editable model · clay inspection')
model.world=world_data; model.camera=cam
for coll in scene.collection.children:
    if coll!=surface_coll: model.collection.children.link(coll)
clay=bpy.data.materials.new('INSPECTION · neutral warm clay'); clay.diffuse_color=(.55,.49,.39,1); clay.use_nodes=True
clay.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.55,.49,.39,1)
clay.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.75
model.view_layers[0].material_override=clay
model.render.engine='CYCLES'; model.cycles.samples=24; model.cycles.use_denoising=True
model.cycles.device=scene.cycles.device
model.render.resolution_x=W; model.render.resolution_y=H; model.render.resolution_percentage=65
model.view_settings.view_transform='AgX'
model.render.filepath=str(ROOT/'output'/'Harbor_editable_geometry.png')
model['Purpose']='Independent geometric reconstruction. Source-depth surfaces are excluded. Clay override reveals actual mesh detail.'

readme=bpy.data.texts.new('START HERE · Harbor reconstruction')
readme.write('HARBOR / THE OTHER SIDE OF YESTERDAY\n\n'
 'Scene 01: source-matched camera projection. The original reference is packed in this file.\n'
 'Scene 02: editable independently modeled architecture, docks, ships, market props and water.\n'
 'The camera is calibrated to the original 1672 x 941 image.\n\n'
 'This is a 2.5D reconstruction. Exact appearance is preserved from the source camera.\n'
 'Hidden sides, roofs and back surfaces are approximations, and textures stretch when viewed from other angles.\n'
 'Semantic depth surfaces are isolated in collection 01. These preserve sky, mountains and fine source details.\n'
 'Hide that collection to inspect the independent modeled volumes, or switch to scene 02.\n'
 'Materials include procedural native surfaces. Set EXACT_REFERENCE in the shared REFERENCE PROJECTION node group to 0 to relight them.\n'
 'Source texture and reference camera background are embedded. No downloads or external assets are required.\n')
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
            area.spaces.active.clip_end=600
            area.spaces.active.overlay.show_overlays=False
bpy.context.window.scene=scene
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'output'/'Yesterday_Harbor.blend'))
print('Saved blend with %d objects'%len(bpy.data.objects),flush=True)
try:
    bpy.ops.render.render(write_still=True,scene=scene.name)
except RuntimeError as error:
    print('GPU render failed; retrying on CPU:',error,flush=True)
    scene.cycles.device='CPU'
    bpy.ops.render.render(write_still=True,scene=scene.name)
print('SOURCE MATCH RENDER COMPLETE',flush=True)
try:
    bpy.ops.render.render(write_still=True,scene=model.name)
except RuntimeError as error:
    print('GPU render failed; retrying on CPU:',error,flush=True)
    model.cycles.device='CPU'
    bpy.ops.render.render(write_still=True,scene=model.name)
print('GEOMETRY RENDER COMPLETE',flush=True)
