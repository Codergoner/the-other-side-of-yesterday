"""Supporting cast builder v1 - The Other Side of Yesterday, Chapters I-II.

Builds the eight lineup roles (Harbor Clerk Enna, Boatwright, Fisherwoman,
Carpenter, Archivist, Baker, Shrine Keeper, Lantern Keeper) plus Tavi the
dockworker from the pinned MPFB 2.0.18 + CC0 MakeHuman sources already used for
Mother/Healer/Sela/Neri. Adds period wardrobe pieces, role props, a holding
pose with breathing/blink idle, review renders and a UE-ready FBX in the proven
centimetre-data/'Armature' representation.

Run inside Blender 5.2 (Text Editor > Run Script, or --background --python).
Which roles are built is read from output/supporting_cast/request.json.
Nothing in game_unreal is read or written by this script.
"""
import bpy
import bmesh
import sys
import os
import json
import math
import time
import types
import shutil
import hashlib
import importlib
import importlib.util
import traceback
from pathlib import Path
from datetime import datetime, timezone
from mathutils import Vector, Matrix, Quaternion
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

ROOT = Path(r'C:\Users\USER\OneDrive\Documents\ChatGPT\The other side of yesterday\development\Release_20261026')
if not ROOT.is_dir():
    ROOT = Path(bpy.path.abspath('//')).resolve()
sys.path.insert(0, str(ROOT))
import build_release_characters as base  # noqa: E402  (proven helpers, read-only use)
import build_release_unit_probe as units  # noqa: E402

SOURCES = base.SOURCES
VENDOR = base.VENDOR
SYSTEM = base.SYSTEM
DRESSES = base.DRESSES
SHIRTS = base.SHIRTS
SUITS = SOURCES / 'extracted/suits02_cc0'
PACKAGE = base.PACKAGE
OUT = ROOT / 'output/supporting_cast'
TEX = OUT / 'textures'
BUILDER_VERSION = 'supporting-cast-v5'
BUILDER_FILE = ROOT / 'build_supporting_cast_v1.py'

MATERIAL_RECIPES = {}
LOG_LINES = []
_LUM_CACHE = {}
_LOGFILE = None


def log(*parts):
    line = time.strftime('%H:%M:%S ') + ' '.join(str(p) for p in parts)
    print(line, flush=True)
    LOG_LINES.append(line)
    if _LOGFILE:
        with open(_LOGFILE, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')


def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def update():
    bpy.context.view_layer.update()


# ---------------------------------------------------------------- scene / MPFB
def clean_scene():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mat in list(bpy.data.materials):
        mat.use_fake_user = False
    for collection in [bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.actions,
                       bpy.data.cameras, bpy.data.lights, bpy.data.curves]:
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)
    for image in list(bpy.data.images):
        if image.users == 0:
            bpy.data.images.remove(image)
    try:
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    except Exception:
        pass
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.frame_start, scene.frame_end = 1, 120
    scene.render.fps = 30
    scene.frame_set(1)
    MATERIAL_RECIPES.clear()


def load_mpfb():
    """Private MPFB registration that is safe to repeat inside one GUI session."""
    module = sys.modules.get(PACKAGE)
    if module is not None and getattr(module, 'TOSOY_SC_REGISTERED', False):
        return module, importlib.import_module(PACKAGE + '.services')
    for key in list(bpy.context.preferences.addons.keys()):
        if 'mpfb' in key.lower() and key != PACKAGE:
            raise RuntimeError('Another MPFB add-on is enabled in this Blender session (' + key +
                               '). Disable it for this session and run again.')
    sys.dont_write_bytecode = True
    bpy.context.preferences.use_preferences_save = False
    home = SOURCES / 'private_runtime/mpfb_home_supporting_cast'
    home.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCES / 'extracted/faceunits01_cc0/targets', home / 'data/targets', dirs_exist_ok=True)
    for package in ['bl_ext', 'bl_ext.tosoy_private']:
        if package not in sys.modules:
            stub = types.ModuleType(package)
            stub.__path__ = []
            sys.modules[package] = stub
    if module is None:
        spec = importlib.util.spec_from_file_location(PACKAGE, VENDOR / '__init__.py',
                                                      submodule_search_locations=[str(VENDOR)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = module
        spec.loader.exec_module(module)
    preferences = importlib.import_module(PACKAGE + '._preferences').MpfbPreferences
    try:
        bpy.utils.register_class(preferences)
    except ValueError:
        pass
    entry = bpy.context.preferences.addons.get(PACKAGE)
    if entry is None:
        entry = bpy.context.preferences.addons.new()
        entry.module = PACKAGE
    entry.preferences.mpfb_user_data = str(home)
    entry.preferences.mh_auto_user_data = False
    module.register()
    module.TOSOY_SC_REGISTERED = True
    services = importlib.import_module(PACKAGE + '.services')
    assert Path(services.LocationService.get_user_home()).resolve() == home.resolve(), 'MPFB user home is not private'
    assert services.FaceService.is_faceunits01_installed(force_recheck=True), 'Face units missing'
    return module, services


def target_file(name):
    found = list((VENDOR / 'data/targets').rglob(name + '.target.gz'))
    assert len(found) == 1, ('Target not found uniquely', name, found)
    return found[0]


def asset_path(pack, relative):
    roots = {'system': SYSTEM, 'dress': DRESSES, 'shirts': SHIRTS, 'suits': SUITS}
    path = roots[pack] / relative
    assert path.is_file(), path
    header = '\n'.join(path.read_text(errors='replace').splitlines()[:30])
    assert 'CC0' in header and 'AGPL' not in header, ('Unresolved asset license', path)
    return path


def mhmat_texture(mhclo_path):
    """Diffuse texture named by the asset's own .mhmat (if any)."""
    folder = Path(mhclo_path).parent
    material = None
    for line in Path(mhclo_path).read_text(errors='replace').splitlines():
        parts = line.split()
        if parts and parts[0] == 'material' and len(parts) > 1:
            material = folder / parts[1]
    if material and material.is_file():
        for line in material.read_text(errors='replace').splitlines():
            parts = line.split(None, 1)
            if parts and parts[0] == 'diffuseTexture' and len(parts) > 1:
                path = folder / parts[1].strip()
                if path.is_file():
                    return path
    return None


# ---------------------------------------------------------------- materials
def _linear(values):
    import numpy as np
    values = np.asarray(values, dtype=np.float32)
    return np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)


def image_mean_luminance(path, alpha=False):
    """Mean linear luminance of an sRGB texture (alpha-covered texels only when masked)."""
    import numpy as np
    key = (str(path), bool(alpha))
    if key in _LUM_CACHE:
        return _LUM_CACHE[key]
    image = bpy.data.images.load(str(path), check_existing=True)
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    pixels = pixels.reshape(-1, 4)[::5]
    rgb = _linear(pixels[:, :3])
    lum = rgb[:, 0] * 0.2126 + rgb[:, 1] * 0.7152 + rgb[:, 2] * 0.0722
    if alpha:
        mask = pixels[:, 3] > 0.5
        if mask.any():
            lum = lum[mask]
    value = float(max(0.02, float(lum.mean())))
    _LUM_CACHE[key] = value
    return value


def _new_material(name):
    old = bpy.data.materials.get(name)
    if old:
        bpy.data.materials.remove(old)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_fake_user = True  # survive MPFB orphan purges until assigned
    return mat, mat.node_tree.nodes.get('Principled BSDF'), mat.node_tree


def _finish(mat, shader, recipe):
    shader.inputs['Roughness'].default_value = recipe.get('roughness', 0.85)
    shader.inputs['Metallic'].default_value = recipe.get('metallic', 0.0)
    shader.inputs['Specular IOR Level'].default_value = recipe.get('specular', 0.35)
    if recipe.get('emissive'):
        shader.inputs['Emission Color'].default_value = (*recipe['emissive'], 1.0)
        shader.inputs['Emission Strength'].default_value = recipe.get('emissive_strength', 4.0)
    if recipe.get('masked'):
        mat.surface_render_method = 'DITHERED'
    mat.use_backface_culling = not recipe.get('two_sided', False)
    MATERIAL_RECIPES[mat.name] = dict(recipe)
    return mat


def flat(name, color, roughness=0.85, metallic=0.0, specular=0.35, two_sided=False, emissive=None, emissive_strength=4.0):
    mat, shader, _ = _new_material(name)
    shader.inputs['Base Color'].default_value = (*color, 1.0)
    mat.diffuse_color = (*color, 1.0)
    return _finish(mat, shader, {'mode': 'flat', 'color': list(color), 'roughness': roughness, 'metallic': metallic,
                                 'specular': specular, 'two_sided': two_sided, 'emissive': list(emissive) if emissive else None,
                                 'emissive_strength': emissive_strength})


def textured(name, image_path, gain=(1, 1, 1), roughness=0.6, masked=False, two_sided=False, specular=0.35):
    """Natural texture (skin, eyes, natural hair) times a linear gain."""
    image_path = Path(image_path)
    assert image_path.is_file(), image_path
    mat, shader, tree = _new_material(name)
    tex = tree.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(image_path), check_existing=True)
    mul = tree.nodes.new('ShaderNodeVectorMath')
    mul.operation = 'MULTIPLY'
    tree.links.new(tex.outputs['Color'], mul.inputs[0])
    mul.inputs[1].default_value = tuple(gain)
    tree.links.new(mul.outputs['Vector'], shader.inputs['Base Color'])
    if masked:
        tree.links.new(tex.outputs['Alpha'], shader.inputs['Alpha'])
    mat.diffuse_color = (*gain, 1.0)
    return _finish(mat, shader, {'mode': 'texture', 'texture': str(image_path), 'texture_sha256': sha(image_path),
                                 'gain': list(gain), 'roughness': roughness, 'specular': specular,
                                 'masked': masked, 'two_sided': two_sided or masked})


def lumtint(name, image_path, tint, contrast=0.75, roughness=0.85, metallic=0.0, specular=0.35,
            masked=False, two_sided=False, tiling=(1.0, 1.0), normal=None, normal_strength=0.6):
    """Recolour any texture: keep its light/dark detail, replace its hue with `tint` (linear)."""
    image_path = Path(image_path)
    assert image_path.is_file(), image_path
    mean = image_mean_luminance(image_path, masked)
    mat, shader, tree = _new_material(name)
    coords = tree.nodes.new('ShaderNodeTexCoord')
    mapping = tree.nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (tiling[0], tiling[1], 1.0)
    tree.links.new(coords.outputs['UV'], mapping.inputs['Vector'])
    tex = tree.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(image_path), check_existing=True)
    tree.links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
    bw = tree.nodes.new('ShaderNodeRGBToBW')
    tree.links.new(tex.outputs['Color'], bw.inputs['Color'])
    chain = bw.outputs['Val']
    for operation, value in [('SUBTRACT', mean), ('MULTIPLY', contrast), ('ADD', mean), ('DIVIDE', mean), ('MAXIMUM', 0.0)]:
        node = tree.nodes.new('ShaderNodeMath')
        node.operation = operation
        tree.links.new(chain, node.inputs[0])
        node.inputs[1].default_value = value
        chain = node.outputs['Value']
    scale = tree.nodes.new('ShaderNodeVectorMath')
    scale.operation = 'SCALE'
    scale.inputs[0].default_value = tuple(tint)
    tree.links.new(chain, scale.inputs['Scale'])
    tree.links.new(scale.outputs['Vector'], shader.inputs['Base Color'])
    if masked:
        tree.links.new(tex.outputs['Alpha'], shader.inputs['Alpha'])
    mat.diffuse_color = (*tint, 1.0)
    recipe = {'mode': 'lumtint', 'texture': str(image_path), 'texture_sha256': sha(image_path), 'tint': list(tint),
              'mean_l': mean, 'contrast': contrast, 'tiling': list(tiling), 'roughness': roughness,
              'metallic': metallic, 'specular': specular, 'masked': masked, 'two_sided': two_sided or masked}
    if normal:
        recipe['normal'] = str(normal)
        recipe['normal_strength'] = normal_strength
    return _finish(mat, shader, recipe)


def detail(kind):
    return TEX / ('detail_' + kind + '.png')


def detail_normal(kind):
    path = TEX / ('normal_' + kind + '.png')
    return path if path.is_file() else None


def fabric(name, kind, tint, contrast=0.9, roughness=0.88, tiling=(4.0, 4.0), two_sided=True, metallic=0.0, specular=0.3):
    """Procedural fabric/leather/wood detail texture tinted to a target colour."""
    return lumtint(name, detail(kind), tint, contrast=contrast, roughness=roughness, metallic=metallic,
                   specular=specular, two_sided=two_sided, tiling=tiling, normal=detail_normal(kind))


# ---------------------------------------------------------------- geometry helpers
ARM_SKIP_LOG = []
RIG_BONES = set()  # set per role from the export rig; only skin-bone groups count as weights
ARM_ROOTS = {'upperarm', 'lowerarm', 'hand', 'thumb', 'index', 'middle', 'ring', 'pinky'}


def is_arm_bone(name):
    return name.split('_')[0] in ARM_ROOTS


def vertex_arm_fraction(obj, mesh=None):
    """Per-vertex share of skin weight on arm/hand/finger bones (0 for unweighted vertices).

    Pass the evaluated mesh when its vertex count can differ from obj.data (masks)."""
    names = {group.index: group.name for group in obj.vertex_groups}
    out = []
    for vertex in (mesh or obj.data).vertices:
        total = arm = 0.0
        for g in vertex.groups:
            name = names.get(g.group)
            # MPFB bodies also carry face-group/helper vertex groups; ignore non-bone groups.
            if name is None or (RIG_BONES and name not in RIG_BONES):
                continue
            total += g.weight
            if is_arm_bone(name):
                arm += g.weight
        out.append(arm / total if total > 1e-6 else 0.0)
    return out


def world_mesh_arrays(objects, skip_arms=False):
    """World-space triangles; skip_arms drops faces that follow the arms (sleeves, hands)."""
    deps = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for obj in objects:
        evaluated = obj.evaluated_get(deps)
        # Vertex groups are only kept on evaluated meshes when explicitly requested.
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=deps) if skip_arms else evaluated.to_mesh()
        arm = vertex_arm_fraction(obj, mesh) if skip_arms else None
        if arm is not None and not any(arm) and len(obj.data.vertices) == len(mesh.vertices):
            arm = vertex_arm_fraction(obj)
        offset = len(verts)
        matrix = obj.matrix_world.copy()
        verts.extend(matrix @ v.co for v in mesh.vertices)
        skipped = 0
        for p in mesh.polygons:
            if arm is not None and max(arm[i] for i in p.vertices) > 0.5:
                skipped += 1
                continue
            polys.append([offset + i for i in p.vertices])
        if skip_arms:
            ARM_SKIP_LOG.append((obj.name, len(mesh.polygons), skipped))
        evaluated.to_mesh_clear()
    return verts, polys


def surface_bvh(objects, skip_arms=False):
    verts, polys = world_mesh_arrays(objects, skip_arms)
    return BVHTree.FromPolygons(verts, polys, all_triangles=False, epsilon=0.0)


def cast(bvh, origin, direction, distance=2.0):
    direction = Vector(direction).normalized()
    location, normal, index, dist = bvh.ray_cast(Vector(origin), direction, distance)
    return location, normal


class BodyWeights:
    """Inverse-distance blend of the nearest body skin weights (bone groups only).

    Worn accessories sample a torso-only tree by default: arm, hand and finger vertices
    (which hang beside the hips in the rest pose) never donate weights, so belts, straps
    and aprons do not follow posed arms.
    """
    def __init__(self, body, rig):
        bones = {bone.name for bone in rig.data.bones}
        names = {group.index: group.name for group in body.vertex_groups}
        mesh = body.data
        self.kd = KDTree(len(mesh.vertices))
        self.weights = []
        matrix = body.matrix_world
        torso = []
        for vertex in mesh.vertices:
            co = matrix @ vertex.co
            self.kd.insert(co, vertex.index)
            row = {}
            for g in vertex.groups:
                name = names.get(g.group)
                if name in bones and g.weight > 1e-4:
                    row[name] = g.weight
            self.weights.append(row)
            total = sum(row.values())
            arm = sum(w for n, w in row.items() if is_arm_bone(n))
            if total > 0 and arm / total < 0.2:
                torso.append((co, vertex.index))
        self.kd.balance()
        self.kd_torso = KDTree(len(torso))
        for co, index in torso:
            self.kd_torso.insert(co, index)
        self.kd_torso.balance()

    def at(self, point, k=6, limit=4, arms=False, exclude=()):
        tree = self.kd if arms else self.kd_torso
        total = {}
        for co, index, dist in tree.find_n(Vector(point), k):
            factor = 1.0 / (dist + 0.002)
            for name, weight in self.weights[index].items():
                if name in exclude or (not arms and is_arm_bone(name)):
                    continue
                total[name] = total.get(name, 0.0) + weight * factor
        top = sorted(total.items(), key=lambda kv: -kv[1])[:limit]
        norm = sum(w for _, w in top)
        return {n: w / norm for n, w in top} if norm > 0 else {'spine_03' if 'head' in exclude else 'pelvis': 1.0}


