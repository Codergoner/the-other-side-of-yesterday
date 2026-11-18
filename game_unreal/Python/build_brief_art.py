"""Add the M1 frontage/domestic kit only to reversible BriefTest map copies.

Run build_art() after the development copy's existing Home story build. Never
regenerates the city/house, replaces a character, or changes the renderer.
TOSOY.ManualOverride actors and externally changed generated actors are preserved.
"""
from pathlib import Path
from datetime import datetime, timezone
import json, hashlib, traceback
import unreal

ROOT=Path(unreal.Paths.project_dir()).resolve();DEV=ROOT.parent
SOURCE=DEV/'output'/'brief_kit';OUT=ROOT/'brief_art_report.json'
OWNED='TOSOY.BriefArtOwned';MANUAL='TOSOY.ManualOverride'
ASSETS=unreal.AssetToolsHelpers.get_asset_tools()
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVEL=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
MAPS=[('/Game/Home/Maps/House_FirstPerson','/Game/BriefTest/Maps/Quarter_FirstPerson'),('/Game/Home/Maps/House_ThirdPerson','/Game/BriefTest/Maps/Quarter_ThirdPerson')]
REF_FIELDS=['PhotoActor','LetterActor','MotherActor','BenchActor','ComponentActor','DrawerActor','AnchorActor','NeriActor','HealerActor','SelaActor','WaterActor','LinenActor','LinenTrayActor','CanvasActor','ClinicInstallActor','HarborInstallActor','MemorialActor','ClinicRecordActor','HarborRecordActor','ClinicCoverActor','HarborCoverActor','NeriHarborDestinationActor','MotherHomeDestinationActor']
ARRAY_FIELDS=['PastActors','PresentActors','PastCollisionActors']
CAMERAS=[
 {'id':'brief.art.camera.home','label':'Brief eye-level — home frontage','position_cm':[100,1800,1005],'target_cm':[-650,1300,1370],'fov':78,'floor_cm':840,'eye_height_cm':165},
 {'id':'brief.art.camera.street','label':'Brief eye-level — uphill street','position_cm':[80,800,1105],'target_cm':[-100,-2300,1600],'fov':70,'floor_cm':940,'eye_height_cm':165},
 {'id':'brief.art.camera.room','label':'Brief eye-level — surviving room','position_cm':[-560,1240,1176],'target_cm':[-965,1460,1180],'fov':78,'floor_cm':1011,'eye_height_cm':165},
 {'id':'brief.art.camera.clinic','label':'Brief eye-level — clinic approach','position_cm':[40,220,1163],'target_cm':[-350,550,1100],'fov':70,'floor_cm':998,'eye_height_cm':165},
]

def xyz(v):return [round(v.x,4),round(v.y,4),round(v.z,4)]
def rpy(v):return [round(v.pitch,4),round(v.yaw,4),round(v.roll,4)]
def digest(file):return hashlib.sha256(file.read_bytes()).hexdigest()
def protected_hashes():
 return {str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for directory in ['Home','Harbor','Opening','FirstPerson','ThirdPerson'] for p in (ROOT/'Content'/directory).rglob('*.uasset')} | {str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in (ROOT/'Content'/'Home'/'Maps').glob('*.umap')}
def world_actors():return list(ACTORS.get_all_level_actors())
def state(actor):
 comp=actor.get_component_by_class(unreal.StaticMeshComponent);mesh=comp.get_editor_property('static_mesh') if comp else None
 try:hidden=bool(actor.get_editor_property('hidden'))
 except Exception:hidden=None
 return {'name':actor.get_name(),'path':actor.get_path_name(),'label':actor.get_actor_label(),'class':actor.get_class().get_path_name(),'location_cm':xyz(actor.get_actor_location()),'rotation':rpy(actor.get_actor_rotation()),'scale':xyz(actor.get_actor_scale3d()),'tags':sorted(str(t) for t in actor.get_editor_property('tags')),'mesh':mesh.get_path_name() if mesh else None,'materials':[comp.get_material(i).get_path_name() if comp.get_material(i) else None for i in range(comp.get_num_materials())] if comp else [],'hidden_in_game':hidden}
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

def local_position(p):
 x,y,z=p;return [(-8-y)*100,(13-x)*100,(8.96+z)*100]
