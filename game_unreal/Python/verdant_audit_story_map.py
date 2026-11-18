"""Read-only inventory of the story map before the Verdant city is merged onto it.

Loads /Game/Quest/Maps/Verdant_Desktop in the editor, records every actor (class, folder, tags,
transform, bounds, meshes, materials, visibility, collision, light / fog / post-process values),
the story manager's actor references and era arrays, and the floor height the current scenery
offers along the story route (downward line traces). Nothing is modified or saved.

Launch: verdant/run_unreal.ps1 -Script verdant_audit_story_map.py -NoRender -UserDir <short dir>
Output: game_unreal/validation/verdant_merge/<stamp>/audit.json
"""
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc

MAP = '/Game/Quest/Maps/Verdant_Desktop'
MANAGER_CLASS = '/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
OUT = vc.PROJECT / 'validation' / 'verdant_merge' / STAMP
REPORT = {'success': False, 'map': MAP, 'run': STAMP, 'read_only': True, 'actors': [], 'manager': {}, 'traces': [],
          'warnings': []}

# Story route anchors in Unreal centimetres (quest_walk_validation.json authored route, chapter-2
# scene placements and the manager's own restore points). Floors are traced at each.
ANCHORS = {
    'home_room': (-620, 1240), 'inside_front_door': (-480, 1240), 'entry_threshold': (-420, 1240),
    'front_porch': (-285, 1240), 'approach_stair_top': (-230, 1240), 'approach_stair_middle': (-115, 1240),
    'approach_stair_foot': (-5, 1240), 'courtyard_gate': (50, 1240), 'gate_restore_point': (120, 1240),
    'memorial_reading': (-245, 1510), 'chronology_board_stand': (-55, 1575), 'archivist': (-120, 1640),
    'street_below_clinic': (50, 950), 'clinic_street': (50, 740), 'clinic_resting_bay': (-75, 730),
    'clinic_healer': (-200, 580), 'clinic_tray': (-210, 520), 'clinic_water': (-210, 640),
    'clinic_fixing': (-190, 390), 'clinic_platform': (-435, 550), 'clinic_return_to_spine': (50, 690),
    'market_approach': (50, 400), 'market_street': (30, 0), 'arcade_street_approach': (-240, -200),
    'arcade_threshold_outer': (-300, -200), 'arcade_doorway': (-435, -200), 'calm_market_arcade': (-600, -200),
    'sela_service_approach': (30, -300), 'sela': (150, -300), 'shop_counter': (233, -300),
    'harbor_story_canopy_approach': (-45, -535), 'harbor_fixing': (90, -535), 'harbor_bench': (242, -660),
    'neri_harbor_destination': (115, -610), 'protected_sea_pause': (50, -900), 'upper_street': (50, -1400),
    'true_shore_opening': (275, -1400), 'upper_harbor_overlook': (450, -1400), 'neri_start': (120, 1050),
}


def xyz(v):
    return [round(float(v.x), 2), round(float(v.y), 2), round(float(v.z), 2)]


def rot(r):
    return {'pitch': round(float(r.pitch), 3), 'yaw': round(float(r.yaw), 3), 'roll': round(float(r.roll), 3)}


def value(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, unreal.Object):
        return v.get_path_name()
    if isinstance(v, unreal.Name):
        return str(v)
    if isinstance(v, unreal.Color):
        return [v.r, v.g, v.b, v.a]
    if isinstance(v, unreal.LinearColor):
        return [round(v.r, 5), round(v.g, 5), round(v.b, 5), round(v.a, 5)]
    if isinstance(v, unreal.Vector):
        return xyz(v)
    if isinstance(v, unreal.Rotator):
        return rot(v)
    if isinstance(v, unreal.Array):
        return [value(x) for x in v]
    return str(v)


def get(obj, field):
    try:
        return value(obj.get_editor_property(field))
    except Exception:
        return None


def props(obj, names):
    row = {}
    for name in names:
        got = get(obj, name)
        if got is not None:
            row[name] = got
    return row


LIGHT_PROPS = ['intensity', 'light_color', 'mobility', 'cast_shadows', 'visible', 'hidden_in_game', 'temperature', 'use_temperature',
               'indirect_lighting_intensity', 'volumetric_scattering_intensity', 'dynamic_shadow_distance_movable_light',
               'dynamic_shadow_cascades', 'cascade_distribution_exponent', 'shadow_bias', 'light_source_angle', 'specular_scale',
               'attenuation_radius', 'intensity_units', 'source_type', 'cubemap', 'real_time_capture', 'cubemap_resolution',
               'lower_hemisphere_is_black', 'lower_hemisphere_color', 'atmosphere_sun_light']
FOG_PROPS = ['visible', 'hidden_in_game', 'fog_density', 'fog_height_falloff', 'fog_inscattering_luminance', 'directional_inscattering_luminance',
             'directional_inscattering_exponent', 'directional_inscattering_start_distance', 'start_distance', 'fog_max_opacity',
             'enable_volumetric_fog', 'fog_cutoff_distance']
