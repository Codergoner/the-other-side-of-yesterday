"""Simulated hand pose for the Quest 3 PIE harnesses (12 November 2026).

The pawn draws each tracked hand from the 25 OpenXR hand-tracking keypoints, read from MotionControllerComponents named
Left/Right + keypoint. Without hardware those components are never tracked, so they stay where they are put: place()
puts them on a plausible hand whose index tip and thumb tip are the two simulated fingertips the harness already feeds
the pinch code, and the pawn's QuestSimJoints flag lets QuestHandDraw show them. Editor tooling only: a headset supplies
the real joints and nothing here ships. The pose is a fixed relaxed hand (index extended, other fingers curled), not
tracked data, so footage of it shows where the hand is and what it pinches, not how a real hand looks.
"""
import math
import unreal

FINGERS = [('Index', 1.0), ('Middle', 1.0), ('Ring', .93), ('Little', .76)]
KEYPOINTS = (['Wrist', 'ThumbMetacarpal', 'ThumbProximal', 'ThumbDistal', 'ThumbTip'] +
             [finger + part for finger, _ in FINGERS for part in ['Metacarpal', 'Proximal', 'Intermediate', 'Distal', 'Tip']])


def _t(v):
    return (v.x, v.y, v.z)


def _add(*vs):
    return tuple(sum(c) for c in zip(*vs))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _norm(a):
    length = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2) or 1.0
    return (a[0] / length, a[1] / length, a[2] / length)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def pose(right, eye, camera_right, index_tip, thumb_tip):
    """Keypoint name -> (x, y, z) in world cm for one hand. eye, camera_right, index_tip, thumb_tip are 3-tuples."""
    sign = 1.0 if right else -1.0
    shoulder = _add(eye, (0.0, 0.0, -28.0), _mul(camera_right, sign * 20.0))
    forward = _norm(_sub(index_tip, shoulder))                      # along the extended index finger
    side = _norm(_cross((0.0, 0.0, 1.0), forward))                  # the hand's own right
    up = _cross(forward, side)                                       # back of the hand
    away = _mul(side, sign)                                          # from the index toward the little finger
    return _hand(index_tip, thumb_tip, forward, away, up)


def watch_pose(right, eye, camera_forward, camera_right, camera_up, reach=34.0, across=-3.0, below=-9.0):
    """The same hand raised to read a watch on its wrist (16 November 2026, night): the forearm lies across the view, the
    fingers point to the far side, the back of the hand faces the eye and the little-finger side is up. The wrist is
    `reach` cm ahead of the eye, `across` cm toward the hand's own side and `below` cm under the eye line. Returns the
    keypoints with an open hand (thumb away from the index tip)."""
    sign = 1.0 if right else -1.0
    wrist = _add(eye, _mul(camera_forward, reach), _mul(camera_right, sign * across), _mul(camera_up, below))
    forward = _norm(_add(_mul(camera_right, -sign * .95), _mul(camera_forward, .22), _mul(camera_up, .08)))   # fingers across the view
    to_eye = _sub(eye, wrist)
    lean = sum(a * b for a, b in zip(to_eye, forward))
    up = _norm(_sub(to_eye, _mul(forward, lean)))                    # back of the hand, straight at the eye
    # The thumb side (index minus little) is forward x up on a right hand and up x forward on a left hand.
    thumb_side = _cross(forward, up) if right else _cross(up, forward)
    away = _mul(thumb_side, -1.0)
    index_tip = _add(wrist, _mul(forward, 18.2), _mul(away, -2.6), _mul(up, -.3))
    thumb_tip = _add(index_tip, _mul(away, -5.0), _mul(up, -3.0), _mul(forward, -4.0))
    return _hand(index_tip, thumb_tip, forward, away, up)


def _hand(index_tip, thumb_tip, forward, away, up):

    def at(base, f=0.0, a=0.0, u=0.0):
        return _add(base, _mul(forward, f), _mul(away, a), _mul(up, u))

    joints = {'IndexTip': index_tip, 'IndexDistal': at(index_tip, -2.3, 0, .15), 'IndexIntermediate': at(index_tip, -4.9, 0, .6),
              'IndexProximal': at(index_tip, -8.9, 0, .9)}
    knuckle = joints['IndexProximal']
    knuckles = {'Index': knuckle, 'Middle': at(knuckle, -.1, 2.0), 'Ring': at(knuckle, -.6, 3.9), 'Little': at(knuckle, -1.5, 5.6, -.2)}
    wrist = at(knuckle, -9.3, 2.6, -.6)
    joints['Wrist'] = wrist
    for finger, k in FINGERS:
        base = knuckles[finger]
        joints[finger + 'Metacarpal'] = _add(wrist, _mul(_sub(base, wrist), .22))
        if finger == 'Index':
            continue
        joints[finger + 'Proximal'] = base
        middle = _add(base, _mul(_norm(_add(_mul(forward, .72), _mul(up, -.69))), 4.3 * k))
        distal = _add(middle, _mul(_norm(_add(_mul(forward, .05), _mul(up, -1.0))), 2.7 * k))
        joints[finger + 'Intermediate'] = middle
        joints[finger + 'Distal'] = distal
        joints[finger + 'Tip'] = _add(distal, _mul(_norm(_add(_mul(forward, -.55), _mul(up, -.83))), 2.3 * k))
    thumb_base = at(wrist, 1.6, -2.4, -.6)
    reach = _sub(thumb_tip, thumb_base)
    joints['ThumbMetacarpal'] = thumb_base
    joints['ThumbProximal'] = _add(thumb_base, _mul(reach, .42), _mul(away, -1.1))
    joints['ThumbDistal'] = _add(thumb_base, _mul(reach, .74), _mul(away, -.7))
    joints['ThumbTip'] = thumb_tip
    return joints


def place(pawn, right, index_tip, thumb_tip):
    """Put one hand's keypoint components on the simulated pose and switch the drawn hands on for the simulation."""
    camera = pawn.get_editor_property('QuestCamera')
    joints = pose(right, _t(camera.get_world_location()), _t(camera.get_right_vector()), _t(index_tip), _t(thumb_tip))
    side = 'Right' if right else 'Left'
    for name in KEYPOINTS:
        pawn.get_editor_property(side + name).set_world_location(unreal.Vector(*joints[name]), False, True)
    pawn.set_editor_property('QuestSimJoints', True)
    return joints


def place_watch(pawn, right, **where):
    """Put one hand's keypoint components on the raised-wrist pose (watch_pose) and feed the pawn's simulated fingertips
    from it (an open hand). Returns the keypoints."""
    camera = pawn.get_editor_property('QuestCamera')
    joints = watch_pose(right, _t(camera.get_world_location()), _t(camera.get_forward_vector()), _t(camera.get_right_vector()),
                        _t(camera.get_up_vector()), **where)
    side = 'Right' if right else 'Left'
    for name in KEYPOINTS:
        pawn.get_editor_property(side + name).set_world_location(unreal.Vector(*joints[name]), False, True)
    pawn.set_editor_property('QuestSimHands', True)
    pawn.set_editor_property('QuestSim' + side + 'Valid', True)
    pawn.set_editor_property('QuestSim' + side + 'Index', unreal.Vector(*joints['IndexTip']))
    pawn.set_editor_property('QuestSim' + side + 'Thumb', unreal.Vector(*joints['ThumbTip']))
    pawn.set_editor_property('QuestSimJoints', True)
    return joints
