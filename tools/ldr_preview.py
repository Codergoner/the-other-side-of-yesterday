"""Estimate of the headset's untonemapped image from the editor's linear scene colour (17 November 2026).

The Quest build runs the mobile forward renderer with r.MobileHDR=False: no exposure, no tonemapper, no bloom. What
reaches the display is the lit colour clamped to 0..1 and sRGB-encoded. verdant_capture.py (job option "hdr") exports
the desktop renderer's linear scene colour for each view; this script clamps and encodes it the same way and reports
how much of each frame clips. It is an estimate from the desktop forward renderer, NOT a capture of the mobile
renderer and not a device result: mobile shading (specular, sky light, fog) differs in detail.

    python ldr_preview.py <capture folder>

Writes <view>_ldr_estimate.png next to each <view>_linear file and ldr_estimate.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
import OpenImageIO as oiio

folder = Path(sys.argv[1])
report = {'kind': 'estimate of untonemapped output from desktop linear scene colour; not a mobile-renderer or device capture', 'views': {}}
for path in sorted(folder.glob('*_linear')):
    source = oiio.ImageInput.open(str(path))
    spec = source.spec()
    pixels = np.asarray(source.read_image(format='float'), np.float32).reshape(spec.height, spec.width, spec.nchannels)[..., :3]
    source.close()
    luminance = pixels @ np.array([.2126, .7152, .0722], np.float32)
    clipped = (pixels.max(-1) >= 1.0)
    encoded = np.clip(pixels, 0, 1)
    encoded = np.where(encoded <= .0031308, encoded * 12.92, 1.055 * encoded ** (1 / 2.4) - .055)
    out = oiio.ImageOutput.create(str(path) + '_ldr_estimate.png')
    out_spec = oiio.ImageSpec(spec.width, spec.height, 3, 'uint8')
    out.open(str(path.parent / (path.name.replace('_linear', '') + '_ldr_estimate.png')), out_spec)
    out.write_image((encoded * 255 + .5).astype(np.uint8))
    out.close()
    report['views'][path.name.replace('_linear', '')] = {
        'clipped_fraction': round(float(clipped.mean()), 4), 'median_linear': round(float(np.median(luminance)), 4),
        'p90_linear': round(float(np.percentile(luminance, 90)), 3), 'p99_linear': round(float(np.percentile(luminance, 99)), 3),
        'mean_encoded': round(float(encoded.mean()), 3)}
(folder / 'ldr_estimate.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
for key, row in report['views'].items():
    print(key, row)
