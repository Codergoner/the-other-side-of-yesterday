"""Verdant street furniture, vegetation and storytelling props. Pivot at ground centre unless
noted. Most come as an inhabited _R and a post-war _D: the same stall frame, emptied.
"""
import json
import math
import random
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
bpy.ops.wm.read_factory_settings(use_empty=True)
collection = bpy.data.collections.new('Props')
bpy.context.scene.collection.children.link(collection)
manifest = {}
built = []
STONE = (0, 1, 0, 0)
WOOD = (0, .9, 0, 0)
OLD = (0, .72, .18, 0)
TEAL = (.11, .3, .31, .2)
CREAM = (.78, .7, .54, .2)
RUST = (.42, .2, .13, .2)
GREY = (.28, .3, .3, .2)
CELL = dict(olive=(0, 0), ivy=(1, 0), cypress=(2, 0), pine=(3, 0), bougainvillea=(0, 1), flowers=(1, 1), grass=(2, 1), vine=(3, 1))


def finish(b, reach=1.2, rays=10, strength=.7):
    b.bake_occlusion(rays=rays, reach=reach, strength=strength)
    obj = b.build(collection)
    vgeo.export_fbx(obj, MESHES / (obj.name + '.fbx'))
    lo = [min(v[i] for v in b.verts) for i in range(3)]
    hi = [max(v[i] for v in b.verts) for i in range(3)]
    manifest[obj.name] = {'triangles': sum(len(f[0]) - 2 for f in b.faces), 'vertices': len(b.verts), 'bounds_m': [lo, hi],
                          'slots': sorted({vgeo.SLOTS[f[1]] for f in b.faces})}
    built.append(obj)


def cell_uv(name, flip=False):
    col, row = CELL[name]
    u0, u1 = col / 4, (col + 1) / 4
    v0, v1 = 1 - (row + 1) / 4, 1 - row / 4
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def card(b, centre, w, h, angle, cell, tilt=0.0, wind=.6, shade=1.0):
    cx, cy, cz = centre
    dx, dy = math.cos(angle) * w / 2, math.sin(angle) * w / 2
    tx, ty = -math.sin(angle) * tilt * h, math.cos(angle) * tilt * h
    colour = (shade, shade, shade, wind)
    low = (shade * .78, shade * .78, shade * .78, wind * .25)
    ids = [b.vertex((cx - dx, cy - dy, cz), low), b.vertex((cx + dx, cy + dy, cz), low),
           b.vertex((cx + dx + tx, cy + dy + ty, cz + h), colour), b.vertex((cx - dx + tx, cy - dy + ty, cz + h), colour)]
    b.face(ids, 'Leaf', cell_uv(cell))


def clump(b, centre, radius, cell, count=3, rng=None, shade=1.0, height=None):
    rng = rng or random
    h = height or radius * 2
    for i in range(count):
        a = i * math.pi / count + rng.uniform(-.2, .2)
        card(b, (centre[0], centre[1], centre[2] - h / 2), radius * 2, h, a, cell, rng.uniform(-.25, .25), shade=shade * rng.uniform(.82, 1.08))


def rubble(name, seed, size, blocks):
    b = Builder('SM_V_Rubble_' + name)
    r = random.Random(seed)
    for i in range(blocks):
        a = r.uniform(0, math.tau)
        d = abs(r.gauss(0, 1)) * size * .42
        x, y = math.cos(a) * d, math.sin(a) * d
        h = max(.1, size * .62 * (1 - d / (size * 1.3)))
        z = r.uniform(0, h)
        s = r.uniform(.1, .34)
        tone = (r.choice((0, 0, .7)), r.uniform(.68, .92), r.uniform(0, .3), 0)
        b.box((x - s, y - s * r.uniform(.6, 1.2), z), (x + s, y + s * r.uniform(.6, 1.2), z + s * r.uniform(.5, 1.1)), 'Masonry', tone, .03)
    for i in range(int(blocks / 12)):
        a = r.uniform(0, math.tau)
        b.beam((math.cos(a) * size * .6, math.sin(a) * size * .6, r.uniform(0, .3)),
               (-math.cos(a) * size * .4, -math.sin(a) * size * .4, r.uniform(.2, size * .55)), .13, .17, 'Timber', OLD)
    finish(b, .9, 8, .6)


