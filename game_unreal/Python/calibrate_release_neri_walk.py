"""QUEUED read-only Neri stance-rate estimate at its actual authored scale.

Uses its own native walk/skeleton. No copying Mother's .96 scale/rate or clips;
no path, 100cm/s movement, story, actor transform, asset or map writes.
"""
from pathlib import Path
from datetime import datetime,timezone
import json
import math
import statistics
import sys
import traceback
import unreal

PROJECT=Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(PROJECT/'Python'))
import release_file_io as io
import calibrate_release_mother_walk as shared_calibration
from release_mother_integration import require,unit_reference,GraphAudit,MANAGER
import opening_graph as og

REPORT=PROJECT/'release_neri_walk_calibration.json'


def main():
    require(PROJECT.parent.name=='Release_20261026','Exact Release project required')
    require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'ReleaseNeriCalibrate'),
            'Root serialized read-only native queue required')
    imported_path=PROJECT/'release_neri_import_report.json'
    retarget_path=PROJECT/'release_neri_retarget_report.json'
    imported,retarget=(json.loads(p.read_text()) for p in [imported_path,retarget_path])
    require(imported['success'] and imported['native_executed'] and imported['character']=='Neri'
            and retarget['success'] and retarget['native_executed']
            and retarget['source_import_report_sha256']==io.sha(imported_path),'Matching actual Neri import/bake proof required')
    before={str(p):io.sha(p) for p in io.files(PROJECT/'Content','*.uasset')+io.files(PROJECT/'Content','*.umap')}
    level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    require(not level.is_in_play_in_editor() and level.load_level('/Game/Quest/Maps/Verdant_Desktop'),'Read actual saved Desktop actor outsidePIE')
    managers=[a for a in actors.get_all_level_actors() if a.actor_has_tag('Opening.Manager')]
    require(len(managers)==1,'Exactly one existing manager required')
    actor=managers[0].get_editor_property('NeriActor')
    require(actor and actor.actor_has_tag('past.neri'),'Stable Neri reference/tag required')
    scale=actor.get_actor_scale3d()
    require(.4<=scale.x<=1.5 and abs(scale.x-scale.y)<1e-5 and abs(scale.x-scale.z)<1e-5,'Review nonuniform/invalid authored Neri scale')
    run=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    folder=PROJECT/'validation/release_neri_walk_calibration'/run
    folder.mkdir(parents=True)
    audit=GraphAudit(folder/'node_exports')
    bp=unreal.load_asset(MANAGER)
    graph=og.L.find_graph(bp,'NpcTick')
    speed_nodes=[]
    for node in og.E.get_graph_editor(graph).list_all_nodes():
        title=str(og.L.get_node_title(node)).replace(' ','').lower()
        if 'setactorlocation' not in title or audit.function(node)[1]!='K2_SetActorLocation':continue
        if not audit.ancestors_have_variable(node,'NeriActor'):continue
        pins=list(og.P.list_connected_pins(og.pin_in(node,'NewLocation')))
        require(len(pins)==1,'Expected the original authored Neri move expression')
        interp=og.P.get_owning_node(pins[0])
        require(audit.function(interp)[1]=='VInterpTo_Constant','Unexpected Neri movement expression')
        speed=float(str(og.P.get_pin_value(og.pin_in(interp,'InterpSpeed'))))
        require(speed==100.0,'Neri route speed must remain100cm/s')
        speed_nodes.append({'node':node.get_path_name(),'guid':audit.guid(node),'interp_speed_cm_s':speed})
    require(len(speed_nodes)==3,'Expected the3existing Neri waypoint movement nodes')
    mesh,sequence=unreal.load_asset(retarget['target_mesh']),unreal.load_asset(retarget['baked']['walk'])
    require(mesh and sequence and sequence.get_editor_property('skeleton')==mesh.get_editor_property('skeleton'),'Own Neri target-skeleton walk required')
    reference=unit_reference(mesh)
    for file,digest in retarget['owned_asset_sha256'].items():require(io.sha(file)==digest,'Neri bake changed since proof')
    duration=float(sequence.get_play_length())
    intervals=max(120,int(math.ceil(duration*120)))
    # Reuse only the stance filter, with this actor's measured scale. No Mother
    # animation, mesh, skeleton, cached result or hard-coded .96 is reused.
    shared_calibration.ACTOR_SCALE=float(scale.x)
    evidence={}
    for name,kind in [('RAW',unreal.AnimDataEvalType.RAW),('COMPRESSED',unreal.AnimDataEvalType.COMPRESSED)]:
        options=unreal.AnimPoseEvaluationOptions()
        for key,value in {'evaluation_type':kind,'should_retarget':True,'extract_root_motion':False,
            'incorporate_root_motion_into_pose':False,'optional_skeletal_mesh':mesh}.items():options.set_editor_property(key,value)
        samples=[]
        for index in range(intervals+1):
            second=duration*index/intervals
            pose=unreal.AnimPoseExtensions.get_anim_pose_at_time(sequence,second,options)
            require(unreal.AnimPoseExtensions.is_valid(pose),'Native Neri pose sampling failed')
            row={'time':second}
            for bone in ['Root','pelvis','foot_l','foot_r','ball_l','ball_r']:
                v=unreal.AnimPoseExtensions.get_bone_pose(pose,bone,unreal.AnimPoseSpaces.WORLD).translation
                row[bone]=[float(v.x),float(v.y),float(v.z)]
            samples.append(row)
        span=max(math.hypot(s['pelvis'][0]-samples[0]['pelvis'][0],s['pelvis'][1]-samples[0]['pelvis'][1]) for s in samples)
        require(span<40,'Neri body travels inside a locked-Root skeleton')
        estimate=shared_calibration.stance_speeds(samples)
        require(.2<=estimate['recommended_play_rate']<=1.5,'Measured Neri rate outside review bounds')
        evidence[name]={'samples':samples,'pelvis_xy_span_cm':span,**estimate}
    raw,compressed=(evidence[k]['recommended_play_rate'] for k in ['RAW','COMPRESSED'])
    require(abs(raw-compressed)<.1*raw,'Neri RAW/COMPRESSED stance estimates disagree')
    require(all(io.sha(file)==digest for file,digest in before.items()),'Read-only Neri calibration changed native assets/maps')
    result={'success':True,'native_executed':True,'character':'Neri','run':run,'target_mesh':retarget['target_mesh'],
        'walk':sequence.get_path_name(),'own_listening_idle':imported['animation'],'native_unit_reference':reference,
        'retarget_report_sha256':io.sha(retarget_path),'import_report_sha256':io.sha(imported_path),
        'observed_authored_actor_uniform_scale':float(scale.x),'observed_actor_path':actor.get_path_name(),
        'expected_runtime_height_at_authored_scale_cm':imported['world_height_cm']*float(scale.x),
        'character_size_visually_approved':False,'scripted_travel_speed_cm_s':100.0,'native_waypoint_speed_nodes':speed_nodes,
        'native_forward_axis':'+Y','sample_rate_hz':intervals/duration,'evaluations':evidence,
        'recommended_play_rate':statistics.median([raw,compressed]),'source_sha256':io.sha(__file__),
        'shared_stance_filter_source_sha256':io.sha(shared_calibration.__file__),
        'native_assets_maps_unchanged':True,'actor_transform_or_scale_changed':False,'save_files_written':False,
        'runtime_play_rate_applied':False,'injured_ankle_wrap_gait_visually_reviewed':False,
        'foot_lock_or_runtime_video_verified':False}
    text=json.dumps(result,indent=2)+'\n'
    REPORT.write_text(text);(folder/'calibration.json').write_text(text)


if __name__=='__main__':
    try:main()
    except Exception:
        REPORT.write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2))
        unreal.log_error(traceback.format_exc())
    unreal.SystemLibrary.quit_editor()
