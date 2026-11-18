"""Update one desktop manager's existing editable credits; no graph rebuild."""
from pathlib import Path
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT/'Python'))
import build_release_art as art
import release_file_io as io

CREDITS = ('Story/design: project-authored production draft.\n'
           'Environment: project-authored geometry; Poly Haven CC0 surfaces/sky.\n'
           'Humans: MakeHuman Community / MPFB CC0 asset exports.\n'
           'Character animation source: Epic Games; adapted project listening/blinks.\n'
           'Family photograph: AI-assisted image, based on our fictional Mother.\n'
           'Ambience and effects: original synthesized project sound design.\n'
           'Dialogue is captioned; voice performances are not included.\n'
           'Powered by Unreal Engine. Full asset provenance accompanies the build.')


def main():
    art.guard()
    art.require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseCreditsWrite'), 'Root writer queue required')
    map_path = '/Game/Quest/Maps/Verdant_Desktop'
    map_file = ROOT/'Content/Quest/Maps/Verdant_Desktop.umap'
    files = io.files(ROOT/'Content', '*.uasset') + io.files(ROOT/'Content', '*.umap')
    files += list((ROOT/'Config').glob('*.ini')) + list(ROOT.glob('*.uproject')) + io.files(ROOT/'Saved/SaveGames', '*.sav')
    before = {str(p): io.sha(p) for p in files}
    art.require(art.LEVEL.load_level(map_path), 'Cannot load desktop map')
    managers = [a for a in art.actors() if a.actor_has_tag('Opening.Manager')]
    art.require(len(managers) == 1, 'Exactly one existing manager required')
    manager = managers[0]
    actors_before, lights_before, refs_before = art.snapshot(), art.lighting(), art.story_refs()
    previous = str(manager.get_editor_property('ReleaseCredits'))
    manager.set_editor_property('ReleaseCredits', CREDITS)
    art.require(actors_before == art.snapshot() and lights_before == art.lighting() and refs_before == art.story_refs(), 'Unrelated scene change')
    if previous != CREDITS:
        art.require(art.LEVEL.save_current_level(), 'Cannot save native credits')
    art.require(art.LEVEL.load_level(map_path), 'Cannot reload native credits')
    manager = next(a for a in art.actors() if a.actor_has_tag('Opening.Manager'))
    art.require(str(manager.get_editor_property('ReleaseCredits')) == CREDITS, 'Saved credits readback differs')
    art.require(all(Path(p) == map_file or io.sha(p) == digest for p, digest in before.items()), 'Unrelated asset/config/save changed')
    (ROOT/'release_credits_validation.json').write_text(json.dumps({'success': True, 'native_executed': True,
        'map': map_path, 'previous': previous, 'credits': CREDITS, 'graph_regenerated': False,
        'unrelated_files_unchanged': True, 'repeated_without_save': previous == CREDITS}, indent=2)+'\n')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        (ROOT/'release_credits_failed.json').write_text(json.dumps({'success': False, 'error': traceback.format_exc()}, indent=2))
    finally:
        unreal.SystemLibrary.quit_editor()
