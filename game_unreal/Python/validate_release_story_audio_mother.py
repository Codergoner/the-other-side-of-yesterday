"""Queued full story/audio suite with passive production Mother-walk evidence.

Run with -ReleaseStoryQA -ReleaseStoryAudioQA -ReleaseStoryMotherQA, sound,
D3D11 and a fresh isolated -UserDir. No NPC flags, waypoints, animation poses,
player camera, world clock or assets are changed by the additive observer.
The inherited harness still uses its documented synthetic actions/positioning;
this is not physical-input, packaged performance or final-trailer evidence.
"""
from pathlib import Path
import ast
import hashlib
import json
import unreal

MOTHER_WRAPPER_SOURCE_PATH = Path(__file__).resolve()
MOTHER_WRAPPER_SOURCE_SHA = hashlib.sha256(MOTHER_WRAPPER_SOURCE_PATH.read_bytes()).hexdigest()
root = Path(unreal.Paths.project_dir()).resolve()
if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseStoryMotherQA'):
    raise RuntimeError('Root queued -ReleaseStoryMotherQA is required')
MOTHER_STORY_PROOF = json.loads((root/'release_mother_integration_report.json').read_text())
MOTHER_FLOOR_PROOF = json.loads((root/'release_mother_floor_projection_report.json').read_text())
if not MOTHER_STORY_PROOF['success'] or not MOTHER_FLOOR_PROOF['success']:
    raise RuntimeError('Actual character integration and bounded floor repair must pass before the combined suite')

# Build the already checked audio/story adaptation without registering its
# native callback. Keep __file__ accurate for its own source-provenance hash.
AUDIO_WRAPPER_PATH = root/'Python/validate_release_story_audio.py'
audio_wrapper = AUDIO_WRAPPER_PATH.read_text(encoding='utf-8')
ending = "exec(compile(source, str(root / 'Python/validate_brief_m2.py'), 'exec'), globals())"
audio_tree=ast.parse(audio_wrapper)
if ast.get_source_segment(audio_wrapper,audio_tree.body[-1])!=ending:
    raise RuntimeError('Review changed audio/story wrapper before additive Mother adaptation')
audio_prefix,audio_separator,audio_suffix=audio_wrapper.rpartition(ending)
if not audio_separator or audio_suffix.strip():
    raise RuntimeError('Audio wrapper final callback launch is no longer the checked final statement')
previous_file = globals().get('__file__')
globals()['__file__'] = str(AUDIO_WRAPPER_PATH)
try:
    exec(compile(audio_prefix+'MOTHER_STORY_SOURCE = source'+audio_suffix,str(AUDIO_WRAPPER_PATH),'exec'),globals())
finally:
    globals()['__file__'] = previous_file
source = MOTHER_STORY_SOURCE


def replace_once(old,new):
    global source
    if source.count(old)!=1:
        raise RuntimeError('Changed additive Mother acceptance point: '+old[:120])
    source=source.replace(old,new)