PPV_SETTINGS = ['auto_exposure_method', 'auto_exposure_bias', 'auto_exposure_apply_physical_camera_exposure', 'auto_exposure_min_brightness',
                'auto_exposure_max_brightness', 'bloom_intensity', 'bloom_threshold', 'vignette_intensity', 'motion_blur_amount', 'white_temp',
                'white_tint', 'film_slope', 'film_toe', 'film_shoulder', 'film_black_clip', 'film_white_clip', 'color_saturation',
                'color_contrast', 'ambient_occlusion_intensity', 'depth_of_field_focal_distance', 'indirect_lighting_intensity', 'sky_light_intensity']


def actor_record(actor):
    origin, extent = actor.get_actor_bounds(False)
    row = {'name': actor.get_name(), 'label': actor.get_actor_label(), 'class': actor.get_class().get_path_name(),
           'folder': str(actor.get_folder_path()), 'tags': [str(t) for t in actor.get_editor_property('tags')],
           'location': xyz(actor.get_actor_location()), 'rotation': rot(actor.get_actor_rotation()), 'scale': xyz(actor.get_actor_scale3d()),
           'bounds_origin': xyz(origin), 'bounds_extent': xyz(extent), 'bounds_min': xyz(origin - extent), 'bounds_max': xyz(origin + extent),
           'hidden_in_game': bool(actor.get_editor_property('hidden')), 'actor_collision_enabled': bool(actor.get_actor_enable_collision()),
           'components': []}
    try:
        row['editor_hidden_temporarily'] = bool(actor.is_temporarily_hidden_in_editor())
    except Exception:
        pass
    for component in actor.get_components_by_class(unreal.SceneComponent):
        c = {'name': component.get_name(), 'class': component.get_class().get_name()}
        if isinstance(component, unreal.PrimitiveComponent):
            c.update({'visible': bool(component.is_visible()), 'hidden_in_game': bool(component.get_editor_property('hidden_in_game')),
                      'collision_enabled': str(component.get_collision_enabled()).split('.')[-1],
                      'collision_profile': str(component.get_collision_profile_name()), 'mobility': str(component.get_editor_property('mobility')).split('.')[-1],
                      'cast_shadow': get(component, 'cast_shadow')})
            if isinstance(component, unreal.StaticMeshComponent):
                mesh = component.get_editor_property('static_mesh')
                c['static_mesh'] = mesh.get_path_name() if mesh else None
                if isinstance(component, unreal.InstancedStaticMeshComponent):
                    c['instances'] = int(component.get_instance_count())
            if isinstance(component, unreal.SkeletalMeshComponent):
                try:
                    mesh = component.get_skeletal_mesh_asset()
                except Exception:
                    mesh = None
                c['skeletal_mesh'] = mesh.get_path_name() if mesh else None
            try:
                c['materials'] = [component.get_material(i).get_path_name() if component.get_material(i) else None
                                  for i in range(component.get_num_materials())]
            except Exception:
                pass
        if isinstance(component, unreal.LightComponentBase):
            c['light'] = props(component, LIGHT_PROPS)
        if isinstance(component, unreal.ExponentialHeightFogComponent):
            c['fog'] = props(component, FOG_PROPS)
        if isinstance(component, unreal.SkyAtmosphereComponent):
            c['sky_atmosphere'] = {'visible': bool(component.is_visible()), 'hidden_in_game': get(component, 'hidden_in_game')}
        if isinstance(component, unreal.VolumetricCloudComponent):
            c['volumetric_cloud'] = {'visible': bool(component.is_visible())}
        if isinstance(component, unreal.AudioComponent):
            c['audio'] = props(component, ['auto_activate', 'sound'])
        row['components'].append(c)
    if isinstance(actor, unreal.PostProcessVolume):
        settings = actor.get_editor_property('settings')
        row['post_process'] = {'enabled': get(actor, 'enabled'), 'unbound': get(actor, 'unbound'), 'priority': get(actor, 'priority'),
                               'blend_weight': get(actor, 'blend_weight'), 'settings': props(settings, PPV_SETTINGS),
                               'overrides': {name: get(settings, 'override_' + name) for name in PPV_SETTINGS if get(settings, 'override_' + name) is not None}}
    if isinstance(actor, unreal.PlayerStart):
        row['player_start'] = True
    return row


