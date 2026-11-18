"""Queued Blender 5.2 VSE encoder test, NEVER game or trailer footage.

blender --background --factory-startup --python tools/smoke_blender_encoder.py -- --run-encoder-test

Creates exactly 60 requested frames at 1920x1080/30fps plus an original stereo
48kHz test tone. Checks the real MP4 sample tables and Blender decode/readback.
Does not install an encoder, change a game project or create a 300-second fake.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import array
import hashlib
import json
import math
import shutil
import struct
import subprocess
import sys
import traceback
import wave

ROOT = Path(__file__).resolve().parents[1]
FRAMES, FPS, RATE = 60, 30, 48000


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def boxes(data, start=0, end=None):
    end = len(data) if end is None else end
    while start + 8 <= end:
        length, kind = struct.unpack_from('>I4s', data, start)
        header = 8
        if length == 1:
            length, header = struct.unpack_from('>Q', data, start + 8)[0], 16
        if length == 0:
            length = end - start
        require(length >= header and start + length <= end, 'Invalid MP4 box boundaries')
        yield kind.decode('ascii', 'replace'), start + header, start + length
        start += length


def child(data, parent, kind):
    return next((box for box in boxes(data, parent[1], parent[2]) if box[0] == kind), None)


def timing(data, box):
    offset = box[1]
    if data[offset] == 1:
        timescale, duration = struct.unpack_from('>IQ', data, offset + 20)
    else:
        timescale, duration = struct.unpack_from('>II', data, offset + 12)
    return {'timescale': timescale, 'duration_ticks': duration, 'seconds': duration / timescale}


def inspect_mp4(path):
    """Parse actual ISO-BMFF tracks/sample tables; no planned-frame substitute."""
    return inspect_mp4_bytes(Path(path).read_bytes())


def inspect_mp4_bytes(data):
    top = list(boxes(data))
    moov = next(b for b in top if b[0] == 'moov')
    movie = timing(data, child(data, moov, 'mvhd'))
    tracks = []
    for track in [b for b in boxes(data, moov[1], moov[2]) if b[0] == 'trak']:
        mdia = child(data, track, 'mdia')
        handler = child(data, mdia, 'hdlr')
        kind = data[handler[1] + 8:handler[1] + 12].decode('ascii')
        row = {'handler': kind, 'media_timing': timing(data, child(data, mdia, 'mdhd'))}
        track_header = child(data, track, 'tkhd')
        duration_offset = track_header[1] + (28 if data[track_header[1]] == 1 else 20)
        duration_fmt = '>Q' if data[track_header[1]] == 1 else '>I'
        row['track_presentation_seconds'] = struct.unpack_from(duration_fmt, data, duration_offset)[0] / movie['timescale']
        stbl = child(data, child(data, mdia, 'minf'), 'stbl')
        stts = child(data, stbl, 'stts')
        count = struct.unpack_from('>I', data, stts[1] + 4)[0]
        entries = [struct.unpack_from('>II', data, stts[1] + 8 + i * 8) for i in range(count)]
        row['sample_count'] = sum(n for n, _ in entries)
        row['sample_time_entries'] = [{'count': n, 'delta': delta} for n, delta in entries]
        row['constant_sample_duration'] = len({delta for _, delta in entries}) == 1
        stsz = child(data, stbl, 'stsz')
        row['sample_size_table_count'] = struct.unpack_from('>I', data, stsz[1] + 8)[0]
        stsd = child(data, stbl, 'stsd')
        entry = next(boxes(data, stsd[1] + 8, stsd[2]))
        row['codec'] = entry[0]
        if kind == 'vide':
            row['width'], row['height'] = struct.unpack_from('>HH', data, entry[1] + 24)
            colr = next((b for b in boxes(data, entry[1] + 78, entry[2]) if b[0] == 'colr'), None)
            if colr:
                row['color_type'] = data[colr[1]:colr[1] + 4].decode('ascii')
                row['color_primaries'], row['color_transfer'], row['color_matrix'] = struct.unpack_from('>HHH', data, colr[1] + 4)
            row['sample_rate_fps'] = row['media_timing']['timescale'] / entries[0][1]
        elif kind == 'soun':
            row['channels'], row['sample_bits'] = struct.unpack_from('>HH', data, entry[1] + 16)
            row['sample_rate_hz'] = struct.unpack_from('>I', data, entry[1] + 24)[0] / 65536
        edts = child(data, track, 'edts')
        elst = child(data, edts, 'elst') if edts else None
        if elst:
            size = 20 if data[elst[1]] == 1 else 12
            fmt = '>Q' if size == 20 else '>I'
            n = struct.unpack_from('>I', data, elst[1] + 4)[0]
            durations = [struct.unpack_from(fmt, data, elst[1] + 8 + i * size)[0] for i in range(n)]
            row['presented_seconds_from_edit_list'] = sum(durations) / movie['timescale']
            row['edit_list'] = []
            for i in range(n):
                offset = elst[1] + 8 + i * size
                duration, media_time = struct.unpack_from('>Qq' if size == 20 else '>Ii', data, offset)
                rate_integer, rate_fraction = struct.unpack_from('>hh', data, offset + (16 if size == 20 else 8))
                row['edit_list'].append({'duration_movie_ticks': duration, 'media_time_media_ticks': media_time,
                                        'rate_integer': rate_integer, 'rate_fraction': rate_fraction})
        tracks.append(row)
    return {'movie_timing': movie, 'tracks': tracks, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def trim_aac_end_presentation(raw, seconds=2.0):
    """Trim AAC presentation using its edit list, without altering encoded samples.

    Keep the existing media_time (AAC priming offset), raw mdhd duration, sample
    tables, chunk offsets and mdat bytes. Only shorten the audio ELST segment and
    align the audio TKHD and movie MVHD durations to the same presentation end.
    This deliberately refuses complex/multiple edit lists instead of guessing.
    """
    before = inspect_mp4_bytes(raw)
    video = next(row for row in before['tracks'] if row['handler'] == 'vide')
    audio = next(row for row in before['tracks'] if row['handler'] == 'soun')
    require(abs(video['media_timing']['seconds'] - seconds) < 1e-9, 'Video duration must already be exact before audio end trim')
    require(audio['codec'] == 'mp4a' and audio['sample_rate_hz'] == RATE and audio['channels'] == 2, 'Unexpected audio codec/rate/layout')
    require(len(audio.get('edit_list', [])) == 1, 'End trim requires one existing audio edit-list segment')
    edit = audio['edit_list'][0]
    require(edit['media_time_media_ticks'] >= 0 and edit['rate_integer'] == 1 and edit['rate_fraction'] == 0, 'Unsupported edit-list priming/rate')
    timescale = before['movie_timing']['timescale']
    target = round(seconds * timescale)
    require(abs(target / timescale - seconds) < 1e-9, 'Target presentation end is not representable in movie timescale')
    removed = edit['duration_movie_ticks'] - target
    require(0 <= removed / timescale < 0.1, 'Refusing a non-padding audio content edit')
    require(edit['media_time_media_ticks'] + round(seconds * audio['media_timing']['timescale']) <= audio['media_timing']['duration_ticks'], 'Raw AAC media cannot cover the requested presentation')
    moov = next(box for box in boxes(raw) if box[0] == 'moov')
    movie_header = child(raw, moov, 'mvhd')
    audio_tracks = []
    for track in [box for box in boxes(raw, moov[1], moov[2]) if box[0] == 'trak']:
        mdia = child(raw, track, 'mdia')
        hdlr = child(raw, mdia, 'hdlr')
        if raw[hdlr[1] + 8:hdlr[1] + 12] == b'soun':
            audio_tracks.append(track)
    require(len(audio_tracks) == 1, 'End trim requires exactly one audio track')
    track = audio_tracks[0]
    track_header = child(raw, track, 'tkhd')
    edit_box = child(raw, child(raw, track, 'edts'), 'elst')
    out = bytearray(raw)
    edits = []

    def patch_duration(box, field, offset_v0, offset_v1):
        version = raw[box[1]]
        require(version in [0, 1], 'Unsupported MP4 full-box version')
        fmt, size = ('>Q', 8) if version == 1 else ('>I', 4)
        offset = box[1] + (offset_v1 if version == 1 else offset_v0)
        previous = struct.unpack_from(fmt, raw, offset)[0]
        struct.pack_into(fmt, out, offset, target)
        edits.append({'field': field, 'offset_bytes': offset, 'size_bytes': size,
                      'old_movie_ticks': previous, 'new_movie_ticks': target})

    patch_duration(edit_box, 'audio.elst.segment_duration', 8, 8)
    patch_duration(track_header, 'audio.tkhd.duration', 20, 28)
    patch_duration(movie_header, 'movie.mvhd.duration', 16, 24)
    result = bytes(out)
    changed = {i for i, (old, new) in enumerate(zip(raw, result)) if old != new}
    allowed = {i for item in edits for i in range(item['offset_bytes'], item['offset_bytes'] + item['size_bytes'])}
    require(changed.issubset(allowed) and len(result) == len(raw), 'Unexpected MP4 data mutation')
    original_mdat = [hashlib.sha256(raw[a:b]).hexdigest() for kind, a, b in boxes(raw) if kind == 'mdat']
    final_mdat = [hashlib.sha256(result[a:b]).hexdigest() for kind, a, b in boxes(result) if kind == 'mdat']
    require(original_mdat and original_mdat == final_mdat, 'Encoded media payload changed')
    after = inspect_mp4_bytes(result)
    after_audio = next(row for row in after['tracks'] if row['handler'] == 'soun')
    after_video = next(row for row in after['tracks'] if row['handler'] == 'vide')
    require(video == after_video, 'Video track changed during AAC presentation trim')
    for field in ['media_timing', 'sample_count', 'sample_time_entries', 'sample_size_table_count', 'codec', 'sample_rate_hz', 'channels']:
        require(audio[field] == after_audio[field], 'Raw AAC media/sample tables changed: ' + field)
    require(after_audio['edit_list'][0]['media_time_media_ticks'] == edit['media_time_media_ticks'], 'AAC priming offset changed')
    require(after_audio['presented_seconds_from_edit_list'] == seconds and after_audio['track_presentation_seconds'] == seconds and after['movie_timing']['seconds'] == seconds, 'Presentation end is not exact after trim')
    return result, {'method': 'AAC end-padding presentation trim via ELST, with matching audio TKHD and movie MVHD durations.',
                    'edits': edits, 'tail_presentation_seconds_removed': removed / timescale,
                    'aac_priming_media_time_retained': edit['media_time_media_ticks'],
                    'raw_aac_media_seconds_retained': audio['media_timing']['seconds'],
                    'raw_sample_tables_unchanged': True, 'video_track_unchanged': True,
                    'mdat_sha256_before_after': original_mdat, 'mdat_unchanged': True,
                    'only_declared_duration_bytes_changed': True}


def original_tone(path):
    samples = array.array('h')
    for i in range(RATE * 2):
        t = i / RATE
        envelope = min(1.0, t / 0.025, (2 - t) / 0.025)
        envelope = max(0, envelope) ** 2
        for frequency in [440, 660]:
            samples.append(round(32767 * 0.12 * envelope * math.sin(math.tau * frequency * t)))
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(samples.tobytes())


def set_enum(owner, name, value):
    """Use actual assignment/readback; static RNA items can be sentinel-only."""
    prop = owner.bl_rna.properties.get(name)
    require(prop is not None, owner.bl_rna.identifier + ' has no property ' + name)
    try:
        setattr(owner, name, value)
        actual = getattr(owner, name)
    except Exception as error:
        raise RuntimeError(owner.bl_rna.identifier + '.' + name + ' rejected ' + repr(value)
                           + ' during native assignment/readback: ' + str(error)) from error
    require(actual == value, owner.bl_rna.identifier + '.' + name + ': requested '
            + repr(value) + ', actual readback ' + repr(actual))


def configure_scene(scene):
    scene.frame_start, scene.frame_end = 1, FRAMES
    scene.render.fps, scene.render.fps_base = FPS, 1.0
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.resolution_percentage = 100
    scene.render.engine = 'BLENDER_EEVEE'
    # Installed OCIO config contains this SDR display/view pair.
    set_enum(scene.display_settings, 'display_device', 'Rec.1886')
    set_enum(scene.view_settings, 'view_transform', 'Standard')
    scene.view_settings.exposure, scene.view_settings.gamma = 0.0, 1.0


def emission(name, rgb):
    import bpy
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    shader = tree.nodes.new('ShaderNodeEmission')
    shader.inputs['Color'].default_value = (*rgb, 1)
    tree.links.new(shader.outputs[0], output.inputs[0])
    return material


def rectangle(scene, name, x, y, width, height, mat, z=0):
    import bpy
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-width / 2, -height / 2, 0), (width / 2, -height / 2, 0),
                     (width / 2, height / 2, 0), (-width / 2, height / 2, 0)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.location = (x, y, z)
    obj.data.materials.append(mat)
    return obj


def make_test_scene():
    import bpy
    scene = bpy.context.scene
    scene.name = 'ENCODER TEST - NOT GAMEPLAY - original generated pattern'
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    configure_scene(scene)
    colors = [(0.7, 0.7, 0.7), (0.7, 0.7, 0.02), (0.02, 0.7, 0.7),
              (0.02, 0.7, 0.02), (0.7, 0.02, 0.7), (0.7, 0.02, 0.02), (0.02, 0.02, 0.7)]
    rectangle(scene, 'Background', 0, 0, 2, 1.125, emission('DarkGray', (0.025, 0.025, 0.025)))
    for index, color in enumerate(colors):
        rectangle(scene, 'Original color bar ' + str(index), -0.84 + index * 0.28, -0.025, 0.28, 0.62, emission('Bar' + str(index), color), 0.01)
    moving = rectangle(scene, 'Moving encoder test marker', -0.84, -0.43, 0.09, 0.09, emission('Marker', (0.9, 0.9, 0.9)), 0.02)
    moving.driver_add('location', 0).driver.expression = '-0.84+(frame-1)*(1.68/59)'
    font = bpy.data.curves.new('Explicit test label', 'FONT')
    font.body = 'ENCODER TEST — NOT GAMEPLAY\n60 FRAMES / 2 SECONDS / 1080p30 / ORIGINAL STEREO TONE'
    font.align_x, font.size, font.space_line = 'CENTER', 0.047, 1.3
    label = bpy.data.objects.new('ENCODER TEST — NOT GAMEPLAY', font)
    scene.collection.objects.link(label)
    label.location = (0, 0.41, 0.03)
    font.materials.append(emission('LabelWhite', (0.85, 0.85, 0.85)))
    camera_data = bpy.data.cameras.new('Encoder test camera')
    camera = bpy.data.objects.new('Encoder test camera', camera_data)
    scene.collection.objects.link(camera)
    camera.location = (0, 0, 10)
    camera_data.type, camera_data.ortho_scale = 'ORTHO', 2.0
    scene.camera = camera
    return scene


def main():
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--run-encoder-test', action='store_true')
    parsed = arguments.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    require(parsed.run_encoder_test, 'Explicit queued --run-encoder-test required')
    import bpy
    require(bpy.app.ffmpeg.supported, 'This Blender build has no FFmpeg support')
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    folder = ROOT / 'output/encoder_smoke' / run
    folder.mkdir(parents=True)
    report = {'success': False, 'scope': 'Two-second encoder test only. NOT GAMEPLAY. NOT TRAILER FOOTAGE.',
              'run': run, 'blender_version': bpy.app.version_string, 'expected_frames': FRAMES, 'expected_seconds': 2,
              'actual_encode_attempted': False, 'game_assets_used': False, 'game_project_modified': False}
    path = folder / 'ENCODER_TEST_NOT_GAMEPLAY.mp4'
    try:
        audio = folder / 'ORIGINAL_ENCODER_TEST_48k_STEREO.wav'
        original_tone(audio)
        pattern = make_test_scene()
        edit = bpy.data.scenes.new('ENCODER TEST VSE EDIT - NOT GAMEPLAY')
        bpy.context.window.scene = edit
        configure_scene(edit)
        editor = edit.sequence_editor_create()
        strip = editor.strips.new_scene(name='Original test pattern - NOT GAMEPLAY', scene=pattern, channel=1, frame_start=1)
        strip.scene_input = 'CAMERA'
        strip.frame_final_duration = FRAMES
        sound = editor.strips.new_sound(name='Original two-second encoder test tone', filepath=str(audio), channel=2, frame_start=1)
        sound.frame_final_duration, sound.volume = FRAMES, 1.0
        edit.render.use_sequencer = True
        edit.render.image_settings.media_type = 'VIDEO'
        edit.render.image_settings.file_format = 'FFMPEG'
        edit.render.image_settings.color_mode = 'RGB'
        edit.render.image_settings.color_depth = '8'
        settings = edit.render.ffmpeg
        for name, value in [('format', 'MPEG4'), ('codec', 'H264'), ('constant_rate_factor', 'HIGH'),
                            ('ffmpeg_preset', 'GOOD'), ('audio_codec', 'AAC'), ('audio_channels', 'STEREO')]:
            set_enum(settings, name, value)
        settings.audio_mixrate, settings.audio_bitrate = RATE, 192
        settings.use_autosplit, settings.use_max_b_frames = False, False
        settings.gopsize = FPS
        edit.render.filepath = str(path)
        report['rna_settings'] = {name: getattr(settings, name) for name in ['format', 'codec', 'audio_codec', 'audio_channels', 'audio_mixrate', 'audio_bitrate', 'constant_rate_factor']}
        report['requested_display_transform'] = {'display': edit.display_settings.display_device, 'view': edit.view_settings.view_transform}
        report['actual_encode_attempted'] = True
        bpy.ops.render.render(animation=True, scene=edit.name)
        report['requested_output_path'] = str(path)
        actual_outputs = list(folder.glob('*.mp4'))
        require(len(actual_outputs) == 1, 'Expected exactly one actual MP4 output: ' + repr(actual_outputs))
        path = actual_outputs[0]
        require(path.is_file() and path.stat().st_size > 1000, 'No real MP4 was produced at the requested path')
        raw_data = path.read_bytes()
        report['raw_encoder_mp4'] = inspect_mp4_bytes(raw_data)
        trimmed_data, trim_record = trim_aac_end_presentation(raw_data, seconds=2.0)
        raw_path = folder / (path.stem + '_RAW_WITH_AAC_PADDING.mp4')
        require(not raw_path.exists(), 'Refusing to overwrite preserved raw encode')
        raw_path.write_bytes(raw_data)
        require(sha(raw_path) == report['raw_encoder_mp4']['sha256'], 'Raw encode preservation failed')
        path.write_bytes(trimmed_data)
        report['presentation_trim'] = dict(trim_record, preserved_raw_path=str(raw_path), preserved_raw_sha256=sha(raw_path))
        actual = inspect_mp4(path)
        report['actual_mp4'] = actual
        video = next(row for row in actual['tracks'] if row['handler'] == 'vide')
        audio_track = next(row for row in actual['tracks'] if row['handler'] == 'soun')
        checks = {
            'actual_h264': video['codec'] in ['avc1', 'avc3'],
            'actual_60_samples': video['sample_count'] == FRAMES == video['sample_size_table_count'],
            'actual_1080p': [video['width'], video['height']] == [1920, 1080],
            'actual_constant_30fps': video['constant_sample_duration'] and abs(video['sample_rate_fps'] - FPS) < 1e-9,
            'actual_video_2_seconds': abs(video['media_timing']['seconds'] - 2.0) < 1e-9,
            'actual_container_2_seconds': abs(actual['movie_timing']['seconds'] - 2.0) < 1e-9,
            'actual_audio_presentation_2_seconds': audio_track.get('presented_seconds_from_edit_list') == 2.0 and audio_track['track_presentation_seconds'] == 2.0,
            'encoded_media_unchanged_by_presentation_trim': trim_record['mdat_unchanged'] and trim_record['raw_sample_tables_unchanged'],
            'actual_48khz_stereo': audio_track['sample_rate_hz'] == RATE and audio_track['channels'] == 2,
            'actual_mp4_audio_track': audio_track['codec'] == 'mp4a',
            'actual_rec709_metadata': video.get('color_primaries') == 1 and video.get('color_transfer') == 1 and video.get('color_matrix') == 1,
        }
        report['checks'] = checks
        clip = bpy.data.movieclips.load(str(path))
        report['blender_movie_readback'] = {'frames': clip.frame_duration, 'size': list(clip.size), 'fps_if_exposed': getattr(clip, 'fps', None)}
        checks['blender_movie_readback'] = clip.frame_duration == FRAMES and list(clip.size) == [1920, 1080]
        # Decode actual exported frames through a new VSE movie strip.
        readback = bpy.data.scenes.new('DECODED ENCODER TEST - NOT GAMEPLAY')
        bpy.context.window.scene = readback
        configure_scene(readback)
        readback.sequence_editor_create().strips.new_movie(name='Actual exported MP4 readback', filepath=str(path), channel=1, frame_start=1)
        readback.render.use_sequencer = True
        readback.render.image_settings.media_type = 'IMAGE'
        readback.render.image_settings.file_format = 'PNG'
        decoded = []
        for frame in [1, 30, 60]:
            readback.frame_set(frame)
            image = folder / ('DECODED_NOT_GAMEPLAY_frame_' + str(frame).zfill(3) + '.png')
            readback.render.filepath = str(image)
            bpy.ops.render.render(write_still=True, scene=readback.name)
            decoded.append({'frame': frame, 'path': str(image), 'sha256': sha(image)})
        report['decoded_frame_images'] = decoded
        checks['decoded_marker_moves'] = len({row['sha256'] for row in decoded}) == 3
        try:
            import aud
            decoded_audio = aud.Sound(str(path)).data()
            report['decoded_audio'] = {'sample_frames': int(decoded_audio.shape[0]), 'channels': int(decoded_audio.shape[1]),
                'left_rms': float((decoded_audio[:, 0] ** 2).mean() ** 0.5), 'right_rms': float((decoded_audio[:, 1] ** 2).mean() ** 0.5)}
            checks['actual_decoded_audio_nonzero'] = decoded_audio.shape[1] == 2 and report['decoded_audio']['left_rms'] > 0.01 and report['decoded_audio']['right_rms'] > 0.01
        except Exception as error:
            report['decoded_audio_error'] = repr(error)
            checks['actual_decoded_audio_nonzero'] = False
        probe = shutil.which('ffprobe')
        if probe:
            result = subprocess.run([probe, '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(path)],
                capture_output=True, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            report['ffprobe'] = {'executable': probe, 'returncode': result.returncode, 'data': json.loads(result.stdout) if result.returncode == 0 else result.stderr}
        report['path'] = str(path)
        report['success'] = all(checks.values())
        report['failed_checks'] = [name for name, passed in checks.items() if not passed]
        bpy.context.window.scene = edit
        bpy.ops.wm.save_as_mainfile(filepath=str(folder / 'ENCODER_TEST_NOT_GAMEPLAY.blend'))
    except Exception as error:
        report.update(error=str(error), traceback=traceback.format_exc())
        print(traceback.format_exc(), flush=True)
    finally:
        out = folder / 'encoder_test_report.json'
        out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        (ROOT / 'output/encoder_smoke/latest.json').write_text(json.dumps({'run': run, 'report': str(out)}, indent=2) + '\n')
        print('ENCODER_TEST_REPORT ' + str(out), flush=True)
    require(report['success'], 'Encoder smoke failed; inspect the actual report. No trailer is claimed.')


if __name__ == '__main__':
    main()
