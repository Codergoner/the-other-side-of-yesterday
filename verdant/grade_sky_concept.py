"""Concept pass of 17 November 2026: a second grade over the finished sky panoramas, toward the entrant's reference
boards and city atlas. Past = golden hour going to sunset (deep blue-violet zenith, rose and amber toward the sun,
peach cloud faces with mauve shadow sides). Present = a cool grey-violet evening with one warm band under the cloud.

    blender --background --python grade_sky_concept.py -- <Past|Present>

Reads output/verdant/sky/Sky_<era>_final.exr and Sky_<era>_ambient.hdr (left untouched, they are the revert), writes
Sky_<era>_concept.exr, Sky_<era>_concept_ambient.hdr and a tonemapped preview PNG. The sun keeps its direction, so
the shadows of the directional light still agree with the painted sun.
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np

ERA = sys.argv[sys.argv.index('--') + 1]
SKY = Path(__file__).resolve().parent.parent / 'output' / 'verdant' / 'sky'
SUN = {'Past': (62.0, 13.0), 'Present': (66.0, 10.5)}[ERA]
LUMA = np.array([.2126, .7152, .0722], np.float32)
# Sky colour by elevation (degrees, colour at unit luminance weight); the second set is used toward the sun.
LOOK = {
    'Past': dict(
        away=[(0, (.92, .56, .52)), (7, (.74, .46, .60)), (20, (.40, .36, .68)), (45, (.20, .25, .62)), (90, (.13, .18, .52))],
        sunward=[(0, (1.30, .66, .26)), (7, (1.18, .60, .34)), (20, (.80, .48, .52)), (45, (.30, .30, .62)), (90, (.13, .18, .52))],
        cloud_lit=(1.22, .86, .66), cloud_lit_sun=(1.42, .82, .44), cloud_dark=(.80, .66, .96), sky_keep=.18, sky_level=1.0, cloud_level=1.0,
        saturation=1.15, depth=[1.0, .92, .66, .44, .32], shoulder=2.4),
    'Present': dict(
        away=[(0, (.60, .54, .60)), (7, (.46, .44, .56)), (20, (.32, .33, .46)), (45, (.22, .24, .36)), (90, (.17, .19, .30))],
        sunward=[(0, (1.10, .70, .40)), (7, (.84, .58, .48)), (20, (.42, .38, .48)), (45, (.23, .25, .36)), (90, (.17, .19, .30))],
        cloud_lit=(.94, .84, .86), cloud_lit_sun=(1.22, .86, .58), cloud_dark=(.62, .60, .78), sky_keep=.30, sky_level=.80, cloud_level=.82,
        saturation=.86, depth=[1.0, .95, .8, .66, .55], shoulder=3.2),
}[ERA]


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def load(path):
    image = bpy.data.images.load(str(path))
    w, h = image.size
    px = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(px)
    rgb = px.reshape(h, w, 4)[::-1][..., :3].copy()
    bpy.data.images.remove(image)
    return rgb


def save(rgb, path, kind):
    h, w = rgb.shape[:2]
    out = bpy.data.images.new('out', w, h, alpha=False, float_buffer=True)
    out.pixels.foreach_set(np.concatenate([rgb[::-1], np.ones((h, w, 1), np.float32)], -1).ravel())
    scene = bpy.context.scene
    scene.render.image_settings.file_format = kind
    if kind == 'OPEN_EXR':
        scene.render.image_settings.color_depth = '16'
    out.save_render(str(path), scene=scene)
    bpy.data.images.remove(out)


def ramp(stops, degrees):
    xs = [s[0] for s in stops]
    return np.stack([np.interp(degrees, xs, [s[1][i] for s in stops]) for i in range(3)], -1).astype(np.float32)


def grade(rgb, ambient=False):
    h, w = rgb.shape[:2]
    el = ((.5 - (np.arange(h) + .5) / h) * math.pi)[:, None]
    az = (((np.arange(w) + .5) / w - .5) * math.tau)[None, :]
    sa, se = math.radians(SUN[0]), math.radians(SUN[1])
    sun = np.array([math.sin(sa) * math.cos(se), math.cos(sa) * math.cos(se), math.sin(se)])
    dirs = np.stack([np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.broadcast_to(np.sin(el), (h, w))], -1)
    angle = np.arccos(np.clip(dirs @ sun, -1, 1))
    toward = np.exp(-(angle / math.radians(58)) ** 2)[..., None]
    degrees = np.broadcast_to(np.maximum(np.degrees(el), 0), (h, w))
    lum = np.maximum(rgb @ LUMA, 1e-4)
    # Open sky is the blue part of the bake; cloud and the glow round the sun are near neutral.
    blue = rgb[..., 2] / np.maximum(rgb[..., 0], 1e-4)
    sky = smooth(1.12, 1.55, blue)[..., None]
    target = ramp(LOOK['away'], degrees) * (1 - toward) + ramp(LOOK['sunward'], degrees) * toward
    target = target / np.maximum(target @ LUMA, 1e-4)[..., None]
    # The evening sky keeps the bake's brightness structure but takes the reference's colour by height.
    # The zenith darkens toward night; the band over the horizon keeps the light.
    falloff = np.interp(degrees, [0, 8, 22, 45, 90], LOOK['depth'])[..., None].astype(np.float32)
    painted = target * lum[..., None] * LOOK['sky_level'] * falloff
    open_sky = rgb * LOOK['sky_keep'] + painted * (1 - LOOK['sky_keep'])
    # Cloud: faces that catch the light go peach (amber toward the sun), shadow sides go mauve.
    median = np.median(lum[: h // 2])
    lit = smooth(median * .7, median * 2.2, lum)[..., None]
    face = np.array(LOOK['cloud_lit'], np.float32) * (1 - toward) + np.array(LOOK['cloud_lit_sun'], np.float32) * toward
    tint = np.array(LOOK['cloud_dark'], np.float32) * (1 - lit) + face * lit
    cloud = rgb * tint * LOOK['cloud_level']
    out = cloud * (1 - sky) + open_sky * sky
    grey = (out @ LUMA)[..., None]
    out = grey + (out - grey) * LOOK['saturation']
    # A shoulder: the headset shows this dome without a tonemapper, so the bright band over the horizon must hold
    # its colour below 1.0 instead of clipping to white. The sun's own core keeps its range (below).
    out = np.maximum(out, 0)
    peak = out.max(-1, keepdims=True)
    out = out / (1 + peak / LOOK['shoulder'])
    # Below the horizon the panorama holds the graded haze of the row just above it, fading down, so the far sea
    # still meets the sky without a seam (the same construction as finish_sky.py).
    top = np.searchsorted(-np.degrees(el[:, 0]), -1.2)
    low = np.searchsorted(-np.degrees(el[:, 0]), -.25)
    band = out[top:max(low, top + 1)].mean(0)
    kernel = max(3, (w // 8) | 1)
    band = np.stack([np.convolve(np.r_[band[-kernel:, i], band[:, i], band[:kernel, i]], np.ones(kernel) / kernel, 'same')[kernel:-kernel] for i in range(3)], -1)
    true_degrees = np.broadcast_to(np.degrees(el), (h, w))
    fade = smooth(.2, -22, true_degrees)[..., None]
    blend = smooth(.35, -.25, true_degrees)[..., None]
    if ambient:
        # The skylight source keeps finish_sky.py's ground bounce under the horizon.
        out = np.where((true_degrees < -1)[..., None], rgb, out)
    else:
        out = out * (1 - blend) + band[None, ...].astype(np.float32) * (1 - fade * .5) * blend
    if not ambient:
        # The disc and its tight halo come through the grade a little warmer, never cooler.
        core = np.exp(-(angle / math.radians(3.2)) ** 2)[..., None]
        out = out * (1 - core) + rgb * np.array([1.0, .9, .74], np.float32) * core
    return np.clip(out, 0, 60).astype(np.float32)


final = grade(load(SKY / ('Sky_%s_final.exr' % ERA)))
save(final, SKY / ('Sky_%s_concept.exr' % ERA), 'OPEN_EXR')
ambient = grade(load(SKY / ('Sky_%s_ambient.hdr' % ERA)), ambient=True)
save(ambient, SKY / ('Sky_%s_concept_ambient.hdr' % ERA), 'HDR')
# Preview: the dome's gain, then a plain display curve (what an untonemapped headset frame would show).
gain = {'Past': .9, 'Present': .8}[ERA]
small = final[::4, ::4] * gain
png = np.clip(small, 0, 1) ** (1 / 2.2)
image = bpy.data.images.new('preview', png.shape[1], png.shape[0], alpha=False)
image.pixels.foreach_set(np.concatenate([png[::-1], np.ones(png.shape[:2] + (1,), np.float32)], -1).ravel())
image.filepath_raw = str(SKY / ('Sky_%s_concept_preview.png' % ERA))
image.file_format = 'PNG'
image.save()
stats = {'sky_mean': [round(float(v), 3) for v in final[: final.shape[0] // 2].reshape(-1, 3).mean(0)],
         'ambient_mean': [round(float(v), 3) for v in ambient[: ambient.shape[0] // 2].reshape(-1, 3).mean(0)]}
print('SKY CONCEPT', ERA, stats, flush=True)
