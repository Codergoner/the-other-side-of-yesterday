"""Install the user-authorized portable Quest Android build dependencies.

Official Google sdkmanager + Eclipse Temurin OpenJDK 21 ZIP only. No Android
Studio, registry writes, permanent environment changes, Unreal launch or APK
packaging. Re-running resumes verified archives and installed SDK packages.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import traceback
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

WORKSPACE = Path(__file__).resolve().parents[1]
# AppData/Local is redirected into the Codex MSIX package cache, adding enough
# path depth to exceed Windows limits in Google's own archive. This plain
# user-owned, unsynced directory keeps the native Android tools on a short path.
INSTALL = Path.home() / 'TOSOYQuestToolchain'
LEGACY_CACHE = Path.home() / 'AppData/Local/TOSOYQuestToolchain/downloads'
SDK = INSTALL / 'sdk'
DOWNLOADS = INSTALL / 'downloads'
JDK_DIR = INSTALL / 'jdk'
MANIFEST = WORKSPACE / 'tools/android_toolchain_manifest.json'
STATUS = WORKSPACE / 'tools/android_toolchain_status.json'
ENGINE_JSON = Path('C:/Program Files/Epic Games/UE_5.8/Engine/Config/Android/Android_SDK.json')
GOOGLE_URL = 'https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip'
GOOGLE_SHA256 = '90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a'
ADOPTIUM_API = 'https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse'
REPORT = {'success': False, 'install_root': str(INSTALL), 'sdk_root': str(SDK),
          'no_global_environment_or_registry_changes': True, 'unreal_launched': False, 'apk_built': False,
          'sources': ['https://developer.android.com/studio', 'https://developer.android.com/tools/sdkmanager',
                      'https://adoptium.net/temurin/releases/?version=21&os=windows&arch=x64',
                      'https://github.com/adoptium/api.adoptium.net/blob/main/docs/cookbook.adoc'],
          'downloads': [], 'commands': []}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def update(phase, **details):
    STATUS.write_text(json.dumps({'phase': phase, 'utc': now(), **details}, indent=2), encoding='utf-8')
    print(phase, json.dumps(details), flush=True)


def write():
    MANIFEST.write_text(json.dumps(REPORT, indent=2), encoding='utf-8')


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'TOSOYQuestToolchain/1.0'}), timeout=90)


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def download(url, name, expected):
    target = DOWNLOADS / name
    old = LEGACY_CACHE / name
    if not target.exists() and old.exists() and sha256(old) == expected:
        shutil.copy2(old, target)
    if not target.exists() or sha256(target) != expected:
        partial = target.with_suffix(target.suffix + '.partial')
        with request(url) as response, partial.open('wb') as destination:
            shutil.copyfileobj(response, destination, 4 * 1024 * 1024)
        actual = sha256(partial)
        if actual != expected:
            raise RuntimeError('Checksum mismatch for ' + name + ': ' + actual)
        # A single verified archive replacement, never a directory move/delete.
        partial.replace(target)
    return {'url': url, 'archive': str(target), 'sha256': sha256(target), 'bytes': target.stat().st_size,
            'publisher_checksum': expected, 'verified_utc': now()}


def extract(archive, destination, strip_prefix=''):
    base = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            relative = member.filename
            if strip_prefix:
                if not relative.startswith(strip_prefix):
                    raise RuntimeError('Unexpected archive root: ' + relative)
                relative = relative[len(strip_prefix):]
            if not relative:
                continue
            target = (base / relative).resolve()
            if not target.is_relative_to(base):
                raise RuntimeError('Archive traversal refused: ' + member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)


def command(args, name, env, stdin=None):
    if str(args[0]).lower().endswith(('.bat', '.cmd')):
        args = [os.environ.get('COMSPEC', 'C:/Windows/System32/cmd.exe'), '/d', '/c', *args]
    log = INSTALL / (name + '.log')
    started = now()
    with log.open('w', encoding='utf-8', errors='replace') as output:
        result = subprocess.run(args, input=stdin, text=True, stdout=output, stderr=subprocess.STDOUT,
                                env=env, cwd=INSTALL, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    REPORT['commands'].append({'arguments': [str(a) for a in args], 'started_utc': started,
                               'finished_utc': now(), 'exit_code': result.returncode, 'log': str(log)})
    write()
    if result.returncode:
        raise RuntimeError(name + ' failed with exit ' + str(result.returncode) + '; inspect ' + str(log))
    return log.read_text(encoding='utf-8', errors='replace')


def folder_bytes(folder):
    return sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())


def package_provenance(packages):
    url = 'https://dl.google.com/android/repository/repository2-3.xml'
    target = INSTALL / 'google_repository2-3.xml'
    with request(url) as response:
        target.write_bytes(response.read())
    records = []
    for node in ET.parse(target).getroot():
        package = node.get('path')
        if package not in packages:
            continue
        archives = []
        for archive in node.iter():
            if archive.tag.rsplit('}', 1)[-1] != 'archive':
                continue
            fields = {x.tag.rsplit('}', 1)[-1]: x for x in archive}
            host = fields.get('host-os')
            if host is not None and host.text != 'windows':
                continue
            complete = fields.get('complete')
            if complete is None:
                continue
            values = {x.tag.rsplit('}', 1)[-1]: x for x in complete}
            checksum = values.get('checksum')
            archives.append({'url': 'https://dl.google.com/android/repository/' + values['url'].text,
                             'bytes': int(values['size'].text), 'checksum': checksum.text if checksum is not None else None,
                             'checksum_type': checksum.get('type') if checksum is not None else None})
        records.append({'package': package, 'official_archives': archives})
    return {'repository': url, 'local_copy': str(target), 'sha256': sha256(target), 'packages': records}


def main():
    for folder in [INSTALL, SDK, DOWNLOADS, JDK_DIR, INSTALL / 'temp', INSTALL / 'android-user', INSTALL / 'gradle']:
        folder.mkdir(parents=True, exist_ok=True)
    requirements = json.loads(ENGINE_JSON.read_text(encoding='utf-8'))
    REPORT.update(started_utc=now(), engine_requirements=requirements, free_bytes_before=shutil.disk_usage(INSTALL).free)
    write()
    update('Querying official JDK 21 distribution')
    with request(ADOPTIUM_API) as response:
        java_release = json.load(response)[0]
    (INSTALL / 'adoptium_release.json').write_text(json.dumps(java_release, indent=2), encoding='utf-8')
    package = java_release['binary']['package']
    REPORT['jdk_release'] = {'api': ADOPTIUM_API, 'release': java_release['release_name'], 'version': java_release['version']}
    update('Downloading and verifying portable CLI/JDK archives')
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(download, GOOGLE_URL, GOOGLE_URL.rsplit('/', 1)[-1], GOOGLE_SHA256),
                 pool.submit(download, package['link'], package['name'], package['checksum'])]
        REPORT['downloads'] = [task.result() for task in tasks]
    write()
    update('Extracting verified archives')
    cli = SDK / 'cmdline-tools/latest'
    # A complete extraction marker avoids treating a partially unpacked CLI as
    # an installed toolchain when retrying after a filesystem interruption.
    if not (cli / '.extracted-verified').exists():
        extract(REPORT['downloads'][0]['archive'], cli, strip_prefix='cmdline-tools/')
        (cli / '.extracted-verified').write_text(GOOGLE_SHA256, encoding='ascii')
    with zipfile.ZipFile(REPORT['downloads'][1]['archive']) as jdk_archive:
        jdk_roots = {member.filename.split('/', 1)[0] for member in jdk_archive.infolist() if member.filename}
    if len(jdk_roots) != 1:
        raise RuntimeError('Expected one JDK archive root: ' + str(jdk_roots))
    java = JDK_DIR / next(iter(jdk_roots))
    if not (java / 'bin/javac.exe').exists():
        extract(REPORT['downloads'][1]['archive'], JDK_DIR)
    env = os.environ.copy()
    env.update(JAVA_HOME=str(java), ANDROID_HOME=str(SDK), ANDROID_SDK_ROOT=str(SDK),
               NDKROOT=str(SDK / 'ndk' / requirements['ndk']), NDK_ROOT=str(SDK / 'ndk' / requirements['ndk']),
               ANDROID_USER_HOME=str(INSTALL / 'android-user'), GRADLE_USER_HOME=str(INSTALL / 'gradle'),
               TEMP=str(INSTALL / 'temp'), TMP=str(INSTALL / 'temp'))
    env['PATH'] = str(java / 'bin') + os.pathsep + str(SDK / 'platform-tools') + os.pathsep + env.get('PATH', '')
    manager = str(cli / 'bin/sdkmanager.bat')
    REPORT.update(java_home=str(java), ndk_root=env['NDKROOT'], gradle_user_home=env['GRADLE_USER_HOME'])
    cli_properties = cli / 'source.properties'
    REPORT['command_line_tools'] = {'directory': str(cli), 'source_properties': cli_properties.read_text(encoding='utf-8'),
                                     'source_properties_sha256': sha256(cli_properties)}
    REPORT['java_version'] = command([str(java / 'bin/java.exe'), '-version'], 'java_version', env)
    REPORT['javac_version'] = command([str(java / 'bin/javac.exe'), '-version'], 'javac_version', env)
    write()
    update('Accepting ordinary SDK dependency licenses in isolated SDK root')
    REPORT['license_acceptance'] = {'authorization': 'User approved Android dependency setup for local Quest APK build',
                                    'scope': 'Official sdkmanager --licenses only', 'utc': now()}
    command([manager, '--sdk_root=' + str(SDK), '--licenses'], 'sdk_licenses', env, stdin='y\n' * 100)
    packages = ['platforms;' + requirements['platforms'], 'build-tools;' + requirements['build-tools'],
                'ndk;' + requirements['ndk'], 'cmake;' + requirements['cmake'], 'platform-tools']
    update('Installing exact installed-engine SDK packages', packages=packages)
    command([manager, '--sdk_root=' + str(SDK), '--channel=0', '--install', *packages],
            'sdk_install', env, stdin='y\n' * 100)
    REPORT['installed_packages_output'] = command([manager, '--sdk_root=' + str(SDK), '--list_installed'],
                                                  'sdk_installed', env)
    REPORT['adb_version'] = command([str(SDK / 'platform-tools/adb.exe'), 'version'], 'adb_version', env)
    clang = SDK / 'ndk' / requirements['ndk'] / 'toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe'
    REPORT['clang_version'] = command([str(clang), '--version'], 'clang_version', env)
    cmake = SDK / 'cmake' / requirements['cmake'] / 'bin/cmake.exe'
    REPORT['cmake_version'] = command([str(cmake), '--version'], 'cmake_version', env)
    REPORT['package_provenance'] = package_provenance(packages)
    REPORT['installed_packages'] = []
    for path in SDK.rglob('package.xml'):
        parent = path.parent
        properties = parent / 'source.properties'
        REPORT['installed_packages'].append({'directory': str(parent), 'package_xml_sha256': sha256(path),
                                             'source_properties': properties.read_text(encoding='utf-8') if properties.exists() else None,
                                             'bytes': folder_bytes(parent)})
    REPORT['licenses'] = [{'file': str(p), 'sha256': sha256(p)} for p in (SDK / 'licenses').glob('*') if p.is_file()]
    REPORT['disk_bytes'] = {'total': folder_bytes(INSTALL), 'sdk': folder_bytes(SDK),
                            'jdk': folder_bytes(JDK_DIR), 'archives': folder_bytes(DOWNLOADS)}
    REPORT.update(success=True, completed_utc=now(), free_bytes_after=shutil.disk_usage(INSTALL).free)
    write()
    update('Portable Android toolchain installed', java_home=str(java), sdk_root=str(SDK), disk_bytes=REPORT['disk_bytes'])


if __name__ == '__main__':
    try:
        main()
    except Exception:
        REPORT['error'] = traceback.format_exc()
        write()
        update('Failed', error=REPORT['error'])
        raise
