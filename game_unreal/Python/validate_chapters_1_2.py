"""Native PIE acceptance tests for the supplied Chapters 1–2 dialogue slice.

This drives the shipped Blueprint action functions and real camera-ray selection.
It never writes story flags, trust or inventory to manufacture progress. Each run
uses a new test save slot; existing user saves and editor-map defaults are restored.
Bulk dialogue uses a test-only shorter minimum hold after testing the real default.
No headset, physical-keyboard or packaged-game success is inferred from this test.
"""
from pathlib import Path
import datetime
import hashlib
import json
import math
import time
import traceback
import unreal

unreal.EditorPythonScripting.set_keep_python_script_alive(True)
try:
    unreal.get_default_object(unreal.EditorPerformanceSettings).set_editor_property('throttle_cpu_when_not_foreground',False)
except Exception:
    pass

ROOT=Path(unreal.Paths.project_dir()).resolve()
STAMP=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
REPORT_PATH=ROOT/'chapters_1_2_runtime_validation.json'
SCREEN_DIR=ROOT/'validation'/'chapters_1_2'/STAMP
SCREEN_DIR.mkdir(parents=True,exist_ok=True)
CONTENT=json.loads((ROOT/'ContentData/chapters_1_2_dialogue.json').read_text(encoding='utf-8'))
NODES=CONTENT['nodes']
SOURCE_LINES={(line['speaker'],line['text']) for node in NODES.values() for line in node.get('lines',[])}
SOURCE_LINES.update((speaker.split('_',1)[0],text) for speaker,text in CONTENT.get('optional_repeat_lines',{}).items())
ORIGINAL_PLAQUE='The storm before the war. The clinic courtyard and harbor waiting shelter were unusable that night. Families scattered through the town. No complete list was made.'
ORIGINAL_BACK='Our first summer at home.'
ORIGINAL_LETTER='The upstairs room still leaks when the wind comes from the sea.'
CLINIC_CAPTION='A covered clinic courtyard became a meeting point during the storm. The register assembled there later helped families find their relatives. These pages preserve some of their names.'
HARBOR_CAPTION='The repaired waiting shelter brought departing families together during the storm. The passenger list assembled there later helped relatives trace where they had gone.'
JOURNAL_OBSERVED='The town remembers a different version of the storm.'
JOURNAL_UNOBSERVED='A record of the storm-night shelter is on display in the present.'
MANAGER_PATH='/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C'
FIELDS=['HomeExplored','PhotoSeen','PhotoBackSeen','LetterRead','MotherMet','MotherSpoken','MotherPromise',
        'RepairIdentified','ComponentCollected','ComponentPlaced','WatchCalibrated','AnchorActivated','DrawerOpen',
        'IntroSeen','NeriMet','HealerMet','SelaMet','OriginalMemorialRead','CanvasOffered','CanvasRequestKnown',
        'HealerReportDone','ConsequenceObserved','Chapter2Complete','HasReturned','DepartureDone',
        'MotherOpeningResponse','EraIndex','LinenState','CanvasPlan','StormCover','CanvasOwned',
        'CalibrationTests','HealerTrust','TrustEventIds','PriorTimelineObservation','ReturnClockSeconds']
FIELDS+=['PhotoExchangeDone','LetterExchangeDone','HealerTaskOffered','WaterTaken','LinenBundleReady',
         'LinenThanksDone','HasDeparted','ReturnSignalActive','ClinicInspected','HarborInspected',
         'CurrentChapter','FinalResponse','LatestTimelineObservation']
IMPORTANT_INITIAL=['PhotoSeen','LetterRead','MotherSpoken','WatchCalibrated','NeriMet','OriginalMemorialRead',
                   'HealerReportDone','ConsequenceObserved','Chapter2Complete','CanvasOwned']
REFS=['PhotoActor','LetterActor','MotherActor','BenchActor','ComponentActor','AnchorActor',
      'NeriActor','HealerActor','SelaActor','WaterActor','LinenActor','LinenTrayActor','CanvasActor',
      'ClinicInstallActor','HarborInstallActor','MemorialActor','ClinicRecordActor','HarborRecordActor',
      'ClinicCoverActor','HarborCoverActor']
CASES=[
    {'id':'Clinic_OriginalRead','map':'House_FirstPerson','cover':1,'memorial':True,'mother':1,'ending':1,'departure':1,'neri':1,'skip_intro':True,'refuse_linen':True,'plan_change':False,'letter_first':False},
    {'id':'Clinic_OriginalUnread','map':'House_ThirdPerson','cover':1,'memorial':False,'mother':2,'ending':2,'departure':2,'neri':2,'skip_intro':False,'refuse_linen':False,'plan_change':False,'letter_first':True},
    {'id':'Harbor_OriginalRead','map':'House_FirstPerson','cover':2,'memorial':True,'mother':3,'ending':3,'departure':2,'neri':1,'skip_intro':True,'refuse_linen':False,'plan_change':False,'letter_first':True},
    {'id':'Harbor_OriginalUnread','map':'House_ThirdPerson','cover':2,'memorial':False,'mother':1,'ending':2,'departure':1,'neri':2,'skip_intro':True,'refuse_linen':False,'plan_change':True,'letter_first':False},
]
LEVEL=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
REPORT={'success':False,'test':'Native PIE four-route Chapters 1–2 acceptance', 'run':STAMP,
        'routes':[],'screenshots':[],'packaged_build_tested':False,'headset_tested':False,
        'physical_keyboard_tested':False,
        'execution_scope':'Real native Blueprint actions, scene collision rays and Unreal SaveGame; no direct story-state writes.',
        'timing_scope':'Default subtitle hold is checked; subsequent bulk reading uses only a temporary test-instance timing override.',
        'save_policy':'Unique Yesterday_Chapters12_QA slots; existing user saves are hashed and never deleted or overwritten.'}
