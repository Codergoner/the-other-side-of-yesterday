"""Compile the private process-only recorder with the approved installed tools.

Uses absolute cl/link paths and explicit include/library paths; does not change
PATH, install/restore packages, configure Windows, or activate any audio stream.
Only --version/--capabilities queries run after a successful native build.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'output/capture_tools/application_loopback'
COMMIT = '0b4e48a88ba446f3d87c5f7df12b33a74899a1e1'


def require(test, message):
    if not test:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    require(os.name == 'nt', 'Approved native Windows build only')
    approved_path = ROOT / 'output/toolchain_staging/installation_verified.json'
    approved = json.loads(approved_path.read_text(encoding='utf-8-sig'))
    require(approved['success'], 'Installed approved compiler verification required')
    compiler = Path(approved['compiler_path'])
    linker = compiler.with_name('link.exe')
    vc = compiler.parents[3]
    sdk = Path('C:/Program Files (x86)/Windows Kits/10')
    version = approved['sdk_version']
    includes = [vc / 'include'] + [sdk / 'Include' / version / x for x in ['ucrt', 'shared', 'um', 'winrt']]
    libraries = [vc / 'lib/x64'] + [sdk / 'Lib' / version / x / 'x64' for x in ['um', 'ucrt']]
    require(compiler.is_file() and linker.is_file() and all(p.is_dir() for p in includes + libraries), 'Approved absolute compiler/SDK paths are missing')
    upstream = DEST / 'upstream'
    license_text = (upstream / 'LICENSE').read_text()
    require('The MIT License (MIT)' in license_text and 'Microsoft Corporation' in license_text, 'Official sample license must be preserved/read before building')
    source = DEST / 'GameProcessAudio.cpp'
    build = DEST / 'build'
    build.mkdir(exist_ok=True)
    obj, exe = build / 'GameProcessAudio.obj', build / 'GameProcessAudio.exe'
    compile_cmd = [str(compiler), '/nologo', '/std:c++17', '/O2', '/W4', '/EHsc', '/MT', '/DUNICODE', '/D_UNICODE',
                   '/c', str(source), '/Fo' + str(obj), *['/I' + str(p) for p in includes]]
    link_cmd = [str(linker), '/nologo', '/MACHINE:X64', '/SUBSYSTEM:CONSOLE', '/OPT:REF', '/OPT:ICF', '/OUT:' + str(exe),
                str(obj), *['/LIBPATH:' + str(p) for p in libraries], 'kernel32.lib', 'user32.lib', 'ole32.lib', 'mmdevapi.lib', 'uuid.lib']
    commands = []
    for label, command in [('compile', compile_cmd), ('link', link_cmd)]:
        result = subprocess.run(command, capture_output=True, text=True, cwd=build, timeout=120,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        path = build / (label + '.log')
        path.write_text(result.stdout + result.stderr)
        commands.append({'id': label, 'command': command, 'returncode': result.returncode, 'log': str(path), 'log_sha256': sha(path)})
        require(result.returncode == 0, 'Native ' + label + ' failed; inspect ' + str(path))
    queried = []
    for option in ['--version', '--capabilities']:
        result = subprocess.run([str(exe), option], capture_output=True, text=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        file = build / (option[2:] + '.json')
        file.write_text(result.stdout)
        require(result.returncode == 0, 'Safe capability query failed: ' + result.stderr)
        data = json.loads(result.stdout)
        require(data['capture_started'] is False and data['desktop_mix'] is False and data['microphone'] is False,
                'Capability query must not activate or capture audio')
        require(data['mode'] == 'INCLUDE_TARGET_PROCESS_TREE_ONLY', 'Recorder isolation policy differs')
        queried.append({'option': option, 'returncode': result.returncode, 'path': str(file), 'sha256': sha(file), 'actual': data})
    files = []
    for file in sorted(upstream.iterdir()):
        relative = 'LICENSE' if file.name == 'LICENSE' else ('Samples/ApplicationLoopback/README.md' if file.name == 'README.md' else 'Samples/ApplicationLoopback/cpp/' + file.name)
        files.append({'path': str(file), 'bytes': file.stat().st_size, 'sha256': sha(file),
                      'url': 'https://raw.githubusercontent.com/microsoft/Windows-classic-samples/' + COMMIT + '/' + relative})
    manifest = {'success': True, 'built_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Native compilation and non-capturing capability queries only. WASAPI activation, actual game-audio capture and output-format validation await a bound game PID.',
        'upstream_project': 'https://github.com/microsoft/Windows-classic-samples/tree/' + COMMIT + '/Samples/ApplicationLoopback',
        'official_documentation': 'https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/',
        'upstream_commit': COMMIT, 'upstream_files': files,
        'license': 'MIT, Microsoft copyright and permission text preserved in upstream/LICENSE; no font assets or other sample content used',
        'license_path': str(upstream / 'LICENSE'), 'license_sha256': sha(upstream / 'LICENSE'),
        'derivative_source': str(source), 'derivative_sha256': sha(source), 'builder_sha256': sha(__file__),
        'executable': str(exe), 'executable_sha256': sha(exe), 'compiler': str(compiler), 'compiler_sha256': sha(compiler),
        'linker': str(linker), 'sdk_version': version, 'approved_toolchain_manifest_sha256': sha(approved_path),
        'commands': commands, 'capability_queries': queried, 'actual_capture_run': False,
        'requested_format': {'rate': 48000, 'channels': 2, 'bits': 16, 'encoding': 'PCM'}, 'actual_capture_format_validated': False,
        'isolation': 'Explicit observed HWND/PID/title/executable binding, fixed INCLUDE_TARGET_PROCESS_TREE only; no exclude, endpoint/system loopback or microphone mode exists',
        'permission_status': 'Activation not attempted; any activation/access-denied HRESULT will fail without fallback. No UI permission bypass or settings changes.',
        'dependencies': 'Installed Windows SDK/WRL and statically linked MSVC CRT only; no WIL/NuGet restore, driver or additional install',
        'PATH_modified': False, 'Windows_settings_modified': False, 'input_automation': False}
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'success': True, 'executable': str(exe), 'sha256': sha(exe), 'capture_run': False,
                      'manifest': str(DEST / 'manifest.json')}, indent=2))


if __name__ == '__main__':
    main()
