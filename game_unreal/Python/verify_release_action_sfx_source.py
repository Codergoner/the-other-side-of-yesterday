"""Offline expansion/syntax proof only. Does not import Unreal or run native QA."""
from pathlib import Path
import ast
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'Python'))
import release_action_sfx_qa_source as sfx


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assemble():
    story = ROOT/'Python/validate_release_story.py'
    audio = ROOT/'Python/validate_release_story_audio.py'
    base = ROOT/'Python/validate_brief_m2.py'
    source = base.read_text(encoding='utf-8')
    wrapper = story.read_text(encoding='utf-8')
    start, end = wrapper.index('def replace('), wrapper.index('# Unsaved fixture helper')
    # Execute only the existing pure string/AST transforms, before its native
    # fixture/import/callback section. These prefixes contain no native calls.
    namespace = {'source': source, 'ast': ast, 'hashlib': hashlib,
                 'Path': Path, 'root': ROOT, '__file__': str(story)}
    exec(compile(wrapper[start:end], str(story)+' [source transforms only]', 'exec'), namespace)
    source = namespace['source']
    wrapper = audio.read_text(encoding='utf-8')
    start, end = wrapper.index('def replace_once('), wrapper.index('# Source syntax is checked')
    namespace.update(source=source, __file__=str(audio))
    exec(compile(wrapper[start:end], str(audio)+' [source transforms only]', 'exec'), namespace)
    expanded = sfx.expand(namespace['source'])
    ast.parse(expanded)
    compile(expanded, 'release_action_sfx_expanded [not executed]', 'exec')
    # Test helper code never seeds progress or authors a native object.
    helpers = Path(sfx.__file__).with_name('release_action_sfx_qa_helpers.py')
    tree = ast.parse(helpers.read_text(encoding='utf-8'))
    forbidden = ['set_editor_property', 'set_actor_location', 'save_loaded_asset', 'save_current_level']
    calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    if any(name in calls for name in forbidden):
        raise RuntimeError('Action SFX helpers acquired direct property/position/asset writes')
    return expanded, [base, story, audio, Path(sfx.__file__), helpers,
                       ROOT/'Python/validate_release_action_sfx.py']


def main():
    expanded, sources = assemble()
    folder = ROOT/'validation/release_action_sfx_source'
    folder.mkdir(parents=True, exist_ok=True)
    output = folder/'expanded_offline.py'
    output.write_text(expanded, encoding='utf-8')
    report = {'success': True, 'scope': __doc__, 'expanded_file': str(output),
        'expanded_sha256': digest(output), 'expanded_lines': len(expanded.splitlines()),
        'source_sha256': {str(path): digest(path) for path in sources},
        'pure_source_transform_match': True, 'syntax_parse_and_compile': True,
        'direct_progress_or_asset_writes_in_helpers': False,
        'native_qa_executed': False, 'pcm_captured': False, 'runtime_accepted': False}
    (folder/'offline_verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['success', 'expanded_lines', 'native_qa_executed', 'pcm_captured']}))
    return report


if __name__ == '__main__':
    main()
