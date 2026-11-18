"""Replaces the engine-primitive story sets of the merged Verdant_Desktop with story-set meshes.

Run with -VerdantPolishStorySets in the full editor, after verdant_import.py -VerdantMeshesOnly
-VerdantMeshFilter=SM_V_Story_ has imported the meshes (one Unreal writer at a time):
    verdant/run_unreal.ps1 -Script verdant_polish_story_sets.py -NoRender -UserDir <short dir> -Flags @('-VerdantPolishStorySets')

Every story actor keeps its name, tags, location, rotation, collision settings and manager references;
only its static mesh, scale and material overrides change (the mesh was modelled at the primitive's size
with the pivot at the primitive's centre). Composite primitives keep one carrier actor and the other
members are made invisible (component visibility, nothing deleted, arrays untouched). New dressing
actors (ruined frames in the present, notice board, luggage, shelf, stock in the past) are tagged
Verdant.StorySet + Opening.PastOnly / Opening.PresentOnly + Opening.Decorative and appended to the
manager's era arrays, exactly as the story's own props are wired. Re-running removes its own dressing
actors first. The map is backed up under validation/verdant_merge/<stamp>/ before anything changes.
"""
import hashlib
import json
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc
import verdant_materials as vm

FLAG = 'VerdantPolishStorySets'
MAP = '/Game/Quest/Maps/Verdant_Desktop'
MAP_FILE = vc.PROJECT / 'Content/Quest/Maps/Verdant_Desktop.umap'
STORY = vc.ROOT_PATH + '/Meshes/SM_V_Story_'
SET_TAG = 'Verdant.StorySet'
PAST, PRESENT, BLOCKING, DECOR = 'Opening.PastOnly', 'Opening.PresentOnly', 'Opening.Blocking', 'Opening.Decorative'
WATCH_FACE = '/Game/Opening/Materials/M_OpeningWatchFace'
INK = '/Game/Opening/Materials/M_OpeningInk'
CASE_GLASS = vc.ROOT_PATH + '/Materials/M_V_Story_Glass'   # see-through pane for the civic cases (the kit glass is opaque)
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
OUT = vc.PROJECT / 'validation' / 'verdant_merge' / STAMP
KEEP = 'keep0'   # the actor's current material 0 moves to that slot of the new mesh

