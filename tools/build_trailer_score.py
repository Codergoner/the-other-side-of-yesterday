"""Original score for the competition trailer, synthesized from sine partials and noise (no samples, no third-party audio).

Run with Blender's bundled Python (it has numpy):
  python.exe -I tools/build_trailer_score.py --jump 46 --end 95 --out output/trailer_edit/score.wav

Structure (seconds; one beat per second, D minor turning to F major at the jump):
  0 .. A      sparse bell motif over a low drone (the ruined present)
  A .. jump   warm pad joins, a slow pulse builds toward the jump
  jump        swell and a soft noise wash, then the major lift (the city alive)
  .. end      reprise, final cadence, fade
The coastal beds of the game (output/release_audio, original procedural audio) are mixed underneath: Present before
the jump, Past after it. Nobody has listened to this file: the report records signal measurements only.
"""
import argparse
import json
import wave
from pathlib import Path

import numpy as np

SR = 48000
ROOT = Path(__file__).resolve().parents[1]


def hz(note):
    """MIDI note number to frequency."""
    return 440.0 * 2 ** ((note - 69) / 12.0)


def place(buffer, start, signal, pan=0.0, gain=1.0):
    i = int(start * SR)
    if i >= buffer.shape[0]:
        return
    n = min(len(signal), buffer.shape[0] - i)
    left, right = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buffer[i:i + n, 0] += signal[:n] * gain * left
    buffer[i:i + n, 1] += signal[:n] * gain * right


def bell(freq, seconds=6.0, brightness=1.0):
    t = np.arange(int(seconds * SR)) / SR
    out = np.zeros_like(t)
    for ratio, amp, decay in [(1.0, 1.0, 1.6), (2.0, 0.5, 1.1), (3.01, 0.28 * brightness, 0.7), (4.2, 0.16 * brightness, 0.45), (5.43, 0.09 * brightness, 0.3)]:
        out += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t / decay)
    attack = np.minimum(1.0, t / 0.006)
    return out * attack


def pad(freqs, seconds, attack=1.6, release=2.2, detune=0.004):
    t = np.arange(int((seconds + release) * SR)) / SR
    out = np.zeros((len(t), 2))
    for f in freqs:
        for side, d in [(0, -detune), (1, detune)]:
            voice = np.zeros_like(t)
            for h in range(1, 7):
                voice += (1.0 / h ** 1.6) * np.sin(2 * np.pi * f * (1 + d) * h * t + h * 0.7 * side)
            out[:, side] += voice
    env = np.minimum(1.0, t / attack) * np.where(t > seconds, np.maximum(0.0, 1 - (t - seconds) / release), 1.0)
    slow = 1.0 + 0.06 * np.sin(2 * np.pi * 0.21 * t)
    return out * (env * slow)[:, None] / max(1, len(freqs))


def reverb(dry, seconds=3.2, mix=0.42, seed=7):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    wet = np.zeros_like(dry)
    size = dry.shape[0] + n
    for ch in range(2):
        ir = rng.standard_normal(n) * np.exp(-t / (seconds / 4.5))
        # darken the tail: one-pole low-pass on the impulse response
        for _ in range(2):
            ir = np.convolve(ir, np.ones(24) / 24, mode='same')
        ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
        spectrum = np.fft.rfft(dry[:, ch], size) * np.fft.rfft(ir, size)
        wet[:, ch] = np.fft.irfft(spectrum, size)[:dry.shape[0]]
    return dry * (1 - mix * 0.4) + wet * mix


def read_wav(path):
    with wave.open(str(path), 'rb') as w:
        assert w.getframerate() == SR and w.getnchannels() == 2 and w.getsampwidth() == 2
        data = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').reshape(-1, 2).astype(np.float64) / 32768.0
    return data


