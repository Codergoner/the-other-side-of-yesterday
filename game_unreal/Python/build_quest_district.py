"""Additive, reversible Verdant district build. Run only under root's native queue.

Copies the existing Brief Quarter into separate Quest desktop and XR maps, never
regenerates the city, and preserves story positions, stable IDs and manual edits.
Navigation medallions are separate from time anchors. Native route validation is
required before the authored expected-floor nodes are considered tested.
"""
from pathlib import Path
from datetime import datetime, timezone
import json, hashlib, traceback, importlib, math
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();DEV=ROOT.parent
SOURCE=DEV/'output'/'quest_district';OUT=ROOT/'quest_district_report.json'
PLAN=DEV/'quest_district_plan.json'
PREFERENCES=ROOT/'ContentData'/'quest_generated_asset_preferences.json'
OWNED='TOSOY.VRQuarterOwned';MANUAL='TOSOY.ManualOverride'
ASSETS=unreal.AssetToolsHelpers.get_asset_tools()
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVEL=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
REF_FIELDS=['PhotoActor','LetterActor','MotherActor','BenchActor','ComponentActor','DrawerActor','AnchorActor','NeriActor','HealerActor','SelaActor','WaterActor','LinenActor','LinenTrayActor','CanvasActor','ClinicInstallActor','HarborInstallActor','MemorialActor','ClinicRecordActor','HarborRecordActor','ClinicCoverActor','HarborCoverActor','NeriHarborDestinationActor','MotherHomeDestinationActor']
ARRAY_FIELDS=['PastActors','PresentActors','PastCollisionActors']
def xyz(v):return [round(v.x,4),round(v.y,4),round(v.z,4)]
def rpy(v):return [round(v.pitch,4),round(v.yaw,4),round(v.roll,4)]
def digest(file):return hashlib.sha256(file.read_bytes()).hexdigest()
def protected_hashes():
 return {str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in (ROOT/'Content').rglob('*') if p.is_file() and p.suffix in ('.uasset','.umap') and 'Quest' not in p.relative_to(ROOT/'Content').parts[:1]}
def world_actors():return list(ACTORS.get_all_level_actors())
def state(actor):
 comp=actor.get_component_by_class(unreal.StaticMeshComponent);mesh=comp.get_editor_property('static_mesh') if comp else None
 try:hidden=bool(actor.get_editor_property('hidden'))
 except Exception:hidden=None
 return {'name':actor.get_name(),'path':actor.get_path_name(),'label':actor.get_actor_label(),'class':actor.get_class().get_path_name(),'location_cm':xyz(actor.get_actor_location()),'rotation':rpy(actor.get_actor_rotation()),'scale':xyz(actor.get_actor_scale3d()),'tags':sorted(str(t) for t in actor.get_editor_property('tags')),'mesh':mesh.get_path_name() if mesh else None,'materials':[comp.get_material(i).get_path_name() if comp.get_material(i) else None for i in range(comp.get_num_materials())] if comp else [],'collision_enabled':str(comp.get_collision_enabled()) if comp else None,'collision_profile':str(comp.get_collision_profile_name()) if comp else None,'collision_responses':{str(ch):str(comp.get_collision_response_to_channel(ch)) for ch in (unreal.CollisionChannel.ECC_PAWN,unreal.CollisionChannel.ECC_VISIBILITY)} if comp else {},'hidden_in_game':hidden}
def snapshot():return {a.get_name():state(a) for a in world_actors()}
def load_asset(path):return unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
def tag_add(actor,*tags):
 values=[str(t) for t in actor.get_editor_property('tags')]
 for t in tags:
  if t and t not in values:values.append(t)
 actor.set_editor_property('tags',[unreal.Name(t) for t in values])
def editable(actor,previous,record):
 if actor.actor_has_tag(MANUAL):record['preserved_manual'].append({'actor':actor.get_path_name(),'reason':MANUAL});return False
 if actor.get_name() in record.get('inferred_manual_names',[]):record['preserved_manual'].append({'actor':actor.get_path_name(),'reason':'Previously detected manual edit remains protected'});return False
 old=previous.get(actor.get_name())
 if old and state(actor)!=old:
  record.setdefault('inferred_manual_names',[]).append(actor.get_name());record['preserved_manual'].append({'actor':actor.get_path_name(),'reason':'Actor differs from last generated after-snapshot'});return False
 return True