# actor name -> (label prefix, mesh suffix, scale, {slot label: material})
SWAP = {
    # Clinic courtyard set
    'StaticMeshActor_95': ('Opening - Courtyard awning post', 'AwningPost', (1, 1, 1), {}),
    'StaticMeshActor_96': ('Opening - Courtyard awning post', 'AwningPost', (1, 1, 1), {}),
    'StaticMeshActor_97': ('Opening - Courtyard awning post', 'AwningPost', (1, 1, 1), {}),
    'StaticMeshActor_98': ('Opening - Courtyard awning post', 'AwningPost', (1, 1, 1), {}),
    'StaticMeshActor_99': ('Opening - Courtyard awning rail', 'Beam', (1.9, .625, .625), {}),
    'StaticMeshActor_100': ('Opening - Courtyard awning rail', 'Beam', (1.9, .625, .625), {}),
    'StaticMeshActor_101': ('Opening - Installed clinic courtyard canvas', 'CanvasCover', (1, 1, 1), {}),
    'StaticMeshActor_102': ('Opening - Clinic courtyard table', 'TableTop', (1, 1, 1), {}),
    'StaticMeshActor_103': ('Opening - Clinic table leg', 'Trestle', (1, 1, 1), {}),
    'StaticMeshActor_104': ('Opening - Clinic table leg', 'Trestle', (1, 1, 1), {}),
    'StaticMeshActor_105': ('Opening - Clinic linen delivery tray', 'LinenTray', (1, 1, 1), {}),
    'StaticMeshActor_106': ('Opening - Clinic water table', 'SideTable', (1, 1, 1), {}),
    'StaticMeshActor_107': ('Opening - Clinic water jug', 'Jug', (1, 1, 1), {}),
    'StaticMeshActor_108': ('Opening - Clinic drinking cup', 'Cup', (1, 1, 1), {}),
    'StaticMeshActor_109': ('Opening - Clinic awning fixing', 'Fixing', (1, 1, 1), {'Iron': KEEP}),
    'StaticMeshActor_110': ('Opening - Clinic repair strap', 'Strap', (1, 1, 1), {}),
    # Sela's shop
    'StaticMeshActor_111': ('Opening - Store canvas support', 'AwningPost', (1, 1, .984), {}),
    'StaticMeshActor_112': ('Opening - Store canvas support', 'AwningPost', (1, 1, .984), {}),
    'StaticMeshActor_113': ('Opening - Store shade', 'Shade', (1, 1, 1), {}),
    'StaticMeshActor_114': ('Opening - Storekeeper counter', 'Counter', (1, 1, 1), {}),
    'StaticMeshActor_115': ('Opening - Wrapped clinic linen', 'LinenParcel', (1, 1, 1), {}),
    'StaticMeshActor_117': ('Opening - Reinforced waterproof canvas', 'CanvasRoll', (1, 1, 1), {}),
    'StaticMeshActor_118': ('Opening - Supplied repair straps', 'Fasteners', (1, 1, 1), {}),
    # Harbour waiting shelter
    'StaticMeshActor_119': ('Opening - Harbor waiting shelter post', 'AwningPost', (1.1, 1.1, 1), {}),
    'StaticMeshActor_120': ('Opening - Harbor waiting shelter post', 'AwningPost', (1.1, 1.1, 1), {}),
    'StaticMeshActor_121': ('Opening - Harbor waiting shelter post', 'AwningPost', (1.1, 1.1, 1), {}),
    'StaticMeshActor_122': ('Opening - Harbor waiting shelter post', 'AwningPost', (1.1, 1.1, 1), {}),
    'StaticMeshActor_123': ('Opening - Harbor waiting shelter rail', 'Beam', (1.9, .75, .75), {}),
    'StaticMeshActor_124': ('Opening - Harbor waiting shelter rail', 'Beam', (1.9, .75, .75), {}),
    'StaticMeshActor_125': ('Opening - Installed harbor waiting cover', 'CanvasCover', (.976, 1.085, 1), {}),
    'StaticMeshActor_126': ('Opening - Harbor waiting bench', 'WaitingBench', (1, 1, 1), {}),
    'StaticMeshActor_127': ('Opening - Departure clerk table', 'ClerkDesk', (1, 1, 1), {}),
    'StaticMeshActor_128': ('Opening - Harbor shelter fixing', 'Fixing', (1.2, 1, 1.14), {'Iron': KEEP}),
    # Memorial, chronology, gate
    'StaticMeshActor_63': ('Opening - Historical display', 'DisplayCase', (1, 1, 1), {'Glass': CASE_GLASS}),
    'StaticMeshActor_82': ('Opening - Preserved clinic register page', 'RecordPage', (1, 1, 1), {'Banner': KEEP}),
    'StaticMeshActor_83': ('Opening - Preserved departure page', 'RecordPage', (1, 1, 1), {'Banner': KEEP}),
    'StaticMeshActor_199': ('Public chronology', 'NoticeCase', (1, 1, 1), {'Glass': CASE_GLASS}),
    'StaticMeshActor_44': ('Opening - Courtyard gate post', 'GatePost', (1, 1, 1), {}),
    'StaticMeshActor_45': ('Opening - Courtyard gate post', 'GatePost', (1, 1, 1), {}),
    'StaticMeshActor_46': ('Opening - Repaired courtyard gate lintel', 'BeamY', (1.25, 4.06, 1.25), {}),
    # Family room and courtyard
    'StaticMeshActor_18': ('Opening - Family photograph', 'PhotoFrame', (1, 1, 1), {'Banner': KEEP}),
    'StaticMeshActor_21': ('Opening - Personal letter', 'Letter', (1, 1, 1), {'Banner': KEEP}),
    'StaticMeshActor_22': ('Opening - Chronowatch workbench', 'Chronowatch', (1, 1, 1), {'Iron': KEEP, 'Flat': WATCH_FACE, 'Paint': INK}),
    'StaticMeshActor_27': ('Opening - Shallow contact dish', 'Dish', (1, 1, 1), {'Flat': KEEP}),
    'StaticMeshActor_34': ('Opening - Prepared watch contact', 'Contact', (1, 1, 1), {'Iron': KEEP}),
    'StaticMeshActor_36': ('Opening - Home time anchor', 'AnchorDial', (1, 1, 1), {'Iron': KEEP, 'Flat': INK}),
    'StaticMeshActor_35': ('Opening - Time anchor stone', 'AnchorStone', (1, 1, 1), {}),
    'StaticMeshActor_38': ('Opening - Ruin barricade timber', 'Beam', (1.93, 1, 1), {}),
    'StaticMeshActor_39': ('Opening - Ruin barricade timber', 'Beam', (1.93, 1, 1), {}),
    'StaticMeshActor_40': ('Opening - Ruin barricade timber', 'Beam', (1.94, 1.06, .94), {}),
    'StaticMeshActor_41': ('Opening - Ruin barricade timber', 'Beam', (2.42, .81, .81), {}),
    'StaticMeshActor_42': ('Opening - Ruin barricade timber', 'Beam', (2.42, .81, .81), {}),
    'StaticMeshActor_139': ('Opening - Past family home closed door', 'PlankDoor', (1, 1, 1), {}),
    'StaticMeshActor_130': ('Opening - Past intact family plaster', 'PlasterPanel', (1, .64, 3.07), {}),
    'StaticMeshActor_131': ('Opening - Past intact family plaster', 'PlasterPanel', (1, .9, 3.07), {}),
    'StaticMeshActor_132': ('Opening - Past intact family plaster', 'PlasterPanel', (1, 1.21, .46), {}),
    'StaticMeshActor_133': ('Opening - Past intact family plaster', 'PlasterPanel', (1, 1.21, .85), {}),
    'StaticMeshActor_134': ('Opening - Past intact family plaster', 'PlasterPanel', (1, 2.95, 2.03), {}),
    'StaticMeshActor_129': ('Opening - Past intact family roof', 'WingRoof', (1, 1, 1), {}),
}
# Members of composite primitives whose role the carrier mesh now plays: made invisible, nothing else.
HIDE = {
    'StaticMeshActor_85': 'clinic threshold slab (the Verdant clinic court is the floor; collision kept, buried)',
    'StaticMeshActor_86': 'clinic plaster back wall (the Verdant clinic block is the building)',
    'StaticMeshActor_87': 'clinic side wall', 'StaticMeshActor_89': 'clinic side wall',
    'StaticMeshActor_88': 'clinic blue shutter (the Verdant block has shutters)', 'StaticMeshActor_90': 'clinic blue shutter',
    'StaticMeshActor_91': 'clinic door jamb (the open entrance is the Verdant block door bay)', 'StaticMeshActor_92': 'clinic door jamb',
    'StaticMeshActor_93': 'clinic door lintel', 'StaticMeshActor_94': 'clinic tile roof',
    'StaticMeshActor_116': 'linen wrap band (modelled on the parcel)',
    'StaticMeshActor_55': 'memorial leg (modelled on the display case)', 'StaticMeshActor_62': 'memorial leg',
    'StaticMeshActor_71': 'memorial recess', 'StaticMeshActor_77': 'memorial recess',
    'StaticMeshActor_73': 'memorial frame bar', 'StaticMeshActor_74': 'memorial frame bar', 'StaticMeshActor_75': 'memorial frame bar',
    'StaticMeshActor_76': 'memorial frame bar', 'StaticMeshActor_78': 'memorial frame bar', 'StaticMeshActor_79': 'memorial frame bar',
    'StaticMeshActor_80': 'memorial frame bar', 'StaticMeshActor_81': 'memorial frame bar',
    'StaticMeshActor_84': 'memorial plaque strip (modelled on the display case)',
    'StaticMeshActor_23': 'watch dial (modelled on the Chronowatch)', 'StaticMeshActor_24': 'watch hand',
    'StaticMeshActor_25': 'watch strap', 'StaticMeshActor_26': 'watch strap',
    'StaticMeshActor_29': 'dish rim (modelled on the dish)', 'StaticMeshActor_30': 'dish rim', 'StaticMeshActor_31': 'dish rim', 'StaticMeshActor_32': 'dish rim',
    'StaticMeshActor_37': 'anchor dial marking (engraved on the dial)',
}
# New dressing: (label, mesh suffix, era, location cm, yaw, scale)
DRESSING = [
    ('Story set - Shelter notice board', 'NoticeBoard', PAST, (300, -660, 1086), 180, (1, 1, 1)),
    ('Story set - Traveller luggage', 'Luggage', PAST, (160, -735, 1093.5), 25, (1, 1, 1)),
    ('Story set - Clinic shelf', 'Shelf', PAST, (-857, 230, 1092), 90, (1, 1, 1)),
    ('Story set - Shop stock', 'Stock', PAST, (225, -160, 1036), -15, (1, 1, 1)),
    ('Story set - Ruined clinic awning frame', 'RuinFrame', PRESENT, (-185, 505, 969.5), 0, (1, 1, 1)),
    ('Story set - Ruined shelter frame', 'RuinFrame', PRESENT, (190, -650, 1085), 0, (.95, 1.087, 1)),
]
REPORT = {'success': False, 'run': STAMP, 'map': MAP, 'swapped': [], 'hidden': [], 'dressing': [], 'warnings': [],
          'rules': 'story actors keep name, tags, transform (except scale), collision and references; composite members only lose '
                   'visibility; dressing actors are new, tagged Verdant.StorySet and wired through the manager arrays'}


