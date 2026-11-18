"""Queued owned glove material usage repair; no map or Character saves."""
from pathlib import Path
import hashlib
import json
import datetime
import shutil
import sys
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
assert root.parent.name == 'Quest_20261025'
assert unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'QuestHandsMaterialOnly'), 'Explicit writer flag required'
sys.path.insert(0, str(root / 'Python'))
import quest_xr_hands

protected = list((root / 'Config').glob('*.ini')) + list((root / 'Content/Quest/Maps').glob('*.umap'))
protected += [root / 'Content/Quest/XR/BP_QuestCharacter.uasset']
def hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}

before = hashes()
package = root / 'Content/Quest/XR/Hands/Materials/M_QuestMatteGlove.uasset'
archive_dir = root.parent / 'output/material_versions' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
archive_dir.mkdir(parents=True, exist_ok=True)
archive = archive_dir / package.name
shutil.copy2(package, archive)
archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
material = quest_xr_hands.matte_material()
flag = bool(material.get_editor_property('used_with_skeletal_mesh'))
version = unreal.EditorAssetLibrary.get_metadata_tag(material, 'Quest.HandMaterialVersion')
emissive = unreal.MaterialEditingLibrary.get_material_property_input_node(material, unreal.MaterialProperty.MP_EMISSIVE_COLOR)
after = hashes()
report = {'success': flag and before == after and version == quest_xr_hands.GLOVE_VERSION and emissive is None,
          'material': material.get_path_name(), 'material_version': version,
          'base_color_linear': list(quest_xr_hands.GLOVE_ALBEDO), 'albedo_multiplier_from_initial': 1.6,
          'emissive_connected': emissive is not None,
          'prior_package_archive': str(archive), 'prior_package_sha256': archive_sha,
          'final_package_file': str(package), 'final_package_sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
          'used_with_skeletal_mesh': flag, 'protected_inputs_unchanged': before == after,
          'protected_before': before, 'protected_after': after, 'headset_tested': False}
(root / 'quest_hands_material_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
assert report['success'], report
unreal.log('QUEST_HANDS_MATERIAL ' + json.dumps(report))