def unique(stable_id):
 matches=[a for a in world_actors() if a.actor_has_tag(stable_id)]
 if len(matches)>1:raise RuntimeError('Duplicate stable art identifier '+stable_id)
 return matches[0] if matches else None

def texture(file,folder,mask=False):
 path=folder+'/'+file.stem;existing=load_asset(path)
 if existing:return existing
 task=unreal.AssetImportTask();task.set_editor_property('filename',str(file));task.set_editor_property('destination_path',folder);task.set_editor_property('destination_name',file.stem);task.set_editor_property('automated',True);task.set_editor_property('replace_existing',False);task.set_editor_property('save',True);ASSETS.import_asset_tasks([task])
 value=load_asset(path)
 if value is None:raise RuntimeError('Texture import failed '+str(file))
 value.set_editor_property('srgb',not mask)
 if mask:value.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_MASKS)
 unreal.EditorAssetLibrary.save_loaded_asset(value);return value

def materials(manifest,folder):
 result={}
 for name,definition in manifest['material_definitions'].items():
  path=folder+'/Materials/'+name;existing=load_asset(path)
  if existing:result[name]=existing;continue
  mat=ASSETS.create_asset(name,folder+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
  if not mat:raise RuntimeError('Cannot create new kit material '+path)
  mat.set_editor_property('two_sided',bool(definition.get('two_sided') or definition.get('pattern')=='cloth'))
  for field,prop,y in [('basecolor',unreal.MaterialProperty.MP_BASE_COLOR,-220),('roughness',unreal.MaterialProperty.MP_ROUGHNESS,40)]:
   file=definition.get(field)
   if isinstance(file,str):
    tex=texture(SOURCE/file,folder+'/Textures',mask=field=='roughness');node=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionTextureSample,-400,y);node.set_editor_property('texture',tex)
    if field=='roughness':node.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    unreal.MaterialEditingLibrary.connect_material_property(node,'R' if field=='roughness' else 'RGB',prop)
   elif field=='basecolor':
    node=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector,-400,y);node.set_editor_property('constant',unreal.LinearColor(*(c/255 for c in definition['rgb']),1));unreal.MaterialEditingLibrary.connect_material_property(node,'',prop)
   else:
    node=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant,-400,y);node.set_editor_property('r',float(definition['roughness']));unreal.MaterialEditingLibrary.connect_material_property(node,'',prop)
  metal=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant,-400,220);metal.set_editor_property('r',float(definition.get('metallic',0)));unreal.MaterialEditingLibrary.connect_material_property(metal,'',unreal.MaterialProperty.MP_METALLIC)
  unreal.MaterialEditingLibrary.recompile_material(mat);unreal.EditorAssetLibrary.save_loaded_asset(mat);result[name]=mat
 return result

