"""Confirm FKey parsing natively, then recover the47 proven lost key names.

Root must queue one editor writer with -ReleaseKeyLiteralWrite. An unsaved
/Temp fixture proves bad/bare E and SpaceBar first. No input is synthesized.
Only47 manager key defaults and two proven photo-yaw defaults may be saved; no graph,
GUID, execution link, campaign/profile schema or map regeneration occurs.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import sys
import traceback
import unreal

ROOT=Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/'Python'))
import opening_graph as og
import release_file_io as io
import release_mother_integration as shared

ASSETS=[shared.MANAGER,'/Game/Opening/Blueprints/BP_OpeningHUD']
FUNCTIONS={'WasInputKeyJustPressed','IsInputKeyDown','WasInputKeyJustReleased'}
BAD=re.compile(r'^\(KeyName="([A-Za-z][A-Za-z0-9_]*)"\)$')
REPORT=ROOT/'release_key_literal_repair_report.json'
BASELINE_SCAN=ROOT/'validation/release_key_literal_repair/20261026T042425_110963/key_scan.json'
INPUT_KEYS=['Escape','One','Two','Three','Escape','SpaceBar','One','Two','Three','E',
    'E','F','R','Left','Right','E','Q','E','MouseScrollUp','Right','MouseScrollDown','Left',
    'M','P','T','One','Two','Three','Four','Tab','E','Left','Right','F1','Tab','Q','F','E']
INPUT_ACTIONS=['CloseModal','HandleOne','HandleTwo','HandleThree','OpenPause',
    'SkipRecollections','HandleOne','HandleTwo','HandleThree','AdvanceDialogue',
    'CloseModal','CloseModal','FlipPhoto','K2_AddActorLocalRotation','K2_AddActorLocalRotation',
    'CloseDocument','CloseModal',{'CloseModal','ConfirmWatch'},'RotateDial','RotateDial','RotateDial','RotateDial',
    'MapView','RequestPerspective','RequestTimePause','HandleOne','HandleTwo','HandleThree','SelectIsland',
    'CloseModal','CloseModal','TurnJournal','TurnJournal','OpenHelp','OpenJournal','OpenWatch','InspectSelected','Interact']
SEMANTIC_PROGRESS=[]
SEMANTIC_PROGRESS_FILE=None


def semantic_progress(row):
    SEMANTIC_PROGRESS.append(row)
    if SEMANTIC_PROGRESS_FILE:
        SEMANTIC_PROGRESS_FILE.write_text(json.dumps(SEMANTIC_PROGRESS,indent=2)+'\n')


def node_guid(node,audit):
    try:
        guid=node.get_editor_property('node_guid')
        return [int(getattr(guid,part)) for part in ['a','b','c','d']]
    except Exception:
        return audit.guid(node)


def snapshot(blueprints,audit):
    rows={}
    for bp in blueprints:
        for graph in og.L.list_graphs(bp):
            for node in og.E.get_graph_editor(graph).list_all_nodes():
                rows[node.get_path_name()]={'guid':node_guid(node,audit),'pins':audit.pins(node)}
    return rows


def fixture(cases,stamp):
    bp=og.blueprint('/Temp/BP_ReleaseKeyLiteralProof_'+stamp,unreal.Actor)
    # Key_IsValid takes const FKey&: its Key pin rejects direct literals. A
    # native assigned member supplies an lvalue, with the same by-value text
    # import path as production PlayerController key-query defaults.
    og.member(bp,'ProofKey',og.struct_type('/Script/InputCore.Key'))
    og.compile_bp(bp)
    records=[]
    for index,(label,literal,expected) in enumerate(cases):
        name='KeyProof'+str(index)
        graph=og.function(bp,name,outputs={'Valid':'bool'})
        setter=graph.set('ProofKey')
        rejection=None
        tested=literal
        try:og.default(setter,'ProofKey',literal)
        except og.GraphError as error:
            # Some editor pins reject the old syntax before compilation. The
            # saved production scan already proves its normalized token "(";
            # test that actual stored value rather than requiring rejection
            # behavior to be identical across different native pin types.
            shared.require(not expected and BAD.fullmatch(literal),
                           'Valid bare/native-token key fixture assignment failed')
            rejection=str(error);tested='('
            og.default(setter,'ProofKey',tested)
        getter=graph.get('ProofKey')
        call=graph.call('/Script/Engine.KismetInputLibrary.Key_IsValid')
        og.link(og.value_pin(getter,'ProofKey'),og.pin_in(call,'Key'))
        graph.output('Valid',og.value_pin(call))
        og.link(graph.entry,og.pin_in(setter))
        og.link(og.pin_out(setter),og.pin_in(graph.result))
        records.append({'name':name,'label':label,'supplied_literal':literal,
                        'tested_literal':tested,'source_syntax_rejection':rejection,
                        'actual_pin_before_compile':str(og.P.get_pin_value(og.pin_in(setter,'ProofKey'))),
                        'expected_registered_key':expected,'node':setter})
    compiled=og.compile_all([bp],save=False)
    cdo=unreal.get_default_object(bp.generated_class())
    for record in records:
        call=record.pop('node')
        record['actual_pin_after_compile']=str(og.P.get_pin_value(og.pin_in(call,'ProofKey')))
        record['actual_registered_key']=bool(cdo.call_method(record['name'],args=()))
        shared.require(record['actual_registered_key']==record['expected_registered_key'],
                       'Native FKey parsing did not confirm the proposed repair: '+json.dumps(record))
    return {'asset':bp.get_path_name(),'saved':False,'compiled':compiled,'cases':records}


def rotation_numbers(value):
    fields=re.findall(r'(Pitch|Yaw|Roll)\s*=\s*([-+0-9.eE]+)',value,re.I)
    if len(fields)==3:
        values={name.lower():float(number) for name,number in fields}
        return [values[name] for name in ['pitch','yaw','roll']]
    parts=value.strip('() ').split(',')
    shared.require(len(parts)==3,'Expected native Rotator pitch,yaw,roll literal: '+value)
    return [float(part) for part in parts]


def rotation_fixture(stamp):
    bp=og.blueprint('/Temp/BP_ReleasePhotoRotationProof_'+stamp,unreal.Actor)
    og.member(bp,'ProofRotation',og.struct_type('rotator'))
    og.compile_bp(bp)
    cases=[('LegacySourceLeft','(Pitch=0,Yaw=-2,Roll=0)',[0,0,0]),
           ('CanonicalLeft','0,-2,0',[0,-2,0]),('CanonicalRight','0,2,0',[0,2,0])]
    records=[]
    for name,literal,expected in cases:
        graph=og.function(bp,name,outputs={'Rotation':og.struct_type('rotator')})
        setter=graph.set('ProofRotation');rejected=None
        try:og.default(setter,'ProofRotation',literal)
        except og.GraphError as error:
            shared.require(name=='LegacySourceLeft','Canonical photo Rotator text was rejected')
            rejected=str(error);og.default(setter,'ProofRotation','0,0,0')
        getter=graph.get('ProofRotation')
        graph.output('Rotation',og.value_pin(getter,'ProofRotation'))
        og.link(graph.entry,og.pin_in(setter));og.link(og.pin_out(setter),og.pin_in(graph.result))
        records.append({'function':name,'supplied_literal':literal,'expected_pitch_yaw_roll':expected,
            'source_syntax_rejected':rejected,'setter':setter})
    compiled=og.compile_all([bp],save=False)
    cdo=unreal.get_default_object(bp.generated_class())
    for record in records:
        setter=record.pop('setter')
        record['stored_pin_literal']=str(og.P.get_pin_value(og.pin_in(setter,'ProofRotation')))
        value=cdo.call_method(record['function'],args=())
        actual=[float(value.pitch),float(value.yaw),float(value.roll)]
        record['actual_pitch_yaw_roll']=actual
        shared.require(all(abs(a-b)<.0001 for a,b in zip(actual,record['expected_pitch_yaw_roll'])),
                       'Native Rotator-member fixture failed: '+json.dumps(record))
    return {'asset':bp.get_path_name(),'saved':False,'compiled':compiled,'cases':records,
        'scope':'Actual native member assignment/readback; legacy text loses yaw, canonical CSV preserves each intended axis.'}


def condition_branch(node,audit):
    """Follow the key's boolean data to its unique condition branch."""
    pending=[og.value_pin(node)];visited=set();branches={}
    for unused in range(5):
        following=[]
        for output in pending:
            for pin in og.P.list_connected_pins(output):
                owner=og.P.get_owning_node(pin);path=owner.get_path_name()
                if owner.get_class().get_name()=='K2Node_IfThenElse':
                    shared.require(str(og.P.get_pin_name(pin))=='Condition','Key output unexpectedly drives an execution pin')
                    branches[path]=owner
                elif path not in visited:
                    visited.add(path)
                    shared.require(audit.function(owner)[1] in ['BooleanAND','BooleanOR'],
                                   'Unexpected key-condition adapter: '+path)
                    following.append(og.value_pin(owner))
        pending=following
        if not pending:break
    shared.require(len(branches)==1,'Expected one actual condition branch per key query')
    return next(iter(branches.values()))


