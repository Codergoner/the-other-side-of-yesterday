"""Story-set props for the merged story map: the pieces that replace the engine-primitive stand-ins
of the clinic, Sela's shop, the harbour waiting shelter, the memorial and chronology cases, the gate,
the family room's watch, photo, letter and anchor, and the past-era infill of the home's wing.

Each replacement is modelled at the exact size of the primitive it replaces, with the pivot at the
centre of that primitive's bounding box, so the story actor keeps its location and only its mesh and
scale change (scale 1, or a per-axis factor where one mesh serves several sizes). New dressing meshes
(ruin frame, notice board, luggage, shelf, stock) have their pivot at the base centre.
SM_V_Story_DoorOpen_R is a kit module (kit pivot) for the clinic's open entrance.

    blender --background --factory-startup --python build_story_props.py
"""
import json
import math
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vgeo
from vgeo import Builder, arch_points, field, jagged
from build_verdant_landmarks_tile import tile_plane

OUT = HERE.parent / 'output' / 'verdant'
MESHES = OUT / 'meshes'
MESHES.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
collection = bpy.data.collections.new('StoryProps')
bpy.context.scene.collection.children.link(collection)
manifest = {}
STONE = (0, 1, 0, 0)
PLASTER = (1, 1, 0, 0)
WOOD = (0, .9, 0, 0)
DARK_WOOD = (0, .62, 0, 0)
OLD = (0, .72, .18, 0)
IRON = (0, .85, 0, 0)
CANVAS = (.8, .72, .56, .12)
LINEN = (.86, .84, .76, .05)
PAPER = (.9, .88, .8, 0)
TARP = (.3, .4, .38, .05)
TEAL_CLOTH = (.2, .42, .44, .12)
CREAM_CLOTH = (.82, .74, .58, .12)
GREY_CLOTH = (.36, .36, .33, .2)


def finish(b, reach=.8, rays=8, strength=.55):
    b.bake_occlusion(rays=rays, reach=reach, strength=strength)
    obj = b.build(collection)
    vgeo.export_fbx(obj, MESHES / (obj.name + '.fbx'))
    lo = [min(v[i] for v in b.verts) for i in range(3)]
    hi = [max(v[i] for v in b.verts) for i in range(3)]
    manifest[obj.name] = {'triangles': sum(len(f[0]) - 2 for f in b.faces), 'vertices': len(b.verts), 'bounds_m': [lo, hi],
                          'slots': sorted({vgeo.SLOTS[f[1]] for f in b.faces}), 'story': True}


def ue(u, v):
    """Blender UV for an Unreal UV (Unreal's V runs down; the FBX exporter flips it)."""
    return (u, 1 - v)


def sheet_x(b, x, y0, y1, z0, z1, slot, colour, uvs=True):
    """Quad facing +X. A viewer in front of it looks along -X and has +Y on their right (checked on the
    chronology case: its lines, shortened at the -Y end, render ragged on the left), so image u runs
    toward +Y and v down."""
    uv = [ue(0, 1), ue(1, 1), ue(1, 0), ue(0, 0)] if uvs else None
    b.quad((x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1), slot, colour, uv)


def cloth_grid(b, corner, du, dv, nu, nv, colour, sag=0.0, slot='Cloth', wind=None, z_fn=None):
    """Sheet from corner spanning du (x) and dv (y) with a sine sag; alpha = wind weight."""
    ox, oy, oz = corner
    for i in range(nu):
        for j in range(nv):
            def p(u, v):
                z = oz + (z_fn(u, v) if z_fn else -sag * math.sin(u * math.pi) * math.sin(v * math.pi))
                return (ox + u * du, oy + v * dv, z)
            u0, u1, v0, v1 = i / nu, (i + 1) / nu, j / nv, (j + 1) / nv
            w = lambda u, v: (wind if wind is not None else colour[3]) * math.sin(u * math.pi) * math.sin(v * math.pi)
            ids = [b.vertex(p(u0, v0), (*colour[:3], w(u0, v0))), b.vertex(p(u1, v0), (*colour[:3], w(u1, v0))),
                   b.vertex(p(u1, v1), (*colour[:3], w(u1, v1))), b.vertex(p(u0, v1), (*colour[:3], w(u0, v1)))]
            b.face(ids, slot, [(u0 * du, v0 * dv), (u1 * du, v0 * dv), (u1 * du, v1 * dv), (u0 * du, v1 * dv)])


# ---- posts and beams ------------------------------------------------------------------------
def post(name, w, h, cap='bracket', band=True):
    b = Builder(name)
    z0, z1 = -h / 2, h / 2
    b.box((-w / 2, -w / 2, z0), (w / 2, w / 2, z1), 'Timber', WOOD, .012)
    if band:
        for z in (z1 - .32, z0 + .25):
            b.box((-w / 2 - .008, -w / 2 - .008, z), (w / 2 + .008, w / 2 + .008, z + .035), 'Iron', IRON)
    if cap == 'bracket':
        for sx in (-1, 1):
            b.beam((sx * w / 2, 0, z1 - .55), (sx * (w / 2 + .3), 0, z1 - .06), w * .55, w * .55, 'Timber', WOOD)
    elif cap == 'pyramid':
        b.box((-w / 2 - .03, -w / 2 - .03, z1), (w / 2 + .03, w / 2 + .03, z1 + .04), 'Timber', DARK_WOOD, .01)
        b.lathe((0, 0, z1 + .04), [(w * .62, 0), (w * .3, .07), (.01, .12)], 'Timber', DARK_WOOD, 8)
    finish(b)