def meshes(manifest,mats,folder):
 result={}
 for entry in manifest['assets']:
  name=entry['name'];path=folder+'/Meshes/'+name;existing=load_asset(path)
  if existing:result[name]=existing;continue
  options=unreal.FbxImportUI();options.set_editor_property('import_mesh',True);options.set_editor_property('import_as_skeletal',False);options.set_editor_property('import_materials',False);options.set_editor_property('import_textures',False);options.set_editor_property('automated_import_should_detect_type',False);options.set_editor_property('mesh_type_to_import',unreal.FBXImportType.FBXIT_STATIC_MESH)
  data=options.get_editor_property('static_mesh_import_data')
  for key,value in [('combine_meshes',True),('transform_vertex_to_absolute',True),('convert_scene',True),('force_front_x_axis',False),('convert_scene_unit',True),('auto_generate_collision',False),('one_convex_hull_per_ucx',True),('generate_lightmap_u_vs',True),('build_nanite',False),('remove_degenerates',True)]:data.set_editor_property(key,value)
  data.set_editor_property('normal_import_method',unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
  task=unreal.AssetImportTask();task.set_editor_property('filename',str(SOURCE/entry['file']));task.set_editor_property('destination_path',folder+'/Meshes');task.set_editor_property('destination_name',name);task.set_editor_property('automated',True);task.set_editor_property('replace_existing',False);task.set_editor_property('save',True);task.set_editor_property('factory',unreal.FbxFactory());task.set_editor_property('options',options);ASSETS.import_asset_tasks([task])
  value=load_asset(path)
  if not isinstance(value,unreal.StaticMesh):raise RuntimeError('Expected one semantic static mesh '+path)
  for i,slot in enumerate(value.get_editor_property('static_materials')):
   key=str(slot.get_editor_property('material_slot_name'));material=mats.get(key) or next((m for k,m in mats.items() if key.startswith(k)),None)
   if not material:raise RuntimeError('Unmatched new kit material '+name+'/'+key)
   value.set_material(i,material)
  unreal.EditorAssetLibrary.save_loaded_asset(value);result[name]=value
 return result

def ensure_refs_in_clone(manager,map_path):
 actors={a.get_name():a for a in world_actors()};rebound=[]
 for field in REF_FIELDS:
  try:old=manager.get_editor_property(field)
  except Exception:continue
  if not old:continue
  target=actors.get(old.get_name())
  if not target:raise RuntimeError('Map clone lost preserved story reference '+field)
  if target!=old:manager.set_editor_property(field,target);rebound.append(field)
  if not target.get_path_name().startswith(map_path+'.'):raise RuntimeError('Story reference points outside Quest map '+field)
 for field in ARRAY_FIELDS:
  old=list(manager.get_editor_property(field));fixed=[actors[a.get_name()] for a in old if a and a.get_name() in actors]
  if len(fixed)!=len(old):raise RuntimeError('Map clone lost era array actor '+field)
  manager.set_editor_property(field,fixed)
 return rebound

def apply_prop(spec,kit,entries,previous,record):
 actor=unique(spec['id'])
 if actor:
  if not actor.actor_has_tag(OWNED):record['preserved_manual'].append({'actor':actor.get_path_name(),'reason':'Stable district ID belongs to an unowned actor'});return actor
  if not editable(actor,previous,record):return actor
 else:actor=ACTORS.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(0,0,0),unreal.Rotator(pitch=0,yaw=0,roll=0))
 actor.set_actor_label('Quest quarter — '+spec['id'].removeprefix('quest.district.').removeprefix('quest.nav.').replace('.',' / '))
 actor.set_folder_path('Quest Quarter/Teleport Landings' if spec.get('navigation') else 'Quest Quarter/Street Rooms')
 actor.set_actor_location(unreal.Vector(*spec['position_cm']),False,False)
 actor.set_actor_rotation(unreal.Rotator(pitch=0,yaw=spec.get('yaw',-90),roll=0),False)
 scale=spec.get('scale',1);actor.set_actor_scale3d(unreal.Vector(scale,scale,scale))
 comp=actor.get_component_by_class(unreal.StaticMeshComponent)
 comp.set_mobility(unreal.ComponentMobility.STATIC);comp.set_static_mesh(preferred_generated_mesh(spec['mesh'],kit[spec['mesh']]));comp.set_simulate_physics(False)
 blocking=entries[spec['mesh']]['collision_count']>0
 if blocking:comp.set_collision_profile_name('BlockAll');comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
 else:comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
 era=spec.get('era');tag_add(actor,OWNED,spec['id'],'Opening.'+era+'Only' if era else None,'Opening.Blocking' if blocking else 'Opening.Decorative')
 if spec.get('navigation'):
  tag_add(actor,'Quest.Teleport','Quest.NavigationNode','Quest.District.'+spec['district'])
  # Medallions carry a simple thin convex shape. They are pointer targets, not
  # extra physical steps: Visibility blocks while the moving Pawn ignores them.
  comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
  comp.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
  comp.set_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY,unreal.CollisionResponseType.ECR_BLOCK)
  comp.set_editor_property('cast_shadow',False)
  actor.set_actor_label('Quest landing — '+spec['id'].removeprefix('quest.nav.')+' (expected floor, validate)')
 actor.set_actor_hidden_in_game(era=='Past');actor.set_actor_enable_collision((blocking or spec.get('navigation',False)) and era!='Past')
 record['added_or_updated'].append(spec['id']);return actor

