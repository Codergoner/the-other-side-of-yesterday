"""Give SM_V_Story_PlankDoor a solid simple box collision (4 November 2026).

The 2 November polish swapped the past-house entrance barrier (Opening.PastHomeDoor) to this plank mesh, whose
8 mm plank gaps line up with the mesh's vertical centre line; its complex-as-simple collision therefore lets the
story harness's centre visibility ray through (editor probe validation/quest3/<stamp>_door/door_probe.json:
4 of 5 centre-column rays miss). A door is a solid barrier: this job adds a box simple collision to the mesh asset
and uses the default trace flag (simple for queries, complex for complex traces). Asset change only; the map and the
actor are untouched. Backup of the .uasset and before/after state under validation/quest3/<stamp>_doorfix/.
Run with -Quest3DoorWrite through verdant/run_unreal.ps1 -NoRender.
"""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Release_20261026'
STAMP = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
OUT = ROOT / 'validation/quest3' / (STAMP + '_doorfix')
MESH = '/Game/Verdant/Meshes/SM_V_Story_PlankDoor'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state(mesh):
    body = mesh.get_editor_property('body_setup')
    return {'trace_flag': str(body.get_editor_property('collision_trace_flag')),
            'simple_collisions': unreal.EditorStaticMeshLibrary.get_simple_collision_count(mesh),
            'convex_collisions': unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh)}


def main():
    report = {'success': False, 'stamp': STAMP, 'mesh': MESH, 'saved': False}
    try:
        if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3DoorWrite'):
            raise RuntimeError('Explicit -Quest3DoorWrite flag and the serialized native writer slot are required')
        OUT.mkdir(parents=True, exist_ok=True)
        disk = ROOT / 'Content' / (MESH.removeprefix('/Game/') + '.uasset')
        backup = OUT / disk.name
        shutil.copy2(disk, backup)
        report['backup'] = {'file': str(disk), 'backup': str(backup), 'sha256_before': sha(backup)}
        mesh = unreal.load_asset(MESH)
        if mesh is None:
            raise RuntimeError('Missing ' + MESH)
        report['before'] = state(mesh)
        added = unreal.EditorStaticMeshLibrary.add_simple_collisions(mesh, unreal.ScriptingCollisionShapeType.BOX)
        report['box_added'] = int(added)
        body = mesh.get_editor_property('body_setup')
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_DEFAULT)
        mesh.set_editor_property('body_setup', body)
        if not unreal.EditorAssetLibrary.save_loaded_asset(mesh):
            raise RuntimeError('Cannot save ' + MESH)
        report['saved'] = True
        report['after'] = state(mesh)
        report['sha256_after'] = sha(disk)
        report['success'] = report['after']['simple_collisions'] >= 1
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'plank_door_collision.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    unreal.log('QUEST3_DOOR_FIX ' + json.dumps({'success': report['success'], 'after': report.get('after')}))


main()
unreal.SystemLibrary.quit_editor()
