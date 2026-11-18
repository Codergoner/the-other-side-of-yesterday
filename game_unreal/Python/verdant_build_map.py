"""Assembles /Game/Verdant/Maps/Verdant_City from output/verdant/plan.json.

Both timelines live in one map: every era-specific actor carries the tag Verdant.Past or
Verdant.Present and the native VerdantEra subsystem (T key, or -VerdantEra=Present) shows one
set at a time. Shared ground, sea, stairs, skylight, exposure and player start are untagged.
Instances are hierarchical instanced static meshes: one component per module per era.
"""
import json
import re
import sys
import time
import traceback
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc

MESHES = vc.ROOT_PATH + '/Meshes/'
MATERIALS = vc.ROOT_PATH + '/Materials/'
PLAN = json.loads((vc.SOURCE / 'plan.json').read_text(encoding='utf-8-sig'))
VEGETATION = json.loads((vc.SOURCE / 'vegetation.json').read_text(encoding='utf-8-sig'))
LIGHTING = json.loads((vc.SOURCE / 'lighting.json').read_text(encoding='utf-8-sig'))
REPORT = {'success': False, 'map': vc.MAP, 'instances': {}, 'components': {}, 'colliders': 0, 'warnings': []}
SHARED_MESHES = ('SM_V_Land_Near', 'SM_V_Land_Far', 'SM_V_Land_Surfaces', 'SM_V_Land_Walls', 'SM_V_Land_Stairs', 'SM_V_Land_Ramps', 'SM_V_Sea')
DEFAULT_TINT = [1.0, .97, .9, .2, .42, .42]
CULL = {'SM_V_GrassTuft': (7000, 12000), 'SM_V_WeedPatch': (9000, 15000), 'SM_V_Bush': (16000, 24000), 'SM_V_Pot': (9000, 14000),
        'SM_V_PotBroken': (9000, 14000), 'SM_V_FlowerBox': (9000, 14000), 'SM_V_IvyCurtain': (14000, 22000), 'SM_V_Bougainvillea': (14000, 22000)}


def transform(row):
    x, y, z = row['p']
    sx, sy, sz = row.get('s', (1, 1, 1))
    # Blender metres to Unreal centimetres: Y mirrors, so a counter-clockwise yaw becomes clockwise.
    return unreal.Transform(location=unreal.Vector(x * 100, -y * 100, z * 100),
                            rotation=unreal.Rotator(roll=0, pitch=0, yaw=-row.get('r', 0)), scale=unreal.Vector(sx, sy, sz))


def mesh_asset(name):
    asset = unreal.load_asset(MESHES + name)
    vc.require(asset is not None, 'Missing imported mesh ' + name)
    return asset


def present_material(material):
    label = re.match(r'^(?:MI|M)_V_([A-Za-z]+)', material.get_name())
    if not label:
        return None
    path = MATERIALS + 'MI_V_%s_Present' % label.group(1)
    return unreal.load_asset(path) if vc.library.does_asset_exist(path) else None


def clear_or_create():
    if vc.library.does_asset_exist(vc.MAP):
        vc.require(vc.levels.load_level(vc.MAP), 'Cannot load existing ' + vc.MAP)
        for actor in vc.actors.get_all_level_actors():
            vc.actors.destroy_actor(actor)
    else:
        vc.require(vc.levels.new_level(vc.MAP), 'new_level failed for ' + vc.MAP)
    return vc.editor.get_editor_world()


def native_tag(actor, era):
    actor.set_editor_property('tags', [unreal.Name('Verdant.' + era)])


# The story-map merge (verdant_merge_story_map.py) imports this module and replaces TAGGER so the
# era actors carry the story's own Opening.PastOnly / Opening.PresentOnly tags instead.
TAGGER = native_tag


def tag(actor, era):
    TAGGER(actor, era)


def holder(label, era=None):
    actor = vc.actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
    actor.set_actor_label(label)
    vc.add_component(actor, unreal.SceneComponent, 'Root')
    if era:
        tag(actor, era)
    return actor


