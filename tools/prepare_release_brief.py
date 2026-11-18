"""Extract the user's bundled documents without rewriting their contents."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parents[1]
folder = root / 'docs/Release_20261026'
text = (folder / 'FULL_RELEASE_PROMPT.md').read_text(encoding='utf-8-sig')
markers = list(re.finditer(r'<!-- Bundled source: ([A-Za-z0-9_]+\.md) -->', text))
records = []
for index, marker in enumerate(markers):
    end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
    content = text[marker.end():end].strip()
    content = re.sub(r'\n\s*---\s*$', '', content).rstrip() + '\n'
    path = folder / marker.group(1)
    if path.exists() and path.read_text(encoding='utf-8-sig').strip() != content.strip():
        path = path.with_stem(path.stem + '_BUNDLED')
    if not path.exists():
        path.write_text(content, encoding='utf-8')
    records.append({'source_section': marker.group(1), 'path': str(path),
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'status': 'authored requirements, not implementation evidence'})
(folder / 'brief_manifest.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
print(json.dumps(records, indent=2))
