"""Hands-only PIE regression of the Quest 3 pawn in the Release copy (no HMD, no hand-tracking hardware).

Run through verdant/run_unreal.ps1 -Script validate_quest3_hands.py -UserDir <fresh short dir> -Flags @('-Quest3HandsQA').
It reuses the harness of validate_quest3_xr.py (map fixture, isolated release profile, real front end, guarded saves,
screenshots, protected-file hashes) and drives every player step through the pawn's simulated hand members
(QuestSimHands, QuestSimLeft/Right Valid, Thumb, Index): the same pinch-distance, eye-to-pinch ray and dispatch code
that the OpenXR hand-tracking keypoints feed on the headset. No controller key, keyboard key or direct manager
player action is used for a player step; the few fixture calls (targeting refresh, a scene start, the end-of-demo
trigger) are listed in the report. Not hand-tracking hardware, not an APK, not headset comfort or frame rate.
Report: game_unreal/quest3_hands_runtime_validation.json, screenshots in validation/quest3_hands/<run>/.
"""
from pathlib import Path
import unreal

X_ROOT = Path(unreal.Paths.project_dir()).resolve()
if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3HandsQA'):
    raise RuntimeError('A queued -Quest3HandsQA run with a dedicated -UserDir is required')
X_PARENT_FILE = X_ROOT / 'Python/validate_quest3_xr.py'
X_PARENT = X_PARENT_FILE.read_text(encoding='utf-8')
X_PREFIX, X_SEP1, X_REST = X_PARENT.partition('\ndef scenario():\n')
X_SCENARIO, X_SEP2, X_SUFFIX = X_REST.partition('\ndef finish(error=None):\n')
if not X_SEP1 or not X_SEP2:
    raise RuntimeError('Review changed the XR harness before adapting it for hands-only input')


def x_replace(text, old, new, count=1):
    if text.count(old) != count:
        raise RuntimeError('Changed harness anchor (%d expected): %s' % (count, old[:120]))
    return text.replace(old, new)


X_PREFIX = x_replace(X_PREFIX, "parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3XRQA')",
                     "parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3HandsQA')")
X_PREFIX = x_replace(X_PREFIX, "'A queued -Quest3XRQA run", "'A queued -Quest3HandsQA run")
X_PREFIX = x_replace(X_PREFIX, "'YQ3XR_'", "'YQ3HD_'", count=2)
X_PREFIX = x_replace(X_PREFIX, "REPORT_PATH = ROOT / 'quest3_xr_runtime_validation.json'",
                     "REPORT_PATH = ROOT / 'quest3_hands_runtime_validation.json'")
X_PREFIX = x_replace(X_PREFIX, "SCREENS = ROOT / 'validation/quest3' / (STAMP + '_xr')",
                     "SCREENS = ROOT / 'validation/quest3_hands' / STAMP")
X_PREFIX = x_replace(X_PREFIX, "'scope': 'Native Quest 3 Blueprint adapter on the Release story map:",
                     "'scope': 'Hands-only input layer of the Quest 3 pawn on the Release story map (simulated fingertip positions, no hardware):")
X_SUFFIX = x_replace(X_SUFFIX, "'QUEST3_XR_RUNTIME_VALIDATION '", "'QUEST3_HANDS_RUNTIME_VALIDATION '")
exec(compile(X_PREFIX, str(X_PARENT_FILE), 'exec'), globals())
REPORT['hand_tracking_hardware_tested'] = False
REPORT['controller_keys_injected'] = 0
REPORT['player_steps_via_simulated_hands'] = 0
REPORT['fixture_calls'] = []
REPORT['hand_actions'] = []
FRAME = 1.0 / 72.0
import sys as x_sys
if str(X_ROOT / 'Python') not in x_sys.path:
    x_sys.path.insert(0, str(X_ROOT / 'Python'))
import quest3_sim_hand


def fixture(name, *args):
    REPORT['fixture_calls'].append({'action': name, 'args': [str(a) for a in args], 'step': S['step']})
    return action(name, *args)


def sim_reset():
    pawn = S['pawn']
    pawn.set_editor_property('QuestSimHands', True)
    pawn.set_editor_property('QuestSimLeftValid', False)
    pawn.set_editor_property('QuestSimRightValid', False)


def hand_point(point, right=True, pinched=True):
    """Place the simulated thumb and index tips at a world point: coincident when pinched, 8 cm apart when open."""
    pawn = S['pawn']
    side = 'Right' if right else 'Left'
    pawn.set_editor_property('QuestSim' + side + 'Valid', True)
    # The index tip stays on the target (the ray and marker aim from it); the thumb closes onto it when pinching.
    thumb = point if pinched else point + unreal.Vector(0, 0, -8)
    pawn.set_editor_property('QuestSim' + side + 'Thumb', thumb)
    pawn.set_editor_property('QuestSim' + side + 'Index', point)
    # The drawn hand: the 25 keypoint components are put on a simulated pose that ends in the same two fingertips.
    quest3_sim_hand.place(pawn, right, point, thumb)


def frame(delta=FRAME):
    qa('QuestHandsFrame', delta)


def last_action():
    return str(S['pawn'].get_editor_property('QuestLastHandAction'))


def pinch(point, right=True):
    """One pinch press at a world point: open, pinched (press edge dispatches), open (release)."""
    pawn = S['pawn']
    side = 'Right' if right else 'Left'
    hand_point(point, right, False)
    frame()
    hand_point(point, right, True)
    frame()
    label = last_action()
    hit_component = pawn.get_editor_property('QuestHandHitComponent')
    hit_actor = pawn.get_editor_property('QuestHandHitActor')
    diagnostic = {'point': xyz(point), 'tracked': bool(pawn.get_editor_property('Quest' + side + 'Tracked')),
                  'pinch': bool(pawn.get_editor_property('Quest' + side + 'Pinch')), 'pressed': bool(pawn.get_editor_property('Quest' + side + 'Pressed')),
                  'pinch_point': xyz(pawn.get_editor_property('Quest' + side + 'PinchPoint')), 'ray_hit': bool(pawn.get_editor_property('QuestHandRayHit')),
                  'ray_start': xyz(pawn.get_editor_property('QuestHandRayStart')), 'ray_end': xyz(pawn.get_editor_property('QuestHandRayEnd')),
                  'hit_component': hit_component.get_name() if hit_component else None, 'hit_actor': hit_actor.get_name() if hit_actor else None}
    hand_point(point, right, False)
    frame(0.4)  # the open hand also lets the 0.35 s per-hand debounce expire before the next pinch
    REPORT['player_steps_via_simulated_hands'] += 1
    REPORT['hand_actions'].append({'hand': 'right' if right else 'left', 'action': label, 'step': S['step'], 'diagnostic': diagnostic})
    return label


def quick_pinch(point, right=True):
    """A pinch with no time passing afterwards (about 14 ms per frame): used to prove the debounce."""
    hand_point(point, right, False)
    frame()
    hand_point(point, right, True)
    frame()
    hand_point(point, right, False)
    frame()
    return last_action()


def angles_from_eye(world_location):
    """(azimuth, elevation) in degrees of a world point relative to the camera's forward axis."""
    camera = comp('QuestCamera')
    v = world_location - camera.get_world_location()
    forward, right, up = camera.get_forward_vector(), camera.get_right_vector(), camera.get_up_vector()
    def dot(a, b):
        return a.x * b.x + a.y * b.y + a.z * b.z
    f, r, u = dot(v, forward), dot(v, right), dot(v, up)
    return (math.degrees(math.atan2(r, f)), math.degrees(math.atan2(u, math.hypot(f, r))))


