"""Measure original GDI or explicit WGC-arrival UTC against audio packet QPC.

No application input or capture is performed. Default writes clock arithmetic
and missing gates only. --mux creates a lossless normal-clock review preview;
it never fills missing audio, changes speed or claims player-controlled input.
Native recorder1.1 paired clock metadata and the new debug_ts video are needed.
"""
from pathlib import Path
from datetime import datetime, timezone
from fractions import Fraction
from local_utc_qpc_calibration import build_local_utc_qpc_calibration
import argparse
import array
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import traceback
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from record_gameplay_window import input_clock
from assemble_release_trailer import io_path, sha, read_json, inside, NO_WINDOW
FILETIME_UNIX_100NS = 116444736000000000
RATE = 48000


def require(test, message):
    if not test: raise RuntimeError(message)


def checked_ref(row):
    require(isinstance(row,dict) and row.get('path') and row.get('sha256'),'Actual file reference and SHA required')
    path=Path(row['path']).resolve()
    require(inside(path) and io_path(path).is_file() and sha(path)==row['sha256'],'Actual evidence bytes changed: '+str(path))
    return path


def clock_pair(row, frequency):
    before,after=int(row['qpc_before']),int(row['qpc_after'])
    require(0 < before <= after,'Invalid measured QPC bracket')
    midpoint = Fraction(before+after,2)
    precise = int(row['precise_filetime_100ns_utc'])
    return {'qpc_midpoint_100ns':midpoint*10000000/frequency,
            'utc_filetime_100ns':precise,
            'half_bracket_ms':float(Fraction(after-before,2)*1000/frequency),
            'system_minus_precise_ms':(int(row['system_filetime_100ns_utc'])-precise)/10000}


