"""Build an editable, game-scale player home from the supplied visual reference."""
import bpy, bmesh, math, random, json, sys
from pathlib import Path
from collections import defaultdict
from mathutils import Vector, Euler

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'/'house'
for p in [OUT,OUT/'meshes',OUT/'previews']:p.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
R=random.Random(2481)
bpy.ops.wm.read_factory_settings(use_empty=True)
S=bpy.context.scene;S.name='Your House · Harbor Home';S.unit_settings.system='METRIC'
S['Description']='Reference-based freestanding player home, real geometry, enterable ground and upper floor'
def collection(name):
 c=bpy.data.collections.new(name);S.collection.children.link(c);return c
SRC=collection('AUTHORING · editable house pieces');EXP=collection('GAME · semantic meshes');COL=collection('COLLISION · convex proxies');SET=collection('PREVIEW · lights and cameras')
parts=defaultdict(list);proxies=defaultdict(list)
specs=json.loads((ROOT/'output/game/textures/materials.json').read_text())
names={'plaster':'M_Plaster','stone':'M_Stone','wood':'M_Wood','roof':'M_Roof','dark':'M_Dark','metal':'M_Metal','leaf':'M_Leaf','fabric':'M_CanvasBlue','terracotta':'M_Terracotta','cobble':'M_Cobble'}
M={}
for key,name in names.items():
 mat=bpy.data.materials.new(name);mat.use_nodes=True;n=mat.node_tree.nodes;l=mat.node_tree.links;p=n.get('Principled BSDF');sp=specs[name]
 p.inputs['Metallic'].default_value=sp['metallic']
 for suffix,socket in [('base_color','Base Color'),('roughness','Roughness'),('normal','Normal')]:
  t=n.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(ROOT/'output/game/textures'/sp[suffix]));t.image.pack()
  if suffix!='base_color':t.image.colorspace_settings.name='Non-Color'
  if suffix=='normal':
   normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.6;l.new(t.outputs['Color'],normal.inputs['Color']);l.new(normal.outputs[0],p.inputs[socket])
  else:l.new(t.outputs['Color'],p.inputs[socket])
 M[key]=mat
custom={'M_HomeFlower':{'color':[.83,.72,.44],'roughness':.83},'M_HomeGlow':{'color':[1,.58,.12],'roughness':.4,'emission':[1,.58,.12],'emission_strength':3},'M_HomeTeal':{'color':[.105,.23,.225],'roughness':.76},'M_HomeLinen':{'color':[.64,.56,.42],'roughness':.9}}
for name,spec in custom.items():
 mat=bpy.data.materials.new(name);mat.use_nodes=True;p=mat.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*spec['color'],1);p.inputs['Roughness'].default_value=spec['roughness']
 if spec.get('emission'):p.inputs['Emission Color'].default_value=(*spec['emission'],1);p.inputs['Emission Strength'].default_value=spec['emission_strength']
 M[{'M_HomeFlower':'flower','M_HomeGlow':'glow','M_HomeTeal':'teal','M_HomeLinen':'linen'}[name]]=mat
M['lantern']=M['glow'];M['shutter']=M['teal']

def uv_metric(data):
 data.update();uv=data.uv_layers.new(name='UV0_Metric')
 for f in data.polygons:
  axis=max(range(3),key=lambda a:abs(f.normal[a]));ax=((1,2),(0,2),(0,1))[axis]
  for li in f.loop_indices:
   v=data.vertices[data.loops[li].vertex_index].co;uv.data[li].uv=(v[ax[0]]*.5,v[ax[1]]*.5)
def mesh(name,verts,faces,mat,group='SM_Home_Shell',collision=False,kind='UCX'):
 data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.update()
 obj=bpy.data.objects.new(name,data);SRC.objects.link(obj)
 if mat:data.materials.append(mat)
 uv_metric(data);parts[group].append(obj)
 if collision:
  proxy=bpy.data.objects.new('%s_%s_%03d'%(kind,group,len(proxies[group])),data.copy());COL.objects.link(proxy);proxy.hide_render=True;proxy.display_type='WIRE';proxies[group].append(proxy)
 return obj
def box(name,loc,size,mat,group='SM_Home_Shell',collision=False,bevel=.025):
 x,y,z=[s/2 for s in size];c=Vector(loc)
 verts=[c+Vector(p) for p in [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]]
 obj=mesh(name,verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],mat,group,collision,'UBX')
 if bevel and min(size)>.06:
  mod=obj.modifiers.new('Worn edges','BEVEL');mod.width=min(bevel,min(size)*.18);mod.segments=2
 return obj
