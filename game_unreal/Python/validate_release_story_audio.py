"""Queued four-route story regression plus real era/load/mute audio evidence.

Root owns the native writer queue. Run only with -ReleaseStoryQA
-ReleaseStoryAudioQA and an isolated short -UserDir, D3D11, and audio enabled.
The existing story harness supplies actual New Game/Continue/ConfirmWatch
actions. This file never writes an era/story flag or changes a shipped graph.
No physical-input, packaged-game, loudspeaker or final-trailer claim.
"""
from pathlib import Path
import ast
import hashlib
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
command = unreal.SystemLibrary.get_command_line()
if not unreal.SystemLibrary.parse_param(command, 'ReleaseStoryAudioQA'):
    raise RuntimeError('Root queued -ReleaseStoryAudioQA is required')
if '-nosound' in command.lower() or '-nullrhi' in command.lower():
    raise RuntimeError('Actual audio/viewport QA requires D3D11 and enabled sound')
AUDIO_PIE_SETTINGS=unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.LevelEditorPlaySettings'))
AUDIO_PIE_SETTINGS_BEFORE={n:AUDIO_PIE_SETTINGS.get_editor_property(n) for n in ['EnableGameSound','SoloAudioInFirstPIEClient']}
AUDIO_PIE_SETTINGS.set_editor_property('EnableGameSound',True)
AUDIO_PIE_SETTINGS.set_editor_property('SoloAudioInFirstPIEClient',False)
AUDIO_MISC_SETTINGS=unreal.get_default_object(unreal.load_class(None,'/Script/UnrealEd.LevelEditorMiscSettings'))
AUDIO_BACKGROUND_BEFORE=AUDIO_MISC_SETTINGS.get_editor_property('bAllowBackgroundAudio')
AUDIO_MISC_SETTINGS.set_editor_property('bAllowBackgroundAudio',True)
wrapper_path = root / 'Python/validate_release_story.py'
wrapper = wrapper_path.read_text(encoding='utf-8')
ending = "exec(compile(source, str(root / 'Python/validate_brief_m2.py'), 'exec'), globals())"
if wrapper.count(ending) != 1:
    raise RuntimeError('Review changed release story wrapper before adapting')
# Let the existing checked adaptation construct its source and unsaved profile
# fixture, but do not start its callback until these additive checks are ready.
exec(compile(wrapper.replace(ending, 'AUDIO_STORY_SOURCE = source'), str(wrapper_path), 'exec'), globals())
source = AUDIO_STORY_SOURCE


def replace_once(old, new):
    global source
    if source.count(old) != 1:
        raise RuntimeError('Changed story audio acceptance point: ' + old[:120])
    source = source.replace(old, new)