def measure(video_report_path,audio_report_path,first,count,folder,allow_natural_vfr_preview=False):
    video_report_path,audio_report_path=Path(video_report_path).resolve(),Path(audio_report_path).resolve()
    require(inside(video_report_path) and inside(audio_report_path),'Capture evidence must remain inside Release')
    video,audio=read_json(video_report_path),read_json(audio_report_path)
    require(video.get('success') and video.get('recorded') and not video.get('window_state_violations'),'Actual successful game-window recording required')
    video_path=Path(video['raw_video']).resolve(); require(sha(video_path)==video.get('raw_sha256'),'Original video bytes changed')
    require(audio.get('success') and audio.get('recorded') and audio.get('actual_capture_format_validated'),'Successful actual process-only audio capture required')
    require(audio.get('mode')=='INCLUDE_TARGET_PROCESS_TREE_ONLY' and audio.get('microphone') is False and audio.get('desktop_mix') is False,'Process-only capture, no microphone/system mix required')
    audio_path=Path(audio['wav_path']).resolve(); require(sha(audio_path)==audio.get('wav_sha256'),'Original audio bytes changed')
    native=read_json(checked_ref(audio['native_report']))
    require(native.get('success') and native.get('microphone') is False and native.get('desktop_mix') is False,'Actual native process-only audio result required')
    # Match the exact observed game process. Recordings may start at different
    # times; launch timestamps are never used to calculate an audio offset.
    video_pid=int(video['evidence']['process_id']); audio_pid=int(audio['evidence']['process_id'])
    require(video_pid==audio_pid==int(native['pid']),'Video/audio belong to different native game processes')
    require(video['evidence']['title']==audio['evidence']['title']==native['actual_window_title'],'Actual bound game titles disagree')
    debug=checked_ref(video['raw_debug_log'])
    probe_path=video_report_path.parent/'ffprobe.json'; probe=read_json(probe_path)
    points=[float(frame['best_effort_timestamp_time']) for frame in probe.get('frames',[]) if 'best_effort_timestamp_time' in frame]
    video_clock_error=0.0
    video_pair_evidence=None
    capture_method=video.get('capture_method','gdigrab_packet_arrival_utc_v1')
    if capture_method=='windows_graphics_capture_hwnd_lavfi_packet_arrival_utc_v1':
        from record_gameplay_wgc import input_clock as wgc_input_clock
        require(video.get('monitor_capture') is False and video.get('capture_cursor') is False and video.get('capture_border') is False,
                'WGC evidence must be explicit HWND-only client capture without cursor/border')
        graph='gfxcapture=hwnd=%d:'%int(video['evidence']['hwnd'])
        require(any(isinstance(part,str) and part.startswith(graph) and 'hwdownload,format=bgra,showinfo' in part
                    and 'monitor_idx' not in part and 'hmonitor' not in part for part in video.get('command',[])),
                'Actual WGC command must retain source showinfo and the exact independently observed HWND')
        clock=wgc_input_clock(io_path(debug).read_text(encoding='utf-8',errors='replace'),points,video['started_utc'],video['ended_utc'])
        require(clock.get('original_input_time_base')==[1,10000000] and clock.get('wgc_source_time_base_verified') is True and
                clock.get('absolute_compositor_qpc_origin_available') is False,
                'WGC native10MHz source intervals and packet-arrival clock semantics must be explicit')
        video_frequency=int(video.get('qpc_frequency',0))
        require(video_frequency>0 and len(video.get('clock_pairs',[]))>=2,'Actual WGC wrapper QPC/precise UTC brackets required')
        video_pairs=[clock_pair(row,video_frequency) for row in video['clock_pairs']]
        video_drift=float((video_pairs[-1]['utc_filetime_100ns']-video_pairs[0]['utc_filetime_100ns'])-
                          (video_pairs[-1]['qpc_midpoint_100ns']-video_pairs[0]['qpc_midpoint_100ns']))/10000
        require(max(pair['half_bracket_ms'] for pair in video_pairs)<=1,
                'WGC measured QPC/UTC bracket invalid; no timing guess')
        # Smooth UTC slew is resolved only by the actual contemporaneous local
        # UTC/QPC calibration after independent audio-pair agreement below.
        video_clock_error=0.0
        video_pair_evidence={'qpc_frequency':video_frequency,'count':len(video_pairs),'qpc_utc_drift_ms':video_drift,
                             'max_system_minus_precise_utc_ms':max(abs(pair['system_minus_precise_ms']) for pair in video_pairs),
                             'measured_bracket_drift_system_clock_bound_ms':video_clock_error,
                             'absolute_compositor_qpc_origin_available':False}
    else:
        require(capture_method=='gdigrab_packet_arrival_utc_v1','Unrecognized video capture clock method')
        clock=input_clock(io_path(debug).read_text(encoding='utf-8',errors='replace'),points,video['started_utc'],video['ended_utc'])
    require(clock['success'] and video.get('clock_metadata_validated') is True,'Original pre-offset UTC video packet clocks did not validate')
    require(clock['encoded_frame_original_utc_us']==video['native_input_clock']['encoded_frame_original_utc_us'],'Reported original frame clocks changed')
    frames=clock['encoded_frame_original_utc_us']
    require(isinstance(first,int) and first>=0 and isinstance(count,int) and count>0 and first+count<=len(frames),'Explicit source frame window is outside the original capture')
    packet_path=checked_ref(audio['packet_clock_log'])
    with io_path(packet_path).open(newline='',encoding='utf-8') as file:
        packets=[{key:int(value) for key,value in row.items()} for row in csv.DictReader(file)]
    require(len(packets)>1,'Actual per-packet audio clocks required')
    frequency=int(native['qpc_frequency']); require(frequency>0,'Measured QPC frequency required')
    require(len(native.get('clock_pairs',[]))>=2,'Native recorder1.1 precise UTC/QPC brackets required; do not estimate old launch times')
    pairs=[clock_pair(row,frequency) for row in native['clock_pairs']]
    anchor=pairs[0]
    clock_drift_ms=float((pairs[-1]['utc_filetime_100ns']-anchor['utc_filetime_100ns'])-
                         (pairs[-1]['qpc_midpoint_100ns']-anchor['qpc_midpoint_100ns']))/10000
    require(max(pair['half_bracket_ms'] for pair in pairs)<=1,'Measured clock-pair uncertainty exceeds1ms')
    local_utc_to_qpc = None
    local_calibration = None
    if video_pair_evidence is not None:
        local_utc_to_qpc,local_calibration=build_local_utc_qpc_calibration(video_pairs,pairs)
        video_clock_error=local_calibration['conservative_observed_calibration_error_bound_ms']
        video_pair_evidence['local_calibration']=local_calibration
        video_pair_evidence['measured_bracket_drift_system_clock_bound_ms']=video_clock_error
    else:
        require(abs(clock_drift_ms)<=2,'UTC/QPC changed by more than2ms during the actual take; no automatic clock warp is allowed')
    def packet_utc(row):
        return Fraction(anchor['utc_filetime_100ns'])+row['qpc_position_100ns']-anchor['qpc_midpoint_100ns']
    total=0
    for index,row in enumerate(packets):
        require(row['packet']==index and row['frames']>0 and row['qpc_position_100ns']>0,'Audio packet sequence/timestamp is invalid')
        require(row.get('cumulative_wav_frame')==total,'Native cumulative WAV frame does not match packet sequence')
        row['_wav_start']=total; row['_wav_end']=total+row['frames']; row['_utc_100ns']=packet_utc(row)
        total+=row['frames']
    with wave.open(str(io_path(audio_path)),'rb') as wav:
        require(wav.getnchannels()==2 and wav.getframerate()==RATE and wav.getsampwidth()==2 and wav.getcomptype()=='NONE','Actual48k stereo PCM16 WAV required')
        require(wav.getnframes()==total==int(native['frames']),'Actual WAV sample count and native packet log disagree')
    first_audio_utc=packets[0]['_utc_100ns']
    # Every frame maps from its original integer UTC capture timestamp, not
    # normalized NUT PTS, nominal frame number or process-start time.
    if local_utc_to_qpc is not None:
        mapping=[round((local_utc_to_qpc(int(timestamp)*10+FILETIME_UNIX_100NS)-packets[0]['qpc_position_100ns'])*RATE/10000000) for timestamp in frames]
    else:
        mapping=[round((Fraction(int(timestamp)*10+FILETIME_UNIX_100NS)-first_audio_utc)*RATE/10000000) for timestamp in frames]
    original=frames[first:first+count]
    wall_duration=(original[-1]-original[0])/1000000+1/30
    if allow_natural_vfr_preview:
        require(video_pair_evidence is not None,'Natural VFR review-only mode is limited to the verified WGC arrival-clock path')
    audio_first=mapping[first]
    audio_count=round((wall_duration if allow_natural_vfr_preview else count/30)*RATE)
    audio_last=audio_first+audio_count
    require(0<=audio_first<audio_last<=total,'The original process audio does not cover the selected video interval; record audio before video and long enough after it')
    selected=[row for row in packets if row['_wav_start']<audio_last and row['_wav_end']>audio_first]
    require(selected,'No original audio packets cover the selected interval')
    discontinuities=[row for row in selected if row['flags']&1 and row['packet']!=0]
    timestamp_errors=[row for row in selected if row['flags']&4]
    require(not discontinuities and not timestamp_errors,'Selected audio interval contains native discontinuity/timestamp-error flags; no silence repair is allowed')
    residuals=[]; previous=None
    # Actual Windows process-loopback1.1 smoke returned devicePosition=0 for
    # every packet while QPC advanced by exactly100000ticks per480frames.
    # This optional virtual-device counter cannot detect gaps in that case.
    # Keep its raw values and use mandatory packet QPC, cumulative WAV frames,
    # flags and independent WAV readback instead. A changing device counter
    # still must advance by the exact preceding packet size.
    device_position_unavailable = all(row['device_frame_position']==0 for row in packets)
    packet_step_errors=[]
    for row in selected:
        expected=first_audio_utc+Fraction(row['_wav_start']*10000000,RATE)
        residuals.append(float(row['_utc_100ns']-expected)/10000)
        if previous:
            if not device_position_unavailable:
                require(row['device_frame_position']==previous['device_frame_position']+previous['frames'],'Selected device-frame clock has an unrepresented gap')
            require(row['qpc_position_100ns']>previous['qpc_position_100ns'],'Selected packet QPC is not increasing')
            step_error=float(Fraction(row['qpc_position_100ns']-previous['qpc_position_100ns'])-Fraction(previous['frames']*10000000,RATE))/10000
            packet_step_errors.append(step_error)
            require(abs(step_error)<=1,'Selected QPC packet-step timing has an unrepresented gap')
        previous=row
    # A fixed initial packet offset is harmless; changing residuals would mean
    # omitted/duplicated audio samples or actual drift. Both remain blocked.
    residual_span=max(residuals)-min(residuals)
    require(max(abs(r) for r in residuals)<=2 and residual_span<=2,'Native packet clock and written48k PCM drift/gap exceeds2ms; no resampling is allowed')
    offsets=[(time-original[0])/1000000-index/30 for index,time in enumerate(original)]
    cadence_valid=(all(abs(error)<=1/60 for error in offsets) and all(0<b-a<=50000 for a,b in zip(original,original[1:])) and
                   abs(wall_duration-count/30)<=1/30)
    if not allow_natural_vfr_preview:
        require(cadence_valid,'Selected original clock cannot map each frame once to30Hz without an unexpected gap/drop/duplicate or duration change')
    else:
        require(all(b>a for a,b in zip(original,original[1:])), 'Natural VFR review timestamps must remain strictly increasing')
    clock_error=max(pair['half_bracket_ms'] for pair in pairs)+(0 if local_calibration is not None else abs(clock_drift_ms))+max(abs(r) for r in residuals)+1000/(2*RATE)+video_clock_error
    encoded_quantization=max(abs((points[first+index]-points[first])-(timestamp-original[0])/1000000)
                             for index,timestamp in enumerate(original))*1000
    max_error=clock_error+encoded_quantization
    require(max_error<=20,'Measured clock arithmetic uncertainty exceeds20ms')
    result={'success':True,'method':'measured_native_qpc_packet_alignment','schema':1,
        'scope':('Measured explicit WGC/lavfi packet-arrival UTC inverted through actual contemporaneous local precise UTC/QPC brackets onto native process-only audio QPC. Original relative WGC intervals retained; private absolute compositor origin is unavailable. No launch-time or compositor-origin guess.' if video_pair_evidence else
                 'Measured original GDI UTC packetPTS vs native process-only audio first-sample QPC with actual precise UTC/QPC brackets. No launch-time guess, input automation or gameplay-state claim.'),
        'video_capture_method':capture_method,'video_clock_pair_evidence':video_pair_evidence,
        'preview_only_natural_vfr':allow_natural_vfr_preview,'source_30Hz_trailer_cadence_gate_passed':cadence_valid,
        'video_path':str(video_path),'video_sha256':sha(video_path),'audio_path':str(audio_path),'audio_sha256':sha(audio_path),
        'video_capture_report':{'path':str(video_report_path),'sha256':sha(video_report_path)},
        'audio_capture_report':{'path':str(audio_report_path),'sha256':sha(audio_report_path)},
        'debug_log':{'path':str(debug),'sha256':sha(debug)},'packet_clock_log':{'path':str(packet_path),'sha256':sha(packet_path)},
        'ffprobe_evidence':{'path':str(probe_path),'sha256':sha(probe_path)},
        'process_id':video_pid,'window_title':video['evidence']['title'],
        'source_in_frame':first,'frame_count':count,'source_frame_count':len(frames),
        'source_actual_wall_duration_seconds':wall_duration,'nominal_duration_seconds':count/30,
        'selected_audio_duration_seconds':audio_count/RATE,
        'audio_zero_at_video_zero_sample':mapping[0],'per_video_frame_audio_sample':mapping,
        'selected_audio_start_sample':audio_first,'selected_audio_end_sample':audio_last,
        'sample_rate':RATE,'channels':2,'clock_drift_ms_over_take':clock_drift_ms,'local_clock_calibration':local_calibration,
        'max_alignment_error_ms':max_error,'max_clock_pair_half_bracket_ms':max(pair['half_bracket_ms'] for pair in pairs),
        'clock_arithmetic_error_bound_ms':clock_error,'encoded_video_pts_quantization_max_ms':encoded_quantization,
        'packet_written_sample_clock_max_residual_ms':max(abs(r) for r in residuals),
        'packet_step_max_timing_error_ms':max((abs(error) for error in packet_step_errors),default=0),
        'device_position_mode':'Native process virtual device returned constant zero; QPC/sample/flag continuity used' if device_position_unavailable else 'Exact native device-position increments also verified',
        'device_position_readback_unique_values':sorted({row['device_frame_position'] for row in packets})[:16],
        'selected_audio_no_unrepresented_gaps':True,'selected_interval_discontinuities':0,'selected_interval_timestamp_errors':0,
        'startup_discontinuity_packet0_only':bool(packets[0]['flags']&1),
        'source_video_normal_wall_clock_validated':True,'source_video_each_original_frame_used_once':True,
        'audio_resampled_or_speed_changed':False,'audio_gap_filled':False,'audio_synthesized':False,
        'reviewed_audio_video_sync':False,'reviewed_by':None,'S07_player_input_proven':False,
        'ready_for_trailer':False,'preview_path':None,
        'clock_bound_scope':('Measured audio/video brackets, bounded local UTC/QPC calibration and independent endpoint agreement, observed system/precise UTC difference, packet residual, audio-sample and encoded-video PTS quantization. It excludes unknown WGC compositor queue/GPU/readback and audio render latency; actual sync review is still required.' if video_pair_evidence else
                             'Measured clock-pair bracket, UTC/QPC change, packet residual, half-audio-sample quantization and actual original-to-encoded video PTS quantization. It excludes unknown GDI pixel/read and audio render latency; an actual sync review is still required.'),
        'source_verification':{
            'video_source':('https://github.com/FFmpeg/FFmpeg/blob/946fcce07b/libavfilter/vsrc_gfxcapture_winrt.cpp#L1417-L1457' if video_pair_evidence else
                            'https://github.com/FFmpeg/FFmpeg/blob/946fcce07b/libavdevice/gdigrab.c#L577'),
            'packet_arrival_utc_override':'https://github.com/FFmpeg/FFmpeg/blob/946fcce07b/libavformat/demux.c#L522',
            'audio_qpc_units':'https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudiocaptureclient-getbuffer'},
        'created_utc':datetime.now(timezone.utc).isoformat(),'aligner_sha256':sha(__file__),
        'local_calibration_implementation':({'path':str(Path(__file__).with_name('local_utc_qpc_calibration.py')),'sha256':sha(Path(__file__).with_name('local_utc_qpc_calibration.py'))} if local_calibration is not None else None)}
    return result


