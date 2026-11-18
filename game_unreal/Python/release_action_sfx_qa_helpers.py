"""Test-only helpers spliced into the existing native story-audio QA harness.

Definitions only. Not imported or shipped as gameplay logic. All observations
come from actual Blueprint instances; only existing menu preferences are driven.
"""


def sfx_actor():
    actors = unreal.GameplayStatics.get_all_actors_with_tag(S['world'], 'release.audio.action_sfx')
    if len(actors) != 1:
        raise RuntimeError('Expected exactly one installed native action-SFX actor')
    return actors[0]


def sfx_state():
    actor = sfx_actor()
    components = list(actor.get_components_by_class(unreal.AudioComponent))
    component = actor.get_editor_property('ActionChannel')
    sound = component.get_editor_property('sound')
    return {'actor': actor.get_path_name(), 'components': sorted(c.get_path_name() for c in components),
        'channel': component.get_path_name(), 'plays': int(actor.get_editor_property('CuePlayCount')),
        'suppressed': int(actor.get_editor_property('CueSuppressedCount')),
        'unknown': int(actor.get_editor_property('CueUnknownCount')),
        'cue': str(actor.get_editor_property('CurrentCueName')), 'playing': bool(component.is_playing()),
        'play_state': str(component.get_play_state()), 'sound': sound.get_path_name() if sound else None,
        'gain': float(component.get_editor_property('volume_multiplier')),
        'last_cue_real_seconds': float(actor.get_editor_property('LastCueRealSeconds')),
        'master': float(prop('ReleaseMasterVolume')),
        'ambience': float(prop('ReleaseAmbienceVolume')),
        'paused': bool(unreal.GameplayStatics.is_game_paused(S['world'])),
        'mute_when_paused': bool(prop('ReleaseMuteWhenPaused'))}


def sfx_progress():
    return {name: plain(prop(name)) for name in ['WatchCalibrated', 'CalibrationTests', 'SelectedEra',
        'EraIndex', 'LinenState', 'CanvasOwned', 'CanvasPlan', 'StormCover', 'HealerTrust', 'TrustEventIds']}


def sfx_expected(before, after, name):
    # This observes successful state changes caused by the existing producer;
    # it never assigns those fields and never turns restored progress into cues.
    if name in ['ReleaseNewGame', 'ReleaseContinue', 'LoadProgress', 'RestoreSafeScene',
                'ApplyState', 'ApplyWorldState', 'SaveProgress', '_SaveCopy']:
        return []
    cues = []
    if not before['WatchCalibrated'] and after['WatchCalibrated']:
        cues.append('calibration')
    if name == 'RotateDial' and before['SelectedEra'] != after['SelectedEra']:
        cues.append('tick')
    if (before['LinenState'], after['LinenState']) in [(1, 2), (2, 3)]:
        cues.append('cloth')
    if not before['CanvasOwned'] and after['CanvasOwned']:
        cues.append('cloth')
    if before['CanvasOwned'] and not after['CanvasOwned'] and before['StormCover'] == 0 and after['StormCover'] in [1, 2]:
        cues.append('cloth')
    return cues


def sfx_action(name, *args):
    before, progress = sfx_state(), sfx_progress()
    result = S['manager'].call_method(name, args=tuple(args))
    after, committed = sfx_state(), sfx_progress()
    expected = sfx_expected(progress, committed, name)
    plays = after['plays']-before['plays']
    suppressed = after['suppressed']-before['suppressed']
    check('One native action channel survives '+name,
          before['components'] == after['components'] and len(after['components']) == 1 and
          after['channel'] == before['channel'] and after['unknown'] == before['unknown'], after)
    check('Actual producer requests match success edges: '+name,
          plays+suppressed == len(expected), {'before': before, 'after': after,
          'progress_before': progress, 'progress_after': committed, 'expected_cues': expected})
    if expected and plays:
        check('Accepted producer uses the expected native cue: '+name,
              after['cue'] == expected[-1], after)
    if expected and before['master'] < .0001:
        check('Master zero suppresses an actual successful producer', plays == 0 and suppressed == len(expected), after)
    if not expected:
        check('Rejected/repeated/nonproducer action adds no one-shot: '+name, plays == 0 and suppressed == 0, after)
    row = {'action': name, 'args': [str(a) for a in args], 'expected_cues': expected,
        'play_delta': plays, 'suppressed_delta': suppressed, 'before': before, 'after': after,
        'progress_before': progress, 'progress_after': committed}
    S['record'].setdefault('action_sfx_trace', []).append(row)
    if name == 'ConfirmWatch' and int(prop('Mode')) != 7:
        S['rejected_confirm_sfx'] = after
    write()
    return result


