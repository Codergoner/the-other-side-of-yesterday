"""Verdant PBR texture set. Run with Blender's Python (needs numpy + bpy image loading).

Every map tiles. Colour targets follow CITY_AND_SKY.md: warm ivory masonry is the largest
area, muted blue-green roofs and shutters, dark brown timber, small flower accents.
Plaster and timber detail comes from the CC0 Poly Haven scans already staged in
output/premium_sources; everything else is synthesised here. Output: output/verdant/textures.
Packed maps are named _ARH: R ambient occlusion, G roughness, B height.
"""
import math
import sys
import zlib
import struct
from pathlib import Path

import numpy as np

import bpy

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'output' / 'verdant' / 'textures'
OUT.mkdir(parents=True, exist_ok=True)
SOURCES = ROOT / 'output' / 'premium_sources' / 'downloads'
RNG = np.random.default_rng(7301)


def save_png(name, array):
    a = np.clip(array, 0, 1)
    if a.ndim == 2:
        a = a[..., None]
    h, w, c = a.shape
    data = (a * 255 + .5).astype(np.uint8)
    kind = {1: 0, 3: 2, 4: 6}[c]
    raw = np.concatenate([np.zeros((h, 1), np.uint8), data.reshape(h, w * c)], axis=1).tobytes()

    def chunk(tag, payload):
        body = tag + payload
        return struct.pack('>I', len(payload)) + body + struct.pack('>I', zlib.crc32(body))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, kind, 0, 0, 0)) + \
        chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b'')
    (OUT / (name + '.png')).write_bytes(png)
    print('wrote', name, a.shape, flush=True)


def srgb(hex_colour):
    h = hex_colour.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)


def fbm(n, beta=2.0, seed=None, low=1.0, high=None):
    """Tileable power-law noise, normalised to 0..1."""
    g = RNG if seed is None else np.random.default_rng(seed)
    white = g.normal(size=(n, n))
    fy = np.fft.fftfreq(n)[:, None] * n
    fx = np.fft.rfftfreq(n)[None, :] * n
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1
    shape = f ** (-beta / 2)
    shape[f < low] = 0
    if high:
        shape *= np.exp(-(f / high) ** 2)
    out = np.fft.irfft2(np.fft.rfft2(white) * shape, s=(n, n)).astype(np.float32)
    lo, hi = np.percentile(out, (.5, 99.5))
    return np.clip((out - lo) / (hi - lo), 0, 1)


def blur(a, radius):
    n, m = a.shape
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.rfftfreq(m)[None, :]
    k = np.exp(-2 * (np.pi * radius) ** 2 * (fx * fx + fy * fy))
    return np.fft.irfft2(np.fft.rfft2(a) * k, s=a.shape).astype(np.float32)


