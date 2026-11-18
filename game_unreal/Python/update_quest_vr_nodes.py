"""Apply only native-audited minimum VR marker/era fixes to the two Quest maps."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import build_quest_district as district
import audit_quest_vr_coverage as audit
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
OUT=ROOT/'quest_vr_node_update.json';FOLDER=ROOT/'validation/vr_node_update'/STAMP;FOLDER.mkdir(parents=True,exist_ok=False)
REPORT={'success':False,'run':STAMP,'maps':[],'scope':'Minimum audited navigation marker/era changes only; no city/asset regeneration',
 'story_flags_written':False,'interaction_range_changed':False,'headset_tested':False,'actual_quest_teleport_pending':True}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def require(ok,message):
 if not ok:raise RuntimeError(message)
def write():OUT.write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
def manager():
 found=[a for a in district.world_actors() if a.actor_has_tag('Opening.Manager')];require(len(found)==1,'One manager required');return found[0]
def actor_visibility():return {a:(bool(a.get_editor_property('hidden')),bool(a.get_actor_enable_collision())) for a in district.world_actors()}
def restore_visibility(saved):
 for actor,(hidden,enabled) in saved.items():actor.set_actor_hidden_in_game(hidden);actor.set_actor_enable_collision(enabled)

def main():
 evidence=json.loads((ROOT/'quest_vr_interaction_coverage.json').read_text())
 require(evidence['success'] and evidence.get('minimum_change_coverage_complete'),'Native coverage must prove complete minimum changes before save')
 require(evidence['protected_maps_and_saves_unchanged'],'Read-only audit preservation failed')
 require(evidence['actual_interaction_range_cm']==260,'Unexpected interaction range; do not change it')
 plan=json.loads(district.PLAN.read_text());production=json.loads(district.OUT.read_text())
 before_plan=sha(district.PLAN);changes=evidence['recommended_changes'];affected={'home_inside'}
 for change in changes:
  if change['action']=='add':
   node=change['node'];require(node['id']=='home_workshop','Only the approved home node may be added by this helper')
   spec=next((n for n in plan['navigation_nodes'] if n['id']==node['id']),None)
   if spec is None:spec={'id':node['id'],'radius_cm':45,'tier':'core','district':'domestic_court'};plan['navigation_nodes'].append(spec)
   spec.update(floor_cm=node['floor_cm'],era='Present');affected.add(node['id'])
  elif change['action']=='move':
   require(change['node'] in ['clinic_approach','sela_service','market_approach'],'Unauthorised marker movement')
   next(n for n in plan['navigation_nodes'] if n['id']==change['node'])['floor_cm']=change['floor_cm'];affected.add(change['node'])
  elif change['action']=='era':
   require(change['node']=='home_inside' and change['era']=='Present','Only present interior gating may change')
   next(n for n in plan['navigation_nodes'] if n['id']=='home_inside')['era']='Present'
 require(['home_inside','home_workshop'] in plan['planned_edges'],'Workshop must have an authored first-hop edge')
 assets={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'Content').rglob('*.uasset')}
 saves={str(p):sha(p) for p in (ROOT/'Saved/SaveGames').glob('*.sav')}
 records={r['path']:r for r in production['maps']}
 # Preflight ownership/manual states in both maps before any mutation/save.
 for path in plan['target_maps']:
  require(district.LEVEL.load_level(path),'Cannot open '+path);record=records[path]
  prior=json.loads(Path(record['after_snapshot']).read_text());guard={'preserved_manual':[],'inferred_manual_names':list(record.get('inferred_manual_names',[]))}
  for id in affected:
   actor=district.unique('quest.nav.'+id)
   if actor:require(actor.actor_has_tag(district.OWNED) and district.editable(actor,prior,guard),'Preserve manual/unowned marker '+id+' '+str(guard))
   else:require(id=='home_workshop','Missing existing navigation node '+id)
 manifest=json.loads((district.SOURCE/'manifest.json').read_text());entries={a['name']:a for a in manifest['assets']}
 mesh_names={s['mesh'] for s in district.navigation_specs(plan) if s['id'].removeprefix('quest.nav.') in affected}
 kit={name:district.load_asset(production['asset_namespace']+'/Meshes/'+name) for name in mesh_names};require(all(kit.values()),'Existing landing meshes missing')
 for path in plan['target_maps']:
  require(district.LEVEL.load_level(path),'Cannot open '+path);world=district.EDITOR.get_editor_world();m=manager();record=records[path]
  before=district.snapshot();refs=district.referenced_story_transforms(m);slot=str(m.get_editor_property('SaveSlot'));range_before=float(m.get_editor_property('InteractionRange'))
  arrays={f:[a.get_name() for a in m.get_editor_property(f)] for f in district.ARRAY_FIELDS}
  baseline=record['baseline_snapshot'];baseline_hash=sha(Path(baseline));prior=json.loads(Path(record['after_snapshot']).read_text())
  row={'path':path,'preserved_manual':[],'inferred_manual_names':list(record.get('inferred_manual_names',[])),'added_or_updated':[]}
  for spec in district.navigation_specs(plan):
   if spec['id'].removeprefix('quest.nav.') in affected:district.apply_prop(spec,kit,entries,prior,row)
  district.register_era_props(m);district.ensure_refs_in_clone(m,path)
  district.validate_navigation(world,plan,row)
  require(not row['navigation_validation']['core_unreachable'],'Core graph is disconnected')
  require(row['navigation_validation']['all_spawned_supported_and_capsule_clear'],'A landing lacks floor/capsule clearance')
  saved=actor_visibility()
  try:
   audit.RANGE=range_before;coverage=audit.coverage(world,m,audit.nodes());row['interaction_coverage']=coverage
   require(not audit.gaps(coverage),'Native post-update fixed-node interaction gap: '+str(audit.gaps(coverage)))
   # Exercise the same era grouping used by the framework, without changing
   # EraIndex, inventory, trust, clues, progress or saved flags.
   audit.era(m,'Past')
   interiors=[district.unique('quest.nav.'+id) for id in ['home_inside','home_workshop']]
   row['past_interiors_hidden_and_query_disabled']=all(a.get_editor_property('hidden') and not a.get_actor_enable_collision() for a in interiors)
   porch=district.unique('quest.nav.home_porch');row['past_porch_remains_query_enabled']=porch.get_actor_enable_collision()
   require(row['past_interiors_hidden_and_query_disabled'] and row['past_porch_remains_query_enabled'],'Interior era gating is unsafe')
  finally:restore_visibility(saved)
  require(refs==district.referenced_story_transforms(m),'Story transforms changed')
  require(slot==str(m.get_editor_property('SaveSlot')) and range_before==float(m.get_editor_property('InteractionRange')),'Save slot/range changed')
  for field in ['PastActors','PastCollisionActors']:require(arrays[field]==[a.get_name() for a in m.get_editor_property(field)],'Unrelated era array changed')
  current_present=[a.get_name() for a in m.get_editor_property('PresentActors')]
  require(set(arrays['PresentActors'])<=set(current_present),'Original present references were lost')
  after=district.snapshot();changed=[name for name,value in before.items() if value!=after.get(name)]
  allowed={district.unique('quest.nav.'+id).get_name() for id in affected}
  require(set(changed)<=allowed,'Unrelated actor state changed: '+str(changed))
  require(district.LEVEL.save_current_level(),'Cannot save minimal node fixes')
  after_file=FOLDER/(path.rsplit('/',1)[-1]+'_after.json');after_file.write_text(json.dumps(after,indent=2))
  record['after_snapshot']=str(after_file);record.setdefault('guarded_navigation_updates',[]).append({'run':STAMP,'report':str(OUT),'node_ids':sorted(affected)})
  require(sha(Path(baseline))==baseline_hash,'First baseline changed')
  row.update(after_snapshot=str(after_file),story_transforms_unchanged=True,save_slot_and_interaction_range_unchanged=True,baseline_preserved=True,
   new_present_refs=[n for n in current_present if n not in arrays['PresentActors']],changed_actor_names=changed)
  REPORT['maps'].append(row);write()
 require(all(sha(ROOT/path)==value for path,value in assets.items()),'Existing assets changed')
 require(saves=={str(p):sha(p) for p in (ROOT/'Saved/SaveGames').glob('*.sav')},'Save files changed')
 district.PLAN.write_text(json.dumps(plan,indent=2),encoding='utf-8');district.OUT.write_text(json.dumps(production,indent=2),encoding='utf-8')
 REPORT.update(success=True,source_plan_sha_before=before_plan,source_plan_sha_after=sha(district.PLAN),source_plan_synchronised=True,
  active_node_count=sum(n['tier']!='optional_lower_harbor' for n in plan['navigation_nodes']),affected_nodes=sorted(affected),assets_and_saves_unchanged=True)

try:main()
except Exception:REPORT['error']=traceback.format_exc();unreal.log_error(REPORT['error'])
finally:write();unreal.log('QUEST_VR_NODE_UPDATE '+str(REPORT['success']));unreal.SystemLibrary.quit_editor()