def instanced(actor, mesh_name, rows, era):
    mesh = mesh_asset(mesh_name)
    component = vc.add_component(actor, unreal.HierarchicalInstancedStaticMeshComponent, mesh_name.replace('SM_V_', ''))
    component.set_editor_property('static_mesh', mesh)
    component.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
    slots = mesh.get_editor_property('static_materials')
    tinted = False
    for index, slot in enumerate(slots):
        material = slot.get_editor_property('material_interface')
        if material is None:
            continue
        if material.get_name() in ('M_V_Masonry', 'M_V_Paint'):
            tinted = True
        if era == 'Present':
            aged = present_material(material)
            if aged is not None:
                component.set_material(index, aged)
    if tinted:
        component.set_editor_property('num_custom_data_floats', 6)
    if mesh_name in CULL:
        component.set_cull_distances(*CULL[mesh_name])
    if mesh_name in ('SM_V_GrassTuft', 'SM_V_WeedPatch', 'SM_V_Bunting', 'SM_V_Laundry', 'SM_V_IvyCurtain', 'SM_V_Bougainvillea'):
        component.set_editor_property('cast_shadow', False)
    indices = component.add_instances([transform(row) for row in rows], True, True)
    vc.require(len(indices) == len(rows), 'Instance count mismatch for ' + mesh_name)
    if tinted:
        for index, row in zip(indices, rows):
            for slot, value in enumerate(row.get('c', DEFAULT_TINT)):
                component.set_custom_data_value(index, slot, float(value), index == indices[-1] and slot == 5)
    REPORT['instances'][era + '/' + mesh_name] = len(rows)
    return component


def era_actor(era):
    rows = PLAN[era]['instances']
    groups = {}
    for row in rows:
        groups.setdefault(row['m'], []).append(row)
    actor = holder('Verdant_' + era, era)
    for mesh_name in sorted(groups):
        instanced(actor, mesh_name, groups[mesh_name], era)
        vc.log(era, mesh_name, len(groups[mesh_name]), 'instances', round(time.monotonic() - started, 1), 's')
    REPORT['components'][era] = len(groups)
    return actor


def shared_actor():
    actor = holder('Verdant_Vegetation')
    groups = {}
    for row in VEGETATION:
        groups.setdefault(row['m'], []).append(row)
    for mesh_name in sorted(groups):
        instanced(actor, mesh_name, groups[mesh_name], 'Shared')
        vc.log('vegetation', mesh_name, len(groups[mesh_name]), round(time.monotonic() - started, 1), 's')
    for mesh_name in SHARED_MESHES:
        sm = vc.actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
        sm.set_actor_label(mesh_name.replace('SM_V_', 'Verdant_'))
        component = sm.static_mesh_component
        component.set_static_mesh(mesh_asset(mesh_name))
        component.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
        if mesh_name == 'SM_V_Land_Ramps':
            component.set_visibility(False)
            component.set_editor_property('cast_shadow', False)
        if mesh_name == 'SM_V_Sea':
            component.set_editor_property('cast_shadow', False)
            component.set_editor_property('receives_decals', False)


def invisible_material():
    path = MATERIALS + 'M_V_Invisible'
    if vc.library.does_asset_exist(path):
        return unreal.load_asset(path)
    material = vc.assets.create_asset('M_V_Invisible', MATERIALS, unreal.Material, unreal.MaterialFactoryNew())
    material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
    zero = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionConstant, -300, 0)
    zero.set_editor_property('r', 0.0)
    unreal.MaterialEditingLibrary.connect_material_property(zero, '', unreal.MaterialProperty.MP_OPACITY_MASK)
    unreal.MaterialEditingLibrary.recompile_material(material)
    vc.library.save_loaded_asset(material)
    return material