def beam(name, length, w, h, axis='X'):
    b = Builder(name)
    a, c = ((-length / 2, 0, 0), (length / 2, 0, 0)) if axis == 'X' else ((0, -length / 2, 0), (0, length / 2, 0))
    b.beam(a, c, w, h, 'Timber', WOOD)
    finish(b)


def post_stub():
    b = Builder('SM_V_Story_PostStub')
    b.box((-.05, -.05, 0), (.05, .05, .55), 'Timber', OLD, .01)
    for i in range(4):
        z = .55 + i * .05
        b.box((-.05 + i * .012, -.05, z), (.05 - i * .02, .05 - i * .018, z + .05), 'Timber', OLD)
    finish(b)


def ruin_frame():
    """What a timber awning frame leaves after twenty years: stubs, one fallen rail, a torn scrap."""
    b = Builder('SM_V_Story_RuinFrame')
    for x, y, h in ((-.95, -1.15, .55), (.95, -1.15, .3), (-.95, 1.15, .72), (.95, 1.15, .18)):
        b.box((x - .05, y - .05, 0), (x + .05, y + .05, h), 'Timber', OLD, .01)
        for i in range(3):
            b.box((x - .05 + i * .015, y - .05, h + i * .04), (x + .05 - i * .02, y + .05 - i * .015, h + i * .04 + .04), 'Timber', OLD)
    b.beam((-.9, -.9, .07), (.75, .6, .09), .09, .09, 'Timber', OLD)
    b.beam((.6, 1.0, .5), (.95, 1.15, .72), .07, .07, 'Timber', OLD)
    pts = [(-.8, -.2), (.4, -.45), (.7, .5), (-.2, .9), (-.9, .4)]
    centre = b.vertex((0, .1, .035), (*GREY_CLOTH[:3], 0))
    ring = [b.vertex((x, y, .02 + field(x, y, 2.0, 61) * .06), (*GREY_CLOTH[:3], .05)) for x, y in jagged(pts[0], pts[1], .08, 3) + jagged(pts[1], pts[2], .08, 4)
            + jagged(pts[2], pts[3], .08, 5) + jagged(pts[3], pts[4], .08, 6) + jagged(pts[4], pts[0], .08, 7)]
    for i in range(len(ring)):
        b.face((centre, ring[i], ring[(i + 1) % len(ring)]), 'Cloth')
    finish(b, 1.0)


