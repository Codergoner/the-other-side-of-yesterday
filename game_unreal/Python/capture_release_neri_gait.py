"""Queued, unsaved PIE review of the actual Mother-compatible walk bake.

Reuse the proved ticking PIE/no-DefaultPawn camera harness. This is an in-place
pose and garment review; it cannot approve foot planting, travel speed, physics
cloth, NPC integration, a packaged build or an uninterrupted performance.
"""
from pathlib import Path
import json
import math
import re
import sys
import time
import traceback
import unreal
sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import capture_release_character_pie as base
import capture_release_character_review as review
import diagnose_release_character_animation as diagnostic
import release_file_io as file_io

PROJECT = Path(unreal.Paths.project_dir()).resolve()
SOURCE = Path(__file__).resolve()
UNIT_CANDIDATE = unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseMotherUnitCandidate')
RETARGET_REPORT = PROJECT / ('release_neri_retarget_report.json' if UNIT_CANDIDATE else 'release_neri_retarget_report.json')


def protected_native_files():
    files = file_io.files(PROJECT/'Content','*.uasset') + file_io.files(PROJECT/'Content','*.umap')
    files += list((PROJECT/'Config').glob('*.ini')) + list(PROJECT.glob('*.uproject'))
    files += [review.IMPORT_REPORT, PROJECT/'Python/capture_release_character_review.py', PROJECT/'Python/import_release_characters.py',
              PROJECT.parent/'build_release_characters.py', SOURCE, PROJECT/'Python/release_file_io.py']
    return {str(p): file_io.sha(p) for p in files if file_io.is_file(p)}


# Preserve the proved capture lifecycle while extending its read-only guards to
# every existing long-path native asset, including the preserved failed bake.
review.sha = file_io.sha
review.native_files = protected_native_files


def distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


