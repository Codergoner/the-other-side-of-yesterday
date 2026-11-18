"""SOURCE ONLY: queued additive action-SFX actor and success-edge hooks.

Never invokes a frontend/story generator or generic save function. Existing
producer nodes and GUIDs survive; only their execution edges receive owned
synchronous calls. The thirteen native SaveGuard calls are snapshotted and
must remain byte-for-byte equivalent in owner/GUID/pins. Native PCM/event QA
is required after authoring; this source has not been executed.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy
import hashlib
import json
import re
import sys
import traceback
import unreal

ROOT=Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/'Python'))
import opening_graph as og
import build_release_hero as hero
import build_opening_actions as base
import import_release_audio as ambient
import release_action_sfx_graph as sfx
import integrate_release_save_guard as audit
from release_frontend_graph import Flow, reset_function

PLAN_FILE=ROOT/'ContentData/release_action_sfx_plan.json'
REPORT=ROOT/'release_action_sfx_report.json'
OWNER='TOSOY.ReleaseActionSfxOwned'
STABLE='release.audio.action_sfx'
MANAGER='/Game/Opening/Blueprints/BP_OpeningActions'
HELPERS={'ReleasePlayActionCue','ReleaseSfxCaptureCalibration','ReleaseSfxCalibrationCue','ReleaseSfxCaptureDial','ReleaseSfxDialCue'}
META='Release.ActionSfx.Hooks'


def require(ok,message):
    if not ok:raise RuntimeError(message)


def read():return json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(data):REPORT.write_text(json.dumps(data,indent=2,default=str)+'\n',encoding='utf-8')


def sfx_actor_state(value):
    row=hero.base.state(value)
    rows=[]
    for comp in value.get_components_by_class(unreal.AudioComponent):
        item={'name':comp.get_name()}
        for key in ['sound','auto_activate','allow_spatialization','is_ui_sound','can_play_multiple_instances','volume_multiplier']:
            current=comp.get_editor_property(key)
            item[key]=current.get_path_name() if isinstance(current,unreal.Object) else current
        rows.append(item)
    row['action_audio_components']=sorted(rows,key=lambda x:x['name'])
    return row


def stable_pins(node):
    result=audit.pins(node)
    for direction,values in [('in',og.L.list_input_pins(node)),('out',og.L.list_output_pins(node))]:
        for pin in values:
            name=str(og.P.get_pin_name(pin));key=direction+':'+name
            if key not in result:continue
            value=og.P.get_pin_value(pin)
            if isinstance(value,unreal.Object):value=value.get_path_name()
            elif isinstance(value,(unreal.Color,unreal.LinearColor)):value={k:getattr(value,k) for k in ['r','g','b','a']}
            elif isinstance(value,unreal.Vector):value={k:getattr(value,k) for k in ['x','y','z']}
            elif isinstance(value,unreal.Rotator):value={k:getattr(value,k) for k in ['pitch','yaw','roll']}
            else:value=str(value)
            result[key]['value']=value
    return result


def nodes(bp,include_helpers=False):
    result={}
    for graph in og.L.list_graphs(bp):
        if not include_helpers and graph.get_name() in HELPERS:continue
        for node in og.E.get_graph_editor(graph).list_all_nodes():result[node.get_path_name()]=node
    return result


def graph_snapshot(bp):
    return {path:{'guid':audit.guid(node),'pins':stable_pins(node),'class':node.get_class().get_path_name()} for path,node in nodes(bp).items()}


def guards(bp):
    good,bad=[],[]
    for path,node in nodes(bp,True).items():
        parent,member=audit.reference(node)
        if member in audit.FUNCTIONS:
            row={'path':path,'guid':audit.guid(node),'owner':parent,'function':member,'pins':audit.pins(node)}
            (good if parent==audit.GUARD else bad).append(row)
    return {'native':sorted(good,key=lambda x:x['path']),'generic':bad}


def owned_helpers(bp):
    output={}
    for graph in og.L.list_graphs(bp):
        if graph.get_name() in HELPERS:
            output[graph.get_name()]={n.get_path_name():{'guid':audit.guid(n),'pins':stable_pins(n)} for n in og.E.get_graph_editor(graph).list_all_nodes()}
    return output


def producers(bp,plan):
    found={}
    for spec in plan['producers']:
        graph=og.L.find_graph(bp,spec['graph'])
        require(graph is not None,'Producer graph missing: '+spec['graph'])
        editor=og.E.get_graph_editor(graph)
        matches=[]
        for node in editor.list_all_nodes():
            title=re.sub(r'[\s_]','',str(og.L.get_node_title(node))).lower()
            if node.get_class().get_name()!='K2Node_VariableSet' or title!='set'+spec['variable'].lower():continue
            pin=og.pin_in(node,spec['variable'])
            if og.P.list_connected_pins(pin):continue
            if str(og.P.get_pin_value(pin)).strip().lower()==spec['literal']:matches.append(node)
        require(len(matches)==1,'Expected one exact successful producer '+spec['id']+', got'+str(len(matches)))
        found[spec['id']]=(og.Graph(bp,editor),matches[0])
    return found


def build_helpers(bp,actor_class):
    og.member(bp,'ReleaseSfxPriorCalibrated','bool',False)
    og.member(bp,'ReleaseSfxPriorEra','int',0)
    for name,args in [('ReleasePlayActionCue',{'CueName':'name'}),('ReleaseSfxCaptureCalibration',{}),
                      ('ReleaseSfxCalibrationCue',{}),('ReleaseSfxCaptureDial',{}),('ReleaseSfxDialCue',{})]:
        og.function(bp,name,inputs=args,reset=False)
    og.compile_bp(bp)
    f=Flow(reset_function(bp,'ReleasePlayActionCue',inputs={'CueName':'name'}))
    # This is an action callback, not a tick/load flag watcher. Session/menu
    # gating prevents an accidental authoring/boot invocation from sounding.
    valid,no=f.branch(f.and_(f.var('ReleaseSessionStarted'),f.not_(f.var('ReleaseMenuActive'))))
    found=valid.data(base.GS+'GetActorOfClass',ActorClass=actor_class)
    cast=valid.g.cast(actor_class,found);og.link(valid.cur,og.pin_in(cast))
    yes=Flow(valid.g,og.pin_out(cast));target=valid.g.cast_value(cast)
    owned,other=yes.branch(yes.tag(target,STABLE))
    owned.call(actor_class+':PlayCue',**{'self':target,'CueName':owned.g.input('CueName')})
    f=Flow(reset_function(bp,'ReleaseSfxCaptureCalibration'));f.set('ReleaseSfxPriorCalibrated',f.var('WatchCalibrated'))
    f=Flow(reset_function(bp,'ReleaseSfxCalibrationCue'))
    changed,same=f.branch(f.and_(f.not_(f.var('ReleaseSfxPriorCalibrated')),f.var('WatchCalibrated')))
    changed.own('ReleasePlayActionCue',CueName=unreal.Name('calibration'))
    f=Flow(reset_function(bp,'ReleaseSfxCaptureDial'));f.set('ReleaseSfxPriorEra',f.var('SelectedEra'))
    f=Flow(reset_function(bp,'ReleaseSfxDialCue'))
    changed,same=f.branch(f.and_(f.eq(f.var('Mode'),4),f.not_(f.eq(f.var('ReleaseSfxPriorEra'),f.var('SelectedEra')))))
    changed.own('ReleasePlayActionCue',CueName=unreal.Name('tick'))
    og.compile_bp(bp)


def splice(graph,node,when,helper,cue=None):
    edge=og.pin_in(node) if when=='before' else og.pin_out(node)
    peers=list(og.P.list_connected_pins(edge))
    require(bool(peers),'Producer '+when+' execution edge is unconnected')
    call=graph.call(base.CLASS+':'+helper,**({'CueName':unreal.Name(cue)} if cue else {}))
    og.P.break_pin_links(edge)
    if when=='before':
        for pin in peers:og.link(pin,og.pin_in(call))
        og.link(og.pin_out(call),edge)
    else:
        og.link(edge,og.pin_in(call))
        for pin in peers:og.link(og.pin_out(call),pin)
    return {'producer_path':node.get_path_name(),'producer_pin':str(og.P.get_pin_name(edge)),
            'when':when,'helper':helper,'cue':cue,'call_path':call.get_path_name(),'call_guid':audit.guid(call),
            'original_peers':[(og.P.get_owning_node(p).get_path_name(),str(og.P.get_pin_name(p))) for p in peers]}


def install():
    hero.guard()
    require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseActionSfxWrite'),'Root native queue and -ReleaseActionSfxWrite required')
    audit.OUT=ROOT/'validation/release_action_sfx_graphs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    audit.EXPORT_CACHE.clear()
    plan=json.loads(PLAN_FILE.read_text(encoding='utf-8'))
    require(plan['owner']==OWNER and plan['stable_id']==STABLE and plan['map']==hero.MAP,'Unexpected SFX scope')
    previous=read()
    for file,digest in previous.get('asset_fingerprints',{}).items():require(Path(file).is_file() and sha(file)==digest,'Preserve externally edited SFX asset')
    bp=unreal.load_asset(MANAGER)
    require(bp is not None,'Existing release manager is missing')
    before_guards=guards(bp)
    require(len(before_guards['native'])==13 and not before_guards['generic'],'Require all13 existing native guard owners; never reintroduce a generic save call')
    raw=unreal.EditorAssetLibrary.get_metadata_tag(bp,META)
    records=json.loads(raw) if raw else {}
    if records:
        require(previous.get('helpers_after')==owned_helpers(bp),'Preserve edited owned SFX helper body')
        current_nodes=nodes(bp)
        for record in records.values():
            call=current_nodes.get(record['call_path'])
            require(call is not None and audit.guid(call)==record['call_guid'] and stable_pins(call)==record.get('call_pins'),
                    'Preserve edited/missing producer hook or cue default')
    else:
        require(not owned_helpers(bp),'Preserve preexisting unowned helper names')
    targets=producers(bp,plan)  # Fail before authoring if success edges changed.
    before_nodes=graph_snapshot(bp)
    before_files=hero.files()
    baseline_file=previous.get('first_graph_baseline_file')
    if baseline_file:
        require(sha(baseline_file)==previous['first_graph_baseline_sha256'],'Original graph baseline changed')
    else:
        baseline_file=audit.OUT/'original_graph_nodes.json';baseline_file.parent.mkdir(parents=True,exist_ok=True)
        baseline_file.write_text(json.dumps(before_nodes,indent=2)+'\n',encoding='utf-8')
    previous.update(first_graph_baseline_file=str(baseline_file),first_graph_baseline_sha256=sha(baseline_file),
                    last_attempt_started=datetime.now(timezone.utc).isoformat())
    write(previous)
    require(hero.base.LEVEL.load_level(hero.MAP),'Cannot preflight the current Desktop map')
    current_sfx=[a for a in hero.base.actors() if a.actor_has_tag(STABLE)]
    require(len(current_sfx)<=1,'Multiple SFX actors; preserve scene')
    if current_sfx:
        require(current_sfx[0].actor_has_tag(OWNER) and not current_sfx[0].actor_has_tag('TOSOY.ManualOverride') and
                previous.get('actor_after')==sfx_actor_state(current_sfx[0]),'Preserve unowned or explicitly/inferred edited SFX actor before any manager write')
    manifest=ambient.source_manifest()
    audio=ambient.report_read()
    require(audio.get('success'),'Existing actual imported seven-wave package required')
    waves={}
    for role in ['SFX_WatchTick','SFX_CalibrationSuccess','SFX_SoftTransition','SFX_ClothInteraction']:
        asset=unreal.load_asset(audio['namespace']+'/Waves/'+role)
        require(isinstance(asset,unreal.SoundWave) and not asset.get_editor_property('looping'),'Existing finite SFX wave missing')
        ambient.verify_owned(asset,audio['signature'])
        waves[role]=asset
    version=hashlib.sha256((sha(Path(__file__))+sha(Path(sfx.__file__))+sha(PLAN_FILE)+json.dumps([(a['role'],a['sha256']) for a in manifest['assets']],sort_keys=True)).encode()).hexdigest()[:16]
    folder='/Game/Release/ActionSfx/V_'+version
    bp_package=folder+'/BP_ReleaseActionSfx'
    if current_sfx:
        require(current_sfx[0].get_class().get_path_name()==bp_package+'.BP_ReleaseActionSfx_C',
                'A SFX class-version upgrade requires a separately reviewed owned-actor replacement; manager is untouched')
    owned=unreal.load_asset(bp_package) if unreal.EditorAssetLibrary.does_asset_exist(bp_package) else None
    if owned:
        require(unreal.EditorAssetLibrary.get_metadata_tag(owned,'Release.ActionSfx.Owner')==OWNER,'Preserve unowned SFX Blueprint')
    else:
        owned=og.blueprint(bp_package,unreal.Actor);sfx.build(owned,waves)
        unreal.EditorAssetLibrary.set_metadata_tag(owned,'Release.ActionSfx.Owner',OWNER)
        unreal.EditorAssetLibrary.set_metadata_tag(owned,'Release.ActionSfx.Version',version)
        og.compile_bp(owned,save=True)
    actor_class=og.L.generated_class(owned).get_path_name()
    if not records or previous.get('version')!=version:
        build_helpers(bp,actor_class)
    if not records:
        for spec in plan['producers']:
            graph,node=targets[spec['id']]
            if spec.get('before_helper'):records[spec['id']+'.before']=splice(graph,node,'before',spec['before_helper'])
            records[spec['id']+'.after']=splice(graph,node,'after',spec.get('after_helper','ReleasePlayActionCue'),spec.get('cue'))
        unreal.EditorAssetLibrary.set_metadata_tag(bp,META,json.dumps(records,sort_keys=True))
    else:
        current=nodes(bp)
        for record in records.values():
            require(record['call_path'] in current and audit.guid(current[record['call_path']])==record['call_guid'],'Preserve missing/edited owned producer hook')
    og.compile_bp(bp)
    audit.EXPORT_CACHE.clear()
    after_nodes=graph_snapshot(bp)
    require(set(before_nodes).issubset(after_nodes),'An original node/function was removed')
    touched={(row['producer_path'],row['producer_pin']) for row in records.values()}
    touched.update((path,pin) for row in records.values() for path,pin in row['original_peers'])
    for path,row in before_nodes.items():
        actual=after_nodes[path]
        require(row['guid']==actual['guid'] and row['class']==actual['class'],'An original node identity changed')
        for key,pin in row['pins'].items():
            direction,name=key.split(':',1)
            if (path,name) in touched:
                require(actual['pins'].get(key,{}).get('value')==pin['value'],'An original hook-edge pin default changed')
                continue
            require(actual['pins'].get(key)==pin,'An original non-hook pin/default/link changed: '+path+' '+key)
    require(guards(bp)==before_guards,'One of13 native save-guard owners/GUIDs/pins changed')
    for record in records.values():record['call_pins']=stable_pins(nodes(bp)[record['call_path']])
    unreal.EditorAssetLibrary.set_metadata_tag(bp,META,json.dumps(records,sort_keys=True))
    og.compile_bp(bp,save=True)
    require(hero.base.LEVEL.load_level(hero.MAP),'Cannot open Desktop map for owned SFX actor')
    scene_before,lights,story=hero.base.snapshot(),hero.base.lighting(),hero.base.story_refs()
    matches=[a for a in hero.base.actors() if a.actor_has_tag(STABLE)]
    require(len(matches)<=1,'Multiple SFX actors; preserve scene for review')
    value=matches[0] if matches else None
    if value:
        require(value.actor_has_tag(OWNER) and not value.actor_has_tag('TOSOY.ManualOverride'),'Preserve unowned/manually tagged SFX actor')
        require(previous.get('actor_after')==sfx_actor_state(value),'Preserve inferred SFX actor edits')
        require(value.get_class().get_path_name()==actor_class,'SFX class upgrade requires a separately reviewed owned-actor replacement')
    else:
        value=hero.base.ACTORS.spawn_actor_from_class(og.L.generated_class(owned),unreal.Vector(),unreal.Rotator())
        value.set_editor_property('tags',[unreal.Name(OWNER),unreal.Name(STABLE),unreal.Name('Opening.Decorative')])
        value.set_actor_label('Release - quiet action SFX');value.set_folder_path('Release/Audio');value.set_actor_enable_collision(False)
    require(len(value.get_components_by_class(unreal.AudioComponent))==1,'Expected exactly one new non-autoplay action channel')
    channel=value.get_components_by_class(unreal.AudioComponent)[0]
    require(not channel.get_editor_property('auto_activate'),'SFX channel must not play on load')
    require(channel.get_editor_property('sound') is None,'SFX channel must be empty on saved boot')
    scene_after=hero.base.snapshot()
    require(all(scene_after.get(name)==row for name,row in scene_before.items()),'Existing scene/ambient actor changed')
    require(hero.base.lighting()==lights and hero.base.story_refs()==story,'SFX authoring changed story/era/light references')
    require(hero.base.LEVEL.save_current_level(),'Cannot save the new owned SFX actor')
    allowed={str(ROOT/'Content/Opening/Blueprints/BP_OpeningActions.uasset'),str(hero.MAP_FILE)}
    after_files=hero.files()
    require(all(after_files.get(path)==digest for path,digest in before_files.items() if path not in allowed),'Unrelated existing native asset/config/save changed')
    own_asset=ROOT/'Content'/(bp_package.removeprefix('/Game/')+'.uasset')
    result={'schema':1,'success':True,'version':version,'namespace':folder,'director_class':actor_class,
            'actor_after':sfx_actor_state(value),'hooks':records,'helpers_after':owned_helpers(bp),'guard_calls_before':before_guards,
            'all13_native_guard_calls_unchanged':True,'original_node_guids_preserved':True,'original_nonhook_pins_preserved':True,
            'existing_ambient_actor_components_untouched':True,'new_action_audio_components':1,'no_wavs_imported':True,
            'native_event_pcm_playtested':False,'cue_on_load_verified':False,'no_duplicate_cues_verified':False,
            'story_routes_retested':False,'asset_fingerprints':{str(own_asset):sha(own_asset)},
            'first_graph_baseline_file':str(baseline_file),'first_graph_baseline_sha256':sha(baseline_file),
            'scope':'Additive SFX Blueprint/actor and11 owned success-edge calls only; no frontend regeneration or save owners changed.'}
    write(result)
    return result


def uninstall():
    """Restore only owned execution splices; retain all imported/source assets."""
    hero.guard()
    require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseActionSfxWrite'),'Root native writer queue required for reversal')
    prior=read();bp=unreal.load_asset(MANAGER)
    require(prior.get('success') and not prior.get('reverted'),'No completed owned SFX installation to reverse')
    require(sha(prior['first_graph_baseline_file'])==prior['first_graph_baseline_sha256'],'Original graph baseline changed')
    require(owned_helpers(bp)==prior['helpers_after'],'Preserve edited SFX helper functions')
    raw=unreal.EditorAssetLibrary.get_metadata_tag(bp,META)
    records=json.loads(raw)
    require(records==prior['hooks'],'Preserve changed hook metadata')
    before_guards=guards(bp);before_files=hero.files()
    require(len(before_guards['native'])==13 and not before_guards['generic'],'Native guard owners changed; review before reversal')
    current=nodes(bp)
    for row in records.values():
        call=current.get(row['call_path'])
        require(call is not None and audit.guid(call)==row['call_guid'] and stable_pins(call)==row['call_pins'],'Preserve edited hook/cue wiring')
    for row in records.values():
        call=current[row['call_path']];producer=current[row['producer_path']]
        edge=og.pin_in(producer) if row['when']=='before' else og.pin_out(producer)
        og.P.break_pin_links(edge);og.P.break_pin_links(og.pin_in(call));og.P.break_pin_links(og.pin_out(call))
        for peer_path,peer_name in row['original_peers']:
            peer=current[peer_path]
            if row['when']=='before':og.link(og.pin_out(peer,peer_name),edge)
            else:og.link(edge,og.pin_in(peer,peer_name))
        og.E.get_graph_editor(call.get_outer()).remove_nodes([call])
    for name in HELPERS:
        graph=og.L.find_graph(bp,name)
        if graph:og.L.remove_function_graph(bp,name)
    unreal.EditorAssetLibrary.set_metadata_tag(bp,META,'')
    og.compile_bp(bp)
    audit.EXPORT_CACHE.clear()
    actual=graph_snapshot(bp)
    baseline=json.loads(Path(prior['first_graph_baseline_file']).read_text(encoding='utf-8'))
    require(all(actual.get(path)==row for path,row in baseline.items()),'Original graph did not restore exactly; map/manager remain unsaved')
    require(guards(bp)==before_guards,'Reversal changed a native guard call')
    require(hero.base.LEVEL.load_level(hero.MAP),'Cannot open SFX reversal map')
    scene_before,lights,story=hero.base.snapshot(),hero.base.lighting(),hero.base.story_refs()
    values=[a for a in hero.base.actors() if a.actor_has_tag(STABLE)]
    require(len(values)<=1,'Multiple SFX actors; preserve scene')
    removed=[];preserved=[]
    for value in values:
        if value.actor_has_tag(OWNER) and not value.actor_has_tag('TOSOY.ManualOverride') and sfx_actor_state(value)==prior['actor_after']:
            name=value.get_name();require(hero.base.ACTORS.destroy_actor(value),'Could not remove unchanged owned SFX actor');removed.append(name)
        else:preserved.append(value.get_name())
    after_scene=hero.base.snapshot()
    require(set(after_scene)==set(scene_before)-set(removed) and all(after_scene[name]==row for name,row in scene_before.items() if name not in removed),'Reversal changed another actor')
    require(hero.base.lighting()==lights and hero.base.story_refs()==story,'Reversal changed story/era/light references')
    og.compile_bp(bp,save=True)
    if removed:require(hero.base.LEVEL.save_current_level(),'Could not save owned SFX removal')
    allowed={str(ROOT/'Content/Opening/Blueprints/BP_OpeningActions.uasset'),str(hero.MAP_FILE)}
    after_files=hero.files()
    require(all(after_files.get(path)==digest for path,digest in before_files.items() if path not in allowed),'Reversal changed an unrelated native file')
    prior.update(reverted=True,revert_result={'restored_original_graph_nodes':True,'native_guard_calls_unchanged':True,
                 'removed_owned_actors':removed,'preserved_manual_actors':preserved,'assets_retained':True,
                 'two_inert_non_savegame_cache_variables_retained':True})
    write(prior)
    return prior


if __name__=='__main__':
    try:
        if unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'RevertReleaseActionSfx'):uninstall()
        else:install()
    except Exception:
        data=read();data.setdefault('failures',[]).append({'at':datetime.now(timezone.utc).isoformat(),'error':traceback.format_exc()});data['last_attempt_success']=False;write(data);raise
    finally:unreal.SystemLibrary.quit_editor()