def parapet(name, slope, state):
    """Two metre bay of the street parapet: limestone pier, cap, timber rail, curb. Pier at X=0."""
    b = Builder('SM_V_Parapet_%s_%s' % (name, state))
    run = 2.0
    tone = STONE if state == 'R' else (0, .88, .2, 0)
    broken = state == 'D2'
    if not broken:
        b.box((-.3, -.3, -.5), (.3, .3, 1.16), 'Masonry', (.75 if state == 'R' else .3, 1, tone[2], 0), .03)
        b.box((-.38, -.38, 1.16), (.38, .38, 1.34), 'Masonry', STONE, .035)
        b.box((-.34, -.34, -.1), (.34, .34, .14), 'Masonry', STONE, .03)
    else:
        for i in range(5):
            b.box((-.28 + i * .05, -.26, -.5 + i * .17), (.28 - i * .03, .26, -.34 + i * .17 + (field(i, 1, .9, 41) * .1)), 'Masonry', tone, .03)
    for i in range(4):
        x0, x1 = .3 + i * .35, .3 + (i + 1) * .35 - .01
        z0, z1 = x0 * slope, x1 * slope
        if broken and i == 3:
            continue
        b.quad((x0, -.21, z1 * 0 + z0 - .5), (x1, -.21, z1 - .5), (x1, -.21, z1 + .26), (x0, -.21, z0 + .26), 'Masonry', tone)
        b.quad((x0, -.21, z0 + .26), (x1, -.21, z1 + .26), (x1, .21, z1 + .26), (x0, .21, z0 + .26), 'Masonry', tone)
        b.quad((x1, .21, z1 - .5), (x0, .21, z0 - .5), (x0, .21, z0 + .26), (x1, .21, z1 + .26), 'Masonry', tone)
    rail = WOOD if state == 'R' else OLD
    if state == 'R':
        b.beam((.3, 0, 1.0 + .3 * slope), (run - .3, 0, 1.0 + (run - .3) * slope), .13, .13, 'Timber', rail)
        b.beam((.3, 0, .42 + .3 * slope), (run - .3, 0, .42 + (run - .3) * slope), .09, .1, 'Timber', rail)
        for i in range(5):
            x = .55 + i * .23
            b.box((x - .035, -.035, .26 + x * slope), (x + .035, .035, .98 + x * slope), 'Timber', rail, .008)
    elif state == 'D1':
        b.beam((.3, 0, 1.0 + .3 * slope), (1.18, 0, .92 + 1.18 * slope), .13, .13, 'Timber', rail)
        b.beam((.3, 0, .42 + .3 * slope), (run - .3, 0, .42 + (run - .3) * slope), .09, .1, 'Timber', rail)
        for i in (0, 1, 3):
            x = .55 + i * .23
            b.box((x - .035, -.035, .26 + x * slope), (x + .035, .035, .74 + x * slope), 'Timber', rail, .008)
    finish(b, .9, 8, .5)


def stall(state):
    b = Builder('SM_V_Stall_' + state)
    w, d, h = 3.2, 1.9, 2.5
    r = random.Random(7)
    corners = [(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)]
    for i, (x, y) in enumerate(corners):
        if state == 'D' and i == 1:
            b.beam((x, y, 0), (x + .35, y + .2, 1.5), .1, .1, 'Timber', OLD)
            continue
        b.box((x - .05, y - .05, 0), (x + .05, y + .05, h + (.45 if y > 0 else 0)), 'Timber', WOOD if state == 'R' else OLD, .012)
    tone = WOOD if state == 'R' else OLD
    b.beam((-w / 2, d / 2, h + .45), (w / 2, d / 2, h + .45), .08, .1, 'Timber', tone)
    if state == 'R':
        b.beam((-w / 2, -d / 2, h), (w / 2, -d / 2, h), .08, .1, 'Timber', tone)
        strips = 9
        for i in range(strips):
            x0, x1 = -w / 2 - .12 + i * (w + .24) / strips, -w / 2 - .12 + (i + 1) * (w + .24) / strips
            c = TEAL if i % 2 == 0 else CREAM
            sag = lambda t: -math.sin(t * math.pi) * .08
            rows = 5
            for j in range(rows):
                t0, t1 = j / rows, (j + 1) / rows
                y0, y1 = d / 2 + .1 - (d + .5) * t0, d / 2 + .1 - (d + .5) * t1
                z0, z1 = h + .5 - .62 * t0 + sag(t0), h + .5 - .62 * t1 + sag(t1)
                b.quad((x0, y1, z1), (x1, y1, z1), (x1, y0, z0), (x0, y0, z0), 'Cloth', c, [(i / strips, t0), ((i + 1) / strips, t0), ((i + 1) / strips, t1), (i / strips, t1)])
            for k in (0, 1):
                b.quad((x1, -d / 2 - .4, h - .12), (x0, -d / 2 - .4, h - .12), (x0, -d / 2 - .4, h - .36 - (k and 0)), (x1, -d / 2 - .4, h - .36), 'Cloth', c) if k == 0 else None
        b.box((-w / 2 + .05, -d / 2 + .08, .78), (w / 2 - .05, d / 2 - .4, .86), 'Timber', WOOD, .012)
        b.box((-w / 2 + .1, -d / 2 + .1, .1), (w / 2 - .1, -d / 2 + .15, .78), 'Timber', (0, .7, 0, 0))
        goods = ('Terracotta', 'Terracotta', 'Leaf')
        for i in range(6):
            x = -w / 2 + .4 + i * .48
            # Baskets of produce: warm spheres on counter, read at a glance from the street.
            bx = .2
            b.cylinder((x, -.15, .86), (x, -.15, 1.0), bx * .8, bx, 'Timber', (0, .75, 0, 0), 8)
            colour = r.choice(((.72, .42, .12, .1), (.62, .16, .1, .1), (.5, .55, .2, .1), (.78, .62, .2, .1)))
            b.lathe((x, -.15, 1.0), [(.17, 0), (.15, .07), (.08, .12), (.01, .135)], 'Cloth', colour, 7)
    else:
        for i in range(3):
            y = d / 2 + .1 - i * .55
            b.beam((-w / 2 - .1, y, h + .4 - i * .2), (w * .1 * (1 + i), y, h + .35 - i * .18), .07, .05, 'Timber', OLD)
        b.quad((-w / 2 - .1, d / 2, h + .42), (-.9, d / 2, h + .42), (-1.15, d / 2 - 1, h - .9), (-w / 2 - .05, d / 2 - .6, h - .75), 'Cloth', GREY, [(0, 0), (1, 0), (1, 1), (0, 1)])
        b.box((-w / 2 + .05, -.1, .74), (.3, d / 2 - .4, .8), 'Timber', OLD, .01)
    finish(b, 1.0, 8, .5)


