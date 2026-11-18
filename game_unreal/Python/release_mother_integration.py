"""Source-only helpers for the queued, Mother-only native integration.

No factory dialogs, component spawn internals, ragdoll simulation or saves here.
The caller must own the serialized native queue and approved corrected-unit /
rendered-gait inputs before invoking any mutating helper.
"""
from pathlib import Path
import hashlib
import json
import re
import unreal
import opening_graph as og
import release_file_io as file_io

LIB = unreal.EditorAssetLibrary
MANAGER = '/Game/Opening/Blueprints/BP_OpeningActions'
GUARD = '/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary'
SAVE_FUNCTIONS = {'LoadGameFromSlot', 'SaveGameToSlot', 'DoesSaveGameExist'}
OWNER = 'TOSOY.ReleaseMotherIntegration'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    return file_io.sha(path)


def path(value):
    return value.get_path_name() if value else None


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def asset_file(project, asset):
    name = str(asset).split('.')[0]
    require(name.startswith('/Game/'), 'Only Release project assets may be owned')
    return project / 'Content' / (name.removeprefix('/Game/') + '.uasset')


def unit_reference(mesh):
    skeleton = mesh.get_editor_property('skeleton')
    pose = unreal.AnimPoseExtensions.get_reference_pose(skeleton)
    require(unreal.AnimPoseExtensions.is_valid(pose), 'Actual native reference pose unavailable')
    names = [str(n) for n in unreal.AnimPoseExtensions.get_bone_names(pose)]
    core = [n for n in names if n.lower() == 'root']
    require(names and len(core) == 1, 'Expected the actual first native bone and one MPFB Root')
    scales = {name: xyz(unreal.AnimPoseExtensions.get_bone_pose(pose, name, unreal.AnimPoseSpaces.LOCAL).scale3d)
              for name in dict.fromkeys([names[0], core[0]])}
    require(all(abs(c-1) < .0001 for s in scales.values() for c in s), 'Native extra-root/CoreRoot scale is not1; old Root100 candidate is forbidden')
    head = unreal.AnimPoseExtensions.get_bone_pose(pose, 'head', unreal.AnimPoseSpaces.WORLD)
    require(100 < head.translation.z < 220, 'Native reference head is not at human-scale world height')
    return {'first_native_bone': names[0], 'native_bone_count': len(names), 'root_local_scales': scales,
            'reference_head_z_cm': float(head.translation.z)}


def create_query_physics(mesh, owner=OWNER):
    """Verified UE5.8 no-dialog generation API; no assignment to Manny/old mesh."""
    subsystem = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    expected = mesh.get_path_name().split('.')[0] + '_PhysicsAsset'
    require(not LIB.does_asset_exist(expected), 'Preserving an existing physics asset; review it or use a new candidate namespace')
    physics = subsystem.create_physics_asset(mesh, False, 0)
    require(physics and physics.get_path_name().split('.')[0] == expected, 'Unexpected generated physics asset path')
    require(subsystem.is_physics_asset_compatible(mesh, physics), 'Generated physics bones/constraints do not match the human skeleton')
    # This installed Python wrapper does not publish the snake-case name for
    # the protected instanced array. Try the exact reflected C++ name; body
    # counts are diagnostic only. The caller still MUST pass all real isolated
    # torso Visibility queries and at least one real-scene same-actor query.
    body_access_error = None
    try:
        bodies = list(physics.get_editor_property('SkeletalBodySetups'))
        require(bodies, 'Generated physics asset has no query bodies')
        names = [str(body.get_editor_property('BoneName')) for body in bodies]
        require(any(name.lower() in ['pelvis', 'spine_01', 'spine_02', 'spine_03'] for name in names), 'No torso query geometry was generated')
    except Exception as error:
        bodies, names, body_access_error = None, None, str(error)
    LIB.set_metadata_tag(physics, 'TOSOY.Owner', owner)
    return physics, {'path': path(physics), 'body_count': len(bodies) if bodies is not None else None, 'body_bones': names,
                     'body_array_access_diagnostic': body_access_error,
                     'body_shape_acceptance': 'Mandatory actual isolated torso and real-scene same-actor Visibility queries in the staging caller',
                     'human_skeleton_compatible': True, 'ragdoll_or_physics_simulation_claimed': False}


def transform_state(value):
    # Struct repr contains a changing native memory address; compare data.
    return {'translation':xyz(value.translation),'rotation_xyzw':[float(value.rotation.x),float(value.rotation.y),float(value.rotation.z),float(value.rotation.w)],'scale':xyz(value.scale3d)}


