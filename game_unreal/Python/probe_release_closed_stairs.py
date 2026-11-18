"""Actual fresh-game capsule walking/jump/crouch closure and exit/return probe.

Reuse the proved menu/movement lifecycle, replacing only the finite route and
expected blocked trials. Scripted AddMovementInput is QA, never S07 footage.
"""
from pathlib import Path
import json,sys,hashlib
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import release_file_io as io

source=(ROOT/'Python/probe_release_upstairs_walk.py').read_text()
source=source.replace('release_upstairs_probe_plan.json','release_upstairs_closed_probe_plan.json').replace('release_upstairs_walk_probe.json','release_upstairs_closed_walk.json').replace('validation/release_upstairs_walk','validation/release_upstairs_closed_walk').replace("PROFILE = 'YRU_'","PROFILE = 'YRC_'")
source=source.replace("'closure_authored': False","'closure_authored': True")
source=source.replace("'route_teleports': 0","'route_teleports': 0, 'trial_input': 'Actual Character Jump/Crouch and AddMovementInput(force=False); no pose/capsule/position setters'")
source=source.replace('def walk(game_time):','def walk_reachable(game_time):')
source=source.replace("location.z - S['half_height']","location.z - float(S['pawn'].get_component_by_class(unreal.CapsuleComponent).get_scaled_capsule_half_height())")
needle='def inspect_stairs(world):'
trial='''def walk(game_time):
    waypoint=ROUTE[S['index']]
    if not waypoint.get('trial'):
        return walk_reachable(game_time)
    if int(prop('Mode'))!=0 or prop('ReleaseMenuActive') or S['pc'].is_move_input_ignored():
        raise RuntimeError('Native mode/input gate blocks the actual trial')
    foot=footpoint();target=waypoint['floor_cm'];elapsed=game_time-S['segment_game']
    if S.get('trial_index')!=S['index']:
        S['trial_index']=S['index']
        if waypoint['trial']=='jump':S['pawn'].jump()
        if waypoint['trial']=='crouch':S['pawn'].crouch(False)
        REPORT['actions'].append({'action':waypoint['trial'],'waypoint':waypoint['id']})
    if game_time-S['last_sample']>=.25:
        REPORT['samples'].append(sample(game_time,target));S['last_sample']=game_time
    if elapsed>=3.0:
        coordinate=foot.x if waypoint['block_axis']=='x' else foot.y
        passed=(coordinate>=waypoint['limit'] if waypoint['blocked_side']=='less' else coordinate<=waypoint['limit'])
        passed=passed and foot.z<1250
        if waypoint['trial']=='crouch':passed=passed and bool(S['pawn'].get_editor_property('is_crouched'))
        row={'id':waypoint['id'],'phase':'blocked_capsule_trial','passed':bool(passed),
             'actual_foot_cm':xyz(foot),'trial':waypoint['trial'],'seconds':elapsed,
             'actual_crouched':bool(S['pawn'].get_editor_property('is_crouched')),
             'native_movement_mode':str(S['move'].get_editor_property('movement_mode'))}
        REPORT['waypoints'].append(row);write()
        S['pawn'].stop_jumping();S['pawn'].un_crouch(False)
        if not passed:raise RuntimeError('Actual capsule bypassed the visible closure: '+str(row))
        S['index']+=1
        if S['index']==len(ROUTE):request_finish()
        else:begin_segment(game_time)
        return
    dx,dy=target[0]-foot.x,target[1]-foot.y;length=math.hypot(dx,dy)
    if length>1:S['pawn'].add_movement_input(unreal.Vector(dx/length,dy/length,0),1.0,False)


'''
assert source.count(needle)==1;source=source.replace(needle,trial+needle)
source=source.replace("REPORT['finding'] = 'Upstairs access remains unresolved. A failed route is not evidence of an authored visible upstairs closure.'",
    "REPORT['finding'] = 'Actual planned capsule blocked trials and ground-floor exit/return route; inspect each result, no physical keyboard or packaged/S07 claim.'\n        REPORT['closure_needed_under_brief'] = False if REPORT['complete_route_walked'] else None")
# Preserve the lifecycle's normal menu and cleanup; strengthen only its local
# file enumeration against existing MAX_PATH assets.
source=source.replace('import unreal\n','import unreal\nimport release_file_io as long_io\n',1)
source=source.replace("paths = set((ROOT / 'Content').rglob('*.uasset')) | set((ROOT / 'Content').rglob('*.umap'))",
    "paths = set(long_io.files(ROOT/'Content','*.uasset')) | set(long_io.files(ROOT/'Content','*.umap'))")
source=source.replace('return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None',
    'return long_io.sha(path) if long_io.is_file(path) else None')
EXPANDED_SOURCE_SHA=hashlib.sha256(source.encode()).hexdigest()
exec(compile(source,str(ROOT/'Python/probe_release_upstairs_walk.py'),'exec'),globals())
REPORT['expanded_source_sha256']=EXPANDED_SOURCE_SHA
OUTPUT.mkdir(parents=True,exist_ok=True)
(OUTPUT/'expanded_fixture.py').write_text(source)
write()
