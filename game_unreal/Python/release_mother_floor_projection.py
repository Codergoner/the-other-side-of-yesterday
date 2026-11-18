"""Bounded Mother-only porch-height repair; run only in Root's native writer queue.

Adds one pure native Blueprint function, preserving all existing waypoint nodes,
XY routes, 100cm/s interpolation settings, era checks and guarded save calls.
This is not a collision/IK solver or a replacement for the final walking review.
"""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import json
import re
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import opening_graph as og
import release_file_io as io
import release_mother_integration as shared
from release_frontend_graph import Flow, MATH

FUNCTION = 'ReleaseMotherProjectPorchFloor'
CLASS = shared.MANAGER + '.BP_OpeningActions_C'
OWNER = 'TOSOY.ReleaseMotherPorchFloor.v1'
MAP = '/Game/Quest/Maps/Verdant_Desktop'
REPORT = ROOT / 'release_mother_floor_projection_report.json'
EXPECTED = [(-915,1240,1011),(-760,1240,1011),(-600,1240,1011),
            (-430,1240,1011),(-300,1240,966),(-150,1240,920),
            (-40,1240,896),(-430,1240,1011),(-600,1240,1011),
            (-760,1240,1011),(-915,1240,1011),(-915,1412,1011)]


def vector_literal(pin):
    shared.require(not list(og.P.list_connected_pins(pin)), 'Expected original unconnected authored vector literal')
    value = str(og.P.get_pin_value(pin))
    fields = re.findall(r'([XYZ])\s*=\s*([-+0-9.eE]+)', value, re.I)
    if len(fields) == 3:
        values = {key.upper(): float(number) for key, number in fields}
        return tuple(values[key] for key in 'XYZ')
    # Native K2 FVector pin values can also use the compact x,y,z format.
    parts = value.strip('() ').split(',')
    shared.require(len(parts) == 3, 'Unexpected native vector default: ' + value)
    return tuple(float(number) for number in parts)


def expected_projection(value):
    x, y, z = value
    if -430 <= x <= -10 and 1239 <= y <= 1241:
        z = 896 + max(0, min(1, (-10-x)/210)) * 115
    return x, y, z


def create_function(bp):
    shared.require(not og.L.find_graph(bp, FUNCTION), 'Existing floor helper requires separate review; do not overwrite it')
    graph = og.function(bp, FUNCTION, inputs={'Location':og.struct_type('vector')},
                        outputs={'ReturnValue':og.struct_type('vector')}, pure=True)
    f = Flow(graph)
    broken = f.call(MATH+'BreakVector', InVec=graph.input('Location'))
    x, y = og.value_pin(broken,'X'), og.value_pin(broken,'Y')
    inside_x = f.and_(f.data(MATH+'GreaterEqual_DoubleDouble',A=x,B=-430.0),
                      f.data(MATH+'LessEqual_DoubleDouble',A=x,B=-10.0))
    inside_y = f.and_(f.data(MATH+'GreaterEqual_DoubleDouble',A=y,B=1239.0),
                      f.data(MATH+'LessEqual_DoubleDouble',A=y,B=1241.0))
    rise = f.data(MATH+'Subtract_DoubleDouble',A=-10.0,B=x)
    fraction = f.data(MATH+'Divide_DoubleDouble',A=rise,B=210.0)
    fraction = f.data(MATH+'FClamp',Value=fraction,Min=0.0,Max=1.0)
    floor = f.data(MATH+'Add_DoubleDouble',A=896.0,
                   B=f.data(MATH+'Multiply_DoubleDouble',A=fraction,B=115.0))
    projected = f.data(MATH+'MakeVector',X=x,Y=y,Z=floor)
    result = f.data(MATH+'SelectVector',A=projected,B=graph.input('Location'),
                    bPickA=f.and_(inside_x,inside_y))
    graph.output('ReturnValue',result)
    og.link(graph.entry,og.pin_in(graph.result))
    og.compile_bp(bp)


def native_self_test(bp):
    # Actual compiled UFunction calls: includes the three bad original targets,
    # both domain boundaries, stair samples, and several unaffected locations.
    samples = EXPECTED + [(-430,1240,500),(-220,1240,10),(-115,1240,10),
        (-10,1240,10),(-431,1240,966),(-9,1240,896),(-40,1238,500),
        (-40,1242,500),(-420,1340,1011),(-915,1412,1011)]
    cdo = unreal.get_default_object(bp.generated_class())
    rows = []
    for value in samples:
        actual = cdo.call_method(FUNCTION,args=(unreal.Vector(*value),))
        actual = shared.xyz(actual)
        expected = expected_projection(value)
        shared.require(all(abs(a-b)<.001 for a,b in zip(actual,expected)),
                       'Compiled floor projection differs from the source geometry: '+str({'input':value,'actual':actual,'expected':expected}))
        shared.require(abs(actual[0]-value[0])<.001 and abs(actual[1]-value[1])<.001,
                       'Floor repair changed XY')
        rows.append({'input_cm':value,'actual_cm':actual,'expected_cm':expected,'passed':True})
    return rows


