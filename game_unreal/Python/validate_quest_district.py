"""Native district assets, harbor guards and reversible generation acceptance.

Uses a fresh test map for manual-edit/idempotence/revert checks. Production maps
are read only. No device performance or complete walking-route claim is made.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, sys, traceback
import unreal

ROOT=Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/'Python'))
import build_quest_district as district

STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
FOLDER=ROOT/'validation'/'quest_district_guards'/STAMP
FOLDER.mkdir(parents=True,exist_ok=False)
REPORT={'success':False,'run':STAMP,'checks':[],
        'scope':'Native imported geometry, scene references, shore collision and isolated generation guards',
        'continuous_walk_tested':False,'headset_tested':False,'performance_measured':False}
OUT=ROOT/'quest_district_validation.json'

def check(name,ok,evidence=None):
    row={'name':name,'passed':bool(ok)}
    if evidence is not None:row['evidence']=evidence
    REPORT['checks'].append(row)
    if not ok:raise AssertionError(name+': '+str(evidence))

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def owned():return [a for a in district.world_actors() if a.actor_has_tag(district.OWNED)]
def ids():
    result={}
    for a in owned():
        for t in a.get_editor_property('tags'):
            s=str(t)
            if s.startswith(('quest.district.','quest.nav.','quest.review.')):
                result[s]=result.get(s,0)+1
    return result

def main():
    original_plan,original_out=district.PLAN,district.OUT
    production=json.loads(original_out.read_text(encoding='utf-8'))
    plan=json.loads(original_plan.read_text(encoding='utf-8'))
    protected={ROOT/'Content'/(p.removeprefix('/Game/')+'.umap'):None for p in plan['target_maps']}
    protected[original_out]=None
    protected={p:sha(p) for p in protected}
    try:
        check('Restricted Quest project',ROOT.parent.name=='Quest_20261025')
        check('Two saved district maps exist',production['success'] and len(production['maps'])==2)
        static=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        check('Initialized native static-mesh editor is available',static is not None)
        manifest=json.loads((district.SOURCE/'manifest.json').read_text(encoding='utf-8'))
        mesh_rows=[]
        for entry in manifest['assets']:
            path=production['asset_namespace']+'/Meshes/'+entry['name']
            mesh=unreal.load_asset(path)
            check('Imported semantic mesh '+entry['name'],isinstance(mesh,unreal.StaticMesh))
            check('Renderable vertices '+entry['name'],static.get_number_verts(mesh,0)>0)
            count=static.get_simple_collision_count(mesh)+static.get_convex_collision_count(mesh)
            expected=entry.get('collision_count',0)
            check('Explicit imported collision '+entry['name'],count>=expected if expected else count==0,{'expected':expected,'actual':count})
            materials=[mesh.get_material(i) for i in range(len(mesh.get_editor_property('static_materials')))]
            check('Assigned versioned materials '+entry['name'],bool(materials) and all(m and m.get_path_name().startswith(production['asset_namespace']+'/Materials/') for m in materials))
            mesh_rows.append({'mesh':path,'vertices':static.get_number_verts(mesh,0),'source_triangles':entry['triangles'],'collisions':count,'material_slots':len(materials)})
        REPORT['meshes']=mesh_rows
        REPORT['maps']=[]
        for record in production['maps']:
            path=record['path'];check('Load native map '+path,district.LEVEL.load_level(path))
            world=district.EDITOR.get_editor_world()
            manager=next(a for a in district.world_actors() if a.actor_has_tag('Opening.Manager'))
            refs=[]
            for field in district.REF_FIELDS+district.ARRAY_FIELDS:
                value=manager.get_editor_property(field)
                values=list(value) if field in district.ARRAY_FIELDS else [value]
                refs.extend(a for a in values if a)
            check('All chapter references remain local '+path,all(a.get_path_name().startswith(path+'.') for a in refs))
            check('Unique owned stable IDs '+path,bool(ids()) and all(n==1 for n in ids().values()),ids())
            check('Core teleport circuit is supported '+path,not record['navigation_validation']['core_unreachable'],record['navigation_validation'])
            for y in [-1735,-1605,-1195,-1065]:
                floor=1020-.1*y
                hit=district.describe_hit(unreal.SystemLibrary.line_trace_single(world,
                    unreal.Vector(200,y,floor+65),unreal.Vector(400,y,floor+65),
                    unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True))
                check('Visible shore return blocks crossing '+path+' Y'+str(y),hit['blocking'],hit)
            comps=[]
            for a in district.world_actors():
                c=a.get_component_by_class(unreal.StaticMeshComponent)
                if c and c.get_editor_property('static_mesh'):
                    comps.append({'actor':a.get_name(),'mesh':c.get_editor_property('static_mesh').get_path_name(),'material_slots':c.get_num_materials()})
            REPORT['maps'].append({'path':path,'static_mesh_components':len(comps),
                'material_slot_sum_upper_bound':sum(c['material_slots'] for c in comps),
                'budget_note':'Scene inventory; these are not measured visible draw calls, GPU time or frame rate.'})
        test='/Game/Quest/Maps/Tests/DistrictGuard_'+STAMP
        plan['target_maps']=[test]
        plan_path=FOLDER/'plan.json';plan_path.write_text(json.dumps(plan,indent=2),encoding='utf-8')
        district.PLAN=plan_path;district.OUT=FOLDER/'build.json'
        first=district.build_district();check('Isolated first generation succeeds',first['success'])
        before_count=len(owned());baseline=Path(first['maps'][0]['baseline_snapshot']);baseline_sha=sha(baseline)
        tagged=district.unique('quest.district.domestic.bench')
        detected=district.unique('quest.district.market.sign')
        district.tag_add(tagged,district.MANUAL)
        tagged.set_actor_location(tagged.get_actor_location()+unreal.Vector(17,0,0),False,False)
        detected.set_actor_location(detected.get_actor_location()+unreal.Vector(0,21,0),False,False)
        expected=[district.state(tagged),district.state(detected)]
        names={tagged.get_name(),detected.get_name()}
        check('Save isolated manual-edit samples',district.LEVEL.save_current_level())
        for iteration in [2,3]:
            rerun=district.build_district();row=rerun['maps'][0]
            check('Rerun preserves tagged and detected manual transforms '+str(iteration),[district.state(district.unique('quest.district.domestic.bench')),district.state(district.unique('quest.district.market.sign'))]==expected)
            check('Rerun has no duplicate owned actors '+str(iteration),len(owned())==before_count and all(n==1 for n in ids().values()))
            check('Rerun retains first baseline '+str(iteration),row['baseline_snapshot']==str(baseline) and sha(baseline)==baseline_sha)
        reverted=district.revert_district(test);REPORT['revert']=reverted
        check('Revert retains only the two edited district actors',{a.get_name() for a in owned()}==names)
        check('Production maps and generator report stay byte-identical',all(sha(p)==v for p,v in protected.items()))
        REPORT['test_map']=test
        REPORT['success']=all(c['passed'] for c in REPORT['checks'])
    except Exception:
        REPORT['error']=traceback.format_exc()
        unreal.log_error(REPORT['error'])
    finally:
        district.PLAN,district.OUT=original_plan,original_out
        OUT.write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
        (FOLDER/'report.json').write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
        unreal.SystemLibrary.quit_editor()

if __name__=='__main__':main()
