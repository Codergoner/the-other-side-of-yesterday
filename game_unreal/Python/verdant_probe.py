"""Throwaway probe under /Game/Verdant/_Probe: sky stack under this renderer, instance components."""
import json
import traceback

import sys
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc

import time
MAP = '/Game/Verdant/_Probe/L_Probe_%d' % int(time.time())
result = {'success': False, 'map': MAP}
try:
    vc.require(vc.levels.new_level(MAP), 'new_level failed')
    world = vc.editor.get_editor_world()

    sun = vc.actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 5000))
    light = sun.get_component_by_class(unreal.DirectionalLightComponent)
    sun.set_actor_rotation(vc.sun_rotation('Past'), False)
    light.set_editor_property('mobility', unreal.ComponentMobility.MOVABLE)
    light.set_editor_property('intensity', 3.5)
    light.set_editor_property('atmosphere_sun_light', True)
    light.set_editor_property('cast_cloud_shadows', True)

    vc.actors.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
    cloud = vc.actors.spawn_actor_from_class(unreal.VolumetricCloud, unreal.Vector(0, 0, 0))
    component = cloud.get_component_by_class(unreal.VolumetricCloudComponent)
    material = unreal.load_asset('/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst')
    result['cloud_material_loaded'] = material is not None
    if material:
        component.set_editor_property('material', material)
        result['scalar_params'] = [str(n) for n in unreal.MaterialEditingLibrary.get_scalar_parameter_names(material)]
        result['vector_params'] = [str(n) for n in unreal.MaterialEditingLibrary.get_vector_parameter_names(material)]
        result['texture_params'] = [str(n) for n in unreal.MaterialEditingLibrary.get_texture_parameter_names(material)]
    sky = vc.actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 3000))
    sky_c = sky.get_component_by_class(unreal.SkyLightComponent)
    sky_c.set_editor_property('mobility', unreal.ComponentMobility.MOVABLE)
    sky_c.set_editor_property('real_time_capture', True)
    sky_c.set_editor_property('intensity', 1.0)
    vc.actors.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0))

    # Instance component round trip.
    holder = vc.actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
    holder.set_actor_label('Verdant_Probe_Instances')
    root = vc.add_component(holder, unreal.SceneComponent, 'Root')
    hism = vc.add_component(holder, unreal.HierarchicalInstancedStaticMeshComponent, 'Instances_Cube')
    hism.set_editor_property('static_mesh', unreal.load_asset('/Engine/BasicShapes/Cube'))
    hism.set_editor_property('num_custom_data_floats', 3)
    transforms = [unreal.Transform(location=[x * 300, y * 300, 200], rotation=[0, 0, 0], scale=[2, 2, 4])
                  for x in range(8) for y in range(8)]
    indices = hism.add_instances(transforms, True, True)
    result['instances_added'] = len(indices)
    hism.set_custom_data_value(0, 0, 0.5, True)
    ground = vc.actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
    ground.static_mesh_component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Plane'))
    ground.set_actor_scale3d(unreal.Vector(400, 400, 1))
    vc.require(vc.levels.save_current_level(), 'save failed')
    vc.levels.load_level(MAP)
    world = vc.editor.get_editor_world()
    found = [a for a in vc.actors.get_all_level_actors() if a.get_actor_label() == 'Verdant_Probe_Instances']
    comps = found[0].get_components_by_class(unreal.InstancedStaticMeshComponent) if found else []
    result['reloaded_instances'] = comps[0].get_instance_count() if comps else 0
    result['renderer'] = [str(unreal.SystemLibrary.get_console_variable_int_value(n)) for n in ('r.ForwardShading',)]
    result['success'] = result['reloaded_instances'] == 64
except Exception:
    result['error'] = traceback.format_exc()
vc.write_json(vc.EVIDENCE / 'probe_report.json', result)
vc.log('probe', json.dumps(result)[:1800])
unreal.SystemLibrary.quit_editor()