def preview(result,folder):
    manifest_path=ROOT/'output/capture_tools/manifest.json'; manifest=read_json(manifest_path)
    exes={}
    for name in ['ffmpeg','ffprobe']:
        row=manifest['executables'][name]; path=Path(row['path']).resolve()
        require(inside(path,ROOT/'output/capture_tools') and sha(path)==row['sha256'],'Private verified FFmpeg tools required')
        exes[name]=path
    first,count=result['source_in_frame'],result['frame_count']
    graph=('[0:v:0]trim=start_frame=%d:end_frame=%d,setpts=PTS-STARTPTS[v];'
           '[1:a:0]atrim=start_sample=%d:end_sample=%d,asetpts=PTS-STARTPTS[a]'%
           (first,first+count,result['selected_audio_start_sample'],result['selected_audio_end_sample']))
    target=folder/'ALIGNED_NORMAL_CLOCK_REVIEW_PREVIEW.nut'
    encoder_clock=['-enc_time_base:v','1:10000000'] if result.get('video_clock_pair_evidence') else []
    command=[str(exes['ffmpeg']),'-hide_banner','-nostdin','-n','-i',result['video_path'],'-i',result['audio_path'],
        '-filter_complex',graph,'-map','[v]','-map','[a]','-c:v','ffv1','-level','3','-g','1',
        *encoder_clock,'-fps_mode:v','passthrough','-c:a','pcm_s16le','-ar','48000','-ac','2',str(target)]
    run=subprocess.run(command,capture_output=True,text=True,timeout=300,creationflags=NO_WINDOW)
    (folder/'mux_stderr.log').write_text(run.stderr,encoding='utf-8')
    require(run.returncode==0 and target.is_file(),'Actual lossless preview mux failed; preserve raw captures and logs')
    probe_command=[str(exes['ffprobe']),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(target)]
    run=subprocess.run(probe_command,capture_output=True,text=True,timeout=60,creationflags=NO_WINDOW)
    (folder/'preview_ffprobe.json').write_text(run.stdout,encoding='utf-8')
    require(run.returncode==0,'Actual aligned preview readback failed')
    data=json.loads(run.stdout); video=[row for row in data['streams'] if row['codec_type']=='video']; audio=[row for row in data['streams'] if row['codec_type']=='audio']
    require(len(video)==len(audio)==1 and int(video[0].get('nb_read_frames',0))==count and
            int(audio[0].get('sample_rate',0))==48000 and audio[0].get('channels')==2,'Actual aligned preview frame/audio format check failed')
    result.update(preview_path=str(target),preview_sha256=sha(target),preview_native_encoded=True,
                  mux_command=command,preview_readback=data,
                  preview_scope='Original contiguous frame trim and aligned original sample trim. No camera/input/gameplay modifications, speed changes, artificial frames or replacement audio. This is review media, not the final trailer.')


