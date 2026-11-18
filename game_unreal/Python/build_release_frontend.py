"""Queued desktop release front end; preserve native story bodies and GUIDs.

Source only until the root grants the serialized Unreal writer slot. Runtime
uses native K2 nodes. A small profile stores a campaign pointer/preferences,
never a second copy of story state. No audio or VR-menu implementation claim.
"""
from pathlib import Path
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Release_20261026', 'Release writer refuses protected projects'
sys.path.insert(0, str(ROOT / 'Python'))
import opening_graph as og
import build_opening_actions as base
import build_chapters_story as story
from release_frontend_graph import Flow, merge, reset_function, wrap_entry, append_save_callback, scale_existing_hud, build_menu_hud
from release_frontend_graph import MATH, SYS, GS, PC, CTL, STR, WIDGET, GUS
from release_audio_frontend import resolve_audio_class, build_audio_functions, render_audio_menu

PROFILE_PATH = '/Game/Release/Blueprints/BP_ReleaseProfile'
PROFILE_CLASS = PROFILE_PATH + '.BP_ReleaseProfile_C'
HUD_PATH = '/Game/Opening/Blueprints/BP_OpeningHUD'
PROFILE_FIELDS = {'ActiveSlot': ('string', ''), 'ProfileVersion': ('int', 1),
                  'Windowed': ('bool', True), 'ResolutionIndex': ('int', 0),
                  'VSync': ('bool', True), 'FrameCapIndex': ('int', 1),
                  'SensitivityIndex': ('int', 1), 'InvertY': ('bool', False),
                  'LargeText': ('bool', False), 'ReducedMotion': ('bool', True),
                  'MasterVolume': ('real', .8), 'AmbienceVolume': ('real', .65),
                  'MusicVolume': ('real', .34), 'MuteWhenPaused': ('bool', True)}
PREFS = [name for name in PROFILE_FIELDS if name not in ['ActiveSlot', 'ProfileVersion']]
SIGNATURES = {name: {} for name in ['ReleaseBoot', 'ReleaseReadProfile', 'ReleaseReadRecoveryProfile',
    'ReleaseAcceptProfile', 'ReleaseCheckContinue', 'ReleaseValidateCandidate', 'ReleaseCommitProfile',
    'ReleaseNewGame', 'ReleaseContinue', 'ReleaseShowMain', 'ReleaseShowSettings', 'ReleaseShowCredits',
    'ReleaseShowEnd', 'ReleaseEnterMenu', 'ReleaseResume', 'ReleaseReviewJournal', 'ReleaseRenderMenu', 'ReleaseMenuTick',
    'ReleaseShowAudioSettings', 'ReleaseApplyAudio', 'ReleasePersistPreferences']}
SIGNATURES.update({'ReleaseSelect': {'Index': 'int', 'Activate': 'bool'},
                   'ReleaseStepSelection': {'Direction': 'int'}, 'ReleaseActivate': {},
                   'ReleaseAdjustSetting': {'Index': 'int'}, 'ReleaseApplyPreferences': {'Display': 'bool'},
                   'ReleaseAdjustAudioSetting': {'Index': 'int'}})
AUDIO_CLASS = None


def manager_members(bp, profile):
    for name, kind, value in [('ReleaseBooted', 'bool', False), ('ReleaseMenuActive', 'bool', False),
        ('ReleaseSessionStarted', 'bool', False), ('ReleaseWriteAllowed', 'bool', False),
        ('ReleaseLoadApproved', 'bool', False), ('ReleaseContinueAvailable', 'bool', False),
        ('ReleaseCandidateValid', 'bool', False), ('ReleaseProfileWritable', 'bool', True),
        ('ReleaseReviewingJournal', 'bool', False),
        ('ReleaseAudioReady', 'bool', False),
        ('ReleaseMenuScreen', 'int', 0), ('ReleaseMenuSelection', 'int', 0), ('ReleaseMenuCount', 'int', 5),
        ('ReleaseFlowMarker', 'int', 0), ('ReleaseMenuTop', 'real', .32),
        ('ReleaseTextScale', 'real', 1.0), ('ReleaseBaseYaw', 'real', 1.0), ('ReleaseBasePitch', 'real', 1.0),
        ('ReleaseLastActivate', 'real', -10.0), ('ReleaseMenuTitle', 'string', ''),
        ('ReleaseMenuBody', 'string', ''), ('ReleaseMenuStatus', 'string', ''),
        ('ReleaseSelectedSlot', 'string', ''), ('ReleaseNewSlot', 'string', ''), ('ReleaseProfileSlot', 'string', 'Yesterday_Release_Profile_v1'),
        ('ReleaseSavePrefix', 'string', 'Yesterday_Release_')]:
        og.member(bp, name, kind, value, instance_editable=name in ['ReleaseProfileSlot', 'ReleaseSavePrefix'])
    for name in range(10):
        og.member(bp, 'ReleaseRow' + str(name), 'string', '')
    for name in PREFS:
        kind, value = PROFILE_FIELDS[name]
        og.member(bp, 'Release' + name, kind, value)
    og.member(bp, 'ReleaseProfile', og.object_type(profile))
    og.member(bp, 'ReleaseProfileCandidate', og.object_type(profile))
    og.member(bp, 'ReleaseCandidate', og.object_type(base.SAVE_CLASS))
    og.member(bp, 'ReleaseCredits', 'string',
              'Story and design: project-authored production draft.\n'
              'Environment geometry: project-authored procedural assets.\n'
              'Additional HDRI/materials: Poly Haven, CC0.\n'
              'Rigged template characters/animations: Epic Games.\n'
              'Powered by Unreal Engine.\n\n'
              'Ambience/audio synthesis: original project-authored sound design.\n'
              'Voice performances are not included in this build.\n'
              'Full asset provenance accompanies the release files.', instance_editable=True)


