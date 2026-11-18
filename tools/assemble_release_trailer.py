"""Opt-in real-footage trailer assembler; default is a no-FFmpeg preflight.

Use --execute only after all 13 shots have concrete, reviewed source takes.
The JSON evidence contract is documented in TRAILER_CAPTURE_HANDOFF.md.
Missing footage/input/clock/rights evidence blocks export. This tool never
captures a screen, controls a game, creates gameplay or infers human input.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from fractions import Fraction
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / 'docs/Release_20261026/TRAILER_SHOTS.json'
TOOL_MANIFEST = ROOT / 'output/capture_tools/manifest.json'
FPS, RATE, TOTAL = 30, 48000, 9000
TITLE_LINES = ['THE OTHER SIDE OF YESTERDAY',
               'If you could change yesterday, what would you risk losing today?',
               'Early Playable — Chapters I–II']
VIDEO_EXTENSIONS = {'.nut', '.mkv', '.mp4', '.mov', '.avi'}
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def io_path(value):
    path = str(Path(value).resolve())
    if os.name == 'nt' and not path.startswith('\\\\?\\'):
        path = '\\\\?\\UNC\\' + path[2:] if path.startswith('\\\\') else '\\\\?\\' + path
    return Path(path)


def sha(path):
    digest = hashlib.sha256()
    with io_path(path).open('rb') as file:
        for block in iter(lambda:file.read(4*1024*1024), b''): digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(io_path(path).read_text(encoding='utf-8-sig'))


def utc(): return datetime.now(timezone.utc).isoformat()


def inside(path, folder=ROOT):
    return Path(path).resolve().is_relative_to(Path(folder).resolve())


def reference_identity(value):
    """Both exact evidence location and bytes identify a packaged version."""
    if not isinstance(value,dict) or not value.get('path') or not value.get('sha256'): return None
    return (os.path.normcase(str(Path(value['path']).resolve())),str(value['sha256']).lower())


def process_image(row):
    evidence = row.get('evidence',{})
    image = evidence.get('process_image') or row.get('process_image')
    if not image:
        app = evidence.get('computer_use_window',{}).get('app','')
        image = app[len('process:'):] if app.startswith('process:') else None
    return os.path.normcase(str(Path(image).resolve())) if image else None


class Assembly:
    def __init__(self, plan_path, folder):
        self.plan_path, self.folder = Path(plan_path).resolve(), Path(folder).resolve()
        if not inside(self.plan_path) or not inside(self.folder, ROOT/'output/trailer_exports'):
            raise RuntimeError('Plan and new output directory must remain in this isolated Release copy')
        if self.folder.exists(): raise RuntimeError('Preserving existing export/evidence directory')
        self.folder.mkdir(parents=True)
        self.plan = read_json(self.plan_path)
        self.report = {'success':False, 'release_acceptance_complete':False,
            'scope':'Actual-file preflight and optional native-footage edit; no generated gameplay or input inference',
            'started_utc':utc(), 'plan_path':str(self.plan_path), 'plan_sha256':sha(self.plan_path),
            'assembler_sha256':sha(__file__), 'ffmpeg_invoked':False, 'encoded':False,
            'missing_gates':[], 'checks':[], 'source_takes':[], 'commands':[],
            'final_video_path':None, 'final_content_review_required':True,
            'S07_normal_clock_input_proven_by_encoder':False}
        self.takes, self.shots = {}, []
        self.target_build = {}
        self.ffmpeg = self.ffprobe = None
        self._probe_cache = {}

    def write(self):
        (self.folder/'export_report.json').write_text(json.dumps(self.report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')

    def gate(self, condition, code, details=None):
        if not condition:
            row = {'code':code}
            if details is not None: row['details'] = details
            self.report['missing_gates'].append(row)
        return bool(condition)

    def check(self, condition, name, details=None):
        self.report['checks'].append({'name':name, 'passed':bool(condition), 'details':details})
        if not condition: raise RuntimeError(name + ': ' + str(details))

    def ref(self, value, code):
        if not self.gate(isinstance(value, dict) and value.get('path') and value.get('sha256'), code+'.reference_required'):
            return {}
        path = Path(value['path']).resolve()
        if not self.gate(inside(path) and io_path(path).is_file(), code+'.actual_file_required', str(path)): return {}
        if not self.gate(sha(path).lower() == str(value['sha256']).lower(), code+'.sha256_mismatch', str(path)): return {}
        try: return read_json(path)
        except Exception as error:
            self.gate(False, code+'.invalid_json', str(error)); return {}

    def preflight(self):
        self.validate_target_build()
        expected_timeline = {'duration_seconds':300, 'frame_rate_numerator':30, 'frame_rate_denominator':1,
            'frame_count':9000, 'first_frame':0, 'end_frame_exclusive':9000,
            'resolution':[1920,1080], 'scan':'progressive', 'audio_sample_rate_hz':48000, 'audio_channels':2}
        timeline = self.plan.get('timeline', {})
        self.gate(all(timeline.get(key) == value for key,value in expected_timeline.items()), 'timeline.must_be_exact_300s_9000_frames_1080p30_stereo48k')
        self.gate(timeline.get('color_space') == 'SDR Rec.709', 'timeline.SDR_Rec709_required')
        route = self.plan.get('narrative_route', {})
        self.gate(route.get('canvas_outcome') == 'clinic' and route.get('original_memorial_inspection_required') is True and
                  route.get('harbor_outcome_in_primary_edit') is False, 'route.clinic_plus_original_inspection_required')
        shots = self.plan.get('shots', [])
        self.gate(len(shots) == 13 and [s.get('id') for s in shots] == ['S%02d'%i for i in range(1,14)], 'shots.exact_13_ordered_slots_required')
        cursor = 0
        for shot in shots:
            label = str(shot.get('id', 'unknown'))
            start, end, count = shot.get('start_frame'), shot.get('end_frame_exclusive'), shot.get('duration_frames')
            valid = all(isinstance(n,int) and not isinstance(n,bool) for n in [start,end,count])
            self.gate(valid and start == cursor and end == start+count and count > 0, label+'.contiguous_frame_schedule_required')
            if valid: cursor = end
            takes = shot.get('source_takes', [])
            self.gate(isinstance(takes,list) and bool(takes), label+'.concrete_source_takes_missing')
            approved = shot.get('approved_take')
            approved = [approved] if isinstance(approved,str) else approved
            self.gate(isinstance(approved,list) and bool(approved), label+'.approved_take_missing')
            local = {}
            for take in takes if isinstance(takes,list) else []:
                if not self.gate(isinstance(take,dict) and isinstance(take.get('id'),str) and
                                 re.fullmatch(r'[A-Za-z0-9_-]{1,64}',take['id']) is not None,
                                 label+'.structured_take_with_safe_id_required'): continue
                key = (label,take['id'])
                if not self.gate(key not in self.takes, label+'.duplicate_take_id'): continue
                local[take['id']] = take; self.takes[key] = take
                self.validate_take(label,take)
            segments = shot.get('edit_segments', [])
            self.gate(isinstance(segments,list) and bool(segments), label+'.explicit_trim_segments_missing')
            total = 0
            for segment in segments if isinstance(segments,list) else []:
                if not self.gate(isinstance(segment,dict), label+'.structured_segment_required'): continue
                take_id = segment.get('take_id'); first = segment.get('source_in_frame'); length = segment.get('frame_count')
                self.gate(take_id in local and isinstance(approved,list) and take_id in approved, label+'.segment_take_not_approved')
                good = isinstance(first,int) and not isinstance(first,bool) and first >= 0 and isinstance(length,int) and not isinstance(length,bool) and length > 0
                self.gate(good, label+'.explicit_nonnegative_integer_frame_trim_required')
                self.gate(set(segment).issubset({'take_id','source_in_frame','frame_count'}), label+'.unsupported_segment_transform', list(segment))
                if good: total += length
            self.gate(total == count, label+'.trim_frame_total_must_match_slot', {'actual':total,'expected':count})
            if label == 'S07': self.validate_s07(shot,local,segments)
            self.validate_overlays(shot,local,segments)
            self.shots.append(shot)
        self.gate(cursor == TOTAL, 'timeline.no_extra_leader_or_tail')
        self.validate_route()
        manifest = read_json(TOOL_MANIFEST)
        self.gate(manifest.get('success') is True, 'tools.verified_private_manifest_required')
        for key in ['ffmpeg','ffprobe']:
            row = manifest.get('executables',{}).get(key,{})
            path = Path(row.get('path','')).resolve()
            okay = inside(path,ROOT/'output/capture_tools') and io_path(path).is_file()
            self.gate(okay and sha(path) == row.get('sha256'), 'tools.'+key+'.actual_verified_binary_required')
            if okay: setattr(self,key,path)
        self.report['private_tool_manifest_sha256'] = sha(TOOL_MANIFEST)
        self.report['preflight_passed'] = not self.report['missing_gates']
        self.report['source_only_ready'] = True
        self.write()
        return self.report['preflight_passed']

    def validate_target_build(self):
        """Exe-only identity misses cooked Blueprint/asset-only fixes."""
        selected = self.plan.get('target_build',{})
        package_ref,manifest_ref = selected.get('package_report'),selected.get('handoff_manifest')
        package = self.ref(package_ref,'target_build.package_report')
        manifest = self.ref(manifest_ref,'target_build.handoff_manifest')
        self.gate(package.get('success') is True,'target_build.successful_actual_package_report_required')
        expected_report = reference_identity(package_ref)
        report_path = os.path.normcase(str(Path(manifest['build_report']).resolve())) if manifest.get('build_report') else None
        self.gate(manifest.get('success') is True and expected_report and report_path == expected_report[0],
                  'target_build.handoff_must_reference_selected_package_report')
        package_root = Path(manifest.get('demo','')).resolve()
        rows = manifest.get('files',[])
        valid_root = inside(package_root,ROOT/'output') and io_path(package_root).is_dir()
        self.gate(valid_root and isinstance(rows,list) and len(rows)>0 and manifest.get('file_count') == len(rows),
                  'target_build.complete_actual_handoff_file_inventory_required')
        verified,seen = [],set()
        for row in rows if isinstance(rows,list) else []:
            if not self.gate(isinstance(row,dict) and row.get('path') and row.get('sha256') and
                             isinstance(row.get('bytes'),int),'target_build.structured_package_file_required'): continue
            relative = str(row['path']).replace('\\','/')
            file = (package_root/relative).resolve()
            safe = (valid_root and not Path(relative).is_absolute() and '..' not in relative.split('/') and
                    file.is_relative_to(package_root) and relative.casefold() not in seen)
            self.gate(safe,'target_build.safe_unique_package_relative_file_required',relative)
            seen.add(relative.casefold())
            actual = safe and io_path(file).is_file()
            matched = self.gate(actual and io_path(file).stat().st_size == row['bytes'] and sha(file) == str(row['sha256']).lower(),
                                'target_build.actual_whole_package_file_changed',relative)
            if matched: verified.append({'path':relative,'bytes':row['bytes'],'sha256':str(row['sha256']).lower()})
        if valid_root:
            auxiliary = {str(row.get('path','')).replace('\\','/').casefold() for row in manifest.get('auxiliary_handoff_files',[])}
            package_io = io_path(package_root)
            actual_inventory = {file.relative_to(package_io).as_posix().casefold() for file in package_io.rglob('*')
                                if file.is_file() and file.relative_to(package_io).as_posix().casefold() not in auxiliary and
                                not file.relative_to(package_io).as_posix().casefold().startswith('yesterdayharbor/saved/')}
            self.gate(actual_inventory == seen,'target_build.manifest_must_cover_every_package_file',
                      {'unlisted':sorted(actual_inventory-seen),'missing':sorted(seen-actual_inventory)})
        required_suffixes = ['YesterdayHarbor-Win64-Shipping.exe','.pak','.ucas','.utoc']
        self.gate(all(any(row['path'].lower().endswith(suffix.lower()) for row in verified) for suffix in required_suffixes),
                  'target_build.executable_and_all_cooked_container_types_required')
        self.gate(sum(row['bytes'] for row in verified) == manifest.get('total_bytes') and len(verified) == len(rows),
                  'target_build.verified_full_file_count_and_total_bytes_required')
        canonical = json.dumps(sorted(verified,key=lambda row:row['path'].casefold()),sort_keys=True,separators=(',',':')).encode('utf-8')
        self.target_build = {'package_report':expected_report,'handoff_manifest':reference_identity(manifest_ref),
            'package_root':package_root,'files':verified,'whole_package_fingerprint_sha256':hashlib.sha256(canonical).hexdigest()}
        self.report['selected_target_build'] = {'package_report':package_ref,'handoff_manifest':manifest_ref,
            'verified_package_file_count':len(verified),'verified_package_total_bytes':sum(row['bytes'] for row in verified),
            'whole_package_fingerprint_sha256':self.target_build['whole_package_fingerprint_sha256'],
            'identity_scope':'Exact package-report path+SHA and full handoff path+SHA, with every declared cooked/package file rehashed. Exe SHA alone is insufficient.'}

    def validate_take(self, label, take):
        code = label+'.'+take['id']
        path = Path(take.get('path','')).resolve()
        okay = self.gate(inside(path,ROOT/'output') and path.suffix.lower() in VIDEO_EXTENSIONS and io_path(path).is_file(), code+'.native_video_file_required', str(path))
        digest = sha(path) if okay else None
        self.gate(okay and digest == take.get('sha256'), code+'.video_sha256_required')
        self.gate(take.get('kind') in ['native_gameplay_video','native_game_cinematic_video'], code+'.native_game_video_kind_required')
        self.gate(take.get('speed') == 1.0 and not take.get('generated_frames') and not take.get('time_warp'), code+'.normal_speed_original_frames_required')
        capture = self.ref(take.get('capture_report'),code+'.capture')
        self.gate(capture.get('success') is True and capture.get('recorded') is True and
                  digest in [capture.get('raw_sha256'),capture.get('video_sha256')] and
                  not capture.get('window_state_violations'), code+'.actual_successful_bound_capture_required')
        build = take.get('build',{})
        executable = Path(build.get('executable','')).resolve()
        build_okay = inside(executable,ROOT/'output') and io_path(executable).is_file()
        self.gate(build_okay and sha(executable) == str(build.get('sha256','')).lower(), code+'.actual_same_build_executable_required')
        package = self.ref(build.get('package_report'),code+'.build_package')
        self.gate(package.get('success') is True, code+'.successful_real_package_report_required')
        target_report = self.target_build.get('package_report')
        target_manifest = self.target_build.get('handoff_manifest')
        self.gate(target_report is not None and reference_identity(build.get('package_report')) == target_report,
                  code+'.must_use_exact_selected_package_report_path_and_sha')
        self.gate(target_manifest is not None and reference_identity(build.get('handoff_manifest')) == target_manifest,
                  code+'.must_use_exact_selected_whole_package_handoff_path_and_sha')
        package_root = self.target_build.get('package_root',ROOT/'output')
        relative_exe = executable.relative_to(package_root).as_posix() if executable.is_relative_to(package_root) else None
        self.gate(relative_exe is not None and any(row['path'].casefold() == relative_exe.casefold() and
                  row['sha256'] == str(build.get('sha256','')).lower() for row in self.target_build.get('files',[])),
                  code+'.recorded_executable_must_belong_to_verified_selected_package')
        self.gate(process_image(capture) == os.path.normcase(str(executable)),code+'.actual_video_process_image_must_match_recorded_build')
        hardware = take.get('hardware',{})
        self.gate(all(isinstance(hardware.get(k),str) and hardware[k] for k in ['cpu','gpu','resolution','graphics_settings']), code+'.actual_capture_hardware_settings_required')
        review = self.ref(take.get('review'),code+'.content_review')
        flags = ['native_scene_verified','no_concept_images','asset_audio_rights_verified','spoilers_reviewed',
                 'no_secret_identity_leak','legitimate_progression','no_quest_prerequisite_bypass']
        self.gate(review.get('success') is True and review.get('video_sha256') == digest and
                  str(review.get('build_executable_sha256','')).lower() == str(build.get('sha256','')).lower() and
                  target_report is not None and str(review.get('package_report_sha256','')).lower() == target_report[1] and
                  target_manifest is not None and str(review.get('handoff_manifest_sha256','')).lower() == target_manifest[1] and
                  review.get('reviewed_by') and review.get('reviewed_at_utc') and review.get('qa_profile') and
                  review.get('route') == 'clinic' and all(review.get(k) is True for k in flags), code+'.actual_review_of_source_content_route_rights_required')
        audio = take.get('audio',{})
        audio_path = Path(audio.get('path','')).resolve()
        audio_okay = inside(audio_path,ROOT/'output') and io_path(audio_path).is_file() and audio_path.suffix.lower() in {'.wav','.nut','.mkv','.mp4','.mov'}
        audio_digest = sha(audio_path) if audio_okay else None
        self.gate(audio_okay and audio_digest == audio.get('sha256'), code+'.actual_original_game_audio_required')
        audio_capture = self.ref(audio.get('capture_report'),code+'.audio_capture')
        native = audio_capture.get('native_report',{}).get('actual',{})
        native_image = os.path.normcase(str(Path(native['actual_process_image']).resolve())) if native.get('actual_process_image') else None
        self.gate(process_image(audio_capture) == native_image == os.path.normcase(str(executable)) and
                  capture.get('evidence',{}).get('process_id') == audio_capture.get('evidence',{}).get('process_id') == native.get('pid') and
                  native.get('pid') is not None,code+'.actual_audio_video_process_binding_must_match_recorded_build')
        self.gate(audio_capture.get('success') is True and audio_capture.get('recorded') is True and
                  audio_capture.get('actual_capture_format_validated') is True and
                  audio_capture.get('wav_sha256') == audio_digest and audio_capture.get('audible_signal_detected') is True and
                  audio_capture.get('mode') == 'INCLUDE_TARGET_PROCESS_TREE_ONLY' and
                  native.get('microphone') is False and native.get('desktop_mix') is False and
                  isinstance(native.get('timestamp_error_packets'),int) and isinstance(native.get('discontinuity_packets'),int),
                  code+'.actual_nonzero_process_only_clocked_audio_required')
        alignment = self.ref(audio.get('alignment'),code+'.audio_alignment')
        offset = alignment.get('audio_zero_at_video_zero_sample')
        alignment_okay = (alignment.get('success') is True and alignment.get('video_sha256') == digest and
            alignment.get('audio_sha256') == audio_digest and isinstance(offset,int) and not isinstance(offset,bool) and
            alignment.get('method') == 'measured_native_qpc_packet_alignment' and
            alignment.get('reviewed_audio_video_sync') is True and alignment.get('reviewed_by') and
            alignment.get('selected_audio_no_unrepresented_gaps') is True and
            alignment.get('selected_interval_discontinuities') == 0 and alignment.get('selected_interval_timestamp_errors') == 0 and
            isinstance(alignment.get('max_alignment_error_ms'),(int,float)) and 0 <= alignment['max_alignment_error_ms'] <= 20 and
            isinstance(alignment.get('clock_drift_ms_over_take'),(int,float)) and abs(alignment['clock_drift_ms_over_take']) <= 10)
        self.gate(alignment_okay,code+'.measured_packet_clock_alignment_required')
        take['_video_path'],take['_audio_path'],take['_alignment'],take['_review'] = path,audio_path,alignment,review
        self.report['source_takes'].append({'shot':label,'id':take['id'],'path':str(path),'sha256':digest,
            'audio_path':str(audio_path),'audio_sha256':audio_digest,'build_executable_sha256':build.get('sha256'),
            'package_report':build.get('package_report'),'handoff_manifest':build.get('handoff_manifest'),
            'whole_package_fingerprint_sha256':self.target_build.get('whole_package_fingerprint_sha256')})

    def validate_route(self):
        route = self.ref(self.plan.get('route_evidence'),'route.provenance')
        build_shas = {str(t.get('build',{}).get('sha256','')).lower() for t in self.takes.values()}
        take_shas = {t.get('sha256') for t in self.takes.values()}
        self.gate(bool(self.takes) and len(build_shas) == 1 and '' not in build_shas,'route.same_actual_game_build_required')
        self.gate(bool(self.takes) and all(reference_identity(t.get('build',{}).get('package_report')) == self.target_build.get('package_report') and
                  reference_identity(t.get('build',{}).get('handoff_manifest')) == self.target_build.get('handoff_manifest') for t in self.takes.values()) and
                  self.target_build.get('package_report') is not None and self.target_build.get('handoff_manifest') is not None,
                  'route.every_take_must_match_the_selected_whole_package_not_only_exe')
        self.gate(route.get('success') is True and route.get('qa_profile') and
                  str(route.get('build_executable_sha256','')).lower() in build_shas and
                  self.target_build.get('package_report') is not None and str(route.get('package_report_sha256','')).lower() == self.target_build['package_report'][1] and
                  self.target_build.get('handoff_manifest') is not None and str(route.get('handoff_manifest_sha256','')).lower() == self.target_build['handoff_manifest'][1] and
                  take_shas.issubset(set(route.get('video_sha256s',[]))) and
                  route.get('original_memorial_inspected_through_play') is True and
                  route.get('clinic_cover_installed_through_play') is True and
                  route.get('direct_story_flag_writes') is False and route.get('quest_prerequisite_bypass') is False and
                  route.get('reviewed_by') and route.get('reviewed_at_utc'), 'route.actual_inspection_and_clinic_installation_evidence_required')
        events = route.get('events',[])
        for name in ['OriginalMemorialInspected','ClinicCanvasPhysicallyInstalled']:
            selected = [e for e in events if isinstance(e,dict) and e.get('name') == name]
            self.gate(bool(selected) and any(e.get('video_sha256') in take_shas and
                      isinstance(e.get('source_time_seconds'),(int,float)) and e['source_time_seconds'] >= 0 and
                      e.get('native_or_human_observation_reference') for e in selected), 'route.actual_event_required.'+name)

    def validate_s07(self, shot, local, segments):
        self.gate(shot.get('start_frame') == 4200 and shot.get('end_frame_exclusive') == 5100 and
                  shot.get('duration_frames') == 900 and len(segments) == 1,'S07.exact_single_contiguous_900_frame_trim_required')
        self.gate(not shot.get('overlays') and not shot.get('end_fade_frames'), 'S07.no_editorial_overlay_fade_or_transform_permitted')
        if len(segments) != 1 or segments[0].get('take_id') not in local: return
        segment = segments[0]; take = local[segment['take_id']]
        self.gate(take.get('kind') == 'native_gameplay_video','S07.cinematic_insert_forbidden')
        proof = self.ref(take.get('input_evidence'),'S07.real_input')
        true_flags = ['continuous_player_control','actual_keyboard_or_gamepad_input','normal_original_game_clock','real_clinic_approach',
                      'contextual_interaction','no_quest_prerequisite_bypass','minimal_real_prompts_subtitles']
        false_flags = ['scripted_camera','free_camera','teleport','speed_change','cuts','camera_or_story_script']
        self.gate(proof.get('success') is True and proof.get('kind') == 'player_input_review' and
                  proof.get('input_source') in ['human','computer_use_native_keyboard_or_gamepad'] and
                  proof.get('video_sha256') == take.get('sha256') and proof.get('audio_sha256') == take.get('audio',{}).get('sha256') and
                  proof.get('reviewed_by') and proof.get('reviewed_at_utc') and proof.get('actual_input_observation_reference') and
                  proof.get('source_in_frame') == segment.get('source_in_frame') and proof.get('frame_count') == 900 and
                  all(proof.get(k) is True for k in true_flags) and all(proof.get(k) is False for k in false_flags),
                  'S07.actual_review_of_player_input_original_clock_and_contextual_interaction_required')
        events = proof.get('events',[])
        for kind in ['player_movement','contextual_interaction']:
            self.gate(any(e.get('kind') == kind and isinstance(e.get('relative_frame'),int) and
                          0 <= e['relative_frame'] < 900 and e.get('observation_reference') for e in events if isinstance(e,dict)),
                      'S07.actual_input_event_required.'+kind)

    def validate_overlays(self, shot, local, segments):
        label = shot['id']; overlays = shot.get('overlays',[])
        self.gate(shot.get('timed_caption_review',{}).get('approved') is True and
                  shot.get('timed_caption_review',{}).get('reviewed_by') and
                  shot.get('timed_caption_review',{}).get('actual_source_captions_or_timed_overlays_reviewed') is True,
                  label+'.actual_readable_caption_timing_review_required')
        for index, overlay in enumerate(overlays):
            first,last = overlay.get('start_frame'),overlay.get('end_frame_exclusive')
            okay = isinstance(first,int) and isinstance(last,int) and 0 <= first < last <= shot['duration_frames']
            self.gate(okay and overlay.get('approved') is True and overlay.get('text') and
                      overlay.get('kind') in ['speaker_caption','title','cinematic_label'], label+'.approved_timed_overlay_required.'+str(index))
            font = Path(overlay.get('font_path','')).resolve()
            self.gate(io_path(font).is_file() and sha(font) == overlay.get('font_sha256'),label+'.verified_font_required.'+str(index))
            self.gate(isinstance(overlay.get('x'),int) and isinstance(overlay.get('y'),int) and
                      isinstance(overlay.get('font_size'),int) and 24 <= overlay['font_size'] <= 100,
                      label+'.explicit_readable_overlay_layout_required.'+str(index))
            if overlay.get('kind') == 'title': self.gate(label == 'S13', label+'.promotional_title_only_in_title_slot')
            if overlay.get('kind') == 'cinematic_label': self.gate(overlay.get('text') == 'Cinematic insert',label+'.unambiguous_cinematic_label_required')
        if label == 'S13':
            titles = [o.get('text') for o in overlays if o.get('kind') == 'title']
            self.gate(titles == TITLE_LINES,'S13.exact_approved_title_tagline_scope_required')
            self.gate(all(o.get('end_frame_exclusive',0)-o.get('start_frame',0) >= 150 for o in overlays if o.get('kind') == 'title'),
                      'S13.title_lines_need_at_least_five_seconds')
        fade = shot.get('end_fade_frames',0)
        self.gate(isinstance(fade,int) and 0 <= fade <= 60 and (fade == 0 or label == 'S13' and shot.get('end_fade_approved') is True),label+'.only_explicit_approved_title_end_fade_supported')
        cursor = 0
        for segment in segments:
            length = segment.get('frame_count',0); take = local.get(segment.get('take_id'),{})
            if take.get('kind') == 'native_game_cinematic_video':
                self.gate(any(o.get('kind') == 'cinematic_label' and o.get('start_frame',99999) <= cursor and
                              o.get('end_frame_exclusive',-1) >= cursor+length for o in overlays),label+'.cinematic_insert_must_be_labeled_throughout')
            cursor += length if isinstance(length,int) else 0

    def run(self, command, label, timeout=1800, capture=False):
        self.report['ffmpeg_invoked'] = True
        row = {'label':label,'command':[str(v) for v in command]}; self.report['commands'].append(row); self.write()
        result = subprocess.run(row['command'],cwd=self.folder,capture_output=True,text=True,encoding='utf-8',errors='replace',
                                timeout=timeout,creationflags=NO_WINDOW)
        log = self.folder/(label+'.log'); log.write_text(result.stderr,encoding='utf-8')
        row.update(returncode=result.returncode,stderr_log=str(log),stderr_sha256=sha(log)); self.write()
        if result.returncode != 0: raise RuntimeError(label+' failed; inspect '+str(log))
        if not capture: (self.folder/(label+'.stdout')).write_text(result.stdout,encoding='utf-8')
        return result.stdout

    def probe(self, path, label, frames=True):
        path = Path(path).resolve()
        digest = sha(path)
        key = (os.path.normcase(str(path)),digest,bool(frames))
        cached = self._probe_cache.get(key)
        if cached:
            file = self.folder/(label+'.json')
            file.write_text(cached['text'],encoding='utf-8')
            self.report.setdefault('probe_cache_hits',[]).append({
                'label':label,'actual_probe_label':cached['label'],'path':str(path),
                'sha256':digest,'frames_mode':bool(frames),'metadata_json':str(file)})
            self.write()
            return json.loads(cached['text'])
        duration_text = self.run([self.ffprobe,'-v','error','-show_entries',
            'format=duration:stream=duration','-of','json',str(path)],
            label+'_duration',timeout=60,capture=True)
        (self.folder/(label+'_duration.json')).write_text(duration_text,encoding='utf-8')
        duration_data = json.loads(duration_text)
        durations = []
        for value in [duration_data.get('format',{})]+duration_data.get('streams',[]):
            try:
                seconds = float(value.get('duration',0))
                if math.isfinite(seconds) and seconds > 0: durations.append(seconds)
            except (TypeError,ValueError):
                pass
        duration = max(durations) if durations else None
        timeout = min(1800,max(300,duration*4+60)) if duration is not None else 1800
        self.report.setdefault('probe_settings',[]).append({
            'label':label,'path':str(path),'sha256':digest,'frames_mode':bool(frames),
            'decoder_threads':8,'actual_duration_metadata_seconds':duration,
            'timeout_seconds':timeout,'timeout_scope':'Bounded decode budget only; duration is not gameplay or cadence proof'})
        command = [self.ffprobe,'-v','error','-threads','8','-count_frames','-show_streams','-show_format']
        if frames: command += ['-show_frames','-show_entries','frame=media_type,best_effort_timestamp_time,pkt_duration_time,interlaced_frame:stream:format']
        command += ['-of','json',str(path)]
        text = self.run(command,label,timeout=timeout,capture=True)
        file = self.folder/(label+'.json'); file.write_text(text,encoding='utf-8')
        data = json.loads(text)
        if sha(path) != digest:
            raise RuntimeError('Actual media changed during probe; cached metadata refused: '+str(path))
        self._probe_cache[key] = {'text':text,'label':label}
        return data

    def probe_sources(self):
        for (shot_id,take_id),take in self.takes.items():
            data = self.probe(take['_video_path'],'probe_'+shot_id+'_'+take_id)
            videos = [s for s in data.get('streams',[]) if s.get('codec_type') == 'video']
            self.check(len(videos) == 1,'Exactly one real source video stream',str(take['_video_path']))
            video = videos[0]
            self.check([video.get('width'),video.get('height')] == [1920,1080] and video.get('field_order') in ['progressive','unknown'],
                       'Source is native progressive1080p',video)
            points = [float(f['best_effort_timestamp_time']) for f in data.get('frames',[]) if f.get('media_type') == 'video' and 'best_effort_timestamp_time' in f]
            deltas = [b-a for a,b in zip(points,points[1:])]
            self.check(bool(deltas) and all(delta > 0 for delta in deltas),
                       'Actual original source timestamps are strictly increasing',
                       {'frames':len(points),'max_delta':max(deltas) if deltas else None,'min_delta':min(deltas) if deltas else None})
            self.check(not any(f.get('interlaced_frame') for f in data.get('frames',[]) if f.get('media_type') == 'video'),
                       'Decoded source frames are progressive')
            color = take.get('source_color')
            self.check(color in ['bt709_limited','bt709_full','srgb_full'], 'Source has explicit reviewed SDR transfer/primaries and range',color)
            self.check(video.get('color_transfer') in [None,'unknown','bt709','iec61966-2-1'] and video.get('color_primaries') in [None,'unknown','bt709'],
                       'Source does not contradict the reviewed SDR Rec709 encoding',video)
            audio_data = self.probe(take['_audio_path'],'audio_'+shot_id+'_'+take_id,frames=False)
            audios = [s for s in audio_data.get('streams',[]) if s.get('codec_type') == 'audio']
            self.check(len(audios) == 1 and int(audios[0].get('sample_rate',0)) == RATE and audios[0].get('channels') == 2,
                       'Actual source audio is48k stereo',audios)
            audio_frames = int(round(float(audios[0].get('duration',audio_data.get('format',{}).get('duration',0)))*RATE))
            take['_frame_count'],take['_audio_frames'] = len(points),audio_frames
            for shot in self.shots:
                if shot['id'] != shot_id: continue
                for segment in shot['edit_segments']:
                    if segment['take_id'] != take_id: continue
                    first,last = segment['source_in_frame'],segment['source_in_frame']+segment['frame_count']
                    native_audio_mapping = take['_alignment'].get('per_video_frame_audio_sample',[])
                    self.check(len(native_audio_mapping) == len(points) and all(isinstance(n,int) for n in native_audio_mapping),
                               'Measured original packet clocks map every source video frame to its audio sample')
                    audio_first = native_audio_mapping[first] if first < len(native_audio_mapping) else -1
                    audio_last = audio_first+segment['frame_count']*(RATE//FPS)
                    self.check(last <= len(points) and 0 <= audio_first < audio_last <= audio_frames,
                               'The original video and aligned audio fully cover the explicit trim',
                               {'shot':shot_id,'video_end_frame':last,'source_frames':len(points),'audio_first':audio_first,'audio_last':audio_last,'source_audio_frames':audio_frames})
                    segment['_audio_start_sample'] = audio_first
                    reviewed_first = int(take['_alignment'].get('source_in_frame',-1))
                    reviewed_last = reviewed_first+int(take['_alignment'].get('frame_count',0))
                    self.check(reviewed_first <= first < last <= reviewed_last,
                               'The concrete edit stays inside the actual reviewed aligned source interval')
                    selected = points[first:last]
                    actual_deltas = [b-a for a,b in zip(selected,selected[1:])]
                    errors = [(point-selected[0])-index/FPS for index,point in enumerate(selected)]
                    mapping = [int(math.floor((point-selected[0])*FPS+.5)) for point in selected]
                    # A real-time VFR capture may jitter around each30Hz tick.
                    # Accept it only when nearest-tick selection maps every
                    # consecutive original frame one-to-one to the output.
                    # No dropped source frame, added duplicate, interpolation,
                    # speed ramp, gap repair or accumulated drift is accepted.
                    self.check(len(selected) == segment['frame_count'] and
                               mapping == list(range(segment['frame_count'])) and
                               all(0 < gap <= .050 for gap in actual_deltas) and
                               all(abs(error) <= .5/FPS for error in errors) and
                               abs((selected[-1]-selected[0]+1/FPS)-segment['frame_count']/FPS) <= 1/FPS,
                               'Selected original frames map one-to-one to30Hz without gaps, duplicate/drop or speed change',
                               {'shot':shot_id,'take':take_id,'frames':len(selected),
                                'max_original_gap_seconds':max(actual_deltas) if actual_deltas else 0,
                                'max_clock_quantization_seconds':max((abs(e) for e in errors),default=0),
                                'actual_wall_duration_seconds':selected[-1]-selected[0]+1/FPS if selected else None,
                                'output_duration_seconds':segment['frame_count']/FPS})
                    self.report.setdefault('source_frame_clock_mappings',[]).append({
                        'shot':shot_id,'take':take_id,'source_in_frame':first,'frame_count':len(selected),
                        'nearest_tick_mapping_one_to_one':True,'dropped_or_added_frames':0,
                        'max_timestamp_quantization_seconds':max((abs(e) for e in errors),default=0),
                        'timestamp_policy':'Bounded30Hz nominal-cadence quantization only; every selected consecutive original frame retained once. Audio keeps its original48k clock.'})

    @staticmethod
    def color_filter(take):
        color = take['source_color']
        range_name = 'limited' if color == 'bt709_limited' else 'full'
        basic = 'scale=in_range=%s:out_range=limited:in_color_matrix=bt709:out_color_matrix=bt709,format=yuv420p'%range_name
        if color == 'srgb_full':
            # First express the same sRGB samples in planar709 YUV, then perform
            # the explicit sRGB-to709 transfer conversion. Color metadata alone
            # is never substituted for this transfer conversion.
            basic += ',colorspace=ispace=bt709:iprimaries=bt709:itrc=iec61966-2-1:irange=tv:all=bt709:range=tv:format=yuv420p'
        return basic

    @staticmethod
    def escape_filter_path(path):
        # Filter-script quoting is independent of the subprocess argument list.
        return str(Path(path).resolve()).replace('\\','/').replace(':','\\:').replace("'","'\\''")

    def encode_shot(self, shot):
        command = [self.ffmpeg,'-hide_banner','-nostdin','-n']
        filters, outputs = [], []
        for index,segment in enumerate(shot['edit_segments']):
            take = self.takes[(shot['id'],segment['take_id'])]
            command += ['-i',take['_video_path'],'-i',take['_audio_path']]
            first,length = segment['source_in_frame'],segment['frame_count']
            filters.append('[%d:v:0]trim=start_frame=%d:end_frame=%d,setpts=N/(30*TB),%s,setsar=1[v%d]'%(index*2,first,first+length,self.color_filter(take),index))
            audio_first = segment['_audio_start_sample']
            filters.append('[%d:a:0]atrim=start_sample=%d:end_sample=%d,asetpts=PTS-STARTPTS[a%d]'%(index*2+1,audio_first,audio_first+length*(RATE//FPS),index))
            outputs += ['[v%d][a%d]'%(index,index)]
        if len(outputs) == 1: video,audio = 'v0','a0'
        else:
            filters.append(''.join(outputs)+'concat=n=%d:v=1:a=1[vjoined][ajoined]'%len(outputs)); video,audio = 'vjoined','ajoined'
        for index,overlay in enumerate(shot.get('overlays',[])):
            text_file = self.folder/(shot['id']+'_overlay_'+str(index)+'.txt')
            text_file.write_text(overlay['text'],encoding='utf-8')
            next_video = 'voverlay'+str(index)
            filters.append("[%s]drawtext=fontfile='%s':textfile='%s':expansion=none:fontcolor=white:fontsize=%d:x=%d:y=%d:box=1:boxcolor=black@0.65:boxborderw=14:enable='between(n,%d,%d)'[%s]"%
                           (video,self.escape_filter_path(overlay['font_path']),self.escape_filter_path(text_file),overlay['font_size'],overlay['x'],overlay['y'],overlay['start_frame'],overlay['end_frame_exclusive']-1,next_video))
            video = next_video
        fade = shot.get('end_fade_frames',0)
        if fade:
            filters.append('[%s]fade=t=out:start_frame=%d:nb_frames=%d[vfade]'%(video,shot['duration_frames']-fade,fade)); video = 'vfade'
            filters.append('[%s]afade=t=out:st=%.9f:d=%.9f[afade]'%(audio,(shot['duration_frames']-fade)/FPS,fade/FPS)); audio = 'afade'
        script = self.folder/(shot['id']+'_filters.txt'); script.write_text(';\n'.join(filters),encoding='utf-8')
        target = self.folder/(shot['id']+'_LOSSLESS_EDIT.nut')
        command += ['-/filter_complex',script,'-map','['+video+']','-map','['+audio+']',
                    '-c:v','ffv1','-level','3','-g','1','-pix_fmt','yuv420p','-fps_mode:v','passthrough','-enc_time_base:v','1:30',
                    '-c:a','pcm_s16le','-ar','48000','-ac','2',
                    '-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709',target]
        self.run(command,'encode_'+shot['id'])
        data = self.probe(target,'check_'+shot['id'],frames=False)
        video_stream = next(s for s in data['streams'] if s['codec_type'] == 'video')
        self.check(int(video_stream.get('nb_read_frames',0)) == shot['duration_frames'], 'Actual lossless slot frame count: '+shot['id'],video_stream)
        return target

    def encode(self):
        if self.report['missing_gates']: raise RuntimeError('Missing concrete footage/evidence gates block encoding')
        self.probe_sources()
        edits = [self.encode_shot(shot) for shot in self.shots]
        concat = self.folder/'lossless_shot_concat.txt'
        # All generated names are fixed ASCII basename-only and are beneath cwd.
        concat.write_text(''.join("file '"+path.name+"'\n" for path in edits),encoding='utf-8')
        raw = self.folder/'TRAILER_RAW_AAC_PADDING.mp4'
        command = [self.ffmpeg,'-hide_banner','-nostdin','-n','-f','concat','-safe','1','-i',concat,
            '-map','0:v:0','-map','0:a:0','-c:v','libx264','-preset','slow','-crf','18','-pix_fmt','yuv420p',
            '-fps_mode:v','passthrough','-enc_time_base:v','1:30','-frames:v','9000','-video_track_timescale','30000','-g','60',
            '-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709',
            '-c:a','aac','-b:a','256k','-ar','48000','-ac','2','-t','300','-movflags','+faststart',raw]
        self.run(command,'encode_final',timeout=3600)
        # Use the already reviewed narrow AAC end-padding presentation repair.
        # It keeps priming, sample tables, media payload and the raw MP4 intact.
        sys.path.insert(0,str(ROOT/'tools'))
        from smoke_blender_encoder import inspect_mp4_bytes, trim_aac_end_presentation
        raw_bytes = io_path(raw).read_bytes()
        metadata = inspect_mp4_bytes(raw_bytes)
        audio = next(t for t in metadata['tracks'] if t['handler'] == 'soun')
        if abs(audio.get('presented_seconds_from_edit_list',-1)-300) < 1e-9 and abs(metadata['movie_timing']['seconds']-300) < 1e-9:
            final_bytes,trim = raw_bytes,{'method':'No padding repair needed; native presentation is already exactly300seconds'}
        else: final_bytes,trim = trim_aac_end_presentation(raw_bytes,seconds=300.0)
        final = self.folder/'The_Other_Side_of_Yesterday_Chapters_I_II_Trailer_300s.mp4'
        with final.open('xb') as file: file.write(final_bytes)
        self.report.update(encoded=True,final_video_path=str(final),final_video_sha256=sha(final),
                           preserved_raw_path=str(raw),preserved_raw_sha256=sha(raw),aac_presentation=trim)
        self.write(); self.verify(final)

    def verify(self, final):
        final = Path(final).resolve()
        if not inside(final,ROOT/'output') or not io_path(final).is_file(): raise RuntimeError('Actual exported video required')
        data = self.probe(final,'final_ffprobe',frames=True)
        videos = [s for s in data['streams'] if s['codec_type'] == 'video']
        audios = [s for s in data['streams'] if s['codec_type'] == 'audio']
        self.check(len(videos) == len(audios) == 1,'Actual final has exactly one video and audio stream')
        video,audio = videos[0],audios[0]
        points = [float(f['best_effort_timestamp_time']) for f in data.get('frames',[]) if f.get('media_type') == 'video' and 'best_effort_timestamp_time' in f]
        self.check(video.get('codec_name') == 'h264' and video.get('pix_fmt') == 'yuv420p' and
                   [video.get('width'),video.get('height')] == [1920,1080], 'Decoded final is H264 progressive1080p SDR8bit',video)
        self.check(video.get('field_order') == 'progressive' and not any(f.get('interlaced_frame') for f in data.get('frames',[]) if f.get('media_type') == 'video'), 'Actual final progressive scan')
        self.check(len(points) == TOTAL == int(video.get('nb_read_frames',0)) and
                   Fraction(video.get('avg_frame_rate','0/1')) == FPS and abs(points[0]) < 1e-6 and
                   all(abs(point-index/FPS) <= .000001 for index,point in enumerate(points)),
                   '9000 decoded frames with exact monotonic30Hz PTS and no extra frames', {'decoded':len(points),'first':points[0] if points else None,'last':points[-1] if points else None})
        self.check(all(video.get(key) == 'bt709' for key in ['color_space','color_transfer','color_primaries']) and video.get('color_range') == 'tv', 'Actual SDRRec709 metadata',video)
        self.check(audio.get('codec_name') == 'aac' and int(audio.get('sample_rate',0)) == RATE and audio.get('channels') == 2,
                   'Actual AAC stereo48k audio',audio)
        sys.path.insert(0,str(ROOT/'tools'))
        from smoke_blender_encoder import inspect_mp4
        mp4 = inspect_mp4(final); self.report['actual_mp4_sample_tables'] = mp4
        self.check(abs(mp4['movie_timing']['seconds']-300) < 1e-9 and
                   all(abs(t['track_presentation_seconds']-300) < 1e-9 for t in mp4['tracks']), 'Exact300second actual movie/track presentation including AAC padding')
        contact_frames = [0]+[(shot['start_frame']+shot['end_frame_exclusive']-1)//2 for shot in self.shots]+[8999]
        contact = self.folder/'DECODED_CONTACT_SHEET.png'
        expression = '+'.join('eq(n,%d)'%frame for frame in contact_frames)
        self.run([self.ffmpeg,'-hide_banner','-nostdin','-n','-i',final,'-an','-vf',"select='%s',scale=480:270,tile=3x5"%expression,
                  '-frames:v','1','-update','1',contact],'decoded_contact_sheet',timeout=300)
        self.check(io_path(contact).is_file() and io_path(contact).stat().st_size > 20000,'Actual final decoded contact sheet exists')
        self.report['contact_sheet'] = {'path':str(contact),'sha256':sha(contact),'frame_indices_row_major':contact_frames}
        self.run([self.ffmpeg,'-hide_banner','-nostdin','-i',final,'-map','0:v:0','-an','-f','framemd5','-'], 'decoded_all_frame_hashes', timeout=600)
        hash_file = self.folder/'decoded_all_frame_hashes.stdout'
        lines = [line for line in hash_file.read_text().splitlines() if line and not line.startswith('#')]
        self.check(len(lines) == TOTAL,'FFmpeg independently decodes all9000 output frames',len(lines))
        hashes = [line.rsplit(',',1)[-1].strip() for line in lines]
        repeats = [i for i in range(1,len(hashes)) if hashes[i] == hashes[i-1]]
        self.report['adjacent_identical_decoded_frames'] = repeats
        self.report['duplicate_frame_scope'] = 'Identical pixels may be legitimate stillness. No frame-rate filter/loop/interpolation is used; frame-count/PTS checks plus S07 PSNR and human raw-take review are required. Pixel equality alone is not a dropped-frame detector.'
        self.verify_s07(final)
        pcm_file = self.folder/'FINAL_DECODED_48k_STEREO_PCM16.raw'
        self.run([self.ffmpeg,'-hide_banner','-nostdin','-n','-i',final,'-map','0:a:0','-vn',
                  '-c:a','pcm_s16le','-ar','48000','-ac','2','-f','s16le',pcm_file], 'decoded_final_audio',timeout=300)
        import array
        pcm = array.array('h'); pcm.frombytes(io_path(pcm_file).read_bytes())
        if sys.byteorder != 'little': pcm.byteswap()
        frames = len(pcm)//2
        left_rms = math.sqrt(sum((sample/32768)**2 for sample in pcm[::2])/max(1,frames))
        right_rms = math.sqrt(sum((sample/32768)**2 for sample in pcm[1::2])/max(1,frames))
        self.check(abs(frames-RATE*300) <= 1024 and left_rms > 1e-6 and right_rms > 1e-6,
                   'Actual decoded final audio has300seconds of nonzero stereo PCM within one AAC packet of padding',
                   {'frames':frames,'left_rms':left_rms,'right_rms':right_rms,'raw_sha256':sha(pcm_file)})
        black = self.run([self.ffmpeg,'-hide_banner','-nostdin','-ss','280','-i',final,'-an','-vf','blackdetect=d=0.05:pix_th=0.10','-f','null','-'], 'decoded_tail_black_check',timeout=120)
        # blackdetect reports on stderr retained in the command log.
        tail_log = (self.folder/'decoded_tail_black_check.log').read_text()
        ranges = [dict(start=float(a)+280,end=float(b)+280,duration=float(c)) for a,b,c in
                  re.findall(r'black_start:([0-9.]+)\s+black_end:([0-9.]+)\s+black_duration:([0-9.]+)',tail_log)]
        allowed_fade = self.shots[-1].get('end_fade_frames',0)/FPS if self.shots else 0
        self.check(all(row['start'] >= 300-allowed_fade-1/FPS and row['end'] <= 300+1/FPS for row in ranges),
                   'No black tail outside the explicitly approved final-slot fade',ranges)
        self.report.update(media_validation_passed=True,final_video_path=str(final),final_video_sha256=sha(final),
            success=False,release_acceptance_complete=False,final_content_review_required=True,
            remaining_gate='Actual final SHA-bound content review of captions, visual/audio sync, title, spoilers, route, rights and source-to-edit continuity is required.')
        self.write()

    def verify_s07(self, final):
        shot = next(s for s in self.shots if s['id'] == 'S07')
        segment = shot['edit_segments'][0]; take = self.takes[('S07',segment['take_id'])]
        first = segment['source_in_frame']
        script = self.folder/'S07_original_to_final_psnr.txt'
        script.write_text('[0:v:0]trim=start_frame=%d:end_frame=%d,setpts=N/(30*TB),%s[original];\n'
                          '[1:v:0]trim=start_frame=4200:end_frame=5100,setpts=PTS-STARTPTS[final];\n'
                          '[original][final]psnr=stats_file=S07_psnr_stats.txt[proof]'%(first,first+900,self.color_filter(take)),encoding='utf-8')
        self.run([self.ffmpeg,'-hide_banner','-nostdin','-i',take['_video_path'],'-i',final,
                  '-/filter_complex',script,'-map','[proof]','-an','-f','null','-'],'S07_original_frame_sequence_comparison',timeout=600)
        rows = (self.folder/'S07_psnr_stats.txt').read_text().splitlines()
        values = [float(v) if v != 'inf' else math.inf for row in rows for v in re.findall(r'psnr_avg:([0-9.]+|inf)',row)]
        self.check(len(rows) == 900 and len(values) == 900 and min(values) >= 30,
                   'Every S07 final frame matches its one consecutive original source frame after encoding',
                   {'actual_compared_frames':len(values),'minimum_psnr_db':min(values) if values else None})
        self.report['S07_sequence_validation'] = {'source_file':str(take['_video_path']),'source_sha256':take['sha256'],
            'source_start_frame':first,'source_frames':900,'timeline_start_frame':4200,'timeline_end_frame_exclusive':5100,
            'cuts_inside_S07':0,'speed_change':False,'fps_filter':False,'frame_loop':False,'interpolation':False,
            'original_frames_each_used_once':True,'bounded_nominal_cadence_quantization':True,
            'evidence_scope':'Actual decoded frame sequence comparison; player input, normal clock, prerequisite and audio-clock proof remain the SHA-bound source evidence. Human or actual computer-use native keyboard/gamepad input is accepted.'}

    def final_review(self, reference):
        review = self.ref(reference,'final.actual_review')
        flags = ['caption_timing_readable','audio_video_sync_reviewed','title_correct','clinic_route_consistent',
                 'no_secret_identity_or_later_spoilers','audio_asset_rights_verified','no_extra_black_tail',
                 'no_added_repeated_or_dropped_frames','S07_original_to_final_continuity_reviewed']
        okay = (self.report.get('media_validation_passed') is True and review.get('success') is True and
                review.get('final_video_sha256') == self.report.get('final_video_sha256') and
                review.get('reviewed_by') and review.get('reviewed_at_utc') and
                all(review.get(k) is True for k in flags))
        self.gate(okay,'final.actual_SHA_bound_content_review_required')
        self.report.update(success=bool(okay),release_acceptance_complete=bool(okay),final_content_review_required=not okay)
        if okay: self.report.pop('remaining_gate',None)
        self.write()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,default=DEFAULT_PLAN)
    parser.add_argument('--output-directory',type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute',action='store_true',help='Probe sources and encode only after every concrete evidence gate passes')
    mode.add_argument('--verify-existing',type=Path,help='Decode/check an existing actual export; requires the same complete source evidence')
    parser.add_argument('--final-review',type=Path,help='Existing SHA-bound human review JSON; checked after actual media verification')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    job = Assembly(args.plan,args.output_directory or ROOT/'output/trailer_exports'/stamp)
    try:
        ready = job.preflight()
        if ready and args.execute: job.encode()
        elif ready and args.verify_existing:
            job.probe_sources(); job.verify(args.verify_existing)
        if ready and args.final_review:
            job.final_review({'path':str(args.final_review.resolve()),'sha256':sha(args.final_review)})
        job.report['ended_utc'] = utc(); job.write()
        print(json.dumps({'report':str(job.folder/'export_report.json'),'preflight_passed':ready,
                          'missing_gates':len(job.report['missing_gates']),'encoded':job.report['encoded'],
                          'media_validation_passed':job.report.get('media_validation_passed',False),
                          'release_acceptance_complete':job.report['release_acceptance_complete']},indent=2))
        return 0 if ready else 2
    except Exception:
        job.report.update(error=traceback.format_exc(),success=False,release_acceptance_complete=False,ended_utc=utc())
        job.write(); print(str(job.folder/'export_report.json')); raise


if __name__ == '__main__':
    raise SystemExit(main())
