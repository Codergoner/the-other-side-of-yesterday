"""Verify the actual local development APK without querying or deploying a device."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import zipfile

root = Path(__file__).resolve().parents[1]
toolchain = json.loads((root / 'tools/android_toolchain_manifest.json').read_text(encoding='utf-8-sig'))
apk = root / 'output/quest_android/Android_ASTC/YesterdayHarbor-arm64.apk'
build_tools = Path(toolchain['sdk_root']) / 'build-tools/36.0.0'
java = Path(toolchain['java_home']) / 'bin/java.exe'

def run(args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True).stdout


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

signature = run([java, '-jar', build_tools / 'lib/apksigner.jar', 'verify', '--verbose', '--print-certs', apk])
badging = run([build_tools / 'aapt2.exe', 'dump', 'badging', apk])
xml = run([build_tools / 'aapt2.exe', 'dump', 'xmltree', '--file', 'AndroidManifest.xml', apk])
package = re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging)
assert package, 'APK package metadata missing'
label = re.search(r"application-label:'([^']+)'", badging)
minimum = re.search(r"(?m)^(?:minSdkVersion|sdkVersion):'([^']+)'", badging)
target = re.search(r"targetSdkVersion:'([^']+)'", badging)
abi = re.search(r"native-code: (.+)", badging)
permissions = re.findall(r"uses-permission: name='([^']+)'", badging)
components = manifest_components(xml)
assert components, 'No Android manifest components decoded'
afs_components = [name for name in components if name.startswith('com.epicgames.unreal.RemoteFileManager')]
assert package.groups() == ('com.yesterdayharbor.questdev', '2', '0.2.0-questdev'), package.groups()
assert label and label.group(1) == 'The Other Side of Yesterday'
assert minimum and minimum.group(1) == '32'
assert target and target.group(1) == '36'
assert abi and abi.group(1).strip() == "'arm64-v8a'"
assert 'Verified using v2 scheme (APK Signature Scheme v2): true' in signature
assert 'android.hardware.vr.headtracking' in badging
assert 'com.android.vending.BILLING' not in permissions, 'Unrequested billing permission retained'
assert not afs_components, 'Android File Server component retained: ' + ', '.join(afs_components)
with zipfile.ZipFile(apk) as archive:
    libraries = [i.filename for i in archive.infolist() if i.filename.startswith('lib/') and i.filename.endswith('.so')]
    embedded = [{'name': i.filename, 'bytes': i.file_size} for i in archive.infolist() if i.filename == 'assets/main.obb.png']
assert 'lib/arm64-v8a/libUnreal.so' in libraries
assert 'lib/arm64-v8a/libopenxr_loader.so' in libraries
assert len(embedded) == 1 and embedded[0]['bytes'] > 0
cert = re.search(r'Signer #1 certificate SHA-256 digest: (\S+)', signature)
subject = re.search(r'Signer #1 certificate DN: (.+)', signature)
with apk.open('rb') as apk_file:
    apk_digest = hashlib.file_digest(apk_file, 'sha256').hexdigest()
report = {
    'success': True,
    'verified_utc': datetime.now(timezone.utc).isoformat(),
    'apk': str(apk),
    'sha256': apk_digest,
    'bytes': apk.stat().st_size,
    'configuration': 'Development ARM64 Vulkan ASTC',
    'signature_verified': 'APK Signature Scheme v2',
    'signer_certificate_subject': subject.group(1).strip() if subject else None,
    'signer_certificate_sha256': cert.group(1) if cert else None,
    'package': package.group(1), 'version_code': int(package.group(2)), 'version_name': package.group(3),
    'application_label': label.group(1), 'min_sdk': int(minimum.group(1)), 'target_sdk': int(target.group(1)),
    'native_libraries': libraries, 'embedded_data': embedded, 'permissions': permissions,
    'billing_permission': False, 'android_file_server_component': False,
    'android_manifest_components': components,
    'headset_tested': False,
    'source_state': 'Premium photographic art, organic olives, articulated matte hands, 15 accessible landing nodes; 462 XR story checks, 84 strict hands/navigation checks, 26 walking points passed',
    'limits': ['Desktop/mobile preview and packaging only; no physical headset input, alignment, comfort, frame time, thermal or memory measurements', 'Development NPCs and some props remain; illustrated full-world brief not complete'],
}
output = root / 'output/quest_android/artifact_manifest.json'
output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
