"""Read-only probe of the past-house entrance barrier (Opening.PastHomeDoor) after the story-set polish.

Loads the story map, reports the door's mesh, collision set-up and bounds, temporarily enables its collision in
the editor world (never saved), and runs the harness's frontage visibility query plus a grid of parallel rays and
a complex-trace variant. Output: -Quest3Out=<dir>/door_probe.json. Quits without saving.
"""
from pathlib import Path
import json
import re
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Release_20261026'
MAP = '/Game/Quest/Maps/Verdant_Desktop'


def out_dir():
    match = re.search(r'-Quest3Out=("[^"]+"|\S+)', unreal.SystemLibrary.get_command_line())
    path = Path(match.group(1).strip('"'))
    path.mkdir(parents=True, exist_ok=True)
    return path


def trace(world, start, end, complex_trace):
    hit = unreal.SystemLibrary.line_trace_single(world, start, end, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, complex_trace, [], unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return {'hit': False, 'actor': None, 'component': None, 'location': None}
    row = hit.to_tuple()
    return {'hit': bool(row[0]), 'actor': str(row[9]) if row[0] else None, 'component': str(row[10]) if row[0] else None,
            'location': [round(row[4].x, 1), round(row[4].y, 1), round(row[4].z, 1)] if row[0] else None}


def main():
    out = out_dir()
    report = {'success': False, 'saved': False}
    try:
        level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        assert level.load_level(MAP)
        world = editor.get_editor_world()
        doors = [a for a in unreal.EditorLevelLibrary.get_all_level_actors() if 'Opening.PastHomeDoor' in [str(t) for t in a.tags]]
        assert len(doors) == 1, len(doors)
        door = doors[0]
        component = door.get_component_by_class(unreal.StaticMeshComponent)
        mesh = component.get_editor_property('static_mesh')
        body = mesh.get_editor_property('body_setup') if mesh else None
        report['door'] = {'name': door.get_name(), 'label': door.get_actor_label(), 'mesh': mesh.get_path_name() if mesh else None,
                          'scale': list(door.get_actor_scale3d().to_tuple()), 'location': list(door.get_actor_location().to_tuple()),
                          'hidden': bool(door.get_editor_property('hidden')), 'actor_collision': bool(door.get_actor_enable_collision()),
                          'component_collision': str(component.get_collision_enabled()),
                          'trace_flag': str(body.get_editor_property('collision_trace_flag')) if body else None,
                          'simple_collision_count': unreal.EditorStaticMeshLibrary.get_simple_collision_count(mesh) if mesh else None,
                          'convex_collision_count': unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh) if mesh else None,
                          'triangles_lod0': unreal.EditorStaticMeshLibrary.get_number_verts(mesh, 0) if mesh else None}
        center, extent = door.get_actor_bounds(False)
        report['door']['bounds_center'] = list(center.to_tuple())
        report['door']['bounds_extent'] = list(extent.to_tuple())
        # Temporary, editor-world only, never saved: make the barrier queryable as it is in the past era.
        door.set_actor_hidden_in_game(False)
        door.set_actor_enable_collision(True)
        component.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
        offset = unreal.Vector(extent.x + 30, 0, 0)
        report['harness_query_simple'] = trace(world, center + offset, center - offset, False)
        report['harness_query_complex'] = trace(world, center + offset, center - offset, True)
        grid = []
        for dy in (-40, -20, 0, 20, 40):
            for dz in (-90, -45, 0, 45, 90):
                o = unreal.Vector(0, dy, dz)
                grid.append({'dy': dy, 'dz': dz, 'simple': trace(world, center + offset + o, center - offset + o, False)['actor'],
                             'complex': trace(world, center + offset + o, center - offset + o, True)['actor']})
        report['grid'] = grid
        report['hits_simple'] = sum(1 for g in grid if g['simple'] and door.get_name() in g['simple'])
        report['hits_complex'] = sum(1 for g in grid if g['complex'] and door.get_name() in g['complex'])
        # Control: the same query against a neighbouring Verdant land mesh and the kit door of the clinic.
        controls = []
        for actor in unreal.EditorLevelLibrary.get_all_level_actors():
            label = actor.get_actor_label()
            if label.startswith('Opening - Past family home') or 'Story_DoorOpen' in label or label.startswith('Verdant_Land'):
                c, e = actor.get_actor_bounds(False)
                o = unreal.Vector(e.x + 30, 0, 0)
                controls.append({'label': label, 'name': actor.get_name(), 'hidden': bool(actor.get_editor_property('hidden')),
                                 'actor_collision': bool(actor.get_actor_enable_collision()), 'x_ray_simple': trace(world, c + o, c - o, False)['actor'],
                                 'x_ray_complex': trace(world, c + o, c - o, True)['actor']})
        report['controls'] = controls[:12]
        overlap = unreal.SystemLibrary.box_overlap_actors(world, center, unreal.Vector(5, 5, 5), [], None, [])
        report['box_overlap_at_center'] = [a.get_name() for a in overlap]
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    (out / 'door_probe.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    unreal.log('QUEST3_DOOR_PROBE ' + json.dumps({'success': report['success'], 'hits_simple': report.get('hits_simple'), 'hits_complex': report.get('hits_complex')}))


main()
unreal.SystemLibrary.quit_editor()
