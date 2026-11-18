"""QUEUED native graph owner substitution after successful guard compilation.

Requires root activation of the compiled plugin, the14-field profile authoring
pass, and -ReleaseSaveGuardWrite. No plugin/config/map/save writes here. Original
story node objects/paths and changed save-node GUIDs are preserved; only3
save-library owners change. Private fields are inspected through public T3D
export, not protected-property access.
"""
from pathlib import Path
import hashlib
import json
import re
import sys
import traceback
import datetime
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(PROJECT / 'Python'))
import opening_graph as og
from release_frontend_graph import Flow, reset_function, MATH

MANAGER = '/Game/Opening/Blueprints/BP_OpeningActions'
GUARD = '/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary'
FUNCTIONS = {'LoadGameFromSlot', 'SaveGameToSlot', 'DoesSaveGameExist'}
REPORT = PROJECT / 'release_save_guard_integration.json'
OUT = PROJECT/'validation/save_guard_integration'/datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
EXPORT_CACHE = {}
EXPORT_SERIAL = 0


def require(ok, text):
    if not ok: raise RuntimeError(text)


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(node):return node.get_path_name()


def export_text(node):
    global EXPORT_SERIAL
    key=identity(node)
    if key not in EXPORT_CACHE:
        OUT.mkdir(parents=True,exist_ok=True)
        # Preserve every export without rescanning thousands of earlier exports
        # for every node. The serial is evidence naming only, never a node ID.
        while True:
            path=OUT/(hashlib.sha256(key.encode()).hexdigest()[:24]+'_'+str(EXPORT_SERIAL)+'.t3d')
            EXPORT_SERIAL += 1
            if not path.exists():break
        task=unreal.AssetExportTask()
        for name,value in {'object':node,'exporter':unreal.ObjectExporterT3D(),'filename':str(path),
                           'automated':True,'prompt':False,'replace_identical':True,'selected':False}.items():
            task.set_editor_property(name,value)
        require(unreal.Exporter.run_asset_export_task(task) and path.exists(),'Public node text export failed')
        raw=path.read_bytes()
        EXPORT_CACHE[key]=raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    return EXPORT_CACHE[key]


def guid(node):
    value=re.search(r'(?m)^\s*NodeGuid=([0-9A-Fa-f]{32})\s*$',export_text(node))
    require(value,'Serialized node GUID missing from public export')
    return value.group(1).upper()


def reference(node):
    if node.get_class().get_name() != 'K2Node_CallFunction': return None, None
    title=re.sub(r'\s+','',str(og.L.get_node_title(node))).lower()
    if not any(name.lower() in title for name in FUNCTIONS) and 'releaseguard' not in title:return None,None
    text=export_text(node)
    entry=re.search(r'(?m)^\s*FunctionReference=\(([^\r\n]*)\)',text)
    require(entry,'Targeted call node has no serialized function reference')
    member=re.search(r'MemberName="([^"]+)"',entry.group(1))
    parent=re.search(r'MemberParent="[^"\r\n]*\x27([^\x27]+)\x27"',entry.group(1))
    require(member,'Serialized function name missing')
    return (parent.group(1) if parent else None),member.group(1)


def pins(node):
    output = {}
    for direction, values in [('in', og.L.list_input_pins(node)), ('out', og.L.list_output_pins(node))]:
        for pin in values:
            name = str(og.P.get_pin_name(pin))
            if name == 'self': continue  # Library CDO owner intentionally changes.
            links = [[identity(og.P.get_owning_node(p)), str(og.P.get_pin_name(p))] for p in og.P.list_connected_pins(pin)]
            output[direction+':'+name] = {'value': str(og.P.get_pin_value(pin)), 'links': sorted(links)}
    return output


