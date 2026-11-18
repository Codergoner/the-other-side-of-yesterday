"""Native additive short-step variation, preserving the original gait and rig.

Reduce only eight leg rotation tracks to42% of their reference-pose delta;
restore the lower stance ball to its own reference height through pelvis Z.
No source overwrite, skeleton/body/garment edit, foot-lock/cloth-simulation claim.
"""
from pathlib import Path
import json,math,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();SOURCE=Path(__file__).resolve()
sys.path.insert(0,str(ROOT/'Python'))
import release_file_io as io
import retarget_release_characters as rt


def blend(a,b,alpha):
    aa=[a.x,a.y,a.z,a.w];bb=[b.x,b.y,b.z,b.w]
    if sum(x*y for x,y in zip(aa,bb))<0:bb=[-x for x in bb]
    v=[x*(1-alpha)+y*alpha for x,y in zip(aa,bb)];norm=math.sqrt(sum(x*x for x in v))
    return unreal.Quat(*(x/norm for x in v))


def main():
    rt.require(ROOT.parent.name=='Release_20261026','Release copy required')
    previous=ROOT/'release_mother_rev7_compatible_bake.json';data=json.loads(previous.read_text())
    rt.require(data['success'],'Actual existing Mother7 compatible walk required')
    for p,digest in data['owned_asset_sha256'].items():rt.require(io.sha(p)==digest,'Original bake changed')
    mesh=unreal.load_asset(data['target_mesh']);old=unreal.load_asset(data['baked']['walk'])
    signature=io.sha(SOURCE)[:12];folder='/Game/Release/MotherShortWalk/V_'+signature
    disk=ROOT/'Content'/folder.removeprefix('/Game/');path=folder+'/A_MotherShortStep'
    rt.require(not unreal.EditorAssetLibrary.does_asset_exist(path),'Preserve existing short-step candidate')
    before={str(p):io.sha(p) for p in io.files(ROOT/'Content','*.uasset')+io.files(ROOT/'Content','*.umap')}
    seq=unreal.EditorAssetLibrary.duplicate_asset(old.get_path_name().split('.')[0],path)
    rt.require(seq and seq.get_editor_property('skeleton')==mesh.get_editor_property('skeleton'),'Native sequence duplicate failed')
    controller=seq.get_editor_property('controller')
    rt.require(controller is not None,'Native animation data controller is unavailable; do not guess a replacement API')
    options=unreal.AnimPoseEvaluationOptions()
    for key,value in {'evaluation_type':unreal.AnimDataEvalType.RAW,'optional_skeletal_mesh':mesh,'should_retarget':True,'extract_root_motion':False}.items():options.set_editor_property(key,value)
    reference=unreal.AnimPoseExtensions.get_reference_pose(mesh.get_editor_property('skeleton'))
    duration=float(old.get_play_length());frames=int(unreal.AnimationLibrary.get_num_frames(old))
    tracks=['thigh_l','thigh_r','calf_l','calf_r','foot_l','foot_r','ball_l','ball_r','pelvis']
    poses=[unreal.AnimPoseExtensions.get_anim_pose_at_time(old,duration*i/(frames-1),options) for i in range(frames)]
    curves={}
    for bone in tracks:
        rows=[unreal.AnimPoseExtensions.get_bone_pose(p,bone,unreal.AnimPoseSpaces.LOCAL) for p in poses]
        rest=unreal.AnimPoseExtensions.get_bone_pose(reference,bone,unreal.AnimPoseSpaces.LOCAL)
        curves[bone]=([p.translation for p in rows],[blend(rest.rotation,p.rotation,.42) if bone!='pelvis' else p.rotation for p in rows],[p.scale3d for p in rows])
    controller.open_bracket('Bounded short-step garment-compatible variation',False)
    try:
        for bone in tracks[:-1]:rt.require(controller.set_bone_track_keys(bone,*curves[bone],False),'Could not author '+bone)
    finally:controller.close_bracket(False)
    desired=min(unreal.AnimPoseExtensions.get_bone_pose(reference,b,unreal.AnimPoseSpaces.WORLD).translation.z for b in ['ball_l','ball_r'])
    adjustments=[];positions=[]
    for i,base in enumerate(curves['pelvis'][0]):
        pose=unreal.AnimPoseExtensions.get_anim_pose_at_time(seq,duration*i/(frames-1),options)
        lowest=min(unreal.AnimPoseExtensions.get_bone_pose(pose,b,unreal.AnimPoseSpaces.WORLD).translation.z for b in ['ball_l','ball_r'])
        delta=float(desired-lowest);adjustments.append(delta);positions.append(unreal.Vector(base.x,base.y,base.z+delta))
    rt.require(max(abs(x) for x in adjustments)<20,'Unexpected short-step vertical correction; inspect native units')
    rt.require(controller.set_bone_track_keys('pelvis',positions,curves['pelvis'][1],curves['pelvis'][2],False),'Native pelvis correction failed')
    seq.set_editor_property('enable_root_motion',False);seq.set_editor_property('force_root_lock',True)
    evidence=rt.sample(seq,mesh,'walk',True)
    rt.require(unreal.EditorAssetLibrary.save_loaded_asset(seq),'Short-step save failed')
    rt.require(all(io.sha(p)==digest for p,digest in before.items()),'Existing mesh/skeleton/clip/map changed')
    result=dict(data);result.update(success=True,native_executed=True,namespace=folder,
        baked={'walk':seq.get_path_name(),'idle':data['baked']['idle']},pose_evidence={'walk':evidence},
        source_bake_report=str(previous),source_bake_report_sha256=io.sha(previous),authoring_source_sha256=io.sha(SOURCE),
        reused_bake_not_retargeted=False,source_derivation='Existing target-compatible walk; eight leg delta rotations nlerp42%, own reference-stance pelvis Z correction',
        pelvis_z_adjustment_cm=adjustments,unchanged_original_native_inputs=True,
        owned_asset_sha256={str(p):io.sha(p) for p in io.files(disk,'*.uasset')},
        new_gait_visually_approved=False,garment_clearance_approved=False,foot_lock_or_ik_claimed=False)
    (ROOT/'release_mother_shortwalk_report.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    try:main()
    except Exception:
        (ROOT/'release_mother_shortwalk_failed.json').write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2));unreal.log_error(traceback.format_exc())
    unreal.SystemLibrary.quit_editor()
