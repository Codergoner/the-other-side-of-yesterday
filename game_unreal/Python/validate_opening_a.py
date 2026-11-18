"""Exercise Milestone A in actual PIE using native Blueprint action functions.

Run only after the Opening assets and both Home maps have finished building:
  UnrealEditor.exe YesterdayHarbor.uproject -unattended -nosplash -nosound
    -ExecutePythonScript=<forward/slash/path/to/this/file>

This test deliberately uses isolated save slots. It does not save map edits,
delete any save, write story flags directly, or simulate OS keyboard success.
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

ROOT = Path(unreal.Paths.project_dir()).resolve()
REPORT_PATH = ROOT/'opening_a_runtime_validation.json'
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
SCREENS = ROOT/'validation'/'opening_a'/STAMP
SCREENS.mkdir(parents=True,exist_ok=True)
MAPS = ['/Game/Home/Maps/House_ThirdPerson','/Game/Home/Maps/House_FirstPerson']
MANAGER_PATH = '/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C'
FLAGS = ['HomeExplored','PhotoSeen','PhotoBackSeen','LetterRead','MotherMet','MotherSpoken',
         'MotherPromise','RepairIdentified','ComponentCollected','ComponentPlaced',
         'WatchCalibrated','AnchorActivated','DrawerOpen']
REFS = ['PhotoActor','LetterActor','MotherActor','BenchActor','DrawerActor','ComponentActor','AnchorActor']
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
REPORT = {'success':False,'test':'Actual Play In Editor: Milestone A, camera ray selection, action functions, interruption and restart',
          'run':STAMP,'maps':[],'screenshots':[],
          'input_scope':'Native runtime Blueprint action functions and native camera/ray eligibility; OS key injection is not claimed.',
          'save_policy':'Per-camera unique Yesterday_Automation_A_v1 slots; no existing save deleted or overwritten.'}
state = {'world':None,'pawn':None,'manager':None,'controller':None,'camera':None,
         'record':None,'editor_override':None,'blocker':None,'step':'startup'}
handle = None
pending = None
deadline = 0.0
closing = False


def vector(v):
    return [round(v.x,3),round(v.y,3),round(v.z,3)]


def distance(a,b):
    return math.sqrt((a.x-b.x)**2+(a.y-b.y)**2+(a.z-b.z)**2)


def prop(name):
    return state['manager'].get_editor_property(name)


def action(name,*args):
    return state['manager'].call_method(name,args=tuple(args))


def flags():
    return {name:bool(prop(name)) for name in FLAGS}


def write():
    REPORT['active_step'] = state['step']
    if state.get('record'):
        REPORT['active_record'] = state['record']
    REPORT_PATH.write_text(json.dumps(REPORT,indent=2),encoding='utf-8')


def check(name,condition,details=None):
    row = {'name':name,'passed':bool(condition)}
    if details is not None:
        row['details'] = details
    if not condition:
        try:
            target = prop('Target')
            row['runtime_state'] = {'mode':int(prop('Mode')),'flags':flags(),
                'target':target.get_name() if target else None,'notice':str(prop('Notice')),
                'panel_title':str(prop('PanelTitle')),'panel_text':str(prop('PanelText')),
                'testing':bool(prop('Testing')),'pawn_cm':vector(state['pawn'].get_actor_location())}
        except Exception:
            pass
    state['record']['checks'].append(row)
    write()
    if not condition:
        raise AssertionError(name+': '+str(details))


def observe(name,condition,details):
    """Record presentation failures without discarding later functional coverage."""
    state['record']['checks'].append({'name':name,'passed':bool(condition),
        'category':'presentation','nonfatal_for_remaining_test_steps':True,'details':details})
    write()


def wait(seconds=.12):
    return {'seconds':seconds}


def until(predicate,description,timeout=20):
    return {'predicate':predicate,'description':description,'timeout':timeout}


def screenshot(label):
    path = SCREENS/(state['record']['camera_mode']+'_'+label+'.png')
    command = 'shot showui filename="'+str(path).replace('\\','/')+'" -nosuffix'
    unreal.SystemLibrary.execute_console_command(state['world'],command)
    return {'screenshot':path,'description':'game viewport HUD screenshot '+label,'timeout':20}


def find_manager(world):
    cls = unreal.load_class(None,MANAGER_PATH)
    if not cls:
        raise RuntimeError('Opening manager class has not been built: '+MANAGER_PATH)
    found = unreal.GameplayStatics.get_all_actors_of_class(world,cls)
    if len(found)!=1:
        raise RuntimeError('Expected one Opening manager, found '+str(len(found)))
    return found[0]


def ready():
    world = EDITOR.get_game_world()
    if world is None:
        return False
    pawn = unreal.GameplayStatics.get_player_character(world,0)
    if pawn is None or pawn.get_controller() is None:
        return False
    state.update(world=world,pawn=pawn,controller=pawn.get_controller(),
                 camera=unreal.GameplayStatics.get_player_camera_manager(world,0),manager=find_manager(world))
    return state['camera'] is not None


def restore_override():
    pair = state.get('editor_override')
    if pair:
        actor,original = pair
        try:
            actor.set_editor_property('SaveSlot',original)
        except Exception:
            pass
        state['editor_override'] = None


def begin_run(map_path,slot):
    if not LEVEL.load_level(map_path):
        raise RuntimeError('Cannot load '+map_path)
    editor_world = EDITOR.get_editor_world()
    state['current_map'] = map_path
    manager = find_manager(editor_world)
    original = manager.get_editor_property('SaveSlot')
    state['editor_override'] = (manager,original)
    manager.set_editor_property('SaveSlot',slot)
    state['record']['original_editor_save_slot'] = original
    original_file = ROOT/'Saved'/'SaveGames'/(str(original)+'.sav')
    state['record']['user_save_digest_before'] = file_hash(original_file)
    LEVEL.editor_request_begin_play()


def prepare_game():
    unreal.GameplayStatics.set_game_paused(state['world'],False)
    for command in ['t.IdleWhenNotForeground 0','Slate.bAllowThrottling 0','r.ScreenPercentage 100']:
        unreal.SystemLibrary.execute_console_command(state['world'],command)


def position_pawn(location):
    movement = state['pawn'].get_component_by_class(unreal.CharacterMovementComponent)
    movement.stop_movement_immediately()
    state['pawn'].set_actor_location(location,False,True)


def interaction_point(actor):
    # Skeletal actors are rooted at their feet; inspect their torso instead.
    if actor==prop('MotherActor'):
        return actor.get_actor_bounds(False)[0]
    return actor.get_actor_location()


def aim_at(actor):
    point = interaction_point(actor)
    camera_pos = state['camera'].get_camera_location()
    rotation = unreal.MathLibrary.find_look_at_rotation(camera_pos,point)
    state['controller'].set_control_rotation(rotation)


def ray_debug(target):
    data = {'mode':int(prop('Mode')),'pawn_cm':vector(state['pawn'].get_actor_location()),
            'target_cm':vector(target.get_actor_location()),'aim_point_cm':vector(interaction_point(target)),
            'target_actor':target.get_name(),'target_tags':[str(t) for t in target.get_editor_property('tags')],
            'interaction_range_cm':float(prop('InteractionRange')),
            'manager_player':prop('Player').get_name() if prop('Player') else None,
            'manager_camera':prop('Camera').get_name() if prop('Camera') else None,
            'distance_to_target_cm':round(state['pawn'].get_distance_to(target),2)}
    try:
        start = state['camera'].get_camera_location()
        rotation = state['camera'].get_camera_rotation()
        forward = unreal.MathLibrary.get_forward_vector(rotation)
        end = start+forward*900
        ignored = list(prop('IgnoredActors'))
        hit = unreal.SystemLibrary.line_trace_single(state['world'],start,end,
                    unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[state['pawn']],unreal.DrawDebugTrace.NONE,True)
        values = hit.to_tuple() if hasattr(hit,'to_tuple') else unreal.GameplayStatics.break_hit_result(hit)
        actor = values[9]
        data.update(camera_cm=vector(start),camera_rotation=[rotation.pitch,rotation.yaw,rotation.roll],
                    control_rotation=str(state['controller'].get_control_rotation()),
                    ignored_actors=[a.get_name() for a in ignored if a],
                    blocking=bool(values[0]),hit_actor=actor.get_name() if actor else None,
                    hit_actor_tags=[str(t) for t in actor.get_editor_property('tags')] if actor else [],
                    hit_actor_label=actor.get_actor_label() if actor else None,
                    hit_point_cm=vector(values[5]))
        if prop('Camera'):
            data['manager_camera_cm'] = vector(prop('Camera').get_camera_location())
        for name in ['DebugTraceStart','DebugTraceEnd','DebugTraceHit','DebugHitActor',
                     'DebugHasTag','DebugTagAllowed','DebugDistance','DebugWithinRange','DebugModeAllowed']:
            try:
                value = prop(name)
                if isinstance(value,unreal.Vector):value=vector(value)
                elif isinstance(value,unreal.Object):value=value.get_name()
                elif not isinstance(value,(bool,int,float,str,type(None))):value=str(value)
                data[name] = value
            except Exception:
                pass
        component = target.get_component_by_class(unreal.PrimitiveComponent)
        if component:
            data['target_collision_enabled'] = str(component.get_collision_enabled())
            data['target_collision_profile'] = str(component.get_collision_profile_name())
    except Exception:
        data['debug_error'] = traceback.format_exc()
    return data


def select(ref):
    """Find an unobstructed nearby standing point, then use the real camera ray."""
    target = prop(ref)
    if target is None:
        raise RuntimeError('Missing authored actor reference '+ref)
    if int(prop('Mode'))!=0:
        action('CloseModal')
        yield wait(.08)
    origin = target.get_actor_location()
    attempts = []
    preferred = {'BenchActor':[(190,0)],'MotherActor':[(200,45)],
                 'DrawerActor':[(100,-125)],'ComponentActor':[(100,-125)],
                 'AnchorActor':[(0,-155)]}.get(ref,[])
    for dx,dy in preferred+[(160,80),(190,0),(160,-80),(0,-185),(0,185),(-170,-70),(-170,70)]:
        # All Milestone A props are on the surviving ground floor / porch.
        position_pawn(unreal.Vector(origin.x+dx,origin.y+dy,1109))
        yield wait(.12)
        for repeat in range(12):
            aim_at(target)
            yield wait(.06)
        action('UpdateTarget')
        chosen = prop('Target')
        attempts.append({'stand_cm':vector(state['pawn'].get_actor_location()),
                         'target':chosen.get_name() if chosen else None,'prompt':str(prop('Prompt')),
                         'ray':ray_debug(target)})
        if chosen==target:
            state['record'].setdefault('ray_selections',[]).append({'reference':ref,'attempts':attempts})
            write()
            return
    raise AssertionError('No actual unobstructed camera ray could select '+ref+': '+json.dumps(attempts))


def interact(ref):
    yield from select(ref)
    action('Interact')
    yield wait(.08)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def scenario():
    for map_path in MAPS:
        mode = map_path.rsplit('_',1)[-1]
        slot = 'Yesterday_Automation_A_v1_'+STAMP+'_'+mode
        record = {'map':map_path,'camera_mode':mode,'save_slot':slot,'checks':[],'ray_selections':[]}
        state['record'] = record
        state['step'] = mode+': start fresh PIE'
        begin_run(map_path,slot)
        yield until(ready,'possessed native Character and Opening manager')
        prepare_game()
        yield wait(.5)
        check('Dedicated automation save slot inherited by PIE actor',prop('SaveSlot')==slot,str(prop('SaveSlot')))
        check('Fresh isolated save begins without committed story flags',not any(flags().values()),flags())
        record['pawn_class'] = state['pawn'].get_class().get_path_name()
        record['controller_class'] = state['controller'].get_class().get_path_name()
        check('Authored important object references exist',all(prop(name) for name in REFS))

        state['step'] = mode+': workbench story eligibility'
        yield from interact('BenchActor')
        check('Workbench cannot skip family sequence',not prop('RepairIdentified') and not prop('WatchCalibrated'),str(prop('Notice')))
        check('Workbench eligibility gives readable feedback',len(str(prop('Notice')))>10)
        action('CloseModal')

        state['step'] = mode+': photograph front and back'
        yield from select('PhotoActor')
        photo = prop('PhotoActor')
        photo_location = photo.get_actor_location()
        photo_component = photo.get_component_by_class(unreal.StaticMeshComponent)
        photo_material = photo_component.get_material(0)
        action('InspectSelected')
        yield wait(.15)
        check('Photo enters controlled inspection',int(prop('Mode'))==1 and prop('PhotoSeen'))
        held_location = photo.get_actor_location()
        cam_location = state['camera'].get_camera_location()
        try: hidden = bool(photo.get_editor_property('hidden'))
        except Exception:
            try:hidden = bool(photo.get_editor_property('bHidden'))
            except Exception:hidden = 'not exposed'
        material = photo_component.get_material(0)
        presentation = {'original_cm':vector(photo_location),'held_cm':vector(held_location),
            'camera_cm':vector(cam_location),'movement_cm':round(distance(held_location,photo_location),2),
            'distance_to_camera_cm':round(distance(held_location,cam_location),2),
            'mobility':str(photo_component.get_editor_property('mobility')),'hidden':hidden,
            'material':material.get_path_name() if material else None}
        state['record']['photo_controlled_view'] = presentation
        observe('Photo physically moves into the controlled inspection view',presentation['movement_cm']>20,presentation)
        observe('Held photograph remains approximately 78cm from the camera',55<presentation['distance_to_camera_cm']<110,presentation)
        observe('Inspection uses the temporary readable material',bool(material and 'Inspection' in material.get_name()),presentation)
        action('FlipPhoto')
        check('Reverse of photograph becomes discovered',prop('PhotoBackSeen') and prop('PhotoBack'))
        check('Handwriting is available as readable UI text',len(str(prop('PanelText')))>35,str(prop('PanelText')))
        yield screenshot('Photo_Reverse')
        action('OpenPause')
        yield wait(.1)
        check('Pause safely interrupts inspection',int(prop('Mode'))==6 and prop('HeldPhoto') is None)
        returned = photo.get_actor_location()
        check('Inspected photograph returns to its designated position',distance(returned,photo_location)<.5,
              {'original':vector(photo_location),'restored':vector(returned)})
        check('Inspection restores the original photograph material',photo_component.get_material(0)==photo_material)
        action('CloseModal')
        check('Closing pause restores exploration',int(prop('Mode'))==0 and not unreal.GameplayStatics.is_game_paused(state['world']))

        state['step'] = mode+': interaction range and obstruction'
        yield from select('PhotoActor')
        near = state['pawn'].get_actor_location()
        target_location = photo.get_actor_location()
        away = (near-target_location)*(650/max(distance(near,target_location),.001))
        position_pawn(target_location+away)
        yield wait(.15)
        aim_at(photo)
        yield wait(.1)
        action('UpdateTarget')
        check('Out-of-range object is not selected',prop('Target')!=photo)
        # Use the actual, existing rear house wall. The workbench sits just
        # inside it; the exterior standing point remains within valid range.
        # No spawned collider, response override or test-only wall is needed.
        bench = prop('BenchActor')
        bench_pos = bench.get_actor_location()
        position_pawn(unreal.Vector(bench_pos.x-190,bench_pos.y,1109))
        for repeat in range(12):
            aim_at(bench)
            yield wait(.06)
        action('UpdateTarget')
        wall = ray_debug(bench)
        state['record']['existing_wall_occlusion'] = wall
        check('Wall test remains inside interaction range',wall['distance_to_target_cm']<=float(prop('InteractionRange')),wall)
        check('Authored solid house wall blocks the camera ray',wall.get('blocking') and wall.get('hit_actor')!=bench.get_name(),wall)
        check('Existing wall prevents interaction with an otherwise nearby workbench',prop('Target')!=bench,wall)

        state['step'] = mode+': letter and Mother conversation'
        yield from interact('LetterActor')
        check('Letter is read and separately legible',prop('LetterRead') and int(prop('Mode'))==2 and len(str(prop('PanelText')))>120)
        yield screenshot('Letter')
        action('CloseModal')
        yield from interact('MotherActor')
        check('Mother opens contextual dialogue',int(prop('Mode'))==3 and prop('MotherMet'))
        action('MotherTopic')
        action('MotherOfferHelp')
        check('Conversation commits knowledge and chosen promise',prop('MotherSpoken') and prop('MotherPromise'))
        yield screenshot('Mother_Dialogue')
        mother = prop('MotherActor')
        position_pawn(mother.get_actor_location()+unreal.Vector(700,0,0))
        yield wait(.2)
        action('UpdateStep',.1)
        check('Walking away safely closes dialogue',int(prop('Mode'))==0)
        check('Dialogue interruption preserves earned progress',prop('MotherSpoken') and prop('MotherPromise'))

        state['step'] = mode+': identify, retrieve and fit repair component'
        yield from interact('BenchActor')
        check('Workbench identifies the final missing alignment component',prop('RepairIdentified') and int(prop('Mode'))==2)
        action('CloseModal')
        yield from interact('DrawerActor')
        check('Parts box opens',prop('DrawerOpen'))
        yield from interact('ComponentActor')
        check('Required component is collected once',prop('ComponentCollected'))
        before_repeat = flags()
        action('PickupComponent')
        check('Repeated component pickup cannot duplicate progress',flags()==before_repeat)
        yield from interact('BenchActor')
        check('Component is fitted at the workbench',prop('ComponentPlaced'))
        action('CloseModal')

        state['step'] = mode+': interrupt and complete calibration'
        yield from interact('BenchActor')
        check('Final calibration begins as a timed test',prop('Testing') and int(prop('Mode'))==4)
        action('OpenPause')
        check('Pause cancels unfinished calibration coherently',not prop('Testing') and not prop('WatchCalibrated') and prop('ComponentPlaced'))
        action('CloseModal')
        yield from interact('BenchActor')
        yield until(lambda:bool(prop('WatchCalibrated')),'real native Tick completes final calibration',8)
        check('Timed calibration finishes without manufacturing the watch',prop('WatchCalibrated') and not prop('Testing'))
        yield screenshot('Calibration_Complete')
        action('CloseModal')

        state['step'] = mode+': watch priority, anchor and journal'
        yield from select('AnchorActor')
        action('OpenWatch')
        check('Calibrated Chronowatch opens',int(prop('Mode'))==4 and len(str(prop('PanelText')))>100)
        action('Interact')
        check('Watch modal prevents nearby-object input overlap',int(prop('Mode'))==4 and not prop('AnchorActivated'))
        action('CloseModal')
        yield from interact('AnchorActor')
        check('First available anchor registers',prop('AnchorActivated'))
        action('OpenJournal')
        journal = str(prop('PanelText'))
        check('Journal contains discovered photograph, document and calibrated watch',all(word in journal.lower() for word in ['photograph','mother','calibration','anchor']))
        check('Journal has no undiscovered Chapter 2 identities','healer' not in journal.lower())
        yield screenshot('Journal')
        action('CloseModal')
        action('SaveProgress')
        completed = flags()
        check('Opening-loop milestone flags committed',all(completed.values()),completed)
        save_path = ROOT/'Saved'/'SaveGames'/(slot+'.sav')
        yield until(lambda:save_path.exists(),'dedicated committed SaveGame file',5)
        record['save_file'] = str(save_path)
        record['saved_flags'] = completed
        record['save_size_bytes'] = save_path.stat().st_size
        LEVEL.editor_request_end_play()
        yield until(lambda:not LEVEL.is_in_play_in_editor(),'stop PIE before restart')
        yield wait(.2)

        state['step'] = mode+': restart and restore committed progress'
        LEVEL.editor_request_begin_play()
        yield until(ready,'restarted native pawn and manager')
        prepare_game()
        yield wait(.35)
        check('Restart continues using isolated automation save slot',prop('SaveSlot')==slot)
        action('LoadProgress')
        yield wait(.15)
        check('All committed discoveries and repair flags survive restart',flags()==completed,{'expected':completed,'restored':flags()})
        check('Reload recovers a stable exploration state',int(prop('Mode'))==0 and not prop('Testing') and prop('HeldPhoto') is None)
        safe = state['pawn'].get_actor_location()
        check('Reload returns to safe porch entrance',distance(safe,unreal.Vector(120,1240,991))<50,vector(safe))
        action('OpenJournal')
        yield screenshot('Journal_After_Restart')
        action('CloseModal')
        LEVEL.editor_request_end_play()
        yield until(lambda:not LEVEL.is_in_play_in_editor(),'stop restarted PIE')
        restore_override()
        original_file = ROOT/'Saved'/'SaveGames'/(str(record['original_editor_save_slot'])+'.sav')
        record['user_save_digest_after'] = file_hash(original_file)
        check('Existing user save remains byte-identical',record['user_save_digest_before']==record['user_save_digest_after'])
        record['passed'] = all(row['passed'] for row in record['checks'])
        REPORT['maps'].append(record)
        state['record'] = None
        write()
        yield wait(.3)


def finish(error=None):
    global closing
    if closing:
        return
    closing = True
    if error:
        REPORT['error'] = error
    if LEVEL.is_in_play_in_editor():
        LEVEL.editor_request_end_play()
    else:
        complete_finish()


def complete_finish():
    try:
        if state.get('blocker') and unreal.SystemLibrary.is_valid(state['blocker']):
            state['blocker'].destroy_actor()
        restore_override()
        # Discard the temporary editor-instance override, without saving maps.
        if state.get('current_map'):
            LEVEL.load_level(state['current_map'])
    except Exception:
        REPORT['cleanup_error'] = traceback.format_exc()
    REPORT['success'] = 'error' not in REPORT and len(REPORT['maps'])==len(MAPS) and all(row['passed'] for row in REPORT['maps'])
    write()
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.log('OPENING_A_RUNTIME_VALIDATION '+json.dumps(REPORT))
    unreal.SystemLibrary.quit_editor()


runner = scenario()


def tick(delta):
    global pending,deadline
    try:
        if closing:
            if not LEVEL.is_in_play_in_editor():
                complete_finish()
            return
        now = time.monotonic()
        if pending:
            if 'seconds' in pending:
                if now<deadline:
                    return
            elif 'predicate' in pending:
                if not pending['predicate']():
                    if now>deadline:
                        raise TimeoutError(pending['description'])
                    return
            elif 'screenshot' in pending:
                path = pending['screenshot']
                if not path.exists() or path.stat().st_size<15000:
                    if now>deadline:
                        raise TimeoutError('Native game viewport screenshot did not export: '+str(path))
                    return
                REPORT['screenshots'].append(str(path))
                write()
            pending = None
        pending = next(runner)
        deadline = now+pending.get('seconds',pending.get('timeout',20))
        write()
    except StopIteration:
        finish()
    except Exception:
        finish(traceback.format_exc())


write()
handle = unreal.register_slate_post_tick_callback(tick)
