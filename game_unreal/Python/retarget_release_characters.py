"""Queued Mother locomotion bake using installed UE5.8 editor APIs.

Source-only until the serialized native writer queue and -ReleaseRetargetWrite.
Creates owned IK rigs/retargeter/baked animations inside a NEW review namespace.
Never swaps production NPCs, assigns incompatible Manny animations, changes
manager graphs, saves maps, edits physics, touches campaign saves or installs.
"""
from pathlib import Path
import hashlib
import json
import math
import sys
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
ROOT = PROJECT.parent
sys.path.insert(0, str(PROJECT / 'Python'))
import release_file_io as file_io
UNIT_CANDIDATE = unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseMotherUnitCandidate')
OWNER = 'TOSOY.ReleaseMotherRetargetOwned'
SOURCE_MESH = '/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple'
SOURCE_ANIMS = {
    'idle': '/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle',
    'walk': '/Game/Characters/Mannequins/Anims/Unarmed/Walk/MF_Unarmed_Walk_Fwd'}
REPORT_PATH = PROJECT / ('release_mother_unit_retarget_report.json' if UNIT_CANDIDATE else 'release_mother_retarget_report.json')
LIB = unreal.EditorAssetLibrary
ASSETS = unreal.AssetToolsHelpers.get_asset_tools()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    return file_io.sha(path)


def protected(excluded):
    paths = file_io.files(PROJECT/'Content','*.uasset') + file_io.files(PROJECT/'Content','*.umap')
    paths += list((PROJECT / 'Config').glob('*.ini')) + list(PROJECT.glob('*.uproject'))
    return {str(p): sha(p) for p in paths if not p.resolve().is_relative_to(excluded.resolve())}


def load(path, cls):
    result = unreal.load_asset(path)
    require(isinstance(result, cls), 'Missing/wrong asset class: ' + path)
    return result


def bone_names(mesh):
    skeleton = mesh.get_editor_property('skeleton')
    pose = unreal.AnimPoseExtensions.get_reference_pose(skeleton)
    require(unreal.AnimPoseExtensions.is_valid(pose), 'Invalid reference pose: ' + mesh.get_path_name())
    return [str(n) for n in unreal.AnimPoseExtensions.get_bone_names(pose)]


def resolve(names, bone):
    found = [n for n in names if n.lower() == bone.lower()]
    require(len(found) == 1, 'Expected one actual bone named ' + bone)
    return found[0]


def chains(names):
    # Source Manny/Quinn has more spine/neck bones than MPFB. Interpolated FK
    # chains map the complete available spine and neck, rather than pretending
    # that a common bone name means the skeletons are animation-compatible.
    spine = sorted(n for n in names if n.lower().startswith('spine_') and n[-2:].isdigit())
    require(spine, 'Spine chain missing')
    pairs = [('Root', 'root', 'root'), ('Spine', spine[0], spine[-1]), ('Head', 'neck_01', 'head')]
    for side in ['l', 'r']:
        pairs += [('Clavicle_' + side, 'clavicle_' + side, 'clavicle_' + side),
                  ('Arm_' + side, 'upperarm_' + side, 'hand_' + side),
                  ('Leg_' + side, 'thigh_' + side, 'foot_' + side),
                  ('Toe_' + side, 'ball_' + side, 'ball_' + side)]
        for finger in ['thumb', 'index', 'middle', 'ring', 'pinky']:
            pairs.append((finger + '_' + side, finger + '_01_' + side, finger + '_03_' + side))
    return [(chain, resolve(names, start), resolve(names, end)) for chain, start, end in pairs]


def new_asset(name, folder, cls, factory, signature):
    path = folder + '/' + name
    # Deliberately refuse overwrite/reuse on a partial run. A new input or
    # algorithm revision produces a new signature folder; existing evidence
    # remains reviewable and no unowned asset can be silently modified.
    require(not LIB.does_asset_exist(path), 'Output already exists; inspect prior evidence before rerunning: ' + path)
    asset = ASSETS.create_asset(name, folder, cls, factory)
    require(asset, 'Asset creation failed: ' + path)
    LIB.set_metadata_tag(asset, 'TOSOY.ReleaseRetarget.Owner', OWNER)
    LIB.set_metadata_tag(asset, 'TOSOY.ReleaseRetarget.Signature', signature)
    return asset


def make_rig(name, folder, mesh, names, signature):
    rig = new_asset(name, folder, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory(), signature)
    controller = unreal.IKRigController.get_controller(rig)
    require(controller.set_skeletal_mesh(mesh), 'IK rig rejected mesh')
    require(controller.set_retarget_root(resolve(names, 'pelvis')), 'IK rig pelvis failed')
    require(controller.set_root_motion_bone(resolve(names, 'root')), 'IK rig root-motion bone failed')
    authored = chains(names)
    for chain, first, last in authored:
        actual = controller.add_retarget_chain(chain, first, last, unreal.Name('None'))
        require(str(actual) == chain, 'Chain creation changed its identity: ' + chain)
        require(str(controller.get_retarget_chain_start_bone(chain)).lower() == first.lower() and
                str(controller.get_retarget_chain_end_bone(chain)).lower() == last.lower(), 'Chain endpoints were not accepted: ' + chain)
    return rig, authored