def pass_rays(component):
    """Boundary proxies stop the walker only. They stand where the old promenade rail and parapets stood
    (open work: interaction and gaze rays passed between the balusters), so the Visibility channel, which
    the manager's target query and the VR gaze ray use, ignores them.

    A static mesh component that still "uses default collision" takes the mesh asset's profile again when
    the level loads, which silently discards a per-channel override. That is switched off first and the
    profile family written explicitly; then the one response changes (the profile reads Custom)."""
    try:
        component.set_editor_property('use_default_collision', False)
    except Exception:
        pass
    component.set_collision_profile_name('BlockAll')
    component.set_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY, unreal.CollisionResponseType.ECR_IGNORE)


def colliders():
    cube = unreal.load_asset('/Engine/BasicShapes/Cube')
    ghost = invisible_material()
    for era in ('Shared', 'Past', 'Present'):
        rows = PLAN.get('colliders', []) if era == 'Shared' else PLAN[era]['colliders']
        for row in rows:
            cx, cy, cz = row['center']
            sx, sy, sz = row['size']
            actor = vc.actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(cx * 100, -cy * 100, cz * 100))
            actor.set_actor_label('Verdant_Collider_' + era)
            actor.set_actor_rotation(unreal.Rotator(roll=0, pitch=0, yaw=-row.get('yaw', 0)), False)
            actor.set_actor_scale3d(unreal.Vector(sx, sy, sz))
            component = actor.static_mesh_component
            component.set_static_mesh(cube)
            component.set_material(0, ghost)
            component.set_editor_property('cast_shadow', False)
            component.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
            actor.set_actor_hidden_in_game(True)
            if era != 'Shared':
                tag(actor, era)
            REPORT['colliders'] += 1
    for x0, x1, y0, y1, z0, z1 in PLAN['blockers']:
        actor = vc.actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector((x0 + x1) * 50, -(y0 + y1) * 50, (z0 + z1) * 50))
        actor.set_actor_label('Verdant_Blocker')
        actor.set_actor_scale3d(unreal.Vector(x1 - x0, y1 - y0, z1 - z0))
        component = actor.static_mesh_component
        component.set_static_mesh(cube)
        component.set_material(0, ghost)
        component.set_editor_property('cast_shadow', False)
        pass_rays(component)
        actor.set_actor_hidden_in_game(True)
        REPORT['colliders'] += 1


def sky_dome(era):
    actor = vc.actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, -200))
    actor.set_actor_label('Verdant_Sky_' + era)
    component = actor.static_mesh_component
    component.set_static_mesh(mesh_asset('SM_V_SkyDome'))
    component.set_material(0, unreal.load_asset(MATERIALS + 'MI_V_Sky_' + era))
    component.set_editor_property('cast_shadow', False)
    component.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
    component.set_editor_property('treat_as_background_for_occlusion', True)
    tag(actor, era)