def blend_weights(a, b, t):
    out = {}
    for name, w in a.items():
        out[name] = out.get(name, 0.0) + w * (1 - t)
    for name, w in b.items():
        out[name] = out.get(name, 0.0) + w * t
    s = sum(out.values()) or 1.0
    return {n: w / s for n, w in out.items()}


class Geo:
    """Accumulates vertices, faces and per-corner UVs before creating one object."""
    def __init__(self):
        self.verts, self.faces, self.uvs = [], [], []

    def add(self, verts, faces, uvs):
        offset = len(self.verts)
        self.verts.extend(Vector(v) for v in verts)
        self.faces.extend(tuple(i + offset for i in f) for f in faces)
        self.uvs.extend(uvs)
        return self

    def transform(self, matrix, start=0):
        for i in range(start, len(self.verts)):
            self.verts[i] = matrix @ self.verts[i]
        return self


def grid(G, U, V, close_i=False, close_j=False, flip=False):
    """G[i][j] positions; U has nj(+1 if close_j) entries, V has ni(+1 if close_i)."""
    ni, nj = len(G), len(G[0])
    verts = [p for row in G for p in row]
    faces, uvs = [], []
    for i in range(ni if close_i else ni - 1):
        for j in range(nj if close_j else nj - 1):
            i2, j2 = (i + 1) % ni, (j + 1) % nj
            quad = (i * nj + j, i * nj + j2, i2 * nj + j2, i2 * nj + j)
            uv = ((U[j], V[i]), (U[j + 1], V[i]), (U[j + 1], V[i + 1]), (U[j], V[i + 1]))
            if flip:
                quad, uv = quad[::-1], uv[::-1]
            faces.append(quad)
            uvs.append(uv)
    return verts, faces, uvs


def cumulative(points, closed=False):
    out = [0.0]
    for a, b in zip(points, points[1:]):
        out.append(out[-1] + (b - a).length)
    if closed:
        out.append(out[-1] + (points[0] - points[-1]).length)
    return out


def path_frames(points, up_hints=None):
    """Tangent-aligned frames (normal, binormal); normal prefers up_hints[i] (e.g. surface normal)."""
    frames = []
    n = len(points)
    for i in range(n):
        a, b = points[max(i - 1, 0)], points[min(i + 1, n - 1)]
        tangent = (b - a).normalized() if (b - a).length > 1e-8 else Vector((0, 0, 1))
        hint = Vector(up_hints[i]) if up_hints else Vector((0, 0, 1))
        if abs(hint.normalized().dot(tangent)) > 0.95:
            hint = Vector((1, 0, 0)) if abs(tangent.x) < 0.9 else Vector((0, 1, 0))
        normal = (hint - tangent * hint.dot(tangent)).normalized()
        binormal = tangent.cross(normal).normalized()
        frames.append((tangent, normal, binormal))
    return frames


def tube(points, radius, sides=10, closed=False, caps=True, radii=None, normals=None):
    frames = path_frames(points, normals)
    G = []
    for i, (p, (t, n, b)) in enumerate(zip(points, frames)):
        r = radii[i] if radii else radius
        G.append([p + (n * math.cos(a) + b * math.sin(a)) * r
                  for a in [2 * math.pi * k / sides for k in range(sides)]])
    U = [k / sides for k in range(sides + 1)]
    L = cumulative(points, closed)
    V = [l / (2 * math.pi * radius * 2) for l in L]
    verts, faces, uvs = grid(G, U, V, close_i=closed, close_j=True)
    if caps and not closed:
        for end, flip in [(0, True), (len(points) - 1, False)]:
            center_index = len(verts)
            verts.append(points[end])
            ring = [end * sides + k for k in range(sides)]
            for k in range(sides):
                a, b = ring[k], ring[(k + 1) % sides]
                face = (a, b, center_index) if not flip else (b, a, center_index)
                faces.append(face)
                uvs.append(((0.5, 0.5), (0.5, 0.5), (0.5, 0.5)))
    return verts, faces, uvs


def ribbon(points, normals, width, thickness=0.004, tiling=8.0):
    """Flat strap following a surface: normals are outward surface normals per point."""
    frames = path_frames(points, normals)
    hw, ht = width / 2, thickness / 2
    profile = [(-hw, -ht), (hw, -ht), (hw, ht), (-hw, ht)]
    G = []
    for p, (t, n, b) in zip(points, frames):
        G.append([p + b * x + n * (y + ht) for x, y in profile])
    L = cumulative(points)
    U = [0.0, 0.5, 0.55, 1.0, 1.05]
    V = [l * tiling for l in L]
    return grid(G, U, V, close_j=True)


def box(center, axes, half, bevel=0.0):
    """Oriented box; axes = (ax, ay, az) unit vectors, half = (hx, hy, hz)."""
    ax, ay, az = [Vector(a).normalized() for a in axes]
    c = Vector(center)
    corners = []
    for sz in (-1, 1):
        for sy in (-1, 1):
            for sx in (-1, 1):
                corners.append(c + ax * half[0] * sx + ay * half[1] * sy + az * half[2] * sz)
    faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    uvs = [((0, 0), (1, 0), (1, 1), (0, 1))] * 6
    return corners, faces, uvs


def ellipsoid(center, axes, radii, u_segments=16, v_segments=10):
    ax, ay, az = [Vector(a).normalized() for a in axes]
    c = Vector(center)
    G = []
    for i in range(v_segments + 1):
        theta = math.pi * i / v_segments
        row = []
        for j in range(u_segments):
            phi = 2 * math.pi * j / u_segments
            row.append(c + ax * (radii[0] * math.sin(theta) * math.cos(phi))
                       + ay * (radii[1] * math.sin(theta) * math.sin(phi))
                       + az * (radii[2] * math.cos(theta)))
        G.append(row)
    U = [j / u_segments for j in range(u_segments + 1)]
    V = [i / v_segments for i in range(v_segments + 1)]
    return grid(G, U, V, close_j=True)


def cylinder(p0, p1, r0, r1=None, sides=16, caps=True):
    r1 = r0 if r1 is None else r1
    return tube([Vector(p0), Vector(p1)], r0, sides=sides, caps=caps, radii=[r0, r1])


def torus(center, axis, major, minor, segments=32, sides=10):
    axis = Vector(axis).normalized()
    a = axis.orthogonal().normalized()
    b = axis.cross(a).normalized()
    pts = [Vector(center) + (a * math.cos(t) + b * math.sin(t)) * major
           for t in [2 * math.pi * k / segments for k in range(segments)]]
    normals = [(p - Vector(center)).normalized() for p in pts]
    return tube(pts, minor, sides=sides, closed=True, caps=False, normals=normals)


def make_part(name, geo, material, rig, weights, smooth=True, recalc=True):
    """Create a skinned mesh object from a Geo; weights is a dict or a per-vertex list/callable."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in geo.verts], [], [tuple(f) for f in geo.faces])
    mesh.update()
    layer = mesh.uv_layers.new(name='UVMap')
    for poly in mesh.polygons:
        corner_uvs = geo.uvs[poly.index]
        for k, loop_index in enumerate(poly.loop_indices):
            layer.data[loop_index].uv = corner_uvs[k] if k < len(corner_uvs) else (0.0, 0.0)
    if recalc:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()
    mesh.materials.append(material)
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = rig
    obj.matrix_parent_inverse = rig.matrix_world.inverted()
    groups = {}
    for index, vertex in enumerate(geo.verts):
        if callable(weights):
            row = weights(index, vertex)
        elif isinstance(weights, dict):
            row = weights
        else:
            row = weights[index]
        for bone, weight in row.items():
            if weight <= 1e-4:
                continue
            group = groups.get(bone)
            if group is None:
                group = obj.vertex_groups.new(name=bone)
                groups[bone] = group
            group.add([index], float(weight), 'REPLACE')
    modifier = obj.modifiers.new('Armature', 'ARMATURE')
    modifier.object = rig
    return obj


def push_outward(obj, distance, exclude_top_z=None):
    """Offset a fitted garment along its vertex normals (layering over another garment)."""
    mesh = obj.data
    keys = mesh.shape_keys.key_blocks if mesh.shape_keys else None
    mesh.calc_normals_split() if hasattr(mesh, 'calc_normals_split') else None
    normals = [v.normal.copy() for v in mesh.vertices]
    for v, n in zip(mesh.vertices, normals):
        v.co += n * distance
    if keys:
        for key in keys:
            for i, n in enumerate(normals):
                key.data[i].co += n * distance
    mesh.update()


def bone_head(rig, name):
    return rig.matrix_world @ rig.data.bones[name].head_local


def bone_tail(rig, name):
    return rig.matrix_world @ rig.data.bones[name].tail_local


# ---------------------------------------------------------------- body landmarks
class Ctx:
    """Per-role build context: export rig/body, skin weights and landmarks (rest pose, metres)."""
    def __init__(self, role, rig, body, garments, hair, eyes):
        self.role, self.rig, self.body = role, rig, body
        self.garments, self.hair, self.eyes = garments, hair, eyes
        RIG_BONES.clear()
        RIG_BONES.update(bone.name for bone in rig.data.bones)
        self.bw = BodyWeights(body, rig)
        b = lambda n: bone_head(rig, n)
        self.spine1, self.spine2, self.spine3 = b('spine_01'), b('spine_02'), b('spine_03')
        self.neck, self.head = b('neck_01'), b('head')
        self.head_tail = bone_tail(rig, 'head')
        self.sh = {'l': b('upperarm_l'), 'r': b('upperarm_r')}
        self.hip = {'l': b('thigh_l'), 'r': b('thigh_r')}
        self.knee = {'l': b('calf_l'), 'r': b('calf_r')}
        self.ankle = {'l': b('foot_l'), 'r': b('foot_r')}
        zs = [(body.matrix_world @ v.co).z for v in body.data.vertices]
        ground_zs = list(zs)
        for obj in garments:
            ground_zs.extend((obj.matrix_world @ v.co).z for v in obj.data.vertices)
        self.ground, self.top = min(ground_zs), max(zs)
        self.height = self.top - self.ground
        head_pts = []
        for threshold in (0.95, 0.75, 0.5):
            head_pts = [body.matrix_world @ v.co for i, v in enumerate(body.data.vertices)
                        if self.bw.weights[i].get('head', 0) > threshold]
            if len(head_pts) > 200:
                break
        if not head_pts:
            head_pts = [self.head, self.head_tail]
        xs, ys, zz = [p.x for p in head_pts], [p.y for p in head_pts], [p.z for p in head_pts]
        self.head_center = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zz) + max(zz)) / 2))
        self.head_radii = Vector(((max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2, (max(zz) - min(zz)) / 2))
        self.axis_y = (self.spine1.y + self.spine3.y) / 2
        self._bvh = {}
        self.parts = []
        self.notes = []

    def bvh(self, key='clothed'):
        if key not in self._bvh:
            if key == 'clothed':
                objs = [self.body] + list(self.garments)
            elif key == 'head':
                objs = [self.body] + list(self.hair)
            elif key == 'garments':
                objs = list(self.garments) or [self.body]
            else:
                objs = [self.body]
            self._bvh[key] = surface_bvh(objs, skip_arms=True)
        return self._bvh[key]

    def invalidate(self):
        self._bvh.clear()

    def front_y(self, x, z, key='clothed', default=None):
        loc, nor = cast(self.bvh(key), (x, -1.5, z), (0, 1, 0), 3.0)
        return (loc.y, nor) if loc is not None else (default, None)

    def back_y(self, x, z, key='clothed', default=None):
        loc, nor = cast(self.bvh(key), (x, 1.5, z), (0, -1, 0), 3.0)
        return (loc.y, nor) if loc is not None else (default, None)

    def radial(self, z, angle, key='clothed', center=None, max_r=0.6):
        c = Vector((0.0, self.axis_y, z)) if center is None else Vector((center[0], center[1], z))
        d = Vector((math.cos(angle), math.sin(angle), 0.0))
        loc, nor = cast(self.bvh(key), c + d * max_r, -d, max_r)
        return (loc, d) if loc is not None else (None, d)

    def project_to_surface(self, point, key='clothed', center=None, offset=0.004):
        """Project roughly onto the outer surface along the horizontal radial direction."""
        point = Vector(point)
        c = Vector((0.0, self.axis_y, point.z)) if center is None else Vector(center)
        d = Vector((point.x - c.x, point.y - c.y, 0.0))
        if d.length < 1e-6:
            d = Vector((0, -1, 0))
        d.normalize()
        loc, nor = cast(self.bvh(key), Vector((c.x, c.y, point.z)) + d * 0.6, -d, 0.6)
        if loc is None:
            return point, d
        return loc + d * offset, d

    def add(self, obj, label):
        self.parts.append((label, obj.name))
        return obj


def _smooth_ring(values, passes=2):
    n = len(values)
    for _ in range(passes):
        values = [(values[(i - 2) % n] + 2 * values[(i - 1) % n] + 3 * values[i] + 2 * values[(i + 1) % n]
                   + values[(i + 2) % n]) / 9.0 for i in range(n)]
    return values


def _fill_missing(values):
    n = len(values)
    known = [i for i, v in enumerate(values) if v is not None]
    if not known:
        return None
    out = list(values)
    for i in range(n):
        if out[i] is None:
            nearest = min(known, key=lambda k: min(abs(k - i), n - abs(k - i)))
            out[i] = values[nearest]
    return out


def ring_radii(ctx, z, n=48, key='clothed', center=None, max_r=0.6):
    c = Vector((0.0, ctx.axis_y)) if center is None else Vector(center[:2])
    radii = []
    for k in range(n):
        a = 2 * math.pi * k / n
        loc, d = ctx.radial(z, a, key, center=(c.x, c.y), max_r=max_r)
        radii.append((Vector((loc.x, loc.y)) - c).length if loc is not None else None)
    radii = _fill_missing(radii)
    return _smooth_ring(radii) if radii else None, c


# ---------------------------------------------------------------- garments
def belt(ctx, name, material, z, width=0.045, thickness=0.009, offset=0.004, n=48, buckle=None, center=None,
         key='clothed', max_r=0.6):
    lower, c = ring_radii(ctx, z - width / 2, n, key, center, max_r)
    upper, _ = ring_radii(ctx, z + width / 2, n, key, center, max_r)
    middle, _ = ring_radii(ctx, z, n, key, center, max_r)
    if not lower or not upper:
        ctx.notes.append(name + ': no surface found at z=%.3f' % z)
        return None
    r_in = [max(a, b, m) + offset for a, b, m in zip(lower, upper, middle)]
    G = []
    for k in range(n):
        a = 2 * math.pi * k / n
        d = Vector((math.cos(a), math.sin(a), 0.0))
        p = lambda r, h: Vector((c.x, c.y, h)) + d * r
        G.append([p(r_in[k], z - width / 2), p(r_in[k] + thickness, z - width / 2),
                  p(r_in[k] + thickness, z + width / 2), p(r_in[k], z + width / 2)])
    circumference = sum(2 * math.pi * r for r in r_in) / n
    U = [0.0, 0.1, 0.9, 1.0, 1.1]
    V = [circumference * k / n / 0.25 for k in range(n + 1)]
    verts, faces, uvs = grid(G, U, V, close_i=True, close_j=True)
    geo = Geo().add(verts, faces, uvs)
    obj = make_part(name, geo, material, ctx.rig, lambda i, v: ctx.bw.at(v))
    ctx.add(obj, 'belt')
    if buckle:
        k = int(n * 0.75)  # front: angle 270 deg
        a = 2 * math.pi * k / n
        d = Vector((math.cos(a), math.sin(a), 0.0))
        centre = Vector((c.x, c.y, z)) + d * (r_in[k] + thickness + 0.003)
        side = Vector((0, 0, 1)).cross(d).normalized()
        bgeo = Geo().add(*box(centre, (side, d, Vector((0, 0, 1))), (0.026, 0.004, width * 0.62)))
        ctx.add(make_part(name + '_Buckle', bgeo, buckle, ctx.rig, ctx.bw.at(centre), smooth=False), 'buckle')
    return obj


def apron(ctx, name, material, top_z, bottom_z, half_top, half_bottom, bib_top_z=None, bib_half=0.11,
          offset=0.012, rows=26, cols=15, waist_band=True, band_material=None):
    """Front apron: bib follows the chest; the skirt hangs from its widest point (cumulative drape)."""
    zs = []
    if bib_top_z:
        bib_rows = 8
        zs += [bib_top_z - (bib_top_z - top_z) * r / bib_rows for r in range(bib_rows)]
    skirt_start = len(zs)
    zs += [top_z - (top_z - bottom_z) * r / (rows - 1) for r in range(rows)]
    hip_z = (ctx.hip['l'].z + ctx.hip['r'].z) / 2
    Y, X = [], []
    for r, z in enumerate(zs):
        if r < skirt_start:
            t = r / max(1, skirt_start)
            hw = bib_half * (0.92 + 0.08 * t)
        else:
            t = (r - skirt_start) / max(1, rows - 1)
            hw = half_top + (half_bottom - half_top) * (t ** 0.8)
        xs = [hw * (2 * c / (cols - 1) - 1) for c in range(cols)]
        ys = [ctx.front_y(x, z)[0] for x in xs]
        if all(y is None for y in ys):
            ys = [Y[-1][c] if Y else -0.15 for c in range(cols)]
        else:
            known = [y for y in ys if y is not None]
            ys = [y if y is not None else max(known) for y in ys]
        X.append(xs)
        Y.append(ys)
    # skirt: bridge leg gaps (row dilation) and hang (cumulative minimum downward)
    for r in range(skirt_start, len(zs)):
        row = Y[r]
        Y[r] = [min(row[max(0, c - 2):c + 3]) for c in range(cols)]
        if r > skirt_start:
            Y[r] = [min(Y[r][c], Y[r - 1][c]) for c in range(cols)]
    # smooth across columns and rows
    for _ in range(2):
        for r in range(len(zs)):
            row = Y[r]
            Y[r] = [(row[max(c - 1, 0)] + 2 * row[c] + row[min(c + 1, cols - 1)]) / 4 for c in range(cols)]
    G = [[Vector((X[r][c], Y[r][c] - offset, zs[r])) for c in range(cols)] for r in range(len(zs))]
    U = [x / 0.25 for x in X[-1]]
    V = [z / 0.25 for z in zs]
    verts, faces, uvs = grid(G, U, V, flip=True)

    def weights(i, v):
        if v.z >= hip_z:
            return ctx.bw.at(v + Vector((0, offset + 0.02, 0)))
        side = max(-1.0, min(1.0, v.x / max(half_bottom, 0.05)))
        drop = max(0.0, min(1.0, (hip_z - v.z) / 0.45))
        thigh = 0.38 * drop + 0.12
        return {'pelvis': 1 - thigh, 'thigh_l': thigh * (0.5 + 0.5 * side), 'thigh_r': thigh * (0.5 - 0.5 * side)}
    obj = make_part(name, Geo().add(verts, faces, uvs), material, ctx.rig, weights, recalc=False)
    ctx.add(obj, 'apron')
    if waist_band:
        belt(ctx, name + '_Ties', band_material or material, top_z + 0.01, width=0.028, thickness=0.004, offset=0.006)
    if bib_top_z:
        neck_strap(ctx, name + '_NeckStrap', band_material or material, bib_top_z, bib_half * 0.9)
    return obj


def under_panel(ctx, name, material, top_z, bottom_z, half_top, half_bottom, offset=0.004, rows=12, cols=9):
    """Inner front layer fitted to the skin (under any open neckline), torso-weighted."""
    zs = [top_z - (top_z - bottom_z) * r / (rows - 1) for r in range(rows)]
    G = []
    for r, z in enumerate(zs):
        t = r / (rows - 1)
        hw = half_top + (half_bottom - half_top) * t
        row = []
        for c in range(cols):
            x = hw * (2 * c / (cols - 1) - 1)
            y, _ = ctx.front_y(x, z, key='body')
            row.append(Vector((x, (y if y is not None else ctx.axis_y - 0.1) - offset, z)))
        G.append(row)
    U = [c / (cols - 1) for c in range(cols)]
    V = [r / (rows - 1) * 2 for r in range(rows)]
    verts, faces, uvs = grid(G, U, V, flip=True)
    obj = make_part(name, Geo().add(verts, faces, uvs), material, ctx.rig,
                    lambda i, v: ctx.bw.at(v + Vector((0, offset + 0.02, 0)), exclude=('head',)), recalc=False)
    return ctx.add(obj, 'under_panel')


def neck_strap(ctx, name, material, bib_top_z, half):
    """Loop from the bib's top corners up and around the back of the neck."""
    nb = ctx.neck
    centre = (0.0, nb.y)
    sides = {}
    for side in (1, -1):
        seq = []
        y0, _ = ctx.front_y(side * half, bib_top_z)
        seq.append(Vector((side * half, (y0 if y0 is not None else -0.1) - 0.012, bib_top_z)))
        for t in [0.3, 0.6, 0.85]:
            z = bib_top_z + (nb.z + 0.015 - bib_top_z) * t
            x = side * (half + (0.06 - half) * t)
            y1, _ = ctx.front_y(x, z)
            seq.append(Vector((x, (y1 if y1 is not None else -0.08) - 0.006, z)))
        for a in [-55.0, -15.0, 25.0, 60.0]:
            ang = math.radians(a)
            p = Vector((side * 0.075 * math.cos(ang), nb.y + 0.075 * math.sin(ang), nb.z + 0.02 + 0.02 * (a + 55) / 115))
            q, _ = ctx.project_to_surface(p, center=(centre[0], centre[1], p.z), offset=0.005)
            seq.append(q)
        sides[side] = seq
    back = Vector((0.0, nb.y + 0.09, nb.z + 0.042))
    qb, _ = ctx.project_to_surface(back, center=(0.0, nb.y, back.z), offset=0.005)
    pts = sides[1] + [qb] + list(reversed(sides[-1]))
    normals = []
    for p in pts:
        d = Vector((p.x, p.y - nb.y, 0.0))
        normals.append(d.normalized() if d.length > 1e-6 else Vector((0, -1, 0)))
    verts, faces, uvs = ribbon(pts, normals, 0.022, 0.003)
    obj = make_part(name, Geo().add(verts, faces, uvs), material, ctx.rig,
                    lambda i, v: ctx.bw.at(v, exclude=('head',)))
    return ctx.add(obj, 'strap')


