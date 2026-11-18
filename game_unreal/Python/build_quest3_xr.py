"""Author the Quest 3 XR adapter of the Release copy as native Blueprint gameplay (2 November 2026).

Derived from build_quest_xr.py (Quest_20261025) and adapted to the release front end:
- BP_QuestCharacter: tracked head, controller rays, world panel, teleport landings, snap turn, room-scale,
  head occlusion (unchanged design), plus the release title / pause / settings / credits / end menus on the
  world panel driven by the thumbsticks, trigger / A and B, and the menu button opening the main menu.
- BP_OpeningActions: _Quest_* adapters and tag-gated wrappers on SetMode / MovementFrame / InputFrame /
  CameraFraming / OpenPause (desktop bodies preserved through the else pin); head recentering after the
  story's own checkpoint placements; the release LoadProgress / SaveProgress / EndSlice front-end hooks are
  re-authored without their XR exclusion so the headset player boots into the title menu, saves through the
  guard and reaches the end-of-demo screen. Interaction targeting keeps the manager's own gaze ray.
- BP_OpeningHUD: screen-space drawing is skipped for the XR player.
- BP_QuestGameMode: XR pawn, release HUD class.

Run only through verdant/run_unreal.ps1 (one native writer at a time) with -Quest3XRWrite. Backups of the
four assets go to validation/quest3/<stamp>/backup/; the report is game_unreal/quest3_xr_build_report.json.
Python is editor tooling only; nothing at runtime depends on it.
"""
from pathlib import Path
import datetime
import hashlib
import json
import math
import shutil
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
assert ROOT.parent.name == 'Release_20261026', 'Quest 3 XR writer runs only in the Release copy'
sys.path.insert(0, str(ROOT / 'Python'))
import opening_graph as og
import build_opening_actions as base
from build_opening_actions import Flow, MATH, SYS, GS, ACT, PC, CTL, CAM
import release_frontend_graph as rfg

CHAR_PATH = '/Game/Quest/XR/BP_QuestCharacter'
CHAR_CLASS = CHAR_PATH + '.BP_QuestCharacter_C'
GM_PATH = '/Game/Quest/XR/BP_QuestGameMode'
HUD_PATH = '/Game/Opening/Blueprints/BP_OpeningHUD'
MANAGER_PATH = base.PATH
MANAGER_CLASS = base.CLASS
SC = '/Script/Engine.SceneComponent.'
MC = '/Script/HeadMountedDisplay.MotionControllerComponent.'
HMD = '/Script/XRBase.HeadMountedDisplayFunctionLibrary.'
TEXT = '/Script/Engine.TextRenderComponent.'
STR = '/Script/Engine.KismetStringLibrary.'
MACRO = '/Engine/EditorBlueprintResources/StandardMacros.StandardMacros:ForEachLoop'
MARKER = 'Quest.XRWrapper.v1'
STAMP = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
MENU_HINT = '\nHands: point at Up / Down / Select / Back below and pinch.\nController: stick up / down, trigger or A confirms, B goes back.'
# Hands-first seated layer (6 November 2026, Meta VR Start competition brief). -Quest3XRCharacterOnly re-authors the
# pawn alone and leaves the manager, HUD and game mode bytes untouched.
CHARACTER_ONLY = unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3XRCharacterOnly')
PINCH_ON_CM = 2.5
PINCH_OFF_CM = 4.5
MENU_GESTURE_SECONDS = 1.0
SEATED_EYE_CM = 162.0
# Easier-controls pass (10 November 2026): onboarding, context hints, hover feedback, forgiving targets, debounce, gaze dwell.
DEBOUNCE_SECONDS = 0.35
DWELL_SECONDS = 1.5
GENERIC_DWELL_SECONDS = 3.0
HOVER_SCALE = 1.15
SNAP_RADIUS_CM = 5.0
AIM_LATCH_CM = 6.0
AUTO_GAZE_SECONDS = 15.0
# Demo-review fixes (12 November 2026).
WRAP_LINES = 18
PANEL_WRAP = 68          # characters per panel line at text size 5.5 (about 1.9 cm each on the 133 cm text width); the
                         # manager's own lines run to 67 characters, so they pass through unchanged
HUD_WRAP = 62            # characters per HUD status line at text size 3.0 (about 1 cm each on the 78 cm plate)
PANEL_PITCH_DOWN = -15.0
PANEL_PITCH_UP = 20.0
PANEL_BOTTOM_CM = 70.0   # the panel's lower edge stays within this height below the eye (clear of table tops)
PANEL_LOWER_EDGE_RATIO = 92.0 / 180.0  # lower edge (cluster bottom) below the panel root, per cm of panel distance
PANEL_MIN_CM = 90.0      # nearest the panel comes (it shrinks with distance, so its angular size stays the same)
PANEL_EDGE_DEGREES = 18.0
PROMPT_KEY_PREFIX_MAX = 7  # a desktop key prefix ("E", "F / E") ends in a double space within this many characters
# Hand names in player text are tokens (<Main>, <Off>, <mainl>, <offl>) resolved by set_text(..., hands=True) from the
# player's main hand, so a left-handed player is never told to pinch with the wrong hand.
PANEL_HELP = {1: '<Main> pinch or trigger: turn the photograph over.\n<Off> pinch or B: put it back.',
              2: 'Pinch or trigger to close.',
              3: 'Pinch or trigger to continue.',
              'intro': 'Pinch or trigger to continue.    Back, <Off> pinch or B: skip.',
              4: 'Up / Down: turn the dial.    Select: confirm.\n<Off> pinch or B: close.',
              'dial': 'Pinch the watch hand and turn it:\nleft is the past, right is the present.\nSelect: confirm.    <Off> pinch or B: close.',
              'test': '<Off> pinch or B: cancel the test.',
              5: 'Up / Down: turn the page.    <Off> pinch or B: close.'}
# New names are appended: the gaze-dwell ids are positions in this list.
UI_NAMES = ['QuestBtnUp', 'QuestBtnDown', 'QuestBtnOk', 'QuestBtnBack', 'QuestBtnTurnLeft', 'QuestBtnWatch', 'QuestBtnMenu',
            'QuestBtnJournal', 'QuestBtnTurnRight', 'QuestBtnCoachNext', 'QuestBtnCoachSkip',
            'QuestChoice1', 'QuestChoice2', 'QuestChoice3', 'QuestChoice4', 'QuestChoice5',
            'QuestChoice6', 'QuestChoice7', 'QuestDial', 'QuestWristTouch']
# Competition pass (12 November 2026, later): drawn hands, the watch hand turned by a pinch, main-hand choice, large text.
HAND_FINGERS = [('Index', 1.0), ('Middle', 1.0), ('Ring', .95), ('Little', .85)]
HAND_KEYPOINTS = (['Wrist', 'ThumbMetacarpal', 'ThumbProximal', 'ThumbDistal', 'ThumbTip'] +
                  [finger + part for finger, _ in HAND_FINGERS for part in ['Metacarpal', 'Proximal', 'Intermediate', 'Distal', 'Tip']])
# (segment name, joint A, joint B, thickness in cm): one stretched sphere per finger bone, overlapping at the joints.
HAND_SEGMENTS = ([('Thumb1', 'ThumbMetacarpal', 'ThumbProximal', 2.3), ('Thumb2', 'ThumbProximal', 'ThumbDistal', 2.0), ('Thumb3', 'ThumbDistal', 'ThumbTip', 1.7)] +
                 [(finger + str(i + 1), finger + a, finger + b, round(t * k, 2)) for finger, k in HAND_FINGERS
                  for i, (a, b, t) in enumerate([('Proximal', 'Intermediate', 1.9), ('Intermediate', 'Distal', 1.7), ('Distal', 'Tip', 1.5)])])
HAND_PARTS = [s[0] for s in HAND_SEGMENTS] + ['Palm']
DIAL_Y = -42.0            # dial centre on the panel (panel units: +Y is the viewer's left, +Z up)
DIAL_Z = 0.0
DIAL_RADIUS = 22.0
DIAL_MARK_DEG = 50.0      # the two era marks: +50 (viewer's left) the past, -50 the present
DIAL_MAX_DEG = 80.0
DIAL_SWITCH_DEG = 8.0     # the hand must pass this far beyond the top before the era changes (no flicker at the middle)
DIAL_WRAP = 44            # characters per line of the watch text while the dial takes the right of the panel
# True watch readout (16 November 2026): what the panel draws in place of the manager's watch tail and CONFIRM line.
WATCH_TAIL = '\n\nISLANDS'                 # the manager's watch text from here on is dropped by the headset panel
WATCH_CONFIRM = 'CONFIRM TRANSITION'       # the manager's line, replaced by what Select will really do:
WATCH_HERE = 'YOU ARE HERE'                # the dial points at the era the player is in
WATCH_READY = 'READY — PINCH SELECT TO TRAVEL'
WATCH_FAR = 'GO TO THE GATE TO TRAVEL'     # the gate anchor is not registered or is further than WATCH_GATE_CM
WATCH_GATE_CM = 260.0                      # the manager's own ConfirmWatch distance
WATCH_AWAY = '\nTIME AWAY FROM HOME — '
WATCH_WAS_AWAY = '\nTIME SPENT IN THE PAST — '
DIAL_SUBDIAL = 0.47       # the seconds subdial sits this fraction of the radius below the dial centre (watch_face_material)
# Parts added for the better-looking watch: shown and hidden with the dial; the two lamps show the selected era.
DIAL_DECOR = ['QuestDialBezel', 'QuestDialCrown', 'QuestDialHandTail', 'QuestDialKnobCore', 'QuestDialHubCap',
              'QuestDialSecondsHand', 'QuestDialSecondsHub']
DIAL_LAMPS = [('QuestDialGlowPast', 1), ('QuestDialGlowNow', 0)]
# Watch on the wrist (16 November 2026, night; the entrant asked for it and for the build with the best chance against
# past winners, whose hand interactions are things worn and handled, not buttons): once the watch is calibrated a small
# copy of it is drawn on the wrist of the off hand, from that hand's keypoints. It shows the era the player is in and a
# running seconds hand, follows the big watch hand while the panel is open, and a main-hand pinch on it (or a look, with
# gaze select) opens the watch. The Watch button stays. Root axes: +X is twelve o'clock (the little-finger side), -Z points
# out of the back of the wrist, so the face is seen exactly as the panel's face is (watch_face_material).
WRIST_PARTS = ['QuestWristCuff', 'QuestWristStrap', 'QuestWristCase', 'QuestWristDial', 'QuestWristHand', 'QuestWristHub',
               'QuestWristSecondsHand']
WRIST_FACE_CM = 4.4       # diameter of the face
WRIST_TOUCH_CM = 6.0      # diameter of the hidden disc a pinch has to hit (QuestWristTouch)
WRIST_BACK_CM = 4.0       # the watch sits this far behind the wrist keypoint, toward the elbow
WRIST_RISE_CM = 1.7       # and this far out of the back of the wrist (half the thickness of the drawn cuff)
DIAL_TICK_DEG = 10.0      # a tick is heard each time the held watch hand passes this many degrees
DIAL_PARTS = ['QuestDial', 'QuestDialRim', 'QuestDialHand', 'QuestDialKnob', 'QuestDialHub', 'QuestDialMarkPast', 'QuestDialMarkNow',
              'QuestDialPastText', 'QuestDialNowText']
LARGE_TEXT_ZOOM = 1.3
# Tutorial lines (13 November 2026): each is shown on the HUD plate until the player has done it once.
IDLE_HINT = 'Look at an object, then pinch.'
TUTORIAL_USE = 'Tutorial: look at something and pinch to use it.'
TUTORIAL_MOVE = 'Tutorial: to move, pinch a floor disc or a Turn button.'
TEXT_PLAIN =[('—', '-'), ('–', '-'), ('’', "'"), ('‘', "'"), ('“', '"'), ('”', '"'), ('…', '...')]
COMPETITION_PASS = {
    'date': '2026-11-12',
    'hands': 'each tracked hand is drawn from the 25 OpenXR hand-tracking keypoints (wrist, 4 thumb and 5 joints per finger; MotionControllerComponents named Left/Right + keypoint): 15 stretched spheres for the finger bones and one for the palm, unlit, no collision, no shadow',
    'dial': 'calibrated watch panel shows a watch face; a main-hand pinch on it takes hold of the watch hand, which follows the eye-to-pinch ray around the centre; past the top by %.0f degrees the era changes (left the past, right the present) through the manager RotateDial; Up / Down / Select / Back stay' % DIAL_SWITCH_DEG,
    'main_hand': 'the first pinch of a session aimed at a button with the other hand makes that hand the main hand; pause row "Main hand" switches it; every hand name in player text follows it',
    'large_text': 'pause row "Large text" enlarges the panel and the HUD row %.0f percent in angular size' % (LARGE_TEXT_ZOOM * 100 - 100),
    'simulation': 'QuestSimJoints with the joint MotionControllerComponents placed by the PIE harness (quest3_sim_hand.py) draws the same hands without hardware'}
HANDS_COMFORT = {
    'date': '2026-11-10',
    'onboarding': 'since 13 November: two tutorial lines on the HUD plate at the first exploration of each session (use a gazed object; move or turn), each gone once the player has done it, in either order, nothing blocked; Skip tutorial always available. Before: a 4-step coach (pinch Next, off-hand pinch, off-hand hold, move), each step performed in order',
    'hints': 'HUD hint line says what a pinch will do now ("Pinch: <prompt>", "Pinch: move here", button names); modal panels keep their own hint text',
    'hover': 'a pointed UI button or row grows 15 percent while targeted; the pointer dot grows with distance so it stays visible',
    'forgiveness': 'component pick falls back to the nearest UI component whose collision lies within %.0f cm of the pinch ray; %.2f s debounce per hand' % (SNAP_RADIUS_CM, DEBOUNCE_SECONDS),
    'gaze_dwell': 'optional: pause row "Gaze select" arms a %.1f s look-to-select (%.1f s for plain advance); also arms by itself after %.0f s with no tracked hand or controller' % (DWELL_SECONDS, GENERIC_DWELL_SECONDS, AUTO_GAZE_SECONDS)}
HANDS_LAYER = {
    'date': '2026-11-06',
    'joints': 'MotionControllerComponents LeftIndexTip / LeftThumbTip / RightIndexTip / RightThumbTip (OpenXR hand-tracking keypoint motion sources)',
    'pinch': 'thumb tip to index tip distance below %.1f cm, released above %.1f cm (hysteresis)' % (PINCH_ON_CM, PINCH_OFF_CM),
    'ray': 'eye-to-pinch-point ray from the HMD camera, 650 cm, Visibility channel; the pointer, UI picking and teleport use it ahead of the controller aim',
    'grammar': {
        'release menus': 'Up / Down / Select / Back buttons under the panel; left pinch anywhere = Back',
        'exploration': 'right pinch = interact with the gazed object; pinch on a landing disc = teleport; HUD row: Turn left / Watch / Menu / Journal / Turn right',
        'dialogue': 'right pinch = continue; pinch a choice row = choose; left pinch during the recollections = skip',
        'photograph': 'right pinch = turn over; left pinch or Back = close; the held photo follows the left hand',
        'letter': 'any pinch = close',
        'watch': 'Up / Down = dial; Select = confirm; left pinch or Back = close',
        'journal': 'Up / Down = pages; left pinch or Back = close',
        'pause': 'pinch a row (Resume / Save / Load / Recenter the seated view); Up / Down cycle; Select confirms; left pinch or Back = resume'},
    'menu_gesture': 'left pinch held %.1f s opens the pause panel in exploration and resumes from it' % MENU_GESTURE_SECONDS,
    'seated': 'Local (eye-level) tracking origin, eye at %.0f cm above the floor, recentre at BeginPlay and from the fourth pause row' % SEATED_EYE_CM,
    'comfort': 'camera blink (0.25 s from black) after every teleport and snap turn; no joystick locomotion',
    'simulation': 'QuestSimHands with QuestSimLeft/Right Valid, Thumb and Index members drive the same pinch and ray code in PIE',
    'controllers': 'optional: the thumbstick, trigger / A / B / X / Y and menu-button paths are unchanged'}


class QFlow(Flow):
    def var(self, name, owner=None, cls=''):
        # APawn already has a Controller-typed property. Keep a distinct typed
        # PlayerController reference for polling rather than shadowing it.
        if name == 'Controller' and owner is None and not cls:
            name = 'QuestController'
        return super().var(name, owner, cls)

    def own(self, name, **params):
        return self.call(CHAR_CLASS + ':' + name, **params)

    def branch(self, condition):
        n = self.g.branch(condition)
        og.link(self.cur, og.pin_in(n))
        return QFlow(self.g, og.pin_out(n, 'then')), QFlow(self.g, og.pin_out(n, 'else'))

    def manager(self, name, **params):
        return self.call(MANAGER_CLASS + ':' + name, **{'self': self.var('QuestManager'), **params})

    def mv(self, name):
        return self.var(name, self.var('QuestManager'), MANAGER_CLASS)


def reset_function(bp, name, inputs=None):
    old = og.L.find_graph(bp, name)
    if old:
        ed = og.E.get_graph_editor(old)
        ed.remove_nodes([n for n in ed.list_all_nodes()
                         if n.get_class().get_name() not in ['K2Node_FunctionEntry', 'K2Node_FunctionResult']])
    return og.function(bp, name, inputs=inputs, reset=False)


def merge(*flows):
    n = flows[0].g.set('QuestFlowMarker', 0)
    for f in flows:
        og.link(f.cur, og.pin_in(n))
    return type(flows[0])(flows[0].g, og.pin_out(n))


def vec(f, x=0, y=0, z=0):
    return f.data(MATH + 'MakeVector', X=x, Y=y, Z=z)


def split_vec(f, v):
    n = f.call(MATH + 'BreakVector', InVec=v)
    return [og.value_pin(n, p) for p in ['X', 'Y', 'Z']]


def add(f, a, b):
    return f.data(MATH + 'Add_VectorVector', A=a, B=b)


def sub(f, a, b):
    return f.data(MATH + 'Subtract_VectorVector', A=a, B=b)


def scale(f, v, s):
    return f.data(MATH + 'Multiply_VectorFloat', A=v, B=s)


def location(f, name):
    return f.data(SC + 'K2_GetComponentLocation', **{'self': f.var(name)})


def rotation(f, name):
    return f.data(SC + 'K2_GetComponentRotation', **{'self': f.var(name)})


def join_text(f, a, b):
    return f.data(STR + 'Concat_StrStr', A=a, B=b)


def set_text(f, component, value, hands=False):
    # UE5.8 K2_SetText unconditionally dirties render state. Compare strings
    # first so stationary text does not rebuild its meshes every frame.
    # hands=True (every call for that component must pass it): the hand-name tokens are resolved from the main hand; the
    # unresolved value is compared in QuestRaw<component> and the resolved text is what QuestCached<component> holds.
    cache = 'QuestCached' + component
    source = ('QuestRaw' + component) if hands else cache
    changed, unchanged = f.branch(f.data(STR + 'NotEqual_StrStr', A=value, B=f.var(source)))
    rendered = value
    if hands:
        for token, left_handed, right_handed in [('<Main>', 'Left', 'Right'), ('<Off>', 'Right', 'Left'),
                                                 ('<mainl>', 'left', 'right'), ('<offl>', 'right', 'left')]:
            rendered = changed.data(STR + 'Replace', SourceString=rendered, From=token,
                                    To=changed.data(MATH + 'SelectString', A=left_handed, B=right_handed, bPickA=changed.var('QuestLeftHanded')))
        resolved = rendered
    for _ in range(3):
        rendered = changed.data(STR + 'Replace', SourceString=rendered, From='\n\n', To='\n')
    # The text-render font has no long dashes or curly quotes: the story's "RETURN SIGNAL — STABLE" was drawn with an
    # empty box (seen in the 12 November demo frames). They are drawn as their plain forms; the cached text is unchanged.
    for fancy, plain in TEXT_PLAIN:
        rendered = changed.data(STR + 'Replace', SourceString=rendered, From=fancy, To=plain)
    text = changed.data('/Script/Engine.KismetTextLibrary.Conv_StringToText', InString=rendered)
    changed.call(TEXT + 'K2_SetText', **{'self': changed.var(component), 'Value': text})
    if hands:
        changed.set(cache, resolved)
        changed.set(source, value)
    else:
        changed.set(cache, value)
    f.cur = merge(changed, unchanged).cur


def _subobjects(bp):
    sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    result = []
    for handle in sub.k2_gather_subobject_data_for_blueprint(bp):
        data = lib.get_data(handle)
        obj = lib.get_object_for_blueprint(data, bp)
        result.append((str(lib.get_variable_name(data)), handle, obj, data))
    return sub, lib, result


def component(bp, name, cls, parent_name=None):
    sub, lib, entries = _subobjects(bp)
    found = next((e for e in entries if e[0] == name), None)
    if found:
        return found[2]
    parent = next((e for e in entries if e[0] == parent_name), None) if parent_name else entries[0]
    if parent is None:
        raise RuntimeError('Missing component parent: ' + str(parent_name))
    params = unreal.AddNewSubobjectParams(parent_handle=parent[1], new_class=cls,
                                        blueprint_context=bp, conform_transform_to_parent=False)
    handle, reason = sub.add_new_subobject(params)
    if not lib.is_handle_valid(handle):
        raise RuntimeError('Cannot add ' + name + ': ' + str(reason))
    if not sub.rename_subobject(handle, unreal.Text(name)):
        raise RuntimeError('Cannot name component ' + name)
    obj = lib.get_object_for_blueprint(lib.get_data(handle), bp)
    if obj is None:
        raise RuntimeError('No component template for ' + name)
    return obj


def transform(c, at=(0, 0, 0), rot=(0, 0, 0), size=(1, 1, 1)):
    c.set_editor_property('relative_location', unreal.Vector(*at))
    c.set_editor_property('relative_rotation', unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]))
    c.set_editor_property('relative_scale3d', unreal.Vector(*size))


def text_component(bp, name, parent, at, size):
    c = component(bp, name, unreal.TextRenderComponent, parent)
    transform(c, at)
    c.set_world_size(size)
    c.set_editor_property('x_scale', .85)
    c.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_LEFT)
    c.set_vertical_alignment(unreal.VerticalTextAligment.EVRTA_TEXT_TOP)
    c.set_editor_property('text_render_color', unreal.Color(244, 237, 218, 255))
    c.set_text_material(readable_text_material())
    c.set_editor_property('cast_shadow', False)
    c.set_editor_property('text', unreal.Text(''))
    return c


def readable_text_material():
    path = '/Game/Quest/XR/Materials/M_QuestReadableText'
    asset = unreal.load_asset(path)
    if asset:
        return asset
    asset = unreal.EditorAssetLibrary.duplicate_asset('/Engine/EngineMaterials/DefaultTextMaterialOpaque', path)
    if not asset:
        raise RuntimeError('Cannot create owned readable font material')
    node = unreal.MaterialEditingLibrary.get_material_property_input_node(asset, unreal.MaterialProperty.MP_BASE_COLOR)
    output = unreal.MaterialEditingLibrary.get_material_property_input_node_output_name(asset, unreal.MaterialProperty.MP_BASE_COLOR)
    if node is None or not unreal.MaterialEditingLibrary.connect_material_property(node, output, unreal.MaterialProperty.MP_EMISSIVE_COLOR):
        raise RuntimeError('Default font color graph could not be preserved as emissive')
    asset.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    asset.set_editor_property('two_sided', True)
    unreal.MaterialEditingLibrary.recompile_material(asset)
    unreal.EditorAssetLibrary.save_loaded_asset(asset)
    return asset


