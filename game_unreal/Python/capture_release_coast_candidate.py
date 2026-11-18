"""Queued actual editor PNG A/B for the coast candidate, with exact cleanup.

Five first-route views plus the old sea's perimeter in both era visibility
previews. No PIE, moving/runtime/device/performance acceptance is implied.
"""
from pathlib import Path
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT/'Python'))
import release_coast_candidate as coast
import capture_release_art as review

VIEWS = [
    {'id': 'RoomConversation', 'xy': [-620,1240], 'ground': 'house', 'target': [-950,1360,1150], 'fov': 82},
    {'id': 'HomeFrontage', 'xy': [100,1800], 'ground': 'street', 'target': [-650,1300,1320], 'fov': 74},
    {'id': 'UphillCathedral', 'xy': [0,1100], 'ground': 'street', 'target': [-100,-4000,1600], 'fov': 74},
    {'id': 'ClinicCourtyard', 'xy': [100,550], 'ground': 'street', 'target': [-410,550,1090], 'fov': 76},
    {'id': 'HarborOverlook', 'xy': [0,-700], 'ground': 'street', 'target': [4800,-2600,650], 'fov': 78},
    {'id': 'SeaPerimeter', 'xy': [120,-1050], 'ground': 'street', 'target': [18000,-14500,0], 'fov': 72},
]


class Capture(review.Capture):
    def __init__(self):
        coast.guard(write_native=True)
        self.coast = coast.ready()
        coast.require(not self.coast.get('active'), 'Capture the original-vs-candidate before adoption')
        review.VIEWS = VIEWS
        review.base.VIEWS = VIEWS
        self.scene_before = None
        self.sea_override = None
        self.ring = None
        super().__init__()
        self.folder = ROOT/'validation/release_coast_capture'/self.stamp
        self.folder.mkdir(parents=True, exist_ok=False)
        self.report_path = ROOT/'release_coast_capture_report.json'
        self.report.update(scope=__doc__, coast_signature=self.coast['signature'],
            capture_kind='editor', temporary_new_mesh_actors=1,
            story_flags_modified=False, moving_water_aliasing_tested=False,
            visual_accepted=False, packaged_runtime_verified=False, performance_measured=False)
        self.protected.update({Path(path): digest for path, digest in coast.protected_files().items()})
        self.groups = [
            {'label': label, 'map': coast.MAP, 'era': era,
             'jobs': [(view, 'Lit') for view in VIEWS] +
                     ([(VIEWS[-1], 'BaseColor')] if label == 'After' and era == 'Present' else [])}
            for era in ['Present', 'Past'] for label in ['Before', 'After']]

    def apply_era_preview(self, era):
        actor, ring = coast.editable(self.coast)
        coast.require(ring is None, 'Unexpected saved coast extension before A/B')
        self.scene_before = coast.snapshot()
        current = coast.base.lighting()
        if self.saved_lights is None:
            self.saved_lights = current
        coast.require(current == self.saved_lights, 'Saved lighting differs between coast views')
        # Invoke the existing temporary visibility preview, not a gameplay setter.
        has_past = review.base.ArtCapture.apply_era_preview(self, era)
        if self.groups[self.group_index]['label'] == 'After':
            component = actor.get_component_by_class(unreal.StaticMeshComponent)
            self.sea_override = list(component.get_editor_property('override_materials'))
            component.set_material(0, coast.base.load(self.coast['material_path']))
            self.ring = coast.spawn_extension(self.coast)
        return has_past

    def restore_world(self):
        # Base cleanup removes the transient SceneCapture and restores all era
        # visibility first; only then compare the complete original actor state.
        super().restore_world()
        try:
            if self.ring is not None:
                coast.require(self.actors.destroy_actor(self.ring), 'Could not remove preview coast extension')
                self.ring = None
            if self.sea_override is not None:
                coast.sea().get_component_by_class(unreal.StaticMeshComponent).set_editor_property(
                    'override_materials', self.sea_override)
                self.sea_override = None
            if self.scene_before is not None:
                coast.require(coast.snapshot() == self.scene_before,
                              'Coast capture did not restore exact original actor state')
                self.scene_before = None
                self.report['original_actor_state_restored'] = True
        except Exception:
            # Let the common finish path record failure and quit even when a
            # cleanup guard fails; never leave an unattended editor hanging.
            self.report['cleanup_errors'].append(traceback.format_exc())

    def export(self):
        super().export()
        row = self.report['images'][-1]
        row['sha256'] = coast.fio.sha(row['path'])
        row['review_view_id'] = 'HomeFront' if row['view'] == 'HomeFrontage' else row['view']
        self.write()

    def finish(self, error=None):
        pairs = {(label, era, view['id']) for label in ['Before', 'After']
                 for era in ['Past', 'Present'] for view in VIEWS}
        actual = {(row['label'], row['era'], row['view']) for row in self.report['images']
                  if row['mode'] == 'Lit'}
        self.report['all_24_matched_era_view_images_complete'] = pairs.issubset(actual)
        if error is None and not pairs.issubset(actual):
            error = 'Missing required actual Before/After era/view image'
        super().finish(error)


if __name__ == '__main__':
    session = None
    try:
        session = Capture()
        session.start()
    except Exception:
        if session:
            session.finish(traceback.format_exc())
        else:
            (ROOT/'release_coast_capture_report.json').write_text(json.dumps(
                {'success': False, 'error': traceback.format_exc()}, indent=2), encoding='utf-8')
            unreal.SystemLibrary.quit_editor()
