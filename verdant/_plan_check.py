import sys, json, math
sys.path.insert(0, r'C:\Users\USER\OneDrive\Documents\ChatGPT\The other side of yesterday\development\Release_20261026\verdant')
import verdant_plan as v
v.write()
B = v.BUILDINGS
rects = []
for b in B:
    pts = [b.world(0,0)[:2], b.world(b.w*v.BW,0)[:2], b.world(b.w*v.BW,b.d*v.BW)[:2], b.world(0,b.d*v.BW)[:2]]
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    rects.append((b.name,min(xs),max(xs),min(ys),max(ys),b.z))
clash=0
for i,a in enumerate(rects):
    for c in rects[i+1:]:
        ox=min(a[2],c[2])-max(a[1],c[1]); oy=min(a[4],c[4])-max(a[3],c[3])
        if ox>.05 and oy>.05:
            print('OVERLAP',a[0],c[0],round(ox,2),round(oy,2)); clash+=1
for s in v.SURFACES:
    for n,x0,x1,y0,y1,z in rects:
        ox=min(x1,s['x1'])-max(x0,s['x0']); oy=min(y1,s['y1'])-max(y0,s['y0'])
        if ox>.7 and oy>.7 and s['name'] not in ('VillaTerrace','VillaLow','Quay','LighthouseIsland'):
            print('ON WALKWAY',n,s['name'],round(ox,2),round(oy,2)); clash+=1
print('clashes',clash,'buildings',len(B))