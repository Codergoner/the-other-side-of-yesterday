"""Audit all three protected source generations without changing any of them."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

root = Path(__file__).resolve().parents[1]
result = {'success': True, 'utc': datetime.now(timezone.utc).isoformat(), 'generations': []}
for filename in ['source_baseline_manifest.json', 'quest_baseline_manifest.json', 'release_baseline_manifest.json']:
    manifest = json.loads((root / filename).read_text(encoding='utf-8-sig'))
    changes = []
    for row in manifest['files']:
        path = Path(row['source'])
        if not path.is_file():
            changes.append({'path': str(path), 'reason': 'missing'})
        elif hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            changes.append({'path': str(path), 'reason': 'SHA-256 mismatch'})
    result['generations'].append({'manifest': filename, 'files_checked': len(manifest['files']), 'unchanged': not changes, 'changes': changes})
    result['success'] = result['success'] and not changes
(root / 'release_preservation_validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['success'] else 1)
