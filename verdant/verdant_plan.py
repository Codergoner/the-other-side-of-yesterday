"""The city of Verdant as data: one street plan, resolved separately for each timeline.

Coordinates are the existing game's Blender metres (Unreal = 100X, -100Y, 100Z), so the uphill
road, harbor stairs, campanile, cathedral plaza and lighthouse island stay where the story
already expects them. Pure Python: Blender reads it for landscape, Unreal for placement.

Run directly to write output/verdant/plan.json.
"""
import json
import math
import random
import zlib
from pathlib import Path

BW, HG, HU, T = 2.5, 3.6, 3.2, .45
ROOF_RUN, ROOF_RISE, GABLE_SPAN, GABLE_RISE = 4.0, 1.6, 7.5, 1.5
SQUARE_Z = 10.7


def street_z(y):
    return 8 + (y + 22) * .10


# Local bay codes: P plain, W window, D door, S shop, B balcony, R repaired door (present only).
class Building:
    def __init__(self, name, x, y, yaw, w, d, floors, z=None, front=None, ridge='X', tint=0, paint=0, damage=None, cared=False,
                 chimney=True, rear=None):
        self.name, self.x, self.y, self.yaw, self.w, self.d, self.floors = name, x, y, yaw, w, d, floors
        self.front, self.ridge, self.tint, self.paint, self.damage, self.cared, self.chimney = front or {}, ridge, tint, paint, damage, cared, chimney
        self.rear = rear or {}
        a = math.radians(yaw)
        self.ax, self.ay = math.cos(a), math.sin(a)
        self.bx, self.by = -math.sin(a), math.cos(a)
        if z is None:
            cy = y + self.ay * w * BW / 2
            z = street_z(cy)
        self.z = z

    def world(self, u, v, z=0.0):
        return (self.x + self.ax * u + self.bx * v, self.y + self.ay * u + self.by * v, self.z + z)


# Yaw of the facade run. The outer face looks along local -Y.
WEST = 90        # west side of a street: faces +X, runs north
EAST = -90       # east side of a street: faces -X, runs south
FACE_SOUTH = 0   # north side of a square: faces -Y, runs east
FACE_NORTH = 180 # south side of a square: faces +Y, runs west


def collapse(cx, cz, radius, level=1.0):
    return {'side': 'front', 'u': cx, 'z': cz, 'radius': radius, 'level': level}


BUILDINGS = [
    # ---- Street row, west side, south to north. Front face at X=-4. ------------------------
    Building('StreetSouth', -4, -25.2, WEST, 2, 3, 3, front={0: 'SD', 1: 'WW', 2: 'WB'}, tint=1, paint=0, damage=collapse(2.5, 9, 7, .75)),
    Building('FamilyHome', -6.6, -18, WEST, 4, 3, 2, z=street_z(-13) + .35, front={0: 'WDWP', 1: 'WBBW'}, tint=0, paint=1,
             damage=collapse(9.2, 6, 6.2, 1.2), cared=True),
    Building('ClinicBlock', -8.6, -7.6, WEST, 3, 3, 2, z=street_z(-4), front={0: 'WDW', 1: 'WWW'}, tint=3, paint=1, damage=collapse(1.0, 7, 3.6, .55), cared=True),
    Building('ArcadeSouth', -4, -.1, WEST, 1, 3, 3, z=street_z(1), front={0: 'S', 1: 'B', 2: 'W'}, tint=2, paint=2, damage=collapse(0, 10, 5, .5)),
    Building('SelaShop', -4, 4.6, WEST, 3, 3, 3, z=street_z(8), front={0: 'SSD', 1: 'BWB', 2: 'WWW'}, tint=1, paint=0, damage=collapse(6.5, 11, 4.5, .72), cared=True),
    Building('StreetMid', -4, 16.2, WEST, 3, 3, 3, front={0: 'SDS', 1: 'WBW', 2: 'WWW'}, tint=2, paint=0, damage=collapse(3.8, 10.5, 7, 1.05)),
    Building('StreetNorth', -4, 24, WEST, 3, 3, 4, front={0: 'DSW', 1: 'BWW', 2: 'WWB', 3: 'WWW'}, tint=0, paint=2, damage=collapse(6, 13, 6.5, .85)),

    # ---- Market Square. Open plan X -36..-11.5, Y 0.2..16 -----------------------------------
    Building('SquareWestA', -36.5, .2, WEST, 3, 3, 3, z=SQUARE_Z, front={0: 'SDS', 1: 'BWB', 2: 'WWW'}, tint=2, paint=2, damage=collapse(2, 8.5, 7, .9)),
    Building('SquareWestB', -36.5, 8.1, WEST, 3, 3, 4, z=SQUARE_Z, front={0: 'SSD', 1: 'WBW', 2: 'WWW', 3: 'WPW'}, tint=1, paint=0, damage=collapse(5.5, 14, 5, .7)),
    Building('SquareNorthC', -36, 16, FACE_SOUTH, 2, 3, 3, z=SQUARE_Z + .05, front={0: 'DS', 1: 'WB', 2: 'WW'}, tint=1, paint=0, ridge='Y', damage=collapse(2, 11, 4, .75)),
    Building('SquareNorthA', -30.6, 16, FACE_SOUTH, 3, 3, 3, z=SQUARE_Z + .05, front={0: 'SDS', 1: 'WWW', 2: 'WWW'}, tint=0, paint=1, ridge='Y', damage=collapse(4, 9, 6, .95)),
    Building('SquareNorthB', -22.8, 16, FACE_SOUTH, 3, 3, 3, z=SQUARE_Z + .05, front={0: 'SDW', 1: 'BWW', 2: 'WPW'}, tint=2, paint=2, damage=collapse(2, 9, 4, .6)),
    Building('SquareSouthB', -20.4, .2, FACE_NORTH, 3, 3, 2, z=SQUARE_Z, front={0: 'SSD', 1: 'WBW'}, tint=0, paint=2, ridge='Y', damage=collapse(1.5, 7, 5.5, 1.1)),
    Building('SquareSouthA', -28.3, .2, FACE_NORTH, 3, 3, 3, z=SQUARE_Z, front={0: 'SDS', 1: 'BWW', 2: 'WWW'}, tint=3, paint=0, damage=collapse(4, 8, 5, .8)),

    # ---- Side lanes behind the street row ---------------------------------------------------
    Building('LaneWestA', -14.8, 23.8, WEST, 2, 3, 3, z=13.05, front={0: 'DW', 1: 'WW', 2: 'WB'}, tint=2, paint=1, damage=collapse(2, 9, 4.5, .85)),
    Building('LaneWestB', -14.8, 29.2, WEST, 2, 3, 3, z=14.75, front={0: 'WD', 1: 'BW', 2: 'WW'}, tint=1, paint=0, damage=collapse(1, 8, 3.8, .5)),
    Building('LaneEastA', -20.4, -15.5, WEST, 3, 3, 3, z=9.25, front={0: 'WDW', 1: 'WBW', 2: 'WWW'}, tint=0, paint=2, damage=collapse(3, 9, 5, .9)),
    Building('LaneEastB', -20.4, -23.6, WEST, 3, 3, 2, z=8.4, front={0: 'DWW', 1: 'WWB'}, tint=2, paint=1, damage=collapse(1, 7, 5, 1.0)),
    Building('GateRow', -12, -20.2, FACE_NORTH, 3, 3, 2, z=8.3, front={0: 'WDW', 1: 'BWW'}, tint=3, paint=0, ridge='Y', damage=collapse(5, 7, 4.5, .8)),

    # ---- Harbor ---------------------------------------------------------------------------
    Building('VillaLower', 9.8, 20.5, WEST, 3, 2, 2, z=6.0, front={0: 'WDW', 1: 'BWB'}, tint=0, paint=1, damage=collapse(6, 6, 5, 1.05)),
    Building('VillaUpper', 16.5, 29.5, WEST, 3, 2, 2, z=3.5, front={0: 'SDW', 1: 'WBW'}, tint=1, paint=2, damage=collapse(2, 7, 3.5, .5)),
    Building('HarborMaster', 14, 18.6, FACE_SOUTH, 3, 2, 2, z=1.25, front={0: 'SDS', 1: 'WWW'}, tint=2, paint=0, damage=collapse(1, 6, 3.5, .6), cared=True, chimney=False),
]

