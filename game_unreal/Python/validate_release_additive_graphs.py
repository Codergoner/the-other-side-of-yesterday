"""Read-only native audit after additive writers; never repairs or compiles assets.

Keeps the pinned original 47 keyboard/two photo defaults and 13 guarded calls
distinct from newly authored keyboard queries. Historical proofs are retained.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import opening_graph as og
import release_file_io as io
import release_mother_integration as shared
import persist_release_key_repair as persist
import install_release_action_sfx as sfx


def main():
    shared.require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseAdditiveGraphRead'),
                   'Root fresh-process read-only flag required')
    shared.require(not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor(), 'Exit PIE before saved readback')
    out = ROOT / 'validation/release_additive_graphs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    out.mkdir(parents=True, exist_ok=False)
    protected = persist.protected_files(set())
    proof, data = persist.load_proof()
    rows = persist.changes(proof, data)
    bp = unreal.load_asset(shared.MANAGER)
    audit = shared.GraphAudit(out / 'native_exports')
    nodes = {node.get_path_name(): node for graph in og.L.list_graphs(bp)
             for node in og.E.get_graph_editor(graph).list_all_nodes()}
    targets = persist.validate_targets(nodes, rows, data, audit, 'after')
    guards = audit.guarded_calls(bp)
    shared.require(guards == proof['guarded_save_calls_after'], 'An original guarded save node/owner/GUID/pin changed')
    original_keys = {row['node'] for row in rows if row['pin'] == 'Key'}
    additional = []
    quest_report = ROOT / 'quest_story_v02_integration.json'
    quest = json.loads(quest_report.read_text(encoding='utf-8')) if quest_report.exists() else {}
    for path, node in nodes.items():
        keys = [p for p in og.L.list_input_pins(node) if str(og.P.get_pin_name(p)) == 'Key']
        if not keys or path in original_keys:
            continue
        shared.require(len(keys) == 1, 'Ambiguous additional key query')
        value = str(og.P.get_pin_value(keys[0]))
        owner, function = audit.function(node)
        shared.require(quest.get('success') and ':InputFrame.' in path and value == 'Two'
                       and function == 'WasInputKeyJustPressed', 'Unreviewed additional keyboard query: ' + path)
        additional.append({'node': path, 'guid': audit.guid(node), 'key': value, 'owner': owner, 'function': function})
    shared.require(len(additional) == (1 if quest.get('success') else 0), 'Unexpected additive keyboard query count')
    sfx_report = sfx.read()
    shared.require(sfx_report.get('success'), 'Actual SFX authoring report required')
    for file, digest in sfx_report['asset_fingerprints'].items():
        shared.require(io.sha(file) == digest, 'Saved SFX class bytes differ')
    shared.require(sfx.owned_helpers(bp) == sfx_report['helpers_after'], 'Saved SFX helper body differs')
    records = json.loads(unreal.EditorAssetLibrary.get_metadata_tag(bp, sfx.META))
    shared.require(records == sfx_report['hooks'], 'Saved SFX hook metadata differs')
    for row in records.values():
        call = nodes[row['call_path']]
        shared.require(sfx.audit.guid(call) == row['call_guid'] and sfx.stable_pins(call) == row['call_pins'],
                       'Saved SFX producer hook/cue differs')
    shared.require(sfx.hero.base.LEVEL.load_level(sfx.hero.MAP), 'Cannot load actual Desktop map for readback')
    actors = [a for a in sfx.hero.base.actors() if a.actor_has_tag(sfx.STABLE)]
    shared.require(len(actors) == 1 and sfx.sfx_actor_state(actors[0]) == sfx_report['actor_after'], 'Saved SFX actor differs')
    channel = actors[0].get_components_by_class(unreal.AudioComponent)
    shared.require(len(channel) == 1 and not channel[0].get_editor_property('auto_activate')
                   and channel[0].get_editor_property('sound') is None, 'SFX boot channel is not empty and silent')
    shared.require(all(io.sha(p) == digest for p, digest in protected.items()), 'Read-only audit changed native/config/save bytes')
    manager_sha = io.sha(shared.asset_file(ROOT, shared.MANAGER))
    key_result = {'success': True, 'manager_asset_sha256': manager_sha,
                  'fresh_process_reader_verified': True, 'all49_saved_values_and_guids_match_pinned_full_comparison': True,
                  'verified_key_defaults': 47, 'verified_photo_rotation_defaults': 2,
                  'additional_keyboard_defaults_verified': additional, 'native_targets_after_reload': targets,
                  'guarded_save_calls_after': guards, 'asset_config_or_save_writes': False,
                  'protected_files_unchanged': True, 'whole_graph_comparison_repeated': False,
                  'scope': 'Original49 reviewed targets plus13 guarded calls and explicitly reviewed additive key queries; not a whole-graph or runtime input test.'}
    integration = ROOT / 'release_save_guard_integration.json'
    guard_result = {'success': True, 'manager_asset_sha256': manager_sha,
                    'original13_node_guids_members_pins_preserved': True, 'generic_save_calls': 0,
                    'original_integration_sha256': io.sha(integration), 'guarded_save_calls_after': guards,
                    'fresh_process_reader_verified': True, 'asset_config_or_save_writes': False}
    result = {'success': True, 'manager_asset_sha256': manager_sha, 'original_key_photo_defaults_verified': 49,
              'additional_keyboard_defaults_verified': additional, 'native_guard_calls_verified': 13,
              'sfx_saved_helpers_hooks_actor_verified': True, 'sfx_boot_empty_channel_verified': True,
              'sfx_runtime_playback_verified': False, 'perceptual_audio_approved': False,
              'native_config_save_files_unchanged': True, 'protected_file_count': len(protected), 'run': str(out)}
    for name, value in [('release_key_literal_persistence_validation.json', key_result),
                        ('release_save_guard_final_audit.json', guard_result),
                        ('release_additive_graphs_validation.json', result)]:
        target = ROOT / name
        if target.exists():
            shutil.copy2(target, out / (name + '.previous'))
        (out / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
        target.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    try:
        main()
    except Exception:
        (ROOT / 'release_additive_graphs_validation_failed.json').write_text(
            json.dumps({'success': False, 'error': traceback.format_exc()}, indent=2), encoding='utf-8')
        unreal.log_error(traceback.format_exc())
    finally:
        unreal.SystemLibrary.quit_editor()