def main():
    require(PROJECT.parent.name == 'Release_20261026', 'Refusing protected project copies')
    require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseSaveGuardWrite'), 'Root serialized writer queue required')
    guard = unreal.load_class(None, GUARD)
    require(guard, 'Compiled/activated native SaveGuard is required; this writer never activates plugins')
    manager = unreal.load_asset(MANAGER)
    profile_class = unreal.load_class(None, '/Game/Release/Blueprints/BP_ReleaseProfile.BP_ReleaseProfile_C')
    require(manager and profile_class, 'Actual release manager/profile required')
    profile = unreal.get_default_object(profile_class)
    for name in ['MasterVolume','AmbienceVolume','MusicVolume','MuteWhenPaused']:
        profile.get_editor_property(name)  # Fail before edits if14-field native profile is not authored.
    own_file = PROJECT / 'Content/Opening/Blueprints/BP_OpeningActions.uasset'
    protected = list((PROJECT/'Content').rglob('*.uasset'))+list((PROJECT/'Content').rglob('*.umap'))
    protected += list((PROJECT/'Config').glob('*.ini'))+list(PROJECT.glob('*.uproject'))
    before_files = {str(p):sha(p) for p in protected if p != own_file}
    graphs = list(og.L.list_graphs(manager))
    own_helpers = {'ReleaseGuardProfileLoadCheck','ReleaseGuardCampaignLoadCheck','ReleaseGuardResetCampaignRecovery'}
    before_nodes = {graph.get_name(): {identity(n) for n in og.E.get_graph_editor(graph).list_all_nodes()} for graph in graphs
                    if graph.get_name() not in own_helpers}
    changed, occupied = [], []
    old_class = unreal.GameplayStatics.static_class()
    for graph in graphs:
        editor = og.E.get_graph_editor(graph)
        for node in editor.list_all_nodes():
            parent, member = reference(node)
            if member not in FUNCTIONS: continue
            if parent == GUARD:
                occupied.append({'graph':graph.get_name(),'guid':guid(node),'function':member})
                continue
            if parent != old_class.get_path_name(): continue
            previous = pins(node); previous_guid = guid(node)
            require(editor.retarget_node_class(node, old_class, guard), 'Library owner retarget failed')
            EXPORT_CACHE.pop(identity(node),None)
            require(reference(node) == (GUARD,member), 'Native function owner did not update')
            require(guid(node) == previous_guid and pins(node) == previous, 'Retarget changed a save node GUID/pin/default/link')
            changed.append({'graph':graph.get_name(),'node_path':identity(node),'guid':previous_guid,'function':member,
                            'pins_before':previous,'pins_after':pins(node)})
    require(changed or occupied, 'No reviewed save call nodes found')

    # A verified backup profile must remain read-only: its corrupt primary is
    # preserved by the guard, so New Game must not create a GUID campaign whose
    # profile pointer cannot be committed. This adds only a new owned helper.
    og.member(manager,'ReleaseGuardCampaignRecoveryBlocked','bool',False)
    helper = 'ReleaseGuardProfileLoadCheck'
    g = reset_function(manager, helper)
    f = Flow(g)
    state = f.data(GUARD + '.GetLastSaveGuardResult')
    value = f.data(MATH + 'Conv_ByteToInt', InByte=state)
    # Enum->byte compatibility is explicitly supported by UE5.8 K2 schema.
    # RecoveredBackup is1 in the compiled guard's versioned public enum.
    recovered, ordinary = f.branch(f.eq(value, 1))
    recovered.set('ReleaseProfileWritable', False)
    recovered.set('ReleaseMenuStatus', 'Verified profile backup loaded read-only. Existing damaged files are preserved; a separate recovery profile is required for New Game.')
    g = reset_function(manager,'ReleaseGuardResetCampaignRecovery')
    Flow(g).set('ReleaseGuardCampaignRecoveryBlocked',False)
    g = reset_function(manager,'ReleaseGuardCampaignLoadCheck')
    f = Flow(g)
    state = f.data(GUARD + '.GetLastSaveGuardResult')
    value = f.data(MATH + 'Conv_ByteToInt',InByte=state)
    recovered,ordinary = f.branch(f.eq(value,1))
    recovered.set('ReleaseGuardCampaignRecoveryBlocked',True)
    recovered.set('ReleaseCandidateValid',False)
    recovered.set('ReleaseContinueAvailable',False)
    recovered.set('ReleaseMenuStatus','The latest campaign file is damaged. A verified backup is preserved, but Continue cannot safely save to this file. New Game creates a separate playthrough.')
    og.compile_bp(manager)
    hooks = []
    for graph in og.L.list_graphs(manager):
        if graph.get_name() not in ['ReleaseReadProfile','ReleaseReadRecoveryProfile','ReleaseCheckContinue']: continue
        helper = 'ReleaseGuardCampaignLoadCheck' if graph.get_name()=='ReleaseCheckContinue' else 'ReleaseGuardProfileLoadCheck'
        editor = og.E.get_graph_editor(graph)
        for node in list(editor.list_all_nodes()):
            if reference(node) != (GUARD,'LoadGameFromSlot'): continue
            tail = og.pin_out(node)
            targets = list(og.P.list_connected_pins(tail))
            if any(reference(og.P.get_owning_node(p))[1] == helper for p in targets): continue
            og.P.break_pin_links(tail)
            call = editor.add_call_function_node('/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C:' + helper)
            og.link(tail, og.pin_in(call))
            for target in targets: og.link(og.pin_out(call), target)
            hooks.append({'graph':graph.get_name(),'load_guid':guid(node),'helper_guid':guid(call)})
    # Reset only at the start of each new candidate check. Capture the native
    # load result immediately after its load node; no later Exists/Save may
    # replace that evidence. A recovered candidate must not become valid again
    # when the original structural/state validator executes.
    graph = og.L.find_graph(manager,'ReleaseCheckContinue')
    g = og.Graph(manager,og.E.get_graph_editor(graph))
    targets=list(og.P.list_connected_pins(g.entry))
    if not any(reference(og.P.get_owning_node(p))[1]=='ReleaseGuardResetCampaignRecovery' for p in targets):
        og.P.break_pin_links(g.entry)
        call=g.call('/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C:ReleaseGuardResetCampaignRecovery')
        og.link(g.entry,og.pin_in(call))
        for target in targets:og.link(og.pin_out(call),target)
    graph=og.L.find_graph(manager,'ReleaseValidateCandidate')
    g=og.Graph(manager,og.E.get_graph_editor(graph))
    gate_guid=unreal.EditorAssetLibrary.get_metadata_tag(manager,'Release.SaveGuard.CandidateGateNodePath')
    nodes={identity(n):n for n in g.editor.list_all_nodes()}
    if gate_guid and gate_guid in nodes:
        require(any(identity(og.P.get_owning_node(p))==gate_guid for p in og.P.list_connected_pins(g.entry)), 'Existing guard validation gate was disconnected; preserve and review it')
    if not gate_guid or gate_guid not in nodes:
        targets=list(og.P.list_connected_pins(g.entry));og.P.break_pin_links(g.entry)
        f=Flow(g,g.entry)
        blocked,ordinary=f.branch(f.var('ReleaseGuardCampaignRecoveryBlocked'))
        new_gate_guid=identity(og.P.get_owning_node(blocked.cur))
        blocked.set('ReleaseCandidateValid',False)
        for target in targets:og.link(ordinary.cur,target)
        unreal.EditorAssetLibrary.set_metadata_tag(manager,'Release.SaveGuard.CandidateGateNodePath',new_gate_guid)
    compiled = og.compile_all([manager], save=False)
    for graph in og.L.list_graphs(manager):
        for node in og.E.get_graph_editor(graph).list_all_nodes():
            parent, member = reference(node)
            require(not (parent == old_class.get_path_name() and member in FUNCTIONS), 'Unsafe generic save call remains: '+graph.get_name())
    after_nodes = {graph.get_name(): {identity(n) for n in og.E.get_graph_editor(graph).list_all_nodes()} for graph in og.L.list_graphs(manager)}
    require(all(values.issubset(after_nodes[name]) for name,values in before_nodes.items()), 'Existing original node object/path was removed')
    require(unreal.EditorAssetLibrary.save_loaded_asset(manager), 'Guarded manager save failed')
    require(all(Path(p).exists() and sha(Path(p)) == digest for p,digest in before_files.items()), 'Unowned asset/map/config/plugin file changed')
    unreal.EditorAssetLibrary.set_metadata_tag(manager, 'Release.SaveGuard.Integrated', '1')
    # Metadata belongs to this manager; include it in the explicit save.
    require(unreal.EditorAssetLibrary.save_loaded_asset(manager), 'Guard metadata save failed')
    result = {'success':True,'compiled':compiled,'changed':changed,'already_guarded':occupied,'profile_backup_hooks':hooks,
              'all_original_node_objects_paths_preserved':True,'changed_save_node_guids_preserved':True,
              'all_internal_node_guids_directly_inspected':False,'save_node_pins_defaults_links_preserved':True,
              'protected_files_unchanged':True,'maps_saved':False,'saves_written':False,'plugin_activated_by_script':False,
              'runtime_or_packaged_fault_tested':False,
              'campaign_backup_policy':'Continue blocked with an explanation; structural validation cannot override rejection; separate New Game remains available when its profile is writable.',
              'profile_backup_policy':'Verified backup may be read but its corrupt primary index remains nonwritable; New Game is blocked to prevent unreachable campaigns.',
              'warning':'Run this after the final frontend graph writer; regenerating frontend functions can reintroduce generic calls and requires this owner audit again.'}
    result['manager_asset_sha256']=sha(own_file)
    result['public_node_export_directory']=str(OUT)
    (OUT/'node_objects_before_after.json').write_text(json.dumps({'before':{k:sorted(v) for k,v in before_nodes.items()},'after':{k:sorted(v) for k,v in after_nodes.items()}},indent=2),encoding='utf-8')
    REPORT.write_text(json.dumps(result,indent=2),encoding='utf-8')
    (OUT/'integration.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__ == '__main__':
    settings=unreal.get_default_object(unreal.load_class(None,'/Script/BlueprintGraph.BlueprintEditorSettings'))
    promotion=settings.get_editor_property('bEnableTypePromotion')
    try:
        settings.set_editor_property('bEnableTypePromotion',False)
        main()
    except Exception:
        REPORT.write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2),encoding='utf-8')
        unreal.log_error(traceback.format_exc())
    finally:settings.set_editor_property('bEnableTypePromotion',promotion)
    unreal.SystemLibrary.quit_editor()
