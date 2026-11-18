from pathlib import Path
import sys,json,traceback,unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import release_distant_ridges as ridges
import build_release_hero as hero
import release_file_io as io
try:
 hero.sha=io.sha
 hero.files=lambda:{str(p):io.sha(p) for p in io.files(ROOT/'Content','*.uasset')+io.files(ROOT/'Content','*.umap')+list((ROOT/'Config').glob('*.ini'))+list(ROOT.glob('*.uproject'))+io.files(ROOT/'Saved/SaveGames','*.sav')}
 ridges.sha=io.sha
 ridges.apply()
except Exception:
 (ROOT/'release_ridges_adoption_error.json').write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2));unreal.log_error(traceback.format_exc())
finally:unreal.SystemLibrary.quit_editor()
