"""QUEUED Neri-only compatible walk bake; its own Listening stays the idle.

Corrected unit-scale / PelvisMotion horizontal0 / FK method already exercised
on Mother. No Mother clips/skeleton aliases, NPC swap, path or save edits.
An ankle wrap does not establish an injury/limp animation: gait review is still
required on Neri's actual body, boots, wrap and wardrobe before integration.
"""
from pathlib import Path
import hashlib
import json
import sys
import traceback
import unreal

PROJECT=Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(PROJECT/'Python'))
import retarget_release_characters as rt
import release_file_io as io
from release_mother_integration import unit_reference

REPORT=PROJECT/'release_neri_retarget_report.json'


def main():
    rt.require(PROJECT.parent.name=='Release_20261026','Exact Release project required')
    rt.require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseNeriRetargetWrite'),
               'Root serialized native writer queue required')
    imported_path=PROJECT/'release_neri_import_report.json'
    imported=json.loads(imported_path.read_text())
    rt.require(imported['success'] and imported['native_executed'] and imported['character']=='Neri'
               and imported['native_unit_scale']['unit_root_scale_passed'] and imported['human_height_passed'],
               'Actual normalized Neri import proof required')
    for file,digest in imported['owned_asset_sha256'].items():rt.require(io.sha(file)==digest,'Neri import changed since native proof')
    target=rt.load(imported['mesh'],unreal.SkeletalMesh)
    reference=unit_reference(target)
    idle=rt.load(imported['animation'],unreal.AnimSequence)
    rt.require(idle.get_editor_property('skeleton')==target.get_editor_property('skeleton'),'Neri own Listening skeleton differs')
    source=rt.load(rt.SOURCE_MESH,unreal.SkeletalMesh)
    source_walk=rt.load(rt.SOURCE_ANIMS['walk'],unreal.AnimSequence)
    rt.require(source_walk.get_editor_property('skeleton')==source.get_editor_property('skeleton'),'Epic source skeleton mismatch')
    rt.require(source.get_editor_property('skeleton')!=target.get_editor_property('skeleton'),'A source alias is not a target-compatible bake')
    signature=hashlib.sha256((io.sha(imported_path)+io.sha(__file__)+io.sha(rt.__file__)).encode()).hexdigest()[:12]
    folder='/Game/Release/NeriRetarget/Unit_'+signature
    disk=PROJECT/'Content'/folder.removeprefix('/Game/')
    before=rt.protected(disk)
    # New owned Neri namespace only; the shared helper's metadata value is
    # changed in this process, never in its source or Mother's saved outputs.
    rt.OWNER='TOSOY.ReleaseNeriRetargetOwned'
    src_names,dst_names=rt.bone_names(source),rt.bone_names(target)
    src_rig,src_chains=rt.make_rig('IK_QuinnSource',folder,source,src_names,signature)
    dst_rig,dst_chains=rt.make_rig('IK_NeriTarget',folder,target,dst_names,signature)
    retargeter=rt.new_asset('RTG_QuinnToNeri',folder,unreal.IKRetargeter,unreal.IKRetargetFactory(),signature)
    controller=unreal.IKRetargeterController.get_controller(retargeter)
    src,dst=unreal.RetargetSourceOrTarget.SOURCE,unreal.RetargetSourceOrTarget.TARGET
    controller.set_ik_rig(src,src_rig);controller.set_ik_rig(dst,dst_rig)
    controller.set_preview_mesh(src,source);controller.set_preview_mesh(dst,target)
    pelvis_index=controller.add_retarget_op('/Script/IKRig.IKRetargetPelvisMotionOp')
    rt.require(pelvis_index>=0 and controller.add_retarget_op('/Script/IKRig.IKRetargetFKChainsOp')>=0,'Native op creation failed')
    controller.assign_ik_rig_to_all_ops(src,src_rig);controller.assign_ik_rig_to_all_ops(dst,dst_rig)
    pelvis=controller.get_op_controller(pelvis_index)
    rt.require(isinstance(pelvis,unreal.IKRetargetPelvisMotionController),'Actual native pelvis controller required')
    settings=pelvis.get_settings();settings.set_editor_property('scale_horizontal',0.0);pelvis.set_settings(settings)
    rt.require(pelvis.get_settings().get_editor_property('scale_horizontal')==0.0,'Pelvis motion policy failed readback')
    controller.auto_map_chains(unreal.AutoMapChainType.EXACT,True,unreal.Name('None'))
    for name,_,_ in dst_chains:
        rt.require(controller.set_source_chain(name,name,unreal.Name('None')),'Explicit target chain mapping failed')
    aligned=controller.create_retarget_pose('NeriAligned',dst)
    rt.require(controller.set_current_retarget_pose(aligned,dst),'Neri alignment pose did not activate')
    controller.auto_align_all_bones(dst,unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN)
    inputs=unreal.IKRetargetBatchOperationInputs()
    for key,value in {'assets_to_retarget':[rt.LIB.find_asset_data(source_walk.get_path_name())],
        'source_mesh':source,'target_mesh':target,'ik_retarget_asset':retargeter,'prefix':'Neri_',
        'target_path':folder+'/Baked','use_source_path':False,'include_referenced_assets':False,
        'overwrite_existing_files':False,'retain_additive_flags':True}.items():inputs.set_editor_property(key,value)
    output=unreal.IKRetargetBatchOperation.run_batch_retarget(inputs)
    rt.require(len(output)==1,'Expected exactly one Neri-compatible walk')
    sequence=rt.load(folder+'/Baked/Neri_'+source_walk.get_name(),unreal.AnimSequence)
    sequence.set_editor_property('enable_root_motion',False);sequence.set_editor_property('force_root_lock',True)
    rt.LIB.set_metadata_tag(sequence,'TOSOY.ReleaseRetarget.Owner',rt.OWNER)
    rt.LIB.set_metadata_tag(sequence,'TOSOY.ReleaseRetarget.Signature',signature)
    evidence=rt.sample(sequence,target,'walk',strict_unit=True)
    for asset in [sequence,src_rig,dst_rig,retargeter]:rt.require(rt.LIB.save_loaded_asset(asset),'Owned Neri bake save failed')
    rt.require(before==rt.protected(disk),'Protected native/config/maps changed')
    result={'success':True,'native_executed':True,'character':'Neri','target_mesh':target.get_path_name(),
        'target_skeleton':target.get_editor_property('skeleton').get_path_name(),'namespace':folder,
        'source_import_report_sha256':io.sha(imported_path),'source_sha256':io.sha(__file__),'shared_method_source_sha256':io.sha(rt.__file__),
        'baked':{'walk':sequence.get_path_name(),'idle':idle.get_path_name()},
        'idle_policy':'Own imported target-compatible Listening, including own facial curves; no Mother or Manny alias',
        'pose_evidence':{'walk':evidence},'native_unit_reference':reference,
        'source_chains':src_chains,'target_chains':dst_chains,
        'motion_policy':'Pelvis horizontal scale0; vertical bob/rotation and limb FK remain; horizontal sway intentionally removed',
        'owned_asset_sha256':{str(p):io.sha(p) for p in io.files(disk,'*.uasset')},
        'injured_ankle_wrap_gait_visually_reviewed':False,'limp_or_injury_animation_claimed':False,
        'physics_created':False,'stable_npc_or_story_maps_changed':False,'play_rate_calibrated':False,
        'foot_lock_or_runtime_video_verified':False,'protected_native_inputs_unchanged':True}
    REPORT.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    try:main()
    except Exception:
        REPORT.write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2))
        unreal.log_error(traceback.format_exc())
    unreal.SystemLibrary.quit_editor()