def fountain(state):
    b = Builder('SM_V_Fountain_' + state)
    tone = STONE if state == 'R' else (0, .85, .22, 0)
    b.lathe((0, 0, 0), [(3.0, 0), (3.0, .16), (2.86, .22), (2.86, .32), (2.6, .36), (0.1, .36)], 'Masonry', tone, 28)
    b.lathe((0, 0, .2), [(2.4, .0), (2.4, .62), (2.5, .66), (2.5, .78), (2.34, .82), (2.3, .3), (.1, .3)], 'Masonry', tone, 28)
    b.lathe((0, 0, .5), [(.42, 0), (.36, .5), (.26, 1.2), (.36, 1.34), (1.16, 1.44), (1.2, 1.52), (.96, 1.58), (.3, 1.5)], 'Masonry', tone, 18)
    if state == 'R':
        b.lathe((0, 0, 2.05), [(.16, 0), (.12, .5), (.2, .58), (.5, .64), (.5, .7), (.14, .7), (.08, 1.0), (.14, 1.05), (.02, 1.22)], 'Masonry', tone, 14)
        water = (.2, .34, .36, .05)
        loop = [(2.36 * math.cos(i * math.tau / 28), 2.36 * math.sin(i * math.tau / 28), .78) for i in range(28)]
        b.face([b.vertex(p, (0, 1, 0, 0)) for p in loop], 'Glass', [(.5 + .5 * math.cos(i * math.tau / 28), .5 + .5 * math.sin(i * math.tau / 28)) for i in range(28)])
    else:
        b.lathe((0, 0, 2.05), [(.16, 0), (.12, .32), (.18, .4)], 'Masonry', tone, 14)
        r = random.Random(3)
        for i in range(10):
            a = r.uniform(0, math.tau)
            d = r.uniform(.5, 2.2)
            s = r.uniform(.1, .22)
            b.box((math.cos(a) * d - s, math.sin(a) * d - s, .52), (math.cos(a) * d + s, math.sin(a) * d + s, .52 + s), 'Masonry', tone, .02)
        for i in range(5):
            a = i * 1.3
            clump(b, (math.cos(a) * 1.4, math.sin(a) * 1.4, .9), .34, 'grass', 2, r)
    finish(b, 1.4, 10, .6)


def planter(name, kind):
    b = Builder('SM_V_' + name)
    r = random.Random(len(name))
    if kind == 'pot':
        b.lathe((0, 0, 0), [(.19, 0), (.32, .3), (.38, .56), (.36, .62), (.4, .68), (.3, .68), (.3, .62)], 'Terracotta', (0, .95, 0, 0), 12)
        for i in range(3):
            clump(b, (0, 0, 1.0), .44, 'flowers', 2, r)
    elif kind == 'box':
        b.box((-.55, -.2, 0), (.55, .2, .3), 'Timber', WOOD, .012)
        for x in (-.32, .32):
            clump(b, (x, 0, .56), .34, 'flowers', 2, r)
    elif kind == 'broken':
        b.lathe((0, 0, 0), [(.19, 0), (.32, .3), (.36, .46)], 'Terracotta', OLD, 12)
        clump(b, (0, 0, .62), .3, 'grass', 2, r)
    finish(b, .5, 6, .4)


def crates():
    b = Builder('SM_V_Crates')
    for x, y, z, s in ((0, 0, 0, .34), (.72, .08, 0, .3), (.28, .04, .68, .28), (-.1, .68, 0, .3)):
        b.box((x - s, y - s, z), (x + s, y + s, z + s * 2), 'Timber', WOOD, .012)
        for i in range(3):
            zz = z + s * .4 + i * s * .6
            b.box((x - s - .012, y - s - .012, zz), (x + s + .012, y + s + .012, zz + .05), 'Timber', (0, .7, 0, 0))
    finish(b, .7, 6, .5)


def barrels():
    b = Builder('SM_V_Barrels')
    for x, y in ((0, 0), (.72, .1), (.3, .66)):
        b.lathe((x, y, 0), [(.26, 0), (.33, .24), (.36, .46), (.33, .68), (.26, .92), (.2, .92)], 'Timber', WOOD, 14)
        for z in (.2, .72):
            b.lathe((x, y, z), [(.335, 0), (.345, .03), (.345, .07), (.335, .1)], 'Iron', (0, .9, 0, 0), 14)
    finish(b, .6, 6, .5)


def amphorae():
    b = Builder('SM_V_Amphorae')
    for x, y, s in ((0, 0, 1), (.62, .1, .84), (.26, .56, .92), (-.5, .3, .76)):
        b.lathe((x, y, 0), [(.08 * s, 0), (.2 * s, .12), (.3 * s, .42), (.26 * s, .72), (.1 * s, .9), (.08 * s, 1.0), (.12 * s, 1.04), (.09 * s, 1.04)], 'Terracotta', (0, .96, 0, 0), 12)
    finish(b, .6, 6, .5)


def bench():
    b = Builder('SM_V_Bench')
    for x in (-.8, .8):
        b.box((x - .22, -.22, 0), (x + .22, .22, .42), 'Masonry', STONE, .025)
    b.box((-1.1, -.24, .42), (1.1, .24, .54), 'Masonry', STONE, .03)
    finish(b, .6, 6, .5)


