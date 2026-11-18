"""Geometry contracts only; no native or visual validation is implied."""
from pathlib import Path
import collections
import math
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'game_unreal/Python'))
import release_coast_contract as coast


class CoastContract(unittest.TestCase):
    def test_ring_has_exact_empty_inner_perimeter_and_no_duplicate_faces(self):
        vertices, triangles = coast.geometry()
        self.assertEqual(vertices[:4], [(-155., -138., -.01999999999999999),
                                      (205., -138., -.01999999999999999),
                                      (205., 222., -.01999999999999999),
                                      (-155., 222., -.01999999999999999)])
        self.assertEqual(len(set(tuple(sorted(t)) for t in triangles)), 8)
        edges = collections.Counter(tuple(sorted((a, b))) for triangle in triangles
                                    for a, b in zip(triangle, triangle[1:]+triangle[:1]))
        boundary = {edge for edge, count in edges.items() if count == 1}
        self.assertEqual(boundary, {(0, 1), (1, 2), (2, 3), (0, 3),
                                    (4, 5), (5, 6), (6, 7), (4, 7)})
        self.assertTrue(all(count in (1, 2) for count in edges.values()))

    def test_area_and_winding_do_not_cover_the_old_sea_or_leave_a_gap(self):
        vertices, triangles = coast.geometry()
        area = 0
        for triangle in triangles:
            a, b, c = [vertices[i] for i in triangle]
            signed_twice = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            self.assertGreater(signed_twice, 0)
            area += signed_twice/2
            centroid = [sum(vertices[i][axis] for i in triangle)/3 for axis in [0, 1]]
            self.assertFalse(-155 < centroid[0] < 205 and -138 < centroid[1] < 222)
        self.assertTrue(math.isclose(area, 16000**2-360**2, abs_tol=.0001))

    def test_native_basis_and_flat_seam_height(self):
        bounds = coast.bounds_cm()
        self.assertEqual(bounds['min'][:2], [-797500., -804200.])
        self.assertEqual(bounds['max'][:2], [802500., 795800.])
        self.assertAlmostEqual(bounds['min'][2], -2)
        self.assertAlmostEqual(bounds['max'][2], -2)
        self.assertEqual(coast.unreal_cm((-155, 222, -.02)), [-15500, -22200, -2])

    def test_normal_fade_is_clamped_and_monotonic_at_close_and_horizon_ranges(self):
        distances = [-100, 0, 5000, 6000, 28000, 50000, 800000]
        values = [coast.fade_at_distance_cm(d) for d in distances]
        self.assertEqual(values[:4], [0, 0, 0, 0])
        self.assertEqual(values[-2:], [1, 1])
        self.assertEqual(values, sorted(values))
        self.assertAlmostEqual(values[4], .5)


if __name__ == '__main__':
    unittest.main()
