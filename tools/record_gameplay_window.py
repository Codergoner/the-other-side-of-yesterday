"""Opt-in real-time window recorder; never sends input or modifies the game.

Requires a current computer-use observation containing the actual HWND, PID and
title. A caller must supply --record; without it this validates/prints the plan.
The raw FFV1/NUT take keeps capture timestamps and receives no CFR duplication,
retiming, image interpolation, audio replacement, or gameplay test commands.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'output/capture_tools'


def require(test, message):
    if not test:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def observe(hwnd):
    """Read native window state only. There are deliberately no input APIs."""
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.IsWindow.argtypes = [wintypes.HWND]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetForegroundWindow.restype = wintypes.HWND
    require(user.IsWindow(hwnd), 'The observed HWND no longer identifies a window')
    pid, title, rect = wintypes.DWORD(), ctypes.create_unicode_buffer(4096), wintypes.RECT()
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    user.GetWindowTextW(hwnd, title, len(title))
    require(user.GetClientRect(hwnd, ctypes.byref(rect)), 'GetClientRect failed')
    return {'utc': utc(), 'process_id': int(pid.value), 'title': title.value,
            'client_size': [rect.right - rect.left, rect.bottom - rect.top],
            'visible': bool(user.IsWindowVisible(hwnd)), 'minimized': bool(user.IsIconic(hwnd)),
            'foreground': int(user.GetForegroundWindow() or 0) == hwnd}


def evidence(path):
    row = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    require(row.get('source') == 'computer-use', 'Evidence must come from the actual computer-use window observation')
    require(row.get('observation_reference'), 'Keep the original computer-use observation reference')
    raw = row.get('hwnd')
    hwnd = int(raw, 0) if isinstance(raw, str) else int(raw)
    require(hwnd > 0 and int(row['process_id']) > 0 and row.get('title'), 'HWND, PID and actual title are required')
    when = datetime.fromisoformat(row['observed_at_utc'].replace('Z', '+00:00'))
    require(when.tzinfo is not None, 'Observation timestamp must contain its timezone')
    require(0 <= (datetime.now(timezone.utc) - when).total_seconds() < 900,
            'Re-observe the actual game window: evidence is older than 15 minutes')
    return row, hwnd


def mismatch(row, observed, dimensions):
    return [reason for ok, reason in [
        (observed['process_id'] == int(row['process_id']), 'window PID changed'),
        (observed['title'] == row['title'], 'window title changed'),
        (observed['client_size'] == dimensions, 'client dimensions changed'),
        (observed['visible'], 'window was hidden'), (not observed['minimized'], 'window was minimized'),
        (observed['foreground'], 'window lost foreground')
    ] if not ok]


def input_clock(log_text, frame_pts, started_utc, ended_utc):
    """Recover original integer gdigrab UTC packet PTS before tsfixup.

    Pinned FFmpeg946fcce07b gdigrab.c sets its input time base to1/1e6.
    With the explicit use_wallclock_as_timestamps option, libavformat replaces
    packet PTS with av_gettime after read_packet. The CLI `demuxer ->` line is
    BEFORE ts_offset/start_at_zero. Decimal pkt_pts_time is unused.
    Runtime input tbn and encoded-frame correspondence still must validate.
    """
    input_block = re.search(r'Input #0, gdigrab,[\s\S]*?(?=Stream mapping:|Output #0,|$)',log_text)
    tbn = re.search(r'\b([0-9.]+)([kMG]?) tbn\b',input_block.group(0)) if input_block else None
    scale = {'':1,'k':1000,'M':1000000,'G':1000000000}
    clock_rate = float(tbn.group(1))*scale[tbn.group(2)] if tbn else None
    original = [int(value) for value in re.findall(r'(?<![+\w])demuxer -> ist_index:0:0 type:video\s+pkt_pts:(-?\d+)\b',log_text)]
    count = len(frame_pts)
    enough = count > 1 and len(original) >= count
    selected = original[:count] if enough else []
    errors = [abs((packet-selected[0])-(point-frame_pts[0])*1000000)
              for packet,point in zip(selected,frame_pts)] if enough else []
    first_epoch = datetime.fromisoformat(started_utc).timestamp()*1000000
    last_epoch = datetime.fromisoformat(ended_utc).timestamp()*1000000
    valid = (clock_rate == 1000000 and enough and
             all(b > a for a,b in zip(selected,selected[1:])) and
             all(abs(error) <= 17000 for error in errors) and
             first_epoch-2000000 <= selected[0] <= last_epoch+2000000 and
             first_epoch-2000000 <= selected[-1] <= last_epoch+2000000)
    return {'success':bool(valid),'clock':'UTC Unix epoch microseconds; units are not a claim of clock precision',
        'original_input_time_base':[1,1000000],'runtime_input_tbn':clock_rate,
        'packet_clock_stage':'libavformat UTC override after gdigrab read_packet, before CLI start offset; use_wallclock_as_timestamps=1',
        'original_input_packet_pts_us':original,'encoded_frame_original_utc_us':selected,
        'first_encoded_frame_utc_us':selected[0] if selected else None,
        'last_encoded_frame_utc_us':selected[-1] if selected else None,
        'input_packet_count':len(original),'encoded_frame_count':count,
        'extra_prefetched_input_packets':len(original)-count if enough else None,
        'max_encoded_relative_pts_error_us':max(errors) if errors else None,
        'correspondence':'Every encoded frame matched in order to an original input packet; nominal encoder time-base quantization may differ by at most half a30Hz frame',
        'source_verification':{
            'commit':'946fcce07b',
            'gdigrab':'https://github.com/FFmpeg/FFmpeg/blob/946fcce07b/libavdevice/gdigrab.c#L416',
            'packet_pts':'https://github.com/FFmpeg/FFmpeg/blob/946fcce07b/libavdevice/gdigrab.c#L577',
            'explicit_wallclock_override':'https://github.com/FFmpeg/FFmpeg/blob/946fcce07b/libavformat/demux.c#L522',
            'pre_offset_debug':'https://github.com/FFmpeg/FFmpeg/blob/946fcce07b/fftools/ffmpeg_demux.c#L367',
            'utc_clock':'https://github.com/FFmpeg/FFmpeg/blob/946fcce07b/libavutil/time.c#L36'},
        'A_V_sync_proven':False,'limitations':['A measured audio QPC/UTC pair and packet clock are still required.',
            'The explicit wallclock timestamp follows GDI packet read; unknown pixel-copy/game-present/audio-render latency still requires actual sync review.',
            'Original raw stderr and all integer packet PTS remain preserved.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window-evidence', required=True, type=Path)
    parser.add_argument('--seconds', type=float, default=30.0)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    parser.add_argument('--record', action='store_true', help='Actually capture after validating the current window')
    args = parser.parse_args()
    require(os.name == 'nt', 'Native Windows recorder only')
    require(0 < args.seconds <= 1800, 'Duration must be within 0–1800 seconds')
    manifest = json.loads((TOOLS / 'manifest.json').read_text())
    require(manifest.get('success'), 'Verified private recorder manifest required')
    exe, probe = Path(manifest['executables']['ffmpeg']['path']), Path(manifest['executables']['ffprobe']['path'])
    for name, path in [('ffmpeg', exe), ('ffprobe', probe)]:
        require(path.is_file() and path.is_relative_to(TOOLS), 'Executable must remain inside the private capture-tools folder')
        require(sha(path) == manifest['executables'][name]['sha256'], 'Private executable changed since verification')
    row, hwnd = evidence(args.window_evidence)
    dimensions = [args.width, args.height]
    before = observe(hwnd)
    require(not mismatch(row, before, dimensions), 'Window preflight: ' + '; '.join(mismatch(row, before, dimensions)))
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    folder = ROOT / 'output/gameplay_takes' / run
    raw_file = folder / 'REALTIME_WINDOW_RAW_FFV1.nut'
    command = [str(exe), '-hide_banner', '-nostdin', '-y', '-debug_ts', '-loglevel', 'verbose', '-copyts', '-start_at_zero',
        '-use_wallclock_as_timestamps', '1', '-f', 'gdigrab', '-framerate', '30',
        '-draw_mouse', '0', '-i', 'hwnd=' + str(hwnd), '-t', str(args.seconds),
        '-an', '-c:v', 'ffv1', '-level', '3', '-g', '1', '-pix_fmt', 'bgr0',
        '-fps_mode', 'passthrough', '-f', 'nut', str(raw_file)]
    plan = {'scope': 'External real-time video recording; no input controls, game state changes or FPS claim',
        'evidence': row, 'evidence_sha256': sha(args.window_evidence), 'preflight': before,
        'command': command, 'raw_video': str(raw_file), 'audio_recorded': False,
        'timestamp_policy': 'Original integer gdigrab UTC packet PTS retained from pre-offset debug_ts; raw NUT retains normalized encoded PTS. No duplication, interpolation or speed change.',
        'recorder_source_sha256':sha(__file__),
        'limitations': ['GDI may fail or show black/occluded content; inspect a real game smoke take first.',
            'Foreground checks do not prove absence of overlays or content occlusion.',
            '30 Hz capture cadence does not establish game render rate.',
            'No game audio in this take; separate authorized process-specific loopback recording is required.']}
    if not args.record:
        print(json.dumps(plan, indent=2))
        return
    folder.mkdir(parents=True)
    report_path = folder / 'capture_report.json'
    report = dict(plan, success=False, started_utc=utc(), samples=[], recorded=True)
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    start = time.perf_counter()
    with (folder / 'ffmpeg.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        while process.poll() is None:
            try:
                sample = observe(hwnd)
                sample['elapsed_wall_seconds'] = time.perf_counter() - start
                sample['invalid_reasons'] = mismatch(row, sample, dimensions)
            except Exception as exc:
                sample = {'utc': utc(), 'invalid_reasons': [str(exc)]}
            report['samples'].append(sample)
            time.sleep(0.25)
        report['returncode'] = process.returncode
    report['ended_utc'], report['process_wall_seconds'] = utc(), time.perf_counter() - start
    report['window_state_violations'] = [s for s in report['samples'] if s['invalid_reasons']]
    if raw_file.is_file():
        report['raw_sha256'], report['raw_bytes'] = sha(raw_file), raw_file.stat().st_size
        inspect = subprocess.run([str(probe), '-v', 'error', '-count_frames', '-show_streams', '-show_format',
            '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time,duration_time:stream:format',
            '-of', 'json', str(raw_file)], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        (folder / 'ffprobe.json').write_text(inspect.stdout)
        (folder / 'ffprobe_errors.log').write_text(inspect.stderr)
        report['ffprobe_returncode'] = inspect.returncode
        if inspect.returncode == 0:
            parsed = json.loads(inspect.stdout)
            points = [float(f['best_effort_timestamp_time']) for f in parsed.get('frames', [])
                      if 'best_effort_timestamp_time' in f]
            deltas = [b - a for a, b in zip(points, points[1:])]
            report['capture_cadence'] = {'timestamped_frames': len(points),
                'first_pts': points[0] if points else None, 'last_pts': points[-1] if points else None,
                'pts_strictly_increasing': bool(deltas) and all(d > 0 for d in deltas),
                'max_gap_seconds': max(deltas) if deltas else None,
                'gaps_over_60ms': sum(d > 0.060 for d in deltas), 'game_render_FPS_proven': False}
            log_path = folder / 'ffmpeg.log'
            report['native_input_clock'] = input_clock(log_path.read_text(encoding='utf-8',errors='replace'),points,report['started_utc'],report['ended_utc'])
            report['clock_metadata_validated'] = report['native_input_clock']['success']
            report['raw_debug_log'] = {'path':str(log_path),'sha256':sha(log_path)}
    report['success'] = (report['returncode'] == 0 and report.get('ffprobe_returncode') == 0
                         and not report['window_state_violations'])
    report['content_review_required'] = True
    report['S07_proven'] = False  # Requires actual human-input/content/audio review, never inferred by this recorder.
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(str(report_path))
    require(report['success'], 'Recorder or window preflight failed; retain the raw take and report for diagnosis')


if __name__ == '__main__':
    main()
