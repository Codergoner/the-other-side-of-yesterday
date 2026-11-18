"""Finite serial native character import, own Neri bake and stance estimates."""
from pathlib import Path
import json,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import import_release_mother_rev6 as mother
import retarget_release_neri as neri
import calibrate_release_neri_walk as neri_rate

report={'success':False,'completed':[]}
try:
    mother.main();report['completed'].append('Mother REV6 new mesh / existing53-bone skeleton / compatible existing gait')
    neri.main();report['completed'].append('Neri own compatible walk bake')
    neri_rate.main();report['completed'].append('Neri actual stance-rate calibration')
    script=ROOT/'Python/calibrate_release_mother_walk.py'
    source=script.read_text().replace('release_mother_unit_retarget_report.json','release_mother_rev6_compatible_bake.json').replace('release_mother_walk_calibration','release_mother_rev6_walk_calibration')
    exec(compile(source,str(script),'exec'),{'__name__':'release_calibration_queued','__file__':str(script)})
    scope={'__name__':'release_calibration_queued','__file__':str(script)}
    exec(compile(source,str(script),'exec'),scope);scope['main']()
    report['completed'].append('Mother REV6 stance-rate calibration')
    report['success']=True
except Exception:
    report['error']=traceback.format_exc();unreal.log_error(report['error'])
finally:
    (ROOT/'release_character_queue_report.json').write_text(json.dumps(report,indent=2)+'\n')
    unreal.SystemLibrary.quit_editor()