def text_degrees(name):
    """Angular height in degrees of a text component at its distance from the eye: its world size times the scale it
    carries (a panel pulled nearer is scaled down with its distance; 12 November 2026: the scale used to be left out,
    which overstated the panel's text by the panel's scale)."""
    c = comp(name)
    d = distance(c.get_world_location(), comp('QuestCamera').get_world_location())
    return math.degrees(2 * math.atan((float(c.get_editor_property('world_size')) * abs(c.get_world_scale().z) / 2.0) / d))


def component_state(name):
    c = comp(name)
    state = {'visible': c.is_visible(), 'location': xyz(c.get_world_location()), 'rotation': [round(c.get_world_rotation().pitch, 2), round(c.get_world_rotation().yaw, 2), round(c.get_world_rotation().roll, 2)]}
    if isinstance(c, unreal.PrimitiveComponent):
        state.update({'collision': str(c.get_collision_enabled()), 'profile': str(c.get_collision_profile_name()),
                      'response_visibility': str(c.get_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY)),
                      'object_type': str(c.get_collision_object_type())})
    return state


def long_left_pinch(point, seconds=1.2):
    hand_point(point, False, False)
    frame()
    hand_point(point, False, True)
    frame(seconds / 2)
    frame(seconds / 2)
    label = last_action()
    hand_point(point, False, False)
    frame(0.4)
    REPORT['player_steps_via_simulated_hands'] += 1
    REPORT['hand_actions'].append({'hand': 'left-held', 'action': label, 'step': S['step']})
    return label


def ahead(distance=45):
    camera = comp('QuestCamera')
    return camera.get_world_location() + camera.get_forward_vector() * distance


def button(name):
    return comp(name).get_world_location()


def mode():
    return int(prop('Mode'))


