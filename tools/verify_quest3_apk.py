"""Verify an actual Quest 3 APK built from the Release copy without querying or deploying a device.

Usage (Blender's or the engine's python, -I):
  verify_quest3_apk.py --apk <path> --output <json> --configuration Shipping|Development
                       [--package com.yesterdayharbor.quest3] [--version-code 3] [--version-name 0.1.0-quest3]
Inspection only: signature scheme, package/label/SDK/ABI, OpenXR loader, embedded data, permissions,
manifest components. It never claims a device launch or headset result.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import subprocess
import zipfile

root = Path(__file__).resolve().parents[1]


def run(args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True, encoding='utf-8', errors='replace').stdout


def manifest_components(xmltree):
    """Read component names, ignoring metadata and intent-action name strings."""
    stack = []
    result = []
    component_tags = {'activity', 'activity-alias', 'service', 'receiver', 'provider'}
    for line in xmltree.splitlines():
        element = re.match(r'^(\s*)E:\s+([A-Za-z0-9_-]+)\b', line)
        if element:
            indent = len(element.group(1))
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, element.group(2)))
        elif stack and stack[-1][1] in component_tags:
            name = re.search(r'A:\s+(?:http://schemas.android.com/apk/res/android:|android:)name(?:\([^)]*\))?="([^"]+)"', line)
            if name:
                result.append(name.group(1))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--configuration', required=True, choices=['Shipping', 'Development'])
    parser.add_argument('--package', default='com.yesterdayharbor.quest3')
    parser.add_argument('--version-code', default='15')
    parser.add_argument('--version-name', default='0.3.0-competition')
    parser.add_argument('--label', default='The Other Side of Yesterday')
    args = parser.parse_args()
    toolchain = json.loads((root / 'tools/android_toolchain_manifest.json').read_text(encoding='utf-8-sig'))
    build_tools = Path(toolchain['sdk_root']) / 'build-tools/36.0.0'
    java = Path(toolchain['java_home']) / 'bin/java.exe'
    apk = args.apk.resolve()
    report = {'success': False, 'verified_utc': datetime.now(timezone.utc).isoformat(), 'apk': str(apk),
              'configuration': args.configuration + ' ARM64 Vulkan ASTC', 'headset_tested': False, 'checks': []}

    def check(label, ok, detail=None):
        report['checks'].append({'label': label, 'pass': bool(ok), 'detail': detail})
        if not ok:
            raise AssertionError(label + ('' if detail is None else ': ' + str(detail)))

    try:
        check('APK exists', apk.is_file(), str(apk))
        signature = run([java, '-jar', build_tools / 'lib/apksigner.jar', 'verify', '--verbose', '--print-certs', apk])
        badging = run([build_tools / 'aapt2.exe', 'dump', 'badging', apk])
        xml = run([build_tools / 'aapt2.exe', 'dump', 'xmltree', '--file', 'AndroidManifest.xml', apk])
        package = re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging)
        check('APK package metadata present', package is not None)
        label = re.search(r"application-label:'([^']+)'", badging)
        minimum = re.search(r"(?m)^(?:minSdkVersion|sdkVersion):'([^']+)'", badging)
        target = re.search(r"targetSdkVersion:'([^']+)'", badging)
        abi = re.search(r"native-code: (.+)", badging)
        permissions = re.findall(r"uses-permission: name='([^']+)'", badging)
        components = manifest_components(xml)
        check('Manifest components decoded', bool(components))
        check('Package, version code and version name', package.groups() == (args.package, args.version_code, args.version_name), package.groups())
        check('Application label', label is not None and label.group(1) == args.label, label.group(1) if label else None)
        check('minSdkVersion 32', minimum is not None and minimum.group(1) == '32', minimum.group(1) if minimum else None)
        check('targetSdkVersion 36', target is not None and target.group(1) == '36', target.group(1) if target else None)
        check('ARM64 only', abi is not None and abi.group(1).strip() == "'arm64-v8a'", abi.group(1) if abi else None)
        check('APK Signature Scheme v2 verified', 'Verified using v2 scheme (APK Signature Scheme v2): true' in signature)
        check('VR headtracking feature declared', 'android.hardware.vr.headtracking' in badging)
        check('No billing permission', 'com.android.vending.BILLING' not in permissions, permissions)
        afs = [name for name in components if name.startswith('com.epicgames.unreal.RemoteFileManager')]
        check('No Android File Server component', not afs, afs)
        with zipfile.ZipFile(apk) as archive:
            libraries = [i.filename for i in archive.infolist() if i.filename.startswith('lib/') and i.filename.endswith('.so')]
            embedded = [{'name': i.filename, 'bytes': i.file_size} for i in archive.infolist() if i.filename == 'assets/main.obb.png']
        check('libUnreal.so present', 'lib/arm64-v8a/libUnreal.so' in libraries, libraries)
        check('OpenXR loader present', 'lib/arm64-v8a/libopenxr_loader.so' in libraries, libraries)
        check('Game data embedded in the APK', len(embedded) == 1 and embedded[0]['bytes'] > 0, embedded)
        validation_layer = 'lib/arm64-v8a/libVkLayer_khronos_validation.so' in libraries
        if args.configuration == 'Shipping':
            check('Shipping APK carries no Vulkan validation layer', not validation_layer, libraries)
        cert = re.search(r'Signer #1 certificate SHA-256 digest: (\S+)', signature)
        subject = re.search(r'Signer #1 certificate DN: (.+)', signature)
        with apk.open('rb') as apk_file:
            apk_digest = hashlib.file_digest(apk_file, 'sha256').hexdigest()
        report.update({
            'sha256': apk_digest, 'bytes': apk.stat().st_size,
            'signature_verified': 'APK Signature Scheme v2',
            'signer_certificate_subject': subject.group(1).strip() if subject else None,
            'signer_certificate_sha256': cert.group(1) if cert else None,
            'package': package.group(1), 'version_code': int(package.group(2)), 'version_name': package.group(3),
            'application_label': label.group(1), 'min_sdk': int(minimum.group(1)), 'target_sdk': int(target.group(1)),
            'native_libraries': libraries, 'vulkan_validation_layer': validation_layer, 'embedded_data': embedded,
            'permissions': permissions, 'android_manifest_components': components,
            'supported_devices_meta': re.search(r"com\.oculus\.supportedDevices.*", xml) is not None,
        })
        report['success'] = True
    except Exception as exc:
        report['error'] = repr(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: report.get(k) for k in ['success', 'sha256', 'bytes', 'package', 'version_name', 'error']}, indent=2))
    raise SystemExit(0 if report['success'] else 1)


if __name__ == '__main__':
    main()
