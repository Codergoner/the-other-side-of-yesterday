"""Read-only native-capture post-audit; no Unreal imports or actor changes."""
from pathlib import Path
import json
import math
import hashlib


def audit(project):
    source = project/'release_mother_gait_review_report.json'
    report = json.loads(source.read_text())
    rows = [r for r in report['images'] if r['job'].get('clip') == 'walk'
            and r['job'].get('view') == 'full' and r['job'].get('angle') == 'front']
    points = [r['actual_pose']['tracked_world_bones']['pelvis']['translation'] for r in rows]
    span = max((math.hypot(p[0]-points[0][0], p[1]-points[0][1]) for p in points), default=float('inf'))
    result = {'success': bool(report['success'] and len(rows) == 4 and span < 40),
        'scope': 'Post-audit of actual native world-bone capture evidence; no new engine run or visual/cloth approval',
        'capture_report_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'run': report['run'],
        'walk_pelvis_xy_span_cm': span, 'max_allowed_cm': 40, 'actual_native_pelvis_world_points_cm': points,
        'root_drift_cm': report.get('walk_root_drift_cm'), 'actor_drift_cm': report.get('actor_drift_cm'),
        'reason': 'In-place body drift bounded' if span < 40 else 'Body travels inside the locked-Root skeleton; incompatible with scripted NPC actor movement',
        'gait_visually_approved': False, 'native_capture_report_preserved': True, 'story_npcs_replaced': False}
    (project/'release_mother_gait_review_audit.json').write_text(json.dumps(result, indent=2)+'\n')
    history = project/'validation/release_mother_gait'/report['run']/'body_drift_post_audit.json'
    history.write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    print(json.dumps(audit(Path(__file__).resolve().parents[1]), indent=2))
