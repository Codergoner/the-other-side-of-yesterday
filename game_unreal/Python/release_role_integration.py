"""Source-only bounded candidate staging for Healer/Sela/Neri.

No entry point launches a writer. A caller must own Root's native queue and
SHA-pinned native/art approvals. Era flags, same actors, paths and saves remain
the existing story manager's responsibility.
"""
import unreal
import opening_graph as og
import release_mother_integration as shared

ROLES = {
    'Healer': {'actor_ref':'HealerActor','stable_tag':'past.healer','era':1,'moving':False,
               'expected_existing_play_nodes':0,'expected_existing_move_nodes':0},
    'Sela': {'actor_ref':'SelaActor','stable_tag':'past.sela','era':1,'moving':False,
             'expected_existing_play_nodes':0,'expected_existing_move_nodes':0},
    'Neri': {'actor_ref':'NeriActor','stable_tag':'past.neri','era':1,'moving':True,
             'expected_existing_play_nodes':3,'expected_idle_nodes':2,'expected_walk_nodes':1,
             'expected_existing_move_nodes':3}}


def stage_candidate(world, manager, role, candidate, physics):
    """Unsaved same-actor swap + controlled query fixture, with flag rollback.

    Hidden past actors cannot honestly be queried before the original era flow
    exposes them. This temporary fixture enables only the selected actor and
    restores its exact authored flags; it is not a narrative/past-era test.
    """
    spec = ROLES[role]
    actor = manager.get_editor_property(spec['actor_ref'])
    shared.require(actor and actor.actor_has_tag(spec['stable_tag']), 'Existing stable role actor/tag required')
    component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    shared.require(component, 'Expected the original skeletal role actor')
    before = shared.component_state(actor)
    # Native baseline is queried, never reset from a source assumption.
    shared.require(component.get_collision_enabled() in [unreal.CollisionEnabled.QUERY_ONLY, unreal.CollisionEnabled.NO_COLLISION],
                   'Unexpected native collision mode; preserve it for review')
    shared.require(component.get_collision_enabled()==unreal.CollisionEnabled.QUERY_ONLY or not actor.get_actor_enable_collision(),
                   'A visible enabled role must retain QueryOnly collision')
    shared.require(component.get_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY)==unreal.CollisionResponseType.ECR_BLOCK
                   and component.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)==unreal.CollisionResponseType.ECR_IGNORE,
                   'Native role query policy differs from the verified ghost-Pawn baseline')
    hidden, enabled = bool(actor.get_editor_property('hidden')), bool(actor.get_actor_enable_collision())
    previous = {'mesh':component.get_skeletal_mesh_asset(), 'physics':component.get_editor_property('physics_asset_override'),
        'materials':list(component.get_editor_property('override_materials')), 'animation_mode':component.get_editor_property('animation_mode'),
        'animation_data':component.get_editor_property('animation_data')}
    mesh, idle = unreal.load_asset(candidate['mesh']), unreal.load_asset(candidate['animation'])
    shared.require(mesh and idle and idle.get_editor_property('skeleton')==mesh.get_editor_property('skeleton'),
                   'Role must use its own exact target-compatible Listening clip, never Mother/Manny aliases')
    shared.require(candidate['character']==role and candidate['native_executed'] and candidate['human_height_passed']
                   and candidate['native_unit_scale']['unit_root_scale_passed'] and candidate['authored_bone_and_curve_data_passed'],
                   'Actual matching normalized role and own Listening/face-curve data proof required')
    shared.unit_reference(mesh)
    subsystem=unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    shared.require(subsystem.is_physics_asset_compatible(mesh,physics), 'Role query physics is not for its actual bone set')
    try:
        component.override_animation_data(None,True,False,0.0,1.0)
        component.set_skeletal_mesh_asset(mesh)
        component.set_editor_property('override_materials',[])
        component.override_animation_data(idle,True,True,0.0,1.0)
        component.set_physics_asset(physics,True)
        actor.set_actor_hidden_in_game(False)
        actor.set_actor_enable_collision(True)
        shared.require(component.get_collision_enabled()==unreal.CollisionEnabled.QUERY_ONLY,
                       'Enabling the original era actor did not restore its configured QueryOnly policy')
        query=shared.query_mother(world,actor)
        for row in query['visibility_rays']:
            row['same_stable_actor_hit']=row.pop('same_mother_actor_hit')
        origin,extent,_=unreal.SystemLibrary.get_component_bounds(component)
        scale=actor.get_actor_scale3d()
        shared.require(abs(scale.x-scale.y)<1e-5 and abs(scale.x-scale.z)<1e-5,'Review nonuniform authored role scaling')
        expected=float(candidate['world_height_cm'])*float(scale.x)
        shared.require(80<=extent.z*2<=220 and abs(extent.z*2-expected)<=max(10,expected*.12),
                       'Production body/physics bounds differ from the exact native mesh and preserved authored scale')
        # Keep the exact era/authoring flags; only ApplyWorldState may expose
        # the NPC during the real story. The same actor stays in PastActors.
        actor.set_actor_hidden_in_game(hidden)
        actor.set_actor_enable_collision(enabled)
        after=shared.component_state(actor)
        keys=['actor_path','actor_transform','actor_tags','actor_collision_enabled','collision_enabled','profile',
              'object_type','visibility_response','pawn_response']
        shared.require(all(before[k]==after[k] for k in keys), 'Role identity/authored transform/query policy changed: '+str({k:{'before':before[k],'after':after[k]} for k in keys if before[k]!=after[k]}))
        return actor, component, previous, {'character':role,'before':before,'after':after,
            'own_listening_idle':idle.get_path_name(),'world_height_cm':float(extent.z*2),
            'expected_height_from_native_mesh_and_authored_scale_cm':expected,
            'actual_authored_scale_preserved':shared.xyz(scale),'character_size_visually_approved_by_this_fixture':False,
            'authored_hidden_in_game_preserved':hidden,'authored_actor_collision_enabled_preserved':enabled,
            'controlled_visibility_fixture':True,'fixture_flags_restored_before_save':True,
            'real_story_era_or_dialogue_tested':False,'same_actor_query_proof':query}
    except Exception:
        actor.set_actor_hidden_in_game(hidden);actor.set_actor_enable_collision(enabled)
        component.override_animation_data(None,True,False,0.0,1.0)
        component.set_skeletal_mesh_asset(previous['mesh']);component.set_physics_asset(previous['physics'],True)
        component.set_editor_property('override_materials',previous['materials'])
        component.set_animation_mode(previous['animation_mode']);component.set_editor_property('animation_data',previous['animation_data'])
        raise


