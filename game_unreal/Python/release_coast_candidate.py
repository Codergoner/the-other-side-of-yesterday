"""Bounded Desktop coast candidate: prepare assets, unsaved preview, adopt/revert.

Imports have no authoring side effects. No commandlet, whole-city importer,
configuration change, sky/light adjustment or runtime Python is involved.
Root owns the single native writer queue. All writes require -ReleaseCoastWrite.
"""
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import math
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
DEV = ROOT.parent
sys.path.insert(0, str(ROOT/'Python'))
import build_release_art as base
import release_coast_contract as contract
import release_file_io as fio

SOURCE = DEV/'output/release_coast_extension'
REPORT = ROOT/'release_coast_candidate_report.json'
REVIEW = ROOT/'release_coast_candidate_review.json'
MAP = '/Game/Quest/Maps/Verdant_Desktop'
MAP_FILE = ROOT/'Content/Quest/Maps/Verdant_Desktop.umap'
OWNER = 'TOSOY.ReleaseCoastOwned'
ID = 'release.visual.coast_extension'
LIB, MEL = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
STATIC = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
EXTRA_STORY_REFS = ['DrawerActor', 'ClinicRecordActor', 'HarborRecordActor',
                    'ClinicCoverActor', 'HarborCoverActor', 'NeriHarborDestination',
                    'MotherHomeDestination']


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def read():
    return json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {}


def write(record):
    REPORT.write_text(json.dumps(record, indent=2, default=str)+'\n', encoding='utf-8')


def guard(write_native=False):
    base.guard()
    require(DEV.name == 'Release_20261026', 'Coast authoring refuses another project')
    contract.policy()
    if write_native:
        require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),
                                                'ReleaseCoastWrite'),
                'Root native queue and -ReleaseCoastWrite are required')


def load_map():
    # Never discard an artist's unsaved map while opening our one allowed target.
    require(not list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()),
            'Save/review existing dirty maps before the coast queue runs')
    require(not list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()),
            'Save/review existing dirty content before the coast queue runs')
    require(base.LEVEL.load_level(MAP), 'Cannot load the Release Desktop map')


def state(actor):
    row = base.state(actor)
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    if component:
        row['component_visible'] = bool(component.get_editor_property('visible'))
        row['component_cast_shadow'] = bool(component.get_editor_property('cast_shadow'))
    return row


def snapshot():
    return {actor.get_name(): state(actor) for actor in base.actors()}


def story():
    data = base.story_refs()
    for actor in base.actors():
        if not actor.actor_has_tag('Opening.Manager'):
            continue
        entry = data.setdefault(actor.get_name(), {})
        for name in EXTRA_STORY_REFS:
            try:
                value = actor.get_editor_property(name)
            except Exception:
                continue
            entry[name] = value.get_path_name() if isinstance(value, unreal.Object) else str(value)
    return data


def protected_files():
    paths = []
    for directory, pattern in [(ROOT/'Content', '*.uasset'), (ROOT/'Content', '*.umap'),
                               (ROOT/'Config', '*.ini'), (ROOT, '*.uproject'),
                               (ROOT/'Saved/SaveGames', '*.sav')]:
        paths.extend(fio.files(directory, pattern) if directory.exists() else [])
    return {str(path): fio.sha(path) for path in paths}


def check_files(before, map_save=False):
    for file, digest in before.items():
        if map_save and Path(file) == MAP_FILE:
            continue
        require(fio.is_file(file) and fio.sha(file) == digest,
                'Preserving changed existing asset/config/save: '+file)


def sea():
    plan = contract.policy()
    values = [actor for actor in base.actors() if actor.get_name() == plan['original_sea_actor']]
    require(len(values) == 1, 'Expected exactly the original sea actor')
    actor = values[0]
    require(state(actor)['mesh'] == plan['original_sea_mesh'], 'Original sea mesh differs')
    require(not actor.actor_has_tag('TOSOY.ManualOverride'), 'Preserving manually marked sea')
    return actor


def extension():
    values = [actor for actor in base.actors() if actor.actor_has_tag(ID)]
    require(len(values) <= 1, 'Duplicate coast extension identity')
    return values[0] if values else None