def preferred_generated_mesh(role,fallback):
 """Select approved generated art before assignment; do not reset then reapply.

The durable preference is committed only after a guarded art update succeeds.
Missing approved assets fail visibly instead of silently reverting their art.
"""
 if not PREFERENCES.exists():return fallback
 data=json.loads(PREFERENCES.read_text(encoding='utf-8'));path=data.get('meshes',{}).get(role)
 if not path:return fallback
 value=load_asset(path)
 if not isinstance(value,unreal.StaticMesh):raise RuntimeError('Approved generated mesh is unavailable: '+str(path))
 return value

def navigation_specs(plan):
 # Steep lower-harbor flights are deliberately not advertised as tested teleport
 # routes. Their >650cm landing gaps need a separate authored solution and QA.
 flat={'home_inside','home_workshop','home_porch','market_arcade','upper_overlook'}
 for node in plan['navigation_nodes']:
  if node['tier']=='optional_lower_harbor':continue
  yield {'id':'quest.nav.'+node['id'],'mesh':'SM_QuestDistrict_Landing'+('Flat' if node['id'] in flat else 'Street'),'position_cm':node['floor_cm'],'yaw':-90,'navigation':True,'district':node['district'],'era':node.get('era')}

def add_cameras(plan,previous,record):
 for view in plan['review_cameras']:
  actor=unique(view['id'])
  if actor and (not actor.actor_has_tag(OWNED) or not editable(actor,previous,record)):continue
  if not actor:actor=ACTORS.spawn_actor_from_class(unreal.CameraActor,unreal.Vector(0,0,0),unreal.Rotator(pitch=0,yaw=0,roll=0))
  actor.set_actor_label('Quest review only — '+view['id'].removeprefix('quest.review.'));actor.set_folder_path('Quest Quarter/Review Cameras')
  tag_add(actor,OWNED,view['id'],'Quest.ReviewCameraOnly')
  p=unreal.Vector(*view['position_cm']);target=unreal.Vector(*view['target_cm'])
  actor.set_actor_location(p,False,False);actor.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(p,target),False)
  actor.get_component_by_class(unreal.CameraComponent).set_field_of_view(view['fov']);actor.set_actor_enable_collision(False)

def register_era_props(manager):
 for field,tag in [('PastActors','Opening.PastOnly'),('PresentActors','Opening.PresentOnly'),('PastCollisionActors','Opening.PastOnly')]:
  values=list(manager.get_editor_property(field))
  for actor in world_actors():
   if not actor.actor_has_tag(OWNED) or not actor.actor_has_tag(tag):continue
   if field=='PastCollisionActors' and not actor.actor_has_tag('Opening.Blocking'):continue
   if actor not in values:values.append(actor)
  manager.set_editor_property(field,values)

def referenced_story_transforms(manager):
 result={}
 for field in REF_FIELDS:
  try:actor=manager.get_editor_property(field)
  except Exception:continue
  if actor:result[field]={'name':actor.get_name(),'location_cm':xyz(actor.get_actor_location()),'rotation':rpy(actor.get_actor_rotation()),'scale':xyz(actor.get_actor_scale3d())}
 return result

def validate_anchor_reservation(plan,manifest):
 """Reject new colliding furniture inside the existing anchor interaction apron."""
 reserve=plan['preserved_story'].get('anchor_interaction_reservation')
 if not reserve:return []
 center=reserve['center_xy_cm'];minimum=reserve['new_collision_footprint_min_distance_cm']
 entries={a['name']:a for a in manifest['assets']};rows=[]
 for spec in plan['props']:
  entry=entries['SM_QuestDistrict_'+spec['mesh']]
  if not entry['collision_count']:continue
  bounds=entry['bounds_m'];angle=math.radians(spec.get('yaw',-90));c,s=math.cos(angle),math.sin(angle);points=[]
  for x in (bounds['min'][0],bounds['max'][0]):
   for y in (bounds['min'][1],bounds['max'][1]):
    # FBX converts Blender Y to -Y before the native actor yaw.
    scale=spec.get('scale',1)
    points.append((spec['position_cm'][0]+100*scale*(x*c+y*s),spec['position_cm'][1]+100*scale*(x*s-y*c)))
  lo=[min(p[i] for p in points) for i in (0,1)];hi=[max(p[i] for p in points) for i in (0,1)]
  nearest=[max(lo[i],min(center[i],hi[i])) for i in (0,1)];distance=math.dist(nearest,center)
  rows.append({'id':spec['id'],'visual_bounds_distance_cm':round(distance,3),'minimum_cm':minimum})
  if distance<minimum:raise RuntimeError('New furniture intrudes on time-anchor interaction apron: '+spec['id']+' distance='+str(distance))
 return rows

