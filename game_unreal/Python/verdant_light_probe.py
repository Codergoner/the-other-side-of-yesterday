"""Lighting diagnostic for Verdant_City: per era, dumps every light's state after the era switch and
captures two views normally, with the skylight muted, and with the sun muted. Nothing is saved."""
import json
import sys
import time
import traceback
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc

VIEWS = [('MarketSquare', (-13.2, 6.4, 12.32), (-33, 9.5, 13.2), 78), ('HarborOverlook', (1.0, 7.0, 12.52), (44, 26, 5.5), 80)]
FOLDER = vc.EVIDENCE / 'captures' / ('lightprobe_' + time.strftime('%Y%m%dT%H%M%S'))
FOLDER.mkdir(parents=True, exist_ok=True)
REPORT = {'success': False, 'lights': {}, 'images': []}


def light_state(world):
    rows = []
    for actor in vc.actors.get_all_level_actors():
        if not isinstance(actor, (unreal.DirectionalLight, unreal.SkyLight, unreal.ExponentialHeightFog, unreal.PostProcessVolume)):
            continue
        component = actor.get_component_by_class(unreal.LightComponentBase) or actor.get_component_by_class(unreal.SceneComponent)
        row = {'label': actor.get_actor_label(), 'class': actor.get_class().get_name(), 'tags': [str(t) for t in actor.get_editor_property('tags')],
               'hidden_in_game': actor.is_hidden_ed() if hasattr(actor, 'is_hidden_ed') else None,
               'temporarily_hidden_in_editor': actor.is_temporarily_hidden_in_editor(),
               'component_visible': component.is_visible() if component else None}
        if isinstance(actor, (unreal.DirectionalLight, unreal.SkyLight)):
            light = actor.get_component_by_class(unreal.LightComponentBase)
            row['intensity'] = light.get_editor_property('intensity')
            row['affects_world'] = light.get_editor_property('affects_world')
            row['cast_shadows'] = light.get_editor_property('cast_shadows')
            if isinstance(actor, unreal.DirectionalLight):
                row['rotation'] = str(actor.get_actor_rotation())
        rows.append(row)
    return rows


class Session:
    def __init__(self):
        self.phase = 'load'
        self.jobs = []
        self.index = 0
        self.frames = 0
        self.started = time.monotonic()
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
            self.finish(traceback.format_exc())

    def setup(self):
        vc.require(vc.levels.load_level(vc.MAP), 'Cannot load ' + vc.MAP)
        self.world = vc.editor.get_editor_world()
        self.cap = vc.actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 2000))
        self.comp = self.cap.get_component_by_class(unreal.SceneCaptureComponent2D)
        self.rt = unreal.RenderingLibrary.create_render_target2d(self.world, 1280, 720, unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                                                 unreal.LinearColor(0, 0, 0, 1), False, False)
        self.rt.set_editor_property('target_gamma', 2.2)
        for key, value in [('texture_target', self.rt), ('capture_every_frame', False), ('capture_on_movement', False),
                           ('always_persist_rendering_state', True), ('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR),
                           ('post_process_blend_weight', 0.0)]:
            self.comp.set_editor_property(key, value)
        for era in ('Past', 'Present'):
            for variant in ('normal', 'no_skylight', 'no_sun'):
                for view in VIEWS:
                    self.jobs.append((era, variant, view))

    def apply(self, era, variant):
        unreal.VerdantEraLibrary.apply_era(self.world, era == 'Past')
        REPORT['lights'][era] = light_state(self.world)
        self.muted = []
        for actor in vc.actors.get_all_level_actors():
            if variant == 'no_skylight' and isinstance(actor, unreal.SkyLight) or variant == 'no_sun' and isinstance(actor, unreal.DirectionalLight):
                light = actor.get_component_by_class(unreal.LightComponentBase)
                self.muted.append((light, light.get_editor_property('intensity')))
                light.set_editor_property('intensity', 0.0)

    def restore(self):
        for light, value in self.muted:
            light.set_editor_property('intensity', value)
        self.muted = []

    def step(self):
        if self.phase == 'load':
            self.setup()
            self.phase = 'warm'
            self.started = time.monotonic()
        elif self.phase == 'warm':
            if time.monotonic() - self.started > 30:
                self.phase = 'next'
        elif self.phase == 'next':
            if self.index >= len(self.jobs):
                self.finish(None)
                return
            era, variant, (name, pos, target, fov) = self.jobs[self.index]
            self.apply(era, variant)
            p, t = vc.to_unreal(pos), vc.to_unreal(target)
            self.cap.set_actor_location(p, False, False)
            self.cap.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(p, t), False)
            self.comp.set_editor_property('fov_angle', fov)
            self.frames = 0
            self.phase = 'settle'
        elif self.phase == 'settle':
            self.comp.capture_scene()
            self.frames += 1
            if self.frames >= 16:
                era, variant, (name, _, _, _) = self.jobs[self.index]
                file = '%02d_%s_%s_%s.png' % (self.index, era, variant, name)
                unreal.RenderingLibrary.export_render_target(self.world, self.rt, str(FOLDER), file)
                samples = [unreal.RenderingLibrary.read_render_target_pixel(self.world, self.rt, x, y) for x, y in ((640, 600), (640, 200), (200, 500), (1000, 500))]
                REPORT['images'].append({'file': file, 'rgb': [[c.r, c.g, c.b] for c in samples]})
                self.restore()
                self.index += 1
                self.phase = 'next'

    def finish(self, error):
        self.done = True
        unreal.unregister_slate_post_tick_callback(self.handle)
        REPORT['success'] = error is None
        REPORT['error'] = error
        REPORT['folder'] = str(FOLDER)
        vc.write_json(vc.EVIDENCE / 'light_probe_report.json', REPORT)
        vc.log('light probe', 'ok' if error is None else error[-300:])
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()


Session().start()