def first_exec_calls(pin,audit):
    """Inspect both control-flow paths until each first actual action call."""
    pending=[pin];visited=set();result=[]
    for unused in range(12):
        following=[]
        for output in pending:
            for linked in og.P.list_connected_pins(output):
                node=og.P.get_owning_node(linked);path=node.get_path_name()
                if path in visited:continue
                visited.add(path)
                member=audit.function(node)[1]
                if member:
                    result.append({'node':path,'function':member,'object':node});continue
                for outgoing in og.L.list_output_pins(node):
                    name=str(og.P.get_pin_name(outgoing))
                    if name in ['then','else'] or name.startswith('then_'):following.append(outgoing)
        pending=following
        if not pending:break
    return result


def semantic_guard(entry,expected,audit,parameter=None):
    branch=condition_branch(entry['node'],audit)
    calls=first_exec_calls(og.pin_out(branch,'then'),audit)
    actual={row['function'] for row in calls}
    required=expected if isinstance(expected,set) else {expected}
    diagnostic={'query_node':entry['record']['node'],'query_function':entry['record']['function'],
        'restored_key':entry['new_value'],'condition_branch':branch.get_path_name(),
        'expected_actions':sorted(required),'actual_actions':sorted(actual),
        'actual_call_nodes':[{k:v for k,v in row.items() if k!='object'} for row in calls],
        'parameters':[],'passed':False}
    semantic_progress(diagnostic)
    shared.require(actual==required,'Authored key/action recovery mismatch: '+json.dumps(diagnostic))
    parameters=[]
    if parameter:
        name,value=parameter
        for call in calls:
            pin=og.pin_in(call['object'],name)
            linked=bool(list(og.P.list_connected_pins(pin)))
            actual_value=str(og.P.get_pin_value(pin))
            parameter_diagnostic={'call_node':call['node'],'call_function':call['function'],
                'parameter':name,'source_intended_value':value,'actual_literal':actual_value,'linked':linked}
            diagnostic['parameters'].append(parameter_diagnostic)
            if SEMANTIC_PROGRESS_FILE:SEMANTIC_PROGRESS_FILE.write_text(json.dumps(SEMANTIC_PROGRESS,indent=2)+'\n')
            shared.require(not linked,'Authored action parameter is no longer literal: '+json.dumps(diagnostic))
            if name=='DeltaRotation':
                actual_rotation=rotation_numbers(actual_value)
                actual_number=actual_rotation[1]
            else:actual_number=float(actual_value)
            parameter_diagnostic['actual_number']=actual_number
            if name=='DeltaRotation' and call['function']=='K2_AddActorLocalRotation':
                # Actual exported call91 proves the source Rotator text was
                # normalized to the autogenerated0,0,0 before this repair.
                # Key identity is independently pinned by all47 GUIDs, held
                # type, original creation order and this exact action. Root
                # authorized correcting only these two proven zero defaults.
                matches_source=abs(actual_number-value)<.0001
                normalized_zero=all(abs(number)<.0001 for number in actual_rotation)
                parameter_diagnostic['known_nonkey_rotation_normalized_to_zero']=normalized_zero and not matches_source
                shared.require(normalized_zero,'Photo-yaw repair accepts only the exact reviewed all-zero old rotation: '+json.dumps(diagnostic))
                canonical='0,'+str(int(value))+',0'
                correction={'query_node':entry['record']['node'],'restored_key':entry['new_value'],
                    'node':call['node'],'function':call['function'],'pin':'DeltaRotation',
                    'before':actual_value,'proposed_after':canonical,'expected_pitch_yaw_roll':[0.0,value,0.0]}
                entry.setdefault('rotation_fixes',[]).append({'node':call['object'],'pin':pin,'record':correction})
                parameter_diagnostic['proposed_canonical_rotation']=canonical
                parameters.append({'name':name,'source_intended':value,'actual':actual_value,
                    'proven_zero_loss_defect':True,'proposed_correction':canonical,
                    'repair_scope':'One of two explicitly authorized existing photo yaw defaults only'})
            else:
                shared.require(abs(actual_number-value)<.0001,'Authored key/action direction changed: '+json.dumps(diagnostic))
                parameters.append({'name':name,'expected':value,'actual':actual_value})
            if SEMANTIC_PROGRESS_FILE:SEMANTIC_PROGRESS_FILE.write_text(json.dumps(SEMANTIC_PROGRESS,indent=2)+'\n')
    diagnostic['passed']=True
    if SEMANTIC_PROGRESS_FILE:SEMANTIC_PROGRESS_FILE.write_text(json.dumps(SEMANTIC_PROGRESS,indent=2)+'\n')
    return {'condition_branch':branch.get_path_name(),'first_actions':[
        {k:v for k,v in row.items() if k!='object'} for row in calls],'literal_parameter_checks':parameters}