def build_functions(bp, profile):
    for name, params in SIGNATURES.items():
        reset_function(bp, name, params)
    og.compile_bp(bp)
    def fn(name): return Flow(reset_function(bp, name, SIGNATURES[name]))
    def pref(f, name): return f.var('Release' + name)
    def set_pref(f, name, value): return f.set('Release' + name, value)
    def profile_get(f, name): return f.var(name, f.var('ReleaseProfile'), PROFILE_CLASS)
    def clamp(f, value, minimum, maximum): return f.data(MATH + 'Clamp', Value=value, Min=minimum, Max=maximum)

    f = fn('ReleaseBoot')
    f.set('ReleaseBooted', True)
    f.set('ReleaseBaseYaw', f.data(PC + 'GetDeprecatedInputYawScale', **{'self': f.var('Controller')}))
    f.set('ReleaseBasePitch', f.data(PC + 'GetDeprecatedInputPitchScale', **{'self': f.var('Controller')}))
    f.own('ReleaseReadProfile')
    f.own('ReleaseApplyPreferences', Display=False)
    f.own('ReleaseShowMain')

    f = fn('ReleaseReadProfile')
    created = f.data(GS + 'CreateSaveGameObject', SaveGameClass=PROFILE_CLASS)
    cast = f.g.cast(profile, created)
    og.link(f.cur, og.pin_in(cast))
    f = Flow(f.g, og.pin_out(cast))
    f.set('ReleaseProfile', f.g.cast_value(cast))
    f.set('ReleaseProfileWritable', True)
    exists, missing = f.branch(f.data(GS + 'DoesSaveGameExist', SlotName=f.var('ReleaseProfileSlot'), UserIndex=0))
    loaded = exists.data(GS + 'LoadGameFromSlot', SlotName=exists.var('ReleaseProfileSlot'), UserIndex=0)
    cast = exists.g.cast(profile, loaded)
    og.link(exists.cur, og.pin_in(cast))
    typed, bad = Flow(f.g, og.pin_out(cast)), Flow(f.g, og.pin_out(cast, 'CastFailed'))
    typed.set('ReleaseProfileCandidate', typed.g.cast_value(cast))
    supported, future = typed.branch(typed.eq(typed.var('ProfileVersion', typed.var('ReleaseProfileCandidate'), PROFILE_CLASS), 1))
    supported.set('ReleaseProfile', supported.var('ReleaseProfileCandidate'))
    supported.own('ReleaseAcceptProfile')
    recovery = merge(bad, future, missing)
    recovery.own('ReleaseReadRecoveryProfile')

    f = fn('ReleaseReadRecoveryProfile')
    # Preserve an unreadable primary index. Recovery writes use a different
    # index filename; campaigns are always separate GUID slots.
    primary_exists = f.data(GS + 'DoesSaveGameExist', SlotName=f.var('ReleaseProfileSlot'), UserIndex=0)
    recovery_slot = f.text(f.var('ReleaseProfileSlot'), '_recovered')
    exists, absent = f.branch(f.data(GS + 'DoesSaveGameExist', SlotName=recovery_slot, UserIndex=0))
    loaded = exists.data(GS + 'LoadGameFromSlot', SlotName=recovery_slot, UserIndex=0)
    cast = exists.g.cast(profile, loaded)
    og.link(exists.cur, og.pin_in(cast))
    typed, bad = Flow(f.g, og.pin_out(cast)), Flow(f.g, og.pin_out(cast, 'CastFailed'))
    supported, future = typed.branch(typed.eq(typed.var('ProfileVersion', typed.g.cast_value(cast), PROFILE_CLASS), 1))
    supported.set('ReleaseProfile', supported.g.cast_value(cast))
    supported.set('ReleaseProfileSlot', recovery_slot)
    supported.own('ReleaseAcceptProfile')
    invalid = merge(bad, future)
    invalid.set('ReleaseProfileWritable', False)
    invalid.set('ReleaseMenuStatus', 'Save profiles are unreadable. Existing files are preserved.')
    use_recovery, no_primary = absent.branch(primary_exists)
    use_recovery.set('ReleaseProfileSlot', recovery_slot)
    use_recovery.set('ReleaseMenuStatus', 'Unreadable profile preserved. A separate recovery profile will be used.')

    f = fn('ReleaseAcceptProfile')
    for name in PREFS:
        value = profile_get(f, name)
        if name in ['ResolutionIndex']: value = clamp(f, value, 0, 1)
        if name in ['FrameCapIndex', 'SensitivityIndex']: value = clamp(f, value, 0, 2)
        if name in ['MasterVolume', 'AmbienceVolume', 'MusicVolume']:
            value = f.data(MATH + 'FClamp', Value=value, Min=0.0, Max=1.0)
        set_pref(f, name, value)
    f.set('ReleaseSelectedSlot', profile_get(f, 'ActiveSlot'))

    f = fn('ReleaseValidateCandidate')
    f.set('ReleaseCandidateValid', False)
    valid, invalid = f.branch(f.valid(f.var('ReleaseCandidate')))
    def sv(name): return valid.var(name, valid.var('ReleaseCandidate'), base.SAVE_CLASS)
    def between(value, lo, hi):
        return valid.and_(valid.data(MATH + 'GreaterEqual_IntInt', A=value, B=lo),
                          valid.data(MATH + 'LessEqual_IntInt', A=value, B=hi))
    def implies(a, b): return valid.or_(valid.not_(a), b)
    schema = sv('SchemaVersion')
    supported = valid.or_(valid.eq(schema, 1), valid.eq(schema, 2))
    modern = supported
    for name, lo, hi in [('EraIndex', 0, 1), ('CurrentChapter', 1, 2), ('StormCover', 0, 2),
                          ('CanvasPlan', 0, 2), ('LinenState', 0, 3), ('CalibrationTests', 0, 2),
                          ('HealerTrust', 0, 100), ('FinalResponse', 0, 3), ('MotherOpeningResponse', 0, 3)]:
        modern = valid.and_(modern, between(sv(name), lo, hi))
    cover = valid.data(MATH + 'Greater_IntInt', A=sv('StormCover'), B=0)
    for condition in [implies(sv('ComponentPlaced'), sv('ComponentCollected')),
        implies(sv('WatchCalibrated'), valid.and_(sv('ComponentPlaced'), valid.data(MATH + 'GreaterEqual_IntInt', A=sv('CalibrationTests'), B=2))),
        implies(sv('HasDeparted'), sv('WatchCalibrated')),
        implies(sv('CanvasOwned'), valid.and_(sv('CanvasOffered'), valid.not_(cover))),
        implies(cover, valid.and_(valid.not_(sv('CanvasOwned')), valid.eq(sv('LinenState'), 3))),
        implies(sv('HealerReportDone'), cover),
        implies(sv('HasReturned'), valid.and_(sv('HealerReportDone'), sv('HasDeparted'))),
        implies(sv('Chapter2Complete'), valid.and_(valid.and_(sv('HasReturned'), sv('ConsequenceObserved')), between(sv('FinalResponse'), 1, 3)))]:
        modern = valid.and_(modern, condition)
    safe_id = sv('SafeLocationId')
    safe = valid.or_(valid.eqs(safe_id, 'present.home'), valid.or_(valid.eqs(safe_id, 'present.gate'), valid.eqs(safe_id, 'past.gate')))
    modern = valid.and_(modern, safe)
    modern = valid.and_(modern, valid.eq(sv('Chapter'), sv('CurrentChapter')))
    era_alias = valid.select('Present', 'Past', valid.eq(sv('EraIndex'), 0))
    modern = valid.and_(modern, valid.eqs(sv('Era'), era_alias))
    modern = valid.and_(modern, implies(valid.eq(sv('EraIndex'), 1), valid.eqs(safe_id, 'past.gate')))
    modern = valid.and_(modern, implies(valid.eq(sv('EraIndex'), 0), valid.not_(valid.eqs(safe_id, 'past.gate'))))
    modern = valid.and_(modern, valid.data(MATH + 'GreaterEqual_DoubleDouble', A=sv('ReturnClockSeconds'), B=0.0))
    # Schema1 is the documented opening-only migration; new fields have class
    # defaults and must not be mistaken for corruption before that migration.
    accepted = valid.or_(valid.and_(valid.and_(valid.eq(schema, 1), between(sv('Chapter'), 1, 1)), valid.eqs(sv('Era'), 'Present')),
                        valid.and_(valid.eq(schema, 2), modern))
    valid.set('ReleaseCandidateValid', accepted)

    f = fn('ReleaseCheckContinue')
    f.set('ReleaseContinueAvailable', False)
    f.set('ReleaseCandidate', None)
    named, no = f.branch(f.data(STR + 'StartsWith', SourceString=f.var('ReleaseSelectedSlot'), InPrefix=f.var('ReleaseSavePrefix'), SearchCase='CaseSensitive'))
    exists, missing = named.branch(named.data(GS + 'DoesSaveGameExist', SlotName=named.var('ReleaseSelectedSlot'), UserIndex=0))
    loaded = exists.data(GS + 'LoadGameFromSlot', SlotName=exists.var('ReleaseSelectedSlot'), UserIndex=0)
    cast = exists.g.cast(base.SAVE_CLASS, loaded)
    og.link(exists.cur, og.pin_in(cast))
    typed = Flow(f.g, og.pin_out(cast))
    typed.set('ReleaseCandidate', typed.g.cast_value(cast))
    typed.own('ReleaseValidateCandidate')
    typed.set('ReleaseContinueAvailable', typed.var('ReleaseCandidateValid'))

    f = fn('ReleaseCommitProfile')
    permitted = f.and_(f.var('ReleaseProfileWritable'), f.and_(f.var('ReleaseWriteAllowed'), f.var('SaveSucceeded')))
    yes, no = f.branch(f.and_(permitted, f.valid(f.var('ReleaseProfile'))))
    yes.set('ActiveSlot', yes.var('SaveSlot'), yes.var('ReleaseProfile'), PROFILE_CLASS)
    yes.set('ReleaseSelectedSlot', yes.var('SaveSlot'))
    for name in PREFS:
        yes.set(name, pref(yes, name), yes.var('ReleaseProfile'), PROFILE_CLASS)
    saved = yes.data(GS + 'SaveGameToSlot', SaveGameObject=yes.var('ReleaseProfile'), SlotName=yes.var('ReleaseProfileSlot'), UserIndex=0)
    okay, failed = yes.branch(saved)
    okay.set('ReleaseMenuStatus', '')
    failed.set('ReleaseMenuStatus', 'Campaign saved, but the profile index could not be saved.')
    failed.notice('Campaign saved, but the profile index could not be saved. Existing campaigns remain intact.')

    f = fn('ReleaseNewGame')
    f, protected = f.branch(f.var('ReleaseProfileWritable'))
    protected.set('ReleaseMenuStatus', 'New Game is unavailable while save profiles are unreadable or recovery-only. Existing files have not been changed.')
    guid = f.data('/Script/Engine.KismetGuidLibrary.NewGuid')
    token = f.data('/Script/Engine.KismetGuidLibrary.Conv_GuidToString', InGuid=guid)
    f.set('ReleaseNewSlot', f.text(f.var('ReleaseSavePrefix'), token))
    # A GUID collision is not assumed impossible; refuse an occupied filename.
    occupied, free = f.branch(f.data(GS + 'DoesSaveGameExist', SlotName=f.var('ReleaseNewSlot'), UserIndex=0))
    occupied.set('ReleaseMenuStatus', 'That new slot already exists. Select New Game again; no file was overwritten.')
    free.own('RestorePhoto')
    free.set('ReleaseReviewingJournal', False)
    free.call(GS + 'SetGamePaused', bPaused=False)
    free.set('ReleaseMenuStatus', '')
    free.set('SaveSlot', free.var('ReleaseNewSlot'))
    for name in story.STATE:
        default = unreal.get_default_object(og.class_(base.SAVE_CLASS)).get_editor_property(name)
        if isinstance(default, unreal.Array):
            assert not list(default), 'New-game array default needs an explicit authoring path: ' + name
            free.call('/Script/Engine.KismetArrayLibrary.Array_Clear', TargetArray=free.var(name))
        else:
            free.set(name, default)
    for name in ['DialogueActive', 'DialogueWaitingChoice', 'IntroActive', 'Testing', 'MotherMoving', 'NeriMoving']:
        free.set(name, False)
    free.set('PauseReturnMode', 0)
    free.set('DocumentKind', '')
    free.set('SaveRef', free.data(GS + 'CreateSaveGameObject', SaveGameClass=base.SAVE_CLASS))
    free.set('ReleaseWriteAllowed', True)
    free.set('ReleaseSessionStarted', True)
    free.set('ReleaseMenuActive', False)
    free.own('RestoreSafeScene')
    free.own('RestorePlayerCheckpoint')
    free.own('ApplyWorldState')
    free.own('SetMode', NewMode=0)
    free.own('ReleaseResume')
    free.own('SaveProgress')
    free.set('IntroActive', True)
    free.own('StartScene', SceneId='C1_00')

    f = fn('ReleaseContinue')
    f.own('ReleaseCheckContinue')
    okay, invalid = f.branch(f.var('ReleaseContinueAvailable'))
    invalid.set('ReleaseWriteAllowed', False)
    invalid.set('ReleaseMenuStatus', 'No supported save can be loaded. Existing files were not changed. New Game uses a separate slot.')
    invalid.own('ReleaseShowMain')
    okay.set('SaveSlot', okay.var('ReleaseSelectedSlot'))
    okay.set('ReleaseMenuStatus', '')
    okay.set('ReleaseWriteAllowed', True)
    okay.set('ReleaseLoadApproved', True)
    okay.set('ReleaseSessionStarted', True)
    okay.set('ReleaseMenuActive', False)
    okay.own('LoadProgress')
    okay.call(WIDGET + 'SetInputMode_GameOnly', PlayerController=okay.var('Controller'), bFlushInput=True)
    okay.set('bShowMouseCursor', False, okay.var('Controller'), '/Script/Engine.PlayerController')
    complete, active = okay.branch(okay.var('Chapter2Complete'))
    complete.own('ReleaseShowEnd')
    recollections, ordinary = active.branch(active.and_(active.not_(active.var('IntroSeen')), active.not_(active.var('HasDeparted'))))
    recollections.set('IntroActive', True)
    recollections.own('StartScene', SceneId='C1_00')

    f = fn('ReleaseEnterMenu')
    f.call(GS + 'SetGamePaused', bPaused=False)
    f.set('ReleaseMenuActive', True)
    f.own('SetMode', NewMode=8)
    f.set('bShowMouseCursor', True, f.var('Controller'), '/Script/Engine.PlayerController')
    f.set('bEnableClickEvents', True, f.var('Controller'), '/Script/Engine.PlayerController')
    f.set('bEnableMouseOverEvents', True, f.var('Controller'), '/Script/Engine.PlayerController')
    f.call(WIDGET + 'SetInputMode_GameAndUIEx', PlayerController=f.var('Controller'), InWidgetToFocus=None,
           InMouseLockMode='DoNotLock', bHideCursorDuringCapture=False, bFlushInput=True)
    f.own('ReleaseRenderMenu')

    for name, screen in [('ReleaseShowMain', 0), ('ReleaseShowSettings', 1), ('ReleaseShowCredits', 2), ('ReleaseShowEnd', 3), ('ReleaseShowAudioSettings', 4)]:
        f = fn(name)
        f.set('ReleaseReviewingJournal', False)
        f.set('ReleaseMenuScreen', screen)
        f.set('ReleaseMenuSelection', 0)
        if screen == 0: f.own('ReleaseCheckContinue')
        if screen == 4: f.own('ReleaseApplyAudio')
        f.own('ReleaseEnterMenu')

    f = fn('ReleaseResume')
    f.set('ReleaseMenuActive', False)
    f.call(GS + 'SetGamePaused', bPaused=False)
    f.set('bShowMouseCursor', False, f.var('Controller'), '/Script/Engine.PlayerController')
    f.set('bEnableClickEvents', False, f.var('Controller'), '/Script/Engine.PlayerController')
    f.set('bEnableMouseOverEvents', False, f.var('Controller'), '/Script/Engine.PlayerController')
    f.call(WIDGET + 'SetInputMode_GameOnly', PlayerController=f.var('Controller'), bFlushInput=True)
    f.own('SetMode', NewMode=6)
    f.own('CloseModal')

    # Genuine player-facing ending review; the ordinary native journal and its
    # page controls render after the menu is dismissed. No story field changes.
    f = fn('ReleaseReviewJournal')
    f.set('ReleaseReviewingJournal', True)
    f.set('ReleaseMenuActive', False)
    f.call(GS + 'SetGamePaused', bPaused=False)
    f.set('bShowMouseCursor', False, f.var('Controller'), '/Script/Engine.PlayerController')
    f.set('bEnableClickEvents', False, f.var('Controller'), '/Script/Engine.PlayerController')
    f.set('bEnableMouseOverEvents', False, f.var('Controller'), '/Script/Engine.PlayerController')
    f.call(WIDGET + 'SetInputMode_GameOnly', PlayerController=f.var('Controller'), bFlushInput=True)
    f.own('OpenJournal')

    f = fn('ReleaseRenderMenu')
    for index in range(10): f.set('ReleaseRow' + str(index), '')
    main, tail = f.branch(f.eq(f.var('ReleaseMenuScreen'), 0))
    main.set('ReleaseMenuTitle', 'Early Playable - Chapters I-II')
    main.set('ReleaseMenuBody', 'A small story about the people who remain.\nNew Game always creates a separate playthrough.')
    main.set('ReleaseMenuCount', 5); main.set('ReleaseMenuTop', .34)
    for i, label in enumerate(['New Game', 'Continue', 'Settings', 'Credits', 'Quit']): main.set('ReleaseRow' + str(i), label)
    missing, ready = main.branch(main.not_(main.var('ReleaseContinueAvailable')))
    missing.set('ReleaseRow1', 'Continue - no valid save')
    main = merge(missing, ready)
    writable, protected = main.branch(main.var('ReleaseProfileWritable'))
    protected.set('ReleaseRow0', 'New Game - save profile recovery required')
    settings, tail = tail.branch(tail.eq(tail.var('ReleaseMenuScreen'), 1))
    settings.set('ReleaseMenuTitle', 'Settings')
    settings.set('ReleaseMenuBody', 'Click a row or press Enter. Changes apply immediately.\nAudio opens volume and game-pause controls.')
    settings.set('ReleaseMenuCount', 10); settings.set('ReleaseMenuTop', .29)
    settings.set('ReleaseRow0', settings.select('Display: Windowed', 'Display: Borderless desktop', pref(settings, 'Windowed')))
    settings.set('ReleaseRow1', settings.select('Window resolution: 1600 x 900', 'Window resolution: 1920 x 1080', settings.eq(pref(settings, 'ResolutionIndex'), 0)))
    settings.set('ReleaseRow2', settings.select('VSync: On', 'VSync: Off', pref(settings, 'VSync')))
    cap = settings.select('Frame cap: 30', 'Frame cap: 60', settings.eq(pref(settings, 'FrameCapIndex'), 0))
    cap = settings.select('Frame cap: 120', cap, settings.eq(pref(settings, 'FrameCapIndex'), 2)); settings.set('ReleaseRow3', cap)
    sensitivity = settings.select('Mouse sensitivity: 0.5x', 'Mouse sensitivity: 1.0x', settings.eq(pref(settings, 'SensitivityIndex'), 0))
    sensitivity = settings.select('Mouse sensitivity: 1.5x', sensitivity, settings.eq(pref(settings, 'SensitivityIndex'), 2)); settings.set('ReleaseRow4', sensitivity)
    settings.set('ReleaseRow5', settings.select('Invert mouse Y: On', 'Invert mouse Y: Off', pref(settings, 'InvertY')))
    settings.set('ReleaseRow6', settings.select('Text size: Large', 'Text size: Standard', pref(settings, 'LargeText')))
    settings.set('ReleaseRow7', settings.select('Reduced motion: On (no room auto-framing)', 'Reduced motion: Off', pref(settings, 'ReducedMotion')))
    settings.set('ReleaseRow8', 'Audio'); settings.set('ReleaseRow9', 'Back')
    credits, tail = tail.branch(tail.eq(tail.var('ReleaseMenuScreen'), 2))
    credits.set('ReleaseMenuTitle', 'Credits and attribution'); credits.set('ReleaseMenuBody', credits.var('ReleaseCredits'))
    credits.set('ReleaseMenuCount', 1); credits.set('ReleaseMenuTop', .76); credits.set('ReleaseRow0', 'Back')
    audio_menu, ending = tail.branch(tail.eq(tail.var('ReleaseMenuScreen'), 4))
    render_audio_menu(audio_menu)
    ending.set('ReleaseMenuTitle', 'End of Chapters I–II — Early Playable')
    ending.set('ReleaseMenuBody', 'The lamp is still on.\n\nThe city remains damaged. One community record now exists\nbecause of the gathering place you made usable.\n\nThank you for playing this opening.')
    ending.set('ReleaseMenuCount', 3); ending.set('ReleaseMenuTop', .65)
    ending.set('ReleaseRow0', 'Return to menu'); ending.set('ReleaseRow1', 'Start a separate playthrough')
    ending.set('ReleaseRow2', 'Review journal')

    f = fn('ReleaseStepSelection')
    value = f.add(f.var('ReleaseMenuSelection'), f.g.input('Direction'))
    low, other = f.branch(f.data(MATH + 'Less_IntInt', A=value, B=0))
    low.set('ReleaseMenuSelection', f.data(MATH + 'Subtract_IntInt', A=f.var('ReleaseMenuCount'), B=1))
    high, middle = other.branch(other.data(MATH + 'GreaterEqual_IntInt', A=value, B=other.var('ReleaseMenuCount')))
    high.set('ReleaseMenuSelection', 0); middle.set('ReleaseMenuSelection', value)

    f = fn('ReleaseSelect')
    allowed = f.and_(f.var('ReleaseMenuActive'), f.and_(f.data(MATH + 'GreaterEqual_IntInt', A=f.g.input('Index'), B=0),
                       f.data(MATH + 'Less_IntInt', A=f.g.input('Index'), B=f.var('ReleaseMenuCount'))))
    yes, no = f.branch(allowed)
    yes.set('ReleaseMenuSelection', yes.g.input('Index'))
    activate, hover = yes.branch(yes.g.input('Activate'))
    activate.own('ReleaseActivate')

    f = fn('ReleaseActivate')
    now = f.data(GS + 'GetRealTimeSeconds')
    yes, no = f.branch(f.data(MATH + 'Greater_DoubleDouble', A=f.data(MATH + 'Subtract_DoubleDouble', A=now, B=f.var('ReleaseLastActivate')), B=.15))
    yes.set('ReleaseLastActivate', now)
    main, tail = yes.branch(yes.eq(yes.var('ReleaseMenuScreen'), 0))
    for index, action in enumerate(['ReleaseNewGame', 'ReleaseContinue', 'ReleaseShowSettings', 'ReleaseShowCredits', None]):
        chosen, main = main.branch(main.eq(main.var('ReleaseMenuSelection'), index))
        if action: chosen.own(action)
        else: chosen.call(SYS + 'QuitGame', SpecificPlayer=chosen.var('Controller'), QuitPreference='Quit', bIgnorePlatformRestrictions=False)
    settings, tail = tail.branch(tail.eq(tail.var('ReleaseMenuScreen'), 1))
    back, change = settings.branch(settings.eq(settings.var('ReleaseMenuSelection'), 9))
    back.own('ReleaseShowMain')
    audio, other = change.branch(change.eq(change.var('ReleaseMenuSelection'), 8))
    audio.own('ReleaseShowAudioSettings'); other.own('ReleaseAdjustSetting', Index=other.var('ReleaseMenuSelection'))
    credits, tail = tail.branch(tail.eq(tail.var('ReleaseMenuScreen'), 2))
    credits.own('ReleaseShowMain')
    audio_menu, ending = tail.branch(tail.eq(tail.var('ReleaseMenuScreen'), 4))
    back, change = audio_menu.branch(audio_menu.eq(audio_menu.var('ReleaseMenuSelection'), 4))
    back.own('ReleaseShowSettings'); change.own('ReleaseAdjustAudioSetting', Index=change.var('ReleaseMenuSelection'))
    menu, other = ending.branch(ending.eq(ending.var('ReleaseMenuSelection'), 0))
    menu.set('ReleaseSessionStarted', False); menu.own('ReleaseShowMain')
    new, journal = other.branch(other.eq(other.var('ReleaseMenuSelection'), 1))
    new.own('ReleaseNewGame'); journal.own('ReleaseReviewJournal')

    f = fn('ReleaseMenuTick')
    tail = f
    for key, direction in [('Up', -1), ('Down', 1), ('Tab', 1)]:
        yes, tail = tail.branch(tail.key(key)); yes.own('ReleaseStepSelection', Direction=direction)
    yes, tail = tail.branch(tail.or_(tail.key('Enter'), tail.key('E'))); yes.own('ReleaseActivate')
    escape, tail = tail.branch(tail.key('Escape'))
    main, other = escape.branch(escape.eq(escape.var('ReleaseMenuScreen'), 0))
    resume, no = main.branch(main.and_(main.var('ReleaseSessionStarted'), main.not_(main.var('Chapter2Complete'))))
    resume.own('ReleaseResume')
    audio, other = other.branch(other.eq(other.var('ReleaseMenuScreen'), 4))
    audio.own('ReleaseShowSettings'); other.own('ReleaseShowMain')

    f = fn('ReleaseAdjustSetting')
    tail = f
    for index, name in enumerate(['Windowed', 'ResolutionIndex', 'VSync', 'FrameCapIndex', 'SensitivityIndex', 'InvertY', 'LargeText', 'ReducedMotion']):
        yes, tail = tail.branch(tail.eq(tail.g.input('Index'), index))
        if PROFILE_FIELDS[name][0] == 'bool':
            set_pref(yes, name, yes.not_(pref(yes, name)))
        else:
            limit = 1 if name == 'ResolutionIndex' else 2
            next_value = yes.add(pref(yes, name), 1)
            wrap, step = yes.branch(yes.data(MATH + 'Greater_IntInt', A=next_value, B=limit))
            set_pref(wrap, name, 0); set_pref(step, name, next_value); yes = merge(wrap, step)
        yes.own('ReleaseApplyPreferences', Display=index in [0, 1])
        yes.own('ReleasePersistPreferences')
        yes.own('ReleaseRenderMenu')

    build_audio_functions(bp, profile, PROFILE_CLASS, PREFS, AUDIO_CLASS)

    f = fn('ReleaseApplyPreferences')
    user_settings = f.data(GUS + 'GetGameUserSettings')
    f.set('ReleaseTextScale', f.data(MATH + 'SelectFloat', A=1.15, B=1.0, bPickA=pref(f, 'LargeText')))
    sensitivity = f.data(MATH + 'SelectFloat', A=.5, B=1.0, bPickA=f.eq(pref(f, 'SensitivityIndex'), 0))
    sensitivity = f.data(MATH + 'SelectFloat', A=1.5, B=sensitivity, bPickA=f.eq(pref(f, 'SensitivityIndex'), 2))
    f.call(PC + 'SetDeprecatedInputYawScale', **{'self': f.var('Controller'), 'NewValue': f.data(MATH + 'Multiply_DoubleDouble', A=f.var('ReleaseBaseYaw'), B=sensitivity)})
    pitch = f.data(MATH + 'Multiply_DoubleDouble', A=f.var('ReleaseBasePitch'), B=sensitivity)
    sign = f.data(MATH + 'SelectFloat', A=-1.0, B=1.0, bPickA=pref(f, 'InvertY'))
    f.call(PC + 'SetDeprecatedInputPitchScale', **{'self': f.var('Controller'), 'NewValue': f.data(MATH + 'Multiply_DoubleDouble', A=pitch, B=sign)})
    f.own('ReleaseApplyAudio')
    ready, missing = f.branch(f.valid(user_settings))
    ready.call(GUS + 'SetVSyncEnabled', **{'self': user_settings, 'bEnable': pref(ready, 'VSync')})
    cap = ready.data(MATH + 'SelectFloat', A=30.0, B=60.0, bPickA=ready.eq(pref(ready, 'FrameCapIndex'), 0))
    cap = ready.data(MATH + 'SelectFloat', A=120.0, B=cap, bPickA=ready.eq(pref(ready, 'FrameCapIndex'), 2))
    ready.call(GUS + 'SetFrameRateLimit', **{'self': user_settings, 'NewLimit': cap})
    display, no_display = ready.branch(ready.g.input('Display'))
    window, borderless = display.branch(pref(display, 'Windowed'))
    window.call(GUS + 'SetFullscreenMode', **{'self': user_settings, 'InFullscreenMode': 'Windowed'})
    small, large = window.branch(window.eq(pref(window, 'ResolutionIndex'), 0))
    for part, resolution in [(small, '(X=1600,Y=900)'), (large, '(X=1920,Y=1080)')]:
        part.call(GUS + 'SetScreenResolution', **{'self': user_settings, 'Resolution': resolution})
    borderless.call(GUS + 'SetFullscreenMode', **{'self': user_settings, 'InFullscreenMode': 'WindowedFullscreen'})
    join = merge(small, large, borderless)
    join.call(GUS + 'ApplySettings', **{'self': user_settings, 'bCheckForCommandLineOverrides': False})
    # Boot/input/text changes must not silently resize the native game window
    # or override an explicit capture command line.
    no_display.call(GUS + 'ApplyNonResolutionSettings', **{'self': user_settings})


