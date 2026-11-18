"""Apply only the guarded scenery/material update to both existing Quest maps.

Queued by the root after other native authoring. Does not regenerate districts,
change XR/player/story classes, create map copies or touch desktop configuration.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, sys, traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import quest_scenery

MAPS = ['/Game/Quest/Maps/Verdant_Desktop', '/Game/Quest/Maps/Verdant_VR']
OUT = ROOT / 'quest_scenery_update_report.json'


def sha(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def run():
    if ROOT.parent.name != 'Quest_20261025':
        raise RuntimeError('Scenery update is restricted to the protected Quest copy')
    if '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError('Use the full editor -ExecutePythonScript entry point; this updater needs LevelEditorSubsystem UI initialization')
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if level.is_in_play_in_editor():
        raise RuntimeError('Scenery update must run outside PIE')
    # Saved production maps must already exist. This is never a map-cloning or
    # broad district build; all component/actor guards stay in apply_scenery().
    for path in MAPS:
        if not unreal.EditorAssetLibrary.does_asset_exist(path):
            raise RuntimeError('Required existing Quest map is missing: ' + path)
    protected = [ROOT / 'YesterdayHarbor.uproject', *(ROOT / 'Config').glob('*.ini')]
    for folder in ['Home', 'Harbor', 'BriefTest']:
        protected.extend((ROOT / 'Content' / folder).rglob('*.umap'))
    before = {str(file): sha(file) for file in protected if file.is_file()}
    report = {'success': False, 'run': datetime.now(timezone.utc).isoformat(),
              'scope': 'Known family-house wood/plaster component materials and QuestSoft lighting only',
              'default_profile': quest_scenery.DEFAULT_PROFILE,
              'source_sha256': sha(ROOT / 'Python' / 'quest_scenery.py'),
              'maps': [], 'protected_sha_before': before,
              'native_visual_or_headset_test': False}
    try:
        for path in MAPS:
            if not level.load_level(path):
                raise RuntimeError('Cannot load existing Quest map ' + path)
            world = editor.get_editor_world()
            row = quest_scenery.apply_scenery(world, quest_scenery.DEFAULT_PROFILE)
            if not row.get('success') or not row.get('shared_assets_unchanged'):
                raise RuntimeError('Guarded scenery application failed in ' + path)
            if not level.save_current_level():
                raise RuntimeError('Cannot save guarded scenery update in ' + path)
            report['maps'].append({'path': path, 'saved': True,
                'profile': row['lighting_profile'],
                'material_override_count': len(row['material_overrides']),
                'material_overrides': row['material_overrides'],
                'preserved_manual': row['preserved_manual'],
                'shared_assets_unchanged': row['shared_assets_unchanged']})
        report['protected_sha_after'] = {path: sha(Path(path)) for path in before}
        report['protected_inputs_unchanged'] = before == report['protected_sha_after']
        if not report['protected_inputs_unchanged']:
            raise RuntimeError('A protected non-Quest map, configuration or project file changed')
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        OUT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('QUEST_SCENERY_UPDATE_COMPLETE ' + json.dumps({'report': str(OUT), 'maps': len(report['maps']), 'profile': quest_scenery.DEFAULT_PROFILE}), flush=True)
    return report


if __name__ == '__main__':
    try:
        run()
    except Exception:
        unreal.log_error('QUEST_SCENERY_UPDATE_FAILED\n' + traceback.format_exc())
    finally:
        unreal.SystemLibrary.quit_editor()