def floor_z(y):return 1020-y*.1
def placement(id,mesh,p,space='world',era=None,scale=1,yaw=-90):return {'id':'brief.art.'+id,'mesh':'SM_Brief_'+mesh,'position_cm':local_position(p) if space=='home' else p,'era':era,'scale':scale,'yaw':yaw}
def placements():
 p=[
  placement('home.chair_repaired','ChairRepaired',[-2.3,2.15,1.15],'home','Present'),
  placement('home.chair_empty','ChairEmpty',[-1.45,2.1,1.15],'home','Present',yaw=-105),
  placement('home.clean_cup','CleanCup',[-.55,.20,1.995],'home','Present'),
  placement('home.cloth_tray','ClothTray',[-.45,-.40,1.997],'home','Present'),
  placement('home.coat_hook','CoatHook',[-.40,-3.42,1.80],'home','Present'),
  placement('home.latch_repair','LatchRepair',[1.12,-3.83,2.23],'home'),
  placement('home.workshop_sketch','WorkshopSketch',[.55,2.1,2.135],'home','Present'),
  placement('home.planter_left','FlowerPlanter',[-4.08,-4.15,1.15],'home',scale=.80),
  placement('home.planter_right','FlowerPlanter',[1.95,-5.10,1.15],'home',scale=.70),
  placement('home.window_box','WindowBox',[-2.70,-3.93,1.67],'home',scale=.92),
  placement('street.B.awning_past','AwningOpen',[-385,-180,1282],era='Past'),
  placement('street.B.awning_present','AwningFolded',[-385,-180,1282],era='Present'),
  placement('street.C.awning_past','AwningOpen',[-385,-1800,1442],era='Past',scale=.92),
  placement('street.B.window_box','WindowBox',[-385,-460,1410],era='Past'),
  placement('street.C.window_box','WindowBox',[-385,-2060,1600],era='Past'),
  placement('store.parcel_sign','SupplySign',[275,-175,1265],era='Past',yaw=90),
  placement('store.supplies','CrateSupplies',[325,-440,floor_z(-440)],era='Past',scale=.85),
  placement('street.empty_crate','CrateEmpty',[-325,-960,floor_z(-960)],era='Present',scale=.80,yaw=-104),
  placement('harbor.empty_crate','CrateEmpty',[345,-660,floor_z(-660)],era='Present',scale=.75),
  placement('street.maintained_planter','FlowerPlanter',[-330,-1080,floor_z(-1080)],scale=.85),
  placement('street.parapet_planter','FlowerPlanter',[430,-1140,floor_z(-1140)],scale=.72),
  placement('street.upper_planter','FlowerPlanter',[-345,-2750,floor_z(-2750)],scale=.70),
  placement('street.upper_empty_crate','CrateEmpty',[-350,-3060,floor_z(-3060)],era='Present',scale=.72),
  placement('street.upper_supply_crate','CrateSupplies',[-350,-3060,floor_z(-3060)],era='Past',scale=.72),
 ]
 return p

def ensure_refs_in_clone(manager,map_path):
 actors={a.get_name():a for a in world_actors()};rebound=[]
 for field in REF_FIELDS:
  try:old=manager.get_editor_property(field)
  except Exception:continue
  if not old:continue
  target=actors.get(old.get_name())
  if not target:raise RuntimeError('Map clone lost actor reference '+field)
  if target!=old:manager.set_editor_property(field,target);rebound.append(field)
  if not target.get_path_name().startswith(map_path+'.'):raise RuntimeError('Reference points outside cloned map '+field)
 for field in ARRAY_FIELDS:
  try:old=list(manager.get_editor_property(field))
  except Exception:continue
  fixed=[actors[a.get_name()] for a in old if a and a.get_name() in actors]
  if len(fixed)!=len(old):raise RuntimeError('Map clone lost era-array actor '+field)
  manager.set_editor_property(field,fixed)
 return rebound