def component_state(actor):
    comp = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    require(comp, 'Stable Mother is not the expected SkeletalMeshActor')
    mesh = comp.get_skeletal_mesh_asset()
    return {'actor_path': path(actor), 'actor_transform': transform_state(actor.get_actor_transform()),
            'actor_tags': sorted(str(t) for t in actor.get_editor_property('tags')),
            'actor_collision_enabled': bool(actor.get_actor_enable_collision()),
            'mesh': path(mesh), 'mesh_default_physics': path(mesh.get_editor_property('physics_asset')),
            'component_physics_override': path(comp.get_editor_property('physics_asset_override')),
            'component_relative_transform': transform_state(comp.get_relative_transform()),
            'collision_enabled': str(comp.get_collision_enabled()), 'profile': str(comp.get_collision_profile_name()),
            'object_type': str(comp.get_collision_object_type()),
            'visibility_response': str(comp.get_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY)),
            'pawn_response': str(comp.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)),
            'override_materials': [path(m) for m in comp.get_editor_property('override_materials')],
            'animation_data': str(comp.get_editor_property('animation_data'))}


def query_mother(world, actor):
    """Real scene query plus isolated shape queries; same stable actor required."""
    comp = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    require(comp.get_collision_enabled() == unreal.CollisionEnabled.QUERY_ONLY, 'Preserve the baseline QueryOnly policy')
    require(comp.get_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY) == unreal.CollisionResponseType.ECR_BLOCK,
            'Human body no longer blocks interaction Visibility queries')
    require(comp.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN) == unreal.CollisionResponseType.ECR_IGNORE,
            'Do not introduce a solid NPC/player blocker')
    origin = actor.get_actor_location()
    center = origin + unreal.Vector(0, 0, 85)
    offsets = [(200, 45, 98), (-180, 0, 98), (0, 180, 98), (0, -180, 98)]
    others = [a for a in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor) if a != actor]
    rows = []
    for isolated, ignored in [(False, []), (True, others)]:
        for offset in offsets:
            start = origin + unreal.Vector(*offset)
            hit = unreal.SystemLibrary.line_trace_single(world, start, center, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                         False, ignored, unreal.DrawDebugTrace.NONE, True)
            values = hit.to_tuple() if hit is not None else None
            selected = bool(values and values[0] and values[9] == actor)
            rows.append({'isolated_shape_query': isolated, 'start_cm': xyz(start), 'end_cm': xyz(center),
                         'same_mother_actor_hit': selected, 'hit_actor': path(values[9]) if values else None})
    require(any(r['same_mother_actor_hit'] for r in rows if not r['isolated_shape_query']), 'No real scene ray selected the stable Mother actor after the unsaved swap')
    require(all(r['same_mother_actor_hit'] for r in rows if r['isolated_shape_query']), 'Human physics has missing/incorrectly placed torso query geometry')
    return {'visibility_rays': rows, 'baseline_pawn_response_preserved': 'Ignore',
            'solid_npc_collision_claimed': False, 'note': 'Baseline ghost-to-player behavior is preserved; no Pawn blocking or ragdoll feature was added.'}