def long(path):
    value = str(Path(path))
    return Path(value if value.startswith('\\\\?\\') else '\\\\?\\' + value)


def sha(path):
    return hashlib.sha256(long(path).read_bytes()).hexdigest()


def tags_of(actor):
    return [str(t) for t in actor.get_editor_property('tags')]


def enum_name(value):
    return str(value).split('.')[-1].split(':')[0]


def collision_state(component):
    """The component's own collision set-up (the effective value also folds in the actor flag)."""
    body = component.get_editor_property('body_instance')
    return {'effective': enum_name(component.get_collision_enabled()), 'own': enum_name(body.get_editor_property('collision_enabled')),
            'profile': str(body.get_editor_property('collision_profile_name')),
            'visibility': enum_name(component.get_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY)),
            'pawn': enum_name(component.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN)),
            'world_static': enum_name(component.get_collision_response_to_channel(unreal.CollisionChannel.ECC_WORLD_STATIC))}


def restore_collision(component, state):
    """Re-applies the recorded set-up: SetStaticMesh may take the new mesh's default collision instead."""
    try:
        component.set_editor_property('use_default_collision', False)
    except Exception:
        pass
    if state['profile'] not in ('', 'Custom', 'None'):
        component.set_collision_profile_name(state['profile'])
    component.set_collision_enabled(getattr(unreal.CollisionEnabled, state['own']))
    if state['own'] == 'QUERY_ONLY' and state['visibility'] == 'ECR_BLOCK' and state['pawn'] == 'ECR_IGNORE':
        component.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
        component.set_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY, unreal.CollisionResponseType.ECR_BLOCK)
    elif state['own'] == 'NO_COLLISION':
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)