def recovery_candidates(entries,blueprints,audit):
    baseline=json.loads(BASELINE_SCAN.read_text())['scanned']
    current=[entry['record'] for entry in entries]
    fields=['asset','graph','node','guid','function','key_literal','linked_key_input']
    shared.require(len(baseline)==len(current)==47 and
        [{k:r[k] for k in fields} for r in baseline]==[{k:r[k] for k in fields} for r in current],
        'Actual47-node identities/order/defaults differ from the root-reviewed native scan')
    shared.require(all(row['key_literal']=='(' and not row['linked_key_input'] for row in current),
                   'Lost-token recovery accepts only the47 proven unlinked literal "(" inputs')
    groups={name:[e for e in entries if e['record']['graph']==name] for name in
            ['InputFrame','MovementFrame','ReleaseMenuTick']}
    shared.require([len(groups[k]) for k in groups]==[39,2,6] and
        all(row['asset'].split('.')[0]==ASSETS[0] for row in current),
        'Expected exact manager graph distribution39/2/6 and no HUD key queries')
    metadata=unreal.EditorAssetLibrary.get_metadata_tag(blueprints[0],'Release.FrontendHooks')
    hooks=json.loads(metadata)
    hook_names=set(hooks['InputFrame']['nodes'])
    f10=[e for e in groups['InputFrame'] if e['node'].get_name() in hook_names]
    shared.require(len(f10)==1,'Expected one key query in the existing F10 frontend hook')
    original=[e for e in groups['InputFrame'] if e not in f10]
    def order(entry):
        match=re.fullmatch(r'K2Node_CallFunction_(\d+)',entry['node'].get_name())
        shared.require(match,'Reviewed numeric call-node creation name required')
        return int(match.group(1))
    original.sort(key=order)
    shared.require(len(original)==len(INPUT_KEYS)==len(INPUT_ACTIONS)==38,'Expected38 original story queries')
    semantic=[]
    for index,(entry,key,expected) in enumerate(zip(original,INPUT_KEYS,INPUT_ACTIONS)):
        entry['new_value']=key
        kind='IsInputKeyDown' if index in [13,14] else 'WasInputKeyJustPressed'
        shared.require(entry['record']['function']==kind,'Original story query held/pressed type changed')
        parameter=None
        if index in [13,14]:parameter=('DeltaRotation',-2.0 if index==13 else 2.0)
        elif index in [18,19,20,21]:parameter=('Direction',1.0 if index in [18,19] else -1.0)
        elif index in [31,32]:parameter=('Direction',-1.0 if index==31 else 1.0)
        elif index==28:parameter=('Island',4.0)
        proof=semantic_guard(entry,expected,audit,parameter)
        semantic.append(dict(entry['record'],restored_key=key,source_order_index=index,semantic=proof))
    entry=f10[0];entry['new_value']='F10'
    shared.require(entry['record']['function']=='WasInputKeyJustPressed','F10 query type changed')
    semantic.append(dict(entry['record'],restored_key='F10',frontend_hook_metadata_verified=True,
        semantic=semantic_guard(entry,{'OpenPause','ReleaseShowMain'},audit)))
    menu=sorted(groups['ReleaseMenuTick'],key=order)
    for index,(entry,key) in enumerate(zip(menu,['Up','Down','Tab','Enter','E','Escape'])):
        entry['new_value']=key
        shared.require(entry['record']['function']=='WasInputKeyJustPressed','Menu query type changed')
        expected='ReleaseStepSelection' if index<3 else ('ReleaseActivate' if index<5 else
                    {'ReleaseResume','ReleaseShowSettings','ReleaseShowMain'})
        param=('Direction',-1.0 if index==0 else 1.0) if index<3 else None
        semantic.append(dict(entry['record'],restored_key=key,source_order_index=index,
            semantic=semantic_guard(entry,expected,audit,param)))
    movement=sorted(groups['MovementFrame'],key=order)
    for index,(entry,key,kind) in enumerate(zip(movement,['LeftShift','LeftControl'],['IsInputKeyDown','WasInputKeyJustPressed'])):
        entry['new_value']=key
        shared.require(entry['record']['function']==kind,'Movement held/pressed query type changed')
        if index==0:
            branch=condition_branch(entry['node'],audit);speeds=[]
            for output,value in [('then',420.0),('else',260.0)]:
                links=list(og.P.list_connected_pins(og.pin_out(branch,output)))
                shared.require(len(links)==1,'Expected original jog/walk speed setter')
                setter=og.P.get_owning_node(links[0]);text=audit.text(setter)
                shared.require('MemberName="MaxWalkSpeed"' in text,'Expected native CharacterMovement MaxWalkSpeed setter')
                pin=og.pin_in(setter,'MaxWalkSpeed')
                shared.require(not list(og.P.list_connected_pins(pin)) and
                    abs(float(str(og.P.get_pin_value(pin)))-value)<.0001,'Original jog/walk speeds changed')
                speeds.append({'branch':output,'cm_s':value,'setter':setter.get_path_name()})
            proof={'condition_branch':branch.get_path_name(),'speed_setters':speeds}
        else:proof=semantic_guard(entry,{'UnCrouch','Crouch'},audit)
        semantic.append(dict(entry['record'],restored_key=key,source_order_index=index,semantic=proof))
    shared.require(len(semantic)==47 and all(e.get('new_value') for e in entries),'Incomplete key recovery map')
    return entries,{'baseline_scan':str(BASELINE_SCAN),'baseline_scan_sha256':io.sha(BASELINE_SCAN),
        'exact_original47_identities_and_distribution_verified':True,'semantic_action_guards':semantic,
        'source_creation_order_note':'Original38 InputFrame calls numeric order; later F10 hook isolated by owned frontend metadata because it reused low suffix3.'}