def editable(record):
    actor, ring = sea(), extension()
    actual = state(actor)
    if record.get('after_sea'):
        require(actual == record['after_sea'], 'Preserving sea edited after the last coast operation')
    elif record.get('baseline_sea'):
        require(actual == record['baseline_sea'], 'Preserving sea edited after coast preparation')
    else:
        art = base.read_report()
        reference = art['maps'][MAP]['after'][actor.get_name()]
        require(base.state(actor) == reference, 'Sea differs from the actual persisted Release art record')
    if ring:
        require(ring.actor_has_tag(OWNER) and not ring.actor_has_tag('TOSOY.ManualOverride'),
                'Preserving unowned or manually marked coast extension')
        require(record.get('after_extension') == state(ring),
                'Preserving coast extension edited after adoption')
    else:
        require(not record.get('active'), 'Active coast extension is missing; preserve manual deletion')
    return actor, ring


def source():
    manifest = json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8'))
    require(manifest['owner'] == OWNER and manifest['triangles'] == 8 and
            manifest['material_slots'] == 1 and manifest['collision_shapes'] == 0,
            'Unexpected coast export scope')
    for file, key in [(DEV/'build_release_coast_extension.py', 'source_sha256'),
                      (Path(contract.__file__), 'contract_sha256'),
                      (contract.PLAN, 'policy_sha256')]:
        require(fio.sha(file) == manifest[key], 'Coast source changed after export: '+str(file))
    path = (SOURCE/manifest['mesh_file']).resolve()
    require(path.is_relative_to(SOURCE.resolve()) and fio.sha(path) == manifest['mesh_sha256'],
            'Coast FBX escaped staging or changed')
    require(manifest['expected_native_bounds_cm'] == contract.bounds_cm(), 'Export bounds differ')
    return manifest, path


def signature(manifest):
    value = manifest['mesh_sha256']+manifest['policy_sha256']+fio.sha(__file__)
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def mark(asset, sig):
    LIB.set_metadata_tag(asset, 'Release.Coast.Owner', OWNER)
    LIB.set_metadata_tag(asset, 'Release.Coast.Signature', sig)


def assert_owned(asset, sig):
    require(LIB.get_metadata_tag(asset, 'Release.Coast.Owner') == OWNER and
            LIB.get_metadata_tag(asset, 'Release.Coast.Signature') == sig,
            'Preserving unowned coast candidate asset')


def candidate_files(folder):
    path = ROOT/'Content'/folder.removeprefix('/Game/')
    return {str(file): fio.sha(file) for file in fio.files(path, '*.uasset')}


def save_owned(asset, folder, record):
    require(LIB.save_loaded_asset(asset, only_if_is_dirty=False), 'Could not save '+asset.get_path_name())
    record['asset_fingerprints'] = candidate_files(folder)
    write(record)


def subtract(mat, a, b):
    node = base.node(mat, 'Subtract')
    base.wire(a, node, 'A'); base.wire(b, node, 'B')
    return node


def lerp(mat, a, b, alpha):
    node = base.node(mat, 'LinearInterpolate')
    base.wire(a, node, 'A'); base.wire(b, node, 'B'); base.wire(alpha, node, 'Alpha')
    return node


def append(mat, a, b):
    node = base.node(mat, 'AppendVector')
    base.wire(a, node, 'A'); base.wire(b, node, 'B')
    return node