def lights(era):
    spec = LIGHTING[era]
    sun = vc.actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 6000))
    sun.set_actor_label('Verdant_Sun_' + era)
    sun.set_actor_rotation(vc.sun_rotation(era), False)
    light = sun.get_component_by_class(unreal.DirectionalLightComponent)
    light.set_editor_property('mobility', unreal.ComponentMobility.MOVABLE)
    light.set_editor_property('intensity', spec['sun_intensity'])
    # 17 November 2026: unreal.Color takes b, g, r, a positionally, so the positional form used until now gave the
    # authored warm sun (1.0, .86, .7) as pale blue. Named channels. (The story map's suns were corrected by
    # verdant_concept_pass.py; this line matters only if the standalone map is rebuilt.)
    red, green, blue = (int(v * 255) for v in spec['sun_color'])
    light.set_editor_property('light_color', unreal.Color(r=red, g=green, b=blue, a=255))
    light.set_editor_property('temperature', 6500.0)
    light.set_editor_property('use_temperature', False)
    light.set_editor_property('dynamic_shadow_distance_movable_light', spec.get('shadow_distance', 22000))
    light.set_editor_property('dynamic_shadow_cascades', 4)
    light.set_editor_property('cascade_distribution_exponent', 2.4)
    light.set_editor_property('shadow_bias', .6)
    light.set_editor_property('light_source_angle', 1.2)
    light.set_editor_property('specular_scale', spec.get('specular_scale', 1.0))
    tag(sun, era)
    fog = vc.actors.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0))
    fog.set_actor_label('Verdant_Fog_' + era)
    f = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    f.set_editor_property('fog_density', spec['fog_density'])
    f.set_editor_property('fog_height_falloff', spec.get('fog_falloff', .25))
    f.set_editor_property('fog_inscattering_luminance', unreal.LinearColor(*spec['fog_color'], 1))
    f.set_editor_property('fog_max_opacity', spec.get('fog_max_opacity', .86))
    f.set_editor_property('start_distance', spec.get('fog_start', 1500))
    f.set_editor_property('directional_inscattering_luminance', unreal.LinearColor(*spec['fog_sun_color'], 1))
    f.set_editor_property('directional_inscattering_exponent', spec.get('fog_sun_exponent', 9.0))
    f.set_editor_property('directional_inscattering_start_distance', spec.get('fog_sun_start', 6000))
    tag(fog, era)
    sky = vc.actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 3000))
    sky.set_actor_label('Verdant_SkyLight_' + era)
    component = sky.get_component_by_class(unreal.SkyLightComponent)
    component.set_editor_property('mobility', unreal.ComponentMobility.MOVABLE)
    cube = unreal.load_asset(vc.ROOT_PATH + '/Textures/TC_V_SkyAmbient_' + era)
    if isinstance(cube, unreal.TextureCube):
        component.set_editor_property('source_type', unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
        component.set_editor_property('cubemap', cube)
        component.set_editor_property('real_time_capture', False)
        REPORT.setdefault('skylight_source', {})[era] = 'specified cubemap'
    else:
        component.set_editor_property('source_type', unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
        component.set_editor_property('real_time_capture', True)
        REPORT.setdefault('skylight_source', {})[era] = 'real-time capture (cubemap import did not produce a TextureCube)'
    component.set_editor_property('intensity', spec.get('skylight', LIGHTING['skylight_intensity']))
    component.set_editor_property('lower_hemisphere_is_black', False)
    component.set_editor_property('lower_hemisphere_color', unreal.LinearColor(*LIGHTING['ground_bounce'], 1))
    component.set_editor_property('cubemap_resolution', 128)
    tag(sky, era)


EXPOSURE_SETTINGS = (('override_auto_exposure_method', True), ('auto_exposure_method', unreal.AutoExposureMethod.AEM_MANUAL),
                     ('override_auto_exposure_apply_physical_camera_exposure', True), ('auto_exposure_apply_physical_camera_exposure', False),
                     ('override_auto_exposure_bias', True), ('auto_exposure_bias', LIGHTING['exposure_bias']),
                     ('override_bloom_intensity', True), ('bloom_intensity', LIGHTING.get('bloom', .25)),
                     ('override_vignette_intensity', True), ('vignette_intensity', .25),
                     ('override_white_temp', True), ('white_temp', 6500.0),
                     ('override_film_slope', True), ('film_slope', LIGHTING.get('film_slope', .86)),
                     ('override_film_toe', True), ('film_toe', LIGHTING.get('film_toe', .52)))


def exposure_volume():
    volume = vc.actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
    volume.set_actor_label('Verdant_Exposure')
    volume.set_editor_property('unbound', True)
    settings = volume.get_editor_property('settings')
    for key, value in EXPOSURE_SETTINGS:
        settings.set_editor_property(key, value)
    volume.set_editor_property('settings', settings)
    return volume


def player_start():
    start = vc.actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, 2000, 930))
    start.set_actor_label('Verdant_PlayerStart')
    start.set_actor_rotation(unreal.Rotator(roll=0, pitch=0, yaw=-90), False)


def shared_lighting():
    exposure_volume()
    player_start()