audio_helpers = r'''
def audio_director():
    actors = unreal.GameplayStatics.get_all_actors_with_tag(S['world'], 'release.audio.director')
    if len(actors) != 1: raise RuntimeError('Expected exactly one native audio director')
    return actors[0]

def audio_components():
    return list(audio_director().get_components_by_class(unreal.AudioComponent))

def audio_state():
    actor = audio_director()
    components = audio_components()
    rows = []
    for member in ['AudioPresent', 'AudioPast']:
        component = actor.get_editor_property(member)
        sound = component.get_editor_property('sound')
        rows.append({'member':member, 'path':component.get_path_name(),
                     'sound':sound.get_path_name() if sound else None,
                     'playing':bool(component.is_playing()), 'state':str(component.get_play_state())})
    return {'director':actor.get_path_name(), 'component_count':len(components),
            'component_paths':sorted(c.get_path_name() for c in components),
            'era':int(actor.get_editor_property('CurrentEra')),
            'starts':int(actor.get_editor_property('BedStartCount')),
            'switches':int(actor.get_editor_property('EraSwitchCount')),
            'gain':float(actor.get_editor_property('CurrentBedGain')),
            'muted':bool(actor.get_editor_property('CurrentMuted')), 'components':rows}

def audio_record(label):
    import array, wave
    folder = SCREEN_DIR / 'audio'; folder.mkdir(exist_ok=True)
    serial = len(REPORT.setdefault('native_mixer_recordings', []))
    name = S['record']['case']['id'] + '_' + str(serial) + '_' + label
    target = folder / (name + '.wav')
    unreal.AudioMixerLibrary.start_recording_output(S['world'], .5, None)
    yield wait(.5)
    unreal.AudioMixerLibrary.stop_recording_output(S['world'], unreal.AudioRecordingExportType.WAV_FILE,
                                                  name, str(folder), None, None)
    yield until(lambda:target.exists() and target.stat().st_size > 2000, 'actual native audio WAV ' + label, 10)
    with wave.open(str(target), 'rb') as wav:
        width = wav.getsampwidth()
        if width not in [2, 4]: raise RuntimeError('Unexpected native mixer PCM width')
        pcm = array.array('h' if width == 2 else 'i'); pcm.frombytes(wav.readframes(wav.getnframes()))
        scale = float(1 << (width*8-1))
        rms = math.sqrt(sum((sample/scale)**2 for sample in pcm) / max(1, len(pcm)))
        row = {'path':str(target), 'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
               'rate':wav.getframerate(), 'channels':wav.getnchannels(), 'frames':wav.getnframes(),
               'sample_width':width, 'rms':rms, 'peak':max((abs(sample)/scale for sample in pcm), default=0),
               'audio_state':audio_state(), 'story_era':int(prop('EraIndex'))}
    REPORT['native_mixer_recordings'].append(row); write()
    check('Actual mixer capture is finite 48k stereo PCM: ' + label,
          row['rate'] == 48000 and row['channels'] == 2 and row['frames'] > 12000 and math.isfinite(rms), row)
    return rms

def audio_settled(label, expected_era=None, record_pcm=False):
    # Headless repeated PIE can leave the editor device active after a world
    # restart. Route this QA process to its ACTUAL current world/controller.
    unreal.SystemLibrary.execute_console_command(S['world'],'au.Debug.SoloAudio',S['controller'])
    REPORT['editor_audio_device_condition']='Current actual PIE world selected with transient au.Debug.SoloAudio and AllowBackgroundAudio=true; original editor values restored; no audio assets/gains or config writes'
    if expected_era is None: expected_era = int(prop('EraIndex'))
    yield until(lambda:int(audio_director().get_editor_property('CurrentEra')) == expected_era,
                'native ambience era ' + label, 10)
    # The authored crossfade is .8s. Check after the old bed has finished its
    # envelope; two simultaneously playing components during the fade are valid.
    yield wait(1.1)
    row = audio_state()
    active = row['components'][expected_era]
    inactive = row['components'][1-expected_era]
    expected_suffix = 'Amb_Coast_Present_60s' if expected_era == 0 else 'Amb_Coast_Past_60s'
    check('One director retains exactly its two persistent beds: ' + label,
          row['component_count'] == 2 and len(set(row['component_paths'])) == 2, row)
    check('Actual settled ambience matches the committed era: ' + label,
          row['era'] == expected_era and active['playing'] and not inactive['playing'] and
          active['sound'] and active['sound'].endswith('.' + expected_suffix), row)
    expected_gain = float(prop('ReleaseMasterVolume')) * float(prop('ReleaseAmbienceVolume'))
    check('Actual era mix retains saved Master times Ambience: ' + label,
          abs(row['gain']-expected_gain) < .0001, row)
    check('Each era switch has exactly one start, with one initial bed: ' + label,
          row['starts'] == row['switches']+1, row)
    yield wait(.25)
    steady = audio_state()
    check('Steady ticks add no duplicate starts or components: ' + label,
          steady['component_paths'] == row['component_paths'] and
          steady['starts'] == row['starts'] and steady['switches'] == row['switches'], steady)
    S['record'].setdefault('audio_states', []).append({'label':label, **steady}); write()
    if record_pcm:
        rms = yield from audio_record(label)
        expected_audible = expected_gain > .0001 and not steady['muted']
        check('Actual native era PCM is audible when its saved gain permits: ' + label,
              rms > 1e-6 if expected_audible else rms < 1e-7, {'rms':rms, 'audible_expected':expected_audible})
    return steady

def audio_old_components_stopped(old):
    rows = []
    for component in old:
        retired_proxy = None
        try:
            valid = bool(unreal.SystemLibrary.is_valid(component))
        except TypeError as error:
            # EndPIE destroys the native world/component before Python drops
            # its proxy. The binding rejects that exact expired UObject.
            if 'Cannot nativize' not in str(error) or 'AudioComponent' not in str(error): raise
            valid = False; retired_proxy = str(error)
        row = {'valid':valid, 'playing':False, 'destroyed_native_proxy_diagnostic':retired_proxy}
        if valid:
            row.update(path=component.get_path_name(), playing=bool(component.is_playing()))
        rows.append(row)
    check('Ending the old world stops its actual audio components', all(not row['playing'] for row in rows), rows)

def audio_click(index):
    S['controller'].get_hud().call_method('ReceiveHitBoxClick', args=(unreal.Name('ReleaseRow'+str(index)),))

def audio_mute_unmute():
    # Drive the real HUD settings rows in the first route, after its genuine
    # Continue. The callbacks are synthetic; no physical mouse claim is made.
    before = audio_state(); saved_master = float(prop('ReleaseMasterVolume')); old_story = snapshot()
    action('ReleaseShowMain'); yield wait(.2)
    audio_click(2); yield wait(.2); audio_click(8); yield wait(.2)
    check('Existing native HUD opens Audio during the real campaign',
          int(prop('ReleaseMenuScreen')) == 4 and int(prop('ReleaseMenuCount')) == 5)
    unreal.SystemLibrary.execute_console_command(S['world'], 'au.NeverDisableSubmixes 1')
    REPORT['silent_pcm_capture_condition'] = 'Process-local au.NeverDisableSubmixes=1; transient EnableGameSound=true/SoloAudioInFirstPIEClient=false restored at finish; no asset/config write'
    baseline = yield from audio_record('MenuMasterBaseline')
    check('Current saved mix produces real baseline PCM', baseline > 1e-6, baseline)
    for unused in range(12):
        if float(prop('ReleaseMasterVolume')) < .0001: break
        audio_click(0); yield wait(.2)
    else: raise RuntimeError('Native Master row never reached zero')
    yield wait(.4)
    muted = yield from audio_record('MenuMasterZero')
    check('HUD Master zero silences actual PCM', muted < max(1e-7, baseline*.05), {'baseline':baseline, 'muted':muted})
    for unused in range(12):
        if abs(float(prop('ReleaseMasterVolume'))-saved_master) < .0001: break
        audio_click(0); yield wait(.2)
    else: raise RuntimeError('Native Master row could not restore its saved value')
    yield wait(.4)
    restored = yield from audio_record('MenuMasterRestored')
    check('Restoring saved Master gain restores real PCM', restored > max(1e-6, muted*10), restored)
    after = audio_state()
    check('Mute/unmute never recreates or restarts an ambience bed',
          after['component_paths'] == before['component_paths'] and after['starts'] == before['starts'] and
          after['switches'] == before['switches'], after)
    audio_click(4); yield wait(.2); audio_click(9); yield wait(.2); action('ReleaseResume'); yield wait(.2)
    stable_fields = {key:value for key,value in old_story.items() if key != 'ReturnClockSeconds'}
    check('Audio HUD actions do not alter campaign progress', all(plain(prop(key)) == value for key,value in stable_fields.items()))
    yield from audio_settled('after native HUD mute/unmute', record_pcm=False)

'''

