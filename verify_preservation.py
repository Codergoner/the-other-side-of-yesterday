"""Read-only SHA-256 audit of both protected source generations."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json

root=Path(__file__).resolve().parent
report={'success':True,'utc':datetime.now(timezone.utc).isoformat(),'generations':[]}
for manifest_name in ['source_baseline_manifest.json','quest_baseline_manifest.json']:
    manifest=json.loads((root/manifest_name).read_text(encoding='utf-8'))
    changed=[]
    for row in manifest['files']:
        source=Path(row['source'])
        if not source.is_file():changed.append({'path':str(source),'reason':'missing'})
        elif hashlib.sha256(source.read_bytes()).hexdigest()!=row['sha256']:
            changed.append({'path':str(source),'reason':'SHA-256 changed'})
    report['generations'].append({'manifest':manifest_name,'files_checked':len(manifest['files']),'unchanged':not changed,'changes':changed})
    report['success']=report['success'] and not changed
(root/'preservation_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['success'] else 1)
