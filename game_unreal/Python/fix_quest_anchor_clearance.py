"""Guarded bench/tree transform correction only; no map/kit/scenery regeneration.

Preserves manual edits, first baselines, story, era arrays, lights and shared
assets. Replays the six actual camera rays from the failed native story report.
Run in the root-granted full-editor queue, never as a commandlet.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,sys,traceback,math
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import build_quest_district as district
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
FOLDER=ROOT/'validation'/'quest_anchor_clearance'/STAMP;FOLDER.mkdir(parents=True,exist_ok=False)
OUT=ROOT/'quest_anchor_clearance_fix.json'
PLAN=json.loads(district.PLAN.read_text(encoding='utf-8'))
IDS=['quest.district.domestic.bench','quest.district.domestic.tree']
REPORT={'success':False,'run':STAMP,'scope':'Two owned actor transforms only; no map/asset/scenery regeneration','maps':[],
 'manual_edits_preserved':True,'headset_tested':False,'story_regression_rerun_pending':True,'continuous_walk_rerun_pending':True}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def assets():return {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'Content').rglob('*.uasset')}
def save_report():OUT.write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
def require(ok,message):
 if not ok:raise RuntimeError(message)
def local_manager():
 a=[a for a in district.world_actors() if a.actor_has_tag('Opening.Manager')]
 require(len(a)==1,'Expected one story manager');return a[0]

def floor_support(world,bench,tree):
 ignored=[bench,tree]+[a for a in district.world_actors() if a.actor_has_tag('Quest.NavigationNode')]
 rows=[]
 probes=[]
 # Bench feet (including their box corners), all within the original porch.
 for x in (-326,-274):
  for y in (1602.5,1623.5,1736.5,1757.5):probes.append(('bench',x,y))
 # Tree's actual30cm contact base plus complete33cm proxy points, at its authored scale; its rim
 # is wider above the ground and may overhang a slab edge without losing support.
 spec=next(p for p in PLAN['props'] if p['id']=='quest.district.domestic.tree');p=spec['position_cm'];scale=spec.get('scale',1)
 for dx in (-33,0,33):
  for dy in (-33,0,33):probes.append(('tree',p[0]+dx*scale,p[1]+dy*scale))
 for name,x,y in probes:
  hit=district.describe_hit(unreal.SystemLibrary.line_trace_single(world,unreal.Vector(x,y,1036),unreal.Vector(x,y,971),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,ignored,unreal.DrawDebugTrace.NONE,True))
  passed=hit['blocking'] and abs(hit['point_cm'][2]-1011)<=3
  rows.append({'prop':name,'xy_cm':[x,y],'expected_floor_cm':1011,'trace':hit,'passed':passed})
 require(all(r['passed'] for r in rows),'Native porch support failed: '+str([r for r in rows if not r['passed']]))
 return rows

def tree_body_clear(world,bench,tree):
 spec=next(p for p in PLAN['props'] if p['id']=='quest.district.domestic.tree');p=spec['position_cm'];scale=spec.get('scale',1)
 center=unreal.Vector(p[0],p[1],p[2]+24*scale)
 half=unreal.Vector(33*scale-.25,33*scale-.25,24*scale-.35)
 hit=unreal.SystemLibrary.box_trace_single(world,center,center+unreal.Vector(0,0,.1),half,unreal.Rotator(pitch=0,yaw=0,roll=0),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[tree],unreal.DrawDebugTrace.NONE,True)
 result=district.describe_hit(hit)
 require(not result['blocking'],'Tree pot overlaps inherited collision: '+str(result))
 return {'body_center_cm':district.xyz(center),'half_extent_cm':district.xyz(half),'trace':result,'passed':True}

def anchor_rays(world,anchor):
 # Exact observed starts from the failed story run, not newly favorable views.
 starts=[[-305,1281.544,1178.369],[-132.964,1536.018,1034.689],[-101.544,1450,1042.689],
         [-132.964,1363.982,1142.212],[-305,1251.544,1178.369],[-305,1648.456,1178.369]]
 rows=[];target=anchor.get_actor_location()
 for i,p in enumerate(starts):
  start=unreal.Vector(*p);direction=target-start;length=math.sqrt(direction.x**2+direction.y**2+direction.z**2)
  end=start+direction*(900/length)
  hit=unreal.SystemLibrary.line_trace_single(world,start,end,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
  value=hit.to_tuple();actor=value[9]
  rows.append({'approach_index':i+1,'camera_cm':p,'target_cm':district.xyz(target),'hit_actor':actor.get_name() if actor else None,'passed':bool(value[0]) and actor==anchor})
 require(all(r['passed'] for r in rows),'Not all six inherited anchor approach rays hit the anchor: '+str(rows))
 return rows

def main():
 production=json.loads(district.OUT.read_text(encoding='utf-8'))
 protected_assets=assets();protected_saves={str(p):sha(p) for p in (ROOT/'Saved/SaveGames').glob('*.sav')}
 REPORT['assets_sha_before']=protected_assets
 manifest=json.loads((district.SOURCE/'manifest.json').read_text(encoding='utf-8'))
 REPORT['anchor_reservation']=district.validate_anchor_reservation(PLAN,manifest)
 # Preflight both maps before any save, including explicit and inferred manuals.
 for path in PLAN['target_maps']:
  require(district.LEVEL.load_level(path),'Cannot load '+path)
  record=next(r for r in production['maps'] if r['path']==path)
  prior=json.loads(Path(record['after_snapshot']).read_text(encoding='utf-8'))
  guard={'preserved_manual':[],'inferred_manual_names':list(record.get('inferred_manual_names',[]))}
  for id in IDS:
   actor=district.unique(id)
   require(actor is not None and actor.actor_has_tag(district.OWNED),'Missing owned actor '+id)
   require(district.editable(actor,prior,guard),'Manual/externally edited actor must be preserved: '+id+' '+str(guard))
 for path in PLAN['target_maps']:
  require(district.LEVEL.load_level(path),'Cannot load '+path)
  record=next(r for r in production['maps'] if r['path']==path);manager=local_manager();world=district.EDITOR.get_editor_world()
  before=district.snapshot();story=district.referenced_story_transforms(manager)
  arrays={f:[a.get_name() for a in manager.get_editor_property(f)] for f in district.ARRAY_FIELDS}
  slot=str(manager.get_editor_property('SaveSlot'))
  before_file=FOLDER/(path.rsplit('/',1)[-1]+'_before.json');before_file.write_text(json.dumps(before,indent=2),encoding='utf-8')
  row={'path':path,'before_snapshot':str(before_file),'locations_before':{id:district.xyz(district.unique(id).get_actor_location()) for id in IDS}}
  for id in IDS:
   spec=next(p for p in PLAN['props'] if p['id']==id)
   district.unique(id).set_actor_location(unreal.Vector(*spec['position_cm']),False,False)
   scale=spec.get('scale',1);district.unique(id).set_actor_scale3d(unreal.Vector(scale,scale,scale))
  bench,tree=(district.unique(id) for id in IDS)
  row['floor_support']=floor_support(world,bench,tree)
  row['tree_body_clearance']=tree_body_clear(world,bench,tree)
  row['anchor_approach_rays']=anchor_rays(world,manager.get_editor_property('AnchorActor'))
  after=district.snapshot();changed=[name for name,state in before.items() if after.get(name)!=state]
  require(set(changed)<={bench.get_name(),tree.get_name()},'Unexpected actor edits: '+str(changed))
  require(story==district.referenced_story_transforms(manager),'Reserved story transforms changed')
  require(arrays=={f:[a.get_name() for a in manager.get_editor_property(f)] for f in district.ARRAY_FIELDS},'Era arrays changed')
  require(slot==str(manager.get_editor_property('SaveSlot')),'Campaign save slot changed')
  require(district.LEVEL.save_current_level(),'Cannot save guarded relocation '+path)
  after_file=FOLDER/(path.rsplit('/',1)[-1]+'_after.json');after_file.write_text(json.dumps(after,indent=2),encoding='utf-8')
  row.update(after_snapshot=str(after_file),locations_after={id:district.xyz(district.unique(id).get_actor_location()) for id in IDS},changed_actors=changed,story_unchanged=True,era_arrays_unchanged=True,save_slot_unchanged=True)
  record['after_snapshot']=str(after_file) # retain original baseline_snapshot
  record.setdefault('guarded_geometry_fixes',[]).append({'run':STAMP,'report':str(OUT),'purpose':'Clear the existing time anchor interaction rays','ids':IDS})
  REPORT['maps'].append(row);save_report()
 require(protected_assets==assets(),'A shared/versioned asset changed unexpectedly')
 require(protected_saves=={str(p):sha(p) for p in (ROOT/'Saved/SaveGames').glob('*.sav')},'Save files changed unexpectedly')
 production['anchor_reservation']=REPORT['anchor_reservation']
 district.OUT.write_text(json.dumps(production,indent=2),encoding='utf-8')
 REPORT.update(success=True,shared_assets_unchanged=True,save_files_unchanged=True)

if __name__=='__main__':
 try:main()
 except Exception:REPORT['error']=traceback.format_exc();unreal.log_error(REPORT['error'])
 finally:
  save_report();unreal.log('QUEST_ANCHOR_CLEARANCE_FIX '+str(REPORT['success']));unreal.SystemLibrary.quit_editor()
