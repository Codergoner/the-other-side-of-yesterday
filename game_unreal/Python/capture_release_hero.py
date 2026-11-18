"""Queued native editor floor A/B at existing162cm eye height; no saves.

Only the two reviewed first material overrides are restored in memory for the
Before group. After reloads the saved desktop map. Sun/skylight/exposure remain
fixed; these are scene-capture PNGs, not gameplay or final visual acceptance.
"""
from pathlib import Path
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT/'Python'))
import build_release_hero as hero
import capture_release_art as review

VIEWS = [
    {'id': 'SurvivingRoom', 'xy': [-620,1240], 'ground': 'house', 'target': [-950,1360,1150], 'fov': 82},
    {'id': 'RoomFloor', 'xy': [-620,1240], 'ground': 'house', 'target': [-800,1560,1011], 'fov': 78},
    {'id': 'StreetFloor', 'xy': [0,400], 'ground': 'street', 'target': [0,-900,1080], 'fov': 78},
]


class Capture(review.Capture):
    def __init__(self):
        review.VIEWS = VIEWS
        super().__init__()
        self.folder = ROOT/'validation/release_hero_capture'/self.stamp
        self.folder.mkdir(parents=True, exist_ok=False)
        self.report_path = ROOT/'release_hero_capture_report.json'
        self.report.update(scope=__doc__, profile_policy='Saved desktop lighting, no light/property/profile setter',
                           new_detail_props_required=False, native_floor_quality_accepted=False)
        self.groups = [
            {'label':'Before','map':hero.MAP,'era':'Present','jobs':[(view,'Lit') for view in VIEWS]},
            {'label':'After','map':hero.MAP,'era':'Present','jobs':[(view,'Lit') for view in VIEWS]+[(VIEWS[1],'BaseColor')]},
        ]
        self.protected.update({path: hero.sha(path) for path in (ROOT/'Saved/SaveGames').glob('*.sav')})

    def apply_era_preview(self, era):
        current = hero.base.lighting()
        if self.saved_lights is None:
            self.saved_lights = current
        hero.require(current == self.saved_lights, 'Saved light fields differ across hero pairs')
        if self.groups[self.group_index]['label'] == 'Before':
            records = hero.read_report()['floors']['baseline']
            for actor in self.actors.get_all_level_actors():
                first = records.get(actor.get_name())
                if first:
                    actor.get_component_by_class(unreal.StaticMeshComponent).set_editor_property('override_materials',
                        [hero.base.load(path) if path else None for path in first['raw_override_materials']])
        return True


if __name__ == '__main__':
    session = None
    try:
        session = Capture()
        session.start()
    except Exception:
        if session:
            session.finish(traceback.format_exc())
        else:
            (ROOT/'release_hero_capture_report.json').write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2),encoding='utf-8')
            unreal.SystemLibrary.quit_editor()