mother_helpers = r'''
MOTHER_OBSERVER={'active':None}

def mother_runtime_path(value):
    return value.get_path_name() if value else None

def mother_floor_height(location):
    # Existing native source ramp: worldX -220..-10, top1011 -> foot896.
    # Both actual authored routes stay on this porch or its flat home floor.
    if not (-940 <= location.x <= 0 and 1220 <= location.y <= 1430):
        raise RuntimeError('Actual Mother left the reviewed home/porch route domain')
    return 1011.0 if location.x<=-220 else 896.0+max(0,min(1,(-10-location.x)/210))*115.0

def mother_active_asset(component):
    instance=component.get_anim_instance()
    if not instance:raise RuntimeError('Mother has no actual native animation instance')
    # Installed AnimSingleNodeInstance.h:77-78 public BlueprintCallable getter.
    return instance.get_animation_asset()

def mother_finalize(segment):
    rows=segment.pop('samples')
    if not rows:raise RuntimeError('Actual Mother walk had no native samples')
    active=[r for r in rows if r['animation_active']]
    moving=[r for r in active if r['world_seconds']-segment['start_world_seconds']>.12]
    segment['sample_count']=len(rows);segment['active_animation_samples']=len(active)
    segment['duration_world_seconds']=rows[-1]['world_seconds']-rows[0]['world_seconds']
    segment['maximum_floor_error_cm']=max(abs(r['floor_error_cm']) for r in rows)
    segment['maximum_root_floor_error_cm']=max(abs(r['root_floor_error_cm']) for r in rows)
    segment['minimum_x_cm']=min(r['actor_location_cm'][0] for r in rows)
    segment['maximum_x_cm']=max(r['actor_location_cm'][0] for r in rows)
    segment['maximum_world_dimensions_cm']=[max(r['world_dimensions_cm'][i] for r in rows) for i in range(3)]
    # Offscreen pose culling is valid. Only a continuously recently rendered
    # interval of two game seconds can fail the visible-motion check.
    blocks=[];block=[]
    for row in moving:
        if row['recently_rendered']:
            if block and row['world_seconds']-block[-1]['world_seconds']>.25:blocks.append(block);block=[]
            block.append(row)
        else:
            if block:blocks.append(block);block=[]
    if block:blocks.append(block)
    visible_motion=[]
    for block in blocks:
        duration=block[-1]['world_seconds']-block[0]['world_seconds']
        if duration<2.0:continue
        positions=[r['animation_position_seconds'] for r in block]
        bone_motion=max(math.sqrt(sum((r['foot_l_component_cm'][i]-block[0]['foot_l_component_cm'][i])**2 for i in range(3))) for r in block)
        evidence={'visible_world_seconds':duration,'position_span_seconds':max(positions)-min(positions),
                  'left_foot_pose_delta_cm':bone_motion}
        visible_motion.append(evidence)
        check('Rendered Mother walk advances its own clip and visible foot pose: '+segment['direction'],
              evidence['position_span_seconds']>.02 and bone_motion>.1,evidence)
    segment['visible_motion_evidence']=visible_motion
    segment['offscreen_bone_pose_culling_permitted']=True
    segment['completed_naturally']=not bool(prop('MotherMoving'))
    folder=SCREEN_DIR/'mother_samples';folder.mkdir(exist_ok=True)
    file=folder/(S['record']['case']['id']+'_'+segment['direction']+'.json')
    file.write_text(json.dumps({'summary':segment,'samples':rows},indent=2)+'\n')
    segment['sample_file']=str(file);segment['sample_file_sha256']=hashlib.sha256(file.read_bytes()).hexdigest()
    check('Natural Mother route supplies normally ticking movement samples: '+segment['direction'],
          len(rows)>=20 and len(moving)>=10 and segment['duration_world_seconds']>2 and segment['completed_naturally'],segment)
    check('Actual Mother actor and native Root follow the reviewed floor: '+segment['direction'],
          segment['maximum_floor_error_cm']<1.0 and segment['maximum_root_floor_error_cm']<2.0,segment)
    check('Mother uses exact own human mesh, 53 bones, walk asset and calibrated rate: '+segment['direction'],
          all(r['mesh']==MOTHER_STORY_PROOF['mesh'] and r['native_bone_count']==53 and
              r['active_animation']==MOTHER_STORY_PROOF['walk'] and
              abs(r['play_rate']-float(MOTHER_STORY_PROOF['mother_walk_rate_estimate']))<.0001 and
              all(abs(s-1)<.001 for s in r['root_component_scale']) for r in moving),
          {'samples':len(moving),'expected_mesh':MOTHER_STORY_PROOF['mesh'],'expected_walk':MOTHER_STORY_PROOF['walk']})
    check('Actual Mother world bounds retain human dimensions: '+segment['direction'],
          all(115<r['world_dimensions_cm'][2]<200 and max(r['world_dimensions_cm'][:2])<125 for r in moving),
          segment['maximum_world_dimensions_cm'])
    facing=[r['travel_facing_dot'] for r in moving if r.get('travel_facing_dot') is not None and r.get('stable_travel_seconds',0)>1.15]
    check('Mother body faces sustained native travel after bounded turns: '+segment['direction'],
          len(facing)>=5 and min(facing)>.70,{'samples':len(facing),'minimum_dot':min(facing) if facing else None})
    if segment['direction']=='outbound':
        ramp=[r for r in rows if -220<r['actor_location_cm'][0]<-55]
        check('Actual outbound walk covers home, porch and ramp without a skip',
              segment['minimum_x_cm']<-870 and segment['maximum_x_cm']>-70 and len(ramp)>=4,
              {'ramp_samples':len(ramp),'x_range':[segment['minimum_x_cm'],segment['maximum_x_cm']]})
    else:
        check('Actual return walk reaches the surviving room through the existing route',
              segment['minimum_x_cm']<-870 and segment['maximum_x_cm']>-460,
              {'x_range':[segment['minimum_x_cm'],segment['maximum_x_cm']]})
    S['record'].setdefault('mother_walk_segments',[]).append(segment)

def mother_runtime_tick():
    record=S.get('record');world=S.get('world');manager=S.get('manager')
    if not record or record.get('case') not in CASES or not world or not manager:return
    if not LEVEL.is_in_play_in_editor():return
    try:
        if not unreal.SystemLibrary.is_valid(world) or not unreal.SystemLibrary.is_valid(manager):return
    except TypeError as error:
        # The existing restart ends a world before prepare_world replaces S.
        # Its retired Python proxy cannot enter the native UObject binding.
        if 'Cannot nativize' not in str(error):raise
        REPORT['mother_retired_world_observer_skips']=REPORT.get('mother_retired_world_observer_skips',0)+1
        return
    if not prop('ReleaseSessionStarted') or int(prop('EraIndex'))!=0:return
    moving=bool(prop('MotherMoving'))
    segment=MOTHER_OBSERVER['active']
    if not moving:
        if segment:
            mother_finalize(segment);MOTHER_OBSERVER['active']=None
        return
    direction='outbound' if prop('MotherToGate') else 'return'
    actor=prop('MotherActor');component=actor.get_component_by_class(unreal.SkeletalMeshComponent)
    if not segment:
        segment={'direction':direction,'start_world_seconds':float(unreal.GameplayStatics.get_time_seconds(world)),
            'samples':[],'stable_direction_since':None,'previous_travel_direction':None,
            'source_trigger':'Existing C1_05.second_test or C2_08A/B FinishNode; observer never writes NPC state'}
        MOTHER_OBSERVER['active']=segment
    if segment['direction']!=direction:raise RuntimeError('Mother changed route before the previous native movement completed')
    second=float(unreal.GameplayStatics.get_time_seconds(world))
    location=actor.get_actor_location();floor=mother_floor_height(location)
    root_world=component.get_socket_transform('Root',unreal.RelativeTransformSpace.RTS_WORLD)
    root_component=component.get_socket_transform('Root',unreal.RelativeTransformSpace.RTS_COMPONENT)
    mesh=component.get_skeletal_mesh_asset()
    pose=unreal.AnimPoseExtensions.get_reference_pose(mesh.get_editor_property('skeleton'))
    reference_root=unreal.AnimPoseExtensions.get_bone_pose(pose,'Root',unreal.AnimPoseSpaces.WORLD).translation
    component_offset=component.get_world_location().z-location.z
    expected_root=floor+component_offset+reference_root.z*actor.get_actor_scale3d().z
    origin,extent,radius=unreal.SystemLibrary.get_component_bounds(component)
    row={'world_seconds':second,'actor_location_cm':xyz(location),'expected_floor_cm':floor,
        'floor_error_cm':location.z-floor,'root_world_z_cm':root_world.translation.z,
        'reference_root_base_cm':reference_root.z,'component_origin_offset_z_cm':component_offset,
        'root_floor_error_cm':root_world.translation.z-expected_root,
        'root_component_scale':xyz(root_component.scale3d),'mesh':mother_runtime_path(mesh),
        'native_bone_count':component.get_num_bones(),'active_animation':mother_runtime_path(mother_active_asset(component)),
        'animation_active':bool(prop('MotherAnimActive')),'animation_position_seconds':float(component.get_position()),
        'play_rate':float(component.get_play_rate()),'recently_rendered':bool(component.was_recently_rendered(.25)),
        'foot_l_component_cm':xyz(component.get_socket_transform('foot_l',unreal.RelativeTransformSpace.RTS_COMPONENT).translation),
        'world_dimensions_cm':[extent.x*2,extent.y*2,extent.z*2],
        'world_paused':bool(unreal.GameplayStatics.is_game_paused(world)),'waypoint_read_only':int(prop('MotherWaypoint')),
        'component_world_rotation':str(component.get_component_rotation())}
    if row['world_paused']:raise RuntimeError('Mother walk observer expects normal unpaused native world time')
    if segment['samples'] and second-segment['samples'][-1]['world_seconds']<.04:return
    if segment['samples']:
        previous=segment['samples'][-1];dx=location.x-previous['actor_location_cm'][0];dy=location.y-previous['actor_location_cm'][1]
        length=math.hypot(dx,dy)
        if length>.1:
            travel=(dx/length,dy/length);old=segment['previous_travel_direction']
            if old is None or travel[0]*old[0]+travel[1]*old[1]<.95:segment['stable_direction_since']=second
            segment['previous_travel_direction']=travel
            facing=unreal.MathLibrary.get_right_vector(component.get_component_rotation())
            row['travel_facing_dot']=facing.x*travel[0]+facing.y*travel[1]
            row['stable_travel_seconds']=second-segment['stable_direction_since']
    segment['samples'].append(row)

def mother_wait(direction):
    yield until(lambda:not bool(prop('MotherMoving')),'natural observed Mother '+direction+' walking',22)
    mother_runtime_tick()
    segments=[s for s in S['record'].get('mother_walk_segments',[]) if s['direction']==direction]
    check('Full native Mother '+direction+' walk was passively observed exactly once',
          len(segments)==1 and segments[0]['completed_naturally'],segments)

def mother_route_complete():
    mother_runtime_tick()
    segments=S['record'].get('mother_walk_segments',[])
    check('Both real Mother walking directions were observed without NPC-state writes',
          sorted(s['direction'] for s in segments)==['outbound','return'],segments)
    component=prop('MotherActor').get_component_by_class(unreal.SkeletalMeshComponent)
    check('Arrived Mother restores her own Listening clip at idle rate',
          mother_runtime_path(mother_active_asset(component))==MOTHER_STORY_PROOF['listening_idle'] and
          abs(float(component.get_play_rate())-1)<.0001,
          {'asset':mother_runtime_path(mother_active_asset(component)),'rate':float(component.get_play_rate())})


'''

