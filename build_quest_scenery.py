"""Author original, metric Quest scenery in a unique build; no city is loaded.

Run with Blender --background --python build_quest_scenery.py. This source writes
only output/quest_scenery and retains the four established distant land masses.
The sky is a conventional shader sky, never a photograph of city geometry.
"""
from pathlib import Path
from datetime import datetime, timezone
import bpy, bmesh, math, json, hashlib, struct, zlib
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
if ROOT.name != 'Quest_20261025':
    raise RuntimeError('Quest scenery authoring is restricted to the Quest copy')
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
OUT = ROOT / 'output' / 'quest_scenery'
BUILD = OUT / 'builds' / STAMP
for folder in ['meshes', 'textures', 'previews']:
    (BUILD / folder).mkdir(parents=True, exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
SC = bpy.context.scene
SC.name = 'Verdant Quest scenery - rounded real land and coastal atmosphere'
SC.unit_settings.system = 'METRIC'
SC.unit_settings.scale_length = 1
AUTH = bpy.data.collections.new('AUTHORING - four editable distant land masses')
SC.collection.children.link(AUTH)
EXP = bpy.data.collections.new('EXPORT - low cost scenery')
SC.collection.children.link(EXP)


def png(path, size, pixels):
    def chunk(kind, payload):
        return struct.pack('!I', len(payload)) + kind + payload + struct.pack('!I', zlib.crc32(kind + payload) & 0xffffffff)
    raw = b''.join(b'\0' + pixels[y * size * 3:(y + 1) * size * 3] for y in range(size))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', size, size, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 8)) + chunk(b'IEND', b''))


def texture(name, size, sample):
    data = bytearray()
    for y in range(size):
        for x in range(size):
            data.extend(max(0, min(255, round(c))) for c in sample(x / size, y / size))
    file = BUILD / 'textures' / (name + '.png')
    png(file, size, data)
    return str(file.relative_to(OUT)).replace('\\', '/')


def wood(u, v):
    grain = math.sin(math.tau * (u * 9 + .10 * math.sin(v * math.tau * 2))) * 4.5
    grain += math.sin(math.tau * (u * 31 + .035 * math.sin(v * math.tau * 3))) * 1.8
    grain += math.sin(math.tau * (u * 4 + v * 2)) * 1.2
    return (139 + grain, 103 + grain * .85, 69 + grain * .65)


def plaster(u, v):
    # Broad limewash variation without repeated black crack lines.
    n = math.sin(math.tau * (u * 2 + v)) * 2.4 + math.cos(math.tau * (u * 3 - v * 2)) * 1.5
    n += math.sin(math.tau * (u * 17 + v * 11)) * .7
    return (202 + n, 188 + n, 159 + n)


def normal_from_height(fn, u, v, strength):
    d = 1 / 512
    dx = (fn(u + d, v) - fn(u - d, v)) * strength
    dy = (fn(u, v + d) - fn(u, v - d)) * strength
    n = Vector((-dx, -dy, 1)).normalized()
    return tuple((c * .5 + .5) * 255 for c in n)


def water_height(u, v):
    return math.sin(math.tau * (u * 4 + v * 3)) * .62 + math.cos(math.tau * (u * 7 - v * 5)) * .24


def plaster_height(u, v):
    return math.sin(math.tau * (u * 19 + v * 13)) * .4 + math.cos(math.tau * (u * 31 - v * 23)) * .15


def cloud(u, v):
    # Authored seamless cloud coverage, not a photograph or projected backdrop.
    n = .5 + .16 * math.sin(math.tau * (u * 2 + v)) + .13 * math.cos(math.tau * (u - v * 2))
    n += .08 * math.sin(math.tau * (u * 5 + v * 3)) + .04 * math.cos(math.tau * (u * 9 - v * 7))
    coverage = max(0, min(1, (n - .54) / .25))
    return (coverage * 255,) * 3


TEXTURES = {
    'timber': texture('T_QuestTimber_BaseColor', 512, wood),
    'plaster': texture('T_QuestLimewash_BaseColor', 512, plaster),
    'plaster_normal': texture('T_QuestLimewash_Normal', 256, lambda u, v: normal_from_height(plaster_height, u, v, .30)),
    'water_normal': texture('T_QuestWater_Normal', 256, lambda u, v: normal_from_height(water_height, u, v, .52)),
    'cloud': texture('T_QuestSky_CloudCoverage', 256, cloud),
}


def srgb(value):
    return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4


def material(name, rgb, roughness=1):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bs = m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*(srgb(c / 255) for c in rgb), 1)
    bs.inputs['Roughness'].default_value = roughness
    return m


LAND = material('M_QuestDistantLand', (146, 159, 166), .97)
SKY = material('M_QuestCoastalSky', (116, 160, 188), 1)


