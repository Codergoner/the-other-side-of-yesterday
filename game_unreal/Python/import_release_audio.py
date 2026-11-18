"""Queued native audio import + additive director in Release Verdant_Desktop.

Source-only until a root-granted full-editor -ReleaseAudioWrite authoring pass.
Creates versioned owned assets and one actor; no existing manager/HUD/input,
story/era array, geometry, collision, sky, renderer or user save is changed.
Runtime Python is not required. SFX/music are imported references, untriggered.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy
import hashlib
import json
import re
import sys
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
RELEASE = PROJECT.parent
sys.path.insert(0, str(PROJECT / 'Python'))
import opening_graph as og
import build_opening_actions as base
import build_chapters_story as story
import release_audio_graph as graph

SOURCE = RELEASE / 'output/release_audio'
REPORT = PROJECT / 'release_audio_import_report.json'
OWNER = 'TOSOY.ReleaseAudioOwned'
STABLE = 'release.audio.director'
MAP = '/Game/Quest/Maps/Verdant_Desktop'
LIB = unreal.EditorAssetLibrary
ASSETS = unreal.AssetToolsHelpers.get_asset_tools()
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def guard(write=False):
    require(RELEASE.name == 'Release_20261026', 'Refusing a protected or unrelated project')
    require('-run=' not in unreal.SystemLibrary.get_command_line().lower(), 'A full editor entry point is required')
    require(LEVEL and ACTORS and EDITOR, 'Full editor subsystems are required')
    require(not LEVEL.is_in_play_in_editor(), 'Native authoring/readback cannot run during PIE')
    baseline = json.loads((RELEASE / 'release_baseline_manifest.json').read_text(encoding='utf-8'))
    require(Path(baseline['target']).resolve() == RELEASE, 'Release identity mismatch')
    if write:
        require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseAudioWrite'), 'Root queue and -ReleaseAudioWrite are required')


def source_manifest():
    manifest = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    require(manifest['success'] and len(manifest['assets']) == 7, 'Seven generated audio sources are required')
    for entry in manifest['assets']:
        file = (SOURCE / entry['filename']).resolve()
        require(file.parent == SOURCE.resolve() and file.suffix == '.wav', 'Unsafe source filename')
        require(sha(file) == entry['sha256'], 'Audio source changed: ' + file.name)
        require(entry['sample_rate_hz'] == 48000 and entry['pcm_bits'] == 16 and entry['channels'] == 2, 'Unsupported PCM source')
    return manifest


def signature(manifest):
    data = {'waves': [(a['filename'], a['sha256']) for a in manifest['assets']],
            'importer': sha(Path(__file__)), 'graph': sha(Path(graph.__file__))}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def mark(asset, sig, stage='Complete'):
    LIB.set_metadata_tag(asset, 'Release.Audio.Owner', OWNER)
    LIB.set_metadata_tag(asset, 'Release.Audio.Signature', sig)
    LIB.set_metadata_tag(asset, 'Release.Audio.Stage', stage)


def verify_owned(asset, sig):
    require(LIB.get_metadata_tag(asset, 'Release.Audio.Owner') == OWNER, 'Preserving unowned asset: ' + asset.get_path_name())
    require(LIB.get_metadata_tag(asset, 'Release.Audio.Signature') == sig, 'Preserving changed asset provenance')
    require(LIB.get_metadata_tag(asset, 'Release.Audio.Stage') == 'Complete', 'Incomplete native audio version; do not reuse without repair')
    old = report_read()
    saved_path = PROJECT / 'Content' / (asset.get_path_name().split('.')[0].removeprefix('/Game/') + '.uasset')
    expected = old.get('asset_fingerprints', {}).get(str(saved_path))
    if expected:
        require(saved_path.exists() and sha(saved_path) == expected, 'Preserving externally edited audio asset: ' + asset.get_path_name())


def save(asset):
    require(LIB.save_loaded_asset(asset, only_if_is_dirty=False), 'Failed saving ' + asset.get_path_name())


def sound_classes(folder, sig):
    classes = {}
    existing = {}
    for name in ['Master', 'Ambience', 'Music', 'SFX']:
        path = folder + '/Classes/SC_Release' + name
        asset = unreal.load_asset(path)
        existing[name] = asset is not None
        if asset:
            verify_owned(asset, sig)
        else:
            asset = ASSETS.create_asset('SC_Release' + name, folder + '/Classes', unreal.SoundClass, unreal.SoundClassFactory())
            require(asset, 'Cannot create owned sound class ' + name)
            mark(asset, sig, 'Building')
            properties = asset.get_editor_property('properties')
            properties.set_editor_property('volume', 1.0)
            asset.set_editor_property('properties', properties)
        classes[name] = asset
    # Append one child at a time. SoundClass::PostEditChangeProperty updates
    # parentage for the first added child per editor property notification.
    if not any(existing.values()):
        children = []
        for name in ['Ambience', 'Music', 'SFX']:
            children.append(classes[name])
            classes['Master'].set_editor_property('child_classes', children)
        for asset in classes.values():
            mark(asset, sig)
        for asset in classes.values():
            save(asset)
    elif not all(existing.values()):
        raise RuntimeError('Partial SoundClass version is preserved; author a clean new signature')
    for name, asset in classes.items():
        parent = asset.get_editor_property('parent_class')
        require((parent is None if name == 'Master' else parent == classes['Master']), 'Native SoundClass parent mismatch: ' + name)
        require(abs(asset.get_editor_property('properties').get_editor_property('volume') - 1.0) < 1e-6, 'Preserving edited class gain: ' + name)
    return classes


def wave_readback(asset, entry, expected_class):
    require(isinstance(asset, unreal.SoundWave), 'Native import is not a SoundWave')
    actual = {'path': asset.get_path_name(), 'looping': bool(asset.get_editor_property('looping')),
              'duration_seconds': float(asset.get_editor_property('duration')),
              'channels': int(asset.get_editor_property('num_channels')),
              'imported_sample_rate': int(asset.get_editor_property('imported_sample_rate')),
              'class': asset.get_editor_property('sound_class_object').get_path_name()}
    require(actual['looping'] == entry['loop'], 'Native bLooping mismatch')
    require(abs(actual['duration_seconds'] - entry['seconds']) < .001, 'Native source duration mismatch')
    require(actual['channels'] == 2 and actual['imported_sample_rate'] == 48000, 'Native PCM format mismatch')
    require(asset.get_editor_property('sound_class_object') == expected_class, 'Native SoundClass routing changed')
    return actual


def import_waves(manifest, folder, sig, classes):
    waves, readback = {}, []
    for entry in manifest['assets']:
        path = folder + '/Waves/' + entry['role']
        asset = unreal.load_asset(path)
        category = 'Ambience' if entry['loop'] else ('Music' if entry['role'].startswith('MUS_') else 'SFX')
        if asset:
            verify_owned(asset, sig)
            require(LIB.get_metadata_tag(asset, 'Release.Audio.SourceSHA256') == entry['sha256'], 'Audio provenance was edited')
        else:
            task = unreal.AssetImportTask()
            factory = unreal.SoundFactory()
            factory.set_editor_property('auto_create_cue', False)
            for key, value in {'filename': str(SOURCE / entry['filename']), 'destination_path': folder + '/Waves',
                               'destination_name': entry['role'], 'automated': True, 'replace_existing': False,
                               'save': False, 'factory': factory}.items():
                task.set_editor_property(key, value)
            ASSETS.import_asset_tasks([task])
            asset = unreal.load_asset(path)
            require(isinstance(asset, unreal.SoundWave), 'SoundWave import failed: ' + entry['role'])
            mark(asset, sig, 'Building')
            asset.set_editor_property('looping', entry['loop'])
            asset.set_editor_property('sound_class_object', classes[category])
            if entry['loop']:
                asset.set_editor_property('virtualization_mode', unreal.VirtualizationMode.PLAY_WHEN_SILENT)
            LIB.set_metadata_tag(asset, 'Release.Audio.SourceSHA256', entry['sha256'])
            mark(asset, sig)
            save(asset)
        readback.append(wave_readback(asset, entry, classes[category]))
        waves[entry['role']] = asset
    return waves, readback


def build_director(folder, sig, waves):
    path = folder + '/BP_ReleaseAudioDirector'
    # Loading a nonexistent BP first creates an empty UPackage. The native
    # BlueprintEditorLibrary creation helper then rejects that package as an
    # existing asset, even though it contains no Blueprint.
    bp = unreal.load_asset(path) if LIB.does_asset_exist(path) else None
    if bp:
        verify_owned(bp, sig)
        require(LIB.get_metadata_tag(bp, 'Release.Audio.GraphSourceSHA') == sha(Path(graph.__file__)), 'Preserving edited director provenance')
        return bp
    bp = og.blueprint(path, unreal.Actor)
    mark(bp, sig, 'Building')
    base.MATH_LITERALS.clear()
    graph.build(bp, waves)
    for node, name, value in base.MATH_LITERALS:
        pin = og.L.find_input_pin(node, name)
        if og.P.is_valid(pin) and not og.P.list_connected_pins(pin):
            og.default(pin, value)
    og.compile_bp(bp)
    LIB.set_metadata_tag(bp, 'Release.Audio.GraphSourceSHA', sha(Path(graph.__file__)))
    mark(bp, sig)
    save(bp)
    return bp


def actor_snapshot(actor):
    def xyz(value): return [round(value.x, 5), round(value.y, 5), round(value.z, 5)]
    rotation = actor.get_actor_rotation()
    state = {'name': actor.get_name(), 'label': actor.get_actor_label(), 'class': actor.get_class().get_path_name(),
             'location': xyz(actor.get_actor_location()), 'rotation': [rotation.pitch, rotation.yaw, rotation.roll],
             'scale': xyz(actor.get_actor_scale3d()), 'tags': sorted(str(t) for t in actor.get_editor_property('tags')),
             'collision': actor.get_actor_enable_collision(), 'hidden': bool(actor.get_editor_property('hidden')),
             'components': [], 'mix': {}}
    for component in actor.get_components_by_class(unreal.PrimitiveComponent):
        # Scene/audio components create transient editor-only sprite helpers.
        # Their generated names change on map reload and they are not cooked.
        if component.get_editor_property('is_editor_only'):
            continue
        mesh = component.get_editor_property('static_mesh') if isinstance(component, unreal.StaticMeshComponent) else None
        state['components'].append({'name': component.get_name(), 'type': component.get_class().get_path_name(),
                                    'is_editor_only': False,
                                    'mesh': mesh.get_path_name() if mesh else None,
                                    'collision': str(component.get_collision_enabled()),
                                    'profile': str(component.get_collision_profile_name()),
                                    'pawn_response': str(component.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)),
                                    'visibility_response': str(component.get_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY)),
                                    'materials': [component.get_material(i).get_path_name() if component.get_material(i) else None for i in range(component.get_num_materials())]})
    state['lights'] = []
    for component in actor.get_components_by_class(unreal.LightComponentBase):
        light = {'name': component.get_name(), 'type': component.get_class().get_path_name()}
        for name in ['intensity', 'visible', 'light_color', 'cast_shadows', 'real_time_capture', 'cubemap', 'source_cubemap_angle']:
            try:
                value = component.get_editor_property(name)
                if isinstance(value, unreal.Object):
                    value = value.get_path_name()
                elif isinstance(value, (unreal.Color, unreal.LinearColor)):
                    value = {channel: getattr(value, channel) for channel in ['r', 'g', 'b', 'a']}
                elif value is not None and not isinstance(value, (bool, int, float, str)):
                    value = str(value)
                light[name] = value
            except Exception:
                pass
        state['lights'].append(light)
    if actor.actor_has_tag(OWNER):
        for name in ['MasterGain', 'AmbienceGain', 'MusicGain', 'MuteWhenPaused']:
            state['mix'][name] = actor.get_editor_property(name)
        for component in actor.get_components_by_class(unreal.AudioComponent):
            state['components'].append({'name': component.get_name(), 'sound': component.get_editor_property('sound').get_path_name(),
                                        'auto_activate': bool(component.get_editor_property('auto_activate')),
                                        'allow_spatialization': bool(component.get_editor_property('allow_spatialization')),
                                        'is_ui_sound': bool(component.get_editor_property('is_ui_sound'))})
    return canonical_state(state)


def canonical_state(state):
    state = copy.deepcopy(state)
    # Normalize the first report's legacy snapshot of native editor-only audio
    # icons. Current native snapshots exclude them via bIsEditorOnly above.
    state['components'] = [entry for entry in state.get('components', [])
        if not ('is_editor_only' not in entry and entry.get('type') == '/Script/Engine.BillboardComponent'
                and re.fullmatch(r'BillboardComponent_\d+', entry.get('name', ''))
                and entry.get('collision') == '<CollisionEnabled.NO_COLLISION: 0>'
                and entry.get('materials') == [])]
    for entry in state['components']:
        if 'type' in entry:
            entry.setdefault('is_editor_only', False)
    state['components'].sort(key=lambda entry: (entry.get('type', ''), entry.get('name', '')))
    state['lights'] = sorted(state.get('lights', []), key=lambda entry: entry['name'])
    return state


def actors():
    return list(ACTORS.get_all_level_actors())


def snapshot():
    return {actor.get_name(): actor_snapshot(actor) for actor in actors()}


def protect():
    paths = list((PROJECT / 'Content').rglob('*.uasset')) + list((PROJECT / 'Content').rglob('*.umap'))
    paths += list((PROJECT / 'Config').glob('*.ini')) + list(PROJECT.glob('*.uproject'))
    paths += list((PROJECT / 'Saved/SaveGames').glob('*.sav'))
    return {str(path): sha(path) for path in paths}


def story_snapshot():
    result = {}
    for actor in actors():
        if not actor.actor_has_tag('Opening.Manager'):
            continue
        result[actor.get_name()] = {}
        names = list(dict.fromkeys(story.STATE + base.REFS + story.REFS +
                     ['SaveSlot', 'InteractionRange', 'PastActors', 'PresentActors', 'PastCollisionActors']))
        for name in names:
            value = actor.get_editor_property(name)
            if isinstance(value, unreal.Array):
                value = [item.get_path_name() if isinstance(item, unreal.Object) else str(item) for item in value]
            result[actor.get_name()][name] = str(value)
    return result


def report_read():
    return json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {'schema': 1, 'map': MAP}


def validate_director(actor):
    components = actor.get_components_by_class(unreal.AudioComponent)
    require(len(components) == 2, 'The director must own exactly two persistent audio components')
    require(not actor.get_actor_enable_collision(), 'Audio director unexpectedly has collision')
    for component in components:
        require(not component.get_editor_property('auto_activate'), 'Audio must start only through the era selector')
        require(not component.get_editor_property('allow_spatialization'), 'Ambience bed must be nonspatial')
        require(not component.get_editor_property('can_play_multiple_instances'), 'Audio component permits duplicate instances')
        require(component.get_editor_property('sound').get_editor_property('looping'), 'Bed is not a looping SoundWave')
    return actor_snapshot(actor)


def _apply():
    guard(write=True)
    before_files = protect()
    for path, digest in report_read().get('asset_fingerprints', {}).items():
        require(Path(path).exists() and sha(path) == digest, 'Preserving externally edited previous audio asset: ' + path)
    manifest = source_manifest()
    sig = signature(manifest)
    folder = '/Game/Release/Audio/V_' + sig
    classes = sound_classes(folder, sig)
    waves, wave_checks = import_waves(manifest, folder, sig, classes)
    bp = build_director(folder, sig, waves)
    require(LEVEL.load_level(MAP), 'Cannot load the Release desktop map')
    require(EDITOR.get_editor_world().get_path_name().split('.')[0] == MAP, 'Unexpected map loaded')
    baseline = snapshot()
    story_before = story_snapshot()
    require(len(story_before) == 1, 'Exactly one existing story manager is required')
    old = report_read()
    old.setdefault('first_baseline', {'map_sha256': sha(PROJECT / 'Content/Quest/Maps/Verdant_Desktop.umap'),
                                      'actors': copy.deepcopy(baseline), 'story': copy.deepcopy(story_before)})
    candidates = [actor for actor in actors() if actor.actor_has_tag(STABLE) or actor.actor_has_tag(OWNER)]
    require(len(candidates) <= 1, 'Multiple audio directors found; preserving the map')
    actor = candidates[0] if candidates else None
    if actor:
        require(actor.actor_has_tag(OWNER), 'Preserving unowned actor at reserved audio identity')
        if actor.actor_has_tag('TOSOY.ManualOverride') or actor.get_name() in old.get('inferred_manual_names', []):
            return {'success': False, 'preserved_manual': actor.get_path_name(), 'reason': 'Explicit or sticky manual override'}
        if canonical_state(old.get('after', {})) != actor_snapshot(actor):
            old.setdefault('inferred_manual_names', []).append(actor.get_name())
            old['preserved_manual'] = actor.get_path_name()
            REPORT.write_text(json.dumps(old, indent=2), encoding='utf-8')
            return {'success': False, 'preserved_manual': actor.get_path_name(), 'reason': 'Director differs from last generated snapshot'}
        if actor.get_class() != og.L.generated_class(bp):
            require(ACTORS.destroy_actor(actor), 'Could not remove unchanged obsolete director')
            actor = None
    if actor is None:
        actor = ACTORS.spawn_actor_from_class(og.L.generated_class(bp), unreal.Vector(0, 0, 0))
        require(actor, 'Could not spawn the audio director')
        actor.set_actor_label('Release Audio Director')
        actor.set_editor_property('tags', [OWNER, STABLE])
        actor.set_actor_enable_collision(False)
    checked = validate_director(actor)
    after = snapshot()
    original_directors = {name for name, state in baseline.items() if OWNER in state['tags']}
    for name, state in baseline.items():
        if name not in original_directors:
            require(after.get(name) == state, 'Unrelated actor changed: ' + name)
    allowed_names = (set(baseline) - original_directors) | {actor.get_name()}
    require(set(after) == allowed_names, 'Unexpected actor creation/removal')
    require(story_before == story_snapshot(), 'Story state/refs were changed')
    require(LEVEL.save_current_level(), 'Cannot save the additive director map')
    allowed_map = str(PROJECT / 'Content/Quest/Maps/Verdant_Desktop.umap')
    after_files = protect()
    for path, digest in before_files.items():
        require(path == allowed_map or after_files.get(path) == digest, 'Existing protected file changed: ' + path)
    old.update(success=True, signature=sig, namespace=folder, after=checked, reverted=False,
               wav_readback=wave_checks, class_paths={k: v.get_path_name() for k, v in classes.items()},
               baseline_preserved=True, runtime_compiled=True, runtime_playtested=False,
               packaged_playtested=False, listening_review=False, event_sfx_hooked=False,
               music_playback_enabled=False, manager_hud_or_story_graph_modified=False,
               asset_fingerprints={path: digest for path, digest in after_files.items()
                                   if Path(path).is_relative_to(PROJECT / 'Content/Release/Audio' / ('V_' + sig))},
               updated_utc=datetime.now(timezone.utc).isoformat())
    REPORT.write_text(json.dumps(old, indent=2), encoding='utf-8')
    return old


def apply():
    guard(write=True)
    settings = unreal.get_default_object(unreal.load_class(None, '/Script/BlueprintGraph.BlueprintEditorSettings'))
    promotion = settings.get_editor_property('bEnableTypePromotion')
    try:
        settings.set_editor_property('bEnableTypePromotion', False)
        return _apply()
    finally:
        settings.set_editor_property('bEnableTypePromotion', promotion)


def revert():
    guard(write=True)
    require(LEVEL.load_level(MAP), 'Cannot load the Release desktop map')
    old = report_read()
    require(old.get('success') and old.get('after'), 'No successful generated director baseline')
    matches = [actor for actor in actors() if actor.actor_has_tag(STABLE) or actor.actor_has_tag(OWNER)]
    require(len(matches) <= 1, 'Multiple directors found; preserve all')
    before = snapshot()
    before_story = story_snapshot()
    if matches:
        actor = matches[0]
        require(actor.actor_has_tag(OWNER) and not actor.actor_has_tag('TOSOY.ManualOverride'), 'Preserving manual/unowned director')
        require(actor.get_name() not in old.get('inferred_manual_names', []) and actor_snapshot(actor) == canonical_state(old['after']), 'Preserving inferred manual director')
        name = actor.get_name()
        require(ACTORS.destroy_actor(actor), 'Could not remove generated director')
        before.pop(name)
    require(before == snapshot() and before_story == story_snapshot(), 'Revert changed another actor/story field')
    require(LEVEL.save_current_level(), 'Cannot save audio revert')
    old['reverted'] = True
    REPORT.write_text(json.dumps(old, indent=2), encoding='utf-8')
    return {'success': True, 'director_removed': bool(matches), 'versioned_assets_retained_for_recovery': True}


def validate_saved():
    guard()
    old = report_read()
    require(old.get('success') and not old.get('reverted'), 'No applied native audio result')
    manifest = source_manifest()
    classes = {name: unreal.load_asset(path) for name, path in old['class_paths'].items()}
    for entry in manifest['assets']:
        category = 'Ambience' if entry['loop'] else ('Music' if entry['role'].startswith('MUS_') else 'SFX')
        wave_readback(unreal.load_asset(old['namespace'] + '/Waves/' + entry['role']), entry, classes[category])
    require(LEVEL.load_level(MAP), 'Cannot read back the desktop map')
    matches = [actor for actor in actors() if actor.actor_has_tag(OWNER)]
    require(len(matches) == 1, 'Director not unique in saved map')
    require(validate_director(matches[0]) == canonical_state(old['after']), 'Saved director differs from generated readback')
    return {'success': True, 'native_wave_count': 7, 'sound_class_count': 4, 'director_count': 1,
            'bed_component_count': 2, 'runtime_playtested': False, 'packaged_playtested': False}


if __name__ == '__main__':
    try:
        result = apply()
        require(result['success'], 'Audio actor preserved; no successful apply')
        validate_saved()
    except Exception:
        failure = {'success': False, 'error': traceback.format_exc(), 'runtime_playtested': False}
        (PROJECT / 'release_audio_import_failure.json').write_text(json.dumps(failure, indent=2), encoding='utf-8')
        raise
