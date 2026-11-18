"""Read and stage installed Epic XR template assets outside project Content.

No Unreal process, asset import, package rewrite or live Content mutation.
Raw package mounts are recorded because moving .uasset files to a different
mount without Unreal migration would break their serialized references.
"""
from pathlib import Path
import datetime
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('C:/Program Files/Epic Games/UE_5.8/Templates/TemplateResources/Standard/XRMannequins/Content')
STAGE = ROOT / 'output/staging/xr_hands/OriginalMount_XRMannequins'
MANIFEST = ROOT / 'output/staging/xr_hands/manifest.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def names(path):
    values = {s.decode('ascii') for s in re.findall(rb'[\x20-\x7e]{4,}', path.read_bytes())}
    return {'package_paths': sorted(s for s in values if s.startswith(('/Game/', '/Engine/', '/Script/'))),
            'animation_names': sorted(s for s in values if any(k in s.lower() for k in
                                      ['grasp', 'trigger', 'grip', 'thumb', 'indexcurl', 'mirror', 'righthand', 'lefthand', 'blendspace']))}


def main():
    records = []
    STAGE.mkdir(parents=True, exist_ok=True)
    assert STAGE.resolve().is_relative_to((ROOT / 'output/staging').resolve())
    for source in sorted(SOURCE.rglob('*')):
        if not source.is_file():
            continue
        relative = source.relative_to(SOURCE)
        destination = STAGE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected = digest(source)
        if not destination.exists() or digest(destination) != expected:
            shutil.copy2(source, destination)
        record = {'relative': relative.as_posix(), 'source': str(source), 'staged': str(destination),
                  'bytes': source.stat().st_size, 'sha256': expected,
                  'original_package': '/Game/XRMannequins/' + relative.with_suffix('').as_posix()}
        if source.suffix == '.uasset':
            record.update(names(source))
        records.append(record)
    report = {'success': True, 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source': str(SOURCE), 'staging': str(STAGE), 'original_mount': '/Game/XRMannequins',
              'live_content_written': False, 'unreal_launched': False, 'files': records,
              'file_count': len(records), 'bytes': sum(r['bytes'] for r in records),
              'provenance': 'Epic Games UE 5.8 installed Standard/XRMannequins template content; existing Unreal license applies. No new external hand asset or third-party license is asserted.',
              'intended_runtime': ['Meshes/SKM_QuinnXR_left.uasset', 'Meshes/SKM_QuinnXR_right.uasset',
                                   'Meshes/SK_MannequinsXR.uasset', 'Animations/MDT_MannequinsXR.uasset',
                                   'Animations/A_MannequinsXR_Idle_Right.uasset',
                                   'Animations/A_MannequinsXR_Grasp_Right.uasset',
                                   'Animations/A_MannequinsXR_IndexCurl_Right.uasset',
                                   'Animations/A_MannequinsXR_Point_Right.uasset'],
              'pending_native_inspection': ['Exact grip-relative mesh transforms from template SCS',
                                            'Skeleton bone/reference-pose compatibility and left mirroring',
                                            'LOD vertex/triangle counts and bounds',
                                            'AnimSequence key counts, duration, additive flags and static pose meaning',
                                            'BlendSpace factory/sample-data editing and native triangulation validation']}
    MANIFEST.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'success': True, 'files': report['file_count'], 'bytes': report['bytes'],
                      'manifest': str(MANIFEST), 'live_content_written': False}))


if __name__ == '__main__':
    main()
