import json
from pathlib import Path
path=Path(__file__).resolve().parent/'output'/'game'/'manifest.json'
data=json.loads(path.read_text())
route=data['route_waypoints_blender']
for i,point in enumerate(route):
    if point['name']=='Campanile approach':
        route[i]={'name':'Campanile approach','position':[.8,42,16.66]}
        route.insert(i,{'name':'Campanile clear lane','position':[.8,35,13.7]})
        break
data['validation']='Native Unreal collision/character validation is recorded in game_unreal/import_report.json and runtime_validation.json.'
path.write_text(json.dumps(data,indent=2),encoding='utf-8')
print('Final manifest:',len(data['assets']),'assets;',len(data['route_waypoints_blender']),'route waypoints')
