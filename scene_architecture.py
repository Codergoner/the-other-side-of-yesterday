"""Editable volumetric architecture aligned to the 1672 by 941 harbour camera."""
import math
import random
import bpy
from mathutils import Vector


def add_architecture(api):
    objects=[]
    mats=api['materials']
    projection=api.get('projection_mat')
    project=api.get('project_object')
    current=None
    def group(name):
        nonlocal current
        current=bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(current)
    def W(u,v,d):
        return Vector(api['world'](u,v,d))
    def mesh(name,verts,faces,material='plaster',proj=True):
        data=bpy.data.meshes.new(name+' mesh')
        data.from_pydata([tuple(p) for p in verts],[],faces)
        data.update()
        obj=bpy.data.objects.new(name,data)
        current.objects.link(obj)
        objects.append(obj)
        data.materials.append(mats.get(material,mats['stone']))
        if proj and projection:
            data.materials.append(projection)
            data.polygons[0].material_index=1
        if project:
            project(obj)
        return obj
    def facade(name,poly,d,t,material='plaster',proj=True):
        front=[W(u,v,d) for u,v in poly]
        back=[p+Vector((0,t,0)) for p in front]
        n=len(front)
        faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]
        faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        return mesh(name,front+back,faces,material,proj)
    def rect(name,l,top,r,bottom,d,t=.2,material='plaster',proj=True):
        return facade(name,[(l,top),(r,top),(r,bottom),(l,bottom)],d,t,material,proj)
    def beam(name,a,b,d,w=1.5,material='wood'):
        a=W(*a,d);b=W(*b,d);delta=b-a
        if delta.length<.00001:return
        n=6;rad=w*d/1550
        direction=delta.normalized()
        normal=direction.cross(Vector((0,1,0))).normalized()
        tangent=direction.cross(normal).normalized()
        verts=[]
        for p in (a,b):
            verts += [p+rad*(normal*math.cos(2*math.pi*i/n)+tangent*math.sin(2*math.pi*i/n)) for i in range(n)]
        faces=[tuple(reversed(range(n))),tuple(range(n,n*2))]
        faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        return mesh(name,verts,faces,material,False)
    def ring(name,cx,spring,rx,ry,th,d,t,material='stone',n=17):
        for i in range(n):
            a=math.pi*i/n+.009;b=math.pi*(i+1)/n-.009
            facade(name+' voussoir %02d'%i,[(cx+rx*math.cos(a),spring-ry*math.sin(a)),(cx+rx*math.cos(b),spring-ry*math.sin(b)),(cx+(rx+th)*math.cos(b),spring-(ry+th)*math.sin(b)),(cx+(rx+th)*math.cos(a),spring-(ry+th)*math.sin(a))],d,t,material)
    def arches(name,l,r,top,bottom,opens,d,t,material='stone',rim=3):
        edge=l
        for k,(cx,rx,spring,ry) in enumerate(opens):
            left=cx-rx;right=cx+rx
            if left>edge:rect(name+' pier %d'%k,edge,top,left,bottom,d,t,material)
            n=20
            for j in range(n):
                x0=left+2*rx*j/n;x1=left+2*rx*(j+1)/n
                y0=spring-ry*math.sqrt(max(0,1-((x0-cx)/rx)**2))
                y1=spring-ry*math.sqrt(max(0,1-((x1-cx)/rx)**2))
                facade(name+' spandrel %d %d'%(k,j),[(x0,top),(x1,top),(x1,y1),(x0,y0)],d,t,material)
            ring(name+' arch %d'%k,cx,spring,rx,ry,rim,d-.025,t+.025,material)
            for j in range(n):
                a=math.pi*j/n;b=math.pi*(j+1)/n
                p=W(cx+rx*math.cos(a),spring-ry*math.sin(a),d)
                q=W(cx+rx*math.cos(b),spring-ry*math.sin(b),d)
                mesh(name+' vault soffit %d %d'%(k,j),[p,q,q+Vector((0,t,0)),p+Vector((0,t,0))],[(0,1,2,3)],material,False)
            edge=right
        if edge<r:rect(name+' end pier',edge,top,r,bottom,d,t,material)
        rect(name+' coping',l-1,top-3,r+1,top+2,d-.045,t+.09,'stone')
    def window(name,cx,top,w,h,d,shutters=False,arched=False):
        l=cx-w/2;r=cx+w/2;s=max(1,w*.085)
        rect(name+' inset',l,top,r,top+h,d+.015,.025,'dark')
        for a,b in [(l-s,l),(r,r+s)]:rect(name+' jamb',a,top-s,b,top+h,d-.025,.08,'stone')
        rect(name+' sill',l-s-1,top+h,r+s+1,top+h+s,d-.05,.12,'stone')
        rect(name+' lintel',l-s,top-s,r+s,top,d-.03,.08,'stone')
        if w>10:rect(name+' mullion',cx-.6,top,cx+.6,top+h,d-.035,.035,'wood')
        if shutters:
            for x in (l-w*.46-1,r+1):
                rect(name+' shutter',x,top,x+w*.44,top+h,d-.065,.065,'roof')
                for y in range(int(top+4),int(top+h),max(4,int(h/8))):
                    rect(name+' shutter slat',x+.6,y,x+w*.44-.6,y+.7,d-.08,.02,'wood')
        if arched:ring(name+' head',cx,top+w/2,w/2,w/2,s,d-.07,.08,'stone',12)
    def balcony(name,l,r,top,d,h=30):
        rect(name+' slab',l-3,top+h,r+4,top+h+4,d-.18,.55,'stone')
        beam(name+' handrail',(l,top),(r,top),d-.35,1.6)
        beam(name+' bottomrail',(l,top+h-3),(r,top+h-3),d-.35,1.2)
        n=max(5,int((r-l)/8))
        for i in range(n+1):
            x=l+(r-l)*i/n
            beam(name+' baluster %d'%i,(x,top+1),(x,top+h-4),d-.35,1.3,'plaster')
        for x in (l+8,r-8):beam(name+' bracket',(x,top+h+4),(x+9,top+h+20),d-.015,2)
    def roof(name,l,r,top,bottom,d,t=1.2):
        mid=(l+r)/2
        facade(name,[(l,bottom),(l+(r-l)*.16,top+5),(mid,top),(r-(r-l)*.14,top+5),(r,bottom)],d,t,'roof')
        beam(name+' ridge',(l+(r-l)*.22,top+3),(r-(r-l)*.2,top+4),d-.025,1.2,'roof')
        for j in range(4,max(5,int(bottom-top)),5):
            f=j/max(1,bottom-top)
            for x in range(int(mid+(l-mid)*f),int(mid+(r-mid)*f),7):
                beam(name+' tile',(x,top+j),(x+2,top+j+4),d-.035,.55,'roof')

    group('Architecture | foreground ruined houses')
    facade('Left cropped plaster house',[(-90,-85),(76,-67),(100,9),(208,29),(212,413),(182,453),(12,515),(-90,487)],10.5,2.7)
    facade('Middle ruined jagged house',[(205,166),(267,167),(319,152),(349,147),(363,89),(387,85),(403,69),(432,72),(442,123),(450,12),(468,13),(476,62),(486,70),(490,185),(488,423),(445,449),(438,541),(381,548),(364,439),(211,440)],15.1,2.5)
    facade('Middle left annexe',[(203,197),(336,187),(350,385),(337,482),(216,472)],13.8,1.8)
    facade('Rear broken house',[(488,230),(527,229),(535,249),(545,248),(547,275),(559,251),(574,259),(578,242),(591,251),(606,240),(627,270),(650,280),(657,387),(635,417),(617,461),(557,461),(538,428),(492,420)],20.5,2.1)
    facade('Rear roof remnant',[(489,222),(548,205),(565,231),(528,247),(490,249)],20.2,1.3,'roof')
    timbers=[((-25,1),(272,25),10.25,5),((-21,27),(317,39),10.1,4),((26,2),(108,59),10,4),((96,6),(228,78),10.1,4),((164,19),(321,98),10.2,4),((188,36),(278,115),10.2,3.5),((214,131),(329,104),13.5,4),((230,156),(338,141),13.3,3),((344,91),(447,94),14.85,3),((362,67),(445,53),14.7,3),((374,41),(426,119),14.65,2),((350,95),(416,29),14.8,2.5),((327,173),(498,196),14.8,4),((331,182),(355,229),14.8,2),((369,185),(390,229),14.8,2),((407,191),(427,231),14.8,2),((444,199),(461,232),14.8,2),((474,203),(485,232),14.8,2),((535,232),(634,278),20.2,2.5),((545,252),(593,204),20.2,2.5),((567,237),(663,262),20.2,3),((589,221),(628,284),20.2,2.5),((613,249),(700,273),20.2,2.5),((650,270),(713,271),20.2,2)]
    for i,(a,b,d,w) in enumerate(timbers):beam('Exposed roof timber %02d'%i,a,b,d,w)
    for i in range(10):beam('Overhanging foreground rafter %d'%i,(12+i*26,-12),(75+i*26,44+i%3*4),9.95,3.5)
    for args in [('Left shutter window A',103,172,31,118,10.35,True),('Left shutter window B',162,181,26,112,10.35,True),('Middle left window',241,243,28,64,13.58),('Balcony doorway',451,237,27,79,14.9,True),('Middle narrow window',478,249,14,68,14.9,True),('Rear broken window',579,294,17,38,20.25),('Rear small slot',655,305,12,52,20.3)]:window(*args)
    balcony('Left main balcony',-8,258,306,9.95,57)
    balcony('Annexe balcony',216,321,304,13.3,32)
    balcony('Middle balcony',448,528,315,14.5,32)
    arches('Left shadow doorway',221,325,391,512,[(272,35,449,47)],12.9,.85,'stone',4)
    rect('Middle shop dark entrance',432,447,500,523,14.45,.25,'dark')

    group('Architecture | lane gateway and waterside villas')
    arches('Ruined lane gateway',653,779,381,531,[(707,23,456,29)],23.5,1.6,'plaster',5.7)
    facade('Gateway crumbled parapet',[(653,382),(660,369),(672,376),(688,365),(710,373),(722,364),(738,372),(759,366),(774,375),(778,396),(655,398)],23.45,1.6)
    rng=random.Random(22381)
    for i in range(17):
        x=656+i*7;y=371+rng.uniform(-5,7)
        rect('Loose gateway stone %d'%i,x,y,x+6,y+5,23.35,.25,'stone')
    facade('Tall waterside villa',[(775,343),(841,341),(848,403),(851,510),(833,554),(777,550)],29.5,1.8)
    roof('Tall villa roof',763,851,321,344,29.25,1.8)
    facade('Villa wing',[(843,371),(904,372),(912,505),(902,556),(851,555)],29,1.7)
    roof('Villa wing roof',836,917,349,375,28.8,1.7)
    facade('Lower villa tower',[(837,434),(912,435),(913,580),(846,600),(841,512)],26.4,1.9)
    roof('Lower villa roof',815,927,405,438,26.1,2)
    facade('Gateway rear villa',[(723,355),(778,351),(778,412),(728,422)],28.3,1.3)
    roof('Gateway rear roof',700,790,343,366,28,1.4)
    for args in [('Tall villa window',820,355,13,25,29.25),('Tall villa lower window',809,404,12,24,29.25),('Tall villa slim window',783,406,10,22,29.25),('Wing window',870,388,10,18,28.8),('Lower villa window',868,459,13,26,26.2),('Villa side slot',904,492,8,18,26.2)]:window(*args)
    rect('Villa chimney shaft',891,304,903,358,30.2,.42)
    facade('Villa chimney cap',[(887,303),(896,294),(907,304),(905,309),(889,309)],30.12,.5,'stone')
    window('Chimney opening',897,310,4,7,30)

    group('Architecture | campanile and high aqueduct')
    facade('Campanile lower shaft',[(589,122),(665,125),(670,203),(654,224),(600,219)],68,5.1)
    rect('Campanile upper shaft',594,57,660,126,67.7,4.8)
    for u in (596,652):
        rect('Campanile upper corner pilaster',u,59,u+5,124,67.42,.3,'stone')
        rect('Campanile lower corner pilaster',u-2,131,u+6,197,67.6,.38,'stone')
    for v in (55,120,128,195):rect('Campanile cornice',587,v,669,v+4,67.35,5.8,'stone')
    for name,cx,top,h,w,d in [('Upper belfry left',611,75,33,9,67.22),('Upper belfry right',644,77,32,7,67.22),('Lower belfry left',614,143,29,8,67.43),('Lower belfry right',650,144,29,6,67.43)]:window(name,cx,top,w,h,d,False,True)
    facade('Campanile lead dome',[(599,51),(602,35),(607,23),(616,18),(627,17),(640,23),(647,34),(651,50)],67.5,3.5,'roof')
    for u in (608,619,629,640):beam('Campanile dome rib',(627,18),(u,49),67.35,.8,'metal')
    beam('Campanile finial',(627,19),(628,7),67.4,.6,'metal')
    arches('High aqueduct western span',665,898,198,301,[(708,20,250,37),(761,26,251,41),(828,22,259,34),(878,12,262,25)],76,4.2,'plaster',3.7)
    for x in range(675,901,24):rect('Aqueduct merlon',x,192,x+7,201,75.75,.8,'stone')
    facade('Rear left chapel tower',[(502,107),(523,108),(527,179),(500,185)],84,2.2)
    rect('Rear chapel belfry',503,95,525,112,83.8,1.8)
    roof('Rear chapel cap',499,527,89,98,83.5,1.8)
    for top in (104,126,145):window('Rear chapel slit',513,top,6,12,83.55,False,True)

    group('Architecture | hill cathedral')
    facade('Cathedral nave volume',[(885,118),(909,113),(916,105),(1023,108),(1065,136),(1061,194),(880,197)],112,8.5)
    facade('Cathedral nave roof',[(904,111),(942,96),(1017,106),(1048,130),(1020,133),(940,116)],111.8,7.3,'roof')
    facade('Cathedral left tower',[(916,70),(959,71),(963,159),(915,160)],110.7,3.1)
    rect('Cathedral left belfry',928,55,954,74,110.4,2.6)
    facade('Cathedral left dome',[(931,55),(934,47),(940,44),(947,48),(950,56)],110.25,2,'roof')
    beam('Cathedral left finial',(941,44),(941,38),110.1,.5,'metal')
    for v in (70,100,128):rect('Cathedral tower string course',913,v,963,v+2.4,110.3,3.8,'stone')
    for cx in (937,949):
        window('Cathedral tower upper slit',cx,82,5,15,110.3,False,True)
        window('Cathedral tower lower slit',cx,111,5,15,110.3,False,True)
    facade('Cathedral right tower',[(1038,105),(1067,104),(1070,164),(1039,166)],112.3,3)
    rect('Cathedral right belfry',1042,92,1063,109,112.05,2.3)
    facade('Cathedral right dome',[(1043,94),(1045,85),(1052,81),(1058,86),(1061,94)],111.9,1.8,'roof')
    beam('Cathedral right finial',(1052,82),(1052,75),111.8,.4,'metal')
    window('Cathedral right opening',1053,98,5,13,111.8,False,True)
    facade('Cathedral apse facade',[(965,134),(1001,127),(1032,131),(1048,145),(1049,197),(961,198)],109.9,6.8)
    facade('Cathedral apse dome',[(963,134),(975,120),(994,115),(1018,120),(1034,132),(1038,139)],109.6,5.5,'roof')
    for u in (968,985,1004,1022,1040):
        rect('Cathedral apse pilaster',u,145,u+2,193,109.58,.32,'stone')
        window('Cathedral apse clerestory',u+5,144,5,9,109.5,False,True)
    window('Cathedral portal',1005,157,14,36,109.45,False,True)
    window('Cathedral left lancet',886,133,10,25,111.6,False,True)
    window('Cathedral second lancet',908,126,8,26,111.6,False,True)
    facade('Cathedral forecourt chapel',[(894,180),(922,174),(952,182),(951,211),(895,217)],105.7,2.7)
    roof('Forecourt chapel roof',889,956,170,184,105.5,2.7)
    for x in (904,922,939):window('Forecourt chapel window',x,190,5,12,105.35,False,True)
    arches('Cathedral roofless eastern arcade',1065,1164,161,218,[(1081,9,197,17),(1106,9,196,18),(1132,9,195,22),(1153,7,192,25)],114.3,2.2,'plaster',2.4)
    facade('Cathedral ruined east gable',[(1131,157),(1148,141),(1152,127),(1157,140),(1167,142),(1169,210),(1161,211),(1160,153),(1151,148),(1141,161)],114.1,1.1,'stone')
    for x in (1074,1090,1110,1126):beam('Cathedral broken roof strut',(x,155),(x+25,175),113.9,1.3)

    group('Architecture | cliff palaces and retaining walls')
    facade('Headland retaining curtain',[(887,224),(939,220),(966,216),(991,227),(1044,218),(1087,219),(1129,224),(1142,250),(1113,330),(1091,385),(1046,390),(1021,365),(983,354),(968,306),(923,301),(887,279)],89,5.2,'stone')
    arches('Upper retaining gallery',856,1125,217,272,[(873,9,252,16),(902,9,250,17),(929,9,249,18),(1089,10,259,22),(1115,8,254,18)],88.65,3.9,'plaster',2.6)
    facade('Cliff palace west block',[(959,275),(1008,270),(1013,337),(983,343),(961,325)],82.5,3)
    facade('Cliff palace square tower',[(986,250),(1004,244),(1026,254),(1028,341),(1010,356),(986,342)],82,3.5)
    roof('Cliff palace watchtower roof',984,1029,241,255,81.8,3.3)
    facade('Cliff waterside annexe',[(994,346),(1064,345),(1070,382),(1003,385)],81,3.1)
    roof('Cliff waterside roof',984,1075,329,349,80.8,3.1)
    facade('Far eastern buttress tower',[(1244,299),(1261,294),(1272,307),(1271,356),(1258,381),(1247,360)],99,2)
    facade('Far eastern castle',[(1208,277),(1228,279),(1229,286),(1250,286),(1257,313),(1246,359),(1228,347),(1217,322)],99.5,3)
    for cx,top,w,h,d in [(1000,266,5,11,81.7),(1017,278,6,11,81.7),(1002,303,6,14,81.7),(1017,315,5,14,81.7),(972,288,5,12,82.2),(976,314,5,12,82.2),(1019,357,6,14,80.7),(1046,355,6,13,80.7),(1100,247,6,14,88.3),(1117,279,6,18,88.3),(1254,314,4,12,98.7),(1221,292,4,12,99.2)]:window('Headland palace window',cx,top,w,h,d,False,True)
    for u in (946,976,1031,1062,1126):facade('Stone retaining buttress',[(u,230),(u+6,231),(u+9,322),(u-3,321)],88.35,.8,'stone')
    for i in range(22):
        x=860+i*12;y=213+int(max(0,x-1040)*.09)
        rect('Headland parapet block',x,y,x+7,y+6,88.1,.7,'stone')
    for x,y in [(882,212),(920,210),(1092,217),(1137,222),(1180,236)]:
        rect('Headland pinnacle',x-2,y-13,x+2,y+5,88,.55)
        facade('Pinnacle cap',[(x-3,y-12),(x,y-18),(x+3,y-12)],87.9,.55,'stone')

    group('Architecture | harbour bridge')
    arches('Harbour bridge',944,1180,429,506,[(973,19,475,28),(1033,24,476,31),(1091,22,478,28)],47.5,3.6,'stone',4.2)
    rect('Harbour bridge parapet',940,419,1185,430,47.1,3.9,'stone')
    for i in range(16):rect('Bridge parapet cap',948+i*15,415,959+i*15,420,46.95,.75,'stone')
    for i,x in enumerate((947,1003,1063,1124,1174)):facade('Bridge cutwater %d'%i,[(x-5,461),(x+5,461),(x+8,496),(x,509),(x-7,499)],46.4,2.7,'stone')
    facade('Bridge watchhouse',[(1022,388),(1062,387),(1065,422),(1024,423)],46.8,1.6)
    roof('Bridge watchhouse roof',1015,1070,374,390,46.6,1.6)
    window('Bridge watchhouse left window',1035,398,5,10,46.45)
    window('Bridge watchhouse right window',1053,397,5,10,46.45)

    group('Architecture | lighthouse and distant city')
    facade('Lighthouse bastion',[(1561,438),(1589,433),(1624,432),(1658,438),(1662,479),(1652,500),(1606,506),(1571,496),(1551,477)],56.5,4.7,'stone')
    arches('Lighthouse bastion doorway',1557,1593,447,495,[(1573,8,479,13)],56.15,2.1,'stone',2.6)
    facade('Lighthouse tapered tower',[(1608,355),(1634,355),(1640,436),(1634,443),(1601,441)],55.8,2.1)
    for v,l,r in [(355,1607,1635),(363,1607,1635),(433,1599,1641),(442,1598,1642)]:rect('Lighthouse stone course',l,v,r,v+3,55.55,2.4,'stone')
    rect('Lighthouse lantern chamber',1615,333,1633,350,55.35,1.4,'dark')
    for x in (1614,1620,1627,1633):beam('Lantern mullion',(x,333),(x,351),55.2,.6,'metal')
    facade('Lighthouse lantern roof',[(1611,333),(1624,325),(1637,333),(1635,336),(1612,336)],55.15,1.8,'roof')
    beam('Lighthouse finial',(1624,325),(1624,319),55.05,.5,'metal')
    rect('Lighthouse gallery',1608,349,1639,353,55.05,2.7,'stone')
    beam('Lighthouse gallery rail',(1608,346),(1638,346),54.95,.65,'metal')
    for x in range(1608,1640,5):beam('Gallery stanchion',(x,346),(x,351),54.95,.5,'metal')
    window('Lighthouse upper slit',1621,371,4,11,55.48)
    window('Lighthouse lower slit',1623,408,4,11,55.48)
    skyline=[(1281,244,14,47),(1300,225,11,61),(1313,251,18,37),(1336,269,18,22),(1360,254,17,36),(1379,247,20,42),(1402,243,20,46),(1422,237,13,49),(1439,244,28,43),(1477,240,11,49),(1491,263,19,26),(1514,269,16,23),(1535,254,12,37),(1556,275,19,21),(1578,282,12,17)]
    for i,(x,top,w,h) in enumerate(skyline):
        rect('Distant city house %02d'%i,x,top,x+w,top+h,178+i*.1,1.4,'stone')
        if i%3==0:facade('Distant city gable',[(x-1,top),(x+w*.5,top-6),(x+w+1,top)],177.8+i*.1,1.4,'roof')
        if w>12:
            for xx in range(x+4,x+w-2,6):window('Distant tiny window',xx,top+7,2.4,4,177.7+i*.1)
    rect('Distant harbour bell tower',1536,252,1547,286,176.2,1.4,'stone')
    facade('Distant harbour bell roof',[(1534,252),(1542,242),(1549,252)],176,1.4,'roof')
    for x in (1539,1544):window('Distant bell opening',x,256,2.2,6,175.9,False,True)
    return objects
