"""Bakes one art-directed HDR sky panorama per era with Cycles (real volumetric clouds).

    blender --background --factory-startup --python bake_sky.py -- <Past|Present> <width> <samples> <out.exr>

The panorama is centred on +Y (uphill, toward the cathedral) with +X (the sea) to the right,
in the same metres/axes as the city plan, so the painted sun lines up with the directional
light. A clear pocket is kept behind the cathedral; clouds build over the open sea.
"""
import math
import sys

import bpy

ERA, WIDTH, SAMPLES, OUT = sys.argv[sys.argv.index('--') + 1:][:4]
WIDTH, SAMPLES = int(WIDTH), int(SAMPLES)

ERAS = {
    'Past': dict(azimuth=62.0, elevation=13.0, threshold=.462, sun=(1.0, .7, .44), sun_power=9.0, aerosol=.9,
                 sky_strength=.14, density=.0075, bank=0.0, ozone=1.2),
    'Present': dict(azimuth=66.0, elevation=10.5, threshold=.44, sun=(1.0, .66, .46), sun_power=7.0, aerosol=1.3,
                    sky_strength=.12, density=.0095, bank=1.0, ozone=1.0),
}
E = ERAS[ERA]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'HIP'
prefs.get_devices()
for device in prefs.devices:
    device.use = device.type == 'HIP' and '9070' in device.name
scene.cycles.device = 'GPU'
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPENIMAGEDENOISE'
scene.cycles.volume_bounces = 24
scene.cycles.max_bounces = 32
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = .03
scene.render.resolution_x = WIDTH
scene.render.resolution_y = WIDTH // 2
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'OPEN_EXR'
scene.render.image_settings.color_depth = '16'
scene.render.image_settings.exr_codec = 'ZIP'
scene.view_settings.view_transform = 'Standard'

cam_data = bpy.data.cameras.new('pano')
cam_data.type = 'PANO'
cam_data.panorama_type = 'EQUIRECTANGULAR'
cam_data.clip_end = 200000
cam = bpy.data.objects.new('pano', cam_data)
scene.collection.objects.link(cam)
cam.location = (0, 0, 30)
cam.rotation_euler = (math.pi / 2, 0, 0)  # looks along +Y, Z up
scene.camera = cam

world = bpy.data.worlds.new('sky')
world.use_nodes = True
scene.world = world
tree = world.node_tree
background = tree.nodes['Background']
sky = tree.nodes.new('ShaderNodeTexSky')
sky.sky_type = 'MULTIPLE_SCATTERING'
sky.sun_disc = False
sky.sun_elevation = math.radians(E['elevation'])
# Blender measures sun rotation clockwise from +Y, which is the plan's azimuth.
sky.sun_rotation = math.radians(E['azimuth'])
sky.altitude = 40
sky.aerosol_density = E['aerosol']
sky.air_density = 1.0
sky.ozone_density = E['ozone']
tree.links.new(sky.outputs[0], background.inputs['Color'])
background.inputs['Strength'].default_value = E['sky_strength']

sun_data = bpy.data.lights.new('sun', 'SUN')
sun_data.energy = E['sun_power']
sun_data.color = E['sun']
sun_data.angle = math.radians(1.2)
sun = bpy.data.objects.new('sun', sun_data)
scene.collection.objects.link(sun)
a, e = math.radians(E['azimuth']), math.radians(E['elevation'])
to_sun = (math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e))
# Lamp shines along local -Z, so aim local +Z at the sun.
from mathutils import Vector
sun.rotation_mode = 'QUATERNION'
sun.rotation_quaternion = Vector(to_sun).to_track_quat('Z', 'Y')

