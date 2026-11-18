"""Writes output/verdant/capture_job.json for close-up captures of each story set on the merged map,
in both eras and, for the clinic and shelter, in the uninstalled and installed canvas states.

    blender --background --python story_closeups.py -- [label]

Positions are Blender metres at player eye height (1.62 m). The era is applied through the story's
Opening.PastOnly / Opening.PresentOnly tags, with the committed-state actors (installed covers,
preserved record pages) hidden as ApplyWorldState keeps them before a branch is committed;
`show_tags` shows the ones a view wants, as the committed state would.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verdant_plan as plan

EYE = 1.62
HOME = 10.11
z = plan.street_z
VIEWS = [
    # Courtyard framed so the awning (canvas at 12.2 m) and the table set are both in view.
    ('Clinic_Bare', 'Past', dict(pos=(1.3, -3.2, z(-3.2) + EYE), target=(-1.85, -5.05, 11.4), fov=82), []),
    ('Clinic_Installed', 'Past', dict(pos=(1.3, -3.2, z(-3.2) + EYE), target=(-1.85, -5.05, 11.4), fov=82), ['Opening.ClinicCover']),
    # The open entrance: kit module at bay origin (-8.6, -5.1) facing east, opening centred at y -3.6
    # (bay width 3 m, leaf hinged on the south jamb and swung into the room); seen from the court.
    ('Clinic_Entrance', 'Past', dict(pos=(-5.4, -3.6, z(-3.6) + EYE), target=(-8.6, -3.6, 10.9), fov=70), []),
    ('Clinic_Ruin', 'Present', dict(pos=(1.3, -3.2, z(-3.2) + EYE), target=(-1.85, -5.05, 10.9), fov=82), []),
    ('Shop', 'Past', dict(pos=(-.4, 3.0, z(3.0) + EYE), target=(2.4, 3.1, 11.4), fov=70), []),
    ('Shop_Counter', 'Past', dict(pos=(1.0, 2.2, z(2.2) + EYE), target=(2.3, 3.4, 11.5), fov=62), []),
    ('Shop_Present', 'Present', dict(pos=(-.4, 3.0, z(3.0) + EYE), target=(2.4, 3.1, 11.4), fov=70), []),
    # Shelter framed from across the road so the cover (13.4 m) sits inside the frame above the bench.
    ('Shelter_Bare', 'Past', dict(pos=(-1.6, 4.9, z(4.9) + EYE), target=(1.9, 6.6, 12.3), fov=88), []),
    ('Shelter_Installed', 'Past', dict(pos=(-1.6, 4.9, z(4.9) + EYE), target=(1.9, 6.6, 12.3), fov=88), ['Opening.HarborCover']),
    ('Shelter_Ruin', 'Present', dict(pos=(-1.6, 4.9, z(4.9) + EYE), target=(1.9, 6.6, 11.6), fov=88), []),
    ('Memorial_Clinic', 'Present', dict(pos=(-2.25, -14.6, HOME + EYE), target=(-3.5, -14.6, 11.55), fov=82), ['Opening.ClinicRecord']),
    ('Memorial_Harbor', 'Present', dict(pos=(-2.25, -14.6, HOME + EYE), target=(-3.5, -14.6, 11.55), fov=82), ['Opening.HarborRecord']),
    ('Memorial_Past', 'Past', dict(pos=(-2.25, -14.6, HOME + EYE), target=(-3.5, -14.6, 11.55), fov=82), []),
    ('Chronology', 'Present', dict(pos=(-.3, -15.75, z(-15.75) + EYE), target=(-2.09, -15.75, 11.4), fov=58), []),
    ('Gate', 'Present', dict(pos=(1.2, -12.4, z(-12.4) + EYE), target=(-2.2, -12.4, 11.6), fov=72), []),
    ('Gate_Past', 'Past', dict(pos=(1.2, -12.4, z(-12.4) + EYE), target=(-2.2, -12.4, 11.6), fov=72), []),
    ('Home_Watch', 'Present', dict(pos=(-8.7, -12.6, HOME + EYE), target=(-10.1, -11.92, 11.17), fov=52), []),
    ('Home_Photo', 'Present', dict(pos=(-6.5, -13.3, HOME + EYE), target=(-7.82, -13.7, 11.1), fov=50), []),
    ('Anchor', 'Present', dict(pos=(-2.15, -14.5, HOME + EYE), target=(-3.05, -14.5, 10.45), fov=70), []),
    # The past-house entrance barrier (closed plank door at Unreal (-444, 1240, 1123)) from the porch.
    ('Door_Past', 'Past', dict(pos=(-2.9, -12.4, HOME + EYE), target=(-4.44, -12.4, 11.23), fov=60), []),
    ('Wing_Past', 'Past', dict(pos=(-.6, -8.6, z(-8.6) + EYE), target=(-6.0, -9.6, 12.6), fov=74), []),
    ('Wing_Present', 'Present', dict(pos=(-.6, -8.6, z(-8.6) + EYE), target=(-6.0, -9.6, 12.6), fov=74), []),
]
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
label = args[0] if args else 'story_closeups'
views = [{'id': key, 'era': era, 'show_tags': show, **view} for key, era, view, show in VIEWS]
job = {'map': '/Game/Quest/Maps/Verdant_Desktop', 'label': label, 'era_mode': 'story', 'warmup_seconds': 40, 'settle_frames': 30,
       'width': 1600, 'height': 900, 'views': views, 'measure_frames': 60, 'eye_height_m': EYE}
(HERE.parent / 'output' / 'verdant' / 'capture_job.json').write_text(json.dumps(job, indent=1), encoding='utf-8')
print('CAPTURE JOB', label, len(views), 'views', flush=True)