def loop_to(data, seconds):
    n = int(seconds * SR)
    reps = int(np.ceil(n / data.shape[0]))
    return np.tile(data, (reps, 1))[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jump', type=float, default=46.0)
    ap.add_argument('--end', type=float, default=95.0)
    ap.add_argument('--pad-in', type=float, default=14.0)
    ap.add_argument('--out', default='output/trailer_edit/score.wav')
    # Optional second turn (15 November 2026, the longer cut): the return to the present. From here the bells thin out
    # and drop an octave, the pad eases, a softer wash marks the moment and the coastal bed goes back to the present.
    ap.add_argument('--return-at', type=float, default=None)
    args = ap.parse_args()
    total = args.end + 4.0
    music = np.zeros((int(total * SR), 2))
    D2, A2, D3, F3, A3, Bb2, C3, F2, C4, D4, E4, F4, G4, A4, Bb3, C5, D5, F5, A5 = 38, 45, 50, 53, 57, 46, 48, 41, 60, 62, 64, 65, 67, 69, 58, 72, 74, 77, 81

    # Low drone under everything before the jump.
    t = np.arange(int((args.jump + 2) * SR)) / SR
    drone = (np.sin(2 * np.pi * hz(D2) * t) + 0.5 * np.sin(2 * np.pi * hz(D2) * 2 * t) + 0.3 * np.sin(2 * np.pi * hz(A2) * t))
    drone *= np.minimum(1.0, t / 4.0) * np.minimum(1.0, (args.jump + 2 - t) / 2.0) * (1 + 0.08 * np.sin(2 * np.pi * 0.13 * t))
    place(music, 0, drone, 0.0, 0.10)

    # Bell motif in D minor: a falling, questioning figure, one phrase every 8 seconds.
    minor_phrase = [(0.0, A4), (1.0, F4), (2.0, D4), (3.5, E4), (5.0, F4), (6.0, D4)]
    start = 1.0
    index = 0
    while start + 7 < args.jump - 4:
        for offset, note in minor_phrase:
            lift = 12 if index % 2 == 1 and offset >= 3.5 else 0
            place(music, start + offset, bell(hz(note + lift), 6.0, 0.8), -0.25 + 0.5 * ((offset * 3) % 1), 0.20)
        start += 8.0
        index += 1

    # Pad: Dm - Bb - F - C, four seconds each, from pad-in to the jump, growing.
    minor_chords = [[D3, F3, A3], [Bb2, D3, F3], [F2, A2 + 12, C4], [C3, E4 - 12, G4 - 12]]
    start = args.pad_in
    k = 0
    while start < args.jump - 0.5:
        length = min(4.0, args.jump - start)
        growth = 0.35 + 0.65 * (start - args.pad_in) / max(1.0, args.jump - args.pad_in)
        place_stereo = pad([hz(n) for n in minor_chords[k % 4]], length)
        i = int(start * SR)
        n = min(len(place_stereo), music.shape[0] - i)
        music[i:i + n] += place_stereo[:n] * 0.22 * growth
        start += 4.0
        k += 1

    # Slow pulse (a low heartbeat) for the last ten seconds before the jump.
    for beat in np.arange(max(args.pad_in, args.jump - 10.0), args.jump - 0.4, 1.0):
        tt = np.arange(int(0.5 * SR)) / SR
        thump = np.sin(2 * np.pi * (58 - 18 * tt) * tt) * np.exp(-tt / 0.12)
        place(music, beat, thump, 0.0, 0.16 + 0.02 * (beat - (args.jump - 10.0)))

    # The jump: rising swell into a soft noise wash.
    rise = 3.0
    tt = np.arange(int(rise * SR)) / SR
    sweep = np.sin(2 * np.pi * (hz(D3) * tt + (hz(D4) - hz(D3)) * tt ** 2 / (2 * rise))) * (tt / rise) ** 2
    place(music, args.jump - rise, sweep, 0.0, 0.16)
    rng = np.random.default_rng(11)
    tt = np.arange(int(4.0 * SR)) / SR
    wash = rng.standard_normal(len(tt))
    for _ in range(3):
        wash = np.convolve(wash, np.ones(40) / 40, mode='same')
    wash *= np.exp(-tt / 1.1) * np.minimum(1.0, tt / 0.03)
    place(music, args.jump, wash / (np.max(np.abs(wash)) + 1e-9), 0.0, 0.20)

    # After the jump: F - C - Dm - Bb in a brighter register, bells an octave up, a full pad.
    major_chords = [[F3, A3, C4], [C3 + 12 - 12, E4 - 12, G4 - 12, C4], [D3, F3, A3, D4], [Bb2, D3, F3, Bb3]]
    start = args.jump + 0.5
    k = 0
    while start < args.end - 9:
        length = min(4.0, args.end - 9 - start)
        chord = pad([hz(n) for n in major_chords[k % 4]], length, attack=0.9)
        i = int(start * SR)
        n = min(len(chord), music.shape[0] - i)
        back = args.return_at is not None and start >= args.return_at - 0.5
        music[i:i + n] += chord[:n] * (0.24 if back else 0.30)
        arp = [F4, A4, C5, F5] if k % 4 == 0 else [E4, G4, C5, E4 + 12] if k % 4 == 1 else [D4, F4, A4, D5] if k % 4 == 2 else [D4, F4, Bb3 + 12, D5]
        for j, note in enumerate(arp):
            if back and j % 2 == 1:
                continue
            if start + j < args.end - 9:
                place(music, start + j, bell(hz(note - (12 if back else 0)), 5.0, 0.8 if back else 1.0), -0.4 + 0.27 * j, 0.17)
        start += 4.0
        k += 1
    if args.return_at is not None:
        place(music, args.return_at, wash / (np.max(np.abs(wash)) + 1e-9), 0.0, 0.11)

    # Final cadence: Bb - C - D (major), a last bell, fade.
    for offset, chord, length in [(args.end - 9, [Bb2, D3, F3, Bb3], 3.0), (args.end - 6, [C3, E4 - 12, G4 - 12, C4], 3.0), (args.end - 3, [D3, A3, D4, 66], 5.5)]:
        voice = pad([hz(n) for n in chord], length, attack=0.8, release=3.0)
        i = int(offset * SR)
        n = min(len(voice), music.shape[0] - i)
        music[i:i + n] += voice[:n] * 0.28
    for offset, note in [(args.end - 3.0, A4), (args.end - 2.0, 66 + 12), (args.end - 1.0, D5), (args.end, A5)]:
        place(music, offset, bell(hz(note), 6.0, 0.9), 0.0, 0.2)

    music = reverb(music)
    # Coastal beds of the game underneath.
    audio = ROOT / 'output' / 'release_audio'
    present = loop_to(read_wav(audio / 'Amb_Coast_Present_60s.wav'), total)
    past = loop_to(read_wav(audio / 'Amb_Coast_Past_60s.wav'), total)
    tt = np.arange(music.shape[0]) / SR
    cross = np.clip((tt - (args.jump - 0.5)) / 2.0, 0.0, 1.0)
    if args.return_at is not None:
        cross = cross * (1.0 - np.clip((tt - (args.return_at - 0.5)) / 2.0, 0.0, 1.0))
    cross = cross[:, None]
    bed = present * (1 - cross) * 0.55 + past * cross * 0.7
    mix = music + bed
    fade_in = np.minimum(1.0, tt / 2.0)
    fade_out = np.clip((total - tt) / 4.0, 0.0, 1.0)
    mix *= (fade_in * fade_out)[:, None]
    peak = float(np.max(np.abs(mix)))
    mix *= 0.89 / peak
    out = (ROOT / args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(np.round(mix * 32767), -32768, 32767).astype('<i2')
    with wave.open(str(out), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    rms = float(np.sqrt(np.mean(mix ** 2)))
    report = {'file': str(out), 'seconds': round(total, 3), 'sample_rate': SR, 'channels': 2, 'jump_seconds': args.jump, 'return_seconds': args.return_at, 'end_seconds': args.end,
              'peak_dbfs': round(20 * np.log10(np.max(np.abs(mix)) + 1e-12), 2), 'rms_dbfs': round(20 * np.log10(rms + 1e-12), 2),
              'provenance': 'Synthesized by tools/build_trailer_score.py from sine partials and noise, plus the game\'s own procedural coastal beds. No third-party audio.',
              'listened_to': False}
    out.with_suffix('.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
