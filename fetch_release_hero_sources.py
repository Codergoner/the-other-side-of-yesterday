"""Stage selected official CC0 PBR maps; no Unreal/Blender/plugin operation.

Powered by Poly Haven. Downloads only reviewed asset maps through its public
API; API example renders/gallery imagery are not used as redistributable art.
"""
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlparse
import hashlib
import json
from PIL import Image

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/release_hero_sources'
UA = 'YesterdayHarborReleaseArt/1.0 (Powered by Poly Haven)'
ASSETS = {'stone_tiles_02': 'room_floor', 'cobblestone_floor_02': 'street_floor', 'rough_linen': 'woven_panel'}


def get(url):
    assert urlparse(url).hostname in ['api.polyhaven.com', 'dl.polyhaven.org', 'polyhaven.com', 'raw.githubusercontent.com', 'creativecommons.org']
    with urlopen(Request(url, headers={'User-Agent': UA}), timeout=45) as response:
        data = response.read(40 * 1024 * 1024 + 1)
        assert len(data) <= 40 * 1024 * 1024 and response.status == 200
        assert urlparse(response.url).scheme == 'https'
        return data, {'requested_url': url, 'final_url': response.url, 'http_status': response.status,
                      'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def build():
    assert ROOT.name == 'Release_20261026', 'Stage only in the release copy'
    (OUT / 'metadata').mkdir(parents=True, exist_ok=True)
    catalog_path = OUT / 'metadata/polyhaven_texture_catalog.json'
    if not catalog_path.exists():
        catalog_path.write_bytes(get('https://api.polyhaven.com/assets?t=textures')[0])
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    license_data, license_evidence = get('https://polyhaven.com/license')
    assert b'CC0' in license_data and b'commercial' in license_data
    _, api_evidence = get('https://raw.githubusercontent.com/Poly-Haven/Public-API/master/ToS.md')
    _, cc0_evidence = get('https://creativecommons.org/publicdomain/zero/1.0/legalcode.en')
    entries = []
    for asset, role in ASSETS.items():
        metadata_path = OUT / 'metadata' / (asset + '_files.json')
        if not metadata_path.exists():
            metadata_path.write_bytes(get('https://api.polyhaven.com/files/' + asset)[0])
        versions = json.loads(metadata_path.read_text(encoding='utf-8'))
        maps = []
        for channel, kind in [('Diffuse', 'base_color'), ('nor_dx', 'normal_directx'), ('Rough', 'roughness')]:
            selected = versions[channel]['2k']['png']
            url = selected['url']
            path = OUT / 'textures' / asset / Path(urlparse(url).path).name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                data, download = get(url)
                path.write_bytes(data)
            else:
                data = path.read_bytes()
                download = {'requested_url': url, 'final_url': url, 'http_status': 200,
                            'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'cache_reused': True}
            assert len(data) == selected['size'] and hashlib.md5(data).hexdigest() == selected['md5']
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                size, mode = list(image.size), image.mode
            # Scanned cloth is2048x2052 in the provider's2k set. Keep the exact
            # source bytes; native texture build can resample to2048 square.
            assert min(size) == 2048 and max(size) <= 2064
            maps.append({'kind': kind, 'file': str(path.relative_to(OUT)).replace('\\', '/'),
                         'provider_md5': selected['md5'], 'provider_size': selected['size'],
                         'dimensions_px': size, 'mode': mode, **download})
            print(asset, kind, len(data), 'bytes', flush=True)
        entries.append({'id': asset, 'role': role, 'page': 'https://polyhaven.com/a/' + asset,
                        'name': catalog[asset]['name'], 'authors': catalog[asset]['authors'],
                        'provider_dimensions_raw': catalog[asset].get('dimensions'), 'license': 'CC0 1.0',
                        'file_metadata_sha256': hashlib.sha256(metadata_path.read_bytes()).hexdigest(), 'maps': maps})
    manifest = {'schema': 1, 'success': True, 'provider': 'Poly Haven', 'credit': 'Powered by Poly Haven',
                'license': {'name': 'CC0 1.0 Universal', 'official_policy': license_evidence,
                            'legal_code': cc0_evidence, 'api_terms': api_evidence,
                            'summary': 'The official provider license permits commercial use and redistribution of its CC0 assets. Live API calls identify this authoring tool; no runtime API service or third-party gallery art is included.'},
                'assets': entries, 'source_count': 3, 'map_count': 9,
                'verified_utc': datetime.now(timezone.utc).isoformat(),
                'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'native_imported': False, 'native_visual_reviewed': False}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Staged9 original CC0 provider maps, no native imports.', flush=True)
    return manifest


if __name__ == '__main__':
    build()