replace_once('def complete_finish():', 'def complete_finish():\n    for name,value in AUDIO_PIE_SETTINGS_BEFORE.items(): AUDIO_PIE_SETTINGS.set_editor_property(name,value)\n    AUDIO_MISC_SETTINGS.set_editor_property("bAllowBackgroundAudio",AUDIO_BACKGROUND_BEFORE)')
replace_once('def check_era_boundaries(era):', audio_helpers + '\ndef check_era_boundaries(era):')
# Every fresh/restored world uses the established production manager path.
replace_once("    prepare_world();yield wait(.12)\n    restored=snapshot()",
             "    prepare_world();yield wait(.12)\n    yield from audio_settled('Continue: '+label, expected['EraIndex'])\n    restored=snapshot()")
replace_once("    yield until(ready,'legacy A SaveGame migration');prepare_world();yield wait(.12)",
             "    yield until(ready,'legacy A SaveGame migration');prepare_world();yield wait(.12)\n    yield from audio_settled('pinned legacy Continue')")
replace_once("        yield until(ready,'native player and dialogue manager');prepare_world();yield wait(.10)",
             "        yield until(ready,'native player and dialogue manager');prepare_world();yield wait(.10)\n        yield from audio_settled('fresh New Game')")
replace_once("    previous=int(prop('EraIndex'))\n    action('ConfirmWatch')",
             "    previous=int(prop('EraIndex'))\n    before_audio=audio_state()\n    action('ConfirmWatch')")
