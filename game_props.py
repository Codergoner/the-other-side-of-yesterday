"""Freestanding, metric market, dock and boat assets for the playable harbor.

No reference-camera coordinates or image projection are used here.  Geometry is
Z-up in meters; primitive meshes have native local UVs.  add_props is additive.
"""
import math

from mathutils import Vector


def add_props(api):
    get = api.get if isinstance(api, dict) else lambda key: getattr(api, key)
    raw_box, raw_mesh, raw_beam = get("box"), get("mesh"), get("beam")
    m = get("materials")
    objects = []

    def uv(obj):
        if obj is None:
            return obj
        objects.append(obj)
        if getattr(obj, "type", None) == "MESH":
            data = obj.data
            data.update()
            layer = data.uv_layers.active or data.uv_layers.new(name="Native metric UV")
            for face in data.polygons:
                normal = face.normal
                axis = max(range(3), key=lambda a: abs(normal[a]))
                axes = ((1, 2), (0, 2), (0, 1))[axis]
                for loop_index in face.loop_indices:
                    co = data.vertices[data.loops[loop_index].vertex_index].co
                    layer.data[loop_index].uv = (co[axes[0]], co[axes[1]])
        return obj

    def box(name, center, size, material="wood", group="SM_MarketProps", collision=False, bevel=.025):
        return uv(raw_box(name, center, size, m[material], group=group, collision=collision, bevel=bevel))

    def mesh(name, verts, faces, material="wood", group="SM_MarketProps", collision=False):
        return uv(raw_mesh(name, verts, faces, m[material], group=group, collision=collision))

    def beam(name, a, b, radius=.05, material="wood", group="SM_MarketProps", collision=False):
        return uv(raw_beam(name, a, b, radius, m[material], group=group, collision=collision))

    def floor(y):
        return 8 + (y + 22) * .10

    def line(name, points, radius=.012, material="fabric", group="SM_MarketProps", sag=0):
        if sag and len(points) == 2:
            a, b = Vector(points[0]), Vector(points[1])
            points = [a.lerp(b, j / 10) - Vector((0, 0, sag * 4 * j / 10 * (1 - j / 10))) for j in range(11)]
        for i in range(len(points) - 1):
            beam(name + "_%02d" % i, points[i], points[i + 1], radius, material, group)

    def lathe(name, location, profile, material="wood", group="SM_MarketProps", segments=16,
              closed_bottom=True, closed_top=True):
        c = Vector(location)
        verts = []
        for z, radius in profile:
            for j in range(segments):
                a = 2 * math.pi * j / segments
                verts.append(c + Vector((radius * math.cos(a), radius * math.sin(a), z)))
        faces = []
        for row in range(len(profile) - 1):
            for j in range(segments):
                a = row * segments + j
                b = row * segments + (j + 1) % segments
                faces.append((a, b, b + segments, a + segments))
        if closed_bottom:
            faces.append(tuple(range(segments - 1, -1, -1)))
        if closed_top:
            faces.append(tuple(range((len(profile) - 1) * segments, len(profile) * segments)))
        obj = mesh(name, verts, faces, material, group)
        # Cylindrical UVs preserve useful, contiguous native surfaces.
        layer = obj.data.uv_layers.active
        perimeter = max(r for z, r in profile) * 2 * math.pi
        for poly in obj.data.polygons:
            for index in poly.loop_indices:
                vi = obj.data.loops[index].vertex_index
                row, col = divmod(vi, segments)
                layer.data[index].uv = (col / segments * perimeter, profile[row][0])
        return obj

    def barrel(name, at, scale=1, group="SM_MarketProps"):
        profile = [(0, .27), (.06, .30), (.23, .34), (.52, .35), (.77, .32), (.87, .28)]
        profile = [(z * scale, r * scale) for z, r in profile]
        lathe(name + "_oak_staves", at, profile, "wood", group)
        for i, z in enumerate((.12, .37, .71)):
            radius = (.325 if i != 1 else .355) * scale
            lathe(name + "_iron_hoop_%d" % i, at, [(z * scale, radius), ((z + .055) * scale, radius)],
                  "metal", group, closed_bottom=False, closed_top=False)
        # Real shallow stave grooves remain readable in an untextured view.
        x, y, z0 = at
        for i in range(12):
            a = 2 * math.pi * i / 12
            line(name + "_stave_%d" % i,
                 [(x + r * math.cos(a), y + r * math.sin(a), z0 + z) for z, r in profile],
                 .0035 * scale, "dark", group)
        beam(name + "_bung", (x, y, z0 + .87 * scale), (x, y, z0 + .887 * scale), .04 * scale, "wood", group)

    def crate(name, at, size=(.65, .55, .45), group="SM_MarketProps", produce=False):
        x, y, z = at
        w, d, h = size
        box(name + "_bottom", (x, y, z + .035), (w, d, .07), "wood", group)
        for sx in (-1, 1):
            for sy in (-1, 1):
                box(name + "_corner_%d_%d" % (sx, sy), (x + sx * (w / 2 - .035), y + sy * (d / 2 - .035), z + h / 2),
                    (.065, .065, h), "wood", group)
        for row in range(3):
            zz = z + .12 + row * (h - .15) / 3
            for side in (-1, 1):
                box(name + "_side_%d_%d" % (side, row), (x + side * (w / 2 - .015), y, zz),
                    (.035, d, .075), "wood", group, bevel=.007)
                box(name + "_end_%d_%d" % (side, row), (x, y + side * (d / 2 - .015), zz),
                    (w, .035, .075), "wood", group, bevel=.007)
        if produce:
            for ix in range(4):
                for iy in range(3):
                    colors = ("fruit_gold", "fruit_red", "fruit_green")
                    color = colors[(ix + iy) % 3]
                    if color not in m:
                        color = "terracotta" if (ix + iy) % 3 else "leaf"
                    sphere(name + "_fruit_%d_%d" % (ix, iy),
                           (x + (ix - 1.5) * w / 5, y + (iy - 1) * d / 4, z + h - .045), .065,
                           color, group)

    def sphere(name, center, radius, material, group):
        c = Vector(center)
        verts = [c + Vector((0, 0, -radius))]
        for i in range(1, 6):
            phi = math.pi * i / 6
            for j in range(10):
                theta = 2 * math.pi * j / 10
                verts.append(c + Vector((math.sin(phi) * math.cos(theta), math.sin(phi) * math.sin(theta), -math.cos(phi))) * radius)
        verts.append(c + Vector((0, 0, radius)))
        faces = [(0, 1 + (j + 1) % 10, 1 + j) for j in range(10)]
        for i in range(4):
            for j in range(10):
                a, b = 1 + i * 10 + j, 1 + i * 10 + (j + 1) % 10
                faces.append((a, b, b + 10, a + 10))
        faces += [(51, 41 + j, 41 + (j + 1) % 10) for j in range(10)]
        return mesh(name, verts, faces, material, group)

    def pot(name, at, scale=1, group="SM_MarketProps"):
        profile = [(0, .16), (.08, .23), (.30, .31), (.49, .28), (.64, .16), (.69, .17),
                   (.72, .205), (.75, .205), (.75, .16), (.69, .14), (.64, .14), (.56, .17)]
        lathe(name + "_hollow_terracotta", at, [(z * scale, r * scale) for z, r in profile],
              "terracotta", group, closed_top=False)
        x, y, z = at
        lathe(name + "_inside_shadow", (x, y, z + .54 * scale), [(0, .17 * scale)], "dark", group)

    def stall(index, x, y, width=3, depth=3, facing=1):
        group = "SM_MarketStalls"
        name = "Market_%02d" % index
        xmin, xmax = x - width / 2, x + width / 2
        ymin, ymax = y - depth / 2, y + depth / 2
        frontx = xmax if facing > 0 else xmin
        backx = xmin if facing > 0 else xmax
        canvas = {3: "canvas_rust", 4: "canvas_blue", 5: "canvas_rust"}.get(index, "fabric")
        if canvas not in m:
            canvas = "fabric"
        for ix, xx in enumerate((xmin, xmax)):
            for iy, yy in enumerate((ymin, ymax)):
                z = floor(yy)
                top = z + (3.05 if xx == backx else 2.65)
                box(name + "_upright_%d_%d" % (ix, iy), (xx, yy, (z + top) / 2), (.13, .13, top - z),
                    "wood", group, collision=True)
        for iy, yy in enumerate((ymin, ymax)):
            beam(name + "_roof_end_%d" % iy, (backx, yy, floor(yy) + 3.05),
                 (frontx, yy, floor(yy) + 2.65), .055, "wood", group)
        for ix, xx in enumerate((xmin, xmax)):
            zz = 3.05 if xx == backx else 2.65
            beam(name + "_eaves_%d" % ix, (xx, ymin, floor(ymin) + zz), (xx, ymax, floor(ymax) + zz), .055, "wood", group)
        # A real double-sided canopy: shallow thickness keeps its underside solid.
        nu, nv = 8, 10
        verts = []
        for shell in (0, 1):
            for i in range(nu + 1):
                u = i / nu
                xx = xmin - .12 + (width + .24) * u
                for j in range(nv + 1):
                    v = j / nv
                    yy = ymin - .12 + (depth + .24) * v
                    slope_u = u if facing > 0 else 1 - u
                    z = floor(yy) + 3.05 - .40 * slope_u - .16 * math.sin(math.pi * u) * math.sin(math.pi * v)
                    z += .025 * math.sin(v * math.pi * 10) * math.sin(math.pi * u) - shell * .012
                    verts.append((xx, yy, z))
        stride = (nu + 1) * (nv + 1)
        faces = []
        for shell in (0, 1):
            for i in range(nu):
                for j in range(nv):
                    a = shell * stride + i * (nv + 1) + j
                    f = (a, a + nv + 1, a + nv + 2, a + 1)
                    faces.append(f if shell == 0 else tuple(reversed(f)))
        boundary = list(range(nv + 1)) + [i * (nv + 1) + nv for i in range(1, nu + 1)]
        boundary += [nu * (nv + 1) + j for j in range(nv - 1, -1, -1)]
        boundary += [i * (nv + 1) for i in range(nu - 1, 0, -1)]
        for i, a in enumerate(boundary):
            b = boundary[(i + 1) % len(boundary)]
            faces.append((a, b, b + stride, a + stride))
        mesh(name + "_sagged_linen_canopy", verts, faces, canvas, group)
        # Scalloped, sewn front valance is intentionally lower than the front rail.
        for j in range(10):
            ya, yb = ymin - .12 + (depth + .24) * j / 10, ymin - .12 + (depth + .24) * (j + 1) / 10
            za, zb = floor(ya) + 2.65, floor(yb) + 2.65
            mesh(name + "_linen_valance_%02d" % j,
                 [(frontx + facing * .12, ya, za), (frontx + facing * .12, yb, zb), (frontx + facing * .12, yb, zb - .14),
                  (frontx + facing * .12, (ya + yb) / 2, (za + zb) / 2 - .23), (frontx + facing * .12, ya, za - .14)],
                 [(0, 1, 2, 3, 4), (4, 3, 2, 1, 0)], canvas, group)
        # Counter faces the street; its legs follow local floor elevation.
        counterx, counterz = frontx - facing * .35, floor(y) + .98
        box(name + "_counter_top", (counterx, y, counterz), (.77, depth - .35, .09), "wood", group, collision=True)
        for yy in (ymin + .3, ymax - .3):
            for xx in (counterx - .27, counterx + .27):
                ground = floor(yy)
                box(name + "_counter_leg_%.1f_%.1f" % (xx, yy), (xx, yy, (ground + counterz) / 2),
                    (.09, .09, counterz - ground), "wood", group, collision=True)
        box(name + "_counter_front", (counterx + facing * .32, y, counterz - .30), (.045, depth - .4, .47), "wood", group)
        for j in range(2):
            crate(name + "_produce_crate_%d" % j, (counterx, y + (j - .5) * .9, counterz + .055),
                  (.58, .78, .28), produce=True)
        barrel(name + "_rear_barrel", (backx + facing * .50, y + .75, floor(y + .75)), .85)
        pot(name + "_large_pot", (backx + facing * .55, y - .75, floor(y - .75)), 1.1)
        crate(name + "_ground_crate", (x - .2, ymin + .45, floor(ymin + .45)), (.75, .6, .47))
        crate(name + "_stacked_crate", (x - .2, ymin + .45, floor(ymin + .45) + .47), (.66, .55, .40))
        line(name + "_canopy_tie", [(backx, ymin, floor(ymin) + 3.05), (backx - facing * .42, ymin - .25, floor(ymin - .25) + .12)],
             .012, "fabric", group)

    for i, y in enumerate((-16, -6, 6, 18), 1):
        stall(i, -4.5, y)
    # A compact right-hand vendor leaves the central walking corridor open.
    stall(5, 4.4, 10, 2.4, 2.6, facing=-1)

    # Continuous collision decks carry the player.  Board gaps are visual only.
    def dock(name, a, b, width=3, posts=True):
        group = "SM_DocksMain"
        a, b = Vector(a), Vector(b)
        delta = b - a
        along_x = abs(delta.x) > abs(delta.y)
        length = abs(delta.x) if along_x else abs(delta.y)
        center = (a + b) / 2
        size = (length, width, .35) if along_x else (width, length, .35)
        box(name + "_continuous_walkable_deck", (center.x, center.y, 1.025), size,
            "wood", group, collision=True, bevel=.012)
        count = max(1, round(length / .24))
        for i in range(count):
            t = (i + .5) / count
            p = a.lerp(b, t)
            plank_size = (length / count - .014, width, .035) if along_x else (width, length / count - .014, .035)
            box(name + "_deck_board_%03d" % i, (p.x, p.y, 1.2175), plank_size, "wood", group, bevel=.004)
        # Longitudinal bearers and full-depth foundation piles make it 3D below.
        for side in (-1, 1):
            offset = Vector((0, side * (width / 2 - .28), -.37)) if along_x else Vector((side * (width / 2 - .28), 0, -.37))
            beam(name + "_underdeck_bearer_%d" % side, a + offset, b + offset, .14, "wood", group)
        if posts:
            np = max(2, int(length / 4) + 1)
            for j in range(np):
                p = a.lerp(b, j / (np - 1))
                for side in (-1, 1):
                    q = p + (Vector((0, side * (width / 2 - .12), 0)) if along_x else Vector((side * (width / 2 - .12), 0, 0)))
                    beam(name + "_pile_%02d_%d" % (j, side), (q.x, q.y, -1.6), (q.x, q.y, 2.0), .105, "wood", group, collision=True)
                    lathe(name + "_pile_rope_wrap_%02d_%d" % (j, side), (q.x, q.y, 1.54),
                          [(0, .113), (.12, .113)], "fabric", group, closed_bottom=False, closed_top=False)
            # Rope rail only on the waterside.  Keep junctions open to walking.
            if along_x:
                for j in range(np - 1):
                    pa, pb = a.lerp(b, j / (np - 1)), a.lerp(b, (j + 1) / (np - 1))
                    line(name + "_waterside_rope_%d" % j,
                         [(pa.x, pa.y - width / 2 + .12, 1.8), (pb.x, pb.y - width / 2 + .12, 1.8)],
                         .018, "fabric", group, sag=.17)

    dock("Harbor_access", (11, 12, 1.2), (40, 12, 1.2))
    dock("Harbor_main_pier", (30, -1, 1.2), (30, 28, 1.2))
    dock("Harbor_side_connector", (30, 23, 1.2), (36, 23, 1.2), posts=False)
    dock("Harbor_side_finger", (36, 23, 1.2), (47, 23, 1.2))

    for i, (x, y, scale) in enumerate([(15, 12.8, 1), (16, 12.8, .8), (22, 13, 1),
                                       (29.1, 6, .9), (30.8, 18, 1), (45.7, 23.8, .85)]):
        barrel("Dock_cargo_barrel_%02d" % i, (x, y, 1.24), scale, "SM_DockCargo")
    for i, (x, y, scale) in enumerate([(18, 12.6, 1), (19, 12.6, .8), (30.6, 25.6, 1), (43.5, 23.7, 1)]):
        crate("Dock_shipping_crate_%02d" % i, (x, y, 1.24), (.9 * scale, .75 * scale, .7 * scale), "SM_DockCargo")
        if i % 2 == 0:
            crate("Dock_stacked_crate_%02d" % i, (x, y, 1.94), (.75, .65, .55), "SM_DockCargo")

    def sail(name, a, b, c, billow, group):
        # Barycentric triangular patch bows away from its supporting ropes.
        a, b, c = Vector(a), Vector(b), Vector(c)
        n = 8
        verts, lookup = [], {}
        for i in range(n + 1):
            for j in range(n + 1 - i):
                u, v = i / n, j / n
                w = 1 - u - v
                p = a * w + b * u + c * v
                p.x += billow * 27 * u * v * w
                lookup[(i, j)] = len(verts)
                verts.append(p)
        faces = []
        for i in range(n):
            for j in range(n - i):
                faces.append((lookup[i, j], lookup[i + 1, j], lookup[i, j + 1]))
                if j < n - i - 1:
                    faces.append((lookup[i + 1, j], lookup[i + 1, j + 1], lookup[i, j + 1]))
        # Back-facing copies give cloth a visible inside in engine materials.
        faces += [tuple(reversed(f)) for f in faces[:]]
        obj = mesh(name, verts, faces, "fabric", group)
        layer = obj.data.uv_layers.active
        for poly in obj.data.polygons:
            for index in poly.loop_indices:
                vtx = verts[obj.data.loops[index].vertex_index]
                layer.data[index].uv = (vtx.y * .4, vtx.z * .4)
        line(name + "_boltrope", [a, b, c, a], .012, "fabric", group)
        return obj

    def boat(letter, at, length, width, mast_height):
        group = "SM_Boat_" + letter
        name = "Boat_" + letter
        c = Vector(at)
        stations = [(-.5, .30), (-.40, .65), (-.25, .92), (0, 1), (.22, .88), (.40, .53), (.50, .025)]
        cross = [(-1, .78), (-.98, .31), (-.73, -.31), (-.34, -.62), (0, -.72),
                 (.34, -.62), (.73, -.31), (.98, .31), (1, .78)]
        verts = []
        for inner in (False, True):
            for t, taper in stations:
                for sx, z in cross:
                    xx = sx * width / 2 * taper
                    zz = z * (.52 + .48 * taper)
                    if inner:
                        xx *= .91
                        zz += .075 if z < .7 else -.025
                    verts.append(c + Vector((xx, t * length, zz)))
        rings, cols = len(stations), len(cross)
        layer_count = rings * cols
        faces = []
        for inner in range(2):
            for i in range(rings - 1):
                for j in range(cols - 1):
                    a = inner * layer_count + i * cols + j
                    f = (a, a + cols, a + cols + 1, a + 1)
                    faces.append(f if not inner else tuple(reversed(f)))
        # Bridge inner and outer shells at both gunwales and at stem/transom.
        for i in range(rings - 1):
            for j in (0, cols - 1):
                a, b = i * cols + j, (i + 1) * cols + j
                faces.append((a, b, b + layer_count, a + layer_count))
        for row in (0, rings - 1):
            for j in range(cols - 1):
                a, b = row * cols + j, row * cols + j + 1
                faces.append((a, b, b + layer_count, a + layer_count))
        mesh(name + "_curved_solid_hull", verts, faces, "wood", group)
        for side in (-1, 1):
            sheer = [c + Vector((side * width / 2 * taper, t * length, .78 * (.52 + .48 * taper))) for t, taper in stations]
            line(name + "_rounded_gunwale_%d" % side, sheer, .045, "wood", group)
            stripe = [c + Vector((side * width * .485 * taper, t * length, .28 * (.52 + .48 * taper))) for t, taper in stations]
            line(name + "_dark_strake_%d" % side, stripe, .025, "dark", group)
        # Raised wooden cockpit floor, separate seats, and a covered bow deck.
        box(name + "_cockpit_floor", c + Vector((0, -.1 * length, -.18)), (width * .65, length * .52, .08), "wood", group)
        for j, t in enumerate((-.30, -.08, .15)):
            box(name + "_thwart_%d" % j, c + Vector((0, t * length, .48)), (width * .78, .27, .10), "wood", group)
            for side in (-1, 1):
                beam(name + "_thwart_bracket_%d_%d" % (j, side), c + Vector((side * width * .32, t * length, -.1)),
                     c + Vector((side * width * .32, t * length, .48)), .035, "wood", group)
        bowverts = [c + Vector((0, .49 * length, .44)), c + Vector((-width * .30, .30 * length, .69)),
                    c + Vector((width * .30, .30 * length, .69))]
        mesh(name + "_bow_deck", bowverts, [(0, 1, 2)], "wood", group)
        for j in range(7):
            t = -.32 + j * .075
            beam(name + "_hull_rib_%d" % j, c + Vector((-width * .37, t * length, .35)),
                 c + Vector((width * .37, t * length, .35)), .025, "wood", group)
        mastfoot = c + Vector((0, -.06 * length, -.1))
        masttop = c + Vector((0, -.06 * length, mast_height))
        beam(name + "_mast", mastfoot, masttop, .073, "wood", group)
        boomroot = c + Vector((0, -.06 * length, 1.15))
        boomtip = c + Vector((0, -.43 * length, 1.45))
        beam(name + "_boom", boomroot, boomtip, .052, "wood", group)
        sail(name + "_billowing_mainsail", masttop - Vector((0, 0, .3)), boomroot + Vector((0, 0, .10)),
             boomtip + Vector((0, 0, .12)), .42 * length / 9, group)
        sail(name + "_billowing_jib", masttop - Vector((0, 0, 1.0)), c + Vector((0, .45 * length, .72)),
             c + Vector((0, .025 * length, 1.36)), .26 * length / 9, group)
        for side in (-1, 1):
            for t in (-.27, .18):
                line(name + "_standing_rig_%d_%.2f" % (side, t),
                     [masttop - Vector((0, 0, .35)), c + Vector((side * width * .43, t * length, .66))], .011, "fabric", group)
        line(name + "_forestay", [masttop, c + Vector((0, .48 * length, .60))], .012, "fabric", group)
        line(name + "_backstay", [masttop, c + Vector((0, -.48 * length, .55))], .012, "fabric", group)
        line(name + "_mainsheet", [boomtip, c + Vector((.25, -.34 * length, .38))], .015, "fabric", group, sag=.20)
        # Rudder and tiller are real slabs at the transom.
        box(name + "_rudder", c + Vector((0, -.51 * length, -.20)), (.10, .46, 1.15), "wood", group)
        beam(name + "_tiller", c + Vector((0, -.50 * length, .52)), c + Vector((0, -.31 * length, .72)), .04, "wood", group)
        for j, xx in enumerate((-.26, .26)):
            barrel(name + "_small_cask_%d" % j, c + Vector((xx, -.24 * length, -.11)), .38, group)

    boat("A", (38, 32, .25), 9, 2.55, 10)
    boat("B", (48, 44, .20), 7, 2.0, 8)
    boat("C", (42, 3, .25), 10, 2.8, 10.7)
    line("Boat_C_bow_mooring", [(42, 7.8, .87), (38, 10.65, 1.8)], .022, "fabric", "SM_Boat_C", sag=.35)
    line("Boat_C_stern_mooring", [(42, -1.8, .78), (31.35, -.7, 1.8)], .022, "fabric", "SM_Boat_C", sag=.5)
    line("Boat_A_mooring", [(37.1, 29, .85), (30.9, 27.8, 1.8)], .018, "fabric", "SM_Boat_A", sag=.35)

    # A handcart stays entirely outside the 4m-wide player corridor.
    group, name = "SM_MarketProps", "Corner_handcart"
    cx, cy, ground = -4, -20, 8.2
    box(name + "_bed", (cx, cy, ground + .78), (1.12, 1.75, .13), "wood", group)
    for row in range(3):
        zz = ground + .91 + row * .14
        for side in (-1, 1):
            box(name + "_side_%d_%d" % (side, row), (cx + side * .55, cy, zz), (.05, 1.75, .11), "wood", group)
        box(name + "_back_%d" % row, (cx, cy + .86, zz), (1.12, .05, .11), "wood", group)
    beam(name + "_axle", (cx - .8, cy + .1, ground + .57), (cx + .8, cy + .1, ground + .57), .07, "metal", group)
    for side in (-1, 1):
        wx, wy, wz = cx + side * .72, cy + .1, ground + .57
        verts, faces = [], []
        seg = 24
        # Four concentric tire rims produce a solid annular wheel along X.
        for offset, radius in ((-.055, .57), (.055, .57), (-.055, .49), (.055, .49)):
            for j in range(seg):
                theta = 2 * math.pi * j / seg
                verts.append((wx + offset, wy + radius * math.cos(theta), wz + radius * math.sin(theta)))
        for j in range(seg):
            k = (j + 1) % seg
            faces += [(j, k, seg + k, seg + j), (seg * 2 + j, seg * 3 + j, seg * 3 + k, seg * 2 + k),
                      (j, seg * 2 + j, seg * 2 + k, k), (seg + j, seg + k, seg * 3 + k, seg * 3 + j)]
        mesh(name + "_wheel_iron_tire_%d" % side, verts, faces, "metal", group)
        beam(name + "_wheel_hub_%d" % side, (wx - .1, wy, wz), (wx + .1, wy, wz), .12, "wood", group)
        for j in range(12):
            theta = 2 * math.pi * j / 12
            beam(name + "_wheel_%d_spoke_%02d" % (side, j), (wx, wy, wz),
                 (wx, wy + .51 * math.cos(theta), wz + .51 * math.sin(theta)), .025, "wood", group)
        beam(name + "_shaft_%d" % side, (cx + side * .42, cy - .75, ground + .74),
             (cx + side * .53, cy - 2.40, ground + .93), .045, "wood", group)
    crate(name + "_cargo_crate", (cx, cy, ground + .86), (.76, .67, .47), group, produce=True)

    return objects
