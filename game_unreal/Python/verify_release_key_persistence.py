"""Fresh-editor, read-only verification of the actually force-saved49 defaults."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import persist_release_key_repair as persist
import release_file_io as io
import release_mother_integration as shared


def main():
    shared.require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseKeyPersistenceRead'),
                   'Root fresh-process read-only verification grant required')
    proof,data=persist.load_proof();rows=persist.changes(proof,data)
    report_path=persist.REPORT;saved=json.loads(report_path.read_text());report_sha=io.sha(report_path)
    shared.require(saved['success'] and saved['manager_bytes_actually_changed'] and
        saved['forced_save_only_if_is_dirty'] is False and saved['prior_report_sha256']==persist.PRIOR_SHA and
        saved['complete_prior_snapshot_sha256']==persist.SNAPSHOT_SHA,
        'Actual forced-save report required')
    file=shared.asset_file(ROOT,shared.MANAGER)
    shared.require(io.sha(file)==saved['manager_asset_sha256'] and
        saved['manager_asset_sha256']!=saved['manager_sha256_before'],'New saved manager bytes unavailable')
    protected=persist.protected_files(set())
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    out=ROOT/'validation/release_key_literal_persistence_read'/stamp;out.mkdir(parents=True)
    bp=unreal.load_asset(shared.MANAGER);audit=shared.GraphAudit(out/'node_exports')
    nodes=persist.native_nodes(bp,data)
    actual=persist.validate_targets(nodes,rows,data,audit,'after')
    guards=audit.guarded_calls(bp)
    shared.require(guards==saved['guarded_save_calls_after']==proof['guarded_save_calls_after'],
                   'Fresh reader found changed guarded save calls')
    shared.require(all(io.sha(path)==digest for path,digest in protected.items()) and io.sha(report_path)==report_sha,
                   'Read-only fresh load changed native/config/save bytes or the persistence report')
    result={'success':True,'native_executed':True,'run':stamp,'manager_asset_sha256':io.sha(file),
        'forced_persistence_report':str(report_path),'forced_persistence_report_sha256':report_sha,
        'fresh_process_reader_verified':True,'verified_key_defaults':47,'verified_photo_rotation_defaults':2,
        'all49_saved_values_and_guids_match_pinned_full_comparison':True,'native_targets_after_reload':actual,
        'guarded_save_nodes_unchanged':True,'guarded_save_calls_after':guards,
        'asset_config_or_save_writes':False,'protected_files_unchanged':True,
        'whole_graph_comparison_repeated':False,'prior_complete_snapshot_sha256':persist.SNAPSHOT_SHA,
        'physical_keyboard_or_packaged_input_verified':False,'new_windows_build_required':True}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    validation=ROOT/'release_key_literal_persistence_validation.json'
    validation.write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'release_key_literal_repair_status.json').write_text(json.dumps({
        'active_persistence_report':str(report_path),'active_report_sha256':report_sha,
        'fresh_reader_validation':str(validation),'fresh_reader_validation_sha256':io.sha(validation),
        'superseded_report':str(persist.PRIOR),'superseded_claim':'Old success/saved_assets proved persistence',
        'fresh_reader_required':False,'native_persistence_confirmed':True,
        'packaged_keyboard_verification_required':True},indent=2)+'\n')


if __name__=='__main__':
    try:main()
    except Exception:
        (ROOT/'release_key_literal_persistence_validation_failed.json').write_text(json.dumps({
            'success':False,'error':traceback.format_exc(),'asset_or_save_writes':False},indent=2)+'\n')
        unreal.log_error(traceback.format_exc())
    unreal.SystemLibrary.quit_editor()
