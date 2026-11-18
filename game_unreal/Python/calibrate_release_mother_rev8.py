"""QUEUED native, read-only stance-velocity estimate for scripted Mother travel.

No gameplay, movement speed/path, asset, map, animation key or save writes. A
rate estimate from actual RAW/COMPRESSED foot tracks is not a foot-lock claim;
later runtime heading/turn/step video must assess the final garment and sliding.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import math
import statistics
import sys
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(PROJECT/'Python'))
import release_file_io as file_io
from release_mother_integration import require, unit_reference

REPORT = PROJECT/'release_mother_rev8_walk_calibration.json'
ACTOR_SCALE = .96
SCRIPT_SPEED = 100.0


def stance_speeds(samples):
    """Low/near-level feet moving opposite +Y travel; reject swing samples."""
    rows = []
    for side in ['l', 'r']:
        foot, ball = 'foot_'+side, 'ball_'+side
        floor_foot = min(p[foot][2] for p in samples)
        floor_ball = min(p[ball][2] for p in samples)
        for a, b in zip(samples, samples[1:]):
            dt = b['time'] - a['time']
            velocity = [(b[foot][axis]-a[foot][axis])/dt for axis in range(3)]
            low_foot = max(a[foot][2], b[foot][2]) <= floor_foot + 3.0
            low_ball = max(a[ball][2], b[ball][2]) <= floor_ball + 3.0
            if low_foot and low_ball and velocity[1] < -20 and abs(velocity[2]) < 35 and abs(velocity[0]) < 60:
                rows.append({'foot': side, 'start_seconds': a['time'], 'end_seconds': b['time'],
                    'native_forward_stance_speed_cm_s': -velocity[1], 'vertical_velocity_cm_s': velocity[2],
                    'foot_height_threshold_cm': floor_foot+3, 'ball_height_threshold_cm': floor_ball+3})
    require(len(rows) >= 10 and all(sum(r['foot']==side for r in rows) >= 4 for side in ['l','r']),
            'Insufficient measured low-foot stance intervals; do not invent a play rate')
    values = sorted(r['native_forward_stance_speed_cm_s'] for r in rows)
    median = statistics.median(values)
    return {'stance_intervals': rows, 'median_native_cm_s': median,
        'p10_native_cm_s': values[int((len(values)-1)*.10)], 'p90_native_cm_s': values[int((len(values)-1)*.90)],
        'world_stance_speed_at_rate1_cm_s': median*ACTOR_SCALE,
        'recommended_play_rate': SCRIPT_SPEED/(median*ACTOR_SCALE)}


def main():
    require(PROJECT.parent.name == 'Release_20261026', 'Exact Release project required')
    require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseMotherCalibrate'), 'Root read-only native queue required')
    retarget_path = PROJECT/'release_mother_rev8_compatible_bake.json'
    retarget = json.loads(retarget_path.read_text())
    require(retarget['success'] and retarget['native_executed'] and retarget['pose_evidence']['walk']['pelvis_xy_span_cm'] < 40,
            'Only a verified unit-scale, in-place bake may be calibrated')
    mesh, sequence = unreal.load_asset(retarget['target_mesh']), unreal.load_asset(retarget['baked']['walk'])
    require(mesh and sequence and sequence.get_editor_property('skeleton') == mesh.get_editor_property('skeleton'), 'Actual matching target-skeleton clip required')
    unit = unit_reference(mesh)
    for file, digest in retarget['owned_asset_sha256'].items():
        require(file_io.sha(file) == digest, 'Baked asset changed since native proof')
    before = {str(p):file_io.sha(p) for p in file_io.files(PROJECT/'Content','*.uasset')+file_io.files(PROJECT/'Content','*.umap')}
    duration = float(sequence.get_play_length())
    #120Hz finite differences over both actual stride cycles; retain raw sample
    #positions so the estimate/stance filtering remains independently reviewable.
    intervals = max(120, int(math.ceil(duration*120)))
    evidence = {}
    for name, kind in [('RAW', unreal.AnimDataEvalType.RAW), ('COMPRESSED', unreal.AnimDataEvalType.COMPRESSED)]:
        options = unreal.AnimPoseEvaluationOptions()
        for key, value in {'evaluation_type': kind, 'should_retarget': True, 'extract_root_motion': False,
                           'incorporate_root_motion_into_pose': False, 'optional_skeletal_mesh': mesh}.items():
            options.set_editor_property(key, value)
        samples = []
        for index in range(intervals+1):
            second = duration*index/intervals
            pose = unreal.AnimPoseExtensions.get_anim_pose_at_time(sequence, second, options)
            require(unreal.AnimPoseExtensions.is_valid(pose), 'Native dense pose evaluation failed')
            row = {'time': second}
            for bone in ['Root','pelvis','foot_l','foot_r','ball_l','ball_r']:
                p = unreal.AnimPoseExtensions.get_bone_pose(pose, bone, unreal.AnimPoseSpaces.WORLD).translation
                row[bone] = [float(p.x),float(p.y),float(p.z)]
            samples.append(row)
        pelvis_span = max(math.hypot(s['pelvis'][0]-samples[0]['pelvis'][0],s['pelvis'][1]-samples[0]['pelvis'][1]) for s in samples)
        require(pelvis_span < 40, 'Dense poses expose hidden body travel; do not calibrate it away')
        estimate = stance_speeds(samples)
        require(.2 <= estimate['recommended_play_rate'] <= 1.5, 'Estimated rate is outside the review bounds')
        evidence[name] = {'pelvis_xy_span_cm': pelvis_span, 'samples': samples, **estimate}
    raw_rate, compressed_rate = (evidence[n]['recommended_play_rate'] for n in ['RAW','COMPRESSED'])
    require(abs(raw_rate-compressed_rate) <= .1*raw_rate, 'RAW/COMPRESSED stance rates disagree')
    require(all(file_io.sha(p) == digest for p,digest in before.items()), 'Read-only calibration changed native inputs')
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    folder = PROJECT/'validation/release_mother_rev8_walk_calibration'/run
    folder.mkdir(parents=True)
    result = {'success': True, 'native_executed': True, 'run': run,
        'scope': 'Dense native foot-track stance-speed estimate only; no runtime/video or foot-lock acceptance',
        'target_mesh': retarget['target_mesh'], 'walk': sequence.get_path_name(), 'unit_reference': unit,
        'retarget_report_sha256': file_io.sha(retarget_path), 'source_sha256': file_io.sha(__file__),
        'scripted_travel_speed_cm_s': SCRIPT_SPEED, 'assumed_authored_actor_uniform_scale': ACTOR_SCALE,
        'actor_scale_must_be_checked_before_apply': True, 'native_forward_axis': '+Y', 'sample_rate_hz': intervals/duration,
        'recommended_play_rate': statistics.median([raw_rate,compressed_rate]), 'evaluations': evidence,
        'native_assets_unchanged': True, 'runtime_play_rate_applied': False, 'foot_lock_or_speed_match_verified_in_video': False,
        'query_physics_or_story_changes': False, 'save_files_written': False}
    text = json.dumps(result,indent=2)+'\n'
    REPORT.write_text(text)
    (folder/'calibration.json').write_text(text)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        REPORT.write_text(json.dumps({'success': False, 'error': traceback.format_exc()},indent=2))
        unreal.log_error(traceback.format_exc())
    unreal.SystemLibrary.quit_editor()