def sfx_boot_silence(label):
    yield wait(.25)
    state = sfx_state()
    check('New Game/Continue/restore starts no one-shot: '+label,
          state['plays'] == 0 and state['suppressed'] == 0 and state['unknown'] == 0 and
          not state['playing'] and len(state['components']) == 1, state)
    old_progress = sfx_progress()
    action('ApplyWorldState')
    yield wait(.2)
    after = sfx_state()
    check('Real committed ApplyWorldState remains silent without rewards',
          after['plays'] == 0 and after['suppressed'] == 0 and not after['playing'] and
          sfx_progress() == old_progress, {'before': state, 'after': after})
    S['record'].setdefault('sfx_boot_states', []).append({'label': label, **after})
    write()


def sfx_finite_assets():
    rows = []
    for member, seconds in [('WatchTickAsset', .18), ('CalibrationAsset', 2.8),
                            ('TransitionAsset', 3.4), ('ClothAsset', 1.25)]:
        wave = sfx_actor().get_editor_property(member)
        row = {'member': member, 'asset': wave.get_path_name(),
            'duration': float(wave.get_editor_property('duration')),
            'looping': bool(wave.get_editor_property('looping')),
            'channels': int(wave.get_editor_property('num_channels')),
            'rate': int(wave.get_editor_property('imported_sample_rate'))}
        check('Native action source is finite stereo48k: '+member,
              not row['looping'] and math.isfinite(row['duration']) and
              abs(row['duration']-seconds) < .001 and row['channels'] == 2 and row['rate'] == 48000, row)
        rows.append(row)
    S['record']['action_sfx_native_waves'] = rows
    write()


def sfx_rejected_confirm_settled():
    before = S.get('rejected_confirm_sfx')
    if before is None:
        raise RuntimeError('Expected a real rejected ConfirmWatch observation')
    yield wait(.5)
    after = sfx_state()
    check('Rejected destination never produces a delayed transition cue',
          after['plays'] == before['plays'] and after['suppressed'] == before['suppressed'] and
          int(prop('Mode')) != 7, {'before': before, 'after': after})


def sfx_finite_tail(before, seconds, label):
    active = sfx_state()
    yield wait(seconds)
    after = sfx_state()
    check('Actual finite one-shot ends without replay '+label,
          active['plays'] == before['plays']+1 and after['plays'] == active['plays'] and
          after['suppressed'] == active['suppressed'] and not after['playing'],
          {'before': before, 'active': active, 'settled': after})


