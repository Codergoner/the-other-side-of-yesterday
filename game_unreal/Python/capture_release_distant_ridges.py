"""Queued fixed-view current-vs-ridge editor captures; no map/asset saves."""
from pathlib import Path
import json
import sys
import traceback
import unreal

ROOT=Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/'Python'))
import release_distant_ridges as ridges
import capture_release_art as review

VIEWS=[{'id':'StreetFloor','xy':[0,400],'ground':'street','target':[0,-900,1080],'fov':78},
       {'id':'HarborVista','xy':[0,-700],'ground':'street','target':[4800,-2600,650],'fov':78}]


class Capture(review.Capture):
    def __init__(self):
        self.ridge=ridges.ready()
        self.original=None
        review.VIEWS=VIEWS
        super().__init__()
        self.folder=ROOT/'validation/release_distant_ridges_capture'/self.stamp
        self.folder.mkdir(parents=True,exist_ok=False)
        self.report_path=ridges.CAPTURE
        self.report.update(scope=__doc__,ridge_signature=self.ridge['signature'],
                           original_actor='StaticMeshActor_195',new_scene_actors=0,
                           profile_policy='Saved desktop lighting; only the existing distant actor mesh changes transiently',
                           visual_accepted=False)
        self.groups=[{'label':'Before','map':ridges.MAP,'era':'Present','jobs':[(view,'Lit') for view in VIEWS]},
                     {'label':'After','map':ridges.MAP,'era':'Present','jobs':[(view,'Lit') for view in VIEWS]+[(VIEWS[0],'BaseColor')]}]

    def apply_era_preview(self,era):
        value=ridges.actor()
        current=ridges.base.lighting()
        if self.saved_lights is None:self.saved_lights=current
        ridges.require(current==self.saved_lights,'Saved lighting differs between ridge views')
        ridges.require(ridges.preserve_reason(value,self.ridge) is None,'Preserve manually edited distant actor')
        before=ridges.state(value)
        if self.original is None:self.original=before
        ridges.require(before==self.original,'Current saved distant actor changed across pairs')
        if self.groups[self.group_index]['label']=='After':
            value.get_component_by_class(unreal.StaticMeshComponent).set_static_mesh(ridges.base.load(self.ridge['mesh_path']))
            after=ridges.state(value)
            ridges.require(all(before[k]==after[k] for k in before if k!='mesh'),'Ridge preview changed collision/transform/material/visibility')
        return True

    def finish(self,error=None):
        try:
            if self.original:
                # Discard the whole unsaved preview, not just its mesh pointer.
                # Native SetStaticMesh may leave editor component state pending
                # across its render-proxy rebuild. Reload verifies the actual
                # saved actor and keeps all protected map bytes unchanged.
                self.restore_world()
                ridges.require(self.level.load_level(ridges.MAP),'Could not reload saved ridge preview map')
                value=ridges.actor()
                self.report['distant_actor_restored_readback']=ridges.state(value)
                ridges.require(ridges.state(value)==self.original,'Saved ridge actor did not restore on reload')
            self.report['original_distant_actor_restored']=True
        except Exception:error=error or traceback.format_exc()
        super().finish(error)


if __name__=='__main__':
    session=None
    try:session=Capture();session.start()
    except Exception:
        if session:session.finish(traceback.format_exc())
        else:
            ridges.CAPTURE.write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2),encoding='utf-8')
            unreal.SystemLibrary.quit_editor()
