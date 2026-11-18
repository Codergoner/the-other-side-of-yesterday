"""Measure actual floor-comparison PNGs; pixel changes are not art acceptance."""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / 'release_hero_capture_report.json'
OUTPUT = ROOT / 'release_hero_image_metrics.json'
REGIONS = {'SurvivingRoom': [.05, .58, .44, .96],
           'RoomFloor': [.05, .58, .44, .96],
           'StreetFloor': [.23, .58, .72, .98]}


def stats(rgb):
    luma = rgb @ np.array([.2126, .7152, .0722])
    return {'encoded_rgb_mean_0_255': np.mean(rgb, axis=(0, 1)).tolist(),
            'encoded_luma_mean_0_255': float(np.mean(luma)),
            'encoded_luma_percentiles_5_50_95': np.percentile(luma, [5, 50, 95]).tolist(),
            'encoded_luma_below16_percent': float(np.mean(luma < 16) * 100),
            'any_channel_at_least254_percent': float(np.mean(np.max(rgb, axis=2) >= 254) * 100),
            'all_channels_at_least254_percent': float(np.mean(np.min(rgb, axis=2) >= 254) * 100)}


def main(report=REPORT, output=OUTPUT, log_name='release_hero_capture.log'):
    source = json.loads(report.read_text(encoding='utf-8'))
    if not source['success'] or len(source['images']) != 7:
        raise RuntimeError('Expected the completed seven-image native floor capture')
    result = {'success': False, 'capture_run': source['run'],
              'scope': 'Encoded PNG pixel statistics of fixed native editor views, not radiometric light values, gameplay, performance or visual acceptance.',
              'visual_accepted': False, 'images': [], 'paired_floor_regions': []}
    arrays = {}
    for entry in source['images']:
        path = Path(entry['path'])
        rgb = np.asarray(Image.open(path).convert('RGB'), dtype=np.float32)
        if rgb.shape != (900, 1600, 3):
            raise RuntimeError('Unexpected native PNG dimensions: ' + str(path))
        arrays[entry['label'], entry['view'], entry['mode']] = rgb
        result['images'].append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'label': entry['label'], 'view': entry['view'], 'mode': entry['mode'],
            'dimensions_px': [1600, 900], 'whole_image': stats(rgb)})
    for view, region in REGIONS.items():
        a = arrays['Before', view, 'Lit']
        b = arrays['After', view, 'Lit']
        x0, y0, x1, y1 = [round(v * (1600 if i % 2 == 0 else 900)) for i, v in enumerate(region)]
        ra, rb = a[y0:y1, x0:x1], b[y0:y1, x0:x1]
        result['paired_floor_regions'].append({'view': view, 'normalized_region': region,
            'pixel_bounds_xyxy': [x0, y0, x1, y1], 'before': stats(ra), 'after': stats(rb),
            'mean_absolute_rgb_difference_0_255': float(np.mean(np.abs(rb - ra))),
            'changed_rgb_pixels_percent': float(np.mean(np.any(rb != ra, axis=2)) * 100)})
    log = ROOT / log_name
    text = log.read_text(encoding='utf-8', errors='replace')
    failures = [line.strip() for line in text.splitlines() if 'Failed to compile Material ' in line]
    result['shader_log_observations'] = {'log': str(log), 'sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
        'hero_material_compile_failure_lines': [line for line in failures if '/Game/Release/Hero/' in line],
        'other_material_compile_failure_lines': failures,
        'note': 'The capture logged an Engine/BufferVisualization/CustomDepthWorldUnits SM5 debug-shader warning. Actual Lit/BaseColor PNGs rendered; that diagnostic is not a hero-material compile failure.'}
    result['success'] = True
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'success': True, 'images': len(result['images']), 'floor_regions': len(result['paired_floor_regions']),
                      'output': str(output)}))


if __name__ == '__main__':
    main()
