"""Stage an isolated native template inspection project; no production writes."""
from pathlib import Path
import hashlib
import json
import shutil

root = Path(__file__).resolve().parents[1]
stage = root / 'output/staging/xr_hands/template_inspection'
engine = Path('C:/Program Files/Epic Games/UE_5.8')
sources = {'XRFramework': engine / 'Templates/TemplateResources/Standard/XRFramework/Content',
           'XRMannequins': root / 'output/staging/xr_hands/OriginalMount_XRMannequins'}
entries = []
for mount, source in sources.items():
    assert source.is_dir(), source
    for original in sorted(source.rglob('*')):
        if original.is_file():
            dest = stage / 'Content' / mount / original.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, dest)
            entries.append({'source': str(original), 'staged': str(dest),
                            'sha256': hashlib.sha256(original.read_bytes()).hexdigest()})
project = {'FileVersion': 3, 'EngineAssociation': '5.8',
           'Plugins': [{'Name': name, 'Enabled': True} for name in
                       ['PythonScriptPlugin', 'EditorScriptingUtilities', 'EnhancedInput', 'ControlRig', 'FullBodyIK', 'OpenXR', 'Niagara']]}
(stage / 'TemplateInspection.uproject').write_text(json.dumps(project, indent=2), encoding='utf-8')
(stage / 'staging_manifest.json').write_text(json.dumps({'purpose': 'Read native Epic XRFramework attachment transforms; never save inspected packages', 'files': entries}, indent=2), encoding='utf-8')
print(json.dumps({'project': str(stage / 'TemplateInspection.uproject'), 'file_count': len(entries)}))