def main():
    global SEMANTIC_PROGRESS_FILE
    shared.require(ROOT.parent.name=='Release_20261026' and
        unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseKeyLiteralWrite'),
        'Root serialized Release key-repair writer grant required')
    level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    shared.require(not level.is_in_play_in_editor(),'Key repair requires an exited PIE session')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    out=ROOT/'validation/release_key_literal_repair'/stamp
    out.mkdir(parents=True)
    SEMANTIC_PROGRESS_FILE=out/'semantic_progress.json'
    blueprints=[unreal.load_asset(path) for path in ASSETS]
    shared.require(all(blueprints),'Both existing manager and HUD are required')
    owned={shared.asset_file(ROOT,path) for path in ASSETS}
    native=io.files(ROOT/'Content','*.uasset')+io.files(ROOT/'Content','*.umap')
    native+=list((ROOT/'Config').glob('*.ini'))+list(ROOT.glob('*.uproject'))
    native+=io.files(ROOT/'Saved/SaveGames','*.sav')
    protected={str(path):io.sha(path) for path in native if path not in owned}
    originals={str(path):io.sha(path) for path in owned}
    for path in owned:
        (out/(path.name+'.before')).write_bytes(io.io_path(path).read_bytes())
    audit=shared.GraphAudit(out/'node_exports')
    guards_before=audit.guarded_calls(blueprints[0])
    candidates=[]
    entries=[]
    scanned=[]
    for bp in blueprints:
        for graph in og.L.list_graphs(bp):
            for node in og.E.get_graph_editor(graph).list_all_nodes():
                title=re.sub(r'\s+','',str(og.L.get_node_title(node))).lower()
                if not any(name.lower() in title for name in FUNCTIONS):continue
                owner,member=audit.function(node)
                if member not in FUNCTIONS:continue
                shared.require(owner=='/Script/Engine.PlayerController','Unexpected key-query owner: '+str(owner))
                pin=og.pin_in(node,'Key')
                links=list(og.P.list_connected_pins(pin))
                value=str(og.P.get_pin_value(pin))
                row={'asset':bp.get_path_name(),'graph':graph.get_name(),'node':node.get_path_name(),
                     'guid':node_guid(node,audit),'function':member,'key_literal':value,'linked_key_input':bool(links)}
                scanned.append(row)
                entries.append({'bp':bp,'node':node,'pin':pin,'record':row})
                match=BAD.fullmatch(value)
                if match and not links:
                    candidates.append({'bp':bp,'node':node,'pin':pin,'record':row,'new_value':match.group(1)})
    (out/'key_scan.json').write_text(json.dumps({'scanned':scanned},indent=2))
    (out/'patcher_source_snapshot.py').write_bytes(Path(__file__).read_bytes())
    parser_proof=fixture([('bad E','(KeyName="E")',False),('bare E','E',True),('bad SpaceBar','(KeyName="SpaceBar")',False),('bare SpaceBar','SpaceBar',True),('actual lost token','(',False)],stamp+'_ReadOnlyParsing')
    (out/'parser_proof.json').write_text(json.dumps(parser_proof,indent=2))
    candidates,recovery=recovery_candidates(entries,blueprints,audit)
    (out/'recovery_plan.json').write_text(json.dumps(recovery,indent=2)+'\n')
    proof=parser_proof
    keys=sorted({entry['new_value'] for entry in candidates})
    registered=fixture([(key,key,True) for key in keys],stamp+'_Registered')
    (out/'registered_keys_proof.json').write_text(json.dumps(registered,indent=2)+'\n')
    rotations=[fix for entry in candidates for fix in entry.get('rotation_fixes',[])]
    shared.require(len(rotations)==2 and {fix['record']['restored_key'] for fix in rotations}=={'Left','Right'},
                   'Expected exactly the two existing held-photo Left/Right rotation fixes')
    rotation_proof=rotation_fixture(stamp)
    (out/'rotation_parser_proof.json').write_text(json.dumps(rotation_proof,indent=2)+'\n')
    shared.require(all(io.sha(path)==digest for path,digest in originals.items()),'Proof-only fixture changed an owned asset before repair')
    shared.require(all(io.sha(path)==digest for path,digest in protected.items()),'Proof-only fixture changed an unowned asset')
    if unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseKeyLiteralPlanOnly'):
        plan={'success':True,'native_executed':True,'plan_only':True,'existing_asset_writes':False,
            'native_parsing_fixture':proof,'per_corrected_key_registration_fixture':registered,
            'lost_token_recovery':recovery,'proposed_key_count':len(candidates),'evidence_directory':str(out),
            'native_rotation_fixture':rotation_proof,'proposed_photo_rotation_fixes':[fix['record'] for fix in rotations],
            'owned_asset_bytes_unchanged':True,'unowned_native_config_save_files_unchanged':True}
        (out/'read_only_plan.json').write_text(json.dumps(plan,indent=2)+'\n')
        (ROOT/'release_key_literal_repair_plan.json').write_text(json.dumps(plan,indent=2)+'\n')
        return
    before=snapshot(blueprints,audit)
    changes=[]
    for entry in candidates:
        shared.require(og.P.set_pin_value(entry['pin'],entry['new_value']),'Native key default write refused')
        actual=str(og.P.get_pin_value(entry['pin']))
        shared.require(actual==entry['new_value'],'Native key default was not stored as the exact bare name')
        changes.append(dict(entry['record'],before=entry['record']['key_literal'],after=actual))
    rotation_changes=[]
    for fix in rotations:
        row=fix['record']
        shared.require(str(og.P.get_pin_value(fix['pin']))==row['before'],'Photo rotation changed after proof')
        shared.require(og.P.set_pin_value(fix['pin'],row['proposed_after']),'Canonical photo rotation default refused')
        actual=str(og.P.get_pin_value(fix['pin']))
        shared.require(all(abs(a-b)<.0001 for a,b in zip(rotation_numbers(actual),row['expected_pitch_yaw_roll'])),
                       'Stored photo rotation differs from the native-proven canonical axes')
        rotation_changes.append(dict(row,after=actual))
    changed_assets={entry['bp'].get_path_name() for entry in candidates}
    compiled=og.compile_all([bp for bp in blueprints if bp.get_path_name() in changed_assets],save=False)
    audit.cache.clear()
    after=snapshot(blueprints,audit)
    shared.require(set(before)==set(after),'Original manager/HUD graph node set changed')
    allowed={row['node']:row for row in changes}
    allowed_rotations={row['node']:row for row in rotation_changes}
    for path,old in before.items():
        new=after[path]
        shared.require(old['guid']==new['guid'],'Original graph node GUID changed: '+path)
        if path in allowed:
            old_pins=dict(old['pins']);new_pins=dict(new['pins'])
            old_key=old_pins.pop('in:Key');new_key=new_pins.pop('in:Key')
            shared.require(old_pins==new_pins and old_key['links']==new_key['links']==[] and
                old_key['value']==allowed[path]['before'] and new_key['value']==allowed[path]['after'],
                'A key repair changed execution/non-key pins: '+path)
        elif path in allowed_rotations:
            old_pins=dict(old['pins']);new_pins=dict(new['pins'])
            old_rotation=old_pins.pop('in:DeltaRotation');new_rotation=new_pins.pop('in:DeltaRotation')
            shared.require(old_pins==new_pins and old_rotation['links']==new_rotation['links']==[] and
                old_rotation['value']==allowed_rotations[path]['before'] and
                new_rotation['value']==allowed_rotations[path]['after'],
                'Photo-yaw repair changed execution/other data pins: '+path)
        else:
            shared.require(old==new,'Unchanged manager/HUD node was modified: '+path)
    guards_after=audit.guarded_calls(blueprints[0])
    shared.require(guards_after==guards_before,'Key-only repair changed one of the13 guarded save nodes')
    shared.require(all(io.sha(path)==digest for path,digest in protected.items()),'Unowned native input changed before save')
    saved=[]
    for bp in blueprints:
        if bp.get_path_name() in changed_assets:
            shared.require(unreal.EditorAssetLibrary.save_loaded_asset(bp,only_if_is_dirty=False),'Changed key-query asset forced save failed')
            saved_file=shared.asset_file(ROOT,bp.get_path_name())
            shared.require(io.sha(saved_file)!=originals[str(saved_file)],
                           'Changed key-query asset bytes stayed unchanged; persistence is unproven')
            saved.append(bp.get_path_name())
    shared.require(all(io.sha(path)==digest for path,digest in protected.items()),'Unowned native input changed during explicit saves')
    # An unchanged HUD must retain its exact bytes; no convenience resave.
    for path,digest in originals.items():
        asset='/Game/'+Path(path).relative_to(ROOT/'Content').with_suffix('').as_posix()
        if not any(name.split('.')[0]==asset for name in saved):
            shared.require(io.sha(path)==digest,'An unchanged owned asset was resaved')
    snapshots=out/'original_node_snapshots.json'
    snapshots.write_text(json.dumps({'before':before,'after':after},indent=2)+'\n')
    result={'success':True,'native_executed':True,'run':stamp,'native_parsing_fixture':proof,
        'lost_token_recovery':recovery,
        'per_corrected_key_registration_fixture':registered,'scanned_key_queries':scanned,
        'native_rotation_fixture':rotation_proof,'photo_rotation_fixes':rotation_changes,
        'changed_key_defaults':changes,'changed_count':len(changes),'saved_assets':saved,'compiled':compiled,
        'all_original_node_guids_preserved':True,'all_execution_and_unlisted_data_pins_preserved':True,
        'only_nonkey_changes_are_two_documented_photo_yaw_defaults':True,
        'original_node_count':len(before),'complete_node_snapshot_file':str(snapshots),
        'complete_node_snapshot_sha256':io.sha(snapshots),'guarded_save_nodes_unchanged':True,
        'guarded_save_calls_after':guards_after,'manager_asset_sha256':io.sha(shared.asset_file(ROOT,ASSETS[0])),
        'hud_asset_sha256':io.sha(shared.asset_file(ROOT,ASSETS[1])),
        'unowned_native_config_save_files_unchanged':True,'protected_file_count':len(protected),
        'protected_file_sha256':protected,'owned_sha256_before':originals,'rollback_archive':str(out),
        'physical_keyboard_or_packaged_input_verified':False,'new_windows_build_required':True,
        'scope':'47 existing PlayerController key defaults plus two native-proven photo yaw defaults; /Temp fixtures unsaved; no synthetic input or graph regeneration.'}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    REPORT.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    settings=unreal.get_default_object(unreal.load_class(None,'/Script/BlueprintGraph.BlueprintEditorSettings'))
    old=settings.get_editor_property('bEnableTypePromotion')
    try:
        settings.set_editor_property('bEnableTypePromotion',False);main()
    except Exception:
        (ROOT/'release_key_literal_repair_failed.json').write_text(json.dumps({'success':False,
            'error':traceback.format_exc(),'rollback_policy':'Inspect byte archive after editor exit; never overwrite loaded assets.'},indent=2)+'\n')
        unreal.log_error(traceback.format_exc())
    finally:settings.set_editor_property('bEnableTypePromotion',old)
    unreal.SystemLibrary.quit_editor()