def apply_prop(spec,kit,entries,previous,record):
 actor=unique(spec['id'])
 if actor:
  if not actor.actor_has_tag(OWNED):record['preserved_manual'].append({'actor':actor.get_path_name(),'reason':'Stable ID exists on unowned actor'});return actor
  if not editable(actor,previous,record):return actor
 else:actor=ACTORS.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(0,0,0),unreal.Rotator(pitch=0,yaw=0,roll=0))
 actor.set_actor_label('Brief — '+spec['id'].removeprefix('brief.art.').replace('.',' / '));actor.set_folder_path('Brief Art/House' if '.home.' in spec['id'] else 'Brief Art/Street')
 actor.set_actor_location(unreal.Vector(*spec['position_cm']),False,False);actor.set_actor_rotation(unreal.Rotator(pitch=0,yaw=spec['yaw'],roll=0),False);actor.set_actor_scale3d(unreal.Vector(spec['scale'],spec['scale'],spec['scale']))
 comp=actor.get_component_by_class(unreal.StaticMeshComponent);comp.set_mobility(unreal.ComponentMobility.STATIC);comp.set_static_mesh(kit[spec['mesh']]);comp.set_simulate_physics(False)
 blocking=entries[spec['mesh']]['collision_count']>0
 if blocking:comp.set_collision_profile_name('BlockAll');comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
 else:comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
 era='Opening.'+spec['era']+'Only' if spec['era'] else None
 tag_add(actor,OWNED,spec['id'],era,'Opening.Blocking' if blocking else 'Opening.Decorative')
 actor.set_actor_hidden_in_game(spec['era']=='Past');actor.set_actor_enable_collision(blocking and spec['era']!='Past')
 record['added_or_updated'].append(spec['id']);return actor

def add_cameras(previous,record):
 for view in CAMERAS:
  actor=unique(view['id'])
  if actor and (not actor.actor_has_tag(OWNED) or not editable(actor,previous,record)):continue
  if not actor:actor=ACTORS.spawn_actor_from_class(unreal.CameraActor,unreal.Vector(0,0,0),unreal.Rotator(pitch=0,yaw=0,roll=0))
  actor.set_actor_label(view['label']);actor.set_folder_path('Brief Art/Eye-level review cameras');tag_add(actor,OWNED,view['id'])
  pos=unreal.Vector(*view['position_cm']);target=unreal.Vector(*view['target_cm']);actor.set_actor_location(pos,False,False);actor.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(pos,target),False);actor.get_component_by_class(unreal.CameraComponent).set_field_of_view(view['fov']);actor.set_actor_enable_collision(False)

def override_wood(mats,previous,record):
 names={'SM_Home_Timber','SM_Home_Balcony','SM_Home_Details','SM_LeftHouse_B','SM_LeftHouse_C'}
 for actor in world_actors():
  comp=actor.get_component_by_class(unreal.StaticMeshComponent);mesh=comp.get_editor_property('static_mesh') if comp else None
  if not mesh or mesh.get_name() not in names:continue
  if not editable(actor,previous,record):continue
  for i in range(comp.get_num_materials()):
   old=comp.get_material(i)
   if old and old.get_name()=='M_Wood':comp.set_material(i,mats['M_Brief_Wood']);record['component_material_overrides'].append({'actor':actor.get_path_name(),'slot':i,'from':old.get_path_name(),'to':mats['M_Brief_Wood'].get_path_name()})