def patch_neri_animation_values(manager,audit,fallback_animations):
    """Only the3 existing Neri PlayAnimation value pins; no Mother calls."""
    shared.require(set(fallback_animations)=={'IdleAnimation','WalkAnimation'},'Only the two existing global animation defaults are accepted')
    for name in ['IdleAnimation','WalkAnimation']:
        shared.require(fallback_animations.get(name),'Actual compatible existing mannequin defaults required')
        og.member(manager,'Neri'+name,og.object_type(unreal.AnimSequence),instance_editable=True)
    og.compile_bp(manager)
    cdo=unreal.get_default_object(manager.generated_class())
    for name,value in fallback_animations.items():cdo.set_editor_property('Neri'+name,value)
    changes=[]
    for graph in og.L.list_graphs(manager):
        if graph.get_name() not in ['RestoreSafeScene','NpcTick']:continue
        editor=og.E.get_graph_editor(graph)
        for node in list(editor.list_all_nodes()):
            title=str(og.L.get_node_title(node)).replace(' ','').lower()
            if 'playanimation' not in title or audit.function(node)[1]!='PlayAnimation':continue
            if not audit.ancestors_have_variable(node,'NeriActor'):continue
            pin=og.pin_in(node,'NewAnimToPlay');links=list(og.P.list_connected_pins(pin))
            shared.require(len(links)==1,'Expected original Neri global animation input')
            source=audit.text(og.P.get_owning_node(links[0]))
            import re
            old=next((name for name in ['IdleAnimation','WalkAnimation'] if re.search(r'MemberName="'+name+'"',source)),None)
            shared.require(old,'Unexpected/already-migrated Neri animation input; review it first')
            before_guid,before_pins=audit.guid(node),audit.pins(node,['NewAnimToPlay'])
            getter=editor.add_get_member_variable_node('Neri'+old,'')
            og.P.break_pin_links(pin);og.link(og.value_pin(getter),pin)
            audit.cache.pop(node.get_path_name(),None)
            shared.require(audit.guid(node)==before_guid and audit.pins(node,['NewAnimToPlay'])==before_pins,
                           'Neri value patch changed an original node/GUID/other pin')
            changes.append({'graph':graph.get_name(),'node':node.get_path_name(),'guid':before_guid,
                            'old_value':old,'new_value':'Neri'+old})
    shared.require(len(changes)==3 and sum(r['new_value']=='NeriIdleAnimation' for r in changes)==2,
                   'Expected exactly2Neri idle and1Neri walk original calls')
    og.compile_all([manager],save=False)
    return changes
