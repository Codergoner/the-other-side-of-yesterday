"""Pure geometry/policy contract. Does not import Unreal or Blender or write files."""
from pathlib import Path
import json
import math

PLAN = Path(__file__).resolve().parents[1] / 'ContentData/release_coast_candidate.json'


def policy():
    value = json.loads(PLAN.read_text(encoding='utf-8'))
    sea, extension, water = value['source_sea_box_blender_m'], value['extension'], value['water']
    assert value['map'] == '/Game/Quest/Maps/Verdant_Desktop'
    assert value['original_sea_actor'] == 'StaticMeshActor_69'
    assert sea == {'center': [25.0, 42.0, -0.12], 'dimensions': [360.0, 360.0, 0.20]}
    assert 180 < extension['outer_half_extent_m'] <= 8000
    assert extension['triangles'] == 8 and extension['new_actors'] == 1
    assert extension['material_slots'] == 1 and extension['new_collision_shapes'] == 0
    assert not extension['casts_shadow'] and not extension['offset_or_displacement']
    assert extension['common_to_both_eras']
    assert water['texture_samples'] == 2 and water['opaque']
    assert not any(water[k] for k in ['emissive', 'world_position_offset', 'scene_color_or_refraction'])
    assert 0 <= water['far_normal_strength'] <= water['near_normal_strength'] <= .5
    assert 0 < water['near_roughness'] <= water['far_roughness'] <= 1
    assert 0 <= water['specular'] <= .5
    assert water['distance_fade_end_cm'] > water['distance_fade_start_cm'] > 0
    assert math.isclose(sum(water['blend_weights']), 1)
    assert all(c > 0 for key in ['normal_wavelength_a_cm', 'normal_wavelength_b_cm'] for c in water[key])
    return value


def geometry(plan=None):
    """Four disjoint trapezoids. Inner edges exactly share the old top perimeter.

    Blender metres; exporter uses the already proven project basis X,-Y,Z and
    unit scale 100. No overlapping centre surface, skirts, bevels or collision.
    """
    plan = policy() if plan is None else plan
    center = plan['source_sea_box_blender_m']['center']
    dimensions = plan['source_sea_box_blender_m']['dimensions']
    x, y, z = center[0], center[1], center[2] + dimensions[2] / 2
    def corners(rx, ry):
        return [(x-rx, y-ry, z), (x+rx, y-ry, z), (x+rx, y+ry, z), (x-rx, y+ry, z)]
    half = plan['extension']['outer_half_extent_m']
    vertices = corners(dimensions[0]/2, dimensions[1]/2) + corners(half, half)
    triangles = []
    for i in range(4):
        j = (i+1) % 4
        triangles.extend([(i, i+4, j+4), (i, j+4, j)])
    return vertices, triangles


def unreal_cm(vertex):
    return [vertex[0]*100, -vertex[1]*100, vertex[2]*100]


def bounds_cm(plan=None):
    vertices, _ = geometry(plan)
    points = [unreal_cm(v) for v in vertices]
    return {side: [fn(p[axis] for p in points) for axis in range(3)]
            for side, fn in [('min', min), ('max', max)]}


def fade_at_distance_cm(distance, plan=None):
    """Reference for the shader's clamped distance interpolation; not a GPU test."""
    water = (policy() if plan is None else plan)['water']
    return min(1, max(0, (distance-water['distance_fade_start_cm']) /
                         (water['distance_fade_end_cm']-water['distance_fade_start_cm'])))