def lantern(kind):
    b = Builder('SM_V_Lantern_' + kind)
    if kind == 'Wall':
        b.beam((0, 0, 0), (0, -.46, 0), .03, .03, 'Iron', STONE)
        b.beam((0, -.12, -.22), (0, -.42, -.02), .02, .02, 'Iron', STONE)
        top = -.04
        y = -.46
    else:
        b.cylinder((0, 0, 0), (0, 0, .35), .13, .1, 'Masonry', STONE, 8)
        b.cylinder((0, 0, .35), (0, 0, 3.1), .05, .035, 'Iron', STONE, 8)
        b.beam((0, 0, 3.05), (.45, 0, 3.05), .03, .03, 'Iron', STONE)
        top, y = 3.02, 0
        b.quad((.45, y - .01, top), (.46, y + .01, top), (.46, y + .01, top - .05), (.45, y - .01, top - .05), 'Iron', STONE)
    x = 0 if kind == 'Wall' else .45
    b.lathe((x, y, top - .52), [(.1, 0), (.13, .03), (.13, .1), (.1, .12)], 'Iron', STONE, 6)
    b.lathe((x, y, top - .4), [(.09, 0), (.13, .22), (.13, .3)], 'Glass', (1, 1, 0, .0), 6)
    b.lathe((x, y, top - .1), [(.15, 0), (.04, .1), (.015, .12)], 'Iron', STONE, 6)
    b.cylinder((x, y, top - .38), (x, y, top - .16), .05, .05, 'Flat', (1, 1, 0, 0), 6)
    finish(b, .3, 4, .2)


def awning(state):
    """Wall-hung shop awning, 2.5 m wide. Origin at the wall above the bay, centred on X."""
    b = Builder('SM_V_Awning_' + state)
    w, depth, drop = 2.5, 1.5, .55
    if state == 'R':
        strips = 7
        for i in range(strips):
            x0, x1 = -w / 2 + i * w / strips, -w / 2 + (i + 1) * w / strips
            c = TEAL if i % 2 == 0 else CREAM
            for j in range(4):
                t0, t1 = j / 4, (j + 1) / 4
                y0, y1, z0, z1 = -t0 * depth, -t1 * depth, -t0 * drop - .08 * math.sin(t0 * math.pi), -t1 * drop - .08 * math.sin(t1 * math.pi)
                b.quad((x0, y1, z1), (x1, y1, z1), (x1, y0, z0), (x0, y0, z0), 'Cloth', c, [(0, 0), (1, 0), (1, 1), (0, 1)])
            b.quad((x0, -depth, -drop), (x1, -depth, -drop), (x1, -depth, -drop - .24), (x0, -depth, -drop - .24), 'Cloth', c)
        for x in (-w / 2, w / 2):
            b.beam((x, 0, -.02), (x, -depth, -drop), .05, .05, 'Timber', WOOD)
            b.beam((x, 0, -1.0), (x, -depth * .72, -drop * .78), .04, .04, 'Iron', STONE)
        b.beam((-w / 2, -depth, -drop), (w / 2, -depth, -drop), .05, .05, 'Timber', WOOD)
    else:
        for x in (-w / 2, w / 2):
            b.beam((x, 0, -.02), (x, -depth * (.6 if x < 0 else .9), -drop * .9), .05, .05, 'Timber', OLD)
        b.quad((-w / 2, 0, -.02), (.2, 0, -.02), (-.1, -1.0, -.6), (-w / 2, -.8, -.55), 'Cloth', GREY, [(0, 0), (1, 0), (1, 1), (0, 1)])
    finish(b, .5, 4, .2)


def banner():
    """Civic banner on a post: 3.8 m post, 1 x 2 m cloth."""
    b = Builder('SM_V_Banner')
    b.cylinder((0, 0, 0), (0, 0, 4.2), .06, .045, 'Timber', WOOD, 8)
    b.beam((-.12, 0, 3.95), (.95, 0, 3.95), .05, .05, 'Timber', WOOD)
    rows, cols = 6, 3
    for r in range(rows):
        for c in range(cols):
            def p(u, v):
                return (.03 + u * .85, .03 * math.sin(u * 7 + v * 3), 3.9 - v * 2.0)
            u0, u1, v0, v1 = c / cols, (c + 1) / cols, r / rows, (r + 1) / rows
            w0 = (1, 1, 1, .15 + v0 * .85)
            w1 = (1, 1, 1, .15 + v1 * .85)
            ids = [b.vertex(p(u0, v1), w1), b.vertex(p(u1, v1), w1), b.vertex(p(u1, v0), w0), b.vertex(p(u0, v0), w0)]
            b.face(ids, 'Banner', [(u0, 1 - v1), (u1, 1 - v1), (u1, 1 - v0), (u0, 1 - v0)])
    finish(b, .3, 4, .2)


def clinic_flag():
    """Hanging cloth with a plain red cross, as on the lookbook clinic."""
    b = Builder('SM_V_ClinicFlag')
    b.beam((-.8, -.06, 0), (.8, -.06, 0), .05, .05, 'Iron', STONE)
    w, h = 1.4, 2.3
    pale = (.86, .8, .68, .25)
    red = (.46, .08, .06, .25)
    grid = 7
    for r in range(grid + 3):
        for c in range(grid):
            u0, u1, v0, v1 = c / grid, (c + 1) / grid, r / (grid + 3), (r + 1) / (grid + 3)
            in_cross = (2 <= c <= 4 and 2 <= r <= 7 and (c == 3 or 4 <= r <= 5))
            colour = red if in_cross else pale
            sag = lambda v: -.08 * math.sin(v * math.pi)
            b.quad((-w / 2 + u0 * w, -.07 + sag(v1), -v1 * h), (-w / 2 + u1 * w, -.07 + sag(v1), -v1 * h),
                   (-w / 2 + u1 * w, -.07 + sag(v0), -v0 * h), (-w / 2 + u0 * w, -.07 + sag(v0), -v0 * h), 'Cloth', colour, [(0, 0), (1, 0), (1, 1), (0, 1)])
    finish(b, .3, 4, .2)


