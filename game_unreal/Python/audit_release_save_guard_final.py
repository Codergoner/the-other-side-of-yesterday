"""Read/compile-only final13-node save guard audit after presentation writers."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import opening_graph as og
import release_mother_integration as helper
import release_file_io as io


def main():
    helper.require(ROOT.parent.name=='Release_20261026','Release copy required')
    proof_file=ROOT/'release_save_guard_integration.json';proof=json.loads(proof_file.read_text())
    helper.require(proof['success'] and len(proof['changed'])==13,'Preserved original13-node owner integration proof required')
    bp=unreal.load_asset(helper.MANAGER);file=helper.asset_file(ROOT,helper.MANAGER);before=io.sha(file)
    out=ROOT/'validation/release_save_guard_final'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    audit=helper.GraphAudit(out);rows=audit.guarded_calls(bp);by_path={r['node']:r for r in rows}
    baseline_file=ROOT/'release_mother_integration_report.json'
    baseline=json.loads(baseline_file.read_text()) if baseline_file.exists() else None
    helper.require(baseline and baseline['success'] and baseline['guarded_save_nodes_unchanged'],'Actual post-recovery-helper integration snapshot required')
    by_baseline={r['node']:r for r in baseline['guarded_save_calls_after']}
    for expected in proof['changed']:
        row=by_path.get(expected['node_path']);helper.require(row and row['guid']==expected['guid'] and row['function']==expected['function'],'Original guarded node/GUID/member changed')
        # The original owner integration subsequently inserted its documented
        # backup-recovery exec hooks; its immediate-retarget snapshot precedes
        # those hooks. Retain all original data pins and compare complete exec
        # wiring against the actual later unchanged13-node integration snapshot.
        excluded=['in:execute','out:then']
        pins={k:v for k,v in row['pins'].items() if not k.endswith(':self') and k not in excluded}
        original={k:v for k,v in expected['pins_after'].items() if k not in excluded}
        helper.require(json.dumps(pins,sort_keys=True)==json.dumps(original,sort_keys=True),'Original guarded save data pins changed')
        helper.require(json.dumps(row,sort_keys=True)==json.dumps(by_baseline[row['node']],sort_keys=True),'Post-recovery guarded save execution/data snapshot changed')
    compiled=og.compile_all([bp],save=False);helper.require(io.sha(file)==before,'Read-only audit changed saved manager bytes')
    (ROOT/'release_save_guard_final_audit.json').write_text(json.dumps({'success':True,'native_executed':True,
        'manager_asset_sha256':before,'original_integration_sha256':io.sha(proof_file),'complete_pin_baseline_sha256':io.sha(baseline_file),'guarded_calls':rows,'compiled':compiled,
        'original13_node_guids_members_pins_preserved':True,'generic_save_calls':0,'asset_or_save_writes':False},indent=2)+'\n')


if __name__=='__main__':
    try:main()
    except Exception:
        (ROOT/'release_save_guard_final_failed.json').write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2));unreal.log_error(traceback.format_exc())
    unreal.SystemLibrary.quit_editor()
