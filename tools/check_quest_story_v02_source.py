"""Parse/expand the queued harness without importing or simulating Unreal.

Only the existing wrapper's pure source-text transformations are evaluated.
No gameplay, editor APIs, save migration, fixtures or native tests run here.
"""
from pathlib import Path
import ast
import hashlib
import json
import py_compile

RELEASE = Path(__file__).resolve().parents[1]
ROOT = RELEASE / 'game_unreal'


def selected_transformations(path, helper_names, literal_assignments=()):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    selected = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in helper_names:
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in literal_assignments for t in node.targets):
            selected.append(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id in helper_names:
            selected.append(node)
        elif isinstance(node, ast.For):
            # Both wrappers' top-level loops are explicit source-label
            # replacements. Refuse any changed loop that invokes native APIs.
            if any(isinstance(x, ast.Name) and x.id in {'unreal', 'og'} for x in ast.walk(node)):
                raise RuntimeError('Native operation entered a source-text transformation loop')
            selected.append(node)
    return ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))


def main():
    files = [ROOT / 'Python/integrate_quest_story_v02.py', ROOT / 'Python/validate_quest_story_v02.py']
    for file in files:
        py_compile.compile(str(file), doraise=True)
    data = json.loads((ROOT / 'ContentData/quest_story_v02.json').read_text(encoding='utf-8'))
    if [row['value'] for row in data['intentions']] != [1, 2, 3]:
        raise AssertionError('Exactly three explicit journey intentions are required')
    scope = {'Path': Path, 'ast': ast, 'hashlib': hashlib, 'json': json, 'root': ROOT,
             'source': (ROOT / 'Python/validate_brief_m2.py').read_text(encoding='utf-8')}
    parent = ROOT / 'Python/validate_release_story.py'
    exec(compile(selected_transformations(parent, {'replace', 'replace_function'}), str(parent), 'exec'), scope)
    child = ROOT / 'Python/validate_quest_story_v02.py'
    exec(compile(selected_transformations(child, {'v2_replace'}, {'V2_HELPERS'}), str(child), 'exec'), scope)
    expanded = scope['source']
    ast.parse(expanded)
    for text in ['C1_INTENTION_01', 'PublicChronologyObserved', 'OrderRegisterObserved',
                 'MotherJourneyIntention', 'QuestV2InspectDatedRecord', 'chronology_after',
                 'The original final Tomorrow exchange remains last', 'restart_and_check']:
        if text not in expanded:
            raise AssertionError('Queued acceptance coverage missing: ' + text)
    out = ROOT / 'validation/quest_story_v02_source'
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'expanded_harness_NOT_EXECUTED.py'
    target.write_text(expanded, encoding='utf-8')
    report = {'success': True, 'scope': 'Python syntax, JSON and pure queued-harness text expansion only',
              'native_unreal_imported': False, 'native_runtime_tested': False, 'native_guard_migration_tested': False,
              'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              'expanded_harness_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'expanded_harness': str(target)}
    (out / 'source_check.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