def neck_scarf(ctx, name, material, tube=0.017, lift=0.03, drape=None, drape_len=0.16, tail_len=0.30, knot_material=None):
    """Soft roll around the neck base (front lower than back) with an optional drape or two tails."""
    base_z = ctx.neck.z + lift
    n = 40
    ring, normals = [], []
    for k in range(n):
        a = 2 * math.pi * k / n
        front = -math.sin(a)  # 1 at the front (a = 270 deg)
        z = base_z - 0.025 * max(0.0, front) + 0.012 * max(0.0, -front)
        loc, d = ctx.radial(z, a, center=(0.0, ctx.neck.y), max_r=0.13)
        r = (Vector((loc.x, loc.y)) - Vector((0.0, ctx.neck.y))).length if loc is not None else 0.065
        r = min(max(r, 0.045), 0.105)
        ring.append((d, r, z))
    rs = _smooth_ring([r for _, r, _ in ring])
    path = [Vector((0.0, ctx.neck.y, z)) + d * (r + tube * 0.85) for (d, _, z), r in zip(ring, rs)]
    norms = [d for d, _, _ in ring]
    verts, faces, uvs = tube_closed(path, tube, norms)
    neck_w = lambda i, v: ctx.bw.at(v, exclude=('head',))
    obj = make_part(name, Geo().add(verts, faces, uvs), material, ctx.rig, neck_w)
    ctx.add(obj, 'scarf')
    front_k = int(n * 0.75)
    knot_c = path[front_k] + Vector((0, -tube * 0.6, -0.008))
    ks = max(0.6, min(1.3, tube / 0.017))
    kgeo = Geo().add(*ellipsoid(knot_c, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.026 * ks, 0.017 * ks, 0.022 * ks), 12, 8))
    ctx.add(make_part(name + '_Knot', kgeo, knot_material or material, ctx.rig, ctx.bw.at(knot_c, exclude=('head',))), 'knot')
    if drape == 'triangle':
        rows, cols = 8, 9
        top_z = knot_c.z - 0.01
        G = []
        for r in range(rows):
            t = r / (rows - 1)
            z = top_z - drape_len * t
            hw = 0.075 * (1 - t) + 0.004
            row = []
            for c in range(cols):
                x = hw * (2 * c / (cols - 1) - 1)
                y, _ = ctx.front_y(x, z)
                row.append(Vector((x, (y if y is not None else knot_c.y) - 0.007, z)))
            G.append(row)
        U = [c / (cols - 1) for c in range(cols)]
        V = [r / (rows - 1) for r in range(rows)]
        verts, faces, uvs = grid(G, U, V, flip=True)
        ctx.add(make_part(name + '_Drape', Geo().add(verts, faces, uvs), material, ctx.rig,
                          lambda i, v: ctx.bw.at(v + Vector((0, 0.02, 0)), exclude=('head',)), recalc=False), 'drape')
    elif drape == 'tails':
        for side, sx in (('L', 0.035), ('R', -0.045)):
            pts, nrm = [], []
            for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
                z = knot_c.z - 0.02 - tail_len * t
                x = sx + 0.02 * t * (1 if sx > 0 else -1)
                y, _ = ctx.front_y(x, z)
                pts.append(Vector((x, (y if y is not None else knot_c.y) - 0.008, z)))
                nrm.append(Vector((0, -1, 0)))
            verts, faces, uvs = ribbon(pts, nrm, 0.065, 0.004, tiling=4)
            ctx.add(make_part(name + '_Tail' + side, Geo().add(verts, faces, uvs), material, ctx.rig,
                              lambda i, v: ctx.bw.at(v + Vector((0, 0.02, 0)), exclude=('head',))), 'tail')
    return obj


def tube_closed(points, radius, normals, sides=10):
    return tube(points, radius, sides=sides, closed=True, caps=False, normals=normals)


def head_cover(ctx, name, material, kind='kerchief', offset=0.006, knot=True, tails=True, brim_material=None):
    """Kerchief/bandana covering the top and back of the head, or a flat cap with a short brim."""
    hc = ctx.head_center
    bvh = ctx.bvh('head')
    n_phi, n_rows = 40, 14
    if kind == 'cap':
        e_front, e_back, e_side = 20.0, -2.0, 8.0
        offset = 0.012
    elif kind == 'bandana':
        e_front, e_back, e_side = 28.0, -30.0, 2.0
    else:  # kerchief: covers to the nape
        e_front, e_back, e_side = 24.0, -42.0, -6.0

    def e_min(phi):
        f = -math.sin(phi)  # +1 front, -1 back
        if f >= 0:
            return e_side + (e_front - e_side) * f
        return e_side + (e_back - e_side) * (-f)

    def surface(phi, e):
        d = Vector((math.cos(math.radians(e)) * math.cos(phi), math.cos(math.radians(e)) * math.sin(phi), math.sin(math.radians(e))))
        loc, nor = cast(bvh, hc + d * 0.45, -d, 0.45)
        if loc is None:
            loc = hc + d * max(ctx.head_radii)
        return loc + d * offset, d
    G = []
    for r in range(1, n_rows + 1):
        row = []
        for k in range(n_phi):
            phi = 2 * math.pi * k / n_phi
            e = 90 - (90 - e_min(phi)) * r / n_rows
            p, d = surface(phi, e)
            row.append(p)
        G.append(row)
    if kind == 'cap':
        top = max(p.z for row in G for p in row)
        for row in G:
            for p in row:
                if p.z > top - 0.035:
                    p.z = top - 0.035 + (p.z - (top - 0.035)) * 0.35
    apex, _ = surface(0.0, 90.0)
    if kind == 'cap':
        apex.z = min(apex.z, max(p.z for row in G for p in row) + 0.004)
    U = [k / n_phi * 3.0 for k in range(n_phi + 1)]
    V = [r / n_rows * 1.2 for r in range(n_rows)]
    verts, faces, uvs = grid(G, U, V, close_j=True)
    # apex fan
    apex_i = len(verts)
    verts.append(apex)
    for k in range(n_phi):
        a, b = k, (k + 1) % n_phi
        faces.append((b, a, apex_i))
        uvs.append(((U[k + 1], 0.0), (U[k], 0.0), (U[k], 0.0)))
    geo = Geo().add(verts, faces, uvs)
    obj = make_part(name, geo, material, ctx.rig, {'head': 1.0})
    ctx.add(obj, kind)
    if kind == 'cap':
        # brim from the lower front edge
        edge = G[-1]
        sel = [k for k in range(n_phi) if -math.sin(2 * math.pi * k / n_phi) > 0.45]
        sel.sort(key=lambda k: math.atan2(math.sin(2 * math.pi * k / n_phi), math.cos(2 * math.pi * k / n_phi)))
        inner = [edge[k] + Vector((0, 0, 0.004)) for k in sel]
        outer = []
        for k, p in zip(sel, inner):
            phi = 2 * math.pi * k / n_phi
            d = Vector((math.cos(phi), math.sin(phi), 0.0))
            outer.append(p + d * 0.06 + Vector((0, 0, -0.012)))
        Gb = [inner, outer]
        Gt = [[p + Vector((0, 0, 0.004)) for p in inner], [p + Vector((0, 0, 0.004)) for p in outer]]
        Ub = [i / max(1, len(sel) - 1) for i in range(len(sel))]
        bgeo = Geo()
        bgeo.add(*grid(Gb, Ub, [0, 1]))
        bgeo.add(*grid(Gt, Ub, [0, 1], flip=True))
        ctx.add(make_part(name + '_Brim', bgeo, brim_material or material, ctx.rig, {'head': 1.0}, recalc=False), 'brim')
    elif knot:
        back_phi = math.pi / 2
        p, d = surface(back_phi, e_back + 8)
        kc = p + d * 0.018
        kgeo = Geo().add(*ellipsoid(kc, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.032, 0.022, 0.026), 12, 8))
        ctx.add(make_part(name + '_Knot', kgeo, material, ctx.rig, {'head': 1.0}), 'knot')
        if tails:
            for sx in (0.022, -0.022):
                pts = [kc + Vector((sx, 0.012, -0.01)), kc + Vector((sx * 1.6, 0.03, -0.06)), kc + Vector((sx * 2.2, 0.035, -0.12))]
                nrm = [Vector((0, 1, 0))] * 3
                verts, faces, uvs = ribbon(pts, nrm, 0.04, 0.003, tiling=3)
                ctx.add(make_part(name + '_Tail', Geo().add(verts, faces, uvs), material, ctx.rig,
                                  lambda i, v: blend_weights({'head': 1.0}, {'neck_01': 1.0}, 0.5)), 'tail')
    return obj


def bun(ctx, name, material, size=(0.040, 0.032, 0.036), elevation=16.0):
    hc = ctx.head_center
    d = Vector((0.0, math.cos(math.radians(elevation)), math.sin(math.radians(elevation))))
    loc, nor = cast(ctx.bvh('head'), hc + d * 0.45, -d, 0.45)
    if loc is None:
        loc = hc + d * ctx.head_radii.y
    centre = loc + d * (size[1] * 0.75)
    ax = Vector((1, 0, 0))
    ay = d
    az = ax.cross(ay).normalized()
    geo = Geo().add(*ellipsoid(centre, (ax, ay, az), size, 18, 12))
    return ctx.add(make_part(name, geo, material, ctx.rig, {'head': 1.0}), 'bun')


def glasses(ctx, name, material):
    eyes = ctx.eyes
    if eyes is None:
        ctx.notes.append('glasses: eye mesh missing')
        return None
    pts = [eyes.matrix_world @ v.co for v in eyes.data.vertices]
    left = [p for p in pts if p.x > 0]
    right = [p for p in pts if p.x < 0]
    geo = Geo()
    rims = []
    for cluster in (left, right):
        xs, ys, zs = [p.x for p in cluster], [p.y for p in cluster], [p.z for p in cluster]
        c = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2))
        r_eye = (max(xs) - min(xs)) / 2
        lens = c + Vector((0, -(r_eye + 0.011), -0.002))
        rims.append(lens)
        geo.add(*torus(lens, (0, 1, 0), 0.0185, 0.0012, 28, 6))
    l, r = rims
    bridge = [l + Vector((-0.0185, 0, 0.004)), (l + r) / 2 + Vector((0, -0.002, 0.009)), r + Vector((0.0185, 0, 0.004))]
    geo.add(*tube(bridge, 0.0011, sides=6))
    for lens, sx in ((l, 1), (r, -1)):
        side_loc, d = ctx.radial(lens.z, 0.0 if sx > 0 else math.pi, key='head', center=(0.0, ctx.head_center.y))
        x_side = abs(side_loc.x) + 0.004 if side_loc is not None else abs(lens.x) + 0.05
        start = lens + Vector((sx * 0.0185, 0.0, 0.002))
        mid = Vector((sx * x_side, lens.y + 0.03, lens.z + 0.004))
        end = Vector((sx * (x_side - 0.004), ctx.head_center.y + 0.015, lens.z - 0.012))
        geo.add(*tube([start, mid, end], 0.0011, sides=6))
    return ctx.add(make_part(name, geo, material, ctx.rig, {'head': 1.0}, smooth=True), 'glasses')