def describe_hit(hit):
 if hit is None:return {'blocking':False}
 values=hit.to_tuple() if hasattr(hit,'to_tuple') else unreal.GameplayStatics.break_hit_result(hit)
 actor=values[9]
 return {'blocking':bool(values[0]),'initial_overlap':bool(values[1]),'point_cm':xyz(values[5]),'normal':xyz(values[7]),'actor':actor.get_name() if actor else None}

def validate_navigation(world,plan,record):
 """Editor floor/capsule evidence; not a substitute for native play or HMD QA."""
 nodes=[n for n in plan['navigation_nodes'] if n['tier']!='optional_lower_harbor']
 discs=[a for a in world_actors() if a.actor_has_tag('Quest.NavigationNode')]
 rows=[];valid=[]
 for node in nodes:
  actor=unique('quest.nav.'+node['id']);p=node['floor_cm'];row={'id':node['id'],'expected_floor_cm':p,'radius_cm':node['radius_cm']}
  floor=describe_hit(unreal.SystemLibrary.line_trace_single(world,unreal.Vector(p[0],p[1],p[2]+45),unreal.Vector(p[0],p[1],p[2]-80),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,discs,unreal.DrawDebugTrace.NONE,True))
  row['floor_trace']=floor;row['supported']=bool(floor['blocking'] and abs(floor['point_cm'][2]-p[2])<=12)
  if floor['blocking']:
   row['floor_error_cm']=round(abs(floor['point_cm'][2]-p[2]),3)
   row['slope_degrees']=round(math.degrees(math.acos(max(-1,min(1,floor['normal'][2])))),3)
  # XR Character uses 34cm radius / 88cm half height; 5cm toe clearance
  # separates an obstruction test from the intended support surface.
  center=unreal.Vector(p[0],p[1],p[2]+93)
  overlap=describe_hit(unreal.SystemLibrary.capsule_trace_single(world,center,center+unreal.Vector(0,0,.1),34.0,88.0,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,discs,unreal.DrawDebugTrace.NONE,True))
  row['capsule_clear']=not overlap['blocking'];row['capsule_obstruction']=overlap if overlap['blocking'] else None
  row['candidate_pass']=row['supported'] and row['capsule_clear']
  if row['candidate_pass']:valid.append(node['id'])
  elif actor and actor.actor_has_tag(OWNED) and not actor.actor_has_tag(MANUAL):
   actor.set_editor_property('tags',[t for t in actor.get_editor_property('tags') if str(t)!='Quest.Teleport'])
   tag_add(actor,'Quest.NavigationUnverified');row['unsafe_teleport_tag_removed']=True
  rows.append(row)
 points={n['id']:n['floor_cm'] for n in nodes};edges=[];graph={key:[] for key in valid}
 for a,b in plan['planned_edges']:
  if a not in points or b not in points:continue
  distance=math.dist(points[a],points[b]);within=distance<=600 # leave head-to-floor ray margin inside 650cm
  item={'from':a,'to':b,'floor_distance_cm':round(distance,3),'range650_with_headroom_margin':within}
  if a in graph and b in graph and within:graph[a].append(b);graph[b].append(a)
  edges.append(item)
 seen=set();pending=['home_inside'] if 'home_inside' in graph else []
 while pending:
  key=pending.pop()
  if key in seen:continue
  seen.add(key);pending.extend(graph[key])
 record['navigation_validation']={'method':'Editor Visibility floor traces and 34x88cm capsule overlap checks; no physical VR traversal claim','nodes':rows,'edges':edges,'reachable_from_home':sorted(seen),'core_unreachable':[n['id'] for n in nodes if n['tier']=='core' and n['id'] not in seen],'all_spawned_supported_and_capsule_clear':all(r['candidate_pass'] for r in rows),'line_of_sight_and_headset_test_pending':True}
 record['stable_id_unique']=all(len([a for a in world_actors() if a.actor_has_tag(s['id'])])==1 for s in list(plan['props'])+list(navigation_specs(plan))+list(plan['review_cameras']))

