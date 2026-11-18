"""Writes output/verdant/capture_job.json for the five art-gate views of the release prompt on the
story map (living-room conversation, home frontage, uphill cathedral road, clinic courtyard, harbour
overlook), at player eye height (1.62 m above the floor the player stands on), in both eras.

    blender --background --python story_views.py -- [label]

Positions are Blender metres (Unreal = 100X, -100Y, 100Z). The era is applied through the story's own
Opening.PastOnly / Opening.PresentOnly tags (era_mode 'story' in verdant_capture.py); the capture uses
the map's own exposure volume.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verdant_plan as plan

EYE = 1.62
HOME_FLOOR = 10.11     # the family home's floor and porch (Unreal 1011 cm)
LANDING = 11.6         # the harbour stair landing, the story's overlook waypoint (450, -1400, 1160)
VIEWS = {
    'LivingRoom': dict(pos=(-5.6, -12.4, HOME_FLOOR + EYE), target=(-9.15, -14.12, HOME_FLOOR + 1.35), fov=74,
                       note='player at the New Game start looking at Mother'),
    'HomeFront': dict(pos=(0.6, -16.0, plan.street_z(-16.0) + EYE), target=(-5.0, -12.0, HOME_FLOOR + 1.6), fov=76,
                      note='on the road south of the gate looking at the porch, door and collapsed wing'),
    'UphillCathedral': dict(pos=(0.4, -21.0, plan.street_z(-21.0) + EYE), target=(1.5, 52.0, 30.0), fov=74,
                            note='on the road looking uphill to the campanile and cathedral'),
    'ClinicCourtyard': dict(pos=(-0.6, -1.0, plan.street_z(-1.0) + EYE), target=(-6.8, -4.6, plan.street_z(-4.0) + 1.3), fov=76,
                            note='on the road looking into the clinic court and awning frame'),
    'HarborOverlook': dict(pos=(4.5, 14.0, LANDING + EYE), target=(44.0, 26.0, 5.5), fov=80,
                           note='on the stair landing (story overlook waypoint) looking at the harbour and lighthouse'),
}
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
label = args[0] if args else 'story_artgate'
views = [{'id': key, 'era': era, **VIEWS[key]} for era in ('Past', 'Present') for key in VIEWS]
job = {'map': '/Game/Quest/Maps/Verdant_Desktop', 'label': label, 'era_mode': 'story', 'warmup_seconds': 40, 'settle_frames': 30,
       'width': 1600, 'height': 900, 'views': views, 'measure_frames': 60, 'eye_height_m': EYE}
(HERE.parent / 'output' / 'verdant' / 'capture_job.json').write_text(json.dumps(job, indent=1), encoding='utf-8')
print('CAPTURE JOB', label, len(views), 'views', flush=True)