def panel_material(name, rgb, two_sided=False):
    path = '/Game/Quest/XR/Materials/' + name
    asset = unreal.load_asset(path)
    if asset:
        return asset
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, '/Game/Quest/XR/Materials', unreal.Material, unreal.MaterialFactoryNew())
    asset.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    asset.set_editor_property('two_sided', two_sided)
    node = unreal.MaterialEditingLibrary.create_material_expression(asset, unreal.MaterialExpressionConstant3Vector, -250, 0)
    node.set_editor_property('constant', unreal.LinearColor(*rgb, 1))
    unreal.MaterialEditingLibrary.connect_material_property(node, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    unreal.MaterialEditingLibrary.recompile_material(asset)
    unreal.EditorAssetLibrary.save_loaded_asset(asset)
    return asset


def hand_material():
    """Unlit, see-through hand material: a faint warm core that brightens and becomes solid toward the silhouette (Fresnel),
    so the stretched spheres read as rounded fingers and the panel text behind a raised hand stays readable. No lighting cost.
    The look carries a version tag; an older look is rebuilt in place."""
    path = '/Game/Quest/XR/Materials/M_QuestHand'
    look = 'ghost-2'
    mel = unreal.MaterialEditingLibrary
    asset = unreal.load_asset(path)
    if asset and unreal.EditorAssetLibrary.get_metadata_tag(asset, 'Quest.HandLook') == look:
        return asset
    if asset:
        mel.delete_all_material_expressions(asset)
    else:
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            'M_QuestHand', '/Game/Quest/XR/Materials', unreal.Material, unreal.MaterialFactoryNew())
    asset.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    asset.set_editor_property('blend_mode', unreal.BlendMode.BLEND_TRANSLUCENT)
    core = mel.create_material_expression(asset, unreal.MaterialExpressionConstant3Vector, -700, -120)
    core.set_editor_property('constant', unreal.LinearColor(.50, .37, .25, 1))
    rim = mel.create_material_expression(asset, unreal.MaterialExpressionConstant3Vector, -700, 60)
    rim.set_editor_property('constant', unreal.LinearColor(1.0, .86, .64, 1))
    fresnel = mel.create_material_expression(asset, unreal.MaterialExpressionFresnel, -700, 240)
    fresnel.set_editor_property('exponent', 1.6)
    fresnel.set_editor_property('base_reflect_fraction', 0.0)
    blend = mel.create_material_expression(asset, unreal.MaterialExpressionLinearInterpolate, -400, 0)
    thin = mel.create_material_expression(asset, unreal.MaterialExpressionConstant, -700, 420)
    thin.set_editor_property('r', 0.30)
    solid = mel.create_material_expression(asset, unreal.MaterialExpressionConstant, -700, 500)
    solid.set_editor_property('r', 0.92)
    opacity = mel.create_material_expression(asset, unreal.MaterialExpressionLinearInterpolate, -400, 420)
    if not (mel.connect_material_expressions(core, '', blend, 'A') and mel.connect_material_expressions(rim, '', blend, 'B')
            and mel.connect_material_expressions(fresnel, '', blend, 'Alpha')
            and mel.connect_material_property(blend, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
            and mel.connect_material_expressions(thin, '', opacity, 'A') and mel.connect_material_expressions(solid, '', opacity, 'B')
            and mel.connect_material_expressions(fresnel, '', opacity, 'Alpha')
            and mel.connect_material_property(opacity, '', unreal.MaterialProperty.MP_OPACITY)):
        raise RuntimeError('Cannot wire the hand material')
    mel.recompile_material(asset)
    unreal.EditorAssetLibrary.set_metadata_tag(asset, 'Quest.HandLook', look)
    unreal.EditorAssetLibrary.save_loaded_asset(asset)
    return asset


WATCH_FACE_CODE = '''
float2 p = P.xy / 50.0;   // the cylinder cap in units of its radius: x is up on the panel, y the viewer's left
float r = length(p);
float px = max(abs(ddx(p.x)) + abs(ddy(p.x)), abs(ddx(p.y)) + abs(ddy(p.y))) + 0.00001;
float ang = degrees(atan2(p.y, p.x));
float3 ivory = float3(0.88, 0.80, 0.60);
float3 brass = float3(0.75, 0.43, 0.12);
float3 c = lerp(float3(0.030, 0.058, 0.105), float3(0.008, 0.017, 0.038), saturate(r * r));
float ray = 0.5 + 0.5 * cos(radians(ang) * 72.0);
c *= 1.0 + 0.12 * ray * smoothstep(0.12, 0.5, r) * (1.0 - smoothstep(0.70, 0.76, r));
float am = abs(frac(ang / 6.0 + 0.5) - 0.5) * 6.0;
float ah = abs(frac(ang / 30.0 + 0.5) - 0.5) * 30.0;
float band = 1.0 - smoothstep(0.94 - px, 0.94 + px, r);
float tm = (1.0 - smoothstep(0.006 - px, 0.006 + px, sin(radians(am)) * r)) * smoothstep(0.885 - px, 0.885 + px, r) * band;
float th = (1.0 - smoothstep(0.013 - px, 0.013 + px, sin(radians(ah)) * r)) * smoothstep(0.83 - px, 0.83 + px, r) * band;
c = lerp(c, ivory * 0.7, tm);
c = lerp(c, ivory, th);
c = lerp(c, brass, 1.0 - smoothstep(0.005, 0.005 + px * 1.5, abs(r - 0.965)));
c = lerp(c, brass * 0.6, 1.0 - smoothstep(0.004, 0.004 + px * 1.5, abs(r - 0.775)));
float arc = (1.0 - smoothstep(0.014, 0.014 + px * 1.5, abs(r - 0.775))) * (1.0 - smoothstep(MarkDeg, MarkDeg + 1.0, abs(ang)));
c = lerp(c, brass * 1.15, arc);
float2 q = p - float2(-0.47, 0.0);
float rs = length(q);
float inside = 1.0 - smoothstep(0.25 - px, 0.25 + px, rs);
c = lerp(c, float3(0.006, 0.012, 0.028), inside);
float a5 = abs(frac(degrees(atan2(q.y, q.x)) / 30.0 + 0.5) - 0.5) * 30.0;
float ts = (1.0 - smoothstep(0.006 - px, 0.006 + px, sin(radians(a5)) * rs)) * smoothstep(0.19 - px, 0.19 + px, rs) * inside;
c = lerp(c, ivory * 0.8, ts);
c = lerp(c, brass, 1.0 - smoothstep(0.005, 0.005 + px * 1.5, abs(rs - 0.25)));
return c;
'''


def watch_face_material():
    """The watch face drawn by one unlit material (16 November 2026, the entrant asked for a better-looking watch): a navy
    dial with a faint sunray, sixty minute ticks with twelve longer ones, two brass rings, a brighter arc over the hand's
    travel between the two era marks, and a seconds subdial at the bottom. It is drawn from the mesh-local position, so it
    needs no texture and no UVs and stays sharp at any distance. The look carries a version tag; an older look is rebuilt."""
    path = '/Game/Quest/XR/Materials/M_QuestWatchFace'
    look = 'dial-1'
    mel = unreal.MaterialEditingLibrary
    asset = unreal.load_asset(path)
    if asset and unreal.EditorAssetLibrary.get_metadata_tag(asset, 'Quest.WatchLook') == look:
        return asset
    if asset:
        mel.delete_all_material_expressions(asset)
    else:
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            'M_QuestWatchFace', '/Game/Quest/XR/Materials', unreal.Material, unreal.MaterialFactoryNew())
    asset.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    world = mel.create_material_expression(asset, unreal.MaterialExpressionWorldPosition, -900, 0)
    local = mel.create_material_expression(asset, unreal.MaterialExpressionTransformPosition, -650, 0)
    local.set_editor_property('transform_source_type', unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD)
    local.set_editor_property('transform_type', unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL)
    mark = mel.create_material_expression(asset, unreal.MaterialExpressionConstant, -650, 200)
    mark.set_editor_property('r', DIAL_MARK_DEG)
    custom = mel.create_material_expression(asset, unreal.MaterialExpressionCustom, -350, 0)
    custom.set_editor_property('code', WATCH_FACE_CODE)
    custom.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    rows = []
    for key in ['P', 'MarkDeg']:
        row = unreal.CustomInput()
        row.set_editor_property('input_name', key)
        rows.append(row)
    custom.set_editor_property('inputs', rows)
    if not (mel.connect_material_expressions(world, '', local, '') and mel.connect_material_expressions(local, '', custom, 'P')
            and mel.connect_material_expressions(mark, '', custom, 'MarkDeg')
            and mel.connect_material_property(custom, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)):
        raise RuntimeError('Cannot wire the watch face material')
    mel.recompile_material(asset)
    unreal.EditorAssetLibrary.set_metadata_tag(asset, 'Quest.WatchLook', look)
    unreal.EditorAssetLibrary.save_loaded_asset(asset)
    return asset


def setup_components(bp):
    cdo = unreal.get_default_object(og.L.generated_class(bp))
    cdo.set_editor_property('use_controller_rotation_yaw', False)
    cdo.set_editor_property('use_controller_rotation_pitch', False)
    cdo.set_editor_property('use_controller_rotation_roll', False)
    capsule = cdo.get_editor_property('capsule_component')
    capsule.set_editor_property('capsule_half_height', 88.0)
    capsule.set_editor_property('capsule_radius', 30.0)
    movement = cdo.get_editor_property('character_movement')
    movement.set_editor_property('max_walk_speed', 0.0)
    movement.set_editor_property('orient_rotation_to_movement', False)
    sub, lib, entries = _subobjects(bp)
    capsule_name = next(e[0] for e in entries if isinstance(e[2], unreal.CapsuleComponent))
    origin = component(bp, 'VROrigin', unreal.SceneComponent, capsule_name)
    transform(origin, (0, 0, -88))
    camera = component(bp, 'QuestCamera', unreal.CameraComponent, 'VROrigin')
    transform(camera, (0, 0, 160))  # desktop fallback; HMD path uses floor pose at runtime
    camera.set_editor_property('lock_to_hmd', True)
    camera.set_editor_property('use_pawn_control_rotation', False)
    occluder = component(bp, 'QuestHeadOccluder', unreal.StaticMeshComponent, 'QuestCamera')
    occluder.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Sphere'))
    transform(occluder, size=(.35, .35, .35))
    occluder.set_material(0, panel_material('M_QuestHeadOcclusion', (0, 0, 0), two_sided=True))
    occluder.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    occluder.set_editor_property('cast_shadow', False)
    occluder.set_editor_property('only_owner_see', True)
    occluder.set_editor_property('receives_decals', False)
    occluder.set_editor_property('visible_in_reflection_captures', False)
    occluder.set_editor_property('visible', False)
    for name, source in [('LeftGrip', 'LeftGrip'), ('RightGrip', 'RightGrip'),
                         ('LeftAim', 'LeftAim'), ('RightAim', 'RightAim')]:
        c = component(bp, name, unreal.MotionControllerComponent, 'VROrigin')
        c.set_editor_property('motion_source', unreal.Name(source))
        c.set_editor_property('player_index', 0)
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    sphere = unreal.load_asset('/Engine/BasicShapes/Sphere')
    for hand in ['LeftGrip', 'RightGrip']:
        c = component(bp, hand + 'Proxy', unreal.StaticMeshComponent, hand)
        c.set_static_mesh(sphere)
        transform(c, size=(.06, .035, .09))
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        c.set_editor_property('cast_shadow', False)
    panel = component(bp, 'QuestPanelRoot', unreal.SceneComponent, capsule_name)
    panel.set_editor_property('absolute_location', True)
    panel.set_editor_property('absolute_rotation', True)
    cube = unreal.load_asset('/Engine/BasicShapes/Cube')
    back = component(bp, 'QuestPanelBack', unreal.StaticMeshComponent, 'QuestPanelRoot')
    back.set_static_mesh(cube)
    back.set_material(0, panel_material('M_QuestPanel', (.012, .022, .028)))
    transform(back, (-1, 0, -14), size=(.012, 1.42, 1.40))
    back.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    back.set_editor_property('cast_shadow', False)
    # Visual polish (11 November 2026): a warm accent line under the title and a thin frame around the panel back. Unlit,
    # no collision, shown and hidden with the panel.
    for name, at, size in [('QuestPanelAccent', (0.6, 0, 37), (.012, 1.30, .006)), ('QuestPanelFrameTop', (0.2, 0, 57), (.014, 1.45, .012)),
                           ('QuestPanelFrameBottom', (0.2, 0, -85), (.014, 1.45, .012)), ('QuestPanelFrameLeft', (0.2, 72, -14), (.014, .012, 1.43)),
                           ('QuestPanelFrameRight', (0.2, -72, -14), (.014, .012, 1.43))]:
        bar = component(bp, name, unreal.StaticMeshComponent, 'QuestPanelRoot')
        bar.set_static_mesh(cube)
        bar.set_material(0, panel_material('M_QuestPointer', (.75, .43, .12)))
        transform(bar, at, size=size)
        bar.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        bar.set_editor_property('cast_shadow', False)
    text_component(bp, 'QuestPanelTitle', 'QuestPanelRoot', (1, 65, 46), 7.0)
    text_component(bp, 'QuestPanelText', 'QuestPanelRoot', (1, 65, 32), 5.5)
    for i in range(1, 4):
        z = 28 - i * 20
        button = component(bp, 'QuestChoice' + str(i), unreal.StaticMeshComponent, 'QuestPanelRoot')
        button.set_static_mesh(cube)
        button.set_material(0, panel_material('M_QuestChoice', (.035, .07, .075)))
        transform(button, (0, 0, z), size=(.012, 1.3, .16))
        button.set_collision_profile_name('UI')
        button.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
        button.set_editor_property('cast_shadow', False)
        text_component(bp, 'QuestChoiceText' + str(i), 'QuestPanelRoot', (1, 62, z + 5), 6.0)
    text_component(bp, 'QuestStatusText', 'LeftGrip', (14, 13, 8), 1.2)
    marker = component(bp, 'QuestPointer', unreal.StaticMeshComponent, capsule_name)
    marker.set_static_mesh(sphere)
    marker.set_material(0, panel_material('M_QuestPointer', (.75, .43, .12)))
    transform(marker, size=(.016, .016, .016))
    marker.set_editor_property('absolute_location', True)
    marker.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    marker.set_editor_property('cast_shadow', False)
    # Hands-first layer: fingertip motion sources from the OpenXR hand-tracking plugin, pinch markers, the
    # Up / Down / Select / Back cluster under the panel, the lazy-follow HUD row and a fourth pause row.
    for name in ['LeftIndexTip', 'LeftThumbTip', 'RightIndexTip', 'RightThumbTip']:
        c = component(bp, name, unreal.MotionControllerComponent, 'VROrigin')
        c.set_editor_property('motion_source', unreal.Name(name))
        c.set_editor_property('player_index', 0)
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    for name in ['QuestLeftTipMarker', 'QuestRightTipMarker']:
        c = component(bp, name, unreal.StaticMeshComponent, capsule_name)
        c.set_static_mesh(sphere)
        c.set_material(0, panel_material('M_QuestPointer', (.75, .43, .12)))
        transform(c, size=(.014, .014, .014))
        c.set_editor_property('absolute_location', True)
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        c.set_editor_property('cast_shadow', False)
        c.set_editor_property('visible', False)

    def button(name, parent, at, width, height, label, label_size):
        b = component(bp, name, unreal.StaticMeshComponent, parent)
        b.set_static_mesh(cube)
        b.set_material(0, panel_material('M_QuestChoice', (.035, .07, .075)))
        transform(b, at, size=(.012, width, height))
        b.set_collision_profile_name('UI')
        b.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
        b.set_editor_property('cast_shadow', False)
        t = text_component(bp, name + 'Text', parent, (1, at[1], at[2] + 3), label_size)
        t.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
        t.set_editor_property('text', unreal.Text(label))
        return b
    for name, y, label in [('QuestBtnUp', 54, 'Up'), ('QuestBtnDown', 18, 'Down'), ('QuestBtnOk', -18, 'Select'), ('QuestBtnBack', -54, 'Back')]:
        button(name, 'QuestPanelRoot', (0, y, -82), .32, .12, label, 4.0)
    hud = component(bp, 'QuestHudRoot', unreal.SceneComponent, capsule_name)
    hud.set_editor_property('absolute_location', True)
    hud.set_editor_property('absolute_rotation', True)
    # Row narrowed to +/- 44 cm so the five buttons stay inside about 20 degrees either side of the view centre at 150 cm.
    for name, y, label in [('QuestBtnTurnLeft', 44, 'Turn left'), ('QuestBtnWatch', 22, 'Watch'), ('QuestBtnMenu', 0, 'Menu'),
                           ('QuestBtnJournal', -22, 'Journal'), ('QuestBtnTurnRight', -44, 'Turn right')]:
        button(name, 'QuestHudRoot', (0, y, 0), .21, .10, label, 3.0)
    # Onboarding coach buttons under the row (shown only while the coach is on).
    button('QuestBtnCoachNext', 'QuestHudRoot', (0, 24, -16), .34, .10, 'Next', 3.0)
    # Under the right end of the row: in the middle it sat on whatever the player looked down at (seen in the 13 November frames).
    button('QuestBtnCoachSkip', 'QuestHudRoot', (0, -39, -16), .30, .10, 'Skip tutorial', 2.6)
    # The hint and coach lines sit centred over the row on a dark plate (12 November 2026): as pale text straight on the
    # warm plaster of the visual pass they could not be read.
    status = text_component(bp, 'QuestHudStatusText', 'QuestHudRoot', (1, 0, 24), 3.0)
    status.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
    plate = component(bp, 'QuestHudStatusBack', unreal.StaticMeshComponent, 'QuestHudRoot')
    plate.set_static_mesh(cube)
    plate.set_material(0, panel_material('M_QuestPanel', (.012, .022, .028)))
    transform(plate, (-0.6, 0, 17.5), size=(.012, .78, .15))
    plate.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    plate.set_editor_property('cast_shadow', False)
    # Pause rows 4 to 7 are shorter (12 cm) and half width, two by two, so seven rows fit above the cluster: Recenter and
    # Gaze select on the left, Main hand and Large text on the right (12 November 2026, later).
    for index, y, z in [(4, 33.5, -50), (5, 33.5, -64), (6, -33.5, -50), (7, -33.5, -64)]:
        row = component(bp, 'QuestChoice' + str(index), unreal.StaticMeshComponent, 'QuestPanelRoot')
        row.set_static_mesh(cube)
        row.set_material(0, panel_material('M_QuestChoice', (.035, .07, .075)))
        transform(row, (0, y, z), size=(.012, .63, .12))
        row.set_collision_profile_name('UI')
        row.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
        row.set_editor_property('cast_shadow', False)
        text_component(bp, 'QuestChoiceText' + str(index), 'QuestPanelRoot', (1, y + 29, z + 4), 4.6)
    # Watch face on the right of the calibrated watch panel: the hand turns about the pivot (roll); +roll swings it to
    # the viewer's left (the past mark), -roll to the right (the present mark).
    cylinder = unreal.load_asset('/Engine/BasicShapes/Cylinder')
    amber = panel_material('M_QuestPointer', (.75, .43, .12))

    def dial_part(name, mesh, material, parent, at, size, rot=(0, 0, 0)):
        part = component(bp, name, unreal.StaticMeshComponent, parent)
        part.set_static_mesh(mesh)
        part.set_material(0, material)
        transform(part, at, rot, size)
        part.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        part.set_editor_property('cast_shadow', False)
        part.set_editor_property('visible', False)
        return part
    # Better-looking watch (16 November 2026): the face is drawn by watch_face_material (ticks, rings, travel arc, seconds
    # subdial); around it a dark outer bezel, the amber rim and a crown; the hand has a counterweight, the knob a pale jewel,
    # the hub a dark cap; a small seconds hand runs in the subdial and a pale lamp on the rim shows the selected era.
    # The face, the pivot, the hand's reach and the two marks are where they were: how the dial is used is unchanged.
    ivory = panel_material('M_QuestWatchIvory', (.88, .80, .60))
    dark_brass = panel_material('M_QuestWatchBrassDark', (.30, .16, .04))
    navy = panel_material('M_QuestWatchNavy', (.006, .012, .028))
    dial_part('QuestDialBezel', cylinder, dark_brass, 'QuestPanelRoot', (-0.25, DIAL_Y, DIAL_Z), (.51, .51, .002), rot=(90, 0, 0))
    dial_part('QuestDialCrown', cube, amber, 'QuestPanelRoot', (-0.1, DIAL_Y, DIAL_Z + 26.6), (.006, .034, .026))
    dial_part('QuestDialRim', cylinder, amber, 'QuestPanelRoot', (-0.2, DIAL_Y, DIAL_Z), (.47, .47, .006), rot=(90, 0, 0))
    face = dial_part('QuestDial', cylinder, watch_face_material(), 'QuestPanelRoot', (0.3, DIAL_Y, DIAL_Z),
                     (DIAL_RADIUS / 50.0, DIAL_RADIUS / 50.0, .008), rot=(90, 0, 0))
    face.set_collision_profile_name('UI')
    pivot = component(bp, 'QuestDialPivot', unreal.SceneComponent, 'QuestPanelRoot')
    transform(pivot, (1.2, DIAL_Y, DIAL_Z), rot=(0, 0, -DIAL_MARK_DEG))
    dial_part('QuestDialHand', cube, amber, 'QuestDialPivot', (0.2, 0, 8.5), (.008, .012, .17))
    dial_part('QuestDialHandTail', cube, amber, 'QuestDialPivot', (0.2, 0, -2.2), (.008, .022, .044))
    dial_part('QuestDialKnob', sphere, amber, 'QuestDialPivot', (0.6, 0, 17.5), (.045, .045, .045))
    dial_part('QuestDialKnobCore', sphere, ivory, 'QuestDialPivot', (2.0, 0, 17.5), (.026, .026, .026))
    dial_part('QuestDialHub', sphere, amber, 'QuestPanelRoot', (1.2, DIAL_Y, DIAL_Z), (.036, .036, .036))
    dial_part('QuestDialHubCap', sphere, navy, 'QuestPanelRoot', (2.4, DIAL_Y, DIAL_Z), (.016, .016, .016))
    seconds = component(bp, 'QuestDialSecondsPivot', unreal.SceneComponent, 'QuestPanelRoot')
    transform(seconds, (0.9, DIAL_Y, DIAL_Z - DIAL_SUBDIAL * DIAL_RADIUS))
    dial_part('QuestDialSecondsHand', cube, ivory, 'QuestDialSecondsPivot', (0, 0, 1.7), (.003, .005, .046))
    dial_part('QuestDialSecondsHub', sphere, amber, 'QuestPanelRoot', (0.9, DIAL_Y, DIAL_Z - DIAL_SUBDIAL * DIAL_RADIUS), (.012, .012, .012))
    for name, angle, label, text_name in [('QuestDialMarkPast', DIAL_MARK_DEG, 'BEFORE THE WAR', 'QuestDialPastText'),
                                          ('QuestDialMarkNow', -DIAL_MARK_DEG, 'PRESENT', 'QuestDialNowText')]:
        offset_y = math.sin(math.radians(angle))
        offset_z = math.cos(math.radians(angle))
        dial_part(name, cube, amber, 'QuestPanelRoot', (0.9, DIAL_Y + offset_y * DIAL_RADIUS * .86, DIAL_Z + offset_z * DIAL_RADIUS * .86),
                  (.008, .012, .045), rot=(0, 0, angle))
        dial_part(name.replace('Mark', 'Glow'), sphere, ivory, 'QuestPanelRoot',
                  (0.6, DIAL_Y + offset_y * DIAL_RADIUS * 1.035, DIAL_Z + offset_z * DIAL_RADIUS * 1.035), (.02, .02, .02))
        mark_text = text_component(bp, text_name, 'QuestPanelRoot', (1, DIAL_Y + offset_y * 20.0, DIAL_Z + 31.5), 3.6)
        mark_text.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
        mark_text.set_editor_property('text', unreal.Text(label))
        mark_text.set_editor_property('visible', False)
    # Drawn hands: one MotionControllerComponent per OpenXR hand keypoint (the fingertip sources above are four of them)
    # and one stretched sphere per finger bone plus the palm, placed in world space each frame by QuestHandDraw.
    hand_look = hand_material()
    for side in ['Left', 'Right']:
        for keypoint in HAND_KEYPOINTS:
            c = component(bp, side + keypoint, unreal.MotionControllerComponent, 'VROrigin')
            c.set_editor_property('motion_source', unreal.Name(side + keypoint))
            c.set_editor_property('player_index', 0)
            c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        for part_name in HAND_PARTS:
            part = component(bp, 'QuestHand' + side + part_name, unreal.StaticMeshComponent, capsule_name)
            part.set_static_mesh(sphere)
            part.set_material(0, hand_look)
            transform(part, size=(.02, .02, .02))
            for flag in ['absolute_location', 'absolute_rotation', 'absolute_scale']:
                part.set_editor_property(flag, True)
            part.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            part.set_editor_property('cast_shadow', False)
            part.set_editor_property('visible', False)
    # Watch on the wrist: a root placed in world space each frame by QuestWristFrame; the parts are fixed to it.
    wrist_root = component(bp, 'QuestWristRoot', unreal.SceneComponent, capsule_name)
    for flag in ['absolute_location', 'absolute_rotation', 'absolute_scale']:
        wrist_root.set_editor_property(flag, True)
    face_size = WRIST_FACE_CM / 100.0
    face_radius = WRIST_FACE_CM / 2.0
    strap = panel_material('M_QuestWatchStrap', (.035, .02, .012))
    transform(component(bp, 'QuestWristPivot', unreal.SceneComponent, 'QuestWristRoot'), (0, 0, -0.86))
    transform(component(bp, 'QuestWristSecondsPivot', unreal.SceneComponent, 'QuestWristRoot'), (-DIAL_SUBDIAL * face_radius, 0, -0.84))
    dial_part('QuestWristCuff', sphere, hand_look, 'QuestWristRoot', (0, 0, WRIST_RISE_CM), (.056, .075, WRIST_RISE_CM / 50.0))
    dial_part('QuestWristStrap', cylinder, strap, 'QuestWristRoot', (0, 0, WRIST_RISE_CM), (.061, WRIST_RISE_CM / 50.0 + .005, .022), rot=(0, 0, 90))
    dial_part('QuestWristCase', cylinder, amber, 'QuestWristRoot', (0, 0, -0.45), (face_size + .006, face_size + .006, .005))
    dial_part('QuestWristDial', cylinder, watch_face_material(), 'QuestWristRoot', (0, 0, -0.72), (face_size, face_size, .001))
    # What a pinch has to hit: a hidden disc a little wider than the case (WRIST_TOUCH_CM) and a centimetre thick. It is
    # left out of the near-miss snap of QuestUiPick (seen in the first take: a hand parked 4 cm beside the watch pointed
    # at it), so the watch opens only when the pinch ray really passes through it.
    wrist_touch = dial_part('QuestWristTouch', cylinder, strap, 'QuestWristRoot', (0, 0, -0.6), (WRIST_TOUCH_CM / 100.0, WRIST_TOUCH_CM / 100.0, .01))
    wrist_touch.set_collision_profile_name('UI')
    dial_part('QuestWristHand', cube, amber, 'QuestWristPivot', (face_radius * .39, 0, 0), (face_radius * .0078, .003, .0015))
    dial_part('QuestWristHub', sphere, amber, 'QuestWristRoot', (0, 0, -0.86), (.005, .005, .004))
    dial_part('QuestWristSecondsHand', cube, ivory, 'QuestWristSecondsPivot', (face_radius * .08, 0, 0), (face_radius * .0017, .0012, .001))
    gaze = component(bp, 'QuestGazeDot', unreal.StaticMeshComponent, capsule_name)
    gaze.set_static_mesh(sphere)
    gaze.set_material(0, panel_material('M_QuestPointer', (.75, .43, .12)))
    transform(gaze, size=(.012, .012, .012))
    gaze.set_editor_property('absolute_location', True)
    gaze.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    gaze.set_editor_property('cast_shadow', False)
    gaze.set_editor_property('visible', False)
    return cdo


