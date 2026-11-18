"""Read-only schema/compiler checks, plus one report in this staging folder.

This does NOT compile C++, deserialize saves or launch Unreal. Native safety,
transaction recovery, module integration and Shipping behavior remain untested.
"""
from pathlib import Path
import ast
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
RELEASE = HERE.parent
PROJECT = RELEASE / 'game_unreal'
PLUGIN = HERE / 'YesterdaySaveGuard'
ENGINE = Path('C:/Program Files/Epic Games/UE_5.8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def literal(path, name):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == name for n in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f'Missing source declaration {name}: {path}')


checks = []
def check(label, value):
    checks.append({'label': label, 'pass': bool(value)})
    if not value:
        raise AssertionError(label)


report = {'kind': 'source_only', 'time_utc': datetime.now(timezone.utc).isoformat(),
          'native_compilation_verified_by_this_script': False, 'candidate_activation_verified': False,
          'native_tests_run_by_this_script': False, 'checks': checks}
try:
    check('Staging is in isolated release copy', RELEASE.name == 'Release_20261026')
    descriptor = json.loads((PLUGIN / 'YesterdaySaveGuard.uplugin').read_text())
    check('Plugin disabled by default', descriptor['EnabledByDefault'] is False)
    check('Source candidate outside game Plugins', not PLUGIN.resolve().is_relative_to((PROJECT/'Plugins').resolve()))
    deployed=PROJECT/'Plugins/YesterdaySaveGuard'
    report['deployed_plugin_present']=deployed.exists()
    if deployed.exists():
        candidate_files=[p for p in (PLUGIN/'Source').rglob('*') if p.is_file()]
        report['deployed_sources_match_candidate']=all((deployed/p.relative_to(PLUGIN)).is_file() and sha(deployed/p.relative_to(PLUGIN))==sha(p) for p in candidate_files)
    # Version 5 (2 November 2026) adds Android (Meta Quest 3) beside Win64 as a recorded platform change.
    check('Win64 + Android runtime candidate', descriptor['SupportedTargetPlatforms'] == ['Win64', 'Android'] and
          descriptor['Modules'][0]['Type'] == 'Runtime' and
          descriptor['Modules'][0].get('PlatformAllowList') == ['Win64', 'Android'])
    build_rules = (PLUGIN / 'Source/YesterdaySaveGuard/YesterdaySaveGuard.Build.cs').read_text(encoding='utf-8-sig')
    check('bcrypt.lib linked only on Win64', re.search(r'if \(Target\.Platform == UnrealTargetPlatform\.Win64\)\s*\{\s*PublicSystemLibraries\.Add\("bcrypt\.lib"\)', build_rules) is not None
          and build_rules.count('bcrypt.lib') == 1)

    py = PROJECT / 'Python'
    base = py / 'build_opening_actions.py'
    story = py / 'build_chapters_story.py'
    frontend = py / 'build_release_frontend.py'
    expected_campaign = {n: 'B' for n in literal(base, 'FLAGS') + literal(story, 'NEW_FLAGS')}
    expected_campaign.update({n: 'I' for n in literal(story, 'INT_FIELDS')})
    expected_campaign.update({n: 'S' for n in literal(story, 'STRING_FIELDS')})
    expected_campaign.update({n: 'R' for n in literal(story, 'REAL_FIELDS')})
    expected_campaign.update({'TrustEventIds': 'A', 'Chapter': 'I', 'SchemaVersion': 'I',
                              'Era': 'S', 'SafeLocationId': 'S'})
    types = {'bool': 'B', 'int': 'I', 'string': 'S', 'real': 'R'}
    expected_profile = {n: types[t[0]] for n, t in literal(frontend, 'PROFILE_FIELDS').items()}
    # Additive campaign revisions: each later kind is exactly the previous kind plus its
    # authoring script's FIELDS (story v0.2 chronology/intention, then identity consent).
    revisions = [('campaign-v1', expected_campaign)]
    previous = dict(expected_campaign)
    for kind, script in [('campaign-v2', py / 'integrate_quest_story_v02.py'), ('campaign-v3', py / 'integrate_quest_identity_v02.py')]:
        if not script.is_file():
            break
        current = dict(previous)
        current.update({n: types[t[0]] for n, t in literal(script, 'FIELDS').items()})
        revisions.append((kind, current))
        previous = current
    cpp = PLUGIN / 'Source/YesterdaySaveGuard/Private/YesterdaySaveGuardLibrary.cpp'
    text = cpp.read_text(encoding='utf-8-sig')
    schema_source = re.search(r'TMap<FString, TCHAR> Schema\(const FString& Kind\)\s*\{(.*?)\n\}\n', text, re.S)
    check('Closed Schema() function present', schema_source is not None)
    schema_source = schema_source.group(1)

    def kinds_of(condition):
        return set(re.findall(r'Kind == TEXT\("([^"]+)"\)', condition))

    def block_fields(kind):
        """Fields granted to a kind: every Add() whose enclosing if-conditions all name that kind."""
        actual, stack = {}, []
        for line in schema_source.splitlines():
            stripped = line.strip()
            indent = len(line) - len(line.lstrip(' '))
            while stack and stack[-1][0] >= indent and not stripped.startswith('{'):
                stack.pop()
            if stripped.startswith(('if (', 'else if (')):
                stack.append((indent, kind in kinds_of(stripped)))
                continue
            found = re.match(r'Add\(TEXT\("([^"]+)"\), \'([BISRA])\'\);', stripped)
            if found and stack and all(active for _, active in stack):
                for field in found.group(1).split(','):
                    check(f'{kind}: no duplicate {field}', field not in actual)
                    actual[field] = found.group(2)
        return actual

    supported = kinds_of(schema_source)
    for name, expected in revisions + [('profile-v1', expected_profile)]:
        check(f'Closed schema block for {name}', name in supported)
        actual = block_fields(name)
        check(f'{name}: exact current source field/type parity', actual == expected)
        report.setdefault('schema_fields', {})[name] = len(actual)
    check('No unreviewed schema kinds', supported == {name for name, _ in revisions} | {'profile-v1'})
    check('Only pinned import calls raw decoder', text.count('UGameplayStatics::LoadGameFromMemory(') == 1)
    check('Windows CNG and Win32 file primitives are compiled only on Windows',
          text.count('#if PLATFORM_WINDOWS') >= 3 and text.count('#include <bcrypt.h>') == 1 and
          text.index('#if PLATFORM_WINDOWS') < text.index('#include <bcrypt.h>'))
    check('Portable SHA-256 and POSIX lock/rename exist for the Android target',
          'struct FPortableSha256' in text and 'LOCK_EX | LOCK_NB' in text and 'RenameWithoutReplace(' in text and
          '::rename(' in text and text.count('MoveFileExW') == 2)
    check('Portable SHA-256 is validated on the host by the automation test',
          'Portable SHA-256 abc vector' in text and 'Portable SHA-256 two-block padding vector' in text)
    descriptor_version = int(descriptor['Version'])
    # Version numbering: 1 = source candidate, 2 = CNG baseline, 3 = story v0.2 (campaign-v2),
    # 4 = identity v0.2 (campaign-v3), 5 = Android (Meta Quest 3) platform revision, same schemas.
    check('Descriptor version matches the campaign revisions plus the CNG baseline and the Android platform revision',
          descriptor_version == len(revisions) + 2)
    report['descriptor'] = {'Version': descriptor_version, 'VersionName': descriptor.get('VersionName')}
    fixture = RELEASE.parent / 'Brief_20261025/game_unreal/Saved/SaveGames/Yesterday_Automation_A_v1_20261024T151953_576332_FirstPerson.sav'
    expected_hash = '0f698bb9c4a003a7aa2883af39317161a1e38290ca388626231bce5f1caf94e8'
    check('Exact legacy fixture hash pin matches protected fixture', fixture.is_file() and sha(fixture) == expected_hash and expected_hash in text)
    report['legacy_fixture_sha256'] = expected_hash
    report['sources_sha256'] = {str(p.relative_to(HERE)): sha(p) for p in sorted(HERE.rglob('*'))
                                if p.is_file() and p.name != 'source_audit.json' and '__pycache__' not in p.parts}
    sdk = ENGINE / 'Engine/Config/Windows/Windows_SDK.json'
    report['engine_sdk_config_sha256'] = sha(sdk)
    report['toolchain_discovery'] = {
        'cl_on_path': shutil.which('cl.exe'), 'clang_cl_on_path': shutil.which('clang-cl.exe'),
        'default_visual_studio_path_exists': Path('C:/Program Files/Microsoft Visual Studio').exists(),
        'vswhere_exists': Path('C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe').is_file(),
        'windows_sdk_include_exists': Path('C:/Program Files (x86)/Windows Kits/10/Include').is_dir(),
        'custom_toolchain_search_exhaustive': False}
    report['source_audit_passed'] = True
except Exception as exc:
    report['source_audit_passed'] = False
    report['error'] = repr(exc)
finally:
    (HERE / 'source_audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({k: report.get(k) for k in ['kind', 'source_audit_passed', 'schema_fields', 'toolchain_discovery', 'error']}, indent=2))
raise SystemExit(0 if report['source_audit_passed'] else 1)
