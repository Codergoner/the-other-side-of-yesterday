"""Queued one-channel action SFX actor; ambient director/frontend stay intact.

Only mix settings are polled. Gameplay cues arrive explicitly at accepted
producer execution edges. No saved quest flags, load/restore events, music,
dialogue audio, ambience components or save functions are authored here.
"""
import unreal
import opening_graph as og
import build_opening_actions as base
import release_audio_graph as audio_graph

MATH, GS, AC = base.MATH, base.GS, '/Script/Engine.AudioComponent.'
CUES = [('tick', 'WatchTickAsset', .12, 0), ('calibration', 'CalibrationAsset', .26, 2),
        ('transition', 'TransitionAsset', .22, 3), ('cloth', 'ClothAsset', .20, 1)]


class Flow(audio_graph.Flow):
    scope = ''


def build(bp, waves):
    Flow.scope = bp.get_path_name() + '_C'
    members = [('MixManager', og.object_type(base.CLASS), None), ('CueGain', 'real', .12),
               ('CuePriority', 'int', -1), ('LastCueRealSeconds', 'real', -100),
               ('CuePlayCount', 'int', 0), ('CueSuppressedCount', 'int', 0),
               ('CueUnknownCount', 'int', 0), ('AudioFlowMarker', 'int', 0),
               ('CurrentCueName', 'name', '')]
    for name, kind, value in members: og.member(bp, name, kind, value)
    for role, member in [('SFX_WatchTick', 'WatchTickAsset'), ('SFX_CalibrationSuccess', 'CalibrationAsset'),
                         ('SFX_SoftTransition', 'TransitionAsset'), ('SFX_ClothInteraction', 'ClothAsset')]:
        og.member(bp, member, og.object_type(unreal.SoundWave), waves[role])
    component = audio_graph.component(bp, 'ActionChannel')
    for key, value in {'auto_activate': False, 'allow_spatialization': False, 'is_ui_sound': True,
                       'can_play_multiple_instances': False, 'volume_multiplier': .1}.items():
        component.set_editor_property(key, value)
    signatures = {'FindMixManager': {}, 'RefreshCueMix': {}, 'PlayCue': {'CueName': 'name'},
                  'StartCue': {'Sound': og.object_type(unreal.SoundWave), 'Gain': 'real', 'Priority': 'int', 'CueName': 'name'}}
    for name, args in signatures.items(): og.function(bp, name, inputs=args)
    og.compile_bp(bp)
    def fn(name): return Flow(og.function(bp, name, inputs=signatures[name], reset=False))

    f = fn('FindMixManager')
    found = f.data(GS + 'GetActorOfClass', ActorClass=base.CLASS)
    cast = f.g.cast(base.CLASS, found)
    og.link(f.cur, og.pin_in(cast))
    Flow(f.g, og.pin_out(cast)).set('MixManager', f.g.cast_value(cast))

    f = fn('RefreshCueMix')
    valid, missing = f.branch(f.valid(f.var('MixManager')))
    missing.own('FindMixManager')
    master = valid.data(MATH + 'FClamp', Value=valid.var('ReleaseMasterVolume', valid.var('MixManager'), base.CLASS), Min=0.0, Max=1.0)
    gain = valid.data(MATH + 'Multiply_DoubleDouble', A=master, B=valid.var('CueGain'))
    valid.audio('ActionChannel', 'SetVolumeMultiplier', NewVolumeMultiplier=gain)
    paused = valid.and_(valid.var('ReleaseMuteWhenPaused', valid.var('MixManager'), base.CLASS), valid.data(GS + 'IsGamePaused'))
    valid.audio('ActionChannel', 'SetPaused', bPause=paused)
    # Never Play/Resume based on a stored reward or calibration flag. Setting
    # volume to0 may finish a finite one-shot; unmute does not replay it.

    f = fn('StartCue')
    valid, missing = f.branch(f.valid(f.var('MixManager')))
    missing.set('CueSuppressedCount', missing.data(MATH + 'Add_IntInt', A=missing.var('CueSuppressedCount'), B=1))
    master = valid.data(MATH + 'FClamp', Value=valid.var('ReleaseMasterVolume', valid.var('MixManager'), base.CLASS), Min=0.0, Max=1.0)
    audible = valid.data(MATH + 'Greater_DoubleDouble', A=master, B=.0001)
    paused = valid.and_(valid.var('ReleaseMuteWhenPaused', valid.var('MixManager'), base.CLASS), valid.data(GS + 'IsGamePaused'))
    gap = valid.data(MATH + 'Subtract_DoubleDouble', A=valid.data(GS + 'GetRealTimeSeconds'), B=valid.var('LastCueRealSeconds'))
    ready = valid.and_(audible, valid.and_(valid.not_(paused), valid.data(MATH + 'GreaterEqual_DoubleDouble', A=gap, B=.10)))
    allowed, suppressed = valid.branch(ready)
    suppressed.set('CueSuppressedCount', suppressed.data(MATH + 'Add_IntInt', A=suppressed.var('CueSuppressedCount'), B=1))
    playing = allowed.data(AC + 'IsPlaying', **{'self': allowed.var('ActionChannel')})
    priority_ok = allowed.or_(allowed.not_(playing), allowed.data(MATH + 'GreaterEqual_IntInt', A=allowed.g.input('Priority'), B=allowed.var('CuePriority')))
    play, lower = allowed.branch(priority_ok)
    lower.set('CueSuppressedCount', lower.data(MATH + 'Add_IntInt', A=lower.var('CueSuppressedCount'), B=1))
    play.audio('ActionChannel', 'Stop')
    play.set('CueGain', play.g.input('Gain'))
    play.set('CuePriority', play.g.input('Priority'))
    play.set('CurrentCueName', play.g.input('CueName'))
    play.audio('ActionChannel', 'SetSound', NewSound=play.g.input('Sound'))
    play.own('RefreshCueMix')
    play.audio('ActionChannel', 'Play', StartTime=0.0)
    play.set('LastCueRealSeconds', play.data(GS + 'GetRealTimeSeconds'))
    play.set('CuePlayCount', play.data(MATH + 'Add_IntInt', A=play.var('CuePlayCount'), B=1))

    f = fn('PlayCue')
    tail = f
    for cue, member, gain, priority in CUES:
        matches = tail.data(MATH + 'EqualEqual_NameName', A=tail.g.input('CueName'), B=unreal.Name(cue))
        yes, tail = tail.branch(matches)
        yes.own('StartCue', Sound=yes.var(member), Gain=gain, Priority=priority, CueName=unreal.Name(cue))
    tail.set('CueUnknownCount', tail.data(MATH + 'Add_IntInt', A=tail.var('CueUnknownCount'), B=1))

    events = og.events(bp)
    begin = Flow(events, og.pin_out(events.event('ReceiveBeginPlay')))
    begin.own('FindMixManager'); begin.own('RefreshCueMix')
    Flow(events, og.pin_out(events.event('ReceiveTick'))).own('RefreshCueMix')
    Flow(events, og.pin_out(events.event('ReceiveEndPlay'))).audio('ActionChannel', 'Stop')
    og.compile_bp(bp)
    cdo = unreal.get_default_object(og.L.generated_class(bp))
    tick = cdo.get_editor_property('primary_actor_tick')
    for key, value in {'start_with_tick_enabled': True, 'tick_even_when_paused': True, 'tick_interval': 0.0}.items(): tick.set_editor_property(key, value)
    cdo.set_editor_property('primary_actor_tick', tick)
    return bp