def wrapper(bp, name, quest_name, player_field='Player', is_hud=False):
    """Insert an XR branch before an existing function, preserving its body (re-runnable)."""
    g = og.events(bp) if is_hud else og.Graph(bp, og.E.get_graph_editor(og.L.find_graph(bp, name)))
    entry = og.pin_out(g.event(name)) if is_hud else g.entry
    ed = g.editor
    comments = [c for c in ed.list_comment_nodes() if str(og.L.get_comment_text(c)) == MARKER + ':' + name]
    raw = unreal.EditorAssetLibrary.get_metadata_tag(bp, 'Quest.XRWrappers')
    records = json.loads(raw) if raw else {}
    names = records.get(name, [])
    marked = [n for n in ed.list_all_nodes() if n.get_name() in names]
    if not marked:
        marked = [n for c in comments for n in og.L.get_nodes_in_comment(c)]
    if marked:
        branch = next(n for n in marked if n.get_class().get_name() == 'K2Node_IfThenElse')
        original = list(og.P.list_connected_pins(og.pin_out(branch, 'else')))
        for comment in comments:
            ed.remove_comment_node(comment)
        ed.remove_nodes(marked)
    else:
        original = list(og.P.list_connected_pins(entry))
    og.P.break_pin_links(entry)
    before = set(n.get_path_name() for n in ed.list_all_nodes())
    f = Flow(g, entry)
    player = f.data(GS + 'GetPlayerCharacter', PlayerIndex=0) if is_hud else f.var(player_field)
    xr, desktop = f.branch(f.tag(player, 'Quest.XRPlayer'))
    for destination in original:
        og.link(desktop.cur, destination)
    if quest_name:
        params = {str(og.P.get_pin_name(p)): p for p in og.L.list_output_pins(g.entry_node)
                  if str(og.P.get_pin_name(p)) != 'then'}
        xr.own(quest_name, **params)
    new_nodes = [n for n in ed.list_all_nodes() if n.get_path_name() not in before]
    for i, n in enumerate(new_nodes):
        og.L.set_node_pos(n, unreal.IntPoint(-2600 + (i % 5) * 300, -1000 + (i // 5) * 240))
    records[name] = [n.get_name() for n in new_nodes]
    unreal.EditorAssetLibrary.set_metadata_tag(bp, 'Quest.XRWrappers', json.dumps(records))


def build_character(manager):
    bp = og.blueprint(CHAR_PATH, unreal.Character)
    for name, kind, value in [('QuestXRActive', 'bool', False), ('QuestSnapLatched', 'bool', False),
                              ('QuestComfortSimulation', 'bool', False), ('QuestHeadBlocked', 'bool', False),
                              ('QuestModalAxisLatched', 'bool', False), ('QuestMenuAxisLatched', 'bool', False),
                              ('QuestChoiceIndex', 'int', 1), ('QuestLastMode', 'int', -1), ('QuestFlowMarker', 'int', 0),
                              ('QuestMenuText', 'string', '')]:
        og.member(bp, name, kind, value)
    for name in ['QuestHeadBefore', 'QuestDestination', 'QuestBodyBefore']:
        og.member(bp, name, og.struct_type('vector'))
    og.member(bp, 'QuestController', og.object_type(unreal.PlayerController))
    og.member(bp, 'QuestManager', og.object_type(manager))
    og.member(bp, 'QuestIgnoredActors', og.array_type(og.object_type(unreal.Actor)))
    for name in ['QuestPanelTitle', 'QuestPanelText', 'QuestChoiceText1', 'QuestChoiceText2', 'QuestChoiceText3', 'QuestStatusText',
                 'QuestChoiceText4', 'QuestChoiceText5', 'QuestHudStatusText']:
        og.member(bp, 'QuestCached' + name, 'string', '')
    # Hands-first layer members (6 November 2026).
    # The simulation members are instance-editable so the PIE harnesses can drive them from Python (plain
    # Blueprint members cannot be set on instances); the tuning values are editable for the same reason.
    for name in ['QuestSimHands', 'QuestSimLeftValid', 'QuestSimRightValid']:
        og.member(bp, name, 'bool', False, instance_editable=True)
    for name in ['QuestLeftTracked', 'QuestRightTracked', 'QuestLeftPinch', 'QuestRightPinch', 'QuestLeftPinchWas',
                 'QuestRightPinchWas', 'QuestLeftPressed', 'QuestRightPressed', 'QuestHandsActive', 'QuestMenuGestureFired',
                 'QuestHandRayHit', 'QuestHudVisible']:
        og.member(bp, name, 'bool', False)
    og.member(bp, 'QuestSeated', 'bool', True, instance_editable=True)
    og.member(bp, 'QuestLeftPinchHeld', 'real', 0.0)
    for name, value in [('QuestPinchOn', PINCH_ON_CM), ('QuestPinchOff', PINCH_OFF_CM), ('QuestMenuGestureSeconds', MENU_GESTURE_SECONDS)]:
        og.member(bp, name, 'real', value, instance_editable=True)
    for name in ['QuestSeatedCalibrations', 'QuestBlinks', 'QuestHudPlacements']:
        og.member(bp, name, 'int', 0)
    for name in ['QuestSimLeftThumb', 'QuestSimLeftIndex', 'QuestSimRightThumb', 'QuestSimRightIndex']:
        og.member(bp, name, og.struct_type('vector'), instance_editable=True)
    for name in ['QuestLeftPinchPoint', 'QuestRightPinchPoint', 'QuestLeftAimPoint', 'QuestRightAimPoint', 'QuestHandThumb', 'QuestHandIndex', 'QuestHandRayStart',
                 'QuestHandRayEnd', 'QuestHudTarget']:
        og.member(bp, name, og.struct_type('vector'))
    og.member(bp, 'QuestHandHitActor', og.object_type(unreal.Actor))
    og.member(bp, 'QuestTeleportTarget', og.object_type(unreal.Actor))
    og.member(bp, 'QuestHandHitComponent', og.object_type(unreal.PrimitiveComponent))
    og.member(bp, 'QuestUiHitComponent', og.object_type(unreal.PrimitiveComponent))
    og.member(bp, 'QuestUiHit', 'bool', False)
    og.member(bp, 'QuestUiHitDistance', 'real', 0.0)
    og.member(bp, 'QuestUiHitLocation', og.struct_type('vector'))
    og.member(bp, 'QuestPanelDistance', 'real', 180.0)
    og.member(bp, 'QuestLastHandAction', 'string', '')
    # Easier-controls pass (10 November 2026). Members the PIE harnesses set are instance-editable.
    og.member(bp, 'QuestOnboardStep', 'int', 1, instance_editable=True)
    og.member(bp, 'QuestGazeSelect', 'bool', False, instance_editable=True)
    og.member(bp, 'QuestAutoGazeEnabled', 'bool', True, instance_editable=True)
    og.member(bp, 'QuestDwellSeconds', 'real', DWELL_SECONDS, instance_editable=True)
    og.member(bp, 'QuestDebounceSeconds', 'real', DEBOUNCE_SECONDS, instance_editable=True)
    for name in ['QuestOnboardDone', 'QuestGazeFire', 'QuestHoverLanding', 'QuestHoverPrevValid', 'QuestAutoGaze', 'QuestLeftAimValid', 'QuestRightAimValid']:
        og.member(bp, name, 'bool', False)
    for name in ['QuestRightCool', 'QuestLeftCool', 'QuestDwellTime', 'QuestNoInputTime', 'QuestUiSnapBest', 'QuestTelemetryTime', 'QuestFps']:
        og.member(bp, name, 'real', 0.0)
    og.member(bp, 'QuestActionLog', 'string', '')
    for name, value in [('QuestDwellId', 0), ('QuestDwellSubject', 0), ('QuestDwellFiredId', -1), ('QuestDebounced', 0), ('QuestGazeFires', 0)]:
        og.member(bp, name, 'int', value)
    og.member(bp, 'QuestHintText', 'string', '')
    # Demo-review fixes (12 November 2026): word wrap for panel and HUD text (recomputed only when the source changes).
    for name in ['QuestWrapRest', 'QuestWrapOut', 'QuestWrapSrcPanel', 'QuestWrappedPanel', 'QuestWrapSrcMenu', 'QuestWrappedMenu',
                 'QuestWrapSrcHud', 'QuestWrappedHud']:
        og.member(bp, name, 'string', '')
    og.member(bp, 'QuestHoverPrev', og.object_type(unreal.PrimitiveComponent))
    og.member(bp, 'QuestUiSnapComponent', og.object_type(unreal.PrimitiveComponent))
    og.member(bp, 'QuestUiSnapPoint', og.struct_type('vector'))
    # Competition pass (12 November 2026, later): drawn hands, watch dial, main hand, large text.
    for name in ['QuestLeftHanded', 'QuestLargeText', 'QuestSimJoints', 'QuestMainChosen', 'QuestOnboardUsed', 'QuestOnboardMoved']:
        og.member(bp, name, 'bool', False, instance_editable=True)
    for name in ['QuestHandShownLeft', 'QuestHandShownRight', 'QuestDialHeld', 'QuestDialVisible', 'QuestDialGrabPending', 'QuestHudDirty',
                 'QuestPhysLeftTracked', 'QuestPhysRightTracked', 'QuestSwapTemp']:
        og.member(bp, name, 'bool', False)
    og.member(bp, 'QuestDialAngle', 'real', -DIAL_MARK_DEG)
    og.member(bp, 'QuestDialSecondsAngle', 'real', 0.0)
    for name in ['QuestDialOffset', 'QuestDialRayAngle']:
        og.member(bp, name, 'real', 0.0)
    og.member(bp, 'QuestUiZoom', 'real', 1.0)
    og.member(bp, 'QuestDialTurns', 'int', 0)
    # Watch on the wrist and the tick heard on a pinch (16 November 2026, night).
    for name in ['QuestWristShown', 'QuestTickPending']:
        og.member(bp, name, 'bool', False)
    og.member(bp, 'QuestWristSecondsAngle', 'real', 0.0)
    for name in ['QuestDialTickStep', 'QuestTicks']:
        og.member(bp, name, 'int', 0)
    for name in ['QuestRawQuestPanelText', 'QuestRawQuestHudStatusText', 'QuestCachedQuestChoiceText6', 'QuestCachedQuestChoiceText7']:
        og.member(bp, name, 'string', '')
    signatures = {'QuestBegin': {}, 'QuestFrame': {'DeltaSeconds': 'real'}, 'QuestInput': {},
                  'QuestPrimary': {}, 'QuestPanelFrame': {}, 'QuestPlacePanel': {}, 'QuestPhotoPose': {},
                  'QuestSnap': {'Angle': 'real'}, 'QuestTeleport': {}, 'QuestAlignHead': {},
                  'QuestCycleChoice': {}, 'QuestPointerTrace': {}, 'QuestRoomscale': {}, 'QuestHeadOcclusion': {},
                  'QuestSetComfortSimulation': {'Enabled': 'bool'}, 'QuestPickUI': {},
                  'QuestMenuInput': {}, 'QuestMenuBack': {}, 'QuestMenuRender': {}, 'QuestShowLandings': {},
                  'QuestHandsFrame': {'DeltaSeconds': 'real'}, 'QuestHandAct': {'Right': 'bool'}, 'QuestMenuGesture': {},
                  'QuestSeatedCalibrate': {}, 'QuestBlink': {}, 'QuestHudFrame': {}, 'QuestTeleportTo': {}, 'QuestUiPick': {},
                  'QuestToggleGaze': {}, 'QuestDwellFrame': {'DeltaSeconds': 'real'}, 'QuestHintFrame': {}, 'QuestHoverApply': {},
                  'QuestOnboardAdvance': {'FromStep': 'int'}, 'QuestTelemetry': {'DeltaSeconds': 'real'},
                  'QuestWrap': {'Text': 'string', 'Width': 'int'},
                  'QuestHandDraw': {}, 'QuestDialFrame': {'DeltaSeconds': 'real'}, 'QuestDialApply': {}, 'QuestAdoptHand': {},
                  'QuestToggleHand': {}, 'QuestToggleLargeText': {}, 'QuestWristFrame': {'DeltaSeconds': 'real'}}
    for name, inputs in signatures.items():
        reset_function(bp, name, inputs)
    probe_graph = og.function(bp, 'QuestHeadOcclusion', reset=False)
    probe = probe_graph.call(SYS + 'SphereOverlapComponents')
    og.member(bp, 'QuestWorldObjectTypes', og.P.get_pin_type(og.pin_in(probe, 'ObjectTypes')))
    probe_graph.editor.remove_nodes([probe])
    og.compile_bp(bp)
    setup_components(bp)
    cdo = unreal.get_default_object(og.L.generated_class(bp))
    cdo.set_editor_property('QuestWorldObjectTypes', [unreal.ObjectTypeQuery.ECC_WORLD_STATIC,
                                                   unreal.ObjectTypeQuery.ECC_WORLD_DYNAMIC,
                                                   unreal.ObjectTypeQuery.ECC_PAWN,
                                                   unreal.ObjectTypeQuery.ECC_PHYSICS_BODY,
                                                   unreal.ObjectTypeQuery.ECC_VEHICLE,
                                                   unreal.ObjectTypeQuery.ECC_DESTRUCTIBLE])
    og.compile_bp(bp)

    def fn(name):
        return QFlow(reset_function(bp, name, signatures[name]))

    def key(f, k, held=False):
        return f.key(k, held)

    def any_key(f, *keys):
        result = key(f, keys[0])
        for k in keys[1:]:
            result = f.or_(result, key(f, k))
        return result

    def axis(f, name):
        return f.data(PC + 'GetInputAnalogKeyState', **{'self': f.var('Controller'), 'Key': name})

    def set_pointer_ray(f):
        # Pointer source priority: tracked right hand, tracked left hand (eye-to-pinch ray), right controller aim, camera.
        right_hand, rest = f.branch(f.var('QuestRightTracked'))
        left_hand, rest = rest.branch(rest.var('QuestLeftTracked'))
        aim, cam = rest.branch(rest.data(MC + 'IsTracked', **{'self': rest.var('RightAim')}))
        for flow, point in [(right_hand, 'QuestRightAimPoint'), (left_hand, 'QuestLeftAimPoint')]:
            flow.set('QuestHeadBefore', location(flow, 'QuestCamera'))
            direction = flow.data(MATH + 'Normal', A=sub(flow, flow.var(point), flow.var('QuestHeadBefore')), Tolerance=0.0001)
            flow.set('QuestDestination', add(flow, flow.var('QuestHeadBefore'), scale(flow, direction, 650)))
        for flow, source in [(aim, 'RightAim'), (cam, 'QuestCamera')]:
            flow.set('QuestHeadBefore', location(flow, source))
            flow.set('QuestDestination', add(flow, flow.var('QuestHeadBefore'), scale(flow,
                     flow.data(SC + 'GetForwardVector', **{'self': flow.var(source)}), 650)))
        return merge(right_hand, left_hand, aim, cam)

    f = fn('QuestBegin')
    f.set('QuestController', f.data(GS + 'GetPlayerController', PlayerIndex=0))
    f.set('QuestXRActive', f.data(HMD + 'IsHeadMountedDisplayEnabled'))
    f.call('/Script/Engine.KismetArrayLibrary.Array_AddUnique', TargetArray=f.var('QuestIgnoredActors'),
           NewItem=f.data(GS + 'GetPlayerCharacter', PlayerIndex=0))
    f.call(ACT + 'SetTickableWhenPaused', bTickableWhenPaused=True)
    f.own('QuestShowLandings')
    active, fallback = f.branch(f.var('QuestXRActive'))
    active.call(SC + 'K2_SetRelativeLocation', **{'self': active.var('QuestCamera'),
                'NewLocation': unreal.Vector(0, 0, 0), 'bSweep': False, 'bTeleport': True})
    seated, standing = active.branch(active.var('QuestSeated'))
    seated.own('QuestSeatedCalibrate')
    standing.call(HMD + 'SetTrackingOrigin', Origin='LocalFloor')
    fallback.call(SC + 'K2_SetRelativeLocation', **{'self': fallback.var('QuestCamera'),
                  'NewLocation': unreal.Vector(0, 0, 160), 'bSweep': False, 'bTeleport': True})

    # The merge of 2 November hid the authored landing discs together with the old development scenery
    # (query collision kept). The headset player needs to see them; this is runtime only, the map is unchanged.
    # A landing is shown only when it stands on free floor: a ray from 1.2 m above it must first meet the
    # landing disc itself or a surface within 10 cm of its origin. A landing swallowed by merged city geometry
    # (the market arcade node, 4 November inventory) stays hidden and loses its query collision so the
    # teleport ray can never select it.
    f = fn('QuestShowLandings')
    found = f.call(GS + 'GetAllActorsWithTag', Tag='Quest.Teleport')
    loop = f.g._node(f.g.editor.add_macro_node(MACRO), 'ForEachLoop')
    og.link(f.cur, og.pin_in(loop, 'Exec'))
    og.link(og.value_pin(found, 'OutActors'), og.pin_in(loop, 'Array'))
    body = QFlow(f.g, og.pin_out(loop, 'LoopBody'))
    element = og.value_pin(loop, 'Array Element')
    loc = body.data(ACT + 'K2_GetActorLocation', **{'self': element})
    probe = body.call(SYS + 'LineTraceSingle', Start=add(body, loc, unreal.Vector(0, 0, 120)), End=sub(body, loc, unreal.Vector(0, 0, 100)),
                      TraceChannel='TraceTypeQuery1', bTraceComplex=False, ActorsToIgnore=body.var('QuestIgnoredActors'),
                      DrawDebugType='None', bIgnoreSelf=True)
    probe_hit = body.call(GS + 'BreakHitResult', Hit=og.value_pin(probe, 'OutHit'))
    px, py, pz = split_vec(body, sub(body, og.value_pin(probe_hit, 'ImpactPoint'), loc))
    on_floor = body.or_(body.data(MATH + 'EqualEqual_ObjectObject', A=og.value_pin(probe_hit, 'HitActor'), B=element),
                        body.data(MATH + 'LessEqual_DoubleDouble', A=body.data(MATH + 'Abs', A=pz), B=10.0))
    free, blocked = body.branch(body.and_(og.value_pin(probe, 'ReturnValue'), on_floor))
    free.call(ACT + 'SetActorHiddenInGame', **{'self': element, 'bNewHidden': False})
    blocked.call(ACT + 'SetActorHiddenInGame', **{'self': element, 'bNewHidden': True})
    blocked.call(ACT + 'SetActorEnableCollision', **{'self': element, 'bNewActorEnableCollision': False})

    f = fn('QuestFrame')
    ready, missing = f.branch(f.valid(f.var('QuestManager')))
    actor = missing.data(GS + 'GetActorOfClass', ActorClass=MANAGER_CLASS)
    cast = missing.g.cast(manager, actor)
    og.link(missing.cur, og.pin_in(cast))
    assigned = QFlow(missing.g, og.pin_out(cast))
    assigned.set('QuestManager', missing.g.cast_value(cast))
    f = merge(ready, assigned)
    f.own('QuestRoomscale')
    f.own('QuestHeadOcclusion')
    f.own('QuestHandsFrame', DeltaSeconds=f.g.input('DeltaSeconds'))
    f.own('QuestHandDraw')
    f.own('QuestPanelFrame')
    f.own('QuestDialFrame', DeltaSeconds=f.g.input('DeltaSeconds'))
    f.own('QuestWristFrame', DeltaSeconds=f.g.input('DeltaSeconds'))
    f.own('QuestPhotoPose')
    f.own('QuestPointerTrace')
    f.own('QuestHintFrame')
    f.own('QuestHudFrame')
    f.own('QuestDwellFrame', DeltaSeconds=f.g.input('DeltaSeconds'))
    f.own('QuestTelemetry', DeltaSeconds=f.g.input('DeltaSeconds'))
    # The release menus run outside InputFrame (UpdateStep skips it while a menu is active), so the
    # controller menu input lives on the pawn's own tick. Physical head motion never reads controller look.
    menu, no_menu = f.branch(f.mv('ReleaseMenuActive'))
    menu.own('QuestMenuInput')

    # Word wrap (12 November 2026): TextRender does not wrap, and a long manager line (the watch status, a journal page)
    # ran off the panel. Unrolled: up to WRAP_LINES lines; existing line breaks are kept; a line is cut at its last
    # space inside Width characters (hard cut when it has none). Text whose lines already fit comes back unchanged.
    f = fn('QuestWrap')
    f.set('QuestWrapRest', f.g.input('Text'))
    f.set('QuestWrapOut', '')
    for _ in range(WRAP_LINES):
        more, done = f.branch(f.data(MATH + 'Greater_IntInt', A=f.data(STR + 'Len', S=f.var('QuestWrapRest')), B=0))
        head = more.data(STR + 'Left', SourceString=more.var('QuestWrapRest'), Count=more.data(MATH + 'Add_IntInt', A=more.g.input('Width'), B=1))
        newline = more.data(STR + 'FindSubstring', SearchIn=head, Substring='\n', bUseCase=False, bSearchFromEnd=False, StartPosition=-1)
        broken, unbroken = more.branch(more.data(MATH + 'GreaterEqual_IntInt', A=newline, B=0))
        broken.set('QuestWrapOut', join_text(broken, join_text(broken, broken.var('QuestWrapOut'),
                   broken.data(STR + 'Left', SourceString=broken.var('QuestWrapRest'), Count=newline)), '\n'))
        broken.set('QuestWrapRest', broken.data(STR + 'RightChop', SourceString=broken.var('QuestWrapRest'), Count=broken.data(MATH + 'Add_IntInt', A=newline, B=1)))
        short, long_ = unbroken.branch(unbroken.data(MATH + 'LessEqual_IntInt', A=unbroken.data(STR + 'Len', S=unbroken.var('QuestWrapRest')), B=unbroken.g.input('Width')))
        short.set('QuestWrapOut', join_text(short, short.var('QuestWrapOut'), short.var('QuestWrapRest')))
        short.set('QuestWrapRest', '')
        space = long_.data(STR + 'FindSubstring', SearchIn=head, Substring=' ', bUseCase=False, bSearchFromEnd=True, StartPosition=-1)
        soft, hard = long_.branch(long_.data(MATH + 'Greater_IntInt', A=space, B=0))
        soft.set('QuestWrapOut', join_text(soft, join_text(soft, soft.var('QuestWrapOut'),
                 soft.data(STR + 'Left', SourceString=soft.var('QuestWrapRest'), Count=space)), '\n'))
        soft.set('QuestWrapRest', soft.data(STR + 'RightChop', SourceString=soft.var('QuestWrapRest'), Count=soft.data(MATH + 'Add_IntInt', A=space, B=1)))
        hard.set('QuestWrapOut', join_text(hard, join_text(hard, hard.var('QuestWrapOut'),
                 hard.data(STR + 'Left', SourceString=hard.var('QuestWrapRest'), Count=hard.g.input('Width'))), '\n'))
        hard.set('QuestWrapRest', hard.data(STR + 'RightChop', SourceString=hard.var('QuestWrapRest'), Count=hard.g.input('Width')))
        f = merge(broken, short, soft, hard, done)
    f.set('QuestWrapOut', join_text(f, f.var('QuestWrapOut'), f.var('QuestWrapRest')))

    def wrapped(flow, raw, key, width):
        """The wrapped form of a string expression, recomputed only when the expression's value changes."""
        changed, same = flow.branch(flow.data(STR + 'NotEqual_StrStr', A=raw, B=flow.var('QuestWrapSrc' + key)))
        changed.set('QuestWrapSrc' + key, raw)
        changed.own('QuestWrap', Text=changed.var('QuestWrapSrc' + key), Width=width)
        changed.set('QuestWrapped' + key, changed.var('QuestWrapOut'))
        flow.cur = merge(changed, same).cur
        return flow.var('QuestWrapped' + key)

    f = fn('QuestPlacePanel')
    loc = location(f, 'QuestCamera')
    rot = rotation(f, 'QuestCamera')
    br = f.call(MATH + 'BreakRotator', InRot=rot)
    # The panel opens along the line of sight, not only at eye level (12 November 2026): a player looking down at the
    # photograph or the workbench used to get the dialogue text far above their view. The pitch is followed within
    # PANEL_PITCH_DOWN .. PANEL_PITCH_UP degrees; the yaw as before. The panel still faces the eye.
    pitch = f.data(MATH + 'FClamp', Value=f.data(MATH + 'NormalizeAxis', Angle=og.value_pin(br, 'Pitch')), Min=PANEL_PITCH_DOWN, Max=PANEL_PITCH_UP)
    flat = f.data(MATH + 'MakeRotator', Roll=0, Pitch=pitch, Yaw=og.value_pin(br, 'Yaw'))
    fw = f.data(MATH + 'GetForwardVector', InRot=flat)
    panel_up = f.data(MATH + 'GetUpVector', InRot=flat)
    # Line-of-sight clearance: the panel comes closer than its 180 cm default when a wall is ahead, and closer still
    # when furniture would hide the button cluster 80 cm below the eye line (never nearer than 90 cm).
    f.set('QuestPanelDistance', 180.0)
    ahead = f.call(SYS + 'LineTraceSingle', Start=loc, End=add(f, loc, scale(f, fw, 195)), TraceChannel='TraceTypeQuery1',
                   bTraceComplex=False, ActorsToIgnore=f.var('QuestIgnoredActors'), DrawDebugType='None', bIgnoreSelf=True)
    wall, open_ = f.branch(og.value_pin(ahead, 'ReturnValue'))
    wall_hit = wall.call(GS + 'BreakHitResult', Hit=og.value_pin(ahead, 'OutHit'))
    wall.set('QuestPanelDistance', wall.data(MATH + 'FMax', A=PANEL_MIN_CM, B=wall.data(MATH + 'Subtract_DoubleDouble',
             A=wall.data(MATH + 'Vector_Distance', V1=loc, V2=og.value_pin(wall_hit, 'ImpactPoint')), B=20.0)))
    f = merge(wall, open_)
    # People and posts (12 November 2026): the Visibility ray above misses a character or a street post standing between
    # the eye and the panel, so dialogue opened behind the person speaking. Three object rays (centre and both panel
    # edges) bring the panel in front of whatever they meet.
    for angle in (0.0, -PANEL_EDGE_DEGREES, PANEL_EDGE_DEGREES):
        ray = f.data(MATH + 'RotateAngleAxis', InVect=fw, AngleDeg=angle, Axis=panel_up)
        thing = f.call(SYS + 'LineTraceSingleForObjects', Start=loc, End=add(f, loc, scale(f, ray, 195)), ObjectTypes=f.var('QuestWorldObjectTypes'),
                       bTraceComplex=False, ActorsToIgnore=f.var('QuestIgnoredActors'), DrawDebugType='None', bIgnoreSelf=True)
        met, free = f.branch(og.value_pin(thing, 'ReturnValue'))
        thing_hit = met.call(GS + 'BreakHitResult', Hit=og.value_pin(thing, 'OutHit'))
        plane = met.data(MATH + 'Subtract_DoubleDouble', A=met.data(MATH + 'Multiply_DoubleDouble',
                         A=met.data(MATH + 'Vector_Distance', V1=loc, V2=og.value_pin(thing_hit, 'ImpactPoint')), B=math.cos(math.radians(angle))), B=25.0)
        met.set('QuestPanelDistance', met.data(MATH + 'FMax', A=PANEL_MIN_CM, B=met.data(MATH + 'FMin', A=met.var('QuestPanelDistance'), B=plane)))
        f = merge(met, free)
    cluster = add(f, add(f, loc, scale(f, fw, f.var('QuestPanelDistance'))), scale(f, panel_up, -84))
    low = f.call(SYS + 'LineTraceSingle', Start=loc, End=cluster, TraceChannel='TraceTypeQuery1', bTraceComplex=False,
                 ActorsToIgnore=f.var('QuestIgnoredActors'), DrawDebugType='None', bIgnoreSelf=True)
    hidden, visible = f.branch(og.value_pin(low, 'ReturnValue'))
    low_hit = hidden.call(GS + 'BreakHitResult', Hit=og.value_pin(low, 'OutHit'))
    ratio = hidden.data(MATH + 'Divide_DoubleDouble',
                        A=hidden.data(MATH + 'Subtract_DoubleDouble', A=hidden.data(MATH + 'Vector_Distance', V1=loc, V2=og.value_pin(low_hit, 'ImpactPoint')), B=15.0),
                        B=hidden.data(MATH + 'Vector_Distance', V1=loc, V2=cluster))
    hidden.set('QuestPanelDistance', hidden.data(MATH + 'FMax', A=PANEL_MIN_CM, B=hidden.data(MATH + 'Multiply_DoubleDouble', A=hidden.var('QuestPanelDistance'), B=ratio)))
    f = merge(hidden, visible)
    # Table rule (12 November 2026): the home tables and the workbench have no collision, so no trace can see them and
    # the lower rows and the button cluster used to sink behind a table top. The panel's lower edge is therefore kept
    # within PANEL_BOTTOM_CM below the eye (table tops are about 75 cm below it): the panel comes nearer, and shrinks
    # with distance, until its lower edge clears that height.
    # Large text (QuestUiZoom above 1) makes the panel that much taller for its distance, so its lower edge drops faster.
    drop = f.data(MATH + 'FMax', A=0.2, B=f.data(MATH + 'Subtract_DoubleDouble',
                  A=f.data(MATH + 'Multiply_DoubleDouble', A=f.data(MATH + 'Multiply_DoubleDouble', A=PANEL_LOWER_EDGE_RATIO, B=f.var('QuestUiZoom')),
                           B=f.data(MATH + 'DegCos', A=pitch)), B=f.data(MATH + 'DegSin', A=pitch)))
    f.set('QuestPanelDistance', f.data(MATH + 'FMax', A=PANEL_MIN_CM, B=f.data(MATH + 'FMin', A=f.var('QuestPanelDistance'),
          B=f.data(MATH + 'Divide_DoubleDouble', A=PANEL_BOTTOM_CM, B=drop))))
    position = add(f, add(f, loc, scale(f, fw, f.var('QuestPanelDistance'))), scale(f, panel_up, -4))
    look = f.data(MATH + 'FindLookAtRotation', Start=position, Target=loc)
    f.call(SC + 'K2_SetWorldLocationAndRotation', **{'self': f.var('QuestPanelRoot'), 'NewLocation': position,
           'NewRotation': look, 'bSweep': False, 'bTeleport': True})
    # A panel pulled in by a wall shrinks with its distance, so it keeps the same angular size (field of view) and legibility.
    panel_scale = f.data(MATH + 'Multiply_DoubleDouble', A=f.var('QuestUiZoom'),
                         B=f.data(MATH + 'FMax', A=PANEL_MIN_CM / 180.0, B=f.data(MATH + 'Divide_DoubleDouble', A=f.var('QuestPanelDistance'), B=180.0)))
    f.call(SC + 'SetWorldScale3D', **{'self': f.var('QuestPanelRoot'), 'NewScale': f.data(MATH + 'MakeVector', X=panel_scale, Y=panel_scale, Z=panel_scale)})

    f = fn('QuestMenuRender')
    f.set('QuestMenuText', f.mv('ReleaseMenuBody'))
    for i in range(10):
        visible, hidden = f.branch(f.data(MATH + 'Greater_IntInt', A=f.mv('ReleaseMenuCount'), B=i))
        selected = visible.eq(visible.mv('ReleaseMenuSelection'), i)
        prefix = visible.data(MATH + 'SelectString', A='> ', B='   ', bPickA=selected)
        label = join_text(visible, prefix, visible.mv('ReleaseRow' + str(i)))
        visible.set('QuestMenuText', join_text(visible, join_text(visible, visible.var('QuestMenuText'), '\n'), label))
        f = merge(visible, hidden)
    f.set('QuestMenuText', join_text(f, join_text(f, f.var('QuestMenuText'), '\n\n'), f.mv('ReleaseMenuStatus')))
    f.set('QuestMenuText', join_text(f, f.var('QuestMenuText'), MENU_HINT))

    f = fn('QuestPanelFrame')
    changed, same = f.branch(f.not_(f.eq(f.mv('Mode'), f.var('QuestLastMode'))))
    changed.set('QuestLastMode', changed.mv('Mode'))
    changed.set('QuestChoiceIndex', 1)
    changed.own('QuestPlacePanel')
    f = merge(changed, same)
    modal = f.not_(f.eq(f.mv('Mode'), 0))
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestPanelRoot'), 'bNewVisibility': modal, 'bPropagateToChildren': False})
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestPanelBack'), 'bNewVisibility': modal, 'bPropagateToChildren': False})
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestPanelText'), 'bNewVisibility': modal, 'bPropagateToChildren': False})
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestPanelTitle'), 'bNewVisibility': modal, 'bPropagateToChildren': False})
    for name in ['QuestPanelAccent', 'QuestPanelFrameTop', 'QuestPanelFrameBottom', 'QuestPanelFrameLeft', 'QuestPanelFrameRight']:
        f.call(SC + 'SetVisibility', **{'self': f.var(name), 'bNewVisibility': modal, 'bPropagateToChildren': False})
    for name in ['QuestBtnUp', 'QuestBtnDown', 'QuestBtnOk', 'QuestBtnBack']:
        f.call(SC + 'SetVisibility', **{'self': f.var(name), 'bNewVisibility': modal, 'bPropagateToChildren': False})
        f.call(SC + 'SetVisibility', **{'self': f.var(name + 'Text'), 'bNewVisibility': modal, 'bPropagateToChildren': False})
        shown, hidden = f.branch(modal)
        shown.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': shown.var(name), 'NewType': 'QueryOnly'})
        hidden.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': hidden.var(name), 'NewType': 'NoCollision'})
        f = merge(shown, hidden)
    # Watch face: only on the calibrated watch (not the locked watch, not the bench test, which share mode 4).
    f.set('QuestDialVisible', f.and_(f.and_(f.eq(f.mv('Mode'), 4), f.mv('WatchCalibrated')),
                                     f.and_(f.not_(f.mv('Testing')), f.not_(f.mv('ReleaseMenuActive')))))
    for name in DIAL_PARTS:
        f.call(SC + 'SetVisibility', **{'self': f.var(name), 'bNewVisibility': f.var('QuestDialVisible'), 'bPropagateToChildren': False})
    for name in DIAL_DECOR:
        f.call(SC + 'SetVisibility', **{'self': f.var(name), 'bNewVisibility': f.var('QuestDialVisible'), 'bPropagateToChildren': False})
    for name, era in DIAL_LAMPS:
        f.call(SC + 'SetVisibility', **{'self': f.var(name), 'bNewVisibility': f.and_(f.var('QuestDialVisible'), f.eq(f.mv('SelectedEra'), era)),
               'bPropagateToChildren': False})
    dial_on, dial_off = f.branch(f.var('QuestDialVisible'))
    dial_on.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': dial_on.var('QuestDial'), 'NewType': 'QueryOnly'})
    dial_off.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': dial_off.var('QuestDial'), 'NewType': 'NoCollision'})
    f = merge(dial_on, dial_off)
    menu, play = f.branch(f.mv('ReleaseMenuActive'))
    menu.own('QuestMenuRender')
    set_text(menu, 'QuestPanelTitle', menu.mv('ReleaseMenuTitle'))
    set_text(menu, 'QuestPanelText', wrapped(menu, menu.var('QuestMenuText'), 'Menu', PANEL_WRAP), hands=True)
    for i in range(1, 8):
        menu.call(SC + 'SetVisibility', **{'self': menu.var('QuestChoice' + str(i)), 'bNewVisibility': False, 'bPropagateToChildren': False})
        menu.call(SC + 'SetVisibility', **{'self': menu.var('QuestChoiceText' + str(i)), 'bNewVisibility': False, 'bPropagateToChildren': False})
        menu.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': menu.var('QuestChoice' + str(i)), 'NewType': 'NoCollision'})
    set_text(play, 'QuestPanelTitle', play.mv('PanelTitle'))
    paused = play.eq(play.mv('Mode'), 6)
    choosing = play.and_(modal, play.or_(paused, play.and_(play.eq(play.mv('Mode'), 3), play.mv('DialogueWaitingChoice'))))
    choice_text, body_text = play.branch(choosing)
    set_text(choice_text, 'QuestPanelText', 'Point at an option and pinch, or press trigger.\n<Off> pinch or Back closes. A cycles the selection.', hands=True)
    # One help line that fits what the panel is showing (12 November 2026): the old footer listed every control of every
    # panel plus a "Selected option" counter that meant nothing outside a choice.
    # While the watch face is shown the text keeps to the left of it (a narrower wrap).
    pick = lambda a, b, when: body_text.data(MATH + 'SelectString', A=a, B=b, bPickA=when)
    # True watch readout (16 November 2026, the entrant asked for it). The manager's watch text ended in four lines about
    # things the player cannot do (locked islands, perspective, the time-pause test) and a raw "seconds away" count that
    # only changed when the watch was redrawn, and it said CONFIRM TRANSITION even where Select would refuse. The headset
    # panel now shows the manager's own status lines, then what Select will really do, then the home clock as a live
    # minutes:seconds reading. The manager and its text are unchanged; only what this panel draws.
    raw_panel = body_text.mv('PanelText')
    tail_at = body_text.data(STR + 'FindSubstring', SearchIn=raw_panel, Substring=WATCH_TAIL, bUseCase=True, bSearchFromEnd=False, StartPosition=-1)
    watch_head = pick(body_text.data(STR + 'Left', SourceString=raw_panel, Count=tail_at), raw_panel,
                      body_text.data(MATH + 'GreaterEqual_IntInt', A=tail_at, B=0))
    at_gate = body_text.and_(body_text.mv('AnchorActivated'), body_text.data(MATH + 'LessEqual_DoubleDouble',
                             A=body_text.data('/Script/Engine.Actor.GetDistanceTo', OtherActor=body_text.mv('AnchorActor')), B=WATCH_GATE_CM))
    watch_state = pick(WATCH_HERE, pick(WATCH_READY, WATCH_FAR, at_gate), body_text.eq(body_text.mv('SelectedEra'), body_text.mv('EraIndex')))
    watch_head = body_text.data(STR + 'Replace', SourceString=watch_head, From=WATCH_CONFIRM, To=watch_state)
    away_seconds = body_text.data(MATH + 'FTrunc', A=body_text.mv('ReturnClockSeconds'))
    away_rest = body_text.data(MATH + 'Percent_IntInt', A=away_seconds, B=60)
    away_clock = join_text(body_text, join_text(body_text, body_text.data(STR + 'Conv_IntToString', InInt=body_text.data(MATH + 'Divide_IntInt', A=away_seconds, B=60)),
                           pick(':0', ':', body_text.data(MATH + 'Less_IntInt', A=away_rest, B=10))), body_text.data(STR + 'Conv_IntToString', InInt=away_rest))
    away_line = pick(join_text(body_text, WATCH_AWAY, away_clock),
                     pick(join_text(body_text, WATCH_WAS_AWAY, away_clock), '', body_text.data(MATH + 'Greater_IntInt', A=away_seconds, B=0)),
                     body_text.eq(body_text.mv('EraIndex'), 1))
    watch_text = join_text(body_text, watch_head, pick(away_line, '', body_text.var('QuestDialVisible')))
    text = wrapped(body_text, watch_text, 'Panel',
                   body_text.data(MATH + 'SelectInt', A=DIAL_WRAP, B=PANEL_WRAP, bPickA=body_text.var('QuestDialVisible')))
    mode_is = lambda number: body_text.eq(body_text.mv('Mode'), number)
    watch_help = pick(PANEL_HELP['dial'], pick(PANEL_HELP['test'], PANEL_HELP[4], body_text.mv('Testing')), body_text.var('QuestDialVisible'))
    footer = pick(PANEL_HELP[1], pick(PANEL_HELP[2], pick(pick(PANEL_HELP['intro'], PANEL_HELP[3], body_text.mv('IntroActive')),
                  pick(watch_help, PANEL_HELP[5], mode_is(4)), mode_is(3)), mode_is(2)), mode_is(1))
    # A line holding one space keeps the help line apart from the text (set_text folds empty lines away).
    text = join_text(body_text, join_text(body_text, text, '\n \n'), footer)
    set_text(body_text, 'QuestPanelText', text, hands=True)
    play = merge(choice_text, body_text)
    for i in range(1, 4):
        visible = play.and_(choosing, play.or_(paused, play.data(MATH + 'GreaterEqual_IntInt', A=play.mv('DialogueChoiceCount'), B=i)))
        play.call(SC + 'SetVisibility', **{'self': play.var('QuestChoice' + str(i)), 'bNewVisibility': visible,
                  'bPropagateToChildren': False})
        play.call(SC + 'SetVisibility', **{'self': play.var('QuestChoiceText' + str(i)), 'bNewVisibility': visible,
                  'bPropagateToChildren': False})
        on, off = play.branch(visible)
        on.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': on.var('QuestChoice' + str(i)), 'NewType': 'QueryOnly'})
        off.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': off.var('QuestChoice' + str(i)), 'NewType': 'NoCollision'})
        play = merge(on, off)
        pause_row, dialogue_row = play.branch(paused)
        for flow, label in [(pause_row, {1: 'Resume', 2: 'Save committed progress', 3: 'Load saved progress'}[i]),
                            (dialogue_row, dialogue_row.mv('ChoiceLabel' + str(i)))]:
            selected, ordinary = flow.branch(flow.eq(flow.var('QuestChoiceIndex'), i))
            set_text(selected, 'QuestChoiceText' + str(i), join_text(selected, '> ', label))
            set_text(ordinary, 'QuestChoiceText' + str(i), label)
            flow.cur = merge(selected, ordinary).cur
        play = merge(pause_row, dialogue_row)
    # Rows 4 to 7 (pause panel only): recentre, the gaze-dwell fallback, the main hand, large text.
    visible4 = play.and_(choosing, paused)
    for index in (4, 5, 6, 7):
        row_name, row_text = 'QuestChoice' + str(index), 'QuestChoiceText' + str(index)
        play.call(SC + 'SetVisibility', **{'self': play.var(row_name), 'bNewVisibility': visible4, 'bPropagateToChildren': False})
        play.call(SC + 'SetVisibility', **{'self': play.var(row_text), 'bNewVisibility': visible4, 'bPropagateToChildren': False})
        row_on, row_off = play.branch(visible4)
        row_on.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': row_on.var(row_name), 'NewType': 'QueryOnly'})
        row_off.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': row_off.var(row_name), 'NewType': 'NoCollision'})
        play = merge(row_on, row_off)
        if index == 4:
            row_label = 'Recenter the seated view'
        elif index == 5:
            row_label = join_text(play, 'Gaze select (look 1.5 s): ', play.data(MATH + 'SelectString', A='ON', B='off', bPickA=play.var('QuestGazeSelect')))
        elif index == 6:
            row_label = join_text(play, 'Main hand: ', play.data(MATH + 'SelectString', A='LEFT', B='right', bPickA=play.var('QuestLeftHanded')))
        else:
            row_label = join_text(play, 'Large text: ', play.data(MATH + 'SelectString', A='ON', B='off', bPickA=play.var('QuestLargeText')))
        row_selected, row_ordinary = play.branch(play.eq(play.var('QuestChoiceIndex'), index))
        set_text(row_selected, row_text, join_text(row_selected, '> ', row_label))
        set_text(row_ordinary, row_text, row_label)
        play = merge(row_selected, row_ordinary)
    f = merge(menu, play)
    set_text(f, 'QuestStatusText', join_text(f, join_text(f, f.mv('Objective'), '\n'), f.mv('Prompt')))

    f = fn('QuestMenuInput')
    f, not_ready = f.branch(f.valid(f.var('QuestManager')))
    deflection = f.data(MATH + 'Add_DoubleDouble', A=axis(f, 'OculusTouch_Right_Thumbstick_Y'), B=axis(f, 'OculusTouch_Left_Thumbstick_Y'))
    centered, deflected = f.branch(f.data(MATH + 'Less_DoubleDouble', A=f.data(MATH + 'Abs', A=deflection), B=.3))
    centered.set('QuestMenuAxisLatched', False)
    unlatched, held = deflected.branch(deflected.not_(deflected.var('QuestMenuAxisLatched')))
    up, rest = unlatched.branch(unlatched.data(MATH + 'Greater_DoubleDouble', A=deflection, B=.6))
    up.set('QuestMenuAxisLatched', True)
    up.manager('ReleaseStepSelection', Direction=-1)
    down, rest = rest.branch(rest.data(MATH + 'Less_DoubleDouble', A=deflection, B=-.6))
    down.set('QuestMenuAxisLatched', True)
    down.manager('ReleaseStepSelection', Direction=1)
    f = merge(centered, held, up, down, rest)
    confirm, f = f.branch(any_key(f, 'OculusTouch_Right_Trigger_Click', 'OculusTouch_Right_A_Click', 'OculusTouch_Left_Trigger_Click'))
    confirm.manager('ReleaseActivate')
    back, f = f.branch(any_key(f, 'OculusTouch_Right_B_Click'))
    back.own('QuestMenuBack')

    f = fn('QuestMenuBack')
    main, other = f.branch(f.eq(f.mv('ReleaseMenuScreen'), 0))
    resume, stay = main.branch(main.and_(main.mv('ReleaseSessionStarted'), main.not_(main.mv('Chapter2Complete'))))
    resume.manager('ReleaseResume')
    audio, rest = other.branch(other.eq(other.mv('ReleaseMenuScreen'), 4))
    audio.manager('ReleaseShowSettings')
    rest.manager('ReleaseShowMain')

    f = fn('QuestCycleChoice')
    photo, f = f.branch(f.eq(f.mv('Mode'), 1))
    photo.manager('FlipPhoto')
    watch, f = f.branch(f.eq(f.mv('Mode'), 4))
    island = watch.data(MATH + 'Add_IntInt', A=watch.mv('SelectedIsland'), B=1)
    wrap, valid = watch.branch(watch.data(MATH + 'Greater_IntInt', A=island, B=4))
    wrap.manager('SelectIsland', Island=1)
    valid.manager('SelectIsland', Island=island)
    next_ = f.data(MATH + 'Add_IntInt', A=f.var('QuestChoiceIndex'), B=1)
    paused, dialogue = f.branch(f.eq(f.mv('Mode'), 6))
    beyond, valid = paused.branch(paused.data(MATH + 'Greater_IntInt', A=next_, B=7))
    beyond.set('QuestChoiceIndex', 1)
    valid.set('QuestChoiceIndex', next_)
    beyond, valid = dialogue.branch(dialogue.data(MATH + 'Greater_IntInt', A=next_, B=dialogue.mv('DialogueChoiceCount')))
    beyond.set('QuestChoiceIndex', 1)
    valid.set('QuestChoiceIndex', next_)

    f = fn('QuestPrimary')
    explore, rest = f.branch(f.eq(f.mv('Mode'), 0))
    with_target, without_target = explore.branch(explore.valid(explore.mv('Target')))
    with_target.own('QuestOnboardAdvance', FromStep=1)  # tutorial lesson: use something (controller path)
    explore = merge(with_target, without_target)
    explore.manager('Interact')
    dialogue, rest = rest.branch(rest.eq(rest.mv('Mode'), 3))
    choice, advance = dialogue.branch(dialogue.mv('DialogueWaitingChoice'))
    choice.own('QuestPickUI')
    choice.manager('ChooseDialogue', ChoiceIndex=choice.var('QuestChoiceIndex'))
    advance.manager('AdvanceDialogue')
    document, rest = rest.branch(rest.eq(rest.mv('Mode'), 2))
    document.manager('CloseDocument')
    watch, rest = rest.branch(rest.eq(rest.mv('Mode'), 4))
    watch.manager('ConfirmWatch')
    paused, rest = rest.branch(rest.eq(rest.mv('Mode'), 6))
    paused.own('QuestPickUI')
    tail = paused
    for i, action in [(1, 'HandleOne'), (2, 'HandleTwo'), (3, 'HandleThree')]:
        selected, tail = tail.branch(tail.eq(tail.var('QuestChoiceIndex'), i))
        selected.manager(action)
    recenter, tail = tail.branch(tail.eq(tail.var('QuestChoiceIndex'), 4))
    recenter.own('QuestSeatedCalibrate')
    recenter.manager('HandleOne')
    gaze_row, tail = tail.branch(tail.eq(tail.var('QuestChoiceIndex'), 5))
    gaze_row.own('QuestToggleGaze')
    hand_row, tail = tail.branch(tail.eq(tail.var('QuestChoiceIndex'), 6))
    hand_row.own('QuestToggleHand')
    large_row, tail = tail.branch(tail.eq(tail.var('QuestChoiceIndex'), 7))
    large_row.own('QuestToggleLargeText')
    rest.manager('CloseModal')

    f = fn('QuestPickUI')
    f = set_pointer_ray(f)
    f.set('QuestHandRayStart', f.var('QuestHeadBefore'))
    f.set('QuestHandRayEnd', f.var('QuestDestination'))
    f.own('QuestUiPick')
    picked, none = f.branch(f.var('QuestUiHit'))
    for i in range(1, 8):
        selected, picked = picked.branch(picked.data(MATH + 'EqualEqual_ObjectObject', A=picked.var('QuestUiHitComponent'), B=picked.var('QuestChoice' + str(i))))
        selected.set('QuestChoiceIndex', i)

    f = fn('QuestInput')
    f, not_ready = f.branch(f.valid(f.var('QuestManager')))
    transition, f = f.branch(f.eq(f.mv('Mode'), 7))
    for keys, action in [(('OculusTouch_Right_Trigger_Click', 'E'), 'QuestPrimary'),
                         (('OculusTouch_Right_A_Click',), 'QuestCycleChoice')]:
        pressed, f = f.branch(any_key(f, *keys))
        pressed.own(action)
    close, f = f.branch(any_key(f, 'OculusTouch_Right_B_Click', 'Escape'))
    active, closed = close.branch(close.eq(close.mv('Mode'), 0))
    active.manager('OpenPause')
    closed.manager('CloseModal')
    # Menu button (or F10) mirrors the desktop F10 hook: pause first, then the release main menu.
    main_menu, f = f.branch(any_key(f, 'OculusTouch_Left_Menu_Click', 'F10'))
    exploring, other = main_menu.branch(main_menu.eq(main_menu.mv('Mode'), 0))
    exploring.manager('OpenPause')
    exploring.manager('ReleaseShowMain')
    paused_menu, other = other.branch(other.eq(other.mv('Mode'), 6))
    paused_menu.manager('ReleaseShowMain')
    watch, f = f.branch(any_key(f, 'OculusTouch_Left_X_Click', 'Q'))
    explore, blocked = watch.branch(watch.eq(watch.mv('Mode'), 0))
    explore.manager('OpenWatch')
    journal, f = f.branch(any_key(f, 'OculusTouch_Left_Y_Click', 'Tab'))
    explore, blocked = journal.branch(journal.eq(journal.mv('Mode'), 0))
    explore.manager('OpenJournal')
    for k, action in [('One', 'HandleOne'), ('Two', 'HandleTwo'), ('Three', 'HandleThree')]:
        pressed, f = f.branch(key(f, k))
        pressed.manager(action)
    flip, f = f.branch(any_key(f, 'R', 'OculusTouch_Left_Trigger_Click'))
    flip.manager('FlipPhoto')
    intro, other = flip.branch(flip.and_(flip.eq(flip.mv('Mode'), 3), flip.mv('IntroActive')))
    intro.manager('SkipRecollections')
    skip, f = f.branch(key(f, 'SpaceBar'))
    intro, other = skip.branch(skip.and_(skip.eq(skip.mv('Mode'), 3), skip.mv('IntroActive')))
    intro.manager('SkipRecollections')
    teleport, f = f.branch(any_key(f, 'OculusTouch_Left_Thumbstick_Click', 'T'))
    open_, blocked = teleport.branch(teleport.eq(teleport.mv('Mode'), 0))
    open_.own('QuestTeleport')
    # One snap per deflection, reset only near center; no joystick translation.
    snap_axis = axis(f, 'OculusTouch_Right_Thumbstick_X')
    centered, deflected = f.branch(f.data(MATH + 'Less_DoubleDouble', A=f.data(MATH + 'Abs', A=snap_axis), B=.3))
    centered.set('QuestSnapLatched', False)
    unlatched, no = deflected.branch(deflected.not_(deflected.var('QuestSnapLatched')))
    plus, minus = unlatched.branch(unlatched.or_(unlatched.data(MATH + 'Greater_DoubleDouble', A=snap_axis, B=.7), key(unlatched, 'Right')))
    minus, no = minus.branch(minus.or_(minus.data(MATH + 'Less_DoubleDouble', A=snap_axis, B=-.7), key(minus, 'Left')))
    for flow, angle in [(plus, 30), (minus, -30)]:
        flow.set('QuestSnapLatched', True)
        explore, modal = flow.branch(flow.eq(flow.mv('Mode'), 0))
        explore.own('QuestSnap', Angle=angle)
        watch, modal = modal.branch(modal.eq(modal.mv('Mode'), 4))
        watch.manager('RotateDial', Direction=1 if angle > 0 else -1)
        journal, modal = modal.branch(modal.eq(modal.mv('Mode'), 5))
        journal.manager('TurnJournal', Direction=1 if angle > 0 else -1)
    for k, angle in [('PageUp', 30), ('PageDown', -30)]:
        pressed, rest = no.branch(key(no, k))
        explore, blocked = pressed.branch(pressed.eq(pressed.mv('Mode'), 0))
        explore.own('QuestSnap', Angle=angle)
        no = rest

    f = fn('QuestSnap')
    f.set('QuestHeadBefore', location(f, 'QuestCamera'))
    f.call(ACT + 'K2_AddActorWorldRotation', DeltaRotation=f.data(MATH + 'MakeRotator', Roll=0, Pitch=0, Yaw=f.g.input('Angle')),
           bSweep=False, bTeleport=True)
    delta = sub(f, f.var('QuestHeadBefore'), location(f, 'QuestCamera'))
    x, y, z = split_vec(f, delta)
    f.call(ACT + 'K2_AddActorWorldOffset', DeltaLocation=vec(f, x, y, 0), bSweep=True, bTeleport=True)
    f.own('QuestOnboardAdvance', FromStep=4)

    f = fn('QuestTeleport')
    f, head_blocked = f.branch(f.not_(f.var('QuestHeadBlocked')))
    loc = location(f, 'QuestCamera')
    tracked, fallback = f.branch(f.data(MC + 'IsTracked', **{'self': f.var('RightAim')}))
    tracked.set('QuestHeadBefore', location(tracked, 'RightAim'))
    tracked.set('QuestDestination', add(tracked, tracked.var('QuestHeadBefore'), scale(tracked,
                tracked.data(SC + 'GetForwardVector', **{'self': tracked.var('RightAim')}), 650)))
    fallback.set('QuestHeadBefore', loc)
    fallback.set('QuestDestination', add(fallback, fallback.var('QuestHeadBefore'), scale(fallback,
                 fallback.data(SC + 'GetForwardVector', **{'self': fallback.var('QuestCamera')}), 650)))
    f = merge(tracked, fallback)
    clearance = f.call(SYS + 'LineTraceSingle', Start=location(f, 'QuestCamera'), End=f.var('QuestHeadBefore'),
                       TraceChannel='TraceTypeQuery1', bTraceComplex=False, ActorsToIgnore=f.var('QuestIgnoredActors'),
                       DrawDebugType='None', bIgnoreSelf=True)
    f, hand_blocked = f.branch(f.not_(og.value_pin(clearance, 'ReturnValue')))
    trace = f.call(SYS + 'LineTraceSingle', Start=f.var('QuestHeadBefore'), End=f.var('QuestDestination'),
                   TraceChannel='TraceTypeQuery1', bTraceComplex=False, DrawDebugType='None', bIgnoreSelf=True)
    br = f.call(GS + 'BreakHitResult', Hit=og.value_pin(trace, 'OutHit'))
    actor = og.value_pin(br, 'HitActor')
    valid, no = f.branch(f.valid(actor))
    target, no = valid.branch(valid.tag(actor, 'Quest.Teleport'))
    target.set('QuestTeleportTarget', actor)
    target.own('QuestTeleportTo')

    f = fn('QuestTeleportTo')
    f, no_target = f.branch(f.valid(f.var('QuestTeleportTarget')))
    f.set('QuestDestination', f.data(ACT + 'K2_GetActorLocation', **{'self': f.var('QuestTeleportTarget')}))
    head = location(f, 'QuestCamera')
    root = f.data(ACT + 'K2_GetActorLocation')
    dx, dy, dz = split_vec(f, sub(f, head, root))
    landing = sub(f, add(f, f.var('QuestDestination'), unreal.Vector(0, 0, 88)), vec(f, dx, dy, 0))
    f.call(ACT + 'K2_TeleportTo', DestLocation=landing, DestRotation=f.data(ACT + 'K2_GetActorRotation'))
    f.own('QuestOnboardAdvance', FromStep=4)

    f = fn('QuestAlignHead')
    root = f.data(ACT + 'K2_GetActorLocation')
    hx, hy, hz = split_vec(f, sub(f, root, location(f, 'QuestCamera')))
    f.call(ACT + 'K2_AddActorWorldOffset', DeltaLocation=vec(f, hx, hy, 0), bSweep=True, bTeleport=True)

    f = fn('QuestPhotoPose')
    photo, no = f.branch(f.and_(f.eq(f.mv('Mode'), 1), f.valid(f.mv('HeldPhoto'))))
    hand, rest = photo.branch(photo.var('QuestLeftTracked'))
    hand.set('QuestDestination', add(hand, hand.var('QuestLeftPinchPoint'), unreal.Vector(0, 0, 6)))
    tracked, fallback = rest.branch(rest.data(MC + 'IsTracked', **{'self': rest.var('LeftGrip')}))
    tracked.set('QuestDestination', add(tracked, location(tracked, 'LeftGrip'), unreal.Vector(0, 0, 8)))
    fallback.set('QuestDestination', add(fallback, location(fallback, 'QuestCamera'), scale(fallback,
                 fallback.data(SC + 'GetForwardVector', **{'self': fallback.var('QuestCamera')}), 55)))
    photo = merge(hand, tracked, fallback)
    photo.call(ACT + 'K2_SetActorLocation', **{'self': photo.mv('HeldPhoto'), 'NewLocation': photo.var('QuestDestination'),
               'bSweep': False, 'bTeleport': True})
    look = photo.data(MATH + 'FindLookAtRotation', Start=photo.var('QuestDestination'), Target=location(photo, 'QuestCamera'))
    photo.call(ACT + 'K2_SetActorRotation', **{'self': photo.mv('HeldPhoto'), 'NewRotation': look, 'bTeleportPhysics': True})
    back, front = photo.branch(photo.mv('PhotoBack'))
    back.call(ACT + 'K2_AddActorLocalRotation', **{'self': back.mv('HeldPhoto'), 'DeltaRotation': unreal.Rotator(pitch=0, yaw=180, roll=0), 'bSweep': False, 'bTeleport': True})

    f = fn('QuestPointerTrace')
    f = set_pointer_ray(f)
    trace = f.call(SYS + 'LineTraceSingle', Start=f.var('QuestHeadBefore'), End=f.var('QuestDestination'),
                   TraceChannel='TraceTypeQuery1', bTraceComplex=False, DrawDebugType='None', bIgnoreSelf=False)
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestPointer'), 'bNewVisibility': og.value_pin(trace, 'ReturnValue'), 'bPropagateToChildren': False})
    f.set('QuestHoverLanding', False)
    hit, no = f.branch(og.value_pin(trace, 'ReturnValue'))
    br = hit.call(GS + 'BreakHitResult', Hit=og.value_pin(trace, 'OutHit'))
    hit.call(SC + 'K2_SetWorldLocation', **{'self': hit.var('QuestPointer'), 'NewLocation': og.value_pin(br, 'ImpactPoint'), 'bSweep': False, 'bTeleport': True})
    # The pointer dot keeps a constant apparent size: about 1.3 degrees at any range, never smaller than 1.6 cm.
    dot = hit.data(MATH + 'FMax', A=0.016, B=hit.data(MATH + 'Multiply_DoubleDouble', A=0.00022,
                   B=hit.data(MATH + 'Vector_Distance', V1=hit.var('QuestHeadBefore'), V2=og.value_pin(br, 'ImpactPoint'))))
    hit.call(SC + 'SetWorldScale3D', **{'self': hit.var('QuestPointer'), 'NewScale': hit.data(MATH + 'MakeVector', X=dot, Y=dot, Z=dot)})
    landing_hover, other_hover = hit.branch(hit.valid(og.value_pin(br, 'HitActor')))
    on_landing, other_hover2 = landing_hover.branch(landing_hover.tag(og.value_pin(br, 'HitActor'), 'Quest.Teleport'))
    on_landing.set('QuestHoverLanding', True)
    hit = merge(on_landing, other_hover2, other_hover)
    # The pawn's own buttons are picked by component traces, so the pointer lands on them even when the world ray
    # would stop on geometry first.
    f = merge(hit, no)
    f.set('QuestHandRayStart', f.var('QuestHeadBefore'))
    f.set('QuestHandRayEnd', f.var('QuestDestination'))
    f.own('QuestUiPick')
    ui, no_ui = f.branch(f.var('QuestUiHit'))
    ui.call(SC + 'K2_SetWorldLocation', **{'self': ui.var('QuestPointer'), 'NewLocation': ui.var('QuestUiHitLocation'), 'bSweep': False, 'bTeleport': True})
    ui.call(SC + 'SetVisibility', **{'self': ui.var('QuestPointer'), 'bNewVisibility': True, 'bPropagateToChildren': False})
    ui.call(SC + 'SetWorldScale3D', **{'self': ui.var('QuestPointer'), 'NewScale': unreal.Vector(.016, .016, .016)})
    f = merge(ui, no_ui)
    # While the watch hand is held the aim is latched where it was grabbed; the pointer dot would sit there, away from
    # the hand, so it is hidden until the pinch opens.
    holding_dial, not_holding = f.branch(f.var('QuestDialHeld'))
    holding_dial.call(SC + 'SetVisibility', **{'self': holding_dial.var('QuestPointer'), 'bNewVisibility': False, 'bPropagateToChildren': False})
    f = merge(holding_dial, not_holding)
    f.own('QuestHoverApply')

    # Hover feedback: the targeted UI button or row grows 15 percent while pointed at; restored when the pointer leaves.
    f = fn('QuestHoverApply')
    # The watch face does not grow (it would cover its own rim); every other pointed button or row does.
    now_valid = f.and_(f.var('QuestUiHit'), f.not_(f.or_(f.data(MATH + 'EqualEqual_ObjectObject', A=f.var('QuestUiHitComponent'), B=f.var('QuestDial')),
                                                         f.data(MATH + 'EqualEqual_ObjectObject', A=f.var('QuestUiHitComponent'), B=f.var('QuestWristTouch')))))
    changed = f.or_(f.data(MATH + 'NotEqual_BoolBool', A=now_valid, B=f.var('QuestHoverPrevValid')),
                    f.and_(now_valid, f.not_(f.data(MATH + 'EqualEqual_ObjectObject', A=f.var('QuestUiHitComponent'), B=f.var('QuestHoverPrev')))))
    swap, same = f.branch(changed)
    old, keep = swap.branch(swap.var('QuestHoverPrevValid'))
    old.call(SC + 'SetWorldScale3D', **{'self': old.var('QuestHoverPrev'), 'NewScale': scale(old, old.data(SC + 'K2_GetComponentScale', **{'self': old.var('QuestHoverPrev')}), 1.0 / HOVER_SCALE)})
    swap = merge(old, keep)
    new, none = swap.branch(now_valid)
    new.call(SC + 'SetWorldScale3D', **{'self': new.var('QuestUiHitComponent'), 'NewScale': scale(new, new.data(SC + 'K2_GetComponentScale', **{'self': new.var('QuestUiHitComponent')}), HOVER_SCALE)})
    new.set('QuestHoverPrev', new.var('QuestUiHitComponent'))
    # One log line per change of the pointed UI component (a Shipping build compiles PrintString out).
    new.call(SYS + 'PrintString', InString=join_text(new, 'QUESTXR hover=', new.data(SYS + 'GetDisplayName', Object=new.var('QuestUiHitComponent'))),
             bPrintToScreen=False, bPrintToLog=True)
    none.call(SYS + 'PrintString', InString='QUESTXR hover=none', bPrintToScreen=False, bPrintToLog=True)
    swap = merge(new, none)
    swap.set('QuestHoverPrevValid', now_valid)

    # Context hint: what a pinch will do right now (exploration HUD line; modal panels carry their own hint text).
    f = fn('QuestHintFrame')
    f.set('QuestHintText', IDLE_HINT)
    tgt, none = f.branch(f.and_(f.eq(f.mv('Mode'), 0), f.valid(f.mv('Target'))))
    # The manager's prompt starts with the desktop keys and two spaces ("E  Use gate anchor", "F / E  Inspect photograph");
    # a hands player must not be shown a key, so a short prefix that ends in a double space is dropped.
    gap = tgt.data(STR + 'FindSubstring', SearchIn=tgt.mv('Prompt'), Substring='  ', bUseCase=False, bSearchFromEnd=False, StartPosition=-1)
    keyed = tgt.and_(tgt.data(MATH + 'GreaterEqual_IntInt', A=gap, B=0), tgt.data(MATH + 'LessEqual_IntInt', A=gap, B=PROMPT_KEY_PREFIX_MAX))
    prompt = tgt.data(MATH + 'SelectString', A=tgt.data(STR + 'RightChop', SourceString=tgt.mv('Prompt'), Count=tgt.data(MATH + 'Add_IntInt', A=gap, B=2)),
                      B=tgt.mv('Prompt'), bPickA=keyed)
    tgt.set('QuestHintText', join_text(tgt, 'Pinch: ', prompt))
    f = merge(tgt, none)
    landing, rest = f.branch(f.var('QuestHoverLanding'))
    landing.set('QuestHintText', 'Pinch: move here.')
    f = merge(landing, rest)
    # A pointed button names itself, except when no hand is tracked and an object is gazed: then the pointer is only the
    # head's own line of sight passing through a button on its way to the object, and a pinch would use the object
    # (13 November 2026: the hint said "skip the tutorial" while the photograph behind the button was the target).
    gazed_object = f.and_(f.eq(f.mv('Mode'), 0), f.valid(f.mv('Target')))
    ui, no_ui = f.branch(f.and_(f.var('QuestUiHit'), f.or_(f.or_(f.var('QuestHandsActive'), f.var('QuestGazeSelect')), f.not_(gazed_object))))
    flows = []
    for name, label in [('QuestBtnTurnLeft', 'turn left.'), ('QuestBtnWatch', 'open the Chronowatch.'), ('QuestBtnMenu', 'open the menu.'),
                        ('QuestBtnJournal', 'open the journal.'), ('QuestBtnTurnRight', 'turn right.'),
                        ('QuestBtnCoachNext', 'next step.'), ('QuestBtnCoachSkip', 'skip the tutorial.'),
                        ('QuestWristTouch', 'open the Chronowatch on your wrist.')]:
        hovered, ui = ui.branch(ui.data(MATH + 'EqualEqual_ObjectObject', A=ui.var('QuestUiHitComponent'), B=ui.var(name)))
        hovered.set('QuestHintText', 'Pinch: ' + label)
        flows.append(hovered)
    f = merge(*flows, ui, no_ui)

    # Tutorial (13 November 2026): two lessons that are done by playing, in either order, and never block anything.
    # FromStep 1 = the player used a gazed object; FromStep 4 = the player moved or turned. QuestOnboardStep is 1 while
    # the tutorial is showing and 0 when it is over or skipped (the harnesses switch it off with 0, as before).
    # Before: four lessons in order (pinch Next, off-hand pinch, off-hand hold, move), each of which had to be performed.
    f = fn('QuestOnboardAdvance')
    on, off = f.branch(f.eq(f.var('QuestOnboardStep'), 1))
    used, rest = on.branch(on.eq(on.g.input('FromStep'), 1))
    used.set('QuestOnboardUsed', True)
    moved, rest = rest.branch(rest.eq(rest.g.input('FromStep'), 4))
    moved.set('QuestOnboardMoved', True)
    on = merge(used, moved, rest)
    done, going = on.branch(on.and_(on.var('QuestOnboardUsed'), on.var('QuestOnboardMoved')))
    done.set('QuestOnboardStep', 0)
    done.set('QuestOnboardDone', True)

    # Gaze select toggle (pause row 5). Stays in the pause panel.
    f = fn('QuestToggleGaze')
    f.set('QuestGazeSelect', f.not_(f.var('QuestGazeSelect')))
    f.set('QuestAutoGaze', False)
    f.set('QuestDwellTime', 0.0)
    f.set('QuestDwellFiredId', -1)

    # Main hand (12 November 2026, later). The pinch code works on a logical Right (main: select, interact) and a logical
    # Left (off: back, the held menu pinch, the held photograph); QuestLeftHanded maps them onto the other physical hands.
    def hand_changed(flow):
        flow.set('QuestMainChosen', True)
        # The aim latch and the text caches belong to the old mapping.
        flow.set('QuestLeftAimValid', False)
        flow.set('QuestRightAimValid', False)
        flow.set('QuestLeftPinchHeld', 0.0)
        flow.set('QuestDialHeld', False)
        for raw in ['QuestRawQuestPanelText', 'QuestRawQuestHudStatusText']:
            flow.set(raw, '~')

    # Adopted by itself: the first pinch of a session came from the other hand, aimed at a button. The pinch states are
    # left as they are, so on the next frame the still-pinched hand reads as a fresh main-hand press and acts.
    f = fn('QuestAdoptHand')
    f.set('QuestLeftHanded', f.not_(f.var('QuestLeftHanded')))
    hand_changed(f)

    # Switched from the pause row: the pinch states change sides with the hands, so the hand that is still pinching the
    # row does not read as a fresh off-hand press (which would close the panel).
    f = fn('QuestToggleHand')
    f.set('QuestLeftHanded', f.not_(f.var('QuestLeftHanded')))
    f.set('QuestSwapTemp', f.var('QuestLeftPinch'))
    f.set('QuestLeftPinch', f.var('QuestRightPinch'))
    f.set('QuestRightPinch', f.var('QuestSwapTemp'))
    f.set('QuestMenuGestureFired', True)
    for side in ['Left', 'Right']:
        f.set('Quest' + side + 'Cool', f.var('QuestDebounceSeconds'))
    hand_changed(f)

    # Large text (pause row 7): the panel and the HUD row grow in angular size; the open panel is placed again at once.
    f = fn('QuestToggleLargeText')
    f.set('QuestLargeText', f.not_(f.var('QuestLargeText')))
    f.set('QuestUiZoom', f.data(MATH + 'SelectFloat', A=LARGE_TEXT_ZOOM, B=1.0, bPickA=f.var('QuestLargeText')))
    f.set('QuestHudDirty', True)
    f.own('QuestPlacePanel')

    f = fn('QuestSetComfortSimulation')
    f.set('QuestComfortSimulation', f.g.input('Enabled'))

    f = fn('QuestRoomscale')
    active, no = f.branch(f.or_(f.var('QuestXRActive'), f.var('QuestComfortSimulation')))
    active.set('QuestBodyBefore', active.data(ACT + 'K2_GetActorLocation'))
    x, y, z = split_vec(active, sub(active, location(active, 'QuestCamera'), active.var('QuestBodyBefore')))
    active.call(ACT + 'K2_AddActorWorldOffset', DeltaLocation=vec(active, x, y, 0), bSweep=True, bTeleport=True)
    actual = sub(active, active.data(ACT + 'K2_GetActorLocation'), active.var('QuestBodyBefore'))
    active.call(SC + 'K2_AddWorldOffset', **{'self': active.var('VROrigin'), 'DeltaLocation': scale(active, actual, -1),
                'bSweep': False, 'bTeleport': True})

    f = fn('QuestHeadOcclusion')
    f.set('QuestHeadBlocked', False)
    f.call('/Script/Engine.KismetArrayLibrary.Array_AddUnique', TargetArray=f.var('QuestIgnoredActors'),
           NewItem=f.data(GS + 'GetPlayerCharacter', PlayerIndex=0))
    active, no = f.branch(f.or_(f.var('QuestXRActive'), f.var('QuestComfortSimulation')))
    overlap = active.call(SYS + 'SphereOverlapComponents', SpherePos=location(active, 'QuestCamera'),
                          SphereRadius=12.0, ObjectTypes=active.var('QuestWorldObjectTypes'),
                          ComponentClassFilter='/Script/Engine.PrimitiveComponent',
                          ActorsToIgnore=active.var('QuestIgnoredActors'))
    loop = active.g._node(active.g.editor.add_macro_node(MACRO), 'ForEachLoop')
    og.link(active.cur, og.pin_in(loop, 'Exec'))
    og.link(og.value_pin(overlap, 'OutComponents'), og.pin_in(loop, 'Array'))
    body = QFlow(active.g, og.pin_out(loop, 'LoopBody'))
    response = body.data('/Script/Engine.PrimitiveComponent.GetCollisionResponseToChannel',
                         **{'self': og.value_pin(loop, 'Array Element'), 'Channel': 'ECC_Pawn'})
    solid, ignore = body.branch(body.data(MATH + 'EqualEqual_ByteByte', A=response, B=2))
    solid.set('QuestHeadBlocked', True)
    completed = QFlow(active.g, og.pin_out(loop, 'Completed'))
    f = merge(completed, no)
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestHeadOccluder'), 'bNewVisibility': f.var('QuestHeadBlocked'),
           'bPropagateToChildren': False})

    # ---- Hands-first seated layer (6 November 2026) ----
    def on_component(f, name):
        return f.branch(f.data(MATH + 'EqualEqual_ObjectObject', A=f.var('QuestHandHitComponent'), B=f.var(name)))

    def leaf(flow, label):
        # Every dispatched hand action is answered by a soft watch tick on the next frame (QuestHandsFrame): with no
        # controller there is nothing to feel, so the pinch is heard. The next frame, so a cue the action itself starts
        # (the calibration chime, the travel sound) is already playing and keeps its place.
        flow.set('QuestTickPending', True)
        flow.set('QuestLastHandAction', label)
        flow.set('QuestActionLog', join_text(flow, flow.var('QuestActionLog'), label + ';'))
        return flow

    def read_hand(f, side):
        # side is the logical hand (Right = main, Left = off); a left-handed player's main hand is the physical left.
        other = 'Left' if side == 'Right' else 'Right'
        sim, real = f.branch(f.var('QuestSimHands'))
        sources = []
        for flow, simulated in [(sim, True), (real, False)]:
            swapped, straight = flow.branch(flow.var('QuestLeftHanded'))
            for branch, physical in [(swapped, other), (straight, side)]:
                if simulated:
                    branch.set('Quest' + side + 'Tracked', branch.var('QuestSim' + physical + 'Valid'))
                    branch.set('QuestHandThumb', branch.var('QuestSim' + physical + 'Thumb'))
                    branch.set('QuestHandIndex', branch.var('QuestSim' + physical + 'Index'))
                else:
                    branch.set('Quest' + side + 'Tracked', branch.and_(branch.data(MC + 'IsTracked', **{'self': branch.var(physical + 'IndexTip')}),
                                                                    branch.data(MC + 'IsTracked', **{'self': branch.var(physical + 'ThumbTip')})))
                    branch.set('QuestHandThumb', location(branch, physical + 'ThumbTip'))
                    branch.set('QuestHandIndex', location(branch, physical + 'IndexTip'))
                sources.append(branch)
        f = merge(*sources)
        tracked, lost = f.branch(f.var('Quest' + side + 'Tracked'))
        tracked.set('Quest' + side + 'PinchPoint', scale(tracked, add(tracked, tracked.var('QuestHandThumb'), tracked.var('QuestHandIndex')), 0.5))
        # The ray and the fingertip marker use the index tip: it barely moves when the thumb closes onto it, while the midpoint
        # of thumb and index jumps several centimetres at the instant of the pinch (found live in Meta XR Simulator).
        gap = tracked.data(MATH + 'Vector_Distance', V1=tracked.var('QuestHandThumb'), V2=tracked.var('QuestHandIndex'))
        threshold = tracked.data(MATH + 'SelectFloat', A=tracked.var('QuestPinchOff'), B=tracked.var('QuestPinchOn'),
                                 bPickA=tracked.var('Quest' + side + 'Pinch'))
        tracked.set('Quest' + side + 'PinchWas', tracked.var('Quest' + side + 'Pinch'))
        tracked.set('Quest' + side + 'Pinch', tracked.data(MATH + 'Less_DoubleDouble', A=gap, B=threshold))
        # Aim latch: while the thumb and index tips are more than AIM_LATCH_CM apart the aim follows the index tip; once they
        # close in (the pinch is forming or held) the aim stays where it was, so a change of hand posture at the instant of the
        # pinch (found live in Meta XR Simulator, where the pinch pose is a different whole-hand pose) cannot move the ray.
        follow, hold = tracked.branch(tracked.or_(tracked.data(MATH + 'Greater_DoubleDouble', A=gap, B=AIM_LATCH_CM), tracked.not_(tracked.var('Quest' + side + 'AimValid'))))
        follow.set('Quest' + side + 'AimPoint', follow.var('QuestHandIndex'))
        follow.set('Quest' + side + 'AimValid', True)
        tracked = merge(follow, hold)
        lost.set('Quest' + side + 'AimValid', False)
        lost.set('Quest' + side + 'PinchWas', lost.var('Quest' + side + 'Pinch'))
        lost.set('Quest' + side + 'Pinch', False)
        f = merge(tracked, lost)
        f.set('Quest' + side + 'Pressed', f.and_(f.var('Quest' + side + 'Pinch'), f.not_(f.var('Quest' + side + 'PinchWas'))))
        return f

    f = fn('QuestHandsFrame')
    tick_now, no_tick = f.branch(f.and_(f.var('QuestTickPending'), f.valid(f.var('QuestManager'))))
    tick_now.set('QuestTickPending', False)
    # Not during the bench test or the travel itself: their own sounds are due and nothing may stand in their way.
    tick_now, quiet = tick_now.branch(tick_now.and_(tick_now.not_(tick_now.mv('Testing')), tick_now.not_(tick_now.eq(tick_now.mv('Mode'), 7))))
    tick_now.set('QuestTicks', tick_now.data(MATH + 'Add_IntInt', A=tick_now.var('QuestTicks'), B=1))
    tick_now.manager('ReleasePlayActionCue', CueName=unreal.Name('tick'))
    f = merge(tick_now, quiet, no_tick)
    f = read_hand(f, 'Left')
    f = read_hand(f, 'Right')
    f.set('QuestHandsActive', f.or_(f.var('QuestLeftTracked'), f.var('QuestRightTracked')))
    # Which physical hands are tracked (the controller visuals and the drawn hands belong to physical hands).
    for physical, same, crossed in [('Left', 'QuestLeftTracked', 'QuestRightTracked'), ('Right', 'QuestRightTracked', 'QuestLeftTracked')]:
        f.set('QuestPhys' + physical + 'Tracked', f.or_(f.and_(f.var('QuestLeftHanded'), f.var(crossed)),
                                                        f.and_(f.not_(f.var('QuestLeftHanded')), f.var(same))))
    for side in ['Left', 'Right']:
        marker_name = 'Quest' + side + 'TipMarker'
        # The dot sits on the aim point (the index tip, latched as the pinch forms); while the pinch is held it sits where
        # the fingers meet and so follows the hand (seen in the demo frames: it stayed behind while the watch hand was turned).
        f.call(SC + 'K2_SetWorldLocation', **{'self': f.var(marker_name), 'NewLocation': f.data(MATH + 'SelectVector',
               A=f.var('Quest' + side + 'PinchPoint'), B=f.var('Quest' + side + 'AimPoint'), bPickA=f.var('Quest' + side + 'Pinch')),
               'bSweep': False, 'bTeleport': True})
        f.call(SC + 'SetWorldScale3D', **{'self': f.var(marker_name), 'NewScale': f.data(MATH + 'SelectVector',
               A=unreal.Vector(.022, .022, .022), B=unreal.Vector(.014, .014, .014), bPickA=f.var('Quest' + side + 'Pinch'))})
        f.call(SC + 'SetVisibility', **{'self': f.var(marker_name), 'bNewVisibility': f.var('Quest' + side + 'Tracked'),
               'bPropagateToChildren': False})
        # Tracked hands are shown by their fingertip markers only: the controller-hand proxy (and the wrist status text on the
        # left grip, which the HUD line replaces) is hidden while that hand is tracked. Found by playing through the simulator,
        # where the grip pose put a large proxy in front of the eye.
        f.call(SC + 'SetVisibility', **{'self': f.var(side + 'GripProxy'), 'bNewVisibility': f.not_(f.var('QuestPhys' + side + 'Tracked')),
               'bPropagateToChildren': False})
        # The articulated Epic hand mesh on the grip (the large brown hand seen in the simulator) belongs to controllers.
        f.call(SC + 'SetVisibility', **{'self': f.var('QuestHandVisual' + side), 'bNewVisibility': f.not_(f.var('QuestPhys' + side + 'Tracked')),
               'bPropagateToChildren': True})
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestStatusText'), 'bNewVisibility': f.not_(f.var('QuestPhysLeftTracked')),
           'bPropagateToChildren': False})
    # Debounce: after a dispatched pinch the same hand is ignored for QuestDebounceSeconds, so tracking jitter or a
    # double-tap can never fire one action twice. Swallowed presses are counted.
    for side, is_right in [('Right', True), ('Left', False)]:
        f.set('Quest' + side + 'Cool', f.data(MATH + 'FMax', A=0.0, B=f.data(MATH + 'Subtract_DoubleDouble',
              A=f.var('Quest' + side + 'Cool'), B=f.g.input('DeltaSeconds'))))
        pressed, idle = f.branch(f.var('Quest' + side + 'Pressed'))
        ready, swallowed = pressed.branch(pressed.data(MATH + 'LessEqual_DoubleDouble', A=pressed.var('Quest' + side + 'Cool'), B=0.0))
        swallowed.set('QuestDebounced', swallowed.data(MATH + 'Add_IntInt', A=swallowed.var('QuestDebounced'), B=1))
        if is_right:
            ready.set('QuestMainChosen', True)
            ready.own('QuestHandAct', Right=True)
            ready.set('QuestRightCool', ready.var('QuestDebounceSeconds'))
            f = merge(ready, swallowed, idle)
        else:
            # Main hand by itself: until a main-hand pinch has been made this session, a pinch of the other hand that is
            # aimed at one of the pawn's buttons means the player uses that hand. The hands change roles and the same
            # pinch acts as a main-hand press on the next frame (QuestAdoptHand).
            unchosen, chosen = ready.branch(ready.not_(ready.var('QuestMainChosen')))
            unchosen.set('QuestHandRayStart', location(unchosen, 'QuestCamera'))
            aim = unchosen.data(MATH + 'Normal', A=sub(unchosen, unchosen.var('QuestLeftAimPoint'), unchosen.var('QuestHandRayStart')), Tolerance=0.0001)
            unchosen.set('QuestHandRayEnd', add(unchosen, unchosen.var('QuestHandRayStart'), scale(unchosen, aim, 650)))
            unchosen.own('QuestUiPick')
            adopt, plain = unchosen.branch(unchosen.var('QuestUiHit'))
            leaf(adopt, 'adopt_main_hand').own('QuestAdoptHand')
            act = merge(chosen, plain)
            act.own('QuestHandAct', Right=False)
            act.set('QuestLeftCool', act.var('QuestDebounceSeconds'))
            f = merge(adopt, act, swallowed, idle)
    held, released = f.branch(f.var('QuestLeftPinch'))
    held.set('QuestLeftPinchHeld', held.data(MATH + 'Add_DoubleDouble', A=held.var('QuestLeftPinchHeld'), B=held.g.input('DeltaSeconds')))
    fire, waiting = held.branch(held.and_(held.data(MATH + 'GreaterEqual_DoubleDouble', A=held.var('QuestLeftPinchHeld'),
                                                    B=held.var('QuestMenuGestureSeconds')),
                                          held.not_(held.var('QuestMenuGestureFired'))))
    fire.set('QuestMenuGestureFired', True)
    fire.own('QuestMenuGesture')
    released.set('QuestLeftPinchHeld', 0.0)
    released.set('QuestMenuGestureFired', False)

    f = fn('QuestHandAct')
    right = f.g.input('Right')
    hand_point = f.data(MATH + 'SelectVector', A=f.var('QuestRightAimPoint'), B=f.var('QuestLeftAimPoint'), bPickA=right)
    # A gaze-dwell fire uses the head's forward axis as the pinch point instead of a hand.
    point = f.data(MATH + 'SelectVector', A=add(f, location(f, 'QuestCamera'), scale(f, f.data(SC + 'GetForwardVector',
                   **{'self': f.var('QuestCamera')}), 100)), B=hand_point, bPickA=f.var('QuestGazeFire'))
    f.set('QuestHandRayStart', location(f, 'QuestCamera'))
    direction = f.data(MATH + 'Normal', A=sub(f, point, f.var('QuestHandRayStart')), Tolerance=0.0001)
    f.set('QuestHandRayEnd', add(f, f.var('QuestHandRayStart'), scale(f, direction, 650)))
    # World ray (landing discs, scenery) ignores the pawn; the pawn's own buttons and rows are picked by component
    # traces and win when hit, so furniture or a wall between the eye and a button never swallows a pinch.
    trace = f.call(SYS + 'LineTraceSingle', Start=f.var('QuestHandRayStart'), End=f.var('QuestHandRayEnd'),
                   TraceChannel='TraceTypeQuery1', bTraceComplex=False, ActorsToIgnore=f.var('QuestIgnoredActors'),
                   DrawDebugType='None', bIgnoreSelf=True)
    br = f.call(GS + 'BreakHitResult', Hit=og.value_pin(trace, 'OutHit'))
    f.set('QuestHandRayHit', og.value_pin(trace, 'ReturnValue'))
    f.set('QuestHandHitActor', og.value_pin(br, 'HitActor'))
    f.set('QuestHandHitComponent', og.value_pin(br, 'HitComponent'))
    f.own('QuestUiPick')
    ui_hit, no_ui = f.branch(f.var('QuestUiHit'))
    ui_hit.set('QuestHandHitComponent', ui_hit.var('QuestUiHitComponent'))
    f = merge(ui_hit, no_ui)
    f.set('QuestLastHandAction', '')
    hit_actor = f.var('QuestHandHitActor')

    def back_or_left(flow):
        return flow.or_(flow.data(MATH + 'EqualEqual_ObjectObject', A=flow.var('QuestHandHitComponent'), B=flow.var('QuestBtnBack')),
                        flow.not_(right))

    menu, play = f.branch(f.mv('ReleaseMenuActive'))
    # In the menus and on the pause panel a left pinch is always Back, whatever it happens to point at.
    left_menu_back, menu = menu.branch(menu.not_(right))
    leaf(left_menu_back, 'menu_back').own('QuestMenuBack')
    up, menu = on_component(menu, 'QuestBtnUp')
    leaf(up, 'menu_up').manager('ReleaseStepSelection', Direction=-1)
    down, menu = on_component(menu, 'QuestBtnDown')
    leaf(down, 'menu_down').manager('ReleaseStepSelection', Direction=1)
    ok, menu = on_component(menu, 'QuestBtnOk')
    leaf(ok, 'menu_select').manager('ReleaseActivate')
    back, menu = menu.branch(back_or_left(menu))
    leaf(back, 'menu_back').own('QuestMenuBack')

    explore, rest = play.branch(play.eq(play.mv('Mode'), 0))
    # A gazed interactable (the manager's Target, whose prompt is on screen) always wins a right pinch: the HUD row
    # and the landing discs act only when nothing is targeted, so looking down at a seated character or a table
    # never opens the menu by accident.
    # Exception: a hand deliberately pointed at a HUD button (the pinch ray at least 6 degrees away from where the head
    # looks) acts on the button even while an object is gazed, so the Watch / Menu / Journal buttons stay reachable at
    # the anchor, the bench and the table. A pinch along the gaze still interacts with the gazed object.
    hud_hit = explore.data(MATH + 'EqualEqual_ObjectObject', A=explore.var('QuestHandHitComponent'), B=explore.var('QuestBtnTurnLeft'))
    for hud_name in ['QuestBtnWatch', 'QuestBtnMenu', 'QuestBtnJournal', 'QuestBtnTurnRight', 'QuestBtnCoachNext', 'QuestBtnCoachSkip', 'QuestWristTouch']:
        hud_hit = explore.or_(hud_hit, explore.data(MATH + 'EqualEqual_ObjectObject', A=explore.var('QuestHandHitComponent'), B=explore.var(hud_name)))
    off_gaze = explore.data(MATH + 'Less_DoubleDouble', A=explore.data(MATH + 'Dot_VectorVector', A=explore.data(SC + 'GetForwardVector',
                            **{'self': explore.var('QuestCamera')}), B=direction), B=0.9945)
    # A gaze-dwell fire is the gaze itself, so a HUD button it lands on always wins over the object behind it.
    targeted, explore = explore.branch(explore.and_(explore.valid(explore.mv('Target')),
                                                    explore.not_(explore.and_(hud_hit, explore.or_(off_gaze, explore.var('QuestGazeFire'))))))
    targeted_right, targeted_left = targeted.branch(right)
    leaf(targeted_right, 'interact').manager('Interact')
    targeted_right.own('QuestOnboardAdvance', FromStep=1)  # tutorial lesson: use something
    # Tutorial (shown once per session; Skip is always available while it shows).
    coach_skip, explore = on_component(explore, 'QuestBtnCoachSkip')
    leaf(coach_skip, 'coach_skip').set('QuestOnboardStep', 0)
    coach_skip.set('QuestOnboardDone', True)
    turn_left, explore = on_component(explore, 'QuestBtnTurnLeft')
    leaf(turn_left, 'turn_left').own('QuestSnap', Angle=-30)
    turn_left.own('QuestBlink')
    turn_right, explore = on_component(explore, 'QuestBtnTurnRight')
    leaf(turn_right, 'turn_right').own('QuestSnap', Angle=30)
    turn_right.own('QuestBlink')
    watch_btn, explore = on_component(explore, 'QuestBtnWatch')
    leaf(watch_btn, 'open_watch').manager('OpenWatch')
    # The watch on the wrist opens the same watch.
    wrist_watch, explore = on_component(explore, 'QuestWristTouch')
    leaf(wrist_watch, 'open_watch_wrist').manager('OpenWatch')
    journal_btn, explore = on_component(explore, 'QuestBtnJournal')
    leaf(journal_btn, 'open_journal').manager('OpenJournal')
    menu_btn, explore = on_component(explore, 'QuestBtnMenu')
    leaf(menu_btn, 'open_pause').manager('OpenPause')
    has_actor, no_actor = explore.branch(explore.valid(hit_actor))
    landing, other_actor = has_actor.branch(has_actor.tag(hit_actor, 'Quest.Teleport'))
    landing.set('QuestTeleportTarget', hit_actor)
    leaf(landing, 'teleport').own('QuestTeleportTo')
    landing.own('QuestBlink')
    explore = merge(other_actor, no_actor)
    interact, explore = explore.branch(right)
    leaf(interact, 'interact').manager('Interact')

    dialogue, rest = rest.branch(rest.eq(rest.mv('Mode'), 3))
    choosing, talking = dialogue.branch(dialogue.mv('DialogueWaitingChoice'))
    for i in range(1, 4):
        row, choosing = on_component(choosing, 'QuestChoice' + str(i))
        row.set('QuestChoiceIndex', i)
        leaf(row, 'choose_' + str(i)).manager('ChooseDialogue', ChoiceIndex=i)
    # The recollections are skipped by an off-hand pinch or, for a player using one hand, by a pinch on the Back button.
    skip, talking = talking.branch(talking.and_(talking.mv('IntroActive'), back_or_left(talking)))
    leaf(skip, 'skip_recollections').manager('SkipRecollections')
    advance, talking = talking.branch(right)
    leaf(advance, 'advance_dialogue').manager('AdvanceDialogue')

    photo_mode, rest = rest.branch(rest.eq(rest.mv('Mode'), 1))
    close_photo, flip = photo_mode.branch(back_or_left(photo_mode))
    leaf(close_photo, 'close_photo').manager('CloseModal')
    leaf(flip, 'flip_photo').manager('FlipPhoto')

    document, rest = rest.branch(rest.eq(rest.mv('Mode'), 2))
    leaf(document, 'close_document').manager('CloseDocument')

    watch_mode, rest = rest.branch(rest.eq(rest.mv('Mode'), 4))
    left_watch_close, watch_mode = watch_mode.branch(watch_mode.not_(right))
    leaf(left_watch_close, 'close_watch').manager('CloseModal')
    # The watch face: a pinch on it picks the era on that side at once (which is all a gaze-dwell fire does) and a hand
    # pinch also takes hold of the watch hand until the pinch opens (QuestDialFrame).
    dial_grab, watch_mode = on_component(watch_mode, 'QuestDial')
    leaf(dial_grab, 'dial_grab')
    grab_local = dial_grab.data(MATH + 'InverseTransformLocation', T=dial_grab.data(SC + 'K2_GetComponentToWorld', **{'self': dial_grab.var('QuestPanelRoot')}),
                                Location=dial_grab.var('QuestUiHitLocation'))
    gx, gy, gz = split_vec(dial_grab, grab_local)
    dial_grab.set('QuestDialAngle', dial_grab.data(MATH + 'FClamp', Value=dial_grab.data(MATH + 'DegAtan2',
                  Y=dial_grab.data(MATH + 'Subtract_DoubleDouble', A=gy, B=DIAL_Y), X=dial_grab.data(MATH + 'Subtract_DoubleDouble', A=gz, B=DIAL_Z)),
                  Min=-DIAL_MAX_DEG, Max=DIAL_MAX_DEG))
    dial_grab.own('QuestDialApply')
    by_hand, by_gaze = dial_grab.branch(dial_grab.not_(dial_grab.var('QuestGazeFire')))
    by_hand.set('QuestDialHeld', True)
    by_hand.set('QuestDialGrabPending', True)
    dial_left, watch_mode = on_component(watch_mode, 'QuestBtnUp')
    leaf(dial_left, 'dial_left').manager('RotateDial', Direction=-1)
    dial_right, watch_mode = on_component(watch_mode, 'QuestBtnDown')
    leaf(dial_right, 'dial_right').manager('RotateDial', Direction=1)
    confirm, watch_mode = on_component(watch_mode, 'QuestBtnOk')
    leaf(confirm, 'confirm_watch').manager('ConfirmWatch')
    close_watch, watch_mode = watch_mode.branch(back_or_left(watch_mode))
    leaf(close_watch, 'close_watch').manager('CloseModal')

    journal_mode, rest = rest.branch(rest.eq(rest.mv('Mode'), 5))
    left_journal_close, journal_mode = journal_mode.branch(journal_mode.not_(right))
    leaf(left_journal_close, 'close_journal').manager('CloseModal')
    page_back, journal_mode = on_component(journal_mode, 'QuestBtnUp')
    leaf(page_back, 'journal_previous').manager('TurnJournal', Direction=-1)
    page_next, journal_mode = on_component(journal_mode, 'QuestBtnDown')
    leaf(page_next, 'journal_next').manager('TurnJournal', Direction=1)
    close_journal, journal_mode = journal_mode.branch(back_or_left(journal_mode))
    leaf(close_journal, 'close_journal').manager('CloseModal')

    paused_mode, rest = rest.branch(rest.eq(rest.mv('Mode'), 6))
    left_resume, paused_mode = paused_mode.branch(paused_mode.not_(right))
    leaf(left_resume, 'pause_resume').manager('HandleOne')
    for i, handler in [(1, 'HandleOne'), (2, 'HandleTwo'), (3, 'HandleThree')]:
        row, paused_mode = on_component(paused_mode, 'QuestChoice' + str(i))
        row.set('QuestChoiceIndex', i)
        leaf(row, 'pause_row_' + str(i)).manager(handler)
    recenter_row, paused_mode = on_component(paused_mode, 'QuestChoice4')
    recenter_row.set('QuestChoiceIndex', 4)
    leaf(recenter_row, 'recenter').own('QuestSeatedCalibrate')
    recenter_row.manager('HandleOne')
    gaze_row, paused_mode = on_component(paused_mode, 'QuestChoice5')
    gaze_row.set('QuestChoiceIndex', 5)
    leaf(gaze_row, 'toggle_gaze').own('QuestToggleGaze')
    hand_row, paused_mode = on_component(paused_mode, 'QuestChoice6')
    hand_row.set('QuestChoiceIndex', 6)
    leaf(hand_row, 'toggle_main_hand').own('QuestToggleHand')
    large_row, paused_mode = on_component(paused_mode, 'QuestChoice7')
    large_row.set('QuestChoiceIndex', 7)
    leaf(large_row, 'toggle_large_text').own('QuestToggleLargeText')
    select_row, paused_mode = on_component(paused_mode, 'QuestBtnOk')
    leaf(select_row, 'pause_select').own('QuestPrimary')
    cycle_down, paused_mode = on_component(paused_mode, 'QuestBtnDown')
    leaf(cycle_down, 'pause_cycle').own('QuestCycleChoice')
    cycle_up, paused_mode = on_component(paused_mode, 'QuestBtnUp')
    leaf(cycle_up, 'pause_cycle').own('QuestCycleChoice')
    resume, paused_mode = paused_mode.branch(back_or_left(paused_mode))
    leaf(resume, 'pause_resume').manager('HandleOne')

    # The era that QuestDialAngle points at: beyond DIAL_SWITCH_DEG to the viewer's left the past (era 1), to the right the
    # present (era 0); in between nothing changes. The manager's own RotateDial does the selecting and redraws the watch.
    f = fn('QuestDialApply')
    to_past, f = f.branch(f.and_(f.data(MATH + 'Greater_DoubleDouble', A=f.var('QuestDialAngle'), B=DIAL_SWITCH_DEG),
                                 f.not_(f.eq(f.mv('SelectedEra'), 1))))
    to_past.manager('RotateDial', Direction=-1)
    to_now, f = f.branch(f.and_(f.data(MATH + 'Less_DoubleDouble', A=f.var('QuestDialAngle'), B=-DIAL_SWITCH_DEG),
                                f.not_(f.eq(f.mv('SelectedEra'), 0))))
    to_now.manager('RotateDial', Direction=1)
    for flow, label in [(to_past, 'dial_turn_past;'), (to_now, 'dial_turn_present;')]:
        flow.set('QuestDialTurns', flow.data(MATH + 'Add_IntInt', A=flow.var('QuestDialTurns'), B=1))
        flow.set('QuestActionLog', join_text(flow, flow.var('QuestActionLog'), label))

    # Watch hand, every frame the calibrated watch is open. Held (the main hand is still pinching after a pinch on the
    # face): the hand follows the eye-to-pinch ray around the dial centre, keeping the offset it was grabbed with.
    # Free: it settles on the mark of the selected era.
    f = fn('QuestDialFrame')
    f, not_ready = f.branch(f.valid(f.var('QuestManager')))
    shown, hidden = f.branch(f.var('QuestDialVisible'))
    hidden.set('QuestDialHeld', False)
    holding, free = shown.branch(shown.and_(shown.var('QuestDialHeld'), shown.and_(shown.var('QuestRightPinch'), shown.var('QuestRightTracked'))))
    eye = location(holding, 'QuestCamera')
    toward = holding.data(MATH + 'Normal', A=sub(holding, holding.var('QuestRightPinchPoint'), eye), Tolerance=0.0001)
    crossing = holding.call(MATH + 'LinePlaneIntersection_OriginNormal', LineStart=eye, LineEnd=add(holding, eye, scale(holding, toward, 650)),
                            PlaneOrigin=location(holding, 'QuestDialPivot'),
                            PlaneNormal=holding.data(SC + 'GetForwardVector', **{'self': holding.var('QuestPanelRoot')}))
    met, missed = holding.branch(og.value_pin(crossing, 'ReturnValue'))
    on_panel = met.data(MATH + 'InverseTransformLocation', T=met.data(SC + 'K2_GetComponentToWorld', **{'self': met.var('QuestPanelRoot')}),
                        Location=og.value_pin(crossing, 'Intersection'))
    px, py, pz = split_vec(met, on_panel)
    met.set('QuestDialRayAngle', met.data(MATH + 'DegAtan2', Y=met.data(MATH + 'Subtract_DoubleDouble', A=py, B=DIAL_Y),
                                          X=met.data(MATH + 'Subtract_DoubleDouble', A=pz, B=DIAL_Z)))
    first, later = met.branch(met.var('QuestDialGrabPending'))
    first.set('QuestDialGrabPending', False)
    first.set('QuestDialOffset', first.data(MATH + 'Subtract_DoubleDouble', A=first.var('QuestDialAngle'), B=first.var('QuestDialRayAngle')))
    met = merge(first, later)
    met.set('QuestDialAngle', met.data(MATH + 'FClamp', Value=met.data(MATH + 'Add_DoubleDouble', A=met.var('QuestDialRayAngle'), B=met.var('QuestDialOffset')),
                                       Min=-DIAL_MAX_DEG, Max=DIAL_MAX_DEG))
    met.own('QuestDialApply')
    # The held hand is heard as it turns: one tick each time it passes DIAL_TICK_DEG.
    tick_step = met.data(MATH + 'FFloor', A=met.data(MATH + 'Divide_DoubleDouble', A=met.var('QuestDialAngle'), B=DIAL_TICK_DEG))
    stepped, steady = met.branch(met.not_(met.eq(tick_step, met.var('QuestDialTickStep'))))
    stepped.set('QuestDialTickStep', tick_step)
    stepped.set('QuestTickPending', True)
    met = merge(stepped, steady)
    free.set('QuestDialHeld', False)
    free.set('QuestDialAngle', free.data(MATH + 'FInterpTo', Current=free.var('QuestDialAngle'),
             Target=free.data(MATH + 'SelectFloat', A=DIAL_MARK_DEG, B=-DIAL_MARK_DEG, bPickA=free.eq(free.mv('SelectedEra'), 1)),
             DeltaTime=free.g.input('DeltaSeconds'), InterpSpeed=12.0))
    shown = merge(met, missed, free)
    shown.call(SC + 'K2_SetRelativeRotation', **{'self': shown.var('QuestDialPivot'),
               'NewRotation': shown.data(MATH + 'MakeRotator', Roll=shown.var('QuestDialAngle'), Pitch=0, Yaw=0), 'bSweep': False, 'bTeleport': True})
    # The seconds hand in the subdial: once round in sixty seconds, clockwise as the player sees it, while the watch is open.
    shown.set('QuestDialSecondsAngle', shown.data(MATH + 'NormalizeAxis', Angle=shown.data(MATH + 'Subtract_DoubleDouble',
              A=shown.var('QuestDialSecondsAngle'), B=shown.data(MATH + 'Multiply_DoubleDouble', A=shown.g.input('DeltaSeconds'), B=6.0))))
    shown.call(SC + 'K2_SetRelativeRotation', **{'self': shown.var('QuestDialSecondsPivot'),
               'NewRotation': shown.data(MATH + 'MakeRotator', Roll=shown.var('QuestDialSecondsAngle'), Pitch=0, Yaw=0), 'bSweep': False, 'bTeleport': True})

    # Watch on the wrist of the off hand (the physical left, or the right for a left-handed player), once the watch is
    # calibrated and while that hand is drawn. It is placed from joint positions alone (wrist, middle, index and little
    # knuckles), so it does not depend on how a runtime orients the wrist joint.
    f = fn('QuestWristFrame')
    f, not_ready = f.branch(f.valid(f.var('QuestManager')))
    left_handed = f.var('QuestLeftHanded')
    hand_drawn = f.or_(f.and_(left_handed, f.var('QuestHandShownRight')), f.and_(f.not_(left_handed), f.var('QuestHandShownLeft')))
    wanted = f.and_(hand_drawn, f.and_(f.mv('WatchCalibrated'), f.not_(f.mv('ReleaseMenuActive'))))
    changed, same = f.branch(f.data(MATH + 'NotEqual_BoolBool', A=wanted, B=f.var('QuestWristShown')))
    changed.set('QuestWristShown', changed.not_(changed.var('QuestWristShown')))
    for part_name in WRIST_PARTS:
        changed.call(SC + 'SetVisibility', **{'self': changed.var(part_name), 'bNewVisibility': changed.var('QuestWristShown'),
                     'bPropagateToChildren': False})
    f = merge(changed, same)
    # It can be pinched only in exploration (where the Watch button is): never over a panel.
    usable, unusable = f.branch(f.and_(f.var('QuestWristShown'), f.eq(f.mv('Mode'), 0)))
    usable.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': usable.var('QuestWristTouch'), 'NewType': 'QueryOnly'})
    unusable.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': unusable.var('QuestWristTouch'), 'NewType': 'NoCollision'})
    f = merge(usable, unusable)
    draw, skip = f.branch(f.var('QuestWristShown'))

    def off_joint(name):
        return draw.data(MATH + 'SelectVector', A=location(draw, 'Right' + name), B=location(draw, 'Left' + name), bPickA=left_handed)
    wrist = off_joint('Wrist')
    along = draw.data(MATH + 'Normal', A=sub(draw, off_joint('MiddleProximal'), wrist), Tolerance=0.0001)
    across = sub(draw, off_joint('IndexProximal'), off_joint('LittleProximal'))   # toward the thumb side
    # Out of the back of the hand: along x across on a left hand, the opposite on a right hand.
    outward = draw.data(MATH + 'Normal', A=scale(draw, draw.data(MATH + 'Cross_VectorVector', A=along, B=across),
                        draw.data(MATH + 'SelectFloat', A=-1.0, B=1.0, bPickA=left_handed)), Tolerance=0.0001)
    origin = add(draw, add(draw, wrist, scale(draw, along, -WRIST_BACK_CM)), scale(draw, outward, WRIST_RISE_CM))
    draw.call(SC + 'K2_SetWorldLocationAndRotation', **{'self': draw.var('QuestWristRoot'), 'NewLocation': origin,
              'NewRotation': draw.data(MATH + 'MakeRotFromXZ', X=scale(draw, across, -1.0), Z=scale(draw, outward, -1.0)),
              'bSweep': False, 'bTeleport': True})
    # The small hand: with the panel open it is the big hand's twin; otherwise it rests on the era the player is in.
    era_angle = draw.data(MATH + 'SelectFloat', A=DIAL_MARK_DEG, B=-DIAL_MARK_DEG, bPickA=draw.eq(draw.mv('EraIndex'), 1))
    draw.call(SC + 'K2_SetRelativeRotation', **{'self': draw.var('QuestWristPivot'), 'NewRotation': draw.data(MATH + 'MakeRotator', Roll=0, Pitch=0,
              Yaw=draw.data(MATH + 'SelectFloat', A=draw.var('QuestDialAngle'), B=era_angle, bPickA=draw.var('QuestDialVisible'))),
              'bSweep': False, 'bTeleport': True})
    draw.set('QuestWristSecondsAngle', draw.data(MATH + 'NormalizeAxis', Angle=draw.data(MATH + 'Subtract_DoubleDouble',
             A=draw.var('QuestWristSecondsAngle'), B=draw.data(MATH + 'Multiply_DoubleDouble', A=draw.g.input('DeltaSeconds'), B=6.0))))
    draw.call(SC + 'K2_SetRelativeRotation', **{'self': draw.var('QuestWristSecondsPivot'), 'NewRotation': draw.data(MATH + 'MakeRotator', Roll=0, Pitch=0,
              Yaw=draw.var('QuestWristSecondsAngle')), 'bSweep': False, 'bTeleport': True})

    # Drawn hands: each tracked physical hand is 15 stretched spheres along its finger bones and one flattened sphere for
    # the palm, placed from the keypoint components. Nothing is drawn (and nothing computed) for a hand that is not tracked.
    f = fn('QuestHandDraw')
    for side in ['Left', 'Right']:
        shown_name = 'QuestHandShown' + side
        show = f.and_(f.var('QuestPhys' + side + 'Tracked'), f.or_(f.not_(f.var('QuestSimHands')), f.var('QuestSimJoints')))
        changed, same = f.branch(f.data(MATH + 'NotEqual_BoolBool', A=show, B=f.var(shown_name)))
        changed.set(shown_name, changed.not_(changed.var(shown_name)))
        for part_name in HAND_PARTS:
            changed.call(SC + 'SetVisibility', **{'self': changed.var('QuestHand' + side + part_name), 'bNewVisibility': changed.var(shown_name),
                         'bPropagateToChildren': False})
        f = merge(changed, same)
        draw, skip = f.branch(f.var(shown_name))
        for part_name, joint_a, joint_b, thick in HAND_SEGMENTS:
            a = location(draw, side + joint_a)
            b = location(draw, side + joint_b)
            bone = sub(draw, b, a)
            size = draw.data(MATH + 'MakeVector', X=thick / 100.0, Y=thick / 100.0, Z=draw.data(MATH + 'Divide_DoubleDouble',
                             A=draw.data(MATH + 'Add_DoubleDouble', A=draw.data(MATH + 'VSize', A=bone), B=thick * 0.7), B=100.0))
            draw.call(SC + 'K2_SetWorldTransform', **{'self': draw.var('QuestHand' + side + part_name),
                      'NewTransform': draw.data(MATH + 'MakeTransform', Location=scale(draw, add(draw, a, b), 0.5),
                                                Rotation=draw.data(MATH + 'MakeRotFromZ', Z=bone), Scale=size),
                      'bSweep': False, 'bTeleport': True})
        wrist = location(draw, side + 'Wrist')
        knuckle = location(draw, side + 'MiddleProximal')
        along = sub(draw, knuckle, wrist)
        across = sub(draw, location(draw, side + 'IndexProximal'), location(draw, side + 'LittleProximal'))
        palm_size = draw.data(MATH + 'MakeVector',
                              X=draw.data(MATH + 'Divide_DoubleDouble', A=draw.data(MATH + 'Add_DoubleDouble', A=draw.data(MATH + 'VSize', A=across), B=1.4), B=100.0),
                              Y=0.022,
                              Z=draw.data(MATH + 'Divide_DoubleDouble', A=draw.data(MATH + 'Add_DoubleDouble', A=draw.data(MATH + 'VSize', A=along), B=0.6), B=100.0))
        draw.call(SC + 'K2_SetWorldTransform', **{'self': draw.var('QuestHand' + side + 'Palm'),
                  'NewTransform': draw.data(MATH + 'MakeTransform', Location=scale(draw, add(draw, wrist, knuckle), 0.5),
                                            Rotation=draw.data(MATH + 'MakeRotFromZX', Z=along, X=across), Scale=palm_size),
                  'bSweep': False, 'bTeleport': True})
        f = merge(draw, skip)

    # Pick the nearest of the pawn's own enabled UI components along QuestHandRayStart..End by component traces.
    f = fn('QuestUiPick')
    f.set('QuestUiHit', False)
    f.set('QuestUiHitDistance', 100000.0)
    for name in UI_NAMES:
        enabled, disabled = f.branch(f.data(MATH + 'NotEqual_ByteByte', A=f.data('/Script/Engine.PrimitiveComponent.GetCollisionEnabled', **{'self': f.var(name)}), B=0))
        probe = enabled.call('/Script/Engine.PrimitiveComponent.K2_LineTraceComponent', **{'self': enabled.var(name),
                             'TraceStart': enabled.var('QuestHandRayStart'), 'TraceEnd': enabled.var('QuestHandRayEnd'),
                             'bTraceComplex': False, 'bShowTrace': False, 'bPersistentShowTrace': False})
        hit, miss = enabled.branch(og.value_pin(probe, 'ReturnValue'))
        gap = hit.data(MATH + 'Vector_Distance', V1=hit.var('QuestHandRayStart'), V2=og.value_pin(probe, 'HitLocation'))
        closer, farther = hit.branch(hit.data(MATH + 'Less_DoubleDouble', A=gap, B=hit.var('QuestUiHitDistance')))
        closer.set('QuestUiHitDistance', gap)
        closer.set('QuestUiHitLocation', og.value_pin(probe, 'HitLocation'))
        closer.set('QuestUiHitComponent', closer.var(name))
        closer.set('QuestUiHit', True)
        f = merge(closer, farther, miss, disabled)
    # Forgiving targets: with no direct hit, snap to the nearest enabled UI component whose collision lies within
    # SNAP_RADIUS_CM of the ray (a near miss on a small button or a thin row still counts).
    f.set('QuestUiSnapBest', SNAP_RADIUS_CM)
    for name in UI_NAMES:
        if name == 'QuestWristTouch':
            continue  # the watch on the wrist takes direct hits only
        usable, skip = f.branch(f.and_(f.not_(f.var('QuestUiHit')),
                                       f.data(MATH + 'NotEqual_ByteByte', A=f.data('/Script/Engine.PrimitiveComponent.GetCollisionEnabled', **{'self': f.var(name)}), B=0)))
        nearest = usable.data(MATH + 'FindClosestPointOnSegment', Point=location(usable, name), SegmentStart=usable.var('QuestHandRayStart'),
                              SegmentEnd=usable.var('QuestHandRayEnd'))
        probe = usable.call('/Script/Engine.PrimitiveComponent.GetClosestPointOnCollision', **{'self': usable.var(name), 'Point': nearest})
        distance = og.value_pin(probe, 'ReturnValue')
        better, worse = usable.branch(usable.and_(usable.data(MATH + 'GreaterEqual_DoubleDouble', A=distance, B=0.0),
                                                 usable.data(MATH + 'Less_DoubleDouble', A=distance, B=usable.var('QuestUiSnapBest'))))
        better.set('QuestUiSnapBest', distance)
        better.set('QuestUiSnapComponent', better.var(name))
        better.set('QuestUiSnapPoint', og.value_pin(probe, 'OutPointOnBody'))
        f = merge(better, worse, skip)
    snapped, direct = f.branch(f.and_(f.not_(f.var('QuestUiHit')), f.data(MATH + 'Less_DoubleDouble', A=f.var('QuestUiSnapBest'), B=SNAP_RADIUS_CM)))
    snapped.set('QuestUiHit', True)
    snapped.set('QuestUiHitComponent', snapped.var('QuestUiSnapComponent'))
    snapped.set('QuestUiHitLocation', snapped.var('QuestUiSnapPoint'))

    f = fn('QuestMenuGesture')
    menu, play = f.branch(f.mv('ReleaseMenuActive'))
    explore, rest = play.branch(play.eq(play.mv('Mode'), 0))
    leaf(explore, 'gesture_pause').manager('OpenPause')
    paused_mode, rest = rest.branch(rest.eq(rest.mv('Mode'), 6))
    leaf(paused_mode, 'gesture_resume').manager('HandleOne')

    f = fn('QuestSeatedCalibrate')
    f.set('QuestSeatedCalibrations', f.data(MATH + 'Add_IntInt', A=f.var('QuestSeatedCalibrations'), B=1))
    active, no = f.branch(f.var('QuestXRActive'))
    active.call(HMD + 'SetTrackingOrigin', Origin='Local')
    active.call(HMD + 'ResetOrientationAndPosition', Yaw=0.0)
    active.call(SC + 'K2_SetRelativeLocation', **{'self': active.var('VROrigin'), 'NewLocation': unreal.Vector(0, 0, SEATED_EYE_CM - 88),
                'bSweep': False, 'bTeleport': True})
    active.call(SC + 'K2_SetRelativeLocation', **{'self': active.var('QuestCamera'), 'NewLocation': unreal.Vector(0, 0, 0),
                'bSweep': False, 'bTeleport': True})

    f = fn('QuestBlink')
    f.call(CAM + 'StartCameraFade', **{'self': f.data(GS + 'GetPlayerCameraManager', PlayerIndex=0), 'FromAlpha': 1.0, 'ToAlpha': 0.0,
           'Duration': 0.25, 'Color': f.data(MATH + 'MakeColor', R=0.0, G=0.0, B=0.0, A=1.0), 'bShouldFadeAudio': False,
           'bHoldWhenFinished': False})
    f.set('QuestBlinks', f.data(MATH + 'Add_IntInt', A=f.var('QuestBlinks'), B=1))

    f = fn('QuestHudFrame')
    shown = f.and_(f.and_(f.eq(f.mv('Mode'), 0), f.not_(f.mv('ReleaseMenuActive'))),
                   f.or_(f.or_(f.var('QuestXRActive'), f.var('QuestComfortSimulation')), f.var('QuestSimHands')))
    f.set('QuestHudVisible', shown)
    eye = location(f, 'QuestCamera')
    br = f.call(MATH + 'BreakRotator', InRot=rotation(f, 'QuestCamera'))
    flat = f.data(MATH + 'MakeRotator', Roll=0, Pitch=0, Yaw=og.value_pin(br, 'Yaw'))
    f.set('QuestHudTarget', add(f, add(f, eye, scale(f, f.data(MATH + 'GetForwardVector', InRot=flat), 150)), unreal.Vector(0, 0, -48)))
    # Line-of-sight clearance for the row: pulled in to 10 cm before whatever blocks the eye-to-row line, never nearer than 60 cm.
    probe = f.call(SYS + 'LineTraceSingle', Start=eye, End=f.var('QuestHudTarget'), TraceChannel='TraceTypeQuery1', bTraceComplex=False,
                   ActorsToIgnore=f.var('QuestIgnoredActors'), DrawDebugType='None', bIgnoreSelf=True)
    blocked, clear = f.branch(og.value_pin(probe, 'ReturnValue'))
    probe_hit = blocked.call(GS + 'BreakHitResult', Hit=og.value_pin(probe, 'OutHit'))
    reach = blocked.data(MATH + 'FMax', A=60.0, B=blocked.data(MATH + 'Subtract_DoubleDouble',
                         A=blocked.data(MATH + 'Vector_Distance', V1=eye, V2=og.value_pin(probe_hit, 'ImpactPoint')), B=10.0))
    blocked.set('QuestHudTarget', add(blocked, eye, scale(blocked, blocked.data(MATH + 'Normal', A=sub(blocked, blocked.var('QuestHudTarget'), eye), Tolerance=0.0001), reach)))
    f = merge(blocked, clear)
    # Angle between where the head looks and where the row currently sits (the row's own rotation faces back at the eye,
    # so it cannot be compared with the head yaw directly).
    row_bearing = f.data(MATH + 'FindLookAtRotation', Start=eye, Target=location(f, 'QuestHudRoot'))
    delta = f.call(MATH + 'BreakRotator', InRot=f.data(MATH + 'NormalizedDeltaRotator', A=flat, B=row_bearing))
    turned = f.data(MATH + 'Greater_DoubleDouble', A=f.data(MATH + 'Abs', A=og.value_pin(delta, 'Yaw')), B=30.0)
    far = f.data(MATH + 'Greater_DoubleDouble', A=f.data(MATH + 'Vector_Distance', V1=f.var('QuestHudTarget'), V2=location(f, 'QuestHudRoot')), B=60.0)
    move, stay = f.branch(f.or_(f.or_(turned, far), f.var('QuestHudDirty')))
    move.set('QuestHudDirty', False)
    look = move.data(MATH + 'FindLookAtRotation', Start=move.var('QuestHudTarget'), Target=location(move, 'QuestCamera'))
    move.call(SC + 'K2_SetWorldLocationAndRotation', **{'self': move.var('QuestHudRoot'), 'NewLocation': move.var('QuestHudTarget'),
              'NewRotation': look, 'bSweep': False, 'bTeleport': True})
    hud_scale = move.data(MATH + 'Multiply_DoubleDouble', A=move.var('QuestUiZoom'), B=move.data(MATH + 'FClamp', Value=move.data(MATH + 'Divide_DoubleDouble',
                          A=move.data(MATH + 'Vector_Distance', V1=move.var('QuestHudTarget'), V2=eye), B=150.0), Min=0.4, Max=1.0))
    move.call(SC + 'SetWorldScale3D', **{'self': move.var('QuestHudRoot'), 'NewScale': move.data(MATH + 'MakeVector', X=hud_scale, Y=hud_scale, Z=hud_scale)})
    move.set('QuestHudPlacements', move.data(MATH + 'Add_IntInt', A=move.var('QuestHudPlacements'), B=1))
    f = merge(move, stay)
    f.call(SC + 'SetVisibility', **{'self': f.var('QuestHudRoot'), 'bNewVisibility': f.var('QuestHudVisible'), 'bPropagateToChildren': True})
    on, off = f.branch(f.var('QuestHudVisible'))
    for name in ['QuestBtnTurnLeft', 'QuestBtnWatch', 'QuestBtnMenu', 'QuestBtnJournal', 'QuestBtnTurnRight']:
        on.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': on.var(name), 'NewType': 'QueryOnly'})
        off.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': off.var(name), 'NewType': 'NoCollision'})
    f = merge(on, off)
    # Tutorial (13 November 2026): while it shows, the plate carries the lessons still to do above the hint line, and the
    # Skip button is under the row. The old Next button is never shown (its component stays, without collision).
    coach = f.and_(f.var('QuestHudVisible'), f.eq(f.var('QuestOnboardStep'), 1))
    coach_next = f.and_(coach, f.not_(coach))
    for coach_name, coach_visible in [('QuestBtnCoachNext', coach_next), ('QuestBtnCoachSkip', coach)]:
        f.call(SC + 'SetVisibility', **{'self': f.var(coach_name), 'bNewVisibility': coach_visible, 'bPropagateToChildren': False})
        f.call(SC + 'SetVisibility', **{'self': f.var(coach_name + 'Text'), 'bNewVisibility': coach_visible, 'bPropagateToChildren': False})
        c_on, c_off = f.branch(coach_visible)
        c_on.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': c_on.var(coach_name), 'NewType': 'QueryOnly'})
        c_off.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled', **{'self': c_off.var(coach_name), 'NewType': 'NoCollision'})
        f = merge(c_on, c_off)
    coaching, normal = f.branch(coach)
    # A lesson's line is there until the lesson is done. The hint line follows, except the idle hint, which says what the
    # first lesson says. The story objective returns when the tutorial ends.
    lesson_use = coaching.data(MATH + 'SelectString', A='', B=TUTORIAL_USE + '\n', bPickA=coaching.var('QuestOnboardUsed'))
    lesson_move = coaching.data(MATH + 'SelectString', A='', B=TUTORIAL_MOVE + '\n', bPickA=coaching.var('QuestOnboardMoved'))
    hint_line = coaching.data(MATH + 'SelectString', A='', B=coaching.var('QuestHintText'),
                              bPickA=coaching.data(STR + 'EqualEqual_StrStr', A=coaching.var('QuestHintText'), B=IDLE_HINT))
    set_text(coaching, 'QuestHudStatusText', wrapped(coaching, join_text(coaching, join_text(coaching, lesson_use, lesson_move), hint_line), 'Hud', HUD_WRAP), hands=True)
    set_text(normal, 'QuestHudStatusText', wrapped(normal, join_text(normal, join_text(normal, normal.var('QuestHintText'), '\n'), normal.mv('Objective')), 'Hud', HUD_WRAP), hands=True)
    f = merge(coaching, normal)

    # Gaze dwell: optional look-to-select for a player whose pinch is not detected. Arms from the pause row or by itself
    # after AUTO_GAZE_SECONDS in the XR session with no tracked hand and no tracked controller.
    f = fn('QuestDwellFrame')
    xr = f.or_(f.or_(f.var('QuestXRActive'), f.var('QuestComfortSimulation')), f.var('QuestSimHands'))
    idle_now = f.and_(xr, f.and_(f.not_(f.var('QuestHandsActive')), f.and_(f.not_(f.data(MC + 'IsTracked', **{'self': f.var('RightAim')})),
                                                                           f.not_(f.data(MC + 'IsTracked', **{'self': f.var('LeftAim')})))))
    waiting, active_input = f.branch(idle_now)
    waiting.set('QuestNoInputTime', waiting.data(MATH + 'Add_DoubleDouble', A=waiting.var('QuestNoInputTime'), B=waiting.g.input('DeltaSeconds')))
    arm, still = waiting.branch(waiting.and_(waiting.and_(waiting.data(MATH + 'GreaterEqual_DoubleDouble', A=waiting.var('QuestNoInputTime'), B=AUTO_GAZE_SECONDS),
                                                         waiting.not_(waiting.var('QuestGazeSelect'))), waiting.var('QuestAutoGazeEnabled')))
    arm.set('QuestGazeSelect', True)
    arm.set('QuestAutoGaze', True)
    active_input.set('QuestNoInputTime', 0.0)
    f = merge(arm, still, active_input)
    on, off = f.branch(f.and_(f.var('QuestGazeSelect'), f.and_(xr, f.not_(f.eq(f.mv('Mode'), 7)))))
    # What the head is looking at: a pawn UI component (by index), the gazed Target in exploration, or nothing (a plain
    # advance in the dialogue, photograph and letter modes).
    on.set('QuestHandRayStart', location(on, 'QuestCamera'))
    on.set('QuestHandRayEnd', add(on, location(on, 'QuestCamera'), scale(on, on.data(SC + 'GetForwardVector', **{'self': on.var('QuestCamera')}), 650)))
    on.own('QuestUiPick')
    on.set('QuestDwellId', 0)
    ui, none = on.branch(on.var('QuestUiHit'))
    matched = []
    for index, name in enumerate(UI_NAMES):
        found, ui = ui.branch(ui.data(MATH + 'EqualEqual_ObjectObject', A=ui.var('QuestUiHitComponent'), B=ui.var(name)))
        found.set('QuestDwellId', index + 1)
        matched.append(found)
    tgt, plain = none.branch(none.and_(none.eq(none.mv('Mode'), 0), none.valid(none.mv('Target'))))
    tgt.set('QuestDwellId', 100)
    generic, nothing = plain.branch(plain.or_(plain.or_(plain.eq(plain.mv('Mode'), 1), plain.eq(plain.mv('Mode'), 2)),
                                              plain.and_(plain.eq(plain.mv('Mode'), 3), plain.not_(plain.mv('DialogueWaitingChoice')))))
    generic.set('QuestDwellId', 200)
    on = merge(*matched, ui, tgt, generic, nothing)
    # Same subject as last frame and not just fired: accumulate; otherwise restart (and re-arm after looking away).
    same, changed = on.branch(on.and_(on.eq(on.var('QuestDwellId'), on.var('QuestDwellSubject')), on.not_(on.eq(on.var('QuestDwellId'), 0))))
    same.set('QuestDwellTime', same.data(MATH + 'Add_DoubleDouble', A=same.var('QuestDwellTime'), B=same.g.input('DeltaSeconds')))
    changed.set('QuestDwellSubject', changed.var('QuestDwellId'))
    changed.set('QuestDwellTime', 0.0)
    rearm, held_off = changed.branch(changed.not_(changed.eq(changed.var('QuestDwellId'), changed.var('QuestDwellFiredId'))))
    rearm.set('QuestDwellFiredId', -1)
    on = merge(same, rearm, held_off)
    needed = on.data(MATH + 'SelectFloat', A=GENERIC_DWELL_SECONDS, B=on.var('QuestDwellSeconds'), bPickA=on.eq(on.var('QuestDwellId'), 200))
    fire, wait = on.branch(on.and_(on.data(MATH + 'GreaterEqual_DoubleDouble', A=on.var('QuestDwellTime'), B=needed),
                                   on.not_(on.eq(on.var('QuestDwellId'), on.var('QuestDwellFiredId')))))
    fire.set('QuestGazeFire', True)
    fire.own('QuestHandAct', Right=True)
    fire.set('QuestGazeFire', False)
    fire.set('QuestGazeFires', fire.data(MATH + 'Add_IntInt', A=fire.var('QuestGazeFires'), B=1))
    fire.set('QuestDwellTime', 0.0)
    # A plain advance (id 200) repeats every GENERIC_DWELL_SECONDS; everything else needs a look away before it re-arms.
    once, repeat = fire.branch(fire.not_(fire.eq(fire.var('QuestDwellId'), 200)))
    once.set('QuestDwellFiredId', once.var('QuestDwellId'))
    fire = merge(once, repeat)
    on = merge(fire, wait)
    # Progress dot, 110 cm ahead of the eye: grows from 1 to 3 cm as the dwell completes.
    progress = on.data(MATH + 'FClamp', Value=on.data(MATH + 'Divide_DoubleDouble', A=on.var('QuestDwellTime'), B=needed), Min=0.0, Max=1.0)
    size = on.data(MATH + 'Add_DoubleDouble', A=0.01, B=on.data(MATH + 'Multiply_DoubleDouble', A=0.02, B=progress))
    on.call(SC + 'K2_SetWorldLocation', **{'self': on.var('QuestGazeDot'), 'NewLocation': add(on, location(on, 'QuestCamera'), scale(on,
            on.data(SC + 'GetForwardVector', **{'self': on.var('QuestCamera')}), 110)), 'bSweep': False, 'bTeleport': True})
    on.call(SC + 'SetWorldScale3D', **{'self': on.var('QuestGazeDot'), 'NewScale': on.data(MATH + 'MakeVector', X=size, Y=size, Z=size)})
    on.call(SC + 'SetVisibility', **{'self': on.var('QuestGazeDot'), 'bNewVisibility': True, 'bPropagateToChildren': False})
    off.call(SC + 'SetVisibility', **{'self': off.var('QuestGazeDot'), 'bNewVisibility': False, 'bPropagateToChildren': False})

    # Telemetry: one log line every 2 s (and the hand actions since the last line) so a simulator or device run can be
    # audited from the game log. PrintString is compiled out of Shipping, so the entry build carries no log traffic.
    f = fn('QuestTelemetry')
    dt = f.g.input('DeltaSeconds')
    f.set('QuestFps', f.data(MATH + 'Add_DoubleDouble', A=f.data(MATH + 'Multiply_DoubleDouble', A=f.var('QuestFps'), B=0.9),
          B=f.data(MATH + 'Multiply_DoubleDouble', A=0.1, B=f.data(MATH + 'Divide_DoubleDouble', A=1.0, B=f.data(MATH + 'FMax', A=dt, B=0.0001)))))
    f.set('QuestTelemetryTime', f.data(MATH + 'Add_DoubleDouble', A=f.var('QuestTelemetryTime'), B=dt))
    emit, skip = f.branch(f.data(MATH + 'GreaterEqual_DoubleDouble', A=f.var('QuestTelemetryTime'), B=2.0))
    emit.set('QuestTelemetryTime', 0.0)

    def flag(flow, name):
        return flow.data(STR + 'Conv_BoolToString', InBool=flow.var(name))

    line = 'QUESTXR hmd='
    line = join_text(emit, line, flag(emit, 'QuestXRActive'))
    for label, name in [(' rightHand=', 'QuestRightTracked'), (' leftHand=', 'QuestLeftTracked'), (' rightPinch=', 'QuestRightPinch'),
                        (' leftPinch=', 'QuestLeftPinch'), (' gaze=', 'QuestGazeSelect'), (' coach=', None)]:
        if name:
            line = join_text(emit, join_text(emit, line, label), flag(emit, name))
        else:
            line = join_text(emit, join_text(emit, line, label), emit.data(STR + 'Conv_IntToString', InInt=emit.var('QuestOnboardStep')))
    line = join_text(emit, join_text(emit, line, ' mode='), emit.data(STR + 'Conv_IntToString', InInt=emit.mv('Mode')))
    line = join_text(emit, join_text(emit, line, ' fps='), emit.data(STR + 'Conv_IntToString', InInt=emit.data(MATH + 'FFloor', A=emit.var('QuestFps'))))
    line = join_text(emit, join_text(emit, line, ' debounced='), emit.data(STR + 'Conv_IntToString', InInt=emit.var('QuestDebounced')))
    line = join_text(emit, join_text(emit, line, ' hint='), emit.var('QuestHintText'))
    line = join_text(emit, join_text(emit, line, ' actions='), emit.var('QuestActionLog'))
    emit.call(SYS + 'PrintString', InString=line, bPrintToScreen=False, bPrintToLog=True)
    emit.set('QuestActionLog', '')
    # Second line (12 November 2026, later): the drawn hands and the access options. palm is the wrist-to-middle-knuckle
    # distance in millimetres read from the keypoint components, so a run with real joint data shows a hand-sized figure.
    hands_line = 'QUESTXR hands'
    for label, name in [(' drawnLeft=', 'QuestHandShownLeft'), (' drawnRight=', 'QuestHandShownRight'), (' leftHanded=', 'QuestLeftHanded'),
                        (' largeText=', 'QuestLargeText'), (' dial=', 'QuestDialVisible'), (' dialHeld=', 'QuestDialHeld')]:
        hands_line = join_text(emit, join_text(emit, hands_line, label), flag(emit, name))
    for side in ['Left', 'Right']:
        palm_mm = emit.data(MATH + 'FFloor', A=emit.data(MATH + 'Multiply_DoubleDouble', A=10.0,
                            B=emit.data(MATH + 'Vector_Distance', V1=location(emit, side + 'Wrist'), V2=location(emit, side + 'MiddleProximal'))))
        hands_line = join_text(emit, join_text(emit, hands_line, ' palm' + side + 'Mm='), emit.data(STR + 'Conv_IntToString', InInt=palm_mm))
    hands_line = join_text(emit, join_text(emit, hands_line, ' dialTurns='), emit.data(STR + 'Conv_IntToString', InInt=emit.var('QuestDialTurns')))
    emit.call(SYS + 'PrintString', InString=hands_line, bPrintToScreen=False, bPrintToLog=True)

    ev = og.events(bp)
    hands_hooks = [n for n in ev.editor.list_all_nodes()
                   if str(og.L.get_node_title(n)).replace(' ', '').lower().startswith(('questhandsbegin', 'questhandsframe'))]
    ev.editor.remove_nodes(ev.editor.list_all_nodes())
    begin = og.L.add_event_override(bp, 'ReceiveBeginPlay', unreal.IntPoint(0, 0))
    node = ev.call(CHAR_CLASS + ':QuestBegin')
    og.chain(begin, node)
    tick = og.L.add_event_override(bp, 'ReceiveTick', unreal.IntPoint(0, 300))
    node = ev.call(CHAR_CLASS + ':QuestFrame')
    og.link(og.pin_out(tick), og.pin_in(node))
    og.link(og.value_pin(tick, 'DeltaSeconds'), og.pin_in(node, 'DeltaSeconds'))
    cdo = unreal.get_default_object(og.L.generated_class(bp))
    tags = list(cdo.get_editor_property('tags'))
    if unreal.Name('Quest.XRPlayer') not in tags:
        tags.append(unreal.Name('Quest.XRPlayer'))
    cdo.set_editor_property('tags', tags)
    return bp, bool(hands_hooks)