# Cloud slab: broad cumulus base, 1.3-3.6 km up, 190 km across so it reaches the horizon.
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 2450))
domain = bpy.context.object
domain.scale = (190000, 190000, 2300)
mat = bpy.data.materials.new('cloud')
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()
out = nodes.new('ShaderNodeOutputMaterial')
vol = nodes.new('ShaderNodeVolumePrincipled')
vol.inputs['Color'].default_value = (1, 1, 1, 1)
vol.inputs['Anisotropy'].default_value = .62
links.new(vol.outputs[0], out.inputs['Volume'])
geo = nodes.new('ShaderNodeNewGeometry')
split = nodes.new('ShaderNodeSeparateXYZ')
links.new(geo.outputs['Position'], split.inputs[0])


def noise(scale, detail, rough, seed):
    node = nodes.new('ShaderNodeTexNoise')
    node.inputs['Scale'].default_value = scale
    node.inputs['Detail'].default_value = detail
    node.inputs['Roughness'].default_value = rough
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Location'].default_value = (seed * 1311.0, seed * 713.0, 0)
    links.new(geo.outputs['Position'], mapping.inputs[0])
    links.new(mapping.outputs[0], node.inputs['Vector'])
    return node.outputs[0]


def math_node(op, a_in, b_in=None, clamp=False):
    node = nodes.new('ShaderNodeMath')
    node.operation = op
    node.use_clamp = clamp
    for i, value in enumerate((a_in, b_in)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            node.inputs[i].default_value = value
        else:
            links.new(value, node.inputs[i])
    return node.outputs[0]


def ramp(value, a_in, b_in):
    """Smooth 0..1 from a to b."""
    node = nodes.new('ShaderNodeMapRange')
    node.interpolation_type = 'SMOOTHSTEP'
    node.inputs['From Min'].default_value = a_in
    node.inputs['From Max'].default_value = b_in
    links.new(value, node.inputs['Value'])
    return node.outputs[0]


# Large weather pattern, then billows, then fine erosion at the edges.
weather = noise(1 / 15000, 3.0, .5, 1)
billow = noise(1 / 2600, 7.0, .56, 2)
fine = noise(1 / 480, 6.0, .58, 3)
height = math_node('DIVIDE', math_node('SUBTRACT', split.outputs['Z'], 1300), 2300)
# Flat-ish bases, tapering tops.
bottom = ramp(height, 0, .09)
top = math_node('SUBTRACT', 1, ramp(height, .22, .98))
profile = math_node('MULTIPLY', bottom, top)

# Composition mask, in plan axes: clear pocket behind the cathedral along +Y, slightly west.
px = math_node('SUBTRACT', split.outputs['X'], -3000)
pocket_d = math_node('SQRT', math_node('ADD', math_node('POWER', math_node('MULTIPLY', px, 1.0), 2),
                                       math_node('POWER', math_node('MULTIPLY', math_node('SUBTRACT', split.outputs['Y'], 11000), .62), 2)))
pocket = math_node('MULTIPLY', ramp(pocket_d, 2500, 9000), 1.0)
coverage = math_node('SUBTRACT', math_node('ADD', math_node('MULTIPLY', weather, .62), math_node('MULTIPLY', billow, .38)),
                     E['threshold'])
coverage = math_node('SUBTRACT', coverage, math_node('MULTIPLY', math_node('SUBTRACT', 1, pocket), .14))
# Present: a restrained storm bank standing far out over the open sea.
if E['bank']:
    bank = ramp(math_node('ADD', math_node('MULTIPLY', split.outputs['X'], .8), math_node('MULTIPLY', split.outputs['Y'], .25)), 14000, 32000)
    coverage = math_node('ADD', coverage, math_node('MULTIPLY', bank, .12))
eroded = math_node('SUBTRACT', math_node('ADD', coverage, math_node('MULTIPLY', profile, .22)), .22)
eroded = math_node('SUBTRACT', eroded, math_node('MULTIPLY', math_node('SUBTRACT', 1, fine), .085))
shaped = math_node('MULTIPLY', math_node('MULTIPLY', ramp(eroded, 0, .05), profile), E['density'])
links.new(shaped, vol.inputs['Density'])
domain.data.materials.append(mat)

scene.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print('SKY BAKED', ERA, OUT, flush=True)
