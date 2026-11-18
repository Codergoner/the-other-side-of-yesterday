"""Additive M1 domestic/frontage kit. Run with Blender --background --python.

Every build has its own directory; no existing house, harbor, mesh or .blend is
opened or overwritten. Geometry is metric, reusable, and preserves editable parts.
"""
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
import bpy, bmesh, math, random, json, hashlib, struct, zlib
from mathutils import Vector

ROOT=Path(__file__).resolve().parent
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
OUT=ROOT/'output'/'brief_kit';BUILD=OUT/'builds'/STAMP
for p in [BUILD/'meshes',BUILD/'textures',BUILD/'previews']:p.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
SC=bpy.context.scene;SC.name='Brief M1 · maintained domestic and frontage kit'
SC.unit_settings.system='METRIC';SC.unit_settings.scale_length=1
SRC=bpy.data.collections.new('AUTHORING · additive editable kit');SC.collection.children.link(SRC)
EXP=bpy.data.collections.new('GAME · reusable semantic batches');SC.collection.children.link(EXP)
COL=bpy.data.collections.new('COLLISION · named simple proxies');SC.collection.children.link(COL)
R=random.Random(251025);PARTS=defaultdict(list);PROXIES=defaultdict(list)

def png(path,w,h,data):
 def chunk(kind,payload):return struct.pack('!I',len(payload))+kind+payload+struct.pack('!I',zlib.crc32(kind+payload)&0xffffffff)
 raw=b''.join(b'\0'+bytes(data[y*w*3:(y+1)*w*3]) for y in range(h))
 path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw,8))+chunk(b'IEND',b''))

DEFS={
 'Wood':{'rgb':[133,91,58],'roughness':.79,'pattern':'wood'},
 'Stone':{'rgb':[168,158,135],'roughness':.88,'pattern':'stone'},
 'Terracotta':{'rgb':[165,84,48],'roughness':.86,'pattern':'stone'},
 'CreamCloth':{'rgb':[201,190,163],'roughness':.94,'pattern':'cloth'},
 'TealCloth':{'rgb':[62,103,97],'roughness':.94,'pattern':'cloth'},
 'Ceramic':{'rgb':[224,211,179],'roughness':.31},
 'Iron':{'rgb':[74,80,74],'roughness':.58,'metallic':.65},
 'Brass':{'rgb':[150,112,55],'roughness':.50,'metallic':.65},
 'Leaf':{'rgb':[62,96,43],'roughness':.88,'two_sided':True},
 'LeafLight':{'rgb':[92,119,53],'roughness':.88,'two_sided':True},
 'Flower':{'rgb':[239,226,191],'roughness':.86},
 'FlowerCenter':{'rgb':[184,144,55],'roughness':.88},
 'Soil':{'rgb':[53,45,33],'roughness':1},
 'Paper':{'rgb':[220,208,173],'roughness':.91},
 'Ink':{'rgb':[58,67,61],'roughness':.87},
}
M={}
for key,spec in DEFS.items():
 name='M_Brief_'+key;mat=bpy.data.materials.new(name);mat.use_nodes=True
 bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*(c/255 for c in spec['rgb']),1)
 bs.inputs['Roughness'].default_value=spec['roughness'];bs.inputs['Metallic'].default_value=spec.get('metallic',0)
 spec['name']=name
 if spec.get('pattern'):
  pix=bytearray();rough=bytearray();w=h=256
  for y in range(h):
   for x in range(w):
    u=x/w;v=y/h;noise=math.sin(math.tau*(u*5+v*3))*1.9+math.sin(math.tau*(u*17-v*11))*.9
    if spec['pattern']=='wood':noise+=math.sin(math.tau*(u*12+.12*math.sin(math.tau*v*2)))*5+math.sin(math.tau*(u*37+v*.0))*1.5
    if spec['pattern']=='cloth':noise+=(x%3==0)*2+(y%3==0)*2
    pix.extend(max(0,min(255,round(c+noise))) for c in spec['rgb'])
    rr=max(0,min(255,round(spec['roughness']*255+noise*.45)));rough.extend([rr]*3)
  for suffix,data in [('BaseColor',pix),('Roughness',rough)]:
   path=BUILD/'textures'/f'{name}_{suffix}.png';png(path,w,h,data);spec[suffix.lower()]=str(path.relative_to(OUT)).replace('\\','/')
  image=bpy.data.images.load(str(BUILD/'textures'/f'{name}_BaseColor.png'));image.pack();node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=image;mat.node_tree.links.new(node.outputs['Color'],bs.inputs['Base Color'])
 M[key]=mat

