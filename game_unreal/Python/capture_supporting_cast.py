"""Read-only native review captures of the placed supporting cast (no asset or map save).

Run with -SupportingCastCapture and a real offscreen RHI (-RenderOffscreen, not -nullrhi).
Tick driven (keep-alive) so shaders and streaming settle before the first image. Loads
Verdant_Desktop in the editor world, temporarily un-hides each owned cast actor (they are
hidden-in-game until the era presentation shows them, and a SceneCapture renders the game
view), renders a conversation-distance view and a wider context view per role, plus four
cardinal views for three roles, into output/supporting_cast/native_review/<run>/ through a
temporary SceneCapture2D. Hidden flags are restored, the capture actor is destroyed and the
level is never saved. Editor captures only: not PIE, packaged gameplay or art approval.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import math
import time
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
RELEASE = ROOT.parent
MAP = '/Game/Quest/Maps/Verdant_Desktop'
OWNER = 'Release.SupportingCastOwned'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
OUT = RELEASE / 'output' / 'supporting_cast' / 'native_review' / STAMP
REPORT_PATH = ROOT / 'supporting_cast_capture_report.json'
WANT_CARDINALS = {'cast.baker', 'cast.archivist', 'cast.clerk'}
FORWARD_ASSUMED = 90.0   # mesh forward is local +Y: the integrator places actors at (desired yaw - 90)
WARMUP_SECONDS = 25.0
SETTLE_FRAMES = 12


def require(value, message):
    if not value:
        raise RuntimeError(message)


def look_rotation(eye, target):
    d = target - eye
    yaw = math.degrees(math.atan2(d.y, d.x))
    pitch = math.degrees(math.atan2(d.z, math.hypot(d.x, d.y)))
    return unreal.Rotator(pitch=pitch, yaw=yaw, roll=0.0)


class Session:
    def __init__(self):
        self.report = {'success': False, 'run': STAMP, 'images': [], 'actors': [],
                       'scope': 'Editor-world offscreen SceneCapture2D images after shader warm-up; cast temporarily un-hidden; '
                                'not PIE/packaged gameplay or art approval.'}
        self.phase = 'load'
        self.views = []
        self.index = 0
        self.frames = 0
        self.started = time.monotonic()
        self.handle = None
        self.done = False
        self.capture_actor = None
        self.hidden_before = {}

    def start(self):
        require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'SupportingCastCapture'),
                'Explicit -SupportingCastCapture required')
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
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        require(levels.load_level(MAP), 'Cannot load map')
        self.world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        cast = [a for a in self.actors.get_all_level_actors() if a.actor_has_tag(OWNER) and a.actor_has_tag('cast.npc')]
        require(cast, 'No placed supporting cast found')
        OUT.mkdir(parents=True, exist_ok=True)
        self.target = unreal.RenderingLibrary.create_render_target2d(self.world, 1280, 960, unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                                                     unreal.LinearColor(0, 0, 0, 1), False, False)
        self.target.set_editor_property('target_gamma', 2.2)
        self.capture_actor = self.actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 1200))
        self.component = self.capture_actor.get_component_by_class(unreal.SceneCaptureComponent2D)
        for field, value in [('texture_target', self.target), ('capture_every_frame', False), ('capture_on_movement', False),
                             ('always_persist_rendering_state', True), ('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR),
                             ('post_process_blend_weight', 0.0)]:
            self.component.set_editor_property(field, value)
        for actor in cast:
            mesh = actor.get_component_by_class(unreal.SkeletalMeshComponent)
            base = actor.get_actor_location()
            tags = [str(t) for t in actor.get_editor_property('tags')]
            role_tag = next((t for t in tags if t.startswith('cast.') and t != 'cast.npc'), 'cast.unknown')
            origin, extent = actor.get_actor_bounds(False)
            measured = None
            notes = []
            try:
                toes, heels = mesh.get_socket_location('ball_l'), mesh.get_socket_location('foot_l')
                measured = [float(toes.x - heels.x), float(toes.y - heels.y), float(toes.z - heels.z)]
            except Exception as error:
                notes.append('sockets: ' + str(error))
            yaw = actor.get_actor_rotation().yaw
            chest = base + unreal.Vector(0, 0, 120)
            role = role_tag.replace('cast.', '')
            self.report['actors'].append({'role_tag': role_tag, 'label': actor.get_actor_label(), 'location': [base.x, base.y, base.z],
                                          'yaw': yaw, 'bounds_height_cm': extent.z * 2, 'bounds_bottom_z': origin.z - extent.z,
                                          'toe_minus_heel_cm': measured, 'hidden_in_game_before': bool(actor.get_editor_property('hidden')),
                                          'notes': notes})
            if role_tag in WANT_CARDINALS:
                for label, angle in [('E', 0.0), ('N', 90.0), ('W', 180.0), ('S', 270.0)]:
                    a = math.radians(angle)
                    eye = base + unreal.Vector(math.cos(a) * 280, math.sin(a) * 280, 150)
                    self.views.append((actor, role_tag, label, eye, chest, 45, '%s_cardinal_%s.png' % (role, label), base, yaw))
            intended = math.radians(yaw + FORWARD_ASSUMED)
            eye = base + unreal.Vector(math.cos(intended) * 250 + math.cos(intended + 1.2) * 60,
                                       math.sin(intended) * 250 + math.sin(intended + 1.2) * 60, 158)
            self.views.append((actor, role_tag, 'talk', eye, chest + unreal.Vector(0, 0, 20), 42, '%s_talk.png' % role, base, yaw))
            far = base + unreal.Vector(math.cos(intended) * 820, math.sin(intended) * 820, 300)
            self.views.append((actor, role_tag, 'context', far, chest, 60, '%s_context.png' % role, base, yaw))
        self.cast = cast

    def set_hidden(self, actor, hidden):
        actor.set_actor_hidden_in_game(hidden)
        for component in actor.get_components_by_class(unreal.PrimitiveComponent):
            component.set_hidden_in_game(hidden, True)

    def apply_view(self, view):
        actor, role_tag, label, eye, look_at, fov, name, base, yaw = view
        if actor not in self.hidden_before:
            self.hidden_before[actor] = bool(actor.get_editor_property('hidden'))
            self.set_hidden(actor, False)
        self.capture_actor.set_actor_location(eye, False, True)
        self.capture_actor.set_actor_rotation(look_rotation(eye, look_at), True)
        self.component.set_editor_property('fov_angle', fov)
        unreal.AutomationLibrary.finish_loading_before_screenshot()

    def step(self):
        if self.phase == 'load':
            self.setup()
            self.phase = 'warmup'
            self.started = time.monotonic()
        elif self.phase == 'warmup':
            if time.monotonic() - self.started > WARMUP_SECONDS:
                self.phase = 'view'
        elif self.phase == 'view':
            if self.index >= len(self.views):
                self.finish(None)
                return
            self.view = self.views[self.index]
            self.apply_view(self.view)
            self.frames = 0
            self.phase = 'settle'
        elif self.phase == 'settle':
            self.component.capture_scene()
            self.frames += 1
            if self.frames >= SETTLE_FRAMES:
                actor, role_tag, label, eye, look_at, fov, name, base, yaw = self.view
                unreal.RenderingLibrary.export_render_target(self.world, self.target, str(OUT), name)
                self.report['images'].append({'role_tag': role_tag, 'view': label, 'file': str(OUT / name),
                                              'eye': [eye.x, eye.y, eye.z], 'actor_location': [base.x, base.y, base.z], 'actor_yaw': yaw})
                self.index += 1
                self.phase = 'view'

    def finish(self, error):
        self.done = True
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
        try:
            for actor, hidden in self.hidden_before.items():
                self.set_hidden(actor, hidden)
            if self.capture_actor is not None:
                self.actors.destroy_actor(self.capture_actor)
        except Exception:
            self.report['cleanup_error'] = traceback.format_exc()
        self.report['success'] = error is None and 'cleanup_error' not in self.report
        if error:
            self.report['error'] = error
            unreal.log_error(error)
        self.report['level_saved'] = False
        REPORT_PATH.write_text(json.dumps(self.report, indent=2, default=str) + '\n', encoding='utf-8')
        unreal.log('SUPPORTING_CAST_CAPTURE_DONE ' + str(self.report['success']))
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()


Session().start()