def sfx_pcm(label, trigger=None, seconds=.65):
    import array
    import wave
    folder = SCREEN_DIR/'action_sfx_pcm'
    folder.mkdir(exist_ok=True)
    name = S['record']['case']['id']+'_'+str(len(REPORT.setdefault('action_sfx_pcm', [])))+'_'+label
    target = folder/(name+'.wav')
    before = sfx_state()
    unreal.AudioMixerLibrary.start_recording_output(S['world'], seconds, None)
    if trigger is not None:
        trigger()
    yield wait(seconds)
    unreal.AudioMixerLibrary.stop_recording_output(S['world'], unreal.AudioRecordingExportType.WAV_FILE,
                                                  name, str(folder), None, None)
    yield until(lambda: target.exists() and target.stat().st_size > 2000, 'native action PCM '+label, 10)
    with wave.open(str(target), 'rb') as wav:
        width = wav.getsampwidth()
        if width not in [2, 4]:
            raise RuntimeError('Unsupported native mixer PCM sample width')
        pcm = array.array('h' if width == 2 else 'i')
        pcm.frombytes(wav.readframes(wav.getnframes()))
        scale = float(1 << (width*8-1))
        rms = math.sqrt(sum((sample/scale)**2 for sample in pcm)/max(1, len(pcm)))
        row = {'label': label, 'file': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'rate': wav.getframerate(), 'channels': wav.getnchannels(), 'frames': wav.getnframes(),
            'sample_width': width, 'rms': rms, 'peak': max((abs(v)/scale for v in pcm), default=0),
            'before': before, 'after': sfx_state(), 'evidence': 'Actual native master mixer; ambience zero via actual HUD'}
    REPORT['action_sfx_pcm'].append(row)
    check('Actual action mixer recording is finite stereo48k '+label,
          row['rate'] == 48000 and row['channels'] == 2 and row['frames'] > 12000 and math.isfinite(rms), row)
    write()
    return row


def sfx_audio_preferences(master, ambience, mute_when_paused):
    # Synthetic callbacks to existing visible native rows; no direct property,
    # profile or saved-story edits. Preferences remain within the isolated run.
    action('ReleaseShowMain'); yield wait(.2)
    audio_click(2); yield wait(.2); audio_click(8); yield wait(.2)
    check('SFX QA opens the real Audio settings rows',
          int(prop('ReleaseMenuScreen')) == 4 and int(prop('ReleaseMenuCount')) == 5)
    for field, index, target in [('ReleaseMasterVolume', 0, master), ('ReleaseAmbienceVolume', 1, ambience)]:
        for unused in range(13):
            if abs(float(prop(field))-target) < .0001:
                break
            audio_click(index); yield wait(.2)
        else:
            raise RuntimeError('Native volume row did not reach requested test preference '+field)
    if bool(prop('ReleaseMuteWhenPaused')) != mute_when_paused:
        audio_click(3); yield wait(.2)
    check('Native audio rows retained SFX QA preferences',
          abs(float(prop('ReleaseMasterVolume'))-master) < .0001 and
          abs(float(prop('ReleaseAmbienceVolume'))-ambience) < .0001 and
          bool(prop('ReleaseMuteWhenPaused')) == mute_when_paused)
    audio_click(4); yield wait(.2); audio_click(9); yield wait(.2)
    action('ReleaseResume'); yield wait(.3)
    check('Native settings return to the active playthrough',
          not prop('ReleaseMenuActive') and int(prop('Mode')) == 0)