def hook_manager(bp):
    def desktop_split(g, entry):
        f = Flow(g, entry)
        xr, desktop = f.branch(f.tag(f.var('Player'), 'Quest.XRPlayer'))
        return xr, desktop
    def load_hook(g, entry):
        xr, f = desktop_split(g, entry)
        approved, request = f.branch(f.var('ReleaseLoadApproved'))
        approved.set('ReleaseLoadApproved', False)
        booted, boot = request.branch(request.var('ReleaseBooted'))
        boot.own('ReleaseBoot'); booted.own('ReleaseContinue')
        return merge(xr, approved)
    def save_hook(g, entry):
        xr, f = desktop_split(g, entry)
        allowed, blocked = f.branch(f.and_(f.var('ReleaseWriteAllowed'), f.not_(f.var('ReleaseMenuActive'))))
        blocked.notice('This save is protected. New Game creates a separate playthrough.')
        return merge(xr, allowed)
    def tick_hook(g, entry):
        f = Flow(g, entry)
        menu, ordinary = f.branch(f.var('ReleaseMenuActive'))
        menu.own('ReleaseMenuTick')
        return ordinary
    def input_hook(g, entry):
        xr, f = desktop_split(g, entry)
        eligible = f.or_(f.eq(f.var('Mode'), 0), f.eq(f.var('Mode'), 6))
        menu, ordinary = f.branch(f.and_(eligible, f.key('F10')))
        active, paused = menu.branch(menu.eq(menu.var('Mode'), 0))
        active.own('OpenPause')
        merge(active, paused).own('ReleaseShowMain')
        return merge(xr, ordinary)
    def end_hook(g, entry):
        xr, desktop = desktop_split(g, entry)
        desktop.own('ReleaseShowEnd')
        return xr
    def camera_hook(g, entry):
        xr, desktop = desktop_split(g, entry)
        enabled, disabled = desktop.branch(desktop.not_(desktop.var('ReleaseReducedMotion')))
        return merge(xr, enabled)
    def close_hook(g, entry):
        f = Flow(g, entry)
        close, other = f.branch(f.and_(f.var('ReleaseReviewingJournal'), f.eq(f.var('Mode'), 5)))
        close.set('ReleaseReviewingJournal', False)
        close.own('ReleaseShowEnd')
        # Esc pauses the native journal. Resume returns to its current page;
        # it must not close the ending review or enter exploration instead.
        paused = other.and_(other.eq(other.var('Mode'), 6), other.eq(other.var('PauseReturnMode'), 5))
        resume, ordinary = other.branch(other.and_(other.var('ReleaseReviewingJournal'), paused))
        resume.call(GS + 'SetGamePaused', bPaused=False)
        resume.own('RenderJournal')
        return ordinary
    for name, callback in [('LoadProgress', load_hook), ('SaveProgress', save_hook), ('UpdateStep', tick_hook),
                            ('InputFrame', input_hook), ('EndSlice', end_hook), ('CameraFraming', camera_hook),
                            ('CloseModal', close_hook)]:
        wrap_entry(bp, name, callback)
    append_save_callback(bp)


