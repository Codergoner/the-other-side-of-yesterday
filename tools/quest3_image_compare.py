"""Compare two capture folders image by image (Blender headless): mean luminance and mean absolute difference.

    blender --background --factory-startup --python quest3_image_compare.py -- <before dir> <after dir> <output json>

Images are matched by file name. Numbers are data about the captures, not an art judgement.
"""
import json
import sys
from pathlib import Path

import bpy


def load(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    width, height = image.size
    pixels = list(image.pixels)
    bpy.data.images.remove(image)
    return width, height, pixels


def stats(before, after):
    wb, hb, pb = load(before)
    wa, ha, pa = load(after)
    if (wb, hb) != (wa, ha):
        return {'before_size': [wb, hb], 'after_size': [wa, ha], 'comparable': False}
    count = wb * hb
    luma_before = luma_after = diff = 0.0
    for i in range(count):
        o = i * 4
        lb = 0.2126 * pb[o] + 0.7152 * pb[o + 1] + 0.0722 * pb[o + 2]
        la = 0.2126 * pa[o] + 0.7152 * pa[o + 1] + 0.0722 * pa[o + 2]
        luma_before += lb
        luma_after += la
        diff += abs(pb[o] - pa[o]) + abs(pb[o + 1] - pa[o + 1]) + abs(pb[o + 2] - pa[o + 2])
    return {'size': [wb, hb], 'comparable': True, 'mean_luma_before': round(luma_before / count, 4),
            'mean_luma_after': round(luma_after / count, 4), 'mean_abs_diff_rgb': round(diff / (3 * count), 4)}


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    before, after, output = Path(args[0]), Path(args[1]), Path(args[2])
    rows = {}
    for file in sorted(before.glob('*.png')):
        other = after / file.name
        if other.exists():
            rows[file.name] = stats(file, other)
    result = {'before': str(before), 'after': str(after), 'images': rows,
              'max_mean_abs_diff_rgb': max((r['mean_abs_diff_rgb'] for r in rows.values() if r.get('comparable')), default=None)}
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'images': len(rows), 'max_mean_abs_diff_rgb': result['max_mean_abs_diff_rgb']}))


main()
