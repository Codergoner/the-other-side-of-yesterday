"""Read-only Quest APK prerequisites. Never installs, builds or launches UE.

Exit 2 means blocked. A passing result is prerequisites only, not an APK,
deployment, headset test, refresh-rate measurement or store certification.
"""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import subprocess
import sys


def configured_env(name):
    value = os.environ.get(name)
    if value or os.name != 'nt':
        return value
    # Toolchain setup may update registry environment values while the Codex
    # host remains open. Read those values without changing process settings.
    import winreg
    for hive, key in [(winreg.HKEY_CURRENT_USER, 'Environment'),
                      (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')]:
        try:
            with winreg.OpenKey(hive, key) as entry:
                value = winreg.QueryValueEx(entry, name)[0]
                if value:
                    return os.path.expandvars(value)
        except OSError:
            pass
    return None


def inspect(engine, project):
    engine = Path(engine).resolve()
    project = Path(project).resolve()
    portable_path = project.parent.parent / 'tools/android_toolchain_manifest.json'
    portable = json.loads(portable_path.read_text(encoding='utf-8-sig')) if portable_path.exists() else {}
    requirement_file = engine / 'Engine/Config/Android/Android_SDK.json'
    requirements = json.loads(requirement_file.read_text(encoding='utf-8')) if requirement_file.exists() else {}
    checks = []

    def check(name, ok, detail, blocker=True):
        checks.append({'name': name, 'passed': bool(ok), 'blocker': blocker, 'detail': str(detail)})

    check('Engine Android requirements', requirement_file.exists(), requirement_file)
    for relative in ['Engine/Binaries/Android/UnrealGame.target',
                     'Engine/Binaries/Android/UnrealGame-Android-Shipping.target']:
        path = engine / relative
        check('Installed Android payload: ' + path.name, path.exists(), path)
        if path.exists():
            receipt = json.loads(path.read_text(encoding='utf-8'))
            for product in receipt.get('BuildProducts', []):
                if product.get('Type') == 'Executable' and 'arm64' in product.get('Path', ''):
                    binary = Path(product['Path'].replace('$(EngineDir)', str(engine / 'Engine')))
                    check('ARM64 engine executable: ' + binary.name, binary.exists(), binary)
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
    sdk_candidates = [portable.get('sdk_root') if portable.get('success') else None,
                      configured_env('ANDROID_HOME'), configured_env('ANDROID_SDK_ROOT'), str(local / 'Android/Sdk')]
    sdk = next((Path(p).resolve() for p in sdk_candidates if p and Path(p).is_dir()), None)
    check('Android SDK root', sdk is not None, sdk or 'No configured SDK or standard Android/Sdk path')
    if sdk:
        for kind, value in [('platforms', requirements.get('platforms', 'android-36')),
                            ('build-tools', requirements.get('build-tools', '36.0.0')),
                            ('ndk', requirements.get('ndk', '27.2.12479018')),
                            ('cmake', requirements.get('cmake', '3.22.1'))]:
            path = sdk / kind / value
            check(kind + ' ' + value, path.exists(), path)
        clang = sdk / 'ndk' / requirements.get('ndk', '27.2.12479018') / 'toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe'
        check('NDK Android compiler', clang.exists(), clang)
    java_home = (portable.get('java_home') if portable.get('success') else None) or configured_env('JAVA_HOME') or configured_env('AGDE_JAVA_HOME')
    bundled_jbr = Path('C:/Program Files/Android/Android Studio/jbr')
    java = Path(java_home) / 'bin/java.exe' if java_home else bundled_jbr / 'bin/java.exe'
    java_version = ''
    if java.exists():
        result = subprocess.run([str(java), '-version'], capture_output=True, text=True, timeout=15)
        java_version = (result.stderr + result.stdout).strip()
    check('JDK runtime', java.exists(), java_version or java)
    match = re.search(r'version\s+"(?:1\.)?(\d+)', java_version)
    major = int(match.group(1)) if match else None
    check('JDK major version accepted by installed UBT', major is not None and major >= 17,
          'Detected ' + str(major) + '; installed UBT requires at least 17; Epic recommends JDK 21')
    javac = java.with_name('javac.exe')
    check('JDK compiler', javac.exists(), javac)
    adb = sdk / 'platform-tools/adb.exe' if sdk else Path(shutil.which('adb') or 'MISSING_ADB')
    check('ADB deploy tool', adb.exists(), adb)
    devices = []
    if adb.exists():
        # adb devices may start its local daemon; keep the default diagnostic
        # completely process-free. Explicit --devices opts into that query.
        devices = ['Not queried. Run --devices to inspect connected debug-authorized devices.']
    descriptor = json.loads(project.read_text(encoding='utf-8'))
    enabled = {p['Name'] for p in descriptor.get('Plugins', []) if p.get('Enabled')}
    check('Bundled OpenXR enabled', 'OpenXR' in enabled, 'Project Plugins/OpenXR')
    check('OpenXR plugin installed', (engine / 'Engine/Plugins/Runtime/OpenXR/OpenXR.uplugin').exists(), 'Bundled generic Epic OpenXR; Meta XR is not assumed')
    for name in ['BP_QuestCharacter', 'BP_QuestGameMode']:
        path = project.parent / 'Content/Quest/XR' / (name + '.uasset')
        check('Authored XR asset ' + name, path.exists(), path)
    for name in ['Verdant_Desktop', 'Verdant_VR']:
        path = project.parent / 'Content/Quest/Maps' / (name + '.umap')
        check('Quest map ' + name, path.exists(), path)
    check('Headset deployment and performance', False, 'Not tested; requires actual Quest 3 / 3S', blocker=False)
    blockers = [c['name'] for c in checks if c['blocker'] and not c['passed']]
    return {'prerequisites_ready': not blockers, 'apk_built': False, 'headset_tested': False,
            'project': str(project), 'engine': str(engine), 'engine_requirements': requirements,
            'portable_toolchain_manifest': str(portable_path) if portable_path.exists() else None,
            'checks': checks, 'blockers': blockers, 'devices': devices,
            'note': 'Missing Windows OpenXR ActiveRuntime does not block Quest APK packaging. Android payload and SDK are mandatory. No installs or build performed.'}, adb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', default='C:/Program Files/Epic Games/UE_5.8')
    parser.add_argument('--project', default=str(Path(__file__).resolve().parents[1] / 'YesterdayHarbor.uproject'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--devices', action='store_true')
    args = parser.parse_args()
    report, adb = inspect(args.engine, args.project)
    if args.devices and adb.exists():
        result = subprocess.run([str(adb), 'devices', '-l'], capture_output=True, text=True, timeout=20)
        report['devices'] = (result.stdout + result.stderr).splitlines()
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    print(rendered)
    return 0 if report['prerequisites_ready'] else 2


if __name__ == '__main__':
    sys.exit(main())
