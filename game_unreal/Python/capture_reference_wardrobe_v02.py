"""Queued, unsaved PIE wardrobe cardinal/motion images in its isolated map.

-ReferenceWardrobeNativeManifest="absolute native manifest"
-ReferenceWardrobeReviewMode=Cardinals|Motion
Motion additionally needs an explicitly visually selected
-ReleaseCharacterReviewFront=PosX|NegX|PosY|NegY after this candidate's cardinals.
No current NPC, floor, save or motion binding is edited. No native asset is saved.
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
ROOT = PROJECT.parent
SOURCE = Path(__file__).resolve()
sys.path.insert(0, str(PROJECT / 'Python'))
sys.path.insert(0, str(ROOT / 'tools'))
import windows_file_guards as io
import capture_release_character_pie as base
import capture_release_character_review as review
import diagnose_release_character_animation as diagnostic
import release_mother_integration as native_rig


def read(path):
    with open(io.io_path(path), encoding='utf-8') as stream:
        return json.load(stream)


def write(path, data):
    with open(io.io_path(path), 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def protected():
    result = io.native(PROJECT)
    for path in list(PROJECT.glob('release*.json')) + [SOURCE, Path(base.__file__), Path(review.__file__)]:
        result[str(path)] = io.sha(path)
    return result


# The shared rendering/lifecycle harness resolves these functions at callback
# time. Only this fresh, isolated writer process sees the extended hash helper.
review.sha = io.sha
review.native_files = protected


class WardrobeReview(base.PIEReview):
    def __init__(self):
        review.require(PROJECT == SOURCE.parents[1] and ROOT.name == 'Release_20261026', 'Exact Release project required')
        command = unreal.SystemLibrary.get_command_line()
        review.require('-nullrhi' not in command.lower() and '-run=' not in command.lower(), 'Full editor with actual RHI required')
        match = re.search(r'(?i)(?:^|\s)-ReferenceWardrobeNativeManifest=(?:"([^"]+)"|(\S+))', command)
        review.require(match, 'Explicit successful native v02 wardrobe report required')
        self.native_path = Path(match.group(1) or match.group(2)).resolve()
        review.require(self.native_path.is_relative_to(ROOT / 'output/reference_wardrobe_v02'), 'New wardrobe native report required')
        native = read(self.native_path)
        review.require(native['success'] and native['native_executed'] and all(native['guards'].values()), 'Successful guarded native import required')
        self.role = native['character']
        self.imported = native['candidate']
        review.require(self.imported['character'] == self.role and not self.imported['story_npcs_replaced'], 'Matching isolated role candidate required')
        for path, digest in native['owned_asset_sha256'].items():
            review.require(io.sha(path) == digest, 'Preserving a changed native wardrobe asset: ' + path)
        mode = re.search(r'(?i)(?:^|\s)-ReferenceWardrobeReviewMode=(Cardinals|Motion)(?:\s|$)', command)
        review.require(mode, 'Choose Cardinals, then Motion after actual image review')
        self.mode = mode.group(1).title()
        front = re.search(r'(?i)(?:^|\s)-ReleaseCharacterReviewFront=(PosX|NegX|PosY|NegY)(?:\s|$)', command)
        self.front = next((key for key in review.DIRECTIONS if front and key.lower() == front.group(1).lower()), None)
        self.role_root = ROOT / 'output/reference_wardrobe_v02' / self.role
        if self.mode == 'Motion':
            review.require(self.front, 'Explicit visually reviewed cardinal front required for motion/face samples')
            pointer = read(self.role_root / 'cardinals_latest.json')
            cardinals = read(pointer['manifest'])
            review.require(cardinals['success'] and cardinals['native_manifest_sha256'] == io.sha(self.native_path), 'Cardinal evidence belongs to a different candidate')
            review.require({row['job']['direction'] for row in cardinals['images']} == set(review.DIRECTIONS), 'Complete actual cardinal images required')
            for image in cardinals['images']:
                review.require(io.sha(image['path']) == image['sha256'], 'A cardinal image changed after capture')
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        review.require(not self.level.is_in_play_in_editor(), 'Start outside PIE')
        self.before, self.saved_before = protected(), review.save_files()
        self.source_path, self.source_sha = SOURCE, io.sha(SOURCE)
        self.run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
        self.folder = self.role_root / 'reviews' / self.run
        self.folder.mkdir(parents=True, exist_ok=False)
        self.report = {'success': False, 'native_executed': True, 'character': self.role, 'run': self.run, 'mode': self.mode,
            'scope': 'Actual isolated unsaved PIE wardrobe images and deliberate phase poses; not continuous gameplay, foot planting, cloth simulation, final likeness or performance proof.',
            'native_manifest': str(self.native_path), 'native_manifest_sha256': io.sha(self.native_path),
            'map': self.imported['map'], 'mesh': self.imported['mesh'], 'animation': self.imported['animation'],
            'resolution': [review.WIDTH, review.HEIGHT], 'front_direction': self.front,
            'exposure': {'method': 'Manual', 'bias': 0.0, 'physical_camera': False, 'target_gamma': 2.2},
            'images': [], 'cleanup_errors': [], 'checkpoints': [], 'secondary_errors': [],
            'asset_map_save_calls': False, 'story_npcs_replaced': False, 'floor_bindings_changed': False,
            'motion_bindings_changed': False, 'save_profiles_written': False,
            'art_gate_passed': False, 'gait_visually_approved': False, 'eyelid_closure_visually_verified': False,
            'exact_reference_likeness_claimed': False, 'remaining_reference_gaps': native['remaining_reference_gaps']}
        if self.mode == 'Cardinals':
            self.jobs = [{'id': 'FullBody_' + key, 'direction': key, 'view': 'full', 'clip': 'idle', 'fraction': 0.0}
                         for key in review.DIRECTIONS]
        else:
            self.jobs = [{'id': 'Listening_' + angle, 'angle': angle, 'view': 'full', 'clip': 'idle', 'fraction': 0.0}
                         for angle in ['front', 'profile', 'rear']]
            self.jobs += [{'id': 'Listening_t' + str(second), 'angle': 'front', 'view': 'full', 'clip': 'idle', 'fraction': second/4.0}
                          for second in [1, 2, 3]]
            if self.imported.get('walk'):
                self.jobs += [{'id': 'Walk_' + angle + '_phase' + str(phase), 'angle': angle, 'view': 'full',
                               'clip': 'walk', 'fraction': phase/4.0}
                              for phase in range(4) for angle in ['front', 'profile', 'rear']]
            self.jobs += [{'id': 'FaceOpen', 'angle': 'front', 'view': 'face', 'clip': 'idle', 'fraction': 0.0, 'blink': 0.0},
                          {'id': 'FaceBlink', 'angle': 'front', 'view': 'face', 'clip': 'idle', 'fraction': 0.0, 'blink': 1.0}]
        self.index, self.phase, self.handle = 0, 'load', None
        self.active, self.finished, self.closing, self.cleanup_started = False, False, False, False
        self.target, self.capture = None, None
        self.deadline = time.monotonic() + 300
        self.camera_tag = 'TOSOY.UnsavedV02WardrobeReview.' + self.run

    def write(self):
        write(self.folder / 'capture_report.json', self.report)
        if self.report.get('success'):
            write(self.role_root / (self.mode.lower() + '_latest.json'),
                  {'run': self.run, 'manifest': str(self.folder / 'capture_report.json')})

    def initialize_pie(self):
        super().initialize_pie()
        mesh = self.mesh_component.get_skeletal_mesh_asset()
        self.report['native_unit_reference'] = native_rig.unit_reference(mesh)
        self.clips = {'idle': unreal.load_asset(self.imported['animation'])}
        if self.imported.get('walk'):
            self.clips['walk'] = unreal.load_asset(self.imported['walk'])
        for key, clip in self.clips.items():
            review.require(clip and clip.get_editor_property('skeleton') == mesh.get_editor_property('skeleton'),
                           'Refusing a clip from another skeleton: ' + key)
        self.report['clips'] = {key: clip.get_path_name() for key, clip in self.clips.items()}
        self.report['clothing_assets'] = [asset.get_path_name() for asset in mesh.get_editor_property('mesh_clothing_assets')]
        self.report['cloth_simulation_claimed'] = False
        self.report['actor_transform_before'] = review.transform_data(self.actor.get_actor_transform())
        self.start_location = review.xyz(self.actor.get_actor_location())

    def prepare_sample(self):
        if self.index >= len(self.jobs):
            return self.finish()
        self.current = self.jobs[self.index]
        unreal.GameplayStatics.set_game_paused(self.world, False)
        clip = self.clips[self.current['clip']]
        self.mesh_component.play_animation(clip, True)
        self.mesh_component.set_play_rate(0.0)
        self.mesh_component.set_position(float(clip.get_play_length()) * self.current['fraction'], False)
        for actual in self.blink_names.values():
            self.mesh_component.set_morph_target(unreal.Name(actual), self.current.get('blink', 0.0), False)
        self.camera(self.current)
        self.frames, self.warm_started = 0, time.monotonic()
        self.phase = 'warm'
        self.checkpoint('warm_explicit_pose_sample', job=self.current)

    def camera(self, job):
        if job['view'] == 'face':
            return base.PIEReview.camera(self, job)
        if self.mode == 'Cardinals':
            direction = review.DIRECTIONS[job['direction']]
        else:
            front = review.DIRECTIONS[self.front]
            direction = {'front': front, 'profile': (-front[1], front[0]), 'rear': (-front[0], -front[1])}[job['angle']]
        target = unreal.Vector(*self.imported['actor_bounds_cm']['origin'])
        position = target + unreal.Vector(direction[0]*400, direction[1]*400, 0)
        self.capture.set_actor_location(position, False, False)
        self.capture.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(position, target), False)
        self.component.set_editor_property('fov_angle', 48.0)
        self.camera_data = {'position_cm': review.xyz(position), 'target_cm': review.xyz(target),
                            'horizontal_fov': 48.0, 'isolated_art_review_only': True}

    def pose(self):
        value = super().pose()
        value['actor_transform'] = review.transform_data(self.actor.get_actor_transform())
        value['tracked_world_bones'] = {name: review.transform_data(self.mesh_component.get_socket_transform(
            unreal.Name(name), unreal.RelativeTransformSpace.RTS_WORLD))
            for name in ['Root', 'pelvis', 'head', 'foot_l', 'foot_r', 'ball_l', 'ball_r'] if name in self.bones}
        return value

    def finish(self, error=None):
        if self.closing:
            return
        self.closing = True
        if not error and self.mode == 'Motion':
            try:
                rows = [row for row in self.report['images'] if row['job']['view'] == 'full' and row['job']['clip'] == 'idle']
                poses = [row['actual_pose']['bones_component_space'] for row in rows]
                changes = [diagnostic.compare(poses[0], pose) for pose in poses[1:]]
                changed = sorted({name for row in changes for name, delta in row.items() if delta['changed']})
                review.require(changed, 'Actual listening pose samples are static')
                self.report['listening_changed_bones'] = changed
                if 'walk' in self.clips:
                    rows = [row for row in self.report['images'] if row['job']['clip'] == 'walk' and row['job']['angle'] == 'front']
                    review.require(len(rows) == 4, 'Four actual walk phases required')
                    poses = [row['actual_pose']['bones_component_space'] for row in rows]
                    changes = [diagnostic.compare(poses[0], pose) for pose in poses[1:]]
                    changed = sorted({name for row in changes for name, delta in row.items() if delta['changed']})
                    review.require(any(n.startswith(('thigh_', 'calf_', 'foot_')) for n in changed), 'Actual walk leg poses are static')
                    self.report['walk_changed_bones'] = changed
                self.report['actor_transform_after'] = review.transform_data(self.actor.get_actor_transform())
                review.require(self.report['actor_transform_before'] == self.report['actor_transform_after'], 'Isolated actor moved during phase review')
            except Exception:
                error = traceback.format_exc()
        if error:
            self.report['error'] = error
            self.report['failure_phase'] = self.phase
            unreal.log_error(error)
        self.phase = 'cleanup'
        self.cleanup_deadline = time.monotonic() + 15
        self.checkpoint('finish_begin_cleanup')
        try:
            if self.target:
                unreal.RenderingLibrary.release_render_target2d(self.target)
        except Exception:
            self.report['cleanup_errors'].append({'operation': 'release_target', 'error': traceback.format_exc()})
        finally:
            try:
                if self.level.is_in_play_in_editor():
                    self.level.editor_request_end_play()
            except Exception:
                self.report['cleanup_errors'].append({'operation': 'request_end_pie', 'error': traceback.format_exc()})


if __name__ == '__main__':
    try:
        session = WardrobeReview()
        session.start()
    except Exception:
        directory = ROOT / 'output/reference_wardrobe_v02/setup_errors'
        directory.mkdir(parents=True, exist_ok=True)
        write(directory / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f') + '.json'),
              {'success': False, 'error': traceback.format_exc(), 'capture_source': str(SOURCE)})
        unreal.SystemLibrary.quit_editor()
