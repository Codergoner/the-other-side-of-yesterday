"""Queued transient desktop skylight comparison; no saved light/profile edits.

Saved current .105 is compared with .21/.315 on the one existing skylight.
Sun3.5, light color, transforms, cubemap, camera positions and exposure remain
fixed. Output is native editor SceneCapture2D evidence, not a gameplay/device
or final visual-acceptance claim. Root grants the serialized launch separately.
"""
from pathlib import Path
import copy
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

MAP = '/Game/Quest/Maps/Verdant_Desktop'
PROFILES = [('SavedCurrent', .105, .10), ('SkyScale020', .21, .20), ('SkyScale030', .315, .30)]
VIEWS = [
    {'id': 'SurvivingRoom', 'xy': [-620, 1240], 'ground': 'house', 'target': [-950, 1360, 1150], 'fov': 82},
    {'id': 'HarborVista', 'xy': [0, -700], 'ground': 'street', 'target': [4800, -2600, 650], 'fov': 78},
    {'id': 'UphillCathedral', 'xy': [0, 1100], 'ground': 'street', 'target': [850, -6400, 2750], 'fov': 80},
]


class Capture(base.ArtCapture):
    def __init__(self):
        art.guard()
        self.sky_component = None
        self.sky_saved_intensity = None
        self.saved_lights = None
        self.saved_story = None
        base.BEFORE_MAP = MAP
        base.AFTER_MAP = MAP
        super().__init__()
        self.folder = ROOT / 'validation/release_sky_ab' / self.stamp
        self.folder.mkdir(parents=True, exist_ok=False)
        self.report_path = ROOT / 'release_sky_ab_report.json'
        self.report.update(scope=__doc__, profiles=[{'label': label, 'actual_skylight_intensity': intensity,
                                                    'scale_relative_to_original_profile_1_05': scale}
                                                   for label, intensity, scale in PROFILES],
                           source_map=MAP, test_map=MAP,
                           camera_policy='Identical fixed existing M0 cameras, traced ground+162cm; no player-camera or field-of-view edit.',
                           profile_policy='Saved desktop D3D11/SM5, no Android/mobile profile or renderer mutation',
                           native_light_changes=[], rendered_quality_accepted=False,
                           renderer_performance_measured=False, packaged_playtested=False,
                           capture_exposure={'method': 'Manual', 'bias': 0.0, 'physical_camera_exposure': False})
        self.groups = [{'label': label, 'map': MAP, 'era': 'Present', 'jobs': [(view, 'Lit') for view in VIEWS],
                        'sky_intensity': intensity, 'sky_scale': scale}
                       for label, intensity, scale in PROFILES]
        for path in list((ROOT / 'Content').rglob('*.uasset')) + list((ROOT / 'Content').rglob('*.umap')) + list((ROOT / 'Saved/SaveGames').glob('*.sav')):
            self.protected[path] = hashlib.sha256(path.read_bytes()).hexdigest()

    def tick(self, delta):
        if getattr(self, '_tick_active', False):
            return
        self._tick_active = True
        try:
            super().tick(delta)
        finally:
            self._tick_active = False

    def restore_world(self):
        if self.sky_component is not None:
            if not unreal.SystemLibrary.is_valid(self.sky_component):
                raise RuntimeError('Skylight expired before transient intensity restoration')
            self.sky_component.set_intensity(self.sky_saved_intensity)
            art.require(abs(self.sky_component.get_editor_property('intensity') - self.sky_saved_intensity) < 1e-6,
                        'Transient skylight intensity did not restore')
            self.sky_component = None
            self.sky_saved_intensity = None
            art.require(art.lighting() == self.saved_lights, 'Restored light fields differ from saved setup')
        super().restore_world()

    def apply_era_preview(self, era):
        # Called after every clean map load, before its capture actor exists.
        # No visibility groups or manager presentation/story state are edited.
        before = art.lighting()
        story = art.story_refs()
        if self.saved_lights is None:
            self.saved_lights = copy.deepcopy(before)
            self.saved_story = copy.deepcopy(story)
        art.require(before == self.saved_lights and story == self.saved_story, 'Saved map setup differs between candidates')
        skies = [actor for actor in self.actors.get_all_level_actors() if isinstance(actor, unreal.SkyLight)]
        art.require(len(skies) == 1, 'Exactly one existing skylight is required')
        sky = skies[0]
        component = sky.get_component_by_class(unreal.SkyLightComponent)
        saved = float(component.get_editor_property('intensity'))
        art.require(abs(saved - .105) < 1e-5, 'Saved skylight is not the reviewed .105 setup; preserve changed lighting')
        suns = [actor for actor in self.actors.get_all_level_actors()
                if isinstance(actor, unreal.DirectionalLight)
                and actor.get_component_by_class(unreal.DirectionalLightComponent).get_editor_property('intensity') > 0]
        art.require(len(suns) == 1, 'Expected one active existing sun')
        art.require(abs(suns[0].get_component_by_class(unreal.DirectionalLightComponent).get_editor_property('intensity') - 3.5) < 1e-5,
                    'Saved sun no longer matches reviewed3.5; no automatic recalibration')
        group = self.groups[self.group_index]
        target = group['sky_intensity']
        self.sky_component = component
        self.sky_saved_intensity = saved
        if group['label'] != 'SavedCurrent':
            component.set_intensity(target)
        actual = float(component.get_editor_property('intensity'))
        art.require(abs(actual - target) < 1e-6, 'Native skylight did not retain requested temporary intensity')
        expected = copy.deepcopy(before)
        expected[sky.get_name()]['intensity'] = actual
        art.require(art.lighting() == expected, 'Something beyond the one skylight intensity changed')
        art.require(art.story_refs() == story, 'Skylight preview modified a story reference')
        self.report['native_light_changes'].append({'profile': group['label'], 'actor': sky.get_path_name(),
                                                    'saved_intensity': saved, 'requested_intensity': target,
                                                    'actual_intensity': actual, 'sun_intensity': 3.5,
                                                    'only_changed_field': 'SkyLightComponent.Intensity',
                                                    'before': before[sky.get_name()], 'after': art.lighting()[sky.get_name()]})
        return True

    def load_group(self):
        super().load_group()
        settings = self.component.get_editor_property('post_process_settings')
        for field, value in {'auto_exposure_method': unreal.AutoExposureMethod.AEM_MANUAL,
                             'auto_exposure_bias': 0.0, 'auto_exposure_apply_physical_camera_exposure': False,
                             'motion_blur_amount': 0.0, 'bloom_intensity': 0.0}.items():
            settings.set_editor_property('override_' + field, True)
            settings.set_editor_property(field, value)
        self.component.set_editor_property('post_process_settings', settings)

    def export(self):
        # Keep dark baselines as evidence rather than skipping a low-scoring
        # candidate. Full-PNG shadow/clipping metrics are calculated separately.
        colors = []
        for yf in [.1, .3, .5, .7, .9]:
            for xf in [.1, .25, .5, .75, .9]:
                color = unreal.RenderingLibrary.read_render_target_pixel(self.world, self.target, int(base.WIDTH * xf), int(base.HEIGHT * yf))
                colors.append((int(color.r), int(color.g), int(color.b)))
        values = [value for color in colors for value in color]
        mean = sum(values) / len(values)
        sample = {'profile': self.current['label'], 'view': self.current['view'], 'mean': mean,
                  'min': min(values), 'max': max(values), 'samples': colors,
                  'variance': sum((value - mean) ** 2 for value in values) / len(values),
                  'unique_colors': len(set(colors))}
        sample['usable_nonblank_sample_content'] = sample['max'] >= 8 and sample['variance'] >= 2 and sample['unique_colors'] >= 4
        self.report['pixel_samples'].append(sample)
        filename = self.current['label'] + '_' + self.current['view'] + '_NativeEditorSceneCapture.png'
        unreal.RenderingLibrary.export_render_target(self.world, self.target, str(self.folder), filename)
        path = self.folder / filename
        art.require(path.is_file() and path.stat().st_size > 20000, 'Native PNG export failed')
        self.report['images'].append({**self.current, 'path': str(path), 'bytes': path.stat().st_size,
                                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                     'warm_frames': self.frame_count, 'sample_monotonic_seconds': time.monotonic(),
                                     'editor_world_seconds': unreal.GameplayStatics.get_time_seconds(self.world),
                                     'editor_real_seconds': unreal.GameplayStatics.get_real_time_seconds(self.world),
                                     'runtime_gameplay_capture': False})
        self.job_index += 1
        self.phase = 'configure'
        self.phase_time = time.monotonic()
        self.write()

    def finish(self, error=None):
        if self.finished:
            return
        self.finished = True
        if error:
            self.report['error'] = error
        try:
            self.restore_world()
            if self.saved_lights is not None:
                art.require(art.lighting() == self.saved_lights, 'Final restored light fields differ')
                art.require(art.story_refs() == self.saved_story, 'Final story reference snapshot differs')
            self.report['saved_lights_restored'] = True
            self.report['story_references_unchanged'] = True
        except Exception:
            self.report['cleanup_errors'].append(traceback.format_exc())
        for name, value in self.cvar_restore.items():
            try:
                unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), name + ' ' + value)
            except Exception:
                self.report['cleanup_errors'].append(traceback.format_exc())
        self.report['runtime_metadata'] = self.metadata()
        changed = [str(path) for path, digest in self.protected.items() if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest]
        self.report['unexpected_file_changes'] = changed
        self.report['protected_inputs_unchanged'] = not changed
        expected = {(label, view['id']) for label, _, _ in PROFILES for view in VIEWS}
        actual = {(image['label'], image['view']) for image in self.report['images']}
        self.report['required_nine_native_images_complete'] = expected == actual
        self.report['success'] = not error and not changed and not self.report['cleanup_errors'] and expected == actual
        self.report['all_images_have_nonblank_samples'] = all(row['usable_nonblank_sample_content'] for row in self.report['pixel_samples'])
        self.phase = 'finished'
        self.write()
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()


if __name__ == '__main__':
    session = None
    try:
        session = Capture()
        session.start()
    except Exception:
        if session:
            session.finish(traceback.format_exc())
        else:
            (ROOT / 'release_sky_ab_report.json').write_text(json.dumps({'success': False, 'error': traceback.format_exc()}, indent=2), encoding='utf-8')
            unreal.SystemLibrary.quit_editor()
