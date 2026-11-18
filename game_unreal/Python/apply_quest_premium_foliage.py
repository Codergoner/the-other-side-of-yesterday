"""Guarded approved foliage mesh swap only; no district or scenery regeneration."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys,traceback,math
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import build_quest_district as district
import fix_quest_anchor_clearance as clearance
SOURCE=ROOT.parent/'output/premium_foliage'
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
FOLDER=ROOT/'validation/premium_foliage'/STAMP;FOLDER.mkdir(parents=True,exist_ok=False)
OUT=ROOT/'quest_premium_foliage_report.json'
IDS=['quest.district.domestic.tree','quest.district.clinic.tree','quest.district.harbor.tree']
REPORT={'success':False,'run':STAMP,'scope':'Approved new versioned foliage mesh and three owned tree mesh assignments per map only',
 'maps':[],'actor_transforms_edited':False,'headset_tested':False,'performance_measured':False,'regeneration_test_pending':True}

def require(ok,message):
 if not ok:raise RuntimeError(message)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
def all_assets():return {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'Content').rglob('*.uasset')}
def write():OUT.write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
def geometry_vertices(mesh):
 setup=mesh.get_editor_property('body_setup');agg=setup.get_editor_property('agg_geom');hulls=list(agg.get_editor_property('convex_elems'))
 rows=[]
 for hull in hulls:
  vertices=list(hull.get_editor_property('vertex_data'))
  rows.append(sorted(set(tuple(round(float(getattr(v,a)),4) for a in ['x','y','z']) for v in vertices)))
 return rows

def collision_probe(world,old,new):
 actors=[];results=[]
 try:
  for index,mesh in enumerate([old,new]):
   origin=unreal.Vector(100000+index*300,100000,10000)
   actor=district.ACTORS.spawn_actor_from_class(unreal.StaticMeshActor,origin,unreal.Rotator(pitch=0,yaw=0,roll=0));actors.append(actor)
   comp=actor.get_component_by_class(unreal.StaticMeshComponent);comp.set_static_mesh(mesh);comp.set_collision_profile_name('BlockAll');actor.set_actor_enable_collision(True)
   rows=[];center=origin+unreal.Vector(0,0,24)
   for axis in range(3):
    for sign in [-1,1]:
     delta=[0,0,0];delta[axis]=sign*80;start=center+unreal.Vector(*delta)
     hit=unreal.SystemLibrary.line_trace_single(world,start,center,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
     value=hit.to_tuple();require(value[0] and value[9]==actor,'Native collision boundary probe missed '+mesh.get_name())
     point=value[5]-origin;rows.append({'axis':axis,'sign':sign,'local_impact_cm':district.xyz(point)})
   results.append(rows)
  require(all(max(abs(a-b) for a,b in zip(x['local_impact_cm'],y['local_impact_cm']))<=.01 for x,y in zip(results[0],results[1])),'Native imported UCX boundaries differ')
  return {'old':results[0],'new':results[1],'equal_within_cm':.01,'probe_actors_removed':True}
 finally:
  for actor in actors:district.ACTORS.destroy_actor(actor)

def main():
 require((ROOT.parent/'quest_baseline_manifest.json').exists(),'Quest copy only')
 manifest=json.loads((SOURCE/'manifest.json').read_text());entry=manifest['assets'][0];proof=manifest['preservation']
 require(manifest['build_stamp']=='20261025T121443_839255','Only the explicitly approved foliage build may be applied')
 require(entry['triangles']<=3500 and entry['triangles']==3442,'Approved triangle budget mismatch')
 require(proof['pot_soil_triangles_uvs_materials_identical'] and proof['collision_vertices_identical'] and proof['inside_original_maximum_bounds'],'Source preservation proof failed')
 require(sha(SOURCE/entry['file'])==entry['file_sha256'],'Approved FBX hash mismatch')
 production=json.loads(district.OUT.read_text());plan=json.loads(district.PLAN.read_text())
 before_assets=all_assets();saves={str(p):sha(p) for p in (ROOT/'Saved/SaveGames').glob('*.sav')}
 records={r['path']:r for r in production['maps']}
 for path in plan['target_maps']:
  require(district.LEVEL.load_level(path),'Cannot load '+path)
  previous=json.loads(Path(records[path]['after_snapshot']).read_text());guard={'preserved_manual':[],'inferred_manual_names':list(records[path].get('inferred_manual_names',[]))}
  for id in IDS:
   actor=district.unique(id);require(actor is not None and actor.actor_has_tag(district.OWNED),'Missing owned tree '+id)
   require(district.editable(actor,previous,guard),'Manual tree must be preserved: '+id+' '+str(guard))
 old=district.load_asset(production['asset_namespace']+'/Meshes/SM_QuestDistrict_PottedTree')
 mats={name:district.load_asset(production['asset_namespace']+'/Materials/'+name) for name in entry['materials']}
 require(all(mats.values()),'Existing shared foliage materials missing')
 folder='/Game/Quest/PremiumFoliage/V_'+manifest['build_stamp']
 original_source=district.SOURCE
 try:
  district.SOURCE=SOURCE;new=district.meshes(manifest,mats,folder)[entry['name']]
 finally:district.SOURCE=original_source
 static=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
 require(static.get_convex_collision_count(old)==1 and static.get_convex_collision_count(new)==1,'Expected the same one convex collision proxy')
 require(new.get_num_triangles(0)<=3500 and new.get_num_triangles(0)>3000,'Unexpected imported foliage triangle count')
 require(len(new.get_editor_property('static_materials'))==3,'Expected three existing material slots')
 require(all(new.get_material(i)==mats[name] for i,name in enumerate(entry['materials'])),'Native material mapping changed')
 REPORT.update(asset_path=new.get_path_name(),asset_namespace=folder,source_manifest=str(SOURCE/'manifest.json'),source_preservation=proof,
  native_triangles=new.get_num_triangles(0),native_vertices=new.get_num_vertices(0),native_materials=[new.get_material(i).get_path_name() for i in range(3)],native_convex_collision_count=1)
 try:
  old_vertices=geometry_vertices(old);new_vertices=geometry_vertices(new)
 except Exception as error:
  REPORT['native_convex_vertex_introspection_unavailable']=str(error)
 else:
  require(old_vertices==new_vertices,'Native reflected convex vertices differ')
  REPORT['native_convex_vertex_comparison']={'equal':True,'hulls':old_vertices}
 REPORT['native_collision_boundaries']=collision_probe(district.EDITOR.get_editor_world(),old,new)
 for path in plan['target_maps']:
  require(district.LEVEL.load_level(path),'Cannot load '+path);world=district.EDITOR.get_editor_world()
  manager=clearance.local_manager();before=district.snapshot();story=district.referenced_story_transforms(manager)
  arrays={f:[a.get_name() for a in manager.get_editor_property(f)] for f in district.ARRAY_FIELDS};slot=str(manager.get_editor_property('SaveSlot'))
  row={'path':path,'transforms':{},'first_baseline':records[path]['baseline_snapshot'],'first_baseline_sha256':sha(Path(records[path]['baseline_snapshot']))}
  for id in IDS:
   actor=district.unique(id);comp=actor.get_component_by_class(unreal.StaticMeshComponent);old_state=district.state(actor)
   comp.set_static_mesh(new);after_state=district.state(actor)
   require(all(old_state[k]==after_state[k] for k in old_state if k not in ['mesh','materials']),'Tree transform/collision/tags changed '+id)
   require(old_state['materials']==after_state['materials'],'Tree component material references changed '+id)
   row['transforms'][id]={'location_cm':after_state['location_cm'],'rotation':after_state['rotation'],'scale':after_state['scale'],'unchanged':True}
  bench=district.unique('quest.district.domestic.bench');tree=district.unique(IDS[0])
  row['floor_support']=clearance.floor_support(world,bench,tree)
  row['tree_body_clearance']=clearance.tree_body_clear(world,bench,tree)
  row['anchor_approach_rays']=clearance.anchor_rays(world,manager.get_editor_property('AnchorActor'))
  after=district.snapshot();changed=[name for name,value in before.items() if value!=after.get(name)]
  require(set(changed)=={district.unique(id).get_name() for id in IDS},'Unexpected actor changes: '+str(changed))
  require(story==district.referenced_story_transforms(manager),'Story transforms changed')
  require(arrays=={f:[a.get_name() for a in manager.get_editor_property(f)] for f in district.ARRAY_FIELDS},'Era arrays changed')
  require(slot==str(manager.get_editor_property('SaveSlot')),'Campaign slot changed')
  after_file=FOLDER/(path.rsplit('/',1)[-1]+'_after.json');after_file.write_text(json.dumps(after,indent=2))
  require(district.LEVEL.save_current_level(),'Cannot save guarded foliage update')
  record=records[path];record['after_snapshot']=str(after_file)
  record.setdefault('guarded_art_updates',[]).append({'run':STAMP,'report':str(OUT),'ids':IDS,'mesh':new.get_path_name()})
  row.update(after_snapshot=str(after_file),changed_actor_names=changed,story_era_save_slot_unchanged=True)
  require(sha(Path(row['first_baseline']))==row['first_baseline_sha256'],'First baseline changed')
  REPORT['maps'].append(row);write()
 require(all(sha(ROOT/path)==value for path,value in before_assets.items()),'Existing shared asset file changed')
 require(saves=={str(p):sha(p) for p in (ROOT/'Saved/SaveGames').glob('*.sav')},'Save files changed')
 preferences=json.loads(district.PREFERENCES.read_text()) if district.PREFERENCES.exists() else {'schema_version':1,'meshes':{}}
 preferences['meshes']['SM_QuestDistrict_PottedTree']=new.get_path_name();preferences['foliage_source_manifest']=str(SOURCE/'manifest.json');preferences['updated_utc']=STAMP
 district.PREFERENCES.parent.mkdir(parents=True,exist_ok=True);district.PREFERENCES.write_text(json.dumps(preferences,indent=2))
 production['preferred_generated_meshes']=preferences['meshes'];district.OUT.write_text(json.dumps(production,indent=2))
 REPORT.update(success=True,shared_assets_unchanged=True,save_files_unchanged=True,durable_preferences=str(district.PREFERENCES),
  regeneration_selection_proof={'selected':district.preferred_generated_mesh('SM_QuestDistrict_PottedTree',old).get_path_name(),'approved':new.get_path_name()})

try:main()
except Exception:REPORT['error']=traceback.format_exc();unreal.log_error(REPORT['error'])
finally:write();unreal.log('QUEST_PREMIUM_FOLIAGE_APPLY '+str(REPORT['success']));unreal.SystemLibrary.quit_editor()
