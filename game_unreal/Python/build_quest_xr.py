"""Author the isolated Quest adapter as native Blueprint gameplay.

Run only through the root agent's serialized UE asset-writing queue. Python is
editor tooling, never a runtime dependency. Existing desktop graphs survive;
tag-gated wrappers route only BP_QuestCharacter to the XR implementation.
"""
from pathlib import Path
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Quest_20261025', 'Quest writer cannot modify the desktop project'
sys.path.insert(0, str(ROOT / 'Python'))
import opening_graph as og
import build_opening_actions as base
from build_opening_actions import Flow, MATH, SYS, GS, ACT, PC, CTL, CAM

CHAR_PATH = '/Game/Quest/XR/BP_QuestCharacter'
CHAR_CLASS = CHAR_PATH + '.BP_QuestCharacter_C'
GM_PATH = '/Game/Quest/XR/BP_QuestGameMode'
MANAGER_PATH = base.PATH
MANAGER_CLASS = base.CLASS
SC = '/Script/Engine.SceneComponent.'
MC = '/Script/HeadMountedDisplay.MotionControllerComponent.'
HMD = '/Script/XRBase.HeadMountedDisplayFunctionLibrary.'
TEXT = '/Script/Engine.TextRenderComponent.'
STR = '/Script/Engine.KismetStringLibrary.'
MARKER = 'Quest.XRWrapper.v1'


class QFlow(Flow):
    def var(self, name, owner=None, cls=''):
        # APawn already has a Controller-typed property. Keep a distinct typed
        # PlayerController reference for polling rather than shadowing it.
        if name == 'Controller' and owner is None and not cls:
            name = 'QuestController'
        return super().var(name, owner, cls)

    def own(self, name, **params):
        return self.call(CHAR_CLASS + ':' + name, **params)

    def branch(self, condition):
        n = self.g.branch(condition)
        og.link(self.cur, og.pin_in(n))
        return QFlow(self.g, og.pin_out(n, 'then')), QFlow(self.g, og.pin_out(n, 'else'))

    def manager(self, name, **params):
        return self.call(MANAGER_CLASS + ':' + name, **{'self': self.var('QuestManager'), **params})

    def mv(self, name):
        return self.var(name, self.var('QuestManager'), MANAGER_CLASS)


def reset_function(bp, name, inputs=None):
    old = og.L.find_graph(bp, name)
    if old:
        ed = og.E.get_graph_editor(old)
        ed.remove_nodes([n for n in ed.list_all_nodes()
                         if n.get_class().get_name() not in ['K2Node_FunctionEntry', 'K2Node_FunctionResult']])
    return og.function(bp, name, inputs=inputs, reset=False)


def merge(*flows):
    n = flows[0].g.set('QuestFlowMarker', 0)
    for f in flows:
        og.link(f.cur, og.pin_in(n))
    return type(flows[0])(flows[0].g, og.pin_out(n))


def vec(f, x=0, y=0, z=0):
    return f.data(MATH + 'MakeVector', X=x, Y=y, Z=z)


def split_vec(f, v):
    n = f.call(MATH + 'BreakVector', InVec=v)
    return [og.value_pin(n, p) for p in ['X', 'Y', 'Z']]


def add(f, a, b):
    return f.data(MATH + 'Add_VectorVector', A=a, B=b)


def sub(f, a, b):
    return f.data(MATH + 'Subtract_VectorVector', A=a, B=b)


def scale(f, v, s):
    return f.data(MATH + 'Multiply_VectorFloat', A=v, B=s)


def location(f, name):
    return f.data(SC + 'K2_GetComponentLocation', **{'self': f.var(name)})


def rotation(f, name):
    return f.data(SC + 'K2_GetComponentRotation', **{'self': f.var(name)})


def join_text(f, a, b):
    return f.data(STR + 'Concat_StrStr', A=a, B=b)


def set_text(f, component, value):
    # UE5.8 K2_SetText unconditionally dirties render state. Compare strings
    # first so stationary dialogue does not rebuild its meshes every frame.
    cache = 'QuestCached' + component
    changed, unchanged = f.branch(f.data(STR + 'NotEqual_StrStr', A=value, B=f.var(cache)))
    # TextRender's empty-line fallback uses the unscaled font height. Collapse
    # paragraph blank lines before rendering so a small world font cannot
    # introduce 30cm gaps or push later instructions through response rows.
    rendered = value
    for _ in range(3):
        rendered = changed.data(STR + 'Replace', SourceString=rendered, From='\n\n', To='\n')
    text = changed.data('/Script/Engine.KismetTextLibrary.Conv_StringToText', InString=rendered)
    changed.call(TEXT + 'K2_SetText', **{'self': changed.var(component), 'Value': text})
    changed.set(cache, value)
    f.cur = merge(changed, unchanged).cur


def _subobjects(bp):
    sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    result = []
    for handle in sub.k2_gather_subobject_data_for_blueprint(bp):
        data = lib.get_data(handle)
        obj = lib.get_object_for_blueprint(data, bp)
        result.append((str(lib.get_variable_name(data)), handle, obj, data))
    return sub, lib, result


def component(bp, name, cls, parent_name=None):
    sub, lib, entries = _subobjects(bp)
    found = next((e for e in entries if e[0] == name), None)
    if found:
        return found[2]
    parent = next((e for e in entries if e[0] == parent_name), None) if parent_name else entries[0]
    if parent is None:
        raise RuntimeError('Missing component parent: ' + str(parent_name))
    params = unreal.AddNewSubobjectParams(parent_handle=parent[1], new_class=cls,
                                        blueprint_context=bp, conform_transform_to_parent=False)
    handle, reason = sub.add_new_subobject(params)
    if not lib.is_handle_valid(handle):
        raise RuntimeError('Cannot add ' + name + ': ' + str(reason))
    if not sub.rename_subobject(handle, unreal.Text(name)):
        raise RuntimeError('Cannot name component ' + name)
    obj = lib.get_object_for_blueprint(lib.get_data(handle), bp)
    if obj is None:
        raise RuntimeError('No component template for ' + name)
    return obj


def transform(c, at=(0, 0, 0), rot=(0, 0, 0), size=(1, 1, 1)):
    c.set_editor_property('relative_location', unreal.Vector(*at))
    c.set_editor_property('relative_rotation', unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]))
    c.set_editor_property('relative_scale3d', unreal.Vector(*size))


def text_component(bp, name, parent, at, size):
    c = component(bp, name, unreal.TextRenderComponent, parent)
    transform(c, at)
    c.set_world_size(size)
    c.set_editor_property('x_scale', .85)
    c.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_LEFT)
    c.set_vertical_alignment(unreal.VerticalTextAligment.EVRTA_TEXT_TOP)
    c.set_editor_property('text_render_color', unreal.Color(244, 237, 218, 255))
    c.set_text_material(readable_text_material())
    c.set_editor_property('cast_shadow', False)
    c.set_editor_property('text', unreal.Text(''))
    return c