def call_projection(editor, value):
    node = editor.add_call_function_node(CLASS+':'+FUNCTION)
    if isinstance(value,unreal.BlueprintGraphPin):
        og.link(value,og.pin_in(node,'Location'))
    else:
        og.default(node,'Location',unreal.Vector(*value))
    return og.value_pin(node)


def graph_snapshot(bp, audit):
    result = {}
    for name in ['NpcTick','RestoreSafeScene']:
        graph = og.L.find_graph(bp,name)
        shared.require(graph,'Existing story graph missing: '+name)
        for node in og.E.get_graph_editor(graph).list_all_nodes():
            result[node.get_path_name()] = {'guid':audit.guid(node),'pins':audit.pins(node)}
    return result


def main():
    command = unreal.SystemLibrary.get_command_line()
    shared.require(ROOT.parent.name=='Release_20261026' and
        unreal.SystemLibrary.parse_param(command,'ReleaseMotherFloorWrite'),
        'Root serialized Release writer grant required')
    source = ROOT.parent/'build_player_house.py'
    source_text = source.read_text(encoding='utf-8')
    shared.require('(-1.075,-7.9,0)' in source_text and '(-1.075,-5.8,1.15)' in source_text,
                   'Existing house approach source changed; review coordinates before projecting')
    native_path = ROOT/'release_upstairs_walk_probe.json'
    native = json.loads(native_path.read_text())
    shared.require(native['success'] and native['source_geometry']['conversion'] ==
        'WorldUEcm=[(-8-localY)*100,(13-localX)*100,(8.96+localZ)*100]',
        'Actual original native route / known source-world conversion required')
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    shared.require(not level.is_in_play_in_editor() and level.load_level(MAP), 'Saved desktop map outside PIE required')
    bp = unreal.load_asset(shared.MANAGER)
    shared.require(not unreal.EditorAssetLibrary.get_metadata_tag(bp,OWNER),
                   'Owned projection was already saved; inspect its report instead of applying twice')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    out = ROOT/'validation/release_mother_floor_projection'/stamp
    out.mkdir(parents=True)
    manager_file = shared.asset_file(ROOT,shared.MANAGER)
    archive = out/(manager_file.name+'.before')
    archive.write_bytes(manager_file.read_bytes())
    protected = io.files(ROOT/'Content','*.uasset') + io.files(ROOT/'Content','*.umap')
    protected += list((ROOT/'Config').glob('*.ini')) + list(ROOT.glob('*.uproject'))
    protected += io.files(ROOT/'Saved/SaveGames','*.sav')
    unchanged = {str(p):io.sha(p) for p in protected if p != manager_file}
    audit = shared.GraphAudit(out/'node_exports')
    guards = audit.guarded_calls(bp)
    before = graph_snapshot(bp,audit)
    create_function(bp)
    tests = native_self_test(bp)
    allowed, changes, targets = {}, [], []
    def allow(node,*pins):
        allowed.setdefault(node.get_path_name(),set()).update(pins)
    graph = og.L.find_graph(bp,'NpcTick')
    editor = og.E.get_graph_editor(graph)
    for node in list(editor.list_all_nodes()):
        if audit.function(node)[1]!='K2_SetActorLocation' or not audit.ancestors_have_variable(node,'MotherActor'):
            continue
        input_pin = og.pin_in(node,'NewLocation')
        linked = list(og.P.list_connected_pins(input_pin))
        shared.require(len(linked)==1,'Expected one unchanged Mother interpolation input')
        raw = linked[0]
        interp = og.P.get_owning_node(raw)
        shared.require(audit.function(interp)[1]=='VInterpTo_Constant','Refusing unexpected Mother movement')
        shared.require(not list(og.P.list_connected_pins(og.pin_in(interp,'InterpSpeed'))) and
            float(str(og.P.get_pin_value(og.pin_in(interp,'InterpSpeed'))))==100,
            'Existing Mother speed is not 100cm/s')
        target = vector_literal(og.pin_in(interp,'Target'))
        distances = [og.P.get_owning_node(pin) for pin in og.P.list_connected_pins(raw)
            if str(og.P.get_pin_name(pin))=='V1' and audit.function(og.P.get_owning_node(pin))[1]=='Vector_Distance']
        shared.require(len(distances)==1,'Expected the existing waypoint arrival distance')
        distance = distances[0]
        shared.require(vector_literal(og.pin_in(distance,'V2'))==target,'Arrival target differs from authored waypoint')
        floor_target = call_projection(editor,target)
        og.link(floor_target,og.pin_in(interp,'Target'))
        floor_position = call_projection(editor,raw)
        for pin in [input_pin,og.pin_in(distance,'V1')]:
            og.P.break_pin_links(pin);og.link(floor_position,pin)
        og.link(floor_target,og.pin_in(distance,'V2'))
        allow(node,'in:NewLocation')
        allow(interp,'in:Target','out:'+str(og.P.get_pin_name(raw)))
        allow(distance,'in:V1','in:V2')
        targets.append(target)
        changes.append({'move':node.get_path_name(),'guid':audit.guid(node),
            'interp':interp.get_path_name(),'arrival_distance':distance.get_path_name(),
            'authored_target_cm':target,'corrected_target_cm':expected_projection(target),
            'interp_speed_cm_s':100,'original_exec_links_preserved':True})
    shared.require(Counter(targets)==Counter(EXPECTED),'Expected all12 exact original Mother waypoints, and no Neri edits')
    editor = og.E.get_graph_editor(og.L.find_graph(bp,'RestoreSafeScene'))
    restore = []
    for node in list(editor.list_all_nodes()):
        if audit.function(node)[1]!='K2_SetActorLocation' or not audit.ancestors_have_variable(node,'MotherActor'):
            continue
        value = vector_literal(og.pin_in(node,'NewLocation'))
        if value == (-40,1240,896):
            og.link(call_projection(editor,value),og.pin_in(node,'NewLocation'))
            allow(node,'in:NewLocation');restore.append({'node':node.get_path_name(),
                'guid':audit.guid(node),'old_cm':value,'new_cm':expected_projection(value)})
    shared.require(len(restore)==1,'Expected exactly one original at-gate Mother restore placement')
    compiled = og.compile_all([bp],save=False)
    tests = native_self_test(bp)
    audit.cache.clear()
    after = graph_snapshot(bp,audit)
    for path, original in before.items():
        current = after.get(path)
        shared.require(current and current['guid']==original['guid'],'Original movement/restore node GUID changed')
        permitted = allowed.get(path,set())
        old_pins = {k:v for k,v in original['pins'].items() if k not in permitted}
        new_pins = {k:v for k,v in current['pins'].items() if k not in permitted}
        shared.require(old_pins==new_pins,'Unexpected original graph pin mutation: '+path)
    shared.require(audit.guarded_calls(bp)==guards,'Floor-only repair changed a guarded save node')
    shared.require(all(io.sha(p)==digest for p,digest in unchanged.items()),'Unowned native input changed before save')
    unreal.EditorAssetLibrary.set_metadata_tag(bp,OWNER,json.dumps({'run':stamp,'source_sha256':io.sha(source)}))
    shared.require(unreal.EditorAssetLibrary.save_loaded_asset(bp),'Owned manager save failed')
    shared.require(all(io.sha(p)==digest for p,digest in unchanged.items()),'Unowned native input changed during manager save')
    result = {'success':True,'native_executed':True,'run':stamp,'manager':shared.MANAGER,
        'manager_sha256_before':io.sha(archive),'manager_asset_sha256':io.sha(manager_file),
        'source':str(source),'source_sha256':io.sha(source),'native_original_route_sha256':io.sha(native_path),
        'floor_domain_cm':{'x':[-430,-10],'y':[1239,1241]},
        'floor_formula':'896 + clamp((-10-X)/210,0,1)*115; XY unchanged; outside domain returns input',
        'existing_movement_changes':changes,'restore_change':restore,'compiled':compiled,
        'actual_compiled_function_tests':tests,'original_nodes_guids_and_unlisted_pins_preserved':True,
        'guarded_save_nodes_unchanged':True,'guarded_save_calls_after':guards,
        'unowned_native_config_save_files_unchanged':True,'only_manager_asset_saved':True,
        'rollback_archive':str(archive),'actual_walking_or_packaged_review_passed':False,
        'limitations':'Fixed source-authored porch projection only; no ground tracing, foot locking, IK or collision solver claim.'}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    REPORT.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    settings=unreal.get_default_object(unreal.load_class(None,'/Script/BlueprintGraph.BlueprintEditorSettings'))
    old=settings.get_editor_property('bEnableTypePromotion')
    try:
        settings.set_editor_property('bEnableTypePromotion',False)
        main()
    except Exception:
        (ROOT/'release_mother_floor_projection_failed.json').write_text(json.dumps({
            'success':False,'error':traceback.format_exc(),
            'rollback_policy':'Do not overwrite loaded assets; inspect .before byte archive only after the editor exits.'},indent=2)+'\n')
        unreal.log_error(traceback.format_exc())
    finally:
        settings.set_editor_property('bEnableTypePromotion',old)
    unreal.SystemLibrary.quit_editor()
