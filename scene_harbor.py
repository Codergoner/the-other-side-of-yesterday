"""Editable harbor, small craft, and street-market geometry.

Pixel coordinates refer to the 1672 x 941 reference camera.  The module is
deliberately additive: importing it never changes the scene, and add_harbor
only creates named objects inside its own collections.
"""

import math

import bpy
from mathutils import Vector


def add_harbor(api):
    get = api.get if isinstance(api, dict) else lambda key, default=None: getattr(api, key, default)
    world = get("world")
    box = get("box")
    mesh = get("mesh")
    beam = get("beam")
    mat = get("mat")
    collection = get("collection")
    set_collection = get("set_collection")
    project = get("project_object")
    source = get("projection_mat")
    materials = get("materials", {})
    wood = materials["wood"]
    metal = materials["metal"]
    dark = materials["dark"]
    fabric = materials["fabric"]

    ochre = mat("Harbor | terracotta", (0.44, 0.155, 0.074, 1), roughness=0.91)
    orange = mat("Harbor | golden fruit", (0.91, 0.40, 0.045, 1), roughness=0.63)
    red = mat("Harbor | red fruit", (0.55, 0.065, 0.035, 1), roughness=0.59)
    green = mat("Harbor | olive green fruit", (0.24, 0.34, 0.08, 1), roughness=0.69)
    rope_mat = mat("Harbor | flax rope", (0.42, 0.34, 0.21, 1), roughness=0.92)
    sail_mat = mat("Harbor | weathered cream sail", (0.75, 0.70, 0.57, 1), roughness=0.94)
    blue = mat("Harbor | faded blue canvas", (0.19, 0.31, 0.36, 1), roughness=0.94)

    created = []

    def finished(obj):
        if obj is not None:
            project(obj)
            created.append(obj)
        return obj

    def point(p, d):
        return Vector(world(p[0], p[1], d))

    def panel(name, pixels, d, material=source):
        return finished(mesh(name, [point(p, d) for p in pixels], [tuple(range(len(pixels)))], material))

    def solid_panel(name, pixels, d, thickness, material=source):
        front = [point(p, d) for p in pixels]
        back = [v + Vector((0, thickness, 0)) for v in front]
        n = len(front)
        faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, n * 2))]
        faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
        return finished(mesh(name, front + back, faces, material))

    def stroke(name, pixels, d, radius_px=0.8, material=wood):
        radius = radius_px * d / 1550
        for i, (a, b) in enumerate(zip(pixels, pixels[1:])):
            finished(beam(name + " %02d" % (i + 1), point(a, d), point(b, d), radius, material))

    def pbox(name, uv, d, size, material=wood, bevel=0.01):
        s = d / 1550
        return finished(box(name, point(uv, d), (size[0] * s, size[2] * s, size[1] * s), material, bevel=bevel))

    def rope(name, pixels, d, radius_px=0.38):
        stroke(name, pixels, d, radius_px, rope_mat)

    def rope_sag(name, a, b, d, sag=5, radius_px=0.4):
        pixels = []
        for i in range(13):
            t = i / 12
            pixels.append((a[0] * (1 - t) + b[0] * t,
                           a[1] * (1 - t) + b[1] * t + 4 * sag * t * (1 - t)))
        rope(name, pixels, d, radius_px)

    def ring_body(name, uv, d, rings, material, segments=16, cap=True):
        """Lathed vessel; ring pairs are (height in px, radius in px)."""
        scale = d / 1550
        base = point(uv, d)
        verts = []
        for z, r in rings:
            for j in range(segments):
                t = 2 * math.pi * j / segments
                verts.append(base + Vector((r * scale * math.cos(t), r * scale * math.sin(t), z * scale)))
        faces = []
        for row in range(len(rings) - 1):
            for j in range(segments):
                a = row * segments + j
                b = row * segments + (j + 1) % segments
                faces.append((a, b, b + segments, a + segments))
        if cap:
            faces += [tuple(range(segments - 1, -1, -1)),
                      tuple(range((len(rings) - 1) * segments, len(rings) * segments))]
        return finished(mesh(name, verts, faces, material))

    def barrel(name, uv, d, height=24, radius=9):
        rings = [(0, radius * .77), (height * .12, radius * .9),
                 (height * .45, radius), (height * .62, radius),
                 (height * .90, radius * .9), (height, radius * .78)]
        obj = ring_body(name + " oak staves", uv, d, rings, wood)
        for i, h in enumerate((height * .15, height * .79)):
            r = radius * .93
            ring_body(name + " iron hoop %d" % (i + 1), uv, d,
                      [(h, r), (h + height * .07, r)], metal, cap=False)
        base = point(uv, d)
        s = d / 1550
        for i in range(8):
            a = 2 * math.pi * i / 8
            start = base + Vector((radius * .8 * s * math.cos(a), radius * .8 * s * math.sin(a), 0))
            end = base + Vector((radius * .8 * s * math.cos(a), radius * .8 * s * math.sin(a), height * s))
            finished(beam(name + " stave seam %02d" % i, start, end, .11 * s, dark))
        return obj

    def crate(name, uv, d, width=26, height=20, depth=19, material=wood):
        obj = pbox(name + " body", uv, d, (width, height, depth), material)
        x, y = uv
        for j in range(4):
            yy = y - height / 2 + height * (j + .5) / 4
            stroke(name + " plank seam %d" % j, [(x - width / 2, yy), (x + width / 2, yy)], d - .02, .22, dark)
        stroke(name + " diagonal brace", [(x - width * .44, y + height * .43),
                                          (x + width * .44, y - height * .43)], d - .04, 1.2, wood)
        return obj

    def pot(name, uv, d, height=24, radius=10):
        rings = [(0, radius * .5), (height * .14, radius * .74),
                 (height * .42, radius), (height * .68, radius * .92),
                 (height * .88, radius * .53), (height, radius * .57),
                 (height * 1.04, radius * .66), (height * 1.07, radius * .66)]
        obj = ring_body(name + " clay body", uv, d, rings, ochre, cap=False)
        ring_body(name + " dark opening", (uv[0], uv[1] - height * .99), d,
                  [(0, radius * .49)], dark)
        return obj

    def fruit(name, uv, d, r, material):
        base = point(uv, d)
        scale = r * d / 1550
        verts = [base + Vector((0, 0, -scale))]
        for row in range(1, 5):
            phi = math.pi * row / 5
            for col in range(8):
                t = 2 * math.pi * col / 8
                verts.append(base + Vector((math.sin(phi) * math.cos(t),
                                            math.sin(phi) * math.sin(t), -math.cos(phi))) * scale)
        verts.append(base + Vector((0, 0, scale)))
        faces = [(0, 1 + (j + 1) % 8, 1 + j) for j in range(8)]
        for row in range(3):
            for j in range(8):
                a = 1 + row * 8 + j
                b = 1 + row * 8 + (j + 1) % 8
                faces.append((a, b, b + 8, a + 8))
        faces += [(33, 25 + j, 25 + (j + 1) % 8) for j in range(8)]
        return finished(mesh(name, verts, faces, material))

    set_collection(collection("Harbor | docks and mooring"))

    def dock(name, corners, d, board_count=13):
        solid_panel(name + " timber deck", corners, d, .18 * d / 38, wood)
        a, b, c, e = [Vector(p) for p in corners]
        for i in range(1, board_count):
            t = i / board_count
            p = a.lerp(b, t)
            q = e.lerp(c, t)
            stroke(name + " board seam %02d" % i, [p, q], d - .018, .27, dark)
        stroke(name + " fascia", [corners[3], corners[2]], d - .02, 2.3, wood)
        for i, p in enumerate((corners[0], corners[1], corners[2], corners[3])):
            px, py = p
            stroke(name + " mooring pile %d" % (i + 1), [(px, py - 12), (px, py + 25)], d - .035, 2.2, wood)
            stroke(name + " pile cap %d" % (i + 1), [(px - 2.5, py - 12), (px + 2.5, py - 12)], d - .06, 1, wood)

    dock("Near quay", [(1170, 673), (1398, 677), (1430, 704), (1180, 697)], 38, 24)
    dock("Middle landing", [(1175, 505), (1487, 506), (1510, 520), (1179, 520)], 87, 30)
    dock("Right landing finger", [(1501, 512), (1527, 510), (1559, 583), (1535, 587)], 70, 7)
    dock("Foreground pier finger", [(1235, 692), (1264, 697), (1255, 782), (1225, 774)], 32, 6)
    rope_sag("Near quay safety rope", (1170, 661), (1398, 665), 37.8, 9, .5)
    rope_sag("Middle landing rope", (1175, 494), (1487, 495), 86.8, 4, .4)
    for i, (uv, d, h, r) in enumerate([((1213, 688), 37.6, 23, 8), ((1228, 688), 37.5, 18, 7),
                                     ((1376, 690), 37.7, 16, 6), ((1194, 510), 86.8, 10, 4),
                                     ((1482, 515), 86.8, 10, 4)]):
        barrel("Dock cargo barrel %02d" % (i + 1), uv, d, h, r)
    crate("Near quay shipping crate", (1288, 687), 37.6, 24, 17, 18)
    crate("Middle landing crate", (1213, 507), 86.6, 11, 9, 10)

    set_collection(collection("Harbor | sailing boats"))

    def sailboat(name, cx, cy, topx, topy, d, hull_width, hull_height, sail_width):
        left = cx - hull_width * .53
        right = cx + hull_width * .47
        hull = [(left, cy - hull_height * .42), (cx - hull_width * .30, cy - hull_height * .19),
                (right, cy - hull_height * .34), (right - hull_width * .10, cy + hull_height * .30),
                (cx - hull_width * .31, cy + hull_height * .45)]
        solid_panel(name + " painted wooden hull", hull, d, hull_width * d / 1550 * .19, wood)
        panel(name + " open cockpit", [(left + hull_width * .15, cy - hull_height * .37),
                                       (right - hull_width * .13, cy - hull_height * .37),
                                       (right - hull_width * .19, cy - hull_height * .08),
                                       (left + hull_width * .25, cy - hull_height * .05)], d - .04, dark)
        stroke(name + " gunwale", [hull[0], hull[1], hull[2]], d - .06, .85, wood)
        mast_base = (topx + 3, cy - hull_height * .19)
        mast_peak = (topx, topy)
        stroke(name + " main mast", [mast_base, (topx - .4, topy - 3)], d - .12, .8, wood)
        sail_foot = cy - hull_height * .65
        left_foot = (topx - sail_width * .78, sail_foot)
        right_foot = (topx + sail_width * .36, sail_foot - 1)
        # Separate sail meshes remain independently editable and can be re-lit.
        panel(name + " broad triangular mainsail", [(topx - 1.3, topy + 3),
                                                     (topx - 2, sail_foot - 1), left_foot], d - .18, sail_mat)
        panel(name + " narrow foresail", [(topx + 2, topy + 11), right_foot,
                                          (topx + 4, sail_foot - 1)], d - .15, sail_mat)
        stroke(name + " wooden boom", [left_foot, (topx + 6, sail_foot)], d - .22, .66, wood)
        rope(name + " port shroud", [mast_peak, (left + 5, cy - hull_height * .29)], d - .24, .29)
        rope(name + " starboard shroud", [mast_peak, (right - 7, cy - hull_height * .27)], d - .23, .27)
        rope(name + " mainsail leech", [(topx - 1.3, topy + 3), left_foot], d - .205, .17)
        rope(name + " mainsail foot", [left_foot, (topx - 2, sail_foot - 1)], d - .205, .17)
        rope_sag(name + " loose running rigging", (topx + 3, sail_foot), (right - 6, cy - 1), d - .25, 5, .22)
        stroke(name + " tiller", [(right - hull_width * .14, cy - 2),
                                  (right - hull_width * .29, cy - 6)], d - .09, .45, wood)
        for j, t in enumerate((.28, .5, .72)):
            xx = left + hull_width * t
            stroke(name + " transverse seat %d" % j, [(xx, cy - 5), (xx + 4, cy - 1)], d - .075, .9, wood)

    sailboat("Mid harbor cream-sail boat", 1310, 490, 1300, 390, 90, 142, 23, 104)
    sailboat("Distant small sailboat", 1390, 452, 1392, 386, 112, 83, 13, 63)
    sailboat("Foreground moored sailboat", 1445, 729, 1470, 565, 46, 219, 38, 176)
    rope_sag("Foreground boat bow mooring", (1331, 713), (1254, 697), 45.8, 13, .6)
    rope_sag("Foreground boat stern mooring", (1544, 717), (1427, 691), 45.8, 11, .55)
    rope_sag("Main boat shore line", (1235, 486), (1180, 502), 89.7, 5, .27)
    # Two low fishing skiffs, with individual ribs and thwarts.
    for i, (cx, cy, width, d) in enumerate([(1542, 484, 63, 103), (1250, 545, 78, 72)]):
        name = "Fishing skiff %d" % (i + 1)
        solid_panel(name + " hull", [(cx - width * .5, cy - 3), (cx + width * .48, cy - 4),
                                    (cx + width * .32, cy + 7), (cx - width * .35, cy + 8)], d, .5, wood)
        panel(name + " interior", [(cx - width * .35, cy - 3), (cx + width * .34, cy - 3),
                                   (cx + width * .26, cy + 1), (cx - width * .28, cy + 2)], d - .04, dark)
        for j in range(3):
            xx = cx - width * .25 + j * width * .23
            stroke(name + " seat %d" % j, [(xx, cy - 3), (xx + 3, cy + 2)], d - .09, .65, wood)
        stroke(name + " oar", [(cx - 9, cy - 8), (cx + 24, cy + 5)], d - .1, .45, wood)

    set_collection(collection("Market | canvas stalls"))

    def awning(name, corners, d, drop=57, stripes=0, material=fabric):
        solid_panel(name + " canvas", corners, d, .015, material)
        stroke(name + " front hem", [corners[-1], corners[-2]], d - .04, .7, material)
        # Vertical legs follow the two visible front corners.
        for j, p in enumerate((corners[-1], corners[-2])):
            stroke(name + " front post %d" % (j + 1), [(p[0], p[1] - 2), (p[0], p[1] + drop)], d + .035, 1.25, wood)
        for j, p in enumerate(corners[:2]):
            stroke(name + " rear post %d" % (j + 1), [(p[0], p[1] + 2), (p[0], p[1] + drop * .85)], d + .24, .95, wood)
        if stripes:
            a, b, c, e = [Vector(p) for p in corners]
            for j in range(1, stripes):
                t = j / stripes
                stroke(name + " canvas seam %d" % j, [a.lerp(b, t), e.lerp(c, t)], d - .025, .26, material)
        return corners[-1], corners[-2]

    # The broad left canopy has a fifth control vertex at the clipped frame edge.
    solid_panel("Left market broad ochre awning", [(4, 432), (165, 439), (377, 535),
                                                   (345, 602), (0, 548)], 17.4, .024, fabric)
    stroke("Left market awning hem", [(0, 548), (345, 602), (377, 535)], 17.35, 1.1, fabric)
    stroke("Left market awning ridge", [(4, 432), (165, 439), (377, 535)], 17.38, .8, wood)
    for j, t in enumerate((.2, .4, .6, .8)):
        a = Vector((4, 432)).lerp(Vector((165, 439)), t)
        b = Vector((0, 548)).lerp(Vector((345, 602)), t)
        stroke("Left market canvas stitched seam %d" % j, [a, b], 17.36, .24, fabric)
    for j, (x, y, foot) in enumerate([(38, 554, 704), (345, 602, 713), (374, 535, 659)]):
        stroke("Left market timber support %d" % j, [(x, y - 5), (x, foot)], 17.7, 2.2, wood)
    rope_sag("Left market tension cord", (345, 602), (402, 687), 17.65, 9, .45)

    awning("Upper street small stall", [(470, 390), (586, 399), (644, 454), (497, 442)], 28.0, 67, 7, fabric)
    awning("Street market striped stall", [(770, 619), (868, 627), (913, 684), (795, 668)], 21.8, 71, 8, fabric)
    awning("Harbor blue canvas stall", [(1008, 653), (1132, 666), (1090, 745), (982, 722)], 18.4, 81, 7, blue)
    # Source-aligned scalloped hems are separate meshes for straightforward editing.
    for label, a, b, d in [("Street market", (795, 668), (913, 684), 21.75),
                            ("Blue canvas", (982, 722), (1090, 745), 18.35)]:
        for j in range(10):
            t0, t1 = j / 10, (j + 1) / 10
            p = Vector(a).lerp(Vector(b), t0)
            q = Vector(a).lerp(Vector(b), t1)
            m = (p + q) * .5 + Vector((0, 4))
            panel(label + " canvas valance %02d" % j, [p, q, q + Vector((0, 2)), m, p + Vector((0, 2))], d, fabric if label == "Street market" else blue)

    set_collection(collection("Market | produce and merchant props"))
    pbox("Left stall long merchant counter", (200, 661), 17.9, (254, 44, 36), wood)
    pbox("Middle street merchant counter", (849, 720), 22.0, (114, 28, 29), wood)
    pbox("Blue awning merchant counter", (1030, 785), 18.8, (105, 35, 34), wood)
    pbox("Upper street merchant counter", (555, 486), 28.2, (95, 24, 24), wood)
    for i, (uv, d, w, h, dep) in enumerate([((82, 695), 15.9, 48, 37, 34),
                                           ((126, 715), 15.6, 43, 29, 32),
                                           ((365, 693), 17.1, 39, 31, 28),
                                           ((388, 729), 16.5, 33, 28, 24),
                                           ((802, 748), 21.1, 28, 24, 23),
                                           ((823, 754), 20.9, 30, 21, 25),
                                           ((1109, 796), 18.1, 34, 27, 27),
                                           ((1133, 810), 17.9, 29, 25, 22),
                                           ((530, 508), 27.6, 18, 16, 16)]):
        crate("Market stacked crate %02d" % (i + 1), uv, d, w, h, dep)
    for i, (uv, d, h, r) in enumerate([((419, 708), 17.5, 48, 17), ((447, 716), 17.3, 38, 14),
                                     ((745, 718), 21.9, 29, 11), ((933, 747), 20.6, 37, 13),
                                     ((1151, 770), 18.6, 33, 12), ((573, 513), 27.8, 20, 7),
                                     ((68, 744), 15.1, 42, 16)]):
        barrel("Market oak barrel %02d" % (i + 1), uv, d, h, r)
    for i, (uv, d, h, r) in enumerate([((297, 718), 16.8, 39, 16), ((322, 727), 16.4, 29, 12),
                                     ((279, 735), 16.2, 22, 10), ((957, 774), 20.0, 29, 11),
                                     ((974, 790), 19.7, 21, 8), ((1061, 823), 18.1, 33, 13),
                                     ((1080, 829), 17.9, 24, 10), ((599, 507), 27.7, 18, 7)]):
        pot("Market terracotta vessel %02d" % (i + 1), uv, d, h, r)
    # Modest, deterministic produce piles; individual fruit remain editable.
    for group, (cx, cy, d, rows, columns, radius, color) in enumerate([
            (154, 633, 17.7, 3, 9, 3.2, orange), (227, 649, 17.65, 3, 8, 3.1, red),
            (844, 702, 21.7, 2, 8, 2.0, green), (1038, 764, 18.55, 3, 7, 2.7, orange),
            (550, 472, 27.95, 2, 6, 1.5, red)]):
        for row in range(rows):
            for col in range(columns):
                x = cx + (col - (columns - 1) * .5) * radius * 1.72 + (row % 2) * radius * .6
                y = cy + row * radius * 1.06
                fruit("Produce pile %d fruit %02d" % (group + 1, row * columns + col + 1), (x, y), d + row * .005, radius, color)
    # Shallow produce trays sit visibly above the counter edges.
    for i, (uv, d, w, h) in enumerate([((154, 639), 17.75, 61, 9), ((227, 654), 17.7, 52, 8),
                                      ((844, 707), 21.75, 45, 6), ((1038, 771), 18.6, 47, 9)]):
        x, y = uv
        stroke("Produce tray %d front rail" % (i + 1), [(x - w / 2, y), (x + w / 2, y)], d - .025, .9, wood)
        stroke("Produce tray %d left rail" % (i + 1), [(x - w / 2, y - h), (x - w / 2, y)], d - .02, .8, wood)
        stroke("Produce tray %d right rail" % (i + 1), [(x + w / 2, y - h), (x + w / 2, y)], d - .02, .8, wood)

    return created
