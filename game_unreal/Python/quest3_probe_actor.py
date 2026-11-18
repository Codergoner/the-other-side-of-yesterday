"""Read-only lookup of level actors by name on the story map: label, folder, tags, mesh, bounds, collision.

Run through verdant/run_unreal.ps1 -NoRender with -Quest3Out=<dir> -Quest3Actors=Name1,Name2. Quits without saving.
"""
from pathlib import Path
import json
import re
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Release_20261026'
MAP = '/Game/Quest/Maps/Verdant_Desktop'


def arg(name):
    match = re.search(r'-' + name + r'=("[^"]+"|\S+)', unreal.SystemLibrary.get_command_line())
    return match.group(1).strip('"') if match else None


def describe(actor):
    row = {'name': actor.get_name(), 'label': actor.get_actor_label(), 'class': actor.get_class().get_name(),
           'folder': str(actor.get_folder_path()), 'tags': [str(t) for t in actor.tags],
           'location': list(actor.get_actor_location().to_tuple()), 'scale': list(actor.get_actor_scale3d().to_tuple()),
           'hidden_in_game': bool(actor.get_editor_property('hidden')), 'actor_collision': bool(actor.get_actor_enable_collision())}
    center, extent = actor.get_actor_bounds(False)
    row['bounds_center'] = list(center.to_tuple())
    row['bounds_extent'] = list(extent.to_tuple())
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    if component is not None:
        mesh = component.get_editor_property('static_mesh')
        row['mesh'] = mesh.get_path_name() if mesh else None
        row['component_collision'] = str(component.get_collision_enabled())
        row['visibility_response'] = str(component.get_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY))
        row['component_visible'] = bool(component.is_visible())
    return row


def main():
    out = Path(arg('Quest3Out'))
    out.mkdir(parents=True, exist_ok=True)
    wanted = [n for n in (arg('Quest3Actors') or '').split(',') if n]
    report = {'success': False, 'map': MAP, 'actors': {}}
    try:
        level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        assert level.load_level(MAP)
        for actor in unreal.EditorLevelLibrary.get_all_level_actors():
            if actor.get_name() in wanted:
                report['actors'][actor.get_name()] = describe(actor)
        report['missing'] = [n for n in wanted if n not in report['actors']]
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    (out / 'actor_probe.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    unreal.log('QUEST3_ACTOR_PROBE ' + json.dumps({'success': report['success'], 'found': list(report['actors'])}))


main()
unreal.SystemLibrary.quit_editor()