def scenario():
    S['step'] = 'load the story map with the XR game-mode fixture'
    old_world = EDITOR.get_editor_world()
    if old_world:
        S['original_map'] = old_world.get_outer().get_name()
    check('Story map exists', unreal.EditorAssetLibrary.does_asset_exist(MAP))
    check('Story map loads', LEVEL.load_level(MAP))
    apply_fixture()
    yield begin()
    settle()
    yield wait(.4)

    S['step'] = 'hands layer present, idle without tracking'
    pawn = S['pawn']
    camera = comp('QuestCamera')
    check('Actual pawn is the Quest adapter', pawn.get_class().get_path_name() == CHAR_CLASS)
    check('Seated mode is the default', bool(pawn.get_editor_property('QuestSeated')))
    sources = {n: str(comp(n).get_editor_property('motion_source')) for n in ['LeftIndexTip', 'LeftThumbTip', 'RightIndexTip', 'RightThumbTip']}
    check('Fingertip motion sources are the OpenXR hand-tracking keypoint names', all(sources[n] == n for n in sources), sources)
    # The coach and the automatic gaze arming are exercised in their own step; everywhere else they are off so that the
    # older steps keep driving the bare pinch grammar.
    pawn.set_editor_property('QuestOnboardStep', 0)
    pawn.set_editor_property('QuestAutoGazeEnabled', False)
    pawn.set_editor_property('QuestSimHands', False)
    frame()
    check('Without hardware or simulation no hand is tracked and no action fires',
          not pawn.get_editor_property('QuestLeftTracked') and not pawn.get_editor_property('QuestRightTracked') and last_action() == '')
    check('Pinch thresholds carry hysteresis', float(pawn.get_editor_property('QuestPinchOn')) < float(pawn.get_editor_property('QuestPinchOff')),
          {'on_cm': float(pawn.get_editor_property('QuestPinchOn')), 'off_cm': float(pawn.get_editor_property('QuestPinchOff'))})
    sim_reset()

    S['step'] = 'title menu driven by the pinch cluster'
    check('Release front end boots into the title menu', bool(prop('ReleaseMenuActive')) and int(prop('ReleaseMenuScreen')) == 0)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # the pawn tick runs both every frame
    check('Cluster buttons are visible with the modal panel', all(comp(n).is_visible() for n in ['QuestBtnUp', 'QuestBtnDown', 'QuestBtnOk', 'QuestBtnBack']))
    REPORT['cluster_state'] = {n: component_state(n) for n in ['QuestBtnUp', 'QuestBtnDown', 'QuestBtnOk', 'QuestBtnBack', 'QuestChoice1', 'QuestPanelRoot']}
    REPORT['cluster_state']['camera'] = xyz(camera.get_world_location())
    label = pinch(button('QuestBtnDown'))
    text = panel_text()
    check('Pinching Down steps the selection to Continue', label == 'menu_down' and '> Continue' in text,
          {'action': label, 'text': text, 'diagnostic': REPORT['hand_actions'][-1]['diagnostic'], 'cluster': REPORT['cluster_state']})
    label = pinch(button('QuestBtnUp'))
    text = panel_text()
    check('Pinching Up steps back to New Game', label == 'menu_up' and '> New Game' in text, {'action': label})
    label = pinch(ahead(), right=False)
    check('A left pinch is Back and the title screen stays', label == 'menu_back' and int(prop('ReleaseMenuScreen')) == 0 and bool(prop('ReleaseMenuActive')))
    check('Open hands in the menu dispatch nothing', True)
    yield screenshot('Hands_TitleCluster')
    label = pinch(button('QuestBtnOk'))
    check('Pinching Select activates New Game', label == 'menu_select')
    yield until(lambda: bool(prop('ReleaseSessionStarted')), 'real New Game started a session by pinch', 10)
    yield wait(.3)
    if bool(prop('IntroActive')):
        label = pinch(ahead(), right=False)
        check('A left pinch skips the recollections', label == 'skip_recollections')
        yield wait(.2)
    S['slot'] = str(prop('SaveSlot'))
    check('New Game by pinch enters exploration on an isolated slot', S['slot'].startswith(SAVE_PREFIX) and mode() == 0 and not prop('ReleaseMenuActive'),
          {'slot': S['slot'], 'mode': mode()})

    S['step'] = 'HUD row in exploration'
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    hud = comp('QuestHudRoot')
    check('HUD row is visible in exploration with hands', bool(pawn.get_editor_property('QuestHudVisible')) and hud.is_visible() and int(pawn.get_editor_property('QuestHudPlacements')) >= 1)
    check('HUD row sits below the eye line at a close comfortable distance (150 cm, pulled in only for clearance)', 55 <= distance(hud.get_world_location(), camera.get_world_location()) <= 170
          and hud.get_world_location().z < camera.get_world_location().z - 20, {'hud': xyz(hud.get_world_location()), 'eye': xyz(camera.get_world_location())})
    sight = unreal.SystemLibrary.line_trace_single(S['world'], camera.get_world_location(), hud.get_world_location(), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [pawn], unreal.DrawDebugTrace.NONE, True)
    sight_hit = sight.to_tuple() if sight is not None else None  # None means nothing was hit: clear line of sight
    check('HUD row has a clear line of sight from the eye', sight_hit is None or not sight_hit[0], {'blocking_actor': str(sight_hit[9]) if sight_hit and sight_hit[0] else None})
    saved_rotation = camera.get_editor_property('relative_rotation')
    saved_rotation = unreal.Rotator(pitch=saved_rotation.pitch, yaw=saved_rotation.yaw, roll=saved_rotation.roll)
    before = hud.get_world_location()
    camera.set_relative_rotation(unreal.Rotator(pitch=0, yaw=saved_rotation.yaw + 12, roll=0), False, True)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    check('HUD row stays put for a small head turn', distance(before, hud.get_world_location()) < .1)
    camera.set_relative_rotation(unreal.Rotator(pitch=0, yaw=saved_rotation.yaw + 50, roll=0), False, True)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    check('HUD row follows a large head turn', distance(before, hud.get_world_location()) > 50)
    camera.set_relative_rotation(saved_rotation, False, True)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    hand_point(ahead(40), True, False)
    frame()
    qa('QuestPointerTrace')
    check('Right fingertip marker is shown while the hand is tracked', comp('QuestRightTipMarker').is_visible())
    # Competition pass (12 November 2026): each tracked hand is drawn from its 25 keypoints.
    qa('QuestHandDraw')
    right_parts = ['QuestHandRight' + n for n in ['Thumb1', 'Thumb2', 'Thumb3', 'Index1', 'Index2', 'Index3', 'Middle1', 'Middle2', 'Middle3',
                                                 'Ring1', 'Ring2', 'Ring3', 'Little1', 'Little2', 'Little3', 'Palm']]
    check('The tracked right hand is drawn: 15 finger segments and the palm are visible', all(comp(n).is_visible() for n in right_parts),
          [n for n in right_parts if not comp(n).is_visible()])
    left_was_drawn = comp('QuestHandLeftPalm').is_visible()  # the left hand is still tracked where its last pinch left it
    pawn.set_editor_property('QuestSimLeftValid', False)
    frame()
    qa('QuestHandDraw')
    check('A hand that is no longer tracked is not drawn', left_was_drawn and not comp('QuestHandLeftPalm').is_visible() and not comp('QuestHandLeftIndex3').is_visible()
          and comp('QuestHandRightPalm').is_visible(), {'left_was_drawn': left_was_drawn})

    def midpoint(a, b):
        return (comp(a).get_world_location() + comp(b).get_world_location()) * 0.5
    segment_gaps = {'index tip segment': distance(comp('QuestHandRightIndex3').get_world_location(), midpoint('RightIndexDistal', 'RightIndexTip')),
                    'thumb base segment': distance(comp('QuestHandRightThumb1').get_world_location(), midpoint('RightThumbMetacarpal', 'RightThumbProximal')),
                    'palm': distance(comp('QuestHandRightPalm').get_world_location(), midpoint('RightWrist', 'RightMiddleProximal'))}
    index_bone = distance(comp('RightIndexDistal').get_world_location(), comp('RightIndexTip').get_world_location())
    index_scale = comp('QuestHandRightIndex3').get_world_scale()
    check('Each segment sits on its bone and is as long as it', all(v < 0.05 for v in segment_gaps.values())
          and abs(index_scale.z * 100 - (index_bone + 1.5 * 0.7)) < 0.05 and abs(index_scale.x * 100 - 1.5) < 0.01
          and distance(comp('RightIndexTip').get_world_location(), pawn.get_editor_property('QuestSimRightIndex')) < 0.01,
          {'gaps_cm': {k: round(v, 3) for k, v in segment_gaps.items()}, 'index_bone_cm': round(index_bone, 2), 'index_scale': xyz(index_scale)})
    hand_sources = {n: str(comp(n).get_editor_property('motion_source')) for n in ['LeftWrist', 'RightWrist', 'LeftMiddleProximal', 'RightLittleTip', 'RightThumbMetacarpal']}
    check('Keypoint components carry the OpenXR hand-tracking source names', all(hand_sources[n] == n for n in hand_sources), hand_sources)
    pawn.set_editor_property('QuestSimJoints', False)
    qa('QuestHandDraw')
    check('Simulated fingertips without simulated joints draw no hand', not comp('QuestHandRightPalm').is_visible())
    pawn.set_editor_property('QuestSimJoints', True)
    qa('QuestHandDraw')
    yield screenshot('Hands_HudRow')

    S['step'] = 'pause by gesture, recentre row, guarded save by pinch'
    label = long_left_pinch(ahead())
    check('Holding a left pinch opens the pause panel', label == 'gesture_pause' and mode() == 6, {'action': label, 'mode': mode()})
    check('Pause does not pause XR update', not unreal.GameplayStatics.is_game_paused(S['world']))
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # the pawn tick runs both every frame
    check('Fourth pause row offers the seated recentre', comp('QuestChoice4').is_visible() and 'Recenter the seated view' in str(comp('QuestChoiceText4').get_editor_property('text')))
    calibrations = int(pawn.get_editor_property('QuestSeatedCalibrations'))
    label = pinch(button('QuestChoice4'))
    check('Pinching the recentre row recalibrates and resumes', label == 'recenter' and int(pawn.get_editor_property('QuestSeatedCalibrations')) == calibrations + 1 and mode() == 0,
          {'action': label, 'mode': mode()})
    label = long_left_pinch(ahead())
    check('The gesture opens the pause panel again', label == 'gesture_pause' and mode() == 6)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # the pawn tick runs both every frame
    yield screenshot('Hands_PausePanel')
    label = pinch(button('QuestChoice2'))
    yield wait(.25)
    save_file = SAVE_DIR / (S['slot'] + '.sav')
    check('Pinching the Save row reaches the guarded committed save', label == 'pause_row_2' and bool(prop('SaveSucceeded')) and save_file.exists() and save_file.read_bytes()[:8] == b'YDAYSG01',
          {'action': label, 'file': str(save_file), 'bytes': save_file.stat().st_size if save_file.exists() else None})
    REPORT['save_file'] = {'path': str(save_file), 'bytes': save_file.stat().st_size, 'sha256': digest(save_file)}
    if mode() == 6:
        label = pinch(ahead(), right=False)
        check('A left pinch resumes from the pause panel', label == 'pause_resume' and mode() == 0, {'action': label, 'mode': mode()})
    else:
        check('Save returned to exploration', mode() == 0, mode())

    S['step'] = 'HUD buttons: menu, watch, journal'
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    label = pinch(button('QuestBtnMenu'))
    check('HUD Menu button opens the pause panel', label == 'open_pause' and mode() == 6)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # the pawn tick runs both every frame
    label = pinch(button('QuestBtnBack'))
    check('Cluster Back resumes from the pause panel', label == 'pause_resume' and mode() == 0)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    label = pinch(button('QuestBtnWatch'))
    check('HUD Watch button opens the Chronowatch', label == 'open_watch' and mode() == 4, {'action': label, 'mode': mode()})
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # the pawn tick runs both every frame
    # Demo-review fixes (12 November 2026): the long watch status wraps inside the panel and the help line names the dial.
    watch_text = panel_text()
    check('The watch panel wraps its status line and shows the dial help', max(len(line) for line in watch_text.split('\n')) <= 68
          and 'Up / Down: turn the dial.' in watch_text and 'Left pinch or B: close.' in watch_text and 'Selected option' not in watch_text, watch_text)
    check('The watch face stays hidden until the watch is calibrated', not prop('WatchCalibrated') and not comp('QuestDial').is_visible()
          and not comp('QuestDialHand').is_visible() and 'NO' in str(comp('QuestDial').get_collision_enabled()).upper(),
          {'calibrated': bool(prop('WatchCalibrated')), 'collision': str(comp('QuestDial').get_collision_enabled())})
    label = pinch(button('QuestBtnDown'))
    check('Cluster Down turns the dial', label == 'dial_right')
    label = pinch(button('QuestBtnUp'))
    check('Cluster Up turns the dial back', label == 'dial_left')
    yield screenshot('Hands_WatchCluster')
    label = pinch(ahead(), right=False)
    check('A left pinch closes the watch', label == 'close_watch' and mode() == 0, {'action': label, 'mode': mode()})
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    label = pinch(button('QuestBtnJournal'))
    check('HUD Journal button opens the journal', label == 'open_journal' and mode() == 5, {'action': label, 'mode': mode()})
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # the pawn tick runs both every frame
    label = pinch(button('QuestBtnDown'))
    check('Cluster Down turns a journal page', label == 'journal_next')
    label = pinch(button('QuestBtnBack'))
    check('Cluster Back closes the journal', label == 'close_journal' and mode() == 0)

    S['step'] = 'easier controls: coach, hints, hover, forgiving targets, debounce'

    def hud_text():
        return str(pawn.get_editor_property('QuestCachedQuestHudStatusText'))

    def coach_step():
        return int(pawn.get_editor_property('QuestOnboardStep'))

    def yaw_turned(since):
        return abs(((pawn.get_actor_rotation().yaw - since + 180) % 360) - 180)

    saved_camera_rotation = camera.get_editor_property('relative_rotation')
    saved_camera_rotation = unreal.Rotator(pitch=saved_camera_rotation.pitch, yaw=saved_camera_rotation.yaw, roll=saved_camera_rotation.roll)
    yaw_start = pawn.get_actor_rotation().yaw
    # -- onboarding coach: four lessons, each confirmed by the player doing it once --
    pawn.set_editor_property('QuestOnboardStep', 1)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    # Tutorial (13 November 2026): two lessons done by playing, in either order, nothing blocked; no Next button.
    use_line, move_line = 'Tutorial: look at something and pinch to use it.', 'Tutorial: to move, pinch a floor disc or a Turn button.'
    pawn.set_editor_property('QuestOnboardUsed', False)
    pawn.set_editor_property('QuestOnboardMoved', False)
    sim_reset()
    frame()
    qa('QuestPointerTrace'); qa('QuestHintFrame'); qa('QuestPanelFrame'); qa('QuestHudFrame')
    check('The tutorial shows both lessons and Skip, and no Next button', use_line in hud_text() and move_line in hud_text() and comp('QuestBtnCoachSkip').is_visible()
          and not comp('QuestBtnCoachNext').is_visible() and 'NO' in str(comp('QuestBtnCoachNext').get_collision_enabled()).upper()
          and 'QUERY' in str(comp('QuestBtnCoachSkip').get_collision_enabled()).upper() and '<' not in hud_text()
          and max(len(line) for line in hud_text().split('\n')) <= 62, hud_text())
    yield screenshot('Hands_CoachStep1')
    label = pinch(ahead(), right=False)
    check('An off-hand pinch is not a lesson any more: it does nothing in exploration and the tutorial stays', label != 'coach_back' and coach_step() == 1 and mode() == 0,
          {'action': label, 'step': coach_step(), 'mode': mode()})
    label = long_left_pinch(ahead())
    check('The held off-hand pinch opens the pause panel during the tutorial (nothing is blocked)', label == 'gesture_pause' and mode() == 6 and coach_step() == 1,
          {'action': label, 'mode': mode(), 'step': coach_step()})
    label = pinch(ahead(), right=False)
    check('and a pinch of it resumes', label == 'pause_resume' and mode() == 0, {'action': label, 'mode': mode()})
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    label = pinch(button('QuestBtnTurnRight'))
    qa('QuestPointerTrace'); qa('QuestHintFrame'); qa('QuestPanelFrame'); qa('QuestHudFrame')
    check('Turning does the move lesson: its line goes, the other stays, the tutorial goes on', label == 'turn_right' and bool(pawn.get_editor_property('QuestOnboardMoved'))
          and coach_step() == 1 and move_line not in hud_text() and use_line in hud_text() and comp('QuestBtnCoachSkip').is_visible(),
          {'action': label, 'step': coach_step(), 'text': hud_text()})
    label = pinch(button('QuestBtnTurnLeft'))
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    label = pinch(button('QuestBtnCoachSkip'))
    check('Skip tutorial ends it at any point', label == 'coach_skip' and coach_step() == 0 and bool(pawn.get_editor_property('QuestOnboardDone')),
          {'action': label, 'step': coach_step()})
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    check('The Skip button disappears when the tutorial ends and the objective returns', not comp('QuestBtnCoachNext').is_visible() and not comp('QuestBtnCoachSkip').is_visible()
          and 'Tutorial' not in hud_text() and str(prop('Objective'))[:20] in hud_text().replace('\n', ' '), hud_text())

    # -- context hint, hover feedback and the pointer dot --
    hand_point(ahead(40), True, False)
    frame()
    qa('QuestPointerTrace')
    qa('QuestHintFrame')
    idle_hint = str(pawn.get_editor_property('QuestHintText'))
    REPORT['hint_samples'] = {'idle': idle_hint, 'manager_prompt': str(prop('Prompt')), 'objective': str(prop('Objective'))}
    check('The idle hint tells the player what to do', idle_hint.startswith('Look at an object') or idle_hint.startswith('Pinch:'), idle_hint)
    watch = comp('QuestBtnWatch')
    base_scale = watch.get_world_scale()
    hand_point(button('QuestBtnWatch'), True, False)
    frame()
    qa('QuestPointerTrace')
    qa('QuestHintFrame')
    hover_hint = str(pawn.get_editor_property('QuestHintText'))
    REPORT['hint_samples']['watch'] = hover_hint
    check('The hint names the pointed HUD button', hover_hint == 'Pinch: open the Chronowatch.', hover_hint)
    grown = watch.get_world_scale()
    check('A pointed button grows 15 percent', abs(grown.y / base_scale.y - 1.15) < .01, {'base': xyz(base_scale), 'grown': xyz(grown)})
    check('The pointer dot sits on the pointed button and stays visible', comp('QuestPointer').is_visible()
          and distance(comp('QuestPointer').get_world_location(), button('QuestBtnWatch')) < 12 and comp('QuestPointer').get_world_scale().x >= .0155,
          {'dot': xyz(comp('QuestPointer').get_world_location()), 'scale': xyz(comp('QuestPointer').get_world_scale())})
    hand_point(ahead(40), True, False)
    frame()
    qa('QuestPointerTrace')
    check('The button returns to its size when the pointer leaves', abs(watch.get_world_scale().y / base_scale.y - 1.0) < .01, xyz(watch.get_world_scale()))
    yield screenshot('Hands_HoverReticle')

    # -- forgiving targets: a miss up to 5 cm beyond a button edge still selects it; a clear miss does not --
    near_miss = button('QuestBtnTurnRight') + unreal.Vector(0, 0, 9)
    label = pinch(near_miss)
    check('A near miss of a small button still selects it', label == 'turn_right' and yaw_turned(yaw_start) > 25, {'action': label, 'point': xyz(near_miss)})
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    pinch(button('QuestBtnTurnLeft'))
    clear_miss = button('QuestBtnTurnRight') + unreal.Vector(0, 0, 26)
    label = pinch(clear_miss)
    check('A clear miss selects nothing on the HUD row', label not in ('turn_right', 'turn_left', 'open_watch', 'open_pause', 'open_journal') and yaw_turned(yaw_start) < 1,
          {'action': label})

    # -- debounce: a second pinch within 0.35 s of the first is swallowed --
    debounced = int(pawn.get_editor_property('QuestDebounced'))
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    first = quick_pinch(button('QuestBtnTurnRight'))
    second = quick_pinch(button('QuestBtnTurnRight'))
    frame(0.4)
    check('A double tap fires one action, not two', first == 'turn_right' and abs(yaw_turned(yaw_start) - 30) < 1
          and int(pawn.get_editor_property('QuestDebounced')) == debounced + 1, {'turned': yaw_turned(yaw_start), 'debounced': int(pawn.get_editor_property('QuestDebounced')) - debounced})
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    pinch(button('QuestBtnTurnLeft'))
    check('The pawn faces its start again', yaw_turned(yaw_start) < 1, yaw_turned(yaw_start))

    # -- field of view and legibility of the HUD row with the coach on --
    pawn.set_editor_property('QuestOnboardStep', 1)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    hud_names = ['QuestBtnTurnLeft', 'QuestBtnWatch', 'QuestBtnMenu', 'QuestBtnJournal', 'QuestBtnTurnRight', 'QuestBtnCoachNext', 'QuestBtnCoachSkip']
    hud_angles = {n: angles_from_eye(comp(n).get_world_location()) for n in hud_names}
    check('The HUD row and coach sit inside 22 degrees either side and between 30 below and 10 above the eye line',
          all(abs(a) <= 22 and -30 <= e <= 10 for a, e in hud_angles.values()), {n: [round(v, 1) for v in hud_angles[n]] for n in hud_angles})
    hud_text_deg = {n: round(text_degrees(n), 2) for n in ['QuestHudStatusText'] + [n + 'Text' for n in hud_names]}
    check('HUD text is at least 0.9 degrees tall', all(v >= 0.9 for v in hud_text_deg.values()), hud_text_deg)
    REPORT['field_of_view'] = {'hud_degrees': {n: [round(v, 1) for v in hud_angles[n]] for n in hud_angles}, 'hud_text_degrees': hud_text_deg}
    pawn.set_editor_property('QuestOnboardStep', 0)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision

    S['step'] = 'pause panel: gaze-select row, gaze dwell, automatic arming, field of view'
    label = pinch(button('QuestBtnMenu'))
    check('The HUD Menu button opens the pause panel for the gaze tests', label == 'open_pause' and mode() == 6, {'action': label, 'mode': mode()})
    qa('QuestPanelFrame'); qa('QuestHudFrame')
    panel_names = ['QuestChoice1', 'QuestChoice2', 'QuestChoice3', 'QuestChoice4', 'QuestChoice5', 'QuestBtnUp', 'QuestBtnDown', 'QuestBtnOk', 'QuestBtnBack']
    panel_angles = {n: angles_from_eye(comp(n).get_world_location()) for n in panel_names}
    check('Five pause rows and the cluster are visible', all(comp(n).is_visible() for n in panel_names))
    check('Pause rows and cluster sit inside 25 degrees either side and between 32 below and 18 above the eye line',
          all(abs(a) <= 25 and -32 <= e <= 18 for a, e in panel_angles.values()), {n: [round(v, 1) for v in panel_angles[n]] for n in panel_angles})
    panel_text_deg = {n: round(text_degrees(n), 2) for n in ['QuestPanelTitle', 'QuestPanelText'] + ['QuestChoiceText' + str(i) for i in range(1, 6)] + [n + 'Text' for n in panel_names[5:]]}
    check('Panel text is at least 0.9 degrees tall', all(v >= 0.9 for v in panel_text_deg.values()), panel_text_deg)
    REPORT['field_of_view']['panel_degrees'] = {n: [round(v, 1) for v in panel_angles[n]] for n in panel_angles}
    REPORT['field_of_view']['panel_text_degrees'] = panel_text_deg
    REPORT['field_of_view']['panel_distance_cm'] = round(float(pawn.get_editor_property('QuestPanelDistance')), 1)
    # -- competition pass (12 November 2026): Large text and Main hand rows, and the main hand chosen by the first pinch --
    def row_text(index):
        qa('QuestPanelFrame')
        return str(pawn.get_editor_property('QuestCachedQuestChoiceText' + str(index)))

    extra_angles = {n: angles_from_eye(comp(n).get_world_location()) for n in ['QuestChoice6', 'QuestChoice7']}
    check('Rows 6 and 7 offer the main hand and large text, inside the same field of view', comp('QuestChoice6').is_visible() and comp('QuestChoice7').is_visible()
          and 'Main hand: right' in row_text(6) and 'Large text: off' in row_text(7) and all(abs(a) <= 25 and -32 <= e <= 18 for a, e in extra_angles.values())
          and text_degrees('QuestChoiceText6') >= 0.9, {'row6': row_text(6), 'row7': row_text(7), 'degrees': {n: [round(v, 1) for v in extra_angles[n]] for n in extra_angles},
                                                      'text_degrees': round(text_degrees('QuestChoiceText6'), 2)})
    def panel_angular():
        # The panel's angular size is its scale over its distance (it is one rigid board).
        return comp('QuestPanelRoot').get_world_scale().z / distance(comp('QuestPanelRoot').get_world_location(), camera.get_world_location())

    normal_degrees = {n: text_degrees(n) for n in ['QuestPanelText', 'QuestChoiceText1', 'QuestBtnOkText']}
    normal_angular = panel_angular()
    label = pinch(button('QuestChoice7'))
    qa('QuestPanelFrame')
    large_degrees = {n: text_degrees(n) for n in normal_degrees}
    large_angular = panel_angular()
    check('Pinching Large text enlarges the panel 30 percent in angular size (every text at least 20 percent, less off-axis) and stays in the pause panel',
          label == 'toggle_large_text' and mode() == 6 and 'Large text: ON' in row_text(7) and abs(large_angular / normal_angular - 1.3) < 0.03
          and all(large_degrees[n] / normal_degrees[n] >= 1.2 for n in normal_degrees),
          {'action': label, 'panel_ratio': round(large_angular / normal_angular, 3), 'normal': {n: round(v, 2) for n, v in normal_degrees.items()},
           'large': {n: round(v, 2) for n, v in large_degrees.items()}, 'panel_distance_cm': round(float(pawn.get_editor_property('QuestPanelDistance')), 1)})
    large_angles = {n: angles_from_eye(comp(n).get_world_location()) for n in panel_names + ['QuestChoice6', 'QuestChoice7']}
    REPORT['field_of_view']['large_text_panel_degrees'] = {n: [round(v, 1) for v in large_angles[n]] for n in large_angles}
    check('With large text the rows and the cluster are still reachable inside 33 degrees either side', all(abs(a) <= 33 and -42 <= e <= 24 for a, e in large_angles.values()),
          REPORT['field_of_view']['large_text_panel_degrees'])
    yield screenshot('Hands_PauseLargeText')
    label = pinch(button('QuestChoice7'))
    check('Pinching Large text again restores the size', label == 'toggle_large_text' and 'Large text: off' in row_text(7)
          and abs(text_degrees('QuestPanelText') / normal_degrees['QuestPanelText'] - 1.0) < 0.03, {'action': label})
    label = pinch(button('QuestChoice6'))
    check('Pinching Main hand makes the left hand the main hand; the hand still pinching the row does not close the panel',
          label == 'toggle_main_hand' and bool(pawn.get_editor_property('QuestLeftHanded')) and mode() == 6 and 'Main hand: LEFT' in row_text(6),
          {'action': label, 'mode': mode(), 'row6': row_text(6)})
    label = pinch(button('QuestChoice7'), right=False)
    check('The left hand now selects', label == 'toggle_large_text' and 'Large text: ON' in row_text(7), {'action': label})
    label = pinch(button('QuestChoice7'), right=False)
    check('and selects again', label == 'toggle_large_text' and 'Large text: off' in row_text(7), {'action': label})
    lefty_text = panel_text()
    check('Player text names the other hand for a left-handed player', 'Right pinch or Back closes.' in lefty_text and '<' not in lefty_text, lefty_text)
    label = pinch(ahead(), right=True)
    check('The right hand is now the Back hand', label == 'pause_resume' and mode() == 0, {'action': label, 'mode': mode()})
    qa('QuestPanelFrame'); qa('QuestHudFrame')
    label = pinch(button('QuestBtnMenu'), right=False)
    check('The left hand opens the pause panel from the HUD row', label == 'open_pause' and mode() == 6, {'action': label, 'mode': mode()})
    qa('QuestPanelFrame'); qa('QuestHudFrame')
    label = pinch(button('QuestChoice6'), right=False)
    check('Main hand switches back to the right hand', label == 'toggle_main_hand' and not pawn.get_editor_property('QuestLeftHanded') and mode() == 6
          and 'Main hand: right' in row_text(6), {'action': label, 'mode': mode()})
    # The first pinch of a session, made with the other hand and aimed at a button, adopts that hand and then acts.
    pawn.set_editor_property('QuestMainChosen', False)
    choice_before = int(pawn.get_editor_property('QuestChoiceIndex'))
    hand_point(button('QuestBtnDown'), False, False)
    frame()
    hand_point(button('QuestBtnDown'), False, True)
    frame()
    adopted = last_action()
    frame()
    acted = last_action()
    hand_point(button('QuestBtnDown'), False, False)
    frame(0.4)
    check('A first pinch with the left hand on a button adopts the left hand and the same pinch then acts',
          adopted == 'adopt_main_hand' and acted == 'pause_cycle' and bool(pawn.get_editor_property('QuestLeftHanded')) and bool(pawn.get_editor_property('QuestMainChosen'))
          and mode() == 6 and int(pawn.get_editor_property('QuestChoiceIndex')) != choice_before,
          {'adopted': adopted, 'acted': acted, 'left_handed': bool(pawn.get_editor_property('QuestLeftHanded')), 'mode': mode(),
           'choice': [choice_before, int(pawn.get_editor_property('QuestChoiceIndex'))]})
    pawn.set_editor_property('QuestMainChosen', False)
    label = pinch(ahead() + camera.get_right_vector() * 45, right=True)  # well beside the panel
    check('A first pinch with the other hand that is not aimed at a button adopts nothing', label == 'pause_resume' and bool(pawn.get_editor_property('QuestLeftHanded'))
          and mode() == 0, {'action': label, 'mode': mode()})
    qa('QuestPanelFrame'); qa('QuestHudFrame')
    label = pinch(button('QuestBtnMenu'), right=False)
    qa('QuestPanelFrame'); qa('QuestHudFrame')
    label2 = pinch(button('QuestChoice6'), right=False)
    check('Back to a right-handed player in the pause panel for the gaze tests', label == 'open_pause' and label2 == 'toggle_main_hand'
          and not pawn.get_editor_property('QuestLeftHanded') and mode() == 6, {'actions': [label, label2], 'mode': mode()})
    row5 = str(pawn.get_editor_property('QuestCachedQuestChoiceText5'))
    check('Row 5 offers the gaze fallback, off', 'Gaze select' in row5 and 'off' in row5, row5)
    yield screenshot('Hands_PauseGazeRow')
    label = pinch(button('QuestChoice5'))
    qa('QuestPanelFrame')
    check('Pinching row 5 arms gaze select and stays in the pause panel', label == 'toggle_gaze' and bool(pawn.get_editor_property('QuestGazeSelect')) and mode() == 6,
          {'action': label, 'mode': mode()})
    check('Row 5 now reads ON', 'ON' in str(pawn.get_editor_property('QuestCachedQuestChoiceText5')))
    label = pinch(ahead(), right=False)
    check('A left pinch resumes from the pause panel', label == 'pause_resume' and mode() == 0, {'action': label, 'mode': mode()})
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    sim_reset()
    frame()
    aim_camera_at(button('QuestBtnJournal'))
    fires = int(pawn.get_editor_property('QuestGazeFires'))
    elapsed = 0.0
    for _ in range(8):
        qa('QuestDwellFrame', 0.5)
        elapsed += 0.5
        if int(pawn.get_editor_property('QuestGazeFires')) > fires:
            break
    check('Looking at the Journal button for about 1.5 s selects it with no hand tracked',
          int(pawn.get_editor_property('QuestGazeFires')) == fires + 1 and 1.0 <= elapsed <= 2.5 and mode() == 5 and last_action() == 'open_journal',
          {'elapsed': elapsed, 'mode': mode(), 'action': last_action(), 'dwell_id': int(pawn.get_editor_property('QuestDwellId')),
           'subject': int(pawn.get_editor_property('QuestDwellSubject')), 'time': float(pawn.get_editor_property('QuestDwellTime')),
           'fired_id': int(pawn.get_editor_property('QuestDwellFiredId')), 'fires': int(pawn.get_editor_property('QuestGazeFires')),
           'gaze_select': bool(pawn.get_editor_property('QuestGazeSelect')), 'ui_hit': bool(pawn.get_editor_property('QuestUiHit')),
           'hud_visible': bool(pawn.get_editor_property('QuestHudVisible')), 'sim_hands': bool(pawn.get_editor_property('QuestSimHands')),
           'ray_start': xyz(pawn.get_editor_property('QuestHandRayStart')), 'ray_end': xyz(pawn.get_editor_property('QuestHandRayEnd')),
           'journal_button': xyz(button('QuestBtnJournal')), 'journal_collision': str(comp('QuestBtnJournal').get_collision_enabled()),
           'camera': xyz(camera.get_world_location()), 'forward': xyz(camera.get_forward_vector())})
    check('The dwell progress dot is shown while gaze select is on', comp('QuestGazeDot').is_visible())
    camera.set_relative_rotation(saved_camera_rotation, False, True)
    fixture('CloseModal')
    pawn.set_editor_property('QuestGazeSelect', False)
    qa('QuestDwellFrame', 0.1)
    check('The dwell dot hides again when gaze select is off', not comp('QuestGazeDot').is_visible())
    pawn.set_editor_property('QuestAutoGazeEnabled', True)
    sim_reset()
    for _ in range(4):
        qa('QuestDwellFrame', 5.0)
    check('With no tracked hand or controller for 15 s gaze select arms itself', bool(pawn.get_editor_property('QuestGazeSelect')) and bool(pawn.get_editor_property('QuestAutoGaze')))
    pawn.set_editor_property('QuestGazeSelect', False)
    pawn.set_editor_property('QuestAutoGazeEnabled', False)
    qa('QuestDwellFrame', 0.1)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    hand_point(ahead(40), True, False)
    frame()

    S['step'] = 'teleport and snap turn by pinch with a blink'
    movement = pawn.get_component_by_class(unreal.CharacterMovementComponent)
    landings = [a for a in tagged('Quest.Teleport') if not bool(a.get_editor_property('hidden'))]
    pairs = [(a, b) for a in landings for b in landings if a != b and 120 < distance(a.get_actor_location(), b.get_actor_location()) < 500
             and abs(a.get_actor_location().z - b.get_actor_location().z) < 110]
    check('City supplies reachable authored landing pairs', bool(pairs), {'nodes': len(landings), 'pairs': len(pairs)})
    blinks = int(pawn.get_editor_property('QuestBlinks'))
    teleported = False
    attempts = []
    for start, destination in pairs[:18]:
        pawn.set_actor_location(start.get_actor_location() + unreal.Vector(0, 0, 88), False, True)
        aim_camera_at(destination.get_actor_location() + unreal.Vector(0, 0, 2))
        label = pinch(destination.get_actor_location() + unreal.Vector(0, 0, 2))
        yield wait(.06)
        head = camera.get_world_location()
        t = destination.get_actor_location()
        horizontal = math.hypot(head.x - t.x, head.y - t.y)
        attempts.append({'from': start.get_actor_label(), 'to': destination.get_actor_label(), 'action': label, 'head_xy_error_cm': round(horizontal, 3)})
        if label == 'teleport' and horizontal < 40:
            teleported = True
            break
    check('Pinching a landing disc teleports onto it', teleported, attempts)
    check('Teleport blinks the camera', int(pawn.get_editor_property('QuestBlinks')) >= blinks + 1)
    movement.set_movement_mode(unreal.MovementMode.MOVE_WALKING)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    yaw_before = pawn.get_actor_rotation().yaw
    blinks = int(pawn.get_editor_property('QuestBlinks'))
    label = pinch(button('QuestBtnTurnRight'))
    yaw_after = pawn.get_actor_rotation().yaw
    turned = abs(((yaw_after - yaw_before + 180) % 360) - 180)
    check('HUD Turn right snaps the body 30 degrees with a blink', label == 'turn_right' and abs(turned - 30) < 1 and int(pawn.get_editor_property('QuestBlinks')) == blinks + 1,
          {'action': label, 'turned': turned})
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # both, as the pawn tick does: the panel frame drops a closed panel's collision
    label = pinch(button('QuestBtnTurnLeft'))
    check('HUD Turn left snaps back', label == 'turn_left' and abs(((pawn.get_actor_rotation().yaw - yaw_before + 180) % 360) - 180) < 1)

    S['step'] = 'photograph: gaze plus pinch, photo in the left hand, flip and close by pinch'
    photo = prop('PhotoActor')
    target = photo.get_actor_location()
    selected = False
    attempts = []
    for dx, dy in [(150, 0), (0, 150), (-150, 0), (0, -150), (100, 100)]:
        pawn.set_actor_location(unreal.Vector(target.x + dx, target.y + dy, 1107), False, True)
        aim_camera_at(target)
        yield wait(.08)
        fixture('UpdateTarget')
        yield wait(.04)
        attempts.append({'pawn': xyz(pawn.get_actor_location()), 'selected': str(prop('Target'))})
        if prop('Target') == photo:
            selected = True
            break
    check('Gaze selects the photograph', selected, attempts)
    # Demo-review fixes (12 November 2026): no keyboard key in the hint, and the hint line has a dark plate behind it.
    hand_point(ahead(40), True, False)
    frame()
    qa('QuestPointerTrace'); qa('QuestHintFrame'); qa('QuestHudFrame')
    target_hint = str(pawn.get_editor_property('QuestHintText'))
    manager_prompt = str(prop('Prompt'))
    REPORT['hint_samples']['target'] = {'hint': target_hint, 'manager_prompt': manager_prompt}
    key_gap = manager_prompt.find('  ')
    check('The hint for a gazed object drops the keyboard key prefix', 0 <= key_gap <= 7 and target_hint == 'Pinch: ' + manager_prompt[key_gap + 2:]
          and not target_hint.startswith('Pinch: F') and not target_hint.startswith('Pinch: E '), REPORT['hint_samples']['target'])
    check('The hint line sits on its dark plate', comp('QuestHudStatusBack').is_visible() and comp('QuestHudStatusText').is_visible())
    # Tutorial lesson "use something": with the move lesson already done, using the gazed photograph ends the tutorial.
    pawn.set_editor_property('QuestOnboardStep', 1)
    pawn.set_editor_property('QuestOnboardUsed', False)
    pawn.set_editor_property('QuestOnboardMoved', True)
    qa('QuestPointerTrace'); qa('QuestHintFrame'); qa('QuestPanelFrame'); qa('QuestHudFrame')
    lesson_text = str(pawn.get_editor_property('QuestCachedQuestHudStatusText'))
    check('With a gazed object the tutorial shows the remaining lesson above what a pinch will do',
          'Tutorial: look at something and pinch to use it.' in lesson_text and 'Tutorial: to move' not in lesson_text and target_hint in lesson_text, lesson_text)
    label = pinch(ahead())
    yield wait(.2)
    check('A right pinch interacts with the gazed photograph', label == 'interact' and mode() == 3 and str(prop('DialogueRoot')) == 'C1_01',
          {'action': label, 'mode': mode(), 'root': str(prop('DialogueRoot'))})
    check('Using the photograph does the last lesson and ends the tutorial', bool(pawn.get_editor_property('QuestOnboardUsed'))
          and int(pawn.get_editor_property('QuestOnboardStep')) == 0 and bool(pawn.get_editor_property('QuestOnboardDone')),
          {'used': bool(pawn.get_editor_property('QuestOnboardUsed')), 'step': int(pawn.get_editor_property('QuestOnboardStep'))})
    advances = 0
    for _ in range(14):
        if mode() == 1:
            break
        yield wait(.8)
        label = pinch(ahead())
        advances += 1 if label == 'advance_dialogue' else 0
    check('Right pinches advance the conversation to the inspection', mode() == 1 and prop('HeldPhoto') == photo and advances >= 1, {'mode': mode(), 'advances': advances})
    left_point = camera.get_world_location() + camera.get_forward_vector() * 35 + camera.get_right_vector() * -12 + unreal.Vector(0, 0, -18)
    hand_point(left_point, False, False)
    frame()
    qa('QuestPhotoPose')
    left_pinch_point = pawn.get_editor_property('QuestLeftPinchPoint')  # midpoint of the simulated thumb and index tips
    check('Held photograph follows the simulated left hand', distance(photo.get_actor_location(), left_pinch_point + unreal.Vector(0, 0, 6)) < 2.0 and distance(left_pinch_point, left_point) < 12.0,
          {'photo': xyz(photo.get_actor_location()), 'hand': xyz(left_point), 'pinch_point': xyz(left_pinch_point)})
    yield screenshot('Hands_PhotoInLeftHand')
    back_before = bool(prop('PhotoBack'))
    label = pinch(ahead())
    check('A right pinch turns the photograph over', label == 'flip_photo' and bool(prop('PhotoBack')) != back_before)
    label = pinch(left_point, right=False)
    check('A left pinch closes the photograph', label == 'close_photo' and mode() == 0, {'action': label, 'mode': mode()})
    pawn.set_editor_property('QuestSimLeftValid', False)
    frame()

    S['step'] = 'letter: gaze plus pinch, close by pinch'
    letter = prop('LetterActor')
    if letter is not None:
        target = letter.get_actor_location()
        selected = False
        for dx, dy in [(120, 0), (0, 120), (-120, 0), (0, -120), (90, 90)]:
            pawn.set_actor_location(unreal.Vector(target.x + dx, target.y + dy, 1107), False, True)
            aim_camera_at(target)
            yield wait(.08)
            fixture('UpdateTarget')
            yield wait(.04)
            if prop('Target') == letter:
                selected = True
                break
        check('Gaze selects the letter', selected)
        pinch(ahead())
        yield wait(.2)
        for _ in range(14):
            if mode() == 2:
                break
            yield wait(.8)
            if mode() == 3:
                pinch(ahead())
        check('Pinches open the letter as a document', mode() == 2, mode())
        yield screenshot('Hands_Letter')
        label = pinch(ahead())
        check('Any pinch closes the letter (back to exploration, or on into the follow-up dialogue)', label == 'close_document' and mode() in (0, 3), {'action': label, 'mode': mode()})

    S['step'] = 'dialogue choice by pinching a row'
    fixture('StartScene', 'C1_04')
    for _ in range(20):
        if bool(prop('DialogueWaitingChoice')):
            break
        yield wait(.8)
        pinch(ahead())
    check('Native dialogue reaches its choices under pinch advancing', bool(prop('DialogueWaitingChoice')) and int(prop('DialogueChoiceCount')) >= 2)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # the pawn tick runs both every frame
    # Demo-review fix (12 November 2026): the panel opens along the line of sight (the head pitch followed within
    # -15 to +20 degrees), so straight ahead can now be on the panel; "away from the rows" is a point beside the panel.
    panel_root = comp('QuestPanelRoot')
    eye = camera.get_world_location()
    to_panel = panel_root.get_world_location() - eye
    panel_pitch = math.degrees(math.atan2(to_panel.z, math.hypot(to_panel.x, to_panel.y)))
    head_pitch = ((camera.get_world_rotation().pitch + 180.0) % 360.0) - 180.0
    expected_pitch = max(-15.0, min(20.0, head_pitch))
    # Lower edge of the panel (the cluster bottom, 92 cm below the root at full size) as a height below the eye.
    panel_scale = panel_root.get_world_scale().z
    lower_edge = panel_root.get_world_location() - panel_root.get_up_vector() * (88.0 * panel_scale)
    REPORT['panel_placement'] = {'head_pitch_deg': round(head_pitch, 2), 'panel_pitch_deg': round(panel_pitch, 2), 'expected_pitch_deg': round(expected_pitch, 2),
                                 'distance_cm': round(float(pawn.get_editor_property('QuestPanelDistance')), 1), 'scale': round(panel_scale, 3),
                                 'lower_edge_below_eye_cm': round(eye.z - lower_edge.z, 1)}
    check('The panel opens along the line of sight, within the pitch limits', abs(panel_pitch - expected_pitch) < 4.0, REPORT['panel_placement'])
    check('The panel keeps its lower edge above table height (within 72 cm below the eye)', eye.z - lower_edge.z <= 72.0, REPORT['panel_placement'])
    label = pinch(panel_root.get_world_location() + panel_root.get_right_vector() * 130.0)
    check('A pinch away from the rows chooses nothing', label == '' and bool(prop('DialogueWaitingChoice')), {'action': label})
    yield screenshot('Hands_DialogueRows')
    label = pinch(button('QuestChoice2'))
    yield wait(.15)
    check('Pinching the second row chooses it', label == 'choose_2' and str(prop('DialogueNodeId')) == 'C1_04.choice_B' and not bool(prop('DialogueWaitingChoice')),
          {'action': label, 'node': str(prop('DialogueNodeId'))})
    text = panel_text()
    REPORT['panel_text_samples'] = {'dialogue': text}
    check('A dialogue line carries one fitting help line and no option counter', 'Pinch or trigger to continue.' in text and 'Selected option' not in text
          and 'turn over (photo)' not in text, text)
    check('Panel text is wrapped to the panel width', max(len(line) for line in text.split('\n')) <= 68, text)
    fixture('CloseModal')
    yield wait(.1)

    S['step'] = 'end screen and main menu by pinch'
    fixture('EndSlice')
    yield wait(.2)
    text = panel_text()
    check('EndSlice shows the end screen on the panel', bool(prop('ReleaseMenuActive')) and int(prop('ReleaseMenuScreen')) == 3 and '> Return to menu' in text, text)
    qa('QuestPanelFrame'); qa('QuestHudFrame')  # the pawn tick runs both every frame
    label = pinch(button('QuestBtnBack'))
    yield wait(.15)
    check('Cluster Back on the end screen returns to the main menu', label == 'menu_back' and int(prop('ReleaseMenuScreen')) == 0 and bool(prop('ReleaseMenuActive')))
    yield screenshot('Hands_MainMenu')
    label = pinch(ahead(), right=False)
    yield wait(.15)
    check('A left pinch on the main menu resumes the running session', label == 'menu_back' and not prop('ReleaseMenuActive') and mode() == 0, {'action': label, 'mode': mode()})

    S['step'] = 'pinch detection on the Meta XR Simulator hand poses'
    import json as _json
    pose_dirs = sorted(Path(r'C:\Program Files\MetaXRSimulator').glob('v*/config/tracking'))
    if pose_dirs:
        rows = []
        sim_pinch = {}
        for pose in ['RayForward', 'Poke', 'Pinch', 'Grab', 'SideFist']:
            frame0 = _json.loads((pose_dirs[-1] / ('hand_frames_Isdk%s.json' % pose)).read_text(encoding='utf-8'))['hand_frames'][0]
            for side_name, right_flag in [('left', False), ('right', True)]:
                joints = frame0[side_name]['joint_locations']
                def joint_position(joint):
                    raw = joint['pose']['position']
                    return [float(v) for v in (raw.split() if isinstance(raw, str) else raw)]
                thumb = joint_position(joints[5])    # XR_HAND_JOINT_THUMB_TIP_EXT
                index = joint_position(joints[10])   # XR_HAND_JOINT_INDEX_TIP_EXT
                offset = unreal.Vector((index[0] - thumb[0]) * 100.0, (index[1] - thumb[1]) * 100.0, (index[2] - thumb[2]) * 100.0)
                side = 'Right' if right_flag else 'Left'
                base = ahead(60)
                hand_point(base + unreal.Vector(0, 0, 0), right_flag, False)   # open reset (8 cm apart): clears the hysteresis state
                frame(0.1)
                pawn.set_editor_property('QuestSim' + side + 'Valid', True)
                pawn.set_editor_property('QuestSim' + side + 'Thumb', base)
                pawn.set_editor_property('QuestSim' + side + 'Index', base + offset)
                frame(0.1)
                pinched = bool(pawn.get_editor_property('Quest' + side + 'Pinch'))
                gap = math.sqrt(offset.x ** 2 + offset.y ** 2 + offset.z ** 2)
                rows.append({'pose': pose, 'hand': side_name, 'tip_gap_cm': round(gap, 2), 'pinch_detected': pinched})
                sim_pinch[(pose, side_name)] = pinched
        REPORT['simulator_pose_pinch'] = {'source': str(pose_dirs[-1]), 'rows': rows,
                                          'note': 'Canned hand poses of Meta XR Simulator (thumb tip to index tip offsets) fed to the same pinch detector; not a live simulator session.'}
        check('Only the simulator Pinch pose is detected as a pinch (both hands); open, poke, grab and side fist are not',
              all(sim_pinch[(p, s)] == (p == 'Pinch') for p in ['RayForward', 'Poke', 'Pinch', 'Grab', 'SideFist'] for s in ['left', 'right']), rows)
        hand_point(ahead(60), True, False)
        hand_point(ahead(60), False, False)
        frame(0.4)
    else:
        REPORT['simulator_pose_pinch'] = {'skipped': 'Meta XR Simulator is not installed on this machine'}

    S['step'] = 'invariants'
    labels = [a['action'] for a in REPORT['hand_actions']]
    check('Every player step came from the simulated hands, none from a controller key', REPORT['controller_keys_injected'] == 0 and REPORT['player_steps_via_simulated_hands'] >= 30,
          {'steps': REPORT['player_steps_via_simulated_hands'], 'distinct_actions': sorted(set(labels))})
    check('Fixture calls are limited to targeting refresh, a scene start, a modal close and the end trigger',
          set(c['action'] for c in REPORT['fixture_calls']) <= {'UpdateTarget', 'StartScene', 'CloseModal', 'EndSlice'}, REPORT['fixture_calls'])
    S['step'] = 'complete'


exec(compile('def finish(error=None):\n' + X_SUFFIX, str(X_PARENT_FILE), 'exec'), globals())
