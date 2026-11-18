"""Reads back vertex colours from imported Verdant meshes to check they survived import and LODs."""
import json
import sys
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc

result = {}
for name in ('SM_V_G_Plain_R', 'SM_V_Band_R', 'SM_V_Land_Near'):
    mesh = unreal.load_asset(vc.ROOT_PATH + '/Meshes/' + name)
    row = {'lods': mesh.get_num_lods()}
    try:
        desc = mesh.get_mesh_description(0)
        row['desc_methods'] = [m for m in dir(desc) if 'color' in m.lower() or 'colour' in m.lower()][:12]
        count = desc.get_vertex_instance_count()
        row['vertex_instances'] = count
        reds = []
        samples = []
        for i in range(0, count, max(1, count // 40)):
            vid = unreal.VertexInstanceID(i)
            try:
                c = desc.get_vertex_instance_color(vid)
                reds.append(c.r)
                if len(samples) < 6:
                    samples.append([round(c.r, 3), round(c.g, 3), round(c.b, 3), round(c.a, 3)])
            except Exception as problem:
                row['read_error'] = str(problem)[:200]
                break
        if reds:
            row['r_min'], row['r_max'], row['r_mean'] = round(min(reds), 3), round(max(reds), 3), round(sum(reds) / len(reds), 3)
            row['samples'] = samples
    except Exception as problem:
        row['error'] = str(problem)[:300]
    result[name] = row
vc.write_json(vc.EVIDENCE / 'colour_probe.json', result)
vc.log('colour probe', json.dumps(result)[:1500])
unreal.SystemLibrary.quit_editor()
