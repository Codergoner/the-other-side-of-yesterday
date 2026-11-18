"""Read-only persisted glove material check, without PIE duplication."""
from pathlib import Path
import json
import unreal
root = Path(unreal.Paths.project_dir()).resolve()
assert root.parent.name == 'Quest_20261025'
m = unreal.load_asset('/Game/Quest/XR/Hands/Materials/M_QuestMatteGlove')
c = unreal.MaterialEditingLibrary.get_material_property_input_node(m, unreal.MaterialProperty.MP_BASE_COLOR).get_editor_property('constant')
report = {'path': m.get_path_name(), 'color': [c.r, c.g, c.b],
          'metadata': unreal.EditorAssetLibrary.get_metadata_tag(m, 'Quest.HandMaterialVersion'),
          'skeletal_usage': m.get_editor_property('used_with_skeletal_mesh'), 'saved': False}
(root / 'quest_glove_probe.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
unreal.log('QUEST_GLOVE_PROBE ' + json.dumps(report))
