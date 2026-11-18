"""Serial root-owned Mother7 import/calibration and bounded geometry preparation."""
from pathlib import Path
import json,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import import_release_mother_rev7 as mother
import install_release_upstairs_closure as closure
import release_distant_ridges as ridges
import build_release_hero as hero
import release_file_io as io
report={'success':False,'completed':[]}
try:
    mother.main();report['completed'].append('Mother7 native import on existing skeleton / compatible clip data')
    path=ROOT/'Python/calibrate_release_mother_walk.py'
    source=path.read_text().replace('release_mother_unit_retarget_report.json','release_mother_rev7_compatible_bake.json').replace('release_mother_walk_calibration','release_mother_rev7_walk_calibration')
    scope={'__name__':'release_calibration_queued','__file__':str(path)};exec(compile(source,str(path),'exec'),scope);scope['main']()
    report['completed'].append('Mother7 stance calibration')
    closure.main();report['completed'].append('Visible closure native import/readback and7hull/20ray checks')
    hero.sha=io.sha
    hero.files=lambda:{str(p):io.sha(p) for p in io.files(ROOT/'Content','*.uasset')+io.files(ROOT/'Content','*.umap')+list((ROOT/'Config').glob('*.ini'))+list(ROOT.glob('*.uproject'))+io.files(ROOT/'Saved/SaveGames','*.sav')}
    ridges.sha=io.sha;ridges.prepare();report['completed'].append('Distant ridges native prepare/readback; not adopted')
    report['success']=True
except Exception:
    report['error']=traceback.format_exc();unreal.log_error(report['error'])
finally:
    (ROOT/'release_geometry_char7_queue.json').write_text(json.dumps(report,indent=2)+'\n')
    unreal.SystemLibrary.quit_editor()
