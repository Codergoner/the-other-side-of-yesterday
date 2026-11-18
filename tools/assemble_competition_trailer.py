"""Assembles the competition trailer (under 3 minutes) from recorded takes with ffmpeg 9.

  python.exe -I tools/assemble_competition_trailer.py output/trailer_edit/edit.json

edit.json:
  {"out": "output/trailer_edit/TheOtherSideOfYesterday_Trailer.mp4", "fps": 30, "width": 1920, "height": 1080,
   "sources": {"pie": {"path": ..., "crop": "w:h:x:y"}, "sim": {...}},
   "segments": [
     {"card": true, "seconds": 3.0, "lines": [{"text": "...", "size": 54, "y": 0.46}]},
     {"source": "pie", "start": 12.3, "seconds": 5.0, "fade_in": 0.5, "fade_out": 0.0, "speed": 1.0,
      "text": "...", "text_size": 46, "text_y": 0.84, "label": "..."},
     {"xfade": [{"source": "pie", "start": .., "seconds": ..}, {"source": "pie", "start": .., "seconds": ..}], "duration": 1.0, "text": "..."}
   ],
   "score": {"jump_segment": 12, "jump_offset": 4.0}}
Every segment is rendered to an intermediate H.264 file at the output size and frame rate, then concatenated; the score
(tools/build_trailer_score.py) is generated to the exact length with the swell placed on the jump, then muxed as AAC.
No frame is generated or interpolated: sources are cropped, scaled, optionally slowed by an explicit `speed`, and faded.
Report: <out>.json with the timeline, every source range and the footage labels.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / 'output/capture_tools/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe'
FFPROBE = ROOT / 'output/capture_tools/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe'
FONTS = ROOT / 'output/trailer_title_assets/fonts'
PYTHON = Path(sys.executable)


def run(args):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError('ffmpeg failed:\n' + ' '.join(str(a) for a in args)[:1500] + '\n' + result.stderr[-2500:])
    return result


def esc_path(path):
    return str(path).replace('\\', '/').replace(':', '\\:')


def esc_text(text):
    out = text.replace('\\', '\\\\').replace(':', '\\:').replace("'", '’').replace('%', '\\%').replace(',', '\\,')
    return out


def drawtext(text, size, y, duration, font='Roboto-Light.ttf', fade=0.5, x='(w-text_w)/2', colour='white', start=0.0, box=True):
    end = duration
    alpha = "if(lt(t\\,{s})\\,0\\,if(lt(t\\,{s}+{f})\\,(t-{s})/{f}\\,if(lt(t\\,{e}-{f})\\,1\\,if(lt(t\\,{e})\\,({e}-t)/{f}\\,0))))".format(s=start, f=fade, e=end)
    parts = ["fontfile='%s'" % esc_path(FONTS / font), "text='%s'" % esc_text(text), 'fontsize=%d' % size, 'fontcolor=%s' % colour,
             'x=%s' % x, 'y=h*%.4f' % y, "alpha='%s'" % alpha, 'shadowcolor=black@0.75', 'shadowx=2', 'shadowy=2']
    if box:
        parts += ['box=1', 'boxcolor=black@0.28', 'boxborderw=18']
    return 'drawtext=' + ':'.join(parts)


def text_filters(segment, duration):
    filters = []
    if segment.get('text'):
        lines = segment['text'].split('\n')
        size = segment.get('text_size', 46)
        y = segment.get('text_y', 0.82)
        for i, line in enumerate(lines):
            filters.append(drawtext(line, size, y + i * (size * 1.35 / 1080.0), segment.get('text_end', duration), start=segment.get('text_start', 0.3)))
    if segment.get('label'):
        filters.append(drawtext(segment['label'], 22, 0.955, duration, font='Roboto-Regular.ttf', x='w-text_w-36', colour='white@0.8', box=False, fade=0.3))
    return filters


def source_chain(spec, sources, size, fps):
    src = sources[spec['source']]
    chain = []
    crop = spec.get('crop') or src.get('crop')
    if crop:
        chain.append('crop=' + crop)
    chain.append('scale=%d:%d:flags=lanczos' % size)
    speed = float(spec.get('speed', 1.0))
    if speed != 1.0:
        chain.append('setpts=PTS/%.5f' % speed)
    chain.append('fps=%d' % fps)
    if src.get('eq'):
        chain.append('eq=' + src['eq'])
    return src, chain, speed


def render_segment(index, segment, edit, work):
    fps, size = edit['fps'], (edit['width'], edit['height'])
    out = work / ('seg_%02d.mp4' % index)
    encode = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '15', '-pix_fmt', 'yuv420p', '-r', str(fps), '-an']
    if segment.get('card'):
        duration = float(segment['seconds'])
        filters = [drawtext(line['text'], line.get('size', 54), line.get('y', 0.46), duration, font=line.get('font', 'Roboto-Light.ttf'),
                            colour=line.get('colour', 'white'), box=False, start=line.get('start', 0.2), fade=line.get('fade', 0.6)) for line in segment['lines']]
        run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0x050607:s=%dx%d:r=%d:d=%.3f' % (size[0], size[1], fps, duration),
             '-vf', ','.join(filters) if filters else 'null', '-t', '%.3f' % duration] + encode + [out])
        return out, duration, {'card': [line['text'] for line in segment['lines']]}
    if segment.get('xfade'):
        a, b = segment['xfade']
        blend = float(segment.get('duration', 1.0))
        inputs, chains = [], []
        for n, spec in enumerate((a, b)):
            src, chain, speed = source_chain(spec, edit['sources'], size, fps)
            inputs += ['-ss', '%.3f' % spec['start'], '-t', '%.3f' % (spec['seconds'] * speed), '-i', ROOT / src['path']]
            chains.append('[%d:v]%s,format=yuv420p,settb=AVTB[v%d]' % (n, ','.join(chain), n))
        duration = a['seconds'] + b['seconds'] - blend
        graph = ';'.join(chains) + ';[v0][v1]xfade=transition=%s:duration=%.3f:offset=%.3f[x]' % (segment.get('transition', 'fade'), blend, a['seconds'] - blend)
        tail = text_filters(segment, duration)
        fades = []
        if segment.get('fade_in'):
            fades.append('fade=t=in:st=0:d=%.3f' % segment['fade_in'])
        if segment.get('fade_out'):
            fades.append('fade=t=out:st=%.3f:d=%.3f' % (duration - segment['fade_out'], segment['fade_out']))
        graph += ';[x]%s[o]' % (','.join(tail + fades) if tail + fades else 'null')
        run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y'] + inputs + ['-filter_complex', graph, '-map', '[o]', '-t', '%.3f' % duration] + encode + [out])
        return out, duration, {'xfade': [a, b]}
    src, chain, speed = source_chain(segment, edit['sources'], size, fps)
    duration = float(segment['seconds'])
    filters = chain + text_filters(segment, duration)
    if segment.get('fade_in'):
        filters.append('fade=t=in:st=0:d=%.3f%s' % (segment['fade_in'], ':color=white' if segment.get('fade_white') else ''))
    if segment.get('fade_out'):
        filters.append('fade=t=out:st=%.3f:d=%.3f%s' % (duration - segment['fade_out'], segment['fade_out'], ':color=white' if segment.get('fade_out_white') else ''))
    run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-ss', '%.3f' % segment['start'], '-t', '%.3f' % (duration * speed), '-i', ROOT / src['path'],
         '-vf', ','.join(filters), '-t', '%.3f' % duration] + encode + [out])
    return out, duration, {'source': segment['source'], 'source_start': segment['start'], 'speed': speed}


def describe(segment):
    """The source ranges of a segment, for the report (also used when an already rendered segment is reused)."""
    if segment.get('card'):
        return {'card': [line['text'] for line in segment['lines']]}
    if segment.get('xfade'):
        return {'xfade': segment['xfade']}
    return {'source': segment['source'], 'source_start': segment['start'], 'speed': float(segment.get('speed', 1.0)),
            'crop': segment.get('crop'), 'label': segment.get('label')}


def main():
    edit_path = (ROOT / sys.argv[1]).resolve()
    edit = json.loads(edit_path.read_text(encoding='utf-8-sig'))
    out = (ROOT / edit['out']).resolve()
    work = out.parent / (out.stem + '_work')
    work.mkdir(parents=True, exist_ok=True)
    timeline, cursor, files = [], 0.0, []
    only = set(int(a) for a in sys.argv[2:])  # optional: re-render only these segment indices
    for index, segment in enumerate(edit['segments']):
        target = work / ('seg_%02d.mp4' % index)
        if only and index not in only and target.exists():
            probe = subprocess.run([str(FFPROBE), '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(target)], capture_output=True, text=True)
            duration, detail = float(probe.stdout.strip()), dict(describe(segment), reused=True)
            path = target
        else:
            path, duration, detail = render_segment(index, segment, edit, work)
            probe = subprocess.run([str(FFPROBE), '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)], capture_output=True, text=True)
            duration = float(probe.stdout.strip())
        timeline.append({'index': index, 'start': round(cursor, 3), 'seconds': round(duration, 3), 'text': segment.get('text'), **detail})
        cursor += duration
        files.append(path)
    listing = work / 'concat.txt'
    listing.write_text(''.join("file '%s'\n" % str(p).replace('\\', '/') for p in files), encoding='utf-8')
    silent = work / 'video_only.mp4'
    run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', listing, '-c', 'copy', silent])
    total = cursor
    score_spec = edit.get('score', {})
    jump = timeline[score_spec['jump_segment']]['start'] + score_spec.get('jump_offset', 0.0) if 'jump_segment' in score_spec else total * 0.5
    score = work / 'score.wav'
    # Optional "return_segment"/"return_offset": the second turn of the longer cut (the return to the present).
    back = timeline[score_spec['return_segment']]['start'] + score_spec.get('return_offset', 0.0) if 'return_segment' in score_spec else None
    run([PYTHON, '-I', ROOT / 'tools/build_trailer_score.py', '--jump', '%.3f' % jump, '--end', '%.3f' % (total - 3.0),
         '--pad-in', '%.3f' % score_spec.get('pad_in', 14.0), '--out', str(score.relative_to(ROOT)).replace('\\', '/')]
        + (['--return-at', '%.3f' % back] if back is not None else []))
    run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', silent, '-i', score, '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
         '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-af', 'afade=t=out:st=%.3f:d=2.5' % (total - 2.6), '-t', '%.3f' % total, '-movflags', '+faststart', out])
    probe = subprocess.run([str(FFPROBE), '-v', 'error', '-show_entries', 'format=duration,size:stream=codec_name,width,height,r_frame_rate,sample_rate,channels',
                            '-of', 'json', str(out)], capture_output=True, text=True)
    report = {'out': str(out), 'total_seconds': round(total, 3), 'jump_seconds': round(jump, 3), 'return_seconds': round(back, 3) if back is not None else None, 'timeline': timeline, 'probe': json.loads(probe.stdout),
              'sources': edit['sources'], 'score': json.loads(score.with_suffix('.json').read_text(encoding='utf-8')),
              'footage_labels': edit.get('footage_labels'), 'reviewed_by_ear': False,
              'note': 'Frames were inspected as stills by the assembler\'s author; nobody has watched the motion or listened to the audio.'}
    out.with_suffix('.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(json.dumps({'out': str(out), 'seconds': round(total, 2), 'jump': round(jump, 2), 'segments': len(timeline)}))


if __name__ == '__main__':
    main()