def create_water(folder, sig, record):
    path = folder+'/M_ReleaseCoastWater'
    material = base.load(path)
    if material:
        assert_owned(material, sig)
        return material, validate_water(material, compile_graph=True)
    material = base.ASSETS.create_asset('M_ReleaseCoastWater', folder, unreal.Material,
                                       unreal.MaterialFactoryNew())
    require(material is not None, 'Could not create versioned coast material')
    mark(material, sig)
    material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    material.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    water = contract.policy()['water']
    texture = base.load(water['normal_texture'])
    require(isinstance(texture, unreal.Texture2D), 'Existing approved water normal is missing')
    world = base.node(material, 'WorldPosition')
    wx, wy = base.channel(material, world, 'r'), base.channel(material, world, 'g')
    def uv(wavelength, rotate=0):
        # UE Y is the negative of Blender Y; preserve the existing top tangent basis.
        x = base.multiply(material, wx, base.scalar(material, 1/wavelength[0]))
        y = base.multiply(material, wy, base.scalar(material, -1/wavelength[1]))
        if rotate:
            angle = math.radians(rotate)
            x, y = (base.add(material, base.multiply(material, x, base.scalar(material, math.cos(angle))),
                            base.multiply(material, y, base.scalar(material, math.sin(angle)))),
                    base.add(material, base.multiply(material, x, base.scalar(material, -math.sin(angle))),
                            base.multiply(material, y, base.scalar(material, math.cos(angle)))))
        return append(material, x, y)
    a = base.normal_sample(material, texture, base.panner(material,
        uv(water['normal_wavelength_a_cm']), water['normal_a_speed']))
    b = base.normal_sample(material, texture, base.panner(material,
        uv(water['normal_wavelength_b_cm'], water['normal_b_rotation_degrees']), water['normal_b_speed']))
    combined = base.add(material, base.multiply(material, a, base.scalar(material, water['blend_weights'][0])),
                        base.multiply(material, b, base.scalar(material, water['blend_weights'][1])))
    distance = base.node(material, 'Distance')
    base.wire(world, distance, 'A')
    base.wire(base.node(material, 'CameraPositionWS'), distance, 'B')
    start = base.parameter(material, 'DistanceFadeStartCm', water['distance_fade_start_cm'])
    end = base.parameter(material, 'DistanceFadeEndCm', water['distance_fade_end_cm'])
    normalized = base.node(material, 'Divide')
    base.wire(subtract(material, distance, start), normalized, 'A')
    base.wire(subtract(material, end, start), normalized, 'B')
    fade = base.node(material, 'Clamp', min_default=0., max_default=1.)
    base.wire(normalized, fade)
    near = base.parameter(material, 'NearNormalStrength', water['near_normal_strength'])
    far = base.parameter(material, 'FarNormalStrength', water['far_normal_strength'])
    strength = lerp(material, near, far, fade)
    amplitude = append(material, append(material, strength, strength), base.scalar(material, 1))
    normal = base.node(material, 'Normalize')
    base.wire(base.multiply(material, combined, amplitude), normal)
    base.out(normal, material, unreal.MaterialProperty.MP_NORMAL)
    roughness = lerp(material,
        base.parameter(material, 'NearRoughness', water['near_roughness']),
        base.parameter(material, 'FarRoughness', water['far_roughness']), fade)
    base.out(roughness, material, unreal.MaterialProperty.MP_ROUGHNESS)
    fresnel = base.node(material, 'Fresnel', exponent=water['fresnel_exponent'], base_reflect_fraction=0.)
    # Explicit geometric normal avoids a dependency from base colour on the wave normal.
    base.wire(base.vector(material, [0, 0, 1]), fresnel, 'Normal')
    color = lerp(material, base.vector(material, base.linear(water['near_color_srgb8'])),
                 base.vector(material, base.linear(water['grazing_color_srgb8'])),
                 base.multiply(material, fresnel, base.scalar(material, water['grazing_color_amount'])))
    base.out(color, material, unreal.MaterialProperty.MP_BASE_COLOR)
    base.out(base.parameter(material, 'CoastSpecular', water['specular']), material, unreal.MaterialProperty.MP_SPECULAR)
    base.out(base.scalar(material, 0), material, unreal.MaterialProperty.MP_METALLIC)
    proof = validate_water(material, compile_graph=True)
    LIB.set_metadata_tag(material, 'Release.Coast.Policy', json.dumps(water, sort_keys=True))
    save_owned(material, folder, record)
    return material, proof