def satchel(ctx, name, bag_material, strap_material, side='l', size=(0.12, 0.10, 0.03), z=None, forward=0.03):
    sx = 1 if side == 'l' else -1
    hz = z if z is not None else (ctx.hip['l'].z + ctx.hip['r'].z) / 2 - 0.02
    loc, d = ctx.radial(hz, 0.0 if sx > 0 else math.pi)
    if loc is None:
        loc = Vector((sx * 0.18, ctx.axis_y, hz))
    out = Vector((sx, 0.0, 0.0))
    centre = loc + out * (size[2] + 0.012) + Vector((0, -forward, 0))
    geo = Geo()
    geo.add(*box(centre, (out, Vector((0, 1, 0)), Vector((0, 0, 1))), (size[2], size[0], size[1])))
    flap_c = centre + out * (size[2] + 0.004) + Vector((0, 0, size[1] * 0.35))
    geo.add(*box(flap_c, (out, Vector((0, 1, 0)), Vector((0, 0, 1))), (0.004, size[0] * 1.02, size[1] * 0.68)))
    bag_w = blend_weights({'pelvis': 1.0}, {('thigh_l' if sx > 0 else 'thigh_r'): 1.0}, 0.25)
    ctx.add(make_part(name, geo, bag_material, ctx.rig, bag_w, smooth=False), 'satchel')
    # strap: bag top -> across the front -> opposite shoulder -> across the back -> bag top
    top = centre + Vector((0, 0, size[1]))
    opp = ctx.sh['r' if sx > 0 else 'l']
    pts = []
    for t in [0.0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.88]:
        x = top.x * (1 - t) + opp.x * 0.55 * t
        zz = top.z * (1 - t) + (opp.z + 0.06) * t
        y, _ = ctx.front_y(x, zz)
        pts.append(Vector((x, (y if y is not None else -0.12) - 0.005, zz)))
    # over the shoulder (cast from above)
    for oy in [-0.02, 0.0, 0.03]:
        px = opp.x * 0.6
        loc2, _ = cast(ctx.bvh(), (px, opp.y + oy, opp.z + 0.5), (0, 0, -1), 1.0)
        pts.append((loc2 if loc2 is not None else Vector((px, opp.y + oy, opp.z + 0.08))) + Vector((0, 0, 0.005)))
    for t in [0.12, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0]:
        x = opp.x * 0.55 * (1 - t) + top.x * t
        zz = (opp.z + 0.06) * (1 - t) + top.z * t
        y, _ = ctx.back_y(x, zz)
        pts.append(Vector((x, (y if y is not None else 0.12) + 0.005, zz)))
    normals = []
    for p in pts:
        d2 = Vector((p.x, p.y - ctx.axis_y, max(0.0, p.z - opp.z) * 2))
        normals.append(d2.normalized() if d2.length > 1e-6 else Vector((0, -1, 0)))
    verts, faces, uvs = ribbon(pts, normals, 0.032, 0.004)
    ctx.add(make_part(name + '_Strap', Geo().add(verts, faces, uvs), strap_material, ctx.rig,
                      lambda i, v: ctx.bw.at(v)), 'strap')


def suspenders(ctx, name, material, clip_material, waist_z):
    for sx in (1, -1):
        pts = []
        sh = ctx.sh['l' if sx > 0 else 'r']
        for t in [0.0, 0.2, 0.4, 0.6, 0.8, 0.95]:
            x = sx * (0.085 + (abs(sh.x) * 0.55 - 0.085) * t)
            z = waist_z + (sh.z + 0.05 - waist_z) * t
            y, _ = ctx.front_y(x, z)
            pts.append(Vector((x, (y if y is not None else -0.12) - 0.004, z)))
        for oy in [-0.015, 0.02]:
            px = sx * abs(sh.x) * 0.58
            loc, _ = cast(ctx.bvh(), (px, sh.y + oy, sh.z + 0.5), (0, 0, -1), 1.0)
            pts.append((loc if loc is not None else Vector((px, sh.y + oy, sh.z + 0.08))) + Vector((0, 0, 0.004)))
        for t in [0.1, 0.3, 0.5, 0.7, 0.9, 1.0]:
            x = sx * (abs(sh.x) * 0.55 + (0.03 - abs(sh.x) * 0.55) * t)
            z = sh.z + 0.05 + (waist_z + 0.02 - (sh.z + 0.05)) * t
            y, _ = ctx.back_y(x, z)
            pts.append(Vector((x, (y if y is not None else 0.12) + 0.004, z)))
        normals = [Vector((p.x, p.y - ctx.axis_y, max(0.0, p.z - sh.z) * 2)).normalized() for p in pts]
        verts, faces, uvs = ribbon(pts, normals, 0.03, 0.003)
        ctx.add(make_part('%s_%s' % (name, 'L' if sx > 0 else 'R'), Geo().add(verts, faces, uvs), material,
                          ctx.rig, lambda i, v: ctx.bw.at(v)), 'suspender')
        clip = pts[0] + Vector((0, -0.004, 0.012))
        ctx.add(make_part('%s_Clip%s' % (name, 'L' if sx > 0 else 'R'), Geo().add(*box(clip, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.018, 0.004, 0.012))),
                          clip_material, ctx.rig, ctx.bw.at(clip), smooth=False), 'clip')


