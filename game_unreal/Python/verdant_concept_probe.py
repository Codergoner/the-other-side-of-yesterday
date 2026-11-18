"""Read-only inventory for the concept pass of 17 November 2026 (run with -nullrhi). Nothing is saved.

Writes game_unreal/validation/concept_pass/probe.json: every static-mesh component of the story map with its mesh,
instance count, tags and materials; the lights, fog, sky and exposure settings; and where the cloth, lantern and
flower props stand near the played route.
"""
import json
import sys
import traceback
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc

MAP = '/Game/Quest/Maps/Verdant_Desktop'
OUT = vc.PROJECT / 'validation' / 'concept_pass'
OUT.mkdir(parents=True, exist_ok=True)
REPORT = {'success': False, 'components': [], 'lights': [], 'placed': {}}
WATCH = ('Banner', 'Bunting', 'Awning', 'Stall', 'Lantern', 'Bougain', 'Ivy', 'FlowerBox', 'Pot', 'ClinicFlag', 'Laundry', 'Archway', 'Fountain')


def name_of(obj):
    return obj.get_name() if obj is not None else None


def vec(v):
    return [round(v.x, 1), round(v.y, 1), round(v.z, 1)]


def main():
    vc.require(vc.levels.load_level(MAP), 'Cannot load ' + MAP)
    for actor in vc.actors.get_all_level_actors():
        tags = [str(t) for t in actor.get_editor_property('tags')]
        label = actor.get_actor_label()
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            if mesh is None:
                continue
            count = component.get_instance_count() if isinstance(component, unreal.InstancedStaticMeshComponent) else 1
            row = {'actor': actor.get_name(), 'label': label, 'tags': tags, 'component': component.get_name(), 'class': component.get_class().get_name(),
                   'mesh': mesh.get_name(), 'count': count, 'hidden': bool(actor.get_editor_property('hidden')), 'visible': bool(component.is_visible()),
                   'materials': [name_of(component.get_material(i)) for i in range(component.get_num_materials())],
                   'overrides': [name_of(m) for m in component.get_editor_property('override_materials')],
                   'mesh_materials': [name_of(s.get_editor_property('material_interface')) for s in mesh.get_editor_property('static_materials')],
                   'location': vec(actor.get_actor_location())}
            REPORT['components'].append(row)
            if any(key in mesh.get_name() for key in WATCH):
                places = []
                if isinstance(component, unreal.InstancedStaticMeshComponent):
                    for index in range(count):
                        t = component.get_instance_transform(index, True)
                        places.append(vec(t.translation) + [round(t.rotation.rotator().yaw, 0), round(t.scale3d.x, 2)])
                else:
                    t = component.get_world_transform()
                    places.append(vec(t.translation) + [round(t.rotation.rotator().yaw, 0), round(t.scale3d.x, 2)])
                key = mesh.get_name() + '|' + ('Past' if 'Opening.PastOnly' in tags else 'Present' if 'Opening.PresentOnly' in tags else 'Shared')
                REPORT['placed'].setdefault(key, []).extend(places)
        for cls, fields in ((unreal.DirectionalLightComponent, ('intensity', 'light_color', 'specular_scale', 'dynamic_shadow_distance_movable_light', 'mobility', 'cast_shadows')),
                            (unreal.SkyLightComponent, ('intensity', 'light_color', 'source_type', 'mobility', 'lower_hemisphere_is_black', 'lower_hemisphere_color')),
                            (unreal.ExponentialHeightFogComponent, ('fog_density', 'fog_height_falloff', 'fog_inscattering_luminance', 'fog_max_opacity', 'start_distance',
                                                                    'directional_inscattering_luminance', 'directional_inscattering_exponent', 'directional_inscattering_start_distance')),
                            (unreal.PointLightComponent, ('intensity', 'light_color', 'attenuation_radius', 'mobility', 'cast_shadows'))):
            for component in actor.get_components_by_class(cls):
                row = {'actor': actor.get_name(), 'label': label, 'tags': tags, 'class': component.get_class().get_name(), 'hidden': bool(actor.get_editor_property('hidden')),
                       'visible': bool(component.is_visible()), 'rotation': str(actor.get_actor_rotation()), 'location': vec(actor.get_actor_location())}
                for field in fields:
                    try:
                        row[field] = str(component.get_editor_property(field))
                    except Exception as problem:
                        row[field] = 'n/a ' + str(problem)[:60]
                REPORT['lights'].append(row)
        if isinstance(actor, unreal.PostProcessVolume):
            s = actor.get_editor_property('settings')
            REPORT.setdefault('volumes', []).append({
                'actor': actor.get_name(), 'label': label, 'enabled': bool(actor.get_editor_property('enabled')), 'unbound': bool(actor.get_editor_property('unbound')),
                **{k: str(s.get_editor_property(k)) for k in ('auto_exposure_bias', 'auto_exposure_method', 'bloom_intensity', 'film_slope', 'film_toe', 'vignette_intensity',
                                                             'override_auto_exposure_bias', 'override_color_saturation', 'color_saturation', 'override_white_temp', 'white_temp')}})
    for path in ('MI_V_Sky_Past', 'MI_V_Sky_Present'):
        mi = unreal.load_asset(vc.ROOT_PATH + '/Materials/' + path)
        REPORT.setdefault('sky', {})[path] = {'gain': unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(mi, 'SkyGain')}
    REPORT['success'] = True


try:
    main()
except Exception:
    REPORT['error'] = traceback.format_exc()
vc.write_json(OUT / 'probe.json', REPORT)
vc.log('concept probe finished', REPORT['success'], len(REPORT['components']), 'components', (REPORT.get('error') or '')[-400:])
unreal.SystemLibrary.quit_editor()
