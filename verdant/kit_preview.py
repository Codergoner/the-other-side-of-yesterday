"""Contact sheet of kit meshes with a low warm sun, for review before anything reaches Unreal."""
import math

import bpy
from mathutils import Vector


def render(objects, path, columns=8, spacing=4.0, resolution=(1800, 1000), target=None, location=None, lens=34, samples=24):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.image_settings.file_format = 'PNG'
    scene.view_settings.view_transform = 'Standard'
    rows = 0
    for i, obj in enumerate(objects):
        row = i // columns
        rows = max(rows, row + 1)
        obj.location = ((i % columns) * spacing, -row * (spacing + 2.5), 0)
    width = columns * spacing
    depth = rows * (spacing + 2.5)
    world = bpy.data.worlds.new('w')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.55, .68, .95, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .75
    scene.world = world
    sun_data = bpy.data.lights.new('s', 'SUN')
    sun_data.energy = 3.4
    sun_data.color = (1, .82, .6)
    sun_data.angle = math.radians(2)
    sun = bpy.data.objects.new('s', sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(68), 0, math.radians(-32))
    ground = bpy.data.meshes.new('g')
    ground.from_pydata([(-50, -80, -.02), (120, -80, -.02), (120, 60, -.02), (-50, 60, -.02)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new('g', ground)
    scene.collection.objects.link(g)
    data = bpy.data.cameras.new('c')
    data.lens = lens
    cam = bpy.data.objects.new('c', data)
    scene.collection.objects.link(cam)
    aim = Vector(target or (width * .46, -depth * .42, 1.6))
    cam.location = Vector(location or (width * .46, -depth * .42 - max(width, depth) * .92, max(width, depth) * .46))
    cam.rotation_euler = (aim - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print('PREVIEW', path, flush=True)
