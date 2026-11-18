"""Native K2 graph for an owned two-component ambience director.

No runtime Python. Existing manager EraIndex is read-only authority. No story
event or menu graph is changed; stored music/SFX assets have no playback hook.
"""
import unreal
import opening_graph as og
import build_opening_actions as base

MATH, GS = base.MATH, base.GS
AC = '/Script/Engine.AudioComponent.'


class Flow(base.Flow):
    scope = ''

    def own(self, name, **params):
        return self.call(self.scope + ':' + name, **params)

    def branch(self, condition):
        node = self.g.branch(condition)
        og.link(self.cur, og.pin_in(node))
        return type(self)(self.g, og.pin_out(node, 'then')), type(self)(self.g, og.pin_out(node, 'else'))

    def audio(self, component, action, **params):
        return self.call(AC + action, **{'self': self.var(component), **params})


def merge(*flows):
    node = flows[0].g.set('AudioFlowMarker', 0)
    for flow in flows:
        og.link(flow.cur, og.pin_in(node))
    return type(flows[0])(flows[0].g, og.pin_out(node))


def subobjects(bp):
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    result = []
    for handle in subsystem.k2_gather_subobject_data_for_blueprint(bp):
        data = lib.get_data(handle)
        result.append((str(lib.get_variable_name(data)), handle, lib.get_object_for_blueprint(data, bp)))
    return subsystem, lib, result


def component(bp, name):
    subsystem, lib, entries = subobjects(bp)
    found = next((item for item in entries if item[0] == name), None)
    if found:
        return found[2]
    params = unreal.AddNewSubobjectParams(parent_handle=entries[0][1], new_class=unreal.AudioComponent,
                                         blueprint_context=bp, conform_transform_to_parent=False)
    handle, reason = subsystem.add_new_subobject(params)
    if not lib.is_handle_valid(handle) or not subsystem.rename_subobject(handle, unreal.Text(name)):
        raise RuntimeError('Cannot add owned audio component ' + name + ': ' + str(reason))
    return lib.get_object_for_blueprint(lib.get_data(handle), bp)