def reattach_hands(bp):
    """Re-link the articulated hand hooks (QuestHandsBegin / QuestHandsFrame) after the core events were rebuilt."""
    if not og.L.find_graph(bp, 'QuestHandsBegin') or not og.L.find_graph(bp, 'QuestHandsFrame'):
        return False
    graph = og.events(bp)
    ed = graph.editor
    def title(node):
        return str(og.L.get_node_title(node)).replace(' ', '').replace('_', '').lower()
    for original, addition, event in [('questbegin', 'QuestHandsBegin', 'ReceiveBeginPlay'), ('questframe', 'QuestHandsFrame', 'ReceiveTick')]:
        candidates = [n for n in ed.list_all_nodes() if title(n).startswith(original)]
        if len(candidates) != 1:
            raise RuntimeError('Cannot locate the core event call ' + original)
        tail = og.pin_out(candidates[0])
        if list(og.P.list_connected_pins(tail)):
            raise RuntimeError('Core event already has a continuation: ' + original)
        call = graph.call(CHAR_CLASS + ':' + addition)
        og.link(tail, og.pin_in(call))
        if event == 'ReceiveTick':
            source = ed.find_event_node(event)
            og.link(og.value_pin(source, 'DeltaSeconds'), og.pin_in(call, 'DeltaSeconds'))
    return True