def build_art():
 if not (DEV/'baseline_manifest.json').exists():raise RuntimeError('This additive art build is restricted to the protected development copy')
 manifest=json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8'));version='V_'+manifest['build_stamp'];folder='/Game/BriefTest/ArtKit/'+version
 previous_report=json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
 protected_before=protected_hashes();run=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f');snapdir=ROOT/'validation'/'brief_art'/run;snapdir.mkdir(parents=True,exist_ok=True)
 report={'success':False,'scope':'Reversible M1 home frontage, maintained interior and adjacent street art test','kit_manifest':str(SOURCE/'manifest.json'),'asset_namespace':folder,'maps':[],'review_cameras':CAMERAS,'protected_content_sha_before':protected_before,'notes':['Original Home maps and source mesh/material assets are read-only inputs.','Street art additions span about43.6m of the existing spine; this is not a whole-city or final character-art claim.','No renderer, engine or driver setting is changed.']}
 try:
  mats=materials(manifest,folder);kit=meshes(manifest,mats,folder);entries={e['name']:e for e in manifest['assets']}
  for source_map,test_map in MAPS:
   existed=unreal.EditorAssetLibrary.does_asset_exist(test_map)
   if not existed:
    if not LEVEL.load_level(source_map):raise RuntimeError('Cannot open current source map '+source_map)
    if not unreal.EditorLoadingAndSavingUtils.save_map(EDITOR.get_editor_world(),test_map):raise RuntimeError('Cannot save reversible art-map copy '+test_map)
   if not LEVEL.load_level(test_map):raise RuntimeError('Cannot explicitly load art map '+test_map)
   managers=[a for a in world_actors() if a.actor_has_tag('Opening.Manager')]
   if len(managers)!=1:raise RuntimeError('Expected one preserved story manager in '+test_map)
   manager=managers[0]
   if manager.actor_has_tag(MANUAL):raise RuntimeError('Story manager is marked ManualOverride; era registration cannot be changed safely')
   before=snapshot();old_record=next((r for r in previous_report.get('maps',[]) if r.get('path')==test_map),{});prior={}
   if old_record.get('after_snapshot') and Path(old_record['after_snapshot']).exists():prior=json.loads(Path(old_record['after_snapshot']).read_text(encoding='utf-8'))
   record={'path':test_map,'source_map':source_map,'created_copy':not existed,'preserved_manual':[],'inferred_manual_names':list(old_record.get('inferred_manual_names',[])),'added_or_updated':[],'component_material_overrides':[],'manager_refs_rebound':ensure_refs_in_clone(manager,test_map)}
   name=test_map.rsplit('/',1)[-1];before_file=snapdir/(name+'_before.json');before_file.write_text(json.dumps(before,indent=2),encoding='utf-8');record['before_snapshot']=str(before_file);record['baseline_snapshot']=old_record.get('baseline_snapshot') or old_record.get('before_snapshot') or str(before_file)
   record['era_arrays_before']={field:[a.get_name() for a in manager.get_editor_property(field)] for field in ARRAY_FIELDS}
   for spec in placements():apply_prop(spec,kit,entries,prior,record)
   override_wood(mats,prior,record);add_cameras(prior,record)
   for field,tag in [('PastActors','Opening.PastOnly'),('PresentActors','Opening.PresentOnly')]:
    values=list(manager.get_editor_property(field))
    for a in world_actors():
     if a.actor_has_tag(OWNED) and a.actor_has_tag(tag) and a not in values:values.append(a)
    manager.set_editor_property(field,values)
   values=list(manager.get_editor_property('PastCollisionActors'))
   for a in world_actors():
    if a.actor_has_tag(OWNED) and a.actor_has_tag('Opening.PastOnly') and a.actor_has_tag('Opening.Blocking') and a not in values:values.append(a)
   manager.set_editor_property('PastCollisionActors',values)
   if not LEVEL.save_current_level():raise RuntimeError('Cannot save additive art map '+test_map)
   after_file=snapdir/(name+'_after.json');after_file.write_text(json.dumps(snapshot(),indent=2),encoding='utf-8');record['after_snapshot']=str(after_file);report['maps'].append(record)
  unreal.EditorAssetLibrary.save_directory(folder,only_if_is_dirty=True,recursive=True)
  protected_after=protected_hashes();changed=[p for p,h in protected_before.items() if protected_after.get(p)!=h];report['protected_source_content_unchanged']=not changed;report['unexpected_protected_changes']=changed
  if changed:raise RuntimeError('Protected source content changed unexpectedly: '+str(changed))
  report['success']=True
 except Exception:report['error']=traceback.format_exc();raise
 finally:OUT.write_text(json.dumps(report,indent=2),encoding='utf-8')
 return report

def revert_art(map_path):
 """Remove only unmodified owned additions; restore their component overrides."""
 report=json.loads(OUT.read_text(encoding='utf-8'));record=next(r for r in report['maps'] if r['path']==map_path)
 if not LEVEL.load_level(map_path):raise RuntimeError('Cannot open reversible art map')
 before=json.loads(Path(record.get('baseline_snapshot') or record['before_snapshot']).read_text(encoding='utf-8'));after=json.loads(Path(record['after_snapshot']).read_text(encoding='utf-8'));result={'preserved_manual':[],'inferred_manual_names':list(record.get('inferred_manual_names',[])),'removed':[],'restored_materials':[]}
 owned=[a for a in world_actors() if a.actor_has_tag(OWNED) and editable(a,after,result)]
 for manager in [a for a in world_actors() if a.actor_has_tag('Opening.Manager')]:
  if manager.actor_has_tag(MANUAL):continue
  for field in ARRAY_FIELDS:manager.set_editor_property(field,[a for a in manager.get_editor_property(field) if a not in owned])
 for actor in world_actors():
  if actor in owned:result['removed'].append(actor.get_name());ACTORS.destroy_actor(actor);continue
  if not editable(actor,after,result):continue
  old=before.get(actor.get_name());comp=actor.get_component_by_class(unreal.StaticMeshComponent)
  if not old or not comp:continue
  for i,path in enumerate(old.get('materials',[])):
   current=comp.get_material(i)
   if current and current.get_path_name().startswith('/Game/BriefTest/') and path:comp.set_material(i,unreal.load_asset(path));result['restored_materials'].append({'actor':actor.get_name(),'slot':i})
 LEVEL.save_current_level();return result

if __name__=='__main__':print(json.dumps(build_art(),indent=2))