def normal_from(height, strength):
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * strength
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * strength
    # Unreal expects +Y down in texture space (DirectX), matching np row order.
    n = np.stack([-dx, -dy, np.ones_like(height)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * .5 + .5


def cavity(height, radius, gain):
    return np.clip(1 - np.clip(blur(height, radius) - height, 0, 1) * gain, 0, 1)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def ramp(t, colours):
    stops = np.linspace(0, 1, len(colours))
    return np.stack([np.interp(t, stops, [c[i] for c in colours]) for i in range(3)], -1).astype(np.float32)


def tint_cells(ids, count, colours, spread, seed):
    g = np.random.default_rng(seed)
    palette = ramp(g.random(count), colours) * (1 + g.normal(size=(count, 1)) * spread)
    return palette[ids % count]


def load_image(path, size):
    image = bpy.data.images.load(str(path))
    w, h = image.size
    px = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[::-1][..., :3]
    bpy.data.images.remove(image)
    if h != size or w != size:
        y = (np.linspace(0, h - 1, size)).astype(int)
        x = (np.linspace(0, w - 1, size)).astype(int)
        px = px[y][:, x]
    return px


def write_set(name, base, height, roughness, normal_strength, ao=None):
    save_png('T_V_%s_BC' % name, base)
    save_png('T_V_%s_N' % name, normal_from(height, normal_strength))
    ao = cavity(height, 5, 5) if ao is None else ao
    save_png('T_V_%s_ARH' % name, np.stack([ao, np.clip(roughness, .04, 1), height], -1))


def block_layout(n, rows, min_cols, max_cols, seed):
    """Random running bond: returns per-pixel block id and distance to the block edge (px)."""
    g = np.random.default_rng(seed)
    heights = g.uniform(.72, 1.28, rows)
    edges = np.round(np.cumsum(np.r_[0, heights / heights.sum()]) * n).astype(int)
    ids = np.zeros((n, n), np.int32)
    dist = np.zeros((n, n), np.float32)
    next_id = 0
    for r in range(rows):
        y0, y1 = edges[r], edges[r + 1]
        cols = g.integers(min_cols, max_cols + 1)
        widths = g.uniform(.6, 1.45, cols)
        xs = np.round(np.cumsum(np.r_[0, widths / widths.sum()]) * n).astype(int)
        shift = g.integers(0, n)
        for c in range(cols):
            x0, x1 = xs[c], xs[c + 1]
            xx = (np.arange(x0, x1) + shift) % n
            ids[np.ix_(np.arange(y0, y1), xx)] = next_id + c
            dx = np.minimum(np.arange(x1 - x0), np.arange(x1 - x0)[::-1])[None, :]
            dy = np.minimum(np.arange(y1 - y0), np.arange(y1 - y0)[::-1])[:, None]
            dist[np.ix_(np.arange(y0, y1), xx)] = np.minimum(np.broadcast_to(dx, (y1 - y0, x1 - x0)),
                                                             np.broadcast_to(dy, (y1 - y0, x1 - x0)))
        next_id += cols
    return ids, dist, next_id


def voronoi(n, cells, jitter, seed, stretch=1.0):
    """Tileable jittered grid Voronoi: F1, F2 (in cell units) and nearest cell id."""
    g = np.random.default_rng(seed)
    points = g.random((cells, cells, 2)) * jitter + (1 - jitter) / 2
    points[1::2, :, 0] += .5
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) * cells / n
    ix, iy = np.floor(x).astype(np.int32), np.floor(y).astype(np.int32)
    fx, fy = x - ix, y - iy
    best, second = np.full((n, n), 9.0, np.float32), np.full((n, n), 9.0, np.float32)
    ids = np.zeros((n, n), np.int32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            cy = (iy + dy) % cells
            cx = (ix + dx) % cells
            d = (dx + points[cy, cx, 0] - fx) ** 2 + ((dy + points[cy, cx, 1] - fy) * stretch) ** 2
            d = np.sqrt(d)
            closer = d < best
            second = np.where(closer, best, np.minimum(second, d))
            best = np.where(closer, d, best)
            ids = np.where(closer, cy * cells + cx, ids)
    return best, second, ids


def warped(ids, dist, n, amount, seed):
    """Displace the lookup so block edges wander instead of ruling straight lines."""
    yy, xx = np.mgrid[0:n, 0:n]
    wx = ((fbm(n, 2.3, seed, 3) - .5) * amount).astype(np.int32)
    wy = ((fbm(n, 2.3, seed + 1, 3) - .5) * amount).astype(np.int32)
    yw, xw = (yy + wy) % n, (xx + wx) % n
    return ids[yw, xw], dist[yw, xw]


def limestone(n=2048):
    """Dressed ashlar on a 4 m tile: warm ivory blocks, chipped arrises, tight lime joints."""
    ids, dist, count = block_layout(n, 13, 7, 11, 11)
    ids, dist = warped(ids, dist, n, 7, 212)
    chip = fbm(n, 1.9, 21, 6) * 5
    edge = smoothstep(.6, 3.2 + chip, dist)
    pit = fbm(n, 1.1, 22, 12)
    cloud = fbm(n, 2.4, 23, 1.5)
    block_h = np.random.default_rng(5).random(count)[ids % count] * .1
    height = edge * (.6 + block_h + cloud * .16) + (pit - .5) * .1 + (fbm(n, 1.7, 24, 5) - .5) * .13
    height = np.clip(height, 0, 1)
    colours = [srgb(c) for c in ('#C6AC86', '#CFB791', '#D6C19C', '#CBB08A', '#DAC7A4')]
    base = tint_cells(ids, count, colours, .025, 31)
    base *= (.84 + cloud[..., None] * .27)
    mortar = srgb('#A99473')
    base = base * edge[..., None] + mortar * (1 - edge[..., None])
    stain = smoothstep(.52, .86, fbm(n, 2.3, 25, 2))[..., None]
    base *= 1 - stain * np.array([.12, .15, .2])
    speck = (pit > .85)[..., None]
    base = np.where(speck, base * .84, base)
    write_set('Limestone', base, height, .74 + (1 - edge) * .14 + (pit - .5) * .1, 9)

def plaster(n=2048):
    """Aged lime render over a 4 m tile, keyed by the CC0 scan plus sun-bleached blotches."""
    src = SOURCES / 'white_plaster_02'
    scan = load_image(src / 'white_plaster_02_diff_2k.jpg', n)
    nor = load_image(src / 'white_plaster_02_nor_dx_2k.png', n)
    lum = scan.mean(-1)
    # Remove scan-scale illumination so tiling stays even, keep surface detail.
    lum = lum - blur(lum, 120) + .5
    # Blend edges to hide the scan's seam: it already tiles per Poly Haven.
    stain = fbm(n, 2.6, 41, 1.2)
    stain2 = fbm(n, 2.2, 42, 3)
    tone = ramp(stain * .6 + stain2 * .4, [srgb(c) for c in ('#C8B28C', '#DCC9A6', '#E6D6B6', '#D6BF97')])
    base = tone * (.84 + (lum[..., None] - .5) * 1.1)
    drips = np.clip(fbm(n, 1.8, 43, 3) * smoothstep(.45, .9, blur(fbm(n, 2.4, 44, 1), 3)), 0, 1)
    base *= 1 - drips[..., None] * np.array([.18, .2, .24])
    rough = .86 + (lum - .5) * .2
    height = np.clip(lum, 0, 1)
    save_png('T_V_Plaster_BC', base)
    save_png('T_V_Plaster_N', nor)
    save_png('T_V_Plaster_ARH', np.stack([cavity(height, 4, 3), np.clip(rough, .4, 1), height], -1))


def cobble(n=2048):
    """Worn stone setts laid in rows on a 4 m tile, like the polished uphill road concept."""
    rows, lo, hi = 30, 22, 30
    ids, dist, count = block_layout(n, rows, lo, hi, 51)
    # 15 November 2026: in the story map's shade the first version read as pale fuzz between ragged black lines
    # (a pit field too fine and too strong for the normal map, joint edges broken up by noise, deep cavity
    # occlusion). The joints now wander gently, the stone faces are smooth with a broad crown, and the
    # occlusion in the joints is shallow.
    ids, dist = warped(ids, dist, n, 9, 251)
    lean = fbm(n, 2.4, 52, 3) * 1.0
    stone = smoothstep(.8, 3.6 + lean, dist)
    dome = np.sqrt(np.clip(smoothstep(0, 22, dist), 0, 1))
    g = np.random.default_rng(53)
    lift = g.random(count)[ids % count] * .13
    pit = fbm(n, 2.0, 54, 4, 48)
    height = stone * (.4 + dome * .42 + lift) + (pit - .5) * .02
    colours = [srgb(c) for c in ('#9E8E78', '#AD9A7E', '#B9A586', '#A49686', '#C2AD8C', '#94897A')]
    base = tint_cells(ids, count, colours, .05, 55)
    base *= .84 + fbm(n, 2.2, 56, 3)[..., None] * .3
    silt = srgb('#85755F')
    base = base * stone[..., None] + silt * (1 - stone[..., None])
    worn = smoothstep(.45, .95, dome) * stone
    base *= (.94 + worn[..., None] * .1)
    rough = .74 - worn * .2 + (pit - .5) * .08
    height = np.clip(height, 0, 1)
    write_set('Cobble', base, height, rough + (1 - stone) * .2, 6, ao=cavity(height, 5, 1.8))

def flagstone(n=2048):
    """Large rectangular pavers for squares, quays and the cathedral plaza (6 m tile)."""
    ids, dist, count = block_layout(n, 9, 5, 8, 61)
    warp = fbm(n, 2.1, 62, 3) * 6
    edge = smoothstep(2, 7 + warp, dist)
    cloud = fbm(n, 2.3, 63, 2)
    # 15 November 2026: smooth faces and shallow joints, as for the setts above.
    pit = fbm(n, 2.0, 64, 4, 48)
    lift = np.random.default_rng(65).random(count)[ids % count] * .16
    height = np.clip(edge * (.55 + lift + cloud * .12) + (pit - .5) * .025, 0, 1)
    colours = [srgb(c) for c in ('#A8957A', '#BCA88A', '#C8B596', '#9D8E78', '#B09C7E')]
    base = tint_cells(ids, count, colours, .05, 66) * (.86 + cloud[..., None] * .26)
    base = base * edge[..., None] + srgb('#7D6E5A') * (1 - edge[..., None])
    write_set('Flagstone', base, height, .76 + (pit - .5) * .08 + (1 - edge) * .16, 5, ao=cavity(height, 5, 1.8))


def rooftile(n=2048):
    """Barrel tiles, weathered blue-green glaze. Tile = 2.5 x 2.5 m, 11 columns, 7 courses."""
    columns, courses = 11, 7
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) / n
    cx = x * columns
    row = y * courses
    fx = cx - np.floor(cx)
    profile = np.sqrt(np.clip(1 - (2 * fx - 1) ** 2, 0, 1))
    offset = (np.floor(cx) % 2) * .5
    fy = (row + offset) % 1
    # Each tile rises toward its lower lip, then drops onto the tile beneath it.
    lap = fy ** .7
    lip = smoothstep(.0, .05, fy)
    height = profile * (.5 + lap * .42) * lip + (1 - lip) * .12
    ids = (np.floor(cx).astype(np.int32) + 97 * np.floor(row + offset).astype(np.int32)) % 997
    grime = fbm(n, 2.2, 72, 1.6)
    colours = [srgb(c) for c in ('#3B6A6A', '#44756F', '#4F7F76', '#39646A', '#587F75', '#41706C')]
    base = tint_cells(ids, 997, colours, .045, 73)
    base *= (.74 + profile[..., None] * .36)
    lichen = smoothstep(.6, .9, fbm(n, 1.9, 74, 3))[..., None] * .55
    base = base * (1 - lichen) + srgb('#8C8A68') * lichen
    base *= .8 + grime[..., None] * .32
    trough = (1 - profile)[..., None]
    base = base * (1 - trough * .6) + srgb('#20302E') * trough * .4
    shadow = (1 - smoothstep(0, .09, fy))[..., None] * .6
    base *= 1 - shadow
    rough = .5 + (1 - profile) * .3 + (grime - .5) * .2
    write_set('RoofTile', base, np.clip(height, 0, 1), rough, 13)

def timber(n=1024):
    src = SOURCES / 'fine_grained_wood'
    col = load_image(src / 'fine_grained_wood_col_2k.jpg', n)
    nor = load_image(src / 'fine_grained_wood_nor_dx_2k.png', n)
    arm = load_image(src / 'fine_grained_wood_arm_2k.jpg', n)
    lum = col.mean(-1, keepdims=True)
    # Warm, sun-darkened oak so timber reads dark brown without going black.
    base = np.clip(lum * np.array([.74, .54, .36]) * 1.05, 0, 1)
    save_png('T_V_Timber_BC', base)
    save_png('T_V_Timber_N', nor)
    h = lum[..., 0]
    save_png('T_V_Timber_ARH', np.stack([arm[..., 0], np.clip(arm[..., 1] * 1.05, .3, 1), h], -1))


def rock(n=2048):
    """Weathered coastal limestone: banded strata plus ridged breakup (24 m tile)."""
    ridged = 1 - np.abs(fbm(n, 2.1, 81, 2) * 2 - 1)
    strata_warp = fbm(n, 2.6, 82, 1) * .35
    y = np.mgrid[0:n, 0:n][0].astype(np.float32) / n
    strata = .5 + .5 * np.sin((y + strata_warp) * np.pi * 2 * 9)
    fine = fbm(n, 1.6, 83, 6)
    height = np.clip(ridged * .5 + strata * .24 + fine * .3, 0, 1)
    tone = ramp(height * .55 + fbm(n, 2.4, 84, 2) * .45, [srgb(c) for c in ('#6F5F4E', '#8F7A61', '#AB9478', '#C2AE90')])
    tone *= (.8 + cavity(height, 6, 4)[..., None] * .3)
    write_set('Rock', tone, height, .86 + (fine - .5) * .1, 11)


def ground(n=1024):
    """Dry earth with Mediterranean scrub patches; R of _ARH also serves as patch mask."""
    patch = fbm(n, 2.2, 91, 2)
    fine = fbm(n, 1.2, 92, 18)
    grass = smoothstep(.42, .62, patch + (fine - .5) * .2)[..., None]
    earth = ramp(fbm(n, 2, 93, 3), [srgb(c) for c in ('#7A664A', '#937B59', '#A68D69')])
    scrub = ramp(fine * .6 + patch * .4, [srgb(c) for c in ('#47502F', '#5C6636', '#74773F', '#8B8548')])
    base = earth * (1 - grass) + scrub * grass
    height = np.clip(fine * .5 + grass[..., 0] * .4, 0, 1)
    write_set('Ground', base, height, .92 - grass[..., 0] * .08, 6)


def canvas(n=512):
    weave_u = .5 + .5 * np.sin(np.mgrid[0:n, 0:n][1] * np.pi * 2 * 64 / n)
    weave_v = .5 + .5 * np.sin(np.mgrid[0:n, 0:n][0] * np.pi * 2 * 64 / n)
    height = np.clip((weave_u + weave_v) * .35 + fbm(n, 1.6, 101, 6) * .3, 0, 1)
    soil = fbm(n, 2.2, 102, 1.5)
    base = np.ones((n, n, 3), np.float32) * (.82 + soil[..., None] * .22) * (.86 + height[..., None] * .2)
    write_set('Canvas', np.clip(base, 0, 1), height, np.full((n, n), .9, np.float32), 3)


def iron(n=512):
    rust = smoothstep(.45, .8, fbm(n, 1.9, 111, 3))
    fine = fbm(n, 1.1, 112, 20)
    base = srgb('#23221F') * (1 - rust[..., None]) + srgb('#5B3A25') * rust[..., None]
    base = base * (.8 + fine[..., None] * .4)
    write_set('Iron', base, np.clip(fine * .4 + rust * .5, 0, 1), .5 + rust * .4, 5)


def masks(n=1024):
    """R: large peel field. G: crack/pit detail. B: fine speckle. Sampled in world space."""
    peel = fbm(n, 2.15, 121, 1.2)
    crack_a, crack_b, _ = voronoi(n, 14, .9, 122)
    cracks = 1 - smoothstep(0, .05, crack_b - crack_a)
    pits = fbm(n, 1.4, 123, 10)
    detail = np.clip(pits * .7 + cracks * .55, 0, 1)
    speck = fbm(n, .9, 124, 30)
    save_png('T_V_Masks', np.stack([peel, detail, speck], -1))


def water(n=1024):
    """Directional wind waves; two scrolling samples recombine in the sea shader."""
    fy = np.fft.fftfreq(n)[:, None] * n
    fx = np.fft.rfftfreq(n)[None, :] * n
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1
    angle = np.arctan2(fy, fx)
    spread = np.cos(angle - .6) ** 2
    amp = f ** -1.7 * np.exp(-(f / 120) ** 2) * (.35 + spread)
    amp[f < 2] = 0
    g = np.random.default_rng(131)
    h = np.fft.irfft2(np.fft.rfft2(g.normal(size=(n, n))) * amp, s=(n, n)).astype(np.float32)
    h = (h - h.min()) / (h.max() - h.min())
    save_png('T_V_Water_N', normal_from(h, 22))


def banner(n=512):
    """Verdant civic banner, 17 November 2026: the gold tree on red cloth of the entrant's city atlas ("A gold tree
    on red cloth repeats along streets and inside the Cathedral"). The cloth is .85 x 2 m, so the map is n x 2n and
    is drawn in metres: x across, y down from the pole. The tree is symmetric, as on a banner: trunk, three orders
    of boughs, leaves at every tip, three roots."""
    w, h = n, n * 2
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    mx, my = (xx / w - .5) * .85, yy / h * 2.0
    weave = fbm(h, 1.9, 141, 3)[:, :w]
    fold = .5 + .5 * np.sin(mx * 22 + weave * 2.0)
    base = np.ones((h, w, 3), np.float32) * srgb('#8C1A1C')
    base *= (.80 + weave[..., None] * .30) * (.92 + fold[..., None] * .12)
    gold_mask = np.zeros((h, w), np.float32)

    def stroke(a, b, wa, wb):
        """Soft-edged tapering line from a to b (metres)."""
        pad = max(wa, wb) + .01
        x0, x1 = min(a[0], b[0]) - pad, max(a[0], b[0]) + pad
        y0, y1 = min(a[1], b[1]) - pad, max(a[1], b[1]) + pad
        c0, c1 = max(int((x0 / .85 + .5) * w), 0), min(int((x1 / .85 + .5) * w) + 2, w)
        r0, r1 = max(int(y0 / 2.0 * h), 0), min(int(y1 / 2.0 * h) + 2, h)
        if c1 <= c0 or r1 <= r0:
            return
        px, py = mx[r0:r1, c0:c1], my[r0:r1, c0:c1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = np.clip(((px - a[0]) * dx + (py - a[1]) * dy) / max(dx * dx + dy * dy, 1e-9), 0, 1)
        d = np.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))
        width = wa + (wb - wa) * t
        gold_mask[r0:r1, c0:c1] = np.maximum(gold_mask[r0:r1, c0:c1], np.clip((width - d) / .004, 0, 1))

    def leaf(p, angle, size):
        tip = (p[0] + math.sin(angle) * size, p[1] - math.cos(angle) * size)
        mid = ((p[0] + tip[0]) / 2, (p[1] + tip[1]) / 2)
        stroke(p, mid, .003, size * .34)
        stroke(mid, tip, size * .34, .002)

    def bough(p, angle, length, width, depth):
        q = (p[0] + math.sin(angle) * length, p[1] - math.cos(angle) * length)
        stroke(p, q, width, width * .62)
        if depth == 0:
            for da in (-.75, 0, .75):
                leaf(q, angle + da, .034)
            return
        for da, scale in ((-.62, .74), (0, .66), (.62, .74)):
            if depth == 1 and da == 0:
                leaf(q, angle, .04)
                continue
            bough(q, angle * .82 + da, length * scale, width * .6, depth - 1)
        # Leaves along the bough, alternate sides.
        for k, side in ((.45, 1), (.75, -1)):
            m = (p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k)
            leaf(m, angle + side * 1.1, .028 + depth * .004)

    foot = (0.0, 1.36)
    stroke(foot, (0.0, 1.08), .034, .022)                      # trunk
    for da in (-1.32, -.88, -.44, 0, .44, .88, 1.32):           # crown: a full round head, tallest in the middle
        bough((0.0, 1.10 - abs(da) * .015), da, .168 - abs(da) * .046, .017 - abs(da) * .003, 3 if abs(da) < 1 else 2)
    for sx in (-1, 0, 1):                                       # roots
        stroke(foot, (sx * .09, 1.43), .022, .010)
        stroke((sx * .09, 1.43), (sx * .15, 1.455), .010, .003)
    stroke((-.2, 1.47), (.2, 1.47), .006, .006)                 # ground line
    # Border: a gold line inside the hem, and a gold fringe along the foot.
    border = (np.abs(np.abs(mx) - .365) < .006) & (my > .06) & (my < 1.86) | (np.abs(my - .06) < .006) & (np.abs(mx) < .371) | \
             (np.abs(my - 1.86) < .006) & (np.abs(mx) < .371)
    gold_mask = np.maximum(gold_mask, border.astype(np.float32))
    fringe = (my > 1.93) & (((xx // 6) % 2) == 0)
    gold_mask = np.maximum(gold_mask, fringe.astype(np.float32))
    gold = srgb('#D8A63C') * (.84 + fbm(h, 1.4, 142, 8)[:, :w, None] * .30)
    base = base * (1 - gold_mask[..., None]) + gold * gold_mask[..., None]
    pole_shadow = 1 - .35 * np.exp(-(my / .05) ** 2)
    save_png('T_V_Banner_BC', np.clip(base * pole_shadow[..., None], 0, 1))


def banner_teal_before_20261117(n=512):
    """The civic banner until 17 November 2026: deep teal cloth, muted brass compass motif, pale hem. Kept as the
    revert of the concept pass; not in JOBS."""
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) / n
    u, v = x - .5, y - .46
    r = np.sqrt(u * u + v * v)
    a = np.arctan2(v, u)
    base = np.ones((n, n, 3), np.float32) * srgb('#17475A')
    base *= .86 + fbm(n, 1.9, 141, 3)[..., None] * .3
    petal = np.abs(np.cos(a * 4)) ** 3 * .2 + .07
    motif = (r < petal) | ((r > .26) & (r < .275))
    star = (np.abs(u) < .012 * (1 - r * 3)) | (np.abs(v) < .012 * (1 - r * 3))
    brass = srgb('#C69A52')
    base = np.where((motif | (star & (r < .33)))[..., None], brass, base)
    hem = (x < .05) | (x > .95) | (y < .035)
    base = np.where(hem[..., None], srgb('#CDB98C'), base)
    save_png('T_V_Banner_BC', np.clip(base, 0, 1))


def foliage(n=2048):
    """Masked leaf atlas in a 4 x 2 layout: olive, ivy, cypress, pine / bougainvillea,
    wisteria-free flower mix, dry grass, climbing leaf. Mask is painted with soft discs."""
    g = np.random.default_rng(151)
    atlas = np.zeros((n, n, 4), np.float32)
    cell = n // 4

    def stamp(cx, cy, w, h, angle, colour, x0, y0, size):
        # A single leaf: rotated ellipse with a darker midrib.
        r = int(max(w, h) * 1.1) + 2
        x_a, x_b = max(int(cx) - r, x0), min(int(cx) + r, x0 + size)
        y_a, y_b = max(int(cy) - r, y0), min(int(cy) + r, y0 + size * 2 if size == cell else y0 + size)
        if x_b <= x_a or y_b <= y_a:
            return
        yy, xx = np.mgrid[y_a:y_b, x_a:x_b].astype(np.float32)
        dx, dy = xx - cx, yy - cy
        c, s = np.cos(angle), np.sin(angle)
        px, py = dx * c + dy * s, -dx * s + dy * c
        d = (px / w) ** 2 + (py / h) ** 2
        mask = d < 1
        if not mask.any():
            return
        rib = np.clip(np.abs(py) / (h * .16), .86, 1)[..., None]
        shade = (1.08 - d[..., None] * .3) * rib * (1 + g.normal() * .1)
        region = atlas[y_a:y_b, x_a:x_b]
        region[..., :3] = np.where(mask[..., None], colour * shade, region[..., :3])
        region[..., 3] = np.where(mask, 1, region[..., 3])

    def scatter(col, row, span, count, wr, hr, colours, spread=1.0):
        x0, y0 = col * cell, row * cell
        h = cell * span
        for i in range(count):
            px = x0 + cell * (.5 + (g.random() - .5) * .94 * spread)
            py = y0 + h * (.03 + g.random() * .94)
            colour = colours[g.integers(len(colours))] * (.9 + g.random() * .25)
            stamp(px, py, g.uniform(*wr), g.uniform(*hr), g.uniform(0, np.pi), colour, x0, y0, cell)

    olive = [srgb(c) for c in ('#5C6B45', '#6F7D56', '#8A9670', '#4C5C3C')]
    ivy = [srgb(c) for c in ('#2F4F2A', '#3C6134', '#4E7640', '#2A4426')]
    cypress = [srgb(c) for c in ('#1F3A28', '#2A4A30', '#356038')]
    pine = [srgb(c) for c in ('#35522E', '#46683A', '#2C4628')]
    # 17 November 2026 (concept pass): the atlas asks for pink and purple flowers trailing over the masonry. The
    # climber is now magenta bougainvillea running into violet, and the pots and boxes are rose, violet and cream.
    magenta = [srgb(c) for c in ('#C2337F', '#D94C97', '#A0286E', '#8A3FA8', '#A259C4', '#E06AAE')]
    flowers = [srgb(c) for c in ('#D45A9E', '#9A4FC0', '#F0E4D2', '#C63F6E', '#B478D8', '#E8B64A')]
    dry = [srgb(c) for c in ('#8C8A4C', '#A29A5A', '#6F7A3E')]
    scatter(0, 0, 1, 900, (10, 18), (3, 6), olive)
    scatter(1, 0, 1, 520, (16, 26), (11, 18), ivy)
    scatter(2, 0, 1, 1800, (8, 15), (2, 4), cypress)
    scatter(3, 0, 1, 1500, (14, 30), (1.4, 2.6), pine)
    scatter(0, 1, 1, 380, (14, 24), (10, 18), ivy)
    scatter(0, 1, 1, 420, (15, 25), (13, 21), magenta)
    scatter(1, 1, 1, 520, (14, 24), (10, 18), ivy)
    scatter(1, 1, 1, 430, (9, 14), (9, 14), flowers)
    # Grass tufts grow from the bottom edge of their cell.
    x0, y0 = 2 * cell, cell
    for i in range(420):
        px = x0 + cell * g.random()
        length = g.uniform(cell * .25, cell * .9)
        base_y = y0 + cell - 2
        steps = int(length / 4)
        bend = g.uniform(-.5, .5)
        colour = dry[g.integers(len(dry))] * (.9 + g.random() * .3)
        for s in range(steps):
            t = s / max(1, steps)
            stamp(px + bend * length * t * t, base_y - length * t, 2.4 * (1 - t) + .6, 5, 1.57, colour, x0, y0, cell)
    # Vine strand for hanging curtains of foliage.
    x0 = 3 * cell
    for i in range(14):
        px = x0 + cell * (i + .5) / 14
        for s in range(90):
            t = s / 90
            sx = px + np.sin(t * 9 + i) * 10
            stamp(sx + g.normal() * 9, y0 + t * cell, 12 * (1 - t * .5), 8 * (1 - t * .5), g.uniform(0, 3.14),
                  ivy[g.integers(4)] * (.9 + g.random() * .3), x0, y0, cell)
    # Lower half: bark and small cards, opaque.
    bark = fbm(n // 2, 1.8, 152, 6)
    atlas[n // 2:, :n // 2, :3] = ramp(bark, [srgb('#3A2C20'), srgb('#5C4A38'), srgb('#7A6650')])
    atlas[n // 2:, :n // 2, 3] = 1
    # Bleed colour outward so mipmapped alpha edges do not fringe dark.
    rgb = atlas[..., :3].copy()
    alpha = atlas[..., 3:4].copy()
    fill = blur(rgb[..., 0] * alpha[..., 0], 8), blur(rgb[..., 1] * alpha[..., 0], 8), blur(rgb[..., 2] * alpha[..., 0], 8)
    weight = np.maximum(blur(alpha[..., 0], 8), 1e-3)
    bleed = np.stack([f / weight for f in fill], -1)
    atlas[..., :3] = rgb * alpha + bleed * (1 - alpha)
    save_png('T_V_Foliage_BC', np.clip(atlas, 0, 1))


def people_free_glass(n=256):
    """Window glass: faint leading and dusty lower pane. Emissive use reads this as a mask."""
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) / n
    leading = (np.abs((x * 2) % 1 - .5) > .485) | (np.abs((y * 3) % 1 - .5) > .485)
    dust = fbm(n, 2, 161, 1.5)
    base = np.ones((n, n, 3), np.float32) * (.5 + dust[..., None] * .5)
    base = np.where(leading[..., None], 0, base)
    save_png('T_V_Glass_M', np.clip(base, 0, 1))


JOBS = dict(limestone=limestone, plaster=plaster, cobble=cobble, flagstone=flagstone, rooftile=rooftile,
            timber=timber, rock=rock, ground=ground, canvas=canvas, iron=iron, masks=masks, water=water,
            banner=banner, foliage=foliage, glass=people_free_glass)

selected = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else list(JOBS)
for key in selected:
    JOBS[key]()
print('TEXTURES COMPLETE', len(selected), flush=True)
