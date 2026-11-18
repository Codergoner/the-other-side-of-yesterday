"""Author original deterministic PCM sound designs; no Unreal import or writes.

Run with local Python + NumPy. Every noise field and event is synthesized here;
there are no recordings, voices, downloaded samples, or borrowed music. These
are sound-design source assets awaiting actual listening and runtime mix review.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import wave

import numpy as np

RELEASE = Path(__file__).resolve().parents[2]
OUTPUT = RELEASE / 'output' / 'release_audio'
RATE = 48000
SEED = 20261026
VERSION = 'original_coastal_v1'


def db(value):
    return round(20.0 * math.log10(max(float(value), 1e-12)), 4)


def field(seconds, seed, low, high, slope=0.0):
    """Periodic, soft band-limited random field; endpoints are adjacent samples.

    Filtering is performed in the frequency domain, with no playback filter
    state or nonperiodic convolution tail. All fields contain an exact integer
    number of DFT cycles over the authored duration.
    """
    count = round(RATE * seconds)
    rng = np.random.default_rng(seed)
    frequencies = np.fft.rfftfreq(count, 1.0 / RATE)
    spectrum = np.fft.rfft(rng.standard_normal(count, dtype=np.float32))
    rollin = np.minimum(1.0, (frequencies / max(low, .01)) ** 3)
    rolloff = 1.0 / (1.0 + (frequencies / high) ** 8)
    shape = rollin * rolloff / np.maximum(frequencies, low) ** slope
    spectrum *= shape
    spectrum[0] = 0
    # Remove high frequency hash. Noise is never used as an unfiltered track.
    spectrum[frequencies > min(11000, high * 3)] = 0
    signal = np.fft.irfft(spectrum, n=count).astype(np.float32)
    signal /= max(float(np.std(signal, dtype=np.float64)), 1e-8)
    return signal


def periodic_envelope(time, seconds, events):
    envelope = np.zeros_like(time)
    for center, width, gain in events:
        distance = (time - center + seconds * .5) % seconds - seconds * .5
        envelope += gain * np.exp(-.5 * (distance / width) ** 2)
    return envelope


def stereo_field(seconds, seed, low, high, slope=.25, width=.38):
    common = field(seconds, seed, low, high, slope)
    left = field(seconds, seed + 1, low, high, slope)
    right = field(seconds, seed + 2, low, high, slope)
    return np.stack(((1 - width) * common + width * left,
                     (1 - width) * common + width * right), axis=1)


def edge_fades(signal, attack=.012, release=.09):
    signal = np.array(signal, dtype=np.float32, copy=True)
    first = min(len(signal), max(2, round(attack * RATE)))
    last = min(len(signal), max(2, round(release * RATE)))
    signal[:first] *= np.sin(np.linspace(0, math.pi / 2, first))[:, None] ** 2
    signal[-last:] *= np.cos(np.linspace(0, math.pi / 2, last))[:, None] ** 2
    # Exact zero endpoints survive PCM quantization and are useful for one-shots.
    signal[0] = 0
    signal[-1] = 0
    return signal


def tone(seconds, frequency, decay=2.0, pan=0.0, attack=.006):
    time = np.arange(round(seconds * RATE), dtype=np.float64) / RATE
    env = (1 - np.exp(-time / max(attack, 1e-5))) * np.exp(-time * decay)
    mono = (np.sin(2 * math.pi * frequency * time) +
            .19 * np.sin(2 * math.pi * frequency * 2.004 * time) +
            .075 * np.sin(2 * math.pi * frequency * 3.012 * time)) * env
    return np.stack((mono * math.sqrt((1 - pan) / 2),
                     mono * math.sqrt((1 + pan) / 2)), axis=1).astype(np.float32)


def add_event(destination, source, start_seconds, loop=False):
    begin = round(start_seconds * RATE)
    if not loop:
        count = min(len(source), len(destination) - begin)
        if count > 0:
            destination[begin:begin + count] += source[:count]
        return
    indices = (np.arange(len(source)) + begin) % len(destination)
    destination[indices] += source


def coastal_bed(past=False):
    seconds = 60.0
    count = round(seconds * RATE)
    time = np.arange(count, dtype=np.float64) / RATE
    seed = SEED + (100 if past else 0)
    rng = np.random.default_rng(seed)
    # Nonregular overlapping long swells, crossing the loop seam where needed.
    centers = [1.7, 10.6, 21.3, 30.8, 43.9, 53.5]
    if past:
        centers += [6.1, 17.2, 36.0, 48.2, 57.7]
    events = [(center, float(rng.uniform(1.5, 3.2)), float(rng.uniform(.38, .87)))
              for center in centers]
    swell = periodic_envelope(time, seconds, events)
    swell /= max(float(swell.max()), 1e-8)
    surf = stereo_field(seconds, seed + 10, 65, 2350, .29, .34)
    foam = stereo_field(seconds, seed + 20, 750, 4300, .10, .53)
    wind = stereo_field(seconds, seed + 30, 95, 1050, .42, .46)
    gust = (.70 + .19 * np.sin(2 * math.pi * 3 * time / seconds + .7) +
            .11 * np.sin(2 * math.pi * 7 * time / seconds + 1.9))
    signal = surf * (.040 + .105 * swell[:, None])
    signal += foam * (.006 + .018 * swell[:, None] ** 1.7)
    signal += wind * (.022 * gust[:, None])
    # Low, quiet partials imply water around moorings, rather than music.
    lap = stereo_field(seconds, seed + 40, 32, 260, .45, .24)
    signal += lap * (.012 + .010 * swell[:, None])
    if past:
        # Busier means additional little boat/rigging/cloth gestures, no chatter.
        for index, center in enumerate([3.4, 12.8, 19.6, 28.4, 35.2, 46.8, 55.1]):
            creak_seconds = float(rng.uniform(.52, 1.25))
            t = np.arange(round(creak_seconds * RATE), dtype=np.float64) / RATE
            base = float(rng.uniform(155, 245))
            instantaneous = base + 22 * np.sin(2 * math.pi * 1.7 * t)
            phase = 2 * math.pi * np.cumsum(instantaneous) / RATE
            env = np.sin(math.pi * t / creak_seconds) ** 2
            mono = (.70 * np.sin(phase) + .18 * np.sin(phase * 2.13)) * env
            pan = float(rng.uniform(-.65, .65))
            creak = np.stack((mono * math.sqrt((1 - pan) / 2),
                              mono * math.sqrt((1 + pan) / 2)), axis=1)
            add_event(signal, edge_fades(creak) * .016, center, loop=True)
        for index, center in enumerate([8.5, 24.2, 40.8, 51.3]):
            knock = tone(.22, 610 + index * 17, decay=31, pan=(-.55 if index % 2 else .55))
            add_event(signal, edge_fades(knock, .002, .04) * .018, center, loop=True)
        for index, center in enumerate([15.3, 32.6, 58.8]):
            t = np.arange(round(1.8 * RATE), dtype=np.float64) / RATE
            brush = stereo_field(1.8, seed + 80 + index * 5, 270, 3100, .2, .30)
            brush *= (np.sin(math.pi * t / 1.8) ** 2)[:, None]
            add_event(signal, edge_fades(brush) * .008, center, loop=True)
    return signal.astype(np.float32)


def watch_tick():
    seconds = .18
    time = np.arange(round(seconds * RATE), dtype=np.float64) / RATE
    spring = tone(seconds, 1670, decay=70, attack=.0007)
    body = tone(seconds, 710, decay=87, attack=.0005)
    air = stereo_field(seconds, SEED + 201, 900, 4600, .1, .06)
    air *= np.exp(-time * 130)[:, None]
    return edge_fades(spring * .56 + body * .36 + air * .07, .001, .035)


def calibration():
    output = np.zeros((round(2.8 * RATE), 2), dtype=np.float32)
    for start, freq, gain, pan in [(0, 392.0, .55, -.10), (.18, 587.3295, .41, .12),
                                   (.42, 783.9909, .22, 0)]:
        add_event(output, edge_fades(tone(2.2, freq, decay=3.6, pan=pan), .008, .2) * gain, start)
    return edge_fades(output, .008, .35)


def transition():
    seconds = 3.4
    time = np.arange(round(seconds * RATE), dtype=np.float64) / RATE
    air = stereo_field(seconds, SEED + 220, 180, 2600, .28, .50)
    envelope = np.sin(math.pi * time / seconds) ** 2
    signal = air * (.065 * envelope[:, None])
    signal += tone(seconds, 146.8324, decay=1.2, attack=.45) * .030
    add_event(signal, tone(2.2, 220, decay=2.2, attack=.15) * .018, .9)
    return edge_fades(signal, .35, .60)


def cloth():
    seconds = 1.25
    time = np.arange(round(seconds * RATE), dtype=np.float64) / RATE
    brush = stereo_field(seconds, SEED + 240, 240, 3600, .12, .20)
    envelope = (.65 * np.exp(-.5 * ((time - .20) / .10) ** 2) +
                .45 * np.exp(-.5 * ((time - .60) / .17) ** 2) +
                .22 * np.exp(-.5 * ((time - .91) / .075) ** 2))
    return edge_fades(brush * envelope[:, None], .035, .12)


def bell_motif():
    output = np.zeros((round(8.0 * RATE), 2), dtype=np.float32)
    # A newly authored sparse three-note figure; no existing tune is referenced.
    for start, frequency, gain, pan in [(0, 293.6648, .62, -.18),
                                       (1.85, 440.0, .38, .18),
                                       (4.15, 329.6276, .40, -.06)]:
        note = tone(3.8, frequency, decay=1.65, pan=pan, attack=.009)
        add_event(output, edge_fades(note, .008, .55) * gain, start)
    return edge_fades(output, .009, .7)


def prepare(signal, target_rms_db=None, peak_limit_db=-6.0, one_shot=False):
    signal = np.asarray(signal, dtype=np.float32).copy()
    signal -= np.mean(signal, axis=0, dtype=np.float64).astype(np.float32)
    if target_rms_db is not None:
        actual = float(np.sqrt(np.mean(signal.astype(np.float64) ** 2)))
        signal *= 10 ** (target_rms_db / 20) / max(actual, 1e-10)
    peak = float(np.max(np.abs(signal)))
    limit = 10 ** (peak_limit_db / 20)
    if peak > limit:
        signal *= limit / peak
    if one_shot:
        signal = edge_fades(signal, .002, .012)
    return signal


def write_asset(output, name, signal, loop, design, suggested_gain):
    pcm = np.rint(np.clip(signal, -1, 1) * 32767).astype('<i2')
    rotation = 0
    if loop:
        # Circular reindexing preserves every original frame. Choose a small
        # stereo adjacent-sample delta, so a random loud crest is not the cut.
        candidate = pcm[:RATE + 1].astype(np.int32)
        scores = np.max(np.abs(np.diff(candidate, axis=0)), axis=1)
        rotation = int(np.argmin(scores)) + 1
        pcm = np.roll(pcm, -rotation, axis=0)
    path = output / (name + '.wav')
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(pcm.tobytes())
    # Read the actual WAV back: manifest measures the deliverable, not floats.
    with wave.open(str(path), 'rb') as handle:
        assert (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) == (2, 2, RATE)
        actual = np.frombuffer(handle.readframes(handle.getnframes()), dtype='<i2').reshape(-1, 2)
    decoded = actual.astype(np.float64) / 32768
    diffs = np.diff(actual.astype(np.int32), axis=0)
    seam = actual[0].astype(np.int32) - actual[-1].astype(np.int32)
    window = round(.020 * RATE)
    entry = {
        'filename': path.name, 'role': name, 'synthesized_design': design,
        'sample_rate_hz': RATE, 'channels': 2, 'pcm_bits': 16,
        'frames': len(actual), 'seconds': len(actual) / RATE, 'loop': loop,
        'loop_start_frame': 0 if loop else None,
        'loop_end_frame_exclusive': len(actual) if loop else None,
        'circular_start_rotation_frames': rotation,
        'peak_dbfs': db(np.max(np.abs(decoded))),
        'rms_dbfs': db(np.sqrt(np.mean(decoded ** 2))),
        'per_channel_rms_dbfs': [db(v) for v in np.sqrt(np.mean(decoded ** 2, axis=0))],
        'dc_offset': np.mean(decoded, axis=0).tolist(),
        'clipped_samples': int(np.count_nonzero(np.abs(actual.astype(np.int32)) >= 32767)),
        'first_frame_pcm': actual[0].tolist(), 'last_frame_pcm': actual[-1].tolist(),
        'join_delta_pcm_lsb': seam.tolist(),
        'join_delta_dbfs': [db(abs(int(v)) / 32768) for v in seam],
        'internal_adjacent_delta_p99_pcm_lsb': np.percentile(np.abs(diffs), 99, axis=0).tolist(),
        'first_20ms_rms_dbfs': db(np.sqrt(np.mean(decoded[:window] ** 2))),
        'last_20ms_rms_dbfs': db(np.sqrt(np.mean(decoded[-window:] ** 2))),
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'pcm_sha256': hashlib.sha256(actual.tobytes()).hexdigest(),
        'bytes': path.stat().st_size, 'suggested_initial_unreal_volume_multiplier': suggested_gain,
        'suggested_gain_status': 'Starting point only; runtime and listening review pending',
    }
    assert entry['clipped_samples'] == 0 and entry['peak_dbfs'] < -5.9
    if loop:
        assert np.all(np.abs(seam) <= np.percentile(np.abs(diffs), 99, axis=0)), 'Unexpected PCM loop join'
        entry['seam_measurement_passed'] = True
    else:
        assert np.all(actual[0] == 0) and np.all(actual[-1] == 0)
    return entry


def build(output=OUTPUT):
    assert RELEASE.name == 'Release_20261026', 'Author only in the release copy'
    output = Path(output).resolve()
    assert output == OUTPUT.resolve(), 'Outputs must remain in output/release_audio'
    output.mkdir(parents=True, exist_ok=True)
    definitions = [
        ('Amb_Coast_Present_60s', lambda: prepare(coastal_bed(False), -29.0, -12.0), True,
         'Quiet periodic filtered surf, irregular foam swells, low mooring-water wash and soft wind. No recordings or voices.', .65),
        ('Amb_Coast_Past_60s', lambda: prepare(coastal_bed(True), -26.5, -10.0), True,
         'Denser periodic surf/wind with sparse synthesized wood creaks, distant rigging taps and cloth brushes. No people, gull recordings, or voices.', .65),
        ('SFX_WatchTick', lambda: prepare(watch_tick(), -29.0, -14.0, True), False,
         'One short damped spring/body click with softly filtered attack noise; not a running tick loop.', .38),
        ('SFX_CalibrationSuccess', lambda: prepare(calibration(), -25.0, -10.0, True), False,
         'Restrained original three-tone confirmation with decaying partials; no reward fanfare or voice.', .50),
        ('SFX_SoftTransition', lambda: prepare(transition(), -28.0, -12.0, True), False,
         'A gentle air swell and low decaying tones, without bass impact, jump-scare transient, or voice.', .45),
        ('SFX_ClothInteraction', lambda: prepare(cloth(), -29.0, -13.0, True), False,
         'Three overlapping filtered-noise brushes suggesting handling woven fabric; synthesized, not recorded.', .45),
        ('MUS_Optional_BellMotif', lambda: prepare(bell_motif(), -28.0, -11.0, True), False,
         'Original sparse three-note D4-A4-E4 bell-like synthesis with mildly inharmonic partials. Optional cue; no existing composition referenced.', .34),
    ]
    records = []
    for name, factory, loop, design, gain in definitions:
        entry = write_asset(output, name, factory(), loop, design, gain)
        records.append(entry)
        print(name, entry['seconds'], 'sec', 'peak', entry['peak_dbfs'], 'RMS', entry['rms_dbfs'], flush=True)
    manifest = {
        'success': True, 'generator_version': VERSION, 'seed': SEED,
        'generator': str(Path(__file__).resolve()),
        'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'numpy_version': np.__version__, 'format': 'Stereo 48000 Hz signed 16-bit little-endian PCM WAV',
        'provenance': 'New procedural sound designs synthesized from random fields and sinusoidal partials by this source. No third-party audio or external recording input.',
        'loops': 'Both beds use periodic spectral fields, integer-cycle envelopes and wrapped events. A circular start rotation selects a small stereo sample delta and retains every frame. No silence or crossfade gap is inserted. PCM join delta is checked against the internal 99th-percentile adjacent-sample delta.',
        'headroom': 'All individual assets peak below -6 dBFS. This is not a mixed-bus or device loudness/performance claim; multiple simultaneous sources still need runtime gain review.',
        'implemented': ['Original PCM synthesis', 'WAV output/readback', 'Deterministic seed', 'Peak/RMS/DC/clipping/join measurements', 'SHA256 provenance'],
        'not_verified': ['Auditory listening review', 'Native Unreal import', 'Runtime event mapping and era switching', 'Loop playback in Unreal', 'Bus settings/ducking/user volume controls', 'Packaged playback', 'Headset/device playback', 'Perceptual loudness or broadcast LUFS'],
        'mix_notes': ['Use one era bed at a time; crossfade after a committed era change, not during a failed transition.',
                      'Keep the optional bell motif separate from ambience and dialogue; do not loop it continuously.',
                      'Trigger one watch tick per deliberate dial movement; debounce repeated input.',
                      'SFX should not carry information that is absent from existing visual text/prompts.'],
        'assets': records,
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (output / 'README.txt').write_text(
        'ORIGINAL PROCEDURAL AUDIO SOURCE ASSETS\n\n'
        'Two 60-second coastal beds and five restrained one-shot cues.\n'
        'All stereo, 48 kHz, signed 16-bit PCM WAV. Nothing has been imported into Unreal by this script.\n'
        'Synthesized locally from deterministic random fields and sinusoidal partials. No voices or borrowed audio.\n'
        'Present is quieter; Past adds small wood/rigging/cloth details rather than synthetic speech.\n'
        'The optional bell figure is a newly authored sparse cue, not an existing track.\n\n'
        'manifest.json records exact SHA, peak/RMS/DC, PCM endpoints and loop joins measured by reading the WAVs back.\n'
        'The two loops are periodic fields, without inserted start/end silence. Loop markers cover all 2,880,000 frames.\n'
        'Numbers verify signal properties only. Listening, runtime mix, native import and packaged playback remain pending.\n'
        'Suggested per-file gain values are conservative starting points, not a validated final mix.\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    result = build(parser.parse_args().output)
    print('Wrote', len(result['assets']), 'original WAV assets to', OUTPUT, flush=True)