def build(bp, sounds):
    Flow.scope = bp.get_path_name() + '_C'
    members = [('AudioManager', og.object_type(base.CLASS), None),
               ('MasterGain', 'real', .8), ('AmbienceGain', 'real', .65),
               ('MusicGain', 'real', .34), ('MuteWhenPaused', 'bool', True),
               ('CurrentEra', 'int', -1), ('PendingEra', 'int', 0),
               ('CurrentBedGain', 'real', -1.0), ('PendingBedGain', 'real', 0.0),
               ('CurrentMuted', 'bool', False), ('PendingMuted', 'bool', False),
               ('AudioFlowMarker', 'int', 0), ('BedStartCount', 'int', 0), ('EraSwitchCount', 'int', 0)]
    for name, kind, value in members:
        og.member(bp, name, kind, value, instance_editable=name in
                  ['MasterGain', 'AmbienceGain', 'MusicGain', 'MuteWhenPaused'])
    # Retain imported cue references for cook; these are deliberately untriggered.
    for key, name in [('SFX_WatchTick', 'WatchTickAsset'), ('SFX_CalibrationSuccess', 'CalibrationAsset'),
                      ('SFX_SoftTransition', 'TransitionAsset'), ('SFX_ClothInteraction', 'ClothAsset'),
                      ('MUS_Optional_BellMotif', 'OptionalMusicAsset')]:
        og.member(bp, name, og.object_type(unreal.SoundWave), sounds[key])
    for name, role in [('AudioPresent', 'Amb_Coast_Present_60s'), ('AudioPast', 'Amb_Coast_Past_60s')]:
        obj = component(bp, name)
        # UE5.8 AudioComponent.cpp constructor already sets bAutoDestroy=false
        # and bStopWhenOwnerDestroyed=true. Those noneditable flags are not
        # exposed as Python properties; preserve their native defaults.
        for field, value in {'sound': sounds[role], 'auto_activate': False, 'allow_spatialization': False,
                             'is_ui_sound': True, 'can_play_multiple_instances': False,
                             'volume_multiplier': 1.0}.items():
            obj.set_editor_property(field, value)
    signatures = {'FindAudioManager': {}, 'RefreshAudioState': {}, 'StopAudioBeds': {},
                  'SetMixGains': {'Master': 'real', 'Ambience': 'real', 'Music': 'real', 'MuteOnPause': 'bool'}}
    for name, params in signatures.items():
        og.function(bp, name, inputs=params)
    og.compile_bp(bp)
    # Keep the declared entry graph. Removing/recreating it after compiling the
    # stubs leaves old UFunction names reserved and native UE appends "_0".
    def fn(name): return Flow(og.function(bp, name, inputs=signatures[name], reset=False))

    flow = fn('FindAudioManager')
    found = flow.data(GS + 'GetActorOfClass', ActorClass=base.CLASS)
    cast = flow.g.cast(base.CLASS, found)
    og.link(flow.cur, og.pin_in(cast))
    found_flow = Flow(flow.g, og.pin_out(cast))
    found_flow.set('AudioManager', flow.g.cast_value(cast))

    flow = fn('StopAudioBeds')
    for name in ['AudioPresent', 'AudioPast']:
        flow.audio(name, 'Stop')
    flow.set('CurrentEra', -1)
    flow.set('CurrentBedGain', -1.0)

    flow = fn('SetMixGains')
    for name, arg in [('MasterGain', 'Master'), ('AmbienceGain', 'Ambience'), ('MusicGain', 'Music')]:
        flow.set(name, flow.data(MATH + 'FClamp', Value=flow.g.input(arg), Min=0.0, Max=1.0))
    flow.set('MuteWhenPaused', flow.g.input('MuteOnPause'))
    flow.own('RefreshAudioState')

    flow = fn('RefreshAudioState')
    valid, missing = flow.branch(flow.valid(flow.var('AudioManager')))
    missing.own('StopAudioBeds')
    missing.own('FindAudioManager')
    # Reacquisition cannot create components or another director; next tick uses it.
    valid.set('PendingEra', valid.data(MATH + 'Clamp', Value=valid.var('EraIndex', valid.var('AudioManager'), base.CLASS), Min=0, Max=1))
    master = valid.data(MATH + 'FClamp', Value=valid.var('MasterGain'), Min=0.0, Max=1.0)
    ambience = valid.data(MATH + 'FClamp', Value=valid.var('AmbienceGain'), Min=0.0, Max=1.0)
    valid.set('PendingBedGain', valid.data(MATH + 'Multiply_DoubleDouble', A=master, B=ambience))
    valid.set('PendingMuted', valid.and_(valid.var('MuteWhenPaused'), valid.data(GS + 'IsGamePaused')))
    changed, steady = valid.branch(valid.not_(valid.eq(valid.var('CurrentEra'), valid.var('PendingEra'))))
    was_present, previous = changed.branch(changed.eq(changed.var('CurrentEra'), 0))
    was_present.audio('AudioPresent', 'FadeOut', FadeOutDuration=.8, FadeVolumeLevel=0.0, FadeCurve='Linear')
    was_past, initial = previous.branch(previous.eq(previous.var('CurrentEra'), 1))
    was_past.audio('AudioPast', 'FadeOut', FadeOutDuration=.8, FadeVolumeLevel=0.0, FadeCurve='Linear')
    switched = merge(was_present, was_past)
    switched.set('EraSwitchCount', switched.data(MATH + 'Add_IntInt', A=switched.var('EraSwitchCount'), B=1))
    starting = merge(switched, initial)
    present, past = starting.branch(starting.eq(starting.var('PendingEra'), 0))
    for branch, name in [(present, 'AudioPresent'), (past, 'AudioPast')]:
        # Keep the era envelope independent of the user gain. UE5.8 treats a
        # zero AdjustVolume target as a finite fade-out and stops the instance.
        branch.audio(name, 'SetVolumeMultiplier', NewVolumeMultiplier=branch.var('PendingBedGain'))
        branch.audio(name, 'FadeIn', FadeInDuration=.8, FadeVolumeLevel=1.0, StartTime=0.0, FadeCurve='Linear')
    starting = merge(present, past)
    starting.set('CurrentEra', starting.var('PendingEra'))
    starting.set('CurrentBedGain', starting.var('PendingBedGain'))
    starting.set('BedStartCount', starting.data(MATH + 'Add_IntInt', A=starting.var('BedStartCount'), B=1))
    # Explicit pausing preserves loop position; UI-sound components deliberately
    # stay controllable even while the manager's ordinary pause stops world time.
    for name in ['AudioPresent', 'AudioPast']:
        starting.audio(name, 'SetPaused', bPause=starting.var('PendingMuted'))
    starting.set('CurrentMuted', starting.var('PendingMuted'))
    adjust, stable_gain = steady.branch(steady.data(MATH + 'NotEqual_DoubleDouble', A=steady.var('CurrentBedGain'), B=steady.var('PendingBedGain')))
    present, past = adjust.branch(adjust.eq(adjust.var('CurrentEra'), 0))
    for branch, name in [(present, 'AudioPresent'), (past, 'AudioPast')]:
        branch.audio(name, 'SetVolumeMultiplier', NewVolumeMultiplier=branch.var('PendingBedGain'))
    adjusted = merge(present, past)
    adjusted.set('CurrentBedGain', adjusted.var('PendingBedGain'))
    pause_check = merge(adjusted, stable_gain)
    pause_changed, unchanged = pause_check.branch(pause_check.data(MATH + 'NotEqual_BoolBool', A=pause_check.var('CurrentMuted'), B=pause_check.var('PendingMuted')))
    for name in ['AudioPresent', 'AudioPast']:
        pause_changed.audio(name, 'SetPaused', bPause=pause_changed.var('PendingMuted'))
    pause_changed.set('CurrentMuted', pause_changed.var('PendingMuted'))

    events = og.events(bp)
    begin = Flow(events, og.pin_out(events.event('ReceiveBeginPlay')))
    begin.own('FindAudioManager')
    begin.own('RefreshAudioState')
    Flow(events, og.pin_out(events.event('ReceiveTick'))).own('RefreshAudioState')
    Flow(events, og.pin_out(events.event('ReceiveEndPlay'))).own('StopAudioBeds')
    og.compile_bp(bp)
    cdo = unreal.get_default_object(og.L.generated_class(bp))
    tick = cdo.get_editor_property('primary_actor_tick')
    # ReceiveTick makes this generated Blueprint tick-capable; bCanEverTick is
    # not an editable Python property. Set the exposed scheduling fields only.
    for name, value in {'start_with_tick_enabled': True,
                        'tick_even_when_paused': True, 'tick_interval': 0.0}.items():
        tick.set_editor_property(name, value)
    cdo.set_editor_property('primary_actor_tick', tick)
    return bp
