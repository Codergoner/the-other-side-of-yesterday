"""Tonemaps a baked sky EXR to PNG for review and reports where the brightest area sits.

    blender --background --python sky_preview.py -- in.exr out.png
"""
import json
import math
import sys
import zlib
import struct

import bpy
import numpy as np

source, target = sys.argv[sys.argv.index('--') + 1:][:2]
image = bpy.data.images.load(source)
w, h = image.size
px = np.empty(w * h * 4, np.float32)
image.pixels.foreach_get(px)
rgb = px.reshape(h, w, 4)[::-1][..., :3]
lum = rgb @ np.array([.2126, .7152, .0722])
stats = {'width': w, 'height': h, 'max': float(rgb.max()), 'p50': float(np.percentile(lum, 50)), 'p99': float(np.percentile(lum, 99))}
blurred = lum[:h // 2]
row, col = np.unravel_index(np.argmax(np.minimum(blurred, np.percentile(blurred, 99.95)) * (blurred > 0)), blurred.shape)
stats['bright_azimuth_from_+Y_toward_+X'] = (col / w - .5) * 360
stats['bright_elevation'] = 90 - (row + .5) / h * 180
print('SKYSTATS', json.dumps(stats), flush=True)


def aces(x):
    x = x * .6
    return np.clip((x * (2.51 * x + .03)) / (x * (2.43 * x + .59) + .14), 0, 1)


out = aces(rgb * float(sys.argv[-1]) if len(sys.argv) > sys.argv.index('--') + 3 else rgb) ** (1 / 2.2)
out = out[:int(h * .62)]
data = (out * 255 + .5).astype(np.uint8)
hh, ww, _ = data.shape
raw = np.concatenate([np.zeros((hh, 1), np.uint8), data.reshape(hh, ww * 3)], axis=1).tobytes()


def chunk(tag, payload):
    body = tag + payload
    return struct.pack('>I', len(payload)) + body + struct.pack('>I', zlib.crc32(body))


open(target, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', ww, hh, 8, 2, 0, 0, 0)) +
                         chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))
