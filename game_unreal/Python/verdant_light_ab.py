"""Lighting A/B on Verdant_City: each combo sets sun intensity, skylight intensity and exposure bias
in memory, then captures the listed views. Reads output/verdant/light_ab.json; saves nothing."""
import json
import sys
import time
import traceback
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc

JOB = json.loads((vc.SOURCE / 'light_ab.json').read_text(encoding='utf-8-sig'))
FOLDER = vc.EVIDENCE / 'captures' / ('lightab_' + time.strftime('%Y%m%dT%H%M%S'))
FOLDER.mkdir(parents=True, exist_ok=True)
REPORT = {'success': False, 'images': []}


class Session:
    def __init__(self):
        self.phase = 'load'
        self.jobs = [(combo, view) for combo in JOB['combos'] for view in JOB['views']]
        self.index = 0
        self.frames = 0
        self.started = time.monotonic()
        self.done = False
        self.current_combo = None

    def start(self):
        unreal.EditorPythonScripting.set_keep_python_script_alive(True)
        self.handle = unreal.register_slate_post_tick_callback(self.tick)

    def tick(self, _):
        if self.done:
            return
        try:
            self.step()
        except Exception:
            self.finish(traceback.format_exc())

    def setup(self):
        vc.require(vc.levels.load_level(vc.MAP), 'Cannot load ' + vc.MAP)
        self.world = vc.editor.get_editor_world()
        unreal.VerdantEraLibrary.apply_era(self.world, JOB.get('era', 'Past') == 'Past')
        self.cap = vc.actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 2000))
        self.comp = self.cap.get_component_by_class(unreal.SceneCaptureComponent2D)
        self.rt = unreal.RenderingLibrary.create_render_target2d(self.world, 1280, 720, unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                                                 unreal.LinearColor(0, 0, 0, 1), False, False)
        self.rt.set_editor_property('target_gamma', 2.2)
        for key, value in [('texture_target', self.rt), ('capture_every_frame', False), ('capture_on_movement', False),
                           ('always_persist_rendering_state', True), ('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR),
                           ('post_process_blend_weight', 0.0)]:
            self.comp.set_editor_property(key, value)
        self.volume = next(a for a in vc.actors.get_all_level_actors() if isinstance(a, unreal.PostProcessVolume))
        self.lights = [a for a in vc.actors.get_all_level_actors() if isinstance(a, (unreal.DirectionalLight, unreal.SkyLight))
                       and not a.is_temporarily_hidden_in_editor()]

    def apply(self, combo):
        if combo == self.current_combo:
            return
        self.current_combo = combo
        for actor in self.lights:
            light = actor.get_component_by_class(unreal.LightComponentBase)
            light.set_editor_property('intensity', combo['sun'] if isinstance(actor, unreal.DirectionalLight) else combo['sky'])
        settings = self.volume.get_editor_property('settings')
        settings.set_editor_property('override_auto_exposure_bias', True)
        settings.set_editor_property('auto_exposure_bias', combo['bias'])
        self.volume.set_editor_property('settings', settings)

    def step(self):
        if self.phase == 'load':
            self.setup()
            self.phase = 'warm'
            self.started = time.monotonic()
        elif self.phase == 'warm':
            if time.monotonic() - self.started > JOB.get('warmup_seconds', 35):
                self.phase = 'next'
        elif self.phase == 'next':
            if self.index >= len(self.jobs):
                self.finish(None)
                return
            combo, view = self.jobs[self.index]
            self.apply(combo)
            p, t = vc.to_unreal(view['pos']), vc.to_unreal(view['target'])
            self.cap.set_actor_location(p, False, False)
            self.cap.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(p, t), False)
            self.comp.set_editor_property('fov_angle', view.get('fov', 75))
            self.frames = 0
            self.phase = 'settle'
        elif self.phase == 'settle':
            self.comp.capture_scene()
            self.frames += 1
            if self.frames >= JOB.get('settle_frames', 20):
                combo, view = self.jobs[self.index]
                file = '%02d_%s_%s.png' % (self.index, combo['id'], view['id'])
                unreal.RenderingLibrary.export_render_target(self.world, self.rt, str(FOLDER), file)
                REPORT['images'].append({'file': file, **combo, 'view': view['id']})
                self.index += 1
                self.phase = 'next'

    def finish(self, error):
        self.done = True
        unreal.unregister_slate_post_tick_callback(self.handle)
        REPORT['success'] = error is None
        REPORT['error'] = error
        REPORT['folder'] = str(FOLDER)
        vc.write_json(vc.EVIDENCE / 'light_ab_report.json', REPORT)
        vc.log('light ab', 'ok' if error is None else error[-300:])
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()


Session().start()
