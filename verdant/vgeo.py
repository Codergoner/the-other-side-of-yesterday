"""Mesh building blocks shared by the Verdant kit, landmarks and landscape.

All dimensions are metres, Z up. A facade module sits on the XZ plane with its outer face at
Y=0 and thickness toward +Y; X runs left to right seen from outside. Vertex colour channels
drive the masonry shader: R plaster coverage (1 intact, 0 bare limestone), G baked occlusion,
B soot, A wind weight for cloth and leaves.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import delaunay_2d_cdt

SLOTS = ['Masonry', 'Timber', 'Paint', 'Roof', 'Glass', 'Iron', 'Cloth', 'Leaf', 'Terracotta', 'Flat', 'Banner',
         'Cobble', 'Flagstone', 'Rock', 'Ground', 'Sea']

_tables = {}


def noise_table(seed=1, n=256):
    """Tileable value field for vertex painting; low frequencies dominate."""
    if seed not in _tables:
        g = np.random.default_rng(seed)
        fy = np.fft.fftfreq(n)[:, None] * n
        fx = np.fft.rfftfreq(n)[None, :] * n
        f = np.sqrt(fx * fx + fy * fy)
        f[0, 0] = 1
        field = np.fft.irfft2(np.fft.rfft2(g.normal(size=(n, n))) * f ** -1.1, s=(n, n))
        field = (field - field.min()) / (field.max() - field.min())
        _tables[seed] = field
    return _tables[seed]


def field(x, y, scale=1.0, seed=1):
    table = noise_table(seed)
    n = table.shape[0]
    u, v = (x * scale * 37.0) % n, (y * scale * 37.0) % n
    i, j = int(u), int(v)
    fu, fv = u - i, v - j
    a = table[j, i] * (1 - fu) + table[j, (i + 1) % n] * fu
    b = table[(j + 1) % n, i] * (1 - fu) + table[(j + 1) % n, (i + 1) % n] * fu
    return float(a * (1 - fv) + b * fv)


class Builder:
    """Collects triangles and quads per material, then bakes occlusion into vertex colour."""

    def __init__(self, name):
        self.name = name
        self.verts = []
        self.faces = []      # (indices, slot)
        self.uvs = []        # per face corner list
        self.colours = []    # per vertex (plaster, occlusion, soot, wind)
        self.flat = False

    def vertex(self, p, colour=(0, 1, 0, 0)):
        self.verts.append((float(p[0]), float(p[1]), float(p[2])))
        self.colours.append(tuple(colour))
        return len(self.verts) - 1

    def face(self, indices, slot, uv=None):
        self.faces.append((tuple(indices), SLOTS.index(slot)))
        if uv is None:
            uv = [self.planar_uv(i, indices) for i in indices]
        self.uvs.append(uv)

    def planar_uv(self, i, indices):
        a, b, c = [Vector(self.verts[k]) for k in indices[:3]]
        n = (b - a).cross(c - a)
        axis = max(range(3), key=lambda k: abs(n[k]))
        u, v = ((1, 2), (0, 2), (0, 1))[axis]
        p = self.verts[i]
        return (p[u] * .5, p[v] * .5)

    # ---- primitives -----------------------------------------------------------------

    def box(self, lo, hi, slot, colour=(0, 1, 0, 0), chamfer=0.0):
        lo, hi = [min(a, b) for a, b in zip(lo, hi)], [max(a, b) for a, b in zip(lo, hi)]
        size = [b - a for a, b in zip(lo, hi)]
        c = min(chamfer, min(size) * .45)
        if c < .002:
            ids = [self.vertex((x, y, z), colour) for z in (lo[2], hi[2]) for y in (lo[1], hi[1]) for x in (lo[0], hi[0])]
            for f in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
                self.face([ids[k] for k in f], slot)
            return
        # Chamfered box: each corner contributes three vertices.
        index = {}
        for sx, x in ((0, lo[0]), (1, hi[0])):
            for sy, y in ((0, lo[1]), (1, hi[1])):
                for sz, z in ((0, lo[2]), (1, hi[2])):
                    dx, dy, dz = (c if sx == 0 else -c), (c if sy == 0 else -c), (c if sz == 0 else -c)
                    index[sx, sy, sz, 0] = self.vertex((x, y + dy, z + dz), colour)
                    index[sx, sy, sz, 1] = self.vertex((x + dx, y, z + dz), colour)
                    index[sx, sy, sz, 2] = self.vertex((x + dx, y + dy, z), colour)
        q = lambda *k: [index[t] for t in k]
        self.face(q((0, 0, 0, 0), (0, 0, 1, 0), (0, 1, 1, 0), (0, 1, 0, 0)), slot)
        self.face(q((1, 0, 0, 0), (1, 1, 0, 0), (1, 1, 1, 0), (1, 0, 1, 0)), slot)
        self.face(q((0, 0, 0, 1), (1, 0, 0, 1), (1, 0, 1, 1), (0, 0, 1, 1)), slot)
        self.face(q((0, 1, 0, 1), (0, 1, 1, 1), (1, 1, 1, 1), (1, 1, 0, 1)), slot)
        self.face(q((0, 0, 0, 2), (0, 1, 0, 2), (1, 1, 0, 2), (1, 0, 0, 2)), slot)
        self.face(q((0, 0, 1, 2), (1, 0, 1, 2), (1, 1, 1, 2), (0, 1, 1, 2)), slot)
        for sy in (0, 1):
            for sz in (0, 1):
                f = q((0, sy, sz, 1), (1, sy, sz, 1), (1, sy, sz, 2), (0, sy, sz, 2))
                self.face(f if (sy + sz) % 2 == 1 else f[::-1], slot)
        for sx in (0, 1):
            for sz in (0, 1):
                f = q((sx, 0, sz, 0), (sx, 1, sz, 0), (sx, 1, sz, 2), (sx, 0, sz, 2))
                self.face(f if (sx + sz) % 2 == 0 else f[::-1], slot)
        for sx in (0, 1):
            for sy in (0, 1):
                f = q((sx, sy, 0, 0), (sx, sy, 1, 0), (sx, sy, 1, 1), (sx, sy, 0, 1))
                self.face(f if (sx + sy) % 2 == 1 else f[::-1], slot)
        for sx in (0, 1):
            for sy in (0, 1):
                for sz in (0, 1):
                    f = q((sx, sy, sz, 0), (sx, sy, sz, 1), (sx, sy, sz, 2))
                    self.face(f if (sx + sy + sz) % 2 == 1 else f[::-1], slot)

    def beam(self, a, b, width, height, slot, colour=(0, 1, 0, 0), up=(0, 0, 1), chamfer=.012):
        """Sawn timber between two points; UV runs along the grain."""
        a, b = Vector(a), Vector(b)
        axis = b - a
        length = axis.length
        if length < 1e-4:
            return
        d = axis / length
        side = d.cross(Vector(up))
        if side.length < 1e-3:
            side = d.cross(Vector((0, 1, 0)))
        side.normalize()
        top = side.cross(d).normalized()
        w, h = width / 2, height / 2
        c = min(chamfer, w * .4, h * .4)
        ring = [(-w + c, -h), (w - c, -h), (w, -h + c), (w, h - c), (w - c, h), (-w + c, h), (-w, h - c), (-w, -h + c)]
        n = len(ring)
        ids0 = [self.vertex(a + side * x + top * y, colour) for x, y in ring]
        ids1 = [self.vertex(b + side * x + top * y, colour) for x, y in ring]
        run = 0.0
        for i in range(n):
            j = (i + 1) % n
            seg = math.hypot(ring[j][0] - ring[i][0], ring[j][1] - ring[i][1])
            self.face((ids0[i], ids1[i], ids1[j], ids0[j]), slot,
                      [(0, run), (length / 2, run), (length / 2, run + seg / 2), (0, run + seg / 2)])
            run += seg / 2
        self.face(ids0, slot, [(p[0] * 2, p[1] * 2) for p in ring])
        self.face(ids1[::-1], slot, [(p[0] * 2, p[1] * 2) for p in ring[::-1]])

    def cylinder(self, a, b, r0, r1, slot, colour=(0, 1, 0, 0), sides=10, caps=True):
        a, b = Vector(a), Vector(b)
        axis = (b - a).normalized()
        side = axis.orthogonal().normalized()
        top = axis.cross(side)
        ring0, ring1 = [], []
        for i in range(sides):
            t = i * math.tau / sides
            d = side * math.cos(t) + top * math.sin(t)
            ring0.append(self.vertex(a + d * r0, colour))
            ring1.append(self.vertex(b + d * r1, colour))
        height = (b - a).length
        for i in range(sides):
            j = (i + 1) % sides
            u0, u1 = i / sides, (i + 1) / sides
            self.face((ring0[i], ring0[j], ring1[j], ring1[i]), slot,
                      [(u0, 0), (u1, 0), (u1, height / 2), (u0, height / 2)])
        if caps:
            self.face(ring0[::-1], slot)
            self.face(ring1, slot)

    def lathe(self, centre, profile, slot, colour=(0, 1, 0, 0), sides=16):
        """Revolves (radius, height) points around +Z."""
        cx, cy, cz = centre
        rings = []
        for r, z in profile:
            rings.append([self.vertex((cx + r * math.cos(i * math.tau / sides), cy + r * math.sin(i * math.tau / sides), cz + z), colour)
                          for i in range(sides)])
        for k in range(len(rings) - 1):
            v0 = sum(abs(profile[m + 1][1] - profile[m][1]) + abs(profile[m + 1][0] - profile[m][0]) for m in range(k))
            v1 = v0 + abs(profile[k + 1][1] - profile[k][1]) + abs(profile[k + 1][0] - profile[k][0])
            for i in range(sides):
                j = (i + 1) % sides
                a, b = i / sides * 3, (i + 1) / sides * 3
                self.face((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]), slot,
                          [(a, v0 / 2), (b, v0 / 2), (b, v1 / 2), (a, v1 / 2)])

    def quad(self, a, b, c, d, slot, colour=(0, 1, 0, 0), uv=None):
        ids = [self.vertex(p, colour) for p in (a, b, c, d)]
        self.face(ids, slot, uv)
        return ids

    def wall(self, outline, holes=(), thickness=.45, slot='Masonry', paint=None, reveal=None, spacing=.34, y=0.0, axis_map=None):
        """Solid slab with arbitrary outline and openings, tessellated for vertex painting.

        outline/holes are (x, z) loops. paint(x, z) returns the vertex colour for faces;
        reveal(x, z) colours the exposed thickness (window reveals, broken cores).
        axis_map optionally relocates (x, depth, z) to place slabs on other planes.
        """
        place = axis_map or (lambda p: p)
        paint = paint or (lambda x, z: (1, 1, 0, 0))
        reveal = reveal or (lambda x, z: (0, .7, 0, 0))
        outline = _ccw(list(outline))
        holes = [_ccw(list(h))[::-1] for h in holes]
        loops = [outline] + holes
        coords, edges = [], []
        for loop in loops:
            start = len(coords)
            coords.extend(loop)
            n = len(loop)
            edges.extend((start + i, start + (i + 1) % n) for i in range(n))
        lo = (min(p[0] for p in outline), min(p[1] for p in outline))
        hi = (max(p[0] for p in outline), max(p[1] for p in outline))
        cols, rows = int((hi[0] - lo[0]) / spacing), int((hi[1] - lo[1]) / spacing)
        for i in range(1, cols):
            for j in range(1, rows):
                # A small jitter stops the tessellation showing up in vertex colour.
                p = (lo[0] + (i + field(i, j, .13, 3) * .6 - .3) * spacing, lo[1] + (j + field(j, i, .17, 4) * .6 - .3) * spacing)
                if _inside(p, outline, 0.05) and all(not _inside(p, h, -.05) for h in holes):
                    coords.append(p)
        result = delaunay_2d_cdt([Vector(p) for p in coords], edges, [], 0, 1e-5, False)
        out_verts, out_faces = result[0], result[2]
        points = [(v.x, v.y) for v in out_verts]
        for depth, flip in ((y, False), (y + thickness, True)):
            ids = {}
            for tri in out_faces:
                c = (sum(points[k][0] for k in tri) / 3, sum(points[k][1] for k in tri) / 3)
                if not _inside(c, outline) or any(_inside(c, h) for h in holes):
                    continue
                for k in tri:
                    if k not in ids:
                        px, pz = points[k]
                        ids[k] = self.vertex(place((px, depth, pz)), paint(px, pz))
                ordered = [ids[k] for k in tri]
                if _area2([points[k] for k in tri]) < 0:
                    ordered.reverse()
                self.face(ordered[::-1] if flip else ordered, slot)
        # Exposed thickness on every loop edge.
        for loop in loops:
            n = len(loop)
            for i in range(n):
                a, b = loop[i], loop[(i + 1) % n]
                length = math.hypot(b[0] - a[0], b[1] - a[1])
                if length < 1e-4:
                    continue
                f0 = self.vertex(place((a[0], y, a[1])), reveal(*a))
                b0 = self.vertex(place((b[0], y + thickness, b[1])), reveal(*b))
                a1 = self.vertex(place((a[0], y + thickness, a[1])), reveal(*a))
                b1 = self.vertex(place((b[0], y, b[1])), reveal(*b))
                self.face((f0, a1, b0, b1), slot, [(0, 0), (0, thickness / 2), (length / 2, thickness / 2), (length / 2, 0)])

    # ---- finishing ------------------------------------------------------------------

    def bake_occlusion(self, rays=20, reach=2.2, ground=None, strength=1.0):
        """Multiplies vertex G by hemisphere visibility against this mesh."""
        if not self.verts:
            return
        tris = []
        for indices, _ in self.faces:
            for i in range(1, len(indices) - 1):
                tris.append((indices[0], indices[i], indices[i + 1]))
        tree = BVHTree.FromPolygons(self.verts, tris, all_triangles=True)
        normals = [Vector((0, 0, 0)) for _ in self.verts]
        for indices, _ in self.faces:
            a, b, c = [Vector(self.verts[k]) for k in indices[:3]]
            n = (b - a).cross(c - a)
            for k in indices:
                normals[k] += n
        g = np.random.default_rng(99)
        dirs = g.normal(size=(rays, 3))
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
        for i, p in enumerate(self.verts):
            n = normals[i]
            if n.length < 1e-9:
                continue
            n = n.normalized()
            origin = Vector(p) + n * .012
            open_rays = 0
            inside = 0
            for d in dirs:
                v = Vector(d)
                if v.dot(n) < 0:
                    v = -v
                hit = tree.ray_cast(origin, v, reach)
                if hit[0] is None and not (ground is not None and v.z < 0 and origin.z + v.z * reach < ground):
                    open_rays += 1
                elif hit[0] is not None and hit[1].dot(v) > 0:
                    inside += 1
            # A vertex buried in another solid sees only backfaces; its darkness would be false.
            if inside > rays * .2:
                continue
            vis = open_rays / rays
            r, ao, s, w = self.colours[i]
            if w > 0:
                continue
            self.colours[i] = (r, ao * (1 - strength * (1 - vis ** .7)), s, w)

    def build(self, collection=None, smooth_angle=38.0):
        mesh = bpy.data.meshes.new(self.name)
        mesh.from_pydata(self.verts, [], [f[0] for f in self.faces])
        mesh.update()
        slots = sorted({f[1] for f in self.faces})
        for s in slots:
            mesh.materials.append(material(SLOTS[s]))
        remap = {s: i for i, s in enumerate(slots)}
        for poly, (_, s) in zip(mesh.polygons, self.faces):
            poly.material_index = remap[s]
        uv = mesh.uv_layers.new(name='UV0')
        cursor = 0
        for poly, corners in zip(mesh.polygons, self.uvs):
            for li, value in zip(poly.loop_indices, corners):
                uv.data[li].uv = value
        attr = mesh.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
        data = np.zeros(len(mesh.loops) * 4, np.float32)
        loops = np.zeros(len(mesh.loops), np.int32)
        mesh.loops.foreach_get('vertex_index', loops)
        colours = np.array(self.colours, np.float32)
        data[:] = colours[loops].ravel()
        attr.data.foreach_set('color', data)
        mesh.shade_smooth()
        mesh.set_sharp_from_angle(angle=math.radians(smooth_angle))
        obj = bpy.data.objects.new(self.name, mesh)
        (collection or bpy.context.scene.collection).objects.link(obj)
        return obj


_materials = {}
PREVIEW = {'Masonry': (.72, .62, .46), 'Timber': (.2, .12, .07), 'Paint': (.14, .3, .32), 'Roof': (.2, .4, .4), 'Glass': (.05, .07, .08),
           'Iron': (.04, .04, .04), 'Cloth': (.2, .42, .44), 'Leaf': (.2, .3, .14), 'Terracotta': (.55, .27, .15), 'Flat': (.3, .3, .3), 'Banner': (.1, .27, .35),
           'Cobble': (.5, .44, .35), 'Flagstone': (.6, .54, .44), 'Rock': (.45, .38, .3), 'Ground': (.4, .37, .22), 'Sea': (.1, .3, .35)}


def material(slot):
    if slot not in _materials:
        m = bpy.data.materials.new('M_V_' + slot)
        m.use_nodes = True
        nodes = m.node_tree.nodes
        p = nodes['Principled BSDF']
        p.inputs['Base Color'].default_value = (*PREVIEW[slot], 1)
        p.inputs['Roughness'].default_value = .75
        if slot == 'Masonry':
            attr = nodes.new('ShaderNodeVertexColor')
            attr.layer_name = 'Col'
            sep = nodes.new('ShaderNodeSeparateColor')
            mix = nodes.new('ShaderNodeMix')
            mix.data_type = 'RGBA'
            mix.inputs['A'].default_value = (.62, .5, .35, 1)
            mix.inputs['B'].default_value = (.82, .72, .55, 1)
            shade = nodes.new('ShaderNodeMix')
            shade.data_type = 'RGBA'
            shade.blend_type = 'MULTIPLY'
            shade.inputs['Factor'].default_value = 1
            links = m.node_tree.links
            links.new(attr.outputs['Color'], sep.inputs[0])
            links.new(sep.outputs[0], mix.inputs['Factor'])
            links.new(mix.outputs['Result'], shade.inputs['A'])
            links.new(sep.outputs[1], shade.inputs['B'])
            links.new(shade.outputs['Result'], p.inputs['Base Color'])
        _materials[slot] = m
    return _materials[slot]


def _area2(loop):
    return sum(loop[i][0] * loop[(i + 1) % len(loop)][1] - loop[(i + 1) % len(loop)][0] * loop[i][1] for i in range(len(loop)))


def _ccw(loop):
    return loop if _area2(loop) > 0 else loop[::-1]


def _inside(p, loop, margin=0.0):
    x, y = p
    hit = False
    n = len(loop)
    for i in range(n):
        ax, ay = loop[i]
        bx, by = loop[(i + 1) % n]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            hit = not hit
    if not hit or margin <= 0:
        return hit
    for i in range(n):
        ax, ay = loop[i]
        bx, by = loop[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / max(dx * dx + dy * dy, 1e-9)))
        if math.hypot(x - ax - t * dx, y - ay - t * dy) < margin:
            return False
    return True


def arch_points(cx, spring, half, rise=None, segments=14, skip_ends=False):
    """Points along a segmental arch from right to left (counter-clockwise from above)."""
    rise = half if rise is None else rise
    pts = []
    rng = range(1, segments) if skip_ends else range(segments + 1)
    for i in rng:
        t = math.pi * i / segments
        pts.append((cx + half * math.cos(t), spring + rise * math.sin(t)))
    return pts


def jagged(a, b, amplitude, seed, step=.22):
    """Broken masonry edge from a to b: blocks missing in irregular bites."""
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    count = max(2, int(length / step))
    nx, ny = -(b[1] - a[1]) / length, (b[0] - a[0]) / length
    pts = [a]
    for i in range(1, count):
        t = i / count
        coarse = field(t * length, seed * 1.7, .09, 5) - .5
        fine = field(t * length * 3.1, seed * .9, .23, 6) - .5
        off = (coarse * 2.2 + fine * .9) * amplitude
        pts.append((a[0] + (b[0] - a[0]) * t + nx * off, a[1] + (b[1] - a[1]) * t + ny * off))
    pts.append(b)
    return pts


def blob(cx, cz, rx, rz, seed, count=18, roughness=.45):
    """Irregular breach outline."""
    pts = []
    for i in range(count):
        t = i * math.tau / count
        r = 1 + (field(math.cos(t) * 2 + seed, math.sin(t) * 2, .21, 7) - .5) * roughness * 2
        pts.append((cx + rx * r * math.cos(t), cz + rz * r * math.sin(t)))
    return pts


def export_fbx(obj, path):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={'MESH'}, axis_forward='-Y', axis_up='Z',
                             global_scale=1, apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', use_mesh_modifiers=False,
                             add_leaf_bones=False, bake_anim=False, path_mode='RELATIVE', embed_textures=False,
                             mesh_smooth_type='FACE', colors_type='LINEAR')
