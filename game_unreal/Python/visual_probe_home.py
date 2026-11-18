"""Read-only inventory of the family home interior on the story map (11 November 2026, competition visual pass).

Run: verdant/run_unreal.ps1 -Script visual_probe_home.py -NoRender. Saves nothing in the project; writes
validation/visual_pass/<stamp>/home_inventory.json: every actor whose bounds touch the home box (label, class, tags,
mesh, per-slot materials, bounds, collision, hidden state), every light there, and the material assets available for
reuse under /Game/Verdant, /Game/Release, /Game/Quest and /Game/Opening.
"""
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
assert PROJECT.parent.name == 'Release_20261026'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
OUT = PROJECT / 'validation' / 'visual_pass' / STAMP
OUT.mkdir(parents=True, exist_ok=True)
MAP = '/Game/Quest/Maps/Verdant_Desktop'
# Home box in Unreal centimetres around the player start (-620, 1240, 1173) and Mother (-670..-910, 1240).
LO = unreal.Vector(-1500, 700, 950)
HI = unreal.Vector(100, 1900, 1500)
REPORT = {'success': False, 'map': MAP, 'box_cm': [[LO.x, LO.y, LO.z], [HI.x, HI.y, HI.z]], 'actors': [], 'lights': [], 'materials': {}}


def v(p):
    return [round(p.x, 1), round(p.y, 1), round(p.z, 1)]


def overlaps(origin, extent):
    return all(origin_c - extent_c <= hi and origin_c + extent_c >= lo for origin_c, extent_c, lo, hi in [
        (origin.x, extent.x, LO.x, HI.x), (origin.y, extent.y, LO.y, HI.y), (origin.z, extent.z, LO.z, HI.z)])


def main():
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not levels.load_level(MAP):
        raise RuntimeError('Cannot load ' + MAP)
    for actor in actors.get_all_level_actors():
        origin, extent = actor.get_actor_bounds(False)
        if not overlaps(origin, extent):
            continue
        # Skip city-scale actors (land, sea, sky): they overlap the box but are not the home.
        huge = max(extent.x, extent.y) > 3000
        row = {'name': actor.get_name(), 'label': actor.get_actor_label(), 'class': actor.get_class().get_name(),
               'tags': [str(t) for t in actor.get_editor_property('tags')], 'origin': v(origin), 'extent': v(extent),
               'location': v(actor.get_actor_location()), 'hidden': bool(actor.get_editor_property('hidden')), 'huge': huge, 'components': []}
        for c in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = c.get_editor_property('static_mesh')
            row['components'].append({'component': c.get_name(), 'mesh': mesh.get_path_name() if mesh else None, 'visible': bool(c.is_visible()),
                                      'materials': [(m.get_path_name() if m else None) for m in [c.get_material(i) for i in range(c.get_num_materials())]],
                                      'slots': [str(n) for n in c.get_material_slot_names()],
                                      'collision': str(c.get_collision_enabled()), 'cast_shadow': bool(c.get_editor_property('cast_shadow')),
                                      'scale': v(c.get_world_scale())})
        for c in actor.get_components_by_class(unreal.SkeletalMeshComponent):
            row['components'].append({'component': c.get_name(), 'skeletal': True})
        lights = actor.get_components_by_class(unreal.LightComponentBase)
        for c in lights:
            entry = {'actor': actor.get_actor_label(), 'class': c.get_class().get_name(), 'location': v(c.get_world_location()),
                     'intensity': float(c.get_editor_property('intensity')), 'color': str(c.get_editor_property('light_color')),
                     'mobility': str(c.get_editor_property('mobility')), 'cast_shadows': bool(c.get_editor_property('cast_shadows')),
                     'visible': bool(c.is_visible()), 'tags': row['tags']}
            for name in ('attenuation_radius', 'source_radius', 'indirect_lighting_intensity'):
                try:
                    entry[name] = float(c.get_editor_property(name))
                except Exception:
                    pass
            REPORT['lights'].append(entry)
        if row['components'] or lights or row['class'] in ('PostProcessVolume', 'ExponentialHeightFog', 'SkyLight', 'DirectionalLight'):
            REPORT['actors'].append(row)
    # Global lighting actors, wherever they are.
    for actor in actors.get_all_level_actors():
        if actor.get_class().get_name() in ('DirectionalLight', 'SkyLight', 'ExponentialHeightFog', 'PostProcessVolume', 'SkyAtmosphere'):
            REPORT.setdefault('global_lighting', []).append({'label': actor.get_actor_label(), 'class': actor.get_class().get_name(),
                                                             'tags': [str(t) for t in actor.get_editor_property('tags')], 'hidden': bool(actor.get_editor_property('hidden')),
                                                             'location': v(actor.get_actor_location())})
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    for root in ['/Game/Verdant', '/Game/Release', '/Game/Quest', '/Game/Opening']:
        names = []
        for data in registry.get_assets_by_path(root, recursive=True):
            cls = str(data.asset_class_path.asset_name)
            if cls in ('Material', 'MaterialInstanceConstant'):
                names.append(str(data.package_name))
        REPORT['materials'][root] = sorted(names)
    REPORT['success'] = True


try:
    main()
except Exception:
    REPORT['error'] = traceback.format_exc()
(OUT / 'home_inventory.json').write_text(json.dumps(REPORT, indent=1), encoding='utf-8')
unreal.log('VERDANT visual probe ' + ('ok ' if REPORT['success'] else 'FAILED ') + str(OUT))
unreal.SystemLibrary.quit_editor()