def readable_text_material():
    path = '/Game/Quest/XR/Materials/M_QuestReadableText'
    asset = unreal.load_asset(path)
    if asset:
        return asset
    # Preserve Epic's font atlas/mask graph, routing its actual color output
    # to emissive so readable UI does not depend on an unbaked room's lighting.
    asset = unreal.EditorAssetLibrary.duplicate_asset('/Engine/EngineMaterials/DefaultTextMaterialOpaque', path)
    if not asset:
        raise RuntimeError('Cannot create owned readable font material')
    node = unreal.MaterialEditingLibrary.get_material_property_input_node(asset, unreal.MaterialProperty.MP_BASE_COLOR)
    output = unreal.MaterialEditingLibrary.get_material_property_input_node_output_name(asset, unreal.MaterialProperty.MP_BASE_COLOR)
    if node is None or not unreal.MaterialEditingLibrary.connect_material_property(node, output, unreal.MaterialProperty.MP_EMISSIVE_COLOR):
        raise RuntimeError('Default font color graph could not be preserved as emissive')
    asset.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    asset.set_editor_property('two_sided', True)
    unreal.MaterialEditingLibrary.recompile_material(asset)
    unreal.EditorAssetLibrary.save_loaded_asset(asset)
    return asset


def panel_material(name, rgb, two_sided=False):
    path = '/Game/Quest/XR/Materials/' + name
    asset = unreal.load_asset(path)
    if asset:
        return asset
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, '/Game/Quest/XR/Materials', unreal.Material, unreal.MaterialFactoryNew())
    asset.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    asset.set_editor_property('two_sided', two_sided)
    node = unreal.MaterialEditingLibrary.create_material_expression(asset, unreal.MaterialExpressionConstant3Vector, -250, 0)
    node.set_editor_property('constant', unreal.LinearColor(*rgb, 1))
    unreal.MaterialEditingLibrary.connect_material_property(node, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    unreal.MaterialEditingLibrary.recompile_material(asset)
    unreal.EditorAssetLibrary.save_loaded_asset(asset)
    return asset


def setup_components(bp):
    cdo = unreal.get_default_object(og.L.generated_class(bp))
    cdo.set_editor_property('use_controller_rotation_yaw', False)
    cdo.set_editor_property('use_controller_rotation_pitch', False)
    cdo.set_editor_property('use_controller_rotation_roll', False)
    capsule = cdo.get_editor_property('capsule_component')
    capsule.set_editor_property('capsule_half_height', 88.0)
    capsule.set_editor_property('capsule_radius', 30.0)
    movement = cdo.get_editor_property('character_movement')
    movement.set_editor_property('max_walk_speed', 0.0)
    movement.set_editor_property('orient_rotation_to_movement', False)
    sub, lib, entries = _subobjects(bp)
    capsule_name = next(e[0] for e in entries if isinstance(e[2], unreal.CapsuleComponent))
    origin = component(bp, 'VROrigin', unreal.SceneComponent, capsule_name)
    transform(origin, (0, 0, -88))
    camera = component(bp, 'QuestCamera', unreal.CameraComponent, 'VROrigin')
    transform(camera, (0, 0, 160))  # desktop fallback; HMD path uses floor pose at runtime
    camera.set_editor_property('lock_to_hmd', True)
    camera.set_editor_property('use_pawn_control_rotation', False)
    occluder = component(bp, 'QuestHeadOccluder', unreal.StaticMeshComponent, 'QuestCamera')
    occluder.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Sphere'))
    transform(occluder, size=(.35, .35, .35))
    occluder.set_material(0, panel_material('M_QuestHeadOcclusion', (0, 0, 0), two_sided=True))
    occluder.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    occluder.set_editor_property('cast_shadow', False)
    occluder.set_editor_property('only_owner_see', True)
    occluder.set_editor_property('receives_decals', False)
    occluder.set_editor_property('visible_in_reflection_captures', False)
    occluder.set_editor_property('visible', False)
    for name, source in [('LeftGrip', 'LeftGrip'), ('RightGrip', 'RightGrip'),
                         ('LeftAim', 'LeftAim'), ('RightAim', 'RightAim')]:
        c = component(bp, name, unreal.MotionControllerComponent, 'VROrigin')
        c.set_editor_property('motion_source', unreal.Name(source))
        c.set_editor_property('player_index', 0)
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    # Deliberate neutral hand/controller proxies, not unverified vendor meshes.
    sphere = unreal.load_asset('/Engine/BasicShapes/Sphere')
    for hand in ['LeftGrip', 'RightGrip']:
        c = component(bp, hand + 'Proxy', unreal.StaticMeshComponent, hand)
        c.set_static_mesh(sphere)
        transform(c, size=(.06, .035, .09))
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        c.set_editor_property('cast_shadow', False)
    panel = component(bp, 'QuestPanelRoot', unreal.SceneComponent, capsule_name)
    panel.set_editor_property('absolute_location', True)
    panel.set_editor_property('absolute_rotation', True)
    cube = unreal.load_asset('/Engine/BasicShapes/Cube')
    back = component(bp, 'QuestPanelBack', unreal.StaticMeshComponent, 'QuestPanelRoot')
    back.set_static_mesh(cube)
    back.set_material(0, panel_material('M_QuestPanel', (.012, .022, .028)))
    transform(back, (-1, 0, 0), size=(.012, 1.42, 1.12))
    back.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    back.set_editor_property('cast_shadow', False)
    # TextRender glyphs advance along local -Y, and its default bottom
    # alignment would push multiline text above the plate. Start at +Y/top.
    text_component(bp, 'QuestPanelTitle', 'QuestPanelRoot', (1, 65, 46), 7.0)
    text_component(bp, 'QuestPanelText', 'QuestPanelRoot', (1, 65, 32), 5.5)
    for i in range(1, 4):
        z = 28 - i * 20
        button = component(bp, 'QuestChoice' + str(i), unreal.StaticMeshComponent, 'QuestPanelRoot')
        button.set_static_mesh(cube)
        button.set_material(0, panel_material('M_QuestChoice', (.035, .07, .075)))
        transform(button, (0, 0, z), size=(.012, 1.3, .16))
        button.set_collision_profile_name('UI')
        button.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
        button.set_editor_property('cast_shadow', False)
        text_component(bp, 'QuestChoiceText' + str(i), 'QuestPanelRoot', (1, 62, z + 5), 6.0)
    text_component(bp, 'QuestStatusText', 'LeftGrip', (14, 13, 8), 1.2)
    marker = component(bp, 'QuestPointer', unreal.StaticMeshComponent, capsule_name)
    marker.set_static_mesh(sphere)
    marker.set_material(0, panel_material('M_QuestPointer', (.75, .43, .12)))
    transform(marker, size=(.016, .016, .016))
    marker.set_editor_property('absolute_location', True)
    marker.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    marker.set_editor_property('cast_shadow', False)
    return cdo


def wrapper(bp, name, quest_name, player_field='Player', is_hud=False):
    """Insert an XR branch before an existing function, preserving its body."""
    g = og.events(bp) if is_hud else og.Graph(bp, og.E.get_graph_editor(og.L.find_graph(bp, name)))
    entry = og.pin_out(g.event(name)) if is_hud else g.entry
    ed = g.editor
    comments = [c for c in ed.list_comment_nodes() if str(og.L.get_comment_text(c)) == MARKER + ':' + name]
    raw = unreal.EditorAssetLibrary.get_metadata_tag(bp, 'Quest.XRWrappers')
    records = json.loads(raw) if raw else {}
    names = records.get(name, [])
    marked = [n for n in ed.list_all_nodes() if n.get_name() in names]
    if not marked:
        marked = [n for c in comments for n in og.L.get_nodes_in_comment(c)]
    if comments and not marked:
        # Older v1 output predates durable node-name metadata. Recover exactly
        # the wrapper's entry branch, then call, and pure condition inputs.
        connected = list(og.P.list_connected_pins(entry))
        first = og.P.get_owning_node(connected[0]) if connected else None
        if first and first.get_class().get_name() == 'K2Node_IfThenElse':
            xr_call = list(og.P.list_connected_pins(og.pin_out(first, 'then')))
            if is_hud or (xr_call and 'quest' in str(og.L.get_node_title(og.P.get_owning_node(xr_call[0]))).lower()):
                marked = [first] + ([og.P.get_owning_node(xr_call[0])] if xr_call else [])
                todo = list(og.P.list_connected_pins(og.pin_in(first, 'Condition')))
                while todo:
                    n = og.P.get_owning_node(todo.pop())
                    if n in marked or n.get_class().get_name() in ['K2Node_FunctionEntry', 'K2Node_Event']:
                        continue
                    marked.append(n)
                    for p in og.L.list_input_pins(n):
                        todo.extend(og.P.list_connected_pins(p))
    if marked:
        # The branch owns the original desktop entry through its else pin.
        branch = next(n for n in marked if n.get_class().get_name() == 'K2Node_IfThenElse')
        original = list(og.P.list_connected_pins(og.pin_out(branch, 'else')))
        for comment in comments:
            ed.remove_comment_node(comment)
        ed.remove_nodes(marked)
    else:
        original = list(og.P.list_connected_pins(entry))
    og.P.break_pin_links(entry)
    before = set(n.get_path_name() for n in ed.list_all_nodes())
    f = Flow(g, entry)
    player = f.data(GS + 'GetPlayerCharacter', PlayerIndex=0) if is_hud else f.var(player_field)
    xr, desktop = f.branch(f.tag(player, 'Quest.XRPlayer'))
    for destination in original:
        og.link(desktop.cur, destination)
    if quest_name:
        params = {str(og.P.get_pin_name(p)): p for p in og.L.list_output_pins(g.entry_node)
                  if str(og.P.get_pin_name(p)) != 'then'}
        xr.own(quest_name, **params)
    new_nodes = [n for n in ed.list_all_nodes() if n.get_path_name() not in before]
    # Keep wrappers well away from original nodes so editor comment geometry
    # cannot accidentally absorb the preserved desktop implementation.
    for i, n in enumerate(new_nodes):
        og.L.set_node_pos(n, unreal.IntPoint(-2600 + (i % 5) * 300, -1000 + (i // 5) * 240))
    # The installed editor's comment-node helper omits NodeGuid. Durable asset
    # metadata is sufficient for ownership; avoid new cook nondeterminism.
    records[name] = [n.get_name() for n in new_nodes]
    unreal.EditorAssetLibrary.set_metadata_tag(bp, 'Quest.XRWrappers', json.dumps(records))


def build_character(manager):
    bp = og.blueprint(CHAR_PATH, unreal.Character)
    for name, kind, value in [('QuestXRActive', 'bool', False), ('QuestSnapLatched', 'bool', False),
                              ('QuestComfortSimulation', 'bool', False), ('QuestHeadBlocked', 'bool', False),
                              ('QuestModalAxisLatched', 'bool', False), ('QuestChoiceIndex', 'int', 1),
                              ('QuestLastMode', 'int', -1), ('QuestFlowMarker', 'int', 0)]:
        og.member(bp, name, kind, value)
    for name in ['QuestHeadBefore', 'QuestDestination', 'QuestBodyBefore']:
        og.member(bp, name, og.struct_type('vector'))
    og.member(bp, 'QuestController', og.object_type(unreal.PlayerController))
    og.member(bp, 'QuestManager', og.object_type(manager))
    og.member(bp, 'QuestIgnoredActors', og.array_type(og.object_type(unreal.Actor)))
    for name in ['QuestPanelTitle', 'QuestPanelText', 'QuestChoiceText1', 'QuestChoiceText2', 'QuestChoiceText3', 'QuestStatusText']:
        og.member(bp, 'QuestCached' + name, 'string', '')
    signatures = {'QuestBegin': {}, 'QuestFrame': {'DeltaSeconds': 'real'}, 'QuestInput': {},
                  'QuestPrimary': {}, 'QuestPanelFrame': {}, 'QuestPlacePanel': {}, 'QuestPhotoPose': {},
                  'QuestSnap': {'Angle': 'real'}, 'QuestTeleport': {}, 'QuestAlignHead': {},
                  'QuestCycleChoice': {}, 'QuestPointerTrace': {}, 'QuestRoomscale': {}, 'QuestHeadOcclusion': {},
                  'QuestSetComfortSimulation': {'Enabled': 'bool'}, 'QuestPickUI': {}}
    for name, inputs in signatures.items():
        reset_function(bp, name, inputs)
    # Derive the exact enum-array type from a reflected native pin; do not
    # guess an opaque FEdGraphPinType or construct a byte array instead.
    probe_graph = og.function(bp, 'QuestHeadOcclusion', reset=False)
    probe = probe_graph.call(SYS + 'SphereOverlapComponents')
    og.member(bp, 'QuestWorldObjectTypes', og.P.get_pin_type(og.pin_in(probe, 'ObjectTypes')))
    probe_graph.editor.remove_nodes([probe])
    og.compile_bp(bp)
    setup_components(bp)
    cdo = unreal.get_default_object(og.L.generated_class(bp))
    cdo.set_editor_property('QuestWorldObjectTypes', [unreal.ObjectTypeQuery.ECC_WORLD_STATIC,
                                                   unreal.ObjectTypeQuery.ECC_WORLD_DYNAMIC,
                                                   unreal.ObjectTypeQuery.ECC_PAWN,
                                                   unreal.ObjectTypeQuery.ECC_PHYSICS_BODY,
                                                   unreal.ObjectTypeQuery.ECC_VEHICLE,
                                                   unreal.ObjectTypeQuery.ECC_DESTRUCTIBLE])
    og.compile_bp(bp)
    def fn(name):
        return QFlow(reset_function(bp, name, signatures[name]))
    def key(f, k, held=False):
        return f.key(k, held)
    def any_key(f, *keys):
        result = key(f, keys[0])
        for k in keys[1:]:
            result = f.or_(result, key(f, k))
        return result

    f = fn('QuestBegin')
    f.set('QuestController', f.data(GS + 'GetPlayerController', PlayerIndex=0))
    f.set('QuestXRActive', f.data(HMD + 'IsHeadMountedDisplayEnabled'))
    f.call('/Script/Engine.KismetArrayLibrary.Array_AddUnique', TargetArray=f.var('QuestIgnoredActors'),
           NewItem=f.data(GS + 'GetPlayerCharacter', PlayerIndex=0))
    f.call(ACT + 'SetTickableWhenPaused', bTickableWhenPaused=True)
    active, fallback = f.branch(f.var('QuestXRActive'))
    active.call(HMD + 'SetTrackingOrigin', Origin='LocalFloor')
    active.call(SC + 'K2_SetRelativeLocation', **{'self': active.var('QuestCamera'),
                'NewLocation': unreal.Vector(0, 0, 0), 'bSweep': False, 'bTeleport': True})
    fallback.call(SC + 'K2_SetRelativeLocation', **{'self': fallback.var('QuestCamera'),
                  'NewLocation': unreal.Vector(0, 0, 160), 'bSweep': False, 'bTeleport': True})

    f = fn('QuestFrame')
    ready, missing = f.branch(f.valid(f.var('QuestManager')))
    actor = missing.data(GS + 'GetActorOfClass', ActorClass=MANAGER_CLASS)
    cast = missing.g.cast(manager, actor)
    og.link(missing.cur, og.pin_in(cast))
    assigned = QFlow(missing.g, og.pin_out(cast))
    assigned.set('QuestManager', missing.g.cast_value(cast))
    f = merge(ready, assigned)
    f.own('QuestRoomscale')
    f.own('QuestHeadOcclusion')
    f.own('QuestPanelFrame')
    f.own('QuestPhotoPose')
    f.own('QuestPointerTrace')
    # Physical head motion never reads controller look or scripted framing.
    # Mouse-look is deliberately absent: fallback proves graph/story only.

    f = fn('QuestPlacePanel')
    loc = location(f, 'QuestCamera')
    rot = rotation(f, 'QuestCamera')
    br = f.call(MATH + 'BreakRotator', InRot=rot)
    flat = f.data(MATH + 'MakeRotator', Roll=0, Pitch=0, Yaw=og.value_pin(br, 'Yaw'))
    fw = f.data(MATH + 'GetForwardVector', InRot=flat)
    position = add(f, add(f, loc, scale(f, fw, 180)), unreal.Vector(0, 0, -4))
    look = f.data(MATH + 'FindLookAtRotation', Start=position, Target=loc)
    f.call(SC + 'K2_SetWorldLocationAndRotation', **{'self': f.var('QuestPanelRoot'), 'NewLocation': position,
           'NewRotation': look, 'bSweep': False, 'bTeleport': True})

    f = fn('QuestPanelFrame')
    changed, same = f.branch(f.not_(f.eq(f.mv('Mode'), f.var('QuestLastMode'))))
    changed.set('QuestLastMode', changed.mv('Mode'))
    changed.set('QuestChoiceIndex', 1)
    changed.own('QuestPlacePanel')
    f = merge(changed, same)
    modal = f.not_(f.eq(f.mv('Mode'), 0))
    # Do not blanket-propagate visibility: that would re-show and then hide
    # unused response rows every frame, dirtying their render state repeatedly.
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestPanelRoot'), 'bNewVisibility': modal, 'bPropagateToChildren': False})
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestPanelBack'), 'bNewVisibility': modal, 'bPropagateToChildren': False})
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestPanelText'), 'bNewVisibility': modal, 'bPropagateToChildren': False})
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestPanelTitle'), 'bNewVisibility': modal, 'bPropagateToChildren': False})
    set_text(f, 'QuestPanelTitle', f.mv('PanelTitle'))
    paused = f.eq(f.mv('Mode'), 6)
    choosing = f.and_(modal, f.or_(paused, f.and_(f.eq(f.mv('Mode'), 3), f.mv('DialogueWaitingChoice'))))
    choice_text, body_text = f.branch(choosing)
    set_text(choice_text, 'QuestPanelText', 'Point at an option and press trigger.\nA cycles selection; trigger confirms.')
    text = body_text.mv('PanelText')
    text = join_text(body_text, text, '\n\nTrigger / E: continue or select\nB / Esc: close   A: cycle selection\nX / Q: watch   Y / Tab: journal\nSelected option: ')
    text = join_text(body_text, text, body_text.data(STR + 'Conv_IntToString', InInt=body_text.var('QuestChoiceIndex')))
    set_text(body_text, 'QuestPanelText', text)
    f = merge(choice_text, body_text)
    for i in range(1, 4):
        visible = f.and_(choosing, f.or_(paused, f.data(MATH + 'GreaterEqual_IntInt', A=f.mv('DialogueChoiceCount'), B=i)))
        f.call(SC + 'SetVisibility', **{'self': f.var('QuestChoice' + str(i)), 'bNewVisibility': visible,
               'bPropagateToChildren': False})
        f.call(SC + 'SetVisibility', **{'self': f.var('QuestChoiceText' + str(i)), 'bNewVisibility': visible,
               'bPropagateToChildren': False})
        on, off = f.branch(visible)
        on.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': on.var('QuestChoice' + str(i)), 'NewType': 'QueryOnly'})
        off.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': off.var('QuestChoice' + str(i)), 'NewType': 'NoCollision'})
        f = merge(on, off)
        pause_row, dialogue_row = f.branch(paused)
        for flow, label in [(pause_row, {1: 'Resume', 2: 'Save committed progress', 3: 'Load saved progress'}[i]),
                            (dialogue_row, dialogue_row.mv('ChoiceLabel' + str(i)))]:
            selected, ordinary = flow.branch(flow.eq(flow.var('QuestChoiceIndex'), i))
            set_text(selected, 'QuestChoiceText' + str(i), join_text(selected, '> ', label))
            set_text(ordinary, 'QuestChoiceText' + str(i), label)
            flow.cur = merge(selected, ordinary).cur
        f = merge(pause_row, dialogue_row)
    set_text(f, 'QuestStatusText', join_text(f, join_text(f, f.mv('Objective'), '\n'), f.mv('Prompt')))

    f = fn('QuestCycleChoice')
    photo, f = f.branch(f.eq(f.mv('Mode'), 1))
    photo.manager('FlipPhoto')
    watch, f = f.branch(f.eq(f.mv('Mode'), 4))
    island = watch.data(MATH + 'Add_IntInt', A=watch.mv('SelectedIsland'), B=1)
    wrap, valid = watch.branch(watch.data(MATH + 'Greater_IntInt', A=island, B=4))
    wrap.manager('SelectIsland', Island=1)
    valid.manager('SelectIsland', Island=island)
    next_ = f.data(MATH + 'Add_IntInt', A=f.var('QuestChoiceIndex'), B=1)
    paused, dialogue = f.branch(f.eq(f.mv('Mode'), 6))
    beyond, valid = paused.branch(paused.data(MATH + 'Greater_IntInt', A=next_, B=3))
    beyond.set('QuestChoiceIndex', 1)
    valid.set('QuestChoiceIndex', next_)
    beyond, valid = dialogue.branch(dialogue.data(MATH + 'Greater_IntInt', A=next_, B=dialogue.mv('DialogueChoiceCount')))
    beyond.set('QuestChoiceIndex', 1)
    valid.set('QuestChoiceIndex', next_)

    f = fn('QuestPrimary')
    explore, rest = f.branch(f.eq(f.mv('Mode'), 0))
    explore.manager('Interact')
    dialogue, rest = rest.branch(rest.eq(rest.mv('Mode'), 3))
    choice, advance = dialogue.branch(dialogue.mv('DialogueWaitingChoice'))
    choice.own('QuestPickUI')
    choice.manager('ChooseDialogue', ChoiceIndex=choice.var('QuestChoiceIndex'))
    advance.manager('AdvanceDialogue')
    document, rest = rest.branch(rest.eq(rest.mv('Mode'), 2))
    document.manager('CloseDocument')
    watch, rest = rest.branch(rest.eq(rest.mv('Mode'), 4))
    watch.manager('ConfirmWatch')
    paused, rest = rest.branch(rest.eq(rest.mv('Mode'), 6))
    paused.own('QuestPickUI')
    tail = paused
    for i, action in [(1, 'HandleOne'), (2, 'HandleTwo'), (3, 'HandleThree')]:
        selected, tail = tail.branch(tail.eq(tail.var('QuestChoiceIndex'), i))
        selected.manager(action)
    rest.manager('CloseModal')

    f = fn('QuestPickUI')
    # Both dialogue and pause use the same actual scene-component ray picker;
    # A/key selection remains the fallback when a row is difficult to point at.
    tracked, fallback = f.branch(f.data(MC + 'IsTracked', **{'self': f.var('RightAim')}))
    for flow, source in [(tracked, 'RightAim'), (fallback, 'QuestCamera')]:
        flow.set('QuestHeadBefore', location(flow, source))
        flow.set('QuestDestination', add(flow, flow.var('QuestHeadBefore'), scale(flow,
                 flow.data(SC + 'GetForwardVector', **{'self': flow.var(source)}), 500)))
    f = merge(tracked, fallback)
    trace = f.call(SYS + 'LineTraceSingle', Start=f.var('QuestHeadBefore'), End=f.var('QuestDestination'),
                   TraceChannel='TraceTypeQuery1', bTraceComplex=False, DrawDebugType='None', bIgnoreSelf=False)
    br = f.call(GS + 'BreakHitResult', Hit=og.value_pin(trace, 'OutHit'))
    hit_component = og.value_pin(br, 'HitComponent')
    for i in range(1, 4):
        selected, f = f.branch(f.data(MATH + 'EqualEqual_ObjectObject', A=hit_component, B=f.var('QuestChoice' + str(i))))
        selected.set('QuestChoiceIndex', i)

    f = fn('QuestInput')
    f, not_ready = f.branch(f.valid(f.var('QuestManager')))
    transition, f = f.branch(f.eq(f.mv('Mode'), 7))
    for keys, action in [(('OculusTouch_Right_Trigger_Click', 'E'), 'QuestPrimary'),
                         (('OculusTouch_Right_A_Click',), 'QuestCycleChoice')]:
        pressed, f = f.branch(any_key(f, *keys))
        pressed.own(action)
    close, f = f.branch(any_key(f, 'OculusTouch_Right_B_Click', 'Escape'))
    active, closed = close.branch(close.eq(close.mv('Mode'), 0))
    active.manager('OpenPause')
    closed.manager('CloseModal')
    watch, f = f.branch(any_key(f, 'OculusTouch_Left_X_Click', 'Q'))
    explore, blocked = watch.branch(watch.eq(watch.mv('Mode'), 0))
    explore.manager('OpenWatch')
    journal, f = f.branch(any_key(f, 'OculusTouch_Left_Y_Click', 'Tab'))
    explore, blocked = journal.branch(journal.eq(journal.mv('Mode'), 0))
    explore.manager('OpenJournal')
    for k, action in [('One', 'HandleOne'), ('Two', 'HandleTwo'), ('Three', 'HandleThree')]:
        pressed, f = f.branch(key(f, k))
        pressed.manager(action)
    flip, f = f.branch(any_key(f, 'R', 'OculusTouch_Left_Trigger_Click'))
    flip.manager('FlipPhoto')
    intro, other = flip.branch(flip.and_(flip.eq(flip.mv('Mode'), 3), flip.mv('IntroActive')))
    intro.manager('SkipRecollections')
    teleport, f = f.branch(any_key(f, 'OculusTouch_Left_Thumbstick_Click', 'T'))
    open_, blocked = teleport.branch(teleport.eq(teleport.mv('Mode'), 0))
    open_.own('QuestTeleport')
    # One snap per deflection, reset only near center; no joystick translation.
    axis = f.data(PC + 'GetInputAnalogKeyState', **{'self': f.var('Controller'), 'Key': '(KeyName="OculusTouch_Right_Thumbstick_X")'})
    centered, deflected = f.branch(f.data(MATH + 'Less_DoubleDouble', A=f.data(MATH + 'Abs', A=axis), B=.3))
    centered.set('QuestSnapLatched', False)
    unlatched, no = deflected.branch(deflected.not_(deflected.var('QuestSnapLatched')))
    plus, minus = unlatched.branch(unlatched.or_(unlatched.data(MATH + 'Greater_DoubleDouble', A=axis, B=.7), key(unlatched, 'Right')))
    minus, no = minus.branch(minus.or_(minus.data(MATH + 'Less_DoubleDouble', A=axis, B=-.7), key(minus, 'Left')))
    for flow, angle in [(plus, 30), (minus, -30)]:
        flow.set('QuestSnapLatched', True)
        explore, modal = flow.branch(flow.eq(flow.mv('Mode'), 0))
        explore.own('QuestSnap', Angle=angle)
        watch, modal = modal.branch(modal.eq(modal.mv('Mode'), 4))
        watch.manager('RotateDial', Direction=1 if angle > 0 else -1)
        journal, modal = modal.branch(modal.eq(modal.mv('Mode'), 5))
        journal.manager('TurnJournal', Direction=1 if angle > 0 else -1)
    for k, angle in [('PageUp', 30), ('PageDown', -30)]:
        pressed, rest = no.branch(key(no, k))
        explore, blocked = pressed.branch(pressed.eq(pressed.mv('Mode'), 0))
        explore.own('QuestSnap', Angle=angle)
        no = rest

    f = fn('QuestSnap')
    f.set('QuestHeadBefore', location(f, 'QuestCamera'))
    f.call(ACT + 'K2_AddActorWorldRotation', DeltaRotation=f.data(MATH + 'MakeRotator', Roll=0, Pitch=0, Yaw=f.g.input('Angle')),
           bSweep=False, bTeleport=True)
    delta = sub(f, f.var('QuestHeadBefore'), location(f, 'QuestCamera'))
    x, y, z = split_vec(f, delta)
    f.call(ACT + 'K2_AddActorWorldOffset', DeltaLocation=vec(f, x, y, 0), bSweep=True, bTeleport=True)

    f = fn('QuestTeleport')
    f, head_blocked = f.branch(f.not_(f.var('QuestHeadBlocked')))
    # Teleport targets are authored stable, walkable landing actors, not an
    # unchecked point on water, roofs or arbitrary rubble.
    loc = location(f, 'QuestCamera')
    tracked, fallback = f.branch(f.data(MC + 'IsTracked', **{'self': f.var('RightAim')}))
    tracked.set('QuestHeadBefore', location(tracked, 'RightAim'))
    tracked.set('QuestDestination', add(tracked, tracked.var('QuestHeadBefore'), scale(tracked,
                tracked.data(SC + 'GetForwardVector', **{'self': tracked.var('RightAim')}), 650)))
    fallback.set('QuestHeadBefore', loc)
    fallback.set('QuestDestination', add(fallback, fallback.var('QuestHeadBefore'), scale(fallback,
                 fallback.data(SC + 'GetForwardVector', **{'self': fallback.var('QuestCamera')}), 650)))
    f = merge(tracked, fallback)
    # A tracked hand may physically pass through a virtual door. Require an
    # unobstructed head-to-hand segment before trusting its outgoing ray.
    clearance = f.call(SYS + 'LineTraceSingle', Start=location(f, 'QuestCamera'), End=f.var('QuestHeadBefore'),
                       TraceChannel='TraceTypeQuery1', bTraceComplex=False, ActorsToIgnore=f.var('QuestIgnoredActors'),
                       DrawDebugType='None', bIgnoreSelf=True)
    f, hand_blocked = f.branch(f.not_(og.value_pin(clearance, 'ReturnValue')))
    trace = f.call(SYS + 'LineTraceSingle', Start=f.var('QuestHeadBefore'), End=f.var('QuestDestination'),
                   TraceChannel='TraceTypeQuery1', bTraceComplex=False, DrawDebugType='None', bIgnoreSelf=True)
    br = f.call(GS + 'BreakHitResult', Hit=og.value_pin(trace, 'OutHit'))
    actor = og.value_pin(br, 'HitActor')
    valid, no = f.branch(f.valid(actor))
    target, no = valid.branch(valid.tag(actor, 'Quest.Teleport'))
    # Component marker is drawn at the landing actor's floor origin.
    target.set('QuestDestination', target.data(ACT + 'K2_GetActorLocation', **{'self': actor}))
    head = location(target, 'QuestCamera')
    root = target.data(ACT + 'K2_GetActorLocation')
    dx, dy, dz = split_vec(target, sub(target, head, root))
    landing = sub(target, add(target, target.var('QuestDestination'), unreal.Vector(0, 0, 88)), vec(target, dx, dy, 0))
    target.call(ACT + 'K2_TeleportTo', DestLocation=landing, DestRotation=target.data(ACT + 'K2_GetActorRotation'))

    f = fn('QuestAlignHead')
    # Called after chapter travel/checkpoint placement; preserve physical yaw.
    root = f.data(ACT + 'K2_GetActorLocation')
    hx, hy, hz = split_vec(f, sub(f, root, location(f, 'QuestCamera')))
    f.call(ACT + 'K2_AddActorWorldOffset', DeltaLocation=vec(f, hx, hy, 0), bSweep=True, bTeleport=True)

    f = fn('QuestPhotoPose')
    photo, no = f.branch(f.and_(f.eq(f.mv('Mode'), 1), f.valid(f.mv('HeldPhoto'))))
    tracked, fallback = photo.branch(photo.data(MC + 'IsTracked', **{'self': photo.var('LeftGrip')}))
    tracked.set('QuestDestination', add(tracked, location(tracked, 'LeftGrip'), unreal.Vector(0, 0, 8)))
    fallback.set('QuestDestination', add(fallback, location(fallback, 'QuestCamera'), scale(fallback,
                 fallback.data(SC + 'GetForwardVector', **{'self': fallback.var('QuestCamera')}), 55)))
    photo = merge(tracked, fallback)
    photo.call(ACT + 'K2_SetActorLocation', **{'self': photo.mv('HeldPhoto'), 'NewLocation': photo.var('QuestDestination'),
               'bSweep': False, 'bTeleport': True})
    look = photo.data(MATH + 'FindLookAtRotation', Start=photo.var('QuestDestination'), Target=location(photo, 'QuestCamera'))
    photo.call(ACT + 'K2_SetActorRotation', **{'self': photo.mv('HeldPhoto'), 'NewRotation': look, 'bTeleportPhysics': True})
    back, front = photo.branch(photo.mv('PhotoBack'))
    back.call(ACT + 'K2_AddActorLocalRotation', **{'self': back.mv('HeldPhoto'), 'DeltaRotation': unreal.Rotator(pitch=0, yaw=180, roll=0), 'bSweep': False, 'bTeleport': True})

    f = fn('QuestPointerTrace')
    tracked, fallback = f.branch(f.data(MC + 'IsTracked', **{'self': f.var('RightAim')}))
    for flow, component_ in [(tracked, 'RightAim'), (fallback, 'QuestCamera')]:
        flow.set('QuestHeadBefore', location(flow, component_))
        flow.set('QuestDestination', add(flow, flow.var('QuestHeadBefore'), scale(flow,
                 flow.data(SC + 'GetForwardVector', **{'self': flow.var(component_)}), 650)))
    f = merge(tracked, fallback)
    trace = f.call(SYS + 'LineTraceSingle', Start=f.var('QuestHeadBefore'), End=f.var('QuestDestination'),
                   TraceChannel='TraceTypeQuery1', bTraceComplex=False, DrawDebugType='None', bIgnoreSelf=False)
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestPointer'), 'bNewVisibility': og.value_pin(trace, 'ReturnValue'), 'bPropagateToChildren': False})
    hit, no = f.branch(og.value_pin(trace, 'ReturnValue'))
    br = hit.call(GS + 'BreakHitResult', Hit=og.value_pin(trace, 'OutHit'))
    hit.call(SC + 'K2_SetWorldLocation', **{'self': hit.var('QuestPointer'), 'NewLocation': og.value_pin(br, 'ImpactPoint'), 'bSweep': False, 'bTeleport': True})

    f = fn('QuestSetComfortSimulation')
    f.set('QuestComfortSimulation', f.g.input('Enabled'))

    f = fn('QuestRoomscale')
    active, no = f.branch(f.or_(f.var('QuestXRActive'), f.var('QuestComfortSimulation')))
    active.set('QuestBodyBefore', active.data(ACT + 'K2_GetActorLocation'))
    x, y, z = split_vec(active, sub(active, location(active, 'QuestCamera'), active.var('QuestBodyBefore')))
    active.call(ACT + 'K2_AddActorWorldOffset', DeltaLocation=vec(active, x, y, 0), bSweep=True, bTeleport=True)
    actual = sub(active, active.data(ACT + 'K2_GetActorLocation'), active.var('QuestBodyBefore'))
    active.call(SC + 'K2_AddWorldOffset', **{'self': active.var('VROrigin'), 'DeltaLocation': scale(active, actual, -1),
                'bSweep': False, 'bTeleport': True})

    f = fn('QuestHeadOcclusion')
    f.set('QuestHeadBlocked', False)
    # Pawn BeginPlay may precede possession. Refresh the local player ignore
    # entry here so its own capsule can never black out the tracked camera.
    f.call('/Script/Engine.KismetArrayLibrary.Array_AddUnique', TargetArray=f.var('QuestIgnoredActors'),
           NewItem=f.data(GS + 'GetPlayerCharacter', PlayerIndex=0))
    active, no = f.branch(f.or_(f.var('QuestXRActive'), f.var('QuestComfortSimulation')))
    # Built-in world/pawn/physics/vehicle/destructible object types are queried;
    # only actual Pawn-blocking responses occlude. Visual clutter
    # with Pawn=Ignore does not black out the view. Ignore the player's own rig.
    overlap = active.call(SYS + 'SphereOverlapComponents', SpherePos=location(active, 'QuestCamera'),
                          SphereRadius=12.0, ObjectTypes=active.var('QuestWorldObjectTypes'),
                          ComponentClassFilter='/Script/Engine.PrimitiveComponent',
                          ActorsToIgnore=active.var('QuestIgnoredActors'))
    loop = active.g._node(active.g.editor.add_macro_node('/Engine/EditorBlueprintResources/StandardMacros.StandardMacros:ForEachLoop'), 'ForEachLoop')
    og.link(active.cur, og.pin_in(loop, 'Exec'))
    og.link(og.value_pin(overlap, 'OutComponents'), og.pin_in(loop, 'Array'))
    body = QFlow(active.g, og.pin_out(loop, 'LoopBody'))
    response = body.data('/Script/Engine.PrimitiveComponent.GetCollisionResponseToChannel',
                         **{'self': og.value_pin(loop, 'Array Element'), 'Channel': 'ECC_Pawn'})
    solid, ignore = body.branch(body.data(MATH + 'EqualEqual_ByteByte', A=response, B=2))
    solid.set('QuestHeadBlocked', True)
    completed = QFlow(active.g, og.pin_out(loop, 'Completed'))
    f = merge(completed, no)
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestHeadOccluder'), 'bNewVisibility': f.var('QuestHeadBlocked'),
           'bPropagateToChildren': False})
    ev = og.events(bp)
    ev.editor.remove_nodes(ev.editor.list_all_nodes())
    begin = og.L.add_event_override(bp, 'ReceiveBeginPlay', unreal.IntPoint(0, 0))
    node = ev.call(CHAR_CLASS + ':QuestBegin')
    og.chain(begin, node)
    tick = og.L.add_event_override(bp, 'ReceiveTick', unreal.IntPoint(0, 300))
    node = ev.call(CHAR_CLASS + ':QuestFrame')
    og.link(og.pin_out(tick), og.pin_in(node))
    og.link(og.value_pin(tick, 'DeltaSeconds'), og.pin_in(node, 'DeltaSeconds'))
    cdo = unreal.get_default_object(og.L.generated_class(bp))
    tags = list(cdo.get_editor_property('tags'))
    if unreal.Name('Quest.XRPlayer') not in tags:
        tags.append(unreal.Name('Quest.XRPlayer'))
    cdo.set_editor_property('tags', tags)
    return bp


def patch_manager(manager, character):
    for graph in og.L.list_graphs(manager):
        ed = og.E.get_graph_editor(graph)
        for comment in list(ed.list_comment_nodes()):
            if str(og.L.get_comment_text(comment)) == 'Quest.Recenter':
                ed.remove_comment_node(comment)
    for n, kind, value in [('QuestFlowMarker', 'int', 0)]:
        og.member(manager, n, kind, value)
    og.member(manager, 'QuestRayStart', og.struct_type('vector'))
    og.member(manager, 'QuestRayEnd', og.struct_type('vector'))
    signatures = {'_Quest_SetMode': {'NewMode': 'int'}, '_Quest_MovementFrame': {}, '_Quest_InputFrame': {},
                  '_Quest_CameraFraming': {'DeltaSeconds': 'real'}, '_Quest_UpdateTarget': {},
                  '_Quest_OpenPause': {}, '_Quest_Recenter': {}}
    for name, inputs in signatures.items():
        reset_function(manager, name, inputs)
    og.compile_bp(manager)
    def fn(name):
        return Flow(reset_function(manager, name, signatures[name]))
    def character_call(f, function):
        cast = f.g.cast(character, f.var('Player'))
        og.link(f.cur, og.pin_in(cast))
        castflow = Flow(f.g, og.pin_out(cast))
        castflow.call(CHAR_CLASS + ':' + function, **{'self': f.g.cast_value(cast)})

    f = fn('_Quest_SetMode')
    f.set('Mode', f.g.input('NewMode'))
    f.call(CTL + 'ResetIgnoreMoveInput', **{'self': f.var('Controller')})
    f.call(CTL + 'ResetIgnoreLookInput', **{'self': f.var('Controller')})
    # Locomotion is gated in QuestInput. Tracked head rotation is always live.
    fn('_Quest_MovementFrame')
    fn('_Quest_CameraFraming')
    f = fn('_Quest_InputFrame')
    character_call(f, 'QuestInput')
    f = fn('_Quest_Recenter')
    xr, no = f.branch(f.tag(f.var('Player'), 'Quest.XRPlayer'))
    character_call(xr, 'QuestAlignHead')
    f = fn('_Quest_OpenPause')
    f.set('PauseReturnMode', f.var('Mode'))
    f.own('RestorePhoto')
    f.set('Testing', False)
    f.panel(6, 'Paused', '1  Resume\n\n2  Save committed progress\n\n3  Load saved progress',
            'B / Esc  Resume    1 / 2 / 3  Choose')
    # Do not pause XR tracking or input dispatch with SetGamePaused.

    f = fn('_Quest_UpdateTarget')
    f.set('Target', None)
    f.set('Prompt', '')
    active, no = f.guarded_mode(0)
    cast = active.g.cast(character, active.var('Player'))
    og.link(active.cur, og.pin_in(cast))
    active = Flow(active.g, og.pin_out(cast))
    pawn = active.g.cast_value(cast)
    aim = active.var('RightAim', pawn, CHAR_CLASS)
    tracked, fallback = active.branch(active.data(MC + 'IsTracked', **{'self': aim}))
    for flow, component_ in [(tracked, aim), (fallback, flow_camera := active.var('QuestCamera', pawn, CHAR_CLASS))]:
        loc = flow.data(SC + 'K2_GetComponentLocation', **{'self': component_})
        fw = flow.data(SC + 'GetForwardVector', **{'self': component_})
        flow.set('QuestRayStart', loc)
        flow.set('QuestRayEnd', add(flow, loc, scale(flow, fw, flow.var('InteractionRange'))))
    active = merge(tracked, fallback)
    trace = active.call(SYS + 'LineTraceSingle', Start=active.var('QuestRayStart'), End=active.var('QuestRayEnd'),
                        TraceChannel='TraceTypeQuery1', bTraceComplex=False, ActorsToIgnore=active.var('IgnoredActors'),
                        DrawDebugType='None', bIgnoreSelf=True)
    active.set('DebugTraceStart', active.var('QuestRayStart'))
    active.set('DebugTraceEnd', active.var('QuestRayEnd'))
    active.set('DebugTraceHit', og.value_pin(trace, 'ReturnValue'))
    hit, no = active.branch(og.value_pin(trace, 'ReturnValue'))
    br = hit.call(GS + 'BreakHitResult', Hit=og.value_pin(trace, 'OutHit'))
    actor = og.value_pin(br, 'HitActor')
    hit.set('DebugHitActor', actor)
    interactable, no = hit.branch(hit.tag(actor, 'Opening.Interactable'))
    interactable.set('Target', actor)
    interactable.set('Prompt', 'Right trigger / E  Interact')

    for name, quest_name in [('SetMode', '_Quest_SetMode'), ('MovementFrame', '_Quest_MovementFrame'),
                             ('InputFrame', '_Quest_InputFrame'), ('CameraFraming', '_Quest_CameraFraming'),
                             ('UpdateTarget', '_Quest_UpdateTarget'), ('OpenPause', '_Quest_OpenPause')]:
        wrapper(manager, name, quest_name)

    # Add head-offset correction after story-owned player checkpoint placements.
    for name in ['RestorePlayerCheckpoint', 'TravelTick']:
        graph = og.L.find_graph(manager, name)
        ed = og.E.get_graph_editor(graph)
        for n in list(ed.list_all_nodes()):
            if str(og.L.get_node_title(n)).replace(' ', '').lower().startswith('setactorlocation'):
                selfpin = og.L.find_input_pin(n, 'self')
                linked = list(og.P.list_connected_pins(selfpin)) if og.P.is_valid(selfpin) else []
                if not any(str(og.P.get_pin_name(p)) == 'Player' for p in linked):
                    continue
                then = og.pin_out(n)
                connected = list(og.P.list_connected_pins(then))
                if any('questrecenter' in str(og.L.get_node_title(og.P.get_owning_node(p))).replace(' ', '').replace('_', '').lower() for p in connected):
                    continue
                og.P.break_pin_links(then)
                g = og.Graph(manager, ed)
                call = g.call(MANAGER_CLASS + ':_Quest_Recenter')
                og.link(then, og.pin_in(call))
                for destination in connected:
                    og.link(og.pin_out(call), destination)


def main():
    report = {'success': False, 'target': 'Quest 3 / 3S standalone', 'runtime': 'Native Blueprints',
              'headset_tested': False, 'apk_built': False,
              'limitations': ['Neutral controller proxies; rigged hand animation and grip pickup not implemented',
                             'No smooth locomotion; teleport requires authored Quest.Teleport actors',
                             'Room-scale following and opaque head occlusion require physical headset validation',
                             'No vendor foveation, performance certification or store submission',
                             'Desktop fallback is a graph/story check, not a VR result']}
    settings = unreal.get_default_object(unreal.load_class(None, '/Script/BlueprintGraph.BlueprintEditorSettings'))
    old_promotion = settings.get_editor_property('bEnableTypePromotion')
    try:
        settings.set_editor_property('bEnableTypePromotion', False)
        manager = unreal.load_asset(MANAGER_PATH)
        if manager is None:
            raise RuntimeError('Existing native chapter manager is required')
        character = build_character(manager)
        og.compile_bp(character)
        patch_manager(manager, character)
        # Retain a previously queued hand upgrade on subsequent core rebuilds.
        # This never imports staging automatically; the separate hands writer
        # requires an explicit flag and its own serialized asset-writing slot.
        if unreal.EditorAssetLibrary.get_metadata_tag(character, 'Quest.HandsUpgrade') == '1':
            import quest_xr_hands
            report['hands'] = quest_xr_hands.upgrade_blueprint(character)
            report['limitations'][0] = 'Matte articulated Epic template hands; physical grip pickup not implemented'
        hud = unreal.load_asset('/Game/Opening/Blueprints/BP_OpeningHUD')
        wrapper(hud, 'ReceiveDrawHUD', None, is_hud=True)
        gm = og.blueprint(GM_PATH, unreal.GameModeBase)
        og.compile_bp(gm)
        cdo = unreal.get_default_object(og.L.generated_class(gm))
        cdo.set_editor_property('default_pawn_class', og.L.generated_class(character))
        cdo.set_editor_property('hud_class', unreal.HUD)
        report['compiled'] = og.compile_all([character, manager, hud, gm], save=True)
        report['success'] = True
        report['assets'] = [CHAR_PATH, GM_PATH, MANAGER_PATH]
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    finally:
        settings.set_editor_property('bEnableTypePromotion', old_promotion)
        (ROOT / 'quest_xr_build_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if not report['success']:
        raise RuntimeError('Quest native Blueprint authoring failed; inspect quest_xr_build_report.json')


if __name__ == '__main__':
    main()
