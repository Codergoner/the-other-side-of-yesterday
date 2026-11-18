"""Queued Epic XR hand presentation upgrade; never run during cook.

Importing this module does not write assets. The explicit main entry point
copies the verified staging pack into its original /Game/XRMannequins mount,
inspects the real assets, then updates only the owned Quest Character rig.
No new input framework, physics grab, hand tracking, story or camera behavior.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Quest_20261025'
sys.path.insert(0, str(ROOT / 'Python'))
import opening_graph as og
import build_quest_xr as core
MANIFEST = ROOT.parent / 'output/staging/xr_hands/manifest.json'
REPORT = ROOT / 'quest_hands_build_report.json'
PACK = '/Game/XRMannequins'
RIG_PATH = PACK + '/BP_MannequinsXR'
RIG_CLASS = RIG_PATH + '.BP_MannequinsXR_C'
ANIM_PATH = PACK + '/Meshes/ABP_MannequinsXR'
ANIM_CLASS = ANIM_PATH + '.ABP_MannequinsXR_C'
MATERIAL_PATH = '/Game/Quest/XR/Hands/Materials/M_QuestMatteGlove'
SC = '/Script/Engine.SceneComponent.'
SKEL = '/Script/Engine.SkeletalMeshComponent.'
PRIM = '/Script/Engine.PrimitiveComponent.'
POSE_FIELDS = ['PoseAlphaGrasp', 'PoseAlphaIndexCurl', 'PoseAlphaPoint', 'PoseAlphaThumbUp', 'bMirror']
CALIBRATION = ROOT / 'Python/quest_hand_attachment_calibration.json'
GLOVE_ALBEDO = (.152, .0928, .0512)
GLOVE_VERSION = 'Chestnut1p6_20261025'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plain_vector(v):
    return [float(v.x), float(v.y), float(v.z)]


def plain_rotator(r):
    return {'pitch': float(r.pitch), 'yaw': float(r.yaw), 'roll': float(r.roll)}


def template_grip_attachments():
    """Owning Epic Pawn overrides are essential; component CDO is identity."""
    report = json.loads(CALIBRATION.read_text(encoding='utf-8'))
    source = Path(report['source'])
    assert source.exists() and digest(source) == report['source_sha256'], 'Installed Epic Pawn differs from native attachment inspection'
    for side in ['Left', 'Right']:
        value = report['attachments']['Hand' + side]
        assert value['parent_variable'] == 'MotionController' + side + 'Grip'
        assert value['scale'] == [1.0, 1.0, 1.0]
    return report['attachments']


def install_staged_pack():
    """Explicit queued operation. Refuse to overwrite any changed package."""
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    installed = []
    for entry in manifest['files']:
        source = Path(entry['staged'])
        destination = ROOT / 'Content/XRMannequins' / entry['relative']
        assert destination.resolve().is_relative_to((ROOT / 'Content/XRMannequins').resolve())
        if digest(source) != entry['sha256']:
            raise RuntimeError('Staged hand package changed: ' + str(source))
        if destination.exists():
            if digest(destination) != entry['sha256']:
                raise RuntimeError('Refusing to overwrite an existing modified package: ' + str(destination))
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            installed.append(str(destination))
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous([PACK], True)
    return {'copied': installed, 'file_count': manifest['file_count'], 'bytes': manifest['bytes'],
            'provenance': manifest['provenance'], 'mount_preserved': PACK}


def inspect_template():
    """Native gate: no inferred bone frames or invented API names."""
    rig = unreal.load_asset(RIG_PATH)
    anim = unreal.load_asset(ANIM_PATH)
    if not isinstance(rig, unreal.Blueprint) or not isinstance(anim, unreal.AnimBlueprint):
        raise RuntimeError('Verified XRMannequins pack must be imported before native inspection')
    rig_cdo = unreal.get_default_object(og.L.generated_class(rig))
    anim_cdo = unreal.get_default_object(og.L.generated_class(anim))
    fields = {}
    for name in POSE_FIELDS:
        value = anim_cdo.get_editor_property(name)
        fields[name] = {'type': type(value).__name__, 'default': value}
    if not all(isinstance(fields[n]['default'], (int, float)) for n in POSE_FIELDS[:-1]):
        raise RuntimeError('Template pose input types differ from the expected scalar fields')
    sub, lib, entries = core._subobjects(rig)
    if not isinstance(rig_cdo, unreal.SkeletalMeshComponent):
        raise RuntimeError('Stock hand rig is not the inspected skeletal-component Blueprint')
    native_components = [rig_cdo] + list(rig_cdo.get_children_components(True))
    controllers = [c.get_name() for c in native_components if isinstance(c, unreal.MotionControllerComponent)]
    controllers += [name for name, handle, obj, data in entries if isinstance(obj, unreal.MotionControllerComponent)]
    if controllers:
        raise RuntimeError('Refusing nested tracking components in stock hand actor: ' + str(controllers))
    mesh_components = [obj for name, handle, obj, data in entries if isinstance(obj, unreal.SkeletalMeshComponent)]
    if not mesh_components:
        mesh_components = [c for c in native_components if isinstance(c, unreal.SkeletalMeshComponent)]
    if len(mesh_components) != 1:
        raise RuntimeError('Expected one stock hand skeletal component, got ' + str(len(mesh_components)))
    template = mesh_components[0]
    editor = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    meshes = {}
    for side in ['left', 'right']:
        mesh = unreal.load_asset(PACK + '/Meshes/SKM_QuinnXR_' + side)
        skeleton = mesh.get_editor_property('skeleton')
        if skeleton.get_path_name() != PACK + '/Meshes/SK_MannequinsXR.SK_MannequinsXR':
            raise RuntimeError('Unexpected hand skeleton: ' + skeleton.get_path_name())
        lods = [{'lod': i, 'vertices': editor.get_num_verts(mesh, i), 'sections': editor.get_num_sections(mesh, i)}
                for i in range(editor.get_lod_count(mesh))]
        if not lods or lods[0]['vertices'] <= 0 or lods[0]['sections'] <= 0:
            raise RuntimeError('Native hand mesh LOD data did not load: ' + mesh.get_path_name())
        meshes[side] = {'asset': mesh.get_path_name(), 'skeleton': skeleton.get_path_name(), 'lods': lods,
                        'material_slots': len(mesh.get_editor_property('materials'))}
    return {'rig': rig.get_path_name(), 'anim_blueprint': anim.get_path_name(), 'anim_inputs': fields,
            'components': [{'name': name, 'class': obj.get_class().get_path_name() if obj else None}
                           for name, handle, obj, data in entries] +
                          [{'name': c.get_name(), 'class': c.get_class().get_path_name()} for c in native_components],
            'nested_tracking_components': controllers,
            'stock_component_mirror_default': rig_cdo.get_editor_property('bMirror'), 'meshes': meshes,
            'rig_kind': 'SkeletalMeshComponent Blueprint; directly attached, no child actor or second tracking source',
            'template_component_transform': {'location_cm': plain_vector(template.get_editor_property('relative_location')),
                                             'rotation_degrees': plain_rotator(template.get_editor_property('relative_rotation')),
                                             'scale': plain_vector(template.get_editor_property('relative_scale3d'))},
            'attachment_frame': 'Direct child of existing OpenXR Grip; component CDO is not the Pawn attachment calibration. Exact owning BP_XRPawn overrides are recorded separately.',
            'orientation_gate': 'Must inspect simulated hand screenshots and bone transforms before accepting the presentation; physical controller calibration remains pending'}


def matte_material():
    asset = unreal.load_asset(MATERIAL_PATH)
    if asset:
        # A cooked skeletal permutation cannot rely on the editor's automatic
        # usage discovery. Preserve the authored graph, save the explicit flag.
        color = unreal.MaterialEditingLibrary.get_material_property_input_node(asset, unreal.MaterialProperty.MP_BASE_COLOR)
        assert isinstance(color, unreal.MaterialExpressionConstant3Vector), 'Owned glove albedo graph changed'
        previous = color.get_editor_property('constant')
        allowed = [(.095, .058, .032), GLOVE_ALBEDO]
        assert any(all(abs(a - b) < .0001 for a, b in zip((previous.r, previous.g, previous.b), target)) for target in allowed), 'Owned glove albedo has a manual change'
        changed = any(abs(a - b) > .00001 for a, b in zip((previous.r, previous.g, previous.b), GLOVE_ALBEDO))
        if changed or not asset.get_editor_property('used_with_skeletal_mesh') or unreal.EditorAssetLibrary.get_metadata_tag(asset, 'Quest.HandMaterialVersion') != GLOVE_VERSION:
            color.set_editor_property('constant', unreal.LinearColor(*GLOVE_ALBEDO, 1))
            asset.set_editor_property('used_with_skeletal_mesh', True)
            unreal.EditorAssetLibrary.set_metadata_tag(asset, 'Quest.HandMaterialVersion', GLOVE_VERSION)
            unreal.MaterialEditingLibrary.recompile_material(asset)
            unreal.EditorAssetLibrary.save_loaded_asset(asset)
        return asset
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'M_QuestMatteGlove', '/Game/Quest/XR/Hands/Materials', unreal.Material, unreal.MaterialFactoryNew())
    asset.set_editor_property('used_with_skeletal_mesh', True)
    color = unreal.MaterialEditingLibrary.create_material_expression(asset, unreal.MaterialExpressionConstant3Vector, -250, 0)
    color.set_editor_property('constant', unreal.LinearColor(*GLOVE_ALBEDO, 1))
    unreal.MaterialEditingLibrary.connect_material_property(color, '', unreal.MaterialProperty.MP_BASE_COLOR)
    for index, value, prop in [(1, .9, unreal.MaterialProperty.MP_ROUGHNESS),
                               (2, 0.0, unreal.MaterialProperty.MP_METALLIC),
                               (3, .18, unreal.MaterialProperty.MP_SPECULAR)]:
        node = unreal.MaterialEditingLibrary.create_material_expression(asset, unreal.MaterialExpressionConstant, -250, index * 100)
        node.set_editor_property('r', value)
        unreal.MaterialEditingLibrary.connect_material_property(node, '', prop)
    unreal.MaterialEditingLibrary.recompile_material(asset)
    unreal.EditorAssetLibrary.set_metadata_tag(asset, 'Quest.HandMaterialVersion', GLOVE_VERSION)
    unreal.EditorAssetLibrary.save_loaded_asset(asset)
    return asset


def _normalize_title(node):
    return str(og.L.get_node_title(node)).replace(' ', '').replace('_', '').lower()


def _install_hooks(bp):
    graph = og.events(bp)
    ed = graph.editor
    owned = [n for n in ed.list_all_nodes() if _normalize_title(n).startswith(('questhandsbegin', 'questhandsframe'))]
    if owned:
        ed.remove_nodes(owned)
    for original, addition, event in [('questbegin', 'QuestHandsBegin', 'ReceiveBeginPlay'),
                                       ('questframe', 'QuestHandsFrame', 'ReceiveTick')]:
        candidates = [n for n in ed.list_all_nodes() if _normalize_title(n).startswith(original)]
        if len(candidates) != 1:
            raise RuntimeError('Cannot locate the preserved core event call ' + original)
        tail = og.pin_out(candidates[0])
        if list(og.P.list_connected_pins(tail)):
            raise RuntimeError('Core event already has an unowned continuation: ' + original)
        call = graph.call(core.CHAR_CLASS + ':' + addition)
        og.link(tail, og.pin_in(call))
        if event == 'ReceiveTick':
            source = ed.find_event_node(event)
            og.link(og.value_pin(source, 'DeltaSeconds'), og.pin_in(call, 'DeltaSeconds'))


def upgrade_blueprint(bp, inspection=None):
    """Author native hand presentation after the original XR functions exist."""
    inspection = inspection or inspect_template()
    material = matte_material()
    rig_class = unreal.load_class(None, RIG_CLASS)
    anim_bp = unreal.load_asset(ANIM_PATH)
    anim_class = og.L.generated_class(anim_bp)
    attachments = template_grip_attachments()
    for name in ['QuestHandsReady', 'QuestHandsPreview']:
        og.member(bp, name, 'bool', False)
    for side in ['Left', 'Right']:
        og.member(bp, 'QuestHandMesh' + side, og.object_type(unreal.SkeletalMeshComponent))
        og.member(bp, 'QuestHandAnim' + side, og.object_type(anim_bp))
        for value in ['Grip', 'Trigger']:
            og.member(bp, 'QuestHand' + side + value, 'real', 0)
            og.member(bp, 'QuestHandPreview' + side + value, 'real', 0)
        visual = core.component(bp, 'QuestHandVisual' + side, rig_class, side + 'Grip')
        authored = attachments['Hand' + side]
        rotation = authored['rotation_degrees']
        core.transform(visual, authored['location_cm'],
                       (rotation['pitch'], rotation['yaw'], rotation['roll']), authored['scale'])
        visual.set_editor_property('bMirror', side == 'Left')
        visual.set_skeletal_mesh_asset(unreal.load_asset(PACK + '/Meshes/SKM_QuinnXR_' + side.lower()))
        visual.set_anim_instance_class(anim_class)
        visual.set_material(0, material)
        visual.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        visual.set_only_owner_see(True)
        visual.set_cast_shadow(False)
    signatures = {'QuestHandsBegin': {}, 'QuestHandsFrame': {'DeltaSeconds': 'real'},
                  'QuestSetHandsPreview': {'Enabled': 'bool', 'LeftGrip': 'real', 'LeftTrigger': 'real',
                                           'RightGrip': 'real', 'RightTrigger': 'real'}}
    for name, params in signatures.items():
        core.reset_function(bp, name, params)
    og.compile_bp(bp)
    def fn(name):
        return core.QFlow(core.reset_function(bp, name, signatures[name]))

    f = fn('QuestHandsBegin')
    for side, mirror in [('Left', True), ('Right', False)]:
        mesh_ref = f.var('QuestHandVisual' + side)
        ready, missing = f.branch(f.valid(mesh_ref))
        ready.set('bMirror', mirror, mesh_ref, RIG_CLASS)
        ready.set('QuestHandMesh' + side, mesh_ref)
        ready.call(SKEL + 'SetSkeletalMeshAsset', **{'self': mesh_ref, 'NewMesh': unreal.load_asset(PACK + '/Meshes/SKM_QuinnXR_' + side.lower())})
        ready.call(SKEL + 'SetAnimInstanceClass', **{'self': mesh_ref, 'NewClass': anim_class})
        ready.call(PRIM + 'SetMaterial', **{'self': mesh_ref, 'ElementIndex': 0, 'Material': material})
        ready.call(PRIM + 'SetCollisionEnabled', **{'self': mesh_ref, 'NewType': 'NoCollision'})
        ready.call(PRIM + 'SetOnlyOwnerSee', **{'self': mesh_ref, 'bNewOnlyOwnerSee': True})
        ready.call(PRIM + 'SetCastShadow', **{'self': mesh_ref, 'NewCastShadow': False})
        # Retain authored LODs. Only force LOD1 when it exists and LOD0 is
        # unusually dense; recorded native vertex counts make this reviewable.
        lods = inspection['meshes'][side.lower()]['lods']
        forced = 2 if len(lods) > 1 and lods[0]['vertices'] > 8000 else 0
        ready.call('/Script/Engine.SkinnedMeshComponent.SetForcedLOD', **{'self': mesh_ref, 'InNewForcedLOD': forced})
        instance = ready.data(SKEL + 'GetAnimInstance', **{'self': mesh_ref})
        anim_cast = ready.g.cast(anim_class, instance)
        og.link(ready.cur, og.pin_in(anim_cast))
        initialized = core.QFlow(ready.g, og.pin_out(anim_cast))
        initialized.set('QuestHandAnim' + side, initialized.g.cast_value(anim_cast))
        initialized.set('bMirror', mirror, initialized.var('QuestHandAnim' + side), ANIM_CLASS)
        f = core.merge(initialized, missing, core.QFlow(f.g, og.pin_out(anim_cast, 'CastFailed')))
    f.set('QuestHandsReady', f.and_(f.valid(f.var('QuestHandAnimLeft')), f.valid(f.var('QuestHandAnimRight'))))

    f = fn('QuestHandsFrame')
    ready, initialize = f.branch(f.var('QuestHandsReady'))
    initialize.own('QuestHandsBegin')
    f = ready
    for side in ['Left', 'Right']:
        tracked = f.data(core.MC + 'IsTracked', **{'self': f.var(side + 'Grip')})
        visible = f.or_(tracked, f.var('QuestHandsPreview'))
        f.call('/Script/Engine.ActorComponent.SetComponentTickEnabled', **{'self': f.var('QuestHandMesh' + side), 'bEnabled': visible})
        f.call(SC + 'SetVisibility', **{'self': f.var('QuestHandMesh' + side), 'bNewVisibility': visible, 'bPropagateToChildren': False})
        f.call(SC + 'SetVisibility', **{'self': f.var(side + 'GripProxy'), 'bNewVisibility': False, 'bPropagateToChildren': False})
        simulated, live = f.branch(f.var('QuestHandsPreview'))
        for channel in ['Grip', 'Trigger']:
            simulated.set('QuestHand' + side + channel, simulated.var('QuestHandPreview' + side + channel))
            raw = live.data(core.PC + 'GetInputAnalogKeyState', **{'self': live.var('Controller'),
                            'Key': '(KeyName="OculusTouch_' + side + '_' + channel + '_Axis")'})
            current = 'QuestHand' + side + channel
            target = live.data(core.MATH + 'FClamp', Value=raw, Min=0.0, Max=1.0)
            live.set(current, live.data(core.MATH + 'FInterpTo', Current=live.var(current), Target=target,
                                      DeltaTime=live.g.input('DeltaSeconds'), InterpSpeed=12.0))
        f = core.merge(simulated, live)
        owner = f.var('QuestHandAnim' + side)
        for name, value in [('PoseAlphaGrasp', f.var('QuestHand' + side + 'Grip')),
                            ('PoseAlphaIndexCurl', f.var('QuestHand' + side + 'Trigger')),
                            ('PoseAlphaPoint', 0.0), ('PoseAlphaThumbUp', 0.0), ('bMirror', side == 'Left')]:
            f.set(name, value, owner, ANIM_CLASS)

    f = fn('QuestSetHandsPreview')
    enabled = f.and_(f.g.input('Enabled'), f.not_(f.var('QuestXRActive')))
    f.set('QuestHandsPreview', enabled)
    for side in ['Left', 'Right']:
        for channel in ['Grip', 'Trigger']:
            f.set('QuestHandPreview' + side + channel, f.data(core.MATH + 'FClamp',
                  Value=f.g.input(side + channel), Min=0.0, Max=1.0))
    preview, no = f.branch(enabled)
    for side, y in [('Left', -22), ('Right', 22)]:
        preview.call(SC + 'K2_SetRelativeLocationAndRotation', **{'self': preview.var(side + 'Grip'),
                     'NewLocation': unreal.Vector(42, y, 136), 'NewRotation': unreal.Rotator(),
                     'bSweep': False, 'bTeleport': True})
    _install_hooks(bp)
    unreal.EditorAssetLibrary.set_metadata_tag(bp, 'Quest.HandsUpgrade', '1')
    return {'native_inspection': inspection, 'material': MATERIAL_PATH,
            'grip_attachment_calibration': attachments,
            'controller_poses_tested': False, 'physics_grab_implemented': False,
            'gesture_scope': 'Existing Epic finger-pose AnimBlueprint driven by smoothed controller grip/trigger values',
            'limitations': ['Matte stylized template hand geometry; not a new human hand sculpt',
                            'Physical controller alignment, comfort and on-device skinning budget require Quest testing']}


def main():
    report = {'success': False, 'headset_tested': False, 'physics_grab_implemented': False}
    settings = unreal.get_default_object(unreal.load_class(None, '/Script/BlueprintGraph.BlueprintEditorSettings'))
    promotion = settings.get_editor_property('bEnableTypePromotion')
    try:
        if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'QuestHandsUpgrade'):
            raise RuntimeError('Explicit -QuestHandsUpgrade flag and an asset-writer queue slot are required')
        settings.set_editor_property('bEnableTypePromotion', False)
        report['staging_import'] = install_staged_pack()
        inspection = inspect_template()
        report['native_inspection'] = inspection
        bp = unreal.load_asset(core.CHAR_PATH)
        report['hands'] = upgrade_blueprint(bp, inspection)
        report['compiled'] = og.compile_bp(bp, save=True)
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    finally:
        settings.set_editor_property('bEnableTypePromotion', promotion)
    REPORT.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    if not report['success']:
        raise RuntimeError('Hand upgrade failed; inspect quest_hands_build_report.json')


if __name__ == '__main__':
    main()
