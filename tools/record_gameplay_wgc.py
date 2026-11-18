"""Opt-in HWND-only Windows Graphics Capture; no application input.

Stock gfxcapture preserves compositor intervals but privately subtracts the
first SystemRelativeTime. We retain those relative showinfo timestamps AND
explicit libavformat packet-arrival UTC timestamps. The latter can be compared
with native process-audio clocks; they are not absolute compositor timestamps.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import ctypes
from ctypes import wintypes
import json
import os
import re
import subprocess
import time

from record_gameplay_window import ROOT, TOOLS, evidence, mismatch, observe, require, sha, utc

SOURCE_COMMIT = '946fcce07b'
SOURCE_URL = 'https://github.com/FFmpeg/FFmpeg/blob/' + SOURCE_COMMIT + '/libavfilter/vsrc_gfxcapture_winrt.cpp'
CAPTURE_METHOD = 'windows_graphics_capture_hwnd_lavfi_packet_arrival_utc_v1'


def native_image(pid):
    """Read the exact process image; no process memory or input access."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    require(handle, 'Cannot read actual capture process image')
    try:
        size, buffer = wintypes.DWORD(32768), ctypes.create_unicode_buffer(32768)
        require(kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)), 'QueryFullProcessImageNameW failed')
        return str(Path(buffer.value).resolve())
    finally:
        kernel.CloseHandle(handle)


class NativeClock:
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.QueryPerformanceCounter.argtypes = [ctypes.POINTER(ctypes.c_longlong)]
        self.kernel.QueryPerformanceFrequency.argtypes = [ctypes.POINTER(ctypes.c_longlong)]
        self.kernel.GetSystemTimePreciseAsFileTime.argtypes = [ctypes.POINTER(wintypes.FILETIME)]
        self.kernel.GetSystemTimeAsFileTime.argtypes = [ctypes.POINTER(wintypes.FILETIME)]
        frequency = ctypes.c_longlong()
        require(self.kernel.QueryPerformanceFrequency(ctypes.byref(frequency)) and frequency.value > 0, 'Native QPC frequency unavailable')
        self.frequency = frequency.value

    def pair(self, stage):
        before, after = ctypes.c_longlong(), ctypes.c_longlong()
        precise, system = wintypes.FILETIME(), wintypes.FILETIME()
        require(self.kernel.QueryPerformanceCounter(ctypes.byref(before)), 'Native QPC read failed')
        self.kernel.GetSystemTimePreciseAsFileTime(ctypes.byref(precise))
        self.kernel.GetSystemTimeAsFileTime(ctypes.byref(system))
        require(self.kernel.QueryPerformanceCounter(ctypes.byref(after)), 'Native QPC read failed')
        value = lambda f: (int(f.dwHighDateTime) << 32) | int(f.dwLowDateTime)
        return {'stage': stage, 'qpc_before': before.value, 'qpc_after': after.value,
                'precise_filetime_100ns_utc': value(precise), 'system_filetime_100ns_utc': value(system)}


