"""Unsaved desktop waterfront material A/B; no light/story or asset saves.

Before uses the preserved first material overrides in memory. After reloads
the saved map. Both use identical camera/exposure and the same saved lighting.
This is still-image editor evidence, never gameplay/motion/device acceptance.
"""
from pathlib import Path
import hashlib
import json
import sys
import time
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import build_release_art as art
import capture_brief_art as base
import release_file_io as long_io

MAP = '/Game/Quest/Maps/Verdant_Desktop'
VIEWS = [
    {'id': 'HarborVista', 'xy': [0, -700], 'ground': 'street', 'target': [4800, -2600, 650], 'fov': 78},
    {'id': 'WaterAndDocks_A', 'xy': [120, -1050], 'ground': 'street', 'target': [1950, -1450, 360], 'fov': 72},
    {'id': 'WaterAndDocks_B', 'xy': [120, -1050], 'ground': 'street', 'target': [1950, -1450, 360], 'fov': 72},
]


class Capture(base.ArtCapture):
    def __init__(self):
        art.guard()
        base.BEFORE_MAP = MAP
        base.AFTER_MAP = MAP
        super().__init__()
        base.VIEWS = VIEWS
        self.folder = ROOT / 'validation/release_art_capture' / self.stamp
        self.folder.mkdir(parents=True, exist_ok=False)
        self.report_path = ROOT / 'release_art_capture_report.json'
        self.report.update(scope=__doc__, source_map=MAP, test_map=MAP,
                           profile_policy='Saved desktop lighting; no scenery/light setter called',
                           moving_water_aliasing_tested=False)
        self.groups = [
            {'label': 'Before', 'map': MAP, 'era': 'Present', 'jobs': [(view, 'Lit') for view in VIEWS]},
            {'label': 'After', 'map': MAP, 'era': 'Present', 'jobs': [(view, 'Lit') for view in VIEWS] + [(VIEWS[1], 'BaseColor')]},
        ]
        self.protected.update({path: long_io.sha(path)
                               for path in long_io.files(ROOT / 'Content','*.uasset')})
        self.saved_lights = None

    def tick(self, delta):
        if getattr(self, '_tick_active', False):
            return
        self._tick_active = True
        try:
            super().tick(delta)
        finally:
            self._tick_active = False

    def load_group(self):
        super().load_group()
        # Match the saved QuestSoft-derived desktop camera calibration used by
        # capture_release_baseline; the older house helper uses an obsolete
        # -11.5 stop bias intended for a different physical-lighting scale.
        settings = self.component.get_editor_property('post_process_settings')
        values = {'auto_exposure_method': unreal.AutoExposureMethod.AEM_MANUAL,
                  'auto_exposure_bias': 0.0, 'auto_exposure_apply_physical_camera_exposure': False,
                  'motion_blur_amount': 0.0, 'bloom_intensity': 0.0}
        for field, value in values.items():
            settings.set_editor_property('override_' + field, True)
            settings.set_editor_property(field, value)
        self.component.set_editor_property('post_process_settings', settings)
        self.report['capture_exposure'] = {'method': 'Manual', 'bias': 0.0, 'physical_camera_exposure': False,
                                           'same_as_existing_release_m0_capture': True}

    def apply_era_preview(self, era):
        # Presentation remains the saved Present setup. No narrative fields,
        # visibility groups, era arrays, NPCs or light properties are modified.
        current = art.lighting()
        if self.saved_lights is None:
            self.saved_lights = current
        else:
            art.require(current == self.saved_lights, 'Saved lighting changed between A/B views')
        if self.groups[self.group_index]['label'] == 'Before':
            records = art.read_report()['maps'][MAP]['baseline']
            for actor in self.actors.get_all_level_actors():
                original = records.get(actor.get_name())
                if original:
                    comp = actor.get_component_by_class(unreal.StaticMeshComponent)
                    comp.set_editor_property('override_materials', [art.load(path) if path else None for path in original['raw_override_materials']])
        return True

    def finish(self, error=None):
        if self.world is not None and self.saved_lights is not None:
            try:
                art.require(art.lighting() == self.saved_lights, 'Capture modified a light')
                self.report['saved_light_fields_unchanged'] = True
            except Exception:
                error = error or traceback.format_exc()
        super().finish(error)

    def export(self):
        # These are the actual editor-world and monotonic sample times. Pixel
        # differences are measured outside Unreal from the exported PNGs.
        self.current['sample_monotonic_seconds'] = time.monotonic()
        self.current['editor_world_seconds'] = unreal.GameplayStatics.get_time_seconds(self.world)
        self.current['editor_real_seconds'] = unreal.GameplayStatics.get_real_time_seconds(self.world)
        self.current['runtime_gameplay_capture'] = False
        super().export()


if __name__ == '__main__':
    session = None
    try:
        session = Capture()
        session.start()
    except Exception:
        if session:
            session.finish(traceback.format_exc())
        else:
            (ROOT / 'release_art_capture_report.json').write_text(json.dumps({'success': False, 'error': traceback.format_exc()}, indent=2), encoding='utf-8')
            unreal.SystemLibrary.quit_editor()