def main():
    global AUDIO_CLASS
    report = {'success': False, 'runtime': 'Native Blueprint manager/HUD extension', 'scope': 'Desktop release frontend',
              'audio_runtime_playtested': False, 'vr_menus_implemented': False, 'package_playtested': False}
    settings = unreal.get_default_object(unreal.load_class(None, '/Script/BlueprintGraph.BlueprintEditorSettings'))
    promotion = settings.get_editor_property('bEnableTypePromotion')
    try:
        assert unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseFrontendWrite'), 'Root writer queue and -ReleaseFrontendWrite are required'
        settings.set_editor_property('bEnableTypePromotion', False)
        base.MATH_LITERALS.clear()
        manager = unreal.load_asset(base.PATH)
        hud = unreal.load_asset(HUD_PATH)
        assert manager and hud, 'Existing story manager and HUD are required'
        AUDIO_CLASS = resolve_audio_class(ROOT)
        report['audio_native_class'] = AUDIO_CLASS
        report['audio_native_class_available'] = AUDIO_CLASS is not None
        profile = og.blueprint(PROFILE_PATH, unreal.SaveGame)
        for name, (kind, value) in PROFILE_FIELDS.items(): og.member(profile, name, kind, value)
        og.compile_bp(profile)
        manager_members(manager, profile)
        build_functions(manager, profile)
        og.compile_bp(manager)
        hook_manager(manager)
        og.compile_bp(manager)
        scale_existing_hud(hud)
        build_menu_hud(hud, manager)
        for _ in range(2):
            for node, name, value in base.MATH_LITERALS:
                pin = og.L.find_input_pin(node, name)
                if og.P.is_valid(pin) and not og.P.list_connected_pins(pin): og.default(pin, value)
        report['compiled'] = og.compile_all([profile, manager, hud], save=True)
        report['audio_graph_hook_compiled'] = AUDIO_CLASS is not None
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    finally:
        settings.set_editor_property('bEnableTypePromotion', promotion)
        (ROOT / 'release_frontend_build_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if not report['success']:
        raise RuntimeError('Release frontend authoring failed; inspect its build report')


if __name__ == '__main__':
    main()
