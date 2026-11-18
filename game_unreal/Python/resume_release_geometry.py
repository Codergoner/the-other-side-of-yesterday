"""Resume only the failed unsaved geometry stage; Mother7 proofs stay intact."""
from pathlib import Path
import json,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import install_release_upstairs_closure as closure
import release_distant_ridges as ridges
import build_release_hero as hero
import release_file_io as io
report={'success':False,'completed':[]}
try:
    closure.main();report['completed'].append('Visible closure actual native7hulls,20clear interaction rays and saved readback')
    hero.sha=io.sha
    hero.files=lambda:{str(p):io.sha(p) for p in io.files(ROOT/'Content','*.uasset')+io.files(ROOT/'Content','*.umap')+list((ROOT/'Config').glob('*.ini'))+list(ROOT.glob('*.uproject'))+io.files(ROOT/'Saved/SaveGames','*.sav')}
    ridges.sha=io.sha;ridges.prepare();report['completed'].append('Distant ridges native prepare/readback; not adopted')
    report['success']=True
except Exception:
    report['error']=traceback.format_exc();unreal.log_error(report['error'])
finally:
    (ROOT/'release_geometry_resume_report.json').write_text(json.dumps(report,indent=2)+'\n')
    unreal.SystemLibrary.quit_editor()
