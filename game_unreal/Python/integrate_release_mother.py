"""QUEUED native Mother-only integration, requiring an explicit review manifest.

Source-only until Root grants the writer and -ReleaseMotherWrite. The current
extra-root100 art gate and its80m-pelvis retarget cannot satisfy these gates.
No generation of story graphs, new NPC actors, Pawn blockers or player scaling.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import sys
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(PROJECT / 'Python'))
import opening_graph as og
import release_mother_integration as helper
import release_file_io as file_io
import release_mother_locomotion as locomotion

REPORT = PROJECT / 'release_mother_integration_report.json'
MAP = '/Game/Quest/Maps/Verdant_Desktop'


def checked_report(inputs, name):
    file = Path(inputs[name]).resolve()
    helper.require(file.is_relative_to(PROJECT.parent), 'Review evidence must be inside the isolated Release copy')
    helper.require(file.is_file() and helper.sha(file) == inputs[name + '_sha256'], 'Evidence changed since visual approval: ' + name)
    report = json.loads(file.read_text(encoding='utf-8-sig'))
    helper.require(report['success'], 'Native evidence did not pass: ' + name)
    return report


def references(manager):
    names = ['SaveSlot', 'InteractionRange', 'MotherActor', 'NeriActor', 'HealerActor', 'SelaActor',
             'PhotoActor', 'LetterActor', 'BenchActor', 'AnchorActor', 'PastActors', 'PresentActors', 'PastCollisionActors']
    result = {}
    for name in names:
        value = manager.get_editor_property(name)
        result[name] = helper.path(value) if isinstance(value, unreal.Object) else str(value)
    return result


def map_actor_identity(actors):
    return {a.get_path_name(): {'class': helper.path(a.get_class()), 'transform': helper.transform_state(a.get_actor_transform()),
            'tags': sorted(str(t) for t in a.get_editor_property('tags'))} for a in actors}


def stage_mother(world, manager, mesh, idle, walk, physics, rotation_offset):
    mother = manager.get_editor_property('MotherActor')
    helper.require(mother and mother.actor_has_tag('npc.mother'), 'The existing stable Mother reference/tag is required')
    component = mother.get_component_by_class(unreal.SkeletalMeshComponent)
    before = helper.component_state(mother)
    # Retain actual UObject/struct values for this unsaved world's rollback.
    previous = {'mesh': component.get_skeletal_mesh_asset(),
                'physics': component.get_editor_property('physics_asset_override'),
                'rotation': component.get_editor_property('relative_rotation'),
                'materials': list(component.get_editor_property('override_materials')),
                'animation_mode': component.get_editor_property('animation_mode'),
                'animation_data': component.get_editor_property('animation_data')}
    try:
        # Clear the previous mannequin's serialized/single-node animation before
        # switching skeletons; never carry an incompatible animation across.
        component.override_animation_data(None, True, False, 0.0, 1.0)
        component.set_skeletal_mesh_asset(mesh)
        component.set_editor_property('override_materials', [])
        # This SkeletalMeshComponent is the actor root. The approved +X-to-+Y
        # heading basis is applied only by runtime hooks, never saved as a yaw
        # edit on the existing authored actor.
        component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        # Verified public API persists the intended Listening asset and also
        # evaluates/refreshed bones. PlayAnimation alone is transient and must
        # not be used as proof that the saved editor map reloads posed.
        component.override_animation_data(idle, True, True, 0.0, 1.0)
        component.set_physics_asset(physics, True)
        query = helper.query_mother(world, mother)
        origin, extent, radius = unreal.SystemLibrary.get_component_bounds(component)
        height = float(extent.z * 2)
        helper.require(125 <= height <= 210, 'Actual production-world human height is outside125..210cm')
        after = helper.component_state(mother)
        unchanged = ['actor_path', 'actor_transform', 'actor_tags', 'actor_collision_enabled',
                     'collision_enabled', 'profile', 'object_type', 'visibility_response', 'pawn_response']
        helper.require(all(before[key] == after[key] for key in unchanged), 'Stable Mother transform/identity/collision policy changed')
        return mother, component, previous, {'before': before, 'after': after, 'world_height_cm': height,
                'bounds_origin_cm': helper.xyz(origin), 'bounds_extent_cm': helper.xyz(extent), 'query': query}
    except Exception:
        restore(component, previous)
        raise


def restore(component, previous):
    component.set_skeletal_mesh_asset(previous['mesh'])
    component.set_physics_asset(previous['physics'], True)
    component.set_relative_rotation(previous['rotation'], False, False)
    component.set_editor_property('override_materials', previous['materials'])
    component.set_animation_mode(previous['animation_mode'])
    component.set_editor_property('animation_data', previous['animation_data'])


def main():
    helper.require(PROJECT.parent.name == 'Release_20261026', 'Only the isolated Release project is authorized')
    command = unreal.SystemLibrary.get_command_line()
    helper.require(unreal.SystemLibrary.parse_param(command, 'ReleaseMotherWrite'), 'Serialized native queue grant required')
    match = re.search(r'(?i)(?:^|\s)-ReleaseMotherInputs=(?:"([^"]+)"|(\S+))', command)
    helper.require(match, 'Explicit corrected-unit/gait/visual-approval manifest required')
    input_file = Path(match.group(1) or match.group(2)).resolve()
    helper.require(input_file.is_relative_to(PROJECT.parent), 'Integration input must be inside the Release copy')
    inputs = json.loads(input_file.read_text(encoding='utf-8-sig'))
    helper.require(inputs.get('gait_visually_approved') is True and inputs.get('cloth_deformation_approved') is True
                   and inputs.get('basis_reviewed') is True, 'Root must inspect actual gait/garment/basis images before the native swap')
    unit = checked_report(inputs, 'unit_report')
    helper.require(unit.get('native_executed') is True, 'Blender source-scale evidence cannot replace actual native unit evidence')
    candidate = unit.get('preferred_candidate')
    helper.require(isinstance(candidate, dict) and candidate.get('skeletal_actor_count') == 1,
                   'Exactly one explicitly preferred native candidate is required')
    helper.require(candidate['native_unit_scale']['unit_root_scale_passed'] and candidate['human_height_passed']
                   and 125 <= candidate['world_height_cm'] <= 210, 'Rejected extra-root100 or nonhuman-scale candidate')
    retarget = checked_report(inputs, 'retarget_report')
    gait = checked_report(inputs, 'gait_report')
    helper.require(retarget.get('source_unit_probe_report_sha256') == inputs['unit_report_sha256']
                   and gait.get('source_unit_probe_report_sha256') == inputs['unit_report_sha256'], 'Unit/bake/gait provenance does not match')
    for record in [candidate, retarget]:
        helper.require(record.get('owned_asset_sha256'), 'Native unit/bake must record actual owned asset hashes')
        for file, digest in record['owned_asset_sha256'].items():
            helper.require(Path(file).resolve().is_relative_to(PROJECT / 'Content') and helper.sha(file) == digest,
                           'Native unit/baked asset changed since its actual proof: ' + file)
    helper.require(gait.get('reviewed_asset_sha256'), 'Native gait must pin the exact mesh/skeleton/clip bytes')
    for file, digest in gait['reviewed_asset_sha256'].items():
        helper.require(Path(file).resolve().is_relative_to(PROJECT / 'Content') and helper.sha(file) == digest,
                       'Visually reviewed character asset changed: ' + file)
    helper.require(retarget.get('native_executed') and retarget['target_mesh'] == candidate['mesh'], 'Walk bake is not for this corrected skeleton')
    helper.require(gait.get('native_executed') and gait['mesh'] == candidate['mesh'] and gait['baked_walk'] == retarget['baked']['walk']
                   and not gait.get('plausibility_issues') and len(gait.get('images', [])) >= 10,
                   'Actual matching native gait/body/world proof is required')
    helper.require(isinstance(gait.get('walk_pelvis_xy_span_cm'), (int, float)) and gait['walk_pelvis_xy_span_cm'] < 40,
                   'Locked Root alone is insufficient; actual in-place body/pelvis drift must also pass')
    rotation = inputs.get('mesh_relative_rotation_offset_degrees')
    helper.require(isinstance(rotation, list) and len(rotation) == 3 and all(isinstance(v, (int, float)) and abs(v) <= 180 for v in rotation),
                   'An explicit reviewed component-basis offset is required; no actor rotation/scale changes')
    helper.require(all(abs(v)<1e-6 for v in rotation), 'A saved root-component basis offset would alter the authored actor; use the deterministic runtime basis instead')
    calibration = checked_report(inputs, 'calibration_report')
    helper.require(calibration.get('native_executed') and calibration['walk']==retarget['baked']['walk']
                   and calibration['target_mesh']==candidate['mesh'] and calibration['retarget_report_sha256']==inputs['retarget_report_sha256']
                   and calibration['scripted_travel_speed_cm_s']==100.0, 'Matching actual stance calibration for the fixed100cm/s route is required')
    play_rate = calibration['recommended_play_rate']
    helper.require(isinstance(play_rate,(int,float)) and .2<=play_rate<=1.5, 'No valid native stance-derived playback estimate')
    mesh = unreal.load_asset(candidate['mesh'])
    idle, walk = unreal.load_asset(candidate['animation']), unreal.load_asset(retarget['baked']['walk'])
    helper.require(mesh and idle and walk, 'Corrected human assets unavailable')
    for clip in [idle, walk]:
        helper.require(clip.get_editor_property('skeleton') == mesh.get_editor_property('skeleton'), 'Never assign incompatible Manny animation')
    helper.require(3.8 <= idle.get_play_length() <= 4.2, 'Default Mother idle must be the proved Listening clip')
    reference = helper.unit_reference(mesh)
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    folder = PROJECT / 'validation/release_mother_integration' / run
    folder.mkdir(parents=True)
    manager_asset = unreal.load_asset(helper.MANAGER)
    audit = helper.GraphAudit(folder / 'node_exports')
    guards_before = audit.guarded_calls(manager_asset)
    manager_file = helper.asset_file(PROJECT, helper.MANAGER)
    map_file = PROJECT / 'Content/Quest/Maps/Verdant_Desktop.umap'
    # Byte archives are for explicit offline rollback after an exited writer;
    # never overwrite loaded native assets from Python on an error path.
    for file in [manager_file, map_file]:
        (folder / (file.name + '.before')).write_bytes(file.read_bytes())
    before = {str(p): helper.sha(p) for p in file_io.files(PROJECT/'Content','*.uasset') + file_io.files(PROJECT/'Content','*.umap')
              + list((PROJECT / 'Config').glob('*.ini')) + list(PROJECT.glob('*.uproject')) if p not in [manager_file, map_file]}
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    helper.require(not level.is_in_play_in_editor() and level.load_level(MAP), 'Load the saved Desktop map outsidePIE')
    world = editor.get_editor_world()
    managers = [a for a in actors.get_all_level_actors() if a.actor_has_tag('Opening.Manager')]
    helper.require(len(managers) == 1, 'Exactly one existing story manager is required')
    manager = managers[0]
    manager_name = manager.get_name()
    fallback = {name: manager.get_editor_property(name) for name in ['IdleAnimation', 'WalkAnimation']}
    refs_before, identities = references(manager), map_actor_identity(actors.get_all_level_actors())
    mother = manager.get_editor_property('MotherActor')
    scale = mother.get_actor_scale3d()
    helper.require(all(abs(v-calibration['assumed_authored_actor_uniform_scale'])<1e-4 for v in helper.xyz(scale)),
                   'Actual authored Mother scale differs from native stance calibration; do not change actor scale to fit the report')
    authored_rotation = mother.get_actor_rotation()
    helper.require(abs(authored_rotation.pitch)<.01 and abs(authored_rotation.roll)<.01, 'Review a nonupright authored Mother basis explicitly')
    human_authored_rotation = unreal.Rotator(pitch=0,yaw=authored_rotation.yaw-90,roll=0)
    physics, physics_evidence = helper.create_query_physics(mesh)
    mother, component, previous, map_evidence = stage_mother(world, manager, mesh, idle, walk, physics, rotation)
    # No maps/manager are saved until the actual same-actor query/scale gate passes.
    changes = helper.patch_mother_pins(manager_asset, audit, fallback)
    runtime_hooks = locomotion.patch_runtime(manager_asset,audit,changes)
    # Native Blueprint compilation can reinstance manager actors. Resolve its
    # preserved stable path/name again rather than writing a stale Python proxy.
    replacements = [a for a in actors.get_all_level_actors() if a.get_name() == manager_name and a.actor_has_tag('Opening.Manager')]
    helper.require(len(replacements) == 1, 'Manager reinstance did not preserve its stable identity')
    manager = replacements[0]
    manager.set_editor_property('MotherIdleAnimation', idle)
    manager.set_editor_property('MotherWalkAnimation', walk)
    manager.set_editor_property('MotherWalkPlayRate',play_rate)
    manager.set_editor_property('MotherUseHumanLocomotion',True)
    manager.set_editor_property('MotherTurnSpeedDegrees',180.0)
    manager.set_editor_property('MotherAuthoredHumanWorldRotation',human_authored_rotation)
    helper.require(references(manager) == refs_before and map_actor_identity(actors.get_all_level_actors()) == identities,
                   'Story actor refs, era groups, transforms or stable IDs changed')
    audit.cache.clear()
    guards_after = audit.guarded_calls(manager_asset)
    helper.require(guards_after == guards_before, 'Character-only patch changed a guarded save node or pin')
    helper.require(all(file_io.is_file(p) and helper.sha(p) == digest for p, digest in before.items()), 'An unowned native input changed')
    helper.require(unreal.EditorAssetLibrary.save_loaded_asset(physics), 'Owned human query physics save failed')
    helper.require(unreal.EditorAssetLibrary.save_loaded_asset(manager_asset), 'Mother animation-value pin save failed')
    helper.require(level.save_current_level(), 'Stable Mother Desktop map save failed')
    helper.require(all(file_io.is_file(p) and helper.sha(p) == digest for p, digest in before.items()), 'An unowned native input changed during explicit saves')
    result = {'success': True, 'native_executed': True, 'run': run, 'map': MAP, 'mesh': candidate['mesh'],
              'listening_idle': candidate['animation'], 'walk': retarget['baked']['walk'], 'unit_reference': reference,
              'physics': physics_evidence, 'mother': map_evidence, 'animation_pin_changes': changes,
              'all_five_original_play_nodes_guids_preserved': True, 'original_execution_destinations_preserved_through_owned_hooks': True,
              'runtime_locomotion_hooks': runtime_hooks,'mother_walk_rate_estimate':play_rate,
              'authored_human_world_rotation_runtime_only':str(human_authored_rotation),
              'story_actor_refs_and_authored_transforms_preserved': True,
              'baseline_ghost_pawn_policy_preserved': True, 'solid_npc_collision_claimed': False,
              'guarded_save_calls_before': guards_before, 'guarded_save_calls_after': guards_after,
              'guarded_save_nodes_unchanged': True, 'unsafe_generic_save_calls': 0,
              'manager_sha256_before': helper.sha(folder / (manager_file.name + '.before')),
              'manager_asset_sha256': helper.sha(manager_file), 'map_asset_sha256': helper.sha(map_file),
              'protected_native_files_unchanged': True, 'save_files_written': False,
              'runtime_story_or_packaged_tested': False, 'rollback_archive': str(folder),
              'input_manifest': str(input_file), 'input_manifest_sha256': helper.sha(input_file)}
    (folder / 'integration.json').write_text(json.dumps(result, indent=2))
    REPORT.write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    settings = unreal.get_default_object(unreal.load_class(None,'/Script/BlueprintGraph.BlueprintEditorSettings'))
    promotion = settings.get_editor_property('bEnableTypePromotion')
    try:
        settings.set_editor_property('bEnableTypePromotion',False)
        main()
    except Exception:
        REPORT.write_text(json.dumps({'success': False, 'error': traceback.format_exc(),
            'note': 'Do not overwrite loaded assets. Inspect the byte archive and saved stage before any explicit offline rollback.'}, indent=2))
        unreal.log_error(traceback.format_exc())
    finally:
        settings.set_editor_property('bEnableTypePromotion',promotion)
    unreal.SystemLibrary.quit_editor()