def pin_default(pin):
    for name in ('get_pin_default_value', 'get_pin_value', 'get_default_value'):
        getter = getattr(og.P, name, None)
        if getter is None:
            continue
        try:
            return str(getter(pin))
        except Exception:
            continue
    return None


def repair_hand_axes(bp):
    """The 25 October hands job wrote its four controller-axis FKey literals in the parenthesised syntax the
    installed parser reduces to '(' (the same defect the manager's 47 keys had before the 26 October repair).
    Repair them in their authored order: Left Grip, Left Trigger, Right Grip, Right Trigger."""
    graph = og.L.find_graph(bp, 'QuestHandsFrame')
    if graph is None:
        return {'repaired': [], 'note': 'no hands graph'}
    ed = og.E.get_graph_editor(graph)
    broken = []
    for node in ed.list_all_nodes():
        if not str(og.L.get_node_title(node)).replace(' ', '').lower().startswith('getinputanalogkeystate'):
            continue
        pin = og.L.find_input_pin(node, 'Key')
        if og.P.is_valid(pin) and not list(og.P.list_connected_pins(pin)):
            value = pin_default(pin)
            if value is None or value.strip() in ('', '(', 'None'):
                broken.append(node)
    def index(node):
        tail = node.get_name().rsplit('_', 1)[-1]
        return int(tail) if tail.isdigit() else 0
    broken.sort(key=index)
    keys = ['OculusTouch_Left_Grip_Axis', 'OculusTouch_Left_Trigger_Axis', 'OculusTouch_Right_Grip_Axis', 'OculusTouch_Right_Trigger_Axis']
    if len(broken) != len(keys):
        return {'repaired': [], 'warning': 'unexpected number of unrepaired analog reads', 'count': len(broken)}
    repaired = []
    for node, key in zip(broken, keys):
        og.default(node, 'Key', key)
        repaired.append({'node': node.get_name(), 'key': key})
    return {'repaired': repaired}


