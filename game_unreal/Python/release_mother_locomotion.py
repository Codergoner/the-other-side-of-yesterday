"""Source-only, bounded Mother-facing/rate hooks; no route/state regeneration."""
import unreal
import opening_graph as og
from release_frontend_graph import Flow, reset_function, MATH
from release_mother_integration import require, MANAGER

CLASS = MANAGER + '.BP_OpeningActions_C'
ACT = '/Script/Engine.Actor.'
SCENE = '/Script/Engine.SceneComponent.'
SKEL = '/Script/Engine.SkeletalMeshComponent.'


def build_helpers(manager):
    # Transient manager presentation data only; no campaign/profile schema.
    og.member(manager, 'MotherUseHumanLocomotion', 'bool', False, instance_editable=True)
    og.member(manager, 'MotherWalkPlayRate', 'real', 1.0, instance_editable=True)
    og.member(manager, 'MotherTurnSpeedDegrees', 'real', 180.0, instance_editable=True)
    og.member(manager, 'MotherAuthoredHumanWorldRotation', og.struct_type('rotator'), instance_editable=True)
    og.member(manager, 'MotherArrivalFacingRemaining', 'real', 0.0)
    declarations = {
        'ReleaseMotherFaceRotation': {'DesiredRotation':og.struct_type('rotator'),'DeltaSeconds':'real'},
        'ReleaseMotherFaceTravel': {'DesiredLocation':og.struct_type('vector'),'DeltaSeconds':'real'},
        'ReleaseMotherRestoreFacing': {}, 'ReleaseMotherArrived': {},
        'ReleaseMotherIdleFacing': {'DeltaSeconds':'real'}}
    # Publish typed UFunction stubs before any owned helper calls another one.
    for name, inputs in declarations.items():
        reset_function(manager,name,inputs=inputs)
    og.compile_bp(manager)
    g = reset_function(manager, 'ReleaseMotherFaceRotation',
                       inputs={'DesiredRotation': og.struct_type('rotator'), 'DeltaSeconds': 'real'})
    f = Flow(g)
    f, _ = f.branch(f.and_(f.var('MotherUseHumanLocomotion'), f.valid(f.var('MotherActor'))))
    mesh = f.data(ACT+'GetComponentByClass', **{'self': f.var('MotherActor'), 'ComponentClass': '/Script/Engine.SkeletalMeshComponent'})
    current = f.data(SCENE+'K2_GetComponentRotation', **{'self': mesh})
    bounded = f.data(MATH+'RInterpTo_Constant', Current=current, Target=g.input('DesiredRotation'),
                     DeltaTime=g.input('DeltaSeconds'), InterpSpeed=f.var('MotherTurnSpeedDegrees'))
    f.call(SCENE+'K2_SetWorldRotation', **{'self': mesh, 'NewRotation': bounded, 'bSweep': False, 'bTeleport': False})
    g = reset_function(manager, 'ReleaseMotherFaceTravel',
                       inputs={'DesiredLocation': og.struct_type('vector'), 'DeltaSeconds': 'real'})
    f = Flow(g)
    f, _ = f.branch(f.and_(f.var('MotherUseHumanLocomotion'), f.valid(f.var('MotherActor'))))
    current = f.data(ACT+'K2_GetActorLocation', **{'self': f.var('MotherActor')})
    delta = f.data(MATH+'Subtract_VectorVector', A=g.input('DesiredLocation'), B=current)
    flat = f.data(MATH+'ProjectVectorOnToPlane', V=delta, PlaneNormal=unreal.Vector(0,0,1))
    f, _ = f.branch(f.data(MATH+'Greater_DoubleDouble', A=f.data(MATH+'VSizeXY', A=flat), B=.001))
    # Human's actual front is +Y, and +Z stays up even on authored stair paths.
    rotation = f.data(MATH+'MakeRotFromYZ', Y=flat, Z=f.data(MATH+'MakeVector',X=0.0,Y=0.0,Z=1.0))
    f.own('ReleaseMotherFaceRotation', DesiredRotation=rotation, DeltaSeconds=g.input('DeltaSeconds'))
    g = reset_function(manager, 'ReleaseMotherRestoreFacing')
    f = Flow(g)
    f, _ = f.branch(f.and_(f.var('MotherUseHumanLocomotion'), f.valid(f.var('MotherActor'))))
    f.set('MotherArrivalFacingRemaining', 0.0)
    mesh = f.data(ACT+'GetComponentByClass', **{'self':f.var('MotherActor'),'ComponentClass':'/Script/Engine.SkeletalMeshComponent'})
    f.call(SCENE+'K2_SetWorldRotation', **{'self':mesh,'NewRotation':f.var('MotherAuthoredHumanWorldRotation'),
                                        'bSweep':False,'bTeleport':False})
    g = reset_function(manager, 'ReleaseMotherArrived')
    f = Flow(g)
    f, _ = f.branch(f.var('MotherUseHumanLocomotion'))
    f.set('MotherArrivalFacingRemaining', 3.0)
    g = reset_function(manager, 'ReleaseMotherIdleFacing', inputs={'DeltaSeconds':'real'})
    f = Flow(g)
    enabled = f.and_(f.var('MotherUseHumanLocomotion'),f.not_(f.var('MotherMoving')))
    enabled = f.and_(enabled,f.and_(f.eq(f.var('EraIndex'),0),f.var('ReleaseSessionStarted')))
    enabled = f.and_(enabled,f.not_(f.var('ReleaseMenuActive')))
    f, _ = f.branch(enabled)
    active_mode = f.or_(f.eq(f.var('Mode'),0),f.eq(f.var('Mode'),3))
    f, _ = f.branch(active_mode)
    partnered = f.data(MATH+'EqualEqual_ObjectObject',A=f.var('DialoguePartnerActor'),B=f.var('MotherActor'))
    dialogue = f.and_(f.var('DialogueActive'),partnered)
    arrival = f.data(MATH+'Greater_DoubleDouble',A=f.var('MotherArrivalFacingRemaining'),B=0.0)
    player, authored = f.branch(f.and_(f.or_(dialogue,arrival),f.valid(f.var('Player'))))
    target = player.data(ACT+'K2_GetActorLocation', **{'self':player.var('Player')})
    player.own('ReleaseMotherFaceTravel',DesiredLocation=target,DeltaSeconds=g.input('DeltaSeconds'))
    player.set('MotherArrivalFacingRemaining',player.data(MATH+'FClamp',
        Value=player.data(MATH+'Subtract_DoubleDouble',A=player.var('MotherArrivalFacingRemaining'),B=g.input('DeltaSeconds')),Min=0.0,Max=3.0))
    authored.own('ReleaseMotherFaceRotation',DesiredRotation=authored.var('MotherAuthoredHumanWorldRotation'),
                  DeltaSeconds=g.input('DeltaSeconds'))
    og.compile_bp(manager)


