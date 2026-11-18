"""Adapt an inherited read-only art harness for this specific release copy."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'game_unreal/Python/capture_quest_art.py'
target = root / 'game_unreal/Python/capture_release_baseline.py'
text = source.read_text(encoding='utf-8')
old_guard = "if ROOT.parent.name != 'Quest_20261025':"
assert text.count(old_guard) == 1
text = text.replace(old_guard, "if ROOT.parent.name != 'Release_20261026':")
text = text.replace('Quest review is restricted to the protected Quest project',
                    'Release review is restricted to Release_20261026')
text = text.replace('quest_house_hero_preview_report.json', 'release_m0_house_preview_report.json')
text = text.replace("'quest_house_hero_preview'", "'release_m0_house_preview'")
assert 'release_m0_house_preview_report.json' in text
target.write_text(text, encoding='utf-8')
print(target)
