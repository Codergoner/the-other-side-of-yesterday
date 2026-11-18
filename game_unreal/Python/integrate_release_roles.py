"""Same-actor Healer/Sela/Neri integration after actual reviewed native renders.

No map generator, story regeneration, path/speed/save-schema change. Own human
idle/walk assets and query physics replace only the existing role components.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import opening_graph as og
import release_mother_integration as shared
import release_role_integration as roles
import release_neri_locomotion as locomotion
import release_file_io as io
from release_frontend_graph import Flow,reset_function,MATH


def static_facing(bp,role):
    for name,kind,value in [('UseHumanFacing','bool',False),('AuthoredHumanWorldRotation',og.struct_type('rotator'),og.UNSET)]:
        og.member(bp,role+name,kind,value,instance_editable=True)
    name='Release'+role+'Face';g=reset_function(bp,name,inputs={'DeltaSeconds':'real'});f=Flow(g)
    enabled=f.and_(f.var(role+'UseHumanFacing'),f.and_(f.eq(f.var('EraIndex'),1),f.var('ReleaseSessionStarted')))
    f,_=f.branch(enabled);f,_=f.branch(f.valid(f.var(role+'Actor')))
    partner=f.data(MATH+'EqualEqual_ObjectObject',A=f.var('DialoguePartnerActor'),B=f.var(role+'Actor'))
    active=f.and_(f.var('DialogueActive'),partner)
    here=f.data('/Script/Engine.Actor.K2_GetActorLocation',**{'self':f.var(role+'Actor')})
    player=f.data('/Script/Engine.Actor.K2_GetActorLocation',**{'self':f.var('Player')})
    direction=f.data(MATH+'Subtract_VectorVector',A=player,B=here)
    flat=f.data(MATH+'ProjectVectorOnToPlane',V=direction,PlaneNormal=unreal.Vector(0,0,1))
    look=f.data(MATH+'MakeRotFromYZ',Y=flat,Z=f.data(MATH+'MakeVector',X=0.0,Y=0.0,Z=1.0))
    desired=f.data(MATH+'SelectRotator',A=look,B=f.var(role+'AuthoredHumanWorldRotation'),bPickA=active)
    current=f.data('/Script/Engine.Actor.K2_GetActorRotation',**{'self':f.var(role+'Actor')})
    bounded=f.data(MATH+'RInterpTo_Constant',Current=current,Target=desired,DeltaTime=g.input('DeltaSeconds'),InterpSpeed=180.0)
    f.call('/Script/Engine.Actor.K2_SetActorRotation',**{'self':f.var(role+'Actor'),'NewRotation':bounded,'bTeleportPhysics':False})


def main():
    shared.require(ROOT.parent.name=='Release_20261026' and unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseRolesWrite'),'Root native role writer queue required')
    approved=json.loads((ROOT/'release_roles_visual_approval.json').read_text())
    imports={}
    for role in roles.ROLES:
        entry=approved['roles'][role];p=ROOT/entry['render_report']
        shared.require(entry['approved'] and io.sha(p)==entry['render_report_sha256'],'Actual reviewed role renders required')
        render=json.loads(p.read_text());shared.require(render['success'] and len(render['images'])>=6,'Complete native role captures required')
        imports[role]=json.loads((ROOT/('release_'+role.lower()+'_import_report.json')).read_text())
    bake=json.loads((ROOT/'release_neri_retarget_report.json').read_text());rate=json.loads((ROOT/'release_neri_walk_calibration.json').read_text())
    shared.require(bake['success'] and rate['success'] and rate['retarget_report_sha256']==io.sha(ROOT/'release_neri_retarget_report.json'),'Own Neri walk/calibration proof required')
    level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    shared.require(not level.is_in_play_in_editor() and level.load_level('/Game/Quest/Maps/Verdant_Desktop'),'Saved desktop map outsidePIE required')
    manager=next(a for a in actors.get_all_level_actors() if a.actor_has_tag('Opening.Manager'));manager_name=manager.get_name()
    bp=unreal.load_asset(shared.MANAGER);map_file=ROOT/'Content/Quest/Maps/Verdant_Desktop.umap';bp_file=shared.asset_file(ROOT,shared.MANAGER)
    before={str(p):io.sha(p) for p in io.files(ROOT/'Content','*.uasset')+io.files(ROOT/'Content','*.umap')+list((ROOT/'Config').glob('*.ini'))+io.files(ROOT/'Saved/SaveGames','*.sav') if p not in [map_file,bp_file]}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f');out=ROOT/'validation/release_roles_integration'/stamp;out.mkdir(parents=True)
    for file in [map_file,bp_file]:(out/(file.name+'.before')).write_bytes(file.read_bytes())
    audit=shared.GraphAudit(out/'node_exports');save_before=audit.guarded_calls(bp)
    from integrate_release_mother import references,map_actor_identity
    refs=references(manager);identities=map_actor_identity(actors.get_all_level_actors());world=editor.get_editor_world()
    fallback={key:manager.get_editor_property(key) for key in ['IdleAnimation','WalkAnimation']}
    headings={};evidence=[];physics=[]
    for role in roles.ROLES:
        actor=manager.get_editor_property(role+'Actor');rot=actor.get_actor_rotation()
        headings[role]=unreal.Rotator(pitch=0,yaw=rot.yaw-90,roll=0)
        mesh=unreal.load_asset(imports[role]['mesh']);asset,proof=shared.create_query_physics(mesh,'TOSOY.Release'+role+'Integration')
        _,_,_,stage=roles.stage_candidate(world,manager,role,imports[role],asset)
        physics.append(asset);evidence.append(dict(stage,physics=proof))
    changes=roles.patch_neri_animation_values(bp,audit,fallback);hooks=locomotion.patch_runtime(bp,audit,changes)
    for role in ['Healer','Sela']:static_facing(bp,role)
    og.compile_bp(bp)
    graph=og.L.find_graph(bp,'NpcTick');g=og.Graph(bp,og.E.get_graph_editor(graph));targets=list(og.P.list_connected_pins(g.entry));og.P.break_pin_links(g.entry);tail=g.entry
    for role in ['Healer','Sela']:
        call=g.call(shared.MANAGER+'.BP_OpeningActions_C:Release'+role+'Face');og.link(tail,og.pin_in(call));og.link(g.input('DeltaSeconds'),og.pin_in(call,'DeltaSeconds'));tail=og.pin_out(call)
    for pin in targets:og.link(tail,pin)
    compiled=og.compile_all([bp],save=False)
    manager=next(a for a in actors.get_all_level_actors() if a.get_name()==manager_name and a.actor_has_tag('Opening.Manager'))
    for role in ['Healer','Sela']:
        manager.set_editor_property(role+'UseHumanFacing',True);manager.set_editor_property(role+'AuthoredHumanWorldRotation',headings[role])
    for name,value in {'NeriIdleAnimation':unreal.load_asset(imports['Neri']['animation']),'NeriWalkAnimation':unreal.load_asset(bake['baked']['walk']),
        'NeriWalkPlayRate':rate['recommended_play_rate'],'NeriUseHumanLocomotion':True,'NeriTurnSpeedDegrees':180.0,
        'NeriAuthoredHumanWorldRotation':headings['Neri']}.items():manager.set_editor_property(name,value)
    shared.require(references(manager)==refs and map_actor_identity(actors.get_all_level_actors())==identities,'Existing actor transforms/refs/identity changed')
    audit.cache.clear();shared.require(audit.guarded_calls(bp)==save_before,'Guarded save nodes changed')
    for asset in physics:shared.require(unreal.EditorAssetLibrary.save_loaded_asset(asset),'New owned query physics save failed')
    shared.require(unreal.EditorAssetLibrary.save_loaded_asset(bp) and level.save_current_level(),'Role integration save failed')
    shared.require(all(io.sha(p)==digest for p,digest in before.items()),'Unrelated existing asset/config/save changed')
    (ROOT/'release_roles_integration_report.json').write_text(json.dumps({'success':True,'native_executed':True,'roles':evidence,
        'neri_animation_pins':changes,'neri_runtime_hooks':hooks,'compiled':compiled,'guarded_save_nodes_unchanged':True,
        'existing_authored_paths_speeds_transforms_refs_preserved':True,'unrelated_existing_files_unchanged':True,
        'manager_asset_sha256':io.sha(bp_file),'map_asset_sha256':io.sha(map_file),'rollback':str(out),
        'actual_story_or_packaged_tested':False},indent=2)+'\n')


if __name__=='__main__':
    settings=unreal.get_default_object(unreal.load_class(None,'/Script/BlueprintGraph.BlueprintEditorSettings'));old=settings.get_editor_property('bEnableTypePromotion')
    try:settings.set_editor_property('bEnableTypePromotion',False);main()
    except Exception:
        (ROOT/'release_roles_integration_failed.json').write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2));unreal.log_error(traceback.format_exc())
    finally:settings.set_editor_property('bEnableTypePromotion',old)
    unreal.SystemLibrary.quit_editor()