def timber(name,a,b,width=.16,depth=.16,mat=None,group='SM_Home_Timber',collision=False):
 a,b=Vector(a),Vector(b);d=b-a
 if d.length<1e-5:return
 rot=d.to_track_quat('Z','Y').to_matrix();mid=(a+b)/2
 verts=[mid+rot@Vector((x*width/2,y*depth/2,z*d.length/2)) for x,y,z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
 return mesh(name,verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],mat or M['wood'],group,collision)
def cylinder(name,loc,radius,depth,mat,vertices=12,group='SM_Home_Details'):
 verts=[(loc[0]+radius*math.cos(i*math.tau/vertices),loc[1]+radius*math.sin(i*math.tau/vertices),loc[2]+z) for z in [-depth/2,depth/2] for i in range(vertices)]
 faces=[tuple(range(vertices-1,-1,-1)),tuple(range(vertices,vertices*2))]+[(i,(i+1)%vertices,(i+1)%vertices+vertices,i+vertices) for i in range(vertices)]
 return mesh(name,verts,faces,mat,group)
def front_panel(x0,x1,z0,z1,group='SM_Home_Shell',mat=None,y=-3.6,thickness=.26,collision=True):
 return box('Limewashed front wall',((x0+x1)/2,y,(z0+z1)/2),(x1-x0,thickness,z1-z0),mat or M['plaster'],group,collision)
def perforated_front(x0,x1,z0,z1,holes,y=-3.6):
 # Rectangular apertures are genuine openings, surrounded later by arched trim.
 xx=sorted(set([x0,x1]+[h[0] for h in holes]+[h[1] for h in holes]))
 zz=sorted(set([z0,z1]+[h[2] for h in holes]+[h[3] for h in holes]))
 for a,b in zip(xx,xx[1:]):
  for c,d in zip(zz,zz[1:]):
   if any(h[0]<(a+b)/2<h[1] and h[2]<(c+d)/2<h[3] for h in holes):continue
   front_panel(a,b,c,d,y=y)

# Limestone platform; broad usable approach, sitting terrace and continuous stairs.
box('House bedrock plinth',(.4,-.1,.35),(10.4,8,.7),M['stone'],'SM_Home_Foundation',True,.06)
box('Raised porch limestone base',(-.6,-4.6,.67),(8.5,2.65,.96),M['stone'],'SM_Home_Foundation',True,.05)
box('Porch paved top',(-.6,-4.6,1.10),(8.6,2.75,.10),M['stone'],'SM_Home_Foundation',True,.025)
for i in range(6):
 z=(i+1)*1.15/6;y=-7.9+(i+.5)*2.1/6
 box('Entry stair worn tread',(.6,y,z-.09),(3.35,.37,.18),M['stone'],'SM_Home_Approach',False,.025)
# Solid convex ramp, decorative risers above it.
verts=[(-1.075,-7.9,0),(2.275,-7.9,0),(2.275,-5.8,1.15),(-1.075,-5.8,1.15),(-1.075,-7.9,-.2),(2.275,-7.9,-.2),(2.275,-5.8,-.2),(-1.075,-5.8,-.2)]
mesh('Continuous approach stair collision',verts,[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)],M['stone'],'SM_Home_Approach',True)
# Staggered individual paving slabs on terrace, a low left retaining wall.
for row in range(5):
 for col in range(14):
  x=-4.6+col*.6+(row%2)*.3
  if x>3.5:continue
  box('Hand laid porch paving',(x,-5.7+row*.48,1.165+R.uniform(-.012,.012)),(.565,.45,.07),M['stone'],'SM_Home_Paving',False,.018)
for i in range(6):
 box('Left terrace wall cap',(-4.75,-5.8+i*.48,1.57),(.38,.46,.3),M['stone'],'SM_Home_Foundation',True,.035)