replace_once("    yield from settle_transition(expected_era)",
             """    yield from settle_transition(expected_era)
    after_audio=yield from audio_settled('actual ConfirmWatch '+str(expected_era), expected_era,
                                        record_pcm=(S['record']['case'] is CASES[0]))
    check('Real ConfirmWatch preserves component IDs and adds one era switch/start',
          after_audio['component_paths']==before_audio['component_paths'] and
          after_audio['starts']==before_audio['starts']+1 and
          after_audio['switches']==before_audio['switches']+1,
          {'before':before_audio,'after':after_audio})""")
replace_once("    LEVEL.editor_request_end_play();yield until(lambda:not LEVEL.is_in_play_in_editor(),'stop PIE for '+label)",
             """    old_audio_components=audio_components()
    LEVEL.editor_request_end_play();yield until(lambda:not LEVEL.is_in_play_in_editor(),'stop PIE for '+label)
    audio_old_components_stopped(old_audio_components)""")
replace_once("        early=snapshot();yield from restart_and_check(early,'early present after recollections')",
             """        early=snapshot();yield from restart_and_check(early,'early present after recollections')
        if case is CASES[0]: yield from audio_mute_unmute()""")

# Distinct evidence files preserve the established StoryQA output. This remains
# the full four-route story suite, with additional checks inside the same run.
for old, new in {
    'release_story_runtime_validation.json':'release_story_audio_validation.json',
    "'release_story'":"'release_story_audio'",
    'YRStoryQA_':'YRAudioStoryQA_',
    'RELEASE_STORY_RUNTIME_VALIDATION':'RELEASE_STORY_AUDIO_VALIDATION',
}.items():
    if old not in source: raise RuntimeError('Missing additive audio report label: ' + old)
    source = source.replace(old, new)
replace_once("REPORT['native_save_guard_active']=", "REPORT['audio_qa_source_sha256']='" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest() + "'\nREPORT['audio_qa_scope']='Actual native eras from real ConfirmWatch and Continue; persistent component/counter assertions plus real master-mixer PCM. No direct era/story flag writes; synthetic HUD callbacks; no packaged/physical/loudspeaker/trailer claim.'\nREPORT['native_save_guard_active']=")

# Source syntax is checked before registering native callbacks. The expanded
# exact source is retained for debugging, without writing any native asset.
ast.parse(source)
expanded_folder = root / 'validation/release_story_audio_source'
expanded_folder.mkdir(parents=True, exist_ok=True)
expanded_file = expanded_folder / 'expanded_current.py'
expanded_file.write_text(source, encoding='utf-8')
exec(compile(source, str(root / 'Python/validate_brief_m2.py'), 'exec'), globals())
