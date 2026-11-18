"""Moves a trailer edit list onto new takes of the same script (15 November 2026).

  python.exe -I tools/remap_trailer_edit.py <edit.json> <source>=<new take folder> [<source>=<folder> ...] [--out <edit.json>]

A take made by tools/RunTrailerTake.ps1 has take.json (recorder start) and director_report.json (named marks with UTC
times). For every segment of a remapped source the tool finds the last mark of the OLD take at or before the segment's
start, and puts the segment the same number of seconds after the same mark in the NEW take. The director's beats are
timed by fixed waits, so a shot keeps its content to within a few frames; look at the stills afterwards all the same.
A source whose new folder has no marks (the simulator recording) only has its path replaced. Nothing is rendered here.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def marks(folder):
    take = json.loads((folder / 'take.json').read_text(encoding='utf-8-sig'))
    report = folder / 'director_report.json'
    if not report.exists() or not take.get('recorder_started_unix'):
        return None
    base = float(take['recorder_started_unix'])
    rows = [(m['name'], float(m['utc']) - base) for m in json.loads(report.read_text(encoding='utf-8-sig'))['marks']]
    return rows


def main():
    args = sys.argv[1:]
    out = None
    if '--out' in args:
        i = args.index('--out')
        out = ROOT / args[i + 1]
        del args[i:i + 2]
    edit_path = ROOT / args[0]
    edit = json.loads(edit_path.read_text(encoding='utf-8-sig'))
    table = []
    for pair in args[1:]:
        source, folder = pair.split('=', 1)
        new_folder = (ROOT / folder).resolve()
        old_path = edit['sources'][source]['path']
        old_folder = (ROOT / old_path).resolve().parent
        new_path = str((new_folder / 'take.mkv').relative_to(ROOT)).replace('\\', '/')
        old_marks, new_marks = marks(old_folder), marks(new_folder)
        edit['sources'][source]['path'] = new_path
        if not old_marks or not new_marks:
            table.append({'source': source, 'path_only': True})
            continue
        new_by_name = {}
        for name, offset in new_marks:
            new_by_name.setdefault(name, offset)
        specs = []
        for index, segment in enumerate(edit['segments']):
            if segment.get('source') == source:
                specs.append((index, segment))
            for part in segment.get('xfade', []):
                if part.get('source') == source:
                    specs.append((index, part))
        for index, spec in specs:
            start = float(spec['start'])
            before = [(name, offset) for name, offset in old_marks if offset <= start + 0.05]
            if not before:
                raise SystemExit('Segment %d of %s starts before the first mark' % (index, source))
            name, offset = before[-1]
            if name not in new_by_name:
                raise SystemExit('Mark %s (segment %d of %s) is not in the new take' % (name, index, source))
            moved = round(new_by_name[name] + (start - offset), 1)
            table.append({'segment': index, 'source': source, 'mark': name, 'after_mark_s': round(start - offset, 1), 'old_start': start, 'new_start': moved})
            spec['start'] = moved
    target = out or edit_path
    target.write_text(json.dumps(edit, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'edit': str(target), 'moved': table}, indent=1))


if __name__ == '__main__':
    main()
