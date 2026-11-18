"""Verdant modular architecture kit: one grid, restored and damaged variants of every part.

Grid: 2.5 m bay, 3.6 m ground storey, 3.2 m upper storey, 0.45 m wall. Pivot at the lower left
outer corner, +X along the facade seen from outside, +Y into the building, ground line at Z=0.
Variants keep the footprint and pivot, so any module swaps in place between timelines:
  _R restored, _D1 weathered, _D2 heavily damaged, _D3 collapsed stub.

    blender --background --factory-startup --python build_verdant_kit.py [-- preview]
"""
import json
import math
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vgeo
from vgeo import Builder, arch_points, blob, field, jagged

OUT = HERE.parent / 'output' / 'verdant'
MESHES = OUT / 'meshes'
MESHES.mkdir(parents=True, exist_ok=True)

BW, HG, HU, T, BASE = 2.5, 3.6, 3.2, .45, -2.6
STONE = (0, 1, 0, 0)
STONE_DARK = (0, .82, 0, 0)
manifest = {}
bpy.ops.wm.read_factory_settings(use_empty=True)
collection = bpy.data.collections.new('Kit')
bpy.context.scene.collection.children.link(collection)
built = []


def smooth(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def finish(b, reach=2.0, rays=18, strength=.9, ground=None):
    b.bake_occlusion(rays=rays, reach=reach, strength=strength, ground=ground)
    obj = b.build(collection)
    vgeo.export_fbx(obj, MESHES / (obj.name + '.fbx'))
    lo = [min(v[i] for v in b.verts) for i in range(3)]
    hi = [max(v[i] for v in b.verts) for i in range(3)]
    manifest[obj.name] = {'triangles': sum(len(f[0]) - 2 for f in b.faces), 'vertices': len(b.verts), 'bounds_m': [lo, hi],
                          'slots': sorted({vgeo.SLOTS[f[1]] for f in b.faces})}
    built.append(obj)
    return obj


def painter(state, ground, seed, height):
    """Vertex paint: plaster coverage and soot, driven by how far the bay has decayed."""
    loss = {'R': .0, 'D1': .34, 'D2': .58, 'D3': .74}[state]

    def paint(x, z):
        n = field(x + seed * 3.1, z + seed, .42, 11)
        m = field(x * .7 + seed, z * .7, .95, 12)
        cover = 1.0
        if ground:
            cover *= smooth(.72, 1.08, z + (n - .5) * .5)
        # Rising damp stays even on maintained walls; loss eats the render from the corners.
        cover *= .86 + .14 * smooth(0, 1.6, z)
        cover *= 1 - smooth(.58 - loss, .86 - loss, n * .75 + m * .25) * min(1, loss * 2.4)
        soot = smooth(.5, .92, field(x + seed, z, .3, 13)) * min(1, loss * 1.6) * .8
        return (cover, 1, soot, 0)
    return paint


def core(state, seed):
    def colour(x, z):
        return (0, .62, .25 if state != 'R' else 0, 0)
    return colour


def clean_reveal(x, z):
    return (.92, .55, 0, 0)


def sill_stain(paint, cx, half, sill):
    def wrapped(x, z):
        r, g, s, w = paint(x, z)
        if abs(x - cx) < half + .12 and sill - 1.3 < z < sill:
            g *= 1 - .22 * smooth(sill - 1.3, sill, z) * smooth(half + .12, half - .1, abs(x - cx))
        return (r, g, s, w)
    return wrapped


def frame(b, x0, x1, z0, z1, depth, thick=.065, grey=False):
    colour = (0, .85, 0, 0)
    slot = 'Timber'
    b.box((x0, depth, z0), (x0 + thick, depth + .07, z1), slot, colour, .008)
    b.box((x1 - thick, depth, z0), (x1, depth + .07, z1), slot, colour, .008)
    b.box((x0, depth, z0), (x1, depth + .07, z0 + thick), slot, colour, .008)
    b.box((x0, depth, z1 - thick), (x1, depth + .07, z1), slot, colour, .008)


def glazing(b, cx, w, z0, h, depth):
    x0, x1 = cx - w / 2, cx + w / 2
    frame(b, x0, x1, z0, z0 + h, depth)
    bars = (0, .85, 0, 0)
    b.box((cx - .022, depth + .005, z0), (cx + .022, depth + .06, z0 + h), 'Timber', bars)
    for t in (.36, .68):
        b.box((x0, depth + .005, z0 + h * t - .016), (x1, depth + .06, z0 + h * t + .016), 'Timber', bars)
    b.quad((x0 + .05, depth + .04, z0 + .05), (x1 - .05, depth + .04, z0 + .05), (x1 - .05, depth + .04, z0 + h - .05),
           (x0 + .05, depth + .04, z0 + h - .05), 'Glass', (0, 1, 0, 0), [(0, 0), (1, 0), (1, 1), (0, 1)])


def surround(b, cx, w, sill, h):
    """Dressed limestone frame: projecting sill, lintel and jambs."""
    b.box((cx - w / 2 - .16, -.1, sill - .15), (cx + w / 2 + .16, .12, sill), 'Masonry', STONE, .022)
    b.box((cx - w / 2 - .17, -.075, sill + h), (cx + w / 2 + .17, .1, sill + h + .2), 'Masonry', STONE, .02)
    for side in (-1, 1):
        a = cx + side * (w / 2 + .06)
        b.box((a - .07, -.04, sill), (a + .07, .1, sill + h), 'Masonry', STONE, .014)


def shutter(b, x0, x1, z0, z1, y=-.05, hang=0.0, colour=(0, .95, 0, 0)):
    """Louvred leaf. hang swings the free edge downward for failed hinges."""
    width = x1 - x0

    def p(u, v, d=0.0):
        return (x0 + u * math.cos(hang) - v * math.sin(hang) * (z1 - z0) * 0, y + d, z0 + v * (z1 - z0) - u * math.sin(hang))
    rail = .055
    for u0, u1 in ((0, rail), (width - rail, width)):
        b.quad(p(u0, 0), p(u1, 0), p(u1, 1), p(u0, 1), 'Paint', colour)
    b.quad(p(0, 0, .03), p(width, 0, .03), p(width, 1, .03), p(0, 1, .03), 'Flat', (0, .35, 0, 0))
    count = max(5, int((z1 - z0) / .1))
    for i in range(count):
        v0, v1 = i / count, (i + .92) / count
        b.quad(p(rail, v0, .028), p(width - rail, v0, .028), p(width - rail, v1, -.004), p(rail, v1, -.004), 'Paint', colour)
    edge = .05 / (z1 - z0)
    b.quad(p(0, 0, -.006), p(width, 0, -.006), p(width, edge, -.006), p(0, edge, -.006), 'Paint', colour)
    b.quad(p(0, 1 - edge, -.006), p(width, 1 - edge, -.006), p(width, 1, -.006), p(0, 1, -.006), 'Paint', colour)


def boards(b, cx, w, z0, z1, depth, count, seed):
    """Weathered planks nailed across an opening, the repair people actually make."""
    for i in range(count):
        z = z0 + (z1 - z0) * (i + .5) / count
        tilt = (field(i * 2.1, seed, .4, 14) - .5) * .22
        over = .1 + field(i, seed, .7, 15) * .12
        b.beam((cx - w / 2 - over, depth, z - tilt), (cx + w / 2 + over, depth, z + tilt), .05, .17, 'Timber', (0, .86, .1, 0))


def interior_plate(b, x0, x1, z0, z1, y=T - .02):
    b.quad((x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1), 'Flat', (0, .3, 0, 0))


def opening_rect(cx, w, z0, z1):
    return [(cx - w / 2, z0), (cx + w / 2, z0), (cx + w / 2, z1), (cx - w / 2, z1)]


def bay_outline(h, ground, state, seed):
    z0 = BASE if ground else 0
    if state == 'D3':
        top = 1.5 if ground else .85
        edge = jagged((BW, top + .45), (0, top - .1), .95, seed)
        return [(0, z0), (BW, z0)] + edge
    return [(0, z0), (BW, z0), (BW, h), (0, h)]


def base_course(b):
    """Projecting limestone plinth along the street line."""
    b.box((0, -.07, BASE), (BW, .02, .62), 'Masonry', STONE, 0)
    b.box((0, -.09, .62), (BW, .02, .74), 'Masonry', STONE, .022)


def wall_plain(ground, state):
    h = HG if ground else HU
    name = 'SM_V_%s_Plain_%s' % ('G' if ground else 'U', state)
    b = Builder(name)
    seed = 1 + ground * 2 + len(state)
    holes = []
    if state == 'D2':
        cz = 1.9 if ground else 1.6
        holes.append(blob(1.3, cz, .95, .85, seed))
        interior_plate(b, .1, 2.4, cz - 1.2, cz + 1.2, T + .9)
    b.wall(bay_outline(h, ground, state, seed), holes, T, paint=painter(state, ground, seed, h), reveal=core(state, seed))
    if ground and state != 'D3':
        base_course(b)
    return finish(b)


def wall_window(ground, state):
    h = HG if ground else HU
    name = 'SM_V_%s_Window_%s' % ('G' if ground else 'U', state)
    b = Builder(name)
    seed = 5 + ground * 3 + len(state) * 2
    cx, w = BW / 2, 1.05
    sill, wh = (1.2, 1.7) if ground else (.72, 1.78)
    paint = sill_stain(painter(state, ground, seed, h), cx, w / 2, sill)
    b.wall(bay_outline(h, ground, state, seed), [opening_rect(cx, w, sill, sill + wh)], T, paint=paint,
           reveal=clean_reveal if state == 'R' else core(state, seed))
    surround(b, cx, w, sill, wh)
    interior_plate(b, cx - w / 2, cx + w / 2, sill, sill + wh, T - .02)
    if ground:
        base_course(b)
    if state == 'R':
        glazing(b, cx, w, sill, wh, .2)
        shutter(b, cx - w - .16, cx - w / 2 - .16, sill, sill + wh)
        shutter(b, cx + w / 2 + .16, cx + w + .16, sill, sill + wh)
    elif state == 'D1':
        frame(b, cx - w / 2, cx + w / 2, sill, sill + wh, .2)
        b.box((cx - .02, .205, sill), (cx + .02, .26, sill + wh), 'Timber', (0, .8, .15, 0))
        shutter(b, cx - w - .16, cx - w / 2 - .16, sill, sill + wh, hang=.0, colour=(0, .72, .15, 0))
        shutter(b, cx + w / 2 + .12, cx + w + .1, sill - .25, sill + wh - .3, hang=.12, colour=(0, .68, .2, 0))
    elif state == 'D2':
        boards(b, cx, w, sill + .05, sill + wh - .05, -.03, 6, seed)
    return finish(b)


def wall_door(state):
    name = 'SM_V_G_Door_' + state
    b = Builder(name)
    seed = 21 + len(state)
    cx, hw, spring = BW / 2, .72, 2.08
    opening = [(cx - hw, .04), (cx + hw, .04)] + arch_points(cx, spring, hw, .62, 12)[0:] + []
    opening = [(cx - hw, .04), (cx + hw, .04)] + [p for p in arch_points(cx, spring, hw, .62, 12)]
    b.wall(bay_outline(HG, True, 'R' if state == 'REP' else state, seed), [opening], T,
           paint=painter({'R': 'R', 'D1': 'D1', 'D2': 'D2', 'REP': 'D1'}[state], True, seed, HG),
           reveal=clean_reveal if state == 'R' else core(state, seed))
    base_course(b)
    # Voussoirs: individually cut stones with a keystone.
    stones = 11
    for i in range(stones):
        a0, a1 = math.pi * i / stones + .012, math.pi * (i + 1) / stones - .012
        r0, rz0 = hw + .01, .63
        out = .3 if i == stones // 2 else .24
        loop = [(cx + r0 * math.cos(a0), spring + rz0 * math.sin(a0)), (cx + (r0 + out) * math.cos(a0), spring + (rz0 + out) * math.sin(a0)),
                (cx + (r0 + out) * math.cos(a1), spring + (rz0 + out) * math.sin(a1)), (cx + r0 * math.cos(a1), spring + rz0 * math.sin(a1))]
        b.wall(loop, (), .46 + (.05 if i == stones // 2 else 0), paint=lambda x, z: STONE, reveal=lambda x, z: STONE, spacing=9, y=-.06)
    for side in (-1, 1):
        for i in range(5):
            x = cx + side * (hw + .1)
            z0 = .04 + i * .41
            wide = .16 if i % 2 else .22
            b.box((x - wide, -.04, z0 + .01), (x + wide, .46, z0 + .39), 'Masonry', STONE, .014)
    b.box((cx - hw - .28, -.42, -.32), (cx + hw + .28, .12, .04), 'Masonry', STONE, .028)
    # Plank door on strap hinges, recessed in the reveal.
    door = [(cx - hw + .01, .05), (cx + hw - .01, .05)] + [(cx + (hw - .01) * math.cos(t), spring + .61 * math.sin(t)) for t in [math.pi * i / 12 for i in range(13)]]
    if state in ('R', 'D1', 'REP'):
        tone = {'R': (0, .96, 0, 0), 'D1': (0, .78, .1, 0), 'REP': (0, .92, 0, 0)}[state]
        b.wall(door, (), .05, 'Paint' if state == 'R' else 'Timber', paint=lambda x, z: tone, reveal=lambda x, z: tone, spacing=9, y=.28)
        for i in range(1, 7):
            x = cx - hw + i * hw * 2 / 7
            b.box((x - .006, .262, .1), (x + .006, .285, spring + .4), 'Timber', (0, .55, 0, 0))
        for z in (.5, 1.75):
            b.box((cx - hw + .02, .25, z - .03), (cx + .25, .285, z + .03), 'Iron', STONE, .004)
        b.cylinder((cx + hw - .22, .22, 1.08), (cx + hw - .22, .28, 1.08), .05, .05, 'Iron', STONE, 8)
    if state == 'REP':
        # A cared-for repair: fresh planks over the old door, lantern hook above.
        boards(b, cx, hw * 1.6, .7, 1.3, .22, 3, seed)
    if state == 'D2':
        boards(b, cx, hw * 2, .3, spring + .3, -.02, 8, seed)
        interior_plate(b, cx - hw, cx + hw, .04, spring + .6, T)
    return finish(b)


def wall_shop(state):
    name = 'SM_V_G_Shop_' + state
    b = Builder(name)
    seed = 31 + len(state)
    cx, hw, spring = BW / 2, 1.0, 2.0
    opening = [(cx - hw, .06), (cx + hw, .06)] + arch_points(cx, spring, hw, .68, 14)
    b.wall(bay_outline(HG, True, state, seed), [opening], T, paint=painter(state, True, seed, HG), reveal=core(state, seed))
    b.box((0, -.07, BASE), (cx - hw + .02, .02, .62), 'Masonry', STONE, 0)
    b.box((cx + hw - .02, -.07, BASE), (BW, .02, .62), 'Masonry', STONE, 0)
    b.box((cx - hw - .1, -.28, -.22), (cx + hw + .1, .46, .06), 'Masonry', STONE, .025)
    stones = 13
    for i in range(stones):
        a0, a1 = math.pi * i / stones + .012, math.pi * (i + 1) / stones - .012
        out = .27 if i == stones // 2 else .2
        loop = [(cx + hw * math.cos(a0), spring + .68 * math.sin(a0)), (cx + (hw + out) * math.cos(a0), spring + (.68 + out) * math.sin(a0)),
                (cx + (hw + out) * math.cos(a1), spring + (.68 + out) * math.sin(a1)), (cx + hw * math.cos(a1), spring + .68 * math.sin(a1))]
        b.wall(loop, (), .47, paint=lambda x, z: STONE, reveal=lambda x, z: STONE, spacing=9, y=-.05)
    # Shallow shop room so the opening has real depth from the street.
    depth = 1.7
    dim = (.85, .38, 0, 0)
    b.quad((cx - hw - .3, T, .05), (cx - hw - .3, depth, .05), (cx + hw + .3, depth, .05), (cx + hw + .3, T, .05), 'Masonry', (0, .5, 0, 0))
    b.quad((cx + hw + .3, depth, .05), (cx - hw - .3, depth, .05), (cx - hw - .3, depth, 3.0), (cx + hw + .3, depth, 3.0), 'Masonry', dim)
    b.quad((cx - hw - .3, T, .05), (cx - hw - .3, T, 3.0), (cx - hw - .3, depth, 3.0), (cx - hw - .3, depth, .05), 'Masonry', dim)
    b.quad((cx + hw + .3, T, .05), (cx + hw + .3, depth, .05), (cx + hw + .3, depth, 3.0), (cx + hw + .3, T, 3.0), 'Masonry', dim)
    b.quad((cx - hw - .3, T, 3.0), (cx + hw + .3, T, 3.0), (cx + hw + .3, depth, 3.0), (cx - hw - .3, depth, 3.0), 'Timber', (0, .3, 0, 0))
    if state == 'R':
        b.box((cx - .9, .5, .06), (cx + .9, 1.0, .92), 'Timber', (0, .7, 0, 0), .012)
        b.box((cx - .94, .46, .92), (cx + .94, 1.04, .98), 'Timber', (0, .9, 0, 0), .012)
        for z in (1.45, 2.05):
            b.box((cx - 1.15, 1.42, z), (cx + 1.15, 1.68, z + .05), 'Timber', (0, .6, 0, 0))
        for i in range(7):
            x = cx - .95 + i * .32
            z = 1.5
            r = .07 + field(i, 2, .9, 16) * .06
            b.cylinder((x, 1.54, z), (x, 1.54, z + r * 3), r, r * .7, 'Terracotta', (0, .62, 0, 0), 8)
        for i in range(4):
            x = cx - .6 + i * .4
            b.cylinder((x, .75, .98), (x, .75, 1.2), .1, .13, 'Terracotta', (0, .85, 0, 0), 8)
    elif state == 'D1':
        # Half-height plank closure: the shop is shut, not abandoned.
        for i in range(10):
            x = cx - hw + .1 + i * .2
            b.beam((x, .18, .06), (x, .18, 1.25 + field(i, 3, .6, 17) * .35), .18, .04, 'Timber', (0, .85, .12, 0))
        b.beam((cx - hw, .15, .7), (cx + hw, .15, .76), .1, .06, 'Timber', (0, .8, .12, 0))
    elif state == 'D2':
        # Rubble infill walled up after the war, left unpainted.
        b.wall(opening, (), .16, paint=lambda x, z: (0, .86, .12 * field(x, z, .4, 18), 0), reveal=lambda x, z: (0, .7, 0, 0), y=.1)
    return finish(b)


def wall_balcony(state):
    name = 'SM_V_U_Balcony_' + state
    b = Builder(name)
    seed = 41 + len(state)
    cx, w, h = BW / 2, 1.2, 2.42
    b.wall(bay_outline(HU, False, state, seed), [opening_rect(cx, w, .03, h)], T,
           paint=sill_stain(painter(state, False, seed, HU), cx, w / 2, .02),
           reveal=clean_reveal if state == 'R' else core(state, seed))
    b.box((cx - w / 2 - .17, -.075, h), (cx + w / 2 + .17, .1, h + .2), 'Masonry', STONE, .02)
    for side in (-1, 1):
        a = cx + side * (w / 2 + .06)
        b.box((a - .07, -.04, 0), (a + .07, .1, h), 'Masonry', STONE, .014)
    interior_plate(b, cx - w / 2, cx + w / 2, .03, h, T - .02)
    left, right = .18, BW - .18
    deck = -1.08
    corbel = lambda x: [b.box((x - .13, -.42 + d * .12, -.42 + d * .16), (x + .13, .02, -.26 + d * .16), 'Masonry', STONE, .018) for d in range(4)]
    if state in ('R', 'D1'):
        b.box((left, deck, -.2), (right, .02, -.02), 'Masonry', STONE_DARK if state == 'D1' else STONE, .025)
        for x in (left + .32, right - .32):
            for d in range(4):
                length = .95 - d * .24
                b.box((x - .13, -length, -.58 + d * .14), (x + .13, .02, -.42 + d * .14), 'Masonry', STONE, .018)
    else:
        for x in (left + .32, right - .32):
            b.box((x - .13, -.32, -.42), (x + .13, .02, -.26), 'Masonry', (0, .8, .25, 0), .018)
    if state == 'R':
        glazing(b, cx - w / 4, w / 2, .05, h - .06, .22)
        glazing(b, cx + w / 4, w / 2, .05, h - .06, .22)
        shutter(b, cx - w - .16, cx - w / 2 - .16, .1, h - .04)
        shutter(b, cx + w / 2 + .16, cx + w + .16, .1, h - .04)
    elif state == 'D1':
        frame(b, cx - w / 2, cx + w / 2, .05, h, .22)
    else:
        boards(b, cx, w, .15, h - .15, -.03, 7, seed)
    # Timber balustrade in the same posts and rails as the street railing.
    if state != 'D2':
        tone = (0, .92, 0, 0) if state == 'R' else (0, .78, .1, 0)
        posts = [(left + .04, deck + .04), (right - .04, deck + .04)]
        for x, y in posts:
            b.box((x - .05, y - .05, -.02), (x + .05, y + .05, 1.04), 'Timber', tone, .012)
        rail_end = right if state == 'R' else cx + .1
        b.beam((left + .04, deck + .04, 1.04), (rail_end - .04, deck + .04, 1.04 if state == 'R' else .98), .09, .07, 'Timber', tone)
        b.beam((left + .04, deck + .04, .12), (rail_end - .04, deck + .04, .12), .07, .06, 'Timber', tone)
        for y0, y1, x in ((deck + .04, .02, left + .04), (deck + .04, .02, right - .04)):
            if state == 'R' or x == left + .04:
                b.beam((x, y0, 1.04), (x, y1, 1.04), .09, .07, 'Timber', tone)
        count = int((rail_end - left) / .16)
        for i in range(1, count):
            x = left + i * .16
            if state == 'D1' and field(i, 7, .7, 19) > .62:
                continue
            b.box((x - .022, deck + .022, .14), (x + .022, deck + .066, 1.0), 'Timber', tone)
        for i in range(1, 6):
            for x in ((left + .04), (right - .04)):
                if state == 'D1' and x > left + 1:
                    continue
                y = deck + i * .18
                b.box((x - .022, y - .022, .14), (x + .022, y + .022, 1.0), 'Timber', tone)
    return finish(b)


def band(state):
    b = Builder('SM_V_Band_' + state)
    if state == 'R':
        b.box((0, -.07, -.1), (BW, .03, .09), 'Masonry', STONE, .022)
    else:
        for i in range(4):
            if field(i, 2, .9, 20) > .68:
                continue
            x = i * BW / 4
            b.box((x + .01, -.07, -.1), (x + BW / 4 - .01, .03, .09), 'Masonry', STONE_DARK, .022)
    return finish(b, reach=.8, rays=10)


def cornice(state):
    b = Builder('SM_V_Cornice_' + state)
    keep = (lambda i: True) if state == 'R' else (lambda i: field(i, 5, .7, 21) < .66)
    b.box((0, -.05, -.34), (BW, .04, -.2), 'Masonry', STONE, .018)
    for i in range(5):
        if not keep(i):
            continue
        x = (i + .5) * BW / 5
        b.box((x - .09, -.26, -.2), (x + .09, .04, -.03), 'Masonry', STONE, .016)
    for i in range(4):
        if keep(i + 9):
            x = i * BW / 4
            b.box((x, -.34, -.03), (x + BW / 4, .04, .1), 'Masonry', STONE, .02)
    return finish(b, reach=.9, rays=10)


def quoin(ground):
    b = Builder('SM_V_Quoin_' + ('G' if ground else 'U'))
    h = HG if ground else HU
    rows = int(h / .42)
    for i in range(rows):
        z = i * h / rows
        z1 = z + h / rows - .018
        long_face = i % 2 == 0
        tone = (0, .96 - .05 * field(i, 1, .9, 22), 0, 0)
        b.box((-.035, -.035, z), (.62 if long_face else .36, .12, z1), 'Masonry', tone, .018)
        b.box((-.035, -.035, z), (.12, .36 if long_face else .62, z1), 'Masonry', tone, .018)
    return finish(b, reach=.5, rays=6, strength=.4)


def roof(state):
    """One bay of pitched roof over 4 m of run, scaled per building. Barrel tiles are real
    geometry so the eave and every damaged edge have the right silhouette."""
    b = Builder('SM_V_Roof_' + state)
    run, rise, over = 4.0, 1.6, .55
    slope = rise / run
    columns, section, cells = 11, 5, 9
    cw = BW / columns
    y0 = -over
    z_at = lambda y: y * slope + .22
    length = (run + over) * math.hypot(1, slope)

    def tile_present(col, cell):
        u, v = (col + .5) / columns * BW, (cell + .5) / cells * (run + over) - over
        if state == 'R':
            return True
        n = field(u, v, .36, 23)
        d = math.hypot(u - 1.3, (v - 2.0) * .8)
        if state == 'D1':
            return d + (n - .5) * 2.4 > 1.0
        # D2: only tiles along the eave and ridge hold on.
        return (v < .1 and n < .62) or (v > 3.2 and n < .42)
    for col in range(columns):
        x0 = col * cw
        grid = []
        for cell in range(cells + 1):
            y = y0 + (run + over) * cell / cells
            row = []
            for k in range(section):
                s = k / (section - 1)
                row.append(((x0 + s * cw * 1.04), y, z_at(y) + math.sin(s * math.pi) * .085 + .012 * (cell % 2)))
            grid.append(row)
        for cell in range(cells):
            if not tile_present(col, cell):
                continue
            v0, v1 = cell / cells * length / BW, (cell + 1) / cells * length / BW
            for k in range(section - 1):
                u0, u1 = (col + k / (section - 1)) / columns, (col + (k + 1) / (section - 1)) / columns
                ao0 = .55 + .45 * math.sin(k / (section - 1) * math.pi)
                ao1 = .55 + .45 * math.sin((k + 1) / (section - 1) * math.pi)
                ids = [b.vertex(grid[cell][k], (0, ao0, 0, 0)), b.vertex(grid[cell][k + 1], (0, ao1, 0, 0)),
                       b.vertex(grid[cell + 1][k + 1], (0, ao1, 0, 0)), b.vertex(grid[cell + 1][k], (0, ao0, 0, 0))]
                b.face(ids, 'Roof', [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
    tone = (0, .9, 0, 0) if state == 'R' else (0, .74, .24, 0)
    if state == 'R':
        b.quad((0, y0 + .02, z_at(y0) - .02), (0, run, z_at(run) - .02), (BW, run, z_at(run) - .02), (BW, y0 + .02, z_at(y0) - .02), 'Timber', (0, .6, 0, 0))
    rafters = 4
    for i in range(rafters):
        x = (i + .5) * BW / rafters
        reach = run
        if state == 'D2' and field(i, 9, .9, 24) > .52:
            reach = run * (.35 + field(i, 3, .9, 25) * .4)
        b.beam((x, y0, z_at(y0) - .1), (x, reach, z_at(reach) - .1), .1, .15, 'Timber', tone)
    if state != 'R':
        for i in range(10):
            y = y0 + .3 + i * .46
            if state == 'D2' and field(i, 4, .9, 26) > .4:
                continue
            b.beam((0, y, z_at(y) - .005), (BW * (1 if state == 'D1' else .72), y, z_at(y) - .005), .05, .04, 'Timber', (0, .82, .15, 0))
    b.box((0, y0 - .04, z_at(y0) - .09), (BW, y0 + .02, z_at(y0) + .02), 'Timber', tone, .01)
    return finish(b, reach=1.2, rays=8, strength=.6)


def ridge(state):
    b = Builder('SM_V_Ridge_' + state)
    pieces = 6
    for i in range(pieces):
        if state != 'R' and field(i, 8, .9, 27) > .6:
            continue
        x = i * BW / pieces
        b.cylinder((x, 0, .0), (x + BW / pieces - .012, 0, .0), .12, .13, 'Roof', (0, .9, 0, 0), 8, caps=True)
    b.beam((0, 0, -.16), (BW, 0, -.16), .14, .2, 'Timber', (0, .7, 0, 0))
    return finish(b, reach=.6, rays=6, strength=.4)


def gable(state):
    """Triangular wall head for a 7.5 m span; instance X scale adapts it to the building."""
    b = Builder('SM_V_Gable_' + state)
    span, rise = 7.5, 1.5
    seed = 51 + len(state)
    if state == 'R':
        outline = [(0, 0), (span, 0), (span / 2, rise)]
    else:
        outline = [(0, 0), (span, 0)] + jagged((span, .05), (span * .62, rise * .62), .3, seed) + jagged((span * .62, rise * .62), (span * .34, rise * .34), .55, seed + 2) + [(0, 0.05)]
    b.wall(outline, (), T, paint=painter('R' if state == 'R' else 'D2', False, seed, rise), reveal=core(state, seed))
    return finish(b, reach=1.0, rays=8)


def chimney(state):
    b = Builder('SM_V_Chimney_' + state)
    seed = 61
    w, d = .85, .6
    h = 2.5 if state == 'R' else 1.5
    paint = painter('R' if state == 'R' else 'D2', False, seed, h)
    for face, (x0, y0, x1, y1) in enumerate(((0, 0, w, 0), (w, 0, w, d), (w, d, 0, d), (0, d, 0, 0))):
        length = math.hypot(x1 - x0, y1 - y0)
        top = [(length, h), (0, h)] if state == 'R' else jagged((length, h - .1 * face), (0, h + .1 * face), .4, seed + face)
        loop = [(0, -1.2), (length, -1.2)] + top
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        place = lambda p, ux=ux, uy=uy, x0=x0, y0=y0: (x0 + ux * p[0] - uy * p[1], y0 + uy * p[0] + ux * p[1], p[2])
        b.wall(loop, (), .08, paint=paint, reveal=core(state, seed), axis_map=place, spacing=.3)
    if state == 'R':
        b.box((-.08, -.08, h), (w + .08, d + .08, h + .14), 'Masonry', STONE, .02)
        b.cylinder((.26, .3, h + .14), (.26, .3, h + .5), .1, .08, 'Terracotta', STONE, 8)
        b.cylinder((.6, .3, h + .14), (.6, .3, h + .42), .1, .08, 'Terracotta', STONE, 8)
    return finish(b, reach=.8, rays=8)


def floor_slab(state):
    """Interior floor exposed by damage: joists under boards, 2.5 x 2.5 m."""
    b = Builder('SM_V_Floor_' + state)
    tone = (0, .72, .2, 0)
    joists = 4
    for i in range(joists):
        x = (i + .5) * BW / joists
        end = BW if state == 'R' else BW * (.5 + field(i, 6, .9, 28) * .5)
        b.beam((x, 0, -.14), (x, end, -.14), .11, .2, 'Timber', tone)
    count = 9
    for i in range(count):
        y = i * BW / count
        end = BW if state == 'R' else BW * (.42 + field(i, 2, .9, 29) * .6)
        b.box((0, y + .006, -.04), (end, y + BW / count - .006, 0), 'Timber', tone)
    return finish(b, reach=.5, rays=6, strength=.4)


def downpipe():
    b = Builder('SM_V_Downpipe')
    b.cylinder((0, -.06, 0), (0, -.06, HU), .045, .045, 'Terracotta', (0, .9, 0, 0), 8, caps=False)
    for z in (.6, 2.2):
        b.box((-.06, -.11, z), (.06, 0, z + .03), 'Iron', STONE)
    return finish(b, reach=.3, rays=4, strength=.2)


for g in (True, False):
    for s in ('R', 'D1', 'D2', 'D3'):
        wall_plain(g, s)
    for s in ('R', 'D1', 'D2'):
        wall_window(g, s)
for s in ('R', 'D1', 'D2', 'REP'):
    wall_door(s)
for s in ('R', 'D1', 'D2'):
    wall_shop(s)
    wall_balcony(s)
    roof(s)
for s in ('R', 'D'):
    band(s)
    cornice(s)
    ridge(s)
    gable(s)
    chimney(s)
    floor_slab(s)
quoin(True)
quoin(False)
downpipe()

existing = {}
path = OUT / 'kit_manifest.json'
if path.exists():
    existing = json.loads(path.read_text(encoding='utf-8'))
existing.update(manifest)
path.write_text(json.dumps(existing, indent=2), encoding='utf-8')
print('KIT MODULES', len(manifest), 'triangles', sum(m['triangles'] for m in manifest.values()), flush=True)

if 'preview' in sys.argv:
    import kit_preview
    kit_preview.render(built, OUT / 'previews' / 'kit_architecture.png', columns=8, spacing=4.0)
