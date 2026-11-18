"""Verdant landmarks at their established positions: campanile (-3, 41), cathedral front at
Y=55 with twin towers at X 5.75 / 16.25, crossing dome at Y=72, lighthouse island (58, 31).
Each landmark keeps its silhouette in both timelines; the present damages a secondary part.
Meshes are authored in world metres with the pivot at the origin.
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
from build_verdant_landmarks_tile import tile_plane

OUT = HERE.parent / 'output' / 'verdant'
MESHES = OUT / 'meshes'
bpy.ops.wm.read_factory_settings(use_empty=True)
collection = bpy.data.collections.new('Landmarks')
bpy.context.scene.collection.children.link(collection)
manifest = {}
built = []
STONE = (0, 1, 0, 0)
LIME = (.0, .95, 0, 0)


def finish(b, reach=4.0, rays=14, strength=.8):
    b.bake_occlusion(rays=rays, reach=reach, strength=strength)
    obj = b.build(collection)
    vgeo.export_fbx(obj, MESHES / (obj.name + '.fbx'))
    lo = [min(v[i] for v in b.verts) for i in range(3)]
    hi = [max(v[i] for v in b.verts) for i in range(3)]
    manifest[obj.name] = {'triangles': sum(len(f[0]) - 2 for f in b.faces), 'vertices': len(b.verts), 'bounds_m': [lo, hi],
                          'slots': sorted({vgeo.SLOTS[f[1]] for f in b.faces})}
    built.append(obj)


def smooth(a, c, x):
    t = max(0.0, min(1.0, (x - a) / (c - a)))
    return t * t * (3 - 2 * t)


def stone_paint(state='R', seed=1):
    """Cathedral masonry: bare limestone with old render surviving in sheltered patches."""
    def paint(x, z):
        n = field(x + seed, z, .16, 11)
        cover = smooth(.5, .7, n) * (.55 if state == 'R' else .3)
        soot = 0.0 if state == 'R' else smooth(.45, .85, field(x * .6, z * .6 + seed, .14, 13)) * .7
        return (cover, 1, soot, 0)
    return paint


def core(x, z):
    return (0, .65, 0, 0)


def slab(b, a, c, z0, z1, holes=(), t=.6, paint=None, reveal=None, spacing=.9, outline=None):
    """Wall from point a to c with inside on the left. holes are in (u, z) along that run."""
    ax, ay = a
    length = math.hypot(c[0] - ax, c[1] - ay)
    ux, uy = (c[0] - ax) / length, (c[1] - ay) / length
    place = lambda p: (ax + ux * p[0] - uy * p[1], ay + uy * p[0] + ux * p[1], p[2])
    loop = outline(length) if outline else [(0, z0), (length, z0), (length, z1), (0, z1)]
    b.wall(loop, holes, t, paint=paint or stone_paint(), reveal=reveal or core, spacing=spacing, axis_map=place)


def arched(u, z, w, spring, rise=None, segments=10):
    rise = w / 2 if rise is None else rise
    return [(u - w / 2, z), (u + w / 2, z)] + arch_points(u, spring, w / 2, rise, segments)


def dome(b, centre, radius, height, rings=10, sides=28):
    """Ribbed patinated dome, the blue-green crown of the skyline."""
    profile = [(radius * math.cos(i / rings * math.pi / 2), height * math.sin(i / rings * math.pi / 2)) for i in range(rings + 1)]
    profile[-1] = (.02, height)
    b.lathe(centre, profile, 'Roof', (0, .96, 0, 0), sides)
    cx, cy, cz = centre
    for i in range(8):
        a = i * math.tau / 8
        for j in range(5):
            t0, t1 = j / 5 * math.pi / 2, (j + 1) / 5 * math.pi / 2
            p = lambda t: (cx + (radius + .02) * math.cos(t) * math.cos(a), cy + (radius + .02) * math.cos(t) * math.sin(a), cz + (height + .02) * math.sin(t))
            b.beam(p(t0), p(t1), .09, .06, 'Iron', (0, .9, 0, 0), chamfer=.01)


def cross(b, x, y, z, s=1.0):
    b.beam((x, y, z), (x, y, z + 1.2 * s), .06 * s, .06 * s, 'Iron', STONE)
    b.beam((x - .32 * s, y, z + .82 * s), (x + .32 * s, y, z + .82 * s), .05 * s, .05 * s, 'Iron', STONE)


def belfry(b, cx, cy, z, w, h, cell_width, t=.42, state='R'):
    """Four open arches around a hanging bell."""
    half = w / 2
    corners = [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)]
    for i in range(4):
        a, c = corners[i], corners[(i + 1) % 4]
        opening = arched(w / 2, z + .35, cell_width, z + h * .6, cell_width / 2)
        slab(b, a, c, z, z + h, [opening], t, paint=stone_paint(state, i), spacing=.8)
    b.lathe((cx, cy, z + h * .32), [(.2 * w / 4, h * .3), (.28 * w / 4, h * .24), (.36 * w / 4, h * .1), (.6 * w / 4, -.04), (.63 * w / 4, -.1)], 'Iron', (0, .9, 0, 0), 14)
    b.beam((cx - w * .36, cy, z + h * .66), (cx + w * .36, cy, z + h * .66), .16, .18, 'Timber', (0, .8, 0, 0))


def tier(b, cx, cy, z, w, h=.26, over=.14):
    half = w / 2 + over
    b.box((cx - half, cy - half, z), (cx + half, cy + half, z + h), 'Masonry', STONE, .03)


def campanile():
    b = Builder('SM_V_Campanile')
    cx, cy, z = -3.0, 41.0, 17.0
    half = 2.5
    corners = [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)]
    for i in range(4):
        a, c = corners[i], corners[(i + 1) % 4]
        holes = [arched(2.5, z + 7.2, .62, z + 9.4, .31), arched(2.5, z + 2.0, .5, z + 3.4, .25)]
        slab(b, a, c, z - 1, z + 12.5, holes, .5, paint=stone_paint('R', i))
    for h in (0, 5.2, 10.2):
        tier(b, cx, cy, z + h, 5)
    for xx in (cx - 2.5, cx + 2.5):
        for yy in (cy - 2.5, cy + 2.5):
            b.box((xx - .22, yy - .22, z - 1), (xx + .22, yy + .22, z + 17.3), 'Masonry', STONE, .03)
    belfry(b, cx, cy, z + 12.5, 5, 4.7, 1.9, .42)
    tier(b, cx, cy, z + 12.3, 5, .3, .22)
    tier(b, cx, cy, z + 17.2, 5, .34, .26)
    b.lathe((cx, cy, z + 17.5), [(2.4, 0), (2.4, .7), (2.5, .74), (2.5, .86), (2.42, .9)], 'Masonry', STONE, 16)
    dome(b, (cx, cy, z + 18.4), 2.42, 3.5)
    cross(b, cx, cy, z + 21.9)
    finish(b)


def cathedral_core(state):
    """West front, towers, nave. The silhouette survives in both timelines."""
    b = Builder('SM_V_Cathedral_Core_' + state)
    z = 25.0
    x0, x1 = 4.0, 18.0
    y0, y1 = 55.0, 79.0
    paint = stone_paint(state, 3)
    rose_c = (7.0, z + 11.8)

    def rose_hole(u0, r):
        return [(u0 + r * math.cos(i * math.tau / 28), rose_c[1] + r * math.sin(i * math.tau / 28)) for i in range(28)]
    # West front between the towers: great portal, rose window, stepped gable.
    front = lambda length: [(0, z - .4), (length, z - .4), (length, z + 15.0), (length / 2, z + 18.6), (0, z + 15.0)]
    portal = arched(7.0, z + .02, 3.6, z + 3.4, 2.0)
    slab(b, (x0, y0), (x1, y0), z, z + 15, [portal, rose_hole(7.0, 2.25)], .85, paint=paint, outline=front)
    # Recessed orders around the portal.
    for order in range(4):
        hw = 2.05 + order * .3
        ring = 16
        depth = -.12 - order * .13
        for i in range(ring):
            a0, a1 = math.pi * i / ring, math.pi * (i + 1) / ring
            rz = 2.2 + order * .3
            b.box((11 + hw * math.cos(a0) - .13, y0 + depth, z + 3.4 + rz * math.sin(a0) - .13),
                  (11 + hw * math.cos(a1) + .13, y0 + depth + .4, z + 3.4 + rz * math.sin(a1) + .13), 'Masonry', STONE, .02)
        for side in (-1, 1):
            b.cylinder((11 + side * hw, y0 + depth + .1, z), (11 + side * hw, y0 + depth + .1, z + 3.4), .11, .1, 'Masonry', STONE, 10)
    b.box((11 - 1.8, y0 + .25, z), (11 + 1.8, y0 + .4, z + 3.4), 'Timber', (0, .75, 0, 0), .02)
    for i in range(1, 8):
        b.box((11 - 1.8 + i * .45 - .012, y0 + .22, z + .05), (11 - 1.8 + i * .45 + .012, y0 + .26, z + 3.35), 'Iron', (0, .7, 0, 0))
    # Rose tracery: wheel in stone; glass only while the city still has its windows.
    for i in range(12):
        a = i * math.tau / 12
        if state == 'D' and i in (2, 3, 7):
            continue
        b.beam((11, y0 + .34, rose_c[1]), (11 + 2.25 * math.cos(a), y0 + .34, rose_c[1] + 2.25 * math.sin(a)), .16, .16, 'Masonry', STONE)
    b.cylinder((11, y0 + .25, rose_c[1]), (11, y0 + .45, rose_c[1]), .4, .4, 'Masonry', STONE, 14)
    for i in range(28):
        a0, a1 = i * math.tau / 28, (i + 1) * math.tau / 28
        p0 = (11 + 2.5 * math.cos(a0), y0 - .08, rose_c[1] + 2.5 * math.sin(a0))
        p1 = (11 + 2.5 * math.cos(a1), y0 - .08, rose_c[1] + 2.5 * math.sin(a1))
        b.beam(p0, p1, .2, .34, 'Masonry', STONE, up=(0, 1, 0))
    if state == 'R':
        loop = [(11 + 2.3 * math.cos(i * math.tau / 24), y0 + .5, rose_c[1] + 2.3 * math.sin(i * math.tau / 24)) for i in range(24)]
        ids = [b.vertex(p, (0, 1, 0, 0)) for p in loop]
        b.face(ids, 'Glass', [(.5 + .5 * math.cos(i * math.tau / 24), .5 + .5 * math.sin(i * math.tau / 24)) for i in range(24)])
    # Nave walls: north side (left seen from the door) intact, south aisle lives in its own part.
    bays = 6
    length = y1 - y0
    for side, (a, c) in enumerate((((x0, y1), (x0, y0)),)):
        holes = [arched((i + .5) * length / bays, z + 5.0, 1.5, z + 9.2, 1.4) for i in range(bays)]
        slab(b, a, c, z - .4, z + 14, holes, .7, paint=paint)
    for i in range(bays):
        y = y0 + (i + .5) * length / bays
        b.quad((x0 + .4, y - .75, z + 5), (x0 + .4, y + .75, z + 5), (x0 + .4, y + .75, z + 10.6), (x0 + .4, y - .75, z + 10.6), 'Glass', (0, 1, 0, 0), [(0, 0), (1, 0), (1, 2), (0, 2)])
        if i < bays:
            yb = y0 + i * length / bays
            b.box((x0 - 1.1, yb - .4, z - .4), (x0, yb + .4, z + 8), 'Masonry', STONE, .05)
            b.box((x0 - .7, yb - .32, z + 8), (x0, yb + .32, z + 12), 'Masonry', STONE, .05)
    slab(b, (x0, y1), (x1, y1), z - .4, z + 14, [arched(7, z + 5, 3, z + 9.5, 1.5)], .7, paint=paint)
    # Interior arcade, so the shell reads from the doorway.
    for i in range(1, bays):
        y = y0 + i * length / bays
        for x in (x0 + 4, x1 - 4):
            b.cylinder((x, y, z), (x, y, z + 9), .42, .36, 'Masonry', STONE, 12)
            b.box((x - .55, y - .55, z + 9), (x + .55, y + .55, z + 9.5), 'Masonry', STONE, .05)
    # North slope of the nave roof always survives.
    b_eave_z = z + 14
    ridge_z = z + 18.4
    tile_plane(b, (x0 - .5, y1, b_eave_z), (x0 - .5, y0 + .4, b_eave_z), (11, y0 + .4, ridge_z), (11, y1, ridge_z), 44, 14)
    # Crossing dome over its drum, with lantern and cross.
    b.lathe((11, 72, z + 18), [(4.9, -3.3), (4.9, 0), (5.1, .05), (5.1, .3), (4.8, .36), (4.8, 1.5), (5.0, 1.55), (5.0, 1.8)], 'Masonry', STONE, 28)
    for i in range(14):
        a = i * math.tau / 14
        b.box((11 + 5.0 * math.cos(a) - .13, 72 + 5.0 * math.sin(a) - .13, z + 18.3), (11 + 5.0 * math.cos(a) + .13, 72 + 5.0 * math.sin(a) + .13, z + 19.6), 'Masonry', STONE, .02)
    dome(b, (11, 72, z + 19.8), 4.85, 4.2, 12, 36)
    b.lathe((11, 72, z + 23.9), [(.8, 0), (.8, .8), (.95, .86), (.95, .95)], 'Masonry', STONE, 12)
    dome(b, (11, 72, z + 24.9), .9, .9, 5, 12)
    cross(b, 11, 72, z + 25.7, 1.1)
    # Twin west towers: 4.2 m shafts, belfry, drum, dome.
    for tx in (5.75, 16.25):
        ty, w = 56.75, 4.2
        half = w / 2
        c = [(tx - half, ty - half), (tx + half, ty - half), (tx + half, ty + half), (tx - half, ty + half)]
        for i in range(4):
            holes = [arched(w / 2, z + 6.2, .46, z + 8.0, .23), arched(w / 2, z + 12.2, .56, z + 14.3, .28)]
            slab(b, c[i], c[(i + 1) % 4], z - .4, z + 17.6, holes, .5, paint=stone_paint(state, i + 7))
        for h in (0, 5, 10.5):
            tier(b, tx, ty, z + h, w, .24, .12)
        tier(b, tx, ty, z + 17.3, w, .34, .24)
        for xx in (tx - half, tx + half):
            for yy in (ty - half, ty + half):
                b.box((xx - .2, yy - .2, z - .4), (xx + .2, yy + .2, z + 17.3), 'Masonry', STONE, .03)
        belfry(b, tx, ty, z + 17.6, w, 5, 1.55, .4, state)
        tier(b, tx, ty, z + 22.6, w, .3, .2)
        b.lathe((tx, ty, z + 22.9), [(1.95, 0), (1.95, .5), (2.05, .54), (2.05, .66)], 'Masonry', STONE, 14)
        dome(b, (tx, ty, z + 23.55), 1.98, 2.5, 8, 22)
        cross(b, tx, ty, z + 26, .9)
    finish(b, reach=5, rays=10, strength=.7)


def cathedral_south(state):
    """South aisle, south roof slope and the cloister: the part the war took."""
    b = Builder('SM_V_Cathedral_South_' + state)
    z = 25.0
    x1, y0, y1 = 18.0, 55.0, 79.0
    length = y1 - y0
    bays = 6
    eave, ridge = z + 14, z + 18.4
    if state == 'R':
        holes = [arched((i + .5) * length / bays, z + 5.0, 1.5, z + 9.2, 1.4) for i in range(bays)]
        slab(b, (x1, y0), (x1, y1), z - .4, z + 14, holes, .7, paint=stone_paint('R', 2))
        tile_plane(b, (x1 + .5, y0 + .4, eave), (x1 + .5, y1, eave), (11, y1, ridge), (11, y0 + .4, ridge), 44, 14)
        for i in range(bays):
            y = y0 + (i + .5) * length / bays
            b.quad((x1 - .4, y + .75, z + 5), (x1 - .4, y - .75, z + 5), (x1 - .4, y - .75, z + 10.6), (x1 - .4, y + .75, z + 10.6), 'Glass', (0, 1, 0, 0), [(0, 0), (1, 0), (1, 2), (0, 2)])
    else:
        # The wall stands at the west end and steps down in a broken profile to the east.
        def outline(length_):
            top = jagged((length_, z + 3.4), (length_ * .62, z + 6), 1.4, 3) + jagged((length_ * .62, z + 6), (length_ * .3, z + 12.2), 1.8, 4) + [(0, z + 14)]
            return [(0, z - .4), (length_, z - .4)] + top
        holes = [arched(2 + 4 * i, z + 5.0, 1.5, z + 9.2, 1.4) for i in (0, 1)]
        slab(b, (x1, y0), (x1, y1), z - .4, z + 14, holes, .7, paint=stone_paint('D', 2), outline=outline)
        tile_plane(b, (x1 + .5, y0 + .4, eave), (x1 + .5, y1, eave), (11, y1, ridge), (11, y0 + .4, ridge), 44, 14,
                   keep=lambda c, r: (c < 12 and field(c, r, .3, 30) > .22) or (c < 17 and r > 8 and field(c, r, .2, 31) > .5))
        for i in range(13):
            y = y0 + 5.5 + i * 1.5
            top = (.25 + field(i, 1, .9, 32) * .75) if i % 3 else 1.0
            b.beam((x1 + .3, y, eave - .2), (x1 + .3 + (11 - x1 - .3) * top, y, eave - .2 + (ridge - eave) * top), .22, .26, 'Timber', (0, .7, .3, 0))
        # Survivors' repair at the west end: tarred canvas over the last sound bay.
        b.quad((x1 + .55, y0 + 3, eave + .22), (x1 + .55, y0 + 7.5, eave + .22), (13.4, y0 + 7.5, ridge - 1.0), (13.4, y0 + 3, ridge - 1.0), 'Cloth', (.3, .34, .36, 1), [(0, 0), (2, 0), (2, 2), (0, 2)])
        for i in range(6):
            x, y = 22 + field(i, 3, .9, 33) * 4, 60 + i * 3.4
            for j in range(6):
                s = .3 + field(i, j, .8, 34) * .6
                b.box((x + j * .5 - s, y + field(j, i, .8, 35) * 1.2 - s, z), (x + j * .5 + s, y + field(j, i, .8, 35) * 1.2 + s, z + s * .7), 'Masonry', (0, .85, .1, 0))
    # Cloister arcade, roofed when restored.
    for xx, flip in ((21.0, 1), (25.0, -1)):
        for i in range(5):
            a = 56 + i * 4
            opening = arched(2, z + .02, 2.2, z + 4.7, 1.9)
            start, end = ((xx, a), (xx, a + 4)) if flip < 0 else ((xx, a + 4), (xx, a))
            if state == 'D' and i in (3,) and flip < 0:
                continue
            top = z + 8.4 if state == 'R' else z + 7.2 + field(i, flip, .8, 36) * 1.1
            slab(b, start, end, z - .4, top, [opening], .55, paint=stone_paint(state, i))
    if state == 'R':
        tile_plane(b, (25.5, 76, z + 8.4), (25.5, 56, z + 8.4), (23, 56, z + 10.2), (23, 76, z + 10.2), 26, 6)
        tile_plane(b, (20.5, 56, z + 8.4), (20.5, 76, z + 8.4), (23, 76, z + 10.2), (23, 56, z + 10.2), 26, 6)
        slab(b, (25, 76), (21, 76), z - .4, z + 10.2, [], .5, paint=stone_paint('R', 9),
             outline=lambda length_: [(0, z - .4), (length_, z - .4), (length_, z + 8.4), (length_ / 2, z + 10.2), (0, z + 8.4)])
    else:
        outline = lambda length_: [(0, z - .4), (length_, z - .4)] + jagged((length_, z + 8.2), (0, z + 8.8), .9, 8)
        slab(b, (25, 76), (21, 76), z - .4, z + 9, [], .5, paint=stone_paint('D', 9), outline=outline)
        for i in range(0, 5, 2):
            y = 58 + i * 4
            b.beam((21, y, z + 8), (23, y, z + 9.6 + field(i, 2, .9, 37)), .2, .24, 'Timber', (0, .7, .3, 0))
    finish(b, reach=5, rays=10, strength=.7)


def lighthouse(state):
    b = Builder('SM_V_Lighthouse_' + state)
    cx, cy, z = 58.0, 31.0, 2.0
    soot = 0 if state == 'R' else .45
    tone = (.55 if state == 'R' else .3, 1, soot, 0)
    b.lathe((cx, cy, z), [(4.4, -3), (4.4, 2.1), (4.7, 2.15), (4.7, 2.42), (2.0, 2.42)], 'Masonry', (0, 1, 0, 0), 12)
    b.lathe((cx, cy, z), [(1.95, 2.3), (1.82, 3.0), (1.6, 8), (1.36, 12.9)], 'Masonry', tone, 24)
    for h, r in ((3.0, 1.9), (8.0, 1.7)):
        b.lathe((cx, cy, z + h), [(r - .1, -.1), (r, -.05), (r, .12), (r - .1, .17)], 'Masonry', STONE, 24)
    b.lathe((cx, cy, z + 12.9), [(1.36, 0), (1.55, .3), (1.85, .75), (2.15, 1.1), (2.15, 1.3), (1.3, 1.34)], 'Masonry', STONE, 24)
    for a in (0, math.pi / 2, math.pi, math.pi * 1.5):
        for h in (5.5, 10.0):
            r = 1.85 - (h - 2.3) * .05
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            b.box((x - .16, y - .16, z + h), (x + .16, y + .16, z + h + .8), 'Flat', (0, .4, 0, 0))
    sides = 12
    panes = sides if state == 'R' else 0
    for i in range(sides):
        a0, a1 = i * math.tau / sides, (i + 1) * math.tau / sides
        p0 = (cx + 1.25 * math.cos(a0), cy + 1.25 * math.sin(a0))
        p1 = (cx + 1.25 * math.cos(a1), cy + 1.25 * math.sin(a1))
        b.beam((p0[0], p0[1], z + 14.3), (p0[0], p0[1], z + 16.1), .07, .07, 'Iron', STONE)
        if state == 'R' or i in (2, 3, 8):
            b.quad((p0[0], p0[1], z + 14.35), (p1[0], p1[1], z + 14.35), (p1[0], p1[1], z + 16.05), (p0[0], p0[1], z + 16.05), 'Glass', (0, 1, 0, 0), [(0, 0), (1, 0), (1, 1), (0, 1)])
    b.lathe((cx, cy, z + 16.1), [(1.42, 0), (1.5, .04), (1.5, .12)], 'Iron', STONE, sides)
    dome(b, (cx, cy, z + 16.2), 1.5, 1.2, 6, 16)
    b.beam((cx, cy, z + 17.3), (cx, cy, z + 18.2), .06, .06, 'Iron', STONE)
    posts = 24
    for i in range(posts):
        a0, a1 = i * math.tau / posts, (i + 1) * math.tau / posts
        if state != 'R' and 4 < i < 11:
            continue
        p = (cx + 2.08 * math.cos(a0), cy + 2.08 * math.sin(a0))
        q = (cx + 2.08 * math.cos(a1), cy + 2.08 * math.sin(a1))
        b.beam((p[0], p[1], z + 14.2), (p[0], p[1], z + 15.2), .04, .04, 'Iron', STONE)
        b.beam((p[0], p[1], z + 15.2), (q[0], q[1], z + 15.2), .05, .05, 'Iron', STONE)
    if state == 'R':
        # The lamp itself, warm and restrained.
        b.cylinder((cx, cy, z + 14.5), (cx, cy, z + 15.6), .3, .3, 'Flat', (1, 1, 0, 0), 10)
    finish(b, reach=3, rays=10, strength=.6)


campanile()
for s in ('R', 'D'):
    cathedral_core(s)
    cathedral_south(s)
    lighthouse(s)

path = OUT / 'kit_manifest.json'
existing = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
existing.update(manifest)
path.write_text(json.dumps(existing, indent=2), encoding='utf-8')
print('LANDMARKS', len(manifest), 'triangles', sum(m['triangles'] for m in manifest.values()), flush=True)

if 'preview' in sys.argv:
    import kit_preview
    # Authored in world space: show the restored and damaged cathedral side by side.
    for obj in built:
        obj.hide_render = True
    r = [o for o in built if o.name in ('SM_V_Cathedral_Core_R', 'SM_V_Cathedral_South_R')]
    d = [o for o in built if o.name in ('SM_V_Cathedral_Core_D', 'SM_V_Cathedral_South_D')]
    c = [o for o in built if o.name == 'SM_V_Campanile']
    for o in r + d + c:
        o.hide_render = False
    for o in d:
        o.location = (46, 0, 0)
    scene = bpy.context.scene
    kit_preview.render([], OUT / 'previews' / 'landmarks.png', columns=1, target=(32, 60, 34), location=(32, -8, 40), lens=30, samples=32)
