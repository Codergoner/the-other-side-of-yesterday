"""Collision clearances on the merged story map (additive, recorded, reversible).

Run with -VerdantStoryClearances in the full editor (one Unreal writer at a time):
    verdant/run_unreal.ps1 -Script verdant_story_clearances.py -NoRender -UserDir <short dir> -Flags @('-VerdantStoryClearances')

1. Boundary blockers. The 17 shared `Verdant_Blocker` boxes replaced the old promenade rail and parapets
   (open work that rays passed between). As solid boxes they also stopped the Visibility channel, which the
   manager's target query and the VR gaze ray use, so a standing point beyond the street edge could not
   select a story actor on the street (the identity suite's harbour clerk). Their Visibility response is
   now Ignore (`verdant_build_map.pass_rays`, the same call the builder uses for new blockers, which also
   switches off "use default collision" so the override survives a level load); every other response, the
   transform and the tags stay as they were, and the job refuses to save if anything else changed.
   `-VerdantStoryClearancesVerify` is the read-only check of the saved state in a fresh editor.
2. Read-only audits written to the report: editor-world visibility traces from the harness's approach
   positions to the harbour clerk before and after the change, and where every `Quest.Teleport` landing
   lies relative to the Verdant invisible colliders of both eras (the `market_arcade` landing lies inside
   the ArcadeSouth building volume; nothing is moved or carved for it).

The map is backed up under validation/verdant_merge/<stamp>/ before anything changes.
"""
import hashlib
import json
import math
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc
import verdant_build_map as vbm

FLAG = 'VerdantStoryClearances'
MAP = '/Game/Quest/Maps/Verdant_Desktop'
MAP_FILE = vc.PROJECT / 'Content/Quest/Maps/Verdant_Desktop.umap'
OWNER = 'Verdant.StoryOwned'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
OUT = vc.PROJECT / 'validation' / 'verdant_merge' / STAMP
CH = unreal.CollisionChannel
CHANNELS = {'visibility': CH.ECC_VISIBILITY, 'camera': CH.ECC_CAMERA, 'pawn': CH.ECC_PAWN, 'world_static': CH.ECC_WORLD_STATIC,
            'world_dynamic': CH.ECC_WORLD_DYNAMIC, 'physics_body': CH.ECC_PHYSICS_BODY}
# The identity suite's approach positions around the harbour clerk, as its failing record logged them
# (camera, target), and the clerk's authored harbour point.
CLERK_RAYS = [
    ('east_80', (396.518, -469.76, 1069.914), (191.412, -556.478, 1154.293)),
    ('east_0', (408.456, -554.902, 1024.253), (191.434, -556.478, 1154.303)),
    ('east_-80', (396.586, -640.077, 1027.331), (191.377, -556.478, 1154.272)),
]
REPORT = {'success': False, 'run': STAMP, 'map': MAP, 'blockers': [], 'warnings': [],
          'rules': 'only the Visibility response of the 17 shared boundary blockers changes; nothing is moved, scaled, retagged or deleted'}


def long(path):
    value = str(Path(path))
    return Path(value if value.startswith('\\\\?\\') else '\\\\?\\' + value)


def sha(path):
    return hashlib.sha256(long(path).read_bytes()).hexdigest()


def tags_of(actor):
    return [str(t) for t in actor.get_editor_property('tags')]


def enum_name(value):
    return str(value).split('.')[-1].split(':')[0]


def collision_row(component):
    body = component.get_editor_property('body_instance')
    try:
        default = bool(component.get_editor_property('use_default_collision'))
    except Exception:
        default = None
    row = {'enabled': enum_name(component.get_collision_enabled()), 'profile': str(body.get_editor_property('collision_profile_name')),
           'use_default_collision': default}
    for key, channel in CHANNELS.items():
        row[key] = enum_name(component.get_collision_response_to_channel(channel))
    return row


def trace(world, start, end):
    hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(*start), unreal.Vector(*end), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                 False, [], unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return {'hit': False}
    row = hit.to_tuple()
    if not row[0]:
        return {'hit': False}
    actor = row[9]
    point = row[4]
    return {'hit': True, 'actor': actor.get_name() if actor else None, 'label': actor.get_actor_label() if actor else None,
            'tags': tags_of(actor)[:6] if actor else [], 'distance_cm': round(math.dist(start, (point.x, point.y, point.z)), 1)}


def ray_audit(world):
    rows = []
    for name, start, target in CLERK_RAYS:
        d = [target[i] - start[i] for i in range(3)]
        length = math.sqrt(sum(v * v for v in d))
        end = tuple(start[i] + d[i] / length * 900.0 for i in range(3))
        row = {'position': name, 'camera_cm': list(start), 'target_cm': list(target), 'target_distance_cm': round(length, 1)}
        row.update(trace(world, start, end))
        rows.append(row)
    return rows


def inside(actor, point, margin):
    """Point against the oriented box of a 100 cm cube actor, grown by margin on the horizontal axes."""
    location, scale = actor.get_actor_location(), actor.get_actor_scale3d()
    yaw = math.radians(actor.get_actor_rotation().yaw)
    dx, dy, dz = point[0] - location.x, point[1] - location.y, point[2] - location.z
    lx = dx * math.cos(yaw) + dy * math.sin(yaw)
    ly = -dx * math.sin(yaw) + dy * math.cos(yaw)
    return abs(lx) <= scale.x * 50 + margin and abs(ly) <= scale.y * 50 + margin and abs(dz) <= scale.z * 50