def sfx_watch_pcm_suite():
    # Run once at the genuine calibrated departure. Preserve the successful
    # quest path and restore native preferences before the real departure dial.
    prior = snapshot()
    preferences = (float(prop('ReleaseMasterVolume')), float(prop('ReleaseAmbienceVolume')),
                   bool(prop('ReleaseMuteWhenPaused')))
    beds = audio_state()
    check('PCM producer test starts from genuine two-test calibration',
          prop('WatchCalibrated') and int(prop('CalibrationTests')) == 2 and int(prop('EraIndex')) == 0)
    unreal.SystemLibrary.execute_console_command(S['world'], 'au.NeverDisableSubmixes 1')
    yield from sfx_audio_preferences(1., 0., True)
    # Allow the real finite calibration success cue to finish before silence.
    yield wait(3.6)
    action('OpenWatch'); yield wait(.2)
    check('Native watch is available for the accepted dial test', int(prop('Mode')) == 4)
    quiet = yield from sfx_pcm('NoCueBaseline')
    check('Actual ambience-zero baseline is silent', quiet['rms'] < 1e-7, quiet)
    cue = yield from sfx_pcm('AcceptedNativeRotateDial', lambda: action('RotateDial', -1))
    check('Real accepted dial produces one audible tick',
          cue['after']['plays'] == cue['before']['plays']+1 and cue['after']['cue'] == 'tick' and
          cue['rms'] > max(1e-6, quiet['rms']*10), cue)
    repeated = yield from sfx_pcm('RepeatedSameDirectionDial', lambda: action('RotateDial', -1))
    check('Same-direction dial repeat adds no cue or PCM',
          repeated['after']['plays'] == repeated['before']['plays'] and repeated['rms'] < 1e-7, repeated)
    action('RotateDial', 1); yield wait(.4)
    yield from sfx_audio_preferences(0., 0., True)
    action('OpenWatch'); yield wait(.2)
    muted = yield from sfx_pcm('MasterZeroAcceptedDial', lambda: action('RotateDial', -1))
    check('Master0 suppresses the real accepted producer and actual PCM',
          muted['after']['plays'] == muted['before']['plays'] and
          muted['after']['suppressed'] == muted['before']['suppressed']+1 and muted['rms'] < 1e-7, muted)
    yield from sfx_audio_preferences(1., 0., True)
    action('OpenPause'); yield wait(.2)
    check('Native OpenPause actually pauses the world', unreal.GameplayStatics.is_game_paused(S['world']))
    # A real producer cannot commit a dial change while paused. Separately call
    # the actual native actor to verify its own StartCue paused-mute gate.
    rejected = yield from sfx_pcm('PausedRejectedDial', lambda: action('RotateDial', -1))
    check('Paused dial is rejected without a cue or actual PCM',
          rejected['after']['plays'] == rejected['before']['plays'] and rejected['rms'] < 1e-7, rejected)
    paused = yield from sfx_pcm('PausedNativeActorRequest',
        lambda: sfx_actor().call_method('PlayCue', args=(unreal.Name('cloth'),)))
    check('Native action actor itself suppresses a request with paused mute',
          paused['after']['plays'] == paused['before']['plays'] and
          paused['after']['suppressed'] == paused['before']['suppressed']+1 and paused['rms'] < 1e-7, paused)
    counts = sfx_state()
    action('CloseModal'); yield wait(.4)
    check('Pause resume adds no cue replay', sfx_state()['plays'] == counts['plays'] and not sfx_state()['playing'])
    yield from sfx_audio_preferences(*preferences)
    stable = {key: value for key, value in prior.items() if key != 'ReturnClockSeconds'}
    check('Native SFX PCM/preferences tests do not grant or repeat quest rewards',
          all(plain(prop(key)) == value for key, value in stable.items()), snapshot())
    after_beds = audio_state()
    check('Action tests preserve the two ambience components without restart',
          after_beds['component_paths'] == beds['component_paths'] and after_beds['starts'] == beds['starts'] and
          after_beds['switches'] == beds['switches'], {'before': beds, 'after': after_beds})
    action('OpenWatch'); yield wait(.2)


def sfx_transition_after(before, label):
    after = sfx_state()
    check('Successful destination commits exactly one native transition cue '+label,
          after['plays'] == before['plays']+1 and after['suppressed'] == before['suppressed'] and
          after['cue'] == 'transition' and after['components'] == before['components'],
          {'before': before, 'after': after})
    # Verify the actual component stops after the finite3.4s asset. This is an
    # observed native component tail, not a waveform-duration-only inference.
    yield wait(3.7)
    settled = sfx_state()
    check('Finite transition tail ends and steady ticks add no replay '+label,
          not settled['playing'] and settled['plays'] == after['plays'] and
          settled['suppressed'] == after['suppressed'], settled)
    S['record'].setdefault('action_sfx_transitions', []).append({'label': label, 'before': before, 'after': after, 'settled': settled})
    write()
