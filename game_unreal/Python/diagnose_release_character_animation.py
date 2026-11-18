"""Read-only native animation-data diagnostic, not a captured performance.

Uses installed UE5.8 AnimPose.h BlueprintCallable APIs. Compares evaluated
Source/Raw/Compressed animation, both skeleton- and optional-mesh-based, with
the preserved actual editor-component samples. Never relaxes capture assertions
or edits/reimports/saves any asset. Queue this separately in the full editor.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import sys
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
ROOT = PROJECT.parent
IMPORT_PATH = PROJECT / 'release_character_import_report.json'
COMPONENT_PATH = PROJECT / 'release_character_face_pose_report.json'
SOURCE_HEADER = Path('C:/Program Files/Epic Games/UE_5.8/Engine/Source/Editor/AnimationBlueprintLibrary/Public/AnimPose.h')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_files():
    files = list((PROJECT / 'Content').rglob('*.uasset')) + list((PROJECT / 'Content').rglob('*.umap'))
    files += list((PROJECT / 'Config').glob('*.ini')) + list(PROJECT.glob('*.uproject'))
    return {str(p): sha(p) for p in files}


def saves():
    roots = [PROJECT / 'Saved/SaveGames', Path(os.environ.get('LOCALAPPDATA', '')) / 'YesterdayHarbor/Saved/SaveGames']
    return {str(p): sha(p) for root in roots if root.is_dir() for p in root.rglob('*.sav')}


def transform(t):
    return {'translation': [float(getattr(t.translation, a)) for a in 'xyz'],
        'rotation_xyzw': [float(getattr(t.rotation, a)) for a in 'xyzw'],
        'scale': [float(getattr(t.scale3d, a)) for a in 'xyz']}


def difference(a, b):
    dot = abs(sum(x*y for x, y in zip(a['rotation_xyzw'], b['rotation_xyzw'])))
    angle = 2 * math.acos(min(1.0, max(0.0, dot)))
    translation = math.sqrt(sum((x-y)**2 for x, y in zip(a['translation'], b['translation'])))
    scale = max(abs(x-y) for x, y in zip(a['scale'], b['scale']))
    return {'rotation_radians': angle, 'translation_cm': translation, 'max_scale_delta': scale,
        'changed': angle > 1e-5 or translation > 1e-4 or scale > 1e-6}


def compare(first, second):
    return {name: difference(first[name], second[name]) for name in sorted(set(first) & set(second))}


def main():
    command = unreal.SystemLibrary.get_command_line()
    require(PROJECT == Path(__file__).resolve().parents[1] and ROOT.name == 'Release_20261026', 'Exact protected Release project required')
    require('-run=pythonscript' not in command.lower(), 'Use full UnrealEditor, not the Python commandlet')
    require(not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor(), 'No PIE diagnostic')
    before, saved_before = native_files(), saves()
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    folder = PROJECT / 'validation/release_character_animation' / run
    folder.mkdir(parents=True)
    report = {'success': False, 'run': run, 'scope': 'Native animation-data evaluation diagnostic; no rendered animation, gameplay, gait or NPC integration proof',
        'map_asset_save_calls': False, 'story_npcs_replaced': False, 'evaluations': [],
        'source_api': {'header': str(SOURCE_HEADER), 'sha256': sha(SOURCE_HEADER)}}
    try:
        imported = json.loads(IMPORT_PATH.read_text())
        require(imported['success'] and not imported['story_npcs_replaced'], 'Isolated native Mother import required')
        animation, mesh = unreal.load_asset(imported['animation']), unreal.load_asset(imported['mesh'])
        require(animation and mesh, 'Imported native animation/mesh failed to load')
        report.update(animation=imported['animation'], mesh=imported['mesh'], import_report_sha256=sha(IMPORT_PATH),
                      source_fbx_sha256=imported.get('fbx_sha256'))
        report['actual_python_api_docs'] = {name: getattr(unreal.AnimPoseExtensions, name).__doc__ for name in
            ['get_anim_pose_at_time', 'get_bone_names', 'get_bone_pose', 'get_ref_bone_pose', 'get_curve_names', 'get_curve_weight']}
        required = {'spine_02', 'spine_03', 'neck_01', 'upperarm_l', 'upperarm_r', 'lowerarm_l', 'lowerarm_r'}
        for eval_name in ['SOURCE', 'RAW', 'COMPRESSED']:
            for use_mesh in [False, True]:
                options = unreal.AnimPoseEvaluationOptions()
                settings = {'evaluation_type': getattr(unreal.AnimDataEvalType, eval_name),
                    'should_retarget': True, 'extract_root_motion': False,
                    'incorporate_root_motion_into_pose': True, 'retrieve_additive_as_full_pose': True,
                    'evaluate_curves': True, 'optional_skeletal_mesh': mesh if use_mesh else None}
                for key, value in settings.items():
                    options.set_editor_property(key, value)
                entry = {'type': eval_name, 'optional_mesh': use_mesh, 'should_retarget': True, 'samples': []}
                for second in [0.0, 1.0, 1.5, 2.0, 3.0]:
                    pose = unreal.AnimPoseExtensions.get_anim_pose_at_time(animation, second, options)
                    require(unreal.AnimPoseExtensions.is_valid(pose), 'Invalid native evaluated pose')
                    names = [str(n) for n in unreal.AnimPoseExtensions.get_bone_names(pose)]
                    require(required.issubset(names), 'Expected imported GameEngine arm/spine bones missing')
                    sample = {'time_seconds': second, 'bone_names': names,
                        'local': {n: transform(unreal.AnimPoseExtensions.get_bone_pose(pose, unreal.Name(n), unreal.AnimPoseSpaces.LOCAL)) for n in names},
                        'component': {n: transform(unreal.AnimPoseExtensions.get_bone_pose(pose, unreal.Name(n), unreal.AnimPoseSpaces.WORLD)) for n in names},
                        'reference_local': {n: transform(unreal.AnimPoseExtensions.get_ref_bone_pose(pose, unreal.Name(n), unreal.AnimPoseSpaces.LOCAL)) for n in sorted(required)},
                        'curves': {str(n): float(unreal.AnimPoseExtensions.get_curve_weight(pose, n)) for n in unreal.AnimPoseExtensions.get_curve_names(pose)}}
                    entry['samples'].append(sample)
                first = entry['samples'][0]
                entry['motion_vs_t0'] = [{'time_seconds': s['time_seconds'], 'bones': compare(first['local'], s['local'])} for s in entry['samples'][1:]]
                entry['changed_bones'] = sorted({n for row in entry['motion_vs_t0'] for n, delta in row['bones'].items() if delta['changed']})
                entry['t0_arm_delta_from_reference'] = {n: difference(first['reference_local'][n], first['local'][n]) for n in sorted(required) if 'arm_' in n}
                entry['blink_curve_values'] = [{'time_seconds': s['time_seconds'], 'curves': {n: v for n, v in s['curves'].items() if 'blink' in n.lower()}} for s in entry['samples']]
                report['evaluations'].append(entry)
        if COMPONENT_PATH.is_file():
            prior = json.loads(COMPONENT_PATH.read_text())
            require(prior['import_report_sha256'] == sha(IMPORT_PATH), 'Actual component evidence belongs to a different import')
            report['prior_actual_component'] = {'path': str(COMPONENT_PATH), 'sha256': sha(COMPONENT_PATH),
                'run': prior['run'], 'success': prior['success'], 'error': prior.get('error'), 'comparison': []}
            for entry in report['evaluations']:
                for sample in entry['samples']:
                    rows = [r for r in prior['images'] if r['job']['id'] == 'Listening_t' + str(int(sample['time_seconds']))
                            and sample['time_seconds'].is_integer()]
                    if rows:
                        report['prior_actual_component']['comparison'].append({'evaluation': entry['type'], 'optional_mesh': entry['optional_mesh'],
                            'time_seconds': sample['time_seconds'], 'bones': compare(sample['component'], rows[0]['actual_pose']['bones_component_space'])})
        moving_raw = any(e['changed_bones'] for e in report['evaluations'] if e['type'] in ['RAW', 'SOURCE'])
        moving_compressed = any(e['changed_bones'] for e in report['evaluations'] if e['type'] == 'COMPRESSED')
        report['findings'] = {'native_source_or_raw_tracks_change': moving_raw, 'native_compressed_tracks_change': moving_compressed,
            'rendered_pose_proven': False, 'capture_assertions_relaxed': False,
            'interpretation': ('Animation data changes; investigate editor-component evaluation/refresh before claiming a rendered idle.' if moving_raw and moving_compressed
                else 'Source/raw evaluation changes but compressed evaluation does not; inspect native compression/import.' if moving_raw
                else 'Native evaluated bone tracks remain static; inspect FBX export/action baking and native import before any NPC swap.')}
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        after, saved_after = native_files(), saves()
        report['guards'] = {'native_assets_config_unchanged': before == after, 'saved_games_unchanged': saved_before == saved_after,
            'changed_native_paths': sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))}
        report['success'] = bool(report['success'] and before == after and saved_before == saved_after)
        text = json.dumps(report, indent=2) + '\n'
        (folder / 'diagnostic_report.json').write_text(text)
        (PROJECT / 'release_character_animation_diagnostic.json').write_text(text)
        unreal.log('Mother animation-data diagnostic: ' + str(folder))
        if not report['success']:
            unreal.log_error(report.get('error', 'Native diagnostic guard failed'))
        unreal.SystemLibrary.quit_editor()


if __name__ == '__main__':
    main()