replace_once('def check_era_boundaries(era):',mother_helpers+'\ndef check_era_boundaries(era):')
replace_once("        now=time.monotonic()", "        now=time.monotonic()\n        mother_runtime_tick()")
replace_once("            yield until(lambda:not bool(prop('MotherMoving')),'Mother walks to the gate through native NPC movement',18)",
             "            yield from mother_wait('outbound')")
replace_once("            yield from interact('AnchorActor')\n        yield from dialogue(case)\n        check('Departure dialogue does not travel without confirmation'",
             "            yield from interact('AnchorActor')\n        yield from mother_wait('outbound')\n        yield from dialogue(case)\n        check('Departure dialogue does not travel without confirmation'")
replace_once("        yield until(lambda:not bool(prop('MotherMoving')) and prop('MotherActor').get_distance_to(prop('MotherHomeDestinationActor'))<=90,'Mother walks home through the native NPC route',18)",
             "        yield from mother_wait('return')\n        check('Observed Mother return reaches the native home destination',prop('MotherActor').get_distance_to(prop('MotherHomeDestinationActor'))<=90)\n        yield from focus('MotherActor')\n        yield screenshot('Mother_Home_Arrival')")
replace_once("        S['record']['final_state']=snapshot()", "        mother_route_complete()\n        S['record']['final_state']=snapshot()")