# Two storey main house with true doors, windows and an interior stair opening.
perforated_front(-4.2,2.1,1.15,4.24,[(-3.25,-2.15,1.85,3.28),(.025,1.175,1.15,3.45)])
perforated_front(-4.2,2.1,4.24,7.15,[(-2.4,-.9,4.30,6.40),(.45,1.55,4.95,6.60)])
box('Main left wall',(-4.2,-.45,4.15),(.28,6.55,6),M['plaster'],'SM_Home_Shell',True)
box('Main rear wall',(-1.05,2.7,4.15),(6.3,.28,6),M['plaster'],'SM_Home_Shell',True)
# Side doorway into the ruined wing, wide enough for a player capsule.
for cy,sy in [(-2.15,2.9),(2.0,1.4)]:box('Side wall flank',(2.1,cy,4.15),(.28,sy,6),M['plaster'],'SM_Home_Shell',True)
box('Side doorway lintel',(2.1,.7,5.2),(.28,1.45,3.9),M['plaster'],'SM_Home_Shell',True)
box('Ground floor solid support',(-1.05,-.45,1.02),(6.3,6.3,.26),M['stone'],'SM_Home_Floors',True)
# Upper stair landing leaves a full metre of turning space before the rear wall.
for loc,size in [((-.0,-.45,4.18),(4.0,6.3,.24)),((-3.95,-.45,4.18),(.5,6.3,.24)),((-2.85,-3.08,4.18),(1.7,1.04,.24)),((-2.85,2.14,4.18),(1.7,1.15,.24))]:box('Upper oak floor support',loc,size,M['wood'],'SM_Home_Floors',True,.012)
# Narrow irregular floorboards, except the shaft.
for x in [(-4.04+i*.22) for i in range(28)]:
 for a,b in [(-3.42,2.53)] if x>-2.0 or x<-3.7 else [(-3.42,-2.8),(1.70,2.53)]:
  if b-a>.02:box('Upstairs floorboard',(x,(a+b)/2,4.315),(.205,b-a,.035),M['wood'],'SM_Home_Interior',False,.006)
for i in range(18):
 y=-2.72+(i+.5)*4.37/18;z=1.15+(i+1)*3.15/18
 box('Interior stair timber tread',(-2.85,y,z-.05),(1.45,.30,.1),M['wood'],'SM_Home_Staircase',False,.012)
verts=[(-3.57,-2.72,1.15),(-2.13,-2.72,1.15),(-2.13,1.65,4.3),(-3.57,1.65,4.3),(-3.57,-2.72,.95),(-2.13,-2.72,.95),(-2.13,1.65,4.08),(-3.57,1.65,4.08)]
mesh('Continuous interior stair ramp',verts,[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)],M['wood'],'SM_Home_Staircase',True)
for x in [-3.58,-2.10]:
 timber('Stair handrail',(x,-2.7,2.13),(x,1.65,5.3),.075,.075,group='SM_Home_Staircase')
 for i in range(9):
  y=-2.7+i*.54;z=1.15+(y+2.72)*3.15/4.37
  timber('Stair rail baluster',(x,y,z+.05),(x,y,z+.95),.05,.05,group='SM_Home_Staircase')
box('Stairwell safety blocking',(-2.03,-.68,4.75),(.13,3.44,.9),M['wood'],'SM_Home_Staircase',True,.01)

# Timber frame and front attic gable, oversailing eaves with exposed rafter ends.
for x in [-4.12,-2.42,2.02]:
 box('Facade vertical oak frame',(x,-3.8,4.25),(.18,.20,5.9),M['wood'],'SM_Home_Timber',False,.025)
for z in [4.14,7.12]:box('Facade oak tie beam',(-1.05,-3.8,z),(6.65,.24,.24),M['wood'],'SM_Home_Timber',False,.025)
for y in [-3.72,2.8]:
 mesh('Attic limewash triangular gable',[(-4.2,y,7.12),(2.1,y,7.12),(-1.05,y,9.3),(-4.2,y+.18,7.12),(2.1,y+.18,7.12),(-1.05,y+.18,9.3)],[(0,1,2),(5,4,3),(0,3,4,1),(1,4,5,2),(2,5,3,0)],M['plaster'],'SM_Home_Shell',True)
 timber('Gable oak collar',(-4.4,y-.08,7.15),(2.3,y-.08,7.15),.19,.22)
 timber('Gable left bargeboard',(-4.8,y-.12,7.0),(-1.05,y-.12,9.52),.24,.26)
 timber('Gable right bargeboard',(-1.05,y-.12,9.52),(2.7,y-.12,7.0),.24,.26)
 timber('Attic kingpost',(-1.05,y-.16,7.15),(-1.05,y-.16,9.35),.16,.18)
 for x in [-3.1,.95]:timber('Gable diagonal brace',(x,y-.17,7.22),(-1.05,y-.17,8.5),.14,.14)
# Exposed oak rafters and separate overlapping slate tiles with irregular ends.
for j in range(12):
 y=-4.2+j*.68
 for edge in [-4.85,2.75]:timber('Roof rafter',(-1.05,y,9.3),(edge,y,6.95),.14,.18)