def validate_water(material, compile_graph=False):
    water = contract.policy()['water']
    required = ['MP_BASE_COLOR', 'MP_NORMAL', 'MP_ROUGHNESS', 'MP_SPECULAR', 'MP_METALLIC']
    require(all(MEL.get_material_property_input_node(material, getattr(unreal.MaterialProperty, key))
                for key in required), 'Coast material output is missing')
    require(material.get_editor_property('blend_mode') == unreal.BlendMode.BLEND_OPAQUE,
            'Coast material must stay opaque')
    require(material.get_editor_property('shading_model') == unreal.MaterialShadingModel.MSM_DEFAULT_LIT,
            'Coast material must stay default lit')
    for key in ['MP_EMISSIVE_COLOR', 'MP_WORLD_POSITION_OFFSET', 'MP_OPACITY', 'MP_REFRACTION']:
        require(MEL.get_material_property_input_node(material, getattr(unreal.MaterialProperty, key)) is None,
                'Unapproved expensive/displaced/emissive coast output '+key)
    expressions = list(MEL.get_material_expressions(material))
    samples = [node for node in expressions if isinstance(node, unreal.MaterialExpressionTextureSample)]
    require(len(samples) == 2 and all(node.get_editor_property('texture') == base.load(water['normal_texture'])
                                    for node in samples), 'Expected exactly the two existing normal texture samples')
    require(sum(isinstance(node, unreal.MaterialExpressionWorldPosition) for node in expressions) == 1,
            'One shared absolute world-coordinate origin is required')
    defaults = {'DistanceFadeStartCm': water['distance_fade_start_cm'],
        'DistanceFadeEndCm': water['distance_fade_end_cm'], 'NearNormalStrength': water['near_normal_strength'],
        'FarNormalStrength': water['far_normal_strength'], 'NearRoughness': water['near_roughness'],
        'FarRoughness': water['far_roughness'], 'CoastSpecular': water['specular']}
    for name, expected in defaults.items():
        actual = MEL.get_material_default_scalar_parameter_value(material, unreal.Name(name))
        require(abs(actual-expected) < .0001, 'Preserving changed coast parameter '+name)
    errors = list(MEL.recompile_material(material)) if compile_graph else None
    require(not errors, 'Coast material native compilation failed: '+str(errors))
    return {'material': material.get_path_name(), 'texture_samples': 2, 'defaults': defaults,
        'compile_executed': compile_graph, 'compile_errors': errors, 'emissive_or_displacement': False,
        'visual_acceptance_pending': True, 'performance_measured': False}


def mesh_bounds(mesh):
    bounds = mesh.get_bounds()
    return {'min': base.xyz(bounds.origin-bounds.box_extent), 'max': base.xyz(bounds.origin+bounds.box_extent)}


def validate_mesh(mesh, material):
    require(isinstance(mesh, unreal.StaticMesh), 'Coast extension mesh missing')
    require(mesh.get_num_triangles(0) == 8, 'Coast extension must remain eight triangles')
    require(STATIC.get_simple_collision_count(mesh) == 0 and STATIC.get_convex_collision_count(mesh) == 0,
            'Coast extension must have no collision shapes')
    require(len(mesh.get_editor_property('static_materials')) == 1 and mesh.get_material(0) == material,
            'Coast extension material slot differs')
    actual, expected = mesh_bounds(mesh), contract.bounds_cm()
    tolerance = contract.policy()['acceptance']['native_bounds_tolerance_cm']
    require(all(abs(actual[side][axis]-expected[side][axis]) <= tolerance
                for side in ['min', 'max'] for axis in range(3)),
            'Imported coast units/axes/bounds differ; no actor-scaling workaround allowed')
    return {'mesh': mesh.get_path_name(), 'triangles': 8, 'native_bounds_cm': actual,
            'collision_shapes': 0, 'material_slots': 1}


