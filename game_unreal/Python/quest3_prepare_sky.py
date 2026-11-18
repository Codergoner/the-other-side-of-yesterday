"""Headset sky budget: give the two Verdant sky panoramas mipmaps and the Skybox LOD group (2 November 2026).

The baked panoramas are 5120x2560 (not a power of two) with no mipmaps, so no device-profile size cap can
apply to them. This job sets power-of-two stretching, simple-average mips and TEXTUREGROUP_Skybox on
T_V_Sky_Past / T_V_Sky_Present only. On Windows the full-size mip 0 is still what the dome samples (the
Skybox group is uncapped there); on the Quest 3 the project device profile caps the group at 2048, so the APK
only carries the 2048x1024 and smaller mips. Backups and before/after properties go to
validation/quest3/<stamp>_sky/. Run with -Quest3SkyWrite through verdant/run_unreal.ps1.
"""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Release_20261026', 'Quest 3 sky job runs only in the Release copy'
STAMP = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
OUT = ROOT / 'validation/quest3' / (STAMP + '_sky')
TEXTURES = ['/Game/Verdant/Textures/T_V_Sky_Past', '/Game/Verdant/Textures/T_V_Sky_Present']
PROPS = ['compression_settings', 'lod_group', 'mip_gen_settings', 'power_of_two_mode', 'never_stream', 'srgb', 'max_texture_size']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(texture):
    row = {}
    for name in PROPS:
        try:
            row[name] = str(texture.get_editor_property(name))
        except Exception as problem:
            row[name] = 'unreadable: ' + str(problem)[:80]
    try:
        row['size'] = [texture.blueprint_get_size_x(), texture.blueprint_get_size_y()]
    except Exception:
        row['size'] = None
    return row


def main():
    report = {'success': False, 'stamp': STAMP, 'textures': {}, 'saved': False}
    try:
        if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3SkyWrite'):
            raise RuntimeError('Explicit -Quest3SkyWrite flag and the serialized native writer slot are required')
        OUT.mkdir(parents=True, exist_ok=True)
        for path in TEXTURES:
            disk = ROOT / 'Content' / (path.removeprefix('/Game/') + '.uasset')
            backup = OUT / disk.name
            shutil.copy2(disk, backup)
            texture = unreal.load_asset(path)
            if texture is None:
                raise RuntimeError('Missing sky texture ' + path)
            before = snapshot(texture)
            texture.set_editor_property('power_of_two_mode', unreal.TexturePowerOfTwoSetting.STRETCH_TO_POWER_OF_TWO)
            texture.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
            texture.set_editor_property('lod_group', unreal.TextureGroup.TEXTUREGROUP_SKYBOX)
            texture.set_editor_property('never_stream', True)
            if not unreal.EditorAssetLibrary.save_loaded_asset(texture):
                raise RuntimeError('Cannot save ' + path)
            after = snapshot(texture)
            report['textures'][path] = {'file': str(disk), 'backup': str(backup), 'sha256_before': sha(backup), 'sha256_after': sha(disk),
                                        'before': before, 'after': after}
        report['saved'] = True
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'sky_textures.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    unreal.log('QUEST3_SKY ' + json.dumps({'success': report['success'], 'out': str(OUT)}))


main()
unreal.SystemLibrary.quit_editor()