def component_state(component):
    mesh = component.get_editor_property('static_mesh')
    return {'mesh': mesh.get_path_name() if mesh else None, 'visible': bool(component.is_visible()),
            'collision': collision_state(component),
            'materials': [component.get_material(i).get_path_name() if component.get_material(i) else None for i in range(component.get_num_materials())]}


def slot_index(mesh, label):
    for index, slot in enumerate(mesh.get_editor_property('static_materials')):
        if str(slot.get_editor_property('material_slot_name')) == 'M_V_' + label:
            return index
    raise RuntimeError('Mesh %s has no slot M_V_%s' % (mesh.get_name(), label))


def swap(actor, suffix, scale, slots):
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    vc.require(component is not None, 'No static mesh component on ' + actor.get_name())
    before = {'component': component_state(component), 'scale': list(actor.get_actor_scale3d().to_tuple()),
              'location': list(actor.get_actor_location().to_tuple()), 'hidden': bool(actor.get_editor_property('hidden')),
              'actor_collision': bool(actor.get_actor_enable_collision()), 'tags': tags_of(actor)}
    keep = component.get_material(0)
    mesh = unreal.load_asset(STORY + suffix)
    vc.require(mesh is not None, 'Story mesh missing: ' + STORY + suffix)
    component.set_editor_property('override_materials', [])
    vc.require(component.set_static_mesh(mesh), 'set_static_mesh refused on ' + actor.get_name())
    restore_collision(component, before['component']['collision'])
    actor.set_actor_scale3d(unreal.Vector(*scale))
    for label, source in slots.items():
        material = keep if source == KEEP else unreal.load_asset(source)
        vc.require(material is not None, 'Material missing for %s slot %s: %s' % (actor.get_name(), label, source))
        component.set_material(slot_index(mesh, label), material)
    after = {'component': component_state(component), 'scale': list(actor.get_actor_scale3d().to_tuple()),
             'location': list(actor.get_actor_location().to_tuple()), 'hidden': bool(actor.get_editor_property('hidden')),
             'actor_collision': bool(actor.get_actor_enable_collision()), 'tags': tags_of(actor)}
    same = (after['location'] == before['location'] and after['tags'] == before['tags'] and after['hidden'] == before['hidden']
            and after['actor_collision'] == before['actor_collision']
            and all(after['component']['collision'][k] == before['component']['collision'][k] for k in ('effective', 'own', 'visibility', 'pawn', 'world_static')))
    vc.require(same, 'A swap changed more than mesh, scale and materials on %s: before %s after %s' % (actor.get_name(), before['component']['collision'], after['component']['collision']))
    return before, after