def import_mesh(file, folder, sig, material, record):
    package = folder+'/SM_ReleaseCoastExtension'
    mesh = base.load(package)
    if mesh:
        assert_owned(mesh, sig)
        return mesh, validate_mesh(mesh, material)
    options = unreal.FbxImportUI()
    for key, value in {'import_mesh': True, 'import_as_skeletal': False, 'import_materials': False,
        'import_textures': False, 'automated_import_should_detect_type': False,
        'mesh_type_to_import': unreal.FBXImportType.FBXIT_STATIC_MESH}.items():
        options.set_editor_property(key, value)
    data = options.get_editor_property('static_mesh_import_data')
    for key, value in {'combine_meshes': True, 'transform_vertex_to_absolute': True, 'convert_scene': True,
        'convert_scene_unit': True, 'force_front_x_axis': False, 'auto_generate_collision': False,
        'generate_lightmap_u_vs': False, 'build_nanite': False, 'remove_degenerates': True,
        'normal_import_method': unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS}.items():
        data.set_editor_property(key, value)
    task = unreal.AssetImportTask()
    for key, value in {'filename': str(file), 'destination_path': folder,
        'destination_name': 'SM_ReleaseCoastExtension', 'automated': True, 'replace_existing': False,
        'save': False, 'factory': unreal.FbxFactory(), 'options': options}.items():
        task.set_editor_property(key, value)
    base.ASSETS.import_asset_tasks([task])
    mesh = base.load(package)
    require(mesh is not None, 'Coast FBX import failed')
    mesh.set_material(0, material)
    mark(mesh, sig)
    proof = validate_mesh(mesh, material)
    save_owned(mesh, folder, record)
    return mesh, proof


def verify_fingerprints(record):
    for file, digest in record.get('asset_fingerprints', {}).items():
        require(fio.is_file(file) and fio.sha(file) == digest,
                'Preserving artist-edited coast candidate asset '+file)


def prepare():
    """Import/compile new assets only. Saves no level and changes no actor."""
    guard(write_native=True)
    load_map()
    manifest, file = source()
    sig = signature(manifest)
    record = read()
    require(not record or record.get('signature') == sig,
            'Candidate source changed; archive its report and preserve existing assets before a new version')
    verify_fingerprints(record)
    actor, _ = editable(record)
    before, lights, refs, files = snapshot(), base.lighting(), story(), protected_files()
    if not record:
        directory = ROOT/'validation/release_coast_baselines'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')+'.json')
        path.write_text(json.dumps(before, indent=2)+'\n', encoding='utf-8')
        record = {'schema': 1, 'map': MAP, 'signature': sig, 'baseline_sea': state(actor),
            'first_baseline_file': str(path), 'first_baseline_sha256': fio.sha(path),
            'active': False, 'prepared': False, 'visual_accepted': False, 'performance_measured': False}
        write(record)
    folder = '/Game/Release/Coast/V_'+sig
    # Existing versioned assets without a fingerprint are not silently regenerated.
    existing = candidate_files(folder)
    require(all(file in record.get('asset_fingerprints', {}) for file in existing),
            'Preserving an unrecorded/orphaned coast candidate asset')
    material, material_proof = create_water(folder, sig, record)
    mesh, mesh_proof = import_mesh(file, folder, sig, material, record)
    require(snapshot() == before and base.lighting() == lights and story() == refs,
            'Coast preparation changed scene/lighting/story')
    check_files(files)
    record.update(prepared=True, material_path=material.get_path_name(), mesh_path=mesh.get_path_name(),
        material_native_readback=material_proof, mesh_native_readback=mesh_proof,
        source_manifest_sha256=fio.sha(SOURCE/'manifest.json'), native_assets_prepared=True,
        level_saved=False, visual_accepted=False, runtime_or_device_tested=False)
    write(record)
    return record


def ready():
    guard()
    record = read()
    require(record.get('prepared'), 'Prepare the exported coast assets first')
    manifest, _ = source()
    require(signature(manifest) == record['signature'], 'Coast sources changed since preparation')
    require(fio.sha(record['first_baseline_file']) == record['first_baseline_sha256'],
            'Original coast baseline changed')
    require(fio.sha(SOURCE/'manifest.json') == record['source_manifest_sha256'], 'Coast export changed')
    verify_fingerprints(record)
    return record


def spawn_extension(record):
    actor = base.ACTORS.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
    require(actor is not None, 'Cannot spawn coast extension')
    actor.set_actor_label('Release coast extension - visual only')
    actor.set_editor_property('tags', [OWNER, ID, 'Opening.Decorative'])
    actor.set_actor_enable_collision(False)
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    component.set_static_mesh(base.load(record['mesh_path']))
    component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    component.set_editor_property('cast_shadow', False)
    component.set_material(0, base.load(record['material_path']))
    validate_extension(actor, record)
    return actor