def uv_metric(data):
 data.update();uv=data.uv_layers.new(name='UV0_Metric')
 for f in data.polygons:
  axis=max(range(3),key=lambda i:abs(f.normal[i]));axes=((1,2),(0,2),(0,1))[axis]
  for li in f.loop_indices:
   co=data.vertices[data.loops[li].vertex_index].co;uv.data[li].uv=(co[axes[0]]*2,co[axes[1]]*2)

def mesh(group,label,verts,faces,key='Wood',smooth=False):
 data=bpy.data.meshes.new(label);data.from_pydata(verts,[],faces);data.update();data.materials.append(M[key]);uv_metric(data)
 if smooth:
  for p in data.polygons:p.use_smooth=True
 obj=bpy.data.objects.new(label,data);SRC.objects.link(obj);PARTS[group].append(obj);return obj

BOXF=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
def box(group,label,at,size,key='Wood',bevel=.008,collision=False):
 c=Vector(at);h=Vector(size)*.5;vv=[c+Vector((x*h.x,y*h.y,z*h.z)) for x,y,z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
 obj=mesh(group,label,vv,BOXF,key)
 if bevel and min(size)>.015:
  mod=obj.modifiers.new('Restrained worn edge','BEVEL');mod.width=min(bevel,min(size)*.15);mod.segments=2
 if collision:proxy_box(group,at,size)
 return obj

def proxy_box(group,at,size):
 c=Vector(at);h=Vector(size)*.5;vv=[c+Vector((x*h.x,y*h.y,z*h.z)) for x,y,z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
 data=bpy.data.meshes.new('simple collision');data.from_pydata(vv,[],BOXF);data.update();obj=bpy.data.objects.new(f'UBX_{group}_{len(PROXIES[group]):03d}',data);COL.objects.link(obj);obj.hide_render=True;PROXIES[group].append(obj)

def beam(group,label,a,b,width=.04,depth=None,key='Wood'):
 a,b=Vector(a),Vector(b);d=b-a;rot=d.to_track_quat('Z','Y').to_matrix();mid=(a+b)*.5;dd=depth or width
 vv=[mid+rot@Vector((x*width*.5,y*dd*.5,z*d.length*.5)) for x,y,z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
 return mesh(group,label,vv,BOXF,key)

def lathe(group,label,profile,key='Terracotta',n=20):
 vv=[(max(r,.0005)*math.cos(i*math.tau/n),max(r,.0005)*math.sin(i*math.tau/n),z) for z,r in profile for i in range(n)]
 ff=[(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i) for j in range(len(profile)-1) for i in range(n)]
 return mesh(group,label,vv,ff,key,True)

def ring(group,label,center,radius,thickness,key='Iron',axis='Y',n=20):
 c=Vector(center);vv=[]
 for j in range(n):
  a=j*math.tau/n
  for i in range(6):
   b=i*math.tau/6;p=Vector(((radius+thickness*math.cos(b))*math.cos(a),thickness*math.sin(b),(radius+thickness*math.cos(b))*math.sin(a)))
   if axis=='Z':p=Vector((p.x,p.z,p.y))
   vv.append(c+p)
 ff=[(j*6+i,j*6+(i+1)%6,((j+1)%n)*6+(i+1)%6,((j+1)%n)*6+i) for j in range(n) for i in range(6)]
 return mesh(group,label,vv,ff,key,True)

def ellipsoid(group,label,c,size,key,n=10,rings=5):
 c=Vector(c);s=Vector(size);vv=[]
 for j in range(rings+1):
  p=-math.pi*.5+math.pi*j/rings
  for i in range(n):
   a=math.tau*i/n;vv.append(c+Vector((math.cos(p)*math.cos(a)*s.x,math.cos(p)*math.sin(a)*s.y,math.sin(p)*s.z)))
 return mesh(group,label,vv,[(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i) for j in range(rings) for i in range(n)],key,True)

def chair(group,repaired=False):
 for x in [-.20,.20]:
  for y in [-.19,.19]:beam(group,'Turned oak leg',(x*1.08,y*1.08,.025),(x,y,.47),.055,.055)
 for i in range(5):box(group,'Separate seat plank',(-.192+i*.096,0,.465),(.09,.48,.045),bevel=.007)
 for x in [-.21,.21]:
  box(group,'Oak back upright',(x,.215,.69),(.055,.055,.74))
  beam(group,'Side stretcher',(x,-.19,.19),(x,.19,.19),.035)
 for z in [.63,.80,.98]:box(group,'Shaped back rail',(0,.23,z),(.48,.047,.065))
 for y in [-.19,.19]:beam(group,'Underseat stretcher',(-.2,y,.21),(.2,y,.21),.035)
 if repaired:
  beam(group,'Hand repaired diagonal',(-.2,.205,.50),(.19,.205,.90),.034,.024)
  box(group,'Repair metal strap',(-.20,.19,.22),(.075,.067,.045),'Iron',.003)
  box(group,'Clean seat pad',(0,-.015,.503),(.41,.39,.026),'CreamCloth',.015)
 proxy_box(group,(0,0,.23),(.45,.45,.46));proxy_box(group,(0,.225,.77),(.49,.07,.58))
chair('SM_Brief_ChairRepaired',True);chair('SM_Brief_ChairEmpty')

g='SM_Brief_CleanCup';lathe(g,'Glazed hollow ceramic cup',[(0,0),(0,.055),(.012,.065),(.13,.073),(.14,.072),(.14,.063),(.125,.062),(.025,.051),(.018,0)],'Ceramic',24)
ring(g,'Cup handle',(.087,0,.078),.040,.009,'Ceramic','Y',16)
g='SM_Brief_ClothTray';box(g,'Tray base',(0,0,.012),(.47,.31,.024),bevel=.01)
for x in [-.23,.23]:box(g,'Tray end rim',(x,0,.038),(.026,.31,.05))
for y in [-.15,.15]:box(g,'Tray side rim',(0,y,.038),(.45,.026,.05))
for k in range(5):box(g,'Folded clean linen',(-.08+k*.033,-.01,.036+k*.001),(.04,.24,.016),'CreamCloth',.006)

g='SM_Brief_CoatHook';box(g,'Hook wall backing',(0,.02,.88),(.13,.035,.27))
beam(g,'Repaired hook stem',(0,0,.96),(0,-.11,.97),.018,key='Iron');ring(g,'Hook bend',(0,-.105,.93),.035,.009,'Iron','Y',12)
for side in [-1,1]:
 vv=[]
 for j in range(9):
  z=.10+j*.095
  for i in range(6):
   x=side*(.015+i*.039)*(1-.12*j/8);y=-.07-.045*math.sin(i*1.5+j*.35)
   vv.append((x,y,z))
 mesh(g,'Hanging folded coat panel',vv,[(j*6+i,j*6+i+1,(j+1)*6+i+1,(j+1)*6+i) for j in range(8) for i in range(5)],'TealCloth')
 beam(g,'Hanging sleeve',(.20*side,-.07,.77),(.29*side,-.08,.37),.11,.08,'TealCloth')
for z in [.34,.49,.64]:ellipsoid(g,'Plain coat button',(0,-.115,z),(.012,.008,.012),'Iron',8,4)

def flowers(group,base,count=8,spread=.24,height=.52):
 base=Vector(base)
 for k in range(count):
  a=k*math.tau/count+R.uniform(-.12,.12);end=base+Vector((math.cos(a)*spread,math.sin(a)*spread,height*R.uniform(.72,1.15)))
  beam(group,'Living plant stem',base,end,.009,key='Leaf')
  for j in range(3):
   p=base.lerp(end,.32+j*.20);u=Vector((math.cos(a+j),math.sin(a+j),.4))*.12;q=Vector((-u.y,u.x,.02))*.48
   vv=[p,p+u*.5+q,p+u,p+u*.5-q,p+u*.48+Vector((0,0,.017))]
   mesh(group,'Broad flower leaf',vv,[(0,1,4),(1,2,4),(2,3,4),(3,0,4)],'LeafLight' if k%3==0 else 'Leaf')
  for petal in range(5):
   b=petal*math.tau/5;at=end+Vector((math.cos(b)*.025,math.sin(b)*.025,0))
   ellipsoid(group,'Cream flower petal',at,(.027,.022,.008),'Flower',8,4)
  ellipsoid(group,'Flower center',end+Vector((0,0,.006)),(.014,.014,.01),'FlowerCenter',8,4)

g='SM_Brief_FlowerPlanter';lathe(g,'Thick terracotta planter',[(0,0),(0,.18),(.04,.22),(.38,.27),(.48,.28),(.51,.29),(.54,.29),(.54,.245),(.48,.24),(.14,.15),(.08,0)],n=24)
lathe(g,'Planter soil',[(.43,0),(.43,.23),(.44,.23),(.44,0)],'Soil',20);flowers(g,(0,0,.44),9,.24,.56);proxy_box(g,(0,0,.255),(.53,.53,.51))
g='SM_Brief_WindowBox';box(g,'Window box bottom',(0,-.14,.025),(.96,.30,.05))
for x in [-.46,.46]:box(g,'Window box end',(x,-.14,.12),(.04,.30,.23))
for y in [0,-.28]:box(g,'Window box front or rear',(0,y,.12),(.96,.035,.23))
for x in [-.31,-.1,.12,.32]:flowers(g,(x,-.14,.19),4,.12,.26)

def awning(group,depth):
 w=2.15
 beam(group,'Awning wall rail',(-w*.5,0,.4),(w*.5,0,.4),.09)
 beam(group,'Awning leading rail',(-w*.5,-depth,0),(w*.5,-depth,0),.075)
 for x in [-w*.45,w*.45]:beam(group,'Supported diagonal bracket',(x,0,-.30),(x,-depth+.05,-.02),.055)
 vv=[];cols=19;rows=7
 for j in range(rows):
  t=j/(rows-1)
  for i in range(cols):
   xx=-w*.5+w*i/(cols-1);zz=.42*(1-t)-.075*math.sin(math.pi*t)+.025*math.sin(i*1.45)
   vv.append((xx,-depth*t,zz))
 mesh(group,'Woven supported canvas',vv,[(j*cols+i,j*cols+i+1,(j+1)*cols+i+1,(j+1)*cols+i) for j in range(rows-1) for i in range(cols-1)],'TealCloth' if depth>.5 else 'CreamCloth')
 for i in range(12):
  x=-w*.5+i*w/12
  mesh(group,'Short canvas valance',[(x,-depth,.02),(x+w/12,-depth,.02),(x+w/12,-depth,-.11),(x,-depth,-.10)],[(0,1,2,3)],'TealCloth' if depth>.5 else 'CreamCloth')
awning('SM_Brief_AwningOpen',1.14);awning('SM_Brief_AwningFolded',.28)

g='SM_Brief_SupplySign';box(g,'Restrained timber sign',(0,0,0),(.62,.075,.43),bevel=.018)
box(g,'Painted canvas inset',(0,-.041,0),(.50,.009,.31),'CreamCloth',.003)
for x in [-.24,.24]:ring(g,'Sign hanging eye',(x,0,.27),.034,.008,'Iron','Y',12)
for x in [-.09,0,.09]:box(g,'Parcel mark',(x,-.052,0),(.075,.009,.16),'TealCloth',.002)
box(g,'Parcel tying stripe',(0,-.061,0),(.27,.008,.022),'CreamCloth',.001)

def crate(group,filled=False):
 for i in range(4):box(group,'Open crate floor',(-.20+i*.135,0,.025),(.125,.40,.05))
 for x in [-.265,.265]:
  for y in [-.18,.18]:box(group,'Crate corner batten',(x,y,.19),(.045,.045,.38))
 for z in [.095,.21,.325]:
  for y in [-.20,.20]:box(group,'Crate face slat',(0,y,z),(.57,.035,.085))
  for x in [-.27,.27]:box(group,'Crate end slat',(x,0,z),(.035,.40,.085))
 if filled:
  for x,y in [(-.16,-.08),(0,-.08),(.16,-.08),(-.10,.08),(.09,.08)]:ellipsoid(group,'Mundane store produce',(x,y,.34),(.075,.07,.075),'FlowerCenter',10,5)
 proxy_box(group,(0,0,.19),(.58,.44,.38))
crate('SM_Brief_CrateEmpty');crate('SM_Brief_CrateSupplies',True)

g='SM_Brief_LatchRepair';box(g,'Hand repaired latch backing',(0,0,0),(.19,.024,.075),'Wood',.006)
box(g,'Iron latch strap',(0,-.018,0),(.15,.014,.026),'Iron',.003)
for x in [-.067,.067]:ellipsoid(g,'Plain latch rivet',(x,-.029,0),(.009,.005,.009),'Iron',8,4)
ring(g,'Latch lifting ring',(.035,-.04,-.028),.025,.006,'Iron','Y',14)

g='SM_Brief_WorkshopSketch';box(g,'Unrevealing engineering paper',(0,0,.003),(.32,.23,.006),'Paper',.001)
for radius in [.042,.066]:ring(g,'Drawn calibration circle',(-.045,0,.007),radius,.0012,'Ink','Z',24)
for i in range(12):
 a=i*math.tau/12;beam(g,'Drawn dial tick',(-.045+math.cos(a)*.068,math.sin(a)*.068,.007),(-.045+math.cos(a)*.079,math.sin(a)*.079,.007),.0015,.0015,'Ink')
for y in [-.058,-.025,.008,.04]:beam(g,'Unlettered measurement line',(.055,y,.007),(.135,y,.007),.0015,.0015,'Ink')

# Export one mesh per semantic prop; every authoring part remains editable.
bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();assets=[]
for group,objects in PARTS.items():
 vv=[];ff=[];uvs=[];face_mats=[];materials=[]
 for obj in objects:
  ev=obj.evaluated_get(deps);data=ev.to_mesh(preserve_all_data_layers=True,depsgraph=deps);offset=len(vv);vv.extend(obj.matrix_world@v.co for v in data.vertices);layer=data.uv_layers.active
  remap=[]
  for mat in data.materials:
   mat=mat.original if getattr(mat,'is_evaluated',False) else mat
   if mat not in materials:materials.append(mat)
   remap.append(materials.index(mat))
  for face in data.polygons:
   ff.append(tuple(offset+data.loops[li].vertex_index for li in face.loop_indices));uvs.extend(tuple(layer.data[li].uv) if layer else (0,0) for li in face.loop_indices);face_mats.append(remap[face.material_index])
  ev.to_mesh_clear()
 data=bpy.data.meshes.new(group);data.from_pydata(vv,[],ff);data.update();obj=bpy.data.objects.new(group,data);EXP.objects.link(obj)
 for mat in materials:data.materials.append(mat)
 layer=data.uv_layers.new(name='UV0_Metric')
 for i,p in enumerate(uvs):layer.data[i].uv=p
 for face,mi in zip(data.polygons,face_mats):face.material_index=mi
 bm=bmesh.new();bm.from_mesh(data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001);bmesh.ops.triangulate(bm,faces=list(bm.faces));bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free();data.update()
 bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
 for proxy in PROXIES[group]:proxy.select_set(True)
 file=BUILD/'meshes'/f'{group}.fbx'
 bpy.ops.export_scene.fbx(filepath=str(file),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',global_scale=1,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',use_mesh_modifiers=True,add_leaf_bones=False,bake_anim=False,path_mode='RELATIVE',embed_textures=False,mesh_smooth_type='FACE')
 assets.append({'name':group,'file':str(file.relative_to(OUT)).replace('\\','/'),'materials':[m.name for m in materials],'triangles':len(data.polygons),'collision_count':len(PROXIES[group]),'bounds_m':{'min':[min(v.co[i] for v in data.vertices) for i in range(3)],'max':[max(v.co[i] for v in data.vertices) for i in range(3)]}})
 print('BRIEF_KIT',group,len(data.polygons),flush=True)
SRC.hide_render=True;SRC.hide_viewport=True;COL.hide_render=True;COL.hide_viewport=True
SC['Scope']='Additive M1/M2 prop kit, not final character/whole-city art';SC['BuildStamp']=STAMP
text=bpy.data.texts.new('READ ME · reversible kit');text.write('Original house/city untouched. This unique build contains reusable metric props, tileable source textures, editable components and named low-cost collision. Front is -Y. No figures or NPC identities are included.\n')
bpy.ops.wm.save_as_mainfile(filepath=str(BUILD/'Brief_Domestic_Frontage_Kit.blend'))
manifest={'schema_version':1,'name':'Brief M1 domestic/frontage kit','build_stamp':STAMP,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'units':'meters','axes':'Blender X,Y,Z -> Unreal X,-Y,Z; native default yaw -90','assets':assets,'material_definitions':{v['name']:v for v in DEFS.values()},'blend_file':str((BUILD/'Brief_Domestic_Frontage_Kit.blend').relative_to(OUT)).replace('\\','/'),'triangles':sum(a['triangles'] for a in assets),'notes':['Only new versioned build directory written; house and city sources are not loaded.','Props batch into semantic meshes; ornament has no runtime actor per leaf or plank.','Characters and whole-city era finish remain outside this scoped kit.']}
(BUILD/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('BRIEF_KIT_COMPLETE',json.dumps({'assets':len(assets),'triangles':manifest['triangles'],'manifest':str(OUT/'manifest.json')}),flush=True)