def main():
    started = time.monotonic()
    vc.require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), FLAG), 'Explicit -' + FLAG + ' required')
    vc.require(not vc.levels.is_in_play_in_editor(), 'Exit PIE first')
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT['backup'] = {'file': str(OUT / 'Verdant_Desktop.umap.before_polish'), 'sha256': sha(MAP_FILE)}
    shutil.copyfile(long(MAP_FILE), long(OUT / 'Verdant_Desktop.umap.before_polish'))
    REPORT['materials'] = [vm.story_glass().get_path_name()]
    vc.require(vc.levels.load_level(MAP), 'Cannot load ' + MAP)
    actors = list(vc.actors.get_all_level_actors())
    manager = next((a for a in actors if a.actor_has_tag('Opening.Manager')), None)
    vc.require(manager is not None, 'No Opening.Manager')
    by_name = {a.get_name(): a for a in actors}

    previous = [a for a in actors if a.actor_has_tag(SET_TAG)]
    if previous:
        names = {a.get_name() for a in previous}
        for field in ('PastActors', 'PresentActors'):
            manager.set_editor_property(field, [a for a in manager.get_editor_property(field) if a.get_name() not in names])
        for actor in previous:
            vc.actors.destroy_actor(actor)
        REPORT['previous_dressing_removed'] = len(previous)

    for name, (label, suffix, scale, slots) in SWAP.items():
        actor = by_name.get(name)
        if actor is None or not actor.get_actor_label().startswith(label):
            REPORT['warnings'].append('Expected story actor missing or relabelled: %s (%s)' % (name, label))
            continue
        before, after = swap(actor, suffix, scale, slots)
        REPORT['swapped'].append({'name': name, 'label': actor.get_actor_label(), 'mesh': 'SM_V_Story_' + suffix, 'before': before, 'after': after})
    for name, reason in HIDE.items():
        actor = by_name.get(name)
        if actor is None:
            REPORT['warnings'].append('Expected composite member missing: ' + name)
            continue
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        before = component_state(component)
        component.set_visibility(False, True)
        REPORT['hidden'].append({'name': name, 'label': actor.get_actor_label(), 'reason': reason, 'before': before, 'after': component_state(component)})

    past_add, present_add = [], []
    for label, suffix, era, location, yaw, scale in DRESSING:
        mesh = unreal.load_asset(STORY + suffix)
        vc.require(mesh is not None, 'Story mesh missing: ' + suffix)
        actor = vc.actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*location), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
        actor.set_actor_label(label)
        actor.set_actor_scale3d(unreal.Vector(*scale))
        component = actor.static_mesh_component
        component.set_static_mesh(mesh)
        component.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        actor.set_actor_enable_collision(False)
        actor.set_editor_property('tags', [unreal.Name(t) for t in (SET_TAG, era, DECOR)])
        actor.set_folder_path('Verdant/StorySets')
        actor.set_actor_hidden_in_game(era == PAST)     # the saved era is the present, as for every story prop
        (past_add if era == PAST else present_add).append(actor)
        REPORT['dressing'].append({'name': actor.get_name(), 'label': label, 'mesh': 'SM_V_Story_' + suffix, 'era': era, 'location': list(location), 'yaw': yaw, 'scale': list(scale)})
    for field, added in (('PastActors', past_add), ('PresentActors', present_add)):
        values = list(manager.get_editor_property(field))
        manager.set_editor_property(field, values + added)
        REPORT.setdefault('arrays', {})[field] = {'before': len(values), 'after': len(values) + len(added)}
    vc.require(vc.levels.save_current_level(), 'Cannot save ' + MAP)
    REPORT['after_sha256'] = sha(MAP_FILE)
    REPORT['counts'] = {'swapped': len(REPORT['swapped']), 'hidden': len(REPORT['hidden']), 'dressing': len(REPORT['dressing'])}
    REPORT['seconds'] = round(time.monotonic() - started, 1)
    REPORT['success'] = not REPORT['warnings']


try:
    main()
except Exception:
    REPORT['error'] = traceback.format_exc()
    unreal.log_error(REPORT['error'])
vc.write_json(OUT / 'polish_report.json', REPORT)
vc.write_json(vc.EVIDENCE / 'polish_story_sets_report.json', REPORT)
vc.log('polish', json.dumps({k: REPORT.get(k) for k in ('success', 'counts', 'seconds', 'warnings', 'error')})[:900], str(OUT))
unreal.SystemLibrary.quit_editor()
