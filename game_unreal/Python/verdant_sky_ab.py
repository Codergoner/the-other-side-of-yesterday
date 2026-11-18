"""Sky A/B on the throwaway probe map: same camera, different sun strength and exposure."""
import json
import sys
import time
import traceback
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc

MAP = json.loads((vc.EVIDENCE / 'probe_report.json').read_text(encoding='utf-8'))['map']
CASES = [('sun3p5_bias0', 3.5, 0.0, True), ('sun10_bias0', 10.0, 0.0, True), ('sun10_bias2', 10.0, 2.0, True),
         ('sun30_bias0', 30.0, 0.0, True), ('sun10_noflag', 10.0, 0.0, False)]
POS, TARGET = [0, -60, 40], [80, 60, 20]
FOLDER = vc.EVIDENCE / 'captures' / ('skyab_' + str(int(time.time())))
FOLDER.mkdir(parents=True, exist_ok=True)
report = {'success': False, 'images': [], 'cvars': {}}


class Session:
    def __init__(self):
        self.i = 0
        self.frames = 0
        self.phase = 'load'
        self.t = time.monotonic()
        self.done = False

    def start(self):
        unreal.EditorPythonScripting.set_keep_python_script_alive(True)
        self.handle = unreal.register_slate_post_tick_callback(self.tick)

    def tick(self, _):
        if self.done:
            return
        try:
            self.step()
        except Exception:
            self.end(traceback.format_exc())

    def step(self):
        if self.phase == 'load':
            vc.require(vc.levels.load_level(MAP), 'load failed')
            self.world = vc.editor.get_editor_world()
            for name in ('r.SupportSkyAtmosphere', 'r.SkyAtmosphere', 'r.VolumetricCloud', 'r.ForwardShading'):
                report['cvars'][name] = unreal.SystemLibrary.get_console_variable_int_value(name)
            everything = vc.actors.get_all_level_actors()
            report['actors'] = sorted({a.get_class().get_name() for a in everything})
            self.sun = next(a for a in everything if isinstance(a, unreal.DirectionalLight))
            self.light = self.sun.get_component_by_class(unreal.DirectionalLightComponent)
            self.cap = vc.actors.spawn_actor_from_class(unreal.SceneCapture2D, vc.to_unreal(POS))
            self.cap.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(vc.to_unreal(POS), vc.to_unreal(TARGET)), False)
            self.comp = self.cap.get_component_by_class(unreal.SceneCaptureComponent2D)
            self.rt = unreal.RenderingLibrary.create_render_target2d(self.world, 960, 540, unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                                                     unreal.LinearColor(1, 0, 1, 1), False, False)
            self.rt.set_editor_property('target_gamma', 2.2)
            for k, v in [('texture_target', self.rt), ('capture_every_frame', False), ('capture_on_movement', False),
                         ('always_persist_rendering_state', True), ('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR),
                         ('fov_angle', 90)]:
                self.comp.set_editor_property(k, v)
            self.phase = 'warm'
            self.t = time.monotonic()
        elif self.phase == 'warm':
            if time.monotonic() - self.t > 15:
                self.phase = 'set'
        elif self.phase == 'set':
            if self.i >= len(CASES):
                self.end(None)
                return
            name, sun, bias, flag = CASES[self.i]
            self.light.set_editor_property('intensity', sun)
            self.light.set_editor_property('atmosphere_sun_light', flag)
            pp = self.comp.get_editor_property('post_process_settings')
            pp.set_editor_property('override_auto_exposure_method', True)
            pp.set_editor_property('auto_exposure_method', unreal.AutoExposureMethod.AEM_MANUAL)
            pp.set_editor_property('override_auto_exposure_apply_physical_camera_exposure', True)
            pp.set_editor_property('auto_exposure_apply_physical_camera_exposure', False)
            pp.set_editor_property('override_auto_exposure_bias', True)
            pp.set_editor_property('auto_exposure_bias', bias)
            self.comp.set_editor_property('post_process_settings', pp)
            self.comp.set_editor_property('post_process_blend_weight', 1.0)
            self.frames = 0
            self.phase = 'cap'
        elif self.phase == 'cap':
            self.comp.capture_scene()
            self.frames += 1
            if self.frames > 24:
                name = CASES[self.i][0] + '.png'
                unreal.RenderingLibrary.export_render_target(self.world, self.rt, str(FOLDER), name)
                samples = [unreal.RenderingLibrary.read_render_target_pixel(self.world, self.rt, x, y) for x, y in ((480, 30), (800, 100), (200, 100), (480, 270))]
                report['images'].append({'name': name, 'rgb': [[c.r, c.g, c.b] for c in samples]})
                self.i += 1
                self.phase = 'set'

    def end(self, error):
        self.done = True
        unreal.unregister_slate_post_tick_callback(self.handle)
        report['success'] = error is None
        report['error'] = error
        report['folder'] = str(FOLDER)
        vc.write_json(vc.EVIDENCE / 'sky_ab_report.json', report)
        vc.log('skyab', json.dumps(report)[:1400])
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()


Session().start()
