"""Queued one-actor ridge import/preview/apply/revert for Release Desktop.

No whole scenery generator runs. New assets are versioned; only the existing
owned distant-land actor's mesh changes on adoption. The first actor baseline,
material/transform/collision/era state and explicit/inferred edits are preserved.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy
import hashlib
import json
import sys
import traceback
import unreal

ROOT=Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/'Python'))
import build_release_hero as hero
base=hero.base
MAP=hero.MAP
SOURCE=ROOT.parent/'output/release_distant_ridges'
REPORT=ROOT/'release_distant_ridges_report.json'
SELECTION=ROOT/'release_distant_ridges_selection.json'
CAPTURE=ROOT/'release_distant_ridges_capture_report.json'
OWNER='TOSOY.ReleaseDistantRockOwned'
ID='quest.visual.distant_land'
STATIC=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)


def require(value,message):
    if not value:raise RuntimeError(message)


def read():return json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {}
def write(data):REPORT.write_text(json.dumps(data,indent=2,default=str)+'\n',encoding='utf-8')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def guard(write_native=False):
    hero.guard()
    if write_native:
        require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseDistantWrite'),
                'Root native authoring queue and -ReleaseDistantWrite are required')


def actor():
    values=[a for a in base.actors() if a.actor_has_tag(ID)]
    require(len(values)==1 and values[0].actor_has_tag('TOSOY.QuestVisualOwned'),'Expected the one existing owned distant-land actor')
    require(values[0].get_name()=='StaticMeshActor_195','Distant actor identity differs from approved native inventory')
    return values[0]


def state(value):
    row=base.state(value)
    comp=value.get_component_by_class(unreal.StaticMeshComponent)
    row.update(component_visible=bool(comp.get_editor_property('visible')),component_cast_shadow=bool(comp.get_editor_property('cast_shadow')))
    return row


def preserve_reason(value,record):
    if value.actor_has_tag('TOSOY.ManualOverride') or value.get_name() in record.get('inferred_manual_names',[]):
        return 'Explicit or previously detected manual override'
    if record.get('after') and state(value)!=record['after']:
        return 'Distant actor differs from the last applied generated state'
    if not record.get('after'):
        data=hero.read_report()['floors']
        file=Path(data['first_baseline_file'])
        require(sha(file)==data['first_baseline_sha256'],'Preserve changed first floor/reference baseline')
        reference=json.loads(file.read_text(encoding='utf-8'))[value.get_name()]
        if base.state(value)!=reference:
            return 'Distant actor differs from the actual current Release floor baseline'
        comp=value.get_component_by_class(unreal.StaticMeshComponent)
        if comp.get_editor_property('cast_shadow') or not comp.get_editor_property('visible'):
            return 'Distant component differs from reviewed visible/nonshadowing source'
    return None


def enforce_editable(value,record):
    reason=preserve_reason(value,record)
    if reason:
        record.setdefault('preserved_manual',[]).append({'actor':value.get_name(),'reason':reason})
        record['inferred_manual_names']=sorted(set(record.get('inferred_manual_names',[])+[value.get_name()]))
        write(record)
        raise RuntimeError('Preserving distant actor: '+reason)


def source():
    data=json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8'))
    require(data['owner']==OWNER and data['semantic_meshes']==1 and data['triangles']==7200 and data['collision_shapes']==0,'Unexpected ridge source scope/budget')
    require(data['material_slots']==['M_QuestDistantLand'] and len(data['patch_preservation'])==4,'Unexpected ridge material/patch scope')
    require(sha(ROOT.parent/'build_release_distant_ridges.py')==data['source_sha256'],'Ridge generator changed after export')
    require(sha(ROOT/'ContentData/release_distant_rock_proposal.json')==data['proposal_sha256'],'Ridge constraints changed after export')
    for entry in data['patch_preservation']:
        require(entry['xy_footprint_unchanged'] and entry['bounds_m']['max'][2]<=entry['peak_cap_m']+.00001,'Source footprint or sampled height cap changed')
    file=(SOURCE/data['mesh_file']).resolve()
    require(file.is_relative_to(SOURCE.resolve()) and sha(file)==data['mesh_sha256'],'FBX escaped staging or changed')
    return data,file


def bounds(mesh):
    value=mesh.get_bounds()
    return {'min':base.xyz(value.origin-value.box_extent),'max':base.xyz(value.origin+value.box_extent)}


def mesh_readback(mesh,old_mesh,material,manifest):
    require(isinstance(mesh,unreal.StaticMesh),'Ridge mesh import is missing')
    require(mesh.get_num_triangles(0)==manifest['triangles'],'Native triangle count differs from7200 source')
    require(STATIC.get_simple_collision_count(mesh)==0 and STATIC.get_convex_collision_count(mesh)==0,'Distant source must not acquire collision')
    require(len(mesh.get_editor_property('static_materials'))==1 and mesh.get_material(0)==material,'Distant material slot/reference changed')
    old,new=bounds(old_mesh),bounds(mesh)
    require(all(abs(old[side][axis]-new[side][axis])<=.25 for side in ['min','max'] for axis in range(3)),
            'Native imported extent/unit mismatch; no actor scaling workaround is allowed')
    return {'mesh':mesh.get_path_name(),'triangles':mesh.get_num_triangles(0),'vertices':mesh.get_num_vertices(0),
            'collision_shapes':0,'material':material.get_path_name(),'old_bounds_cm':old,'new_bounds_cm':new,
            'bounds_match_tolerance_cm':.25,'per_patch_caps':'Source FBX/manifest proof; no native per-patch isolation assertion'}


def prepare():
    guard(write_native=True)
    record=read()
    for filename,digest in record.get('asset_fingerprints',{}).items():
        require(Path(filename).is_file() and sha(filename)==digest,'Preserving artist-edited ridge asset')
    require(base.LEVEL.load_level(MAP),'Cannot open current Desktop map')
    value=actor()
    enforce_editable(value,record)
    before,lights,story=base.snapshot(),base.lighting(),base.story_refs()
    before_files=hero.files()
    manifest,file=source()
    signature=hashlib.sha256((manifest['mesh_sha256']+manifest['source_sha256']).encode()).hexdigest()[:16]
    folder='/Game/Release/DistantRidges/V_'+signature
    package=folder+'/SM_ReleaseDistantRidges'
    comp=value.get_component_by_class(unreal.StaticMeshComponent)
    old_state=record.get('baseline',state(value))
    old_mesh=base.load(old_state['mesh'])
    material=comp.get_material(0)
    mesh=base.load(package)
    if mesh:
        require(hero.LIB.get_metadata_tag(mesh,'Release.Distant.Owner')==OWNER and
                hero.LIB.get_metadata_tag(mesh,'Release.Distant.Signature')==signature,'Preserve unowned versioned ridge asset')
    else:
        options=unreal.FbxImportUI()
        for key,item in {'import_mesh':True,'import_as_skeletal':False,'import_materials':False,'import_textures':False,
                         'automated_import_should_detect_type':False,'mesh_type_to_import':unreal.FBXImportType.FBXIT_STATIC_MESH}.items():options.set_editor_property(key,item)
        data=options.get_editor_property('static_mesh_import_data')
        for key,item in {'combine_meshes':True,'transform_vertex_to_absolute':True,'convert_scene':True,'convert_scene_unit':True,
                         'force_front_x_axis':False,'auto_generate_collision':False,'generate_lightmap_u_vs':True,'build_nanite':False,
                         'remove_degenerates':True,'vertex_color_import_option':unreal.VertexColorImportOption.REPLACE,
                         'normal_import_method':unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS}.items():data.set_editor_property(key,item)
        task=unreal.AssetImportTask()
        for key,item in {'filename':str(file),'destination_path':folder,'destination_name':'SM_ReleaseDistantRidges','automated':True,
                         'replace_existing':False,'save':False,'factory':unreal.FbxFactory(),'options':options}.items():task.set_editor_property(key,item)
        base.ASSETS.import_asset_tasks([task])
        mesh=base.load(package)
        require(mesh is not None,'Versioned ridge import failed')
        mesh.set_material(0,material)
        hero.LIB.set_metadata_tag(mesh,'Release.Distant.Owner',OWNER)
        hero.LIB.set_metadata_tag(mesh,'Release.Distant.Signature',signature)
        hero.LIB.set_metadata_tag(mesh,'Release.Distant.FBXSHA256',manifest['mesh_sha256'])
        proof=mesh_readback(mesh,old_mesh,material,manifest)
        hero.save(mesh)
    proof=mesh_readback(mesh,old_mesh,material,manifest)
    require(base.snapshot()==before and base.lighting()==lights and base.story_refs()==story,'Ridge preparation changed map actors/lights/story')
    hero.check_existing(before_files)
    if not record.get('first_baseline_file'):
        out=ROOT/'validation/release_distant_baselines'
        out.mkdir(parents=True,exist_ok=True)
        first=out/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')+'.json')
        first.write_text(json.dumps({'target':state(value),'actors':before,'story':story,'lights':lights},indent=2)+'\n',encoding='utf-8')
        record.update(first_baseline_file=str(first),first_baseline_sha256=sha(first),baseline=state(value))
    require(sha(record['first_baseline_file'])==record['first_baseline_sha256'],'Immutable distant actor baseline changed')
    asset_file=ROOT/'Content'/(package.removeprefix('/Game/')+'.uasset')
    record.update(success=True,preview_ready=True,signature=signature,namespace=folder,mesh_path=mesh.get_path_name(),
                  native_mesh_readback=proof,manifest_sha256=sha(SOURCE/'manifest.json'),asset_fingerprints={str(asset_file):sha(asset_file)},
                  map_saved=False,visual_accepted=False,prepared_at=datetime.now(timezone.utc).isoformat())
    write(record)
    return record


def ready():
    guard()
    record=read()
    require(record.get('preview_ready'),'Prepare/import the actual ridge FBX first')
    require(sha(SOURCE/'manifest.json')==record['manifest_sha256'],'Ridge source changed after native preparation')
    for filename,digest in record['asset_fingerprints'].items():require(sha(filename)==digest,'Preserving artist-edited ridge mesh')
    require(sha(record['first_baseline_file'])==record['first_baseline_sha256'],'First ridge baseline changed')
    return record


def refresh_scenery_after(value):
    # Refresh only this legitimately generated actor fingerprint, never the
    # original scenery baseline, other actors, manual list or shared assets.
    import quest_scenery as scenery
    file=scenery.REPORT
    data=json.loads(file.read_text(encoding='utf-8'))
    item=data['maps'][MAP]
    require(value.get_name() in item['after'],'Expected existing scenery after-record')
    item['after'][value.get_name()]=scenery.state(value)
    file.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')


def preferred_mesh(fallback):
    """Release-only hook; no files, actors, materials or lights are written."""
    if ROOT.parent.name!='Release_20261026' or not SELECTION.exists():return fallback
    data=json.loads(SELECTION.read_text(encoding='utf-8'))
    if not data.get('active'):return fallback
    require(data['map']==MAP and data['stable_id']==ID,'Unexpected distant selection scope')
    require(sha(data['asset_file'])==data['asset_sha256'],'Preserve artist-edited preferred ridge asset')
    mesh=base.load(data['mesh_path'])
    require(isinstance(mesh,unreal.StaticMesh),'Preferred ridge is unavailable')
    return mesh


def apply(revert=False):
    guard(write_native=True)
    record=ready()
    if not revert:
        require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseDistantReviewed'),'Actual view review and -ReleaseDistantReviewed are required')
        capture=json.loads(CAPTURE.read_text(encoding='utf-8'))
        require(capture.get('success') and capture['ridge_signature']==record['signature'],'Actual matched ridge Before/After capture is required')
    require(base.LEVEL.load_level(MAP),'Cannot open ridge adoption/reversal map')
    value=actor()
    enforce_editable(value,record)
    before,lights,story,before_files=base.snapshot(),base.lighting(),base.story_refs(),hero.files()
    original=state(value)
    comp=value.get_component_by_class(unreal.StaticMeshComponent)
    mesh=base.load(record['baseline']['mesh'] if revert else record['mesh_path'])
    require(mesh is not None,'Selected distant mesh is unavailable')
    comp.set_static_mesh(mesh)
    after=state(value)
    require(all(original[k]==after[k] for k in original if k!='mesh'),'Ridge assignment changed a transform/material/collision/tag/visibility field')
    after_scene=base.snapshot()
    require(all(before[n]==after_scene[n] for n in before if n!=value.get_name()) and set(before)==set(after_scene),'Ridge assignment changed another actor')
    require(base.lighting()==lights and base.story_refs()==story,'Ridge assignment changed light/story/era references')
    hero.check_existing(before_files)
    changed=original!=after
    if changed:require(base.LEVEL.save_current_level(),'Could not save the one ridge mesh assignment')
    hero.check_existing(before_files,changed_map=True)
    file=Path(next(iter(record['asset_fingerprints'])))
    selection={'schema':1,'map':MAP,'stable_id':ID,'active':not revert,'mesh_path':record['mesh_path'],
               'asset_file':str(file),'asset_sha256':sha(file),'signature':record['signature']}
    SELECTION.write_text(json.dumps(selection,indent=2)+'\n',encoding='utf-8')
    record.update(after=after,active=not revert,reverted=revert,map_saved=changed,idempotent_no_map_save=not changed,
                  visual_accepted=not revert,original_material_transform_collision_era_unchanged=True)
    refresh_scenery_after(value)
    write(record)
    require(base.LEVEL.load_level(MAP) and state(actor())==after,'Saved ridge actor differs on reload')
    return record


if __name__=='__main__':
    try:
        command=unreal.SystemLibrary.get_command_line()
        if unreal.SystemLibrary.parse_param(command,'RevertReleaseDistant'):result=apply(revert=True)
        elif unreal.SystemLibrary.parse_param(command,'ReleaseDistantReviewed'):result=apply()
        else:result=prepare()
    except Exception:
        data=read();data.setdefault('attempt_failures',[]).append({'at':datetime.now(timezone.utc).isoformat(),'error':traceback.format_exc()})
        data['last_attempt_success']=False;write(data);raise
    finally:unreal.SystemLibrary.quit_editor()