# Hillside backdrop: same kit, seen across the roofs. Seeded so both eras agree.
_hill = random.Random(4471)
for row, (x_front, z0, count) in enumerate(((-46, 13.6, 9), (-56, 17.2, 10), (-67, 21.0, 9))):
    y = -46 + row * 4.0
    for i in range(count):
        bays = _hill.choice((2, 3, 3))
        floors = _hill.choice((2, 3, 3))
        tint, paint = _hill.randrange(4), _hill.randrange(3)
        pattern = ''.join(_hill.choice('WWWP') for _ in range(bays))
        heavy = _hill.random()
        BUILDINGS.append(Building('Hill%d_%d' % (row, i), x_front + _hill.uniform(-1.5, 1.5), y, WEST, bays, 3, floors,
                                  z=z0 + (y - 0) * .03 + _hill.uniform(-.2, .2), front={f: pattern for f in range(floors)}, tint=tint, paint=paint,
                                  ridge=_hill.choice('XXY'),
                                  damage=collapse(_hill.uniform(0, bays * BW), 9, _hill.uniform(3.5, 7), .5 + heavy * .75)))
        y += bays * BW + _hill.uniform(1.0, 2.8)

# ---- Walkable ground ----------------------------------------------------------------------
# rect: x0, x1, y0, y1, corner heights (x0y0, x1y0, x1y1, x0y1), surface material.
def rect(name, x0, x1, y0, y1, z, mat):
    z = (z,) * 4 if isinstance(z, (int, float)) else z
    return {'name': name, 'x0': x0, 'x1': x1, 'y0': y0, 'y1': y1, 'z': z, 'mat': mat}


def along_y(name, x0, x1, y0, y1, a, b, mat):
    return rect(name, x0, x1, y0, y1, (a, a, b, b), mat)


def along_x(name, x0, x1, y0, y1, a, b, mat):
    return rect(name, x0, x1, y0, y1, (a, b, b, a), mat)


