"""Dumps reflected property/method names for the classes the Verdant jobs configure."""
import re
import sys
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc

CLASSES = ['MaterialExpressionPerInstanceCustomData', 'ExponentialHeightFogComponent', 'SkyLightComponent', 'DirectionalLightComponent',
           'HierarchicalInstancedStaticMeshComponent', 'InstancedStaticMeshComponent', 'EditorScriptingMeshReductionOptions',
           'EditorScriptingMeshReductionSettings', 'StaticMeshComponent', 'Material', 'MaterialExpressionCustom', 'CustomInput',
           'PostProcessVolume', 'Texture2D', 'MaterialExpressionTextureSampleParameter2D', 'StaticMeshEditorSubsystem', 'MaterialEditingLibrary']
out = []
for name in CLASSES:
    cls = getattr(unreal, name, None)
    if cls is None:
        out.append('MISSING ' + name)
        continue
    doc = cls.__doc__ or ''
    props = re.findall(r'``(\w+)``\s*\((\w+)\)', doc)
    out.append('== %s: %d editor properties' % (name, len(props)))
    out.append('  ' + ', '.join('%s:%s' % p for p in props))
    methods = [m for m in dir(cls) if not m.startswith('_') and callable(getattr(cls, m, None))]
    out.append('  methods: ' + ', '.join(methods))
    for method in ('set_custom_data', 'set_custom_data_value', 'set_cull_distances', 'add_instances', 'set_lods', 'set_material_instance_texture_parameter_value'):
        fn = getattr(cls, method, None)
        if fn is not None:
            out.append('  %s: %s' % (method, (fn.__doc__ or '').strip().splitlines()[0] if fn.__doc__ else '?'))
(vc.EVIDENCE / 'api_probe.txt').write_text('\n'.join(out), encoding='utf-8')
vc.log('api probe written', len(out))
unreal.SystemLibrary.quit_editor()