def landing_audit(actors):
    colliders = [a for a in actors if OWNER in tags_of(a) and a.get_actor_label().startswith('Verdant_Collider_')]
    rows = []
    for landing in sorted((a for a in actors if 'Quest.Teleport' in tags_of(a)), key=lambda a: a.get_actor_label()):
        point = landing.get_actor_location().to_tuple()
        row = {'landing': landing.get_actor_label(), 'name': landing.get_name(), 'location_cm': [round(v, 1) for v in point], 'inside_colliders': []}
        for collider in colliders:
            if inside(collider, point, 34.0):
                tags = tags_of(collider)
                row['inside_colliders'].append({'name': collider.get_name(), 'label': collider.get_actor_label(),
                                                'era': 'Past' if 'Opening.PastOnly' in tags else 'Present' if 'Opening.PresentOnly' in tags else 'Shared',
                                                'location_cm': [round(v, 1) for v in collider.get_actor_location().to_tuple()],
                                                'scale': [round(v, 2) for v in collider.get_actor_scale3d().to_tuple()],
                                                'yaw': round(collider.get_actor_rotation().yaw, 1)})
        rows.append(row)
    return rows


def verify(blockers, world):
    """Read-only: the saved state of every blocker as a freshly loaded editor sees it, plus the ray audit."""
    for actor in blockers:
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        REPORT['blockers'].append({'name': actor.get_name(), 'state': collision_row(component)})
    REPORT['verified_ignore'] = all(r['state']['visibility'] == 'ECR_IGNORE' and r['state']['use_default_collision'] is False for r in REPORT['blockers'])
    REPORT['clerk_rays'] = ray_audit(world)
    REPORT['success'] = REPORT['verified_ignore'] and not REPORT['warnings']


def main():
    started = time.monotonic()
    command = unreal.SystemLibrary.get_command_line()
    verify_only = unreal.SystemLibrary.parse_param(command, FLAG + 'Verify')
    vc.require(verify_only or unreal.SystemLibrary.parse_param(command, FLAG), 'Explicit -' + FLAG + ' required')
    vc.require(not vc.levels.is_in_play_in_editor(), 'Exit PIE first')
    OUT.mkdir(parents=True, exist_ok=True)
    if not verify_only:
        REPORT['backup'] = {'file': str(OUT / 'Verdant_Desktop.umap.before_clearance'), 'sha256': sha(MAP_FILE)}
        shutil.copyfile(long(MAP_FILE), long(OUT / 'Verdant_Desktop.umap.before_clearance'))
    REPORT['mode'] = 'verify (read-only, nothing saved)' if verify_only else 'write'
    REPORT['map_sha256_at_start'] = sha(MAP_FILE)
    vc.require(vc.levels.load_level(MAP), 'Cannot load ' + MAP)
    world = vc.editor.get_editor_world()
    actors = list(vc.actors.get_all_level_actors())
    blockers = sorted((a for a in actors if OWNER in tags_of(a) and a.get_actor_label() == 'Verdant_Blocker'), key=lambda a: a.get_name())
    REPORT['blocker_count'] = len(blockers)
    if len(blockers) != 17:
        REPORT['warnings'].append('Expected 17 shared blockers, found %d' % len(blockers))
    if verify_only:
        verify(blockers, world)
        REPORT['seconds'] = round(time.monotonic() - started, 1)
        return
    REPORT['clerk_rays_before'] = ray_audit(world)
    for actor in blockers:
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        before = collision_row(component)
        location, scale = [round(v, 2) for v in actor.get_actor_location().to_tuple()], [round(v, 3) for v in actor.get_actor_scale3d().to_tuple()]
        tags = tags_of(actor)
        vbm.pass_rays(component)
        after = collision_row(component)
        changed = sorted(k for k in before if before[k] != after[k])
        vc.require(set(changed) <= {'visibility', 'profile', 'use_default_collision'} and after['visibility'] == 'ECR_IGNORE'
                   and after['use_default_collision'] is False and after['enabled'] == before['enabled']
                   and all(after[k] == before[k] for k in CHANNELS if k != 'visibility'),
                   'Clearance changed more than the Visibility response on %s: %s -> %s' % (actor.get_name(), before, after))
        vc.require([round(v, 2) for v in actor.get_actor_location().to_tuple()] == location and
                   [round(v, 3) for v in actor.get_actor_scale3d().to_tuple()] == scale and tags_of(actor) == tags, 'Blocker moved or retagged: ' + actor.get_name())
        REPORT['blockers'].append({'name': actor.get_name(), 'location_cm': location, 'scale': scale, 'changed': changed, 'before': before, 'after': after})
    REPORT['clerk_rays_after'] = ray_audit(world)
    REPORT['landings'] = landing_audit(actors)
    vc.require(vc.levels.save_current_level(), 'Cannot save ' + MAP)
    REPORT['after_sha256'] = sha(MAP_FILE)
    REPORT['seconds'] = round(time.monotonic() - started, 1)
    REPORT['success'] = not REPORT['warnings']


try:
    main()
except Exception:
    REPORT['error'] = traceback.format_exc()
    unreal.log_error(REPORT['error'])
vc.write_json(OUT / ('clearance_verify.json' if REPORT.get('mode', '').startswith('verify') else 'clearance_report.json'), REPORT)
vc.write_json(vc.EVIDENCE / 'story_clearances_report.json', REPORT)
vc.log('clearances', json.dumps({k: REPORT.get(k) for k in ('success', 'blocker_count', 'seconds', 'warnings', 'error')})[:900], str(OUT))
unreal.SystemLibrary.quit_editor()