def leg_cuffs(ctx, name, material, garment, z_cut, width=0.055, thickness=0.012):
    """Roll trousers: remove the garment below z_cut and add a turned-up cuff on each leg."""
    bm = bmesh.new()
    bm.from_mesh(garment.data)
    remove = [f for f in bm.faces if (garment.matrix_world @ f.calc_center_median()).z < z_cut - 0.01]
    bmesh.ops.delete(bm, geom=remove, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(garment.data)
    bm.free()
    garment.data.update()
    ctx.invalidate()
    for side in ('l', 'r'):
        k, a = ctx.knee[side], ctx.ankle[side]
        t = (z_cut - a.z) / max(1e-4, (k.z - a.z))
        center = a.lerp(k, max(0.0, min(1.0, t)))
        belt(ctx, '%s_%s' % (name, side.upper()), material, z_cut + width * 0.35, width=width, thickness=thickness,
             offset=0.003, n=32, center=(center.x, center.y), key='garments', max_r=0.10)


# ---------------------------------------------------------------- pose tools (posed armature space == world)
FINGERS = (('index', 0.85), ('middle', 1.0), ('ring', 1.05), ('pinky', 1.1))


def rotate_bone_world(rig, name, quat):
    update()
    bone = rig.pose.bones[name]
    matrix = bone.matrix.copy()
    head = matrix.to_translation()
    bone.matrix = Matrix.Translation(head) @ quat.to_matrix().to_4x4() @ Matrix.Translation(-head) @ matrix
    update()


def bone_dir(rig, name):
    update()
    bone = rig.pose.bones[name]
    return (bone.tail - bone.head).normalized()


def aim(rig, name, direction):
    current = bone_dir(rig, name)
    rotate_bone_world(rig, name, current.rotation_difference(Vector(direction).normalized()))


def twist(rig, name, degrees):
    rotate_bone_world(rig, name, Quaternion(bone_dir(rig, name), math.radians(degrees)))


def hand_frame(rig, side):
    update()
    pose = rig.pose.bones
    head = pose['hand_' + side].head.copy()
    index = pose['index_01_' + side].head.copy()
    pinky = pose['pinky_01_' + side].head.copy()
    middle = pose['middle_01_' + side].head.copy()
    finger = (middle - head).normalized()
    across = (pinky - index).normalized()
    palm = finger.cross(across).normalized() * (-1.0 if side == 'l' else 1.0)
    centre = head + (middle - head) * 0.62 + palm * 0.012
    return centre, finger, across, palm


def ik_arm(rig, side, target, pole):
    """Analytic two-bone IK: place the wrist (hand head) at target; elbow toward pole."""
    data = rig.data.bones
    l1 = (data['upperarm_' + side].tail_local - data['upperarm_' + side].head_local).length
    l2 = (data['lowerarm_' + side].tail_local - data['lowerarm_' + side].head_local).length
    update()
    shoulder = rig.pose.bones['upperarm_' + side].head.copy()
    target = Vector(target)
    span = target - shoulder
    dist = max(abs(l1 - l2) + 1e-3, min(l1 + l2 - 1e-3, span.length))
    axis = span.normalized()
    a = (l1 * l1 - l2 * l2 + dist * dist) / (2 * dist)
    h = math.sqrt(max(0.0, l1 * l1 - a * a))
    pole = Vector(pole)
    perpendicular = pole - axis * pole.dot(axis)
    if perpendicular.length < 1e-6:
        perpendicular = Vector((0, 0, -1)) - axis * (-axis.z)
    perpendicular.normalize()
    elbow = shoulder + axis * a + perpendicular * h
    wrist = shoulder + axis * dist
    aim(rig, 'upperarm_' + side, elbow - shoulder)
    update()
    aim(rig, 'lowerarm_' + side, wrist - rig.pose.bones['lowerarm_' + side].head)
    return elbow, wrist


def orient_palm(rig, side, target, forearm_share=0.6, hand_limit=55.0):
    target = Vector(target).normalized()
    for bone, share, limit in (('lowerarm_' + side, forearm_share, 120.0), ('hand_' + side, 1.0, hand_limit)):
        _, _, _, palm = hand_frame(rig, side)
        axis = bone_dir(rig, bone)
        p = palm - axis * palm.dot(axis)
        t = target - axis * target.dot(axis)
        if p.length < 1e-4 or t.length < 1e-4:
            continue
        p.normalize()
        t.normalize()
        angle = math.degrees(math.atan2(axis.dot(p.cross(t)), p.dot(t))) * share
        angle = max(-limit, min(limit, angle))
        rotate_bone_world(rig, bone, Quaternion(axis, math.radians(angle)))


def curl(rig, side, angles=(30, 45, 30), thumb=(8, 18, 12)):
    _, _, _, palm = hand_frame(rig, side)
    for finger, scale in FINGERS:
        for joint, angle in zip(('01', '02', '03'), angles):
            name = '%s_%s_%s' % (finger, joint, side)
            if name not in rig.pose.bones:
                continue
            d = bone_dir(rig, name)
            axis = d.cross(palm)
            if axis.length < 1e-5:
                continue
            rotate_bone_world(rig, name, Quaternion(axis.normalized(), math.radians(angle * scale)))
    for joint, angle in zip(('01', '02', '03'), thumb):
        name = 'thumb_%s_%s' % (joint, side)
        if name not in rig.pose.bones:
            continue
        d = bone_dir(rig, name)
        axis = d.cross(palm)
        if axis.length < 1e-5:
            continue
        rotate_bone_world(rig, name, Quaternion(axis.normalized(), math.radians(angle)))


def look(rig, pitch=0.0, yaw=0.0, roll=0.0):
    """Positive pitch = chin down, positive yaw = toward the character's left. Split neck/head."""
    for bone, share in (('neck_01', 0.4), ('head', 0.6)):
        if pitch:
            rotate_bone_world(rig, bone, Quaternion(Vector((1, 0, 0)), math.radians(pitch * share)))
        if yaw:
            rotate_bone_world(rig, bone, Quaternion(Vector((0, 0, 1)), math.radians(yaw * share)))
        if roll:
            rotate_bone_world(rig, bone, Quaternion(Vector((0, -1, 0)), math.radians(roll * share)))


def relaxed_arm(rig, side, out=0.13, forward=0.06, bend=0.22):
    s = 1.0 if side == 'l' else -1.0
    aim(rig, 'upperarm_' + side, (out * s, -forward, -0.99))
    aim(rig, 'lowerarm_' + side, (0.05 * s, -bend, -0.97))
    aim(rig, 'hand_' + side, (0.02 * s, -bend * 0.5, -0.99))
    orient_palm(rig, side, (-s, 0.15, 0.0))
    curl(rig, side, (8, 16, 10), (4, 8, 6))


def prepare_pose(rig):
    rig.animation_data_clear()
    for bone in rig.pose.bones:
        bone.rotation_mode = 'QUATERNION'
        bone.rotation_quaternion = Quaternion()
        bone.location = Vector()
        bone.scale = Vector((1, 1, 1))
    bpy.context.scene.frame_set(1)
    update()


def to_rest(geo, rig, bone):
    """Vertices authored in the posed world -> rest coordinates rigidly bound to `bone`."""
    update()
    pose = rig.matrix_world @ rig.pose.bones[bone].matrix
    rest = rig.matrix_world @ rig.data.bones[bone].matrix_local
    return geo.transform(rest @ pose.inverted())


def prop(ctx, name, geo, material, bone, smooth=True):
    to_rest(geo, ctx.rig, bone)
    return ctx.add(make_part(name, geo, material, ctx.rig, {bone: 1.0}, smooth=smooth), 'prop')


# ---------------------------------------------------------------- idle animation
def bake_idle(rig, meshes, role, breathe=1.0, head_yaw=2.0):
    update()
    base_rot = {b.name: b.rotation_quaternion.copy() for b in rig.pose.bones}
    base_loc = {b.name: b.location.copy() for b in rig.pose.bones}
    rig.animation_data_create()
    rig.animation_data.action = bpy.data.actions.new('A_SC_' + role + '_Idle')
    for frame in [1, 31, 61, 91, 121]:
        ph = (frame - 1) / 120 * 2 * math.pi
        for bone in rig.pose.bones:
            q = base_rot[bone.name].copy()
            if bone.name in ('spine_02', 'spine_03'):
                q = q @ Quaternion((1, 0, 0), math.radians(0.55 * breathe) * math.sin(ph))
            elif bone.name == 'neck_01':
                q = q @ Quaternion((0, 1, 0), math.radians(head_yaw * 0.4) * math.sin(ph + 0.6))
            elif bone.name == 'head':
                q = (q @ Quaternion((0, 1, 0), math.radians(head_yaw * 0.6) * math.sin(ph + 0.6))
                     @ Quaternion((1, 0, 0), math.radians(0.7) * math.sin(2 * ph)))
            elif bone.name in ('clavicle_l', 'clavicle_r'):
                q = q @ Quaternion((1, 0, 0), math.radians(0.35 * breathe) * math.sin(ph))
            bone.rotation_quaternion = q
            bone.location = base_loc[bone.name]
            bone.keyframe_insert('rotation_quaternion', frame=frame, group=bone.name)
            bone.keyframe_insert('location', frame=frame, group=bone.name)
    for obj in meshes:
        if obj.type != 'MESH' or not obj.data.shape_keys:
            continue
        for key_name in ('eyeBlinkLeft', 'eyeBlinkRight'):
            key = obj.data.shape_keys.key_blocks.get(key_name)
            if key:
                for frame, value in [(1, 0), (40, 0), (43, 1), (46, 0), (97, 0), (100, 1), (103, 0), (121, 0)]:
                    key.value = value
                    key.keyframe_insert('value', frame=frame)
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 120
    bpy.context.scene.frame_set(1)
    update()
    return rig.animation_data.action.name


# ---------------------------------------------------------------- facial hair
def _smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def beard_shell(ctx, name, mask_png, material, thickness=0.009, min_mask=0.12):
    """Offset shell of the body's beard region (sampled from a UV mask) with copied skin
    weights and copied facial shape-key deltas, so the beard follows speech and blinks."""
    import numpy as np
    body = ctx.body
    mesh = body.data
    image = bpy.data.images.load(str(mask_png), check_existing=True)
    width, height = image.size
    pixels = np.empty(width * height * image.channels, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    mask = pixels.reshape(height, width, image.channels)[:, :, 0]
    uv = mesh.uv_layers.active.data
    acc = np.zeros(len(mesh.vertices))
    cnt = np.zeros(len(mesh.vertices))
    for loop in mesh.loops:
        u, v = uv[loop.index].uv
        x = min(width - 1, max(0, int(u * width)))
        y = min(height - 1, max(0, int(v * height)))
        acc[loop.vertex_index] += mask[y, x]
        cnt[loop.vertex_index] += 1
    m = np.where(cnt > 0, acc / np.maximum(cnt, 1), 0.0)
    faces = [p for p in mesh.polygons
             if min(m[i] for i in p.vertices) > 0.02 and sum(m[i] for i in p.vertices) / len(p.vertices) > min_mask]
    if not faces:
        ctx.notes.append(name + ': beard mask selected no faces')
        return None
    used = sorted({i for p in faces for i in p.vertices})
    remap = {old: new for new, old in enumerate(used)}
    world = body.matrix_world
    normal_matrix = world.to_3x3().inverted().transposed()
    offsets, normals, verts = [], [], []
    for i in used:
        vertex = mesh.vertices[i]
        n = (normal_matrix @ vertex.normal).normalized()
        off = thickness * _smoothstep(0.08, 0.85, float(m[i]))
        normals.append(n)
        offsets.append(off)
        verts.append(world @ vertex.co + n * off)
    new_faces, uvs = [], []
    for p in faces:
        new_faces.append(tuple(remap[i] for i in p.vertices))
        uvs.append(tuple(tuple(uv[li].uv) for li in p.loop_indices))
    geo = Geo().add(verts, new_faces, uvs)
    weights = [dict(ctx.bw.weights[i]) or {'head': 1.0} for i in used]
    obj = make_part(name, geo, material, ctx.rig, lambda k, v: weights[k], recalc=False)
    keys = mesh.shape_keys.key_blocks if mesh.shape_keys else []
    copied = 0
    if keys:
        obj.shape_key_add(name='Basis', from_mix=False)
        basis = keys[0]
        for key in keys[1:]:
            deltas = [key.data[i].co - basis.data[i].co for i in used]
            if max(d.length for d in deltas) < 1e-6:
                continue
            target = obj.shape_key_add(name=key.name, from_mix=False)
            for k, (i, d) in enumerate(zip(used, deltas)):
                target.data[k].co = world @ (basis.data[i].co + d) + normals[k] * offsets[k]
            copied += 1
    obj.data.update()
    ctx.add(obj, 'beard')
    ctx.notes.append('%s: %d shell faces, %d facial shape keys copied' % (name, len(new_faces), copied))
    return obj


# ---------------------------------------------------------------- props
def open_book(ctx, name, side, cover_mat, page_mat, size=(0.15, 0.21), lift=0.012, along=0.03):
    centre, finger, across, palm = hand_frame(ctx.rig, side)
    c = centre + palm * lift + finger * along
    covers, pages = Geo(), Geo()
    for sgn in (1, -1):
        tilt = Quaternion(finger, math.radians(7 * sgn))
        u = (tilt @ across) * sgn
        n = tilt @ palm
        mid = c + u * (size[0] / 2 + 0.004)
        covers.add(*box(mid, (u, finger, n), (size[0] / 2, size[1] / 2, 0.003)))
        pages.add(*box(mid + n * 0.008, (u, finger, n), (size[0] / 2 - 0.006, size[1] / 2 - 0.006, 0.006)))
    prop(ctx, name + '_Cover', covers, cover_mat, 'hand_' + side, smooth=False)
    prop(ctx, name + '_Pages', pages, page_mat, 'hand_' + side, smooth=False)


def closed_stack(ctx, name, side, cover_mat, page_mat, size=(0.22, 0.30, 0.03), lift=0.016):
    centre, finger, across, palm = hand_frame(ctx.rig, side)
    c = centre + palm * (lift + size[2] / 2) + finger * 0.02
    covers, pages = Geo(), Geo()
    covers.add(*box(c - palm * (size[2] / 2 - 0.002), (across, finger, palm), (size[0] / 2, size[1] / 2, 0.002)))
    pages.add(*box(c + palm * 0.002, (across, finger, palm), (size[0] / 2 - 0.004, size[1] / 2 - 0.006, size[2] / 2 - 0.002)))
    prop(ctx, name + '_Folder', covers, cover_mat, 'hand_' + side, smooth=False)
    prop(ctx, name + '_Sheets', pages, page_mat, 'hand_' + side, smooth=False)


def pencil(ctx, name, side, material, length=0.15):
    centre, finger, across, palm = hand_frame(ctx.rig, side)
    a = centre - finger * 0.02 + palm * 0.006
    b = a + (finger * 0.55 + palm * 0.8).normalized() * length
    prop(ctx, name, Geo().add(*cylinder(a, b, 0.0035, 0.0015, sides=8)), material, 'hand_' + side)


def rope_coil(ctx, name, side, material, major=0.12, minor=0.019):
    centre, finger, across, palm = hand_frame(ctx.rig, side)
    c = centre + Vector((0, 0, -major + 0.015)) + palm * 0.01
    geo = Geo()
    for k, r in enumerate([major, major - 0.02, major - 0.04]):
        geo.add(*torus(c + Vector((0.0, 0.012 * (k - 1), 0.0)), (0, 1, 0), r, minor, 40, 8))
    prop(ctx, name, geo, material, 'hand_' + side)


def plank_on_shoulder(ctx, name, material, length=1.5, width=0.13, thick=0.034):
    sh = ctx.sh['r']
    update()
    loc, _ = cast(ctx.bvh(), (sh.x * 0.78, sh.y, sh.z + 0.6), (0, 0, -1), 1.2)
    top = loc if loc is not None else sh + Vector((0, 0, 0.07))
    axis = Vector((0.05, 1.0, 0.12)).normalized()
    up = Vector((0, 0, 1))
    side = axis.cross(up).normalized()
    normal = side.cross(axis).normalized()
    centre = top + normal * (thick / 2 + 0.006) + axis * 0.18
    geo = Geo().add(*box(centre, (side, axis, normal), (width / 2, length / 2, thick / 2)))
    for v in range(len(geo.uvs)):
        geo.uvs[v] = tuple((u * 6.0, w * 1.0) for (u, w) in geo.uvs[v])
    prop(ctx, name, geo, material, 'clavicle_r', smooth=False)
    return centre, axis, normal, side


def basket_with_bread(ctx, name, wicker, bread, cloth=None):
    c_l, f_l, a_l, p_l = hand_frame(ctx.rig, 'l')
    c_r, f_r, a_r, p_r = hand_frame(ctx.rig, 'r')
    mid = (c_l + c_r) / 2
    rx, ry, h = 0.20, 0.13, 0.11
    base_c = mid + Vector((0, -0.02, -h * 0.55))
    rings = 6
    G = []
    for i in range(rings):
        t = i / (rings - 1)
        s = 0.82 + 0.18 * t
        z = base_c.z + h * t
        G.append([Vector((base_c.x + rx * s * math.cos(a), base_c.y + ry * s * math.sin(a), z))
                  for a in [2 * math.pi * k / 28 for k in range(28)]])
    inner = [[base_c + (p - base_c) * 0.95 + Vector((0, 0, 0.0)) for p in row] for row in reversed(G)]
    walls = Geo()
    walls.add(*grid(G + inner, [k / 28 * 6 for k in range(29)], [i / 3 for i in range(2 * rings)], close_j=True))
    floor = [Vector((base_c.x + rx * 0.80 * math.cos(a), base_c.y + ry * 0.80 * math.sin(a), base_c.z + 0.005))
             for a in [2 * math.pi * k / 28 for k in range(28)]]
    fi = len(floor)
    verts = floor + [base_c + Vector((0, 0, 0.005))]
    faces = [(k, (k + 1) % fi, fi) for k in range(fi)]
    walls.add(verts, faces, [((0, 0), (1, 0), (0.5, 0.5))] * fi)
    rim = [Vector((base_c.x + rx * 1.0 * math.cos(a), base_c.y + ry * 1.0 * math.sin(a), base_c.z + h))
           for a in [2 * math.pi * k / 36 for k in range(36)]]
    walls.add(*tube(rim, 0.011, sides=8, closed=True, caps=False,
                    normals=[(p - base_c).normalized() for p in rim]))
    loaves = Geo()
    spots = [(-0.08, 0.0, 0.075, 0.045, 0.04, 20), (0.0, 0.03, 0.08, 0.05, 0.045, -10), (0.085, -0.01, 0.07, 0.045, 0.04, 35),
             (-0.03, -0.05, 0.06, 0.04, 0.035, 80), (0.05, 0.055, 0.055, 0.038, 0.035, 60)]
    for x, y, a, b, c, rot in spots:
        q = Quaternion((0, 0, 1), math.radians(rot))
        loaves.add(*ellipsoid(base_c + Vector((x, y, h * 0.86)), (q @ Vector((1, 0, 0)), q @ Vector((0, 1, 0)), Vector((0, 0, 1))),
                              (a * 1.12, b * 1.12, c * 1.15), 16, 10))
    prop(ctx, name + '_Basket', walls, wicker, 'hand_r')
    prop(ctx, name + '_Bread', loaves, bread, 'hand_r')


def lantern(ctx, name, side, brass, glow, glass=None, drop=0.17, size=0.055):
    centre, finger, across, palm = hand_frame(ctx.rig, side)
    grip = centre + palm * 0.01
    body_c = grip + Vector((0, 0, -drop))
    frame = Geo()
    frame.add(*torus(grip + Vector((0, 0, -0.035)), (1, 0, 0), 0.03, 0.004, 20, 6))
    top = body_c + Vector((0, 0, size * 1.35))
    frame.add(*cylinder(top, top + Vector((0, 0, 0.035)), size * 1.05, 0.012, sides=12))
    frame.add(*cylinder(body_c + Vector((0, 0, -size * 1.4)), body_c + Vector((0, 0, -size * 1.25)), size * 1.1, size * 1.1, sides=12))
    for sx in (1, -1):
        for sy in (1, -1):
            p = body_c + Vector((sx * size, sy * size, 0.0))
            frame.add(*box(p, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.004, 0.004, size * 1.3)))
    prop(ctx, name + '_Frame', frame, brass, 'hand_' + side)
    core = Geo()
    core.add(*cylinder(body_c + Vector((0, 0, -size * 1.2)), body_c + Vector((0, 0, -size * 0.2)), 0.014, 0.014, sides=10))
    core.add(*ellipsoid(body_c + Vector((0, 0, size * 0.05)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.011, 0.011, 0.024), 10, 8))
    prop(ctx, name + '_Glow', core, glow, 'hand_' + side)
    if glass:
        pane = Geo().add(*box(body_c, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (size * 0.96, size * 0.96, size * 1.25)))
        prop(ctx, name + '_Glass', pane, glass, 'hand_' + side, smooth=False)


def staff_with_lantern(ctx, name, wood, brass, glow):
    centre, finger, across, palm = hand_frame(ctx.rig, 'r')
    axis_point = centre + palm * 0.02
    bottom = Vector((axis_point.x, axis_point.y, ctx.ground + 0.03))
    top = Vector((axis_point.x, axis_point.y, ctx.ground + 2.12))
    pole = Geo().add(*cylinder(bottom, top, 0.017, 0.014, sides=12))
    prop(ctx, name + '_Pole', pole, wood, 'hand_r')
    hook = Geo()
    forward = Vector((0, -1, 0))
    pts = [top + Vector((0, 0, -0.02)), top + Vector((0, 0, 0.05)), top + forward * 0.06 + Vector((0, 0, 0.08)),
           top + forward * 0.13 + Vector((0, 0, 0.05)), top + forward * 0.14 + Vector((0, 0, 0.0))]
    hook.add(*tube(pts, 0.006, sides=8))
    lamp_c = top + forward * 0.14 + Vector((0, 0, -0.11))
    s = 0.045
    hook.add(*cylinder(lamp_c + Vector((0, 0, s * 1.3)), lamp_c + Vector((0, 0, s * 1.3 + 0.03)), s * 1.05, 0.01, sides=10))
    hook.add(*cylinder(lamp_c + Vector((0, 0, -s * 1.35)), lamp_c + Vector((0, 0, -s * 1.2)), s * 1.05, s * 1.05, sides=10))
    for sx in (1, -1):
        for sy in (1, -1):
            hook.add(*box(lamp_c + Vector((sx * s, sy * s, 0)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.0035, 0.0035, s * 1.25)))
    hook.add(*tube([pts[-1], lamp_c + Vector((0, 0, s * 1.33))], 0.002, sides=6))
    prop(ctx, name + '_Hook', hook, brass, 'hand_r')
    glow_geo = Geo().add(*ellipsoid(lamp_c, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.02, 0.02, 0.03), 10, 8))
    prop(ctx, name + '_Flame', glow_geo, glow, 'hand_r')


def bundle_under_arm(ctx, name, cloth, cord):
    update()
    lo = ctx.rig.pose.bones['lowerarm_l']
    mid = (lo.head + lo.tail) / 2
    along = (lo.tail - lo.head).normalized()
    c = mid + Vector((0, 0, 0.075)) + Vector((-0.035, 0.0, 0.0))
    side = along.cross(Vector((0, 0, 1))).normalized()
    up = side.cross(along).normalized()
    geo = Geo().add(*ellipsoid(c, (along, side, up), (0.16, 0.085, 0.075), 18, 12))
    prop(ctx, name, geo, cloth, 'lowerarm_l')
    ties = Geo()
    for t in (-0.07, 0.07):
        ties.add(*torus(c + along * t, along, 0.08, 0.005, 24, 6))
    prop(ctx, name + '_Cord', ties, cord, 'lowerarm_l')


def belt_tool(ctx, name, handle_mat, head_mat, side='r', z=None, kind='hammer'):
    sx = 1 if side == 'l' else -1
    hz = z if z is not None else ctx.spine1.z - 0.02
    loc, d = ctx.radial(hz, math.radians(-55 if sx > 0 else -125))
    if loc is None:
        loc = Vector((sx * 0.14, ctx.axis_y - 0.12, hz))
    p = loc + d * 0.02
    geo, head = Geo(), Geo()
    if kind == 'hammer':
        geo.add(*cylinder(p + Vector((0, 0, -0.24)), p + Vector((0, 0, 0.03)), 0.012, 0.014, sides=10))
        head.add(*box(p + Vector((0, 0, 0.05)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.055, 0.016, 0.016)))
    elif kind == 'chisel':
        geo.add(*cylinder(p + Vector((0, 0, 0.0)), p + Vector((0, 0, 0.10)), 0.013, 0.013, sides=10))
        head.add(*box(p + Vector((0, 0, -0.07)), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.009, 0.003, 0.07)))
    elif kind == 'oilcan':
        head.add(*cylinder(p + Vector((0, 0, -0.06)), p + Vector((0, 0, 0.05)), 0.04, 0.04, sides=16))
        head.add(*cylinder(p + Vector((0, 0, 0.05)), p + Vector((0, -0.06, 0.12)), 0.006, 0.003, sides=8))
        geo.add(*torus(p + Vector((0, 0.04, 0.03)), (1, 0, 0), 0.02, 0.003, 16, 6))
    if geo.verts:
        ctx.add(make_part(name + '_Handle', geo, handle_mat, ctx.rig, {'pelvis': 1.0}), 'tool')
    if head.verts:
        ctx.add(make_part(name + '_Head', head, head_mat, ctx.rig, {'pelvis': 1.0}, smooth=False), 'tool')


def pouch(ctx, name, material, angle_deg, z, size=(0.06, 0.05, 0.025)):
    loc, d = ctx.radial(z, math.radians(angle_deg))
    if loc is None:
        return None
    c = loc + d * (size[2] + 0.01)
    side = Vector((0, 0, 1)).cross(d).normalized()
    geo = Geo().add(*box(c, (side, d, Vector((0, 0, 1))), (size[0], size[2], size[1])))
    return ctx.add(make_part(name, geo, material, ctx.rig, ctx.bw.at(loc), smooth=False), 'pouch')


# ---------------------------------------------------------------- covered skin, renders, export
def occlude_covered_skin(ctx, garments, max_dist=0.05):
    """Remove body faces whose every vertex is covered by a garment along its normal.

    FACES_ONLY: vertices, weights and every shape key are kept. Facial-morph, hand,
    neck and foot vertices (when no footwear) stay protected.
    """
    body = ctx.body
    if not garments:
        return {'removed_faces': 0}
    bvh = surface_bvh(garments)
    mesh = body.data
    keys = mesh.shape_keys.key_blocks if mesh.shape_keys else []
    protected = set()
    if keys:
        basis = keys[0]
        for key in keys[1:]:
            for i in range(len(basis.data)):
                if (key.data[i].co - basis.data[i].co).length_squared > 1e-12:
                    protected.add(i)
    hand_bones = {b.name for b in ctx.rig.data.bones if b.name.startswith(('hand_', 'thumb_', 'index_', 'middle_', 'ring_', 'pinky_'))}
    neck_limit = ctx.neck.z + 0.02
    for v in mesh.vertices:
        w = ctx.bw.weights[v.index]
        if sum(x for n, x in w.items() if n in hand_bones) > 0.05 or (body.matrix_world @ v.co).z > neck_limit:
            protected.add(v.index)
    covered = set()
    matrix = body.matrix_world
    normal_matrix = matrix.to_3x3()
    for v in mesh.vertices:
        if v.index in protected:
            continue
        p = matrix @ v.co
        n = (normal_matrix @ v.normal).normalized()
        loc, nor, idx, dist = bvh.ray_cast(p + n * 0.0005, n, max_dist)
        if loc is not None:
            covered.add(v.index)
    faces = [f.index for f in mesh.polygons if all(i in covered for i in f.vertices)]
    if not faces:
        return {'removed_faces': 0}
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in faces], context='FACES_ONLY')
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    ctx.invalidate()
    return {'removed_faces': len(faces), 'covered_vertices': len(covered), 'protected_vertices': len(protected)}


