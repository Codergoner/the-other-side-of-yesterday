"""Corrugated tile surface shared by landmarks and the waiting shelter."""
import math


def tile_plane(b, p0, p1, p2, p3, columns, cells, keep=lambda c, r: True, height=.11):
    """Corrugated tile surface between four corners; p0-p1 eave, p3-p2 ridge."""
    from mathutils import Vector
    p0, p1, p2, p3 = [Vector(p) for p in (p0, p1, p2, p3)]
    width = (p1 - p0).length
    run = (p3 - p0).length
    up = (p1 - p0).cross(p3 - p0).normalized()
    section = 5
    for col in range(columns):
        for r in range(cells):
            if not keep(col, r):
                continue
            s0, s1 = r / cells, (r + 1) / cells
            for k in range(section - 1):
                a0, a1 = (col + k / (section - 1)) / columns, (col + (k + 1) / (section - 1)) / columns
                h0, h1 = math.sin(k / (section - 1) * math.pi) * height, math.sin((k + 1) / (section - 1) * math.pi) * height
                e0 = p0.lerp(p1, a0)
                e1 = p0.lerp(p1, a1)
                r0 = p3.lerp(p2, a0)
                r1 = p3.lerp(p2, a1)
                ao0, ao1 = .55 + .45 * h0 / height, .55 + .45 * h1 / height
                ids = [b.vertex(e0.lerp(r0, s0) + up * h0, (0, ao0, 0, 0)), b.vertex(e1.lerp(r1, s0) + up * h1, (0, ao1, 0, 0)),
                       b.vertex(e1.lerp(r1, s1) + up * h1, (0, ao1, 0, 0)), b.vertex(e0.lerp(r0, s1) + up * h0, (0, ao0, 0, 0))]
                b.face(ids, 'Roof', [(a0 * width / 2.5, s0 * run / 2.5), (a1 * width / 2.5, s0 * run / 2.5),
                                     (a1 * width / 2.5, s1 * run / 2.5), (a0 * width / 2.5, s1 * run / 2.5)])
