"""Grades a baked Cycles sky into the shipping panorama: blue zenith, peach and amber horizon,
a contained sun, and a haze band below the horizon so the far sea meets the sky without a seam.

    blender --background --python finish_sky.py -- <Past|Present> in.exr out.exr
"""
import math
import sys

import bpy
import numpy as np

ERA, SOURCE, TARGET = sys.argv[sys.argv.index('--') + 1:][:3]
GRADE = {
    'Past': dict(azimuth=62.0, elevation=13.0, peach=(1.28, .98, .74), amber=(1.5, 1.04, .6), zenith=(1.15, 1.22, 1.45), overall=(1.0, 1.0, 1.0), sun=36.0),
    'Present': dict(azimuth=66.0, elevation=10.5, peach=(1.18, .96, .78), amber=(1.36, 1.0, .64), zenith=(1.05, 1.12, 1.3), overall=(.94, .95, 1.0), sun=22.0),
}[ERA]

image = bpy.data.images.load(SOURCE)
w, h = image.size
pixels = np.empty(w * h * 4, np.float32)
image.pixels.foreach_get(pixels)
rgb = pixels.reshape(h, w, 4)[::-1][..., :3].copy()

row = (np.arange(h) + .5) / h
col = (np.arange(w) + .5) / w
elevation = (.5 - row) * math.pi
azimuth = (col - .5) * math.tau
el = elevation[:, None]
az = azimuth[None, :]


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


sa, se = math.radians(GRADE['azimuth']), math.radians(GRADE['elevation'])
sun = np.array([math.sin(sa) * math.cos(se), math.cos(sa) * math.cos(se), math.sin(se)])
dirs = np.stack([np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.broadcast_to(np.sin(el), (h, w))], -1)
angle = np.arccos(np.clip(dirs @ sun, -1, 1))

degrees = np.degrees(el)
horizon = np.exp(-(np.maximum(degrees, 0) / 9.0) ** 2)
toward = np.exp(-(angle / math.radians(62)) ** 2)
peach = np.array(GRADE['peach'], np.float32)
amber = np.array(GRADE['amber'], np.float32)
warm = peach + (amber - peach) * toward[..., None]
rgb *= 1 + (warm - 1) * horizon[..., None]
rgb *= 1 + (np.array(GRADE['zenith'], np.float32) - 1) * smooth(16, 68, degrees)[..., None]
rgb *= np.array(GRADE['overall'], np.float32)

# Cloud bases near the sun pick up amber, the rims stay pale; this reads as depth at low sun.
luminance = rgb @ np.array([.2126, .7152, .0722], np.float32)
rgb += (rgb * np.array([.32, .1, -.12], np.float32)) * (toward * smooth(.2, 1.2, luminance))[..., None]

pre_disc = rgb.copy()
# Sun disc and tight halo, deliberately small: the directional light does the real work.
disc = smooth(math.radians(1.05), math.radians(.72), angle)
halo = np.exp(-(angle / math.radians(4.5)) ** 2)
rgb += (disc * GRADE['sun'])[..., None] * np.array([1, .86, .66], np.float32)
rgb += (halo * .3)[..., None] * np.array([1, .72, .42], np.float32)

# Below the horizon the panorama holds the haze colour, fading gently to the sea.
band = rgb[int(h * .493):int(h * .498)].mean(0)
kernel = 641
band = np.stack([np.convolve(np.r_[band[-kernel:, i], band[:, i], band[:kernel, i]], np.ones(kernel) / kernel, 'same')[kernel:-kernel] for i in range(3)], -1)
fade = smooth(.2, -22, degrees)[..., None]
blend = smooth(.35, -.25, degrees)[..., None]
rgb = rgb * (1 - blend) + band[None, ...].astype(np.float32) * (1 - fade * .5) * blend
rgb = np.clip(rgb, 0, 60).astype(np.float32)
# Ambient source for the skylight cubemap: the sun stays out (the directional light is the sun) and the
# zenith is lifted so shaded ground reads; the visible dome keeps the true grade below.
ambient = pre_disc.copy()
ambient *= (1 + 2.6 * smooth(4, 55, degrees))[..., None]
ground = np.array([.3, .25, .18], np.float32) * band.mean(0).mean() if False else np.array([.26, .22, .16], np.float32)
ambient = np.where((degrees < -1)[..., None], ground * np.clip(ambient.mean() * 2, .2, 1.2), ambient)
AMBIENT_GAIN = {'Past': 1.35, 'Present': 1.2}[ERA]
small = ambient.reshape(h // 5, 5, w // 5, 5, 3).mean(axis=(1, 3)) * AMBIENT_GAIN
small = np.clip(small, 0, 40).astype(np.float32)


out = bpy.data.images.new('sky', w, h, alpha=False, float_buffer=True)
stack = np.concatenate([rgb[::-1], np.ones((h, w, 1), np.float32)], -1)
out.pixels.foreach_set(stack.ravel())
out.filepath_raw = TARGET
out.file_format = 'OPEN_EXR'
scene = bpy.context.scene
scene.render.image_settings.file_format = 'OPEN_EXR'
scene.render.image_settings.color_depth = '16'
out.save_render(TARGET, scene=scene)
hdr = bpy.data.images.new('ambient', small.shape[1], small.shape[0], alpha=False, float_buffer=True)
hdr.pixels.foreach_set(np.concatenate([small[::-1], np.ones((small.shape[0], small.shape[1], 1), np.float32)], -1).ravel())
scene.render.image_settings.file_format = 'HDR'
ambient_path = TARGET.replace('_final.exr', '_ambient.hdr')
hdr.save_render(ambient_path, scene=scene)
print('SKY FINISHED', ERA, TARGET, ambient_path, flush=True)