def rewrap_frontend_hooks(manager):
    """Re-author the release LoadProgress / SaveProgress / EndSlice hooks without their XR exclusion.

    The other release hooks (UpdateStep menu tick, InputFrame F10, CameraFraming, CloseModal) keep their
    recorded shape; InputFrame and CameraFraming are reached only on the desktop pin of the XR wrappers.
    """
    RFlow = rfg.Flow
    def load_hook(g, entry):
        f = RFlow(g, entry)
        approved, request = f.branch(f.var('ReleaseLoadApproved'))
        approved.set('ReleaseLoadApproved', False)
        booted, boot = request.branch(request.var('ReleaseBooted'))
        boot.own('ReleaseBoot')
        booted.own('ReleaseContinue')
        return approved
    def save_hook(g, entry):
        f = RFlow(g, entry)
        allowed, blocked = f.branch(f.and_(f.var('ReleaseWriteAllowed'), f.not_(f.var('ReleaseMenuActive'))))
        blocked.notice('This save is protected. New Game creates a separate playthrough.')
        return allowed
    def end_hook(g, entry):
        f = RFlow(g, entry)
        unreachable, every = f.branch(False)
        every.own('ReleaseShowEnd')
        return unreachable
    for name, callback in [('LoadProgress', load_hook), ('SaveProgress', save_hook), ('EndSlice', end_hook)]:
        rfg.wrap_entry(manager, name, callback)


