"""Native editor acceptance for reversible art authoring, isolated from Quarter.

Creates one uniquely named test map from the current development Home map.
This validates assets/actor guards/reversal, not gameplay, art quality or timing.
Root coordinates the sole Unreal writer; this file does not launch another editor.
"""
from pathlib import Path
from datetime import datetime, timezone
import json, sys, traceback, hashlib
import unreal

ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import build_brief_art as art
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
OUTPUT=ROOT/'validation'/'brief_art_guards'/STAMP;OUTPUT.mkdir(parents=True,exist_ok=True)
REPORT_PATH=ROOT/'brief_art_validation.json'
TEST_MAP='/Game/BriefTest/Tests/ArtGuard_'+STAMP
REPORT={'success':False,'scope':'Native imported-asset, idempotence, manual-edit and reversible-material checks only','engine':unreal.SystemLibrary.get_engine_version(),'test_map':TEST_MAP,'run':STAMP,'checks':[],'gameplay_tested':False,'quarter_maps_modified':False,'art_quality_tested':False}

def check(name,value,evidence=None):
 row={'name':name,'passed':bool(value)}
 if evidence is not None:row['evidence']=evidence
 REPORT['checks'].append(row)
 if not value:raise AssertionError(name+': '+str(evidence))
def file_hashes(folder,pattern):return {str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob(pattern)}
def actors():return list(art.ACTORS.get_all_level_actors())
def owned():return [a for a in actors() if a.actor_has_tag(art.OWNED)]
def stable_counts():
 counts={}
 for a in actors():
  for t in a.get_editor_property('tags'):
   name=str(t)
   if name.startswith('brief.art.'):counts[name]=counts.get(name,0)+1
 return counts
def no_duplicates():return bool(stable_counts()) and all(v==1 for v in stable_counts().values())
def arrays_valid():
 manager=next(a for a in actors() if a.actor_has_tag('Opening.Manager'))
 return {field:[a.get_name() for a in manager.get_editor_property(field)] for field in art.ARRAY_FIELDS}
def validate_arrays(label):
 arrays=arrays_valid();check(label+' era arrays contain no duplicate actor references',all(len(v)==len(set(v)) for v in arrays.values()),{k:len(v) for k,v in arrays.items()})
 manager=next(a for a in actors() if a.actor_has_tag('Opening.Manager'))
 check(label+' era references resolve inside the isolated test map',all(a and a.get_path_name().startswith(TEST_MAP+'.') for f in art.ARRAY_FIELDS for a in manager.get_editor_property(f)))
 return arrays

def validate_meshes(report):
 manifest=json.loads((art.SOURCE/'manifest.json').read_text(encoding='utf-8'));static=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem);namespace=report['asset_namespace'];rows=[]
 if static is None:raise RuntimeError('StaticMeshEditorSubsystem requires the initialized full editor; run this validator with -ExecutePythonScript, not the Python commandlet')
 for entry in manifest['assets']:
  mesh=unreal.load_asset(namespace+'/Meshes/'+entry['name']);check('Imported semantic mesh exists: '+entry['name'],isinstance(mesh,unreal.StaticMesh))
  bounds=mesh.get_bounds();actual_min=art.xyz(bounds.origin-bounds.box_extent);actual_max=art.xyz(bounds.origin+bounds.box_extent);mn=entry['bounds_m']['min'];mx=entry['bounds_m']['max'];expected_min=[mn[0]*100,-mx[1]*100,mn[2]*100];expected_max=[mx[0]*100,-mn[1]*100,mx[2]*100]
  delta=max(abs(a-b) for a,b in zip(actual_min+actual_max,expected_min+expected_max));check('Metric X,-Y,Z bounds and scale: '+entry['name'],delta<=.35,{'actual_min_cm':actual_min,'actual_max_cm':actual_max,'expected_min_cm':expected_min,'expected_max_cm':expected_max,'max_error_cm':delta})
  slots=[str(s.get_editor_property('material_slot_name')) for s in mesh.get_editor_property('static_materials')];assigned=[mesh.get_material(i) for i in range(len(slots))]
  check('Material slots remain assigned in the new namespace: '+entry['name'],bool(slots) and all(m and m.get_path_name().startswith(namespace+'/Materials/') for m in assigned),{'slots':slots,'assigned':[m.get_path_name() if m else None for m in assigned]})
  check('Source material set survived export/import: '+entry['name'],all(any(slot.startswith(name) for slot in slots) for name in entry['materials']))
  simple=static.get_simple_collision_count(mesh);convex=static.get_convex_collision_count(mesh);total=simple+convex;expected=entry['collision_count']
  check('Explicit collision policy survived import: '+entry['name'],total>=expected if expected else total==0,{'expected':expected,'simple':simple,'convex':convex})
  check('Imported mesh has render vertices: '+entry['name'],static.get_number_verts(mesh,0)>0)
  rows.append({'name':entry['name'],'path':mesh.get_path_name(),'bounds_error_cm':delta,'source_triangles':entry['triangles'],'simple_collisions':simple,'convex_collisions':convex,'material_slots':slots})
 REPORT['imported_meshes']=rows

