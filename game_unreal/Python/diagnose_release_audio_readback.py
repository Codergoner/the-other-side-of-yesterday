"""Queued read-only native audio reload diagnostic; no saves or authoring.

Records real bIsEditorOnly sprite helper flags and compares persistent actor
state with the generated report. Runtime audio playback is not tested here.
"""
from pathlib import Path
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import import_release_audio as audio


def run():
    result = {'success': False, 'map_or_asset_saves': False, 'runtime_playtested': False}
    before = audio.protect()
    try:
        audio.guard()
        audio.require(audio.LEVEL.load_level(audio.MAP), 'Cannot load saved audio map')
        owned = [actor for actor in audio.actors() if actor.actor_has_tag(audio.OWNER)]
        audio.require(len(owned) == 1, 'Audio director is not unique')
        actor = owned[0]
        result['native_component_flags'] = [{'name': component.get_name(), 'class': component.get_class().get_path_name(),
                                             'is_editor_only': bool(component.get_editor_property('is_editor_only'))}
                                            for component in actor.get_components_by_class(unreal.ActorComponent)]
        old = audio.report_read()
        result['legacy_report_snapshot'] = old['after']
        result['actual_persistent_snapshot'] = audio.actor_snapshot(actor)
        result['canonical_report_snapshot'] = audio.canonical_state(old['after'])
        legacy_icons = [entry for entry in old['after']['components']
                        if entry not in result['canonical_report_snapshot']['components']
                        and entry.get('type') == '/Script/Engine.BillboardComponent']
        native_icons = [entry for entry in result['native_component_flags']
                        if entry['class'] == '/Script/Engine.BillboardComponent']
        result['legacy_icon_exclusions_backed_by_native_flags'] = (len(legacy_icons) == len(native_icons)
            and all(entry['is_editor_only'] for entry in native_icons))
        audio.require(result['legacy_icon_exclusions_backed_by_native_flags'], 'Legacy helper exclusions are not backed by actual native editor-only flags')
        result['persistent_snapshot_matches'] = result['actual_persistent_snapshot'] == result['canonical_report_snapshot']
        audio.require(result['persistent_snapshot_matches'], 'A persistent field differs; editor icons were not the only difference')
        result['native_readback'] = audio.validate_saved()
        result['success'] = True
    except Exception:
        result['error'] = traceback.format_exc()
        unreal.log_error(result['error'])
    result['protected_files_unchanged'] = audio.protect() == before
    result['success'] = result['success'] and result['protected_files_unchanged']
    (ROOT / 'release_audio_readback_diagnostic.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    try:
        run()
    finally:
        unreal.SystemLibrary.quit_editor()
