"""Read-only Quest 3 inventory of the Release copy: XR assets, manager/HUD graph state, map facts, sky textures.

Run through verdant/run_unreal.ps1 -Script quest3_inventory.py -NoRender -UserDir <short> -Flags @('-Quest3Out=<dir>').
Nothing is saved: Blueprints are compiled in memory only, the level is loaded but never written.
"""
from pathlib import Path
import json
import re
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Release_20261026', 'Quest 3 inventory runs only in the Release copy'
sys.path.insert(0, str(ROOT / 'Python'))
import opening_graph as og

L, P, E = og.L, og.P, og.E
MANAGER = '/Game/Opening/Blueprints/BP_OpeningActions'
HUD = '/Game/Opening/Blueprints/BP_OpeningHUD'
CHARACTER = '/Game/Quest/XR/BP_QuestCharacter'
GAME_MODE = '/Game/Quest/XR/BP_QuestGameMode'
DESKTOP_GAME_MODE = '/Game/FirstPerson/Blueprints/BP_FirstPersonGameMode'
DESKTOP_PAWN = '/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter'
MAP = '/Game/Quest/Maps/Verdant_Desktop'
KEY_NODE_TITLES = ('wasinputkeyjustpressed', 'isinputkeydown', 'getinputanalogkeystate', 'wasinputkeyjustreleased', 'getinputkeytimedown')


def out_dir():
    match = re.search(r'-Quest3Out=("[^"]+"|\S+)', unreal.SystemLibrary.get_command_line())
    if not match:
        raise RuntimeError('-Quest3Out=<dir> is required')
    path = Path(match.group(1).strip('"'))
    path.mkdir(parents=True, exist_ok=True)
    return path


def pin_default(pin):
    for name in ('get_pin_default_value', 'get_pin_value', 'get_default_value'):
        getter = getattr(P, name, None)
        if getter is None:
            continue
        try:
            return str(getter(pin))
        except Exception:
            continue
    return None


def metadata(asset, key):
    try:
        return unreal.EditorAssetLibrary.get_metadata_tag(asset, key)
    except Exception:
        return None


def blueprint_report(path, compile_it=True):
    report = {'path': path, 'exists': unreal.EditorAssetLibrary.does_asset_exist(path)}
    if not report['exists']:
        return report
    bp = unreal.load_asset(path)
    report['class'] = bp.get_class().get_name()
    try:
        parent = bp.get_editor_property('parent_class')
        report['parent_class'] = parent.get_path_name() if parent else None
    except Exception:
        report['parent_class'] = None
    graphs = []
    key_literals = {}
    calls_into_manager = set()
    for graph in L.list_graphs(bp):
        editor = E.get_graph_editor(graph)
        nodes = editor.list_all_nodes()
        graphs.append({'name': graph.get_name(), 'nodes': len(nodes)})
        for node in nodes:
            title = str(L.get_node_title(node))
            compact = title.replace(' ', '').lower()
            if any(compact.startswith(t) for t in KEY_NODE_TITLES):
                pin = L.find_input_pin(node, 'Key')
                if P.is_valid(pin) and not list(P.list_connected_pins(pin)):
                    value = pin_default(pin)
                    key_literals.setdefault(value, 0)
                    key_literals[value] += 1
            if 'BP_OpeningActions' in title or '_Quest_' in title:
                calls_into_manager.add(title)
    report['graphs'] = sorted(graphs, key=lambda g: g['name'])
    report['function_names'] = sorted(g['name'] for g in graphs)
    report['key_literals'] = key_literals
    report['titles_mentioning_manager_or_quest'] = sorted(calls_into_manager)[:200]
    report['variables'] = sorted(str(n) for n in L.list_member_variable_names(bp, False))
    report['metadata'] = {k: metadata(bp, k) for k in ['Quest.XRWrappers', 'Release.FrontendHooks', 'Release.TextScalePatched', 'Quest.HandsUpgrade', 'Quest.HandMaterialVersion']}
    if compile_it:
        try:
            report['compile'] = og.compile_bp(bp, save=False, raise_on_error=False)
        except Exception:
            report['compile'] = {'error': traceback.format_exc()}
    try:
        cdo = unreal.get_default_object(L.generated_class(bp))
        details = {}
        for prop in ['default_pawn_class', 'hud_class', 'player_controller_class', 'game_state_class', 'player_state_class', 'spectator_class']:
            try:
                value = cdo.get_editor_property(prop)
                details[prop] = value.get_path_name() if value else None
            except Exception:
                pass
        try:
            details['tags'] = [str(t) for t in cdo.get_editor_property('tags')]
        except Exception:
            pass
        report['defaults'] = details
    except Exception:
        report['defaults'] = None
    return report