def review(result,path):
    require(not result.get('preview_only_natural_vfr'),'Natural VFR preview-only evidence cannot become trailer-ready through a review flag')
    path=Path(path).resolve(); require(inside(path),'Actual review evidence must remain inside Release')
    proof=read_json(path)
    require(proof.get('success') is True and proof.get('video_sha256')==result['video_sha256'] and
            proof.get('audio_sha256')==result['audio_sha256'] and proof.get('source_in_frame')==result['source_in_frame'] and
            proof.get('frame_count')==result['frame_count'] and proof.get('reviewed_audio_video_sync') is True and
            proof.get('reviewed_by') and proof.get('reviewed_at_utc') and proof.get('observation_reference'),
            'Actual source-bound sync observation/review required; clock arithmetic alone cannot review perceptual latency')
    result.update(reviewed_audio_video_sync=True,reviewed_by=proof['reviewed_by'],reviewed_at_utc=proof['reviewed_at_utc'],
                  sync_review={'path':str(path),'sha256':sha(path)},ready_for_trailer=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video-report',type=Path,required=True)
    parser.add_argument('--audio-report',type=Path,required=True)
    parser.add_argument('--source-in-frame',type=int,default=0)
    parser.add_argument('--frame-count',type=int,required=True)
    parser.add_argument('--output-directory',type=Path)
    parser.add_argument('--mux',action='store_true',help='Actually create a lossless original-clock preview after measuring valid clocks')
    parser.add_argument('--preview-natural-vfr',action='store_true',help='WGC review media only: preserve original VFR timestamps/audio wall duration without claiming30Hz trailer readiness')
    parser.add_argument('--review',type=Path,help='Existing actual source-bound audio/video sync review JSON')
    args=parser.parse_args()
    require(not args.preview_natural_vfr or (args.mux and args.review is None),'Natural VFR mode requires a real preview mux and cannot accept a trailer sync review')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    folder=(args.output_directory or ROOT/'output/clock_alignment'/stamp).resolve()
    require(inside(folder,ROOT/'output/clock_alignment') and not folder.exists(),'New output/clock_alignment directory required')
    folder.mkdir(parents=True); report=folder/'alignment_report.json'
    result={'success':False,'ready_for_trailer':False,'ffmpeg_invoked':False,'S07_player_input_proven':False,
            'video_capture_report':str(args.video_report),'audio_capture_report':str(args.audio_report)}
    try:
        result=measure(args.video_report,args.audio_report,args.source_in_frame,args.frame_count,folder,args.preview_natural_vfr)
        result['ffmpeg_invoked']=bool(args.mux)
        if args.mux: preview(result,folder)
        if args.review: review(result,args.review)
    except Exception:
        result.update(success=False,ready_for_trailer=False,error=traceback.format_exc())
    report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(report),'measured_clock_alignment_passed':result['success'],
                      'preview_path':result.get('preview_path'),'sync_reviewed':result.get('reviewed_audio_video_sync',False),
                      'S07_player_input_proven':False},indent=2))
    return 0 if result['success'] else 2


if __name__=='__main__':
    raise SystemExit(main())
