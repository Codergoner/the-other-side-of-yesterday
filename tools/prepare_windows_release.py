"""Explicit, release-copy-only Windows profile using installed engine binaries."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parents[1]
assert root.name == 'Release_20261026'
game = root / 'game_unreal'
record = root / 'windows_profile_changes.json'
if record.exists():
    previous = json.loads(record.read_text(encoding='utf-8'))
    for row in previous['files']:
        assert hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() == row['after_sha256'], 'Manual profile edit; inspect instead of overwriting'
    print('Approved Windows release profile already applied; no changes.')
    raise SystemExit(0)

descriptor = game / 'YesterdayHarbor.uproject'
engine = game / 'Config/DefaultEngine.ini'
settings = game / 'Config/DefaultGame.ini'
before = {path: path.read_bytes() for path in [descriptor, engine, settings]}
project = json.loads(before[descriptor].decode('utf-8-sig'))
project['Description'] = 'Windows Chapters I-II early-playable release work. The independent Quest project preserves VR.'
for plugin in project['Plugins']:
    if plugin['Name'] == 'OpenXR':
        plugin['PlatformAllowList'] = ['Android']
descriptor.write_text(json.dumps(project, indent=2) + '\n', encoding='utf-8')

text = before[engine].decode('utf-8-sig')
text = text.replace('GameDefaultMap=/Game/Quest/Maps/Verdant_VR', 'GameDefaultMap=/Game/Quest/Maps/Verdant_Desktop')
text = text.replace('GlobalDefaultGameMode=/Game/Quest/XR/BP_QuestGameMode.BP_QuestGameMode_C', 'GlobalDefaultGameMode=/Game/FirstPerson/Blueprints/BP_FirstPersonGameMode.BP_FirstPersonGameMode_C')
text = re.sub(r'^\+D3D12TargetedShaderFormats=.*\n', '', text, flags=re.M)
text = re.sub(r'\[/Script/AndroidPlatformEditor.AndroidSDKSettings\][\s\S]*?(?=\n\[|\Z)', '', text)
text = re.sub(r'^SecurityToken=.*$', 'SecurityToken=', text, flags=re.M)
engine.write_text(text, encoding='utf-8')
text = before[settings].decode('utf-8-sig')
text = text.replace('ProjectName=Yesterday Harbor Quest Development', 'ProjectName=The Other Side of Yesterday')
text = text.replace('Description=Quest 3 / 3S standalone development profile; headset performance is unverified.', 'Description=Chapters I-II early-playable Windows release work; not a completed release.')
text = text.replace('bStartInVR=True', 'bStartInVR=False')
text = text.replace('BuildConfiguration=PPBC_Development', 'BuildConfiguration=PPBC_Shipping')
text = re.sub(r'^\+MapsToCook=\(FilePath="/Game/Quest/Maps/Verdant_VR"\)\s*\n?', '', text, flags=re.M)
settings.write_text(text, encoding='utf-8')

rows = []
backup = root / 'output/windows_profile_baseline'
backup.mkdir(parents=True, exist_ok=True)
for path, data in before.items():
    (backup / path.name).write_bytes(data)
    rows.append({'path': str(path), 'before_sha256': hashlib.sha256(data).hexdigest(), 'after_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
result = {'files': rows, 'renderer': 'Existing mobile-forward/DX11/SM5 path; no pipeline migration',
          'scope': 'Windows release copy only; OpenXR remains allowed for Android, separate Quest project unchanged',
          'packaging_verified': False, 'headset_tested': False}
record.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