def texture_report(path):
    report = {'path': path, 'exists': unreal.EditorAssetLibrary.does_asset_exist(path)}
    if not report['exists']:
        return report
    texture = unreal.load_asset(path)
    for prop in ['compression_settings', 'lod_group', 'mip_gen_settings', 'never_stream', 'srgb', 'max_texture_size', 'lod_bias']:
        try:
            report[prop] = str(texture.get_editor_property(prop))
        except Exception:
            report[prop] = None
    try:
        report['size'] = [texture.blueprint_get_size_x(), texture.blueprint_get_size_y()]
    except Exception:
        try:
            report['size'] = [texture.get_editor_property('size_x'), texture.get_editor_property('size_y')]
        except Exception:
            report['size'] = None
    return report


def map_report():
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    report = {'map': MAP, 'loaded': level.load_level(MAP)}
    world = editor.get_editor_world()
    settings = world.get_world_settings() if world else None
    try:
        override = settings.get_editor_property('default_game_mode') if settings else None
        report['world_settings_game_mode_override'] = override.get_path_name() if override else None
    except Exception:
        report['world_settings_game_mode_override'] = 'unreadable'
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    report['actor_count'] = len(actors)
    landings = []
    managers = []
    starts = []
    hism = {'components': 0, 'instances': 0, 'cull_distance_samples': []}
    tags_summary = {}
    for actor in actors:
        tags = [str(t) for t in actor.tags]
        for t in tags:
            tags_summary[t] = tags_summary.get(t, 0) + 1
        if 'Quest.Teleport' in tags:
            loc = actor.get_actor_location()
            landings.append({'name': actor.get_name(), 'label': actor.get_actor_label(), 'location': [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)],
                             'hidden_in_game': bool(actor.get_editor_property('hidden')), 'collision_enabled': bool(actor.get_actor_enable_collision()),
                             'tags': tags})
        if actor.get_class().get_path_name() == MANAGER + '.BP_OpeningActions_C':
            managers.append({'name': actor.get_name(), 'label': actor.get_actor_label(), 'tags': tags})
        if isinstance(actor, unreal.PlayerStart):
            loc = actor.get_actor_location()
            starts.append({'name': actor.get_name(), 'location': [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)]})
        for component in actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
            hism['components'] += 1
            hism['instances'] += component.get_instance_count()
            if len(hism['cull_distance_samples']) < 8:
                hism['cull_distance_samples'].append({'actor': actor.get_actor_label(), 'start': component.get_editor_property('instance_start_cull_distance'),
                                                      'end': component.get_editor_property('instance_end_cull_distance')})
    report['teleport_landings'] = landings
    report['managers'] = managers
    report['player_starts'] = starts
    report['hism'] = hism
    report['tag_summary'] = {k: v for k, v in sorted(tags_summary.items()) if v >= 1 and (k.startswith('Quest') or k.startswith('Opening') or k.startswith('Verdant') or k.startswith('quest') or k.startswith('npc') or k.startswith('home') or k.startswith('cast'))}
    return report


def main():
    out = out_dir()
    result = {'success': False, 'read_only': True, 'saved_assets': False, 'blueprints': {}, 'textures': {}, 'map': None}
    try:
        for key, path in [('manager', MANAGER), ('hud', HUD), ('character', CHARACTER), ('game_mode', GAME_MODE), ('desktop_game_mode', DESKTOP_GAME_MODE), ('desktop_pawn', DESKTOP_PAWN)]:
            result['blueprints'][key] = blueprint_report(path)
        for key, path in [('sky_past', '/Game/Verdant/Textures/T_V_Sky_Past'), ('sky_present', '/Game/Verdant/Textures/T_V_Sky_Present'),
                          ('ambient_past', '/Game/Verdant/Textures/TC_V_SkyAmbient_Past'), ('ambient_present', '/Game/Verdant/Textures/TC_V_SkyAmbient_Present')]:
            result['textures'][key] = texture_report(path)
        result['map'] = map_report()
        result['success'] = True
    except Exception:
        result['error'] = traceback.format_exc()
        unreal.log_error(result['error'])
    (out / 'inventory.json').write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    unreal.log('QUEST3_INVENTORY ' + json.dumps({'success': result['success'], 'out': str(out)}))


main()
unreal.SystemLibrary.quit_editor()