def build_district():
 if not (DEV/'quest_baseline_manifest.json').exists():raise RuntimeError('Restricted to protected Quest development copy')
 plan=json.loads(PLAN.read_text(encoding='utf-8'));manifest=json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8'))
 anchor_reservation=validate_anchor_reservation(plan,manifest)
 if manifest['triangles']>20000:raise RuntimeError('Unique district geometry exceeds approved budget')
 previous_report=json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
 folder='/Game/Quest/DistrictKit/V_'+manifest['build_stamp'];protected_before=protected_hashes()
 run=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f');snapdir=ROOT/'validation'/'quest_district'/run;snapdir.mkdir(parents=True,exist_ok=True)
 report={'success':False,'scope':plan['scope'],'plan':str(PLAN),'kit_manifest':str(SOURCE/'manifest.json'),'asset_namespace':folder,'unique_triangles':manifest['triangles'],'maps':list(previous_report.get('maps',[])),'anchor_reservation':anchor_reservation,'protected_content_sha_before':protected_before,'navigation_candidates_not_spawned':[n for n in plan['navigation_nodes'] if n['tier']=='optional_lower_harbor'],'notes':['Source coordinates are expected floors, not proof of capsule clearance or headset comfort.','No new physical urban loop is claimed; existing story positions and landmarks are retained.','Quest desktop and XR renderer configuration is owned by the separate XR workstream.']}
 try:
  mats=materials(manifest,folder);kit=meshes(manifest,mats,folder);entries={e['name']:e for e in manifest['assets']}
  scenery=importlib.import_module('quest_scenery')
  for target in plan['target_maps']:
   if not target.startswith('/Game/Quest/Maps/'):raise RuntimeError('Unsafe target map namespace')
   existed=unreal.EditorAssetLibrary.does_asset_exist(target)
   if not existed:
    if not LEVEL.load_level(plan['source_map']):raise RuntimeError('Cannot load source Quarter')
    if not unreal.EditorLoadingAndSavingUtils.save_map(EDITOR.get_editor_world(),target):raise RuntimeError('Cannot clone Quarter into '+target)
   # SaveAs alone can leave stale in-memory world references. Explicit load is mandatory.
   if not LEVEL.load_level(target):raise RuntimeError('Cannot explicitly load Quest map '+target)
   world=EDITOR.get_editor_world();managers=[a for a in world_actors() if a.actor_has_tag('Opening.Manager')]
   if len(managers)!=1:raise RuntimeError('Expected one preserved Opening.Manager')
   manager=managers[0]
   if manager.actor_has_tag(MANUAL):raise RuntimeError('ManualOverride manager prevents safe era-array registration')
   old_record=next((r for r in previous_report.get('maps',[]) if r.get('path')==target),{});prior={}
   if old_record.get('after_snapshot') and Path(old_record['after_snapshot']).exists():prior=json.loads(Path(old_record['after_snapshot']).read_text(encoding='utf-8'))
   record={'path':target,'source_map':plan['source_map'],'created_copy':not existed,'preserved_manual':[],'inferred_manual_names':list(old_record.get('inferred_manual_names',[])),'added_or_updated':[],'manager_refs_rebound':ensure_refs_in_clone(manager,target)}
   name=target.rsplit('/',1)[-1];before=snapshot();before_file=snapdir/(name+'_before.json');before_file.write_text(json.dumps(before,indent=2),encoding='utf-8')
   record['before_snapshot']=str(before_file);record['baseline_snapshot']=old_record.get('baseline_snapshot') or old_record.get('before_snapshot') or str(before_file)
   story_before=referenced_story_transforms(manager);record['story_before']=story_before
   record['era_arrays_before']={f:[a.get_name() for a in manager.get_editor_property(f)] for f in ARRAY_FIELDS}
   manager.set_editor_property('SaveSlot','Yesterday_Quest_20261025');record['isolated_campaign_save_slot']='Yesterday_Quest_20261025'
   for spec in plan['props']:
    spec=dict(spec);spec['mesh']='SM_QuestDistrict_'+spec['mesh'];apply_prop(spec,kit,entries,prior,record)
   for spec in navigation_specs(plan):apply_prop(spec,kit,entries,prior,record)
   add_cameras(plan,prior,record);register_era_props(manager)
   settings=world.get_world_settings()
   original_mode=settings.get_editor_property('default_game_mode')
   record['inherited_game_mode']=original_mode.get_path_name() if original_mode else None
   if target.endswith('_VR'):
    path='/Game/Quest/XR/BP_QuestGameMode'
    if unreal.EditorAssetLibrary.does_asset_exist(path):
     cls=unreal.load_class(None,path+'.BP_QuestGameMode_C')
     if not cls:raise RuntimeError('Quest GameMode asset exists but generated class is unavailable')
     settings.set_editor_property('default_game_mode',cls);record['xr_game_mode']=cls.get_path_name()
    else:record['xr_game_mode_pending']='Quest GameMode asset has not been authored yet'
   record['scenery']=scenery.apply_scenery(world,lighting_profile=scenery.DEFAULT_PROFILE)
   validate_navigation(world,plan,record)
   story_after=referenced_story_transforms(manager);record['story_transforms_unchanged']=story_before==story_after
   if story_before!=story_after:raise RuntimeError('District/scenery changed a reserved story transform')
   # Recheck all story references after era registration/scenery, before map save.
   ensure_refs_in_clone(manager,target)
   record['era_arrays_after']={f:[a.get_name() for a in manager.get_editor_property(f)] for f in ARRAY_FIELDS}
   if not LEVEL.save_current_level():raise RuntimeError('Cannot save Quest map '+target)
   after_file=snapdir/(name+'_after.json');after_file.write_text(json.dumps(snapshot(),indent=2),encoding='utf-8')
   record['after_snapshot']=str(after_file);report['maps']=[r for r in report['maps'] if r.get('path')!=target]+[record]
  unreal.EditorAssetLibrary.save_directory(folder,only_if_is_dirty=True,recursive=True)
  after=protected_hashes();changed=[p for p,h in protected_before.items() if after.get(p)!=h]
  report['protected_source_content_unchanged']=not changed;report['unexpected_protected_changes']=changed
  if changed:raise RuntimeError('Protected source content changed unexpectedly: '+str(changed))
  report['success']=True
 except Exception:report['error']=traceback.format_exc();raise
 finally:OUT.write_text(json.dumps(report,indent=2),encoding='utf-8')
 return report

def revert_district(map_path):
 """Remove only unchanged owned district additions; scenery has its own ownership."""
 if not map_path.startswith('/Game/Quest/Maps/'):raise RuntimeError('Only Quest maps may be reverted')
 report=json.loads(OUT.read_text(encoding='utf-8'));old=next(r for r in report['maps'] if r['path']==map_path)
 if not LEVEL.load_level(map_path):raise RuntimeError('Cannot load Quest map')
 after=json.loads(Path(old['after_snapshot']).read_text(encoding='utf-8'))
 result={'preserved_manual':[],'inferred_manual_names':list(old.get('inferred_manual_names',[])),'removed':[]}
 removable=[a for a in world_actors() if a.actor_has_tag(OWNED) and editable(a,after,result)]
 for manager in [a for a in world_actors() if a.actor_has_tag('Opening.Manager')]:
  if manager.actor_has_tag(MANUAL):continue
  for field in ARRAY_FIELDS:manager.set_editor_property(field,[a for a in manager.get_editor_property(field) if a not in removable])
 for actor in removable:result['removed'].append(actor.get_name());ACTORS.destroy_actor(actor)
 LEVEL.save_current_level();return result

if __name__=='__main__':print(json.dumps(build_district(),indent=2))

