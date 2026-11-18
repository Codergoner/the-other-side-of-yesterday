"""Remove cross-platform native requirements from this Windows-only release copy.

UE5.8 hybrid-target detection checks all enabled platforms, even during a Win64
package. Android-only OpenXR still generates a temporary project target.
The independently preserved Quest project remains the VR/Android path.
"""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parents[1]
assert root.name == 'Release_20261026'
game = root / 'game_unreal'
record = root / 'windows_runtime_isolation.json'
if record.exists():
    data = json.loads(record.read_text())
    assert all(hashlib.sha256(Path(r['path']).read_bytes()).hexdigest() == r['after_sha256'] for r in data['files']), 'Manual configuration change; inspect before repeating'
    print('Windows runtime isolation already applied.')
    raise SystemExit(0)
project_path = game / 'YesterdayHarbor.uproject'
engine_path = game / 'Config/DefaultEngine.ini'
before = {p: p.read_bytes() for p in [project_path, engine_path]}
project = json.loads(before[project_path].decode('utf-8-sig'))
for plugin in project['Plugins']:
    if plugin['Name'] == 'OpenXR':
        plugin['Enabled'] = False
        plugin.pop('PlatformAllowList', None)
project['TargetPlatforms'] = ['Windows']
project_path.write_text(json.dumps(project, indent=2) + '\n', encoding='utf-8')
text = before[engine_path].decode('utf-8-sig')
text = re.sub(r'\[/Script/Android[^\]]*\][\s\S]*?(?=\n\[|\Z)', '', text)
text = re.sub(r'\[OnlineSubsystemGooglePlay.Store\][\s\S]*?(?=\n\[|\Z)', '', text)
engine_path.write_text(text.rstrip() + '\n', encoding='utf-8')
backup = root / 'output/windows_runtime_profile_before_isolation'
backup.mkdir(parents=True, exist_ok=True)
rows = []
for path, old in before.items():
    (backup / path.name).write_bytes(old)
    rows.append({'path': str(path), 'before_sha256': hashlib.sha256(old).hexdigest(), 'after_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
data = {'scope': 'Windows-only release; separate Quest project retains XR and Android support',
        'reason': 'Installed UE5.8 NativeProjects.RequiresTempTarget iterates all enabled platforms',
        'files': rows, 'packaging_verified': False}
record.write_text(json.dumps(data, indent=2), encoding='utf-8')
print(json.dumps(data, indent=2))