def quat_angle(a, b):
    dot = abs(a.x*b.x + a.y*b.y + a.z*b.z + a.w*b.w)
    return math.degrees(2 * math.acos(max(-1.0, min(1.0, dot))))


def sample(sequence, mesh, role, strict_unit=False):
    # Native raw animation evaluation, not a mesh assigned to a mismatched
    # skeleton or a success inferred from nonempty files.
    require(sequence.get_editor_property('skeleton') == mesh.get_editor_property('skeleton'), 'Baked skeleton mismatch')
    duration = sequence.get_play_length()
    require(duration > .2 and unreal.AnimationLibrary.get_num_frames(sequence) > 2, 'Baked sequence has no usable frames')
    options = unreal.AnimPoseEvaluationOptions()
    for key, value in {'evaluation_type': unreal.AnimDataEvalType.RAW,
                       'should_retarget': True, 'extract_root_motion': False,
                       'incorporate_root_motion_into_pose': False,
                       'optional_skeletal_mesh': mesh}.items():
        options.set_editor_property(key, value)
    poses = []
    names = bone_names(mesh)
    tracked = [resolve(names, n) for n in ['root', 'pelvis', 'head', 'upperarm_l', 'hand_l', 'upperarm_r', 'hand_r', 'thigh_l', 'calf_l', 'foot_l', 'foot_r']]
    for fraction in [0, .125, .25, .375, .5, .625, .75, .875]:
        pose = unreal.AnimPoseExtensions.get_anim_pose_at_time(sequence, fraction * duration, options)
        require(unreal.AnimPoseExtensions.is_valid(pose), 'Baked pose failed evaluation')
        poses.append({n: unreal.AnimPoseExtensions.get_bone_pose(pose, n, unreal.AnimPoseSpaces.WORLD) for n in tracked})
    root = resolve(names, 'root')
    if strict_unit:
        for p in poses:
            require(all(abs(c-1) < .0001 for c in [p[root].scale3d.x,p[root].scale3d.y,p[root].scale3d.z]), 'Baked CoreRoot has nonunit component scale')
            require(100 <= p[resolve(names,'head')].translation.z <= 230, 'Baked head has nonhuman component/world height')
            require(all(abs(p[resolve(names,'foot_'+side)].translation.z) <= 80 for side in ['l','r']), 'Baked feet are not near the authored ground')
    root_xy_span = max(math.hypot(p[root].translation.x-poses[0][root].translation.x,
                                 p[root].translation.y-poses[0][root].translation.y) for p in poses)
    require(root_xy_span < 1, 'Baked clip would add horizontal root travel to the scripted NPC route')
    pelvis = resolve(names, 'pelvis')
    pelvis_xy_span = max(math.hypot(p[pelvis].translation.x-poses[0][pelvis].translation.x,
                                   p[pelvis].translation.y-poses[0][pelvis].translation.y) for p in poses)
    if strict_unit:
        require(pelvis_xy_span < 40, 'Body travels inside the skeleton while Root is locked; not an in-place scripted-NPC clip')
    thighs = resolve(names, 'thigh_l')
    movement = max(quat_angle(poses[0][thighs].rotation, p[thighs].rotation) for p in poses)
    if role == 'walk':
        require(movement > 5, 'Walk bake is static or did not transfer leg motion')
    if role == 'idle':
        for side in ['l', 'r']:
            upper, hand = resolve(names, 'upperarm_' + side), resolve(names, 'hand_' + side)
            require(poses[0][upper].translation.z - poses[0][hand].translation.z > 10,
                    'Idle is still a raised-arm reference pose or has wrong axes; inspect before integration')
    return {'seconds': duration, 'frames': unreal.AnimationLibrary.get_num_frames(sequence),
            'root_xy_span_cm': root_xy_span, 'pelvis_xy_span_cm': pelvis_xy_span, 'left_thigh_rotation_span_degrees': movement,
            'sampled_component_transforms': [{n: {'translation_cm': [t.translation.x,t.translation.y,t.translation.z],
                                                'rotation_xyzw': [t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w]}
                                               for n,t in pose.items()} for pose in poses],
            'foot_contact_or_visual_gait_approved': False}