def patch_runtime(manager, audit, animation_changes):
    build_helpers(manager)
    changes_by_path = {r['node']:r for r in animation_changes}
    hooks = []
    movement_count = 0
    # These existing Mother-only PlayAnimation calls keep their objects/GUIDs;
    # an owned post-call rate/basis/arrival chain preserves each original tail.
    for graph in og.L.list_graphs(manager):
        editor = og.E.get_graph_editor(graph)
        if graph.get_name() not in ['RestoreSafeScene','NpcTick']:
            continue
        for node in list(editor.list_all_nodes()):
            record = changes_by_path.get(node.get_path_name())
            if record:
                then = og.pin_out(node)
                targets = list(og.P.list_connected_pins(then))
                self_source = list(og.P.list_connected_pins(og.pin_in(node,'self')))
                require(len(self_source)==1, 'Expected original Mother mesh input')
                og.P.break_pin_links(then)
                rate = editor.add_call_function_node(SKEL+'SetPlayRate')
                og.link(then,og.pin_in(rate));og.link(self_source[0],og.pin_in(rate,'self'))
                if record['new_value']=='MotherWalkAnimation':
                    getter=editor.add_get_member_variable_node('MotherWalkPlayRate','')
                    og.link(og.value_pin(getter),og.pin_in(rate,'Rate'))
                else:
                    og.default(rate,'Rate',1.0)
                tail=og.pin_out(rate)
                if record['new_value']=='MotherIdleAnimation':
                    helper='ReleaseMotherRestoreFacing' if graph.get_name()=='RestoreSafeScene' else 'ReleaseMotherArrived'
                    extra=editor.add_call_function_node(CLASS+':'+helper)
                    og.link(tail,og.pin_in(extra));tail=og.pin_out(extra)
                for target in targets:og.link(tail,target)
                audit.cache.pop(node.get_path_name(),None)
                require(audit.guid(node)==record['guid'],'A Mother PlayAnimation GUID changed')
                hooks.append({'kind':'animation_rate/basis/arrival','original_node':node.get_path_name(),
                              'original_guid':record['guid'],'original_tail_count':len(targets)})
                continue
            if graph.get_name()!='NpcTick':continue
            title=str(og.L.get_node_title(node)).replace(' ','').lower()
            if 'setactorlocation' not in title or audit.function(node)[1]!='K2_SetActorLocation':continue
            if not audit.ancestors_have_variable(node,'MotherActor'):continue
            current_pins=audit.pins(node,exclude=['execute'])
            original_guid=audit.guid(node)
            location=list(og.P.list_connected_pins(og.pin_in(node,'NewLocation')))
            require(len(location)==1,'Expected native authored VInterp movement input')
            interp=og.P.get_owning_node(location[0])
            require(audit.function(interp)[1]=='VInterpTo_Constant','Refusing to alter unexpected NPC movement')
            require(float(str(og.P.get_pin_value(og.pin_in(interp,'InterpSpeed'))))==100.0,'Authored NPC speed must remain100cm/s')
            targets=list(og.P.list_connected_pins(og.pin_in(node)))
            og.P.break_pin_links(og.pin_in(node))
            call=editor.add_call_function_node(CLASS+':ReleaseMotherFaceTravel')
            for source in targets:og.link(source,og.pin_in(call))
            og.link(og.pin_out(call),og.pin_in(node));og.link(location[0],og.pin_in(call,'DesiredLocation'))
            g=og.Graph(manager,editor)
            og.link(g.input('DeltaSeconds'),og.pin_in(call,'DeltaSeconds'))
            audit.cache.pop(node.get_path_name(),None)
            require(audit.guid(node)==original_guid and audit.pins(node,exclude=['execute'])==current_pins,
                    'Movement location/speed/output pins changed')
            movement_count+=1
            hooks.append({'kind':'pre-move heading','original_node':node.get_path_name(),'original_guid':original_guid})
        if graph.get_name()=='NpcTick':
            g=og.Graph(manager,editor)
            targets=list(og.P.list_connected_pins(g.entry));og.P.break_pin_links(g.entry)
            call=editor.add_call_function_node(CLASS+':ReleaseMotherIdleFacing')
            og.link(g.entry,og.pin_in(call));og.link(g.input('DeltaSeconds'),og.pin_in(call,'DeltaSeconds'))
            for target in targets:og.link(og.pin_out(call),target)
    require(movement_count==12,'Expected exactly12 existing Mother waypoint movement nodes, leaving Neri unchanged')
    require(len([h for h in hooks if h['kind']=='animation_rate/basis/arrival'])==5,'Expected5Mother animation hook tails')
    og.compile_all([manager],save=False)
    return {'hooks':hooks,'mother_movement_nodes':movement_count,'neri_modified':False,
            'authored_paths_locations_speed_changed':False,'runtime_max_turn_degrees_s':180,
            'idle_restore_basis':'Explicit stored authored +X heading converted once to human +Y; no repeated subtraction',
            'arrival_policy':'Bounded player facing for3s and throughout actual Mother dialogue; authored workbench heading otherwise',
            'runtime_video_verified':False,'foot_lock_claimed':False}