SURFACES = [
    along_y('Road', -2.8, 3.4, -27.5, 35, street_z(-27.5), street_z(35), 'Cobble'),
    along_y('Walk', -4.4, -2.8, -27.5, 35, street_z(-27.5) + .03, street_z(35) + .03, 'Flagstone'),
    along_x('HomeCourt', -6.8, -4.4, -18.2, -7.7, street_z(-13) + .32, street_z(-13) + .03, 'Flagstone'),
    rect('ClinicCourt', -8.8, -4.4, -7.7, 0.0, street_z(-4) + .02, 'Flagstone'),
    along_x('ArcadeAlley', -11.6, -4.4, 2.2, 4.8, SQUARE_Z, street_z(3.5) + .03, 'Cobble'),
    along_x('MarketLane', -11.6, -4.4, 11.9, 16.4, SQUARE_Z, street_z(14) + .03, 'Cobble'),
    rect('MarketSquare', -36.7, -11.5, 0.0, 16.2, SQUARE_Z, 'Flagstone'),
    along_y('BackLane', -14.9, -11.4, 16.0, 34.5, SQUARE_Z + .05, 16.95, 'Cobble'),
    rect('UpperCourt', -15.0, -5.4, 34.4, 46.2, 17.0, 'Flagstone'),
    rect('Forecourt', -5.5, 3.7, 43.9, 46.1, 17.5, 'Flagstone'),
    along_y('SideLane', -20.5, -16.9, -20.4, 0.2, 8.32, SQUARE_Z, 'Cobble'),
    along_x('GateLane', -20.5, -4.4, -20.4, -18.0, 8.32, street_z(-19) + .03, 'Cobble'),
    rect('PlazaNorth', -4.5, 26.5, 57.0, 84.5, 25.0, 'Flagstone'),
    rect('PlazaApron', 2.7, 26.5, 50.5, 57.0, 25.0, 'Flagstone'),
    rect('StairLanding', 2.2, 8.4, 12.6, 15.4, 11.6, 'Flagstone'),
    rect('Overlook', 5.2, 15.6, -14.0, 2.4, 6.4, 'Flagstone'),
    rect('Quay', 12.4, 25.0, 2.0, 26.5, 1.2, 'Flagstone'),
    rect('VillaTerrace', 3.4, 12.8, 18.5, 31.5, 6.0, 'Flagstone'),
    rect('VillaLow', 10.0, 19.5, 28.0, 39.0, 3.5, 'Flagstone'),
    rect('LighthouseIsland', 50.0, 66.0, 23.0, 38.0, 2.0, 'Flagstone'),
]

# Visible treads over a continuous walkable ramp (collision is the ramp, never the steps).
STAIRS = [
    {'name': 'HarborWest', 'a': (7.0, 14.0, 11.6), 'b': (7.0, 1.0, 6.4), 'width': 2.8, 'treads': 36},
    {'name': 'HarborEast', 'a': (11.0, 1.0, 6.4), 'b': (11.0, 14.0, 1.2), 'width': 2.8, 'treads': 36},
    {'name': 'CampanileApproach', 'a': (1.65, 35.0, 13.7), 'b': (1.65, 44.0, 17.5), 'width': 4.1, 'treads': 26},
    {'name': 'CathedralStair', 'a': (0.0, 45.5, 17.5), 'b': (0.0, 57.0, 25.0), 'width': 5.5, 'treads': 50},
    {'name': 'HomeSteps', 'a': (-4.6, -13.0, street_z(-13) + .02), 'b': (-6.7, -13.0, street_z(-13) + .35), 'width': 3.0, 'treads': 3},
]

# Mole (causeway) from the quay to the lighthouse island.
MOLE = [(24.0, 22.0, 1.25), (34.0, 25.5, 1.7), (44.0, 27.5, 1.9), (52.0, 29.5, 2.0)]
MOLE_WIDTH = 3.6

# Invisible limits at drops the player must not walk off. x0, x1, y0, y1, z0, z1.
BLOCKERS = [
    (3.15, 3.5, -27.5, 12.2, 5, 16), (3.15, 3.5, 15.8, 36, 5, 19),   # street parapet, stair gap
    (-5, 4, -28.2, -27.6, 5, 16), (15.6, 15.9, -14.2, 2.6, 4, 9), (5, 16, -14.3, -14.0, 4, 9),
    (25.0, 25.3, 2, 21, 0, 4), (12.4, 25.3, 1.7, 2.0, 0, 4), (2.2, 8.4, 15.4, 15.6, 9, 14),
    (-5, 27, 84.5, 84.8, 23, 28), (26.5, 26.8, 50.5, 84.8, 23, 28), (2.7, 26.8, 50.2, 50.5, 23, 28), (-4.8, -4.5, 57, 84.8, 23, 28),
    (-15.3, -15.0, 34.4, 46.2, 15, 21), (-15, -5.4, 46.2, 46.5, 15, 21), (-5.8, -5.5, 46.2, 48, 16, 20), (3.7, 4.0, 44, 57, 16, 28), (-3.0, -2.8, 46.2, 57, 16, 28),
]

PLASTER_TINTS = [(1.0, .97, .9), (1.0, .93, .8), (.98, .9, .76), (1.0, .96, .86)]
PAINT_TINTS = [(.2, .42, .42), (.16, .36, .4), (.22, .4, .32)]