for side in [-1,1]:
 for row in range(13):
  t0=row/13;t1=min(1,(row+1.2)/13)
  for j in range(25):
   y=-4.3+j*.31+(row%2)*.15
   if y>3.35:continue
   # At the right rear, torn slate gives way to exposed rafters.
   if side==1 and t0>.60 and y>.5+R.uniform(-.18,.18):continue
   x0=-1.05+side*3.8*t0;x1=-1.05+side*3.8*t1
   z0=9.52-2.35*t0;z1=9.52-2.35*t1;w=.30;d=R.uniform(-.025,.025)
   mesh('Individual weathered teal slate',[(x0,y,z0+.015),(x1,y,z1+d),(x1,y+w,z1+d),(x0,y+w,z0+.015)],[(0,1,2,3)],M['roof'],'SM_Home_Slate')
for j in range(29):
 y=-4.3+j*.27
 # Rounded ridge covers, modeled with four pitches.
 verts=[]
 for yy in [y,y+.29]:
  for x,z in [(-1.27,9.50),(-1.18,9.64),(-1.05,9.68),(-.92,9.64),(-.83,9.50)]:verts.append((x,yy,z))
 mesh('Slate ridge cap',verts,[(i,i+1,i+6,i+5) for i in range(4)],M['roof'],'SM_Home_Slate')
for y in [-3.5,-1.8,0,1.7,2.8]:
 for x in [-4.2,2.1]:timber('Decorative eave knee bracket',(x,y,6.35),(x+(-.65 if x<0 else .65),y,7.05),.16,.16)
for i in range(7):box('Chimney cut limestone course',(-1.8,.6,9.02+i*.19),(.63,.66,.18),M['stone'],'SM_Home_Chimney',False,.025)
box('Chimney projecting cap',(-1.8,.6,10.30),(.85,.85,.2),M['stone'],'SM_Home_Chimney',False,.025)
box('Chimney soot opening',(-1.8,.6,10.415),(.48,.48,.03),M['dark'],'SM_Home_Chimney',False,0)

# Balcony across the intact left facade, with turned-style balusters and banner.
box('Balcony structural deck',(-2.0,-4.57,4.19),(4.65,1.65,.22),M['wood'],'SM_Home_Balcony',True,.025)
for i in range(21):box('Balcony deck plank',(-4.24+i*.22,-4.57,4.325),(.21,1.7,.04),M['wood'],'SM_Home_Balcony',False,.008)
for x in [-4.35,.35]:
 box('Balcony corner post',(x,-5.34,4.85),(.22,.22,1.23),M['wood'],'SM_Home_Balcony',False,.02)
 for y in [-5.22,-3.85]:
  timber('Balcony diagonal structural bracket',(x,y,3.15),(x,-4.7,4.1),.18,.18)
 box('Balcony side rail',(x,-4.55,5.35),(.15,1.65,.15),M['wood'],'SM_Home_Balcony',False,.015)
 box('Balcony side blocking',(x,-4.55,4.85),(.14,1.55,1.02),M['wood'],'SM_Home_Balcony',True,.01).hide_render=True
for z in [4.48,5.36]:box('Balcony horizontal rail',(-2,-5.34,z),(4.9,.16,.16),M['wood'],'SM_Home_Balcony',False,.018)
for i in range(20):
 x=-4.22+i*.235
 for z,r,h in [(4.57,.045,.18),(4.79,.065,.27),(5.08,.045,.28)]:cylinder('Balcony shaped baluster',(x,-5.34,z),r,h,M['wood'],8,'SM_Home_Balcony')
box('Balcony front safety collision',(-2,-5.34,4.87),(4.7,.14,.98),M['wood'],'SM_Home_Balcony',True,0).hide_render=True
# Banner gently folded on front rail; simple hand-cut gold sun crest.
banner=[]
for j in range(9):
 z=5.36-j*.18
 for i in range(6):banner.append((-2.45+i*.20,-5.46-.055*math.sin(i*1.7+j*.4),z+(0 if j<8 else .08*abs(i-2.5))))
mesh('Teal balcony hanging banner',banner,[(j*6+i,j*6+i+1,(j+1)*6+i+1,(j+1)*6+i) for j in range(8) for i in range(5)],M['teal'],'SM_Home_Banner')
for i in range(16):
 a=i*math.tau/16;b=(i+1)*math.tau/16
 timber('Banner embroidered crest',(-1.95+.23*math.cos(a),-5.53,4.76+.23*math.sin(a)),(-1.95+.23*math.cos(b),-5.53,4.76+.23*math.sin(b)),.018,.012,M['flower'],'SM_Home_Banner')