def main():
 old_maps,old_out=art.MAPS,art.OUT
 protected_before=art.protected_hashes();quarter_before=file_hashes(ROOT/'Content'/'BriefTest'/'Maps','*.umap');duplicate=None
 try:
  check('Validation is restricted to the protected development copy',(ROOT.parent/'baseline_manifest.json').exists())
  check('Isolated test map name is new',not unreal.EditorAssetLibrary.does_asset_exist(TEST_MAP))
  art.MAPS=[('/Game/Home/Maps/House_ThirdPerson',TEST_MAP)];art.OUT=OUTPUT/'art_guard_build_report.json'
  first=art.build_art();check('First isolated art build succeeds',first['success'] and first['protected_source_content_unchanged']);validate_meshes(first)
  first_record=first['maps'][0];baseline=Path(first_record.get('baseline_snapshot') or first_record['before_snapshot']);baseline_digest=hashlib.sha256(baseline.read_bytes()).hexdigest();baseline_state=json.loads(baseline.read_text(encoding='utf-8'));count1=len(owned())
  check('All generated props and cameras have unique stable IDs',no_duplicates(),stable_counts());check('Kit is batched into prop/camera actors',count1==len(art.placements())+len(art.CAMERAS),{'owned':count1,'props':len(art.placements()),'cameras':len(art.CAMERAS)})
  validate_arrays('First build')
  # Real duplicate identity is rejected before any production-map mutation.
  duplicate=art.ACTORS.spawn_actor_from_class(unreal.TargetPoint,unreal.Vector(0,0,0),unreal.Rotator(pitch=0,yaw=0,roll=0));duplicate.set_editor_property('tags',[unreal.Name('brief.art.home.chair_repaired')]);rejected=False
  try:art.unique('brief.art.home.chair_repaired')
  except RuntimeError:rejected=True
  check('Duplicate stable-ID lookup stops rather than picking an actor',rejected);art.ACTORS.destroy_actor(duplicate);duplicate=None
  tagged=art.unique('brief.art.home.chair_repaired');untagged=art.unique('brief.art.home.chair_empty');check('Both manual guard specimens exist',tagged is not None and untagged is not None)
  art.tag_add(tagged,art.MANUAL);tagged.set_actor_location(tagged.get_actor_location()+unreal.Vector(17,0,0),False,False);untagged.set_actor_location(untagged.get_actor_location()+unreal.Vector(-23,11,0),False,False)
  tagged_expected=art.state(tagged);untagged_expected=art.state(untagged);names={tagged.get_name(),untagged.get_name()};check('Manual guard seed has only one explicitly tagged actor',tagged.actor_has_tag(art.MANUAL) and not untagged.actor_has_tag(art.MANUAL))
  check('Manual guard seed test map saves',art.LEVEL.save_current_level())
  for iteration in [2,3]:
   report=art.build_art();record=report['maps'][0]
   tagged=art.unique('brief.art.home.chair_repaired');untagged=art.unique('brief.art.home.chair_empty')
   check(f'Rerun {iteration} preserves tagged manual transform and tags',art.state(tagged)==tagged_expected)
   check(f'Rerun {iteration} preserves untagged detected manual transform',art.state(untagged)==untagged_expected)
   check(f'Rerun {iteration} retains explicit inferred-manual protection',untagged.get_name() in record.get('inferred_manual_names',[]))
   check(f'Rerun {iteration} spawns no duplicate prop/camera actor',len(owned())==count1 and no_duplicates(),{'owned':len(owned()),'before':count1})
   check(f'Rerun {iteration} keeps the first material baseline',record.get('baseline_snapshot')==str(baseline) and hashlib.sha256(baseline.read_bytes()).hexdigest()==baseline_digest)
   validate_arrays(f'Rerun {iteration}')
  restored=art.revert_art(TEST_MAP);REPORT['revert_result']=restored;remaining=owned()
  check('Revert retains exactly the two manual edited owned actors',{a.get_name() for a in remaining}==names,{'remaining':[a.get_name() for a in remaining],'expected':sorted(names)})
  check('Revert preserves both manual transforms',art.state(art.unique('brief.art.home.chair_repaired'))==tagged_expected and art.state(art.unique('brief.art.home.chair_empty'))==untagged_expected)
  current={a.get_name():a for a in actors()};overrides=first_record['component_material_overrides'];check('Test exercised real component wood overrides',len(overrides)>0)
  for change in overrides:
   name=change['actor'].rsplit('.',1)[-1];actor=current.get(name);expected=baseline_state[name]['materials'][change['slot']];comp=actor.get_component_by_class(unreal.StaticMeshComponent) if actor else None;actual=comp.get_material(change['slot']).get_path_name() if comp and comp.get_material(change['slot']) else None
   check('Revert restores first baseline component material: '+name,actual==expected,{'expected':expected,'actual':actual})
  after_arrays=validate_arrays('Revert');existing_names=set(current)
  check('Reverted era arrays contain no removed art actor',all(n in existing_names for values in after_arrays.values() for n in values))
  check('Unmodified generated props and review cameras are removed',not any(a.actor_has_tag(view['id']) for a in actors() for view in art.CAMERAS))
  check('Protected Home/Harbor/Opening/player content is byte-identical',art.protected_hashes()==protected_before)
  quarter_after=file_hashes(ROOT/'Content'/'BriefTest'/'Maps','*.umap');check('Production Quarter maps remain byte-identical',quarter_after==quarter_before);REPORT['quarter_maps_modified']=quarter_after!=quarter_before
  REPORT['baseline_snapshot']=str(baseline);REPORT['isolated_build_report']=str(art.OUT);REPORT['success']=all(r['passed'] for r in REPORT['checks'])
 except Exception:REPORT['error']=traceback.format_exc();raise
 finally:
  if duplicate:
   try:art.ACTORS.destroy_actor(duplicate)
   except Exception:pass
  art.MAPS,art.OUT=old_maps,old_out
  REPORT_PATH.write_text(json.dumps(REPORT,indent=2),encoding='utf-8');(OUTPUT/'validation_report.json').write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
 return REPORT

if __name__=='__main__':
 try:print(json.dumps(main(),indent=2))
 finally:unreal.SystemLibrary.quit_editor()
