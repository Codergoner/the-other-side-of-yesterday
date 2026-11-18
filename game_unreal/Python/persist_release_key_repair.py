"""Repeat49 SHA-proved pin edits and FORCE their native asset serialization.

No full6351-node snapshot is repeated. The previous complete comparison is
reused only when the exact original asset bytes and pinned proof still match;
all49 changed nodes and the13 guarded calls are checked again natively.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import opening_graph as og
import release_file_io as io
import release_mother_integration as shared

PRIOR=ROOT/'validation/release_key_literal_repair/20261026T043839_187851/report.json'
PRIOR_SHA='8db2fd1546e4c7380a141ef82a58e70a540faca2a68e0f11347842fbe953ec2b'
SNAPSHOT_SHA='4c7eabc39a7400c240a97ff151f77b3d22cd4163c35a902068db82fc9b666f5a'
REPORT=ROOT/'release_key_literal_persistence_report.json'


def load_proof():
    shared.require(ROOT.parent.name=='Release_20261026','Release copy required')
    shared.require(io.sha(PRIOR)==PRIOR_SHA,'Exact reviewed in-memory repair report changed')
    proof=json.loads(io.io_path(PRIOR).read_text())
    shared.require(proof['success'] and proof['run']=='20261026T043839_187851' and
        proof['changed_count']==47 and len(proof['photo_rotation_fixes'])==2 and
        proof['all_original_node_guids_preserved'] and proof['all_execution_and_unlisted_data_pins_preserved'] and
        proof['guarded_save_nodes_unchanged'],'Prior complete in-memory comparison proof is incomplete')
    snapshot_file=Path(proof['complete_node_snapshot_file'])
    shared.require(proof['complete_node_snapshot_sha256']==SNAPSHOT_SHA and io.sha(snapshot_file)==SNAPSHOT_SHA,
                   'Exact complete before/after snapshot proof changed')
    data=json.loads(io.io_path(snapshot_file).read_text())
    shared.require(len(data['before'])==len(data['after'])==proof['original_node_count']==6351,
                   'Reviewed complete comparison node count changed')
    return proof,data


def changes(proof,data):
    rows=[]
    for row in proof['changed_key_defaults']:
        rows.append({'node':row['node'],'pin':'Key','before':row['before'],'after':row['after'],'function':row['function']})
    for row in proof['photo_rotation_fixes']:
        rows.append({'node':row['node'],'pin':'DeltaRotation','before':row['before'],'after':row['after'],'function':row['function']})
    shared.require(len(rows)==49 and len({row['node'] for row in rows})==49,'Exact49 distinct reviewed data-default edits required')
    for row in rows:
        old=data['before'][row['node']];new=data['after'][row['node']]
        shared.require(old['guid']==new['guid'] and old['pins']['in:'+row['pin']]['value']==row['before'] and
            new['pins']['in:'+row['pin']]['value']==row['after'],'Reviewed individual pin proof is inconsistent')
        row['guid']=old['guid']
    return rows


def native_nodes(bp,data):
    nodes={node.get_path_name():node for graph in og.L.list_graphs(bp)
           for node in og.E.get_graph_editor(graph).list_all_nodes()}
    prefix=bp.get_path_name()+':'
    expected={path for path in data['before'] if path.startswith(prefix)}
    shared.require(set(nodes)==expected,'Original manager graph node set differs from the pinned complete proof')
    return nodes


def validate_targets(nodes,rows,data,audit,phase):
    output=[]
    for row in rows:
        node=nodes[row['node']]
        shared.require(audit.guid(node)==row['guid'],'Reviewed target GUID changed: '+row['node'])
        shared.require(audit.function(node)[1]==row['function'],'Reviewed target function changed')
        pins=audit.pins(node)
        shared.require(pins==data[phase][row['node']]['pins'],
                       'Actual49-node '+phase+' pin snapshot differs: '+row['node'])
        output.append({'node':row['node'],'guid':row['guid'],'pin':row['pin'],
                       'actual':pins['in:'+row['pin']]['value']})
    return output


def protected_files(excluded):
    paths=io.files(ROOT/'Content','*.uasset')+io.files(ROOT/'Content','*.umap')
    paths+=list((ROOT/'Config').glob('*.ini'))+list(ROOT.glob('*.uproject'))
    paths+=io.files(ROOT/'Saved/SaveGames','*.sav*')
    return {str(path):io.sha(path) for path in paths if path not in excluded}


def main():
    shared.require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseKeyPersistWrite'),
                   'Root serialized force-persistence writer grant required')
    shared.require(not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor(),
                   'Force persistence requires exited PIE')
    proof,data=load_proof();rows=changes(proof,data)
    file=shared.asset_file(ROOT,shared.MANAGER)
    old_sha=proof['owned_sha256_before'][str(file)]
    shared.require(proof['manager_asset_sha256']==old_sha and io.sha(file)==old_sha,
                   'Exact original unsaved asset bytes required; do not overwrite another edit')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    out=ROOT/'validation/release_key_literal_persistence'/stamp;out.mkdir(parents=True)
    archive=out/(file.name+'.before');archive.write_bytes(io.io_path(file).read_bytes())
    protected=protected_files({file})
    bp=unreal.load_asset(shared.MANAGER);audit=shared.GraphAudit(out/'node_exports')
    nodes=native_nodes(bp,data)
    before=validate_targets(nodes,rows,data,audit,'before')
    guards=audit.guarded_calls(bp)
    shared.require(guards==proof['guarded_save_calls_after'],'Original13 guarded save calls differ from the reviewed proof')
    for row in rows:
        pin=og.pin_in(nodes[row['node']],row['pin'])
        shared.require(str(og.P.get_pin_value(pin))==row['before'] and not list(og.P.list_connected_pins(pin)),
                       'Reviewed original data default changed before persistence')
        shared.require(og.P.set_pin_value(pin,row['after']),'Native reviewed data-default write refused')
        shared.require(str(og.P.get_pin_value(pin))==row['after'],'Native data default differs from reviewed after value')
    compiled=og.compile_all([bp],save=False)
    audit.cache.clear();nodes=native_nodes(bp,data)
    after=validate_targets(nodes,rows,data,audit,'after')
    guarded_after=audit.guarded_calls(bp)
    shared.require(guarded_after==guards,'Force-persistence retry changed a guarded save call')
    shared.require(all(io.sha(path)==digest for path,digest in protected.items()),'Unowned input changed before explicit save')
    # Pin setters do not reliably mark the package dirty in this engine build.
    # Force actual serialization instead of allowing the default dirty check.
    shared.require(unreal.EditorAssetLibrary.save_loaded_asset(bp,only_if_is_dirty=False),'Forced manager serialization failed')
    new_sha=io.sha(file)
    shared.require(new_sha!=old_sha,'Forced save did not change manager bytes; persistence is unproven')
    shared.require(all(io.sha(path)==digest for path,digest in protected.items()),'Unowned native/config/save input changed during save')
    result={'success':True,'native_executed':True,'run':stamp,'forced_save_only_if_is_dirty':False,
        'manager':shared.MANAGER,'manager_sha256_before':old_sha,'manager_asset_sha256':new_sha,
        'manager_bytes_actually_changed':True,'prior_report':str(PRIOR),'prior_report_sha256':PRIOR_SHA,
        'complete_prior_snapshot_sha256':SNAPSHOT_SHA,'prior_exact_baseline_bytes_matched':True,
        'prior_report_was_in_memory_only':True,
        'historical_claim_correction':'The old report success/saved_assets did not prove disk persistence: its manager SHA stayed equal to baseline. This forced-save report supersedes that persistence claim.',
        'whole_graph_comparison_repeated':False,
        'comparison_scope':'Relies explicitly on SHA-pinned complete6351-node comparison against identical original bytes; repeated native checks cover all49 exact changed nodes, unchanged manager node set and13 guarded save calls.',
        'reviewed_changes':rows,'native_targets_before':before,'native_targets_after':after,
        'guarded_save_nodes_unchanged':True,'guarded_save_calls_after':guarded_after,'compiled':compiled,
        'unowned_native_config_save_files_unchanged':True,'protected_file_count':len(protected),
        'protected_file_sha256':protected,'rollback_archive':str(archive),
        'fresh_process_reader_verified':False,'fresh_process_reader_required':True,
        'physical_keyboard_or_packaged_input_verified':False,'new_windows_build_required':True}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    REPORT.write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'release_key_literal_repair_status.json').write_text(json.dumps({
        'active_persistence_report':str(REPORT),'active_report_sha256':io.sha(REPORT),
        'superseded_report':str(PRIOR),'superseded_claim':'Saved native asset / persisted input fix',
        'superseded_report_retained_as':'SHA-pinned in-memory native parsing and complete graph-comparison proof only',
        'fresh_reader_required':True},indent=2)+'\n')


if __name__=='__main__':
    settings=unreal.get_default_object(unreal.load_class(None,'/Script/BlueprintGraph.BlueprintEditorSettings'))
    old=settings.get_editor_property('bEnableTypePromotion')
    try:settings.set_editor_property('bEnableTypePromotion',False);main()
    except Exception:
        (ROOT/'release_key_literal_persistence_failed.json').write_text(json.dumps({'success':False,
            'error':traceback.format_exc(),'policy':'Inspect archive after editor exit; no overwrite of loaded assets.'},indent=2)+'\n')
        unreal.log_error(traceback.format_exc())
    finally:settings.set_editor_property('bEnableTypePromotion',old)
    unreal.SystemLibrary.quit_editor()