def patch_manager(manager, character):
    for graph in og.L.list_graphs(manager):
        ed = og.E.get_graph_editor(graph)
        for comment in list(ed.list_comment_nodes()):
            if str(og.L.get_comment_text(comment)) == 'Quest.Recenter':
                ed.remove_comment_node(comment)
    og.member(manager, 'QuestFlowMarker', 'int', 0)
    signatures = {'_Quest_SetMode': {'NewMode': 'int'}, '_Quest_MovementFrame': {}, '_Quest_InputFrame': {},
                  '_Quest_CameraFraming': {'DeltaSeconds': 'real'}, '_Quest_OpenPause': {}, '_Quest_Recenter': {}}
    for name, inputs in signatures.items():
        reset_function(manager, name, inputs)
    og.compile_bp(manager)
    def fn(name):
        return Flow(reset_function(manager, name, signatures[name]))
    def character_call(f, function):
        cast = f.g.cast(character, f.var('Player'))
        og.link(f.cur, og.pin_in(cast))
        castflow = Flow(f.g, og.pin_out(cast))
        castflow.call(CHAR_CLASS + ':' + function, **{'self': f.g.cast_value(cast)})

    f = fn('_Quest_SetMode')
    f.set('Mode', f.g.input('NewMode'))
    f.call(CTL + 'ResetIgnoreMoveInput', **{'self': f.var('Controller')})
    f.call(CTL + 'ResetIgnoreLookInput', **{'self': f.var('Controller')})
    fn('_Quest_MovementFrame')
    fn('_Quest_CameraFraming')
    f = fn('_Quest_InputFrame')
    character_call(f, 'QuestInput')
    f = fn('_Quest_Recenter')
    xr, no = f.branch(f.tag(f.var('Player'), 'Quest.XRPlayer'))
    character_call(xr, 'QuestAlignHead')
    f = fn('_Quest_OpenPause')
    f.set('PauseReturnMode', f.var('Mode'))
    f.own('RestorePhoto')
    f.set('Testing', False)
    f.panel(6, 'Paused', '1  Resume\n\n2  Save committed progress\n\n3  Load saved progress',
            'B / Esc  Resume    1 / 2 / 3  Choose    Menu  Main menu')
    # Do not pause XR tracking or input dispatch with SetGamePaused.

    for name, quest_name in [('SetMode', '_Quest_SetMode'), ('MovementFrame', '_Quest_MovementFrame'),
                             ('InputFrame', '_Quest_InputFrame'), ('CameraFraming', '_Quest_CameraFraming'),
                             ('OpenPause', '_Quest_OpenPause')]:
        wrapper(manager, name, quest_name)
    rewrap_frontend_hooks(manager)

    recenter_calls = 0
    for name in ['RestorePlayerCheckpoint', 'TravelTick']:
        graph = og.L.find_graph(manager, name)
        if graph is None:
            raise RuntimeError('Story manager lacks ' + name)
        ed = og.E.get_graph_editor(graph)
        for n in list(ed.list_all_nodes()):
            if str(og.L.get_node_title(n)).replace(' ', '').lower().startswith('setactorlocation'):
                selfpin = og.L.find_input_pin(n, 'self')
                linked = list(og.P.list_connected_pins(selfpin)) if og.P.is_valid(selfpin) else []
                if not any(str(og.P.get_pin_name(p)) == 'Player' for p in linked):
                    continue
                then = og.pin_out(n)
                connected = list(og.P.list_connected_pins(then))
                if any('questrecenter' in str(og.L.get_node_title(og.P.get_owning_node(p))).replace(' ', '').replace('_', '').lower() for p in connected):
                    recenter_calls += 1
                    continue
                og.P.break_pin_links(then)
                g = og.Graph(manager, ed)
                call = g.call(MANAGER_CLASS + ':_Quest_Recenter')
                og.link(then, og.pin_in(call))
                for destination in connected:
                    og.link(og.pin_out(call), destination)
                recenter_calls += 1
    return recenter_calls


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    report = {'success': False, 'target': 'Meta Quest 3 standalone (Release copy)', 'runtime': 'Native Blueprints',
              'stamp': STAMP, 'headset_tested': False, 'apk_built': False,
              'limitations': ['Neutral controller proxies unless the articulated Epic hands are present; grip pickup not implemented',
                              'No smooth locomotion; teleport requires the authored Quest.Teleport landings (shown at runtime for the XR pawn)',
                              'Interaction targeting is the manager gaze ray (head direction); the hand or controller ray drives UI, landings and the pointer',
                              'Hand tracking has never run on a headset: pinch thresholds, the eye-to-pinch ray, fingertip marker size and the seated eye height are untuned',
                              'XR_MSFT_hand_interaction support on the Meta runtime is unverified; the joint-distance pinch is the primary path',
                              'Room-scale following, head occlusion, comfort and text legibility require physical headset validation']}
    settings = unreal.get_default_object(unreal.load_class(None, '/Script/BlueprintGraph.BlueprintEditorSettings'))
    old_promotion = settings.get_editor_property('bEnableTypePromotion')
    assets = {'manager': MANAGER_PATH, 'hud': HUD_PATH, 'character': CHAR_PATH, 'game_mode': GM_PATH}
    backup = ROOT / 'validation/quest3' / (STAMP + '_xrwrite') / 'backup'
    try:
        if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3XRWrite'):
            raise RuntimeError('Explicit -Quest3XRWrite flag and the serialized native writer slot are required')
        backup.mkdir(parents=True, exist_ok=True)
        report['backups'] = {}
        for key, path in assets.items():
            disk = ROOT / 'Content' / (path.removeprefix('/Game/') + '.uasset')
            if disk.exists():
                shutil.copy2(disk, backup / disk.name)
                report['backups'][key] = {'path': str(disk), 'sha256_before': sha(disk), 'backup': str(backup / disk.name)}
        settings.set_editor_property('bEnableTypePromotion', False)
        base.MATH_LITERALS.clear()
        manager = unreal.load_asset(MANAGER_PATH)
        hud = unreal.load_asset(HUD_PATH)
        if manager is None or hud is None:
            raise RuntimeError('Existing native chapter manager and HUD are required')
        character, had_hands = build_character(manager)
        report['hands_hooks_reattached'] = reattach_hands(character)
        report['hand_axes'] = repair_hand_axes(character)
        og.compile_bp(character)
        report['character_only'] = bool(CHARACTER_ONLY)
        if CHARACTER_ONLY:
            # The manager, HUD and game mode keep their pinned bytes; only the pawn is re-authored.
            report['recenter_calls'] = None
            to_compile = [character]
        else:
            report['recenter_calls'] = patch_manager(manager, character)
            wrapper(hud, 'ReceiveDrawHUD', None, is_hud=True)
            gm = og.blueprint(GM_PATH, unreal.GameModeBase)
            og.compile_bp(gm)
            cdo = unreal.get_default_object(og.L.generated_class(gm))
            cdo.set_editor_property('default_pawn_class', og.L.generated_class(character))
            cdo.set_editor_property('hud_class', og.L.generated_class(hud))
            to_compile = [character, manager, hud, gm]
        for _ in range(2):
            for node, name, value in base.MATH_LITERALS:
                pin = og.L.find_input_pin(node, name)
                if og.P.is_valid(pin) and not og.P.list_connected_pins(pin):
                    og.default(pin, value)
        report['compiled'] = og.compile_all(to_compile, save=True)
        report['hands_layer'] = HANDS_LAYER
        report['hands_comfort_layer'] = HANDS_COMFORT
        report['competition_pass'] = COMPETITION_PASS
        report['after'] = {}
        for key, path in assets.items():
            disk = ROOT / 'Content' / (path.removeprefix('/Game/') + '.uasset')
            report['after'][key] = {'path': str(disk), 'sha256_after': sha(disk) if disk.exists() else None}
        report['xr_wrappers'] = json.loads(unreal.EditorAssetLibrary.get_metadata_tag(manager, 'Quest.XRWrappers') or '{}')
        report['frontend_hooks'] = json.loads(unreal.EditorAssetLibrary.get_metadata_tag(manager, 'Release.FrontendHooks') or '{}')
        report['success'] = True
        report['assets'] = list(assets.values())
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    finally:
        settings.set_editor_property('bEnableTypePromotion', old_promotion)
        (ROOT / 'quest3_xr_build_report.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
        if backup.exists():
            (backup.parent / 'xr_build_report.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    unreal.log('QUEST3_XR_BUILD ' + json.dumps({'success': report['success'], 'stamp': STAMP}))
    if not report['success']:
        raise RuntimeError('Quest 3 XR authoring failed; inspect quest3_xr_build_report.json')


if __name__ == '__main__':
    main()
    unreal.SystemLibrary.quit_editor()
