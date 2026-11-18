"""Read-only probe (12 November 2026): which traces see the home furniture the Quest panel must stay clear of.

For the photograph, the letter and the workbench it traces straight down from 150 cm above the actor with four
variants (Visibility channel simple / complex, object types simple / complex) and records what each one hits.
Saves nothing. Report: game_unreal/validation/quest3/furniture_trace_probe.json
"""
import json
from pathlib import Path

import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
OUT = ROOT / 'validation' / 'quest3' / 'furniture_trace_probe.json'
report = {'targets': []}
try:
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level('/Game/Quest/Maps/Verdant_Desktop')
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    manager = next((a for a in actors if a.get_class().get_name().startswith('BP_OpeningActions')), None)
    report['manager'] = str(manager.get_name()) if manager else None
    object_types = [unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY1, unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY2, unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY3,
                    unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY4, unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY5, unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY6]

    def describe(hit):
        if hit is None:
            return None
        t = hit.to_tuple()
        fields = {'blocking': t[0], 'distance': round(t[3], 1), 'impact_z': round(t[5].z, 1)}
        for value in t:
            if isinstance(value, unreal.Actor):
                fields['actor'] = value.get_actor_label()
            elif isinstance(value, unreal.PrimitiveComponent):
                fields['component'] = value.get_name()
                fields['collision'] = str(value.get_collision_enabled())
                fields['profile'] = str(value.get_collision_profile_name())
                if isinstance(value, unreal.StaticMeshComponent) and value.static_mesh:
                    fields['mesh'] = value.static_mesh.get_name()
        return fields

    for name in ['PhotoActor', 'LetterActor', 'BenchActor', 'MotherActor']:
        actor = None
        try:
            actor = manager.get_editor_property(name) if manager else None
        except Exception:  # noqa: BLE001
            actor = None
        if actor is None:
            # The manager fills these at BeginPlay; in the editor world fall back to the actor label.
            word = name[:-5].lower()
            actor = next((a for a in actors if word in a.get_actor_label().lower() and not a.get_class().get_name().startswith('BP_OpeningActions')), None)
        if actor is None:
            report['targets'].append({'name': name, 'missing': True, 'labels': sorted(a.get_actor_label() for a in actors)[:0]})
            continue
        at = actor.get_actor_location()
        entry = {'name': name, 'label': actor.get_actor_label(), 'location': [round(at.x, 1), round(at.y, 1), round(at.z, 1)], 'traces': {}}
        for dx, dy in [(0, 0), (25, 0), (0, 25)]:
            start = unreal.Vector(at.x + dx, at.y + dy, at.z + 150)
            end = unreal.Vector(at.x + dx, at.y + dy, at.z - 150)
            key = '%d,%d' % (dx, dy)
            entry['traces'][key] = {}
            for label, complex_ in [('simple', False), ('complex', True)]:
                hit = unreal.SystemLibrary.line_trace_single(world, start, end, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, complex_, [actor],
                                                             unreal.DrawDebugTrace.NONE, True)
                entry['traces'][key]['visibility_' + label] = describe(hit)
                hit = unreal.SystemLibrary.line_trace_single_for_objects(world, start, end, object_types, complex_, [actor], unreal.DrawDebugTrace.NONE, True)
                entry['traces'][key]['objects_' + label] = describe(hit)
        report['targets'].append(entry)
    report['success'] = True
except Exception as error:  # noqa: BLE001 - the probe must always write its report
    import traceback
    report['success'] = False
    report['error'] = traceback.format_exc()
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=1), encoding='utf-8')
unreal.SystemLibrary.quit_editor()