for i in range(8):
 a=i*math.tau/8
 timber('Crest sunray',(-1.95+.27*math.cos(a),-5.53,4.76+.27*math.sin(a)),(-1.95+.33*math.cos(a),-5.53,4.76+.33*math.sin(a)),.013,.013,M['flower'],'SM_Home_Banner')

# The porch canopy is real folded canvas, with ripped lower edge and framing.
for x in [-3.8,1.72]:
 timber('Porch full height front post',(x,-5.6,1.18),(x,-5.6,3.6),.18,.18,group='SM_Home_Porch',collision=True)
 timber('Porch knee brace',(x,-5.6,2.7),(x,-4.9,3.48),.12,.12,group='SM_Home_Porch')
timber('Porch canopy leading beam',(-4.1,-5.68,3.50),(2.0,-5.68,3.50),.17,.18,group='SM_Home_Porch')
for i in range(7):timber('Porch canopy rafter',(-4.1+i*1.0,-3.68,4.03),(-4.1+i*1.0,-5.84,3.47),.09,.13,group='SM_Home_Porch')
verts=[]
for j in range(9):
 t=j/8
 for i in range(26):
  x=-4.14+i*.25;y=-3.68-2.25*t;z=4.08-.58*t-.13*math.sin(t*math.pi)+.035*math.sin(i*1.7)
  if j==8:z-=.05+(i%5)*.035
  verts.append((x,y,z))
mesh('Sagging teal porch canvas',verts,[(j*26+i,j*26+i+1,(j+1)*26+i+1,(j+1)*26+i) for j in range(8) for i in range(25) if not(j>6 and i in[1,9,19,22])],M['fabric'],'SM_Home_Porch')
for i in range(25):
 if i in [1,9,19,22]:continue
 x=-4.14+i*.25;z=3.43-(i%5)*.035
 mesh('Canopy torn valance',[(x,-5.93,z),(x+.23,-5.93,z),(x+.19,-5.93,z-R.uniform(.11,.34)),(x+.03,-5.93,z-R.uniform(.07,.24))],[(0,1,2,3)],M['fabric'],'SM_Home_Porch')
for x in [-3.8,1.72]:
 for z in [1.48,2.0]:timber('Porch side railing',(x,-5.65,z),(x,-3.8,z),.095,.095,group='SM_Home_Porch')

# Destroyed right wing: stair-stepped broken masonry, hollow interior and rafters.
box('Ruin wing ground floor',(3.7,-.45,1.02),(3.2,6.3,.26),M['stone'],'SM_Home_Ruin',True,.04)
for row in range(27):
 z=1.3+row*.22
 # Ragged front pier descends from intact corner, torn end changes at each course.
 left=2.10;end=2.76+.14*math.sin(row*.73)+(.35 if row<7 else 0)
 for x in [left+.18,end]:box('Exposed broken corner masonry',(x,-3.66+R.uniform(-.05,.05),z),(.37+R.uniform(-.06,.07),.39,.205),M['stone'],'SM_Home_Ruin',False,.035)
for i in range(12):
 x=3.05+i*.23;h=1.3+max(0,(x-4.2)*2.4)+R.uniform(-.2,.2)
 if 3.2<x<4.5:continue
 box('Jagged low front plaster pier',(x,-3.58,1.15+h/2),(.24,.27,h),M['plaster'],'SM_Home_Ruin',True,.03)
for i in range(17):
 y=-3.5+i*.38;h=2.5+1.2*math.sin((y+2)*.9)+R.uniform(-.3,.3)
 box('Torn right outer wall',(5.35,y,1.15+h/2),(.32,.4,h),M['plaster'],'SM_Home_Ruin',True,.04)
 for j in range(3):box('Torn wall exposed stones',(5.35+R.uniform(-.09,.09),y,1.15+h-.1-j*.22),(.43,.38,.20),M['stone'],'SM_Home_Ruin',False,.04)
box('Ruin rear wall',(3.7,2.7,3.0),(3.2,.28,3.7),M['plaster'],'SM_Home_Ruin',True)
# Bare upper roof joists, their splintered ends cantilever into the collapse.
for i in range(10):
 y=-3.6+i*.68
 timber('Broken ruin principal rafter',(1.9,y,7.22),(5.8+R.uniform(-.4,.4),y,5.8+R.uniform(-.2,.3)),.18,.21,group='SM_Home_Ruin')
for x in [2.7,3.6,4.6]:timber('Stripped roof purlin',(x,-3.95,7.30-(x-1.9)*.34),(x,3.0,7.30-(x-1.9)*.34),.15,.19,group='SM_Home_Ruin')
for i in range(5):
 y=-2.7+i*1.2
 timber('Lower ruin lean-to joist',(2.1,y,4.3),(5.95,y,3.45),.13,.17,group='SM_Home_Ruin')