def validate_extension(actor, record):
    value = state(actor)
    require(value['location_cm'] == [0., 0., 0.] and value['rotation'] == [0., 0., 0.] and
            value['scale'] == [1., 1., 1.], 'Coast extension transform changed')
    require(not value['actor_collision'] and not value['component_cast_shadow'] and
            value['component_visible'] and not value['hidden_in_game'], 'Coast extension visibility/physics changed')
    require(actor.get_component_by_class(unreal.StaticMeshComponent).get_collision_enabled() ==
            unreal.CollisionEnabled.NO_COLLISION, 'Coast extension acquired component collision')
    require(value['mesh'] == record['mesh_path'] and value['materials'] == [record['material_path']],
            'Coast extension uses different assets')
    require(not any(tag in value['tags'] for tag in ['Opening.PastOnly', 'Opening.PresentOnly']),
            'Coast extension must remain a common-era visual')
    return value


def check_scene(before, lights, refs, sea_name, ring_name):
    after = snapshot()
    require(set(after) == set(before)|{ring_name}, 'Unexpected actor addition/removal during coast operation')
    for name, baseline in before.items():
        if name == sea_name:
            require(all(after[name][key] == baseline[key] for key in baseline
                        if key not in ['materials', 'raw_override_materials']),
                    'Coast operation changed original sea geometry/collision/visibility/tags')
        else:
            require(after[name] == baseline, 'Coast operation changed another actor '+name)
    require(base.lighting() == lights and story() == refs, 'Coast operation changed sky/light/story/era references')


@contextmanager
def preview():
    """Unsaved editor preview for matched captures; always restores original state.

    Caller controls actual era/camera captures and labels them editor/PIE as used.
    Restore any era/visibility changes before leaving this context. Do not save
    the level from inside this context. This is not runtime proof.
    """
    guard(write_native=True)
    record = ready()
    require(not record.get('active'), 'Revert before previewing a different coast state')
    load_map()
    actor, ring = editable(record)
    require(ring is None, 'Unexpected extension before preview')
    before, lights, refs, files = snapshot(), base.lighting(), story(), protected_files()
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    overrides = list(component.get_editor_property('override_materials'))
    created = None
    try:
        component.set_material(0, base.load(record['material_path']))
        created = spawn_extension(record)
        check_scene(before, lights, refs, actor.get_name(), created.get_name())
        yield {'signature': record['signature'], 'kind': 'unsaved editor preview',
               'extension_actor': created.get_path_name(), 'runtime_proven': False}
    finally:
        if created:
            require(base.ACTORS.destroy_actor(created), 'Could not remove preview-only coast actor')
        component.set_editor_property('override_materials', overrides)
        require(snapshot() == before and base.lighting() == lights and story() == refs,
                'Preview cleanup did not restore all original scene state')
        check_files(files)
        # Preview deliberately leaves the editor package dirty even after state restoration.
        # Close/reload without saving, after this equality proof, before adoption.


def reviewed(record):
    require(REVIEW.exists(), 'Actual matched view/motion review record is required before adoption')
    data = json.loads(REVIEW.read_text(encoding='utf-8'))
    require(data['signature'] == record['signature'] and data['map'] == MAP,
            'Review belongs to a different candidate/map')
    expected = {(era, view) for era in ['Past', 'Present'] for view in
                ['RoomConversation', 'HomeFront', 'UphillCathedral', 'ClinicCourtyard', 'HarborOverlook']}
    require({(row['era'], row['view']) for row in data['views']} == expected,
            'Review must include five actual ordinary-height views in both eras')
    require({row['era'] for row in data['motion']} == {'Past', 'Present'}, 'Moving review required in both eras')
    for row in data['views']+data['motion']:
        path = Path(row['file']).resolve()
        require(path.is_relative_to((ROOT/'validation').resolve()) and fio.is_file(path) and
                fio.sha(path) == row['sha256'], 'Review evidence is missing, changed or outside validation')
    required = ['old_rectangular_edge_absent', 'shared_seam_continuous', 'sea_stays_blue_green',
                'reflection_contained', 'no_moving_shimmer_or_sorting', 'route_and_cathedral_unchanged']
    require(all(data['findings'].get(key) is True for key in required), 'Coast art/motion review did not pass')
    require(data['capture_kind'] in ['editor', 'PIE', 'standalone'], 'Label actual capture kind explicitly')
    require(data['reviewed_by'], 'Record who actually reviewed the evidence')
    return data