S={'world':None,'manager':None,'pawn':None,'controller':None,'camera':None,'record':None,
   'editor_override':None,'current_map':None,'step':'startup','last_line':None,'accelerated':False}
handle=None
pending=None
deadline=0.0
closing=False


def xyz(v):return [round(v.x,3),round(v.y,3),round(v.z,3)]
def dist(a,b):return math.sqrt((a.x-b.x)**2+(a.y-b.y)**2+(a.z-b.z)**2)
def prop(name):return S['manager'].get_editor_property(name)
def action(name,*args):return S['manager'].call_method(name,args=tuple(args))
def plain(value):
    if isinstance(value,(bool,int,float,str,type(None))):return value
    try:return [plain(item) for item in value]
    except TypeError:return str(value)
def snapshot():return {name:plain(prop(name)) for name in FIELDS}
def hash_file(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
def wait(seconds=.06):return {'seconds':seconds}
def until(test,description,timeout=30):return {'predicate':test,'description':description,'timeout':timeout}


def write():
    REPORT['active_step']=S['step']
    if S.get('record'):REPORT['active_route']=S['record']
    REPORT_PATH.write_text(json.dumps(REPORT,indent=2,ensure_ascii=False,default=str),encoding='utf-8')


def check(name,passed,details=None):
    row={'name':name,'passed':bool(passed)}
    if details is not None:row['details']=details
    if not passed:
        try:
            row['state']=snapshot()
            row['dialogue']={name:plain(prop(name)) for name in ['Mode','DialogueNodeId','DialogueRoot','DialogueSpeaker','DialogueLine','DialogueWaitingChoice','DialogueChoiceCount','LineIndex','LineElapsed','PanelText','Notice']}
        except Exception:row['diagnostic_error']=traceback.format_exc()
    S['record']['checks'].append(row);write()
    if not passed:raise AssertionError(name+': '+str(details))


def visible(actor):
    try:return not bool(actor.get_editor_property('hidden'))
    except Exception:return not bool(actor.get_editor_property('bHidden'))


def check_channels():
    channels={name:str(prop(name)) for name in ['DialogueSpeaker','DialogueLine','PanelTitle','PanelText','PanelFooter','Prompt','Objective','Notice']}
    if any('elias' in text.lower() for text in channels.values()):
        check('Writer-only identity never reaches a player-facing channel',False,channels)
    S['record'].setdefault('ui_text_observed',[]).append(channels)


def record_spoken():
    if int(prop('Mode'))!=3:return
    node=str(prop('DialogueNodeId'));index=int(prop('LineIndex'))
    speaker=str(prop('DialogueSpeaker'));line=str(prop('DialogueLine'))
    signature=(node,index,speaker,line)
    if signature==S['last_line'] or not line:return
    S['last_line']=signature
    S['record']['spoken_lines'].append({'node':node,'index':index,'speaker':speaker,'text':line})
    if (speaker,line) not in SOURCE_LINES:
        check('Every spoken subtitle comes from the supplied authored content',False,signature)
    if '*[' in line or 'Staging:' in line or '**Effect' in line:
        check('Stage directions are never spoken as subtitles',False,signature)
    check_channels()


def find_manager(world):
    cls=unreal.load_class(None,MANAGER_PATH)
    if cls is None:raise RuntimeError('Build BP_OpeningActions before running this harness')
    found=unreal.GameplayStatics.get_all_actors_of_class(world,cls)
    if len(found)!=1:raise RuntimeError('Expected one opening manager; found '+str(len(found)))
    return found[0]


def ready():
    world=EDITOR.get_game_world()
    if world is None:return False
    pawn=unreal.GameplayStatics.get_player_character(world,0)
    if pawn is None or pawn.get_controller() is None:return False
    S.update(world=world,pawn=pawn,controller=pawn.get_controller(),
             camera=unreal.GameplayStatics.get_player_camera_manager(world,0),manager=find_manager(world))
    return prop('Player') is not None and S['camera'] is not None


def begin_case(case,legacy_fixture=None):
    path='/Game/Home/Maps/'+case['map']
    if not LEVEL.load_level(path):raise RuntimeError('Cannot load '+path)
    manager=find_manager(EDITOR.get_editor_world());original=manager.get_editor_property('SaveSlot')
    slot='Yesterday_Chapters12_QA_'+STAMP+'_'+case['id']
    S['editor_override']=(manager,original)
    S['current_map']=path
    manager.set_editor_property('SaveSlot',slot)
    record={'case':case,'map':path,'slot':slot,'checks':[],'spoken_lines':[],'ray_selections':[],
            'original_save_slot':str(original),'original_save_digest_before':hash_file(ROOT/'Saved/SaveGames'/(str(original)+'.sav'))}
    if legacy_fixture:
        destination=ROOT/'Saved/SaveGames'/(slot+'.sav')
        if destination.exists():raise RuntimeError('Refusing to replace an existing test save: '+str(destination))
        destination.write_bytes(legacy_fixture.read_bytes())
        record['legacy_fixture']={'source':str(legacy_fixture),'sha256':hash_file(legacy_fixture),'test_copy':str(destination)}
    S.update(record=record,last_line=None,accelerated=False)
    LEVEL.editor_request_begin_play()


def prepare_world():
    for command in ['t.IdleWhenNotForeground 0','Slate.bAllowThrottling 0','r.ScreenPercentage 100','DisableAllScreenMessages']:
        unreal.SystemLibrary.execute_console_command(S['world'],command)


def restore_override():
    pair=S.get('editor_override')
    if pair:
        try:pair[0].set_editor_property('SaveSlot',pair[1])
        except Exception:pass
        S['editor_override']=None


def position(location):
    S['pawn'].get_component_by_class(unreal.CharacterMovementComponent).stop_movement_immediately()
    S['pawn'].set_actor_location(location,False,True)


def point(actor):
    if actor.get_component_by_class(unreal.SkeletalMeshComponent):return actor.get_actor_bounds(False)[0]
    return actor.get_actor_location()


def aim(actor):
    S['controller'].set_control_rotation(unreal.MathLibrary.find_look_at_rotation(S['camera'].get_camera_location(),point(actor)))


def ray_state(target):
    start=S['camera'].get_camera_location();forward=unreal.MathLibrary.get_forward_vector(S['camera'].get_camera_rotation())
    hit=unreal.SystemLibrary.line_trace_single(S['world'],start,start+forward*900,
             unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[S['pawn']],unreal.DrawDebugTrace.NONE,True)
    result=hit.to_tuple();actor=result[9]
    return {'mode':int(prop('Mode')),'pawn_cm':xyz(S['pawn'].get_actor_location()),'camera_cm':xyz(start),
            'target_cm':xyz(point(target)),'distance_cm':round(S['pawn'].get_distance_to(target),2),
            'hit_actor':actor.get_name() if actor else None,'target_actor':target.get_name(),
            'hit_tags':[str(t) for t in actor.get_editor_property('tags')] if actor else [],
            'blocking':bool(result[0]),'target_visible':visible(target)}


def standing_points(ref,target):
    path=ROOT/'chapter2_scene_report.json'
    if path.exists():
        data=json.loads(path.read_text(encoding='utf-8'))
        # The authoring report may place points at root or on each map record.
        groups=[data]+list(data.get('maps',[]))
        for group in groups:
            candidate=group.get('standing_points_cm',{}).get(ref)
            if candidate:
                if isinstance(candidate,dict):candidate=candidate.get('position_cm',candidate.get('position'))
                if candidate:
                    if isinstance(candidate[0],(int,float)):yield unreal.Vector(*candidate)
                    else:
                        for p in candidate:yield unreal.Vector(*p)
                    break
    authored={
        'NeriActor':(-35,1050,1013),'HealerActor':(20,580,1060),'SelaActor':(-25,-300,1148),
        'WaterActor':(0,640,1054),'LinenActor':(0,-235,1141.5),'LinenTrayActor':(0,520,1066),
        'CanvasActor':(0,-365,1154.5),'ClinicInstallActor':(20,390,1079),
        'HarborInstallActor':(-60,-535,1171.5),'MemorialActor':(-245,1510,1109)}
    if ref in authored:yield unreal.Vector(*authored[ref])
    origin=target.get_actor_location()
    preferred={'BenchActor':[(190,0)],'MotherActor':[(200,45)],'ComponentActor':[(100,-125)],'AnchorActor':[(0,-155)]}.get(ref,[])
    for dx,dy in preferred+[(160,80),(190,0),(160,-80),(0,-185),(0,185)]:
        z=1109 if ref in ['PhotoActor','LetterActor','MotherActor','BenchActor','ComponentActor','AnchorActor'] else 1020-(origin.y+dy)*.1+98
        yield unreal.Vector(origin.x+dx,origin.y+dy,z)


def focus(ref,strict=True):
    if int(prop('Mode')) not in [0,1,2,4,5]:
        raise RuntimeError('Drain active dialogue/transition before focusing '+ref)
    if int(prop('Mode'))!=0:
        action('CloseModal');yield wait(.05)
    actor=prop(ref)
    if actor is None:raise RuntimeError('Missing authored reference '+ref)
    attempts=[]
    for location in standing_points(ref,actor):
        position(location);yield wait(.10)
        for repeat in range(12):
            aim(actor);yield wait(.035)
            action('UpdateTarget')
            if prop('Target')==actor:break
        action('UpdateTarget');chosen=prop('Target')
        attempts.append(ray_state(actor))
        if chosen==actor:
            S['record']['ray_selections'].append({'reference':ref,'attempts':attempts});write();return True
        if not strict and len(attempts)>=2:break
    if strict:raise AssertionError('No unobstructed nearby ray selected '+ref+': '+json.dumps(attempts))
    S['record']['ray_selections'].append({'reference':ref,'not_selectable':True,'attempts':attempts});write();return False


def interact(ref,strict=True):
    selected=yield from focus(ref,strict)
    action('Interact');yield wait(.04)
    check_channels()
    return selected


def screenshot(label):
    path=SCREEN_DIR/(S['record']['case']['id']+'_'+label+'.png')
    unreal.SystemLibrary.execute_console_command(S['world'],'shot showui filename="'+str(path).replace('\\','/')+'" -nosuffix')
    return {'screenshot':path,'description':'Native viewport '+label,'timeout':30}


def choose_for(case,node):
    root=node.split('.',1)[0]
    if root=='C1_04':return case['mother']
    if root=='C1_08':return case['departure']
    if root=='C2_00':return case['neri']
    if root=='C2_01':
        if S['record'].get('temporary_refusal_pending'):
            S['record']['temporary_refusal_pending']=False;return 2
        return 1
    if root=='C2_04':return S['record'].get('next_canvas_choice',case['cover'])
    if root=='C2_06':return 1 if case['memorial'] else 2
    if root=='C2_09':return case['ending']
    raise RuntimeError('No authored test choice configured for '+node)


def dialogue(case,stop_at_choice=False):
    guard=0
    while int(prop('Mode'))==3:
        guard+=1
        if guard>450:raise RuntimeError('Dialogue did not complete: '+str(prop('DialogueNodeId')))
        record_spoken()
        node=str(prop('DialogueNodeId'))
        if bool(prop('DialogueWaitingChoice')):
            if stop_at_choice:return
            choice=choose_for(case,node)
            before=snapshot()
            source=NODES.get(node,{})
            available=source.get('choices',[])
            check('Runtime choice exists in the authored node',1<=choice<=int(prop('DialogueChoiceCount')),{'node':node,'choice':choice})
            action('ChooseDialogue',choice)
            S['record'].setdefault('choices',[]).append({'node':node,'index':choice,'before':before})
            if available and choice<=len(available):
                expected=available[choice-1].get('next')
                if expected:check('Only the selected response branch begins',str(prop('DialogueNodeId'))==expected,{'expected':expected,'actual':str(prop('DialogueNodeId'))})
            yield wait(.025);continue
        if node=='C2_09.continuation' and int(prop('LineIndex'))==len(NODES[node]['lines'])-1:
            check('Chapter completion waits for the final manual advance',not prop('Chapter2Complete'))
        if S['accelerated']:S['manager'].set_editor_property('MinimumLineSeconds',.015)
        minimum=float(prop('MinimumLineSeconds'))
        yield until(lambda:float(prop('LineElapsed'))>=float(prop('MinimumLineSeconds')),'readable minimum line hold',5)
        action('AdvanceDialogue');yield wait(max(.025,min(.06,minimum)))
    check_channels()


def settle_transition(expected_era):
    yield until(lambda:int(prop('Mode'))!=7,'safe fade destination restored',15)
    yield wait(.15)
    check('Transition applies the requested era',int(prop('EraIndex'))==expected_era,snapshot())
    check('Transition restores one protagonist without a duplicate copy',len(unreal.GameplayStatics.get_all_actors_of_class(S['world'],unreal.Character))==1)


def confirm_travel(expected_era):
    previous=int(prop('EraIndex'))
    action('ConfirmWatch')
    check('Confirmation begins a fade before committing the new era',int(prop('Mode'))==7 and int(prop('EraIndex'))==previous)
    slot_file=ROOT/'Saved/SaveGames'/(str(prop('SaveSlot'))+'.sav')
    committed_digest=hash_file(slot_file)
    action('SaveProgress')
    check('An in-progress fade cannot overwrite the committed save',hash_file(slot_file)==committed_digest)
    yield from settle_transition(expected_era)


def read_photo(case,check_hold=False):
    yield from interact('PhotoActor')
    if check_hold and int(prop('Mode'))==3:
        check('Production minimum subtitle hold defaults to 0.75 seconds',float(prop('MinimumLineSeconds'))>=.75)
        signature=(str(prop('DialogueNodeId')),int(prop('LineIndex')))
        if float(prop('LineElapsed'))<float(prop('MinimumLineSeconds')):
            action('AdvanceDialogue')
            check('Immediate advance does not bypass the subtitle hold',signature==(str(prop('DialogueNodeId')),int(prop('LineIndex'))))
    S['accelerated']=True
    yield from dialogue(case)
    check('Photo exchange discovers the source photograph',prop('PhotoSeen') and int(prop('Mode'))==1)
    action('FlipPhoto');yield wait(.04)
    check('Photograph reverse uses the supplied inscription',ORIGINAL_BACK in str(prop('PanelText')))
    action('CloseModal')
    count=len(S['record']['spoken_lines'])
    yield from interact('PhotoActor')
    check('Repeat photo inspection does not replay the exchange',int(prop('Mode'))==1 and len(S['record']['spoken_lines'])==count)
    action('CloseModal')


def read_letter(case):
    yield from interact('LetterActor')
    check('Unsent letter is readable independently of a texture',int(prop('Mode'))==2 and ORIGINAL_LETTER in str(prop('PanelText')))
    # This is the native Mode-2 E action; generic modal dismissal cancels it.
    action('CloseDocument');yield wait(.04)
    yield from dialogue(case)
    check('Letter exchange commits only its discovery',prop('LetterRead'))


def legacy_preflight():
    fixture=ROOT/'Saved/SaveGames/Yesterday_Automation_A_v1_20261024T151953_576332_FirstPerson.sav'
    if not fixture.exists():raise RuntimeError('Expected byte-identical legacy A fixture is absent: '+str(fixture))
    case={'id':'Legacy_A_Migration','map':'House_FirstPerson'}
    S['step']='legacy A native SaveGame migration';begin_case(case,fixture)
    yield until(ready,'legacy A SaveGame migration');prepare_world();yield wait(.12)
    check('Legacy A discoveries and repair survive native class migration',all(bool(prop(n)) for n in FIELDS[:13]),snapshot())
    check('Legacy progress suppresses recollections without granting a new Mother response',prop('IntroSeen') and int(prop('Mode'))==0 and int(prop('MotherOpeningResponse'))==0)
    check('A previously calibrated watch keeps both completed tests',prop('WatchCalibrated') and int(prop('CalibrationTests'))==2)
    check('Migration does not invent a Chapter 2 observation or reward',not any(bool(prop(n)) for n in ['NeriMet','OriginalMemorialRead','ConsequenceObserved','Chapter2Complete','CanvasOwned']) and int(prop('HealerTrust'))==0 and int(prop('StormCover'))==0 and not list(prop('TrustEventIds')))
    expected=snapshot();yield from restart_and_check(expected,'migrated legacy A progress')
    check('Migrated save writes schema 2 only in the isolated slot',int(prop('SaveRef').get_editor_property('SchemaVersion'))==2)
    check('Legacy source fixture remains byte-identical',hash_file(fixture)==S['record']['legacy_fixture']['sha256'])
    LEVEL.editor_request_end_play();yield until(lambda:not LEVEL.is_in_play_in_editor(),'stop legacy migration preflight')
    original=S['record']['original_save_slot'];restore_override()
    check('Migration leaves the original user save byte-identical',hash_file(ROOT/'Saved/SaveGames'/(original+'.sav'))==S['record']['original_save_digest_before'])
    S['record']['passed']=all(c['passed'] for c in S['record']['checks'])
    REPORT['legacy_migration']=S['record'];S['record']=None;write();yield wait(.1)


def restart_and_check(expected,label):
    action('SaveProgress')
    slot=str(prop('SaveSlot'));save_file=ROOT/'Saved/SaveGames'/(slot+'.sav')
    yield until(lambda:save_file.exists(),'native SaveGame file written',5)
    S['record'].setdefault('save_files',[]).append({'label':label,'path':str(save_file),'bytes':save_file.stat().st_size})
    LEVEL.editor_request_end_play();yield until(lambda:not LEVEL.is_in_play_in_editor(),'stop PIE for '+label)
    LEVEL.editor_request_begin_play();yield until(ready,'restarted native game for '+label)
    prepare_world();yield wait(.12)
    restored=snapshot()
    stable={k:v for k,v in expected.items() if k!='ReturnClockSeconds'}
    check('Committed state survives restart: '+label,all(restored[k]==v for k,v in stable.items()),{'expected':stable,'restored':restored})
    check('Return clock does not rewind across restart',restored['ReturnClockSeconds']>=expected['ReturnClockSeconds']-.5,{'before':expected['ReturnClockSeconds'],'after':restored['ReturnClockSeconds']})
    check('Load restores the committed era without a half-transition',int(prop('EraIndex'))==expected['EraIndex'] and int(prop('Mode'))!=7)
    S['accelerated']=True
    return restored


def finish_case():
    LEVEL.editor_request_end_play();yield until(lambda:not LEVEL.is_in_play_in_editor(),'end completed route')
    original=S['record']['original_save_slot'];restore_override()
    digest=hash_file(ROOT/'Saved/SaveGames'/(original+'.sav'))
    S['record']['original_save_digest_after']=digest
    check('Original user save remains byte-identical',digest==S['record']['original_save_digest_before'])
    S['record']['passed']=all(c['passed'] for c in S['record']['checks'])
    REPORT['routes'].append(S['record']);S['record']=None;write();yield wait(.1)


def scenario():
    yield from legacy_preflight()
    for case in CASES:
        S['step']=case['id']+': fresh present opening';begin_case(case)
        yield until(ready,'native player and dialogue manager');prepare_world();yield wait(.10)
        check('Fresh route uses only its isolated save slot',str(prop('SaveSlot')).startswith('Yesterday_Chapters12_QA_'+STAMP))
        check('No new-game quest progress is manufactured',not any(bool(prop(n)) for n in IMPORTANT_INITIAL),snapshot())
        check('Authored object and NPC references exist',all(prop(ref) for ref in REFS))
        if case['skip_intro']:
            before={n:plain(prop(n)) for n in IMPORTANT_INITIAL}
            action('SkipRecollections');yield wait(.06)
            check('Skipping recollections grants no undiscovered clues or quest rewards',all(plain(prop(n))==v for n,v in before.items()))
            check('Skipped recollections are recorded once',prop('IntroSeen'))
        else:
            yield from dialogue(case)
            check('All three labeled recollections complete once',prop('IntroSeen'))
        if int(prop('Mode'))!=0:action('CloseModal')
        # Early Mother conversation is noncommitting and gives no penalty.
        S['step']=case['id']+': noncommitting early Mother conversation'
        yield from interact('MotherActor')
        check('Mother dialogue keeps the player camera free',not S['controller'].is_look_input_ignored())
        yield from dialogue(case)
        check('Early Mother conversation cannot complete the departure talk',not prop('MotherSpoken') and int(prop('MotherOpeningResponse'))==0)
        if case['letter_first']:
            S['accelerated']=True;yield from read_letter(case);yield from read_photo(case,False)
        else:
            yield from read_photo(case,case is CASES[0]);yield from read_letter(case)
        S['step']=case['id']+': Mother opening response'
        yield from interact('MotherActor')
        if case is CASES[0]:
            yield from dialogue(case,stop_at_choice=True)
            check('No response is selected before the player chooses',int(prop('MotherOpeningResponse'))==0)
            action('OpenPause');yield wait(.03);action('CloseModal')
            check('Pause cannot choose a default response',int(prop('MotherOpeningResponse'))==0 and not prop('MotherSpoken'))
            if int(prop('Mode'))!=3:yield from interact('MotherActor')
        yield from dialogue(case)
        check('Mother response is saved without a trust penalty',prop('MotherSpoken') and int(prop('MotherOpeningResponse'))==case['mother'] and int(prop('HealerTrust'))==0)

        S['step']=case['id']+': prepared contact and two tests'
        yield from interact('BenchActor');yield from dialogue(case)
        check('The existing mechanism identifies its slipped contact',prop('RepairIdentified'))
        yield from interact('ComponentActor');check('Prepared contact collected once',prop('ComponentCollected'))
        collected=snapshot();action('PickupComponent')
        check('Contact cannot be duplicated',snapshot()==collected)
        yield from interact('BenchActor');yield from dialogue(case)
        check('Actual bench placement secures the contact',prop('ComponentPlaced') and not prop('WatchCalibrated'))
        if case is CASES[0]:
            yield from interact('BenchActor')
            check('Unfinished calibration begins a timed native test',prop('Testing') and int(prop('Mode'))==4)
            action('OpenPause');yield wait(.04)
            check('Pause safely cancels only the unfinished test',not prop('Testing') and int(prop('CalibrationTests'))==0 and not prop('WatchCalibrated') and prop('ComponentPlaced'))
            action('CloseModal');yield wait(.04)
        for number in [1,2]:
            yield from interact('BenchActor')
            yield until(lambda:not bool(prop('Testing')),'native calibration test '+str(number),8)
            yield from dialogue(case)
            check('Calibration stable test '+str(number)+' completes',int(prop('CalibrationTests'))>=number)
        check('Two stable tests calibrate the watch',prop('WatchCalibrated') and int(prop('CalibrationTests'))==2)
        if case['memorial']:
            yield from interact('MemorialActor')
            check('Original memorial caption is separately readable',int(prop('Mode'))==2 and ORIGINAL_PLAQUE in ' '.join(str(prop('PanelText')).split()))
            action('CloseDocument');yield wait(.04);yield from dialogue(case)
            check('Original memorial is an observed prior-history record',prop('OriginalMemorialRead') and ORIGINAL_PLAQUE in str(prop('PriorTimelineObservation')))
        else:check('Skipped memorial remains undiscovered',not prop('OriginalMemorialRead') and not str(prop('PriorTimelineObservation')))
        S['step']=case['id']+': anchored departure'
        if case is CASES[0]:
            yield from focus('AnchorActor');action('OpenWatch');yield wait(.04)
            check('Watch opens before registering its nearby anchor',int(prop('Mode'))==4 and not prop('AnchorActivated'))
            action('Interact');yield wait(.04)
            check('Watch modal prevents exploration input falling through to the anchor',int(prop('Mode'))==4 and not prop('AnchorActivated') and not prop('DepartureDone'))
            action('CloseModal')
        yield from interact('AnchorActor')
        if bool(prop('MotherMoving')):
            check('Departure exchange waits for Mother to reach the gate',int(prop('Mode'))!=3 and not prop('DepartureDone'))
            yield until(lambda:not bool(prop('MotherMoving')),'Mother walks to the gate through native NPC movement',18)
            yield from interact('AnchorActor')
        yield from dialogue(case)
        check('Departure dialogue does not travel without confirmation',int(prop('EraIndex'))==0)
        action('RotateDial',-1)
        check('Anticlockwise dial selects the authored earlier era only',int(prop('SelectedEra'))==1 and int(prop('EraIndex'))==0)
        yield from confirm_travel(1)
        check('Optional absent pause test does not block departure',int(prop('EraIndex'))==1)
        time_before=float(prop('ReturnClockSeconds'));yield wait(.2)
        check('Return signal clock advances during the past excursion',float(prop('ReturnClockSeconds'))>time_before)

        S['step']=case['id']+': Neri and Healer'
        yield from interact('NeriActor');yield from dialogue(case)
        check('Neri meeting reveals the clinic route',prop('NeriMet'))
        S['record']['temporary_refusal_pending']=case['refuse_linen']
        yield from interact('HealerActor');yield from dialogue(case)
        if case['refuse_linen']:
            check('Temporary linen refusal is not betrayal',int(prop('LinenState'))==0 and int(prop('HealerTrust'))==0)
            yield from interact('HealerActor');yield from dialogue(case)
        check('Explicit acceptance starts the linen task',int(prop('LinenState'))==1)
        yield from interact('WaterActor')
        if int(prop('Mode'))==3:yield from dialogue(case)
        if int(prop('Mode'))!=0:action('CloseModal')
        yield from interact('SelaActor');yield from dialogue(case)
        check('A conversation alone does not physically deliver linen',int(prop('LinenState'))<3 and int(prop('HealerTrust'))==0)
        yield from interact('LinenActor')
        check('Wrapped clinic linen is physically collected',int(prop('LinenState'))==2)
        # Returning now must explain the pending practical task.
        yield from focus('AnchorActor');action('OpenWatch');action('RotateDial',1);action('ConfirmWatch');yield wait(.06)
        check('Unsafe partial linen delivery blocks guided return',int(prop('EraIndex'))==1 and int(prop('Mode'))!=7 and int(prop('LinenState'))==2)
        check('Blocked return explains the pending task',len(str(prop('Notice'))+str(prop('Objective')))>12)
        action('CloseModal')
        if case is CASES[0]:yield from restart_and_check(snapshot(),'past carrying clinic linen')
        yield from interact('LinenTrayActor');yield from dialogue(case)
        check('Physical linen delivery commits once with +10 trust',int(prop('LinenState'))==3 and int(prop('HealerTrust'))==10)
        delivered=snapshot();yield from interact('LinenTrayActor',False)
        check('Repeated delivery cannot repeat trust or inventory',int(prop('LinenState'))==3 and int(prop('HealerTrust'))==10 and list(prop('TrustEventIds'))==delivered['TrustEventIds'])
        if int(prop('Mode'))==3:yield from dialogue(case)
        if int(prop('Mode'))!=0:action('CloseModal')

        S['step']=case['id']+': canvas plan and physical installation'
        yield from interact('HealerActor');yield from dialogue(case)
        S['record']['next_canvas_choice']=3 if case['plan_change'] else case['cover']
        yield from interact('SelaActor');yield from dialogue(case)
        check('A canvas plan does not commit history',int(prop('StormCover'))==0 and int(prop('HealerTrust'))==10)
        for ref in ['ClinicInstallActor','HarborInstallActor']:
            yield from interact(ref,False)
            check('Inspecting an uncovered site cannot create a record',int(prop('StormCover'))==0)
            if int(prop('Mode'))==3:yield from dialogue(case)
            if int(prop('Mode'))!=0:action('CloseModal')
        if case['plan_change']:
            check('Not-yet choice leaves the plan uncommitted',int(prop('CanvasPlan'))==0)
            S['record']['next_canvas_choice']=1
            yield from interact('SelaActor');yield from dialogue(case)
            check('Player can plan the clinic before installation',int(prop('CanvasPlan'))==1 and int(prop('StormCover'))==0)
            S['record']['next_canvas_choice']=2
            yield from interact('SelaActor');yield from dialogue(case)
            check('Player can change the plan to harbor before installation',int(prop('CanvasPlan'))==2 and int(prop('StormCover'))==0)
        yield from interact('CanvasActor')
        check('Only one waterproof canvas is physically obtained',prop('CanvasOwned') and int(prop('StormCover'))==0)
        owned=snapshot();yield from interact('CanvasActor',False)
        check('The one canvas cannot be duplicated',bool(prop('CanvasOwned')) and int(prop('StormCover'))==0 and int(prop('HealerTrust'))==10)
        if int(prop('Mode'))!=0:action('CloseModal')
        if case['plan_change']:yield from restart_and_check(snapshot(),'past carrying planned canvas')
        ref='ClinicInstallActor' if case['cover']==1 else 'HarborInstallActor'
        other='HarborInstallActor' if case['cover']==1 else 'ClinicInstallActor'
        yield from interact(ref)
        check('Physical installation atomically consumes and commits canvas',not prop('CanvasOwned') and int(prop('StormCover'))==case['cover'] and int(prop('HealerTrust'))==30)
        yield from dialogue(case)
        history=snapshot();yield from interact(other,False)
        check('Competing site cannot install the same canvas',int(prop('StormCover'))==case['cover'] and not prop('CanvasOwned') and int(prop('HealerTrust'))==30 and list(prop('TrustEventIds'))==history['TrustEventIds'])
        if int(prop('Mode'))==3:yield from dialogue(case)
        if int(prop('Mode'))!=0:action('CloseModal')
        events=list(prop('TrustEventIds'))
        check('Authored relationship rewards are unique and never force 100 trust',len(events)==len(set(map(str,events))) and len(events)==2 and int(prop('HealerTrust'))==30)
        yield from interact('HealerActor');yield from dialogue(case)
        check('Reporting the committed outcome unlocks guided return',prop('HealerReportDone'))
        action('OpenWatch');yield wait(.03)
        action('RequestPerspective');yield wait(.03)
        check('Thirty trust cannot unlock the later perspective scene','PERSPECTIVE UNAVAILABLE' in str(prop('Notice')).upper() and int(prop('HealerTrust'))==30 and int(prop('EraIndex'))==1)
        action('CloseModal')
        yield screenshot('Past_Completed_Choice')

        S['step']=case['id']+': return and observed present consequence'
        yield from interact('AnchorActor');yield from dialogue(case)
        action('RotateDial',1)
        check('Clockwise dial selects later present without auto-travel',int(prop('SelectedEra'))==0 and int(prop('EraIndex'))==1)
        yield from confirm_travel(0)
        check('Exactly one saved archive record is displayed',visible(prop('ClinicRecordActor'))==(case['cover']==1) and visible(prop('HarborRecordActor'))==(case['cover']==2))
        yield from interact('MemorialActor')
        action('CloseDocument');yield wait(.04)
        yield from dialogue(case)
        check('The observed record follows installed cover, not an old plan',prop('ConsequenceObserved') and int(prop('StormCover'))==case['cover'])
        expected_first={
            (1,True):'This frame was empty.',(1,False):'They wrote the names down. In the courtyard.',
            (2,True):"There weren't any names here before.",(2,False):'The departure list. They managed to record everyone waiting there.'}[(case['cover'],case['memorial'])]
        spoken=[row['text'] for row in S['record']['spoken_lines']]
        check('Consequence uses the correct remembered/unremembered variant',expected_first in spoken)
        text='\n'.join(row['PanelText'] for row in S['record'].get('ui_text_observed',[]))
        expected_caption=CLINIC_CAPTION if case['cover']==1 else HARBOR_CAPTION
        check('The bounded archive has its authored consequence caption',expected_caption in ' '.join(text.split()))
        if case['memorial']:check('The traveler retains the original memorial observation',ORIGINAL_PLAQUE in str(prop('PriorTimelineObservation')))
        else:check('The journal does not invent an unobserved original display',not prop('OriginalMemorialRead') and not str(prop('PriorTimelineObservation')))
        yield screenshot('Present_Archive')
        if bool(prop('MotherMoving')):
            yield from interact('MotherActor')
            check('Walking Mother invites the surviving-room ending without starting it outside',int(prop('Mode'))!=3 and not prop('Chapter2Complete') and int(prop('FinalResponse'))==0)
        yield until(lambda:not bool(prop('MotherMoving')) and prop('MotherActor').get_distance_to(prop('MotherHomeDestinationActor'))<=90,'Mother walks home through the native NPC route',18)
        yield from interact('MotherActor');yield from dialogue(case)
        check('Every honest final response leads to chapter completion',prop('Chapter2Complete') and int(prop('EraIndex'))==0 and int(prop('FinalResponse'))==case['ending'])
        if int(prop('Mode'))!=0:action('CloseModal')
        action('OpenJournal');yield wait(.05)
        action('TurnJournal',1);action('TurnJournal',1);yield wait(.05)
        journal=' '.join(str(prop('PanelText')).split())
        check('Final journal preserves the appropriate timeline perspective',(JOURNAL_OBSERVED if case['memorial'] else JOURNAL_UNOBSERVED) in journal)
        yield screenshot('Final_Journal')
        action('CloseModal')
        completed=snapshot();yield from restart_and_check(completed,'completed present consequence')
        check('Archive restoration reads committed history after restart',visible(prop('ClinicRecordActor'))==(case['cover']==1) and visible(prop('HarborRecordActor'))==(case['cover']==2))
        check('Persisted history does not replay trust rewards',int(prop('HealerTrust'))==30 and list(prop('TrustEventIds'))==completed['TrustEventIds'])
        for ref in ['HealerActor','SelaActor','NeriActor']:
            label=prop(ref).get_actor_label().lower()
            check('Player-facing NPC label preserves the Healer secret: '+ref,'elias' not in label and 'father' not in label)
        S['record']['final_state']=snapshot()
        yield from finish_case()


def finish(error=None):
    global closing
    if closing:return
    closing=True
    if error:REPORT['error']=error
    if LEVEL.is_in_play_in_editor():LEVEL.editor_request_end_play()
    else:complete_finish()


def complete_finish():
    try:
        restore_override()
        if S.get('current_map'):LEVEL.load_level(S['current_map'])
    except Exception:REPORT['cleanup_error']=traceback.format_exc()
    REPORT['success']='error' not in REPORT and REPORT.get('legacy_migration',{}).get('passed',False) and len(REPORT['routes'])==len(CASES) and all(r['passed'] for r in REPORT['routes'])
    write()
    if handle is not None:unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.log('CHAPTERS_1_2_RUNTIME_VALIDATION '+json.dumps(REPORT,ensure_ascii=False))
    unreal.SystemLibrary.quit_editor()


runner=scenario()
def tick(delta):
    global pending,deadline
    try:
        if closing:
            if not LEVEL.is_in_play_in_editor():complete_finish()
            return
        now=time.monotonic()
        if pending:
            if 'seconds' in pending:
                if now<deadline:return
            elif 'predicate' in pending:
                if not pending['predicate']():
                    if now>deadline:raise TimeoutError(pending['description'])
                    return
            elif 'screenshot' in pending:
                path=pending['screenshot']
                if not path.exists() or path.stat().st_size<15000:
                    if now>deadline:raise TimeoutError(pending['description'])
                    return
                REPORT['screenshots'].append(str(path));write()
            pending=None
        pending=next(runner)
        deadline=now+pending.get('seconds',pending.get('timeout',30))
        write()
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())

write()
handle=unreal.register_slate_post_tick_callback(tick)