def _look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def setup_studio(ctx):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.image_settings.file_format = 'PNG'
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    if scene.world is None:
        scene.world = bpy.data.worlds.new('SC_World')
    world = scene.world
    world.use_nodes = True
    background = world.node_tree.nodes.get('Background')
    if background:
        background.inputs['Color'].default_value = (0.42, 0.40, 0.36, 1.0)
        background.inputs['Strength'].default_value = 0.55
    created = []
    for name, location, energy, colour, size in [
            ('SC_Key', (-2.4, -3.2, 3.4), 520.0, (1.0, 0.90, 0.76), 3.0),
            ('SC_Fill', (2.8, -2.2, 1.8), 210.0, (0.82, 0.88, 1.0), 3.5),
            ('SC_Rim', (0.9, 2.8, 3.1), 380.0, (1.0, 0.86, 0.70), 2.0)]:
        light = bpy.data.lights.new(name, 'AREA')
        light.energy, light.size, light.color = energy, size, colour
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = location
        _look_at(obj, (0, 0, ctx.ground + ctx.height * 0.55))
        created.append(obj)
    plane = bpy.data.meshes.new('SC_Floor')
    s = 4.0
    plane.from_pydata([(-s, -s, ctx.ground), (s, -s, ctx.ground), (s, s, ctx.ground), (-s, s, ctx.ground)], [], [(0, 1, 2, 3)])
    floor = bpy.data.objects.new('SC_Floor', plane)
    scene.collection.objects.link(floor)
    plane.materials.append(flat('SC_FloorMat', (0.30, 0.27, 0.23), 0.9))
    MATERIAL_RECIPES.pop('SC_FloorMat', None)
    created.append(floor)
    cam_data = bpy.data.cameras.new('SC_Camera')
    camera = bpy.data.objects.new('SC_Camera', cam_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    created.append(camera)
    return created, camera


def render_views(ctx, out_dir, camera):
    scene = bpy.context.scene
    scene.frame_set(1)
    h = ctx.height
    centre_z = ctx.ground + h * 0.52
    views = []
    for label, angle, dist, z, target_z, lens, res in [
            ('Front34', 28, 3.55, ctx.ground + h * 0.58, centre_z, 55, (900, 1200)),
            ('Front', 0, 3.55, ctx.ground + h * 0.56, centre_z, 55, (900, 1200)),
            ('Profile', 90, 3.55, ctx.ground + h * 0.56, centre_z, 55, (900, 1200)),
            ('Back', 180, 3.55, ctx.ground + h * 0.56, centre_z, 55, (900, 1200)),
            ('Face', 22, 0.95, ctx.head_center.z + 0.02, ctx.head_center.z - 0.01, 70, (900, 900))]:
        a = math.radians(angle)
        camera.location = (math.sin(a) * dist, -math.cos(a) * dist, z)
        target = (ctx.head_center.x, ctx.head_center.y, target_z) if label == 'Face' else (0, 0, target_z)
        _look_at(camera, target)
        camera.data.lens = lens
        scene.render.resolution_x, scene.render.resolution_y = res
        path = out_dir / ('%s_%s.png' % (ctx.role, label))
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        views.append(str(path))
    return views


def mesh_stats(objects):
    rows = []
    for obj in objects:
        if obj.type != 'MESH':
            continue
        rows.append({'name': obj.name, 'vertices': len(obj.data.vertices),
                     'triangles': sum(len(p.vertices) - 2 for p in obj.data.polygons),
                     'materials': [m.name for m in obj.data.materials if m],
                     'vertex_groups': len(obj.vertex_groups),
                     'shape_keys': len(obj.data.shape_keys.key_blocks) if obj.data.shape_keys else 0})
    return rows


def export_fbx(ctx, out_dir, exported):
    scene = bpy.context.scene
    scene.frame_set(1)
    for mat in bpy.data.materials:
        mat.use_fake_user = False
    conversion = units.normalize_centimeter_data(ctx.rig, exported)
    assert bpy.data.objects.get('Armature') in (None, ctx.rig), 'Unexpected object named Armature'
    ctx.rig.name = 'Armature'
    bpy.ops.object.select_all(action='DESELECT')
    for obj in exported:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = ctx.rig
    fbx = out_dir / ('SK_SC_%s.fbx' % ctx.role)
    bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'ARMATURE', 'MESH'},
                             add_leaf_bones=False, armature_nodetype='NULL', global_scale=1.0, apply_unit_scale=True,
                             apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Y', axis_up='Z',
                             use_mesh_modifiers=False, mesh_smooth_type='FACE', bake_anim=True,
                             bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
                             bake_anim_simplify_factor=0.0, path_mode='COPY', embed_textures=False)
    return fbx, conversion


# ---------------------------------------------------------------- palette (sRGB in, linear out)
def lin(r, g, b):
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b))


P = {
    'cream': lin(0.84, 0.78, 0.65), 'linen_white': lin(0.88, 0.85, 0.77), 'apron_white': lin(0.90, 0.88, 0.82),
    'teal': lin(0.22, 0.36, 0.42), 'teal_deep': lin(0.16, 0.30, 0.36), 'blue_skirt': lin(0.20, 0.30, 0.42),
    'navy': lin(0.12, 0.15, 0.24), 'navy_coat': lin(0.13, 0.17, 0.27), 'leather_dark': lin(0.24, 0.15, 0.09),
    'leather': lin(0.40, 0.25, 0.14), 'leather_light': lin(0.50, 0.34, 0.19), 'trouser_brown': lin(0.36, 0.27, 0.19),
    'trouser_slate': lin(0.24, 0.25, 0.27), 'trouser_blue': lin(0.21, 0.26, 0.36), 'rust': lin(0.55, 0.25, 0.17),
    'bandana_red': lin(0.62, 0.14, 0.11), 'scarf_blue': lin(0.24, 0.36, 0.50), 'scarf_rust': lin(0.55, 0.30, 0.18),
    'ochre': lin(0.62, 0.48, 0.28), 'gold': lin(0.80, 0.62, 0.30), 'brass': lin(0.78, 0.60, 0.32),
    'iron': lin(0.30, 0.30, 0.31), 'wood': lin(0.48, 0.34, 0.20), 'wood_pale': lin(0.66, 0.52, 0.36),
    'rope': lin(0.62, 0.54, 0.40), 'wicker': lin(0.60, 0.44, 0.24), 'crust': lin(0.62, 0.38, 0.16),
    'paper': lin(0.86, 0.82, 0.70), 'glow': lin(1.0, 0.72, 0.38), 'canvas_sand': lin(0.66, 0.58, 0.44),
    'boot': lin(0.34, 0.22, 0.13), 'shoe_dark': lin(0.20, 0.13, 0.08),
    'hair_dark': lin(0.12, 0.08, 0.06), 'hair_black': lin(0.07, 0.06, 0.055), 'hair_brown': lin(0.30, 0.20, 0.13),
    'hair_auburn': lin(0.40, 0.22, 0.13), 'hair_gray': lin(0.62, 0.60, 0.57), 'hair_white': lin(0.84, 0.82, 0.78),
    'brow_dark': (0.30, 0.22, 0.16), 'brow_gray': (0.80, 0.78, 0.74),
}

GARMENTS = {
    'tee': ('shirts', 'clothes/toigo_basic_tucked_t-shirt/toigo_basic_tucked_t-shirt.mhclo'),
    'dress': ('dress', 'clothes/toigo_camisole_dress_with_full_skirt/toigo_camisole_dress_with_full_skirt.mhclo'),
    'worksuit': ('system', 'clothes/male_worksuit01/male_worksuit01.mhclo'),
    'casual01': ('system', 'clothes/male_casualsuit01/male_casualsuit01.mhclo'),
    'casual05': ('system', 'clothes/male_casualsuit05/male_casualsuit05.mhclo'),
    'casual06': ('system', 'clothes/male_casualsuit06/male_casualsuit06.mhclo'),
    'robe': ('suits', 'clothes/donitz_monk_robe/donitz_monk_robe.mhclo'),
    'kimono': ('dress', 'clothes/mindfront_kimono/mindfront_kimono.mhclo'),
    'vpants': ('suits', 'clothes/rehmanpolanski_viking_pants/rehmanpolanski_viking_pants.mhclo'),
    'vboots': ('suits', 'clothes/rehmanpolanski_viking_boots/rehmanpolanski_viking_boots.mhclo'),
    'sweater': ('shirts', 'clothes/toigo_fisherman_sweater/toigo_fisherman_sweater.mhclo'),
    'shoes01': ('system', 'clothes/shoes01/shoes01.mhclo'),
    'shoes03': ('system', 'clothes/shoes03/shoes03.mhclo'),
}
REGION_KEYS = {'worksuit': 'male_worksuit01', 'casual01': 'male_casualsuit01', 'casual05': 'male_casualsuit05',
               'casual06': 'male_casualsuit06', 'robe': 'donitz_monk_robe'}


def garment_material(role, key, region, colour, contrast=0.6, roughness=0.88, kind=None):
    path = asset_path(*GARMENTS[key])
    tex = mhmat_texture(path)
    name = 'M_SC_%s_%s_%s' % (role, key, region)
    if kind is not None or tex is None:
        return fabric(name, kind or 'canvas', colour, roughness=roughness)
    return lumtint(name, tex, colour, contrast=contrast, roughness=roughness, two_sided=True)


# Each role: identity, generator settings (visual only), skin/eyes/hair, garments with colours, and
# wardrobe/pose builders defined below.
ROLES = {
    'HarborClerk': {
        'display': 'Harbor Clerk', 'working_name': 'Enna', 'story_tag': 'cast.clerk', 'era': 'past',
        'macros': {'gender': 0.0, 'age': 0.52, 'muscle': 0.42, 'weight': 0.45, 'height': 0.52,
                   'race': {'caucasian': 0.78, 'african': 0.12, 'asian': 0.10}},
        'face_targets': {'nose-hump-incr': 0.15, 'chin-prominent-incr': 0.12, 'l-eye-scale-incr': 0.1, 'r-eye-scale-incr': 0.1,
                         'mouth-lowerlip-volume-incr': 0.15},
        'skin': 'young_caucasian_female', 'skin_gain': (0.96, 0.86, 0.76), 'eyes': 'eye_darkbrown.png',
        'hair': 'short04', 'hair_tint': 'hair_dark', 'brows': 'brow_dark',
        'garments': {'tee': {'all': 'cream'}, 'dress': {'all': 'blue_skirt', 'kind': 'wool'}, 'shoes03': {'all': 'boot'}},
    },
    'Boatwright': {
        'display': 'Boatwright', 'story_tag': 'cast.boatwright', 'era': 'past',
        'macros': {'gender': 1.0, 'age': 0.65, 'muscle': 0.78, 'weight': 0.64, 'height': 0.64,
                   'race': {'caucasian': 0.80, 'african': 0.12, 'asian': 0.08}},
        'face_targets': {'chin-width-incr': 0.3, 'head-square': 0.35, 'nose-width1-incr': 0.2, 'nose-hump-incr': 0.2,
                         'l-eye-bag-incr': 0.2, 'r-eye-bag-incr': 0.2},
        'skin_texture': 'skin_boatwright_beard.png', 'skin': 'middleage_caucasian_male', 'skin_gain': (0.90, 0.78, 0.66),
        'eyes': 'eye_darkbrown.png', 'hair': 'short02', 'hair_tint': 'hair_black', 'brows': 'brow_dark',
        'beard': ('full', 'beard_boatwright.png', 0.006),
        'garments': {'worksuit': {'shirt': 'cream', 'overall': 'leather_dark', 'metal': 'brass'}, 'vboots': {'all': 'boot'}},
    },
    'Fisherwoman': {
        'display': 'Fisherwoman', 'story_tag': 'cast.fisherwoman', 'era': 'past',
        'macros': {'gender': 0.0, 'age': 0.49, 'muscle': 0.56, 'weight': 0.44, 'height': 0.56,
                   'race': {'caucasian': 0.70, 'african': 0.20, 'asian': 0.10}},
        'face_targets': {'chin-prominent-incr': 0.1, 'nose-point-up': 0.2, 'l-cheek-bones-incr': 0.2, 'r-cheek-bones-incr': 0.2},
        'skin': 'young_caucasian_female2', 'skin_gain': (0.86, 0.72, 0.60), 'eyes': 'eye_hazel.png',
        'hair': 'long01', 'hair_tint': 'hair_dark', 'brows': 'brow_dark',
        'garments': {'tee': {'all': 'cream'}, 'vpants': {'all': 'trouser_blue'}, 'shoes03': {'all': 'boot'}},
    },
    'Carpenter': {
        'display': 'Carpenter', 'story_tag': 'cast.carpenter', 'era': 'past',
        'macros': {'gender': 1.0, 'age': 0.47, 'muscle': 0.62, 'weight': 0.45, 'height': 0.6,
                   'race': {'caucasian': 0.85, 'african': 0.08, 'asian': 0.07}},
        'face_targets': {'chin-width-incr': 0.15, 'nose-scale-vert-incr': 0.1, 'mouth-scale-horiz-incr': 0.1},
        'skin_texture': 'skin_carpenter_stubble.png', 'skin': 'young_caucasian_male', 'skin_gain': (0.94, 0.82, 0.70),
        'eyes': 'eye_hazel.png', 'hair': 'short04', 'hair_tint': 'hair_brown', 'brows': 'brow_dark',
        'garments': {'casual01': {'shirt': 'cream', 'trousers': 'trouser_brown'}, 'vboots': {'all': 'boot'}},
    },
    'Archivist': {
        'display': 'Archivist', 'story_tag': 'cast.archivist', 'era': 'present',
        'macros': {'gender': 1.0, 'age': 0.77, 'muscle': 0.38, 'weight': 0.55, 'height': 0.48,
                   'race': {'caucasian': 0.82, 'african': 0.08, 'asian': 0.10}},
        'face_targets': {'head-age-incr': 0.35, 'nose-scale-vert-incr': 0.2, 'nose-hump-incr': 0.25, 'forehead-scale-vert-incr': 0.2,
                         'l-eye-bag-incr': 0.4, 'r-eye-bag-incr': 0.4},
        'skin_texture': 'skin_archivist_beard.png', 'skin': 'old_caucasian_male', 'skin_gain': (0.96, 0.88, 0.80),
        'eyes': 'eye_darkbrown.png', 'hair': 'short02', 'hair_tint': 'hair_gray', 'brows': 'brow_gray',
        'beard': ('short', 'beard_archivist.png', 0.004),
        'garments': {'robe': {'robe': 'navy_coat', 'rope': 'gold'}, 'shoes01': {'all': 'shoe_dark'}},
    },
    'Baker': {
        'display': 'Baker', 'story_tag': 'cast.baker', 'era': 'past',
        'macros': {'gender': 0.0, 'age': 0.50, 'muscle': 0.42, 'weight': 0.58, 'height': 0.46,
                   'race': {'caucasian': 0.85, 'african': 0.05, 'asian': 0.10}},
        'face_targets': {'l-cheek-volume-incr': 0.3, 'r-cheek-volume-incr': 0.3, 'nose-point-up': 0.15, 'mouth-angles-up': 0.25},
        'skin': 'young_caucasian_female', 'skin_gain': (1.0, 0.90, 0.82), 'eyes': 'eye_amber.png',
        'hair': 'short04', 'hair_tint': 'hair_auburn', 'brows': 'brow_dark',
        'garments': {'tee': {'all': 'rust'}, 'dress': {'all': 'rust', 'kind': 'linen'}, 'shoes01': {'all': 'shoe_dark'}},
    },
    'ShrineKeeper': {
        'display': 'Shrine Keeper', 'story_tag': 'cast.shrinekeeper', 'era': 'present',
        'macros': {'gender': 0.0, 'age': 0.88, 'muscle': 0.32, 'weight': 0.48, 'height': 0.36,
                   'race': {'caucasian': 0.80, 'african': 0.10, 'asian': 0.10}},
        'face_targets': {'head-age-incr': 0.5, 'l-eye-bag-incr': 0.4, 'r-eye-bag-incr': 0.4, 'mouth-angles-up': 0.2},
        'skin': 'old_caucasian_female', 'skin_gain': (0.96, 0.88, 0.82), 'eyes': 'eye_greyblue.png',
        'hair': 'short04', 'hair_tint': 'hair_white', 'brows': 'brow_gray',
        'garments': {'kimono': {'all': 'teal_deep', 'kind': 'linen'}, 'shoes01': {'all': 'shoe_dark'}},
    },
    'LanternKeeper': {
        'display': 'Lantern Keeper', 'story_tag': 'cast.lanternkeeper', 'era': 'present',
        'macros': {'gender': 1.0, 'age': 0.82, 'muscle': 0.52, 'weight': 0.6, 'height': 0.5,
                   'race': {'caucasian': 0.82, 'african': 0.10, 'asian': 0.08}},
        'face_targets': {'head-age-incr': 0.4, 'nose-scale-depth-incr': 0.2, 'nose-width1-incr': 0.2, 'l-eye-bag-incr': 0.3,
                         'r-eye-bag-incr': 0.3, 'chin-width-incr': 0.2},
        'skin_texture': 'skin_lanternkeeper_beard.png', 'skin': 'old_caucasian_male', 'skin_gain': (0.90, 0.78, 0.68),
        'eyes': 'eye_greyblue.png', 'hair': 'short01', 'hair_tint': 'hair_gray', 'brows': 'brow_gray',
        'beard': ('full', 'beard_lanternkeeper.png', 0.007),
        'garments': {'casual05': {'jacket': 'navy_coat', 'shirt': 'leather', 'trousers': 'trouser_slate', 'buttons': 'brass',
                                  'kinds': {'trousers': 'canvas'}},
                     'vboots': {'all': 'boot'}},
    },
    'Tavi': {
        'display': 'Dockworker', 'working_name': 'Tavi', 'story_tag': 'cast.dockworker', 'era': 'past',
        'macros': {'gender': 1.0, 'age': 0.55, 'muscle': 0.64, 'weight': 0.48, 'height': 0.56,
                   'race': {'caucasian': 0.55, 'african': 0.35, 'asian': 0.10}},
        'face_targets': {'chin-prominent-incr': 0.2, 'nose-flaring-incr': 0.2, 'l-cheek-bones-incr': 0.15, 'r-cheek-bones-incr': 0.15},
        'skin_texture': 'skin_tavi_stubble.png', 'skin': 'young_caucasian_male2', 'skin_gain': (0.74, 0.58, 0.46),
        'eyes': 'eye_darkbrown.png', 'hair': 'short02', 'hair_tint': 'hair_black', 'brows': 'brow_dark',
        'garments': {'casual06': {'shirt': 'ochre', 'trousers': 'trouser_slate', 'kinds': {'shirt': 'canvas'}},
                     'shoes03': {'all': 'boot'}},
    },
}