def bunting():
    """Flag line, 10 m at scale 1, hung across a street with a shallow catenary."""
    b = Builder('SM_V_Bunting')
    length = 10.0
    count = 15
    colours = (TEAL, CREAM, (.5, .24, .14, .2), (.74, .55, .24, .2))
    cat = lambda t: -1.1 * (1 - (2 * t - 1) ** 2)
    prev = None
    for i in range(30):
        t0, t1 = i / 30, (i + 1) / 30
        b.beam((t0 * length, 0, cat(t0)), (t1 * length, 0, cat(t1)), .012, .012, 'Iron', STONE)
    for i in range(count):
        t = (i + .5) / count
        x = t * length
        z = cat(t)
        c = colours[i % 4]
        ids = [b.vertex((x - .18, 0, z), (*c[:3], .4)), b.vertex((x, 0, z - .42), (*c[:3], .9)), b.vertex((x + .18, 0, z), (*c[:3], .4))]
        b.face(ids, 'Cloth', [(0, 1), (.5, 0), (1, 1)])
    finish(b, .2, 2, 0)


def laundry():
    b = Builder('SM_V_Laundry')
    length = 6.0
    cat = lambda t: -.5 * (1 - (2 * t - 1) ** 2)
    for i in range(16):
        t0, t1 = i / 16, (i + 1) / 16
        b.beam((t0 * length, 0, cat(t0)), (t1 * length, 0, cat(t1)), .012, .012, 'Iron', STONE)
    colours = ((.75, .72, .62, .3), (.34, .46, .5, .3), (.62, .56, .44, .3), (.7, .68, .6, .3), (.46, .3, .22, .3))
    x = .5
    r = random.Random(5)
    for i in range(6):
        w, h = r.uniform(.5, .95), r.uniform(.7, 1.15)
        t = x / length
        z = cat(t)
        c = colours[i % 5]
        low = (c[0], c[1], c[2], .9)
        b.quad((x, 0, z - h), (x + w, 0, cat((x + w) / length) - h * r.uniform(.92, 1)), (x + w, 0, cat((x + w) / length)), (x, 0, z), 'Cloth', c, [(0, 0), (1, 0), (1, 1), (0, 1)])
        x += w + r.uniform(.12, .3)
    finish(b, .2, 2, 0)


def archway(state):
    """Arch carrying a lane under an upper room link; 3 m clear, fits the 2.5 m bay plus piers."""
    b = Builder('SM_V_Archway_' + state)
    w, h = 3.4, 4.2
    opening = [(.45, -.2), (w - .45, -.2)] + arch_points(w / 2, 2.4, w / 2 - .45, 1.0, 12)
    paint = lambda x, z: (.8 if state == 'R' else .25, 1, 0 if state == 'R' else .2, 0)
    if state == 'R':
        loop = [(0, -.6), (w, -.6), (w, h), (0, h)]
    else:
        loop = [(0, -.6), (w, -.6)] + jagged((w, h - .2), (0, h - .7), .4, 11)
    b.wall(loop, [opening], .6, paint=paint, spacing=.4)
    stones = 13
    for i in range(stones):
        a0, a1 = math.pi * i / stones + .012, math.pi * (i + 1) / stones - .012
        hw = w / 2 - .45
        out = .3
        stone = [(w / 2 + hw * math.cos(a0), 2.4 + math.sin(a0)), (w / 2 + (hw + out) * math.cos(a0), 2.4 + (1 + out) * math.sin(a0)),
                 (w / 2 + (hw + out) * math.cos(a1), 2.4 + (1 + out) * math.sin(a1)), (w / 2 + hw * math.cos(a1), 2.4 + math.sin(a1))]
        b.wall(stone, (), .68, paint=lambda x, z: STONE, reveal=lambda x, z: STONE, spacing=9, y=-.04)
    finish(b, 1.2, 8, .6)


