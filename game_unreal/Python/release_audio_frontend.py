"""Source-only native menu/profile bridge to the owned ambience director.

Music gain is reserved while the audio director has no music playback route.
No Play/Stop/FadeIn calls live here: UI updates call the director's SetMixGains.
"""
import json
import unreal
import opening_graph as og
from release_frontend_graph import Flow, merge, reset_function, MATH, GS, STR


def resolve_audio_class(project):
    path = project / 'release_audio_import_report.json'
    result = None
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('success') and not data.get('reverted'):
            package = data['namespace'] + '/BP_ReleaseAudioDirector'
            asset = unreal.load_asset(package)
            if asset and unreal.EditorAssetLibrary.get_metadata_tag(asset, 'Release.Audio.Owner') == 'TOSOY.ReleaseAudioOwned':
                result = package + '.BP_ReleaseAudioDirector_C'
                if not unreal.load_class(None, result):
                    raise RuntimeError('Imported audio director generated class is unavailable')
    if unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseAudioFrontendRequired') and result is None:
        raise RuntimeError('Native audio import must succeed before this required audio frontend pass')
    return result


def render_audio_menu(f):
    f.set('ReleaseMenuTitle', 'Audio')
    f.set('ReleaseMenuBody', f.select(
        'Ambience controls connected. Click a volume row; 100% wraps to 0%.\nMusic volume is saved for future music cues.',
        'Audio playback is unavailable in this scene. Preferences can still be saved.\nMusic volume is reserved for future music cues.', f.var('ReleaseAudioReady')))
    f.set('ReleaseMenuCount', 5); f.set('ReleaseMenuTop', .34)
    for index, (name, label) in enumerate([('MasterVolume', 'Master: '), ('AmbienceVolume', 'Ambience: '), ('MusicVolume', 'Music (reserved): ')]):
        percent = f.data(MATH + 'Round', A=f.data(MATH + 'Multiply_DoubleDouble', A=f.var('Release' + name), B=100.0))
        text = f.data(STR + 'Conv_IntToString', InInt=percent)
        f.set('ReleaseRow' + str(index), f.text(label, f.text(text, '%')))
    f.set('ReleaseRow3', f.select('Pause ambience with game pause: On', 'Pause ambience with game pause: Off', f.var('ReleaseMuteWhenPaused')))
    f.set('ReleaseRow4', 'Back')


def build_audio_functions(bp, profile, profile_class, prefs, audio_class):
    def fn(name, params=None):
        return Flow(reset_function(bp, name, params))
    f = fn('ReleaseApplyAudio')
    f.set('ReleaseAudioReady', False)
    if audio_class:
        actors = f.data(GS + 'GetAllActorsWithTag', 'OutActors', Tag='release.audio.director')
        count = f.data('/Script/Engine.KismetArrayLibrary.Array_Length', TargetArray=actors)
        single, unavailable = f.branch(f.eq(count, 1))
        actor = single.data('/Script/Engine.KismetArrayLibrary.Array_Get', 'Item', TargetArray=actors, Index=0)
        cast = single.g.cast(audio_class, actor)
        og.link(single.cur, og.pin_in(cast))
        ready = Flow(single.g, og.pin_out(cast))
        ready.call(audio_class + ':SetMixGains', **{'self': ready.g.cast_value(cast),
            'Master': ready.var('ReleaseMasterVolume'), 'Ambience': ready.var('ReleaseAmbienceVolume'),
            'Music': ready.var('ReleaseMusicVolume'), 'MuteOnPause': ready.var('ReleaseMuteWhenPaused')})
        ready.set('ReleaseAudioReady', True)

    # Existing profile guard is authoritative. This copies preferences only,
    # never ActiveSlot/story fields, and does not make a damaged index writable.
    f = fn('ReleasePersistPreferences')
    permitted, blocked = f.branch(f.and_(f.var('ReleaseProfileWritable'), f.valid(f.var('ReleaseProfile'))))
    for name in prefs:
        permitted.set(name, permitted.var('Release' + name), permitted.var('ReleaseProfile'), profile_class)
    saved = permitted.data(GS + 'SaveGameToSlot', SaveGameObject=permitted.var('ReleaseProfile'), SlotName=permitted.var('ReleaseProfileSlot'), UserIndex=0)
    okay, failed = permitted.branch(saved)
    okay.set('ReleaseMenuStatus', 'Preferences saved.')
    failed.set('ReleaseMenuStatus', 'Applied this session; preferences could not be saved.')
    blocked.set('ReleaseMenuStatus', 'Applied this session. Unreadable profile files remain protected.')

    f = fn('ReleaseAdjustAudioSetting', {'Index': 'int'})
    tail = f
    for index, name in enumerate(['MasterVolume', 'AmbienceVolume', 'MusicVolume']):
        chosen, tail = tail.branch(tail.eq(tail.g.input('Index'), index))
        current = chosen.var('Release' + name)
        wrap, step = chosen.branch(chosen.data(MATH + 'GreaterEqual_DoubleDouble', A=current, B=.99999))
        wrap.set('Release' + name, 0.0)
        step.set('Release' + name, step.data(MATH + 'FClamp', Value=step.data(MATH + 'Add_DoubleDouble', A=current, B=.1), Min=0.0, Max=1.0))
        joined = merge(wrap, step)
        joined.own('ReleaseApplyAudio'); joined.own('ReleasePersistPreferences'); joined.own('ReleaseRenderMenu')
    chosen, unused = tail.branch(tail.eq(tail.g.input('Index'), 3))
    chosen.set('ReleaseMuteWhenPaused', chosen.not_(chosen.var('ReleaseMuteWhenPaused')))
    chosen.own('ReleaseApplyAudio'); chosen.own('ReleasePersistPreferences'); chosen.own('ReleaseRenderMenu')
