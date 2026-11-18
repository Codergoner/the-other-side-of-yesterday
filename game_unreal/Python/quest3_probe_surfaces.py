"""Read-only surface inventory of the story map (15 November 2026): what is each visible surface made of?

Run through verdant/run_unreal.ps1 -NoRender with -Quest3Out=<dir>. Quits without saving.
  materials   every material used by a static-mesh component on the map, with component counts; for materials outside
              /Game/Verdant and /Game/Quest/XR/VisualPass the actors that use them are listed (label, location, tags).
  views       for a few camera views (Blender metres, as trailer_director.SCENIC) a grid of visibility rays; per ray the
              first hits (actor label, mesh, materials, hidden flag, tags) so a pixel in a recorded frame can be named.
"""
from pathlib import Path
import json
import math
import re
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Release_20261026'
MAP = '/Game/Quest/Maps/Verdant_Desktop'
VIEWS = {  # name: (position, target) in Blender metres; Unreal = (100x, -100y, 100z)
    'HomeFront': ((1.4, -16.6, 10.22), (-5.0, -12.0, 11.71)),
    'UphillCathedral': ((0.4, -21.0, 9.72), (1.5, 52.0, 26.0)),
    'HarborOverlook': ((4.5, 14.0, 13.22), (40.0, 30.0, 6.5)),
    'ClinicCourtyard': ((-0.2, -0.4, 11.72), (-6.8, -4.6, 11.10)),
    'Wing': ((-0.2, -8.2, 10.96), (-6.0, -9.6, 12.6)),
}


def arg(name):
    match = re.search(r'-' + name + r'=("[^"]+"|\S+)', unreal.SystemLibrary.get_command_line())
    return match.group(1).strip('"') if match else None


def m(p):
    return unreal.Vector(p[0] * 100.0, -p[1] * 100.0, p[2] * 100.0)


def materials_of(component):
    out = []
    for i in range(component.get_num_materials()):
        mat = component.get_material(i)
        out.append(mat.get_path_name().split('.')[0] if mat else None)
    return out


def main():
    out = Path(arg('Quest3Out'))
    out.mkdir(parents=True, exist_ok=True)
    report = {'success': False, 'map': MAP}
    try:
        level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        assert level.load_level(MAP)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        usage, foreign = {}, {}
        for actor in unreal.EditorLevelLibrary.get_all_level_actors():
            for component in actor.get_components_by_class(unreal.StaticMeshComponent):
                mesh = component.get_editor_property('static_mesh')
                for slot, path in enumerate(materials_of(component)):
                    key = str(path)
                    usage[key] = usage.get(key, 0) + 1
                    if path is None or not (path.startswith('/Game/Verdant') or path.startswith('/Game/Quest/XR/VisualPass')):
                        foreign.setdefault(key, []).append({
                            'label': actor.get_actor_label(), 'name': actor.get_name(), 'slot': slot,
                            'mesh': mesh.get_path_name().split('.')[0] if mesh else None,
                            'location': [round(v, 1) for v in actor.get_actor_location().to_tuple()],
                            'scale': [round(v, 3) for v in actor.get_actor_scale3d().to_tuple()],
                            'tags': [str(t) for t in actor.tags], 'hidden': bool(actor.get_editor_property('hidden')),
                            'component_visible': bool(component.is_visible())})
        report['material_usage'] = dict(sorted(usage.items(), key=lambda kv: -kv[1]))
        report['foreign_material_users'] = foreign
        views = {}
        for name, (pos, target) in VIEWS.items():
            eye, aim = m(pos), m(target)
            rotation = unreal.MathLibrary.find_look_at_rotation(eye, aim)
            fwd = unreal.MathLibrary.get_forward_vector(rotation)
            right = unreal.MathLibrary.get_right_vector(rotation)
            up = unreal.MathLibrary.get_up_vector(rotation)
            rows = []
            columns, lines = 13, 7
            for j in range(lines):
                for i in range(columns):
                    u = (i / (columns - 1)) * 2 - 1          # -1 left .. 1 right, 90 degree horizontal view
                    v = 1 - (j / (lines - 1)) * 2            # 1 top .. -1 bottom
                    direction = fwd + right * u + up * (v * 9.0 / 16.0)
                    end = eye + direction * 30000.0
                    hits = unreal.SystemLibrary.line_trace_multi(world, eye, end, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [],
                                                               unreal.DrawDebugTrace.NONE, True) or []
                    found = []
                    for hit in hits[:4]:
                        t = hit.to_tuple()
                        actor, component = t[9], t[10]
                        if actor is None:
                            continue
                        row = {'label': actor.get_actor_label(), 'name': actor.get_name(), 'cm': round(float(t[3]), 0),
                               'hidden': bool(actor.get_editor_property('hidden')), 'tags': [str(x) for x in actor.tags][:6]}
                        if isinstance(component, unreal.StaticMeshComponent):
                            mesh = component.get_editor_property('static_mesh')
                            row['mesh'] = mesh.get_name() if mesh else None
                            row['materials'] = [str(p).rsplit('/', 1)[-1] for p in materials_of(component)]
                        found.append(row)
                    rows.append({'col': i, 'row': j, 'hits': found})
            views[name] = rows
        report['views'] = views
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    (out / 'surface_probe.json').write_text(json.dumps(report, indent=1, default=str), encoding='utf-8')
    unreal.log('QUEST3_SURFACE_PROBE ' + json.dumps({'success': report['success'], 'materials': len(report.get('material_usage', {}))}))


main()
unreal.SystemLibrary.quit_editor()
