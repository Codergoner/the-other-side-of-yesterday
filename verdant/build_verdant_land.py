"""Verdant ground: terrain, walkable surfaces, retaining walls, stairs, sea and sky dome.

Terrain is a heightfield clamped against every walkable surface and building footprint, so hills
rise behind the city and cliffs fall away from the road without any surface floating or being
buried. Stairs are visible treads over a separate continuous ramp used only for collision.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vgeo
import verdant_plan as plan
from vgeo import Builder

OUT = HERE.parent / 'output' / 'verdant'
MESHES = OUT / 'meshes'
bpy.ops.wm.read_factory_settings(use_empty=True)
collection = bpy.data.collections.new('Land')
bpy.context.scene.collection.children.link(collection)
manifest = {}
built = {}

# Counter-clockwise coast, metres. East of it is open sea.
COAST = np.array([(-1500, -1300), (-300, -340), (-120, -150), (-40, -70), (-6, -42), (3.6, -30), (4.2, -16), (15.0, -15.2), (15.9, 1.4),
                  (24.8, 1.6), (25.2, 26.8), (21, 30.5), (20.0, 39.6), (29, 46), (33.6, 60), (33.6, 77), (24, 88), (11, 104), (18, 125),
                  (46, 150), (58, 190), (92, 240), (150, 300), (240, 430), (260, 900), (-1500, 1400)], float)
ISLAND = np.array([(50.5, 26), (54, 23.4), (60, 23.2), (65, 27), (65.6, 34), (61.6, 38), (54, 37.6), (50.4, 33)], float)
MOLE = np.array(plan.MOLE)


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def polygon_distance(x, y, poly):
    """Signed distance to a polygon, positive inside."""
    inside = np.zeros_like(x, bool)
    best = np.full_like(x, 1e12, float)
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        crossing = ((ay > y) != (by > y)) & (x < (bx - ax) * (y - ay) / (by - ay + 1e-12) + ax)
        inside ^= crossing
        dx, dy = bx - ax, by - ay
        t = np.clip(((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy), 0, 1)
        best = np.minimum(best, np.hypot(x - ax - t * dx, y - ay - t * dy))
    return np.where(inside, best, -best)


_rng = np.random.default_rng(902)
TABLE = None


def fbm_field(n=512, beta=2.2):
    fy = np.fft.fftfreq(n)[:, None] * n
    fx = np.fft.rfftfreq(n)[None, :] * n
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1
    h = np.fft.irfft2(np.fft.rfft2(_rng.normal(size=(n, n))) * f ** (-beta / 2 - .5), s=(n, n))
    return (h - h.min()) / (h.max() - h.min())


TABLE = fbm_field()


def noise(x, y, scale):
    n = TABLE.shape[0]
    u, v = (x * scale) % n, (y * scale) % n
    i, j = u.astype(int), v.astype(int)
    fu, fv = u - i, v - j
    i1, j1 = (i + 1) % n, (j + 1) % n
    return TABLE[j, i] * (1 - fu) * (1 - fv) + TABLE[j, i1] * fu * (1 - fv) + TABLE[j1, i] * (1 - fu) * fv + TABLE[j1, i1] * fu * fv


def pads():
    """Rectangles the terrain must respect: (x0, x1, y0, y1, z(x, y))."""
    rows = []
    for s in plan.SURFACES:
        x0, x1, y0, y1 = s['x0'], s['x1'], s['y0'], s['y1']
        a, b, c, d = s['z']

        def height(x, y, x0=x0, x1=x1, y0=y0, y1=y1, a=a, b=b, c=c, d=d):
            u = np.clip((x - x0) / (x1 - x0), 0, 1)
            v = np.clip((y - y0) / (y1 - y0), 0, 1)
            return (a * (1 - u) + b * u) * (1 - v) + (d * (1 - u) + c * u) * v
        rows.append((x0, x1, y0, y1, height))
    for b in plan.BUILDINGS:
        pts = [b.world(0, 0), b.world(b.w * plan.BW, 0), b.world(b.w * plan.BW, b.d * plan.BW), b.world(0, b.d * plan.BW)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        rows.append((min(xs), max(xs), min(ys), max(ys), lambda x, y, z=b.z: np.full_like(x, z)))
    for st in plan.STAIRS:
        ax, ay, az = st['a']
        bx, by, bz = st['b']
        w = st['width'] / 2
        along_y = abs(by - ay) > abs(bx - ax)
        x0, x1 = (min(ax, bx) - w, max(ax, bx) + w) if along_y else (min(ax, bx), max(ax, bx))
        y0, y1 = (min(ay, by), max(ay, by)) if along_y else (min(ay, by) - w, max(ay, by) + w)

        def height(x, y, ax=ax, ay=ay, bx=bx, by=by, az=az, bz=bz, along_y=along_y):
            t = np.clip((y - ay) / (by - ay), 0, 1) if along_y else np.clip((x - ax) / (bx - ax), 0, 1)
            return az + (bz - az) * t
        rows.append((x0, x1, y0, y1, height))
    return rows


PADS = pads()


def terrain(x, y):
    d = polygon_distance(x, y, COAST)
    island = polygon_distance(x, y, ISLAND)
    # Hills grow with distance from the sea; broken strata keep the shoreline from looking smooth.
    # The town sits on a hillside that climbs gently inland; the drama is in the far ridges.
    inland = np.maximum(d, 0)
    bulk = np.minimum(inland * .14, 40) + 90 * (1 - np.exp(-inland / 900))
    bumps = (noise(x, y, .9) - .5) * (6 + np.minimum(inland * .12, 30))
    fine = (noise(x, y, 4.2) - .5) * 1.8
    h = np.where(d > 0, bulk + bumps * smooth(0, 40, d) + fine * smooth(0, 8, d) + np.minimum(d * 1.3, 4), -6 + d * .22)
    # Headlands and ridges, rounded shoulders, kept well back from the cathedral hill.
    ridges = ((90, 420, 170, 110, 60), (320, 640, 260, 150, 120), (-160, 560, 360, 180, 140), (-620, 140, 380, 340, 170),
              (-900, 820, 520, 300, 300), (-350, 1100, 650, 320, 360), (420, 1150, 520, 300, 330), (-1200, -300, 500, 400, 260))
    for cx, cy, rx, ry, top in ridges:
        q = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
        ridge = 1 - np.abs(noise(x, y, .35) * 2 - 1) * .5
        h = h + top * np.exp(-q) * (.7 + ridge * .5) * (d > -4)
    h = np.where(island > 0, np.maximum(h, 1.2 + np.minimum(island * .5, 2) + (noise(x, y, 6) - .5) * 1.2), h)
    lower = np.full_like(h, -40.0)
    upper = np.full_like(h, 4000.0)
    for x0, x1, y0, y1, height in PADS:
        dx = np.maximum(np.maximum(x0 - x, x - x1), 0)
        dy = np.maximum(np.maximum(y0 - y, y - y1), 0)
        dist = np.hypot(dx, dy)
        near = dist < 90
        z = height(x, y)
        lower = np.where(near, np.maximum(lower, z - .3 - dist * 2.6), lower)
        upper = np.where(near, np.minimum(upper, z - .14 + dist * .85), upper)
    # A wrong order here would bury the street, so the upper limit (never rise above a pad) wins.
    h = np.minimum(np.maximum(h, lower), upper)
    return h, d, island


def land_mesh(name, x0, x1, y0, y1, step, hole=None):
    xs = np.arange(x0, x1 + step, step)
    ys = np.arange(y0, y1 + step, step)
    gx, gy = np.meshgrid(xs, ys)
    gx = gx + (noise(gx, gy, 20) - .5) * step * .3
    gy = gy + (noise(gy, gx, 20) - .5) * step * .3
    h, d, island = terrain(gx, gy)
    if hole:
        # The far grid continues under the near block, sunk so it never pokes through or leaves a crack.
        inside = np.minimum(np.minimum(gx - hole[0], hole[1] - gx), np.minimum(gy - hole[2], hole[3] - gy))
        h = h - 3.0 * smooth(-30, 10, inside)
    ny, nx = gx.shape
    b = Builder(name)
    keep = h > -3.2
    # Rock on steep ground and near the water, scrub and earth elsewhere; G carries slope shade.
    dzdx = np.gradient(h, axis=1) / step
    dzdy = np.gradient(h, axis=0) / step
    slope = np.hypot(dzdx, dzdy)
    rockiness = smooth(.38, .8, slope)
    rockiness = np.maximum(rockiness, smooth(3.4, 0.6, h))
    ids = -np.ones(gx.shape, int)
    for j in range(ny):
        for i in range(nx):
            neighbourhood = keep[max(j - 1, 0):j + 2, max(i - 1, 0):i + 2]
            if neighbourhood.any():
                ids[j, i] = b.vertex((gx[j, i], gy[j, i], h[j, i]), (float(rockiness[j, i]), 1.0, 0, 0))
    for j in range(ny - 1):
        for i in range(nx - 1):
            q = (ids[j, i], ids[j, i + 1], ids[j + 1, i + 1], ids[j + 1, i])
            if min(q) < 0:
                continue
            slot = 'Rock' if rockiness[j:j + 2, i:i + 2].mean() > .5 else 'Ground'
            b.face(q, slot, [(gx[j, i] / 24, gy[j, i] / 24), (gx[j, i + 1] / 24, gy[j, i + 1] / 24), (gx[j + 1, i + 1] / 24, gy[j + 1, i + 1] / 24), (gx[j + 1, i] / 24, gy[j + 1, i] / 24)])
    return emit(b, smooth_angle=70)


def emit(b, smooth_angle=38):
    obj = b.build(collection, smooth_angle)
    built[obj.name] = obj
    vgeo.export_fbx(obj, MESHES / (obj.name + '.fbx'))
    lo = [min(v[i] for v in b.verts) for i in range(3)]
    hi = [max(v[i] for v in b.verts) for i in range(3)]
    manifest[obj.name] = {'triangles': sum(len(f[0]) - 2 for f in b.faces), 'vertices': len(b.verts), 'bounds_m': [lo, hi],
                          'slots': sorted({vgeo.SLOTS[f[1]] for f in b.faces})}
    return obj


def contact_shade(x, y):
    """Dark line where paving meets a wall; the renderer has no screen-space occlusion."""
    best = 9.0
    for b in plan.BUILDINGS:
        pts = [b.world(0, 0), b.world(b.w * plan.BW, 0), b.world(b.w * plan.BW, b.d * plan.BW), b.world(0, b.d * plan.BW)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        best = min(best, math.hypot(max(min(xs) - x, x - max(xs), 0), max(min(ys) - y, y - max(ys), 0)))
    t = max(0.0, min(1.0, best / 1.5))
    return .62 + .38 * t * t * (3 - 2 * t)


def surfaces():
    b = Builder('SM_V_Land_Surfaces')
    skirts = Builder('SM_V_Land_Walls')
    for s in plan.SURFACES:
        x0, x1, y0, y1 = s['x0'], s['x1'], s['y0'], s['y1']
        a, c, e, d = s['z']
        nx, ny = max(1, int((x1 - x0) / .9)), max(1, int((y1 - y0) / .9))

        def z_at(u, v):
            return (a * (1 - u) + c * u) * (1 - v) + (d * (1 - u) + e * u) * v
        ids = {}
        for j in range(ny + 1):
            for i in range(nx + 1):
                u, v = i / nx, j / ny
                x, y = x0 + (x1 - x0) * u, y0 + (y1 - y0) * v
                ids[i, j] = b.vertex((x, y, z_at(u, v)), (0, contact_shade(x, y), 0, 0))
        for j in range(ny):
            for i in range(nx):
                q = (ids[i, j], ids[i + 1, j], ids[i + 1, j + 1], ids[i, j + 1])
                b.face(q, s['mat'], [tuple(p[:2]) for p in (b.verts[k] for k in q)])
        # Retaining face on all four sides, visible only where the terrain falls away.
        edges = [((x0, y0), (x1, y0), a, c), ((x1, y0), (x1, y1), c, e), ((x1, y1), (x0, y1), e, d), ((x0, y1), (x0, y0), d, a)]
        for (p, q, zp, zq) in edges:
            length = math.hypot(q[0] - p[0], q[1] - p[1])
            ux, uy = (q[0] - p[0]) / length, (q[1] - p[1]) / length
            place = lambda t, ux=ux, uy=uy, p=p: (p[0] + ux * t[0] - uy * t[1], p[1] + uy * t[0] + ux * t[1], t[2])
            bottom = min(zp, zq) - 14
            outline = [(0, bottom), (length, bottom), (length, zq - .02), (0, zp - .02)]
            paint = lambda u, z: (0, .55 + .45 * max(0.0, min(1.0, (z - bottom) / 10)), 0, 0)
            skirts.wall(outline, (), .7, paint=paint, reveal=lambda u, z: (0, .8, 0, 0), spacing=2.2, axis_map=place)
    # Mole: a causeway of dressed blocks with a flagged top.
    points = plan.MOLE
    half = plan.MOLE_WIDTH / 2
    for k in range(len(points) - 1):
        p, q = points[k], points[k + 1]
        dx, dy = q[0] - p[0], q[1] - p[1]
        length = math.hypot(dx, dy)
        nx_, ny_ = -dy / length * half, dx / length * half
        steps = max(1, int(length / 1.5))
        rows = []
        for i in range(steps + 1):
            t = i / steps
            x, y, z = p[0] + dx * t, p[1] + dy * t, p[2] + (q[2] - p[2]) * t
            rows.append((b.vertex((x + nx_, y + ny_, z), (0, 1, 0, 0)), b.vertex((x - nx_, y - ny_, z), (0, 1, 0, 0))))
        for i in range(steps):
            f = (rows[i][1], rows[i + 1][1], rows[i + 1][0], rows[i][0])
            b.face(f, 'Flagstone', [tuple(c[:2]) for c in (b.verts[n] for n in f)])
        for sign in (1, -1):
            ax, ay = p[0] + sign * nx_, p[1] + sign * ny_
            bx, by = q[0] + sign * nx_, q[1] + sign * ny_
            start, end = ((ax, ay), (bx, by)) if sign < 0 else ((bx, by), (ax, ay))
            zs, ze = (p[2], q[2]) if sign < 0 else (q[2], p[2])
            ux, uy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
            place = lambda t, ux=ux, uy=uy, s=start: (s[0] + ux * t[0] - uy * t[1], s[1] + uy * t[0] + ux * t[1], t[2])
            skirts.wall([(0, -2.2), (length, -2.2), (length, ze - .02), (0, zs - .02)], (), .9, paint=lambda u, z: (0, .9, 0, 0), spacing=2.0, axis_map=place)
    emit(b)
    emit(skirts)


def stairs():
    treads = Builder('SM_V_Land_Stairs')
    ramps = Builder('SM_V_Land_Ramps')
    for st in plan.STAIRS:
        a, c = st['a'], st['b']
        width, count = st['width'], st['treads']
        along_y = abs(c[1] - a[1]) > abs(c[0] - a[0])
        run = (c[1] - a[1]) if along_y else (c[0] - a[0])
        rise = c[2] - a[2]
        step = abs(run) / count
        sign = 1 if run > 0 else -1
        for i in range(count):
            t = i / count
            base = a[1 if along_y else 0] + run * t
            z_top = a[2] + rise * (i + (1 if rise > 0 else 0)) / count if rise > 0 else a[2] + rise * i / count
            low, high = sorted((base, base + sign * (step + .02)))
            w = width / 2
            tone = (0, 1 - .12 * ((i % 3) == 1), 0, 0)
            if along_y:
                treads.box((a[0] - w, low, z_top - abs(rise) / count - .5), (a[0] + w, high, z_top), 'Masonry', tone, .018)
            else:
                treads.box((low, a[1] - w, z_top - abs(rise) / count - .5), (high, a[1] + w, z_top), 'Masonry', tone, .018)
        # Solid cheek walls so a flight never shows daylight underneath.
        z0, z1 = a[2], c[2]
        for side in (-1, 1):
            if along_y:
                p, q = (a[0] + side * width / 2, a[1]), (a[0] + side * width / 2, c[1])
            else:
                p, q = (a[0], a[1] + side * width / 2), (c[0], a[1] + side * width / 2)
            flip = (side > 0) == (sign > 0) if along_y else (side < 0) == (sign > 0)
            s, e, zs, ze = (q, p, z1, z0) if flip else (p, q, z0, z1)
            length = abs(run)
            ux, uy = (e[0] - s[0]) / length, (e[1] - s[1]) / length
            place = lambda t, ux=ux, uy=uy, s=s: (s[0] + ux * t[0] - uy * t[1], s[1] + uy * t[0] + ux * t[1], t[2])
            ramps_low = min(z0, z1) - 8
            treads.wall([(0, ramps_low), (length, ramps_low), (length, ze + .2), (0, zs + .2)], (), .3, paint=lambda u, z: (0, .9, 0, 0), spacing=1.4, axis_map=place)
        # Ramp used only by collision, centred on the flight with a little width margin.
        w = width / 2
        if along_y:
            quad = [(a[0] - w, a[1], a[2] + .02), (a[0] + w, a[1], a[2] + .02), (a[0] + w, c[1], c[2] + .02), (a[0] - w, c[1], c[2] + .02)]
        else:
            quad = [(a[0], a[1] - w, a[2] + .02), (c[0], a[1] - w, c[2] + .02), (c[0], a[1] + w, c[2] + .02), (a[0], a[1] + w, a[2] + .02)]
        area = (quad[1][0] - quad[0][0]) * (quad[3][1] - quad[0][1]) - (quad[1][1] - quad[0][1]) * (quad[3][0] - quad[0][0])
        ids = [ramps.vertex(p) for p in (quad if area > 0 else quad[::-1])]
        ramps.face(ids, 'Flat')
    emit(treads)
    emit(ramps)


def sea():
    b = Builder('SM_V_Sea')
    xs = np.arange(-60, 300, 4.0)
    ys = np.arange(-110, 270, 4.0)
    gx, gy = np.meshgrid(xs, ys)
    d = polygon_distance(gx, gy, COAST)
    island = polygon_distance(gx, gy, ISLAND)
    near = np.maximum(d, island)
    shore = np.where(near > -28, 1 - np.clip(-near / 28, 0, 1), 0)
    ids = {}
    ny, nx = gx.shape
    for j in range(ny):
        for i in range(nx):
            ids[j, i] = b.vertex((gx[j, i], gy[j, i], 0), (float(shore[j, i]), 1, 0, 0))
    for j in range(ny - 1):
        for i in range(nx - 1):
            if near[j:j + 2, i:i + 2].min() > 3:
                continue
            q = (ids[j, i], ids[j, i + 1], ids[j + 1, i + 1], ids[j + 1, i])
            b.face(q, 'Sea', [tuple(p[:2]) for p in (b.verts[k] for k in q)])
    # Outer ring reaches well past the haze line.
    inner = [(-60, -110), (296, -110), (296, 266), (-60, 266)]
    outer = [(-16000, -16000), (16000, -16000), (16000, 16000), (-16000, 16000)]
    a = [b.vertex((p[0], p[1], 0), (0, 1, 0, 0)) for p in inner]
    c = [b.vertex((p[0], p[1], 0), (0, 1, 0, 0)) for p in outer]
    for i in range(4):
        j = (i + 1) % 4
        q = (c[i], c[j], a[j], a[i])
        b.face(q, 'Sea', [tuple(p[:2]) for p in (b.verts[k] for k in q)])
    emit(b, 180)


def dome():
    b = Builder('SM_V_SkyDome')
    radius = 30000.0
    sides, rows = 72, 40
    rings = []
    for j in range(rows + 1):
        el = -.5 * math.pi * .32 + (math.pi / 2 + .5 * math.pi * .32) * j / rows
        ring = []
        for i in range(sides + 1):
            az = -math.pi + i * math.tau / sides
            ring.append(b.vertex((radius * math.cos(el) * math.sin(az), radius * math.cos(el) * math.cos(az), radius * math.sin(el)), (0, 1, 0, 0)))
        rings.append((ring, .5 + el / math.pi))
    for j in range(rows):
        lo, v0 = rings[j]
        hi, v1 = rings[j + 1]
        for i in range(sides):
            u0, u1 = i / sides, (i + 1) / sides
            b.face((lo[i], hi[i], hi[i + 1], lo[i + 1]), 'Sky', [(u0, v0), (u0, v1), (u1, v1), (u1, v0)])
    emit(b, 180)


def vegetation():
    """Trees and scrub on open ground, seeded so both timelines share the same hillside."""
    g = np.random.default_rng(3303)
    x = np.r_[g.uniform(-96, 40, 5200), g.uniform(-420, 330, 9000)]
    y = np.r_[g.uniform(-86, 118, 5200), g.uniform(-300, 700, 9000)]
    h, d, _ = terrain(x, y)
    h2, _, _ = terrain(x + 1.5, y)
    h3, _, _ = terrain(x, y + 1.5)
    slope = np.hypot(h2 - h, h3 - h) / 1.5
    clear = np.full_like(x, 99.0)
    for x0, x1, y0, y1, _height in PADS:
        dx = np.maximum(np.maximum(x0 - x, x - x1), 0)
        dy = np.maximum(np.maximum(y0 - y, y - y1), 0)
        clear = np.minimum(clear, np.hypot(dx, dy))
    rows = []
    roll = g.random(len(x))
    tuft = g.random(len(x))
    for i in range(len(x)):
        if d[i] < 2 or h[i] < 2.2 or clear[i] < 1.4 or slope[i] > .95:
            continue
        if i >= 5200 and -96 < x[i] < 40 and -86 < y[i] < 118:
            continue
        rocky = slope[i] > .55
        patch = noise(np.array([x[i]]), np.array([y[i]]), 2.5)[0]
        if roll[i] < .1 and not rocky and clear[i] > 2.4:
            mesh = 'SM_V_Cypress' if patch > .52 else 'SM_V_CypressB'
        elif roll[i] < .22 and not rocky and clear[i] > 3.2:
            mesh = 'SM_V_Olive' if tuft[i] > .5 else 'SM_V_OliveB'
        elif roll[i] < .26 and not rocky and clear[i] > 4:
            mesh = 'SM_V_Pine'
        elif roll[i] < .6:
            mesh = 'SM_V_Bush'
        else:
            mesh = 'SM_V_GrassTuft'
        s = float(g.uniform(.72, 1.2))
        rows.append({'m': mesh, 'p': [round(float(x[i]), 2), round(float(y[i]), 2), round(float(h[i]) - .1, 2)], 'r': round(float(g.uniform(0, 360)), 1), 's': [s, s, s]})
    (OUT / 'vegetation.json').write_text(json.dumps(rows), encoding='utf-8')
    print('VEGETATION', len(rows), flush=True)

if 'Sky' not in vgeo.SLOTS:
    vgeo.SLOTS.append('Sky')
    vgeo.PREVIEW['Sky'] = (.4, .6, .9)

land_mesh('SM_V_Land_Near', -96, 80, -86, 118, 1.5)
# Far terrain keeps the same function on a wide grid, with the near block left out by depth.
land_mesh('SM_V_Land_Far', -1400, 330, -1300, 1400, 22, (-96, 80, -86, 118))
surfaces()
stairs()
sea()
dome()
vegetation()

path = OUT / 'kit_manifest.json'
existing = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
existing.update(manifest)
path.write_text(json.dumps(existing, indent=2), encoding='utf-8')
print('LAND', {k: v['triangles'] for k, v in manifest.items()}, flush=True)
