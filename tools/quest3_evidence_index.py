"""Write an evidence index (path, bytes, SHA-256) for the Quest 3 work of the Release copy.

Usage (Blender's python, -I): quest3_evidence_index.py <release root> <output json> <path or glob>...
Paths are relative to the release root; directories are walked. The index is data about files that exist;
it makes no claim about what they prove.
"""
from pathlib import Path
import hashlib
import json
import sys
from datetime import datetime, timezone


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    root = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2])
    rows = []
    for pattern in sys.argv[3:]:
        matches = list(root.glob(pattern)) if any(c in pattern for c in '*?[') else [root / pattern]
        for match in matches:
            files = [p for p in match.rglob('*') if p.is_file()] if match.is_dir() else ([match] if match.is_file() else [])
            for file in sorted(files):
                rows.append({'path': str(file.relative_to(root)).replace('\\', '/'), 'bytes': file.stat().st_size, 'sha256': sha(file)})
    index = {'created_utc': datetime.now(timezone.utc).isoformat(), 'release_root': str(root), 'file_count': len(rows),
             'total_bytes': sum(r['bytes'] for r in rows), 'files': rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, indent=2), encoding='utf-8')
    print(json.dumps({'file_count': len(rows), 'total_bytes': index['total_bytes'], 'output': str(output)}))


if __name__ == '__main__':
    main()