def adopt(revert=False):
    """One sea material override plus one no-collision visual ring, or exact reversal."""
    guard(write_native=True)
    record = ready()
    review = None if revert else reviewed(record)
    load_map()
    actor, ring = editable(record)
    if bool(record.get('active')) == (not revert):
        return {'idempotent': True, 'active': bool(record.get('active')), 'level_saved': False}
    before, lights, refs, files = snapshot(), base.lighting(), story(), protected_files()
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    if revert:
        require(ring is not None, 'No owned extension to reverse')
        ring_name = ring.get_name()
        require(base.ACTORS.destroy_actor(ring), 'Cannot remove the owned extension')
        component.set_editor_property('override_materials',
            [base.load(path) if path else None for path in record['baseline_sea']['raw_override_materials']])
        after = snapshot()
        require(set(after) == set(before)-{ring_name}, 'Reversal removed another actor')
        require(state(actor) == record['baseline_sea'], 'Reversal did not restore exact sea state')
        require(all(after[name] == baseline for name, baseline in before.items()
                    if name not in [actor.get_name(), ring_name]), 'Reversal changed another actor')
    else:
        require(ring is None, 'Extension exists before adoption')
        component.set_material(0, base.load(record['material_path']))
        ring = spawn_extension(record)
        check_scene(before, lights, refs, actor.get_name(), ring.get_name())
    require(base.lighting() == lights and story() == refs, 'Coast operation changed lighting/story')
    check_files(files)
    after_sea, after_ring = state(actor), None if revert else state(ring)
    require(base.LEVEL.save_current_level(), 'Cannot save the bounded coast change')
    check_files(files, map_save=True)
    require(base.LEVEL.load_level(MAP), 'Cannot reload coast persistence check')
    require(state(sea()) == after_sea, 'Sea material did not persist exactly')
    current = extension()
    require((current is None) if revert else (current is not None and state(current) == after_ring),
            'Coast extension did not persist exactly')
    require(base.lighting() == lights and story() == refs, 'Reload changed lighting/story state')
    record.update(active=not revert, reverted=revert, after_sea=after_sea,
        after_extension=after_ring, level_saved=True, persisted_reload_verified=True,
        visual_accepted=not revert, review_sha256=None if revert else fio.sha(REVIEW),
        review_capture_kind=None if revert else review['capture_kind'],
        packaged_runtime_verified=False, headset_tested=False, performance_measured=False)
    write(record)
    return record


def validate_saved():
    """Read-only persisted scene/mesh/material checks. Does not compile or save."""
    guard()
    record = ready()
    load_map()
    actor, ring = editable(record)
    require(record.get('active') and ring is not None, 'No active coast adoption')
    material, mesh = base.load(record['material_path']), base.load(record['mesh_path'])
    return {'success': True, 'map': MAP, 'sea': state(actor), 'extension': validate_extension(ring, record),
        'mesh': validate_mesh(mesh, material), 'water': validate_water(material),
        'assets_or_level_saved': False, 'runtime_tested': False, 'performance_measured': False}


if __name__ == '__main__':
    try:
        flags = {'ReleaseCoastPrepare': prepare, 'ReleaseCoastAdopt': adopt,
                 'ReleaseCoastRevert': lambda: adopt(revert=True), 'ReleaseCoastValidate': validate_saved}
        requested = [flag for flag in flags if unreal.SystemLibrary.parse_param(
            unreal.SystemLibrary.get_command_line(), flag)]
        require(len(requested) == 1, 'Select exactly one ReleaseCoast Prepare/Adopt/Revert/Validate action')
        result = flags[requested[0]]()
        unreal.log('RELEASE_COAST_RESULT '+json.dumps(result, default=str))
    except Exception:
        unreal.log_error(traceback.format_exc())
    finally:
        unreal.SystemLibrary.quit_editor()
