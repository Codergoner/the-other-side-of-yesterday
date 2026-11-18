"""Native isolated Healer/Sela listening/blink review; no story or asset save."""
from pathlib import Path
import json,re,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();SOURCE=Path(__file__).resolve()
sys.path.insert(0,str(ROOT/'Python'))
import capture_release_character_pie as base
import capture_release_character_review as review
import release_file_io as io

review.sha=io.sha
review.native_files=lambda:{str(p):io.sha(p) for p in io.files(ROOT/'Content','*.uasset')+io.files(ROOT/'Content','*.umap')+list((ROOT/'Config').glob('*.ini'))+list(ROOT.glob('*.uproject'))}


class RoleReview(base.PIEReview):
    def __init__(self):
        super().__init__()
        match=re.search(r'-ReleaseRole=(Healer|Sela|Neri)',unreal.SystemLibrary.get_command_line())
        review.require(match,'Exact Healer or Sela role flag required')
        self.role=match.group(1)
        path=ROOT/('release_'+self.role.lower()+'_import_report.json')
        candidate=json.loads(path.read_text())
        review.require(candidate['success'] and candidate['native_executed'] and candidate['character']==self.role,'Matching native role import required')
        for p,digest in candidate['owned_asset_sha256'].items():review.require(io.sha(p)==digest,'Candidate native asset changed')
        self.imported=candidate
        self.folder=ROOT/'validation/release_role_listening'/self.role/self.run
        self.folder.mkdir(parents=True)
        self.source_path,self.source_sha=SOURCE,io.sha(SOURCE)
        self.report.update(character=self.role,map=candidate['map'],mesh=candidate['mesh'],animation=candidate['animation'],
            import_report_sha256=io.sha(path),scope='Isolated native PIE ticking listening and visible open/blink samples; no story swap or package/performance claim.')
        self.jobs=[{'id':'Listening_t'+str(t),'time':t,'view':'full'} for t in range(4)]+[
            {'id':'FaceOpen','blink':0.0,'view':'face'},{'id':'FaceBlink','blink':1.0,'view':'face'}]

    def write(self):
        if not hasattr(self,'role'):return super().write()
        text=json.dumps(self.report,indent=2)+'\n'
        (self.folder/'capture_report.json').write_text(text)
        (ROOT/('release_'+self.role.lower()+'_listening_review.json')).write_text(text)


if __name__=='__main__':
    try:
        session=RoleReview();session.start()
    except Exception:
        (ROOT/'release_role_listening_setup_failed.json').write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2))
        unreal.SystemLibrary.quit_editor()
