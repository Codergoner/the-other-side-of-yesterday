"""Metric, freestanding detail kit for the player's ruined coastal home.

Front is -Y.  build_details is additive and returns its own visible mesh objects.
The house shell, accessible floors and collision belong to the main builder.
"""
import math
import random
from mathutils import Vector, Matrix


def build_details(api):
    get = api.get if isinstance(api, dict) else lambda key: getattr(api, key)
    raw_box, raw_beam, raw_mesh = get('box'), get('beam'), get('mesh')
    materials = get('mat')
    try:
        rng = get('rand')
    except (AttributeError, KeyError):
        rng = random.Random(3471)
    if rng is None:
        rng = random.Random(3471)
    objects = []
    counters = {}

    def name(label):
        label = 'SM_Home_Detail_' + label
        counters[label] = counters.get(label, 0) + 1
        return label + '_%03d' % counters[label]

    def material(key):
        if key == 'shutter':
            return materials.get('shutter', materials['roof'])
        if key == 'glass':
            return materials.get('glass', materials['dark'])
        return materials[key]

    def box(label, loc, size, key='wood', bevel=.012):
        obj = raw_box(name(label), loc, size, material(key), bevel=bevel)
        objects.append(obj)
        return obj

    def mesh(label, verts, faces, key='wood'):
        obj = raw_mesh(name(label), verts, faces, material(key))
        objects.append(obj)
        return obj

    def beam(label, a, b, width=.055, depth=None, key='wood'):
        obj = raw_beam(name(label), a, b, width, depth or width, material(key))
        if obj:
            objects.append(obj)
        return obj

    def transformed_box(label, center, size, transform, key='wood'):
        c = Vector(center)
        half = Vector(size) / 2
        coords = [transform(c + Vector((x * half.x, y * half.y, z * half.z)))
                  for z in (-1, 1) for y in (-1, 1) for x in (-1, 1)]
        return mesh(label, coords,
                    [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4),
                     (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)], key)

    def torus(label, center, radius, thickness, key='metal', axis='Y', transform=None, segments=12):
        verts, faces = [], []
        c = Vector(center)
        for j in range(segments):
            a = math.tau * j / segments
            for i in range(5):
                b = math.tau * i / 5
                rad = radius + thickness * math.cos(b)
                p = Vector((rad * math.cos(a), thickness * math.sin(b), rad * math.sin(a)))
                if axis == 'Z':
                    p = Vector((p.x, p.z, p.y))
                p += c
                verts.append(transform(p) if transform else p)
        for j in range(segments):
            for i in range(5):
                faces.append((j * 5 + i, ((j + 1) % segments) * 5 + i,
                              ((j + 1) % segments) * 5 + (i + 1) % 5,
                              j * 5 + (i + 1) % 5))
        return mesh(label, verts, faces, key)

    def lathe(label, at, profile, key='terracotta', segments=16):
        x, y, z = at
        verts = [(x + r * math.cos(i * math.tau / segments),
                  y + r * math.sin(i * math.tau / segments), z + h)
                 for h, r in profile for i in range(segments)]
        faces = []
        for row in range(len(profile) - 1):
            for i in range(segments):
                a, b = row * segments + i, row * segments + (i + 1) % segments
                faces.append((a, b, b + segments, a + segments))
        faces.append(tuple(range(segments - 1, -1, -1)))
        return mesh(label, verts, faces, key)

    def arch_poly(cx, y, bottom, width, height, depth=.035):
        radius = width / 2
        spring = bottom + height - radius
        outline = [(cx - radius, bottom), (cx + radius, bottom)]
        outline += [(cx + radius * math.cos(a), spring + radius * math.sin(a))
                    for a in [i * math.pi / 14 for i in range(15)]]
        n = len(outline)
        verts = [(x, y + yy, z) for yy in (-depth / 2, depth / 2) for x, z in outline]
        faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
        faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
        return verts, faces

    def arch_trim(label, cx, y, bottom, width, height, key='stone', thick=.12):
        radius = width / 2
        spring = bottom + height - radius
        box(label + '_left_jamb', (cx - radius - thick / 2, y, (bottom + spring) / 2),
            (thick, .16, spring - bottom), key)
        box(label + '_right_jamb', (cx + radius + thick / 2, y, (bottom + spring) / 2),
            (thick, .16, spring - bottom), key)
        # Separate radial voussoirs catch sunlight and give a readable stone arch.
        for j in range(13):
            a0 = (j + .025) * math.pi / 13
            a1 = (j + .975) * math.pi / 13
            r0, r1 = radius + .006, radius + thick
            coords = [(cx + r * math.cos(a), y + yy, spring + r * math.sin(a))
                      for yy in (-.08, .08) for r, a in ((r0, a0), (r0, a1), (r1, a1), (r1, a0))]
            mesh(label + '_arch_stone', coords,
                 [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                  (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], key)

    def window(label, cx, y, bottom, width, height, shutters=True):
        radius = width / 2
        spring = bottom + height - radius
        verts, faces = arch_poly(cx, y + .018, bottom, width, height)
        mesh(label + '_recess_glazing', verts, faces, 'glass')
        arch_trim(label, cx, y - .03, bottom, width, height, 'stone', .135)
        arch_trim(label + '_oak_lining', cx, y - .08, bottom + .025,
                  width - .11, height - .055, 'wood', .046)
        box(label + '_center_mullion', (cx, y - .11, bottom + height * .49),
            (.043, .052, height * .94))
        box(label + '_transom', (cx, y - .11, bottom + height * .40),
            (width - .10, .052, .041))
        box(label + '_spring_bar', (cx, y - .11, spring), (width - .10, .052, .041))
        box(label + '_stone_sill', (cx, y - .14, bottom - .055), (width + .36, .34, .13), 'stone', .025)
        if shutters:
            for side in (-1, 1):
                sw = width * .39
                sx = cx + side * (width / 2 + sw / 2 + .105)
                sh = height * .78
                sz = bottom + sh / 2 + .06
                box(label + '_teal_shutter_back', (sx, y - .07, sz), (sw, .065, sh), 'shutter')
                for j in range(4):
                    xx = sx + (j - 1.5) * sw / 4
                    box(label + '_shutter_seam', (xx, y - .108, sz), (.009, .006, sh - .04), 'dark', 0)
                for zz in (bottom + .17, bottom + sh - .07):
                    box(label + '_shutter_cross_rail', (sx, y - .13, zz), (sw + .015, .04, .065), 'shutter')
                    box(label + '_hinge_strap', (sx - side * .10, y - .157, zz), (.20, .014, .025), 'metal', 0)
                box(label + '_shutter_latch', (sx, y - .14, bottom + .60), (.026, .04, .12), 'metal', .003)

    def door_leaf(label, hinge_x, hinge_y, bottom, width, height, swing=-70, hinge_left=True, glazed=False):
        angle = math.radians(swing)
        direction = 1 if hinge_left else -1
        def xf(v):
            u, v_y, z = v
            return Vector((hinge_x + direction * u * math.cos(angle) - v_y * math.sin(angle),
                           hinge_y + direction * u * math.sin(angle) + v_y * math.cos(angle), bottom + z))
        plank_h = height if not glazed else height * .37
        for j in range(7):
            transformed_box(label + '_individual_oak_plank', ((j + .5) * width / 7, 0, plank_h / 2),
                            (width / 7 - .007, .075, plank_h), xf)
        for xx in (.055, width - .055):
            transformed_box(label + '_door_stile', (xx, -.016, height / 2), (.095, .095, height), xf)
        for zz in (.13, height * .36, height - .11):
            transformed_box(label + '_door_rail', (width / 2, -.022, zz), (width, .095, .10), xf)
        if glazed:
            transformed_box(label + '_glazed_upper_panel', (width / 2, .004, height * .68),
                            (width - .18, .035, height * .55), xf, 'glass')
            for xx in (.33, .66):
                transformed_box(label + '_glazing_mullion', (width * xx, -.025, height * .68),
                                (.027, .055, height * .55), xf)
            transformed_box(label + '_glazing_transom', (width / 2, -.025, height * .72),
                            (width - .16, .055, .026), xf)
        for zz in (.28, height - .29):
            transformed_box(label + '_forged_hinge', (width * .21, -.076, zz), (width * .37, .022, .055), xf, 'metal')
            for xx in (.08, width * .31):
                transformed_box(label + '_hinge_nail', (xx, -.091, zz), (.018, .014, .018), xf, 'metal')
        transformed_box(label + '_handle_escutcheon', (width - .16, -.070, height * .44), (.10, .035, .17), xf, 'metal')
        torus(label + '_iron_ring_handle', (width - .16, -.11, height * .43), .052, .010, transform=xf)
        return xf

    # A real doorway.  The leaf is parked outside the opening, with no opaque
    # background plane inside the opening; the player can cross the threshold.
    door_leaf('entry', .025, -3.82, 1.18, 1.15, 2.22, swing=-70)
    for xx in (-.045, 1.245):
        box('entry_aged_oak_jamb', (xx, -3.75, 2.31), (.13, .20, 2.33))
    box('entry_aged_oak_lintel', (.60, -3.75, 3.49), (1.52, .23, .18))
    box('entry_threshold', (.60, -3.68, 1.18), (1.40, .44, .10), 'stone', .02)
    for side in (-1, 1):
        for row in range(7):
            z = 1.35 + row * .30
            box('entry_surround_limestone', (.60 + side * .79, -3.71, z),
                (.22 + (row % 2) * .03, .18, .28), 'stone', .023)
    box('entry_surround_limestone_header', (.60, -3.71, 3.62), (1.91, .22, .18), 'stone', .027)

    window('ground_left_window', -2.70, -3.77, 1.90, 1.05, 1.20)
    window('upstairs_right_window', 1.00, -3.77, 4.95, 1.10, 1.60)
    window('damaged_wing_window', 3.85, -3.76, 1.65, .95, 1.70)

    # Both balcony leaves are hinged open, exposing the upstairs room.
    door_leaf('balcony_left', -2.40, -3.80, 4.31, .75, 2.03, swing=-72, glazed=True)
    door_leaf('balcony_right', -.90, -3.80, 4.31, .75, 2.03, swing=72, hinge_left=False, glazed=True)
    for xx in (-2.47, -.83):
        box('balcony_door_jamb', (xx, -3.77, 5.33), (.11, .18, 2.14))
    box('balcony_door_lintel', (-1.65, -3.76, 6.41), (1.83, .20, .15))
    arch_trim('balcony_door_crown', -1.65, -3.72, 6.33, 1.62, .86, 'stone', .12)

    def lantern(label, cx, y, z, scale=1):
        # z is the lantern bottom. The warm core can be assigned an emissive
        # lantern material by the builder without creating an actor per face.
        s = scale
        box(label + '_wall_plate', (cx, y + .10, z + .65 * s), (.10 * s, .04, .30 * s), 'metal')
        beam(label + '_scroll_bracket', (cx, y + .08, z + .73 * s), (cx, y - .28 * s, z + .86 * s), .028 * s, key='metal')
        beam(label + '_hanger', (cx, y - .28 * s, z + .86 * s), (cx, y - .28 * s, z + .63 * s), .016 * s, key='metal')
        cy = y - .28 * s
        w, d, h = .24 * s, .21 * s, .40 * s
        box(label + '_bottom_plinth', (cx, cy, z + .05 * s), (w * 1.22, d * 1.22, .07 * s), 'metal')
        box(label + '_warm_glazing', (cx, cy, z + .25 * s), (w * .82, d * .82, h * .83), 'flower', .005)
        for xx in (-1, 1):
            for yy in (-1, 1):
                beam(label + '_frame_upright', (cx + xx * w / 2, cy + yy * d / 2, z + .08 * s),
                     (cx + xx * w / 2, cy + yy * d / 2, z + .46 * s), .020 * s, key='metal')
        box(label + '_top_rail', (cx, cy, z + .47 * s), (w * 1.14, d * 1.14, .048 * s), 'metal')
        verts = [(cx + xx * w * .66, cy + yy * d * .66, z + .49 * s)
                 for xx, yy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        verts += [(cx, cy, z + .64 * s)]
        mesh(label + '_pyramidal_hood', verts, [(0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)], 'metal')
        torus(label + '_suspension_ring', (cx, cy, z + .67 * s), .043 * s, .008 * s)

    lantern('entry_lantern_right', 1.67, -3.85, 2.33)
    lantern('entry_lantern_left', -.90, -3.85, 2.28, .86)
    lantern('balcony_lantern', -3.08, -3.83, 5.20, .82)

    leaf_vertices, leaf_faces, flower_vertices, flower_faces = [], [], [], []

    def leaf(at, size=.09, normal=(0, -1, 0)):
        n = Vector(normal).normalized()
        axis = n.cross(Vector((0, 0, 1)))
        if axis.length < .01:
            axis = n.cross(Vector((0, 1, 0)))
        axis.normalize()
        other = n.cross(axis).normalized()
        a = rng.uniform(-math.pi, math.pi)
        u = axis * math.cos(a) + other * math.sin(a)
        v = -axis * math.sin(a) + other * math.cos(a)
        c = Vector(at)
        points = [c - v * size, c - u * size * .58, c + v * size * 1.05,
                  c + u * size * .58, c + n * size * .17]
        off = len(leaf_vertices)
        leaf_vertices.extend(points)
        leaf_faces.extend([(off + j, off + (j + 1) % 4, off + 4) for j in range(4)])
        leaf_faces.extend([(off + 4, off + (j + 1) % 4, off + j) for j in range(4)])

    def flower(at, size=.043):
        c = Vector(at)
        off = len(flower_vertices)
        flower_vertices.append(c + Vector((0, -.010, 0)))
        for j in range(10):
            a = math.tau * j / 10
            r = size * (1 if j % 2 == 0 else .48)
            flower_vertices.append(c + Vector((r * math.cos(a), .008, r * math.sin(a))))
        flower_faces.extend([(off, off + 1 + j, off + 1 + (j + 1) % 10) for j in range(10)])

    def vine(label, points, leaves_per_segment=5, flowers=False):
        for i in range(len(points) - 1):
            a, b = Vector(points[i]), Vector(points[i + 1])
            beam(label + '_woody_stem', a, b, .018, key='wood')
            for j in range(leaves_per_segment):
                p = a.lerp(b, (j + rng.random()) / leaves_per_segment)
                p += Vector((rng.uniform(-.17, .17), rng.uniform(-.12, .02), rng.uniform(-.13, .13)))
                leaf(p, rng.uniform(.055, .115), (rng.uniform(-.3, .3), -1, rng.uniform(-.3, .3)))
                if flowers and rng.random() < .21:
                    flower(p + Vector((.018, -.035, .027)), rng.uniform(.032, .054))

    # Broad ivy on the left facade edge, with natural draping off the balcony.
    for j in range(14):
        top = rng.uniform(4.15, 6.65)
        bottom = rng.uniform(1.10, 2.6)
        x = rng.uniform(-4.28, -3.52)
        points = [(x + .15 * math.sin(k * .8 + j), -3.89 - rng.uniform(0, .07),
                   bottom + (top - bottom) * k / 10) for k in range(11)]
        vine('left_wall_ivy', points, 5, flowers=True)
    for j in range(6):
        x = -3.9 + j * .21
        points = [(x + .09 * math.sin(k), -4.81 - j * .035, 4.55 - k * .19) for k in range(rng.randint(8, 15))]
        vine('balcony_trailing_jasmine', points, 3, flowers=True)
    for j in range(7):
        x = 1.48 + j * .12
        points = [(x + .08 * math.sin(k + j), -3.90 - rng.uniform(0, .04), 1.16 + k * .20) for k in range(rng.randint(6, 13))]
        vine('entry_corner_ivy', points, 3)

    def pot(label, at, scale=.8, planted=True):
        profile = [(0, .13), (.05, .19), (.21, .26), (.39, .25), (.52, .18),
                   (.55, .19), (.58, .22), (.62, .22), (.62, .17), (.55, .15), (.49, .16)]
        lathe(label + '_hollow_clay', at, [(z * scale, r * scale) for z, r in profile])
        x, y, z = at
        lathe(label + '_potting_soil', (x, y, z + .49 * scale), [(0, .16 * scale), (.008, .16 * scale)], 'dark')
        torus(label + '_rolled_rim', (x, y, z + .60 * scale), .193 * scale, .025 * scale, 'terracotta', axis='Z')
        if planted:
            for k in range(7):
                a = k * math.tau / 7 + rng.uniform(-.1, .1)
                end = Vector((x + .30 * scale * math.cos(a), y + .30 * scale * math.sin(a), z + rng.uniform(.73, 1.10) * scale))
                start = Vector((x, y, z + .52 * scale))
                beam(label + '_plant_stem', start, end, .011 * scale, key='leaf')
                for step in range(5):
                    p = start.lerp(end, (step + 1) / 5)
                    leaf(p, .07 * scale, (math.cos(a), math.sin(a), .5))
                flower(end, .048 * scale)

    for label, at, scale, planted in [
        ('porch_left_large', (-3.43, -4.65, 1.15), 1.24, True),
        ('porch_left_small', (-3.02, -4.79, 1.15), .70, True),
        ('entry_herbs', (1.60, -4.12, 1.15), .79, True),
        ('entry_clay_jug', (1.85, -4.03, 1.15), .55, False),
        ('balcony_pot', (-3.45, -4.03, 4.31), .90, True),
        ('ruin_pot', (2.80, -4.25, 1.15), .74, True),
    ]:
        pot(label, at, scale, planted)

    # A small lived-in bench and boot scraper beside the entrance.
    box('porch_bench_seat', (-.67, -4.11, 1.60), (.67, .34, .075))
    for xx in (-.90, -.43):
        for yy in (-4.23, -3.99):
            box('porch_bench_leg', (xx, yy, 1.37), (.066, .066, .43))
    box('entry_boot_scraper_base', (1.35, -4.25, 1.22), (.30, .25, .06), 'stone')
    beam('entry_boot_scraper', (1.24, -4.25, 1.28), (1.46, -4.25, 1.28), .018, key='metal')

    # Localized collapse debris, confined to the damaged wing; it never spills
    # across the .6m-centered entrance and the left porch route.
    for j in range(46):
        x, y = rng.uniform(2.58, 5.45), rng.uniform(-4.65, -.82)
        z = 1.10 + rng.uniform(0, .18)
        w, d, h = rng.uniform(.13, .48), rng.uniform(.12, .38), rng.uniform(.09, .27)
        c = Vector((x, y, z + h / 2))
        rot = Matrix.Rotation(rng.uniform(-math.pi, math.pi), 4, 'Z') @ Matrix.Rotation(rng.uniform(-.35, .35), 4, 'X')
        coords = []
        for zz in (-1, 1):
            for yy in (-1, 1):
                for xx in (-1, 1):
                    p = Vector((xx * w / 2 * rng.uniform(.84, 1.13), yy * d / 2 * rng.uniform(.84, 1.13), zz * h / 2))
                    coords.append(c + rot.to_3x3() @ p)
        mesh('collapse_irregular_limestone', coords,
             [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)],
             'stone' if j % 4 else 'plaster')
    for j in range(15):
        a = Vector((rng.uniform(2.75, 5.20), rng.uniform(-4.45, -.5), 1.22 + rng.uniform(0, .36)))
        angle = rng.uniform(-math.pi, math.pi)
        b = a + Vector((math.cos(angle), math.sin(angle), rng.uniform(-.12, .15))) * rng.uniform(.45, 1.30)
        if b.x < 2.51:
            b.x = 2.51
        beam('collapse_splintered_oak', a, b, rng.uniform(.075, .13), rng.uniform(.055, .10))

    mesh('combined_ivy_and_plant_leaves', leaf_vertices, leaf_faces, 'leaf')
    mesh('combined_jasmine_blossoms', flower_vertices, flower_faces, 'flower')
    for obj in objects:
        if obj:
            obj['HomeDetail'] = True
    return objects
