"""Bounded release material pass; run only in the root-granted editor queue.

Five known waterfront wood/plaster slots reuse approved inherited materials.
One versioned opaque sea material reuses the existing normal texture. No mesh,
collision, actor transform, sky/light, renderer, gameplay or save change.
Imports are side-effect free. build_all(), revert_map() and validate_saved()
provide explicit authoring, reversal and native readback entry points.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy, hashlib, json, math, traceback
import unreal

ROOT=Path(unreal.Paths.project_dir()).resolve();DEV=ROOT.parent
REPORT_PATH=ROOT/'release_art_report.json'
OWNED='TOSOY.ReleaseArtOwned';MANUAL='TOSOY.ManualOverride'
MAPS=['/Game/Quest/Maps/Verdant_Desktop']
SLOTS={
 'SM_PromenadeRail':{0:('M_Plaster','plaster'),2:('M_Wood','wood')},
 'SM_DocksMain':{0:('M_Wood','wood')},
 'SM_CliffVillas':{1:('M_Wood','wood'),2:('M_Plaster','plaster')},
}
WATER_TEXTURE='/Game/Quest/Scenery/V_20261025T105028_647262/Textures/T_QuestWater_Normal'
WATER_POLICY={'normal_strength':.38,'roughness_min':.38,'roughness_max':.50,'specular':.25,
 'normal_a_scale':[.17,.13],'normal_a_speed':[.0031,.0018],
 'normal_b_scale':[.067,.085],'normal_b_speed':[-.0014,.0023],
 'normal_b_rotation_matrix':[.63,.77,-.77,.63],'blend_weights':[.68,.32],
 'basecolor_srgb8':[31,89,101],'opaque':True}
PARAMS={'WaveNormalStrength':.38,'RoughnessMin':.38,'RoughnessMax':.50}
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVEL=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ASSETS=unreal.AssetToolsHelpers.get_asset_tools();MEL=unreal.MaterialEditingLibrary

def require(ok,message):
 if not ok:raise RuntimeError(message)
def stamp():return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
def guard():
 require('-run=' not in unreal.SystemLibrary.get_command_line().lower(),'Use a full editor Python entry point, not a commandlet')
 require(ACTORS is not None and LEVEL is not None and EDITOR is not None,'Full editor subsystems are required')
 require(not LEVEL.is_in_play_in_editor(),'Material authoring must not run during PIE')
 require(DEV.name=='Release_20261026','Release art refuses another workspace')
 data=json.loads((DEV/'release_baseline_manifest.json').read_text(encoding='utf-8'))
 require(Path(data['target']).resolve()==DEV,'Release copy does not match its baseline')
def read_report():return json.loads(REPORT_PATH.read_text(encoding='utf-8')) if REPORT_PATH.exists() else {'schema_version':1,'maps':{}}
def save_report(report):REPORT_PATH.write_text(json.dumps(report,indent=2),encoding='utf-8')
def load(path):return unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
def copied_asset_unchanged(asset):
 package=asset.get_path_name().split('.')[0]
 if package.startswith('/Game/Release/Art/Water/'):
  return unreal.EditorAssetLibrary.get_metadata_tag(asset,'TOSOY.ReleaseArt.Owner')==OWNED
 if not package.startswith('/Game/'):return False
 path=(ROOT/'Content'/(package.removeprefix('/Game/')+'.uasset')).resolve()
 copied=json.loads((DEV/'release_baseline_manifest.json').read_text(encoding='utf-8'))
 entry=next((e for e in copied['files'] if Path(e['copy']).resolve()==path),None)
 return entry is not None and digest(path)==entry['sha256']
def actors():return list(ACTORS.get_all_level_actors())
def xyz(v):return [round(v.x,4),round(v.y,4),round(v.z,4)]
def state(actor):
 comp=actor.get_component_by_class(unreal.StaticMeshComponent);mesh=comp.get_editor_property('static_mesh') if comp else None
 return {'name':actor.get_name(),'label':actor.get_actor_label(),'class':actor.get_class().get_path_name(),
  'location_cm':xyz(actor.get_actor_location()),'rotation':[round(v,4) for v in [actor.get_actor_rotation().pitch,actor.get_actor_rotation().yaw,actor.get_actor_rotation().roll]],
  'scale':xyz(actor.get_actor_scale3d()),'tags':sorted(str(t) for t in actor.get_editor_property('tags')),
  'hidden_in_game':bool(actor.get_editor_property('hidden')),'actor_collision':actor.get_actor_enable_collision(),
  'mesh':mesh.get_path_name() if mesh else None,'materials':[comp.get_material(i).get_path_name() if comp.get_material(i) else None for i in range(comp.get_num_materials())] if comp else [],
  'raw_override_materials':[m.get_path_name() if m else None for m in comp.get_editor_property('override_materials')] if comp else [],
  'collision_enabled':str(comp.get_collision_enabled()) if comp else None,'collision_profile':str(comp.get_collision_profile_name()) if comp else None,
  'collision_responses':{str(c):str(comp.get_collision_response_to_channel(c)) for c in [unreal.CollisionChannel.ECC_PAWN,unreal.CollisionChannel.ECC_VISIBILITY]} if comp else {}}
def snapshot():return {a.get_name():state(a) for a in actors()}
def physical(s):return {k:v for k,v in s.items() if k not in ['materials','raw_override_materials','tags']}
def config_hashes():return {str(p.relative_to(ROOT)):digest(p) for p in (ROOT/'Config').glob('*.ini')}
def asset_hashes():return {str(p.relative_to(ROOT)):digest(p) for p in (ROOT/'Content').rglob('*.uasset')}
def save_hashes():return {str(p):digest(p) for p in (ROOT/'Saved/SaveGames').glob('*.sav')}
def lighting():
    result={}
    for actor in actors():
        comp=actor.get_component_by_class(unreal.LightComponentBase)
        if comp:
            rotation=actor.get_actor_rotation()
            result[actor.get_name()]={'class':actor.get_class().get_path_name(),'location':xyz(actor.get_actor_location()),
                                      'rotation':[round(rotation.pitch,5),round(rotation.yaw,5),round(rotation.roll,5)]}
            for field in ['intensity','light_color','visible','cast_shadows','real_time_capture','cubemap','source_cubemap_angle']:
                try:
                    value=comp.get_editor_property(field)
                    if isinstance(value,unreal.Object):value=value.get_path_name()
                    elif isinstance(value,(unreal.Color,unreal.LinearColor)):value={channel:getattr(value,channel) for channel in ['r','g','b','a']}
                    elif value is not None and not isinstance(value,(bool,int,float,str)):value=str(value)
                    result[actor.get_name()][field]=value
                except Exception:pass
    return result
def story_refs():
 result={}
 for a in actors():
  if not a.actor_has_tag('Opening.Manager'):continue
  result[a.get_name()]={}
  for name in ['SaveSlot','InteractionRange','PhotoActor','LetterActor','MotherActor','BenchActor','ComponentActor','AnchorActor','NeriActor','HealerActor','SelaActor','WaterActor','LinenActor','LinenTrayActor','CanvasActor','ClinicInstallActor','HarborInstallActor','MemorialActor','PastActors','PresentActors','PastCollisionActors']:
   try:
    value=a.get_editor_property(name)
    if isinstance(value,unreal.Actor):value=value.get_path_name()
    elif name in ['PastActors','PresentActors','PastCollisionActors']:value=[v.get_path_name() for v in value]
    else:value=str(value)
    result[a.get_name()][name]=value
   except Exception:pass
 return result
def local_snapshot(path):
 # Copied reports contain Quest absolute paths. Never read the recovery copy.
 parts=Path(path).parts;indices=[i for i,p in enumerate(parts) if p.lower()=='game_unreal']
 require(bool(indices),'Unrecognized inherited snapshot path')
 target=ROOT.joinpath(*parts[indices[-1]+1:]).resolve()
 require(target.is_relative_to((ROOT/'validation').resolve()),'Snapshot escaped release validation folder')
 return target if target.is_file() else None
def trusted_reference(map_path):
 source=json.loads((ROOT/'quest_district_report.json').read_text(encoding='utf-8'))
 record=next(r for r in source['maps'] if r['path']==map_path)
 local=local_snapshot(record['after_snapshot'])
 if local:return json.loads(local.read_text(encoding='utf-8'))
 # The release copy deliberately omitted old validation folders. The entire
 # saved map must still be byte-identical to the verified copy before we may
 # bootstrap a new actor baseline; never guess after another saved map edit.
 path=(ROOT/'Content'/(map_path.removeprefix('/Game/')+'.umap')).resolve()
 baseline=json.loads((DEV/'release_baseline_manifest.json').read_text(encoding='utf-8'))
 entry=next((e for e in baseline['files'] if Path(e['copy']).resolve()==path),None)
 require(entry is not None and digest(path)==entry['sha256'],
  'No trusted local actor baseline and release map changed since copy: '+map_path)
 return snapshot()
def comparable(s):
 keys=['name','label','class','location_cm','rotation','scale','tags','hidden_in_game','mesh','materials','collision_enabled','collision_profile','collision_responses']
 return {k:s.get(k) for k in keys}
def find_mesh(name):
 matches=[]
 for a in actors():
  comp=a.get_component_by_class(unreal.StaticMeshComponent);mesh=comp.get_editor_property('static_mesh') if comp else None
  if mesh and mesh.get_name()==name:matches.append(a)
 require(len(matches)==1,'Expected one '+name+' actor; found '+str(len(matches)));return matches[0]
def tag(actor,mesh_name):
 stable='release.art.override.'+mesh_name
 require(not any(a!=actor and a.actor_has_tag(stable) for a in actors()),'Duplicate release material ID '+stable)
 values=[str(t) for t in actor.get_editor_property('tags')]
 for value in [OWNED,stable]:
  if value not in values:values.append(value)
 actor.set_editor_property('tags',[unreal.Name(v) for v in values])
def editable(actor,record,previous,reference):
 name=actor.get_name();reason=None
 if actor.actor_has_tag(MANUAL):reason=MANUAL
 elif name in record['inferred_manual_names']:reason='Previously detected manual change'
 elif name in previous and state(actor)!=previous[name]:reason='Actor differs from last successful release after-snapshot'
 elif name not in previous and (name not in reference or comparable(state(actor))!=comparable(reference[name])):reason='No unchanged trusted release-copy baseline'
 if reason:
  record['preserved_manual'].append({'actor':name,'reason':reason})
  if name not in record['inferred_manual_names']:record['inferred_manual_names'].append(name)
  return False
 record['baseline'].setdefault(name,state(actor));return True

def approved_materials(map_path):
 inherited=json.loads((ROOT/'quest_premium_art_report.json').read_text(encoding='utf-8'))['maps'][map_path]
 require(inherited['success'] and inherited['enabled'],'No approved inherited photographic material pass')
 folder=inherited['shader_namespace'];require(folder.startswith('/Game/Quest/PremiumArt/Shader_'),'Unexpected inherited material namespace')
 result={key:load(folder+'/'+name) for key,name in [('wood','M_PhotoQuestTimber'),('plaster','M_PhotoQuestLimewash')]}
 require(all(isinstance(m,unreal.MaterialInterface) for m in result.values()),'Approved photographic materials missing')
 require(all(copied_asset_unchanged(m) for m in result.values()),'Preserve artist-edited approved material assets; release-copy hashes differ')
 return result

def node(mat,kind,**props):
 value=MEL.create_material_expression(mat,getattr(unreal,'MaterialExpression'+kind),-400,0)
 for key,item in props.items():value.set_editor_property(key,item)
 return value
def wire(a,b,pin='',output=''):
 if MEL.connect_material_expressions(a,output,b,pin):return
 names=[str(v) for v in MEL.get_material_expression_input_names(b)]
 if len(names)==1 and MEL.connect_material_expressions(a,output,b,''):return
 raise RuntimeError('Cannot connect '+a.get_class().get_name()+'.'+output+' to '+b.get_class().get_name()+'.'+pin+' inputs='+str(names))
def out(a,mat,property,output=''):
 require(MEL.connect_material_property(a,output,property),'Material output connection failed '+str(property))
def scalar(mat,value):return node(mat,'Constant',r=float(value))
def vector(mat,value):return node(mat,'Constant3Vector',constant=unreal.LinearColor(*value,1))
def multiply(mat,a,b):
 value=node(mat,'Multiply');wire(a,value,'A');wire(b,value,'B');return value
def add(mat,a,b):
 value=node(mat,'Add');wire(a,value,'A');wire(b,value,'B');return value
def channel(mat,input,key):
 value=node(mat,'ComponentMask',r=key=='r',g=key=='g',b=False,a=False);wire(input,value);return value
def parameter(mat,name,value):return node(mat,'ScalarParameter',parameter_name=unreal.Name(name),default_value=float(value))
def linear(rgb):return [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in [c/255 for c in rgb]]
def normal_sample(mat,texture,coords):
 sample=node(mat,'TextureSample',texture=texture,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL);wire(coords,sample,'UVs');return sample
def panner(mat,uv,speed):
 value=node(mat,'Panner',speed_x=speed[0],speed_y=speed[1]);wire(uv,value,'Coordinate');return value
def water_version():return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]
def water_asset_path():return '/Game/Release/Art/Water/V_'+water_version()+'/M_ReleaseCoastalWater'
def validate_water(mat,compile_graph=False):
 required=[unreal.MaterialProperty.MP_BASE_COLOR,unreal.MaterialProperty.MP_NORMAL,unreal.MaterialProperty.MP_ROUGHNESS,unreal.MaterialProperty.MP_SPECULAR,unreal.MaterialProperty.MP_METALLIC]
 require(all(MEL.get_material_property_input_node(mat,p) for p in required),'Water graph is missing a required output')
 errors=list(MEL.recompile_material(mat)) if compile_graph else None
 if compile_graph:require(not errors,'Water compiler errors: '+str(errors))
 values={name:float(MEL.get_material_default_scalar_parameter_value(mat,unreal.Name(name))) for name in PARAMS}
 require(all(abs(values[n]-v)<1e-5 for n,v in PARAMS.items()),'Water parameter defaults changed; preserve artist edits')
 expressions=list(MEL.get_material_expressions(mat));samples=[e for e in expressions if isinstance(e,unreal.MaterialExpressionTextureSample)]
 textures=[e.get_editor_property('texture').get_path_name() for e in samples]
 expected=load(WATER_TEXTURE)
 require(len(samples)==2 and all(e.get_editor_property('texture')==expected for e in samples),'Expected exactly two samples of the existing normal texture')
 require(mat.get_editor_property('blend_mode')==unreal.BlendMode.BLEND_OPAQUE,'Water must remain opaque')
 require(MEL.get_material_property_input_node(mat,unreal.MaterialProperty.MP_EMISSIVE_COLOR) is None,'Water must not add a painted/emissive reflection stripe')
 return {'asset':mat.get_path_name(),'scalar_defaults':values,'texture_samples':textures,'compile_errors':errors,'compilation_executed':compile_graph,
  'blend_mode':str(mat.get_editor_property('blend_mode')),'shading_model':str(mat.get_editor_property('shading_model')),
  'normal_strength_reduced_from_1':True,'roughness_range':[values['RoughnessMin'],values['RoughnessMax']],
  'visual_validation_pending':True,'motion_aliasing_test_pending':True,'device_performance_measured':False}
def create_water():
 guard()
 path=water_asset_path();mat=load(path)
 if mat:
  require(unreal.EditorAssetLibrary.get_metadata_tag(mat,'TOSOY.ReleaseArt.Owner')==OWNED,'Existing versioned water material has no matching ownership')
  require(unreal.EditorAssetLibrary.get_metadata_tag(mat,'TOSOY.ReleaseArt.SourceSHA')==digest(Path(__file__)),'Existing water source marker differs')
  if unreal.EditorAssetLibrary.get_metadata_tag(mat,'TOSOY.ReleaseArt.BuildState')=='Complete':return mat,validate_water(mat,compile_graph=True)
  require(unreal.EditorAssetLibrary.get_metadata_tag(mat,'TOSOY.ReleaseArt.BuildState')=='Building','Unknown water build state')
  MEL.delete_all_material_expressions(mat)
 else:
  folder,name=path.rsplit('/',1);mat=ASSETS.create_asset(name,folder,unreal.Material,unreal.MaterialFactoryNew());require(mat is not None,'Cannot create versioned release water')
 unreal.EditorAssetLibrary.set_metadata_tag(mat,'TOSOY.ReleaseArt.Owner',OWNED)
 unreal.EditorAssetLibrary.set_metadata_tag(mat,'TOSOY.ReleaseArt.SourceSHA',digest(Path(__file__)))
 unreal.EditorAssetLibrary.set_metadata_tag(mat,'TOSOY.ReleaseArt.BuildState','Building')
 mat.set_editor_property('blend_mode',unreal.BlendMode.BLEND_OPAQUE);mat.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
 texture=load(WATER_TEXTURE);require(isinstance(texture,unreal.Texture2D),'Inherited water normal is unavailable')
 uv_a=node(mat,'TextureCoordinate',u_tiling=.17,v_tiling=.13);coords_a=panner(mat,uv_a,WATER_POLICY['normal_a_speed'])
 uv_b=node(mat,'TextureCoordinate',u_tiling=.067,v_tiling=.085);u=channel(mat,uv_b,'r');v=channel(mat,uv_b,'g')
 ru=add(mat,multiply(mat,u,scalar(mat,.63)),multiply(mat,v,scalar(mat,.77)))
 rv=add(mat,multiply(mat,u,scalar(mat,-.77)),multiply(mat,v,scalar(mat,.63)))
 rotated=node(mat,'AppendVector');wire(ru,rotated,'A');wire(rv,rotated,'B');coords_b=panner(mat,rotated,WATER_POLICY['normal_b_speed'])
 a=normal_sample(mat,texture,coords_a);b=normal_sample(mat,texture,coords_b)
 # Small tangent-space normal amplitudes permit a cheap weighted sum/normalize.
 combined=add(mat,multiply(mat,a,scalar(mat,.68)),multiply(mat,b,scalar(mat,.32)))
 strength=parameter(mat,'WaveNormalStrength',PARAMS['WaveNormalStrength'])
 xy=node(mat,'AppendVector');wire(strength,xy,'A');wire(strength,xy,'B')
 xyz_strength=node(mat,'AppendVector');wire(xy,xyz_strength,'A');wire(scalar(mat,1),xyz_strength,'B')
 softened=multiply(mat,combined,xyz_strength);normal=node(mat,'Normalize');wire(softened,normal)
 out(normal,mat,unreal.MaterialProperty.MP_NORMAL)
 low=parameter(mat,'RoughnessMin',PARAMS['RoughnessMin']);high=parameter(mat,'RoughnessMax',PARAMS['RoughnessMax'])
 width=node(mat,'Subtract');wire(high,width,'A');wire(low,width,'B')
 remapped=add(mat,multiply(mat,channel(mat,a,'r'),scalar(mat,.5)),scalar(mat,.5))
 rough=add(mat,low,multiply(mat,remapped,width));clamped=node(mat,'Clamp',min_default=.02,max_default=.98);wire(rough,clamped)
 out(clamped,mat,unreal.MaterialProperty.MP_ROUGHNESS);out(vector(mat,linear(WATER_POLICY['basecolor_srgb8'])),mat,unreal.MaterialProperty.MP_BASE_COLOR)
 out(scalar(mat,.25),mat,unreal.MaterialProperty.MP_SPECULAR);out(scalar(mat,0),mat,unreal.MaterialProperty.MP_METALLIC)
 readback=validate_water(mat,compile_graph=True)
 unreal.EditorAssetLibrary.set_metadata_tag(mat,'TOSOY.ReleaseArt.Policy',json.dumps(WATER_POLICY,sort_keys=True))
 unreal.EditorAssetLibrary.set_metadata_tag(mat,'TOSOY.ReleaseArt.BuildState','Complete');unreal.EditorAssetLibrary.save_loaded_asset(mat)
 return mat,readback

def native_readback(record,mats,water):
 rows=[]
 for item in record['assignments']:
  actor=next(a for a in actors() if a.get_name()==item['actor']);comp=actor.get_component_by_class(unreal.StaticMeshComponent)
  actual=comp.get_material(item['slot']);expected=water if item['role']=='water' else mats[item['role']]
  require(actual==expected,'Native assigned material differs at '+item['actor']+'/'+str(item['slot']))
  rows.append({'actor':item['actor'],'slot':item['slot'],'mesh':comp.get_editor_property('static_mesh').get_path_name(),'material':actual.get_path_name(),'passed':True})
 for name,baseline in record['baseline'].items():
  actor=next((a for a in actors() if a.get_name()==name),None)
  if actor and any(i['actor']==name for i in record['assignments']):require(physical(state(actor))==physical(baseline),'Geometry/transform/collision changed on '+name)
 return {'assignments':rows,'water':validate_water(water),'five_surface_slots_requested':5,
  'surface_slots_applied':sum(i['role']!='water' for i in record['assignments']),'water_slots_applied':sum(i['role']=='water' for i in record['assignments']),
  'complete_requested_scope':len(rows)==6,'manual_override_count':len(record['preserved_manual'])}

def apply_map(map_path,water,folder,all_report):
 guard()
 require(map_path in MAPS,'Refusing a non-release-target map')
 require(LEVEL.load_level(map_path),'Cannot load '+map_path)
 old=all_report['maps'].get(map_path,{})
 record={'path':map_path,'success':False,'run':folder.name,'baseline':copy.deepcopy(old.get('baseline',{})),
  'first_baseline_snapshot':old.get('first_baseline_snapshot'),'inferred_manual_names':list(old.get('inferred_manual_names',[])),
  'preserved_manual':[],'assignments':[],'reverted':False}
 previous=old.get('after',{}) if old.get('success') and not old.get('reverted') else {}
 reference=copy.deepcopy(old.get('baseline')) or trusted_reference(map_path);before=snapshot();sun=lighting();refs=story_refs();mats=approved_materials(map_path)
 before_file=folder/(map_path.rsplit('/',1)[-1]+'_before.json');before_file.write_text(json.dumps(before,indent=2),encoding='utf-8')
 record['before_snapshot']=str(before_file);record['first_baseline_snapshot']=record['first_baseline_snapshot'] or str(before_file)
 for mesh_name,slots in SLOTS.items():
  actor=find_mesh(mesh_name)
  if not editable(actor,record,previous,reference):continue
  comp=actor.get_component_by_class(unreal.StaticMeshComponent)
  if any(comp.get_material(i) and not copied_asset_unchanged(comp.get_material(i)) for i in slots):
   record['preserved_manual'].append({'actor':actor.get_name(),'reason':'Referenced source material differs from verified release-copy asset'})
   if actor.get_name() not in record['inferred_manual_names']:record['inferred_manual_names'].append(actor.get_name())
   continue
  for slot,(original_name,role) in slots.items():
   material=comp.get_material(slot)
   require(material and (material.get_name()==original_name or material==mats[role]),'Unexpected known slot; preserve '+mesh_name+'/'+str(slot))
   comp.set_material(slot,mats[role]);record['assignments'].append({'actor':actor.get_name(),'mesh':mesh_name,'slot':slot,'role':role,'from':material.get_path_name(),'to':mats[role].get_path_name()})
  tag(actor,mesh_name)
 actor=find_mesh('SM_Sea')
 if editable(actor,record,previous,reference):
  comp=actor.get_component_by_class(unreal.StaticMeshComponent);original=comp.get_material(0)
  require(original and copied_asset_unchanged(original),'Preserve changed source sea material; no override applied')
  require(original and (original.get_name()=='M_QuestWater' or original.get_path_name().startswith('/Game/Release/Art/Water/')),'Unexpected existing sea material')
  comp.set_material(0,water);tag(actor,'SM_Sea');record['assignments'].append({'actor':actor.get_name(),'mesh':'SM_Sea','slot':0,'role':'water','from':original.get_path_name(),'to':water.get_path_name()})
 after=snapshot();allowed={i['actor'] for i in record['assignments']}
 require(set(before)==set(after),'Art pass added/removed actors')
 for name in before:
  require(physical(before[name])==physical(after[name]),'Unintended physical actor change '+name)
  if name not in allowed:require(before[name]==after[name],'Unrelated actor changed '+name)
  else:
   allowed_slots={i['slot'] for i in record['assignments'] if i['actor']==name}
   for index,value in enumerate(before[name]['materials']):
    if index not in allowed_slots:require(after[name]['materials'][index]==value,'Unrequested material slot changed '+name+'/'+str(index))
 sun_after=lighting()
 if sun!=sun_after:
  difference={name:{'before':sun.get(name),'after':sun_after.get(name)} for name in set(sun)|set(sun_after) if sun.get(name)!=sun_after.get(name)}
  (folder/'lighting_guard_difference.json').write_text(json.dumps(difference,indent=2),encoding='utf-8')
 require(sun==sun_after,'A light/sky component changed; inspect lighting_guard_difference.json');require(refs==story_refs(),'Story references, era arrays or profile changed')
 record['readback']=native_readback(record,mats,water)
 require(LEVEL.save_current_level(),'Cannot save bounded material update')
 after_file=folder/(map_path.rsplit('/',1)[-1]+'_after.json');after_file.write_text(json.dumps(after,indent=2),encoding='utf-8')
 record.update(success=True,after={name:after[name] for name in allowed},after_snapshot=str(after_file),
  actor_geometry_collision_transforms_unchanged=True,lights_and_story_unchanged=True)
 all_report['maps'][map_path]=record;save_report(all_report);return record

def build_all(map_paths=None):
 guard();paths=list(MAPS if map_paths is None else map_paths);require(paths and all(p in MAPS for p in paths),'Invalid map list')
 report=read_report();run=stamp();folder=ROOT/'validation/release_art'/run;folder.mkdir(parents=True,exist_ok=False)
 before_assets=asset_hashes();before_config=config_hashes();before_saves=save_hashes()
 report.update(success=False,run=run,scope='Exactly five waterfront wood/plaster slots plus one opaque sea slot per eligible map',
  source_sha256=digest(Path(__file__)),water_policy=WATER_POLICY,headset_tested=False,visual_quality_accepted=False,performance_measured=False)
 try:
  # Previously completed owned assets remain manual-edit protected as well.
  for relative,expected in report.get('owned_asset_sha_after',{}).items():require(digest(ROOT/relative)==expected,'Preserve edited release art asset '+relative)
  water,readback=create_water();report['water_native_readback']=readback
  for path in paths:apply_map(path,water,folder,report)
  # A selected lighting pass is a separate owned scope. Art reruns verify it
  # without changing lights, silently reapplying a reverted choice, or replacing
  # artist overrides. This read-only hook never calls the lighting writer.
  from apply_release_skylight import retain_selected
  report['selected_skylight_retention']=retain_selected()
  require(all(digest(ROOT/p)==h for p,h in before_assets.items()),'An existing shared asset changed')
  require(before_config==config_hashes(),'Renderer/project config changed');require(before_saves==save_hashes(),'Save files changed')
  directory=ROOT/'Content/Release/Art/Water'/('V_'+water_version())
  report['owned_asset_sha_after']={str(p.relative_to(ROOT)):digest(p) for p in directory.rglob('*.uasset')}
  if report.get('last_error'):
   report.setdefault('prior_failed_attempts',[]).append({'error':report.pop('last_error'),'retained_at_successful_run':run})
  report.update(success=True,existing_assets_unchanged=True,config_and_saves_unchanged=True,
   native_maps_complete=all(report['maps'][p]['readback']['complete_requested_scope'] for p in paths))
 except Exception:report['last_error']=traceback.format_exc();raise
 finally:save_report(report)
 return report

def revert_map(map_path):
 guard();require(map_path in MAPS,'Refusing a non-target map');report=read_report();old=report['maps'][map_path]
 require(LEVEL.load_level(map_path),'Cannot load reversal map')
 require(old.get('success') and old.get('after'),'No successful owned apply to reverse')
 result={'path':map_path,'preserved_manual':[],'inferred_manual_names':list(old.get('inferred_manual_names',[])),'restored':[]}
 for name,baseline in old['baseline'].items():
  actor=next((a for a in actors() if a.get_name()==name),None)
  if not actor or not actor.actor_has_tag(OWNED):continue
  if not editable(actor,{**result,'baseline':{}},old['after'],{}):continue
  comp=actor.get_component_by_class(unreal.StaticMeshComponent)
  comp.set_editor_property('override_materials',[load(p) if p else None for p in baseline['raw_override_materials']])
  actor.set_editor_property('tags',[unreal.Name(t) for t in baseline['tags']])
  require(state(actor)==baseline,'Reversal failed to restore first baseline '+name);result['restored'].append(name)
 require(LEVEL.save_current_level(),'Cannot save scoped reversal')
 old['reverted']=True;old['revert_result']=result;old['inferred_manual_names']=result['inferred_manual_names'];save_report(report);return result

def validate_saved(map_paths=None):
 """Read-only native graph/material/state readback; never saves a map/asset."""
 guard();report=read_report();water=load(report['water_native_readback']['asset']);require(water is not None,'Applied water asset missing')
 result={'success':False,'maps':[],'map_or_asset_saves':False,'headset_tested':False,'visual_acceptance_pending':True}
 for path in MAPS if map_paths is None else map_paths:
  require(LEVEL.load_level(path),'Cannot load validation map');record=report['maps'][path]
  require(record['success'] and not record.get('reverted'),'Map has no current successful apply')
  row=native_readback(record,approved_materials(path),water)
  row['path']=path;result['maps'].append(row)
 result['success']=True;result['complete_requested_scope']=all(r['complete_requested_scope'] for r in result['maps']);return result

if __name__=='__main__':
 try:
  data=build_all();unreal.log('RELEASE_ART_NATIVE '+str(data['success']))
 except Exception:unreal.log_error(traceback.format_exc())
 finally:unreal.SystemLibrary.quit_editor()
