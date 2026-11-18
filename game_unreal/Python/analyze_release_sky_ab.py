"""Measure actual native A/B PNG shadow values/clipping; no Unreal dependency.

These are fixed display-image statistics, not photometric lighting measures or
automatic visual approval. ROI definitions remain fixed between candidates.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ROIS = {'SurvivingRoom': [.05, .28, .95, .95],
        'HarborVista': [.05, .40, .95, .95],
        'UphillCathedral': [.00, .30, .75, .95]}


def metrics(rgb):
    luma = np.sum(rgb.astype(np.float64) * np.array([.2126, .7152, .0722]), axis=2)
    return {'mean_encoded_luma_8bit': float(luma.mean()),
            'luma_p05_p10_p50_p90_p95': [float(value) for value in np.percentile(luma, [5, 10, 50, 90, 95])],
            'pixels_luma_below8_percent': float(np.mean(luma < 8) * 100),
            'pixels_luma_below16_percent': float(np.mean(luma < 16) * 100),
            'any_channel_at_least254_percent': float(np.mean(np.any(rgb >= 254, axis=2)) * 100),
            'all_channels_at_least254_percent': float(np.mean(np.all(rgb >= 254, axis=2)) * 100)}


def analyze():
    report = json.loads((ROOT / 'release_sky_ab_report.json').read_text(encoding='utf-8'))
    assert report['success'] and report['protected_inputs_unchanged'] and report['required_nine_native_images_complete']
    rows = []
    for image in report['images']:
        path = Path(image['path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == image['sha256']
        rgb = np.array(Image.open(path).convert('RGB'), dtype=np.uint8)
        height, width = rgb.shape[:2]
        roi = ROIS[image['view']]
        x0, y0, x1, y1 = [round(value * size) for value, size in zip(roi, [width, height, width, height])]
        rows.append({'profile': image['label'], 'view': image['view'], 'path': str(path), 'sha256': image['sha256'],
                     'full_image': metrics(rgb), 'fixed_foreground_roi_xyxy': [x0, y0, x1, y1],
                     'fixed_foreground_roi': metrics(rgb[y0:y1, x0:x1])})
    comparisons = []
    for view in ROIS:
        baseline = next(row for row in rows if row['profile'] == 'SavedCurrent' and row['view'] == view)
        for row in rows:
            if row['view'] == view and row['profile'] != 'SavedCurrent':
                comparisons.append({'view': view, 'profile': row['profile'],
                    'foreground_mean_luma_delta': row['fixed_foreground_roi']['mean_encoded_luma_8bit'] - baseline['fixed_foreground_roi']['mean_encoded_luma_8bit'],
                    'foreground_below16_percentage_point_delta': row['fixed_foreground_roi']['pixels_luma_below16_percent'] - baseline['fixed_foreground_roi']['pixels_luma_below16_percent'],
                    'full_image_near_white_percentage_point_delta': row['full_image']['all_channels_at_least254_percent'] - baseline['full_image']['all_channels_at_least254_percent']})
    result = {'success': True, 'capture_run': report['run'], 'metrics': rows, 'comparisons_to_saved': comparisons,
              'definition': 'Encoded RGB luma proxy = .2126R+.7152G+.0722B from8-bit PNGs. Fixed foreground crops include mixed surfaces, not automatic shadow segmentation.',
              'limits': 'Clipping counts are display-image thresholds. These metrics do not prove HDR headroom, perceptual quality, gameplay readability, animation, device compatibility, or performance.',
              'candidate_automatically_selected': False, 'persistent_scene_change': False}
    path = ROOT / 'release_sky_ab_image_metrics.json'
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(comparisons, indent=2))
    return result


if __name__ == '__main__':
    analyze()
