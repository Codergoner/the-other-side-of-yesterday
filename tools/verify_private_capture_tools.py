"""Verify/extract approved pinned FFmpeg privately, then query capabilities only.

No PATH changes, installation, device opening, screen/audio recording or encode.
Archive's license/README are inspected and preserved before any executable runs.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'output/capture_tools'
ZIP = DEST / 'archives/ffmpeg-9.0.2-essentials_build.zip'
EXPECTED_SHA = '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
EXPECTED_BYTES = 114768076
PREFIX = 'ffmpeg-9.0.2-essentials_build'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    require(os.name == 'nt', 'This approved archive contains Windows binaries')
    require(ZIP.stat().st_size == EXPECTED_BYTES, 'Pinned archive size differs; download may still be incomplete')
    actual = sha(ZIP)
    require(actual == EXPECTED_SHA, 'Pinned published SHA256 mismatch')
    published = ZIP.with_name(ZIP.name + '.sha256.published.txt')
    require(EXPECTED_SHA in published.read_text(), 'Pinned official checksum evidence missing')
    with zipfile.ZipFile(ZIP) as archive:
        for member in archive.infolist():
            path = Path(member.filename)
            require(not path.is_absolute() and '..' not in path.parts and path.parts[0] == PREFIX, 'Unsafe/unexpected archive member')
            require(not stat.S_ISLNK(member.external_attr >> 16), 'Symbolic-link archive member rejected')
        licenses = [n for n in archive.namelist() if Path(n).name.lower() in ['license', 'license.txt', 'copying', 'copying.txt']]
        readmes = [n for n in archive.namelist() if Path(n).name.lower().startswith('readme')]
        require(licenses and readmes, 'Included license and build README required before execution')
        license_text = '\n'.join(archive.read(n).decode('utf-8', errors='replace') for n in licenses)
        require('GNU GENERAL PUBLIC LICENSE' in license_text and 'Version 3' in license_text, 'Expected GPLv3 included license missing')
        archive.extractall(DEST)
    executable_paths = {name: DEST / PREFIX / 'bin' / (name + '.exe') for name in ['ffmpeg', 'ffprobe', 'ffplay']}
    require(all(p.is_file() for p in executable_paths.values()), 'Expected private executables missing')
    logs = DEST / 'capability'
    logs.mkdir(exist_ok=True)
    jobs = [('version', 'ffmpeg', ['-version']), ('devices', 'ffmpeg', ['-devices']),
            ('encoders', 'ffmpeg', ['-encoders']), ('gdigrab_help', 'ffmpeg', ['-h', 'demuxer=gdigrab']),
            ('license', 'ffmpeg', ['-L']), ('ffprobe_version', 'ffprobe', ['-version'])]
    queried, outputs = [], {}
    for label, executable, arguments in jobs:
        command = [str(executable_paths[executable]), '-hide_banner', *arguments]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        text = result.stdout + result.stderr
        file = logs / (label + '.txt')
        file.write_text(text, encoding='utf-8')
        queried.append({'id': label, 'command': command, 'returncode': result.returncode,
                        'path': str(file), 'sha256': sha(file)})
        require(result.returncode == 0, 'Capability-only CLI failed: ' + label)
        outputs[label] = text
    require(re.search(r'ffmpeg version 9\.0\.2(?:-|\s)', outputs['version']), 'Actual FFmpeg version differs')
    capabilities = {'gdigrab': bool(re.search(r'\bD\s+gdigrab\b', outputs['devices'])),
        'dshow_compiled': bool(re.search(r'\bD\s+dshow\b', outputs['devices'])),
        'ffv1_encoder': bool(re.search(r'\bffv1\s', outputs['encoders'])),
        'libx264_encoder': bool(re.search(r'\blibx264\s', outputs['encoders'])),
        'aac_encoder': bool(re.search(r'\baac\s', outputs['encoders']))}
    require(all(capabilities.values()), 'Expected compiled recording/encoding capability missing')
    manifest = {'success': True, 'verified_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Private portable recorder staging and capability queries only; no actual capture or encoding',
        'provider_page': 'https://www.gyan.dev/ffmpeg/builds/',
        'official_provider_link_page': 'https://ffmpeg.org/download.html',
        'archive_url': 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip',
        'published_checksum_url': 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip.sha256',
        'source_url': 'https://github.com/FFmpeg/FFmpeg/commit/946fcce07b',
        'source_url_evidence': 'Gyan release 9.0.2 source-code link on official provider page',
        'archive_path': str(ZIP), 'archive_bytes': ZIP.stat().st_size,
        'published_sha256': EXPECTED_SHA, 'actual_sha256': actual,
        'license': 'GNU GPL version 3, included license preserved; private tool, not bundled in the game',
        'included_licenses': [{'path': str(DEST / p), 'sha256': sha(DEST / p)} for p in licenses],
        'included_readmes': [{'path': str(DEST / p), 'sha256': sha(DEST / p)} for p in readmes],
        'executables': {n: {'path': str(p), 'sha256': sha(p)} for n, p in executable_paths.items()},
        'actual_version': outputs['version'].splitlines()[0], 'capabilities': capabilities,
        'queries': queried, 'screen_audio_capture_run': False, 'encoder_run': False,
        'PATH_modified': False, 'installed': False, 'drivers_installed': False}
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ['success', 'actual_sha256', 'actual_version', 'capabilities']}, indent=2))


if __name__ == '__main__':
    main()