def manager_record(actors):
    cls = unreal.load_class(None, MANAGER_CLASS)
    found = [a for a in actors if a.actor_has_tag('Opening.Manager')]
    if len(found) != 1:
        REPORT['warnings'].append('Expected one Opening.Manager, found %d' % len(found))
    manager = found[0] if found else None
    if manager is None:
        return {}
    bp = unreal.load_asset('/Game/Opening/Blueprints/BP_OpeningActions')
    names = [str(n) for n in unreal.BlueprintEditorLibrary.list_member_variable_names(bp, False)] if bp else []
    refs, arrays, scalars, unreadable = {}, {}, {}, []
    for name in sorted(names):
        try:
            got = manager.get_editor_property(name)
        except Exception:
            unreadable.append(name)
            continue
        if isinstance(got, unreal.Actor):
            refs[name] = {'actor': got.get_name(), 'label': got.get_actor_label(), 'location': xyz(got.get_actor_location()),
                          'tags': [str(t) for t in got.get_editor_property('tags')]}
        elif isinstance(got, unreal.Array) and len(got) and isinstance(got[0], unreal.Actor):
            arrays[name] = [{'actor': a.get_name(), 'label': a.get_actor_label(), 'tags': [str(t) for t in a.get_editor_property('tags')]} for a in got]
        elif isinstance(got, (str, int, float, bool)) or isinstance(got, unreal.Name):
            scalars[name] = value(got)
        elif isinstance(got, unreal.Object):
            scalars[name] = got.get_path_name()
    return {'actor': manager.get_name(), 'label': manager.get_actor_label(), 'class': manager.get_class().get_path_name(),
            'class_matches': manager.get_class() == cls, 'member_count': len(names), 'actor_references': refs, 'actor_arrays': arrays,
            'scalar_values': scalars, 'unreadable_members': unreadable}


def trace(world, x, y, top=1500.0, bottom=600.0, ignore=()):
    start, end = unreal.Vector(x, y, top), unreal.Vector(x, y, bottom)
    hit = unreal.SystemLibrary.line_trace_single(world, start, end, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, list(ignore),
                                                 unreal.DrawDebugTrace.NONE, True)
    if isinstance(hit, tuple):
        hit = next((h for h in hit if isinstance(h, unreal.HitResult)), None)
    if hit is None:
        return None
    parts = hit.to_tuple()   # BreakHitResult order: 0 blocking, 4 location, 9 actor, 10 component
    if not bool(parts[0]) or parts[4] is None:
        return None
    actor = parts[9]
    component = parts[10]
    return {'z': round(float(parts[4].z), 2), 'actor': actor.get_name() if actor else None, 'label': actor.get_actor_label() if actor else None,
            'component': component.get_name() if component else None}


def all_hits(world, x, y):
    """Every blocking surface under a point, top down, so stacked floors are visible."""
    rows, ignore, top = [], [], 1500.0
    for _ in range(6):
        hit = trace(world, x, y, top, 600.0, ignore)
        if hit is None:
            break
        rows.append(hit)
        actor = next((a for a in vc.actors.get_all_level_actors() if a.get_name() == hit['actor']), None)
        if actor is None:
            break
        ignore.append(actor)
    return rows


def main():
    started = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    vc.require(vc.levels.load_level(MAP), 'Cannot load ' + MAP)
    world = vc.editor.get_editor_world()
    actors = list(vc.actors.get_all_level_actors())
    REPORT['actor_count'] = len(actors)
    for actor in actors:
        try:
            REPORT['actors'].append(actor_record(actor))
        except Exception:
            REPORT['warnings'].append('actor %s: %s' % (actor.get_name(), traceback.format_exc()[-400:]))
    REPORT['manager'] = manager_record(actors)
    settings = world.get_world_settings()
    REPORT['world_settings'] = {'game_mode_override': value(settings.get_editor_property('default_game_mode')),
                                'kill_z': get(settings, 'kill_z')}
    starts = [a for a in actors if isinstance(a, unreal.PlayerStart)]
    REPORT['player_starts'] = [{'name': a.get_name(), 'location': xyz(a.get_actor_location()), 'rotation': rot(a.get_actor_rotation())} for a in starts]
    for name, (x, y) in ANCHORS.items():
        REPORT['traces'].append({'id': name, 'x': x, 'y': y, 'hits': all_hits(world, float(x), float(y)),
                                 'street_formula_z': round(1020.0 - 0.1 * y, 2)})
    grid = []
    for y in range(-1500, 1801, 100):
        for x in (-450, -350, -250, -150, -50, 50, 150, 250, 350):
            hit = trace(world, float(x), float(y))
            grid.append({'x': x, 'y': y, 'z': hit['z'] if hit else None, 'actor': hit['label'] if hit else None,
                         'street_formula_z': round(1020.0 - 0.1 * y, 2)})
    REPORT['grid'] = grid
    packages = {}
    for row in REPORT['actors']:
        for c in row['components']:
            for key in ('static_mesh', 'skeletal_mesh'):
                if c.get(key):
                    root = '/'.join(c[key].split('/')[:4])
                    packages.setdefault(root, set()).add(row['name'])
    REPORT['asset_roots'] = {k: sorted(v) for k, v in packages.items()}
    REPORT['seconds'] = round(time.monotonic() - started, 1)
    REPORT['success'] = True


try:
    main()
except Exception:
    REPORT['error'] = traceback.format_exc()
vc.write_json(OUT / 'audit.json', REPORT)
vc.log('audit', json.dumps({k: REPORT.get(k) for k in ('success', 'actor_count', 'seconds', 'error')})[:600], str(OUT))
unreal.SystemLibrary.quit_editor()