for i in range(50):
 x=R.uniform(2.3,5.75);y=R.uniform(-3.2,2.5);z=1.25+max(0,(x-2.2)*.16)+R.uniform(0,.35)
 o=box('Collapsed pale limestone rubble',(x,y,z),(R.uniform(.15,.55),R.uniform(.18,.58),R.uniform(.12,.35)),M['stone'],'SM_Home_Rubble',False,.045)
 rotation=Euler((R.uniform(-.4,.4),R.uniform(-.3,.3),R.uniform(-3,3))).to_matrix();center=Vector((x,y,z))
 for v in o.data.vertices:v.co=center+rotation@(v.co-center)
for i in range(12):
 a=Vector((R.uniform(2.7,5.6),R.uniform(-3,2.3),R.uniform(1.25,1.7)));b=a+Vector((R.uniform(-1.2,1.2),R.uniform(-1.3,1.3),R.uniform(-.2,.6)))
 timber('Collapsed splintered oak',a,b,.12,.18,group='SM_Home_Rubble')

# Simple authored living spaces, kept clear around the entry and upstairs route.
box('Kitchen oak worktop',(.7,2.12,2.07),(2.0,.65,.12),M['wood'],'SM_Home_Interior',True,.025)
for x in [-.1,1.5]:
 for y in [1.87,2.37]:box('Kitchen leg',(x,y,1.6),(.095,.095,.86),M['wood'],'SM_Home_Interior',False,.012)
box('Living table top',(-.25,-.1,1.93),(1.5,.9,.12),M['wood'],'SM_Home_Interior',True,.025)
for x in [-.86,.36]:
 for y in [-.43,.23]:box('Table foot',(x,y,1.56),(.09,.09,.75),M['wood'],'SM_Home_Interior',False,.012)
for cx,cy in [(-.3,.9),(-.3,-1.05)]:
 box('Dining stool seat',(cx,cy,1.63),(.44,.44,.1),M['wood'],'SM_Home_Interior',True,.02)
 for dx in [-.15,.15]:
  for dy in [-.15,.15]:box('Stool foot',(cx+dx,cy+dy,1.38),(.06,.06,.46),M['wood'],'SM_Home_Interior',False,.005)
box('Upstairs bed timber frame',(.6,1.05,4.58),(1.6,2.4,.42),M['wood'],'SM_Home_Interior',True,.03)
box('Bed mattress',(.6,.98,4.85),(1.48,2.14,.22),M['linen'],'SM_Home_Interior',False,.07)
box('Teal wool blanket',(.6,.40,4.99),(1.5,1.22,.06),M['teal'],'SM_Home_Interior',False,.025)
box('Linen pillow',(.6,1.65,5.0),(.9,.42,.16),M['linen'],'SM_Home_Interior',False,.06)
box('Bed headboard',(.6,2.20,4.9),(1.68,.12,1.15),M['wood'],'SM_Home_Interior',False,.025)
box('Bedroom writing desk',(.9,-2.6,4.99),(1.25,.60,.10),M['wood'],'SM_Home_Interior',True,.02)
for x in [.36,1.44]:
 for y in [-2.83,-2.37]:box('Writing desk leg',(x,y,4.64),(.07,.07,.68),M['wood'],'SM_Home_Interior',False,.008)
box('Bedroom woven rug',(-.8,-.7,4.34),(1.9,2.5,.025),M['fabric'],'SM_Home_Interior',False,0)
# Attic lattice window as a strong small front-gable accent.
box('Attic shadow opening',(-1.6,-3.84,8.0),(.61,.045,.73),M['dark'],'SM_Home_Details',False,.01)
for x in [-1.92,-1.6,-1.28]:box('Attic window upright',(x,-3.89,8.0),(.07,.08,.81),M['wood'],'SM_Home_Details',False,.01)
for z in [7.60,8.0,8.40]:box('Attic window crosspiece',(-1.6,-3.89,z),(.72,.08,.07),M['wood'],'SM_Home_Details',False,.01)

def detail_box(name,loc,size,mat,bevel=.02):return box(name,loc,size,mat,'SM_Home_Plants' if mat in[M['leaf'],M['flower']] else 'SM_Home_Details',False,bevel)
def detail_mesh(name,verts,faces,mat):return mesh(name,verts,faces,mat,'SM_Home_Plants' if mat in[M['leaf'],M['flower']] else 'SM_Home_Details')
def detail_beam(name,a,b,width,depth,mat):return timber(name,a,b,width,depth,mat,'SM_Home_Plants' if mat in[M['leaf'],M['flower']] else 'SM_Home_Details')
import house_details
house_details.build_details({'box':detail_box,'beam':detail_beam,'cyl':cylinder,'mesh':detail_mesh,'mat':M,'rand':R})

