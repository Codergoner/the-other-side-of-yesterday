"""Serial new lower-skirt mesh import and unchanged short-step calibration."""
from pathlib import Path
import json,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import import_release_mother_rev9 as mother
import calibrate_release_mother_rev9 as calibration
report={'success':False,'completed':[]}
try:
    mother.main();report['completed'].append('Mother9 exact53-bone skeleton reuse and new native cloth mesh')
    calibration.main();report['completed'].append('Existing short-step clip compatibility and own actor-scale stance estimate')
    report['success']=True
except Exception:
    report['error']=traceback.format_exc();unreal.log_error(report['error'])
finally:
    (ROOT/'release_mother9_import_queue.json').write_text(json.dumps(report,indent=2)+'\n')
    unreal.SystemLibrary.quit_editor()