def main():
    require(ROOT.name == 'Release_20261026', 'Refusing protected project copies')
    require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseRetargetWrite'),
            'Serialized root writer queue and -ReleaseRetargetWrite required')
    imported = json.loads((PROJECT / 'release_character_import_report.json').read_text(encoding='utf-8'))
    require(imported.get('success'), 'Actual successful native Mother import is required first')
    unit_probe_path = PROJECT / 'release_character_unit_probe_report.json'
    unit_reference_evidence = None
    if UNIT_CANDIDATE:
        unit = json.loads(unit_probe_path.read_text(encoding='utf-8'))
        require(unit.get('success') and unit.get('native_executed'), 'Actual native corrected-unit probe required')
        preferred = unit.get('preferred_candidate')
        require(isinstance(preferred,dict) and preferred.get('skeletal_actor_count') == 1, 'No exact preferred native unit candidate')
        require(preferred['native_unit_scale']['unit_root_scale_passed'] and preferred['human_height_passed']
                and 125 <= preferred['world_height_cm'] <= 210, 'Preferred native candidate still has invalid root/height')
        imported = dict(imported)
        imported.update({key:preferred[key] for key in ['mesh','namespace','animation','map','actor','native_morph_names']})
    source_manifest = Path(imported['source_manifest'])
    require(sha(source_manifest) == imported['source_manifest_sha256'], 'Imported source manifest changed')
    manifest = json.loads(source_manifest.read_text(encoding='utf-8'))
    require(manifest['rig'] == 'MPFB GameEngine' and manifest['rest_skeleton_unchanged'], 'Unexpected Mother rig')
    target = load(imported['mesh'], unreal.SkeletalMesh)
    require(target.get_path_name().startswith(imported['namespace'] + '/Meshes/'), 'Mother target escaped imported review namespace')
    if UNIT_CANDIDATE:
        from release_mother_integration import unit_reference
        unit_reference_evidence = unit_reference(target)
    source = load(SOURCE_MESH, unreal.SkeletalMesh)
    originals = {role: load(path, unreal.AnimSequence) for role,path in SOURCE_ANIMS.items()}
    source_names, target_names = bone_names(source), bone_names(target)
    expected = {n.lower() for n in manifest['rest_bone_matrices']}
    require(expected.issubset({n.lower() for n in target_names}), 'Imported skeleton lost expected MPFB bones')
    require(source.get_editor_property('skeleton') != target.get_editor_property('skeleton'), 'Retarget must construct a genuinely target-compatible sequence')
    require(all(a.get_editor_property('skeleton') == source.get_editor_property('skeleton') for a in originals.values()), 'Source clips are not compatible with the Quinn source mesh')
    source_digests = {}
    for package in [SOURCE_MESH] + list(SOURCE_ANIMS.values()):
        source_digests[package] = sha(PROJECT/'Content'/(package.removeprefix('/Game/')+'.uasset'))
    script_sha = sha(PROJECT/'Python/retarget_release_characters.py')
    unit_signature = sha(unit_probe_path) if UNIT_CANDIDATE else ''
    signature = hashlib.sha256((imported['source_manifest_sha256'] + unit_signature + imported['mesh'] + json.dumps(source_digests, sort_keys=True) + script_sha).encode()).hexdigest()[:12]
    folder = ('/Game/Release/MotherRetarget/Unit_' + signature) if UNIT_CANDIDATE else (imported['namespace'] + '/Retarget_' + signature)
    disk = PROJECT / 'Content' / folder.removeprefix('/Game/')
    before = protected(disk)
    source_rig, source_chains = make_rig('IK_QuinnSource', folder, source, source_names, signature)
    target_rig, target_chains = make_rig('IK_MotherTarget', folder, target, target_names, signature)
    retargeter = new_asset('RTG_QuinnToMother', folder, unreal.IKRetargeter, unreal.IKRetargetFactory(), signature)
    controller = unreal.IKRetargeterController.get_controller(retargeter)
    src, dst = unreal.RetargetSourceOrTarget.SOURCE, unreal.RetargetSourceOrTarget.TARGET
    controller.set_ik_rig(src, source_rig); controller.set_ik_rig(dst, target_rig)
    controller.set_preview_mesh(src, source); controller.set_preview_mesh(dst, target)
    # The two operations are explicit verified 5.8 USTRUCT paths. There are no
    # IK goals/solvers or foot-plant claims hidden behind default-op warnings.
    op_indices = {}
    for op in ['IKRetargetPelvisMotionOp', 'IKRetargetFKChainsOp']:
        op_indices[op] = controller.add_retarget_op('/Script/IKRig.' + op)
        require(op_indices[op] >= 0, 'Retarget operation failed: ' + op)
    controller.assign_ik_rig_to_all_ops(src, source_rig)
    controller.assign_ik_rig_to_all_ops(dst, target_rig)
    if UNIT_CANDIDATE:
        # ForceRootLock alone does not suppress travel copied into the pelvis.
        # Scripted NPC routes already move the actor; hold retarget pelvis XY
        # at the reference location while preserving vertical bob and rotation.
        pelvis_controller = controller.get_op_controller(op_indices['IKRetargetPelvisMotionOp'])
        require(isinstance(pelvis_controller, unreal.IKRetargetPelvisMotionController), 'Expected actual native pelvis settings controller')
        settings = pelvis_controller.get_settings()
        settings.set_editor_property('scale_horizontal', 0.0)
        pelvis_controller.set_settings(settings)
        require(pelvis_controller.get_settings().get_editor_property('scale_horizontal') == 0.0, 'Pelvis XY suppression did not persist')
    controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True, unreal.Name('None'))
    for name, _, _ in target_chains:
        require(controller.set_source_chain(name, name, unreal.Name('None')), 'Explicit chain map failed: ' + name)
        require(str(controller.get_source_chain(name, unreal.Name('None'))) == name, 'Chain map did not persist: ' + name)
    aligned = controller.create_retarget_pose('MotherAligned', dst)
    require(controller.set_current_retarget_pose(aligned, dst), 'Retarget alignment pose did not activate')
    controller.auto_align_all_bones(dst, unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN)
    inputs = unreal.IKRetargetBatchOperationInputs()
    for key, value in {'assets_to_retarget': [LIB.find_asset_data(a.get_path_name()) for a in originals.values()],
                       'source_mesh': source, 'target_mesh': target, 'ik_retarget_asset': retargeter,
                       'prefix': 'Mother_', 'target_path': folder + '/Baked', 'use_source_path': False,
                       'include_referenced_assets': False, 'overwrite_existing_files': False,
                       'retain_additive_flags': True}.items():
        inputs.set_editor_property(key, value)
    output = unreal.IKRetargetBatchOperation.run_batch_retarget(inputs)
    require(len(output) == 2, 'Batch did not produce exactly two target sequences')
    baked, evidence = {}, {}
    for role, original in originals.items():
        seq = load(folder + '/Baked/Mother_' + original.get_name(), unreal.AnimSequence)
        seq.set_editor_property('enable_root_motion', False)
        seq.set_editor_property('force_root_lock', True)
        LIB.set_metadata_tag(seq, 'TOSOY.ReleaseRetarget.Owner', OWNER)
        LIB.set_metadata_tag(seq, 'TOSOY.ReleaseRetarget.Signature', signature)
        evidence[role] = sample(seq, target, role, UNIT_CANDIDATE)
        baked[role] = seq.get_path_name()
        require(LIB.save_loaded_asset(seq), 'Baked animation save failed')
    for asset in [source_rig, target_rig, retargeter]:
        require(LIB.save_loaded_asset(asset), 'Retarget setup save failed')
    after = protected(disk)
    require(before == after, 'Protected assets/config/maps changed outside the new retarget namespace')
    result = {'success': True, 'scope': 'Actual target-skeleton FK/pelvis bake plus native pose samples; no NPC integration or visual gait approval',
              'native_executed': True, 'target_mesh': target.get_path_name(), 'source_mesh': source.get_path_name(),
              'namespace': folder, 'retargeter': retargeter.get_path_name(), 'source_manifest': str(source_manifest),
              'source_manifest_sha256': sha(source_manifest), 'source_bones': source_names, 'target_bones': target_names,
              'authoring_source_sha256': script_sha, 'source_clip_mesh_sha256': source_digests,
              'unit_candidate': UNIT_CANDIDATE, 'source_unit_probe_report_sha256': unit_signature or None,
              'scripted_npc_motion_policy': 'Pelvis horizontal scale0; vertical bob/rotation and limb FK retained; no IK foot-plant claim' if UNIT_CANDIDATE else 'Original diagnostic bake',
              'native_unit_reference': unit_reference_evidence,
              'source_chains': source_chains, 'target_chains': target_chains, 'baked': baked, 'pose_evidence': evidence,
              'npc_actor_references_changed': False, 'physics_or_collision_changed': False, 'maps_saved': False,
              'manager_animation_selection_changed': False, 'campaign_saves_written': False,
              'protected_native_files_unchanged': before == after, 'protected_sha256': before,
              'owned_asset_sha256': {str(p):sha(p) for p in file_io.files(disk,'*.uasset')},
              'next_gate': 'Native idle/walk captures and cloth/foot-contact review, then Mother-only animation pin adaptation and query capsule before stable actor swap.'}
    REPORT_PATH.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    try:
        main()
    except Exception:
        REPORT_PATH.write_text(json.dumps({'success': False, 'error': traceback.format_exc(),
                                          'scope': 'Queued native retarget attempt; do not integrate failed output'}, indent=2), encoding='utf-8')
        unreal.log_error(traceback.format_exc())
    unreal.SystemLibrary.quit_editor()
