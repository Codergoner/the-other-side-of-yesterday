"""Read-only native coverage/capsule audit; root owns the full-editor queue.

Temporarily mirrors era visibility and authored NPC runtime endpoints without
writing story flags, save data, maps or assets. Tests fixed node XY from seated
hand80/head110 and standing hand110/head160 origins. This is spatial evidence,
not headset/controller testing or a four-route gameplay acceptance.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,math,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import build_quest_district as district
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
OUT=ROOT/'quest_vr_interaction_coverage.json'
MAP='/Game/Quest/Maps/Verdant_VR'
HEIGHTS={'seated_controller80':80,'seated_head110':110,'standing_controller110':110,'standing_head160':160}
CASES=[
 ('photo','PhotoActor','Present',None),('letter','LetterActor','Present',None),
 ('mother_home','MotherActor','Present',None),('workbench','BenchActor','Present',None),
 ('prepared_contact','ComponentActor','Present',None),('anchor_present','AnchorActor','Present',None),
 ('memorial','MemorialActor','Present',None),('mother_gate','MotherActor','Present',[-40,1240,896]),
 ('mother_return_street','MotherActor','Present',[-420,1340,1011]),
 ('neri_gate','NeriActor','Past',None),('healer','HealerActor','Past',None),('sela','SelaActor','Past',None),
 ('water','WaterActor','Past',None),('linen_parcel','LinenActor','Past',None),('linen_tray','LinenTrayActor','Past',None),
 ('waterproof_canvas','CanvasActor','Past',None),('clinic_fixings','ClinicInstallActor','Past',None),
 ('harbor_fixings','HarborInstallActor','Past',None),('anchor_past','AnchorActor','Past',None),
 ('neri_harbor_restored','NeriActor','Past',[120,-570,1077]),
 ('neri_harbor_walk_end','NeriActor','Past',[115,-610,1081]),
]
WORKSHOPS=[[-830,1200,1011],[-820,1200,1011],[-810,1200,1011],[-840,1200,1011],[-830,1190,1011],[-820,1190,1011],[-810,1210,1011]]
CLINIC_ALTERNATIVES=[[-40,580,962],[-20,580,962],[0,560,964],[-30,550,965],[-40,520,968],[-15,300,990]]
REPORT={'success':False,'run':STAMP,'map':MAP,'headset_tested':False,'physical_controller_tested':False,
 'story_flags_written':False,'progress_seeded':False,'maps_or_assets_saved':False,
 'scope':'Fixed-node native Visibility queries at four rest/view heights; conditional targets and authored NPC endpoints are transient diagnostic fixtures only',
 'height_profiles_cm':HEIGHTS,'current':[],'proposed':[],'recommended_changes':[]}

def require(ok,message):
 if not ok:raise RuntimeError(message)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def set_visible(actor,show):
 blocking=any(actor.actor_has_tag(t) for t in ['Opening.Interactable','Opening.Blocking','Opening.OriginalCollision'])
 actor.set_actor_hidden_in_game(not show);actor.set_actor_enable_collision(show and blocking)
def era(manager,which):
 for field,show in [('PastActors',which=='Past'),('PresentActors',which=='Present')]:
  for actor in manager.get_editor_property(field):set_visible(actor,show)
 # Conditional objects are audited at their legal availability phases without
 # granting the inventory/state that normally makes them available.
 for field in ['ComponentActor','LinenActor','CanvasActor']:
  actor=manager.get_editor_property(field)
  if actor:set_visible(actor,(field=='ComponentActor')==(which=='Present'))
def node_era(actor):
 if actor.actor_has_tag('Opening.PresentOnly'):return 'Present'
 if actor.actor_has_tag('Opening.PastOnly'):return 'Past'
 return None
def nodes():
 out=[]
 for actor in district.world_actors():
  if not actor.actor_has_tag('Quest.Teleport'):continue
  ids=[str(t).removeprefix('quest.nav.') for t in actor.get_editor_property('tags') if str(t).startswith('quest.nav.')]
  if ids:out.append({'id':ids[0],'floor_cm':district.xyz(actor.get_actor_location()),'era':node_era(actor)})
 return out
def ray(world,start,target):
 point=target.get_actor_bounds(False)[0] if target.get_component_by_class(unreal.SkeletalMeshComponent) else target.get_actor_location()
 delta=point-start;length=math.sqrt(delta.x**2+delta.y**2+delta.z**2)
 end=start+delta*(RANGE/max(length,.001))
 hit=unreal.SystemLibrary.line_trace_single(world,start,end,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
 values=hit.to_tuple() if hit is not None else None;actor=values[9] if values else None
 return {'origin_cm':district.xyz(start),'target_cm':district.xyz(point),'center_distance_cm':round(length,3),
  'selected_target':bool(values and values[0]) and actor==target,'hit_actor':actor.get_name() if actor else None,'hit_label':actor.get_actor_label() if actor else None}
def coverage(world,manager,places):
 rows=[]
 for id,ref,which,runtime_location in CASES:
  era(manager,which);target=manager.get_editor_property(ref);original=target.get_actor_transform()
  if runtime_location:target.set_actor_location(unreal.Vector(*runtime_location),False,False)
  try:
   set_visible(target,True);profiles={}
   for profile,height in HEIGHTS.items():
    attempts=[]
    for place in places:
     if place.get('era') and place['era']!=which:continue
     p=place['floor_cm'];result=ray(world,unreal.Vector(p[0],p[1],p[2]+height),target);result['node']=place['id'];attempts.append(result)
    profiles[profile]={'covered_by':[a['node'] for a in attempts if a['selected_target']],'attempts':attempts}
   rows.append({'id':id,'ref':ref,'era':which,'authored_runtime_location_fixture_cm':runtime_location,'profiles':profiles,
    'all_profiles_covered':all(p['covered_by'] for p in profiles.values())})
  finally:target.set_actor_transform(original,False,False)
 return rows
def gaps(rows):return [{'case':r['id'],'profiles':[name for name,p in r['profiles'].items() if not p['covered_by']]} for r in rows if not r['all_profiles_covered']]
def capsule_probe(world,p):
 ignored=[a for a in district.world_actors() if a.actor_has_tag('Quest.NavigationNode')]
 floor=district.describe_hit(unreal.SystemLibrary.line_trace_single(world,unreal.Vector(p[0],p[1],p[2]+35),unreal.Vector(p[0],p[1],p[2]-65),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,ignored,unreal.DrawDebugTrace.NONE,True))
 center=unreal.Vector(p[0],p[1],p[2]+93)
 body=district.describe_hit(unreal.SystemLibrary.capsule_trace_single(world,center,center+unreal.Vector(0,0,.1),34,88,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,ignored,unreal.DrawDebugTrace.NONE,True))
 return {'floor_cm':p,'floor_trace':floor,'capsule_trace':body,'passed':floor['blocking'] and abs(floor['point_cm'][2]-p[2])<3 and not body['blocking']}

def main():
 global RANGE
 require((ROOT.parent/'quest_baseline_manifest.json').exists(),'Quest copy only')
 protected={ROOT/'Content/Quest/Maps/Verdant_VR.umap':None,ROOT/'Content/Quest/Maps/Verdant_Desktop.umap':None}
 protected.update({p:None for p in (ROOT/'Saved/SaveGames').glob('*.sav')});protected={p:sha(p) for p in protected}
 require(district.LEVEL.load_level(MAP),'Cannot load VR map');world=district.EDITOR.get_editor_world()
 manager=next(a for a in district.world_actors() if a.actor_has_tag('Opening.Manager'))
 RANGE=float(manager.get_editor_property('InteractionRange'));REPORT['actual_interaction_range_cm']=RANGE
 current=nodes();REPORT['existing_nodes']=current;REPORT['current']=coverage(world,manager,current);REPORT['current_gaps']=gaps(REPORT['current'])
 proposed=[dict(n) for n in current]
 for n in proposed:
  if n['id']=='home_inside':n['era']='Present'
 REPORT['workshop_candidates']=[];chosen=None
 era(manager,'Present')
 for p in WORKSHOPS:
  era(manager,'Present')
  probe=capsule_probe(world,p);REPORT['workshop_candidates'].append(probe)
  if not probe['passed']:continue
  candidate={'id':'home_workshop','floor_cm':p,'era':'Present'}
  rows=coverage(world,manager,proposed+[candidate]);required=[r for r in rows if r['id'] in ['mother_home','workbench','prepared_contact']]
  probe['home_interaction_profiles_covered']=all(r['all_profiles_covered'] for r in required)
  if probe['home_interaction_profiles_covered']:chosen=candidate;break
 require(chosen is not None,'No safe workshop candidate covers Mother/workbench/contact at all rest/view heights')
 proposed.append(chosen);REPORT['recommended_changes'].append({'action':'add','node':chosen})
 REPORT['recommended_changes'].append({'action':'era','node':'home_inside','era':'Present'})
 rows=coverage(world,manager,proposed)
 if gaps(rows):
  REPORT['clinic_adjustment_candidates']=[]
  for p in CLINIC_ALTERNATIVES:
   era(manager,'Past');probe=capsule_probe(world,p);REPORT['clinic_adjustment_candidates'].append(probe)
   if not probe['passed']:continue
   candidate_places=[dict(n,floor_cm=p) if n['id']=='clinic_approach' else dict(n) for n in proposed]
   tested=coverage(world,manager,candidate_places);probe['remaining_gaps']=gaps(tested)
   if not gaps(tested):
    proposed=candidate_places;rows=tested;REPORT['recommended_changes'].append({'action':'move','node':'clinic_approach','floor_cm':p});break
 REPORT['proposed_nodes']=proposed;REPORT['proposed']=rows;REPORT['remaining_gaps']=gaps(rows)
 REPORT['minimum_change_coverage_complete']=not gaps(rows)
 # New/changed destinations need actual QuestTeleport gameplay tests later.
 REPORT['native_quest_teleport_test_pending']=True
 require(district.LEVEL.load_level(MAP),'Cannot discard transient diagnostic era/pose changes')
 REPORT['protected_maps_and_saves_unchanged']=all(sha(p)==v for p,v in protected.items())
 require(REPORT['protected_maps_and_saves_unchanged'],'Read-only audit altered a protected file')
 REPORT['success']=True

if __name__=='__main__':
 try:main()
 except Exception:REPORT['error']=traceback.format_exc();unreal.log_error(REPORT['error'])
 finally:
  try:district.LEVEL.load_level(MAP)
  except Exception:pass
  OUT.write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
  unreal.log('QUEST_VR_COVERAGE_AUDIT '+str(REPORT['success']));unreal.SystemLibrary.quit_editor()
