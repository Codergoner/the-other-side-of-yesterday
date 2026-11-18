"""Queued native audio UI regression with actual master-mixer WAV evidence.

Requires imported ambience/director + authored audio menu, real audio mixer
(do not pass -nosound), and a dedicated short -UserDir. No asset/map writes.
Adds audio checks to the normal/future-only frontend regression. No raw corrupt
input or headset, loudspeaker listening, packaged or perceived-loudness claim.
"""
from pathlib import Path
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
if '-nosound' in unreal.SystemLibrary.get_command_line().lower():
    raise RuntimeError('Actual mixer verification cannot run with -nosound')
safe_path = root / 'Python/validate_release_frontend_safe.py'
safe_source = safe_path.read_text(encoding='utf-8')
ending = "exec(compile(source, str(root / 'Python/validate_release_frontend.py'), 'exec'), globals())"
if safe_source.count(ending) != 1:
    raise RuntimeError('Review the changed safe frontend wrapper')
# Build its reviewed source adaptation without starting its callbacks yet.
exec(compile(safe_source.replace(ending, 'AUDIO_BASE_SOURCE = source'), str(safe_path), 'exec'), globals())
source = AUDIO_BASE_SOURCE
audio_helpers = '''
def audio_director():
    actors=unreal.GameplayStatics.get_all_actors_with_tag(S['world'],'release.audio.director')
    if len(actors)!=1:raise RuntimeError('Expected exactly one owned native audio director')
    return actors[0]

def audio_value(name):return audio_director().get_editor_property(name)

def audio_components():
    return list(audio_director().get_components_by_class(unreal.AudioComponent))

def audio_current_component():
    return audio_director().get_editor_property('AudioPresent' if int(audio_value('CurrentEra'))==0 else 'AudioPast')

def mixer_record(label):
    import array, math, wave
    path=OUT/(label+'.wav')
    unreal.AudioMixerLibrary.start_recording_output(S['world'],.5,None)
    yield wait(.5)
    unreal.AudioMixerLibrary.stop_recording_output(S['world'],unreal.AudioRecordingExportType.WAV_FILE,label,str(OUT),None,None)
    yield until(lambda:path.exists() and path.stat().st_size>2000,'native mixer WAV '+label,10)
    with wave.open(str(path),'rb') as wav:
        width=wav.getsampwidth()
        if width not in [2,4]:raise RuntimeError('Unexpected native mixer WAV width')
        pcm=array.array('h' if width==2 else 'i');pcm.frombytes(wav.readframes(wav.getnframes()))
        scale=float(1<<(width*8-1))
        rms=math.sqrt(sum((n/scale)**2 for n in pcm)/max(1,len(pcm)))
        entry={'path':str(path),'rate':wav.getframerate(),'channels':wav.getnchannels(),'frames':wav.getnframes(),'rms':rms}
    REPORT.setdefault('native_mixer_recordings',[]).append(entry);write()
    return rms

def audio_settings_checks():
    # UE5.8 normally stops processing fully silent submixes, producing no
    # recording buffer at Master0. This documented process-local capture CVar
    # asks the mixer to render silence so zero-gain PCM can be measured.
    unreal.SystemLibrary.execute_console_command(S['world'],'au.NeverDisableSubmixes 1')
    REPORT['mixer_capture_condition']='au.NeverDisableSubmixes=1 in this QA process only; renders silent PCM, no saved config or gameplay graph change'
    click(8);yield wait(.25)
    check('Audio submenu has real gain/pause rows and labels music reserved',int(prop('ReleaseMenuScreen'))==4 and int(prop('ReleaseMenuCount'))==5 and 'reserved' in str(prop('ReleaseRow2')))
    yield until(lambda:bool(prop('ReleaseAudioReady')) and len(audio_components())==2,'native director ready',10)
    yield wait(1)
    check('Native ambience is actually playing',any(c.is_playing() for c in audio_components()))
    starts=int(audio_value('BedStartCount'));switches=int(audio_value('EraSwitchCount'))
    identities=[c.get_path_name() for c in audio_components()]
    baseline=yield from mixer_record('MasterBaseline')
    check('Actual native mixer baseline contains audio',baseline>1e-6)
    # Drive only visible row actions, including the explicit 100% -> 0% wrap.
    for unused in range(12):
        if float(prop('ReleaseMasterVolume'))<.0001:break
        click(0);yield wait(.2)
    else:raise RuntimeError('Master row never reached zero')
    yield wait(.4)
    muted=yield from mixer_record('MasterZero')
    check('Master zero attenuates actual mixer output',muted<max(1e-7,baseline*.05),{'baseline_rms':baseline,'zero_rms':muted})
    click(0);yield wait(.5)
    restored=yield from mixer_record('MasterRestored')
    check('Master unmute restores actual native output',restored>max(1e-7,muted*10))
    click(1);yield wait(.4)
    expected=float(prop('ReleaseMasterVolume'))*float(prop('ReleaseAmbienceVolume'))
    check('Actual director gain follows Master times Ambience',abs(float(audio_value('CurrentBedGain'))-expected)<.0001)
    click(2);yield wait(.2)
    check('Reserved Music value reaches the native director without inventing playback',abs(float(audio_value('MusicGain'))-float(prop('ReleaseMusicVolume')))<.0001 and len(audio_components())==2)
    check('Gain adjustments preserve the existing components and start counters',int(audio_value('BedStartCount'))==starts and int(audio_value('EraSwitchCount'))==switches and identities==[c.get_path_name() for c in audio_components()])
    current=bool(prop('ReleaseMuteWhenPaused'))
    click(3);yield wait(.2)
    check('Visible pause-mute row changes the actual director preference',bool(audio_value('MuteWhenPaused'))!=current)
    click(3);yield wait(.2)
    if not bool(prop('ReleaseMuteWhenPaused')):raise RuntimeError('Pause-on test requires its default enabled')
    check('Audio preferences save without a campaign pointer',prop('ReleaseProfileWritable') and 'saved' in str(prop('ReleaseMenuStatus')).lower() and not prop('ReleaseSessionStarted'))
    yield screenshot('AudioSettings')
    click(4);yield wait(.2)
    if int(prop('ReleaseMenuScreen'))!=1:raise RuntimeError('Audio Back did not return to Settings')

def audio_pause_checks():
    starts=int(audio_value('BedStartCount'))
    call('OpenPause');yield wait(.25)
    check('Game pause actually pauses the active ambience component',bool(audio_value('CurrentMuted')) and 'paused' in str(audio_current_component().get_play_state()).lower(),{'active_state':str(audio_current_component().get_play_state()),'all_states':[str(c.get_play_state()) for c in audio_components()],'muted':bool(audio_value('CurrentMuted'))})
    call('CloseModal');yield wait(.25)
    check('Resume keeps ambience playing without restarting loops',not bool(audio_value('CurrentMuted')) and any(c.is_playing() for c in audio_components()) and int(audio_value('BedStartCount'))==starts)
    call('ReleaseShowMain');yield wait(.2)
    click(2);yield wait(.2);click(8);yield wait(.2);click(3);yield wait(.2)
    if bool(prop('ReleaseMuteWhenPaused')):raise RuntimeError('Visible audio row did not disable pause muting')
    click(4);yield wait(.2);click(9);yield wait(.2);call('ReleaseResume');yield wait(.2)
    call('OpenPause');yield wait(.25)
    check('Disabling pause muting keeps native components playing during game pause',not bool(audio_value('CurrentMuted')) and any(c.is_playing() and 'paused' not in str(c.get_play_state()).lower() for c in audio_components()) and int(audio_value('BedStartCount'))==starts)
    call('CloseModal');yield wait(.2)
    call('ReleaseShowMain');yield wait(.2);click(2);yield wait(.2);click(8);yield wait(.2);click(3);yield wait(.2)
    click(4);yield wait(.2);click(9);yield wait(.2);call('ReleaseResume');yield wait(.2)

'''
if source.count('def scenario():') != 1:
    raise RuntimeError('Expected one reviewed frontend scenario')
source = source.replace('def scenario():', audio_helpers + '\ndef scenario():')
source = source.replace('    user = unreal.GameUserSettings.get_game_user_settings()',
                        '    yield from audio_settings_checks()\n    user = unreal.GameUserSettings.get_game_user_settings()')
marker = "    check('Skip recollections commits only the new campaign', prop('IntroSeen') and not prop('IntroActive') and prop('ReleaseWriteAllowed'))"
if source.count(marker) != 1:
    raise RuntimeError('Review changed New Game acceptance point')
source = source.replace(marker, marker + '\n    yield from audio_pause_checks()')
source = source.replace('release_frontend_safe_validation.json', 'release_audio_settings_validation.json')
source = source.replace("'validation/release_frontend_safe'", "'validation/release_audio_settings'")
source = source.replace("REPORT['corrupt_save_tested']=False", "REPORT['corrupt_save_tested']=False\nREPORT['audio_output_scope']='Actual editor master-mixer WAV, two existing ambience components, native UI actions; no loudspeaker/headset/package or perceived-loudness claim.'")
exec(compile(source, str(root / 'Python/validate_release_frontend.py'), 'exec'), globals())