class Resolver:
    """Turns buildings into module instances for one era."""

    def __init__(self, era):
        self.era = era
        self.items = []
        self.colliders = []
        self.rng = random.Random(9091)

    def add(self, mesh, position, yaw, scale=(1, 1, 1), tint=None, paint=None):
        row = {'m': mesh, 'p': [round(v, 3) for v in position], 'r': round(yaw, 2), 's': list(scale)}
        if tint is not None:
            row['c'] = [round(v, 3) for v in PLASTER_TINTS[tint]] + [round(v, 3) for v in PAINT_TINTS[paint]]
        self.items.append(row)

    def severity(self, b, u, z):
        if self.era == 'Past' or not b.damage:
            return 0.0
        d = b.damage
        distance = math.hypot(u - d['u'], (z - d['z']) * .9)
        wobble = random.Random(zlib.crc32(('%s|%.1f|%.1f' % (b.name, u, z)).encode())).uniform(-.12, .12)
        return max(0.0, d['level'] * (1 - distance / d['radius']) + wobble)

    def wall_mesh(self, code, ground, severity, cared):
        """Maps a bay and its local damage to a kit module; None means the bay has fallen."""
        layer = 'G' if ground else 'U'
        if code == 'O':
            # Open entrance (story clinic): the door stands open in the past; the present keeps the kit door.
            return 'SM_V_Story_DoorOpen_R' if self.era == 'Past' else self.wall_mesh('D', ground, severity, cared)
        if self.era == 'Past':
            return {'P': 'SM_V_%s_Plain_R' % layer, 'W': 'SM_V_%s_Window_R' % layer, 'D': 'SM_V_G_Door_R',
                    'S': 'SM_V_G_Shop_R', 'B': 'SM_V_U_Balcony_R'}[code]
        if severity >= 1.02:
            return None
        if severity >= .8:
            return 'SM_V_%s_Plain_D3' % layer
        stage = 2 if severity >= .46 else 1
        if cared and severity < .3:
            stage = 0
        suffix = {0: 'R', 1: 'D1', 2: 'D2'}[stage]
        if code == 'P':
            return 'SM_V_%s_Plain_%s' % (layer, suffix)
        if code == 'W':
            return 'SM_V_%s_Window_%s' % (layer, suffix)
        if code == 'D':
            return 'SM_V_G_Door_%s' % ('REP' if cared else suffix)
        if code == 'S':
            return 'SM_V_G_Shop_%s' % suffix
        return 'SM_V_U_Balcony_%s' % suffix

    def building(self, b):
        tint, paint = b.tint, b.paint
        columns = {}
        sides = [('front', b.w, 0, 0, 0), ('right', b.d, b.w * BW, 0, 90), ('back', b.w, b.w * BW, b.d * BW, 180), ('left', b.d, 0, b.d * BW, 270)]
        stood = {}
        bays_placed = []
        for side, bays, ou, ov, turn in sides:
            run_u, run_v = {'front': (1, 0), 'right': (0, 1), 'back': (-1, 0), 'left': (0, -1)}[side]
            yaw = b.yaw + turn
            for i in range(bays):
                standing = True
                top = 0
                for floor in range(b.floors):
                    ground = floor == 0
                    z = 0 if ground else HG + (floor - 1) * HU
                    if side == 'front':
                        pattern = b.front.get(floor, '')
                        code = pattern[i] if i < len(pattern) else ('W' if (i + floor) % 2 == 0 else 'P')
                    elif side == 'back':
                        code = 'W' if (i + floor) % 2 == 1 else 'P'
                    else:
                        code = 'P' if ground or i % 2 == 0 else 'W'
                    u = ou + run_u * i * BW
                    v = ov + run_v * i * BW
                    # Damage is measured along the facade; side walls borrow their nearest column.
                    if side == 'front':
                        measure = u + BW / 2
                    elif side == 'back':
                        measure = u - BW / 2
                    else:
                        measure = ou
                    sev = self.severity(b, measure, z + 1.6)
                    mesh = self.wall_mesh(code, ground, sev, b.cared) if standing else None
                    if mesh is None:
                        standing = False
                        continue
                    self.add(mesh, b.world(u, v, z), yaw, tint=tint, paint=paint)
                    bays_placed.append({'side': side, 'code': code, 'floor': floor, 'u': u, 'v': v, 'z': z, 'yaw': yaw, 'run': (run_u, run_v), 'mesh': mesh, 'sev': sev})
                    if '_D3' in mesh:
                        standing = False
                    else:
                        top = floor + 1
                    if floor < b.floors - 1 and standing:
                        self.add('SM_V_Band_' + ('R' if self.era == 'Past' or sev < .3 else 'D'), b.world(u, v, z + (HG if ground else HU)), yaw)
                stood[side, i] = top
                if top == b.floors:
                    self.add('SM_V_Cornice_' + ('R' if self.era == 'Past' else 'D'), b.world(ou + run_u * i * BW, ov + run_v * i * BW, HG + (b.floors - 1) * HU - .02), yaw)
                elif self.era == 'Present':
                    self.ruin_foot(b, ou + run_u * (i + .5) * BW, ov + run_v * (i + .5) * BW, yaw)
        self.corners(b)
        self.roof(b, stood)
        self.dress_building(b, bays_placed)
        hi = HG + (b.floors - 1) * HU
        self.colliders.append({'center': b.world(b.w * BW / 2, b.d * BW / 2, hi / 2 - 1), 'size': [b.w * BW, b.d * BW, hi + 2], 'yaw': b.yaw})

    def dress_building(self, b, bays):
        """Awnings, flower boxes, lanterns and climbers attach to bays that actually exist."""
        r = self.rng
        past = self.era == 'Past'
        hero = not b.name.startswith('Hill')
        for bay in bays:
            run_u, run_v = bay['run']
            middle = lambda dz=0.0, out=0.0: b.world(bay['u'] + run_u * BW / 2 + (b.ax * 0), bay['v'] + run_v * BW / 2, bay['z'] + dz)
            outward = {'front': (0, -1), 'right': (1, 0), 'back': (0, 1), 'left': (-1, 0)}[bay['side']]
            stand_off = lambda u_off, dz, depth=0.0: b.world(bay['u'] + run_u * (BW / 2 + u_off) + outward[0] * depth, bay['v'] + run_v * (BW / 2 + u_off) + outward[1] * depth, bay['z'] + dz)
            if bay['code'] == 'S' and bay['side'] == 'front':
                if past or (b.cared and bay['sev'] < .3):
                    self.add('SM_V_Awning_R', stand_off(0, 3.38), bay['yaw'])
                elif r.random() < .45:
                    self.add('SM_V_Awning_D', stand_off(0, 3.38), bay['yaw'])
            if bay['code'] in ('D', 'O') and bay['side'] == 'front' and hero:
                if past or b.cared:
                    self.add('SM_V_Lantern_Wall', stand_off(-1.02, 2.95), bay['yaw'])
                if past or (b.cared and r.random() < .7):
                    self.add('SM_V_Pot', stand_off(1.0, 0, .55), r.uniform(0, 360), (.6, .6, .6))
            if bay['code'] == 'W' and bay['floor'] >= 1 and bay['side'] == 'front' and hero and '_R' in bay['mesh']:
                if r.random() < (.55 if past else .16):
                    self.add('SM_V_FlowerBox', stand_off(0, .72, .22), bay['yaw'], (.86, 1, 1))
            if bay['code'] == 'B' and hero and past and r.random() < .4:
                self.add('SM_V_Bougainvillea', stand_off(r.uniform(-1, 1), 1.0, .4), bay['yaw'], (.9, 1, .9))
            if bay['floor'] == 0 and bay['side'] == 'front' and hero and past and bay['code'] in 'PW' and r.random() < .3:
                self.add('SM_V_Pot', stand_off(r.uniform(-.8, .8), 0, .5), r.uniform(0, 360), (.6, .6, .6))
            if not past and hero:
                if bay['floor'] == 0 and r.random() < .5:
                    self.add('SM_V_WeedPatch', stand_off(r.uniform(-.9, .9), 0, r.uniform(.2, .5)), r.uniform(0, 360), (.75, .75, r.uniform(.6, 1.0)))
                if bay['floor'] == b.floors - 1 and r.random() < (.3 if b.cared else .55):
                    self.add('SM_V_IvyCurtain', stand_off(r.uniform(-.8, .8), HU - .1, .02), bay['yaw'], (1, 1, r.uniform(.7, 1.25)))
            if past and hero and bay['floor'] == b.floors - 1 and r.random() < .1:
                self.add('SM_V_IvyCurtain', stand_off(r.uniform(-.8, .8), HU - .3, .02), bay['yaw'], (.7, 1, .8))
        if hero:
            self.add('SM_V_Downpipe', b.world(.08, 0, HG), b.yaw, (1, 1, (b.floors - 1) * HU / HU))
    def ruin_foot(self, b, u, v, yaw):
        p = b.world(u, v, 0)
        self.add('SM_V_Rubble_%s' % self.rng.choice('ABC'), p, self.rng.uniform(0, 360), (self.rng.uniform(.8, 1.3),) * 3)

    def corners(self, b):
        corners = [(0, 0, 0), (b.w * BW, 0, 90), (b.w * BW, b.d * BW, 180), (0, b.d * BW, 270)]
        for index, (u, v, turn) in enumerate(corners):
            for floor in range(b.floors):
                z = 0 if floor == 0 else HG + (floor - 1) * HU
                if self.era == 'Present' and self.severity(b, u, z + 1.6) > .55:
                    break
                self.add('SM_V_Quoin_' + ('G' if floor == 0 else 'U'), b.world(u, v, z), b.yaw + turn)

    def roof(self, b, stood):
        top = HG + (b.floors - 1) * HU
        along_x = b.ridge == 'X'
        bays = b.w if along_x else b.d
        span = (b.d if along_x else b.w) * BW
        scale = (span / 2) / ROOF_RUN
        rise = ROOF_RISE * scale
        overhang = 1.04
        for slope in (0, 1):
            for i in range(bays):
                if along_x:
                    u = (i * BW if slope == 0 else (b.w - i) * BW)
                    v = 0 if slope == 0 else b.d * BW
                    yaw = b.yaw if slope == 0 else b.yaw + 180
                    side, index = ('front', i) if slope == 0 else ('back', b.w - 1 - i)
                else:
                    u = 0 if slope == 0 else b.w * BW
                    v = ((b.d - i) * BW if slope == 0 else i * BW)
                    yaw = b.yaw + 270 if slope == 0 else b.yaw + 90
                    side, index = ('left', b.d - 1 - i) if slope == 0 else ('right', i)
                height = stood.get((side, index), b.floors)
                if self.era == 'Past':
                    state = 'R'
                else:
                    near = self.severity(b, u, top + 1)
                    if height < b.floors:
                        if near > .9:
                            continue
                        state = 'D2'
                    elif near > .5:
                        state = 'D2'
                    elif near > .16 or (not b.cared and self.rng.random() < .3):
                        state = 'D1'
                    else:
                        state = 'R'
                self.add('SM_V_Roof_' + state, b.world(u, v, top), yaw, (overhang, scale, scale))
        for i in range(bays):
            if along_x:
                position = b.world(i * BW, b.d * BW / 2, top + rise + .3)
                yaw = b.yaw
            else:
                position = b.world(b.w * BW / 2, (b.d - i) * BW, top + rise + .3)
                yaw = b.yaw + 270
            if self.era == 'Present' and self.severity(b, position[0] * 0 + i * BW, top + 1) > .4:
                continue
            self.add('SM_V_Ridge_' + ('R' if self.era == 'Past' else 'D'), position, yaw, (1.02, 1, 1))
        # Gable ends close the roof on the two walls the ridge runs into.
        gx = span / GABLE_SPAN
        gz = rise / GABLE_RISE
        if along_x:
            ends = [(b.w * BW, 0, b.yaw + 90), (0, b.d * BW, b.yaw + 270)]
        else:
            ends = [(0, 0, b.yaw), (b.w * BW, b.d * BW, b.yaw + 180)]
        for u, v, yaw in ends:
            ruined = self.era == 'Present' and self.severity(b, u, top + .5) > .4
            self.add('SM_V_Gable_' + ('D' if ruined else 'R'), b.world(u, v, top), yaw, (gx, 1, gz), tint=b.tint, paint=b.paint)
        if b.chimney:
            ruined = self.era == 'Present' and self.severity(b, b.w * BW * .7, top + 1) > .15
            self.add('SM_V_Chimney_' + ('D' if ruined else 'R'), b.world(b.w * BW * .68, b.d * BW * .3, top + rise * .5), b.yaw, tint=b.tint, paint=b.paint)