# ---- cloth -----------------------------------------------------------------------------------
def canvas_cover():
    """Installed courtyard canvas, 2.05 x 2.46 m, ties at the corners, hangs 12 cm at the middle."""
    b = Builder('SM_V_Story_CanvasCover')
    w, d = 2.05, 2.46
    cloth_grid(b, (-w / 2, -d / 2, .02), w, d, 8, 10, CANVAS, sag=.12, wind=.2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.beam((sx * w / 2, sy * d / 2, .02), (sx * (w / 2 - .18), sy * (d / 2 - .18), -.02), .02, .02, 'Cloth', (.55, .5, .4, 0))
            b.lathe((sx * (w / 2 - .02), sy * (d / 2 - .02), -.005), [(.03, 0), (.03, .03), (.012, .03)], 'Iron', IRON, 6)
    for x in (-w / 2 + .02, w / 2 - .02):
        b.beam((x, -d / 2, .03), (x, d / 2, .03), .03, .025, 'Cloth', (.6, .55, .44, 0))
    finish(b, .4, 4, .2)


def shade():
    """Sela's striped shade, 1.48 x 2.56 m, stretched between the two posts with a hem board."""
    b = Builder('SM_V_Story_Shade')
    w, d = 1.48, 2.56
    strips = 8
    for i in range(strips):
        y0, y1 = -d / 2 + i * d / strips, -d / 2 + (i + 1) * d / strips
        colour = TEAL_CLOTH if i % 2 == 0 else CREAM_CLOTH
        cloth_grid(b, (-w / 2, y0, 0), w, y1 - y0, 4, 2, colour, sag=.05, wind=.25)
        b.quad((-w / 2, y0, 0), (-w / 2, y1, 0), (-w / 2, y1, -.2), (-w / 2, y0, -.2), 'Cloth', colour)
    for x in (-w / 2, w / 2):
        b.beam((x, -d / 2, .01), (x, d / 2, .01), .05, .04, 'Timber', WOOD)
    finish(b, .4, 4, .2)


# ---- tables, counter, bench ------------------------------------------------------------------
def planks_top(b, x0, x1, y0, y1, z0, z1, count, colour=WOOD, along='Y'):
    if along == 'Y':
        step = (x1 - x0) / count
        for i in range(count):
            b.box((x0 + i * step + .004, y0, z0), (x0 + (i + 1) * step - .004, y1, z1), 'Timber', colour, .006)
    else:
        step = (y1 - y0) / count
        for i in range(count):
            b.box((x0, y0 + i * step + .004, z0), (x1, y0 + (i + 1) * step - .004, z1), 'Timber', colour, .006)


def table_top():
    b = Builder('SM_V_Story_TableTop')
    planks_top(b, -.325, .325, -.56, .56, 0, .05, 4)
    for y in (-.5, .5):
        b.box((-.3, y - .03, -.08), (.3, y + .03, 0), 'Timber', DARK_WOOD, .006)
    finish(b)


def trestle():
    b = Builder('SM_V_Story_Trestle')
    for sx in (-1, 1):
        b.beam((sx * .05, 0, .44), (sx * .24, 0, -.44), .06, .09, 'Timber', WOOD)
    b.beam((-.17, 0, -.1), (.17, 0, -.1), .05, .07, 'Timber', WOOD)
    b.box((-.09, -.045, .36), (.09, .045, .44), 'Timber', DARK_WOOD, .006)
    finish(b)


def legged_table(name, w, d, legs_to, apron=True):
    b = Builder(name)
    planks_top(b, -w / 2, w / 2, -d / 2, d / 2, 0, .05, 4)
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.box((sx * (w / 2 - .06) - .03, sy * (d / 2 - .06) - .03, legs_to), (sx * (w / 2 - .06) + .03, sy * (d / 2 - .06) + .03, 0), 'Timber', DARK_WOOD, .005)
    if apron:
        for sy in (-1, 1):
            b.box((-w / 2 + .05, sy * (d / 2 - .06) - .015, -.1), (w / 2 - .05, sy * (d / 2 - .06) + .015, 0), 'Timber', DARK_WOOD)
        for sx in (-1, 1):
            b.box((sx * (w / 2 - .06) - .015, -d / 2 + .05, -.1), (sx * (w / 2 - .06) + .015, d / 2 - .05, 0), 'Timber', DARK_WOOD)
    return b


def side_table():
    finish(legged_table('SM_V_Story_SideTable', .70, .62, -.88))


def clerk_desk():
    b = legged_table('SM_V_Story_ClerkDesk', .60, .66, -.92)
    # Sloped rest with a lip: the prepared place for the clerk's book, and an inkwell beside it.
    b.quad((-.22, -.26, .05), (.16, -.26, .05), (.16, .2, .19), (-.22, .2, .19), 'Timber', WOOD)
    b.quad((-.22, .2, .19), (.16, .2, .19), (.16, .2, .05), (-.22, .2, .05), 'Timber', DARK_WOOD)
    b.box((-.22, -.27, .05), (.16, -.24, .085), 'Timber', DARK_WOOD)
    b.lathe((.23, -.12, .05), [(.03, 0), (.035, .05), (.02, .06), (.012, .065)], 'Iron', IRON, 8)
    finish(b)


def counter():
    """Sela's counter: planked top 0.78 x 2.10 at the old slab height, boarded front, a stock shelf."""
    b = Builder('SM_V_Story_Counter')
    w, d = .78, 2.10
    planks_top(b, -w / 2, w / 2, -d / 2, d / 2, 0, .06, 5, along='X')
    for i in range(10):
        y0 = -d / 2 + i * d / 10
        b.box((-w / 2 + .02, y0 + .004, -.9), (-w / 2 + .05, y0 + d / 10 - .004, 0), 'Timber', DARK_WOOD, .004)
    for sy in (-1, 1):
        b.box((-w / 2, sy * (d / 2 - .03) - .03, -.9), (w / 2, sy * (d / 2 - .03) + .03, 0), 'Timber', DARK_WOOD, .005)
    b.box((-w / 2 + .05, -d / 2 + .06, -.45), (w / 2 - .04, d / 2 - .06, -.41), 'Timber', WOOD, .004)
    for x, y, s in ((.05, -.7, .17), (.05, .45, .2)):
        b.box((x - s, y - s, -.41), (x + s, y + s, -.41 + s * 1.4), 'Timber', OLD, .01)
    b.lathe((.0, -.1, -.41), [(.14, 0), (.16, .18), (.1, .22)], 'Terracotta', (0, .9, 0, 0), 10)
    finish(b, 1.0)


def waiting_bench():
    b = Builder('SM_V_Story_WaitingBench')
    w, d = .43, 1.80
    planks_top(b, -w / 2, w / 2, -d / 2, d / 2, -.05, .0, 3, along='X')
    for y in (-.8, 0, .8):
        b.box((-w / 2 + .03, y - .04, -.48), (w / 2 - .03, y + .04, -.05), 'Timber', DARK_WOOD, .005)
    b.beam((-w / 2 + .05, -.85, -.3), (-w / 2 + .05, .85, -.3), .04, .05, 'Timber', DARK_WOOD)
    for y in (-.8, 0, .8):
        b.beam((w / 2 - .04, y, -.05), (w / 2 + .06, y, .38), .04, .05, 'Timber', DARK_WOOD)
    b.beam((w / 2 + .05, -.9, .35), (w / 2 + .05, .9, .35), .04, .09, 'Timber', WOOD)
    finish(b, 1.0)


# ---- small props ------------------------------------------------------------------------------
def linen_tray():
    b = Builder('SM_V_Story_LinenTray')
    w, d = .48, .50
    b.box((-w / 2, -d / 2, -.04), (w / 2, d / 2, -.025), 'Timber', WOOD, .004)
    for sx in (-1, 1):
        b.box((sx * (w / 2 - .01) - .01, -d / 2, -.04), (sx * (w / 2 - .01) + .01, d / 2, .04), 'Timber', WOOD, .004)
    for sy in (-1, 1):
        b.box((-w / 2, sy * (d / 2 - .01) - .01, -.04), (w / 2, sy * (d / 2 - .01) + .01, .04), 'Timber', WOOD, .004)
    for i in range(3):
        z = -.025 + i * .04
        b.box((-.19 + i * .01, -.2 + i * .012, z), (.19 - i * .012, .2 - i * .01, z + .04), 'Cloth', LINEN, .012)
    b.beam((-.17, -.21, .095), (.17, -.21, .095), .02, .006, 'Cloth', (.2, .4, .42, 0))
    finish(b, .4, 4, .3)


def cup():
    b = Builder('SM_V_Story_Cup')
    b.lathe((0, 0, -.085), [(.05, 0), (.062, .04), (.065, .12), (.06, .16), (.055, .17), (.05, .17), (.045, .03)], 'Terracotta', (0, .95, 0, 0), 12)
    finish(b, .2, 4, .2)


def jug():
    b = Builder('SM_V_Story_Jug')
    b.lathe((0, 0, -.17), [(.06, 0), (.09, .06), (.095, .16), (.07, .26), (.05, .3), (.058, .34), (.045, .34), (.04, .31)], 'Terracotta', (0, .95, 0, 0), 12)
    b.beam((.07, 0, .07), (.13, 0, .02), .025, .02, 'Terracotta', (0, .9, 0, 0))
    b.beam((.13, 0, .02), (.13, 0, -.08), .025, .02, 'Terracotta', (0, .9, 0, 0))
    b.beam((.13, 0, -.08), (.085, 0, -.11), .025, .02, 'Terracotta', (0, .9, 0, 0))
    finish(b, .2, 4, .2)


def fixing():
    """Awning fixing: brass cleat on a back plate with a ring, 0.15 x 0.18 x 0.22 m."""
    b = Builder('SM_V_Story_Fixing')
    b.box((-.075, -.09, -.11), (.075, .09, -.09), 'Iron', IRON, .004)
    b.box((-.03, -.04, -.09), (.03, .04, .0), 'Iron', IRON, .006)
    b.lathe((0, 0, .0), [(.02, 0), (.022, .03), (.012, .035)], 'Iron', IRON, 8)
    ring = []
    for i in range(12):
        t = i * math.tau / 12
        ring.append((.055 * math.cos(t), 0, .055 + .055 * math.sin(t)))
    for i in range(12):
        b.cylinder(ring[i], ring[(i + 1) % 12], .009, .009, 'Iron', IRON, 5, caps=False)
    finish(b, .2, 4, .2)


def strap():
    b = Builder('SM_V_Story_Strap')
    length = 1.23
    b.cylinder((-length / 2, 0, 0), (length / 2, 0, 0), .014, .014, 'Cloth', (.5, .46, .36, 0), 6)
    for x in (-.4, .1, .45):
        b.lathe((x, 0, 0), [(.014, 0), (.024, .03), (.014, .06)], 'Cloth', (.46, .42, .33, 0), 6)
    finish(b, .1, 2, 0)


def linen_parcel():
    b = Builder('SM_V_Story_LinenParcel')
    b.box((-.195, -.225, -.105), (.195, .225, .105), 'Cloth', LINEN, .03)
    b.box((-.2, -.05, -.11), (.2, .05, .11), 'Paint', (0, .9, 0, 0), .004)
    b.box((-.2, .05, -.02), (.2, .07, .02), 'Paint', (0, .9, 0, 0))
    b.quad((.12, -.2, .106), (.22, -.2, .106), (.22, -.12, .106), (.12, -.12, .106), 'Cloth', PAPER)
    finish(b, .3, 4, .2)


def canvas_roll():
    """The one reinforced canvas: folded heavy tarp, brass eyelets, two straps."""
    b = Builder('SM_V_Story_CanvasRoll')
    b.box((-.21, -.235, -.09), (.21, .235, .09), 'Cloth', TARP, .035)
    for i in range(3):
        z = -.09 + .06 * i + .03
        b.box((-.215, -.235, z - .006), (.215, .235, z + .006), 'Cloth', (.24, .33, .31, 0))
    for x in (-.14, .14):
        for y in (-.19, .19):
            b.lathe((x, y, .09), [(.02, 0), (.022, .01), (.009, .012)], 'Iron', IRON, 8)
    for y in (-.1, .1):
        b.box((-.22, y - .02, -.1), (.22, y + .02, .1), 'Cloth', (.3, .24, .18, 0), .006)
        b.box((.17, y - .025, .1), (.21, y + .025, .115), 'Iron', IRON)
    finish(b, .3, 4, .2)


def fasteners():
    b = Builder('SM_V_Story_Fasteners')
    b.box((-.04, -.18, -.012), (.04, .18, .0), 'Cloth', (.3, .24, .18, 0), .004)
    for y in (-.12, 0, .12):
        b.box((-.045, y - .025, 0), (.045, y + .025, .02), 'Iron', IRON, .003)
        b.box((-.01, y - .018, .02), (.01, y + .018, .035), 'Iron', IRON)
    finish(b, .1, 2, 0)


def luggage():
    b = Builder('SM_V_Story_Luggage')
    b.box((-.3, -.2, 0), (.3, .2, .34), 'Timber', (0, .8, .05, 0), .02)
    for z in (.08, .26):
        b.box((-.305, -.205, z), (.305, .205, z + .03), 'Timber', DARK_WOOD, .004)
    for y in (-.12, .12):
        b.box((-.31, y - .02, -.0), (.31, y + .02, .345), 'Cloth', (.3, .24, .18, 0), .004)
    b.beam((-.08, 0, .34), (.08, 0, .34), .025, .03, 'Iron', IRON)
    b.lathe((.38, .22, 0), [(.08, 0), (.18, .1), (.17, .26), (.08, .34), (.04, .36)], 'Cloth', (.55, .5, .4, .02), 10)
    b.box((.42, -.14, 0), (.66, .1, .22), 'Cloth', (.4, .36, .3, .02), .03)
    finish(b, .4, 4, .2)


def notice_board():
    b = Builder('SM_V_Story_NoticeBoard')
    for y in (-.55, .55):
        b.box((-.04, y - .04, 0), (.04, y + .04, 1.95), 'Timber', WOOD, .008)
    b.box((-.03, -.62, 1.0), (.03, .62, 1.9), 'Timber', DARK_WOOD, .006)
    for y0, y1, z0, z1 in ((-.52, -.2, 1.25, 1.75), (-.14, .22, 1.3, 1.7), (.26, .55, 1.15, 1.6)):
        sheet_x(b, .035, y0, y1, z0, z1, 'Cloth', PAPER, False)
        for k in range(4):
            z = z1 - .08 - k * .09
            b.quad((.037, y1 - .03, z), (.037, y0 + .03, z), (.037, y0 + .03, z - .015), (.037, y1 - .03, z - .015), 'Flat', (0, .5, 0, 0))
    b.box((-.05, -.66, 1.9), (.05, .66, 1.96), 'Timber', DARK_WOOD, .008)
    finish(b, .6, 6, .4)


def shelf():
    """Clinic wall shelf with jars; back face at y = 0, shelf extends toward -Y, base at z = 0."""
    b = Builder('SM_V_Story_Shelf')
    b.box((-.45, -.26, 0), (.45, 0, .035), 'Timber', WOOD, .006)
    for x in (-.36, .36):
        b.beam((x, -.02, -.01), (x, -.24, -.2), .03, .04, 'Timber', DARK_WOOD)
        b.beam((x, -.02, -.22), (x, -.02, .0), .03, .04, 'Timber', DARK_WOOD)
    for i, (x, r, h) in enumerate(((-.33, .05, .18), (-.18, .06, .14), (-.03, .045, .2), (.12, .055, .12), (.3, .07, .16))):
        tone = (0, .95, 0, 0) if i % 2 == 0 else (0, .8, 0, 0)
        b.lathe((x, -.13, .035), [(r * .8, 0), (r, h * .3), (r, h * .8), (r * .7, h), (r * .55, h + .02)], 'Terracotta' if i != 2 else 'Glass', tone if i != 2 else (0, 1, 0, 0), 10)
    b.box((-.1, -.22, .035), (.06, -.08, .11), 'Cloth', LINEN, .015)
    finish(b, .4, 4, .3)


def stock():
    """Simple shop stock: two bolts of cloth and a basket of parcels, base at z = 0."""
    b = Builder('SM_V_Story_Stock')
    for i, colour in enumerate((TEAL_CLOTH, CREAM_CLOTH)):
        y = -.12 + i * .22
        b.lathe((0, y, 0), [(.07, 0), (.08, .02), (.08, .4), (.07, .42), (.04, .42), (.04, 0)], 'Cloth', colour, 10)
    b.lathe((.22, .05, 0), [(.12, 0), (.16, .08), (.17, .2), (.16, .24), (.14, .24), (.13, .2)], 'Timber', (0, .78, 0, 0), 10)
    for x, y, s in ((.2, .02, .05), (.25, .08, .04)):
        b.box((x - s, y - s, .14), (x + s, y + s, .14 + s * 1.3), 'Cloth', LINEN, .01)
    finish(b, .3, 4, .2)


# ---- memorial, chronology ------------------------------------------------------------------
def display_case():
    """Civic display case for the memorial: weathered iron frame, timber back, two glazed mounts,
    a stone plaque strip, iron legs to the ground. 1.78 wide, 1.08 tall, pivot at the old slab centre."""
    b = Builder('SM_V_Story_DisplayCase')
    w, h = 1.78, 1.08
    x_back, x_glass = -.035, .098
    b.box((x_back, -w / 2 + .03, -h / 2 + .03), (x_back + .03, w / 2 - .03, h / 2 - .03), 'Timber', (0, .6, .06, 0), .004)
    for z in (-h / 2, h / 2 - .04):
        b.box((x_back - .005, -w / 2, z), (x_glass + .012, w / 2, z + .04), 'Iron', IRON, .006)
    for y in (-w / 2, w / 2 - .04, -.03, -.01):
        b.box((x_back - .005, y, -h / 2), (x_glass + .012, y + .04 if y < 0 or y > .5 else y + .02, h / 2), 'Iron', IRON, .006)
    for cy in (-.41, .41):
        # Dark lined recess behind each mount, glass in front.
        sheet_x(b, x_back + .031, cy - .355, cy + .355, -.415, .415, 'Flat', (0, .35, 0, 0), False)
        b.box((x_glass, cy - .36, -.42), (x_glass + .008, cy + .36, .42), 'Glass', (0, 1, 0, 0))
        for y in (cy - .36, cy + .33):
            b.box((x_glass - .01, y, -.44), (x_glass + .01, y + .03, .44), 'Iron', IRON)
    b.box((x_glass - .01, -.78, -h / 2 + .04), (x_glass + .006, .78, -h / 2 + .09), 'Masonry', STONE, .004)
    for i in range(6):
        b.quad((x_glass + .007, .7 - i * .26, -h / 2 + .075), (x_glass + .007, .5 - i * .26, -h / 2 + .075), (x_glass + .007, .5 - i * .26, -h / 2 + .06), (x_glass + .007, .7 - i * .26, -h / 2 + .06), 'Flat', (0, .4, 0, 0))
    for y in (-.75, .75):
        b.box((-.025, y - .03, -1.49), (.035, y + .03, -h / 2), 'Iron', IRON, .006)
        b.box((-.06, y - .08, -1.49), (.07, y + .08, -1.46), 'Iron', IRON, .005)
    b.box((-.025, -.78, -.8), (.035, .78, -.74), 'Iron', IRON, .005)
    finish(b, .8, 6, .4)


def record_page():
    """Preserved page behind the memorial glass: faces +X toward the reader (one-sided register
    material), image u toward +Y (the reader's right), v down, a slight bulge off the back board."""
    b = Builder('SM_V_Story_RecordPage')
    w, h = .63, .73
    rows, cols = 4, 2
    for i in range(cols):
        for j in range(rows):
            def p(u, v):
                return (.006 * math.sin(v * math.pi) * (1 - u), -w / 2 + u * w, h / 2 - v * h)
            u0, u1, v0, v1 = i / cols, (i + 1) / cols, j / rows, (j + 1) / rows
            ids = [b.vertex(p(u0, v1), PAPER), b.vertex(p(u1, v1), PAPER), b.vertex(p(u1, v0), PAPER), b.vertex(p(u0, v0), PAPER)]
            b.face(ids, 'Banner', [ue(u0, v1), ue(u1, v1), ue(u1, v0), ue(u0, v0)])
    finish(b, .1, 2, 0)


def notice_case():
    """Public chronology: iron-and-glass notice case 1.10 wide, 1.20 tall, legs to the ground 1.30 below."""
    b = Builder('SM_V_Story_NoticeCase')
    w, h = 1.10, 1.20
    x_back, x_glass = -.05, .045
    b.box((x_back, -w / 2 + .02, -h / 2 + .02), (x_back + .025, w / 2 - .02, h / 2 - .02), 'Timber', (0, .62, .05, 0), .004)
    for z in (-h / 2, h / 2 - .035):
        b.box((x_back - .004, -w / 2, z), (x_glass + .01, w / 2, z + .035), 'Iron', IRON, .005)
    for y in (-w / 2, w / 2 - .035):
        b.box((x_back - .004, y, -h / 2), (x_glass + .01, y + .035, h / 2), 'Iron', IRON, .005)
    b.box((x_back - .004, -.012, -h / 2), (x_glass + .01, .012, h / 2), 'Iron', IRON, .004)
    for cy, z0, z1 in ((-.27, -.5, .5), (.27, -.5, .05), (.27, .12, .5)):
        sheet_x(b, x_back + .026, cy - .22, cy + .22, z0, z1, 'Cloth', PAPER, False)
        k = 0
        z = z1 - .07
        while z > z0 + .05:
            b.quad((x_back + .028, cy + .18, z), (x_back + .028, cy - .18 + (.1 if k % 3 == 2 else 0), z), (x_back + .028, cy - .18 + (.1 if k % 3 == 2 else 0), z - .012), (x_back + .028, cy + .18, z - .012), 'Flat', (0, .45, 0, 0))
            z -= .04
            k += 1
    b.box((x_glass, -w / 2 + .03, -h / 2 + .03), (x_glass + .006, w / 2 - .03, h / 2 - .03), 'Glass', (0, 1, 0, 0))
    for y in (-.42, .42):
        b.box((-.02, y - .025, -1.30), (.02, y + .025, -h / 2), 'Iron', IRON, .005)
        b.box((-.05, y - .07, -1.30), (.05, y + .07, -1.275), 'Iron', IRON, .004)
    b.box((-.02, -.45, -.85), (.02, .45, -.8), 'Iron', IRON, .004)
    finish(b, .8, 6, .4)


# ---- gate and home ---------------------------------------------------------------------------
def photo_frame():
    b = Builder('SM_V_Story_PhotoFrame')
    w, h = .32, .25
    b.box((-.015, -w / 2, -h / 2), (.0, w / 2, h / 2), 'Timber', (0, .7, .03, 0), .003)
    for y in (-w / 2, w / 2 - .022):
        b.box((-.015, y, -h / 2), (.015, y + .022, h / 2), 'Timber', (0, .85, 0, 0), .004)
    for z in (-h / 2, h / 2 - .022):
        b.box((-.015, -w / 2, z), (.015, w / 2, z + .022), 'Timber', (0, .85, 0, 0), .004)
    sheet_x(b, .004, -w / 2 + .022, w / 2 - .022, -h / 2 + .022, h / 2 - .022, 'Banner', PAPER)
    b.beam((-.012, 0, .02), (-.11, 0, -h / 2), .02, .012, 'Timber', (0, .8, 0, 0))
    finish(b, .2, 4, .2)


def letter():
    b = Builder('SM_V_Story_Letter')
    w, d = .31, .22
    cols, rows = 4, 3
    for i in range(cols):
        for j in range(rows):
            def p(u, v):
                x, y = -w / 2 + u * w, -d / 2 + v * d
                lift = .012 * max(0.0, (u - .7) / .3) ** 2 * (1 - v)
                return (x, y, lift)
            u0, u1, v0, v1 = i / cols, (i + 1) / cols, j / rows, (j + 1) / rows
            ids = [b.vertex(p(u0, v0), PAPER), b.vertex(p(u1, v0), PAPER), b.vertex(p(u1, v1), PAPER), b.vertex(p(u0, v1), PAPER)]
            # Read from the table's east side looking west: the top of the page is the west edge and
            # the reader's right is +Y, so image u follows +Y and image v follows +X.
            b.face(ids, 'Banner', [ue(v0, u0), ue(v0, u1), ue(v1, u1), ue(v1, u0)])
    finish(b, .1, 2, 0)


def chronowatch():
    """The Chronowatch on the bench: brass case, dial, hands, two straps. Slots Iron / Flat / Paint / Timber."""
    b = Builder('SM_V_Story_Chronowatch')
    b.lathe((0, 0, -.02), [(.11, 0), (.14, .008), (.14, .03), (.13, .04), (.12, .04)], 'Iron', IRON, 20)
    b.lathe((0, 0, .02), [(.0, 0), (.12, 0), (.12, .004), (.0, .004)], 'Flat', (0, 1, 0, 0), 20)
    for i in range(12):
        t = i * math.tau / 12
        b.box((.095 * math.cos(t) - .006, .095 * math.sin(t) - .006, .024), (.095 * math.cos(t) + .006, .095 * math.sin(t) + .006, .03), 'Paint', (0, 1, 0, 0))
    b.beam((0, 0, .028), (.08 * math.cos(1.0), .08 * math.sin(1.0), .028), .008, .006, 'Paint', (0, 1, 0, 0))
    b.beam((0, 0, .03), (.055 * math.cos(2.6), .055 * math.sin(2.6), .03), .012, .006, 'Paint', (0, 1, 0, 0))
    b.lathe((0, 0, .024), [(.012, 0), (.012, .012), (.0, .012)], 'Iron', IRON, 8)
    b.cylinder((.14, 0, .0), (.17, 0, .0), .018, .016, 'Iron', IRON, 8)
    for sy in (-1, 1):
        b.box((-.06, sy * .14, -.015), (.06, sy * .37, .005), 'Timber', (0, .7, .05, 0), .006)
        b.box((-.055, sy * .3, .005), (.055, sy * .36, .012), 'Iron', IRON, .003)
    finish(b, .2, 4, .2)


def dish():
    b = Builder('SM_V_Story_Dish')
    b.box((-.2, -.2, -.02), (.2, .2, .0), 'Flat', (0, 1, 0, 0), .006)
    for sx in (-1, 1):
        b.box((sx * .2 - .015, -.2, .0), (sx * .2 + .015, .2, .055), 'Flat', (0, .9, 0, 0), .006)
    for sy in (-1, 1):
        b.box((-.2, sy * .2 - .015, .0), (.2, sy * .2 + .015, .055), 'Flat', (0, .9, 0, 0), .006)
    finish(b, .2, 4, .2)


def contact():
    b = Builder('SM_V_Story_Contact')
    b.box((-.035, -.055, -.006), (.035, .055, .0), 'Iron', IRON, .003)
    for y in (-.03, .03):
        b.cylinder((0, y, 0), (0, y, .012), .006, .005, 'Iron', IRON, 6)
    finish(b, .1, 2, 0)


def anchor_stone():
    b = Builder('SM_V_Story_AnchorStone')
    b.lathe((0, 0, -.15), [(.19, 0), (.225, .04), (.225, .22), (.21, .26), (.2, .3), (.0, .3)], 'Masonry', STONE, 16)
    finish(b, .3, 4, .3)


def anchor_dial():
    b = Builder('SM_V_Story_AnchorDial')
    b.lathe((0, 0, -.02), [(.0, 0), (.175, 0), (.175, .035), (.16, .04), (.0, .04)], 'Iron', IRON, 20)
    for i in range(24):
        t = i * math.tau / 24
        long_tick = i % 6 == 0
        r0 = .15 if not long_tick else .11
        b.beam((r0 * math.cos(t), r0 * math.sin(t), .021), (.165 * math.cos(t), .165 * math.sin(t), .021), .006, .004, 'Flat', (0, .3, 0, 0))
    b.lathe((0, 0, .02), [(.03, 0), (.03, .015), (.0, .015)], 'Iron', IRON, 10)
    finish(b, .2, 4, .2)


def plank_door():
    """Closed plank door, 1.14 wide (Y) x 2.24 tall, 0.14 deep; hinges on the iron straps."""
    b = Builder('SM_V_Story_PlankDoor')
    w, h = 1.14, 2.24
    for y in (-w / 2, w / 2 - .07):
        b.box((-.07, y, -h / 2), (.07, y + .07, h / 2), 'Timber', DARK_WOOD, .006)
    b.box((-.07, -w / 2, h / 2 - .08), (.07, w / 2, h / 2), 'Timber', DARK_WOOD, .006)
    planks = 6
    inner = w - .14
    # A solid backing board sits behind the planks and shows only as the dark seams between them. This
    # mesh is a collision barrier (complex-as-simple) and the harness's visibility query runs down its
    # vertical centre line, so no seam may be open all the way through.
    b.box((-.045, -w / 2 + .07, -h / 2 + .01), (-.03, w / 2 - .07, h / 2 - .08), 'Timber', DARK_WOOD, .004)
    for i in range(planks):
        y0 = -w / 2 + .07 + i * inner / planks
        b.box((-.03, y0 + .003, -h / 2 + .01), (.03, y0 + inner / planks - .003, h / 2 - .08), 'Paint', (0, .92, 0, 0), .004)
    for z in (-.6, .45):
        b.box((.03, -w / 2 + .09, z - .03), (.05, .2, z + .03), 'Iron', IRON, .003)
    b.lathe((.03, w / 2 - .24, -.05), [(.02, 0), (.035, .03), (.03, .06)], 'Iron', IRON, 8)
    finish(b, .5, 6, .4)


def plaster_panel():
    b = Builder('SM_V_Story_PlasterPanel')
    b.box((-.085, -.5, -.5), (.085, .5, .5), 'Masonry', PLASTER, 0)
    finish(b, .1, 2, 0)


def wing_roof():
    """Past-era roof over the home's wing: 4.23 m slope (X) x 7.18 m (Y) corrugated tile with rafters."""
    b = Builder('SM_V_Story_WingRoof')
    sx, sy = 4.23 / 2, 7.18 / 2
    tile_plane(b, (sx, -sy, 0), (sx, sy, 0), (-sx, sy, 0), (-sx, -sy, 0), 20, 5, height=.09)
    for i in range(7):
        y = -sy + .3 + i * (sy * 2 - .6) / 6
        b.beam((-sx + .1, y, -.09), (sx - .1, y, -.09), .08, .12, 'Timber', WOOD)
    b.beam((sx - .2, -sy, -.1), (sx - .2, sy, -.1), .12, .12, 'Timber', WOOD)
    finish(b, .6, 4, .3)


# ---- kit module: the clinic's open entrance ------------------------------------------------
BW, HG, T, BASE = 2.5, 3.6, .45, -2.6


def smooth(a, b_, x):
    t = max(0.0, min(1.0, (x - a) / (b_ - a)))
    return t * t * (3 - 2 * t)


def painter(ground, seed, height):
    def paint(x, z):
        n = field(x + seed * 3.1, z + seed, .42, 11)
        cover = 1.0
        if ground:
            cover *= smooth(.72, 1.08, z + (n - .5) * .5)
        cover *= .86 + .14 * smooth(0, 1.6, z)
        return (cover, 1, 0, 0)
    return paint


def door_open():
    b = Builder('SM_V_Story_DoorOpen_R')
    seed = 23
    cx, hw, spring = BW / 2, .72, 2.08
    opening = [(cx - hw, .04), (cx + hw, .04)] + [p for p in arch_points(cx, spring, hw, .62, 12)]
    b.wall([(0, BASE), (BW, BASE), (BW, HG), (0, HG)], [opening], T, paint=painter(True, seed, HG), reveal=lambda x, z: (.92, .55, 0, 0))
    b.box((0, -.07, BASE), (BW, .02, .62), 'Masonry', STONE, 0)
    b.box((0, -.09, .62), (BW, .02, .74), 'Masonry', STONE, .022)
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
    # Dim interior behind the opening: floor, back wall, a bench and a lamp glow at the far wall.
    depth = 2.6
    b.quad((cx - hw - .4, T, .05), (cx - hw - .4, depth, .05), (cx + hw + .4, depth, .05), (cx + hw + .4, T, .05), 'Masonry', (0, .45, 0, 0))
    dim = (.85, .3, 0, 0)
    b.quad((cx + hw + .4, depth, .05), (cx - hw - .4, depth, .05), (cx - hw - .4, depth, 3.0), (cx + hw + .4, depth, 3.0), 'Masonry', dim)
    b.quad((cx - hw - .4, T, .05), (cx - hw - .4, T, 3.0), (cx - hw - .4, depth, 3.0), (cx - hw - .4, depth, .05), 'Masonry', dim)
    b.quad((cx + hw + .4, T, .05), (cx + hw + .4, depth, .05), (cx + hw + .4, depth, 3.0), (cx + hw + .4, T, 3.0), 'Masonry', dim)
    b.quad((cx - hw - .4, T, 3.0), (cx + hw + .4, T, 3.0), (cx + hw + .4, depth, 3.0), (cx - hw - .4, depth, 3.0), 'Timber', (0, .25, 0, 0))
    b.box((cx - .6, depth - .5, .05), (cx + .6, depth - .1, .48), 'Timber', (0, .55, 0, 0), .01)
    b.quad((cx - .2, depth - .02, 1.5), (cx + .2, depth - .02, 1.5), (cx + .2, depth - .02, 1.9), (cx - .2, depth - .02, 1.9), 'Flat', (.6, 1, 0, 0))
    # The door leaf swung 72 degrees into the room on its left jamb.
    angle = math.radians(72)
    hx, hy = cx - hw + .02, .3
    place = lambda p: (hx + p[0] * math.cos(angle) - p[1] * math.sin(angle), hy + p[0] * math.sin(angle) + p[1] * math.cos(angle), p[2])
    leaf = [(0, .05), (hw * 2 - .03, .05)] + [((hw - .015) + (hw - .015) * math.cos(t), spring + .61 * math.sin(t)) for t in [math.pi * i / 12 for i in range(13)]]
    tone = (0, .96, 0, 0)
    b.wall(leaf, (), .05, 'Paint', paint=lambda x, z: tone, reveal=lambda x, z: tone, spacing=9, y=0, axis_map=place)
    for i in range(1, 7):
        x = i * hw * 2 / 7
        b.box((x - .006, .05, .1), (x + .006, .07, spring + .4), 'Timber', (0, .55, 0, 0)) if False else None
    for z in (.5, 1.75):
        q = [place((x, y, z + dz)) for x, y, dz in ((.02, -.01, -.03), (hw + .25, -.01, -.03), (hw + .25, -.01, .03), (.02, -.01, .03))]
        b.quad(*q, 'Iron', IRON)
    finish(b, 2.0, 14, .9)


post('SM_V_Story_AwningPost', .10, 2.44)
post('SM_V_Story_GatePost', .18, 2.38, cap='pyramid')
post_stub()
beam('SM_V_Story_Beam', 1.0, .16, .16)
beam('SM_V_Story_BeamY', 1.0, .16, .16, axis='Y')
ruin_frame()
canvas_cover()
shade()
table_top()
trestle()
side_table()
clerk_desk()
counter()
waiting_bench()
linen_tray()
cup()
jug()
fixing()
strap()
linen_parcel()
canvas_roll()
fasteners()
luggage()
notice_board()
shelf()
stock()
display_case()
record_page()
notice_case()
photo_frame()
letter()
chronowatch()
dish()
contact()
anchor_stone()
anchor_dial()
plank_door()
plaster_panel()
wing_roof()
door_open()

path = OUT / 'kit_manifest.json'
existing = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
existing.update(manifest)
path.write_text(json.dumps(existing, indent=2), encoding='utf-8')
(OUT / 'story_props_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('STORY PROPS', len(manifest), 'triangles', sum(m['triangles'] for m in manifest.values()), flush=True)
