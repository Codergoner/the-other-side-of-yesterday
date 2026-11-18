"""Merges the generated two-era Verdant city onto the story map /Game/Quest/Maps/Verdant_Desktop.

Run with -VerdantMergeStoryMap in the full editor (one Unreal writer at a time):
    verdant/run_unreal.ps1 -Script verdant_merge_story_map.py -NoRender -UserDir <short dir> -Flags @('-VerdantMergeStoryMap')

What it does, in order:
  1. Backs up Verdant_Desktop.umap under validation/verdant_merge/<stamp>/ and records its SHA-256.
  2. Hides the audited development scenery (explicit list below: the inherited Harbor city meshes, the
     Quest sky dome / ridges / district dressing / teleport landings, the Brief street dressing on the old
     houses, the past roof caps of the old houses) with their collision disabled; the old sun, skylight
     and fog are switched off and the old exposure volume disabled. Nothing is deleted; every change is
     recorded with its previous state so the backup or the record can restore it.
  3. Adds the Verdant content from output/verdant/plan_story.json additively (HISM components, landmarks,
     ground, sea, sky domes, per-era sun / fog / cubemap skylight, colliders, blockers, vegetation, one
     exposure volume). Era actors carry the story's own tags Opening.PastOnly / Opening.PresentOnly
     (colliders also Opening.Blocking) and are appended to the manager's PastActors / PresentActors
     arrays, so BP_OpeningActions.ApplyWorldState - the story's authoritative era presentation - shows
     one city and hides the other exactly as it does for the story's own props. No Verdant.Past /
     Verdant.Present tags are placed, so the native explore-mode T toggle stays inert on this map.
  4. Saves the level and writes merge_report.json next to the backup.

Story actors are never moved. Verdant_City and its assets are not touched. Re-running first removes
the actors it owns (tag Verdant.StoryOwned) and re-applies everything.
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
import verdant_build_map as vbm

FLAG = 'VerdantMergeStoryMap'
MAP = '/Game/Quest/Maps/Verdant_Desktop'
MAP_FILE = vc.PROJECT / 'Content/Quest/Maps/Verdant_Desktop.umap'
OWNER = 'Verdant.StoryOwned'
PAST, PRESENT, BLOCKING = 'Opening.PastOnly', 'Opening.PresentOnly', 'Opening.Blocking'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
OUT = vc.PROJECT / 'validation' / 'verdant_merge' / STAMP
PLAN_STORY = vc.SOURCE / 'plan_story.json'
ARRAYS = ('PastActors', 'PresentActors', 'PastCollisionActors')

# Development scenery to hide: actor name -> (label, mode, reason). Modes: 'scenery' hides and disables
# collision; 'visual' hides only (collision kept); 'light' hides the actor and its light / fog component;
# 'ppv' disables the volume. Labels are checked against the saved map before anything changes.
HIDE = {
    # Inherited Harbor city (development art replaced by the Verdant ground, buildings, harbour, landmarks, sea)
    'StaticMeshActor_58': ('SM_BellTower', 'scenery', 'old bell tower; Verdant campanile'),
    'StaticMeshActor_66': ('SM_Boat_A', 'scenery', 'old boat; Verdant fleet'),
    'StaticMeshActor_67': ('SM_Boat_B', 'scenery', 'old boat; Verdant fleet'),
    'StaticMeshActor_68': ('SM_Boat_C', 'scenery', 'old boat; Verdant fleet'),
    'StaticMeshActor_59': ('SM_Cathedral', 'scenery', 'old cathedral; Verdant cathedral'),
    'StaticMeshActor_51': ('SM_CathedralCliff', 'scenery', 'old cliff; Verdant terrain'),
    'StaticMeshActor_50': ('SM_CathedralPlaza', 'scenery', 'old plaza; Verdant plaza'),
    'StaticMeshActor_60': ('SM_CliffVillas', 'scenery', 'old villas; Verdant harbour villas'),
    'StaticMeshActor_70': ('SM_DistantMountains', 'scenery', 'already hidden; collision off; Verdant far terrain'),
    'StaticMeshActor_65': ('SM_DockCargo', 'scenery', 'old dock cargo; Verdant quay props'),
    'StaticMeshActor_64': ('SM_DocksMain', 'scenery', 'old docks; Verdant quay and piers'),
    'StaticMeshActor_72': ('SM_GuardrailCollision', 'scenery', 'old street-end collider; Verdant blockers'),
    'StaticMeshActor_48': ('SM_HarborStairs', 'scenery', 'old harbour stairs; Verdant stair landing and flights'),
    'StaticMeshActor_56': ('SM_LeftHouse_B', 'scenery', 'old street house B; Verdant street row'),
    'StaticMeshActor_57': ('SM_LeftHouse_C', 'scenery', 'old street house C; Verdant street row'),
    'StaticMeshActor_12': ('SM_LeftTownFoundation', 'scenery', 'old west ground; Verdant ground'),
    'StaticMeshActor_61': ('SM_Lighthouse', 'scenery', 'old lighthouse; Verdant lighthouse'),
    'StaticMeshActor_52': ('SM_LighthouseIsland', 'scenery', 'old island; Verdant island'),
    'StaticMeshActor_53': ('SM_LowCliffs', 'scenery', 'old east cliffs; Verdant terrain and overlook'),
    'StaticMeshActor_47': ('SM_PromenadeRail', 'scenery', 'old east rail; Verdant parapets and blockers'),
    'StaticMeshActor_69': ('SM_Sea', 'scenery', 'old sea; Verdant sea'),
    'StaticMeshActor_28': ('SM_StreetDetails', 'scenery', 'old street details; Verdant street'),
    'StaticMeshActor_19': ('SM_StreetFoundation', 'scenery', 'old street foundation; Verdant ground'),
    'StaticMeshActor_20': ('SM_StreetSurface', 'scenery', 'old street surface (z = 1020 - 0.1 y + 2 cm); Verdant road at z = 1020 - 0.1 y'),
    'StaticMeshActor_49': ('SM_UpperRoute', 'scenery', 'old uphill route; Verdant campanile and cathedral stairs'),
    'StaticMeshActor_54': ('SM_VillaQuays', 'scenery', 'old villa quays; Verdant quay'),
    # Quest visual scenery
    'StaticMeshActor_195': ('Quest - rounded coastal massifs', 'scenery', 'old distant ridges; Verdant far terrain'),
    'StaticMeshActor_196': ('Quest - coastal sky gradient and slow clouds', 'scenery', 'old sky dome; Verdant baked sky domes'),
    # Quest quarter street dressing (VR district kit)
    'StaticMeshActor_171': ('Quest quarter — arcade / bench', 'scenery', 'old arcade dressing; Verdant market square'),
    'StaticMeshActor_173': ('Quest quarter — arcade / shelf', 'scenery', 'old arcade dressing; Verdant market square'),
    'StaticMeshActor_172': ('Quest quarter — arcade / table', 'scenery', 'old arcade dressing; Verdant market square'),
    'StaticMeshActor_166': ('Quest quarter — clinic / bench', 'scenery', 'old street dressing; Verdant bench'),
    'StaticMeshActor_167': ('Quest quarter — clinic / sign', 'scenery', 'old sign post; Verdant clinic flag'),
    'StaticMeshActor_168': ('Quest quarter — clinic / tree', 'scenery', 'old potted olive; Verdant planting'),
    'StaticMeshActor_164': ('Quest quarter — domestic / bench', 'scenery', 'old courtyard bench on the plinth; Verdant dressing'),
    'StaticMeshActor_165': ('Quest quarter — domestic / tree', 'scenery', 'old potted olive on the plinth'),
    'StaticMeshActor_175': ('Quest quarter — harbor / bench', 'scenery', 'old overlook bench; Verdant stair landing'),
    'StaticMeshActor_174': ('Quest quarter — harbor / sign', 'scenery', 'old sign post'),
    'StaticMeshActor_176': ('Quest quarter — harbor / tree', 'scenery', 'old potted olive'),
    'StaticMeshActor_169': ('Quest quarter — market / sign', 'scenery', 'old sign post'),
    'StaticMeshActor_170': ('Quest quarter — market / threshold', 'scenery', 'old arcade threshold; Verdant alley'),
    'StaticMeshActor_179': ('Quest quarter — shore / return / north_a', 'scenery', 'old shore rail; Verdant parapets'),
    'StaticMeshActor_180': ('Quest quarter — shore / return / north_b', 'scenery', 'old shore rail; Verdant parapets'),
    'StaticMeshActor_177': ('Quest quarter — shore / return / south_a', 'scenery', 'old shore rail; Verdant parapets'),
    'StaticMeshActor_178': ('Quest quarter — shore / return / south_b', 'scenery', 'old shore rail; Verdant parapets'),
    # Brief street dressing on the old houses and street edge (the shop sign, shop supplies and the
    # present-era harbour crate stay: they dress the story's own shop and shelter sets)
    'StaticMeshActor_150': ('Brief — street / B / awning_past', 'scenery', 'awning on old house B'),
    'StaticMeshActor_151': ('Brief — street / B / awning_present', 'scenery', 'awning on old house B'),
    'StaticMeshActor_152': ('Brief — street / C / awning_past', 'scenery', 'awning on old house C'),
    'StaticMeshActor_153': ('Brief — street / B / window_box', 'scenery', 'window box on old house B'),
    'StaticMeshActor_154': ('Brief — street / C / window_box', 'scenery', 'window box on old house C'),
    'StaticMeshActor_157': ('Brief — street / empty_crate', 'scenery', 'old street crate; Verdant street props'),
    'StaticMeshActor_159': ('Brief — street / maintained_planter', 'scenery', 'old street planter; Verdant pots'),
    'StaticMeshActor_160': ('Brief — street / parapet_planter', 'scenery', 'planter beyond the Verdant road edge'),
    'StaticMeshActor_161': ('Brief — street / upper_planter', 'scenery', 'old street planter; Verdant pots'),
    'StaticMeshActor_162': ('Brief — street / upper_empty_crate', 'scenery', 'old street crate'),
    'StaticMeshActor_163': ('Brief — street / upper_supply_crate', 'scenery', 'old street crate'),
    # Past roof caps authored for the old houses B and C
    'StaticMeshActor_135': ('Opening - Past intact neighborhood roof', 'scenery', 'roof cap of old house B'),
    'StaticMeshActor_136': ('Opening - Past intact neighborhood roof', 'scenery', 'roof cap of old house B'),
    'StaticMeshActor_137': ('Opening - Past intact neighborhood roof', 'scenery', 'roof cap of old house C'),
    'StaticMeshActor_138': ('Opening - Past intact neighborhood roof', 'scenery', 'roof cap of old house C'),
    # Old lighting and sky (one coherent Verdant setup replaces them)
    'DirectionalLight_2': ('Golden hour sun', 'light', 'old sun 3.5 cd; Verdant per-era suns'),
    'SkyLight_1': ('Mediterranean sky fill', 'light', 'old skylight 0.21; Verdant per-era cubemap skylights'),
    'ExponentialHeightFog_1': ('Distant sea haze', 'light', 'old fog 0.0014; Verdant per-era fog'),
    'PostProcessVolume_1': ('Harbor exposure', 'ppv', 'old exposure volume (manual bias 0); Verdant_Exposure (manual bias -0.7) is the one volume'),
}
# VR teleport landings: visible discs on the ground, kept with their query collision, only hidden.
for name in ('StaticMeshActor_181', 'StaticMeshActor_182', 'StaticMeshActor_183', 'StaticMeshActor_184', 'StaticMeshActor_185',
             'StaticMeshActor_186', 'StaticMeshActor_187', 'StaticMeshActor_188', 'StaticMeshActor_189', 'StaticMeshActor_190',
             'StaticMeshActor_191', 'StaticMeshActor_192', 'StaticMeshActor_193', 'StaticMeshActor_194', 'StaticMeshActor_197'):
    HIDE[name] = ('Quest landing', 'visual', 'VR teleport landing disc; collision kept')

REPORT = {'success': False, 'run': STAMP, 'map': MAP, 'plan': str(PLAN_STORY), 'hidden': [], 'warnings': [], 'arrays': {},
          'verdant': {}, 'era_wiring': 'Opening.PastOnly / Opening.PresentOnly tags + manager PastActors / PresentActors arrays; '
                                       'ApplyWorldState (SetGroupVisible -> SetVisible: SetActorHiddenInGame + collision for Opening.Blocking) '
                                       'drives the Verdant actors; no Verdant.Past / Verdant.Present tags, so UVerdantEraSubsystem stays inert '
                                       '(no T toggle, no hint, no begin-play default) on this map',
          'exposure': 'one unbound PostProcessVolume Verdant_Exposure: manual, non-physical, bias %s, bloom %s, vignette 0.25, white 6500 K, '
                      'film slope %s / toe %s (the reviewed Verdant calibration); the old Harbor exposure volume is disabled. '
                      'Captures of this map must use the map\'s own volume (SceneCapture post_process_blend_weight 0).'
                      % (vbm.LIGHTING['exposure_bias'], vbm.LIGHTING.get('bloom'), vbm.LIGHTING.get('film_slope'), vbm.LIGHTING.get('film_toe'))}


def long(path):
    value = str(Path(path))
    return Path(value if value.startswith('\\\\?\\') else '\\\\?\\' + value)


def sha(path):
    return hashlib.sha256(long(path).read_bytes()).hexdigest()


def tags_of(actor):
    return [str(t) for t in actor.get_editor_property('tags')]


def add_tags(actor, *new):
    tags = tags_of(actor)
    actor.set_editor_property('tags', [unreal.Name(t) for t in tags + [t for t in new if t not in tags]])


def state(actor):
    row = {'hidden_in_game': bool(actor.get_editor_property('hidden')), 'actor_collision': bool(actor.get_actor_enable_collision()), 'components': {}}
    for component in actor.get_components_by_class(unreal.PrimitiveComponent):
        row['components'][component.get_name()] = {'visible': bool(component.is_visible()), 'collision': str(component.get_collision_enabled()).split('.')[-1]}
    for component in actor.get_components_by_class(unreal.LightComponentBase):
        row['components'][component.get_name()] = {'visible': bool(component.is_visible()), 'intensity': float(component.get_editor_property('intensity'))}
    for component in actor.get_components_by_class(unreal.ExponentialHeightFogComponent):
        row['components'][component.get_name()] = {'visible': bool(component.is_visible()), 'fog_density': float(component.get_editor_property('fog_density'))}
    if isinstance(actor, unreal.PostProcessVolume):
        row['enabled'] = bool(actor.get_editor_property('enabled'))
    return row


def hide(actor, mode):
    if mode == 'ppv':
        actor.set_editor_property('enabled', False)
        return
    actor.set_actor_hidden_in_game(True)
    for component in actor.get_components_by_class(unreal.PrimitiveComponent):
        component.set_visibility(False, True)
        if mode == 'scenery':
            component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    if mode == 'scenery':
        actor.set_actor_enable_collision(False)
    if mode == 'light':
        for component in actor.get_components_by_class(unreal.LightComponentBase):
            component.set_visibility(False, True)
        for component in actor.get_components_by_class(unreal.ExponentialHeightFogComponent):
            component.set_visibility(False, True)


def story_tagger(actor, era):
    """Era actors get the story's own visibility tags; invisible colliders also block like the story's props."""
    tags = [OWNER, PAST if era == 'Past' else PRESENT]
    if actor.get_actor_label().startswith('Verdant_Collider'):
        tags.append(BLOCKING)
    actor.set_editor_property('tags', [unreal.Name(t) for t in tags])


def apply_initial_era(actor):
    """Saved state mirrors ApplyWorldState for the default era (present): past hidden and non-colliding."""
    tags = tags_of(actor)
    if PAST in tags:
        actor.set_actor_hidden_in_game(True)
        actor.set_actor_enable_collision(False)
    elif PRESENT in tags:
        actor.set_actor_hidden_in_game(False)
        actor.set_actor_enable_collision(BLOCKING in tags)


def manager_actor(actors):
    found = [a for a in actors if a.actor_has_tag('Opening.Manager')]
    vc.require(len(found) == 1, 'Expected exactly one Opening.Manager, found %d' % len(found))
    return found[0]


def main():
    started = time.monotonic()
    command = unreal.SystemLibrary.get_command_line()
    vc.require(unreal.SystemLibrary.parse_param(command, FLAG), 'Explicit -' + FLAG + ' required')
    vc.require(not vc.levels.is_in_play_in_editor(), 'Exit PIE first')
    vc.require(PLAN_STORY.exists(), 'Run verdant/verdant_plan.py story first (plan_story.json missing)')
    plan = json.loads(PLAN_STORY.read_text(encoding='utf-8-sig'))
    vc.require(plan.get('variant', {}).get('name') == 'story', 'plan_story.json is not the story variant')
    boxes = [tuple(b) for b in plan['variant']['exclude_boxes_m']]
    OUT.mkdir(parents=True, exist_ok=True)
    before_sha = sha(MAP_FILE)
    shutil.copyfile(long(MAP_FILE), long(OUT / 'Verdant_Desktop.umap.before'))
    REPORT['backup'] = {'file': str(OUT / 'Verdant_Desktop.umap.before'), 'sha256': before_sha}
    REPORT['plan_variant'] = plan['variant']

    vc.require(vc.levels.load_level(MAP), 'Cannot load ' + MAP)
    world = vc.editor.get_editor_world()
    actors = list(vc.actors.get_all_level_actors())
    manager = manager_actor(actors)
    by_name = {a.get_name(): a for a in actors}

    # Idempotence: drop anything a previous merge owned, from the arrays first, then from the level.
    owned_before = [a for a in actors if a.actor_has_tag(OWNER)]
    if owned_before:
        names = {a.get_name() for a in owned_before}
        for field in ARRAYS:
            manager.set_editor_property(field, [a for a in manager.get_editor_property(field) if a.get_name() not in names])
        for actor in owned_before:
            vc.actors.destroy_actor(actor)
        REPORT['previous_owned_actors_removed'] = len(owned_before)
        actors = list(vc.actors.get_all_level_actors())
        by_name = {a.get_name(): a for a in actors}

    # 2. Development scenery.
    hidden_names = set()
    for name, (label, mode, reason) in HIDE.items():
        actor = by_name.get(name)
        if actor is None:
            REPORT['warnings'].append('Expected development actor missing: %s (%s)' % (name, label))
            continue
        def plain(text):
            return text.replace('—', '-').replace('–', '-').split(' (')[0][:16]
        if not plain(actor.get_actor_label()).startswith(plain(label)):
            REPORT['warnings'].append('Label mismatch for %s: saved "%s", expected "%s"; left untouched' % (name, actor.get_actor_label(), label))
            continue
        row = {'name': name, 'label': actor.get_actor_label(), 'mode': mode, 'reason': reason, 'before': state(actor),
               'tags': tags_of(actor), 'location': [round(v, 1) for v in actor.get_actor_location().to_tuple()]}
        hide(actor, mode)
        row['after'] = state(actor)
        REPORT['hidden'].append(row)
        hidden_names.add(name)
    for field in ARRAYS:
        values = list(manager.get_editor_property(field))
        kept = [a for a in values if a.get_name() not in hidden_names]
        removed = [a.get_actor_label() + '|' + a.get_name() for a in values if a.get_name() in hidden_names]
        manager.set_editor_property(field, kept)
        REPORT['arrays'][field] = {'before': len(values), 'removed_hidden': removed}

    # 3. Verdant content (story variant), additive.
    vbm.PLAN = plan
    vbm.VEGETATION = [row for row in vbm.VEGETATION if not any(x0 <= row['p'][0] <= x1 and y0 <= row['p'][1] <= y1 for x0, x1, y0, y1 in boxes)]
    vbm.TAGGER = story_tagger
    existing = {a.get_name() for a in vc.actors.get_all_level_actors()}
    vbm.shared_actor()
    vc.log('shared done', round(time.monotonic() - started, 1))
    for era in ('Past', 'Present'):
        vbm.era_actor(era)
        vbm.sky_dome(era)
        vbm.lights(era)
    vbm.colliders()
    vc.log('colliders done', round(time.monotonic() - started, 1))
    exposure = vbm.exposure_volume()
    new_actors = [a for a in vc.actors.get_all_level_actors() if a.get_name() not in existing]
    counts = {'Past': 0, 'Present': 0, 'Shared': 0}
    past_add, present_add, past_blocking = [], [], []
    for actor in new_actors:
        add_tags(actor, OWNER)
        tags = tags_of(actor)
        era = 'Past' if PAST in tags else 'Present' if PRESENT in tags else 'Shared'
        counts[era] += 1
        actor.set_folder_path('Verdant/' + era)
        apply_initial_era(actor)
        if era == 'Past':
            past_add.append(actor)
            if BLOCKING in tags:
                past_blocking.append(actor)
        elif era == 'Present':
            present_add.append(actor)
    for field, added in (('PastActors', past_add), ('PresentActors', present_add), ('PastCollisionActors', past_blocking)):
        values = list(manager.get_editor_property(field))
        manager.set_editor_property(field, values + [a for a in added if a not in values])
        REPORT['arrays'][field].update(added_verdant=len(added), after=len(values) + len(added))
    REPORT['verdant'] = {'actors': counts, 'instances': vbm.REPORT['instances'], 'components': vbm.REPORT['components'],
                         'colliders': vbm.REPORT['colliders'], 'skylight_source': vbm.REPORT.get('skylight_source'),
                         'total_instances': sum(vbm.REPORT['instances'].values()), 'vegetation_rows': len(vbm.VEGETATION),
                         'exposure_volume': exposure.get_name(), 'player_start_added': False, 'townsfolk_added': False,
                         'lighting_values': vbm.LIGHTING}
    REPORT['untouched_actor_count'] = len(actors) - len(hidden_names)
    REPORT['level_actor_count_after'] = len(list(vc.actors.get_all_level_actors()))
    vc.require(vc.levels.save_current_level(), 'Cannot save ' + MAP)
    REPORT['after_sha256'] = sha(MAP_FILE)
    REPORT['seconds'] = round(time.monotonic() - started, 1)
    REPORT['success'] = True


try:
    main()
except Exception:
    REPORT['error'] = traceback.format_exc()
    unreal.log_error(REPORT['error'])
vc.write_json(OUT / 'merge_report.json', REPORT)
vc.write_json(vc.EVIDENCE / 'merge_story_map_report.json', REPORT)
vc.log('merge', json.dumps({k: REPORT.get(k) for k in ('success', 'seconds', 'error')})[:600], str(OUT))
unreal.SystemLibrary.quit_editor()