class GaitReview(base.PIEReview):
    def __init__(self):
        super().__init__()
        review_override = None
        unit_path = PROJECT / 'release_neri_import_report.json'
        if UNIT_CANDIDATE:
            unit = json.loads(unit_path.read_text())
            review.require(unit.get('success') and unit.get('native_executed'), 'Actual native corrected-unit probe required')
            preferred = dict(unit, skeletal_actor_count=1, id='Neri')
            review.require(isinstance(preferred, dict) and preferred['skeletal_actor_count'] == 1
                and preferred['native_unit_scale']['unit_root_scale_passed'] and preferred['human_height_passed']
                and preferred['authored_bone_and_curve_data_passed'], 'No proved unit-scale native human/Listening candidate')
            self.imported = dict(self.imported)
            self.imported.update({key: preferred[key] for key in ['map', 'mesh', 'animation', 'actor', 'namespace', 'native_morph_names', 'actor_bounds_cm']})
            self.report.update({'map': self.imported['map'], 'mesh': self.imported['mesh'], 'animation': self.imported['animation'],
                'unit_candidate': preferred['id'], 'source_import_report_sha256': review.sha(unit_path),
                'new_native_authored_data_passed': True,
                'basis_scope': 'Explicit PosY front following the original cardinal review and source-geometry-preserving unit representation; final native front/profile images still require review.'})
        match = re.search(r'(?i)(?:^|\s)-ReleaseMotherReviewReport=(?:"([^"]+)"|(\S+))', unreal.SystemLibrary.get_command_line())
        if match:
            override_path = Path(match.group(1) or match.group(2)).resolve()
            review.require(override_path.is_relative_to(PROJECT), 'Review override must stay inside the Release project')
            review_override = json.loads(override_path.read_text())
            review.require(review_override.get('success') and review_override.get('native_executed'), 'Actual successful native revision import required')
            self.imported.update({key:review_override[key] for key in ['map','mesh','animation','actor','actor_bounds_cm']})
            revised_mesh = unreal.load_asset(self.imported['mesh'])
            review.require(revised_mesh, 'Revised native mesh unavailable')
            self.imported['native_morph_names'] = [m.get_name() for m in revised_mesh.call_method('GetMorphTargetsPtrConv')]
            self.report.update({'map':self.imported['map'],'mesh':self.imported['mesh'],'animation':self.imported['animation'],
                'additional_native_review_report':str(override_path),'additional_native_review_report_sha256':review.sha(override_path)})
        self.retarget = json.loads(RETARGET_REPORT.read_text())
        review.require(self.retarget['success'] and self.retarget['native_executed'], 'Actual target-compatible native bake required')
        if review_override:
            mesh = unreal.load_asset(self.imported['mesh'])
            walk = unreal.load_asset(self.retarget['baked']['walk'])
            idle = unreal.load_asset(self.imported['animation'])
            review.require(mesh and walk and idle and mesh.get_editor_property('skeleton') == walk.get_editor_property('skeleton')
                and mesh.get_editor_property('skeleton') == idle.get_editor_property('skeleton'), 'Revision must use the exact existing normalized skeleton; no animation alias or inferred compatibility')
        else:
            review.require(self.retarget['target_mesh'] == self.imported['mesh'], 'Bake belongs to a different Mother mesh')
        if UNIT_CANDIDATE:
            review.require(self.retarget['source_import_report_sha256'] == review.sha(unit_path), 'Bake belongs to a different native unit probe')
        review.require(self.front in ['PosY', 'NegY'], 'Use the actual cardinal-reviewed +/-Y Mother front')
        self.is_revision_review = bool(review_override)
        self.folder = PROJECT / ('validation/release_neri_revision_gait' if self.is_revision_review else 'validation/release_neri_gait') / self.run
        self.folder.mkdir(parents=True)
        self.source_path, self.source_sha = SOURCE, review.sha(SOURCE)
        self.report.update({'scope': 'Transient native PIE: Listening idle plus in-place target-compatible walk phases, bones/world bounds and garment images; not locomotion/foot-plant approval or production NPC integration.',
            'retarget_report_sha256': review.sha(RETARGET_REPORT),
            'listening_idle': self.imported['animation'], 'baked_walk': self.retarget['baked']['walk'],
            'art_gate_passed': False, 'gait_visually_approved': False, 'cloth_simulation_claimed': False,
            'foot_planting_or_speed_match_tested': False, 'story_npcs_replaced': False,
            'walk_clip_sample_fractions': [0.0, 0.125, 0.25, 0.375],
            'walk_sampling_reason': 'Actual8native pose samples show two repeated stride cycles in this1.5s source clip; sample4distinct phases across the first half instead of aliasing both cycles.',
            'samples_are_explicit_phase_poses': True, 'plausibility_issues': []})
        self.jobs = [{'id': 'Listening_' + view, 'clip': 'idle', 'fraction': 0.0, 'view': 'full', 'angle': view}
                     for view in ['front', 'profile']]
        self.jobs += [{'id': 'Walk_' + view + '_phase' + str(phase), 'clip': 'walk', 'fraction': phase/8.0,
                       'view': 'full', 'angle': view} for phase in range(4) for view in ['front', 'profile']]
        self.jobs += [{'id': 'Feet_' + view + '_phase' + str(phase), 'clip': 'walk', 'fraction': phase/8.0,
                       'view': 'feet', 'angle': view} for phase in [1, 3] for view in ['front', 'profile']]
        if self.is_revision_review:
            self.jobs += [{'id':'Listening_rear','clip':'idle','fraction':0.0,'view':'full','angle':'rear'}]
            self.jobs += [{'id':'Walk_rear_phase'+str(phase),'clip':'walk','fraction':phase/8.0,'view':'full','angle':'rear'}
                          for phase in [1,3]]
            self.jobs += [{'id':'FaceOpen','clip':'idle','fraction':0.0,'view':'face','angle':'front','blink':0.0},
                          {'id':'FaceBlink','clip':'idle','fraction':0.0,'view':'face','angle':'front','blink':1.0}]
            self.report['revision_rear_seam_review_included'] = True
        self.deadline = time.monotonic() + 240

    def write(self):
        text = json.dumps(self.report, indent=2) + '\n'
        (self.folder / 'capture_report.json').write_text(text)
        name = 'release_neri_revision_gait_review_report.json' if self.is_revision_review else 'release_neri_gait_review_report.json'
        (PROJECT / name).write_text(text)

    def initialize_pie(self):
        super().initialize_pie()
        mesh = self.mesh_component.get_skeletal_mesh_asset()
        if UNIT_CANDIDATE:
            from release_mother_integration import unit_reference
            self.report['native_unit_reference'] = unit_reference(mesh)
        self.clips = {'idle': unreal.load_asset(self.imported['animation']),
                      'walk': unreal.load_asset(self.retarget['baked']['walk'])}
        target_skeleton = mesh.get_editor_property('skeleton')
        for key, clip in self.clips.items():
            review.require(clip and clip.get_editor_property('skeleton') == target_skeleton,
                           'Refusing an incompatible skeleton animation: ' + key)
        self.report['target_skeleton'] = target_skeleton.get_path_name()
        self.report['native_executed'] = True
        paths = [mesh.get_path_name(), target_skeleton.get_path_name()] + [clip.get_path_name() for clip in self.clips.values()]
        self.report['reviewed_asset_sha256'] = {str(PROJECT / 'Content' / (name.split('.')[0].removeprefix('/Game/') + '.uasset')):
            review.sha(PROJECT / 'Content' / (name.split('.')[0].removeprefix('/Game/') + '.uasset')) for name in paths}
        self.report['native_clothing_assets'] = [a.get_path_name() for a in mesh.get_editor_property('mesh_clothing_assets')]
        self.report['cloth_evidence_scope'] = ('Clothing assets listed, no simulation acceptance implied'
            if self.report['native_clothing_assets'] else 'Skinned garment only: no native clothing asset or physics cloth simulation')
        self.report['actor_transform_before'] = review.transform_data(self.actor.get_actor_transform())
        self.actor_start = review.xyz(self.actor.get_actor_location())
        self.floor_z = self.actor_start[2]
        self.active_clip = None

    def prepare_sample(self):
        if self.index >= len(self.jobs):
            return self.finish()
        self.current = self.jobs[self.index]
        unreal.GameplayStatics.set_game_paused(self.world, False)
        clip = self.clips[self.current['clip']]
        if self.active_clip != self.current['clip']:
            self.mesh_component.play_animation(clip, True)
            self.active_clip = self.current['clip']
        # A normally ticking component evaluates these explicit, stationary
        # phase samples. World continues; phase pose is held for camera warming.
        self.mesh_component.set_play_rate(0.0)
        self.mesh_component.set_position(float(clip.get_play_length()) * self.current['fraction'], False)
        self.camera(self.current)
        self.frames, self.warm_started = 0, time.monotonic()
        self.phase = 'warm'
        self.checkpoint('warm_gait_sample', job=self.current)

    def camera(self, job):
        if job['view']=='face':
            return base.PIEReview.camera(self,job)
        forward = review.DIRECTIONS[self.front]
        direction = (forward if job['angle'] == 'front' else
                     ((-forward[0],-forward[1]) if job['angle'] == 'rear' else (-forward[1],forward[0])))
        if job['view'] == 'feet':
            target = unreal.Vector(self.actor_start[0], self.actor_start[1], self.floor_z + 25)
            distance_cm, fov = 170.0, 46.0
        else:
            target = unreal.Vector(*self.imported['actor_bounds_cm']['origin'])
            distance_cm, fov = 400.0, 48.0
        position = target + unreal.Vector(direction[0] * distance_cm, direction[1] * distance_cm, 0)
        self.capture.set_actor_location(position, False, False)
        self.capture.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(position, target), False)
        self.component.set_editor_property('fov_angle', fov)
        self.camera_data = {'position_cm': review.xyz(position), 'target_cm': review.xyz(target),
                            'horizontal_fov': fov, 'cinematic_only': True}

    def pose(self):
        data = super().pose()
        origin, extent, radius = unreal.SystemLibrary.get_component_bounds(self.mesh_component)
        data['component_world_bounds'] = {'origin_cm': review.xyz(origin), 'extent_cm': review.xyz(extent), 'sphere_radius_cm': float(radius)}
        data['actor_world_transform'] = review.transform_data(self.actor.get_actor_transform())
        tracked = ['Root', 'pelvis', 'head', 'foot_l', 'foot_r', 'ball_l', 'ball_r']
        data['tracked_world_bones'] = {name: review.transform_data(self.mesh_component.get_socket_transform(
            unreal.Name(name), unreal.RelativeTransformSpace.RTS_WORLD)) for name in tracked if name in self.bones}
        data['foot_bone_height_over_authored_floor_cm'] = {name: data['tracked_world_bones'][name]['translation'][2] - self.floor_z
            for name in ['foot_l', 'foot_r', 'ball_l', 'ball_r'] if name in data['tracked_world_bones']}
        data['native_clothing_simulation_suspended'] = bool(self.mesh_component.is_clothing_simulation_suspended())
        data['note'] = 'Foot-bone heights are not shoe-sole contact or IK foot-plant measurements.'
        return data

    def finish(self, error=None):
        if not error and not self.closing:
            try:
                rows = [r for r in self.report['images'] if r['job']['clip'] == 'walk' and r['job']['view'] == 'full' and r['job']['angle'] == 'front']
                review.require(len(rows) == 4, 'Four real front-view walk phases required')
                poses = [r['actual_pose']['bones_component_space'] for r in rows]
                deltas = [diagnostic.compare(poses[0], p) for p in poses[1:]]
                changed = sorted({name for row in deltas for name, value in row.items() if value['changed']})
                self.report['walk_changed_bones'] = changed
                self.report['walk_phase_deltas'] = deltas
                review.require(any(n.startswith(('thigh_', 'calf_', 'foot_')) for n in changed), 'Actual PIE walk leg poses are static')
                roots = [r['actual_pose']['tracked_world_bones']['Root']['translation'] for r in rows]
                pelvis = [r['actual_pose']['tracked_world_bones']['pelvis']['translation'] for r in rows]
                self.report['walk_root_drift_cm'] = max(distance(roots[0], p) for p in roots)
                self.report['walk_pelvis_xy_span_cm'] = max(math.hypot(p[0]-pelvis[0][0], p[1]-pelvis[0][1]) for p in pelvis)
                self.report['actor_drift_cm'] = distance(self.actor_start, review.xyz(self.actor.get_actor_location()))
                issues = self.report['plausibility_issues']
                for row in self.report['images']:
                    pose = row['actual_pose']
                    z = pose['tracked_world_bones']['head']['translation'][2] - self.floor_z
                    if not 100 <= z <= 230: issues.append(row['job']['id'] + ': head height outside100..230cm: ' + str(z))
                    if any(abs(v) > 80 for v in pose['foot_bone_height_over_authored_floor_cm'].values()):
                        issues.append(row['job']['id'] + ': foot-bone height implausible')
                review.require(self.report['walk_root_drift_cm'] < 2.0 and self.report['actor_drift_cm'] < 0.01,
                               'In-place review root or actor drifted')
                review.require(self.report['walk_pelvis_xy_span_cm'] < 40,
                               'Body travels inside its skeleton despite locked Root; reject in-place NPC integration')
                review.require(not issues, 'Native world body/feet plausibility failed; inspect bake scale/orientation before NPC integration')
            except Exception:
                error = traceback.format_exc()
        return super().finish(error)


if __name__ == '__main__':
    try:
        session = GaitReview()
        session.start()
    except Exception:
        (PROJECT / 'release_neri_gait_setup_error.json').write_text(json.dumps({'success': False, 'error': traceback.format_exc()}, indent=2))
        unreal.SystemLibrary.quit_editor()
