"""Queued Blender authoring: two small original decorative wall groups only.

No existing scene or mesh is loaded. Generates an editable .blend and two FBXs
in a new versioned output/release_hero_kit directory. All geometry is opaque;
no collision, animation, physics, alpha masks, narrative symbols or characters.
Do not execute until root grants the serialized Blender writer queue.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
assert ROOT.name == 'Release_20261026'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
OUT = ROOT / 'output/release_hero_kit'
BUILD = OUT / 'builds' / STAMP
BUILD.mkdir(parents=True, exist_ok=False)
(BUILD / 'meshes').mkdir()
bpy.ops.wm.read_factory_settings(use_empty=True)
SCENE = bpy.context.scene
SCENE.name = 'Release original domestic wall detail'
SCENE.unit_settings.system = 'METRIC'
AUTHOR = bpy.data.collections.new('AUTHORING - editable closed components')
EXPORT = bpy.data.collections.new('EXPORT - two semantic groups, no collision')
SCENE.collection.children.link(AUTHOR)
SCENE.collection.children.link(EXPORT)
PARTS = {}
MATERIALS = {}
for name, color, roughness in [('Wood', (.25, .12, .055), .85), ('Ceramic', (.69, .60, .43), .60),
                                ('Terracotta', (.43, .19, .095), .88), ('Linen', (.21, .38, .49), .95),
                                ('Cream', (.71, .67, .54), .95)]:
    mat = bpy.data.materials.new('M_ReleaseHero_' + name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Roughness'].default_value = roughness
    MATERIALS[name] = mat


def uv_metric(data):
    data.update()
    layer = data.uv_layers.new(name='UV0_Metric')
    for face in data.polygons:
        axis = max(range(3), key=lambda index: abs(face.normal[index]))
        a, b = [(1, 2), (0, 2), (0, 1)][axis]
        for loop in face.loop_indices:
            point = data.vertices[data.loops[loop].vertex_index].co
            layer.data[loop].uv = (point[a] * .5, point[b] * .5)


def mesh(group, name, vertices, faces, material, smooth=False, bevel=0):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    data.materials.append(MATERIALS[material])
    uv_metric(data)
    obj = bpy.data.objects.new(name, data)
    AUTHOR.objects.link(obj)
    for polygon in data.polygons:
        polygon.use_smooth = smooth
    if bevel:
        modifier = obj.modifiers.new('Small rounded wear, real geometry', 'BEVEL')
        modifier.width = bevel
        modifier.segments = 3
    PARTS.setdefault(group, []).append(obj)
    return obj


def box(group, name, at, size, material='Wood', bevel=.004):
    x, y, z = [v * .5 for v in size]
    origin = Vector(at)
    vertices = [origin + Vector(v) for v in [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),
                                             (-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]]
    return mesh(group, name, vertices, [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], material, bevel=bevel)


def beam(group, name, a, b, width=.035, material='Wood'):
    a, b = Vector(a), Vector(b)
    direction = b - a
    rotation = direction.to_track_quat('Z', 'Y').to_matrix()
    middle = (a + b) * .5
    vertices = [middle + rotation @ Vector((x*width*.5, y*width*.5, z*direction.length*.5))
                for x,y,z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    return mesh(group, name, vertices, [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], material, bevel=.003)


def lathe(group, name, at, profile, material='Ceramic', sides=28):
    # Ordered outer -> rolled rim -> inner profile, closed bottom surfaces.
    vertices = [(at[0] + radius*math.cos(index*math.tau/sides),
                 at[1] + radius*math.sin(index*math.tau/sides), at[2] + z)
                for radius,z in profile for index in range(sides)]
    faces = [tuple(range(sides-1,-1,-1)), tuple((len(profile)-1)*sides+i for i in range(sides))]
    for ring in range(len(profile)-1):
        for index in range(sides):
            nxt = (index+1) % sides
            faces.append((ring*sides+index,ring*sides+nxt,(ring+1)*sides+nxt,(ring+1)*sides+index))
    obj = mesh(group, name, vertices, faces, material, smooth=True)
    # Cylindrical metric UVs avoid stretching the photographed ceramic palette.
    uv = obj.data.uv_layers.active
    for face in obj.data.polygons:
        for loop in face.loop_indices:
            vertex = obj.data.loops[loop].vertex_index
            ring, index = divmod(vertex, sides)
            uv.data[loop].uv = (index/sides, profile[ring][1]*.5)
    return obj


group = 'SM_ReleaseHero_WallShelf'
box(group, 'Shelf plank with softened edge', (0,-.12,.0225), (1.15,.24,.045), bevel=.007)
box(group, 'Back retaining strip', (0,-.018,.075), (1.15,.032,.07), bevel=.004)
for x in [-.43, .43]:
    beam(group, 'Wall shelf diagonal bracket', (x,-.018,-.16), (x,-.215,.005))
    box(group, 'Bracket wall cleat', (x,-.012,-.075), (.055,.025,.22), bevel=.003)
profile = [(.05,0),(.062,.012),(.083,.05),(.09,.11),(.081,.16),(.066,.18),(.065,.195),
           (.077,.199),(.078,.208),(.064,.213),(.058,.200),(.057,.180),(.068,.153),(.074,.105),(.066,.05),(.035,.026)]
lathe(group, 'Quiet hand-thrown storage jar', (.30,-.125,.046), profile, 'Terracotta')
lathe(group, 'Small cream ceramic pot', (-.055,-.117,.046), [(r*.78,z*.76) for r,z in profile], 'Ceramic')
bowl = [(.048,0),(.065,.009),(.090,.028),(.103,.060),(.108,.076),(.106,.085),
        (.098,.087),(.096,.077),(.091,.056),(.078,.031),(.048,.015)]
lathe(group, 'Low ceramic household bowl', (-.37,-.126,.046), bowl, 'Ceramic', sides=32)

group = 'SM_ReleaseHero_WovenPanel'
vertices = []
cols, rows = 17, 17
for row in range(rows):
    z = .32 - row*.64/(rows-1)
    for column in range(cols):
        x = -.39 + column*.78/(cols-1)
        depth = -.032 - .012*math.sin(column*math.tau*2.2/(cols-1)+row*.11) - .006*math.sin(row*math.pi/(rows-1))
        vertices.append((x,depth,z))
faces = [(row*cols+col,(row+1)*cols+col,(row+1)*cols+col+1,row*cols+col+1)
         for row in range(rows-1) for col in range(cols-1)]
panel = mesh(group, 'Original folded woven wall panel', vertices, faces, 'Linen', smooth=True)
thickness = panel.modifiers.new('Opaque cloth thickness', 'SOLIDIFY')
thickness.thickness = .004
beam(group, 'Wooden textile hanging rod', (-.44,-.025,.355), (.44,-.025,.355), .026)
for x in [-.29, 0, .29]:
    box(group, 'Textile hanging tab', (x,-.03,.334), (.034,.012,.073), 'Linen', bevel=.002)
for x in [-.345,.345]:
    box(group, 'Subtle cream woven border', (x,-.052,0), (.019,.006,.60), 'Cream', bevel=.001)
for index in range(25):
    x = -.375 + index*.75/24
    beam(group, 'Short woven fringe', (x,-.035,-.315), (x+.003*math.sin(index),-.04,-.365-(index%3)*.006), .0045, 'Cream')

# Combine evaluated copies only. Every authored component/modifier remains
# editable, and no UCX/UBX object or collision approximation is exported.
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
assets = []
for name, objects in PARTS.items():
    vertices, faces, uvs, face_materials, face_smooth, materials = [], [], [], [], [], []
    for obj in objects:
        data = obj.evaluated_get(deps).to_mesh()
        offset = len(vertices)
        vertices.extend(tuple(obj.matrix_world @ vertex.co) for vertex in data.vertices)
        for polygon in data.polygons:
            faces.append(tuple(offset+vertex for vertex in polygon.vertices))
            material = data.materials[polygon.material_index]
            if material not in materials:
                materials.append(material)
            face_materials.append(materials.index(material))
            face_smooth.append(polygon.use_smooth)
            uvs.extend(tuple(data.uv_layers.active.data[index].uv) for index in polygon.loop_indices)
        obj.evaluated_get(deps).to_mesh_clear()
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    for material in materials:
        data.materials.append(material)
    uv = data.uv_layers.new(name='UV0_Metric')
    for index, value in enumerate(uvs):
        uv.data[index].uv = value
    for polygon,index,smooth in zip(data.polygons,face_materials,face_smooth):
        polygon.material_index = index
        polygon.use_smooth = smooth
    obj = bpy.data.objects.new(name, data)
    EXPORT.objects.link(obj)
    data.calc_loop_triangles()
    path = BUILD/'meshes'/(name+'.fbx')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={'MESH'}, axis_forward='-Y', axis_up='Z',
                             global_scale=1, apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS',
                             use_mesh_modifiers=True, add_leaf_bones=False, bake_anim=False, path_mode='RELATIVE', embed_textures=False,
                             mesh_smooth_type='FACE')
    assets.append({'name': name, 'file': str(path.relative_to(OUT)).replace('\\','/'),
                   'triangles': len(data.loop_triangles), 'materials': [m.name for m in materials], 'collision_count': 0,
                   'bounds_m': {'min': [min(v.co[i] for v in data.vertices) for i in range(3)],
                                'max': [max(v.co[i] for v in data.vertices) for i in range(3)]},
                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
assert sum(a['triangles'] for a in assets) <= 12000
AUTHOR.hide_render = True
blend = BUILD/'Release_Domestic_Wall_Detail.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
manifest = {'schema': 1, 'build_stamp': STAMP, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'assets': assets, 'triangles': sum(a['triangles'] for a in assets), 'semantic_groups': 2,
            'axes': 'Blender X,Y,Z -> Unreal X,-Y,Z, instance yaw-90', 'units': 'metres',
            'blend_file': str(blend.relative_to(OUT)).replace('\\','/'), 'original_geometry_loaded': False,
            'collision': 'No collision mesh and no new blocking object',
            'provenance': 'Original small household geometry authored by this source; native material mapping uses separately documented existing/CC0 sources.',
            'placement_candidates_cm': [{'id': 'release.hero.wall_shelf', 'mesh': 'SM_ReleaseHero_WallShelf', 'position': [-1054,1500,1228], 'yaw': -90},
                                        {'id': 'release.hero.woven_panel', 'mesh': 'SM_ReleaseHero_WovenPanel', 'position': [-1054,1322,1250], 'yaw': -90}],
            'native_fit_collision_and_visibility_validated': False}
(BUILD/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n', encoding='utf-8')
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n', encoding='utf-8')
print(json.dumps({'success': True,'triangles': manifest['triangles'],'semantic_groups': 2,'blend': str(blend)}), flush=True)