# Townsfolk: the project's own supporting-cast meshes, placed by their reported era with their idle
# animations. Review dressing for the environment only; no story tags, no interaction, no blocking.
# Heights are the plan's authored surface heights (an editor-world trace does not see actors spawned
# in the same tick); the walking checks are what verify those surfaces.
CAST = json.loads((vc.PROJECT / 'supporting_cast_import_report.json').read_text(encoding='utf-8-sig'))['roles']
PEOPLE = {'Past': [('Baker', (-29.4, 3.4, 10.7), (-24, 8)), ('Carpenter', (-15.0, 11.0, 10.7), (-20, 8)), ('Fisherwoman', (16.5, 10.0, 1.2), (25, 12)),
                   ('Boatwright', (21.0, 6.2, 1.2), (22.5, 8.5)), ('HarborClerk', (12.4, -6.9, 6.4), (10.6, -8.4)), ('Tavi', (-5.6, -16.5, 9.08), (-6.6, -14.2))],
          'Present': [('Archivist', (0.5, 60.0, 25.0), (11, 55)), ('ShrineKeeper', (-20.0, 11.6, 10.7), (-24, 8)), ('LanternKeeper', (2.2, 20.0, 12.2), (2, 32))]}


def townsfolk():
    import math
    world = vc.editor.get_editor_world()
    for era, rows in PEOPLE.items():
        for role, (x, y, z_m), (fx, fy) in rows:
            info = CAST.get(role)
            if not info:
                REPORT['warnings'].append('No cast import for ' + role)
                continue
            mesh, anim = unreal.load_asset(info['mesh']), unreal.load_asset(info['animation'])
            if mesh is None or anim is None:
                REPORT['warnings'].append('Cast assets missing for ' + role)
                continue
            ux, uy, tx, ty = x * 100, -y * 100, fx * 100, -fy * 100
            z = z_m * 100
            actor = vc.actors.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(ux, uy, z))
            actor.set_actor_label('Verdant_Townsfolk_%s_%s' % (era, role))
            component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
            component.set_mobility(unreal.ComponentMobility.MOVABLE)
            component.set_skeletal_mesh_asset(mesh)
            component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
            component.override_animation_data(anim, True, True, 0.0, 1.0)
            component.set_update_animation_in_editor(True)
            component.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
            component.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
            component.set_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY, unreal.CollisionResponseType.ECR_BLOCK)
            # The cast meshes face local +Y, so the facing yaw carries a 90 degree offset.
            desired = math.degrees(math.atan2(ty - uy, tx - ux))
            actor.set_actor_rotation(unreal.Rotator(pitch=0.0, yaw=desired - 90.0, roll=0.0), True)
            tag(actor, era)
            REPORT.setdefault('townsfolk', []).append({'role': role, 'era': era, 'cm': [round(ux), round(uy), round(z, 1)], 'height_source': 'authored plan surface'})

started = time.monotonic()


def main():
    """Rebuilds the standalone Verdant_City map from scratch (the original job)."""
    try:
        clear_or_create()
        vc.log('map ready')
        shared_actor()
        vc.log('shared done', round(time.monotonic() - started, 1))
        for era in ('Past', 'Present'):
            era_actor(era)
            sky_dome(era)
            lights(era)
        colliders()
        vc.log('colliders done', round(time.monotonic() - started, 1))
        townsfolk()
        shared_lighting()
        world = vc.editor.get_editor_world()
        changed = unreal.VerdantEraLibrary.apply_era(world, True)
        REPORT['era_actors_switched'] = changed
        vc.require(vc.levels.save_current_level(), 'save failed')
        REPORT['success'] = True
    except Exception:
        REPORT['error'] = traceback.format_exc()
    REPORT['seconds'] = round(time.monotonic() - started, 1)
    REPORT['total_instances'] = sum(REPORT['instances'].values())
    vc.write_json(vc.EVIDENCE / 'build_map_report.json', REPORT)
    vc.log('build map', json.dumps({k: REPORT[k] for k in ('success', 'colliders', 'total_instances', 'seconds', 'error') if k in REPORT})[:1200])
    unreal.SystemLibrary.quit_editor()


if __name__ == '__main__':
    main()