def mesh(name, vertices, faces, mat, collection, sky=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    data.materials.append(mat)
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    color = data.color_attributes.new(name='QuestSceneryColor', type='FLOAT_COLOR', domain='CORNER')
    uv = data.uv_layers.new(name='UV0_Metric')
    for face in data.polygons:
        face.use_smooth = True
        for li in face.loop_indices:
            p = data.vertices[data.loops[li].vertex_index].co
            if sky:
                elevation = p.z / 2500
                gradient = max(0, min(1, abs(elevation) ** .48))
                cloud_band = max(0, min(1, (elevation - .04) * 5)) * max(0, min(1, (.84 - elevation) * 3))
                color.data[li].color = (gradient, cloud_band, 0, 1)
                vertex_index = data.loops[li].vertex_index
                uv.data[li].uv = ((vertex_index % 49) / 48, math.asin(max(-1, min(1, elevation))) / math.pi + .5)
            else:
                z = max(0, p.z)
                variation = .92 + .055 * math.sin(p.x * .09 + p.y * .07) + .025 * min(1, z / 50)
                color.data[li].color = (variation, variation, variation, 1)
                uv.data[li].uv = (p.x * .025, p.y * .025)
    return obj


land_parts = []
LAND_SPECS = [(-22, 154, 38, 38), (6, 188, 45, 65), (70, 190, 46, 42), (117, 174, 33, 49)]
for i, (cx, cy, radius, height) in enumerate(LAND_SPECS):
    vertices, faces = [], []
    count = 31
    for j in range(count):
        y = j / (count - 1) * 2 - 1
        for k in range(count):
            x = k / (count - 1) * 2 - 1
            envelope = max(0, 1 - x * x - y * y) ** .82
            ridge = .84 + .09 * math.sin(x * 2.8 + y * 1.8 + i * .7) + .065 * math.cos(x * 3.5 - y * 2.4 + i)
            detail = .32 * math.sin(x * 7 + y * 4 + i) * envelope
            z = min(height, height * envelope * ridge + detail) - 1
            vertices.append((cx + x * radius, cy + y * radius, z))
    for j in range(count - 1):
        for k in range(count - 1):
            a = j * count + k
            faces.extend([(a, a + 1, a + count + 1), (a, a + count + 1, a + count)])
    land_parts.append(mesh('Editable coastal massif %02d' % i, vertices, faces, LAND, AUTH))

# The whole distant set remains one semantic mesh, with the established origin.
vertices, faces = [], []
for obj in land_parts:
    offset = len(vertices)
    vertices.extend(v.co.copy() for v in obj.data.vertices)
    faces.extend(tuple(offset + n for n in f.vertices) for f in obj.data.polygons)
land = mesh('SM_QuestDistantLand', vertices, faces, LAND, EXP)

# A standard enclosing sky sphere, with gradient/cloud weights at vertices.
# No painted city, mountain, water or architecture appears in the sky material.
vertices, faces = [], []
segments, rings = 48, 24
for j in range(rings + 1):
    latitude = -math.pi * .5 + math.pi * j / rings
    for i in range(segments + 1):
        angle = math.tau * i / segments
        vertices.append((2500 * math.cos(latitude) * math.cos(angle), 2500 * math.cos(latitude) * math.sin(angle), 2500 * math.sin(latitude)))
for j in range(rings):
    for i in range(segments):
        a = j * (segments + 1) + i
        faces.extend([(a, a + 1, a + segments + 2), (a, a + segments + 2, a + segments + 1)])
sky = mesh('SM_QuestSkyDome', vertices, faces, SKY, EXP, True)

assets = []
for obj in [land, sky]:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    file = BUILD / 'meshes' / (obj.name + '.fbx')
    bpy.ops.export_scene.fbx(filepath=str(file), use_selection=True, object_types={'MESH'}, axis_forward='-Y', axis_up='Z', global_scale=1, apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', use_mesh_modifiers=True, add_leaf_bones=False, bake_anim=False, path_mode='RELATIVE', embed_textures=False, mesh_smooth_type='FACE')
    assets.append({'name': obj.name, 'file': str(file.relative_to(OUT)).replace('\\', '/'), 'triangles': len(obj.data.polygons), 'materials': [m.name for m in obj.data.materials], 'bounds_m': {'min': [min(v.co[c] for v in obj.data.vertices) for c in range(3)], 'max': [max(v.co[c] for v in obj.data.vertices) for c in range(3)]}, 'collision': False, 'smooth_normals': all(p.use_smooth for p in obj.data.polygons)})
assert assets[0]['triangles'] <= 8000
AUTH.hide_render = True
AUTH.hide_viewport = True
SC['Ownership'] = 'TOSOY.QuestVisualOwned; only versioned Quest scenery assets'
SC['BuildStamp'] = STAMP
bpy.ops.wm.save_as_mainfile(filepath=str(BUILD / 'Verdant_Quest_Scenery.blend'))
manifest = {'schema_version': 1, 'build_stamp': STAMP, 'units': 'meters', 'axes': 'same FBX basis as existing Harbor meshes; reuse old actor transform', 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'assets': assets, 'textures': TEXTURES, 'distant_land_specs': LAND_SPECS, 'blend_file': str((BUILD / 'Verdant_Quest_Scenery.blend').relative_to(OUT)).replace('\\', '/'), 'water': {'opaque': True, 'roughness': .30, 'specular': .25, 'metallic': 0, 'normal_pan_uv_per_second': [.008, .003]}, 'notes': ['Original meshes and maps are never opened or overwritten.', '7200-triangle rounded land preserves the four existing footprints and dominant height caps.', 'Sky is an analytic gradient/cloud shader on an enclosing sphere, not an image of scenery.', 'No engine, mobile-preview or headset result is implied by source generation.']}
encoded = json.dumps(manifest, indent=2)
(BUILD / 'manifest.json').write_text(encoded, encoding='utf-8')
(OUT / 'manifest.json').write_text(encoded, encoding='utf-8')
print('QUEST_SCENERY_COMPLETE', json.dumps({'manifest': str(OUT / 'manifest.json'), 'land_triangles': assets[0]['triangles'], 'sky_triangles': assets[1]['triangles']}), flush=True)
