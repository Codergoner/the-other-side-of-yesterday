"""Writes output/verdant/capture_job.json for the concept pass of 17 November 2026: the five art-gate views of
story_views.py plus the shop, the gate, the street up to the cathedral from mid-way and the street down, at player eye
height, in both eras. Plain Python (no bpy):

    python concept_views.py [label] [hdr]

'hdr' also writes the linear scene colour of every view (EXR), which tools/ldr_preview.py turns into an estimate of
the headset's untonemapped output. Positions are Blender metres (Unreal = 100X, -100Y, 100Z).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EYE = 1.62
HOME_FLOOR = 10.11
LANDING = 11.6


def street_z(y):
    return 10.2 + .1 * y


VIEWS = {
    'LivingRoom': dict(pos=(-5.6, -12.4, HOME_FLOOR + EYE), target=(-9.15, -14.12, HOME_FLOOR + 1.35), fov=74),
    'HomeFront': dict(pos=(0.6, -16.0, street_z(-16.0) + EYE), target=(-5.0, -12.0, HOME_FLOOR + 1.6), fov=76),
    'UphillCathedral': dict(pos=(0.4, -21.0, street_z(-21.0) + EYE), target=(1.5, 52.0, 30.0), fov=74),
    'ClinicCourtyard': dict(pos=(-0.6, -1.0, street_z(-1.0) + EYE), target=(-6.8, -4.6, street_z(-4.0) + 1.3), fov=76),
    'HarborOverlook': dict(pos=(4.5, 14.0, LANDING + EYE), target=(44.0, 26.0, 5.5), fov=80),
    'Shop': dict(pos=(-0.6, 2.6, street_z(2.6) + EYE + .04), target=(2.4, 3.1, 11.4), fov=76),
    'Gate': dict(pos=(1.6, -12.4, street_z(-12.4) + EYE), target=(-2.2, -12.4, 11.6), fov=76),
    'StreetUp': dict(pos=(0.5, -6.0, street_z(-6.0) + EYE), target=(1.5, 52.0, 28.0), fov=78),
    'StreetDown': dict(pos=(0.5, 8.0, street_z(8.0) + EYE), target=(0.6, -40.0, 7.0), fov=78),
    'Relief': dict(pos=(-6.2, -3.3, 11.45), target=(-8.56, -3.85, 12.9), fov=64),
}
args = sys.argv[1:]
label = args[0] if args else 'concept'
only = next((a.split('=', 1)[1].split(',') for a in args if a.startswith('only=')), list(VIEWS))
views = [{'id': key, 'era': era, **VIEWS[key]} for era in ('Past', 'Present') for key in VIEWS if key in only]
job = {'map': '/Game/Quest/Maps/Verdant_Desktop', 'label': label, 'era_mode': 'story', 'warmup_seconds': 45, 'settle_frames': 30,
       'width': 1600, 'height': 900, 'views': views, 'measure_frames': 20, 'eye_height_m': EYE, 'hdr': 'hdr' in args}
(HERE.parent / 'output' / 'verdant' / 'capture_job.json').write_text(json.dumps(job, indent=1), encoding='utf-8')
print('CAPTURE JOB', label, len(views), 'views', 'hdr' if job['hdr'] else '')
