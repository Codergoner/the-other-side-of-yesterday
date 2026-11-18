"""Serial root-owned floor palette, photo and credit instance authoring."""
from pathlib import Path
import sys,json,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/'Python'))
import release_file_io as io
import build_release_hero as hero
import prepare_release_floor_tints as floors
import import_release_family_photo as photo
import update_release_credits as credits

report={'success':False,'completed':[]}
try:
    hero.sha=io.sha
    hero.files=lambda:{str(p):io.sha(p) for p in io.files(ROOT/'Content','*.uasset')+io.files(ROOT/'Content','*.umap')+list((ROOT/'Config').glob('*.ini'))+list(ROOT.glob('*.uproject'))+io.files(ROOT/'Saved/SaveGames','*.sav')}
    floors.prepare()
    floors.adopt()
    report['completed'].append('Warm01 persistent palette / native readback')
    photo.main()
    report['completed'].append('Family photograph native prop and inspection references')
    credits.main()
    report['completed'].append('Desktop credits native instance readback')
    report['success']=True
except Exception:
    report['error']=traceback.format_exc();unreal.log_error(report['error'])
finally:
    (ROOT/'release_surface_photo_queue.json').write_text(json.dumps(report,indent=2)+'\n')
    unreal.SystemLibrary.quit_editor()
