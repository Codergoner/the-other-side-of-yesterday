"""Editor SceneCapture review images. Tick driven so shaders, streaming and clouds settle.

The job reads output/verdant/capture_job.json:
  {"map": path, "label": "...", "views": [{"id","era","pos":[x,y,z] metres,"target":[...],"fov"}]}
Positions are Blender metres. Images are editor captures, labelled as such in the report.
"""
import json
import time
import traceback
from datetime import datetime, timezone

import sys
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc

JOB = json.loads((vc.SOURCE / 'capture_job.json').read_text(encoding='utf-8-sig'))
WIDTH, HEIGHT = JOB.get('width', 1600), JOB.get('height', 900)
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
FOLDER = vc.EVIDENCE / 'captures' / (STAMP + '_' + JOB.get('label', 'review'))
FOLDER.mkdir(parents=True, exist_ok=True)
REPORT = {'success': False, 'kind': 'editor SceneCapture2D FinalColorLDR', 'map': JOB['map'], 'folder': str(FOLDER), 'images': []}


class Session:
    def __init__(self):
        self.phase = 'load'
        self.index = 0
        self.frames = 0
        self.started = time.monotonic()
        self.handle = None
        self.done = False
        self.timings = []
        self.last_tick = None
        self.original = {}

    def start(self):
        unreal.EditorPythonScripting.set_keep_python_script_alive(True)
        self.handle = unreal.register_slate_post_tick_callback(self.tick)

    def tick(self, _delta):
        if self.done:
            return
        try:
            self.step()
        except Exception:
            self.finish(traceback.format_exc())

    def setup(self):
        vc.require(vc.levels.load_level(JOB['map']), 'Cannot load ' + JOB['map'])
        self.world = vc.editor.get_editor_world()
        if JOB.get('debug_material'):
            # Review-only override of one material family; the map is not saved by this job.
            debug = unreal.load_asset(vc.ROOT_PATH + '/Materials/' + JOB['debug_material'])
            prefix = JOB.get('debug_prefix', 'M_V_Masonry')
            swapped = 0
            for actor in vc.actors.get_all_level_actors():
                for component in actor.get_components_by_class(unreal.StaticMeshComponent):
                    for index in range(component.get_num_materials()):
                        current = component.get_material(index)
                        if current is not None and current.get_name().replace('MI_V_', 'M_V_').startswith(prefix):
                            component.set_material(index, debug)
                            swapped += 1
            REPORT['debug_slots_swapped'] = swapped
        self.actor = vc.actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 2000))
        self.component = self.actor.get_component_by_class(unreal.SceneCaptureComponent2D)
        self.target = unreal.RenderingLibrary.create_render_target2d(
            self.world, WIDTH, HEIGHT, unreal.TextureRenderTargetFormat.RTF_RGBA8, unreal.LinearColor(0, 0, 0, 1), False, False)
        self.target.set_editor_property('target_gamma', 2.2)
        for field, value in [('texture_target', self.target), ('capture_every_frame', False),
                             ('capture_on_movement', False), ('always_persist_rendering_state', True),
                             ('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)]:
            self.component.set_editor_property(field, value)
        # Without an explicit bias the capture shows the map's own exposure volume, as the game does.
        self.component.set_editor_property('post_process_blend_weight', 1.0 if 'bias' in JOB else 0.0)
        settings = self.component.get_editor_property('post_process_settings')
        settings.set_editor_property('override_auto_exposure_method', True)
        settings.set_editor_property('auto_exposure_method', unreal.AutoExposureMethod.AEM_MANUAL)
        settings.set_editor_property('override_auto_exposure_apply_physical_camera_exposure', True)
        settings.set_editor_property('auto_exposure_apply_physical_camera_exposure', False)
        settings.set_editor_property('override_auto_exposure_bias', True)
        settings.set_editor_property('auto_exposure_bias', JOB.get('bias', 0.0))
        self.component.set_editor_property('post_process_settings', settings)

    # Actors the story shows only in a committed state (ApplyWorldState: installed covers in the past,
    # preserved record pages in the present). A view lists the ones it wants in show_tags.
    STATE_TAGS = ('Opening.ClinicCover', 'Opening.HarborCover', 'Opening.ClinicRecord', 'Opening.HarborRecord')

    def set_shown(self, actor, shown):
        """Mirrors the native switch: game-hidden, editor-hidden and component visibility, where a
        component the level keeps invisible (a hidden composite member) stays invisible."""
        if actor not in self.original:
            self.original[actor] = (bool(actor.get_editor_property('hidden')), [(c, bool(c.is_visible())) for c in actor.get_components_by_class(unreal.SceneComponent)])
        actor.set_actor_hidden_in_game(not shown)
        actor.set_is_temporarily_hidden_in_editor(not shown)
        for component, visible in self.original[actor][1]:
            component.set_visibility(visible and shown, False)

    def story_era(self, era):
        """Story maps: show one era through the story's own tags, as ApplyWorldState does in play."""
        show, hide = ('Opening.PastOnly', 'Opening.PresentOnly') if era == 'Past' else ('Opening.PresentOnly', 'Opening.PastOnly')
        changed = 0
        for actor in vc.actors.get_all_level_actors():
            tags = [str(t) for t in actor.get_editor_property('tags')]
            if show not in tags and hide not in tags:
                continue
            shown = show in tags and not any(t in tags for t in self.STATE_TAGS)
            self.set_shown(actor, shown)
            changed += 1
        return changed

    def restore_story_era(self):
        for actor, (hidden, components) in self.original.items():
            try:
                actor.set_actor_hidden_in_game(hidden)
                actor.set_is_temporarily_hidden_in_editor(False)
                for component, visible in components:
                    component.set_visibility(visible, False)
            except Exception:
                pass
        self.original = {}

    def show_tagged(self, tags):
        """Shows the actors a committed story state would show (installed covers, record pages)."""
        shown = 0
        for actor in vc.actors.get_all_level_actors():
            actor_tags = [str(t) for t in actor.get_editor_property('tags')]
            if any(t in actor_tags for t in tags):
                self.set_shown(actor, True)
                shown += 1
        return shown

    def apply_view(self, view):
        if JOB.get('era_mode') == 'story':
            REPORT['era_actors'] = self.story_era(view['era'])
            REPORT['era_mode'] = 'story tags Opening.PastOnly / Opening.PresentOnly (level not saved)'
            if view.get('show_tags'):
                view['shown_state_actors'] = self.show_tagged(view['show_tags'])
        elif hasattr(unreal, 'VerdantEraLibrary'):
            changed = unreal.VerdantEraLibrary.apply_era(self.world, view['era'] == 'Past')
            REPORT['era_actors'] = changed
        # 17 November 2026: a view may try light intensities by actor label ({"lights": {label: intensity}}), to
        # compare values in one launch. In memory only: this job never saves the level.
        for label, value in (view.get('lights') or {}).items():
            for actor in vc.actors.get_all_level_actors():
                if actor.get_actor_label() == label:
                    actor.get_component_by_class(unreal.LightComponent).set_intensity(float(value))
        position, target = vc.to_unreal(view['pos']), vc.to_unreal(view['target'])
        self.actor.set_actor_location(position, False, False)
        self.actor.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(position, target), False)
        self.component.set_editor_property('fov_angle', view.get('fov', 75))
        unreal.AutomationLibrary.finish_loading_before_screenshot()

    def step(self):
        if self.phase == 'load':
            self.setup()
            self.phase = 'warmup'
            self.started = time.monotonic()
        elif self.phase == 'warmup':
            # Shaders compile asynchronously; give the first view real time.
            if time.monotonic() - self.started > JOB.get('warmup_seconds', 20):
                self.phase = 'view'
        elif self.phase == 'view':
            if self.index >= len(JOB['views']):
                self.phase = 'measure'
                self.frames = 0
                self.component.set_editor_property('capture_every_frame', True)
                self.last_tick = None
                return
            self.view = JOB['views'][self.index]
            self.apply_view(self.view)
            self.frames = 0
            self.phase = 'settle'
        elif self.phase == 'settle':
            self.component.capture_scene()
            self.frames += 1
            if self.frames >= JOB.get('settle_frames', 24):
                name = '%02d_%s_%s.png' % (self.index, self.view['era'], self.view['id'])
                unreal.RenderingLibrary.export_render_target(self.world, self.target, str(FOLDER), name)
                REPORT['images'].append({'file': str(FOLDER / name), **self.view})
                vc.log('captured', name)
                if JOB.get('hdr'):
                    # 17 November 2026: also the linear scene colour (no exposure, no tonemapper), the input for
                    # tools/ldr_preview.py's estimate of the headset's untonemapped image.
                    if not hasattr(self, 'hdr_target'):
                        self.hdr_target = unreal.RenderingLibrary.create_render_target2d(
                            self.world, WIDTH // 2, HEIGHT // 2, unreal.TextureRenderTargetFormat.RTF_RGBA16F, unreal.LinearColor(0, 0, 0, 1), False, False)
                    self.component.set_editor_property('texture_target', self.hdr_target)
                    self.component.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_SCENE_COLOR_HDR)
                    self.frames = 0
                    self.phase = 'hdr'
                    return
                self.index += 1
                self.phase = 'view'
        elif self.phase == 'hdr':
            self.component.capture_scene()
            self.frames += 1
            if self.frames >= 6:
                name = '%02d_%s_%s_linear' % (self.index, self.view['era'], self.view['id'])
                unreal.RenderingLibrary.export_render_target(self.world, self.hdr_target, str(FOLDER), name)
                self.component.set_editor_property('texture_target', self.target)
                self.component.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
                self.index += 1
                self.phase = 'view'
        elif self.phase == 'measure':
            now = time.perf_counter()
            if self.last_tick is not None:
                self.timings.append((now - self.last_tick) * 1000.0)
            self.last_tick = now
            self.frames += 1
            if self.frames > JOB.get('measure_frames', 60):
                rows = sorted(self.timings[10:])
                if rows:
                    REPORT['editor_frame_ms'] = {'view': self.view['id'], 'era': self.view['era'], 'frames': len(rows),
                                                 'median': round(rows[len(rows) // 2], 2), 'p90': round(rows[int(len(rows) * .9)], 2),
                                                 'scope': 'editor tick spacing while a 1600x900 SceneCapture renders every frame offscreen; not a packaged-game benchmark'}
                self.finish(None)

    def finish(self, error):
        self.done = True
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
        REPORT['success'] = error is None
        REPORT['error'] = error
        REPORT['level_saved'] = False
        vc.write_json(vc.EVIDENCE / 'capture_report.json', REPORT)
        vc.write_json(FOLDER / 'capture_report.json', REPORT)
        vc.log('capture finished', error or 'ok', str(FOLDER))
        try:
            self.restore_story_era()
            vc.actors.destroy_actor(self.actor)
        except Exception:
            pass
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()


Session().start()