# ---------------------------------------------------------------- garment operations (export copies)
def cut_faces(obj, predicate):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    matrix = obj.matrix_world
    remove = [f for f in bm.faces if predicate(matrix @ f.calc_center_median())]
    if remove:
        bmesh.ops.delete(bm, geom=remove, context='FACES')
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return len(remove)


def hem_z(obj, half_width=0.14):
    zs = [(obj.matrix_world @ v.co).z for v in obj.data.vertices if abs((obj.matrix_world @ v.co).x) < half_width]
    return min(zs) if zs else None


def top_z(obj, quantile=0.97):
    zs = sorted((obj.matrix_world @ v.co).z for v in obj.data.vertices)
    return zs[int(len(zs) * quantile)] if zs else None


def band_material(obj, material, z_max, z_min=-10.0):
    obj.data.materials.append(material)
    index = len(obj.data.materials) - 1
    matrix = obj.matrix_world
    count = 0
    for poly in obj.data.polygons:
        z = (matrix @ poly.center).z
        if z_min <= z <= z_max:
            poly.material_index = index
            count += 1
    return count


def tuck_into_boots(trousers, boots, overlap=0.045):
    limit = top_z(boots, 0.985) - overlap
    return cut_faces(trousers, lambda c: c.z < limit and abs(c.x) < 0.5)


# ---------------------------------------------------------------- role wardrobe + pose
def chest_front(ctx, dz=0.0):
    z = ctx.spine3.z + dz
    y, _ = ctx.front_y(0.0, z)
    return (y if y is not None else ctx.spine3.y - 0.12), z


def wardrobe_HarborClerk(ctx, M, G):
    tee_hem = hem_z(G['tee'])
    cut_faces(G['dress'], lambda c: c.z > tee_hem + 0.035)
    ctx.invalidate()
    belt(ctx, 'SC_HarborClerk_Belt', M['leather'], tee_hem + 0.015, width=0.06, thickness=0.008, buckle=M['brass'])
    satchel(ctx, 'SC_HarborClerk_Satchel', M['leather'], M['leather_dark'], side='l')
    pouch(ctx, 'SC_HarborClerk_Pouch', M['leather_dark'], -120, tee_hem + 0.0)
    bun(ctx, 'SC_HarborClerk_Bun', M['hair'])


def pose_HarborClerk(ctx, M):
    rig = ctx.rig
    fy, cz = chest_front(ctx, -0.1)
    ik_arm(rig, 'l', (0.07, fy - 0.12, cz - 0.07), (1.0, 0.7, -0.6))
    aim(rig, 'hand_l', bone_dir(rig, 'lowerarm_l') + Vector((-0.25, -0.1, 0.1)))
    orient_palm(rig, 'l', (0.0, 0.1, 1.0))
    curl(rig, 'l', (10, 14, 8), (10, 15, 10))
    ik_arm(rig, 'r', (-0.02, fy - 0.16, cz - 0.01), (-1.0, 0.6, -0.7))
    aim(rig, 'hand_r', (0.35, -0.35, -0.85))
    orient_palm(rig, 'r', (0.2, 0.3, -1.0))
    curl(rig, 'r', (35, 55, 40), (15, 25, 20))
    look(rig, pitch=14, yaw=6)
    open_book(ctx, 'SC_HarborClerk_Ledger', 'l', M['leather_dark'], M['paper'])
    pencil(ctx, 'SC_HarborClerk_Pencil', 'r', M['wood'])


def wardrobe_Boatwright(ctx, M, G):
    tuck_into_boots(G['worksuit'], G['vboots'])
    ctx.invalidate()
    z = ctx.spine1.z - 0.05
    belt(ctx, 'SC_Boatwright_ToolBelt', M['leather'], z, width=0.065, thickness=0.01, buckle=M['iron'])
    belt_tool(ctx, 'SC_Boatwright_Hammer', M['wood'], M['iron'], side='r', z=z)
    belt_tool(ctx, 'SC_Boatwright_Chisel', M['wood'], M['iron'], side='l', z=z)
    pouch(ctx, 'SC_Boatwright_Pouch', M['leather_dark'], -20, z - 0.03, (0.07, 0.06, 0.03))


def pose_Boatwright(ctx, M):
    rig = ctx.rig
    fy, cz = chest_front(ctx, -0.12)
    ik_arm(rig, 'l', (-0.11, fy - 0.075, cz - 0.03), (0.9, 0.4, -0.7))
    aim(rig, 'hand_l', (-0.45, 0.75, 0.25))
    orient_palm(rig, 'l', (0.0, 1.0, 0.2))
    curl(rig, 'l', (25, 40, 30), (10, 15, 10))
    ik_arm(rig, 'r', (0.12, fy - 0.115, cz + 0.035), (-0.9, 0.4, -0.7))
    aim(rig, 'hand_r', (0.45, 0.75, 0.25))
    orient_palm(rig, 'r', (0.0, 1.0, 0.2))
    curl(rig, 'r', (25, 40, 30), (10, 15, 10))
    look(rig, pitch=-3, yaw=-8)


def wardrobe_Fisherwoman(ctx, M, G):
    tee_hem = hem_z(G['tee'])
    z_cut = ctx.knee['l'].z - 0.13
    leg_cuffs(ctx, 'SC_Fisherwoman_Cuff', M['cuff'], G['vpants'], z_cut)
    ctx.invalidate()
    belt(ctx, 'SC_Fisherwoman_Belt', M['leather'], tee_hem + 0.01, width=0.045, thickness=0.008, buckle=M['iron'])
    pouch(ctx, 'SC_Fisherwoman_Pouch', M['leather_dark'], -30, tee_hem - 0.02)
    pouch(ctx, 'SC_Fisherwoman_Knife', M['leather_dark'], -150, tee_hem - 0.04, (0.03, 0.08, 0.02))
    neck_scarf(ctx, 'SC_Fisherwoman_Scarf', M['scarf'], tube=0.013, drape='tails', tail_len=0.26)
    head_cover(ctx, 'SC_Fisherwoman_Bandana', M['bandana'], kind='bandana')


def pose_Fisherwoman(ctx, M):
    rig = ctx.rig
    hip = ctx.hip['l']
    ik_arm(rig, 'l', (hip.x + 0.10, hip.y - 0.10, hip.z + 0.04), (1.0, 1.0, -0.2))
    aim(rig, 'hand_l', (0.15, -0.25, -0.95))
    orient_palm(rig, 'l', (-1.0, 0.0, 0.0))
    curl(rig, 'l', (45, 60, 45), (20, 30, 20))
    relaxed_arm(rig, 'r', out=0.16, forward=0.05)
    look(rig, pitch=-4, yaw=-10)
    rope_coil(ctx, 'SC_Fisherwoman_Rope', 'l', M['rope'])


def wardrobe_Carpenter(ctx, M, G):
    tuck_into_boots(G['casual01'], G['vboots'])
    ctx.invalidate()
    z = ctx.spine1.z - 0.06
    suspenders(ctx, 'SC_Carpenter_Suspenders', M['leather'], M['iron'], z + 0.02)
    belt(ctx, 'SC_Carpenter_ToolBelt', M['leather_dark'], z, width=0.05, thickness=0.01, buckle=M['iron'])
    belt_tool(ctx, 'SC_Carpenter_Hammer', M['wood'], M['iron'], side='l', z=z)
    pouch(ctx, 'SC_Carpenter_NailPouch', M['leather'], -140, z - 0.05, (0.07, 0.07, 0.035))
    neck_scarf(ctx, 'SC_Carpenter_Neckerchief', M['scarf'], tube=0.009, drape='triangle', drape_len=0.12)


def pose_Carpenter(ctx, M):
    rig = ctx.rig
    relaxed_arm(rig, 'l', out=0.12)
    centre, axis, normal, side = plank_on_shoulder(ctx, 'SC_Carpenter_Plank', M['wood_pale'])
    grip = centre - axis * 0.42 - normal * 0.05
    ik_arm(rig, 'r', grip + Vector((-0.02, 0.0, -0.04)), (-1.0, 0.2, -0.8))
    aim(rig, 'hand_r', (0.15, -0.3, 0.95))
    orient_palm(rig, 'r', (0.4, 0.0, 1.0))
    curl(rig, 'r', (40, 55, 45), (15, 25, 20))
    look(rig, pitch=-2, yaw=-12)


def wardrobe_Archivist(ctx, M, G):
    ctx.invalidate()
    glasses(ctx, 'SC_Archivist_Glasses', M['brass'])
    satchel(ctx, 'SC_Archivist_Satchel', M['leather'], M['leather_dark'], side='r', size=(0.11, 0.09, 0.03))


def pose_Archivist(ctx, M):
    rig = ctx.rig
    fy, cz = chest_front(ctx, -0.16)
    ik_arm(rig, 'l', (0.10, fy - 0.15, cz - 0.04), (1.0, 0.6, -0.6))
    aim(rig, 'hand_l', bone_dir(rig, 'lowerarm_l') + Vector((-0.3, 0.0, 0.1)))
    orient_palm(rig, 'l', (0.0, 0.1, 1.0))
    curl(rig, 'l', (12, 18, 10), (10, 15, 10))
    relaxed_arm(rig, 'r', out=0.12)
    look(rig, pitch=8, yaw=5)
    closed_stack(ctx, 'SC_Archivist_Papers', 'l', M['leather_dark'], M['paper'])


def wardrobe_Baker(ctx, M, G):
    tee_hem = hem_z(G['tee'])
    cut_faces(G['dress'], lambda c: c.z > tee_hem + 0.035)
    ctx.invalidate()
    apron(ctx, 'SC_Baker_Apron', M['apron'], tee_hem + 0.01, ctx.knee['l'].z - 0.22, 0.17, 0.22,
          bib_top_z=ctx.spine3.z + 0.05, bib_half=0.11, offset=0.012, band_material=M['apron'])
    head_cover(ctx, 'SC_Baker_Kerchief', M['kerchief'], kind='kerchief', tails=False)


def pose_Baker(ctx, M):
    rig = ctx.rig
    waist = ctx.spine1
    fy, _ = ctx.front_y(0.0, waist.z)
    fy = fy if fy is not None else waist.y - 0.12
    for side, sx in (('l', 1), ('r', -1)):
        ik_arm(rig, side, (sx * 0.15, fy - 0.20, waist.z - 0.02), (sx * 1.0, 0.7, -0.6))
        aim(rig, 'hand_' + side, (-sx * 0.2, -0.55, -0.8))
        orient_palm(rig, side, (-sx * 1.0, 0.0, 0.2))
        curl(rig, side, (40, 55, 40), (15, 25, 20))
    look(rig, pitch=6, yaw=4)
    basket_with_bread(ctx, 'SC_Baker', M['wicker'], M['crust'])


def wardrobe_ShrineKeeper(ctx, M, G):
    ctx.invalidate()
    z = ctx.spine1.z - 0.01
    belt(ctx, 'SC_ShrineKeeper_Sash', M['gold'], z, width=0.07, thickness=0.006)
    pouch(ctx, 'SC_ShrineKeeper_Charms', M['brass'], -60, z - 0.06, (0.025, 0.03, 0.01))
    under_panel(ctx, 'SC_ShrineKeeper_Underlayer', M['apron'], ctx.neck.z - 0.005, ctx.spine2.z, 0.07, 0.10)
    neck_scarf(ctx, 'SC_ShrineKeeper_Shawl', M['shawl'], tube=0.016, drape='tails', tail_len=0.36)
    bun(ctx, 'SC_ShrineKeeper_Bun', M['hair'], size=(0.036, 0.03, 0.033))


def pose_ShrineKeeper(ctx, M):
    rig = ctx.rig
    fy, cz = chest_front(ctx, -0.22)
    ik_arm(rig, 'r', (-0.02, fy - 0.16, cz + 0.02), (-1.0, 0.7, -0.6))
    aim(rig, 'hand_r', (0.3, -0.4, -0.85))
    orient_palm(rig, 'r', (1.0, 0.0, 0.0))
    curl(rig, 'r', (45, 60, 45), (20, 30, 20))
    ik_arm(rig, 'l', (0.06, fy - 0.15, cz - 0.10), (1.0, 0.7, -0.6))
    aim(rig, 'hand_l', (-0.4, -0.5, 0.2))
    orient_palm(rig, 'l', (0.0, 0.2, 1.0))
    curl(rig, 'l', (18, 24, 14), (10, 15, 10))
    look(rig, pitch=10, yaw=-4)
    lantern(ctx, 'SC_ShrineKeeper_Lantern', 'r', M['brass'], M['glow'])


def wardrobe_LanternKeeper(ctx, M, G):
    tuck_into_boots(G['casual05'], G['vboots'])
    ctx.invalidate()
    z = ctx.spine1.z - 0.05
    belt(ctx, 'SC_LanternKeeper_Belt', M['leather_dark'], z, width=0.05, thickness=0.01, buckle=M['brass'])
    belt_tool(ctx, 'SC_LanternKeeper_OilCan', M['brass'], M['iron'], side='l', z=z, kind='oilcan')
    pouch(ctx, 'SC_LanternKeeper_Pouch', M['leather'], -140, z - 0.04, (0.06, 0.06, 0.03))
    neck_scarf(ctx, 'SC_LanternKeeper_Scarf', M['scarf'], tube=0.013, drape=None)
    head_cover(ctx, 'SC_LanternKeeper_Cap', M['cap'], kind='cap', brim_material=M['cap'])


def pose_LanternKeeper(ctx, M):
    rig = ctx.rig
    sh = ctx.sh['r']
    ik_arm(rig, 'r', (sh.x - 0.12, sh.y - 0.22, sh.z - 0.16), (-1.0, 0.3, -0.9))
    aim(rig, 'hand_r', (0.55, -0.75, 0.1))
    orient_palm(rig, 'r', (0.8, 0.0, 0.0))
    curl(rig, 'r', (50, 65, 50), (25, 35, 25))
    relaxed_arm(rig, 'l', out=0.14)
    look(rig, pitch=-16, yaw=-8)
    staff_with_lantern(ctx, 'SC_LanternKeeper', M['wood'], M['iron'], M['glow'])


def wardrobe_Tavi(ctx, M, G):
    ctx.invalidate()
    z = ctx.spine1.z - 0.07
    belt(ctx, 'SC_Tavi_Belt', M['leather_dark'], z, width=0.04, thickness=0.008, buckle=M['iron'])
    neck_scarf(ctx, 'SC_Tavi_Neckerchief', M['scarf'], tube=0.009, drape='triangle', drape_len=0.10)


