"""Import one visible solid stair enclosure; preserve existing scene identities.

Shared in both eras per approved plan. Seven native convex hulls must match
seven visible solids; no invisible collision-only actor or map regeneration.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,shutil,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import build_release_art as art
import release_file_io as io


def main():
    art.guard();art.require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseClosureWrite'),'Root queue required')
    source=ROOT.parent/'output/release_upstairs_closure';manifest=json.loads((source/'manifest.json').read_text())
    plan_file=ROOT/'ContentData/release_upstairs_closure_plan.json';plan=json.loads(plan_file.read_text())
    art.require(manifest['plan_sha256']==io.sha(plan_file) and manifest['source_sha256']==io.sha(ROOT.parent/'build_release_upstairs_closure.py'),'Closure source/plan changed')
    file=source/manifest['file'];art.require(io.sha(file)==manifest['file_sha256'] and manifest['ucx_boxes']==7 and manifest['triangles']<=5000,'Closure export proof differs')
    report_file=ROOT/'release_upstairs_closure_validation.json'
    previous=json.loads(report_file.read_text()) if report_file.exists() else None
    if previous:
        art.require(previous['success'] and previous['source_sha256']!=manifest['file_sha256'],'Preserve the prior adoption; only an explicit new source revision may refresh it')
    before_files={str(p):io.sha(p) for p in io.files(ROOT/'Content','*.uasset')+io.files(ROOT/'Content','*.umap')+list((ROOT/'Config').glob('*.ini'))+list(ROOT.glob('*.uproject'))+io.files(ROOT/'Saved/SaveGames','*.sav')}
    map_file=ROOT/'Content/Quest/Maps/Verdant_Desktop.umap'
    art.require(art.LEVEL.load_level('/Game/Quest/Maps/Verdant_Desktop'),'Cannot load desktop map')
    actors_before,lights,story=art.snapshot(),art.lighting(),art.story_refs()
    matches=[a for a in art.actors() if a.actor_has_tag(plan['stable_id'])]
    art.require(len(matches)==(1 if previous else 0),'Unexpected existing closure actor count')
    if previous:art.require(art.state(matches[0])==previous['actor'],'Preserving an edited closure actor')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f');backup=ROOT/'validation/release_upstairs_closure'/stamp;backup.mkdir(parents=True)
    shutil.copy2(map_file,backup/'Verdant_Desktop.before.umap')
    if previous:(backup/'previous_validation.json').write_text(json.dumps(previous,indent=2)+'\n')
    folder='/Game/Release/HomeClosure/V_'+manifest['file_sha256'][:12]
    options=unreal.FbxImportUI()
    for key,value in {'import_mesh':True,'import_as_skeletal':False,'import_materials':False,'import_textures':False,
        'automated_import_should_detect_type':False,'mesh_type_to_import':unreal.FBXImportType.FBXIT_STATIC_MESH}.items():options.set_editor_property(key,value)
    for key,value in {'combine_meshes':True,'transform_vertex_to_absolute':True,'convert_scene':True,'convert_scene_unit':True,
        'auto_generate_collision':False,'one_convex_hull_per_ucx':True,'generate_lightmap_u_vs':True,'build_nanite':False,
        'normal_import_method':unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS}.items():options.get_editor_property('static_mesh_import_data').set_editor_property(key,value)
    task=unreal.AssetImportTask()
    for key,value in {'filename':str(file),'destination_path':folder,'destination_name':manifest['mesh_name'],'automated':True,
        'replace_existing':False,'save':False,'factory':unreal.FbxFactory(),'options':options}.items():task.set_editor_property(key,value)
    art.ASSETS.import_asset_tasks([task]);mesh=unreal.load_asset(folder+'/'+manifest['mesh_name'])
    art.require(isinstance(mesh,unreal.StaticMesh) and mesh.get_num_triangles(0)==manifest['triangles'],'Native closure mesh/triangle mismatch')
    static=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    art.require(static.get_convex_collision_count(mesh)==7,'Native closure must have exactly7 visible-body UCX hulls')
    palette={'wood':'/Game/Harbor/Materials/M_Wood','plaster':'/Game/Harbor/Materials/M_Plaster','metal':'/Game/Opening/Materials/M_OpeningInk'}
    for index,slot in enumerate(mesh.get_editor_property('static_materials')):
        name=str(slot.get_editor_property('imported_material_slot_name')).lower()
        role=next((k for k in palette if k in name),None);art.require(role,'Unexpected closure slot '+name)
        mat=unreal.load_asset(palette[role]);art.require(mat,'Existing closure material missing '+role);mesh.set_material(index,mat)
    unreal.EditorAssetLibrary.set_metadata_tag(mesh,'TOSOY.Owner',plan['owner'])
    actor=matches[0] if previous else art.ACTORS.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(),unreal.Rotator())
    actor.set_actor_label('Home - closed upstairs stair enclosure')
    actor.set_editor_property('tags',[unreal.Name(plan['owner']),unreal.Name(plan['stable_id']),unreal.Name('Opening.Blocking')])
    actor.set_folder_path('Release/Home closure')
    comp=actor.get_component_by_class(unreal.StaticMeshComponent);comp.set_static_mesh(mesh);comp.set_collision_profile_name('BlockAll')
    comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS);actor.set_actor_enable_collision(True)
    origin,extent=actor.get_actor_bounds(False)
    # Exact proxy extents provide an independent native centimetre/unit check.
    expected_min=[min(s['bounds_ue_cm']['min'][i] for s in plan['blocking_visible_solids']) for i in range(3)]
    expected_max=[max(s['bounds_ue_cm']['max'][i] for s in plan['blocking_visible_solids']) for i in range(3)]
    actual_min,actual_max=art.xyz(origin-extent),art.xyz(origin+extent)
    art.require(all(abs(actual_min[i]-expected_min[i])<8 and abs(actual_max[i]-expected_max[i])<8 for i in range(3)),'Native closure bounds/unit mismatch')
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    ignored=[a for a in art.actors() if a!=actor]
    rays=[]
    for ray in plan['source_ray_intersection_checks']['rays']:
        hit=unreal.SystemLibrary.line_trace_single(world,unreal.Vector(*ray['from_cm']),unreal.Vector(*ray['to_cm']),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,ignored,unreal.DrawDebugTrace.NONE,True)
        result=hit.to_tuple() if hit is not None else None
        art.require(result is None or not result[0],'Closure blocks a required interaction ray '+ray['id']);rays.append({'id':ray['id'],'clear_of_closure':True})
    hulls=[]
    for solid in plan['blocking_visible_solids']:
        c=unreal.Vector(*solid['center_ue_cm']);axis=0 if solid['size_ue_cm'][0]<solid['size_ue_cm'][1] else 1
        delta=unreal.Vector(50 if axis==0 else 0,50 if axis==1 else 0,0)
        hit=unreal.SystemLibrary.line_trace_single(world,c-delta,c+delta,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,ignored,unreal.DrawDebugTrace.NONE,True)
        hit=hit.to_tuple() if hit is not None else None
        art.require(hit is not None and bool(hit[0]) and hit[9]==actor,'Visible solid has no native collision '+solid['id']);hulls.append({'id':solid['id'],'same_closure_hit':True})
    after=art.snapshot();art.require(set(after)==set(actors_before)|{actor.get_name()},'Unexpected scene actor change')
    art.require(all(after[n]==state for n,state in actors_before.items() if n!=actor.get_name()) and art.lighting()==lights and art.story_refs()==story,'Unrelated scene/light/story edit')
    if previous:
        prior=actors_before[actor.get_name()];current=after[actor.get_name()]
        art.require(all(prior[k]==current[k] for k in prior if k not in ['mesh','materials','raw_override_materials']),'Closure refresh changed its authored identity/transform/query policy')
    art.require(unreal.EditorAssetLibrary.save_loaded_asset(mesh) and art.LEVEL.save_current_level(),'Closure save failed')
    art.require(all(Path(p)==map_file or io.sha(p)==digest for p,digest in before_files.items()),'Unrelated asset/config/save edit')
    actor_name=actor.get_name()
    art.require(art.LEVEL.load_level('/Game/Quest/Maps/Verdant_Desktop'),'Cannot reload native closure')
    reloaded=next(a for a in art.actors() if a.actor_has_tag(plan['stable_id']))
    art.require(art.state(reloaded)==after[actor_name],'Closure saved readback differs')
    report={'success':True,'native_executed':True,'mesh':mesh.get_path_name(),'source_sha256':manifest['file_sha256'],
        'actor':after[actor_name],'visible_matched_convex_hulls':7,'actual_bounds_cm':[actual_min,actual_max],
        'required_interaction_rays':rays,'visible_collision_body_queries':hulls,'both_eras_common':True,'era_arrays_unchanged':True,
        'unrelated_existing_files_unchanged':True,'rollback':str(backup),'ordinary_capsule_bypass_tested':False,'visual_review_passed':False}
    report_file.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    try:main()
    except Exception:
        (ROOT/'release_upstairs_closure_failed.json').write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2));unreal.log_error(traceback.format_exc())
    unreal.SystemLibrary.quit_editor()