class GraphAudit:
    def __init__(self, folder):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.cache = {}

    def text(self, node):
        key = node.get_path_name()
        if key not in self.cache:
            file = self.folder / (hashlib.sha256(key.encode()).hexdigest()[:24] + '_' + str(len(list(self.folder.glob('*.t3d')))) + '.t3d')
            task = unreal.AssetExportTask()
            for key_, value in {'object': node, 'exporter': unreal.ObjectExporterT3D(), 'filename': str(file),
                                'automated': True, 'prompt': False, 'replace_identical': False, 'selected': False}.items():
                task.set_editor_property(key_, value)
            require(unreal.Exporter.run_asset_export_task(task), 'Public graph text export failed')
            exported = file.read_bytes()
            self.cache[key] = exported.decode('utf-16' if exported.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
        return self.cache[key]

    def guid(self, node):
        result = re.search(r'(?m)^\s*NodeGuid=([0-9A-Fa-f]{32})\s*$', self.text(node))
        require(result, 'Public serialized node GUID unavailable')
        return result.group(1).upper()

    def function(self, node):
        match = re.search(r'(?m)^\s*FunctionReference=\(([^\r\n]*)\)', self.text(node))
        if not match:
            return None, None
        name = re.search(r'MemberName="([^"]+)"', match.group(1))
        parent = re.search(r'MemberParent="[^"\r\n]*\x27([^\x27]+)\x27"', match.group(1))
        return (parent.group(1) if parent else None), (name.group(1) if name else None)

    def ancestors_have_variable(self, node, variable, depth=0):
        if depth > 6:
            return False
        for pin in og.L.list_input_pins(node):
            if str(og.P.get_pin_name(pin)) == 'execute':
                continue
            for connected in og.P.list_connected_pins(pin):
                owner = og.P.get_owning_node(connected)
                match = re.search(r'(?m)^\s*VariableReference=\(([^\r\n]*)\)', self.text(owner))
                if match and re.search(r'MemberName="' + re.escape(variable) + '"', match.group(1)):
                    return True
                if self.ancestors_have_variable(owner, variable, depth+1):
                    return True
        return False

    def pins(self, node, exclude=()):
        result = {}
        for direction, pins in [('in', og.L.list_input_pins(node)), ('out', og.L.list_output_pins(node))]:
            for pin in pins:
                name = str(og.P.get_pin_name(pin))
                if name in exclude:
                    continue
                links = [[og.P.get_owning_node(p).get_path_name(), str(og.P.get_pin_name(p))] for p in og.P.list_connected_pins(pin)]
                result[direction+':'+name] = {'value': str(og.P.get_pin_value(pin)), 'links': sorted(links)}
        return result

    def guarded_calls(self, manager):
        rows = []
        for graph in og.L.list_graphs(manager):
            for node in og.E.get_graph_editor(graph).list_all_nodes():
                title = re.sub(r'\s+', '', str(og.L.get_node_title(node))).lower()
                if not any(name.lower() in title for name in SAVE_FUNCTIONS):
                    continue
                parent, name = self.function(node)
                if name not in SAVE_FUNCTIONS:
                    continue
                require(parent == GUARD, 'Unsafe generic save owner appeared during Mother patch')
                rows.append({'node': node.get_path_name(), 'guid': self.guid(node), 'owner': parent, 'function': name, 'pins': self.pins(node)})
        require(len(rows) == 13, 'Reviewed save owner count changed')
        return rows


def patch_mother_pins(manager, audit, fallback_animations):
    """Keep all5 original PlayAnimation objects/GUIDs and every execution link."""
    defaults = dict(fallback_animations)
    require(set(defaults) == {'IdleAnimation', 'WalkAnimation'} and all(defaults.values()),
            'Actual existing map mannequin animation defaults are required')
    for name in ['MotherIdleAnimation', 'MotherWalkAnimation']:
        og.member(manager, name, og.object_type(unreal.AnimSequence), instance_editable=True)
    og.compile_bp(manager)
    cdo = unreal.get_default_object(manager.generated_class())
    # Unmigrated maps keep their compatible mannequin defaults. Corrected human
    # animation refs are assigned only on a migrated map's manager instance.
    for name in defaults:
        cdo.set_editor_property('Mother' + name, defaults[name])
    changes = []
    for graph in og.L.list_graphs(manager):
        editor = og.E.get_graph_editor(graph)
        for node in list(editor.list_all_nodes()):
            title = re.sub(r'\s+', '', str(og.L.get_node_title(node))).lower()
            if 'playanimation' not in title or audit.function(node)[1] != 'PlayAnimation':
                continue
            if not audit.ancestors_have_variable(node, 'MotherActor'):
                continue
            require(graph.get_name() in ['RestoreSafeScene', 'NpcTick'], 'Unexpected Mother animation graph')
            input_pin = og.pin_in(node, 'NewAnimToPlay')
            old_links = list(og.P.list_connected_pins(input_pin))
            require(len(old_links) == 1, 'Mother animation must retain one reviewed value source')
            source = og.P.get_owning_node(old_links[0])
            source_text = audit.text(source)
            old_name = next((n for n in ['IdleAnimation', 'WalkAnimation']
                             if re.search(r'MemberName="' + n + '"', source_text)), None)
            require(old_name, 'Refusing an already migrated or unexpected Mother animation value')
            before_guid, before_pins = audit.guid(node), audit.pins(node, ['NewAnimToPlay'])
            getter = editor.add_get_member_variable_node('Mother' + old_name, '')
            og.P.break_pin_links(input_pin)
            og.link(og.value_pin(getter), input_pin)
            audit.cache.pop(node.get_path_name(), None)
            require(audit.guid(node) == before_guid and audit.pins(node, ['NewAnimToPlay']) == before_pins,
                    'Mother patch altered a PlayAnimation object/GUID/other pin or execution link')
            changes.append({'graph': graph.get_name(), 'node': node.get_path_name(), 'guid': before_guid,
                            'old_value': old_name, 'new_value': 'Mother' + old_name})
    require(len(changes) == 5 and sum(c['new_value'] == 'MotherIdleAnimation' for c in changes) == 3,
            'Expected exactly3Mother idle and2Mother walk value-pin changes')
    og.compile_all([manager], save=False)
    return changes
