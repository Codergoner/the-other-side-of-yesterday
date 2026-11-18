"""Read-only pixel measurements plus separately attributed visual review.

Never rewrites the native capture report/images or infers visible blinking from
file hashes/target getters. The visual-review flag must follow inspection of
the actual images; pixel deltas are supporting measurements, not a classifier.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
from PIL import Image, ImageChops, ImageStat


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def measurements(first, second, box):
    diff = ImageChops.difference(first.crop(box), second.crop(box))
    pixels = list(diff.get_flattened_data())
    return {'box_xyxy': box, 'pixels': len(pixels), 'mean_absolute_rgb_8bit': ImageStat.Stat(diff).mean,
            'maximum_absolute_channel_difference': max(max(pixel) for pixel in pixels),
            'pixels_any_channel_difference_over8': sum(max(pixel) > 8 for pixel in pixels),
            'fraction_any_channel_difference_over8': sum(max(pixel) > 8 for pixel in pixels) / len(pixels),
            'semantic_eyelid_closure_detector': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-report', required=True, type=Path)
    parser.add_argument('--root-verified-visible-blink', action='store_true')
    args = parser.parse_args()
    path = args.capture_report.resolve()
    capture = json.loads(path.read_text())
    assert capture['success'] and all(capture['guards'].values()), 'Successful native capture with unchanged guards required'
    rows = {row['job']['id']: row for row in capture['images']}
    images = [Path(rows[key]['path']) for key in ['FaceOpen', 'FaceBlink']]
    protected = {str(p): sha(p) for p in [path, *images]}
    assert all(sha(p) == rows[key]['sha256'] for key, p in zip(['FaceOpen', 'FaceBlink'], images)), 'Actual capture image differs from the raw report'
    opened, closed = [Image.open(p).convert('RGB') for p in images]
    assert opened.size == closed.size == (1920, 1080), 'This measured ROI is authored for the inspected1920×1080 review only'
    result = {'success': True, 'review_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Separate inspection annotation of existing actual native PIE art samples; original evidence is preserved.',
        'capture_run': capture['run'], 'capture_report': str(path), 'capture_report_sha256': sha(path),
        'images': [{'path': str(p), 'sha256': sha(p)} for p in images],
        'root_verified_visible_eyelid_closure': args.root_verified_visible_blink,
        'verification_attribution': 'Root explicitly inspected actual FaceOpen/FaceBlink and reported clear visible closure; this agent also inspected the actual image pair.' if args.root_verified_visible_blink else 'No visual closure verification supplied',
        'pixel_measurements_support_visual_review_only': True,
        'regions': {'left_eye_screen': measurements(opened, closed, [800, 515, 920, 585]),
                    'right_eye_screen': measurements(opened, closed, [1010, 515, 1135, 585]),
                    'combined_eyes': measurements(opened, closed, [790, 500, 1145, 590]),
                    'cheek_control': measurements(opened, closed, [785, 620, 870, 700])},
        'native_bone_motion_sampled': bool(capture.get('motion_changed_bones')),
        'native_changed_bones': capture.get('motion_changed_bones', []),
        'visual_findings': ['Actual face images show open eyes changing to visibly closed lids.',
            'Actual PIE images show the textured skin/hair/knit and lowered arms; no new normal/material edit was needed.',
            'Small dark lash specks remain visible on the closed lids and need later polish.',
            'Engine.DefaultPawn gray sphere occludes the footwear in Listening_t0. This run cannot pass the full-body/footwear visual gate.'] if args.root_verified_visible_blink else [],
        'full_body_visual_gate_passed': False, 'footwear_deformation_gate_passed': False,
        'production_idle_gait_or_retarget_proven': False, 'story_npc_integration_passed': False,
        'raw_capture_rewritten': False, 'protected_evidence_sha256': protected}
    assert protected == {str(p): sha(p) for p in [path, *images]}, 'Read-only image review changed original evidence'
    destination = path.parent / 'visual_review.json'
    assert not destination.exists(), 'Preserve the existing review annotation'
    destination.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'review': str(destination), 'sha256': sha(destination), 'regions': result['regions']}, indent=2))


if __name__ == '__main__':
    main()
