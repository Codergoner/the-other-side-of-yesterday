"""Opt-in process-tree-only game audio; no screen capture or input controls.

Uses current computer-use window evidence with a read-only native HWND/PID/path
binding. An opaque computer-use window identifier is never assumed to be an HWND.
Without --record, validates/prints the plan and never activates WASAPI.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import record_gameplay_window as window
PRIVATE = ROOT / 'output/capture_tools/application_loopback'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window-evidence', required=True, type=Path)
    parser.add_argument('--seconds', type=float, default=30.0)
    parser.add_argument('--record', action='store_true', help='Actually activate only this observed game process tree')
    args = parser.parse_args()
    window.require(os.name == 'nt' and 0 < args.seconds <= 1800, 'Native Windows/bounded duration required')
    row, hwnd = window.evidence(args.window_evidence)
    observed = window.observe(hwnd)
    window.require(observed['process_id'] == row['process_id'] and observed['title'] == row['title'], 'Observed native HWND/PID/title binding changed')
    source_app = row.get('computer_use_window', {}).get('app', '')
    window.require(source_app.startswith('process:'), 'Actual computer-use observation must include the exact game process image path')
    image = Path(source_app[len('process:'):]).resolve()
    window.require(image.is_file() and image.suffix.lower() == '.exe', 'Observed game executable path is missing')
    window.require(row.get('native_handle_source'), 'Preserve how the native HWND was obtained separately from the opaque computer-use identifier')
    manifest_path = PRIVATE / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    exe = Path(manifest['executable']).resolve()
    window.require(manifest['success'] and exe.is_relative_to(PRIVATE) and exe.is_file()
                   and window.sha(exe) == manifest['executable_sha256'], 'Verified private process-only audio recorder required')
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    folder = ROOT / 'output/game_audio_takes' / run
    wav = folder / 'GAME_ONLY_PROCESS_TREE_RAW.wav'
    command = [str(exe), '--capture', '--pid', str(row['process_id']), '--hwnd', str(hwnd),
               '--image', str(image), '--title', row['title'], '--seconds', str(args.seconds),
               '--output', str(wav), '--evidence', str(args.window_evidence.resolve())]
    plan = {'scope': 'External game-process-tree-only audio recording; no input, microphone, desktop mix or game-state changes',
        'evidence': row, 'evidence_sha256': window.sha(args.window_evidence), 'preflight': observed,
        'process_image': str(image), 'command': command, 'mode': 'INCLUDE_TARGET_PROCESS_TREE_ONLY',
        'recorder_manifest_sha256': window.sha(manifest_path), 'microphone': False, 'desktop_mix': False,
        'synthetic_audio': False, 'requested_format': {'sample_rate': 48000, 'channels': 2, 'bits': 16, 'encoding': 'PCM'},
        'actual_capture_format_validated': False, 'recorded': False,
        'limitations': ['A process without a playing render stream may legitimately produce native silence.',
            'API initialization/permission failure stops the take; no system-loopback fallback exists.',
            'Packet QPC/UTC metadata must be aligned with actual video clocks; this does not establish A/V sync.']}
    if not args.record:
        print(json.dumps(plan, indent=2))
        return
    folder.mkdir(parents=True)
    report = dict(plan, success=False, recorded=True, started_utc=window.utc())
    path = folder / 'capture_report.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    result = subprocess.run(command, capture_output=True, text=True, timeout=args.seconds + 30,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    (folder / 'native_stdout.log').write_text(result.stdout)
    (folder / 'native_stderr.log').write_text(result.stderr)
    report.update(returncode=result.returncode, ended_utc=window.utc())
    native_path = wav.with_suffix('.capture.json')
    if native_path.is_file():
        native = json.loads(native_path.read_text())
        report['native_report'] = {'path': str(native_path), 'sha256': window.sha(native_path), 'actual': native}
    if wav.is_file():
        report['wav_path'], report['wav_sha256'], report['wav_bytes'] = str(wav), window.sha(wav), wav.stat().st_size
        try:
            with wave.open(str(wav), 'rb') as audio:
                actual = {'sample_rate': audio.getframerate(), 'channels': audio.getnchannels(),
                    'sample_width_bytes': audio.getsampwidth(), 'frames': audio.getnframes(), 'compression': audio.getcomptype()}
                actual['duration_seconds'] = actual['frames'] / actual['sample_rate']
            report['independent_wav_readback'] = actual
            report['actual_capture_format_validated'] = (actual['sample_rate'] == 48000 and actual['channels'] == 2
                and actual['sample_width_bytes'] == 2 and actual['compression'] == 'NONE' and actual['frames'] > 0)
        except Exception as exc:
            report['wav_readback_error'] = str(exc)
    native = report.get('native_report', {}).get('actual', {})
    packet_path = wav.with_suffix('.packets.csv')
    if packet_path.is_file():
        report['packet_clock_log'] = {'path':str(packet_path),'sha256':window.sha(packet_path)}
    report['paired_clock_metadata_available'] = (len(native.get('clock_pairs',[])) >= 2 and
        native.get('qpc_frequency',0) > 0 and bool(report.get('packet_clock_log')))
    report['audible_signal_detected'] = bool(native.get('actual_peak_pcm16', 0) > 0)
    report['success'] = (result.returncode == 0 and native.get('success', False) and report['actual_capture_format_validated'])
    report['A_V_sync_proven'], report['S07_proven'] = False, False
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(str(path))
    window.require(report['success'], 'Game-only capture/format validation failed; retain actual logs/partial artifacts')


if __name__ == '__main__':
    main()
