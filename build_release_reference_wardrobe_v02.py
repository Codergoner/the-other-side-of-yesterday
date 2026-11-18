"""Add reversible, skinned reference-palette wardrobe layers to proved humans.

Queue this script with root before running Blender. No MPFB registration, native
asset import, story-NPC replacement, source overwrite, install, or UI operation.
All existing vertices/UVs/weights, face keys, rig bones and action keys remain
unchanged. Added clothing is a candidate requiring native walking/close-up QA.

blender --background --factory-startup --python this_file -- --character Mother
Use --inspect-only for a source registry without an FBX or .blend export.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import shutil
import struct
import sys
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_release_characters as base
import build_release_unit_probe as units
from tools import windows_file_guards as files

OUT = ROOT / 'output/reference_wardrobe_v02'
TEAL = ROOT / 'assets/release_v02/materials/T_Reference_TealLinen_BaseColor_v01.png'
TEAL_PROVENANCE = ROOT / 'assets/release_v02/materials/material_provenance_v01.json'
REFERENCE = ROOT / 'docs/Release_20261026/References/05_Character_Design_Reference_v02.png'
LINEN = ROOT / 'output/release_hero_sources/textures/rough_linen/rough_linen_diff_2k.png'
SOURCE_POINTERS = {
    'Mother': ROOT / 'output/release_mother_rev11/latest.json',
    'Healer': ROOT / 'output/release_npc_variations/Healer/latest.json',
}
MOTHER_SOURCE_FBX_SHA = '865062a7039d261b64f7b31c8e611487c356dcf35b734747bbeef649a1b6c408'
TEAL_SHA = '0e36d933f845177acad8125e7c962deed0a14a6c91a0acde1203adc72c46b98a'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def read_json(path):
    with open(files.io_path(path), encoding='utf-8') as stream:
        return json.load(stream)


def write_json(path, value):
    with open(files.io_path(path), 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def load_source(role):
    pointer = SOURCE_POINTERS[role]
    manifest = Path(read_json(pointer)['manifest'])
    data = read_json(manifest)
    require(data.get('success'), 'Source manifest did not pass: ' + str(manifest))
    blend = Path(data['blend'])
    require(blend.is_file(), 'Missing original normalized source .blend')
    require(files.sha(data['fbx']['path']) == data['fbx']['sha256'], 'Source FBX changed')
    if role == 'Mother':
        require(data.get('art_revision') == 11, 'This additive Mother pass requires REV11')
        require(data['fbx']['sha256'] == MOTHER_SOURCE_FBX_SHA, 'Mother source provenance changed')
    require(data.get('coordinate_representation') == 'CentimeterData_ArmatureName', 'Do not convert another source representation implicitly')
    return pointer, manifest, blend, data


def protected(pointer, manifest, blend, data):
    result = files.native(ROOT / 'game_unreal')
    paths = [pointer, manifest, blend, Path(data['fbx']['path']), REFERENCE,
             TEAL, TEAL_PROVENANCE, LINEN, Path(base.__file__), Path(units.__file__)]
    # Exclude this candidate's output and other agents' text/source work. Protect
    # the original character source directory and existing native authoring data.
    paths += files.files(manifest.parent)
    for path in paths:
        result[files.canonical(path)] = files.sha(path)
    return result


def geometry_fingerprint(objects):
    """Include exact topology, rest positions, all UV loops, vertex groups/weights.

    Material slots intentionally differ. Shape-key coordinates and action keys
    have separate exhaustive proofs; neither is hidden by this fingerprint.
    """
    result = {}
    for obj in objects:
        if obj.type != 'MESH':
            continue
        digest = hashlib.sha256()
        mesh = obj.data
        for vertex in mesh.vertices:
            digest.update(struct.pack('<3d', *vertex.co))
            for group in vertex.groups:
                digest.update(struct.pack('<id', group.group, group.weight))
        for edge in mesh.edges:
            digest.update(struct.pack('<2i', *edge.vertices))
        for poly in mesh.polygons:
            digest.update(struct.pack('<i', len(poly.vertices)))
            digest.update(struct.pack('<' + str(len(poly.vertices)) + 'i', *poly.vertices))
        for layer in mesh.uv_layers:
            digest.update(layer.name.encode())
            for loop in layer.data:
                digest.update(struct.pack('<2d', *loop.uv))
        digest.update(json.dumps([(group.index, group.name) for group in obj.vertex_groups]).encode())
        digest.update(json.dumps([[float(v) for v in row] for row in obj.matrix_world]).encode())
        result[obj.name] = digest.hexdigest()
    return result


def animation_fingerprint(objects):
    owners = objects + [obj.data.shape_keys for obj in objects if obj.type == 'MESH' and obj.data.shape_keys]
    rows = []
    for owner in owners:
        animation = owner.animation_data
        action = animation.action if animation else None
        for index, curve in enumerate(units.curves(action)):
            rows.append([owner.name, action.name, index, curve.data_path, curve.array_index,
                [[list(p.co), list(p.handle_left), list(p.handle_right), p.interpolation] for p in curve.keyframe_points]])
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def physical_vertices(obj, scale):
    return [(obj.matrix_world @ vertex.co) * scale for vertex in obj.data.vertices]


def bounds(objects, scale):
    points = [point for obj in objects if obj.type == 'MESH' for point in physical_vertices(obj, scale)]
    require(points, 'No source mesh points')
    return {'min': [min(p[i] for p in points) for i in range(3)],
            'max': [max(p[i] for p in points) for i in range(3)]}


def influence_audit(obj, rig=None):
    histogram, examples, sums = {}, [], []
    for vertex in obj.data.vertices:
        values = [(obj.vertex_groups[g.group].name, float(g.weight)) for g in vertex.groups if g.weight > 0.0]
        if rig is not None:
            values = [(bone, weight) for bone, weight in values if bone in rig.data.bones]
        count = len(values)
        histogram[str(count)] = histogram.get(str(count), 0) + 1
        sums.append(sum(weight for _, weight in values))
        if count > 4 and len(examples) < 8:
            examples.append({'vertex': vertex.index, 'groups': values})
    return {'positive_weight_epsilon': 0.0, 'scope': 'Deform bone groups only' if rig else 'All positive vertex groups, including non-deform masks',
        'maximum_positive_influences': max(map(int, histogram), default=0),
        'influence_count_histogram': histogram, 'examples_above_four': examples,
        'maximum_weight_sum_error': max((abs(total-1) for total in sums if total > 0), default=0)}


def build_bvh(objects, scale):
    from mathutils.bvhtree import BVHTree
    points, polygons = [], []
    for obj in objects:
        offset = len(points)
        points += physical_vertices(obj, scale)
        polygons += [tuple(offset + v for v in poly.vertices) for poly in obj.data.polygons]
    return BVHTree.FromPolygons(points, polygons, all_triangles=False)


def skinned_mesh(name, points_m, faces, rig, scale, materials, weights, uv_faces=None, material_indices=None):
    """New mesh in world coordinates, attached to the existing unmodified rig."""
    import bpy
    from mathutils import Matrix
    require(len(points_m) == len(weights), 'Every added point needs explicit weights')
    mesh = bpy.data.meshes.new(name + '_Mesh')
    mesh.from_pydata([tuple(p / scale) for p in points_m], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = rig
    obj.matrix_parent_inverse = rig.matrix_world.inverted()
    obj.matrix_world = Matrix.Identity(4)
    modifier = obj.modifiers.new('Existing53BoneSkin', 'ARMATURE')
    modifier.object = rig
    for material in materials:
        mesh.materials.append(material)
    for index, assignments in enumerate(weights):
        # Retain every positive source influence, including the source's small
        # sum error, so copied panels evaluate like their fitted source surface.
        # Generated apron/belt/bun weights sum to one. No silent prune/normalize.
        require(assignments and abs(sum(assignments.values()) - 1) < 0.02, 'Unexpected source clothing weight sum')
        require(len(assignments) <= 8, 'Added clothing exceeds the explicit eight-influence candidate bound')
        for bone, weight in assignments.items():
            require(bone in rig.data.bones, 'New clothing references a missing bone: ' + bone)
            group = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
            group.add([index], weight, 'REPLACE')
    if uv_faces is not None:
        layer = mesh.uv_layers.new(name='ReferenceGarmentUV')
        for poly, coordinates in zip(mesh.polygons, uv_faces):
            require(len(coordinates) == len(poly.loop_indices), 'Wrong UV corner count')
            for loop, coordinate in zip(poly.loop_indices, coordinates):
                layer.data[loop].uv = coordinate
    for poly in mesh.polygons:
        poly.use_smooth = True
        if material_indices is not None:
            poly.material_index = material_indices[poly.index]
    return obj


def material_set(role):
    base.MATERIAL_RECIPES.clear()
    require(files.sha(TEAL) == TEAL_SHA, 'Generated teal textile changed')
    provenance = read_json(TEAL_PROVENANCE)
    require(provenance['sha256'] == TEAL_SHA, 'Teal textile provenance does not match')
    require(files.sha(REFERENCE) == provenance['reference_sha256'], 'Character design reference changed')
    prefix = 'M_ReleaseV02_' + role
    # The licensed source linen is blue. Channel gains neutralize its measured
    # mean albedo to warm cream in both Blender and the existing native recipe.
    cream = base.textured_material(prefix + '_CreamLinen', LINEN, (1.94, 1.15, 0.553), 0.94)
    teal = base.textured_material(prefix + '_MutedTealLinen', TEAL, (0.80, 0.88, 0.90), 0.91)
    leather = base.plain_material(prefix + '_WeatheredBrownLeather', (0.105, 0.052, 0.025), 0.78)
    stitch = base.plain_material(prefix + '_SandThread', (0.38, 0.27, 0.12), 0.92)
    brass = base.plain_material(prefix + '_WornBrass', (0.28, 0.17, 0.048), 0.50)
    brass.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value = 0.65
    base.MATERIAL_RECIPES[brass.name]['metallic'] = 0.65
    for material in [cream, teal]:
        material.use_backface_culling = False
        base.MATERIAL_RECIPES[material.name]['two_sided'] = True
    return {'cream': cream, 'teal': teal, 'leather': leather, 'stitch': stitch, 'brass': brass}


def replace_materials(obj, material):
    # Reassigning existing slots preserves the original per-face slot indices.
    require(len(obj.data.materials) > 0, 'Source garment has no material slots')
    for index in range(len(obj.data.materials)):
        obj.data.materials[index] = material


def source_weights(obj, index):
    values = {obj.vertex_groups[g.group].name: g.weight for g in obj.data.vertices[index].groups if g.weight > 0.0}
    require(1 <= len(values) <= 8, 'Source clothing exceeds the explicit eight-influence candidate bound')
    total = sum(values.values())
    require(total > 1e-6, 'Source clothing contains an unweighted vertex')
    require(abs(total-1) < .02, 'Source clothing weight sum requires a separate reviewed correction')
    return values


def mother_outer_panels(sweater, rig, scale, mats, height):
    """Copy fitted torso faces with their UVs/weights; cream underblouse stays intact."""
    from mathutils import Vector
    points = physical_vertices(sweater, scale)
    torso_groups = {'pelvis', 'spine_01', 'spine_02', 'spine_03', 'clavicle_l', 'clavicle_r'}
    chosen = []
    waist, top = height * 0.60, height * 0.866
    for poly in sweater.data.polygons:
        center = sum((points[i] for i in poly.vertices), Vector()) / len(poly.vertices)
        torso = sum(sum(weight for bone, weight in source_weights(sweater, i).items() if bone in torso_groups)
                    for i in poly.vertices) / len(poly.vertices)
        t = max(0.0, min(1.0, (center.z - waist) / (top - waist)))
        open_front_half_width = 0.025 + t * 0.072
        front_opening = center.y < 0 and abs(center.x) < open_front_half_width
        if waist + 0.015 < center.z < top and torso >= 0.57 and not front_opening:
            chosen.append(poly)
    require(70 <= len(chosen) <= 1900, 'Unexpected fitted outer-panel face selection')
    ids = sorted({index for poly in chosen for index in poly.vertices})
    mapped = {old: new for new, old in enumerate(ids)}
    normal_matrix = sweater.matrix_world.to_3x3().inverted().transposed()
    offset_points = []
    for index in ids:
        normal = normal_matrix @ sweater.data.vertices[index].normal
        normal.normalize()
        offset_points.append(points[index] + normal * 0.0035)
    source_uv = sweater.data.uv_layers.active
    require(source_uv is not None, 'Fitted sweater UV layer missing')
    uv_faces = [[tuple(source_uv.data[i].uv) for i in poly.loop_indices] for poly in chosen]
    return skinned_mesh('Mother_V02_FittedTealOuterPanels', offset_points,
        [tuple(mapped[i] for i in poly.vertices) for poly in chosen], rig, scale,
        [mats['teal']], [source_weights(sweater, i) for i in ids], uv_faces), {
            'source_mesh': sweater.name, 'copied_faces': len(chosen), 'surface_offset_m': 0.0035,
            'existing_cream_underblouse_preserved': True, 'scope': 'Fitted open torso panels; not a claim of a finished tailored jacket.'}


def apron(skirt, rig, scale, mats, height):
    from mathutils import Vector
    from mathutils.kdtree import KDTree
    points = physical_vertices(skirt, scale)
    tree = build_bvh([skirt], scale)
    kd = KDTree(len(points))
    for index, point in enumerate(points):
        kd.insert(point, index)
    kd.balance()
    minimum = min(p.z for p in points)
    top, bottom = height * 0.60, max(minimum + 0.035, height * 0.255)
    rows, columns = 24, 20
    vertices, assignments, uv = [], [], []
    for row in range(rows + 1):
        t = row / rows
        z = top * (1 - t) + bottom * t
        # A narrowed household apron, not an extra skirt silhouette.
        half_width = 0.105 * (1 - t) + 0.165 * t
        for column in range(columns + 1):
            u = column / columns
            x = (u * 2 - 1) * half_width
            hit, normal, face, distance = tree.ray_cast(Vector((x, -1.0, z)), Vector((0, 1, 0)), 2.0)
            require(hit is not None and hit.y < 0.1, 'Apron projection missed the existing fitted skirt')
            position = hit + Vector((0, -0.006, 0))
            vertices.append(position)
            _, source_index, _ = kd.find(hit)
            assignments.append(source_weights(skirt, source_index))
            uv.append((u, t))
    faces, uv_faces, indices = [], [], []
    for row in range(rows):
        for column in range(columns):
            a = row * (columns + 1) + column
            face = (a, a + columns + 1, a + columns + 2, a + 1)
            faces.append(face)
            uv_faces.append([uv[i] for i in face])
            indices.append(1 if row in [rows - 3, rows - 1] or column in [0, columns - 1] else 0)
    obj = skinned_mesh('Mother_V02_CreamHouseholdApron', vertices, faces, rig, scale,
        [mats['cream'], mats['teal']], assignments, uv_faces, indices)
    return obj, {'projection': 'Every grid point ray-projected onto actual source skirt rest surface',
        'rows': rows, 'columns': columns, 'surface_offset_m': 0.006,
        'weight_source': skirt.name, 'top_z_m': top, 'bottom_z_m': bottom,
        'cloth_simulation_claimed': False, 'walk_clipping_approved': False}


def belt(garments, rig, scale, mats, height, role):
    from mathutils import Vector
    tree = build_bvh(garments, scale)
    center = (rig.matrix_world @ rig.data.bones['pelvis'].head_local) * scale
    zcenter = height * 0.602
    vertices, uv = [], []
    segments = 64
    for row, dz in enumerate([-0.025, 0.025]):
        for segment in range(segments):
            angle = math.tau * segment / segments
            direction = Vector((math.cos(angle), math.sin(angle), 0))
            origin = Vector((center.x, center.y, zcenter + dz)) + direction
            hit, normal, face, distance = tree.ray_cast(origin, -direction, 1.3)
            require(hit is not None, 'Waist belt surface projection missed the fitted garment')
            require((hit - Vector((center.x, center.y, hit.z))).length < 0.40, 'Belt ray hit an unexpected arm or loose garment surface')
            vertices.append(hit + direction * 0.008)
            uv.append((segment / segments * 3, row))
    faces, uv_faces = [], []
    for segment in range(segments):
        nxt = (segment + 1) % segments
        face = (segment, nxt, nxt + segments, segment + segments)
        faces.append(face)
        uv_faces.append([uv[i] for i in face])
    obj = skinned_mesh(role + '_V02_ProjectedBrownWaistBelt', vertices, faces, rig, scale,
        [mats['leather']], [{'pelvis': 0.8, 'spine_01': 0.2} for _ in vertices], uv_faces)
    return obj, {'surface_projected': True, 'height_m': 0.05, 'segments': segments,
                 'surface_clearance_m': 0.008, 'weights': {'pelvis': 0.8, 'spine_01': 0.2},
                 'walk_clipping_approved': False}


def skirt_gold_hem(skirt, rig, scale, mats):
    from mathutils import Vector
    tree = build_bvh([skirt], scale)
    source_points = physical_vertices(skirt, scale)
    bottom = min(point.z for point in source_points)
    center = (rig.matrix_world @ rig.data.bones['pelvis'].head_local) * scale
    segments = 64
    points, faces, uv_faces = [], [], []
    # The original hem can be uneven. Find the lowest complete narrow band
    # actually supported by all 128 source-surface rays; never invent a radius.
    selected_height = None
    for clearance in [.035, .050, .065, .080, .095]:
        trial = []
        for row in [0, 1]:
            z = bottom + clearance + row*.009
            for segment in range(segments):
                angle = math.tau*segment/segments
                direction = Vector((math.cos(angle), math.sin(angle), 0))
                hit, _, _, _ = tree.ray_cast(Vector((center.x, center.y, z)) + direction, -direction, 1.3)
                if hit is None:
                    break
                trial.append(hit + direction*.0025)
        if len(trial) == segments*2:
            points, selected_height = trial, bottom + clearance
            break
    require(selected_height is not None, 'No complete low source-skirt band exists for the gold-thread hem')
    for segment in range(segments):
        nxt = (segment+1)%segments
        faces.append((segment, nxt, nxt+segments, segment+segments))
        uv_faces.append([(segment/segments*4, 0), ((segment+1)/segments*4, 0),
                         ((segment+1)/segments*4, 1), (segment/segments*4, 1)])
    obj = skinned_mesh('Mother_V02_FadedGoldThreadHem', points, faces, rig, scale, [mats['stitch']],
        [{'pelvis': .8, 'thigh_l': .1, 'thigh_r': .1} for _ in points], uv_faces)
    return obj, {'source_surface_projected': True, 'height_m': .009, 'bottom_z_m': selected_height,
        'surface_clearance_m': .0025, 'nonmetallic_faded_thread': True,
        'walk_clipping_approved': False}


def healer_scarf(robe, rig, scale, mats, height):
    """Real weighted cloth; an intact robe is retained until coat tailoring QA."""
    from mathutils import Vector
    tree = build_bvh([robe], scale)
    vertices, faces, uv_faces = [], [], []
    # Two modest overlapping front tails, projected to the actual robe surface.
    for tail, (xcenter, end) in enumerate([(-0.035, 0.68), (0.038, 0.72)]):
        start, stop = height * 0.824, height * end
        rows = 14
        offset = len(vertices)
        for row in range(rows + 1):
            t = row / rows
            for side in [-1, 1]:
                x = xcenter + side * 0.039 + t * (-0.015 if tail == 0 else 0.012)
                z = start * (1-t) + stop*t
                hit, normal, face, distance = tree.ray_cast(Vector((x, -1, z)), Vector((0, 1, 0)), 2)
                require(hit is not None, 'Healer scarf projection missed actual robe')
                vertices.append(hit + Vector((0, -0.012-tail*0.0015, 0)))
        for row in range(rows):
            a = offset + row*2
            faces.append((a, a+2, a+3, a+1))
            uv_faces.append([(0, row/rows), (0, (row+1)/rows), (0.5, (row+1)/rows), (0.5, row/rows)])
    return skinned_mesh('Healer_V02_TealScarfTails', vertices, faces, rig, scale, [mats['teal']],
        [{'spine_03': 0.75, 'spine_02': 0.25} for _ in vertices], uv_faces)


def mother_low_bun(hair, rig, scale):
    """Optional A/B clone: keep source immutable, remove clone tail faces only.

    This is a visible silhouette candidate, not a strand-groom or likeness claim.
    The fitted scalp surface, original UVs and original skin weights are retained.
    """
    import bpy
    from mathutils import Vector
    head = (rig.matrix_world @ rig.data.bones['head'].head_local) * scale
    cut = head.z + 0.012
    clone = hair.copy()
    clone.data = hair.data.copy()
    clone.name = 'Mother_V02_ClonedFittedHairCap'
    bpy.context.collection.objects.link(clone)
    clone.hide_render = False
    clone.hide_set(False)
    source_points = physical_vertices(clone, scale)
    old_vertices = [tuple(vertex.co) for vertex in clone.data.vertices]
    old_uv = {tuple(poly.vertices): [tuple(clone.data.uv_layers.active.data[i].uv) for i in poly.loop_indices]
              for poly in clone.data.polygons}
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(clone.data)
    bm.verts.ensure_lookup_table()
    doomed = [face for face in bm.faces if min(source_points[v.index].z for v in face.verts) < cut]
    count = len(doomed)
    # Actual source audit: 2,457 dense braid-tail faces and 302 fitted scalp
    # faces at this measured nape. A percentage cap incorrectly rejects it
    # because the braid carries most of this asset's geometry. Retain a real
    # measured cap, and require its actual images before any native adoption.
    retained_cap_faces = len(bm.faces) - count
    require(count > 10 and retained_cap_faces >= 250 and count < len(bm.faces)*.95,
        'Nape cut requires review: ' + json.dumps({'removed': count, 'source_faces': len(bm.faces),
            'head_m': list(head), 'cut_z_m': cut}))
    bmesh.ops.delete(bm, geom=doomed, context='FACES_ONLY')
    bm.to_mesh(clone.data)
    bm.free()
    clone.data.update()
    require(old_vertices == [tuple(vertex.co) for vertex in clone.data.vertices], 'Hair cap clone moved/deleted vertices')
    for poly in clone.data.polygons:
        require(old_uv[tuple(poly.vertices)] == [tuple(clone.data.uv_layers.active.data[i].uv) for i in poly.loop_indices],
                'A retained hair-cap UV corner changed')
    dark = base.plain_material('M_ReleaseV02_Mother_LowBunBrownHair', (0.052, 0.029, 0.016), .84)
    ridge = base.plain_material('M_ReleaseV02_Mother_LowBunStrandRidges', (0.075, 0.042, 0.022), .84)
    center = head + Vector((0, .105, .045))
    radii = Vector((.065, .044, .055))
    points, faces, uvs = [], [], []
    rings, segments = 14, 32
    for row in range(rings+1):
        phi = math.pi * (.002 + .996*row/rings)
        for segment in range(segments):
            theta = math.tau*segment/segments
            points.append(center + Vector((radii.x*math.sin(phi)*math.cos(theta),
                radii.y*math.sin(phi)*math.sin(theta), radii.z*math.cos(phi))))
    for row in range(rings):
        for segment in range(segments):
            nxt = (segment+1)%segments
            faces.append((row*segments+segment, row*segments+nxt, (row+1)*segments+nxt, (row+1)*segments+segment))
            uvs.append([(segment/segments, row/rings), ((segment+1)/segments, row/rings),
                        ((segment+1)/segments, (row+1)/rings), (segment/segments, (row+1)/rings)])
    bun = skinned_mesh('Mother_V02_LowBunVolume', points, faces, rig, scale, [dark], [{'head': 1.0} for _ in points], uvs)
    # Eight restrained elliptical surface ridges follow the gathered hair mass.
    # They are genuine geometry, with a common existing head-bone skin binding.
    points, faces, uvs = [], [], []
    around, tube = 36, 5
    for strand in range(8):
        phi = .30 + strand*(math.pi-.60)/7
        offset = len(points)
        for segment in range(around):
            theta = math.tau*segment/around + .20*phi
            normal = Vector((math.sin(phi)*math.cos(theta), math.sin(phi)*math.sin(theta), math.cos(phi)))
            tangent = Vector((-math.sin(theta), math.cos(theta), 0))
            side = tangent.cross(normal).normalized()
            origin = center + Vector((radii.x*normal.x, radii.y*normal.y, radii.z*normal.z)) + normal*.0007
            for corner in range(tube):
                angle = math.tau*corner/tube
                points.append(origin + normal*(math.cos(angle)*.0018) + side*(math.sin(angle)*.0018))
        for segment in range(around):
            nxt = (segment+1)%around
            for corner in range(tube):
                cn = (corner+1)%tube
                faces.append((offset+segment*tube+corner, offset+nxt*tube+corner,
                              offset+nxt*tube+cn, offset+segment*tube+cn))
                uvs.append([(segment/around, corner/tube), ((segment+1)/around, corner/tube),
                            ((segment+1)/around, (corner+1)/tube), (segment/around, (corner+1)/tube)])
    strands = skinned_mesh('Mother_V02_LowBunSurfaceRidges', points, faces, rig, scale, [ridge],
        [{'head': 1.0} for _ in points], uvs)
    return [clone, bun, strands], {'source_hair': hair.name, 'original_hair_source_modified': False,
        'original_hair_excluded_from_this_candidate_export': True, 'clone_tail_faces_removed': count,
        'cloned_fitted_cap_faces_retained': retained_cap_faces,
        'clone_vertices_deleted_or_moved': 0, 'retained_cap_uvs_weights_preserved': True,
        'nape_cut_z_m': cut, 'bun_center_m': list(center), 'bun_radii_m': list(radii),
        'bun_weight': {'head': 1.0}, 'hair_strand_groom_claimed': False,
        'rear_profile_neck_intersection_approved': False}


def review_images(rig, exported, output, scale, height, role):
    """Render actual normalized CM data; scale camera, lights and inverse-square power."""
    import bpy
    from mathutils import Vector
    scene = bpy.context.scene
    for obj in scene.objects:
        if obj not in exported:
            obj.hide_render = True
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.view_settings.view_transform = 'AgX'
    scene.world = bpy.data.worlds.new(role + '_V02_ReviewWorld')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (0.095, 0.105, 0.12, 1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = 0.35
    created = []
    for name, location, energy, size in [
        ('Key', (-2.2, -3.2, 3.4), 450, 3.0), ('Fill', (2.5, -1.2, 2), 170, 2.5),
        ('Rim', (0.8, 2.2, 2.5), 300, 2.0)]:
        light = bpy.data.lights.new(role + '_V02_' + name, 'AREA')
        light.energy, light.shape, light.size = energy / scale**2, 'DISK', size / scale
        obj = bpy.data.objects.new(light.name, light)
        scene.collection.objects.link(obj)
        obj.location = Vector(location) / scale
        obj.rotation_euler = (Vector((0, 0, height * 0.6)) / scale - obj.location).to_track_quat('-Z', 'Y').to_euler()
        created.append(obj)
    camera = bpy.data.objects.new(role + '_V02_ReviewCamera', bpy.data.cameras.new(role + '_V02_ReviewCamera'))
    scene.collection.objects.link(camera)
    camera.data.lens, camera.data.clip_start, camera.data.clip_end = 65, 0.01/scale, 100/scale
    scene.camera = camera
    created.append(camera)
    images = []
    shots = [('Front', (0, -3.6, height*0.66), height*.52, 1),
        ('Rear', (0, 3.6, height*.66), height*.52, 1),
        ('Profile', (3.6, -0.3, height*.66), height*.52, 1),
        ('FaceOpen', (0.04, -1.2, height*.925), height*.91, 1),
        ('FaceBlink', (0.04, -1.2, height*.925), height*.91, 46)]
    try:
        for label, location, target_z, frame in shots:
            scene.frame_set(frame)
            camera.location = Vector(location) / scale
            camera.rotation_euler = (Vector((0, 0, target_z)) / scale - camera.location).to_track_quat('-Z', 'Y').to_euler()
            file = output / (role + '_V02_' + label + '.png')
            scene.render.filepath = str(file)
            bpy.ops.render.render(write_still=True)
            images.append(str(file))
    finally:
        scene.frame_set(1)
        scene.camera = None
        for obj in created:
            bpy.data.objects.remove(obj, do_unlink=True)
    return images


def build(role, inspect_only=False, skip_previews=False, hair_style='original'):
    import bpy
    require(ROOT.name == 'Release_20261026', 'Preserve original and Quest projects')
    pointer, manifest, blend, source = load_source(role)
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    output = OUT / role / 'builds' / run
    output.mkdir(parents=True, exist_ok=False)
    before_files = protected(pointer, manifest, blend, source)
    shutil.copyfile(__file__, output / 'builder_source_snapshot.py')
    report = {'success': False, 'character': role, 'art_revision': 'reference_wardrobe_v02', 'run': run,
        'scope': 'Additive skinned source candidate. Native import, gait and likeness approval remain separate.',
        'source_manifest': str(manifest), 'source_manifest_sha256': files.sha(manifest),
        'source_blend': str(blend), 'source_blend_sha256': files.sha(blend),
        'source_fbx_sha256': source['fbx']['sha256'], 'reference': str(REFERENCE),
        'reference_sha256': files.sha(REFERENCE), 'builder_source_sha256': files.sha(__file__),
        'native_imported': False, 'native_animation_verified': False, 'visual_approved': False,
        'walk_clipping_approved': False, 'exact_reference_likeness_claimed': False,
        'export_performed': False, 'inspect_only': inspect_only, 'hair_style': hair_style, 'body_face_rig_weights_edited': False,
        'existing_garment_geometry_uv_weights_edited': False, 'hair_geometry_edited': False,
        'story_data_or_campaign_save_changed': False,
        'pending_approvals': ['Review real front/rear/profile/open/blink renders',
            'Import into a new v02 native namespace using the existing matching 53-bone skeleton',
            'Read back every effective native facial morph, scale and imported material',
            'Review existing listening and own walking clips from front/back/side before any NPC swap',
            'Check shoulder/waist/hem collisions and hands at conversation distance'],
        'remaining_reference_gaps': ['Existing authored face and hair identity are preserved; facial likeness is not recreated.',
            'Mother retains original braid; the reference low bun needs a separate sculpt and back/profile approval.',
            'Mother cream underblouse is a fitted full-sleeve source sweater, with additive open torso panels.',
            'Healer retains an intact robe, not the reference open coat; open-coat tailoring needs covered-skin repair.',
            'Healer beard, tied hair, bag and bandages are not claimed by this source pass.']}
    try:
        bpy.context.preferences.use_preferences_save = False
        bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False, use_scripts=False)
        bpy.context.preferences.use_preferences_save = False
        scene = bpy.context.scene
        scale = float(scene.unit_settings.scale_length)
        require(abs(scale - .01) < 1e-8, 'Expected already normalized centimeter data; refusing double conversion')
        rig = bpy.data.objects.get('Armature')
        require(rig is not None and rig.type == 'ARMATURE' and len(rig.data.bones) == 53, 'Wrong existing source rig')
        original = [rig] + list(rig.children_recursive)
        original = [obj for obj in original if obj == rig or obj.type == 'MESH']
        require(all(obj.type != 'MESH' or any(m.type == 'ARMATURE' and m.object == rig for m in obj.modifiers)
                    for obj in original), 'Unexpected unskinned descendant')
        scene.frame_set(1)
        bpy.context.view_layer.update()
        extent = bounds(original, scale)
        height = extent['max'][2] - min(0.0, extent['min'][2])
        require(1.25 < height < 2.1, 'Source physical scale is not human')
        report['source_registry'] = [{'name': obj.name, 'vertices': len(obj.data.vertices),
            'triangles': sum(len(p.vertices)-2 for p in obj.data.polygons),
            'materials': [m.name for m in obj.data.materials if m],
            'skin_influences': influence_audit(obj, rig),
            'physical_bounds_m': bounds([obj], scale)} for obj in original if obj.type == 'MESH']
        report.update(source_core_bone_count=len(rig.data.bones), rest_bone_names=sorted(b.name for b in rig.data.bones),
            coordinate_representation='CentimeterData_ArmatureName', scene_meters_per_unit=scale,
            measured_source_height_m=height, height_is_authoring_measurement_not_story_canon=True)
        report['physical_rest_bones_m'] = units.rest_world(rig, scale)
        if role == 'Mother':
            measured_hair = next(obj for obj in original if obj.type == 'MESH' and 'braid01' in obj.name)
            measured_points = physical_vertices(measured_hair, scale)
            measured_head_z = report['physical_rest_bones_m']['head']['head_m'][2]
            report['hair_nape_cut_audit'] = [{'cut_z_m': measured_head_z + offset,
                'tail_faces_below_cut': sum(min(measured_points[i].z for i in p.vertices) < measured_head_z + offset
                    for p in measured_hair.data.polygons),
                'retained_cap_faces': sum(min(measured_points[i].z for i in p.vertices) >= measured_head_z + offset
                    for p in measured_hair.data.polygons)} for offset in [-.03, 0, .012, .025]]
        if inspect_only:
            report['success'] = True
            return
        original_geometry = geometry_fingerprint(original)
        original_animation = animation_fingerprint(original)
        original_rest = units.basis_hash(rig)
        original_shapes = units.shape_coordinates(original, scale)
        original_poses = units.snapshot(rig, original)
        scene.frame_set(1)
        mats = material_set(role)
        additions, wardrobe, excluded = [], {}, []
        if role == 'Mother':
            sweater = next(obj for obj in original if obj.type == 'MESH' and 'toigo_fisherman_sweater' in obj.name)
            skirt = next(obj for obj in original if obj.name == 'Mother_Rev11_FULL_FittedDress')
            replace_materials(sweater, mats['cream'])
            replace_materials(skirt, mats['teal'])
            panels, wardrobe['outer_panels'] = mother_outer_panels(sweater, rig, scale, mats, height)
            household_apron, wardrobe['apron'] = apron(skirt, rig, scale, mats, height)
            waist, wardrobe['belt'] = belt([sweater, skirt], rig, scale, mats, height, role)
            gold_hem, wardrobe['gold_thread_hem'] = skirt_gold_hem(skirt, rig, scale, mats)
            additions += [panels, household_apron, waist, gold_hem]
            if hair_style == 'low-bun':
                hair = next(obj for obj in original if obj.type == 'MESH' and 'braid01' in obj.name)
                hair_parts, wardrobe['low_bun'] = mother_low_bun(hair, rig, scale)
                additions += hair_parts
                excluded.append(hair)
                report['remaining_reference_gaps'][1] = 'Optional low-bun silhouette is a cloned mesh candidate; scalp boundary, neck/ear intersections and strand quality require rear/profile review.'
        else:
            require(hair_style == 'original', 'The low-bun option belongs only to Mother')
            robe = next(obj for obj in original if obj.type == 'MESH' and 'donitz_monk_robe' in obj.name)
            replace_materials(robe, mats['cream'])
            scarf = healer_scarf(robe, rig, scale, mats, height)
            waist, wardrobe['belt'] = belt([robe], rig, scale, mats, height, role)
            additions += [scarf, waist]
            wardrobe['robe'] = {'existing_closed_robe_topology_preserved': True, 'open_coat_claimed': False}
            wardrobe['scarf'] = {'real_skinned_surface_projected_front_tails': True, 'neck_loop_or_cloth_simulation_claimed': False}
        exported = [obj for obj in original if obj not in excluded] + additions
        report['candidate_only_excluded_source_meshes'] = [obj.name for obj in excluded]
        require(geometry_fingerprint(original) == original_geometry, 'Existing vertices/UV/topology/weights changed')
        require(units.basis_hash(rig) == original_rest, 'Existing local skeleton basis changed')
        require(animation_fingerprint(original) == original_animation, 'Existing rig or facial action keys changed')
        report['physical_morph_coordinate_preservation'] = units.shape_difference(original_shapes, units.shape_coordinates(original, scale))
        report['physical_pose_preservation'] = units.snapshot_difference(original_poses, units.snapshot(rig, original))
        scene.frame_set(1)
        source_effective = source['effective_morph_measurement']
        effective = base.effective_morph_metrics(exported, source_effective['source_shape_key_names'])
        # The inherited helper measures raw coordinates and labels them metres.
        # This source is already centimetre-data: report physical metre deltas.
        effective['delta_epsilon_m'] *= scale
        for metric in effective['metrics'].values():
            metric['max_delta_m'] *= scale
            for row in metric['meshes']:
                row['max_delta_m'] *= scale
        effective['measurement_representation'] = 'CentimeterData; reported delta values explicitly multiplied by scene metres per unit'
        require(effective['effective_facial_morphs'] == source_effective['effective_facial_morphs'], 'Effective facial morph set changed')
        added_triangles = sum(sum(len(p.vertices)-2 for p in obj.data.polygons) for obj in additions)
        removed_triangles = sum(sum(len(p.vertices)-2 for p in obj.data.polygons) for obj in excluded)
        net_added_triangles = added_triangles - removed_triangles
        require(net_added_triangles <= 6000, 'Additive wardrobe exceeds its explicit net 6K-triangle source budget')
        previews = [] if skip_previews else review_images(rig, exported, output, scale, height, role)
        require(animation_fingerprint(original) == original_animation, 'Review render changed action keys')
        require(geometry_fingerprint(original) == original_geometry, 'Review render changed source geometry')
        for obj in list(scene.objects):
            if obj.type in ['CAMERA', 'LIGHT']:
                bpy.data.objects.remove(obj, do_unlink=True)
        scene.camera = None
        bpy.ops.object.select_all(action='DESELECT')
        for obj in exported:
            obj.hide_set(False)
            obj.hide_render = False
            obj.select_set(True)
        bpy.context.view_layer.objects.active = rig
        fbx = output / ('SK_ReleaseV02_' + role + '_ReferenceWardrobe.fbx')
        bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'ARMATURE', 'MESH'},
            add_leaf_bones=False, armature_nodetype='NULL', global_scale=1.0, apply_unit_scale=True,
            apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Y', axis_up='Z', use_mesh_modifiers=False,
            mesh_smooth_type='FACE', bake_anim=True, bake_anim_use_nla_strips=False,
            bake_anim_use_all_actions=False, bake_anim_simplify_factor=0.0, path_mode='COPY', embed_textures=False)
        candidate_blend = output / (role + '_ReferenceWardrobe_V02_CentimeterData.blend')
        bpy.ops.wm.save_as_mainfile(filepath=str(candidate_blend))
        used = {m.name for obj in exported if obj.type == 'MESH' for m in obj.data.materials if m}
        recipes = {name: dict(value) for name, value in source['material_recipes'].items()}
        recipes.update(base.MATERIAL_RECIPES)
        require(used.issubset(recipes), 'An exported material lacks a native-compatible recipe')
        report.update(success=True, export_performed=True, blend=str(candidate_blend),
            fbx={'path': str(fbx), 'sha256': files.sha(fbx)},
            material_recipes={name: recipes[name] for name in sorted(used)},
            effective_morph_measurement=effective, previews=previews, previews_rendered=not skip_previews,
            existing_geometry_uv_weights_sha256=original_geometry, existing_animation_sha256=original_animation,
            normalized_rest_bone_basis_sha256=original_rest, added_triangles=added_triangles,
            candidate_only_excluded_triangles=removed_triangles, net_added_triangles=net_added_triangles,
            added_meshes=[{'name': obj.name, 'vertices': len(obj.data.vertices),
                'triangles': sum(len(p.vertices)-2 for p in obj.data.polygons),
                'weighted_to_existing_rig': True, 'new_bones': 0,
                'skin_influences': influence_audit(obj, rig)} for obj in additions],
            total_triangles=sum(sum(len(p.vertices)-2 for p in obj.data.polygons) for obj in exported if obj.type == 'MESH'),
            wardrobe=wardrobe, native_material_recipe_schema='Existing import_release_characters.material',
            textile_provenance=str(TEAL_PROVENANCE), texture_seamless_verified=False,
            existing_geometry_topology_uv_weights_unchanged=True, existing_action_keys_unchanged=True,
            existing_bones_rest_basis_unchanged=True, new_bones=0)
        report['copied_source_weights_policy'] = {
            'all_positive_source_bone_influences_preserved': True, 'silently_pruned_influences': 0,
            'copied_weights_normalized_or_changed': False, 'explicit_added_influence_bound': 8,
            'observed_source_sweater_maximum': next(row['skin_influences']['maximum_positive_influences']
                for row in report['source_registry'] if 'toigo_fisherman_sweater' in row['name']) if role == 'Mother' else None,
            'installed_engine_constant_evidence': 'UE_5.8/Engine/Source/Runtime/Engine/Public/GPUSkinPublicDefs.h declares MAX_TOTAL_INFLUENCES 12; native candidate readback still required',
            'quest_performance_or_weight_import_preservation_claimed': False}
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        after_files = protected(pointer, manifest, blend, source)
        report['protected_old_source_and_native_unchanged'] = before_files == after_files
        report['success'] = bool(report['success'] and before_files == after_files)
        report['protected_sha256'] = before_files
        write_json(output / 'manifest.json', report)
        if report['success'] and not inspect_only:
            write_json(OUT / role / 'latest.json', {'run': run, 'manifest': str(output / 'manifest.json')})
        print('REFERENCE_WARDROBE_V02_REPORT ' + str(output / 'manifest.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--character', choices=sorted(SOURCE_POINTERS), required=True)
    parser.add_argument('--inspect-only', action='store_true')
    parser.add_argument('--skip-previews', action='store_true', help='Source export only, never visual approval')
    parser.add_argument('--hair-style', choices=['original', 'low-bun'], default='original', help='Optional cloned Mother hair A/B; never edits the source braid')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    build(args.character, args.inspect_only, args.skip_previews, args.hair_style)