def pose_Tavi(ctx, M):
    rig = ctx.rig
    sh = ctx.sh['l']
    ik_arm(rig, 'l', (sh.x + 0.02, sh.y - 0.16, ctx.spine1.z + 0.04), (1.0, 0.8, -0.4))
    aim(rig, 'hand_l', (-0.1, -0.85, 0.3))
    orient_palm(rig, 'l', (-1.0, 0.0, 0.3))
    curl(rig, 'l', (30, 45, 30), (15, 20, 15))
    relaxed_arm(rig, 'r', out=0.14)
    look(rig, pitch=0, yaw=-14)
    bundle_under_arm(ctx, 'SC_Tavi_Bundle', M['bundle'], M['rope'])


def role_materials(role, R):
    """Shared accessory materials (tinted procedural detail textures)."""
    M = {
        'leather': fabric('M_SC_%s_Leather' % role, 'leather', P['leather'], roughness=0.62, tiling=(3, 3), two_sided=False, specular=0.4),
        'leather_dark': fabric('M_SC_%s_LeatherDark' % role, 'leather', P['leather_dark'], roughness=0.6, tiling=(3, 3), two_sided=False, specular=0.4),
        'brass': flat('M_SC_%s_Brass' % role, P['brass'], roughness=0.38, metallic=1.0),
        'iron': flat('M_SC_%s_Iron' % role, P['iron'], roughness=0.45, metallic=1.0),
        'wood': fabric('M_SC_%s_Wood' % role, 'wood', P['wood'], roughness=0.7, tiling=(1, 4), two_sided=False),
        'paper': fabric('M_SC_%s_Paper' % role, 'paper', P['paper'], roughness=0.9, tiling=(2, 2), two_sided=True),
    }
    extra = {
        'Fisherwoman': {'cuff': fabric('M_SC_Fisherwoman_Cuff', 'canvas', P['trouser_blue'], tiling=(4, 2)),
                        'scarf': fabric('M_SC_Fisherwoman_Scarf', 'wool', P['scarf_blue'], tiling=(6, 6)),
                        'bandana': fabric('M_SC_Fisherwoman_Bandana', 'linen', P['bandana_red'], tiling=(5, 5)),
                        'rope': fabric('M_SC_Fisherwoman_Rope', 'rope', P['rope'], tiling=(1, 6), two_sided=False)},
        'Carpenter': {'scarf': fabric('M_SC_Carpenter_Neckerchief', 'linen', P['scarf_rust'], tiling=(6, 6)),
                      'wood_pale': fabric('M_SC_Carpenter_Plank', 'wood', P['wood_pale'], roughness=0.75, tiling=(1, 3), two_sided=False)},
        'Baker': {'apron': fabric('M_SC_Baker_Apron', 'linen', P['apron_white'], tiling=(4, 4)),
                  'kerchief': fabric('M_SC_Baker_Kerchief', 'linen', P['apron_white'], tiling=(5, 5)),
                  'wicker': fabric('M_SC_Baker_Wicker', 'wicker', P['wicker'], roughness=0.8, tiling=(2, 1)),
                  'crust': fabric('M_SC_Baker_Bread', 'crust', P['crust'], roughness=0.75, tiling=(2, 2), two_sided=False)},
        'ShrineKeeper': {'gold': fabric('M_SC_ShrineKeeper_Sash', 'canvas', P['gold'], roughness=0.6, tiling=(6, 2)),
                         'apron': fabric('M_SC_ShrineKeeper_Underlayer', 'linen', P['cream'], tiling=(4, 4)),
                         'shawl': fabric('M_SC_ShrineKeeper_Shawl', 'wool', P['teal'], tiling=(6, 6)),
                         'glow': flat('M_SC_ShrineKeeper_Flame', P['glow'], roughness=0.5, emissive=P['glow'], emissive_strength=8.0)},
        'LanternKeeper': {'scarf': fabric('M_SC_LanternKeeper_Scarf', 'wool', P['scarf_blue'], tiling=(6, 6)),
                          'cap': fabric('M_SC_LanternKeeper_Cap', 'wool', P['navy'], tiling=(6, 6)),
                          'glow': flat('M_SC_LanternKeeper_Flame', P['glow'], roughness=0.5, emissive=P['glow'], emissive_strength=8.0)},
        'Tavi': {'scarf': fabric('M_SC_Tavi_Neckerchief', 'linen', P['bandana_red'], tiling=(6, 6)),
                 'bundle': fabric('M_SC_Tavi_Bundle', 'canvas', P['canvas_sand'], tiling=(3, 3)),
                 'rope': fabric('M_SC_Tavi_Cord', 'rope', P['rope'], tiling=(1, 6), two_sided=False)},
    }
    M.update(extra.get(role, {}))
    hair_texture = SYSTEM / 'hair' / R['hair'] / ('%s_diffuse.png' % ('afro' if R['hair'] == 'afro01' else R['hair']))
    M['hair'] = lumtint('M_SC_%s_Hair' % role, hair_texture, P[R['hair_tint']], contrast=0.95, roughness=0.6,
                        masked=True, two_sided=True)
    return M


# ---------------------------------------------------------------- pipeline
def _name_matches(obj, path):
    folder = Path(path).parent.name.lower()
    stem = Path(path).stem.lower()
    name = obj.name.lower()
    return folder in name or stem in name


def build_role(role, svc, run):
    R = ROLES[role]
    clean_scene()
    out_dir = OUT / role / 'builds' / run
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    log('== building', role, '->', out_dir)
    macros = svc.TargetService.get_default_macro_info_dict()
    macros.update(R['macros'])
    body = svc.HumanService.create_human(scale=0.1, macro_detail_dict=macros)
    body.name = role + '_SourceBody'
    targets = []
    for name, value in R.get('face_targets', {}).items():
        path = target_file(name)
        svc.TargetService.load_target(body, str(path), weight=value)
        targets.append({'name': name, 'weight': value})
    skin_dir = SYSTEM / 'skins' / R['skin']
    skin_image = TEX / R['skin_texture'] if R.get('skin_texture') else None
    if skin_image is None:
        for line in (skin_dir / (R['skin'] + '.mhmat')).read_text(errors='replace').splitlines():
            if line.startswith('diffuseTexture '):
                skin_image = skin_dir / line.split(None, 1)[1].strip()
    body.data.materials.clear()
    body.data.materials.append(textured('M_SC_%s_Skin' % role, skin_image, R['skin_gain'], roughness=0.6, specular=0.42))
    rig = svc.HumanService.add_builtin_rig(body, 'game_engine')
    M = role_materials(role, R)
    regions = json.loads((TEX / 'garment_regions.json').read_text())
    sources = [('Eyes', None, asset_path('system', 'eyes/low-poly/low-poly.mhclo')),
               ('Eyebrows', None, asset_path('system', 'eyebrows/eyebrow002/eyebrow002.mhclo')),
               ('Eyelashes', None, asset_path('system', 'eyelashes/eyelashes01/eyelashes01.mhclo')),
               ('Hair', None, asset_path('system', 'hair/%s/%s.mhclo' % (R['hair'], R['hair'])))]
    sources += [('Clothes', key, asset_path(*GARMENTS[key])) for key in R['garments']]
    notes = []
    for kind, key, path in sources:
        obj = svc.HumanService.add_mhclo_asset(str(path), body, asset_type=kind, subdiv_levels=0, material_type='GAMEENGINE')
        assert obj and obj.type == 'MESH', ('asset failed', path)
        obj.data.materials.clear()
        if kind == 'Eyes':
            obj.data.materials.append(textured('M_SC_%s_Eyes' % role, TEX / R['eyes'], (1, 1, 1), roughness=0.22, specular=0.5))
        elif kind == 'Eyebrows':
            obj.data.materials.append(textured('M_SC_%s_Brows' % role, SYSTEM / 'eyebrows/eyebrow002/eyebrow002.png',
                                               P[R['brows']], 0.85, masked=True))
        elif kind == 'Eyelashes':
            obj.data.materials.append(textured('M_SC_%s_Lashes' % role, SYSTEM / 'eyelashes/eyelashes01/eyelashes01.png',
                                               (0.30, 0.24, 0.18), 0.9, masked=True))
        elif kind == 'Hair':
            obj.data.materials.append(M['hair'])
        else:
            spec = R['garments'][key]
            if key in REGION_KEYS:
                region_list = regions[REGION_KEYS[key]]['regions']
                names = sorted(set(region_list))
                if len(obj.data.polygons) == len(region_list):
                    index = {}
                    for region in names:
                        colour_key = spec.get(region, spec.get('all', 'cream'))
                        metallic = colour_key in ('brass', 'iron')
                        mat = garment_material(role, key, region, P[colour_key],
                                               roughness=0.42 if metallic else 0.86,
                                               kind=spec.get('kinds', {}).get(region))
                        if metallic:
                            mat.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value = 1.0
                            MATERIAL_RECIPES[mat.name]['metallic'] = 1.0
                        obj.data.materials.append(mat)
                        index[region] = len(obj.data.materials) - 1
                    for poly, region in zip(obj.data.polygons, region_list):
                        poly.material_index = index[region]
                else:
                    notes.append('%s: face count %d differs from region map %d; single colour used'
                                 % (key, len(obj.data.polygons), len(region_list)))
                    first = next(v for v in spec.values() if isinstance(v, str))
                    obj.data.materials.append(garment_material(role, key, 'Main', P[first]))
            else:
                obj.data.materials.append(garment_material(role, key, 'Main', P[spec['all']], kind=spec.get('kind')))
    log('assets fitted', role)
    export_rig = svc.ExportService.create_character_copy(body, name_suffix='_Export')
    export_body = svc.ObjectService.find_object_of_type_amongst_nearest_relatives(export_rig)
    svc.TargetService.bake_targets(export_body)
    svc.FaceService.load_targets(export_body, load_microsoft_visemes=False, load_meta_visemes=False, load_arkit_faceunits=True)
    svc.FaceService.interpolate_targets(export_body)
    svc.ExportService.bake_modifiers_remove_helpers(export_body, bake_masks=True, bake_subdiv=False, remove_helpers=True)
    export_rig.name = 'SK_SC_' + role
    export_body.name = 'SK_SC_%s_Body' % role
    for obj in base.descendants(rig):
        obj.hide_render = True
        obj.hide_set(True)
    meshes = [o for o in base.descendants(export_rig) if o.type == 'MESH']
    G = {}
    for kind, key, path in sources:
        if key:
            match = [o for o in meshes if o is not export_body and _name_matches(o, path)]
            assert match, ('export garment not found', key, [o.name for o in meshes])
            G[key] = match[0]
    hair = [o for o in meshes if R['hair'] in o.name.lower()]
    eyes = next((o for o in meshes if 'low-poly' in o.name.lower()), None)
    mpfb_meshes = list(meshes)
    for obj in mpfb_meshes:
        for modifier in list(obj.modifiers):
            if modifier.type == 'SUBSURF':
                obj.modifiers.remove(modifier)
        for poly in obj.data.polygons:
            poly.use_smooth = True
    ctx = Ctx(role, export_rig, export_body, list(G.values()), hair, eyes)
    ctx.notes.extend(notes)
    log('landmarks', role, 'height %.3f m' % ctx.height, 'head', tuple(round(c, 3) for c in ctx.head_center))
    del ARM_SKIP_LOG[:]
    globals()['wardrobe_' + role](ctx, M, G)
    seen = {}
    for name, total, skipped in ARM_SKIP_LOG:
        seen[name] = (total, skipped)
    log('arm-free surfaces', role, {k: '%d/%d skipped' % (v[1], v[0]) for k, v in seen.items()})
    ctx.notes.append('arm-free wardrobe surfaces (faces skipped/total): ' +
                     json.dumps({k: [v[1], v[0]] for k, v in seen.items()}))
    if R.get('beard'):
        style, texture, thickness = R['beard']
        beard_mat = textured('M_SC_%s_Beard' % role, TEX / texture, (1, 1, 1), roughness=0.75, masked=True,
                             two_sided=True, specular=0.3)
        beard_shell(ctx, 'SC_%s_Beard' % role, TEX / ('shellmask_%s.png' % style), beard_mat, thickness=thickness)
    occlusion = occlude_covered_skin(ctx, list(G.values()))
    log('wardrobe done', role, occlusion)
    exported = base.descendants(export_rig)
    required = importlib.import_module(PACKAGE + '.services.faceservice').ARKIT_FACEUNITS
    keys = base.canonical_morphs(exported, required)
    metrics = base.effective_morph_metrics(exported, keys)
    prepare_pose(export_rig)
    globals()['pose_' + role](ctx, M)
    action = bake_idle(export_rig, base.descendants(export_rig), role,
                       head_yaw=R.get('head_yaw', 2.0))
    log('posed and animated', role, action)
    studio, camera = setup_studio(ctx)
    previews = render_views(ctx, out_dir, camera)
    for obj in studio:
        bpy.data.objects.remove(obj, do_unlink=True)
    log('renders', role, len(previews))
    exported = base.descendants(export_rig)
    stats = mesh_stats(exported)
    recipes = {}
    for obj in exported:
        if obj.type == 'MESH':
            for mat in obj.data.materials:
                if mat and mat.name in MATERIAL_RECIPES:
                    recipes[mat.name] = MATERIAL_RECIPES[mat.name]
    height = ctx.height
    fbx, conversion = export_fbx(ctx, out_dir, exported)
    blend = out_dir / ('%s_SupportingCast.blend' % role)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), copy=True)
    manifest = {
        'success': True, 'builder': BUILDER_VERSION, 'role': role, 'display_name': R['display'],
        'working_name': R.get('working_name'), 'story_tag': R['story_tag'], 'era': R['era'], 'run': run,
        'generator_parameters_visual_only': macros, 'face_targets': targets, 'height_m': height,
        'skeleton': 'MPFB2 game_engine', 'bone_count': len(export_rig.data.bones),
        'bones': sorted(b.name for b in export_rig.data.bones),
        'fbx': {'path': str(fbx), 'sha256': sha(fbx)}, 'blend': str(blend), 'previews': previews,
        'animation': action, 'frames': [1, 120], 'fps': 30, 'materials': recipes, 'meshes': stats,
        'total_triangles': sum(r['triangles'] for r in stats), 'facial_morphs': keys,
        'effective_facial_morphs': metrics['effective_facial_morph_count'], 'occlusion': occlusion,
        'parts': ctx.parts, 'notes': ctx.notes, 'unit_conversion': conversion,
        'coordinate_representation': 'CentimeterData_ArmatureName', 'export_armature_object_name': export_rig.name,
        'sources': [str(p) for _, _, p in sources], 'seconds': round(time.time() - started, 1),
        'native_imported': False,
        'scope': 'Blender source candidate with review renders; not a native Unreal import or gameplay test.',
    }
    snapshot = out_dir / 'builder_snapshot.py'
    if BUILDER_FILE.is_file():
        snapshot.write_bytes(BUILDER_FILE.read_bytes())
        manifest['builder_file'] = str(BUILDER_FILE)
        manifest['builder_sha256'] = sha(BUILDER_FILE)
    manifest_path = out_dir / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + '\n', encoding='utf-8')
    (OUT / role / 'latest.json').write_text(json.dumps({'run': run, 'manifest': str(manifest_path)}, indent=2) + '\n')
    log('== done', role, '%.1fs' % (time.time() - started), 'triangles', manifest['total_triangles'])
    return str(manifest_path)


def write_status(status):
    path = OUT / 'status.json'
    path.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')


def main():
    global _LOGFILE
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    (OUT / 'logs').mkdir(parents=True, exist_ok=True)
    _LOGFILE = OUT / 'logs' / (run + '.log')
    request_file = OUT / 'request.json'
    request = json.loads(request_file.read_text()) if request_file.is_file() else {}
    roles = [r for r in (request.get('roles') or list(ROLES)) if r in ROLES]
    status = {'run': run, 'state': 'running', 'builder': BUILDER_VERSION, 'roles': {}, 'blender': bpy.app.version_string,
              'started_utc': datetime.now(timezone.utc).isoformat()}
    write_status(status)
    try:
        base.verify_sources()
        _, svc = load_mpfb()
    except Exception:
        status['state'] = 'failed'
        status['error'] = traceback.format_exc()
        log(status['error'])
        write_status(status)
        raise
    for role in roles:
        try:
            status['roles'][role] = {'ok': True, 'manifest': build_role(role, svc, run)}
        except Exception:
            error = traceback.format_exc()
            log('FAILED', role, error)
            status['roles'][role] = {'ok': False, 'error': error}
        write_status(status)
    status['state'] = 'done'
    status['finished_utc'] = datetime.now(timezone.utc).isoformat()
    write_status(status)
    log('ALL DONE', json.dumps({k: v['ok'] for k, v in status['roles'].items()}))


main()
