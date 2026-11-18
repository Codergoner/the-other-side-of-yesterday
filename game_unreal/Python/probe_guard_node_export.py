"""Read-only public editor export probe; writes QA text/report only."""
from pathlib import Path
import datetime,json,traceback
import unreal
root=Path(unreal.Paths.project_dir()).resolve()
out=root/'validation/guard_node_export_probe'/datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
out.mkdir(parents=True,exist_ok=True)
result={'success':False,'exports':[]}
try:
    bp=unreal.load_asset('/Game/Opening/Blueprints/BP_OpeningActions')
    for graph_name in ['ReleaseCheckContinue','LoadProgress']:
        graph=unreal.BlueprintEditorLibrary.find_graph(bp,graph_name)
        nodes=unreal.BlueprintGraphEditor.get_graph_editor(graph).list_all_nodes()
        chosen=[nodes[0]]+[n for n in nodes if 'loadgamefromslot' in str(unreal.BlueprintEditorLibrary.get_node_title(n)).replace(' ','').lower()][:1]
        for node in chosen:
            path=out/(graph_name+'_'+node.get_name()+'.t3d')
            task=unreal.AssetExportTask()
            for key,value in {'object':node,'exporter':unreal.ObjectExporterT3D(),'filename':str(path),
                              'automated':True,'prompt':False,'replace_identical':True,'selected':False}.items():
                task.set_editor_property(key,value)
            ok=unreal.Exporter.run_asset_export_task(task)
            text=path.read_text(encoding='utf-8-sig') if path.exists() else ''
            result['exports'].append({'node':node.get_name(),'class':node.get_class().get_name(),'ok':ok,'path':str(path),'text':text[:12000]})
    result['success']=all(x['ok'] for x in result['exports'])
except Exception:result['error']=traceback.format_exc()
(root/'guard_node_export_probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
unreal.SystemLibrary.quit_editor()
