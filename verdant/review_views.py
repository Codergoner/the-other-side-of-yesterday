"""Writes output/verdant/capture_job.json: the fixed review cameras, eye height 1.62 m, both eras.

    blender --background --python review_views.py -- [label] [view ids...]
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verdant_plan as plan

EYE = 1.62
VIEWS = {
    'HomeFront': dict(pos=(-1.6, -14.6, plan.street_z(-14.6) + EYE), target=(-6.6, -11.5, plan.street_z(-13) + 2.6), fov=74),
    'UphillCathedral': dict(pos=(0.4, -21, plan.street_z(-21) + EYE), target=(1.5, 52, 30), fov=74),
    'HarborOverlook': dict(pos=(1.0, 7.0, plan.street_z(7.0) + EYE), target=(44, 26, 5.5), fov=80),
    'MarketSquare': dict(pos=(-13.2, 6.4, plan.SQUARE_Z + EYE), target=(-33, 9.5, 13.2), fov=78),
    'ClinicCourtyard': dict(pos=(-4.8, -0.6, plan.street_z(-4) + EYE), target=(-8.6, -5.2, plan.street_z(-4) + 2.4), fov=76),
    'QuayLighthouse': dict(pos=(14.2, 7.5, 1.2 + EYE), target=(50, 28, 5), fov=78),
    'PlazaCathedral': dict(pos=(1.2, 37.5, 14.76 + EYE), target=(9, 60, 38), fov=84),
    'Portal': dict(pos=(20, 52.6, 25 + EYE), target=(11, 55.5, 29), fov=74),
    'SideLane': dict(pos=(-18.6, -1.5, plan.SQUARE_Z + EYE), target=(-18.7, -17, 10.5), fov=74),
}
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
label = args[0] if args else 'review'
chosen = args[1:] or list(VIEWS)
views = []
for era in ('Past', 'Present'):
    for key in chosen:
        views.append({'id': key, 'era': era, **VIEWS[key]})
job = {'map': '/Game/Verdant/Maps/Verdant_City', 'label': label, 'warmup_seconds': 40, 'settle_frames': 30, 'width': 1600, 'height': 900,
       'views': views, 'measure_frames': 60}
(HERE.parent / 'output' / 'verdant' / 'capture_job.json').write_text(json.dumps(job, indent=1), encoding='utf-8')
print('CAPTURE JOB', label, len(views), 'views', flush=True)
