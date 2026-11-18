"""Trailer take director for the competition video (11 November 2026). PIE, Quest pawn, desktop preview camera.

Run through tools/RunTrailerTake.ps1 (visible editor, floating PIE window, window capture), flag -Quest3TrailerTake.
It reuses the harness of validate_quest3_xr.py (map fixture, isolated release profile, real front end) and plays:
  Part 1  real pinch-driven beats at a natural pace through the pawn's simulated fingertips (the same pinch, ray and
          dispatch code the OpenXR hand-tracking keypoints feed): title, New Game, the coach, a look around the room,
          the photograph, the letter, Mother's reply rows, the Chronowatch dial, the pause panel, a teleport.
  Part 2  scenic camera moves on the same map in both eras from matching positions (for match cuts). The era is shown
          with the manager's own SetGroupVisible on its PastActors / PresentActors arrays. These are views of the game
          world, not story progression: no story flag is written and the session is discarded.
Flags: -Quest3DemoOnly (Part 1 only), -Quest3ToJump (the timed first-time path to the jump, no demonstration beats),
-Quest3ChapterTwo (the path to the jump, then Chapter II to its end screen by pinch, 15 November 2026).
Evidence label: Unreal editor preview of the Quest build on PC with simulated hand input. Not a headset, not the APK,
not Meta XR Simulator. Report with UTC marks for every shot: game_unreal/validation/trailer/<run>/director_report.json.
"""
import time
from pathlib import Path
import unreal

X_ROOT = Path(unreal.Paths.project_dir()).resolve()
if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3TrailerTake'):
    raise RuntimeError('A -Quest3TrailerTake run with a dedicated -UserDir is required')
X_PARENT_FILE = X_ROOT / 'Python/validate_quest3_xr.py'
X_PARENT = X_PARENT_FILE.read_text(encoding='utf-8')
X_PREFIX, X_SEP1, X_REST = X_PARENT.partition('\ndef scenario():\n')
X_SCENARIO, X_SEP2, X_SUFFIX = X_REST.partition('\ndef finish(error=None):\n')
if not X_SEP1 or not X_SEP2:
    raise RuntimeError('Review changed the XR harness before adapting it for the trailer take')


def x_replace(text, old, new, count=1):
    if text.count(old) != count:
        raise RuntimeError('Changed harness anchor (%d expected): %s' % (count, old[:120]))
    return text.replace(old, new)


X_PREFIX = x_replace(X_PREFIX, "parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3XRQA')",
                     "parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3TrailerTake')")
X_PREFIX = x_replace(X_PREFIX, "'A queued -Quest3XRQA run", "'A queued -Quest3TrailerTake run")
X_PREFIX = x_replace(X_PREFIX, "'YQ3XR_'", "'YQ3TR_'", count=2)
X_PREFIX = x_replace(X_PREFIX, "REPORT_PATH = ROOT / 'quest3_xr_runtime_validation.json'",
                     "REPORT_PATH = ROOT / 'validation/trailer/director_report_latest.json'\n(ROOT / 'validation/trailer').mkdir(parents=True, exist_ok=True)")
X_PREFIX = x_replace(X_PREFIX, "SCREENS = ROOT / 'validation/quest3' / (STAMP + '_xr')", "SCREENS = ROOT / 'validation/trailer' / STAMP")
X_PREFIX = x_replace(X_PREFIX, "'scope': 'Native Quest 3 Blueprint adapter on the Release story map:",
                     "'scope': 'Trailer take: Unreal editor preview of the Quest build with simulated hand input and scenic camera moves (not a test, not a headset):")
X_SUFFIX = x_replace(X_SUFFIX, "'QUEST3_XR_RUNTIME_VALIDATION '", "'QUEST3_TRAILER_TAKE '")
exec(compile(X_PREFIX, str(X_PARENT_FILE), 'exec'), globals())
REPORT['marks'] = []
REPORT['hand_actions'] = []
REPORT['footage_label'] = 'Unreal editor preview of the Quest build on PC, simulated hand input; scenic shots use the manager era visibility; not a headset, not the APK'
EYE = 72.0  # fallback camera height above the pawn origin (camera at +160 under an origin at -88)
import sys as x_sys
if str(X_ROOT / 'Python') not in x_sys.path:
    x_sys.path.insert(0, str(X_ROOT / 'Python'))
import quest3_sim_hand


def mark(name):
    REPORT['marks'].append({'name': name, 'utc': time.time()})
    write()


def V(x, y, z):
    return unreal.Vector(x, y, z)


def lerp(a, b, u):
    return unreal.Vector(a.x + (b.x - a.x) * u, a.y + (b.y - a.y) * u, a.z + (b.z - a.z) * u)


def ease(u):
    return u * u * (3 - 2 * u)


def set_hand(point, right=True, pinched=False):
    pawn = S['pawn']
    side = 'Right' if right else 'Left'
    c = camera()
    # Open hand: the thumb tip rests about 7 cm from the index tip, toward the thumb's side, a little below and behind
    # (beyond the 4.5 cm release distance and the 6 cm aim latch). Pinched: the two tips meet.
    thumb = point if pinched else point + c.get_right_vector() * (-5.0 if right else 5.0) + c.get_up_vector() * -4.0 + c.get_forward_vector() * -2.5
    pawn.set_editor_property('QuestSimHands', True)
    pawn.set_editor_property('QuestSim' + side + 'Valid', True)
    pawn.set_editor_property('QuestSim' + side + 'Index', point)
    pawn.set_editor_property('QuestSim' + side + 'Thumb', thumb)
    # The pawn draws its hands from 25 keypoints; without hardware they are put on a fixed relaxed pose that ends in the
    # same two fingertips (quest3_sim_hand.py). The pose is simulated; the drawing code is the game's.
    quest3_sim_hand.place(pawn, right, point, thumb)


def drop_hand(right=True):
    S['pawn'].set_editor_property('QuestSim' + ('Right' if right else 'Left') + 'Valid', False)


def hands_off():
    S['pawn'].set_editor_property('QuestSimLeftValid', False)
    S['pawn'].set_editor_property('QuestSimRightValid', False)
    S['pawn'].set_editor_property('QuestSimHands', False)


def camera():
    return comp('QuestCamera')


def ahead(distance=45, right=0.0, up=0.0):
    c = camera()
    return c.get_world_location() + c.get_forward_vector() * distance + c.get_right_vector() * right + c.get_up_vector() * up