for old,new in {'release_story_audio_validation.json':'release_story_audio_mother_validation.json',
                "'release_story_audio'":"'release_story_audio_mother'",'YRAudioStoryQA_':'YRAMotherStoryQA_',
                'RELEASE_STORY_AUDIO_VALIDATION':'RELEASE_STORY_AUDIO_MOTHER_VALIDATION'}.items():
    if old not in source:raise RuntimeError('Missing combined Mother report label: '+old)
    source=source.replace(old,new)
replace_once("REPORT['native_save_guard_active']=", "REPORT['mother_qa_source_sha256']='"+MOTHER_WRAPPER_SOURCE_SHA+"'\nREPORT['mother_qa_scope']='Passive normally ticking existing NPC movement, exact own mesh/clips/rate, source floor/root offsets and real world bounds; existing native viewport screenshots retained. Offscreen bone culling permitted; no state/pose writes or packaged/S07/physical-input claim.'\nREPORT['native_save_guard_active']=")

ast.parse(source)
expanded_folder=root/'validation/release_story_audio_mother_source'
expanded_folder.mkdir(parents=True,exist_ok=True)
(expanded_folder/'expanded_current.py').write_text(source,encoding='utf-8')
exec(compile(source,str(root/'Python/validate_brief_m2.py'),'exec'),globals())
