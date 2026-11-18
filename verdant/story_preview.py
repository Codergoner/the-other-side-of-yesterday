"""Contact sheet of the exported story-set meshes (each stood on the ground), for review before import.

    blender --background --factory-startup --python story_preview.py
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE.parent / 'output' / 'verdant'
bpy.ops.wm.read_factory_settings(use_empty=True)
objects = []
for file in sorted((OUT / 'meshes').glob('SM_V_Story_*.fbx')):
    bpy.ops.import_scene.fbx(filepath=str(file))
    objects.extend(o for o in bpy.context.selected_objects if o.type == 'MESH')
columns, spacing = 8, 4.6
rows = 0
for i, obj in enumerate(objects):
    row = i // columns
    rows = max(rows, row + 1)
    low = min((obj.matrix_world @ Vector(v.co)).z for v in obj.data.vertices)
    obj.location = ((i % columns) * spacing, -row * (spacing + 3.0), -low)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 16
scene.cycles.use_denoising = True
scene.render.resolution_x, scene.render.resolution_y = 2200, 1400
scene.render.image_settings.file_format = 'PNG'
scene.view_settings.view_transform = 'Standard'
world = bpy.data.worlds.new('w')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (.55, .68, .95, 1)
world.node_tree.nodes['Background'].inputs[1].default_value = .8
scene.world = world
sun_data = bpy.data.lights.new('s', 'SUN')
sun_data.energy = 3.2
sun_data.color = (1, .85, .66)
sun = bpy.data.objects.new('s', sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(62), 0, math.radians(-40))
ground = bpy.data.meshes.new('g')
ground.from_pydata([(-20, -80, -.01), (60, -80, -.01), (60, 20, -.01), (-20, 20, -.01)], [], [(0, 1, 2, 3)])
scene.collection.objects.link(bpy.data.objects.new('g', ground))
width, depth = columns * spacing, rows * (spacing + 3.0)
data = bpy.data.cameras.new('c')
data.lens = 30
cam = bpy.data.objects.new('c', data)
scene.collection.objects.link(cam)
aim = Vector((width * .46, -depth * .45, 1.2))
cam.location = Vector((width * .46, -depth * .45 - max(width, depth) * .78, max(width, depth) * .5))
cam.rotation_euler = (aim - cam.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam
path = OUT / 'previews' / 'story_props.png'
path.parent.mkdir(parents=True, exist_ok=True)
scene.render.filepath = str(path)
bpy.ops.render.render(write_still=True)
print('PREVIEW', path, len(objects), 'objects', [o.name for o in objects], flush=True)
