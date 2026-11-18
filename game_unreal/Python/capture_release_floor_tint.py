"""Queued current-photo-floor vs warm-candidate native PNGs; no map saves.

Before is the saved accepted floor pattern. After changes only two material
overrides in memory. Current lighting/cameras remain fixed. Existing native
input hashes and actual restored actor overrides are checked before exit.
"""
from pathlib import Path
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import build_release_hero as hero
import prepare_release_floor_tints as palette
import capture_release_art as review
from capture_release_hero import VIEWS


class Capture(review.Capture):
    def __init__(self, candidate=None):
        self.candidate = candidate or palette.prepared()
        self.original_floors = {}
        review.VIEWS = VIEWS
        super().__init__()
        self.folder = ROOT / 'validation/release_floor_tint_capture' / self.stamp
        self.folder.mkdir(parents=True, exist_ok=False)
        self.report_path = palette.CAPTURE
        self.report.update(scope=__doc__, candidate_signature=self.candidate['signature'],
                           policy_sha256=self.candidate['policy_sha256'], candidate=self.candidate['candidate'],
                           before_meaning='Current saved accepted photographic floor patterns',
                           after_meaning='Warm01 linear BaseColor multipliers only, transient material overrides',
                           visual_accepted=False, profile_policy='Saved desktop 0.21 skylight and all other lights unchanged')
        self.report['candidate_materials_transient'] = bool(self.candidate.get('transient'))
        self.groups = [
            {'label': 'Before', 'map': hero.MAP, 'era': 'Present', 'jobs': [(view, 'Lit') for view in VIEWS]},
            {'label': 'After', 'map': hero.MAP, 'era': 'Present',
             'jobs': [(view, 'Lit') for view in VIEWS] + [(VIEWS[1], 'BaseColor')]},
        ]
        self.protected.update({path: hero.sha(path) for path in (ROOT / 'Saved/SaveGames').glob('*') if path.is_file()})

    def apply_era_preview(self, era):
        lights = hero.base.lighting()
        if self.saved_lights is None:
            self.saved_lights = lights
        hero.require(lights == self.saved_lights, 'Current lighting differs between palette pairs')
        record = hero.read_report()['floors']
        for recipe in hero.config()['floor_scope']:
            actor = hero.base.find_mesh(recipe['mesh'])
            hero.require(hero.eligible(actor, record, recipe) is None, 'Preserving manually edited floor during preview')
            state = hero.base.state(actor)
            self.original_floors.setdefault(actor.get_name(), state)
            hero.require(self.original_floors[actor.get_name()] == state, 'Saved floors changed across palette pairs')
            if self.groups[self.group_index]['label'] == 'After':
                path = self.candidate['material_paths'][recipe['role']]
                material = unreal.find_object(None, path) if path.startswith('/Engine/Transient.') else hero.base.load(path)
                hero.require(material is not None, 'Prepared candidate material is missing')
                actor.get_component_by_class(unreal.StaticMeshComponent).set_material(recipe['slot'], material)
        return True

    def finish(self, error=None):
        try:
            for name, saved in self.original_floors.items():
                actor = next((actor for actor in hero.base.actors() if actor.get_name() == name), None)
                hero.require(actor is not None, 'Current floor actor disappeared during capture')
                actor.get_component_by_class(unreal.StaticMeshComponent).set_editor_property('override_materials',
                    [hero.base.load(path) if path else None for path in saved['raw_override_materials']])
                hero.require(hero.base.state(actor) == saved, 'Transient candidate floor override did not restore')
            self.report['transient_floor_overrides_restored'] = True
        except Exception:
            error = error or traceback.format_exc()
        super().finish(error)


if __name__ == '__main__':
    session = None
    try:
        transient = unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseFloorTintTransient')
        session = Capture(palette.prepare(transient=True) if transient else None)
        session.start()
    except Exception:
        if session:
            session.finish(traceback.format_exc())
        else:
            palette.CAPTURE.write_text(json.dumps({'success': False, 'error': traceback.format_exc()}, indent=2), encoding='utf-8')
            unreal.SystemLibrary.quit_editor()
