"""Inspect the real M0 package independently from UAT's successful exit."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import struct

root = Path(__file__).resolve().parents[1]
archive = root / 'output/windows_m0_probe'
uat = root / 'game_unreal/release_windows_m0_uat.log'
assert 'AutomationTool exiting with ExitCode=0 (Success)' in uat.read_text(encoding='utf-8-sig')
boot = archive / 'YesterdayHarbor.exe'
runtime = archive / 'Engine/Binaries/Win64/UnrealGame-Win64-Shipping.exe'
def pe(path):
    with path.open('rb') as stream:
        assert stream.read(2) == b'MZ', path
        stream.seek(0x3c)
        offset = struct.unpack('<I', stream.read(4))[0]
        stream.seek(offset)
        assert stream.read(4) == b'PE\0\0', path
        assert struct.unpack('<H', stream.read(2))[0] == 0x8664, path
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'machine': 'AMD64'}
executables = [pe(boot), pe(runtime)]
files = [p for p in archive.rglob('*') if p.is_file() and p.name != 'artifact_manifest.json']
containers = [p for p in files if p.suffix in {'.pak', '.utoc', '.ucas'}]
assert any(p.suffix == '.ucas' for p in containers)
assert any(p.suffix == '.utoc' for p in containers)
assert not any(part in {'Intermediate', 'DerivedDataCache', 'SaveGames'} for p in files for part in p.relative_to(archive).parts)
result = {'success': True, 'verified_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'M0 standalone Win64 Shipping package inspection before release frontend and new human art',
    'uat_success': True, 'archive': str(archive), 'archive_layout': 'single-platform files directly at archive root',
    'postcheck_correction': 'The initial wrapper expected a Windows subfolder; actual files were at archive root. No artifact or receipt was fabricated.',
    'executables': executables, 'files': len(files), 'total_bytes': sum(p.stat().st_size for p in files),
    'containers': [{'path': str(p.relative_to(archive)), 'bytes': p.stat().st_size} for p in containers],
    'runtime_prerequisites': [str(p.relative_to(archive)) for p in files if 'redist' in p.name.lower() or p.suffix == '.msi'],
    'package_playtested': False, 'device_tested': False, 'trailer_captured': False, 'trailer_encoded': False}
public_manifest = dict(result)
public_manifest['archive'] = '.'
public_manifest['executables'] = [dict(row, path=str(Path(row['path']).relative_to(archive))) for row in executables]
(archive / 'artifact_manifest.json').write_text(json.dumps(public_manifest, indent=2), encoding='utf-8')
(root / 'game_unreal/release_windows_m0_package_verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
