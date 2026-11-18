"""Unsaved native Mother review, in two explicitly selected camera passes.

First queue with -ReleaseCharacterCardinals. Review the four actual images.
Then queue -ReleaseCharacterReviewFront=PosX|NegX|PosY|NegY using that evidence.
The second pass captures open/blink faces and listening samples at0/1/2/3seconds.
No camera direction is inferred from Blender conventions or assumed body axes.
Full UnrealEditor with a real RHI is required. Never a gameplay/headset claim.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
import sys
import time
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
EXPECTED_PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
sys.path.insert(0, str(PROJECT / 'Python'))
import capture_brief_art as metadata_helpers

DIRECTIONS = {'PosX': (1, 0), 'NegX': (-1, 0), 'PosY': (0, 1), 'NegY': (0, -1)}
IMPORT_REPORT = PROJECT / 'release_character_import_report.json'
CARDINAL_REPORT = PROJECT / 'release_character_cardinals_report.json'
WIDTH, HEIGHT = 1920, 1080


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def xyz(v):
    return [float(v.x), float(v.y), float(v.z)]


def transform_data(t):
    return {'translation': xyz(t.translation), 'rotation_xyzw': [float(getattr(t.rotation, p)) for p in 'xyzw'], 'scale': xyz(t.scale3d)}


def native_files():
    files = list((PROJECT / 'Content').rglob('*.uasset')) + list((PROJECT / 'Content').rglob('*.umap'))
    files += list((PROJECT / 'Config').glob('*.ini')) + list(PROJECT.glob('*.uproject'))
    files += [IMPORT_REPORT, PROJECT / 'Python/capture_release_character_review.py', PROJECT / 'Python/import_release_characters.py', ROOT / 'build_release_characters.py']
    return {str(path): sha(path) for path in files if path.is_file()}


def save_files():
    roots = [PROJECT / 'Saved/SaveGames', Path(os.environ.get('LOCALAPPDATA', '')) / 'YesterdayHarbor/Saved/SaveGames']
    return {str(path): sha(path) for root in roots if root.is_dir() for path in root.rglob('*.sav')}


def exposure(settings):
    for field, value in {'auto_exposure_method': unreal.AutoExposureMethod.AEM_MANUAL,
        'auto_exposure_bias': 0.0, 'auto_exposure_apply_physical_camera_exposure': False,
        'motion_blur_amount': 0.0, 'bloom_intensity': 0.0}.items():
        settings.set_editor_property('override_' + field, True)
        settings.set_editor_property(field, value)
    return settings


class CharacterReview:
    def __init__(self):
        command = unreal.SystemLibrary.get_command_line()
        require(PROJECT == EXPECTED_PROJECT and ROOT.name == 'Release_20261026', 'Capture must use the exact protected Release project')
        require('-run=pythonscript' not in command.lower() and '-nullrhi' not in command.lower(), 'Use full UnrealEditor with a real RHI')
        match = re.search(r'(?i)(?:^|\s)-ReleaseCharacterReviewFront=(PosX|NegX|PosY|NegY)(?:\s|$)', command)
        self.front = next((key for key in DIRECTIONS if match and key.lower() == match.group(1).lower()), None)
        require(self.front or '-releasecharactercardinals' in command.lower(), 'Explicit cardinals pass or reviewed front-direction flag required')
        self.mode = 'FaceAndListening' if self.front else 'Cardinals'
        self.imported = json.loads(IMPORT_REPORT.read_text())
        require(self.imported['success'] and not self.imported['story_npcs_replaced'], 'Isolated native Mother import proof required')
        if self.front:
            prior = json.loads(CARDINAL_REPORT.read_text())
            require(prior['success'] and prior['map'] == self.imported['map'], 'Complete the actual cardinal capture before selecting a front direction')
            require(prior['import_report_sha256'] == sha(IMPORT_REPORT), 'Cardinal evidence belongs to a different native import')
            require(any(row['job']['direction'] == self.front for row in prior['images']), 'No actual cardinal image exists for this direction')
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        require(not self.level.is_in_play_in_editor(), 'Review must run outside PIE')
        self.before = native_files()
        self.saves_before = save_files()
        self.run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
        self.folder = PROJECT / 'validation/release_character_review' / self.run
        self.folder.mkdir(parents=True)
        self.path = CARDINAL_REPORT if not self.front else PROJECT / 'release_character_face_pose_report.json'
        self.report = {'success': False, 'run': self.run, 'mode': self.mode,
            'scope': 'Actual native desktop-editor character art/pose samples. Not gameplay, an uninterrupted performance, standing proof or a headset render.',
            'map': self.imported['map'], 'mesh': self.imported['mesh'], 'animation': self.imported['animation'],
            'import_report_sha256': sha(IMPORT_REPORT), 'resolution': [WIDTH, HEIGHT],
            'exposure': {'method': 'Manual', 'bias': 0.0, 'physical_camera': False, 'target_gamma': 2.2},
            'front_direction': self.front, 'front_selection': 'Explicit queued direction following actual four-cardinal review' if self.front else 'No body-front direction assumed; inspect actual images',
            'eyelid_closure_visually_verified': False, 'art_gate_passed': False,
            'blink_limit': 'Morph getters and PNG hashes do not prove visible eyelid closure; actual eye-region/geometry review is required.',
            'images': [], 'cleanup_errors': [], 'warnings': [], 'map_asset_save_calls': False,
            'story_npcs_replaced': False, 'save_profiles_written': False, 'gameplay_tested': False}
        self.jobs = ([{'id': 'FullBody_' + key, 'direction': key, 'view': 'full', 'time': 0.0, 'blink': 0.0} for key in DIRECTIONS]
            if not self.front else [
                {'id': 'FaceOpen', 'direction': self.front, 'view': 'face', 'time': 0.0, 'blink': 0.0},
                {'id': 'FaceBlink', 'direction': self.front, 'view': 'face', 'time': 0.0, 'blink': 1.0},
            ] + [{'id': 'Listening_t' + str(t), 'direction': self.front, 'view': 'full', 'time': float(t), 'blink': 0.0} for t in range(4)])
        self.index, self.frames, self.phase = 0, 0, 'load'
        self.finished, self.active, self.handle = False, False, None
        self.capture, self.target, self.component, self.mesh_component = None, None, None, None
        self.restore_cvars = {}

    def write(self):
        text = json.dumps(self.report, indent=2) + '\n'
        self.path.write_text(text)
        (self.folder / 'capture_report.json').write_text(text)

    def initialize_world(self):
        require(self.level.load_level(self.imported['map']), 'Cannot load the isolated character review map')
        self.world = self.editor.get_editor_world()
        self.actor = next((a for a in self.actors.get_all_level_actors() if a.get_name() == self.imported['actor']), None)
        require(self.actor, 'Imported review actor not found')
        self.mesh_component = self.actor.get_component_by_class(unreal.SkeletalMeshComponent)
        require(self.mesh_component.get_skeletal_mesh_asset().get_path_name() == self.imported['mesh'], 'Review actor mesh differs')
        self.animation = unreal.load_asset(self.imported['animation'])
        self.mesh_component.set_update_animation_in_editor(True)
        self.mesh_component.set_component_tick_enabled(True)
        self.mesh_component.set_editor_property('visibility_based_anim_tick_option', unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
        self.mesh_component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        self.mesh_component.play_animation(self.animation, True)
        self.mesh_component.set_play_rate(0.0)
        self.mesh_component.set_position(0.0, False)
        self.bones = [str(self.mesh_component.get_bone_name(i)) for i in range(self.mesh_component.get_num_bones())]
        require('head' in self.bones and 'spine_02' in self.bones, 'Expected imported GameEngine bones missing')
        self.blink_names = {}
        for name in ['eyeBlinkLeft', 'eyeBlinkRight']:
            matches = [n for n in self.imported['native_morph_names'] if n == name or n.endswith('_' + name)]
            require(len(matches) == 1, 'Cannot uniquely resolve actual blink morph: ' + name)
            self.blink_names[name] = matches[0]
        for name in ['t.IdleWhenNotForeground', 'Slate.bAllowThrottling']:
            old = unreal.SystemLibrary.get_console_variable_string_value(name)
            if old != '':
                self.restore_cvars[name] = old
                unreal.SystemLibrary.execute_console_command(self.world, name + ' 0')
        self.capture = self.actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(), unreal.Rotator(), True)
        self.capture.set_actor_label('Transient character review camera - NEVER SAVE')
        self.component = self.capture.get_component_by_class(unreal.SceneCaptureComponent2D)
        self.target = unreal.RenderingLibrary.create_render_target2d(self.world, WIDTH, HEIGHT,
            unreal.TextureRenderTargetFormat.RTF_RGBA8, unreal.LinearColor(0, 0, 0, 1), False, False)
        self.target.set_editor_property('target_gamma', 2.2)
        for field, value in {'texture_target': self.target, 'capture_every_frame': False, 'capture_on_movement': False,
                             'always_persist_rendering_state': True, 'capture_source': unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR}.items():
            self.component.set_editor_property(field, value)
        self.component.set_editor_property('post_process_settings', exposure(self.component.get_editor_property('post_process_settings')))
        self.component.set_editor_property('post_process_blend_weight', 1.0)
        self.report['bone_names'] = self.bones
        self.report['actual_blink_morph_names'] = self.blink_names
        self.report['runtime_metadata'] = metadata_helpers.ArtCapture.metadata(self)
        self.phase = 'configure'

    def set_sample(self):
        job = self.jobs[self.index]
        self.mesh_component.set_position(job['time'], False)
        for name in self.blink_names.values():
            self.mesh_component.set_morph_target(unreal.Name(name), job['blink'], False)

    def configure(self):
        if self.index >= len(self.jobs):
            return self.finish()
        self.current = self.jobs[self.index]
        self.set_sample()
        direction = DIRECTIONS[self.current['direction']]
        if self.current['view'] == 'full':
            origin = self.imported['actor_bounds_cm']['origin']
            target = unreal.Vector(*origin)
            distance, fov = 400.0, 48.0
        else:
            head = self.mesh_component.get_socket_transform(unreal.Name('head'), unreal.RelativeTransformSpace.RTS_WORLD).translation
            target = head + unreal.Vector(0, 0, 4)
            distance, fov = 85.0, 36.0
        position = target + unreal.Vector(direction[0] * distance, direction[1] * distance, 0)
        self.capture.set_actor_location(position, False, False)
        self.capture.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(position, target), False)
        self.component.set_editor_property('fov_angle', fov)
        self.camera = {'position_cm': xyz(position), 'target_cm': xyz(target), 'horizontal_fov': fov,
                       'cinematic_only': True, 'body_axis_assumed': False}
        self.frames, self.started = 0, time.monotonic()
        self.phase = 'warm'
        self.write()

    def snapshot(self):
        result = {'animation_position_seconds': float(self.mesh_component.get_position()),
            'play_rate': float(self.mesh_component.get_play_rate()),
            'morph_override_readback': {name: float(self.mesh_component.get_morph_target(unreal.Name(actual))) for name, actual in self.blink_names.items()},
            'bones_component_space': {name: transform_data(self.mesh_component.get_socket_transform(unreal.Name(name), unreal.RelativeTransformSpace.RTS_COMPONENT)) for name in self.bones}}
        require(abs(result['animation_position_seconds'] - self.current['time']) < 1e-4, 'Actual animation position differs from requested sample')
        require(all(abs(value - self.current['blink']) < 1e-5 for value in result['morph_override_readback'].values()), 'Blink override readback differs')
        return result

    def export(self):
        pose = self.snapshot()
        file = self.folder / (self.current['id'] + '.png')
        unreal.RenderingLibrary.export_render_target(self.world, self.target, str(self.folder), file.name)
        require(file.is_file() and file.stat().st_size > 10000, 'Native image export failed')
        self.report['images'].append({'job': self.current, 'camera': self.camera, 'actual_pose': pose,
            'path': str(file), 'sha256': sha(file), 'bytes': file.stat().st_size, 'warm_frames': self.frames})
        self.index += 1
        self.phase = 'configure'
        self.write()

    def verify_pose_changes(self):
        if not self.front:
            return {'tested': False, 'reason': 'Cardinal camera orientation review only'}
        rows = {image['job']['id']: image for image in self.report['images']}
        hashes_differ = rows['FaceOpen']['sha256'] != rows['FaceBlink']['sha256']
        base = rows['Listening_t0']['actual_pose']['bones_component_space']
        changes = []
        for t in range(1, 4):
            pose = rows['Listening_t' + str(t)]['actual_pose']['bones_component_space']
            max_translation, max_rotation = 0.0, 0.0
            for name in base:
                max_translation = max(max_translation, math.sqrt(sum((a - b) ** 2 for a, b in zip(base[name]['translation'], pose[name]['translation']))))
                # q and -q represent the same rotation.
                a, b = base[name]['rotation_xyzw'], pose[name]['rotation_xyzw']
                rotation = min(math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))), math.sqrt(sum((x + y) ** 2 for x, y in zip(a, b))))
                max_rotation = max(max_rotation, rotation)
            changes.append({'time_seconds': t, 'max_bone_translation_delta_cm': max_translation, 'max_quaternion_delta': max_rotation})
        require(any(row['max_bone_translation_delta_cm'] > 1e-3 or row['max_quaternion_delta'] > 1e-5 for row in changes), 'Actual component-space bones did not change across listening samples')
        return {'tested': True, 'open_blink_file_hashes_differ': hashes_differ,
                'hash_difference_is_blink_proof': False, 'eyelid_closure_visually_verified': False,
                'listening_sample_deltas': changes,
                'limit': 'Discrete bone pose samples only; actual visible eyelid closure, continuous performance and retarget quality remain unproven.'}

    def finish(self, error=None):
        if self.finished:
            return
        self.finished = True
        if error:
            self.report['error'] = error
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
        try:
            if not error:
                self.report['pose_checks'] = self.verify_pose_changes()
        except Exception:
            self.report['error'] = traceback.format_exc()
        try:
            if self.capture:
                self.actors.destroy_actor(self.capture)
            if self.target:
                unreal.RenderingLibrary.release_render_target2d(self.target)
            for name, value in self.restore_cvars.items():
                unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), name + ' ' + value)
            require(self.level.load_level(self.imported['map']), 'Could not reload saved map for cleanup')
            self.report['saved_map_reloaded_for_cleanup'] = True
        except Exception:
            self.report['cleanup_errors'].append(traceback.format_exc())
        changed = [path for path, digest in self.before.items() if not Path(path).is_file() or sha(path) != digest]
        current_native = native_files()
        added_native = sorted(set(current_native) - set(self.before))
        current_saves = save_files()
        self.report.update(protected_native_files_unchanged=not changed and not added_native,
            unexpected_native_changes=changed, unexpected_native_files=added_native,
            existing_saves_unchanged=current_saves == self.saves_before, protected_sha256=self.before,
            runtime_metadata=metadata_helpers.ArtCapture.metadata(self), required_images=len(self.jobs))
        self.report['success'] = not self.report.get('error') and not self.report['cleanup_errors'] and not changed and not added_native and current_saves == self.saves_before and len(self.report['images']) == len(self.jobs)
        self.write()
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()

    def tick(self, delta):
        if self.active or self.finished:
            return
        self.active = True
        try:
            if self.phase == 'load':
                self.initialize_world()
            elif self.phase == 'configure':
                self.configure()
            elif self.phase == 'warm':
                self.set_sample()
                # UE5.8 LevelEditorSubsystem.h declares this BlueprintCallable API.
                self.level.editor_invalidate_viewports()
                self.component.capture_scene()
                self.frames += 1
                if self.frames >= 45 and time.monotonic() - self.started >= 2.0:
                    # Same API used by the already successful native art captures;
                    # AutomationBlueprintFunctionLibrary.h80 declares this method.
                    unreal.AutomationLibrary.finish_loading_before_screenshot()
                    self.component.capture_scene()
                    self.export()
        except Exception:
            self.finish(traceback.format_exc())
        finally:
            self.active = False

    def start(self):
        unreal.EditorPythonScripting.set_keep_python_script_alive(True)
        self.write()
        self.handle = unreal.register_slate_post_tick_callback(self.tick)


if __name__ == '__main__':
    session = None
    try:
        session = CharacterReview()
        session.start()
    except Exception:
        error = traceback.format_exc()
        if session:
            session.finish(error)
        else:
            (PROJECT / 'release_character_capture_setup_error.json').write_text(json.dumps({'success': False, 'error': error}, indent=2))
            unreal.log_error(error)
            unreal.EditorPythonScripting.set_keep_python_script_alive(False)
            unreal.SystemLibrary.quit_editor()