def input_clock(log_text, frame_pts, started_utc, ended_utc):
    """Validate actual arrival UTC and separately retain original WGC intervals.

    libavformat's explicit UTC override runs after lavfi read_packet; showinfo
    is inside that source graph, before the override and CLI start offset.
    No launch-time estimate supplies the missing absolute compositor origin.
    """
    block = re.search(r'Input #0, lavfi,[\s\S]*?(?=Stream mapping:|Output #0,|$)', log_text)
    tbn = re.search(r'\b([0-9.]+)([kMG]?) tbn\b', block.group(0)) if block else None
    scale = {'': 1, 'k': 1000, 'M': 1000000, 'G': 1000000000}
    rate = float(tbn.group(1)) * scale[tbn.group(2)] if tbn else None
    packets = [int(p) for p in re.findall(r'(?<![+\w])demuxer -> ist_index:0:0 type:video\s+pkt_pts:(-?\d+)\b', log_text)]
    relative = [(int(n), int(p)) for n, p in re.findall(r'showinfo[^\n]*?\bn:\s*(\d+)\s+pts:\s*(-?\d+)\b', log_text)]
    source_tb = bool(re.search(r'showinfo[^\n]*config in time_base:\s*1/10000000\b', log_text))
    count = len(frame_pts)
    enough = count > 1 and len(packets) >= count and len(relative) >= count
    selected = packets[:count] if enough else []
    wgc = relative[:count] if enough else []
    # av_gettime is in microseconds; rescale to the lavfi1/10MHz timebase is exact.
    integer_us = bool(selected) and all(p % 10 == 0 for p in selected)
    utc_us = [p // 10 for p in selected] if integer_us else []
    errors = [abs((p-selected[0])/10 - (point-frame_pts[0])*1000000)
              for p, point in zip(selected, frame_pts)] if enough else []
    start = datetime.fromisoformat(started_utc).timestamp() * 1000000
    end = datetime.fromisoformat(ended_utc).timestamp() * 1000000
    valid = (rate == 10000000 and source_tb and enough and integer_us and
             all(b > a for a, b in zip(selected, selected[1:])) and
             [n for n, _ in wgc] == list(range(count)) and wgc[0][1] == 0 and
             all(b[1] > a[1] for a, b in zip(wgc, wgc[1:])) and
             all(error <= 2 for error in errors) and
             start-2000000 <= utc_us[0] <= end+2000000 and
             start-2000000 <= utc_us[-1] <= end+2000000)
    return {'success': bool(valid), 'capture_method': CAPTURE_METHOD,
            'clock': 'Explicit libavformat packet-arrival UTC after WGC/lavfi read; compositor origin is unavailable',
            'original_input_time_base': [1, 10000000], 'runtime_input_tbn': rate,
            'original_input_packet_pts_100ns': packets,
            'encoded_frame_original_utc_us': utc_us,
            'first_encoded_frame_utc_us': utc_us[0] if utc_us else None,
            'last_encoded_frame_utc_us': utc_us[-1] if utc_us else None,
            'wgc_relative_time_base': [1, 10000000],
            'wgc_original_relative_pts_100ns': [p for _, p in relative],
            'wgc_source_time_base_verified': source_tb,
            'absolute_compositor_qpc_origin_available': False,
            'input_packet_count': len(packets), 'encoded_frame_count': count,
            'showinfo_source_frame_count': len(relative),
            'extra_prefetched_input_packets': len(packets)-count if enough else None,
            'max_encoded_relative_pts_error_us': max(errors) if errors else None,
            'correspondence': 'Encoded frames map in order to original packet UTC and original relative WGC showinfo frames; no CFR duplication/drop/filter',
            'A_V_sync_proven': False,
            'source_verification': {
                'wgc_frame_and_origin_subtraction': SOURCE_URL + '#L1417-L1457',
                'wgc_time_base': SOURCE_URL + '#L1262',
                'explicit_packet_utc_override': 'https://github.com/FFmpeg/FFmpeg/blob/'+SOURCE_COMMIT+'/libavformat/demux.c#L522',
                'utc_clock': 'https://github.com/FFmpeg/FFmpeg/blob/'+SOURCE_COMMIT+'/libavutil/time.c#L36',
                'system_relative_time': 'https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.direct3d11captureframe.systemrelativetime'},
            'limitations': [
                'The stock filter subtracts its private first compositor QPC value. External QPC/UTC pairs cannot reconstruct that missing origin.',
                'Packet UTC measures arrival after WGC acquisition and readback. Unknown compositor queue, GPU/readback and audio-render latency are excluded from arithmetic bounds.',
                'Microsecond UTC units do not establish microsecond precision. Original relative WGC PTS and measured system/precise UTC differences remain available.',
                'Actual changed-image and audio/video content review is required; clock/count success cannot prove live content or perceptual sync.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window-evidence', required=True, type=Path)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    parser.add_argument('--max-framerate', type=int, default=30, metavar='1..120',
                        help='Requested WGC maximum capture rate; actual original timestamps determine cadence')
    parser.add_argument('--codec', choices=['ffv1', 'h264_rgb_lossless'], default='ffv1',
                        help='Lossless RGB storage codec; original frame timestamps are preserved')
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.max_framerate <= 120:
        parser.error('--max-framerate must be an integer from 1 through 120')
    require(os.name == 'nt' and 0 < args.seconds <= 1800, 'Native Windows/bounded duration required')
    manifest = json.loads((TOOLS/'manifest.json').read_text())
    require(manifest.get('success'), 'Verified private FFmpeg manifest required')
    exes = {}
    for name in ['ffmpeg', 'ffprobe']:
        path = Path(manifest['executables'][name]['path']).resolve()
        require(path.is_relative_to(TOOLS) and path.is_file() and sha(path) == manifest['executables'][name]['sha256'], 'Private executable changed')
        exes[name] = path
    row, hwnd = evidence(args.window_evidence)
    image = row.get('computer_use_window', {}).get('app', '')
    require(image.startswith('process:') and row.get('native_handle_source'), 'Actual computer-use process path and independent native HWND source required')
    actual_image = native_image(int(row['process_id']))
    require(os.path.normcase(actual_image) == os.path.normcase(str(Path(image[8:]).resolve())), 'Capture native process image changed')
    dimensions = [args.width, args.height]
    before = observe(hwnd)
    require(not mismatch(row, before, dimensions), 'Window preflight: '+ '; '.join(mismatch(row, before, dimensions)))
    capability = subprocess.run([str(exes['ffmpeg']), '-hide_banner', '-h', 'filter=gfxcapture'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    help_text = capability.stdout + capability.stderr
    require(capability.returncode == 0 and all(option in help_text for option in ['hwnd', 'capture_cursor', 'capture_border', 'max_framerate', 'bgra']), 'Verified installed WGC filter unavailable; no desktop fallback')
    encoder_help = ''
    if args.codec == 'h264_rgb_lossless':
        encoder_capability = subprocess.run([str(exes['ffmpeg']), '-hide_banner', '-h', 'encoder=libx264rgb'],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        encoder_help = encoder_capability.stdout + encoder_capability.stderr
        require(encoder_capability.returncode == 0 and 'Encoder libx264rgb' in encoder_help and
                re.search(r'Supported pixel formats:[^\n]*\bbgr0\b', encoder_help),
                'Verified installed lossless RGB encoder unavailable; no codec fallback')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    folder = ROOT/'output/wgc_gameplay_takes'/stamp
    raw = folder/('REALTIME_WGC_WINDOW_RAW_FFV1.nut' if args.codec == 'ffv1' else
                 'REALTIME_WGC_WINDOW_RAW_H264_RGB_LOSSLESS.nut')
    graph = 'gfxcapture=hwnd=%d:capture_cursor=false:capture_border=false:max_framerate=%d:output_fmt=bgra,hwdownload,format=bgra,showinfo' % (hwnd, args.max_framerate)
    codec_options = (['-c:v', 'ffv1', '-level', '3', '-g', '1', '-pix_fmt', 'bgra'] if args.codec == 'ffv1' else
                     ['-c:v', 'libx264rgb', '-preset', 'ultrafast', '-crf', '0', '-tune', 'zerolatency',
                      '-g', '60', '-bf', '0', '-pix_fmt', 'bgr0'])
    command = [str(exes['ffmpeg']), '-hide_banner', '-nostdin', '-n', '-debug_ts', '-loglevel', 'verbose',
               '-copyts', '-start_at_zero', '-use_wallclock_as_timestamps', '1', '-f', 'lavfi', '-i', graph,
               '-t', str(args.seconds), '-an'] + codec_options + [
               '-enc_time_base:v', '1:10000000', '-fps_mode:v', 'passthrough', '-f', 'nut', str(raw)]
    probe_timeout = min(1800, max(300, args.seconds * 4 + 60))
    plan = {'scope': 'Actual bound game HWND-only WGC video; no input/audio/desktop capture/game-state changes',
            'capture_method': CAPTURE_METHOD, 'evidence': row, 'evidence_sha256': sha(args.window_evidence),
            'preflight': before, 'process_image': actual_image, 'command': command, 'raw_video': str(raw),
            'recorder_source_sha256': sha(__file__), 'ffmpeg_sha256': sha(exes['ffmpeg']),
            'capture_cursor': False, 'capture_border': False, 'monitor_capture': False,
            'recorded': False, 'content_review_required': True, 'S07_proven': False,
            'A_V_sync_proven': False, 'capture_rate_is_only_maximum_request': True,
            'requested_max_framerate': args.max_framerate,
            'requested_storage_codec': args.codec, 'lossless_rgb_storage': True,
            'alpha_channel_preserved': args.codec == 'ffv1',
            'probe_decoder_threads': 8, 'probe_timeout_seconds': probe_timeout,
            'no_frame_duplication_interpolation_or_rate_filter': True,
            'timestamp_policy': 'Preserve relative nativeWGC showinfo PTS and explicit packet-arrival UTC; fine encoder timebase avoids nominal-rate quantization. No compositor-origin guess.',
            'limitations': ['WGC content must be compared with actual changed game observations.',
                            'The requested maximum capture rate is not proof of actual CFR or game FPS.',
                            'H264 RGB lossless storage omits the unused alpha channel; RGB values are lossless.',
                            'Packet-arrival clocks exclude unknown compositor/readback/audio-render latency.',
                            'No audio in this video; separate process-only capture and actual sync review required.']}
    if not args.record:
        print(json.dumps(plan, indent=2)); return 0
    folder.mkdir(parents=True)
    (folder/'actual_filter_capability.txt').write_text(help_text)
    if encoder_help:
        (folder/'actual_encoder_capability.txt').write_text(encoder_help)
    report_path = folder/'capture_report.json'
    report = dict(plan, success=False, recorded=True, started_utc=utc(), samples=[])
    clock = NativeClock()
    report.update(qpc_frequency=clock.frequency, clock_pairs=[clock.pair('before_owned_ffmpeg_start')])
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    start = time.perf_counter()
    with (folder/'ffmpeg.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        timed_out = False
        while process.poll() is None:
            if time.perf_counter()-start > args.seconds+30:
                timed_out = True; process.terminate(); process.wait(timeout=10); break
            sample = {'utc': utc(), 'invalid_reasons': []}
            try:
                sample = observe(hwnd); sample['invalid_reasons'] = mismatch(row, sample, dimensions)
            except Exception as error:
                sample['invalid_reasons'] = [str(error)]
            sample['elapsed_wall_seconds'] = time.perf_counter()-start
            report['samples'].append(sample)
            report['clock_pairs'].append(clock.pair('window_monitor_sample'))
            time.sleep(.25)
        report.update(returncode=process.returncode, wall_timeout=timed_out)
    report['clock_pairs'].append(clock.pair('after_owned_ffmpeg_exit'))
    report.update(ended_utc=utc(), process_wall_seconds=time.perf_counter()-start)
    report['window_state_violations'] = [s for s in report['samples'] if s['invalid_reasons']]
    if raw.is_file():
        report.update(raw_sha256=sha(raw), raw_bytes=raw.stat().st_size)
        probe_command = [str(exes['ffprobe']), '-v', 'error', '-threads', '8', '-count_frames', '-show_streams', '-show_format', '-show_frames',
            '-show_entries', 'frame=best_effort_timestamp,best_effort_timestamp_time,duration_time:stream:format', '-of', 'json', str(raw)]
        report['probe_command'] = probe_command
        try:
            inspect = subprocess.run(probe_command, capture_output=True, text=True, timeout=probe_timeout,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired as error:
            report.update(probe_timed_out=True, probe_error=str(error), success=False)
            report_path.write_text(json.dumps(report, indent=2)+'\n')
            raise
        (folder/'ffprobe.json').write_text(inspect.stdout); (folder/'ffprobe_errors.log').write_text(inspect.stderr)
        report['ffprobe_returncode'] = inspect.returncode
        if inspect.returncode == 0:
            data = json.loads(inspect.stdout)
            streams = [s for s in data['streams'] if s['codec_type'] == 'video']
            report['actual_dimensions_validated'] = len(streams) == 1 and [streams[0]['width'], streams[0]['height']] == dimensions
            report['actual_codec_validated'] = len(streams) == 1 and streams[0]['codec_name'] == ('ffv1' if args.codec == 'ffv1' else 'h264')
            points = [float(f['best_effort_timestamp_time']) for f in data['frames'] if 'best_effort_timestamp_time' in f]
            gaps = [b-a for a,b in zip(points, points[1:])]
            report['capture_cadence'] = {'timestamped_frames': len(points), 'first_pts': points[0] if points else None,
                'last_pts': points[-1] if points else None, 'pts_strictly_increasing': bool(gaps) and all(g>0 for g in gaps),
                'max_gap_seconds': max(gaps) if gaps else None, 'gaps_over_50ms': sum(g>.05 for g in gaps), 'game_render_FPS_proven': False}
            log_path = folder/'ffmpeg.log'
            report['native_input_clock'] = input_clock(log_path.read_text(encoding='utf-8', errors='replace'), points, report['started_utc'], report['ended_utc'])
            report['clock_metadata_validated'] = report['native_input_clock']['success']
            report['raw_debug_log'] = {'path': str(log_path), 'sha256': sha(log_path)}
    report['success'] = (report['returncode'] == 0 and not report['wall_timeout'] and report.get('ffprobe_returncode') == 0 and
        report.get('actual_dimensions_validated') and report.get('actual_codec_validated') and
        not report['window_state_violations'] and report.get('clock_metadata_validated'))
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    print(str(report_path))
    require(report['success'], 'WGC/format/clock capture failed; preserve actual partial files/logs; no fallback')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