def parapet_run(r, x0, y0, x1, y1, z0, z1, slope_name, gaps=()):
    """Stone piers every two metres along a run, broken more often in the present."""
    length = math.hypot(x1 - x0, y1 - y0)
    yaw = math.degrees(math.atan2(y1 - y0, x1 - x0))
    count = int(length / 2)
    for i in range(count):
        t = i / max(1, count)
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        if any(a <= (y if abs(y1 - y0) > abs(x1 - x0) else x) <= c for a, c in gaps):
            continue
        z = z0 + (z1 - z0) * t
        state = 'R'
        if r.era == 'Present':
            roll = r.rng.random()
            state = 'D2' if roll < .2 else 'D1' if roll < .75 else 'R'
        r.add('SM_V_Parapet_%s_%s' % (slope_name, state), (x, y, z), yaw)


def group(r, mesh, points, z=None, scale=(1, 1, 1), spin=True):
    for x, y, zz in points:
        r.add(mesh, (x, y, zz if z is None else z), r.rng.uniform(0, 360) if spin else 0, scale)


def box_collider(r, x, y, z, sx, sy, sz, yaw=0):
    r.colliders.append({'center': (x, y, z + sz / 2), 'size': [sx, sy, sz], 'yaw': yaw})


def dress_city(r):
    past = r.era == 'Past'
    s = 'R' if past else 'D'
    rng = r.rng
    parapet_run(r, 3.1, -26, 3.1, 12, street_z(-26), street_z(12), 'Slope')
    parapet_run(r, 3.1, 16, 3.1, 34, street_z(16), street_z(34), 'Slope')
    parapet_run(r, 15.5, -14, 15.5, 2.4, 6.4, 6.4, 'Flat')
    parapet_run(r, 5.4, -14, 15.5, -14, 6.4, 6.4, 'Flat')
    parapet_run(r, 26.4, 50.6, 26.4, 84, 25, 25, 'Flat')
    parapet_run(r, 3.0, 50.6, 26.4, 50.6, 25, 25, 'Flat')
    parapet_run(r, -4.4, -18, -4.4, -14.6, street_z(-16) + .1, street_z(-14.6) + .1, 'Flat')
    parapet_run(r, -4.4, -11.4, -4.4, -8, street_z(-10) + .1, street_z(-8) + .1, 'Flat')

    # Landmarks.
    r.add('SM_V_Campanile', (0, 0, 0), 0)
    r.add('SM_V_Cathedral_Core_' + s, (0, 0, 0), 0)
    r.add('SM_V_Cathedral_South_' + s, (0, 0, 0), 0)
    r.add('SM_V_Lighthouse_' + s, (0, 0, 0), 0)
    r.add('SM_V_Shelter_' + s, (10.6, -6.4, 6.4), 0)
    for px in (-3.5, -1.17, 1.17, 3.5):
        for py in (-2, 2):
            box_collider(r, 10.6 + px, -6.4 + py, 6.4, .32, .32, 3)
    box_collider(r, 10.6, -6.4 + 1.38, 6.4, 5.2, .5, 1)
    box_collider(r, 10.6 - .3, -6.4 - 2.02, 6.4, 2.4, .12, 2.2)
    # Landmarks: walls as thin boxes so the cathedral portal and nave stay enterable.
    box_collider(r, -3, 41, 16, 5.2, 5.2, 22)
    box_collider(r, 58, 31, 1.5, 8.8, 8.8, 17)
    for x0, x1, y0, y1, h in ((3.3, 4.7, 55, 79, 14), (17.3, 18.7, 55, 79, 14), (4, 9.2, 54.2, 55.9, 19), (12.8, 18, 54.2, 55.9, 19),
                              (4, 18, 78.3, 79.7, 14), (3.65, 7.85, 54.65, 58.85, 26), (14.15, 18.35, 54.65, 58.85, 26), (20.5, 25.5, 55.5, 76.5, 9)):
        box_collider(r, (x0 + x1) / 2, (y0 + y1) / 2, 24.6, x1 - x0, y1 - y0, h)
    for x, y in ((7.5, 59), (7.5, 63), (7.5, 67), (7.5, 71), (7.5, 75), (14.5, 59), (14.5, 63), (14.5, 67), (14.5, 71), (14.5, 75)):
        box_collider(r, x, y, 25, .9, .9, 9)
    r.add('SM_V_Fountain_' + s, (-24, 8, SQUARE_Z), 0)
    box_collider(r, -24, 8, SQUARE_Z, 5.2, 5.2, 1.4)
    r.add('SM_V_ClinicFlag', (-8.56, -2.0, street_z(-4) + 6.2), 90)

    # Archways keep the lanes intimate and are the most reused view across eras.
    r.add('SM_V_Archway_' + s, (-4.0, 1.9, street_z(3) + .05), 90, (.84, 1, 1))
    r.add('SM_V_Archway_' + s, (-14.85, 20.0, 12.25), 0)
    r.add('SM_V_Archway_' + s, (-14.85, 28.0, 14.75), 0)
    r.add('SM_V_Archway_' + s, (-20.55, -9.0, 9.55), 0, (1.08, 1, 1))

    # Piers. Present keeps the first bays and loses the end of the main pier.
    for row, bays in ((12.0, 6), (20.0, 3)):
        for i in range(bays):
            if not past and (i >= 4 or (i == 2 and row > 15)):
                continue
            mesh = 'SM_V_Pier_R' if past or (i < 2 and row < 15) else 'SM_V_Pier_D'
            r.add(mesh, (25.0 + i * 3, row, 1.2), 0)
    r.add('SM_V_Crane_' + s, (22.5, 8.0, 1.2), 0)
    box_collider(r, 22.5, 8.0, 1.2, 2, 2, 5)

    fleet = [('Sail', 33, 7.5, 190), ('Sail', 37, 16.5, 80), ('Sail', 46, 4, 150), ('Sail', 62, 8, 200), ('Sail', 74, 42, 110), ('Sail', 41, -18, 230),
             ('Row', 29.5, 9.8, 95), ('Row', 30.5, 14.3, 80), ('Row', 27, 21.5, 100)]
    if past:
        for kind, x, y, yaw in fleet:
            r.add('SM_V_Boat_' + kind, (x, y, .0), yaw)
    else:
        for kind, x, y, yaw in (('Row', 29.5, 9.8, 95), ('Sail', 41, -18, 230), ('Wreck', 34, 16, 70), ('Wreck', 30, 3.5, 140)):
            r.add('SM_V_Boat_' + kind, (x, y, -.15 if kind == 'Wreck' else 0), yaw)

    # Market Square life.
    stalls = [(-31, 3.4, 90), (-31, 12.8, 90), (-17.5, 3.0, 270), (-16.5, 13.2, 270), (-25.5, 14.2, 180), (-24.5, 2.3, 0)]
    for i, (x, y, yaw) in enumerate(stalls):
        if past:
            r.add('SM_V_Stall_R', (x, y, SQUARE_Z), yaw)
            box_collider(r, x, y, SQUARE_Z, 3.2 if yaw % 180 == 0 else 1.9, 1.9 if yaw % 180 == 0 else 3.2, 2.4)
        elif i in (0, 3):
            r.add('SM_V_Stall_D', (x, y, SQUARE_Z), yaw)
            box_collider(r, x, y, SQUARE_Z, 3.2 if yaw % 180 == 0 else 1.9, 1.9 if yaw % 180 == 0 else 3.2, 2.4)
        elif i == 4:
            r.add('SM_V_Stall_R', (x, y, SQUARE_Z), yaw)   # one trader stayed
            box_collider(r, x, y, SQUARE_Z, 3.2, 1.9, 2.4)
    trees = [(-13.8, 1.8), (-34.2, 14), (-33.5, 2.2)]
    group(r, 'SM_V_Olive', [(x, y, SQUARE_Z) for x, y in trees])
    for x, y in trees:
        box_collider(r, x, y, SQUARE_Z, .8, .8, 3)

    # Street edge: the concept's flowers, goods and banners on the sunlit walk.
    if past:
        street = [(-3.5, y) for y in (-23, -16.2, -9.4, -6, -3, 5.4, 9.6, 18.4, 21.2, 26, 29.6)]
        for i, (x, y) in enumerate(street):
            mesh = ('SM_V_Pot', 'SM_V_Crates', 'SM_V_Pot', 'SM_V_Barrels', 'SM_V_Pot', 'SM_V_Amphorae')[i % 6]
            r.add(mesh, (x, y, street_z(y)), rng.uniform(0, 360), (.6, .6, .6) if mesh == 'SM_V_Pot' else (1, 1, 1))
        for y in (-20, -8, 6, 22, 30):
            r.add('SM_V_Banner', (3.1, y, street_z(y) + 1.34), 180)
        for y in (-13, 0, 9.5, 26):
            r.add('SM_V_Pot', (3.1, y, street_z(y) + 1.34), rng.uniform(0, 360), (.45, .45, .45))
        for y in (-5, 10, 24):
            r.add('SM_V_Bunting', (-4, y, street_z(y) + 6.6), 0, (.72, 1, 1))
        r.add('SM_V_Bunting', (-36, 6.5, 17.2), 0, (1.2, 1, 1))
        r.add('SM_V_Bunting', (-36, 12, 17.2), -4, (2.4, 1, 1))
        r.add('SM_V_Bunting', (-36, 3, 16.8), 2, (2.4, 1, 1))
        for x, y, mesh in ((15.5, 9, 'SM_V_Crates'), (14, 4, 'SM_V_Barrels'), (20, 16, 'SM_V_Amphorae'), (17, 13.5, 'SM_V_Crates'), (23.5, 15, 'SM_V_Barrels'), (19, 4, 'SM_V_Crates')):
            r.add(mesh, (x, y, 1.2), rng.uniform(0, 360))
        for x, y, z in ((-8, -1, street_z(-4)), (-6.5, -6.6, street_z(-4)), (-7.8, -3.8, street_z(-4))):
            r.add('SM_V_Crates' if x < -7.9 else 'SM_V_Pot', (x, y, z), rng.uniform(0, 360), (1, 1, 1) if x < -7.9 else (.6, .6, .6))
    else:
        for y in (-22, -2, 21, 28):
            r.add('SM_V_Rubble_%s' % rng.choice('ABC'), (-3.6, y, street_z(y)), rng.uniform(0, 360), (.8, .8, .7))
        for y, mesh in ((-11, 'SM_V_PotBroken'), (7.5, 'SM_V_Sandbags'), (19, 'SM_V_PotBroken'), (31, 'SM_V_Crates')):
            r.add(mesh, (-3.5, y, street_z(y)), rng.uniform(-20, 20))
        for x, y, z, sc in ((-14.5, -6, 9.8, 1.1), (-26, -7, 10.6, 1.4), (-9, 26, 13, 1.2), (-27, 10.8, SQUARE_Z, .7), (-34, 2.4, SQUARE_Z, .8)):
            r.add('SM_V_Rubble_D', (x, y, z), rng.uniform(0, 360), (sc, sc, sc))
        for x, y in ((-3.3, 12.5), (2.2, -24), (2.6, 3), (-3.4, -15), (2.5, 31)):
            r.add('SM_V_WeedPatch', (x, y, street_z(y)), rng.uniform(0, 360), (.8, .8, .8))
        r.add('SM_V_Scaffold', (18.9, 57, 25), 90, (1, 1, 1.5))
        r.add('SM_V_Scaffold', (-4.0, 18, street_z(18)), 90)
        r.add('SM_V_Sandbags', (18, 3.5, 1.2), 20)
        r.add('SM_V_DeadTree', (-13.8, -3, 9.8), 40)
        r.add('SM_V_Cypress', (-32, 6, SQUARE_Z), 0, (.42, .42, .42))    # a sapling grown through the old paving

    # Laundry survives the war: the most human sign in both timelines.
    r.add('SM_V_Laundry', (-14.8, 26.0, 18.5), 0, (.55, 1, 1))
    r.add('SM_V_Laundry', (-20.4, -5.0, 14.2), 0, (.58, 1, 1))
    if past:
        r.add('SM_V_Laundry', (-14.8, 31.5, 20.0), 0, (.55, 1, 1))
        r.add('SM_V_Laundry', (-20.4, -13, 13.4), 0, (.58, 1, 1))

    # Cypresses frame the climb to the cathedral in both eras.
    for x, y, z in ((4.8, 40, 17.2), (5.2, 46, 17.5), (-7, 45.5, 17), (-9, 40.6, 17), (-1, 60, 25), (-1, 66, 25), (-1, 72, 25), (24, 53, 25)):
        r.add('SM_V_Cypress' if int(y) % 2 else 'SM_V_CypressB', (x, y, z), rng.uniform(0, 360))
        box_collider(r, x, y, z, .7, .7, 3)
    r.add('SM_V_Pine', (13.5, -11.5, 6.4), 0, (.9, .9, .9))
    box_collider(r, 13.5, -11.5, 6.4, .6, .6, 3)

    for x, y, z, yaw in ((-3.6, -12.9, street_z(-13), 0), (9, 1.2, 6.4, 0), (-12, 1.4, SQUARE_Z, 0), (1.6, 45.2, 17.5, 0), (23, 3, 1.2, 0)):
        r.add('SM_V_Lantern_Post', (x, y, z), yaw)
    r.add('SM_V_Bench', (10.6, -12, 6.4), 0)
    r.add('SM_V_Bench', (-6.4, -3, street_z(-4)), 90)