# Consolidate semantic groups while keeping every original component editable.
bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();assets=[]
for group,objects in parts.items():
 vv=[];ff=[];uu=[];fm=[];ml=[]
 for obj in objects:
  if obj.hide_render:continue
  ev=obj.evaluated_get(deps);data=ev.to_mesh(preserve_all_data_layers=True,depsgraph=deps);offset=len(vv);vv.extend(obj.matrix_world@v.co for v in data.vertices);uv=data.uv_layers.active;remap=[]
  for mat in data.materials:
   mat=mat.original if getattr(mat,'is_evaluated',False) else mat
   if mat not in ml:ml.append(mat)
   remap.append(ml.index(mat))
  for f in data.polygons:
   ff.append(tuple(offset+data.loops[li].vertex_index for li in f.loop_indices));uu.extend(tuple(uv.data[li].uv) if uv else(0,0) for li in f.loop_indices);fm.append(remap[f.material_index] if remap else 0)
  ev.to_mesh_clear()
 data=bpy.data.meshes.new(group);data.from_pydata(vv,[],ff);data.update();obj=bpy.data.objects.new(group,data);EXP.objects.link(obj)
 for mat in ml:data.materials.append(mat)
 uv=data.uv_layers.new(name='UV0_Tiling')
 for i,p in enumerate(uu):uv.data[i].uv=p
 for i,mi in enumerate(fm):data.polygons[i].material_index=mi
 uv1=data.uv_layers.new(name='UV1_Lightmap');grid=math.ceil(math.sqrt(max(1,len(ff))))
 for i,f in enumerate(data.polygons):
  axis=max(range(3),key=lambda a:abs(f.normal[a]));axes=((1,2),(0,2),(0,1))[axis];coords=[(data.vertices[data.loops[li].vertex_index].co[axes[0]],data.vertices[data.loops[li].vertex_index].co[axes[1]]) for li in f.loop_indices];lo=[min(p[j] for p in coords) for j in [0,1]];hi=[max(p[j] for p in coords) for j in [0,1]]
  for li,p in zip(f.loop_indices,coords):uv1.data[li].uv=((i%grid+.08+.84*(p[0]-lo[0])/max(hi[0]-lo[0],1e-6))/grid,(i//grid+.08+.84*(p[1]-lo[1])/max(hi[1]-lo[1],1e-6))/grid)
 data.uv_layers.active_index=0;bm=bmesh.new();bm.from_mesh(data);bmesh.ops.triangulate(bm,faces=list(bm.faces));bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free();data.update()
 assets.append({'name':group,'file':'meshes/'+group+'.fbx','materials':[m.name for m in ml],'bounds_m':{'min':[min(v.co[i] for v in data.vertices) for i in range(3)],'max':[max(v.co[i] for v in data.vertices) for i in range(3)]},'collision_count':len(proxies[group]),'triangles':len(data.polygons),'vertices':len(data.vertices)})
 print('Batched',group,len(data.polygons),'triangles',len(proxies[group]),'colliders',flush=True)
SRC.hide_render=True;SRC.hide_viewport=True;COL.hide_render=True
route=[('Street approach',(.6,-8.4,0)),('Approach stairs',(.6,-6.85,.575)),('Front porch',(.6,-5.3,1.2)),('Entry threshold',(.6,-3.6,1.15)),('Entry living room',(.6,-2.35,1.15)),('Stair foot',(-2.85,-2.5,1.31)),('Stair middle',(-2.85,-.535,2.725)),('Stair landing',(-2.85,2.05,4.3)),('Upstairs passage',(-1.4,1.7,4.3)),('Bedroom',(-.9,-1.7,4.3)),('Balcony door',(-1.65,-3.65,4.3)),('Balcony',(-1.65,-4.65,4.345))]
manifest={'name':'Your Harbor House','units':'meters','assets':assets,'material_definitions':custom,'unreal_transform':{'unit_scale':100,'axes':['X','-Y','Z']},'ground_floor_z':1.15,'upper_floor_z':4.3,'entrance_facing_blender':[0,-1,0],'route_waypoints_blender':[{'name':name,'position':list(p)} for name,p in route],'reference':'../../assets/player_house_reference.png','notes':['Actual geometry with open entry, usable interior stairs, upstairs bed and balcony.','Exterior follows supplied house reference; unseen interior was authored for gameplay.','Dynamic lighting with tileable PBR UV0 and padded UV1.']}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
for a in assets:
 obj=bpy.data.objects[a['name']];bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
 for p in proxies[a['name']]:p.select_set(True)
 bpy.ops.export_scene.fbx(filepath=str(OUT/a['file']),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',global_scale=1,apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',use_mesh_modifiers=True,add_leaf_bones=False,bake_anim=False,path_mode='RELATIVE',embed_textures=False,mesh_smooth_type='FACE')
COL.hide_viewport=True
# Neutral ground is preview-only, not exported as part of the modular home.
data=bpy.data.meshes.new('Preview paving');data.from_pydata([(-35,-35,-.04),(35,-35,-.04),(35,35,-.04),(-35,35,-.04)],[],[(0,1,2,3)]);data.materials.append(M['cobble']);uv_metric(data);obj=bpy.data.objects.new('Preview ground',data);SET.objects.link(obj)
world=bpy.data.worlds.new('Coastal golden hour');world.use_nodes=True;S.world=world;bg=world.node_tree.nodes.get('Background');bg.inputs['Color'].default_value=(.32,.46,.65,1);bg.inputs['Strength'].default_value=.48
sd=bpy.data.lights.new('Warm evening sun','SUN');sd.energy=3.0;sd.angle=.13;sd.color=(1,.76,.50);sun=bpy.data.objects.new('Warm evening sun',sd);SET.objects.link(sun);sun.rotation_euler=(math.radians(48),math.radians(-30),math.radians(-35))
ad=bpy.data.lights.new('Sky fill','AREA');ad.energy=1700;ad.size=12;ad.color=(.65,.8,1);ar=bpy.data.objects.new('Sky fill',ad);SET.objects.link(ar);ar.location=(0,-10,12);ar.rotation_euler=(Vector((0,0,4))-ar.location).to_track_quat('-Z','Y').to_euler()
for name,loc,energy in [('Living room lamplight',(-.7,-.4,3.3),160),('Bedroom lamplight',(-1,-.2,6.3),100),('Porch lantern spill',(.8,-4.2,3.1),45)]:
 d=bpy.data.lights.new(name,'POINT');d.energy=energy;d.color=(1,.73,.46);d.shadow_soft_size=.45;o=bpy.data.objects.new(name,d);SET.objects.link(o);o.location=loc
def camera(name,pos,target,lens):
 d=bpy.data.cameras.new(name);o=bpy.data.objects.new(name,d);SET.objects.link(o);o.location=pos;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();d.lens=lens;return o
cam=camera('House reference view',(13,-22,9.5),(.25,-.6,4.45),45);inside=camera('Interior player view',(.8,-2.6,2.8),(-1,1,2.6),22)
S.camera=cam;S.render.engine='CYCLES';S.cycles.samples=40;S.cycles.use_denoising=True
try:
 prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='HIP';prefs.get_devices()
 for d in prefs.devices:d.use=d.type=='HIP' and '9070' in d.name
 if any(d.use for d in prefs.devices):S.cycles.device='GPU'
except Exception:pass
S.render.resolution_x=1600;S.render.resolution_y=1100;S.render.resolution_percentage=100;S.view_settings.view_transform='AgX';S.render.image_settings.file_format='PNG'
for name,p in route:
 marker=bpy.data.objects.new('NAV_'+name,None);SET.objects.link(marker);marker.location=p;marker.empty_display_type='SPHERE';marker.empty_display_size=.15
readme=bpy.data.texts.new('PLAYER HOUSE · READ ME');readme.write('Player home built from the supplied exterior reference.\nReal metric geometry; entry opens; ground living room, interior stair and upper bedroom/balcony.\nOriginal pieces preserved in AUTHORING. GAME contains semantic export meshes. COLLISION contains named convex proxies.\nFBX assets and route manifest accompany this source. Interiors are an authored interpretation.\n')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Your_Harbor_House.blend'))
(OUT/'exports_complete.json').write_text(json.dumps({'status':'complete','assets':len(assets),'triangles':sum(a['triangles'] for a in assets)},indent=2))
S.render.filepath=str(OUT/'previews/House_Blender_Exterior.png');bpy.ops.render.render(write_still=True)
S.camera=inside;S.render.filepath=str(OUT/'previews/House_Blender_Interior.png');bpy.ops.render.render(write_still=True)
S.camera=cam
print('PLAYER HOUSE BUILD COMPLETE',flush=True)
