"""Transient PIE character art/motion samples, never story gameplay or S07.

Uses a normally ticking game-world skeletal component. Listening samples are
paused individually for camera warming. Open/blink samples run at play rate0
with explicit morph overrides. No unreflected bone-refresh calls are used.
Every image and measured pose still requires actual visual review.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import sys
import time
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
SOURCE_PATH = Path(__file__).resolve()  # ExecutePythonScript deletes __file__ before later Slate callbacks.
sys.path.insert(0, str(PROJECT / 'Python'))
import capture_release_character_review as review
import diagnose_release_character_animation as diagnostic
import capture_brief_art as metadata


class PIEReview:
    def __init__(self):
        review.require(PROJECT == SOURCE_PATH.parents[1] and PROJECT.parent.name == 'Release_20261026', 'Exact Release project required')
        command = unreal.SystemLibrary.get_command_line()
        review.require('-nullrhi' not in command.lower() and '-run=pythonscript' not in command.lower(), 'Full UnrealEditor with a real RHI required')
        match = re.search(r'(?i)(?:^|\s)-ReleaseCharacterReviewFront=(PosX|NegX|PosY|NegY)(?:\s|$)', command)
        self.front = next((n for n in review.DIRECTIONS if match and n.lower() == match.group(1).lower()), None)
        review.require(self.front, 'Actual cardinal-reviewed front direction flag required')
        self.imported = json.loads(review.IMPORT_REPORT.read_text())
        cardinals = json.loads(review.CARDINAL_REPORT.read_text())
        review.require(self.imported['success'] and cardinals['success'] and cardinals['import_report_sha256'] == review.sha(review.IMPORT_REPORT), 'Matching native import/cardinal evidence required')
        raw_path = PROJECT / 'release_character_animation_diagnostic.json'
        raw = json.loads(raw_path.read_text())
        review.require(raw['success'] and raw['import_report_sha256'] == review.sha(review.IMPORT_REPORT), 'Run the native raw animation diagnostic first')
        review.require(raw['findings']['native_source_or_raw_tracks_change'], 'Native raw animation data is static; repair export/import first')
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        review.require(not self.level.is_in_play_in_editor(), 'PIE must start stopped')
        self.before, self.saved_before = review.native_files(), review.save_files()
        self.source_path, self.source_sha = SOURCE_PATH, review.sha(SOURCE_PATH)
        self.run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
        self.folder = PROJECT / 'validation/release_character_pie' / self.run
        self.folder.mkdir(parents=True)
        self.report = {'success': False, 'run': self.run,
            'scope': 'Native transient PIE character art/pose samples, with deliberate pauses between samples. Not uninterrupted gameplay, S07, gait, production idle, standing or headset proof.',
            'import_report_sha256': review.sha(review.IMPORT_REPORT), 'raw_diagnostic_sha256': review.sha(raw_path),
            'map': self.imported['map'], 'mesh': self.imported['mesh'], 'animation': self.imported['animation'],
            'resolution': [review.WIDTH, review.HEIGHT], 'front_direction': self.front,
            'exposure': {'method': 'Manual', 'bias': 0.0, 'physical_camera': False, 'target_gamma': 2.2},
            'images': [], 'cleanup_errors': [], 'checkpoints': [], 'secondary_errors': [],
            'asset_map_save_calls': False, 'story_npcs_replaced': False,
            'eyelid_closure_visually_verified': False, 'face_pixel_review_required': True,
            'art_gate_passed': False, 'notes': ['Morph getter values and PNG hashes are not visible blink proof.']}
        self.jobs = [{'id': 'Listening_t' + str(s), 'time': s, 'view': 'full'} for s in range(4)] + [
            {'id': 'FaceOpen', 'blink': 0.0, 'view': 'face'}, {'id': 'FaceBlink', 'blink': 1.0, 'view': 'face'}]
        self.index, self.phase, self.handle = 0, 'load', None
        self.active, self.finished, self.closing, self.cleanup_started = False, False, False, False
        self.target, self.capture = None, None
        self.deadline = time.monotonic() + 120
        self.camera_tag = 'TOSOY.UnsavedPIEReviewCamera.' + self.run

    def write(self):
        text = json.dumps(self.report, indent=2) + '\n'
        (self.folder / 'capture_report.json').write_text(text)
        (PROJECT / 'release_character_pie_review_report.json').write_text(text)

    def safe_write(self):
        try:
            self.write()
        except Exception:
            error = traceback.format_exc()
            self.report['secondary_errors'].append({'operation': 'write_report', 'error': error})
            unreal.log_error('RELEASE_CHARACTER_PIE_REPORT_WRITE_FAILED ' + error)

    def checkpoint(self, label, **details):
        self.report['last_checkpoint'] = label
        self.report['phase'] = self.phase
        self.report['checkpoints'].append({'label': label, 'phase': self.phase, 'wall_monotonic': time.monotonic(), **details})
        unreal.log('RELEASE_CHARACTER_PIE_CHECKPOINT ' + label)
        self.safe_write()

    def initialize_pie(self):
        self.checkpoint('initialize_game_world')
        self.world = self.editor.get_game_world()
        review.require(self.world, 'PIE world unavailable')
        self.checkpoint('hide_only_temporary_default_review_pawns')
        mode = unreal.GameplayStatics.get_game_mode(self.world)
        review.require(mode and mode.get_class().get_path_name() == '/Script/Engine.GameModeBase',
                       'Only the temporary GameModeBase review world may hide its default pawn')
        hidden_pawns = []
        for pawn in unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.DefaultPawn):
            review.require(pawn.get_class().get_path_name() == '/Script/Engine.DefaultPawn',
                           'Preserving an unexpected derived/story pawn in the review world')
            before = {'hidden_in_game': bool(pawn.get_editor_property('hidden')),
                      'collision_enabled': bool(pawn.get_actor_enable_collision())}
            pawn.set_actor_hidden_in_game(True)
            pawn.set_actor_enable_collision(False)
            after = {'hidden_in_game': bool(pawn.get_editor_property('hidden')),
                     'collision_enabled': bool(pawn.get_actor_enable_collision())}
            review.require(after['hidden_in_game'] and not after['collision_enabled'], 'Temporary review pawn remained visible/collidable')
            hidden_pawns.append({'actor': pawn.get_path_name(), 'class': pawn.get_class().get_path_name(),
                                 'before': before, 'after': after})
        self.report['hidden_temporary_review_pawns'] = hidden_pawns
        self.report['hidden_pawn_scope'] = 'Only exact Engine.DefaultPawn instances in the unsaved Engine.GameModeBase PIE review world; discarded when PIE ends.'
        self.checkpoint('find_game_world_mother', world=self.world.get_path_name())
        actors = unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.SkeletalMeshActor)
        candidates = [a for a in actors if a.get_component_by_class(unreal.SkeletalMeshComponent).get_skeletal_mesh_asset().get_path_name() == self.imported['mesh']]
        review.require(len(candidates) == 1, 'PIE must contain exactly one imported Mother')
        self.actor = candidates[0]
        self.mesh_component = self.actor.get_component_by_class(unreal.SkeletalMeshComponent)
        self.checkpoint('enable_game_world_mesh_tick', actor=self.actor.get_path_name())
        self.mesh_component.set_component_tick_enabled(True)
        self.mesh_component.set_editor_property('visibility_based_anim_tick_option', unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
        self.mesh_component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        self.checkpoint('play_native_animation_rate1')
        self.mesh_component.play_animation(unreal.load_asset(self.imported['animation']), True)
        self.mesh_component.set_play_rate(1.0)
        self.bones = [str(self.mesh_component.get_bone_name(i)) for i in range(self.mesh_component.get_num_bones())]
        self.blink_names = {}
        for name in ['eyeBlinkLeft', 'eyeBlinkRight']:
            matches = [n for n in self.imported['native_morph_names'] if n == name or n.endswith('_' + name)]
            review.require(len(matches) == 1, 'Ambiguous actual blink morph: ' + name)
            self.blink_names[name] = matches[0]
        self.checkpoint('resolve_duplicated_unsaved_camera')
        cameras = [a for a in unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.SceneCapture2D)
                   if a.actor_has_tag(unreal.Name(self.camera_tag))]
        review.require(len(cameras) == 1, 'Expected the one unsaved editor camera duplicated into PIE')
        self.capture = cameras[0]
        self.checkpoint('create_game_world_render_target', camera=self.capture.get_path_name())
        self.component = self.capture.get_component_by_class(unreal.SceneCaptureComponent2D)
        self.target = unreal.RenderingLibrary.create_render_target2d(self.world, review.WIDTH, review.HEIGHT,
            unreal.TextureRenderTargetFormat.RTF_RGBA8, unreal.LinearColor(0, 0, 0, 1), False, False)
        self.target.set_editor_property('target_gamma', 2.2)
        for field, value in {'texture_target': self.target, 'capture_every_frame': False, 'capture_on_movement': False,
            'always_persist_rendering_state': True, 'capture_source': unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR}.items():
            self.component.set_editor_property(field, value)
        self.component.set_editor_property('post_process_settings', review.exposure(self.component.get_editor_property('post_process_settings')))
        self.component.set_editor_property('post_process_blend_weight', 1.0)
        self.report['actual_blink_morph_names'] = self.blink_names
        self.report['runtime_metadata'] = metadata.ArtCapture.metadata(self)
        self.motion_started = unreal.GameplayStatics.get_time_seconds(self.world)
        self.phase = 'await_sample'
        self.checkpoint('game_world_capture_ready', motion_start_world_time=self.motion_started)

    def camera(self, job):
        direction = review.DIRECTIONS[self.front]
        if job['view'] == 'full':
            target, distance, fov = unreal.Vector(*self.imported['actor_bounds_cm']['origin']), 400.0, 48.0
        else:
            head = self.mesh_component.get_socket_transform(unreal.Name('head'), unreal.RelativeTransformSpace.RTS_WORLD).translation
            target, distance, fov = head + unreal.Vector(0, 0, 4), 85.0, 36.0
        position = target + unreal.Vector(direction[0] * distance, direction[1] * distance, 0)
        self.capture.set_actor_location(position, False, False)
        self.capture.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(position, target), False)
        self.component.set_editor_property('fov_angle', fov)
        self.camera_data = {'position_cm': review.xyz(position), 'target_cm': review.xyz(target), 'horizontal_fov': fov, 'cinematic_only': True}

    def pose(self):
        return {'world_game_time': float(unreal.GameplayStatics.get_time_seconds(self.world)),
            'world_paused': bool(unreal.GameplayStatics.is_game_paused(self.world)),
            'animation_position_seconds': float(self.mesh_component.get_position()),
            'play_rate': float(self.mesh_component.get_play_rate()),
            'bones_component_space': {n: review.transform_data(self.mesh_component.get_socket_transform(unreal.Name(n), unreal.RelativeTransformSpace.RTS_COMPONENT)) for n in self.bones},
            'morph_override_readback': {n: float(self.mesh_component.get_morph_target(unreal.Name(actual))) for n, actual in self.blink_names.items()}}

    def prepare_sample(self):
        if self.index >= len(self.jobs):
            return self.finish()
        self.current = self.jobs[self.index]
        if self.current['view'] == 'full':
            if unreal.GameplayStatics.get_time_seconds(self.world) - self.motion_started < self.current['time']:
                return
            review.require(unreal.GameplayStatics.set_game_paused(self.world, True), 'Could not pause only the transient art-review world')
        else:
            unreal.GameplayStatics.set_game_paused(self.world, False)
            self.mesh_component.set_play_rate(0.0)
            self.mesh_component.set_position(0.0, False)
        self.camera(self.current)
        self.frames, self.warm_started = 0, time.monotonic()
        self.phase = 'warm'
        self.checkpoint('warm_sample', job=self.current, pose=self.pose())

    def export(self):
        actual = self.pose()
        file = self.folder / (self.current['id'] + '.png')
        unreal.RenderingLibrary.export_render_target(self.world, self.target, str(self.folder), file.name)
        review.require(file.is_file() and file.stat().st_size > 10000, 'Native PIE image export failed')
        self.report['images'].append({'job': self.current, 'camera': self.camera_data, 'actual_pose': actual,
            'path': str(file), 'sha256': review.sha(file), 'bytes': file.stat().st_size, 'warm_frames': self.frames})
        if self.current['view'] == 'full':
            unreal.GameplayStatics.set_game_paused(self.world, False)
        self.index += 1
        self.phase = 'await_sample'
        self.checkpoint('image_exported', path=str(file))

    def finish(self, error=None):
        # Preserve the first traceback before any cleanup call can fail or pump Slate.
        if error:
            if not self.report.get('error'):
                self.report['error'] = error
                self.report['failure_phase'] = self.phase
                self.report['failure_checkpoint'] = self.report.get('last_checkpoint')
                unreal.log_error('RELEASE_CHARACTER_PIE_FIRST_FAILURE ' + error)
            else:
                self.report['secondary_errors'].append({'operation': self.phase, 'error': error})
            self.safe_write()
        if self.closing:
            return
        self.closing = True
        if not error:
            try:
                poses = [r['actual_pose']['bones_component_space'] for r in self.report['images'] if r['job']['view'] == 'full']
                changes = [diagnostic.compare(poses[0], pose) for pose in poses[1:]]
                self.report['motion_changed_bones'] = sorted({n for row in changes for n, d in row.items() if d['changed']})
                self.report['motion_deltas'] = changes
                review.require(self.report['motion_changed_bones'], 'Actual normally-ticking PIE bone transforms did not change')
            except Exception:
                self.report['error'] = traceback.format_exc()
                self.report['failure_phase'] = 'verify_actual_pie_motion'
                self.report['failure_checkpoint'] = self.report.get('last_checkpoint')
                unreal.log_error('RELEASE_CHARACTER_PIE_MOTION_FAILURE ' + self.report['error'])
        self.phase = 'cleanup'
        self.cleanup_deadline = time.monotonic() + 15
        self.checkpoint('finish_begin_cleanup')
        try:
            if self.target:
                unreal.RenderingLibrary.release_render_target2d(self.target)
        except Exception:
            self.report['cleanup_errors'].append({'operation': 'release_target', 'error': traceback.format_exc()})
            self.safe_write()
        finally:
            try:
                if self.level.is_in_play_in_editor():
                    self.level.editor_request_end_play()
            except Exception:
                self.report['cleanup_errors'].append({'operation': 'request_end_pie', 'error': traceback.format_exc()})
                self.safe_write()

    def cleanup(self):
        if self.cleanup_started:
            return
        try:
            still_playing = self.level.is_in_play_in_editor()
        except Exception:
            still_playing = False
            self.report['cleanup_errors'].append({'operation': 'query_pie_state', 'error': traceback.format_exc()})
        if still_playing and time.monotonic() < self.cleanup_deadline:
            return
        # One attempt only. Disable callback before level reload/hash/report operations.
        self.cleanup_started, self.finished = True, True
        self.report['cleanup_attempts'] = 1
        try:
            try:
                if self.handle is not None:
                    unreal.unregister_slate_post_tick_callback(self.handle)
                    self.handle = None
                self.checkpoint('cleanup_callback_unregistered')
                review.require(not self.level.is_in_play_in_editor(), 'PIE did not stop within the cleanup deadline')
                review.require(self.level.load_level(self.imported['map']), 'Could not reload the saved isolated map')
                self.report['saved_map_reloaded_once'] = True
            except Exception:
                self.report['cleanup_errors'].append({'operation': 'stop_pie_reload_once', 'error': traceback.format_exc()})
            finally:
                try:
                    after, saved_after = review.native_files(), review.save_files()
                    self.report['guards'] = {'native_assets_config_sources_unchanged': self.before == after,
                        'saved_games_unchanged': self.saved_before == saved_after,
                        'capture_source_unchanged': self.source_sha == review.sha(self.source_path)}
                except Exception:
                    self.report['cleanup_errors'].append({'operation': 'hash_guards', 'error': traceback.format_exc()})
                self.report['success'] = (not self.report.get('error') and not self.report['cleanup_errors']
                    and bool(self.report.get('guards')) and all(self.report['guards'].values())
                    and len(self.report['images']) == len(self.jobs))
                self.report['phase'] = 'complete'
                self.safe_write()
        finally:
            try:
                unreal.EditorPythonScripting.set_keep_python_script_alive(False)
            finally:
                unreal.SystemLibrary.quit_editor()

    def tick(self, delta):
        if self.active or self.finished:
            return
        self.active = True
        try:
            if self.phase == 'cleanup':
                self.cleanup()
            elif time.monotonic() > self.deadline:
                raise TimeoutError('Transient PIE character review timed out')
            elif self.phase == 'load':
                self.checkpoint('load_saved_review_map')
                review.require(self.level.load_level(self.imported['map']), 'Cannot load isolated review map')
                world = self.editor.get_editor_world()
                world.get_world_settings().set_editor_property('default_game_mode', unreal.GameModeBase.static_class())
                self.report['unsaved_game_mode_override'] = '/Script/Engine.GameModeBase: prevents story game-mode startup; discarded after PIE'
                self.checkpoint('spawn_unsaved_editor_camera_for_pie_copy')
                actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                editor_camera = actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(), unreal.Rotator(), False)
                review.require(editor_camera, 'Cannot create unsaved editor review camera')
                editor_camera.set_actor_label('UNSAVED Mother PIE capture camera - discard on reload')
                editor_camera.set_editor_property('tags', [unreal.Name(self.camera_tag)])
                self.checkpoint('request_begin_pie', unsaved_camera=editor_camera.get_path_name())
                self.level.editor_request_begin_play()
                self.phase = 'waiting_pie'
            elif self.phase == 'waiting_pie':
                if self.editor.get_game_world() and self.level.is_in_play_in_editor():
                    self.initialize_pie()
            elif self.phase == 'await_sample':
                self.prepare_sample()
            elif self.phase == 'warm':
                if self.current['view'] == 'face':
                    for actual in self.blink_names.values():
                        self.mesh_component.set_morph_target(unreal.Name(actual), self.current['blink'], False)
                self.component.capture_scene()
                self.frames += 1
                if self.frames >= 45 and time.monotonic() - self.warm_started >= 2.0:
                    unreal.AutomationLibrary.finish_loading_before_screenshot()
                    self.component.capture_scene()
                    self.export()
        except Exception:
            self.finish(traceback.format_exc())
        finally:
            self.active = False

    def start(self):
        unreal.EditorPythonScripting.set_keep_python_script_alive(True)
        self.checkpoint('start')
        self.handle = unreal.register_slate_post_tick_callback(self.tick)


if __name__ == '__main__':
    try:
        session = PIEReview()
        session.start()
    except Exception:
        (PROJECT / 'release_character_pie_setup_error.json').write_text(json.dumps({'success': False, 'error': traceback.format_exc()}, indent=2))
        unreal.SystemLibrary.quit_editor()