def resolve(era):
    r = Resolver(era)
    for b in BUILDINGS:
        r.building(b)
    dress_city(r)
    return r


# ---- Story-map variant ----------------------------------------------------------------------
# The story map /Game/Quest/Maps/Verdant_Desktop keeps its own family home (origin (-8, -13, 8.96) m,
# plinth x -11.9..-1.97, y -17.94..-7.4, floor 10.11 m, collapsed wing to y -6.89). The Verdant
# FamilyHome stand-in, its forecourt pieces and every instance inside the plinth box are left out,
# and the clinic block becomes two bays starting 1.8 m clear of the ruined wing (its door keeps the
# same place). The land meshes are not rebuilt: the baked pads stay under the house plinth.
STORY_EXCLUDE = [(-14.2, -1.9, -18.1, -7.3)]   # x0, x1, y0, y1 in metres


def story_variant():
    global BUILDINGS, SURFACES, STAIRS
    BUILDINGS = [b for b in BUILDINGS if b.name != 'FamilyHome']
    for index, b in enumerate(BUILDINGS):
        if b.name == 'ClinicBlock':
            BUILDINGS[index] = Building('ClinicBlock', -8.6, -5.1, WEST, 2, 3, 2, z=street_z(-4), front={0: 'OW', 1: 'WW'}, tint=3, paint=1,
                                        damage=collapse(1.0, 7, 3.6, .55), cared=True)
    SURFACES = [s for s in SURFACES if s['name'] != 'HomeCourt']
    STAIRS = [s for s in STAIRS if s['name'] != 'HomeSteps']


