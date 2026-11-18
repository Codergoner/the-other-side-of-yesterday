"""Asynchronous native PIE continuous walk; root controls the editor launch queue.

Only AddMovementInput drives the route. One separately reported initial spawn
placement is allowed if the normal fresh checkpoint is outside the home. No
waypoint teleport, collision disable, movement-mode override or quest flag write
can turn a blocked route into a pass. This is desktop collision evidence only.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, math, time, traceback
import unreal

ROOT=Path(unreal.Paths.project_dir()).resolve()
BASELINE=ROOT.parent/'quest_baseline_manifest.json'
if not BASELINE.exists():raise RuntimeError('Restricted to protected Quest development copy')
COPY=json.loads(BASELINE.read_text(encoding='utf-8'))
if Path(COPY['quest_copy']).resolve()!=ROOT.parent:raise RuntimeError('Quest baseline path mismatch')
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
SLOT='Yesterday_Quest_Walk_QA_'+STAMP
MAP='/Game/Quest/Maps/Verdant_Desktop'
OUT=ROOT/'quest_walk_validation.json'
DETAIL=ROOT/'validation'/'quest_walk'/STAMP
DETAIL.mkdir(parents=True,exist_ok=False)
LEVEL=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

# Actual house coordinates: entry is X=-440; porch/stair top X=-220;
# six decorative stair treads sit over a real ramp ending X=-10. All are Y=1240.
# The optional arcade uses the new threshold between X=-290 and -410.
ROUTE=[
 ('home_room',[-620,1240,1011]),
 ('inside_front_door',[-480,1240,1011]),
 ('entry_threshold',[-420,1240,1011]),
 ('front_porch',[-285,1240,1011]),
 ('approach_stair_top',[-230,1240,1011]),
 ('approach_stair_middle',[-115,1240,953.5]),
 ('approach_stair_foot',[-5,1240,896]),
 ('courtyard_gate',[50,1240,896]),
 ('street_below_clinic',[50,950,925]),
 ('clinic_street',[50,740,946]),
 ('clinic_resting_bay_approach',[-75,730,947]),
 ('clinic_return_to_spine',[50,690,951]),
 ('market_approach',[50,400,980]),
 ('market_street',[30,0,1020]),
 ('arcade_street_approach',[-240,-200,1040]),
 ('arcade_threshold_outer',[-300,-200,1040.833]),
 ('arcade_doorway',[-435,-200,1050]),
 ('calm_market_arcade',[-600,-200,1050]),
 ('arcade_return_doorway',[-435,-200,1050]),
 ('arcade_return_to_street',[-240,-200,1040]),
 ('sela_service_approach',[30,-300,1050]),
 ('harbor_story_canopy_approach',[-45,-535,1073.5]),
 ('protected_sea_pause',[50,-900,1110]),
 ('upper_street',[50,-1400,1160]),
 ('true_shore_opening',[275,-1400,1160]),
 ('upper_harbor_overlook',[450,-1400,1160]),
]

def xyz(v):return [round(v.x,3),round(v.y,3),round(v.z,3)]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
def all_saves():
 bases=[ROOT,Path(COPY['original_workspace'])/'game_unreal',Path(COPY['source_development_copy'])/'game_unreal',Path.home()/'AppData/Local/YesterdayHarbor']
 files=set()
 for base in bases:
  directory=base/'Saved/SaveGames'
  if directory.exists():files.update(directory.glob('*.sav'))
  files.update(directory/(name+'.sav') for name in ['Yesterday_Quest_20261025','Yesterday_Brief_20261025','Yesterday_Opening_v1'])
 return sorted(files,key=str)

PROTECTED={p:sha(p) for p in all_saves()}
PROTECTED[ROOT/'Content/Quest/Maps/Verdant_Desktop.umap']=sha(ROOT/'Content/Quest/Maps/Verdant_Desktop.umap')
REPORT={'success':False,'run':STAMP,'map':MAP,'test_save_slot':SLOT,
 'scope':'Actual desktop PIE CharacterMovement input across the home stairs, street, clinic approach, market arcade and protected overlook',
 'input_method':'Pawn.AddMovementInput(world_direction, scale, force=False); native CharacterMovement performs all route movement',
 'route_teleports':0,'collision_disabled':False,'movement_mode_forced':False,'story_flags_written':False,
 'headset_tested':False,'performance_measured':False,'physical_keyboard_tested':False,
 'all_cities_tested':False,'full_city_loop_claimed':False,'waypoints':[], 'samples':[], 'actions':[],
 'authored_route':[{'id':name,'floor_cm':point} for name,point in ROUTE],
 'source_geometry':{'home_stairs':'build_player_house.py:81-90; local approach Y=-7.9..-5.8, rise115cm/run210cm',
  'street':'build_game_harbor.py:105-109; continuous floor=1020-0.1*UEY',
  'arcade_threshold':'build_quest_district_kit.py SM_QuestDistrict_Threshold, 120cm run/10cm rise'},
 'protected_digests_before':{str(p):v for p,v in PROTECTED.items()}}
STATE={'phase':'load','wall_start':time.monotonic(),'phase_wall':time.monotonic(),'route_index':0,'editor_override':None,
 'world':None,'pawn':None,'manager':None,'movement':None,'controller':None,'fall_since':None,'last_sample_game':-100,
 'closing':False,'close_wall':None,'handle':None,'last_write':0}

def write():
 REPORT['active_phase']=STATE['phase'];REPORT['active_waypoint']=ROUTE[min(STATE['route_index'],len(ROUTE)-1)][0]
 OUT.write_text(json.dumps(REPORT,indent=2,default=str),encoding='utf-8')
 (DETAIL/'report.json').write_text(json.dumps(REPORT,indent=2,default=str),encoding='utf-8')
 STATE['last_write']=time.monotonic()

def phase(name,game_time=0):
 STATE.update(phase=name,phase_wall=time.monotonic(),phase_game=game_time);write()

def manager_for(world):
 matches=unreal.GameplayStatics.get_all_actors_with_tag(world,'Opening.Manager')
 if len(matches)!=1:raise RuntimeError('Expected one Opening.Manager, got '+str(len(matches)))
 return matches[0]

def mode():return int(STATE['manager'].get_editor_property('Mode'))
def action(name):
 STATE['manager'].call_method(name,args=())
 REPORT['actions'].append({'action':name,'wall_seconds':round(time.monotonic()-STATE['wall_start'],3)})

def footpoint(pawn):
 p=pawn.get_actor_location();h=STATE['half_height']
 return unreal.Vector(p.x,p.y,p.z-h)

def native_sample(game_time,target=None):
 pawn=STATE['pawn'];move=STATE['movement'];foot=footpoint(pawn)
 row={'game_seconds':round(game_time,3),'foot_cm':xyz(foot),'velocity_cm_s':xyz(pawn.get_velocity()),
  'grounded':bool(move.is_moving_on_ground()),'falling':bool(move.is_falling()),
  'movement_mode':str(move.get_editor_property('movement_mode')),'story_mode':mode()}
 if target:row['distance_to_waypoint_cm']=round(math.hypot(target[0]-foot.x,target[1]-foot.y),3)
 ignored=[pawn]+list(unreal.GameplayStatics.get_all_actors_with_tag(STATE['world'],'Quest.NavigationNode'))
 hit=unreal.SystemLibrary.line_trace_single(STATE['world'],foot+unreal.Vector(0,0,25),foot-unreal.Vector(0,0,160),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,ignored,unreal.DrawDebugTrace.NONE,True)
 values=hit.to_tuple() if hit is not None else None
 row['floor_below']={'blocking':bool(values[0]),'impact_cm':xyz(values[5]),'actor':values[9].get_name() if values[9] else None} if values else {'blocking':False}
 return row

def request_finish(error=None):
 if STATE['closing']:return
 if error:REPORT['error']=error
 STATE.update(closing=True,close_wall=time.monotonic());phase('ending_pie')
 if LEVEL.is_in_play_in_editor():LEVEL.editor_request_end_play()

def finish():
 try:
  pair=STATE.get('editor_override')
  if pair:pair[0].set_editor_property('SaveSlot',pair[1])
  # Reload discards the temporary in-memory test-slot edit. Never save the map.
  if not LEVEL.load_level(MAP):raise RuntimeError('Failed to reload untouched desktop map on cleanup')
 except Exception:REPORT['cleanup_error']=traceback.format_exc()
 REPORT['protected_digests_after']={str(p):sha(p) for p in PROTECTED}
 REPORT['protected_files_unchanged']=all(sha(p)==old for p,old in PROTECTED.items())
 REPORT['continuous_walking_tested']=bool(REPORT['waypoints'])
 REPORT['complete_route_walked']=len(REPORT['waypoints'])==len(ROUTE) and all(w['passed'] for w in REPORT['waypoints'])
 REPORT['success']='error' not in REPORT and 'cleanup_error' not in REPORT and REPORT['complete_route_walked'] and REPORT['protected_files_unchanged']
 REPORT['wall_seconds']=round(time.monotonic()-STATE['wall_start'],3);STATE['phase']='complete';write()
 if STATE['handle'] is not None:unreal.unregister_slate_post_tick_callback(STATE['handle'])
 unreal.EditorPythonScripting.set_keep_python_script_alive(False)
 unreal.log('QUEST_CONTINUOUS_WALK_VALIDATION '+json.dumps({'success':REPORT['success'],'waypoints':len(REPORT['waypoints']),'error':REPORT.get('error')}))
 unreal.SystemLibrary.quit_editor()

def begin_segment(game_time,foot):
 index=STATE['route_index'];target=ROUTE[index][1]
 STATE.update(segment_game=game_time,progress_game=game_time,progress_distance=math.hypot(target[0]-foot.x,target[1]-foot.y),segment_start=xyz(foot),fall_since=None)

def walk_tick(game_time):
 pawn=STATE['pawn'];move=STATE['movement'];foot=footpoint(pawn)
 name,target=ROUTE[STATE['route_index']];dx,dy=target[0]-foot.x,target[1]-foot.y;distance=math.hypot(dx,dy)
 if mode()!=0:raise RuntimeError('Story mode changed during walking; input is not bypassed: '+str(mode()))
 if STATE['controller'].is_move_input_ignored():raise RuntimeError('Native controller is ignoring movement input; no force-input bypass used')
 if game_time-STATE['last_sample_game']>=.25:
  sample=native_sample(game_time,target);REPORT['samples'].append(sample);STATE['last_sample_game']=game_time
 if move.is_falling():
  if STATE['fall_since'] is None:STATE['fall_since']=game_time
  if game_time-STATE['fall_since']>1.0:raise RuntimeError('Capsule remained in falling mode for >1s near '+name+'; '+str(xyz(foot)))
 else:STATE['fall_since']=None
 previous=STATE['segment_start'];vx,vy=target[0]-previous[0],target[1]-previous[1]
 denominator=vx*vx+vy*vy
 t=max(0,min(1,((foot.x-previous[0])*vx+(foot.y-previous[1])*vy)/denominator)) if denominator else 1
 expected_z=previous[2]+(target[2]-previous[2])*t
 if foot.z<expected_z-75:raise RuntimeError('Capsule fell >75cm below authored route near '+name+'; '+str(xyz(foot)))
 if distance<=18:
  if not move.is_moving_on_ground():return # allow physical settling, never set movement mode
  error=abs(foot.z-target[2]);row={'id':name,'expected_floor_cm':target,'actual_foot_cm':xyz(foot),'floor_error_cm':round(error,3),
   'xy_error_cm':round(distance,3),'grounded':True,'passed':error<=30,'segment_game_seconds':round(game_time-STATE['segment_game'],3)}
  REPORT['waypoints'].append(row);write()
  if not row['passed']:raise RuntimeError('Wrong actual floor at '+name+': '+str(row))
  STATE['route_index']+=1
  if STATE['route_index']>=len(ROUTE):request_finish();return
  begin_segment(game_time,foot);return
 if distance<STATE['progress_distance']-7:
  STATE.update(progress_distance=distance,progress_game=game_time)
 if game_time-STATE['progress_game']>2.5:
  REPORT['stall_diagnostic']=native_sample(game_time,target)
  raise RuntimeError('Native walking collision/input stall before '+name+'; remaining='+str(round(distance,2))+'cm')
 if game_time-STATE['segment_game']>20:raise RuntimeError('Native walking segment timeout before '+name)
 # Scale down within 90cm so real braking handles turns. force=False respects
 # the controller/story input lock; no velocity, transform or collision edits.
 pawn.add_movement_input(unreal.Vector(dx/distance,dy/distance,0),min(1.0,distance/90),False)
 if time.monotonic()-STATE['last_write']>.75:write()

def tick(delta):
 try:
  if STATE['closing']:
   if not LEVEL.is_in_play_in_editor():finish()
   elif time.monotonic()-STATE['close_wall']>20:raise RuntimeError('PIE did not finish shutdown')
   return
  if time.monotonic()-STATE['wall_start']>240:raise RuntimeError('Continuous walk wall-time watchdog')
  if STATE['phase']=='load':
   if not LEVEL.load_level(MAP):raise RuntimeError('Cannot load desktop Verdant map')
   manager=manager_for(EDITOR.get_editor_world());old=manager.get_editor_property('SaveSlot')
   if str(old)!='Yesterday_Quest_20261025':raise RuntimeError('Unexpected campaign slot '+str(old))
   if (ROOT/'Saved/SaveGames'/(SLOT+'.sav')).exists():raise RuntimeError('Refusing to reuse existing QA save slot')
   STATE['editor_override']=(manager,old);manager.set_editor_property('SaveSlot',SLOT)
   LEVEL.editor_request_begin_play();phase('waiting_for_player');return
  world=EDITOR.get_game_world();pawn=unreal.GameplayStatics.get_player_character(world,0) if world else None
  if STATE['phase']=='waiting_for_player':
   if not pawn or pawn.get_controller() is None:return
   manager=manager_for(world)
   if manager.get_editor_property('Player') is None:return
   move=pawn.get_component_by_class(unreal.CharacterMovementComponent);capsule=pawn.get_component_by_class(unreal.CapsuleComponent)
   if not move or not capsule:raise RuntimeError('No native walking capsule/movement component')
   STATE.update(world=world,pawn=pawn,controller=pawn.get_controller(),manager=manager,movement=move,
    half_height=float(capsule.get_scaled_capsule_half_height()))
   REPORT['native_character']={'class':pawn.get_class().get_path_name(),'capsule_radius_cm':float(capsule.get_scaled_capsule_radius()),
    'capsule_half_height_cm':STATE['half_height'],'max_step_height_cm':float(move.get_editor_property('max_step_height')),
    'walkable_floor_angle_degrees':float(move.get_walkable_floor_angle())}
   if str(manager.get_editor_property('SaveSlot'))!=SLOT:raise RuntimeError('PIE inherited wrong save slot')
   for command in ['t.IdleWhenNotForeground 0','Slate.bAllowThrottling 0']:
    unreal.SystemLibrary.execute_console_command(world,command)
   game_time=unreal.GameplayStatics.get_time_seconds(world)
   if bool(manager.get_editor_property('IntroActive')):action('SkipRecollections')
   phase('settling_fresh_home',game_time);return
  game_time=unreal.GameplayStatics.get_time_seconds(world)
  if STATE['phase']=='settling_fresh_home':
   if game_time-STATE['phase_game']<.6:return
   if bool(STATE['manager'].get_editor_property('IntroActive')):
    action('SkipRecollections');phase('settling_fresh_home',game_time);return
   if mode()!=0:raise RuntimeError('Intro did not release movement after normal SkipRecollections action')
   foot=footpoint(pawn);target=ROUTE[0][1]
   REPORT['natural_fresh_spawn_foot_cm']=xyz(foot)
   if math.hypot(foot.x-target[0],foot.y-target[1])>80 or abs(foot.z-target[2])>45:
    desired=unreal.Vector(target[0],target[1],target[2]+STATE['half_height']+2)
    REPORT['initial_spawn_placement']={'from_foot_cm':xyz(foot),'to_capsule_center_cm':xyz(desired),'purpose':'One initial setup only, before any walked segment','counts_as_walking':False}
    pawn.set_actor_location(desired,False,True)
    phase('settling_initial_placement',game_time);return
   begin_segment(game_time,foot);phase('walking',game_time);return
  if STATE['phase']=='settling_initial_placement':
   if game_time-STATE['phase_game']<.6:return
   begin_segment(game_time,footpoint(pawn));phase('walking',game_time);return
  if STATE['phase']=='walking':walk_tick(game_time)
 except Exception:
  if STATE['closing']:
   REPORT['shutdown_error']=traceback.format_exc();finish()
  else:request_finish(traceback.format_exc())

unreal.EditorPythonScripting.set_keep_python_script_alive(True)
try:unreal.get_default_object(unreal.EditorPerformanceSettings).set_editor_property('throttle_cpu_when_not_foreground',False)
except Exception:pass
write();STATE['handle']=unreal.register_slate_post_tick_callback(tick)