def toward(point, distance=45):
    """A point `distance` cm from the eye on the line to a world point: where a pointing hand would be."""
    eye = camera().get_world_location()
    d = point - eye
    length = max(1.0, d.length())
    return eye + d * (distance / length)


def rest(right=True):
    return ahead(38, 16 if right else -16, -24)


def glide(seconds, a_fn, b_fn, right=True):
    """Moves an open hand from a() to b() over `seconds` (functions, so a moving head keeps the path attached)."""
    start = time.time()
    while True:
        u = min(1.0, (time.time() - start) / seconds)
        set_hand(lerp(a_fn(), b_fn(), ease(u)), right, False)
        yield wait(0.01)
        if u >= 1.0:
            return


def pinch_at(point_fn, right=True, hold=0.3, settle_after=0.55, expect=None):
    set_hand(point_fn(), right, False)
    yield wait(0.12)
    set_hand(point_fn(), right, True)
    yield wait(hold)
    label = str(S['pawn'].get_editor_property('QuestLastHandAction'))
    set_hand(point_fn(), right, False)
    REPORT['hand_actions'].append({'hand': 'right' if right else 'left', 'action': label, 'expected': expect, 'step': S['step'], 'utc': time.time()})
    write()
    yield wait(settle_after)


def reach_and_pinch(target_fn, right=True, travel=0.9, expect=None, hold=0.3):
    yield from glide(travel, lambda: rest(right), lambda: toward(target_fn()), right)
    yield wait(0.25)
    yield from pinch_at(lambda: toward(target_fn()), right, hold, expect=expect)
    yield from glide(0.6, lambda: toward(target_fn()), lambda: rest(right), right)


def hold_left(seconds=1.3):
    point = lambda: ahead(40, -14, -10)
    set_hand(point(), False, False)
    yield wait(0.25)
    set_hand(point(), False, True)
    yield wait(seconds)
    label = str(S['pawn'].get_editor_property('QuestLastHandAction'))
    set_hand(point(), False, False)
    REPORT['hand_actions'].append({'hand': 'left-held', 'action': label, 'step': S['step'], 'utc': time.time()})
    yield wait(0.5)


def button(name):
    return comp(name).get_world_location()


def mode():
    return int(prop('Mode'))


def look(seconds, target_a, target_b):
    start = time.time()
    while True:
        u = min(1.0, (time.time() - start) / seconds)
        aim_camera_at(lerp(target_a, target_b, ease(u)))
        yield wait(0.01)
        if u >= 1.0:
            return


def place(pos):
    """Puts the preview camera at a world position (the pawn origin sits EYE below it)."""
    S['pawn'].set_actor_location(unreal.Vector(pos.x, pos.y, pos.z - EYE), False, True)


def dolly(seconds, pos_a, pos_b, target_a, target_b):
    start = time.time()
    while True:
        u = min(1.0, (time.time() - start) / seconds)
        e = ease(u)
        place(lerp(pos_a, pos_b, e))
        aim_camera_at(lerp(target_a, target_b, e))
        yield wait(0.01)
        if u >= 1.0:
            return


def m(x, y, z):
    """Art-gate coordinates are Blender metres: Unreal = (100x, -100y, 100z)."""
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


def show_era(past):
    manager = S['manager']
    manager.call_method('SetGroupVisible', args=(manager.get_editor_property('PastActors'), bool(past)))
    manager.call_method('SetGroupVisible', args=(manager.get_editor_property('PresentActors'), not bool(past)))


def fade(from_alpha, to_alpha, seconds, white=True):
    manager_camera = unreal.GameplayStatics.get_player_camera_manager(S['world'], 0)
    colour = unreal.LinearColor(1.0, 0.97, 0.9, 1.0) if white else unreal.LinearColor(0, 0, 0, 1)
    manager_camera.start_camera_fade(from_alpha, to_alpha, seconds, colour, False, True)


def gaze_select(actor, offsets, z=1107):
    target = actor.get_actor_location()
    for dx, dy in offsets:
        S['pawn'].set_actor_location(unreal.Vector(target.x + dx, target.y + dy, z), False, True)
        aim_camera_at(target)
        yield wait(0.1)
        action('UpdateTarget')
        yield wait(0.05)
        if prop('Target') == actor:
            return
    REPORT.setdefault('notes', []).append('gaze did not select ' + actor.get_actor_label())


SCENIC = [
    # name, seconds, pos_a, pos_b, target_a, target_b  (Blender metres, from verdant/story_views.py and the close-up job)
    ('HarborOverlook', 8.0, (4.5, 14.0, 13.22), (5.3, 14.6, 13.22), (40.0, 30.0, 6.5), (46.0, 22.0, 5.5)),
    ('UphillCathedral', 8.0, (0.4, -21.0, 9.72), (0.5, -18.6, 9.9), (1.5, 52.0, 26.0), (1.5, 52.0, 31.0)),
    ('HomeFront', 7.0, (1.4, -16.6, 10.22), (0.4, -15.6, 10.3), (-5.0, -12.0, 11.71), (-5.0, -12.4, 11.9)),
    ('ClinicCourtyard', 7.0, (-0.2, -0.4, 11.72), (-0.9, -1.4, 11.72), (-6.8, -4.6, 11.10), (-6.8, -4.6, 11.3)),
    ('Gate', 6.0, (1.6, -12.4, 10.58), (0.9, -12.4, 10.62), (-2.2, -12.4, 11.6), (-2.2, -12.4, 11.75)),
    ('Shop', 6.0, (-0.6, 2.6, 12.12), (-0.2, 3.2, 12.12), (2.4, 3.1, 11.4), (2.4, 3.1, 11.5)),
    ('Wing', 6.0, (-0.2, -8.2, 10.96), (-0.9, -8.9, 11.0), (-6.0, -9.6, 12.6), (-6.0, -9.6, 12.8)),
]