def excluded(point, boxes=STORY_EXCLUDE):
    return any(x0 <= point[0] <= x1 and y0 <= point[1] <= y1 for x0, x1, y0, y1 in boxes)


def write(variant=None):
    out = Path(__file__).resolve().parent.parent / 'output' / 'verdant'
    if variant == 'story':
        story_variant()
    payload = {}
    for era in ('Past', 'Present'):
        r = resolve(era)
        items, colliders = r.items, r.colliders
        if variant == 'story':
            items = [row for row in items if not excluded(row['p'])]
            colliders = [row for row in colliders if not excluded(row['center'])]
        payload[era] = {'instances': items, 'colliders': colliders}
    payload['surfaces'] = SURFACES
    payload['stairs'] = STAIRS
    payload['mole'] = {'points': MOLE, 'width': MOLE_WIDTH}
    payload['blockers'] = BLOCKERS
    payload['buildings'] = [{'name': b.name, 'x': b.x, 'y': b.y, 'yaw': b.yaw, 'w': b.w, 'd': b.d, 'floors': b.floors, 'z': b.z} for b in BUILDINGS]
    if variant == 'story':
        payload['variant'] = {'name': 'story', 'exclude_boxes_m': STORY_EXCLUDE, 'removed_buildings': ['FamilyHome'],
                              'changed_buildings': ['ClinicBlock: 2 bays at y -5.1 (front OW: open entrance SM_V_Story_DoorOpen_R in the past, kit door in the present), door position unchanged'],
                              'removed_surfaces': ['HomeCourt'], 'removed_stairs': ['HomeSteps'], 'land_meshes_rebuilt': False}
    name = 'plan_story.json' if variant == 'story' else 'plan.json'
    (out / name).write_text(json.dumps(payload), encoding='utf-8')
    for era in ('Past', 'Present'):
        print(name, era, len(payload[era]['instances']), 'instances', len(payload[era]['colliders']), 'colliders', flush=True)


if __name__ == '__main__':
    import sys
    write('story' if 'story' in sys.argv[1:] else None)