def boat(kind):
    """Fishing boats. Hull lofted from sections; origin amidships at the waterline."""
    b = Builder('SM_V_Boat_' + kind)
    length, beam, depth = (7.0, 2.2, 1.1) if kind != 'Row' else (3.6, 1.3, .55)
    n, sections = 8, 13

    def section(t):
        """t 0 bow..1 stern; returns half-beam and sheer height."""
        taper = math.sin(min(1, t * 1.02) ** .62 * math.pi) ** .55
        hb = beam / 2 * max(.02, taper) * (1 if t < .9 else 1 - (t - .9) * 3)
        sheer = depth * (.74 + .5 * (2 * t - 1) ** 2)
        return hb, sheer
    grid = []
    for i in range(sections):
        t = i / (sections - 1)
        hb, sheer = section(t)
        row = []
        for j in range(n):
            a = -math.pi / 2 + j / (n - 1) * math.pi
            row.append((math.sin(a) * hb, (t - .5) * length, -.18 * depth + (1 - math.cos(a)) * 0 + (sheer + .18 * depth) * (abs(math.sin(a)) ** 2.4)))
        grid.append(row)
    ruined = kind == 'Wreck'
    for i in range(sections - 1):
        for j in range(n - 1):
            if ruined and (3 < i < 8 and 3 < j < 7):
                continue
            tone = (0, .92, 0, 0)
            slot = 'Paint' if abs(j - (n - 1) / 2) > 2.0 and not ruined else 'Timber'
            ids = [b.vertex(grid[i][j], tone), b.vertex(grid[i + 1][j], tone), b.vertex(grid[i + 1][j + 1], tone), b.vertex(grid[i][j + 1], tone)]
            b.face(ids, slot, [(i / 3, j / 4), ((i + 1) / 3, j / 4), ((i + 1) / 3, (j + 1) / 4), (i / 3, (j + 1) / 4)])
    # Deck and thwarts.
    for i in range(2, sections - 2):
        hb, sheer = section(i / (sections - 1))
        if ruined and i % 2:
            continue
        y = (i / (sections - 1) - .5) * length
        b.box((-hb * .92, y - .1, sheer * .72), (hb * .92, y + .1, sheer * .76), 'Timber', WOOD)
    if kind == 'Sail':
        b.cylinder((0, -.6, .4), (0, -.6, 8.2), .085, .05, 'Timber', WOOD, 8)
        b.beam((0, -.6, 1.7), (0, 2.9, 1.5), .06, .06, 'Timber', WOOD)
        # Lateen-style sail with a soft belly.
        rows, cols = 7, 5
        for r in range(rows):
            for c in range(cols):
                def p(u, v):
                    top = 7.6 - v * 5.6
                    x = math.sin(v * math.pi) * .55 * math.sin(u * math.pi) + .08
                    return (x, -.55 + u * (3.2 - (1 - v) * 2.5), 1.9 + (top - 1.9) * (1 - u * .35))
                u0, u1, v0, v1 = c / cols, (c + 1) / cols, r / rows, (r + 1) / rows
                colour = (.8, .74, .62, .3 + .3 * u0) if c % 2 == 0 else (.74, .68, .56, .3 + .3 * u0)
                b.quad(p(u0, v1), p(u1, v1), p(u1, v0), p(u0, v0), 'Cloth', colour, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
        for end in ((0, -.6, 8.2), ):
            b.beam(end, (0, -3.2, 1.2), .012, .012, 'Iron', STONE)
            b.beam(end, (0, 3.2, 1.3), .012, .012, 'Iron', STONE)
    elif ruined:
        b.beam((0, -.6, .3), (.9, .3, 5.0), .09, .09, 'Timber', OLD)
    finish(b, 1.2, 8, .5)


def pier(state):
    """Three metre timber pier bay, 3 m wide, top at Z=0. Piles drop into the sea."""
    b = Builder('SM_V_Pier_' + state)
    r = random.Random(13 if state == 'R' else 17)
    tone = WOOD if state == 'R' else OLD
    planks = 12
    for i in range(planks):
        x = i * .25
        if state == 'D' and r.random() < .34:
            continue
        lean = r.uniform(-.008, .008)
        b.box((x + .006, -1.5 - r.uniform(0, .06), -.06 + lean), (x + .244, 1.5 + r.uniform(0, .06), 0 + lean), 'Timber', tone, .006)
    for y in (-1.3, 0, 1.3):
        b.beam((0, y, -.16), (3, y, -.16), .14, .18, 'Timber', tone)
    for y in (-1.4, 1.4):
        if state == 'D' and y > 0:
            b.cylinder((.1, y, -3), (.1, y, -.9), .15, .14, 'Timber', OLD, 8)
            continue
        b.cylinder((.1, y, -3), (.1, y, .62), .15, .14, 'Timber', tone, 8)
    if state == 'R':
        for y in (-1.4, 1.4):
            b.beam((.1, y, .55), (3.1, y, .55), .08, .09, 'Timber', tone)
    finish(b, .8, 6, .4)


def crane(state):
    b = Builder('SM_V_Crane_' + state)
    tone = WOOD if state == 'R' else OLD
    b.box((-1, -1, 0), (1, 1, .3), 'Timber', tone, .02)
    for x, y in ((-.7, -.7), (.7, -.7), (.7, .7), (-.7, .7)):
        b.beam((x, y, .3), (0, 0, 5.2), .16, .16, 'Timber', tone)
    if state == 'R':
        b.beam((0, 0, 4.6), (4.6, 0, 7.4), .2, .2, 'Timber', tone)
        b.beam((0, 0, 3.4), (2.6, 0, 6.1), .12, .12, 'Timber', tone)
        b.beam((4.6, 0, 7.4), (4.6, 0, 2.2), .02, .02, 'Iron', STONE)
        b.box((4.3, -.3, 1.4), (4.9, .3, 2.1), 'Timber', tone, .02)
    else:
        b.beam((0, 0, 4.6), (2.1, 0, 5.9), .2, .2, 'Timber', tone)
    finish(b, 1, 6, .4)


def shelter(state):
    """The Waiting Shelter: timber frame, tiled roof, bench, noticeboard, lamp hook. 7 x 4 m."""
    b = Builder('SM_V_Shelter_' + state)
    w, d, h = 7.0, 4.0, 3.0
    tone = WOOD if state == 'R' else OLD
    for x in (-w / 2, -w / 6, w / 6, w / 2):
        for y in (-d / 2, d / 2):
            b.box((x - .11, y - .11, 0), (x + .11, y + .11, h), 'Timber', tone, .015)
            b.box((x - .2, y - .2, 0), (x + .2, y + .2, .2), 'Masonry', STONE, .02)
            b.beam((x, y, h - .85), (x + (.62 if x < 0 else -.62), y, h - .08), .08, .08, 'Timber', tone)
    for y in (-d / 2, d / 2):
        b.beam((-w / 2 - .5, y, h), (w / 2 + .5, y, h), .16, .2, 'Timber', tone)
    ridge = h + 1.35
    keep_ok = lambda c, r: state == 'R' or (field(c, r, .4, 51) < .54 and c < 13)
    from build_verdant_landmarks_tile import tile_plane
    tile_plane(b, (-w / 2 - .5, -d / 2 - .55, h + .1), (w / 2 + .5, -d / 2 - .55, h + .1), (w / 2 + .5, 0, ridge), (-w / 2 - .5, 0, ridge), 26, 6, keep_ok, .08)
    tile_plane(b, (w / 2 + .5, d / 2 + .55, h + .1), (-w / 2 - .5, d / 2 + .55, h + .1), (-w / 2 - .5, 0, ridge), (w / 2 + .5, 0, ridge), 26, 6, keep_ok, .08)
    for i in range(8):
        x = -w / 2 + i * w / 7
        if state == 'D' and field(i, 2, .9, 52) > .58:
            continue
        b.beam((x, -d / 2 - .4, h + .08), (x, 0, ridge - .05), .08, .12, 'Timber', tone)
        b.beam((x, d / 2 + .4, h + .08), (x, 0, ridge - .05), .08, .12, 'Timber', tone)
    b.beam((-w / 2 - .5, 0, ridge), (w / 2 + .5, 0, ridge), .15, .2, 'Timber', tone)
    # Bench along the sea side, and the noticeboard the clerk's book would sit under.
    b.box((-2.6, 1.15, .42), (2.6, 1.6, .5), 'Timber', tone, .012)
    for x in (-2.4, 0, 2.4):
        b.box((x - .06, 1.2, 0), (x + .06, 1.55, .42), 'Timber', tone)
    b.box((-2.6, 1.56, .5), (2.6, 1.62, .96), 'Timber', tone, .01)
    b.box((-1.5, -2.06, .8), (.9, -1.98, 2.2), 'Timber', tone, .015)
    if state == 'R':
        for i in range(4):
            x = -1.3 + i * .55
            b.quad((x, -2.08, 1.2), (x + .42, -2.08, 1.2), (x + .42, -2.08, 1.9), (x, -2.08, 1.9), 'Cloth', (.8, .75, .62, .05), [(0, 0), (1, 0), (1, 1), (0, 1)])
        for x, y, s in ((2.6, -1.1, .34), (3.0, -.3, .28)):
            b.box((x - s, y - s * 1.3, 0), (x + s, y + s * 1.3, s * 1.2), 'Timber', (0, .65, 0, 0), .03)
    finish(b, 1.4, 8, .6)


def scaffold():
    """Timber scaffold, the sign that somebody is still mending the city. 6 x 1.4 x 7 m."""
    b = Builder('SM_V_Scaffold')
    for x in (0, 3, 6):
        for y in (0, 1.4):
            b.cylinder((x, y, 0), (x, y, 7.4), .06, .055, 'Timber', OLD, 6)
    for z in (2.2, 4.4, 6.6):
        for y in (0, 1.4):
            b.beam((-.2, y, z), (6.2, y, z), .08, .08, 'Timber', OLD)
        for i in range(10):
            x = .1 + i * .6
            b.box((x, 0, z + .04), (x + .55, 1.4, z + .08), 'Timber', OLD)
    b.beam((0, 0, 0), (3, 0, 4.4), .06, .06, 'Timber', OLD)
    b.beam((3, 0, 0), (6, 0, 4.4), .06, .06, 'Timber', OLD)
    finish(b, .6, 4, .3)


def sandbags():
    b = Builder('SM_V_Sandbags')
    r = random.Random(23)
    for layer in range(3):
        for i in range(6 - layer):
            x = -1.2 + i * .52 + layer * .26
            b.lathe((x, 0, layer * .22), [(.1, 0), (.25, .05), (.26, .12), (.2, .2), (.02, .21)], 'Cloth', (.4, .36, .27, 0.01), 7)
    finish(b, .3, 2, 0)


def tarp():
    b = Builder('SM_V_Tarp')
    cols, rows = 5, 5
    for r in range(rows):
        for c in range(cols):
            def p(u, v):
                return (u * 3 - 1.5, v * 3 - 1.5, .12 * math.sin(u * 6) * math.sin(v * 5))
            u0, u1, v0, v1 = c / cols, (c + 1) / cols, r / rows, (r + 1) / rows
            tone = (.21, .27, .28, .1)
            b.quad(p(u0, v0), p(u1, v0), p(u1, v1), p(u0, v1), 'Cloth', tone, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
    finish(b, .2, 2, 0)


def vegetation():
    r = random.Random(61)
    b = Builder('SM_V_GrassTuft')
    for i in range(4):
        card(b, (r.uniform(-.3, .3), r.uniform(-.3, .3), 0), r.uniform(.5, .8), r.uniform(.4, .75), r.uniform(0, 3.14), 'grass', r.uniform(-.2, .2))
    finish(b, .2, 2, 0)
    b = Builder('SM_V_WeedPatch')
    for i in range(9):
        a, d = r.uniform(0, math.tau), r.uniform(0, 1.2)
        card(b, (math.cos(a) * d, math.sin(a) * d, 0), r.uniform(.6, 1.0), r.uniform(.5, 1.0), r.uniform(0, 3.14), 'grass', r.uniform(-.2, .2), shade=r.uniform(.8, 1.05))
    finish(b, .2, 2, 0)
    b = Builder('SM_V_Bush')
    for i in range(7):
        a, d = r.uniform(0, math.tau), r.uniform(0, .7)
        clump(b, (math.cos(a) * d, math.sin(a) * d, r.uniform(.5, 1.0)), r.uniform(.5, .85), 'olive', 3, r)
    finish(b, .2, 2, 0)
    # Climbers hang from Z=0 at the wall (Y=0), growing outward along -Y and down.
    b = Builder('SM_V_IvyCurtain')
    for i in range(16):
        x = r.uniform(-1.3, 1.3)
        z = -r.uniform(0, 3.4)
        h = r.uniform(.8, 1.7)
        cell = 'vine' if i % 2 else 'ivy'
        ids = [b.vertex((x - h / 2, -.06, z - h), (1, 1, 1, .15)), b.vertex((x + h / 2, -.06, z - h), (1, 1, 1, .15)),
               b.vertex((x + h / 2, -.06 - r.uniform(.04, .2), z), (1, 1, 1, .4)), b.vertex((x - h / 2, -.06 - r.uniform(.04, .2), z), (1, 1, 1, .4))]
        b.face(ids, 'Leaf', cell_uv(cell))
    finish(b, .2, 2, 0)
    b = Builder('SM_V_Bougainvillea')
    for i in range(14):
        x = r.uniform(-1.1, 1.1)
        z = -r.uniform(0, 2.2) * (1 - abs(x) / 2)
        s = r.uniform(.6, 1.1)
        ids = [b.vertex((x - s / 2, -.08, z - s), (1, 1, 1, .2)), b.vertex((x + s / 2, -.1, z - s), (1, 1, 1, .2)),
               b.vertex((x + s / 2, -.25 - r.uniform(0, .3), z), (1, 1, 1, .5)), b.vertex((x - s / 2, -.25 - r.uniform(0, .3), z), (1, 1, 1, .5))]
        b.face(ids, 'Leaf', cell_uv('bougainvillea'))
    finish(b, .2, 2, 0)


def tree(name, seed, kind):
    r = random.Random(seed)
    b = Builder('SM_V_' + name)
    if kind == 'olive':
        for i in range(3):
            a = i * 2.1
            b.beam((.1 * math.cos(a), .1 * math.sin(a), 0), (.26 * math.cos(a), .26 * math.sin(a), 1.6), .24, .26, 'Timber', (0, .85, 0, 0), chamfer=.06)
        tips = []
        for i in range(7):
            a = r.uniform(0, math.tau)
            d = r.uniform(.9, 2.2)
            tip = (math.cos(a) * d, math.sin(a) * d, r.uniform(2.6, 4.2))
            b.beam((.2 * math.cos(a), .2 * math.sin(a), 1.5), tip, .11, .12, 'Timber', (0, .85, 0, 0), chamfer=.03)
            tips.append(tip)
        for tip in tips:
            for i in range(4):
                c = (tip[0] + r.uniform(-.9, .9), tip[1] + r.uniform(-.9, .9), tip[2] + r.uniform(-.5, .7))
                clump(b, c, r.uniform(.75, 1.15), 'olive', 3, r, shade=r.uniform(.84, 1.08))
    elif kind == 'cypress':
        height = r.uniform(8, 9.5)
        b.cylinder((0, 0, 0), (0, 0, height * .9), .16, .05, 'Timber', (0, .8, 0, 0), 6)
        layers = 10
        for i in range(layers):
            t = (i + .3) / layers
            radius = .85 * math.sin(min(1, t * 1.25 + .06) * math.pi) ** .62 * (1 - t * .28)
            z = .5 + t * (height - .8)
            for k in range(3):
                card(b, (0, 0, z - .9), radius * 2.1, 2.4, k * 1.05 + i * .5, 'cypress', r.uniform(-.1, .1), wind=.2 + t * .5, shade=r.uniform(.82, 1.05))
    elif kind == 'pine':
        b.cylinder((0, 0, 0), (0, 0, 6.0), .26, .14, 'Timber', (0, .85, 0, 0), 8)
        for i in range(9):
            a = r.uniform(0, math.tau)
            d = r.uniform(1.4, 3.2)
            b.beam((0, 0, 4.8 + r.uniform(0, 1.2)), (math.cos(a) * d, math.sin(a) * d, 6.8 + r.uniform(0, 1.0)), .12, .14, 'Timber', (0, .85, 0, 0), chamfer=.03)
            for k in range(5):
                c = (math.cos(a) * d + r.uniform(-1.1, 1.1), math.sin(a) * d + r.uniform(-1.1, 1.1), 7.2 + r.uniform(-.2, 1.1))
                clump(b, c, r.uniform(1.0, 1.5), 'pine', 3, r, height=r.uniform(1.0, 1.5))
    elif kind == 'dead':
        b.beam((0, 0, 0), (.3, .1, 2.3), .22, .24, 'Timber', OLD, chamfer=.05)
        for i in range(5):
            a = i * 1.6
            b.beam((.3, .1, 1.6 + i * .2), (.3 + math.cos(a) * 1.4, .1 + math.sin(a) * 1.4, 3 + r.uniform(0, .8)), .08, .08, 'Timber', OLD)
    finish(b, .5, 4, .2)


for name, seed, size, blocks in (('A', 1, 1.5, 40), ('B', 2, 2.1, 60), ('C', 3, 1.1, 26), ('D', 4, 3.0, 120)):
    rubble(name, seed, size, blocks)
for name, slope in (('Slope', .1), ('Flat', 0)):
    for s in ('R', 'D1', 'D2'):
        parapet(name, slope, s)
for s in ('R', 'D'):
    stall(s)
    fountain(s)
    awning(s)
    archway(s)
    pier(s)
    crane(s)
    shelter(s)
planter('Pot', 'pot')
planter('FlowerBox', 'box')
planter('PotBroken', 'broken')
crates()
barrels()
amphorae()
bench()
lantern('Wall')
lantern('Post')
banner()
clinic_flag()
bunting()
laundry()
for kind in ('Sail', 'Row', 'Wreck'):
    boat(kind)
scaffold()
sandbags()
tarp()
vegetation()
tree('Olive', 71, 'olive')
tree('OliveB', 72, 'olive')
tree('Cypress', 73, 'cypress')
tree('CypressB', 74, 'cypress')
tree('Pine', 75, 'pine')
tree('DeadTree', 76, 'dead')

path = OUT / 'kit_manifest.json'
existing = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
existing.update(manifest)
path.write_text(json.dumps(existing, indent=2), encoding='utf-8')
print('PROPS', len(manifest), 'triangles', sum(m['triangles'] for m in manifest.values()), flush=True)

if 'preview' in sys.argv:
    import kit_preview
    kit_preview.render(built, OUT / 'previews' / 'kit_props.png', columns=10, spacing=7.0, samples=20)