def scenario():
    S['step'] = 'load the story map with the XR game-mode fixture'
    old_world = EDITOR.get_editor_world()
    if old_world:
        S['original_map'] = old_world.get_outer().get_name()
    check('Story map loads', LEVEL.load_level(MAP))
    apply_fixture()
    go = ROOT / 'validation/trailer/go.txt'
    yield until(lambda: go.exists(), 'go signal (viewport made immersive, recorder running)', 300)
    yield wait(4.0)  # the recorder starts on the same signal
    yield begin()
    settle()
    yield wait(1.5)
    pawn = S['pawn']
    cam = camera()
    pawn.set_editor_property('QuestAutoGazeEnabled', False)
    pawn.set_editor_property('QuestSimHands', True)
    pawn.set_editor_property('QuestSimLeftValid', False)
    pawn.set_editor_property('QuestSimRightValid', False)
    movement = pawn.get_component_by_class(unreal.CharacterMovementComponent)
    # -Quest3ToJump: the timed first-time path (title, the recollections read through, photograph, letter, Mother, the
    # bench, the gate, the jump) with no demonstration beats; implies the pinch-driven part only.
    TO_JUMP = unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3ToJump')
    # -Quest3ChapterTwo (15 November 2026): the same path to the jump (the recollections skipped after three lines), then
    # Chapter II by pinch at a filming pace: Neri, the Healer, the linen, the canvas choice, the installation, the
    # return through the gate, the changed record, Mother at home. For the longer trailer; not a timing.
    CH2 = unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3ChapterTwo')
    TO_JUMP = TO_JUMP or CH2
    REPORT['take_mode'] = 'Chapter I to the jump, then Chapter II by pinch' if CH2 else 'timed run to the first jump' if TO_JUMP else 'trailer beats'

    # ---- Part 1: pinch-driven beats ----
    S['step'] = 'title menu'
    mark('title_hold')
    yield wait(2.0 if TO_JUMP else 5.0)
    mark('title_pinch_new_game')
    yield from reach_and_pinch(lambda: button('QuestBtnOk'), True, 1.2, 'menu_select')
    yield until(lambda: bool(prop('ReleaseSessionStarted')), 'New Game started by pinch', 12)
    mark('recollections')
    yield wait(1.0)
    for _ in range(40 if TO_JUMP and not CH2 else 3):
        if not bool(prop('IntroActive')):
            break
        yield wait(2.2 if TO_JUMP else 2.6)
        yield from pinch_at(lambda: ahead(42, 10, -6), True, expect='advance_dialogue')
    if bool(prop('IntroActive')):
        yield from pinch_at(lambda: ahead(40, -12, -8), False, expect='skip_recollections')
        drop_hand(False)
    yield wait(1.2)

    def scenic_part():
        S['step'] = 'scenic'
        hands_off()
        comp('QuestPointer').set_hidden_in_game(True, False)
        movement.set_movement_mode(unreal.MovementMode.MOVE_NONE)
        yield wait(0.5)
        for past in (False, True):
            show_era(past)
            yield wait(2.5)
            for name, seconds, pa, pb, ta, tb in SCENIC:
                place(m(*pa))
                aim_camera_at(m(*ta))
                yield wait(1.0)
                mark('scenic_%s_%s' % ('Past' if past else 'Present', name))
                yield from dolly(seconds, m(*pa), m(*pb), m(*ta), m(*tb))
                yield wait(0.4)
        # The jump, staged at the gate: present, a warm white fade, the same view in the past.
        show_era(False)
        place(m(1.6, -12.4, 10.58))
        aim_camera_at(m(-2.2, -12.4, 11.6))
        yield wait(2.0)
        mark('jump_present')
        yield from dolly(3.0, m(1.6, -12.4, 10.58), m(1.2, -12.4, 10.6), m(-2.2, -12.4, 11.6), m(-2.2, -12.4, 11.65))
        fade(0.0, 1.0, 0.9)
        yield wait(1.0)
        show_era(True)
        mark('jump_swap')
        yield wait(0.6)
        fade(1.0, 0.0, 1.6)
        yield from dolly(5.0, m(1.2, -12.4, 10.6), m(0.4, -12.4, 10.66), m(-2.2, -12.4, 11.65), m(-2.2, -12.4, 11.8))
        mark('jump_end')
        # Home doorway toward the sea, present era, for the opening.
        show_era(False)
        place(V(-1000, 1500, 1180))
        aim_camera_at(V(-460, 1150, 1150))
        yield wait(2.0)
        mark('doorway_present')
        yield from dolly(7.0, V(-1000, 1500, 1180), V(-900, 1430, 1178), V(-460, 1150, 1150), V(-430, 1150, 1150))
        place(V(-620, 1240, 1173))
        yield wait(0.5)
        mark('room_wide_present')
        yield from dolly(7.0, V(-485, 1135, 1185), V(-520, 1160, 1180), V(-1000, 1600, 1100), V(-1000, 1420, 1110))

    if unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3ScenicOnly'):
        # Scenic shots from a fresh New Game (15 November 2026): the story has not moved on, so Mother is in the home
        # and not at the gate, where she stands in front of two of the scenic cameras once the bench is done.
        REPORT['take_mode'] = 'scenic shots only, straight after New Game'
        yield from scenic_part()
        movement.set_movement_mode(unreal.MovementMode.MOVE_WALKING)
        mark('end')
        yield wait(1.0)
        S['step'] = 'complete'
        return

    S['step'] = 'coach'
    mark('coach')
    yield wait(2.5)
    # Tutorial (13 November 2026): two lines on the plate, each gone once done. Turning here does the move lesson; the
    # photograph below does the other. Nothing is switched off by the script: the tutorial ends by being played.
    REPORT['tutorial'] = {'shown_at_start': int(pawn.get_editor_property('QuestOnboardStep')) == 1}
    if int(pawn.get_editor_property('QuestOnboardStep')) == 1:
        yield from reach_and_pinch(lambda: button('QuestBtnTurnRight'), True, 0.9, 'turn_right')
        yield wait(1.4)
        yield from reach_and_pinch(lambda: button('QuestBtnTurnLeft'), True, 0.9, 'turn_left')
    REPORT['tutorial']['moved_after_turning'] = bool(pawn.get_editor_property('QuestOnboardMoved'))
    yield wait(1.0)

    if not TO_JUMP:
        S['step'] = 'look around the room'
        mark('room_pan')
        drop_hand(True)
        eye = cam.get_world_location()
        yield from look(7.0, V(eye.x - 300, eye.y + 260, eye.z - 30), V(eye.x - 300, eye.y - 160, eye.z - 20))
        yield wait(0.5)

    S['step'] = 'photograph'
    photo = prop('PhotoActor')
    yield from gaze_select(photo, [(150, 0), (0, 150), (-150, 0), (0, -150), (100, 100)])
    mark('photo_gaze')
    yield wait(2.2)
    yield from glide(0.8, lambda: rest(True), lambda: ahead(44, 4, -4), True)
    yield from pinch_at(lambda: ahead(44, 4, -4), True, expect='interact')
    mark('photo_dialogue')
    REPORT['tutorial']['ended_by_using_the_photograph'] = int(pawn.get_editor_property('QuestOnboardStep')) == 0 and bool(pawn.get_editor_property('QuestOnboardUsed'))
    write()
    for _ in range(12):
        if mode() == 1:
            break
        yield wait(2.4)
        if mode() == 3:
            yield from pinch_at(lambda: ahead(44, 4, -4), True, expect='advance_dialogue')
    mark('photo_in_hand')
    left_a = lambda: ahead(34, -18, -20)
    left_b = lambda: ahead(36, -6, -10)
    yield from glide(1.6, left_a, left_b, False)
    yield wait(1.6)
    yield from pinch_at(lambda: ahead(44, 10, -6), True, expect='flip_photo')
    mark('photo_flipped')
    yield from glide(1.4, left_b, lambda: ahead(36, -10, -6), False)
    yield wait(2.0)
    yield from pinch_at(lambda: ahead(36, -10, -6), False, expect='close_photo')
    drop_hand(False)
    yield wait(1.0)

    S['step'] = 'letter'
    letter = prop('LetterActor')
    if letter is not None:
        yield from gaze_select(letter, [(120, 0), (0, 120), (-120, 0), (0, -120), (90, 90)])
        mark('letter_gaze')
        yield wait(1.8)
        yield from pinch_at(lambda: ahead(44, 4, -4), True, expect='interact')
        for _ in range(12):
            if mode() == 2:
                break
            yield wait(2.2)
            if mode() == 3:
                yield from pinch_at(lambda: ahead(44, 4, -4), True, expect='advance_dialogue')
        mark('letter_open')
        yield wait(4.0)
        yield from pinch_at(lambda: ahead(44, 4, -4), True, expect='close_document')
        for _ in range(8):
            if mode() == 0:
                break
            yield wait(2.0)
            if mode() == 3:
                yield from pinch_at(lambda: ahead(44, 4, -4), True, expect='advance_dialogue')

    S['step'] = 'mother'
    mother = prop('MotherActor')
    spot = mother.get_actor_location()
    pawn.set_actor_location(unreal.Vector(spot.x + 190, spot.y + 30, 1107), False, True)
    aim_camera_at(unreal.Vector(spot.x, spot.y, spot.z + 140))  # her face (the actor origin is at her feet)
    yield wait(0.4)
    mark('mother_scene')
    action('StartScene', 'C1_04')
    for _ in range(24):
        if bool(prop('DialogueWaitingChoice')):
            break
        yield wait(2.5)
        yield from pinch_at(lambda: ahead(44, 6, -6), True, expect='advance_dialogue')
    mark('mother_choices')
    yield wait(2.0)
    if bool(prop('DialogueWaitingChoice')):
        yield from glide(1.0, lambda: rest(True), lambda: toward(button('QuestChoice1')), True)
        yield wait(0.8)
        yield from glide(0.9, lambda: toward(button('QuestChoice1')), lambda: toward(button('QuestChoice2')), True)
        yield wait(0.7)
        yield from pinch_at(lambda: toward(button('QuestChoice2')), True, expect='choose_2')
        mark('mother_chosen')
    # The conversation is played to its end (12 November 2026, later): the bench will not start the calibration until
    # Mother has been heard out, and cutting the scene short left the story at "speak with Mother".
    for _ in range(20):
        if mode() != 3:
            break
        yield wait(2.2)
        if mode() == 3 and not bool(prop('DialogueWaitingChoice')):
            yield from pinch_at(lambda: ahead(44, 6, -6), True, expect='advance_dialogue')
    mark('mother_done')
    REPORT['mother_spoken'] = bool(prop('MotherSpoken'))
    if mode() != 0:
        action('CloseModal')
    yield wait(0.8)

    S['step'] = 'workbench and watch'
    bench = prop('BenchActor')
    if bench is not None:
        b = bench.get_actor_location()
        pawn.set_actor_location(unreal.Vector(b.x + 150, b.y + 60, 1107), False, True)
        mark('workbench')
        yield from look(5.0, unreal.Vector(b.x, b.y - 40, b.z + 20), unreal.Vector(b.x, b.y + 30, b.z + 5))
    yield wait(0.5)

    # Calibration at the bench, by pinches (12 November 2026, later): the fault, the prepared contact, placing it, two
    # tests. The watch face with its hand only exists on a calibrated watch. Each stage is tried by gaze and pinch; a
    # stage that does not register is repeated once through the manager's own Interact and listed in the report.
    S['step'] = 'calibration'
    around = [(150, 60), (150, 0), (120, 90), (0, 150), (0, -150), (-150, 0)]
    REPORT['calibration'] = {'by_pinch': [], 'by_fixture': []}

    def reply_for():
        """The reply row to pinch: the first, except the changed-record scene, whose first reply belongs to a traveller
        who read the original memorial before leaving (the story acceptance chooses the same way)."""
        node = str(prop('DialogueNodeId')).split('.', 1)[0]
        wanted = 2 if node == 'C2_06' and not bool(prop('OriginalMemorialRead')) else 1
        return max(1, min(wanted, int(prop('DialogueChoiceCount'))))

    def talk_through(limit=14, browse=False, choice_mark=None):
        for _ in range(limit):
            if mode() != 3:
                return
            yield wait(1.5)
            if mode() == 3 and bool(prop('DialogueWaitingChoice')):
                # A reply is asked for: read the rows, then pinch one (the first, see reply_for).
                row = reply_for()
                name = 'QuestChoice%d' % row
                if choice_mark:
                    mark(choice_mark)
                if browse and int(prop('DialogueChoiceCount')) >= 2:
                    other = 'QuestChoice%d' % (2 if row == 1 else 1)
                    yield from glide(0.9, lambda: rest(True), lambda: toward(button(other)), True)
                    yield wait(1.1)
                    yield from glide(0.9, lambda: toward(button(other)), lambda: toward(button(name)), True)
                    yield wait(1.0)
                else:
                    yield from glide(0.8, lambda: rest(True), lambda: toward(button(name)), True)
                    yield wait(2.0)
                yield from pinch_at(lambda: toward(button(name)), True, expect='choose_%d' % row)
            elif mode() == 3:
                yield from pinch_at(lambda: ahead(44, 6, -6), True, expect='advance_dialogue')

    def pinch_object(name, done, label):
        actor = prop(name)
        if actor is None:
            return
        yield from gaze_select(actor, around)
        yield wait(0.7)
        yield from glide(0.7, lambda: rest(True), lambda: ahead(44, 4, -4), True)
        yield from pinch_at(lambda: ahead(44, 4, -4), True, expect='interact')
        yield wait(0.4)
        if done():
            REPORT['calibration']['by_pinch'].append(label)
        else:
            action('UpdateTarget')
            action('Interact')
            yield wait(0.4)
            REPORT['calibration']['by_fixture' if done() else 'by_pinch'].append(label + ('' if done() else ' (not registered)'))

    if prop('BenchActor') is not None and not bool(prop('WatchCalibrated')):
        mark('bench_fault')
        yield from pinch_object('BenchActor', lambda: bool(prop('RepairIdentified')) or mode() == 3, 'bench: the fault')
        yield from talk_through()
        mark('contact')
        yield from pinch_object('ComponentActor', lambda: bool(prop('ComponentCollected')), 'the prepared contact')
        yield from talk_through()
        mark('bench_place')
        yield from pinch_object('BenchActor', lambda: bool(prop('ComponentPlaced')) or mode() == 3, 'bench: placing the contact')
        yield from talk_through()
        for number in (1, 2):
            mark('bench_test_%d' % number)
            yield from pinch_object('BenchActor', lambda: bool(prop('Testing')) or int(prop('CalibrationTests')) >= number, 'bench: test %d' % number)
            for _ in range(60):
                if not bool(prop('Testing')):
                    break
                yield wait(0.25)
            yield wait(0.8)
            yield from talk_through()
        mark('calibrated')
        yield wait(1.0)
    REPORT['calibration']['watch_calibrated'] = bool(prop('WatchCalibrated'))
    write()
    if mode() != 0:
        action('CloseModal')
        yield wait(0.5)

    # The watch hand, turned by a pinch: reach to the hand, pinch, carry the pinch round the centre, let go.
    def on_dial(angle, radius=16.0):
        a = math.radians(angle)
        panel = comp('QuestPanelRoot')
        return unreal.MathLibrary.transform_location(panel.get_world_transform(), unreal.Vector(2.0, -42.0 + math.sin(a) * radius, math.cos(a) * radius))

    def turn(to_past, seconds):
        start_angle = 50.0 if int(prop('SelectedEra')) == 1 else -50.0
        end_angle = 50.0 if to_past else -50.0
        yield from glide(1.0, lambda: rest(True), lambda: toward(on_dial(start_angle)), True)
        yield wait(0.6)
        set_hand(toward(on_dial(start_angle)), True, True)
        yield wait(0.4)
        label = str(pawn.get_editor_property('QuestLastHandAction'))
        REPORT['hand_actions'].append({'hand': 'right', 'action': label, 'expected': 'dial_grab', 'step': S['step'], 'utc': time.time()})
        began = time.time()
        while True:
            u = min(1.0, (time.time() - began) / seconds)
            set_hand(toward(on_dial(start_angle + (end_angle - start_angle) * ease(u))), True, True)
            yield wait(0.01)
            if u >= 1.0:
                break
        yield wait(0.7)
        set_hand(toward(on_dial(end_angle)), True, False)
        REPORT['hand_actions'].append({'hand': 'right', 'action': 'era_%d' % int(prop('SelectedEra')), 'expected': 'era_%d' % (1 if to_past else 0),
                                       'step': S['step'], 'utc': time.time()})
        write()
        yield wait(0.9)
        yield from glide(0.7, lambda: toward(on_dial(end_angle)), lambda: rest(True), True)

    # The watch on the wrist (16 November 2026, night): the off hand comes up as one reads a watch, the watch is seen
    # running on the wrist, and the main hand pinches it open. The pose is simulated (quest3_sim_hand.watch_pose); the
    # watch, its placement on the wrist and the pinch that opens it are the game's.
    def wrist_open():
        def raised(u):
            quest3_sim_hand.place_watch(pawn, False, reach=34.0, across=-3.0 - 12.0 * (1 - u), below=-9.0 - 18.0 * (1 - u))
        # The main hand goes down and out of sight first, so the wrist is seen alone.
        if bool(pawn.get_editor_property('QuestSimRightValid')):
            parked = pawn.get_editor_property('QuestSimRightIndex')
            yield from glide(0.5, lambda: parked, lambda: rest(True), True)
        drop_hand(True)
        began = time.time()
        mark('wrist_raise')
        while True:
            u = min(1.0, (time.time() - began) / 1.0)
            raised(ease(u))
            yield wait(0.01)
            if u >= 1.0:
                break
        mark('wrist_watch_shown')
        yield wait(2.4)

        def on_wrist():
            dial = comp('QuestWristDial').get_world_location()
            return toward(dial, max(12.0, (dial - camera().get_world_location()).length() - 1.2))
        REPORT['wrist_watch'] = {'shown': bool(pawn.get_editor_property('QuestWristShown')), 'calibrated': bool(prop('WatchCalibrated'))}
        yield from glide(0.9, lambda: rest(True), on_wrist, True)
        yield wait(0.35)
        mark('wrist_pinch')
        yield from pinch_at(on_wrist, True, expect='open_watch_wrist')
        REPORT['wrist_watch']['opened'] = mode() == 4
        write()
        yield from glide(0.6, on_wrist, lambda: rest(True), True)
        began = time.time()
        while True:
            u = min(1.0, (time.time() - began) / 0.7)
            raised(1.0 - ease(u))
            yield wait(0.01)
            if u >= 1.0:
                break
        drop_hand(False)

    # ---- Chapter II by pinch (15 November 2026, -Quest3ChapterTwo) ----
    # The player is placed where the four-route story acceptance stands for each object (validate_brief_m2.py
    # standing_points) and looks at it; the use is a pinch on the game's own gaze target. A step that does not register
    # is repeated once through the manager's own Interact and listed in the report as 'fixture'.
    C2_SPOTS = {'NeriActor': (-35, 1050, 1013), 'HealerActor': (20, 580, 1060), 'SelaActor': (-25, -300, 1148),
                'WaterActor': (0, 640, 1054), 'LinenActor': (0, -235, 1141.5), 'LinenTrayActor': (0, 520, 1066),
                'CanvasActor': (0, -365, 1154.5), 'ClinicInstallActor': (20, 390, 1079),
                'HarborInstallActor': (-60, -535, 1171.5), 'MemorialActor': (-245, 1510, 1109)}
    C2_HOME = ('MotherActor', 'AnchorActor', 'MemorialActor')

    def body(actor):
        if actor.get_component_by_class(unreal.SkeletalMeshComponent):
            return actor.get_actor_bounds(False)[0]
        return actor.get_actor_location()

    def stand_at(ref):
        actor = prop(ref)
        if actor is None:
            return False
        origin = actor.get_actor_location()
        spots = [unreal.Vector(*C2_SPOTS[ref])] if ref in C2_SPOTS else []
        for dx, dy in {'AnchorActor': [(0, -155)], 'MotherActor': [(200, 45)]}.get(ref, []) + [(160, 80), (190, 0), (160, -80), (0, -185), (0, 185)]:
            spots.append(unreal.Vector(origin.x + dx, origin.y + dy, 1109 if ref in C2_HOME else 1020 - (origin.y + dy) * .1 + 98))
        for spot in spots:
            movement.stop_movement_immediately()
            pawn.set_actor_location(spot, False, True)
            yield wait(0.12)
            for _ in range(10):
                aim_camera_at(body(actor))
                yield wait(0.04)
                action('UpdateTarget')
                if prop('Target') == actor:
                    return True
        return False

    def use(ref, done, label, hold=0.9):
        gazed = yield from stand_at(ref)
        yield wait(hold)
        # The pinch stays within 6 degrees of the gaze: looking down at a low object brings the button row up into the
        # middle of the view, and a pinch further from the gaze than that presses the button under it (take 1 opened the
        # journal four times this way).
        yield from glide(0.9, lambda: rest(True), lambda: ahead(44, 2, -2.5), True)
        yield wait(0.5)
        yield from pinch_at(lambda: ahead(44, 2, -2.5), True, expect='interact')
        yield wait(0.4)
        by = 'pinch'
        if not done():
            yield from put_away()
            action('UpdateTarget')
            action('Interact')
            yield wait(0.4)
            by = 'fixture' if done() else 'not registered'
        REPORT['chapter_two'].append({'step': label, 'gazed': bool(gazed), 'by': by, 'mode': mode(), 'utc': time.time()})
        write()

    def put_away():
        """Closes whatever a use left open: a document by a main-hand pinch, another panel by the off hand."""
        if mode() == 2:
            yield from pinch_at(lambda: ahead(44, 4, -4), True, expect='close_document')
            yield wait(0.4)
            yield from talk_through(30)
        if mode() in (1, 4, 5):
            yield from pinch_at(lambda: ahead(40, -14, -10), False, expect={1: 'close_photo', 4: 'close_watch', 5: 'close_journal'}[mode()])
            drop_hand(False)
            yield wait(0.4)
        if mode() not in (0, 3, 7):
            action('CloseModal')
            REPORT['chapter_two'].append({'step': 'a panel closed by the manager', 'by': 'fixture', 'mode': mode(), 'utc': time.time()})
            yield wait(0.4)

    def level_ahead():
        f = cam.get_forward_vector()
        flat = unreal.Vector(f.x, f.y, 0)
        length = max(0.01, flat.length())
        return unreal.Vector(flat.x / length, flat.y / length, 0)

    def chapter_two():
        REPORT['chapter_two'] = []
        S['step'] = 'chapter two: arrival'
        mark('c2_arrival')
        drop_hand(True)
        eye = cam.get_world_location()
        fwd, side = level_ahead(), cam.get_right_vector()
        yield from look(7.0, eye + fwd * 600 - side * 380 + V(0, 0, 40), eye + fwd * 600 + side * 380 + V(0, 0, 10))
        yield wait(0.5)

        S['step'] = 'chapter two: a move by pinch in the past'
        here = pawn.get_actor_location()
        landings = [a for a in tagged('Quest.Teleport') if not bool(a.get_editor_property('hidden'))]
        pairs = [(a, b) for a in landings for b in landings if a != b and 150 < distance(a.get_actor_location(), b.get_actor_location()) < 480
                 and abs(a.get_actor_location().z - b.get_actor_location().z) < 110]
        pairs.sort(key=lambda p: distance(p[0].get_actor_location(), here))
        mark('c2_teleport')
        for start, destination in pairs[:14]:
            pawn.set_actor_location(start.get_actor_location() + unreal.Vector(0, 0, 88), False, True)
            aim_camera_at(destination.get_actor_location() + unreal.Vector(0, 0, 60))
            yield wait(0.1)
            # Only a landing the eye can see: nothing between the eye and the disc.
            spot = destination.get_actor_location() + unreal.Vector(0, 0, 4)
            hit = unreal.SystemLibrary.line_trace_single(S['world'], cam.get_world_location(), spot, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                         False, [pawn], unreal.DrawDebugTrace.NONE, True)
            if hit is not None:
                found = hit.to_tuple()
                if bool(found[0]) and found[9] != destination and distance(found[4], spot) > 45:
                    continue
            yield wait(1.6)
            yield from glide(0.9, lambda: rest(True), lambda d=destination: toward(d.get_actor_location() + unreal.Vector(0, 0, 2)), True)
            yield wait(0.4)
            yield from pinch_at(lambda d=destination: toward(d.get_actor_location() + unreal.Vector(0, 0, 2)), True, expect='teleport')
            yield wait(1.6)
            if REPORT['hand_actions'][-1]['action'] == 'teleport':
                break

        S['step'] = 'chapter two: Neri'
        mark('c2_neri')
        yield from use('NeriActor', lambda: mode() == 3 or bool(prop('NeriMet')), 'Neri', 1.6)
        yield wait(1.6)
        yield from talk_through(60, True, 'c2_neri_reply')
        yield from put_away()

        S['step'] = 'chapter two: the Healer and the linen'
        mark('c2_healer')
        yield from use('HealerActor', lambda: mode() == 3, 'the Healer', 1.6)
        yield wait(1.6)
        yield from talk_through(60, True, 'c2_healer_reply')
        yield from put_away()
        mark('c2_water')
        yield from use('WaterActor', lambda: True, 'the water')
        yield from talk_through(30)
        yield from put_away()
        mark('c2_sela')
        yield from use('SelaActor', lambda: mode() == 3, 'Sela', 1.4)
        yield wait(1.4)
        yield from talk_through(60, True)
        yield from put_away()
        mark('c2_linen')
        yield from use('LinenActor', lambda: int(prop('LinenState')) >= 2, 'the wrapped linen picked up', 1.8)
        yield wait(1.8)
        yield from talk_through(30)
        yield from put_away()
        mark('c2_linen_tray')
        yield from use('LinenTrayActor', lambda: int(prop('LinenState')) >= 3 or mode() == 3, 'the linen delivered', 1.6)
        yield wait(1.6)
        yield from talk_through(60)
        yield from put_away()
        REPORT['chapter_two_linen'] = {'state': int(prop('LinenState')), 'healer_trust': int(prop('HealerTrust'))}

        S['step'] = 'chapter two: the canvas'
        mark('c2_healer_canvas')
        yield from use('HealerActor', lambda: mode() == 3, 'the Healer: the storm', 1.2)
        yield wait(1.2)
        yield from talk_through(60, True)
        yield from put_away()
        mark('c2_sela_canvas')
        yield from use('SelaActor', lambda: mode() == 3, 'Sela: where the canvas goes', 1.2)
        yield wait(1.2)
        yield from talk_through(60, True, 'c2_canvas_choice')
        yield from put_away()
        mark('c2_canvas')
        yield from use('CanvasActor', lambda: bool(prop('CanvasOwned')), 'the canvas picked up', 1.8)
        yield wait(1.8)
        yield from talk_through(30)
        yield from put_away()
        plan = int(prop('CanvasPlan'))
        site = 'HarborInstallActor' if plan == 2 else 'ClinicInstallActor'
        mark('c2_install')
        yield from use(site, lambda: int(prop('StormCover')) != 0, 'the canvas put up (%s)' % ('harbor' if plan == 2 else 'clinic'), 2.2)
        mark('c2_installed')
        yield wait(2.6)
        yield from talk_through(60)
        yield from put_away()
        mark('c2_report')
        yield from use('HealerActor', lambda: mode() == 3 or bool(prop('HealerReportDone')), 'the Healer: the report', 1.2)
        yield wait(1.2)
        yield from talk_through(60, True)
        yield from put_away()
        REPORT['chapter_two_canvas'] = {'plan': plan, 'storm_cover': int(prop('StormCover')), 'healer_trust': int(prop('HealerTrust')),
                                        'report_done': bool(prop('HealerReportDone'))}
        write()

        S['step'] = 'chapter two: the return'
        mark('c2_gate')
        yield from use('AnchorActor', lambda: mode() in (3, 4), 'the gate, in the past', 1.4)
        yield from talk_through(60, True)
        if mode() == 0:
            yield from use('AnchorActor', lambda: mode() in (3, 4), 'the gate again', 0.8)
            yield from talk_through(60, True)
        if mode() != 4:
            yield from reach_and_pinch(lambda: button('QuestBtnWatch'), True, 1.0, 'open_watch')
        yield wait(1.8)
        mark('c2_watch')
        if mode() == 4 and bool(pawn.get_editor_property('QuestDialVisible')) and int(prop('SelectedEra')) != 0:
            yield from turn(False, 2.2)
        yield wait(0.8)
        era_then = int(prop('EraIndex'))
        mark('c2_confirm')
        yield from reach_and_pinch(lambda: button('QuestBtnOk'), True, 1.0, 'confirm_watch')
        drop_hand(True)
        eye = cam.get_world_location()
        yield from look(1.2, button('QuestBtnOk'), eye + level_ahead() * 600 + V(0, 0, 25))
        for _ in range(120):
            if int(prop('EraIndex')) != era_then:
                break
            yield wait(0.25)
        mark('c2_return_jump')
        for _ in range(80):
            if mode() != 7:
                break
            yield wait(0.25)
        mark('c2_returned')
        REPORT['chapter_two_return'] = {'era_before': era_then, 'era_after': int(prop('EraIndex')), 'returned': era_then == 1 and int(prop('EraIndex')) == 0}
        write()
        eye = cam.get_world_location()
        fwd, side = level_ahead(), cam.get_right_vector()
        yield from look(5.0, eye + fwd * 600 - side * 260 + V(0, 0, 30), eye + fwd * 600 + side * 260 + V(0, 0, 10))
        if mode() == 3:
            yield from talk_through(40, True)
        yield from put_away()

        S['step'] = 'chapter two: the changed record'
        mark('c2_memorial')
        yield from use('MemorialActor', lambda: mode() in (2, 3), 'the record in the present', 1.8)
        mark('c2_memorial_open')
        yield wait(6.0)
        if mode() == 2:
            yield from pinch_at(lambda: ahead(44, 4, -4), True, expect='close_document')
            yield wait(0.8)
        mark('c2_memorial_talk')
        yield from talk_through(60, True, 'c2_record_reply')
        yield from put_away()
        REPORT['chapter_two_record'] = {'consequence_observed': bool(prop('ConsequenceObserved')), 'storm_cover': int(prop('StormCover'))}
        write()

        S['step'] = 'chapter two: Mother at home'
        home = prop('MotherHomeDestinationActor')
        for _ in range(120):
            if not bool(prop('MotherMoving')) and (home is None or prop('MotherActor').get_distance_to(home) <= 90):
                break
            yield wait(0.25)
        mark('c2_mother_home')
        yield from use('MotherActor', lambda: mode() == 3, 'Mother, at home again', 1.6)
        yield wait(1.6)
        yield from talk_through(80, True, 'c2_final_reply')
        mark('c2_complete')
        REPORT['chapter_two_complete'] = {'chapter2_complete': bool(prop('Chapter2Complete')), 'era': int(prop('EraIndex')),
                                          'release_menu': bool(prop('ReleaseMenuActive')), 'title': str(prop('ReleaseMenuTitle'))}
        steps = REPORT['chapter_two']
        REPORT['chapter_two_summary'] = {'steps': len(steps), 'by_pinch': len([s for s in steps if s['by'] == 'pinch']),
                                         'by_fixture': [s['step'] for s in steps if s['by'] == 'fixture'],
                                         'not_registered': [s['step'] for s in steps if s['by'] == 'not registered'],
                                         'unexpected_actions': [a for a in REPORT['hand_actions'] if a.get('expected') and a.get('action') != a.get('expected')]}
        write()
        drop_hand(True)
        yield wait(6.0)
        mark('c2_end_screen')

    if TO_JUMP:
        # Timed run (13 November 2026): straight on to the gate and through it, as a first-time player would go, with no
        # demonstration beats. The player is placed in front of each object by the script (a person would teleport there:
        # that time is not in the figure); everything else is pinches at the director's reading pace.
        S['step'] = 'gate'
        mark('gate')
        gate_spots = [(0, -155), (160, 80), (190, 0), (160, -80), (0, -185), (0, 185)]

        def at_gate(done, label):
            actor = prop('AnchorActor')
            yield from gaze_select(actor, gate_spots)
            yield wait(0.7)
            yield from glide(0.7, lambda: rest(True), lambda: ahead(44, 4, -4), True)
            yield from pinch_at(lambda: ahead(44, 4, -4), True, expect='interact')
            yield wait(0.5)
            REPORT['gate'].append({'step': label, 'registered': bool(done()), 'mode': mode(), 'utc': time.time()})
            write()

        REPORT['gate'] = []
        yield from at_gate(lambda: bool(prop('AnchorActivated')), 'register the gate anchor')
        for _ in range(160):  # Mother walks to the gate before the departure exchange
            if not bool(prop('MotherMoving')):
                break
            yield wait(0.25)
        mark('mother_at_gate')
        if mode() == 0:
            yield from at_gate(lambda: mode() in (3, 4), 'the gate again, with Mother there')
        yield from talk_through(40)
        mark('departure_done')
        if mode() == 0:
            yield from at_gate(lambda: mode() == 4, 'the gate: the watch')
        if mode() != 4:
            yield from reach_and_pinch(lambda: button('QuestBtnWatch'), True, 1.0, 'open_watch')
        yield wait(1.6)
        mark('watch_at_gate')
        if mode() == 4 and bool(pawn.get_editor_property('QuestDialVisible')) and int(prop('SelectedEra')) != 1:
            yield from turn(True, 2.0)
        era_before = int(prop('EraIndex'))
        mark('confirm')
        yield from reach_and_pinch(lambda: button('QuestBtnOk'), True, 1.0, 'confirm_watch')
        drop_hand(True)
        if CH2:
            # The head comes up from the button to the gate while the fade runs, so the arrival is seen level.
            eye = cam.get_world_location()
            yield from look(1.2, button('QuestBtnOk'), eye + level_ahead() * 600 + V(0, 0, 25))
        for _ in range(120):
            if int(prop('EraIndex')) != era_before:
                break
            yield wait(0.25)
        mark('jump')
        for _ in range(80):
            if mode() != 7:
                break
            yield wait(0.25)
        mark('arrived')
        yield wait(4.0)
        marks = {m['name']: m['utc'] for m in REPORT['marks']}
        lines = [a for a in REPORT['hand_actions'] if a.get('action') == 'advance_dialogue']
        REPORT['to_jump'] = {
            'era_before': era_before, 'era_after': int(prop('EraIndex')), 'jumped': int(prop('EraIndex')) == 1 and era_before == 0,
            'seconds_new_game_to_jump': round(marks['jump'] - marks['title_pinch_new_game'], 1),
            'seconds_new_game_to_arrival': round(marks['arrived'] - marks['title_pinch_new_game'], 1),
            'seconds_first_exploration_to_jump': round(marks['jump'] - marks['coach'], 1),
            'hand_actions': len(REPORT['hand_actions']), 'dialogue_lines_advanced': len(lines),
            'unexpected_actions': [a for a in REPORT['hand_actions'] if a.get('expected') and a.get('action') != a.get('expected')],
            'pace': 'each dialogue line is held about 2.2 s before the pinch that advances it (about 3.2 s per line in all); the recollections are read through, not skipped',
            'not_included': 'moving between the objects (the script places the player; a person teleports), a person\'s reading speed and hesitation, the headset'}
        write()
        if CH2:
            yield from chapter_two()
        movement.set_movement_mode(unreal.MovementMode.MOVE_WALKING)
        mark('end')
        yield wait(1.0)
        S['step'] = 'complete'
        return

    S['step'] = 'watch'
    mark('watch_open')
    drop_hand(False)
    if bool(prop('WatchCalibrated')):
        yield from wrist_open()
    if mode() != 4:
        yield from reach_and_pinch(lambda: button('QuestBtnWatch'), True, 1.0, 'open_watch')
    yield wait(2.2)
    if mode() == 4 and bool(pawn.get_editor_property('QuestDialVisible')):
        if int(prop('SelectedEra')) == 1:
            mark('watch_dial_to_present')
            yield from turn(False, 1.4)
            yield wait(0.8)
        mark('watch_dial_to_past')
        yield from turn(True, 2.2)
        mark('watch_dial_done')
        yield wait(2.0)
        yield from pinch_at(lambda: ahead(40, -14, -10), False, expect='close_watch')
        drop_hand(False)
    elif mode() == 4:
        for name, expected in [('QuestBtnDown', 'dial_right'), ('QuestBtnDown', 'dial_right'), ('QuestBtnUp', 'dial_left')]:
            yield from reach_and_pinch(lambda n=name: button(n), True, 0.8, expected)
            yield wait(0.9)
        mark('watch_select_reach')
        yield from glide(0.9, lambda: rest(True), lambda: toward(button('QuestBtnOk')), True)
        yield wait(1.2)
        yield from glide(0.6, lambda: toward(button('QuestBtnOk')), lambda: rest(True), True)
        yield from pinch_at(lambda: ahead(40, -14, -10), False, expect='close_watch')
        drop_hand(False)
    yield wait(0.8)

    S['step'] = 'pause panel'
    mark('pause')
    yield from hold_left(1.3)
    drop_hand(False)
    yield wait(3.0)
    if mode() == 6:
        yield from reach_and_pinch(lambda: button('QuestChoice1'), True, 0.9, 'pause_row_1')
    yield wait(0.8)

    S['step'] = 'teleport'
    landings = [a for a in tagged('Quest.Teleport') if not bool(a.get_editor_property('hidden'))]
    pairs = [(a, b) for a in landings for b in landings if a != b and 150 < distance(a.get_actor_location(), b.get_actor_location()) < 480
             and abs(a.get_actor_location().z - b.get_actor_location().z) < 110]
    mark('teleport')
    for start, destination in pairs[:10]:
        pawn.set_actor_location(start.get_actor_location() + unreal.Vector(0, 0, 88), False, True)
        aim_camera_at(destination.get_actor_location() + unreal.Vector(0, 0, 60))
        yield wait(1.2)
        yield from glide(0.9, lambda: rest(True), lambda d=destination: toward(d.get_actor_location() + unreal.Vector(0, 0, 2)), True)
        yield wait(0.4)
        yield from pinch_at(lambda d=destination: toward(d.get_actor_location() + unreal.Vector(0, 0, 2)), True, expect='teleport')
        yield wait(1.4)
        if REPORT['hand_actions'][-1]['action'] == 'teleport':
            break
    movement.set_movement_mode(unreal.MovementMode.MOVE_WALKING)
    if unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3DemoOnly'):
        # Demo run (12 November 2026): the pinch-driven beats only, for reviewing the interface; no scenic part.
        mark('end')
        yield wait(1.0)
        S['step'] = 'complete'
        return

    # ---- Part 2: scenic moves in both eras ----
    yield from scenic_part()
    mark('end')
    yield wait(1.0)
    S['step'] = 'complete'


exec(compile('def finish(error=None):\n' + X_SUFFIX, str(X_PARENT_FILE), 'exec'), globals())
