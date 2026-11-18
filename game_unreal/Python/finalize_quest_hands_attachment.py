"""Queued hand attachment-only save using natively inspected Epic Pawn values."""
from pathlib import Path
import hashlib
import json
import sys
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
assert root.parent.name == 'Quest_20261025'
assert unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'QuestHandsAttachmentOnly'), 'Explicit writer flag required'
sys.path.insert(0, str(root / 'Python'))
import quest_xr_hands as hands
import build_quest_xr as core
import opening_graph as og

protected = list((root / 'Config').glob('*.ini')) + list((root / 'Content/Quest/Maps').glob('*.umap'))
protected += list((root / 'Content/Opening').rglob('*.uasset'))
def hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}

before = hashes()
bp = unreal.load_asset(core.CHAR_PATH)
assert unreal.EditorAssetLibrary.get_metadata_tag(bp, 'Quest.HandsUpgrade') == '1'
attachments = hands.template_grip_attachments()
entries = core._subobjects(bp)[2]
for side in ['Left', 'Right']:
    obj = next(e[2] for e in entries if e[0] == 'QuestHandVisual' + side)
    authored = attachments['Hand' + side]
    r = authored['rotation_degrees']
    core.transform(obj, authored['location_cm'], (r['pitch'], r['yaw'], r['roll']), authored['scale'])
compiled = og.compile_bp(bp, save=True)
after = hashes()
report = {'success': before == after, 'compiled': compiled, 'attachments': attachments,
          'headset_tested': False, 'protected_inputs_unchanged': before == after,
          'scope': 'Only owned Character hand component transforms changed; template values copied without new tracking source'}
(root / 'quest_hands_attachment_report.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
assert report['success'], report
unreal.log('QUEST_HANDS_ATTACHMENT ' + json.dumps(report, default=str))
