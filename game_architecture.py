"""Freestanding metric Mediterranean ruin architecture for the playable harbour."""
import math
import random
from mathutils import Vector


def add_architecture(api):
    mats=api['materials']
    made=[]
    rng=random.Random(8205)
    def B(name,p,size,mat='stone',group='SM_Architecture',collision=False,bevel=.025):
        ob=api['box'](name,p,size,mats[mat],group=group,collision=collision,bevel=bevel)
        made.append(ob);return ob
    def M(name,v,f,mat='stone',group='SM_Architecture',collision=False):
        ob=api['mesh'](name,v,f,mats[mat],group=group,collision=collision)
        made.append(ob);return ob
    def beam(name,a,b,r=.06,mat='wood',group='SM_Architecture',collision=False):
        ob=api['beam'](name,a,b,r,mats[mat],group=group,collision=collision)
        made.append(ob);return ob
    def P(axis,c,u,z):
        return Vector((c,u,z)) if axis=='X' else Vector((u,c,z))
    def poly(name,pts,axis,c,t,inside,mat,group,collision=False):
        front=[P(axis,c,u,z) for u,z in pts]
        delta=Vector((inside*t,0,0)) if axis=='X' else Vector((0,inside*t,0))
        verts=front+[p+delta for p in front];n=len(front)
        frontids=list(range(n))
        if (axis=='X' and inside>0) or (axis=='Y' and inside<0):frontids.reverse()
        faces=[tuple(frontids),tuple(i+n for i in reversed(frontids))]
        faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        return M(name,verts,faces,mat,group,collision)
    def wall(name,axis,c,l,r,z0,z1,t=.35,inside=-1,mat='plaster',group='SM_Architecture',collision=True):
        center=P(axis,c+inside*t/2,(l+r)/2,(z0+z1)/2)
        size=(t,r-l,z1-z0) if axis=='X' else (r-l,t,z1-z0)
        return B(name,center,size,mat,group,collision,.025)
    def perforated(name,axis,c,l,r,z0,z1,holes,t=.35,inside=-1,mat='plaster',group='SM_Architecture'):
        xs=sorted(set([l,r]+[max(l,min(r,h[i])) for h in holes for i in (0,1)]))
        zs=sorted(set([z0,z1]+[max(z0,min(z1,h[i])) for h in holes for i in (2,3)]))
        for i in range(len(xs)-1):
            for j in range(len(zs)-1):
                a,b=xs[i:i+2];bottom,top=zs[j:j+2]
                mid=(a+b)/2;zz=(bottom+top)/2
                if b-a<.01 or top-bottom<.01:continue
                if any(h[0]<mid<h[1] and h[2]<zz<h[3] for h in holes):continue
                wall(name+' panel %d %d'%(i,j),axis,c,a,b,bottom,top,t,inside,mat,group)
    def arch(name,axis,c,l,r,bottom,top,cx,rx,spring,ry,t=.45,inside=-1,mat='stone',group='SM_Architecture',trim=.22):
        wall(name+' left pier',axis,c,l,cx-rx,bottom,top,t,inside,mat,group)
        wall(name+' right pier',axis,c,cx+rx,r,bottom,top,t,inside,mat,group)
        n=20
        for j in range(n):
            a=cx-rx+2*rx*j/n;b=cx-rx+2*rx*(j+1)/n
            za=spring+ry*math.sqrt(max(0,1-((a-cx)/rx)**2))
            zb=spring+ry*math.sqrt(max(0,1-((b-cx)/rx)**2))
            if top>max(za,zb):poly(name+' spandrel %02d'%j,[(a,za),(b,zb),(b,top),(a,top)],axis,c,t,inside,mat,group,True)
        for j in range(17):
            a=math.pi*j/17+.01;b=math.pi*(j+1)/17-.01
            pts=[(cx+rx*math.cos(a),spring+ry*math.sin(a)),(cx+(rx+trim)*math.cos(a),spring+(ry+trim)*math.sin(a)),(cx+(rx+trim)*math.cos(b),spring+(ry+trim)*math.sin(b)),(cx+rx*math.cos(b),spring+ry*math.sin(b))]
            poly(name+' arch voussoir %02d'%j,pts,axis,c-inside*.05,t+.1,inside,'stone',group)
    def frame(name,axis,c,u,z,w,h,group,shutters=True):
        inward=-1 if axis=='X' else 1
        for side in (-1,1):
            wall(name+' stone jamb',axis,c,u+side*w/2-.08,u+side*w/2+.08,z-.08,z+h+.08,.16,inward,'stone',group,False)
        wall(name+' sill',axis,c,u-w/2-.15,u+w/2+.15,z-.12,z+.02,.28,inward,'stone',group,False)
        wall(name+' lintel',axis,c,u-w/2-.12,u+w/2+.12,z+h,z+h+.17,.18,inward,'stone',group,False)
        beam(name+' vertical mullion',P(axis,c-.025*inward,u,z+.05),P(axis,c-.025*inward,u,z+h-.05),.035,'wood',group)
        beam(name+' crossbar',P(axis,c-.025*inward,u-w/2,z+h*.58),P(axis,c-.025*inward,u+w/2,z+h*.58),.03,'wood',group)
        if shutters:
            for side in (-1,1):
                su=u+side*(w*.77+.08)
                wall(name+' open shutter',axis,c-.08*inward,su-w*.23,su+w*.23,z,z+h,.075,inward,'roof',group,False)
                for j in range(max(3,int(h/.17))):
                    zz=z+.10+j*.17
                    beam(name+' shutter louvre',P(axis,c-.13*inward,su-w*.2,zz),P(axis,c-.13*inward,su+w*.2,zz),.022,'wood',group)
    def hiproof(name,cx,cy,z,w,d,h,group,mat='roof',ruined=False):
        x0=cx-w/2;x1=cx+w/2;y0=cy-d/2;y1=cy+d/2
        ridge=max(.2,d/2-w*.3)
        verts=[(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z),(cx,cy-ridge,z+h),(cx,cy+ridge,z+h)]
        faces=[(0,1,4),(1,2,5,4),(2,3,5),(3,0,4,5)]
        if ruined:faces=faces[1:3]
        M(name+' solid roof slopes',verts,faces,mat,group,False)
        B(name+' front eave',(x1,cy,z-.07),(.2,d+.22,.2),'wood',group)
        B(name+' rear eave',(x0,cy,z-.07),(.2,d+.22,.2),'wood',group)
        beam(name+' ridge cap',(cx,cy-ridge,z+h),(cx,cy+ridge,z+h),.12,mat,group)
        # Modular rounded tile courses establish silhouette and highlights.
        for side in (-1,1):
            if ruined and side>0:continue
            for course in range(1,8):
                f=course/8;x=cx+side*w*.5*f;zz=z+h*(1-f)
                shorten=(1-f)*max(0,d*.2)
                count=max(3,int((d-2*shorten)/.36))
                for j in range(count):
                    yy=y0+shorten+(j+.5)*(d-2*shorten)/count
                    a=(x,yy,zz+.035);b=(x+side*w*.5/8,yy,zz-h/8+.035)
                    beam(name+' barrel tile',a,b,.058,mat,group)
    def dome(name,cx,cy,z,r,h,group,mat='roof',n=32):
        verts=[];rings=10
        for j in range(rings+1):
            a=(math.pi/2)*j/rings
            rr=r*math.cos(a)
            for i in range(n):
                b=i*math.tau/n;verts.append((cx+rr*math.cos(b),cy+rr*math.sin(b),z+h*math.sin(a)))
        faces=[]
        for j in range(rings):
            for i in range(n):faces.append((j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i))
        ob=M(name,verts,faces,mat,group)
        if ob and hasattr(ob,'data'):
            for p in ob.data.polygons:p.use_smooth=True
        for i in range(8):
            a=i*math.tau/8
            for j in range(8):
                p=j*math.pi/16;q=(j+1)*math.pi/16
                beam(name+' lead rib',(cx+r*math.cos(p)*math.cos(a),cy+r*math.cos(p)*math.sin(a),z+h*math.sin(p)+.035),(cx+r*math.cos(q)*math.cos(a),cy+r*math.cos(q)*math.sin(a),z+h*math.sin(q)+.035),.035,'metal',group)
    def balcony(name,x,cy,z,w,group):
        B(name+' stone deck',(x+.62,cy,z),(1.5,w+.4,.22),'stone',group,True)
        for yy in (cy-w/2,cy+w/2):beam(name+' timber bracket',(x,yy,z-1.1),(x+1.25,yy,z-.1),.10,'wood',group)
        beam(name+' front handrail',(x+1.3,cy-w/2,z+1.05),(x+1.3,cy+w/2,z+1.05),.065,'wood',group)
        for side in (-1,1):beam(name+' side handrail',(x,cy+side*w/2,z+1.05),(x+1.3,cy+side*w/2,z+1.05),.065,'wood',group)
        for j in range(int(w/.28)+1):
            yy=cy-w/2+j*w/max(1,int(w/.28))
            beam(name+' baluster',(x+1.3,yy,z+.17),(x+1.3,yy,z+1.02),.055,'plaster',group)
    # Three substantial hollow houses leave a clear five metre street beside them.
    for index,(cy,h) in enumerate([(-13,12),(2,14),(18,11)]):
        g='SM_LeftHouse_'+chr(65+index);cx=-7;z=8+(cy+22)*.10
        front=-4;back=-10;y0=cy-5;y1=cy+5
        B(g+' foundation',(cx,cy,z-.3),(6.3,10.3,.6),'stone',g,True)
        for floor in (0,3.5,7):B(g+' floor slab',(cx,cy,z+floor),(5.6,9.6,.20),'wood' if floor else 'stone',g,True)
        # Front ground story has a true open arched entrance.
        arch(g+' street door','X',front,y0,y1,z,z+3.5,cy,1.05,z+2.0,1.0,.38,-1,'plaster',g,.22)
        holes=[]
        for level in (4.25,8.1):
            for yy in (cy-2.6,cy+2.6):holes.append((yy-.65,yy+.65,z+level,z+level+2.05))
        perforated(g+' street wall','X',front,y0,y1,z+3.5,z+h,holes,.38,-1,'plaster',g)
        # Rear and side walls make an actual freestanding enclosed volume.
        wall(g+' rear wall','X',back,y0,y1,z,z+h-.4,.42,1,'plaster',g)
        for yy,inside in ((y0,1),(y1,-1)):
            holeside=[(cx-.55,cx+.55,z+4.4,z+6.2),(cx-.55,cx+.55,z+8.4,z+10)]
            perforated(g+' side wall','Y',yy,back,front,z,z+h-.2,holeside,.4,inside,'plaster',g)
            frame(g+' side window','Y',yy,cx,z+4.4,1.1,1.8,g,False)
        for level in (4.25,8.1):
            for yy in (cy-2.6,cy+2.6):frame(g+' shutter window','X',front+.03,yy,z+level,1.3,2.05,g,True)
        for level in (3.4,7.0):B(g+' projecting floor belt',(front+.05,cy,z+level),(.22,10.15,.18),'stone',g)
        balcony(g+' balcony',front,cy-2.6,z+4.1,2.4,g)
        # Broken gable tops and roof remnants expose genuine wooden framing.
        hiproof(g+' ruined green roof',cx,cy,z+h,6.8,10.5,2.3,g,'roof',True)
        for j in range(9):
            yy=y0+.2+j*1.15
            beam(g+' exposed roof rafter',(back-.3,yy,z+h),(cx,yy,z+h+2.3),.11,'wood',g)
            if j%3!=1:beam(g+' broken roof rafter',(cx,yy,z+h+2.3),(front+rng.uniform(-.7,.5),yy,z+h+rng.uniform(.1,.7)),.12,'wood',g)
        beam(g+' ridge timber',(cx,y0-.5,z+h+2.3),(cx,y1+.5,z+h+2.3),.17,'wood',g)
        for j in range(8):
            yy=y0+.3+j*1.3
            B(g+' jagged plaster crown',(front-.08,yy,z+h+rng.uniform(.1,.5)),(.45,.7,rng.uniform(.25,.9)),'plaster',g,False)
        B(g+' chimney',(-8.8,cy+2.2,z+h+1),( .8,.85,3.4),'plaster',g,True)
        B(g+' chimney cap',(-8.8,cy+2.2,z+h+2.75),(1.05,1.1,.20),'stone',g)
        for j in range(12):
            yy=y0+.4+j*.75;zz=z+rng.choice([.5,3.8,7.4])+rng.uniform(-.3,.3)
            B(g+' exposed rubble repair',(front+.04,yy,zz),(.18,.45,.22),'stone',g)

    def arcade_stage(name,cx,cy,z,width,height,group,material='plaster',opening=.75):
        for axis,c,u,inside in [('X',cx+width/2,cy,-1),('X',cx-width/2,cy,1),('Y',cy-width/2,cx,1),('Y',cy+width/2,cx,-1)]:
            arch(name+' '+axis+str(inside),axis,c,u-width/2,u+width/2,z,z+height,u,opening,z+height*.52,height*.32,.38,inside,material,group,.19)
    def bell(name,cx,cy,z,group,scale=1):
        profile=[(.20,.8),(.29,.72),(.33,.43),(.42,.16),(.62,0),(.66,-.1),(.50,-.16)]
        verts=[];n=20
        for r,h in profile:
            for i in range(n):
                a=i*math.tau/n;verts.append((cx+scale*r*math.cos(a),cy+scale*r*math.sin(a),z+scale*h))
        faces=[]
        for j in range(len(profile)-1):
            for i in range(n):faces.append((j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i))
        ob=M(name,verts,faces,'metal',group)
        if ob and hasattr(ob,'data'):
            for p in ob.data.polygons:p.use_smooth=True
        beam(name+' oak yoke',(cx-.9*scale,cy,z+scale),(cx+.9*scale,cy,z+scale),.14*scale,'wood',group)
        beam(name+' clapper',(cx,cy,z+.3*scale),(cx,cy,z-.2*scale),.05*scale,'metal',group)
    def cylindrical_wall(name,cx,cy,z,r,h,group,material='plaster',n=24,topr=None):
        topr=r if topr is None else topr
        verts=[]
        for zz,rr in ((z,r),(z+h,topr)):
            for i in range(n):
                a=i*math.tau/n;verts.append((cx+rr*math.cos(a),cy+rr*math.sin(a),zz))
        faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]
        faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        ob=M(name,verts,faces,material,group,True)
        return ob

    # Landmark campanile: four genuinely open upper arches surround a hanging bell.
    g='SM_BellTower';cx=-3;cy=41;z=17
    B('Campanile stepped foundation',(cx,cy,z-.3),(6.1,6.1,.6),'stone',g,True)
    for axis,c,u,inside in [('X',-.5,cy,-1),('X',-5.5,cy,1),('Y',38.5,cx,1),('Y',43.5,cx,-1)]:
        if axis=='Y' and inside==1:
            arch('Campanile arched entry',axis,c,u-2.5,u+2.5,z,z+6,u,.85,z+2.2,1.1,.5,inside,'plaster',g,.22)
            perforated('Campanile upper shaft',axis,c,u-2.5,u+2.5,z+6,z+12.5,[(u-.3,u+.3,z+8,z+10.5)],.5,inside,'plaster',g)
        else:
            perforated('Campanile shaft',axis,c,u-2.5,u+2.5,z,z+12.5,[(u-.28,u+.28,z+7.2,z+9.7)],.5,inside,'plaster',g)
        frame('Campanile slit',axis,c-inside*.02,u,z+8 if axis=='Y' and inside==1 else z+7.2,.56,2.5,g,False)
    for height in (0,5.2,10.2,12.4,17.3):B('Campanile tier cornice',(cx,cy,z+height),(5.42,5.42,.25),'stone',g,False,.04)
    arcade_stage('Campanile open belfry',cx,cy,z+12.5,5,4.7,g,opening=.8)
    B('Campanile belfry floor',(cx,cy,z+12.5),(4.3,4.3,.23),'stone',g,True)
    bell('Campanile bronze bell',cx,cy,z+14.1,g,1.3)
    # Engaged corner pilasters unify the separately editable shaft panels.
    for xx in (cx-2.52,cx+2.52):
        for yy in (cy-2.52,cy+2.52):B('Campanile corner pilaster',(xx,yy,z+8.5),(.28,.28,16.8),'stone',g)
    cylindrical_wall('Campanile octagonal dome drum',cx,cy,z+17.45,2.45,.75,g,'stone',12)
    dome('Campanile patinated lead dome',cx,cy,z+18.1,2.45,3.5,g)
    beam('Campanile finial',(cx,cy,z+21.5),(cx,cy,z+22.7),.065,'metal',g)
    beam('Campanile crossbar',(cx-.35,cy,z+22.35),(cx+.35,cy,z+22.35),.045,'metal',g)

    # Cathedral, facing the town along -Y, is a navigable hollow masonry shell.
    g='SM_Cathedral';cx=11;cy=67;z=25
    B('Cathedral broad stylobate',(cx,cy,z-.35),(15.4,25.4,.7),'stone',g,True)
    B('Cathedral nave stone floor',(cx,cy,z+.08),(13.3,23.3,.18),'stone',g,True)
    arch('Cathedral west portal','Y',55,4,18,z,z+13,cx,1.7,z+3.3,2.7,.7,1,'plaster',g,.4)
    # Projecting portal columns and stepped courses give the entry a deep reveal.
    for side in (-1,1):
        for j in range(3):
            xx=cx+side*(1.9+j*.22)
            beam('Cathedral portal limestone column',(xx,54.65-j*.1,z+.15),(xx,54.65-j*.1,z+3.3),.10,'stone',g)
    for step in range(4):B('Cathedral entry stair',(cx,53.6+step*.35,z-.45+step*.12),(5.8,.75,.20),'stone',g,True)
    for xx,inside in ((4,1),(18,-1)):
        wall('Cathedral aisle plinth','X',xx,55,79,z,z+4,.65,inside,'plaster',g)
        for i in range(6):
            yy=55+i*4
            arch('Cathedral nave lancet %d'%i,'X',xx,yy,yy+4,z+4,z+13,yy+2,.66,z+8.5,2.0,.65,inside,'plaster',g,.22)
            beam('Cathedral lancet mullion',(xx-inside*.06,yy+2,z+4.1),(xx-inside*.06,yy+2,z+10.3),.045,'stone',g)
            # External stepped flying buttress support without blocking windows.
            if i<5:
                outer=xx-inside*1.0
                B('Cathedral buttress lower',(outer,yy+.3,z+3.2),(.9,.75,6.4),'stone',g,True)
                B('Cathedral buttress upper',(outer+inside*.22,yy+.3,z+8.1),(.55,.65,3.5),'plaster',g)
                beam('Cathedral flying buttress',(outer,yy+.3,z+7),(xx,yy+.3,z+11),.22,'stone',g)
        B('Cathedral aisle cornice',(xx,cy,z+12.85),(.55,24.5,.30),'stone',g)
    perforated('Cathedral rear wall','Y',79,4,18,z,z+13,[(9.5,12.5,z+5,z+10)],.65,-1,'plaster',g)
    # Actual volumetric green roofs and smooth dome cross the nave mass.
    hiproof('Cathedral pitched nave roof',cx,cy,z+13.05,14.8,25,4.0,g,'roof')
    cylindrical_wall('Cathedral dome drum',cx,72,z+14.8,4.8,1.7,g,'plaster',32)
    for angle in range(0,360,30):
        a=math.radians(angle)
        xx=cx+4.84*math.cos(a);yy=72+4.84*math.sin(a)
        B('Cathedral drum limestone pilaster',(xx,yy,z+15.7),(.16,.16,1.7),'stone',g)
    dome('Cathedral grand crossing dome',cx,72,z+16.5,5,4.0,g)
    cylindrical_wall('Cathedral dome lantern drum',cx,72,z+20.4,.8,.75,g,'stone',12)
    dome('Cathedral lantern dome',cx,72,z+21.1,.9,.9,g)
    beam('Cathedral central finial',(cx,72,z+21.9),(cx,72,z+23.0),.06,'metal',g)
    beam('Cathedral central cross',(cx-.35,72,z+22.65),(cx+.35,72,z+22.65),.045,'metal',g)
    # Twin west towers are independent 3.5 m square architectural volumes.
    for index,tx in enumerate((5.75,16.25)):
        ty=56.75;tz=z;tw=3.5
        for axis,c,u,inside in [('X',tx+tw/2,ty,-1),('X',tx-tw/2,ty,1),('Y',ty-tw/2,tx,1),('Y',ty+tw/2,tx,-1)]:
            perforated('Cathedral tower %d shaft'%index,axis,c,u-tw/2,u+tw/2,tz,tz+17.5,[(u-.22,u+.22,tz+6,tz+8.3),(u-.26,u+.26,tz+12.1,tz+14.5)],.40,inside,'plaster',g)
        for h in (0,5,10,15,17.4,22.6):B('Cathedral tower %d cornice'%index,(tx,ty,tz+h),(3.85,3.85,.23),'stone',g)
        arcade_stage('Cathedral tower %d belfry'%index,tx,ty,tz+17.5,3.5,5,g,opening=.58)
        bell('Cathedral tower %d bell'%index,tx,ty,tz+19.3,g,.85)
        cylindrical_wall('Cathedral tower %d dome drum'%index,tx,ty,tz+22.7,1.8,.45,g,'stone',12)
        dome('Cathedral tower %d cap'%index,tx,ty,tz+23.1,1.82,2.3,g)
        beam('Cathedral tower %d finial'%index,(tx,ty,tz+25.3),(tx,ty,tz+26.1),.045,'metal',g)
    # Roofless monastery arcade to the right, exposing stone piers and broken gable.
    for xx,inside in ((21,1),(25,-1)):
        for i in range(5):
            a=56+i*4
            arch('Roofless monastery bay','X',xx,a,a+4,z,z+8.4,a+2,1.1,z+4.7,2.0,.55,inside,'stone',g,.28)
            if i%2==0:beam('Monastery snapped roof beam',(xx,a,z+8.3),(23,a,z+10.3),.12,'wood',g)
    arch('Monastery rear gable','Y',76,21,25,z,z+9,23,1,z+4.6,2,.5,-1,'plaster',g,.3)
    poly('Monastery broken triangular gable',[(21,z+9),(22.3,z+10.7),(22.5,z+9.9),(23.1,z+12),(24.1,z+10.1),(24.6,z+10.3),(25,z+9)],'Y',76,.5,-1,'stone',g,True)
    B('Monastery stone floor',(23,66,z+.02),(4.2,20.5,.20),'stone',g,True)

    # Two complete waterside villas, with shutters and asymmetric tiled roofs.
    g='SM_CliffVillas'
    for idx,(cx,cy,z) in enumerate(((7,24,6),(13,33,4))):
        w=5;d=7;h=8;prefix='Waterside villa %d'%idx
        B(prefix+' foundation',(cx,cy,z-.25),(5.5,7.5,.5),'stone',g,True)
        B(prefix+' floor',(cx,cy,z+.05),(4.5,6.5,.20),'stone',g,True)
        B(prefix+' upper floor',(cx,cy,z+4),(4.5,6.5,.18),'wood',g,True)
        for axis,c,u,length,inside in [('X',cx+2.5,cy,7,-1),('X',cx-2.5,cy,7,1),('Y',cy-3.5,cx,5,1),('Y',cy+3.5,cx,5,-1)]:
            holes=[(u-.55,u+.55,z+4.7,z+6.5)]
            if axis=='Y' and inside==1:holes.append((u-.65,u+.65,z,z+2.6))
            perforated(prefix+' wall',axis,c,u-length/2,u+length/2,z,z+h,holes,.35,inside,'plaster',g)
            frame(prefix+' upper window',axis,c-inside*.03,u,z+4.7,1.1,1.8,g,True)
        hiproof(prefix+' tiled hip roof',cx,cy,z+h,5.7,7.7,1.8,g,'roof')
        balcony(prefix+' harbour balcony',cx+2.5,cy,z+4.4,2.6,g)
        B(prefix+' chimney',(cx-1.5,cy+1.5,z+h+1),(.55,.65,2.6),'plaster',g,True)
        B(prefix+' chimney cap',(cx-1.5,cy+1.5,z+h+2.35),(.8,.9,.18),'stone',g)

    # Island lighthouse: actual tapered polygonal shaft with lantern and gallery.
    g='SM_Lighthouse';cx=58;cy=31;z=2
    cylindrical_wall('Lighthouse octagonal bastion',cx,cy,z,4.3,2.3,g,'stone',8)
    # The taper is a metric three dimensional mesh; gallery can be viewed all round.
    cylindrical_wall('Lighthouse tapered limestone shaft',cx,cy,z+2.3,1.8,11.7,g,'plaster',16,1.25)
    for h,r in ((2.3,1.85),(3,1.78),(12.9,1.44),(14,1.7)):
        cylindrical_wall('Lighthouse projecting stone belt',cx,cy,z+h,r,.22,g,'stone',16)
    cylindrical_wall('Lighthouse gallery floor',cx,cy,z+14.1,2.05,.22,g,'stone',24)
    # Lantern glass is deliberately dark and partially open, with metal mullions.
    cylindrical_wall('Lighthouse lantern lower curb',cx,cy,z+14.35,1.28,.20,g,'stone',16)
    for i in range(12):
        a=i*math.tau/12;b=(i+1)*math.tau/12
        xx=cx+1.23*math.cos(a);yy=cy+1.23*math.sin(a)
        beam('Lighthouse lantern mullion',(xx,yy,z+14.5),(xx,yy,z+16.2),.045,'metal',g)
        if i%3!=0:
            M('Lighthouse dark lantern pane',[(xx,yy,z+14.55),(cx+1.23*math.cos(b),cy+1.23*math.sin(b),z+14.55),(cx+1.23*math.cos(b),cy+1.23*math.sin(b),z+16.15),(xx,yy,z+16.15)],[(0,1,2,3)],'dark',g)
    dome('Lighthouse lantern copper cap',cx,cy,z+16.2,1.55,1.2,g,'roof',24)
    beam('Lighthouse finial',(cx,cy,z+17.3),(cx,cy,z+18.25),.05,'metal',g)
    # Gallery guard rail is individually editable and carries no collision.
    for i in range(24):
        a=i*math.tau/24;b=(i+1)*math.tau/24
        p=(cx+1.92*math.cos(a),cy+1.92*math.sin(a),z+15.2)
        q=(cx+1.92*math.cos(b),cy+1.92*math.sin(b),z+15.2)
        beam('Lighthouse circular gallery rail',p,q,.04,'metal',g)
        beam('Lighthouse gallery stanchion',(p[0],p[1],z+14.35),p,.035,'metal',g)
    # Exterior inset slit frames use dark recesses without cutting collision detail.
    for h in (6,10):
        for a in (0,math.pi/2,math.pi,math.pi*1.5):
            r=1.8-(h-2.3)/11.7*.55
            xx=cx+(r+.015)*math.cos(a);yy=cy+(r+.015)*math.sin(a)
            if abs(math.cos(a))>.5:B('Lighthouse shadow slit',(xx,yy,z+h),(.035,.22,.85),'dark',g)
            else:B('Lighthouse shadow slit',(xx,yy,z+h),(.22,.035,.85),'dark',g)
    return made
