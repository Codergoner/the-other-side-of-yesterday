"""Queued bounded hero surfaces and two decorative wall groups.

Default apply_floors() changes two explicit material slots only. Detail props
have a separate apply_details() gate, after actual floor review and Blender kit
export. Original meshes, coordinates, collision, materials and lights are never
edited. No whole-scene generator, NPC swap, story event or runtime Python.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy
import hashlib
import json
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
DEV = ROOT.parent
sys.path.insert(0, str(ROOT / 'Python'))
import build_release_art as base

SOURCE = DEV / 'output/release_hero_sources'
KIT = DEV / 'output/release_hero_kit'
PLAN = ROOT / 'ContentData/release_hero_plan.json'
REPORT = ROOT / 'release_hero_report.json'
MAP = '/Game/Quest/Maps/Verdant_Desktop'
MAP_FILE = ROOT / 'Content/Quest/Maps/Verdant_Desktop.umap'
OWNER = 'TOSOY.ReleaseHeroOwned'
LIB, MEL, ASSETS = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary, base.ASSETS
TRANSIENT_PREVIEW_REFERENCES = []


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def guard(write=False):
    base.guard()
    require(DEV.name == 'Release_20261026', 'Hero authoring refuses protected projects')
    if write:
        require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseHeroWrite'), 'Root queue and -ReleaseHeroWrite are required')


def config():
    data = json.loads(PLAN.read_text(encoding='utf-8'))
    require(data['map'] == MAP and len(data['floor_scope']) == 2 and len(data['props']) <= 10, 'Unexpected hero scope')
    require(data['caps']['new_triangles'] <= 12000 and data['caps']['new_colliders'] == 0 and data['caps']['new_lights'] == 0, 'Hero budget changed')
    selection_file = ROOT / 'release_floor_tint_selection.json'
    if selection_file.exists():
        selection = json.loads(selection_file.read_text(encoding='utf-8'))
        if selection.get('adopted'):
            require(selection['map'] == MAP and selection['base_plan_sha256'] == sha(PLAN), 'Floor palette selection belongs to a different plan')
            require(set(selection['linear_tints']) == {entry['role'] for entry in data['floor_scope']}, 'Unexpected selected floor palette roles')
            for recipe in data['floor_scope']:
                tint = selection['linear_tints'][recipe['role']]
                require(len(tint) == 3 and all(isinstance(v, (int, float)) and 0 < v <= 1 for v in tint), 'Unsafe floor palette multiplier')
                recipe['base_color_tint'] = tint
    return data


def source():
    data = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    require(data['success'] and data['source_count'] == 3 and data['map_count'] == 9, 'Expected three CC0 PBR sources')
    for asset in data['assets']:
        require(asset['license'] == 'CC0 1.0', 'Unapproved art license')
        for entry in asset['maps']:
            path = (SOURCE / entry['file']).resolve()
            require(path.is_relative_to(SOURCE.resolve()) and sha(path) == entry['sha256'], 'PBR source changed or escaped staging')
    return data


def read_report():
    return json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {'schema': 1, 'map': MAP}


def write_report(data):
    REPORT.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def files():
    paths = list((ROOT / 'Content').rglob('*.uasset')) + list((ROOT / 'Content').rglob('*.umap'))
    paths += list((ROOT / 'Config').glob('*.ini')) + list(ROOT.glob('*.uproject')) + list((ROOT / 'Saved/SaveGames').glob('*.sav'))
    return {str(path): sha(path) for path in paths}


def check_existing(before, changed_map=False):
    after = files()
    for path, digest in before.items():
        require((changed_map and Path(path) == MAP_FILE) or after.get(path) == digest, 'Existing protected file changed: ' + path)


def version(manifest, plan):
    policy = {'source': [(a['id'], [(m['kind'], m['sha256']) for m in a['maps']]) for a in manifest['assets']],
              'plan': plan, 'importer': sha(Path(__file__))}
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()[:16]


def mark(asset, signature, stage='Complete'):
    LIB.set_metadata_tag(asset, 'Release.Hero.Owner', OWNER)
    LIB.set_metadata_tag(asset, 'Release.Hero.Signature', signature)
    LIB.set_metadata_tag(asset, 'Release.Hero.Stage', stage)


def owned(asset, signature):
    require(LIB.get_metadata_tag(asset, 'Release.Hero.Owner') == OWNER and
            LIB.get_metadata_tag(asset, 'Release.Hero.Signature') == signature and
            LIB.get_metadata_tag(asset, 'Release.Hero.Stage') == 'Complete', 'Preserving unowned/unfinished hero asset: ' + asset.get_path_name())


def save(asset):
    require(LIB.save_loaded_asset(asset, only_if_is_dirty=False), 'Could not save ' + asset.get_path_name())


def texture(entry, folder, signature):
    name = 'T_Hero_' + Path(entry['file']).stem
    path = folder + '/Textures/' + name
    asset = unreal.load_asset(path) if LIB.does_asset_exist(path) else None
    if asset:
        owned(asset, signature)
        require(LIB.get_metadata_tag(asset, 'Release.Hero.SourceSHA256') == entry['sha256'], 'Preserving edited texture provenance')
        return asset
    task = unreal.AssetImportTask()
    for name_, value in {'filename': str(SOURCE / entry['file']), 'destination_path': folder + '/Textures',
                         'destination_name': name, 'automated': True, 'replace_existing': False, 'save': False}.items():
        task.set_editor_property(name_, value)
    ASSETS.import_asset_tasks([task])
    asset = unreal.load_asset(path)
    require(isinstance(asset, unreal.Texture2D), 'Hero texture import failed')
    mark(asset, signature, 'Building')
    kind = entry['kind']
    asset.set_editor_property('srgb', kind == 'base_color')
    asset.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP if kind == 'normal_directx' else
                             (unreal.TextureCompressionSettings.TC_GRAYSCALE if kind == 'roughness' else unreal.TextureCompressionSettings.TC_DEFAULT))
    asset.set_editor_property('max_texture_size', 2048)
    if entry['dimensions_px'] != [2048, 2048]:
        # Keep exact original2048x2052 provider bytes; build a mip-safe2k square
        # resource through native texture settings, not an edited source image.
        asset.set_editor_property('power_of_two_mode', unreal.TexturePowerOfTwoSetting.RESIZE_TO_SPECIFIC_RESOLUTION)
        asset.set_editor_property('resize_during_build_x', 2048)
        asset.set_editor_property('resize_during_build_y', 2048)
    if kind == 'normal_directx':
        asset.set_editor_property('flip_green_channel', False)
    LIB.set_metadata_tag(asset, 'Release.Hero.SourceSHA256', entry['sha256'])
    mark(asset, signature)
    save(asset)
    return asset


def sampled(mat, tex, uv, normal=False, rough=False):
    node = base.node(mat, 'TextureSample', texture=tex,
                     sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if normal else
                     (unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE if rough else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR))
    base.wire(uv, node, 'UVs')
    return node


def material(role, recipe, textures, folder, signature, save_asset=True):
    name = 'M_ReleaseHero_' + role
    path = folder + '/Materials/' + name
    mat = unreal.load_asset(path) if LIB.does_asset_exist(path) else None
    if mat:
        owned(mat, signature)
        return mat
    if save_asset:
        mat = ASSETS.create_asset(name, folder + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    else:
        # PyCore.NewObject defaults the omitted outer to GetTransientPackage;
        # this installed build does not expose a get_transient_package helper.
        mat = unreal.new_object(unreal.Material, name=name + '_' + signature)
        TRANSIENT_PREVIEW_REFERENCES.append(mat)
    require(mat, 'Could not create versioned hero material')
    mark(mat, signature, 'Building')
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    mat.set_editor_property('two_sided', False)
    uv = base.node(mat, 'TextureCoordinate', u_tiling=recipe['uv_scale'], v_tiling=recipe['uv_scale'])
    color = sampled(mat, textures['base_color'], uv)
    base_color = base.multiply(mat, color, base.scalar(mat, recipe['base_color_gain']))
    if 'base_color_tint' in recipe:
        base_color = base.multiply(mat, base_color, base.vector(mat, recipe['base_color_tint']))
    base.out(base_color, mat, unreal.MaterialProperty.MP_BASE_COLOR)
    normal = sampled(mat, textures['normal_directx'], uv, normal=True)
    scale = base.vector(mat, [recipe['normal_strength'], recipe['normal_strength'], 1.0])
    normalized = base.node(mat, 'Normalize')
    base.wire(base.multiply(mat, normal, scale), normalized)
    base.out(normalized, mat, unreal.MaterialProperty.MP_NORMAL)
    rough = sampled(mat, textures['roughness'], uv, rough=True)
    value = base.add(mat, base.multiply(mat, rough, base.scalar(mat, recipe['roughness_scale'])), base.scalar(mat, recipe['roughness_bias']))
    clamp = base.node(mat, 'Clamp', min_default=.72, max_default=.98)
    base.wire(value, clamp)
    base.out(clamp, mat, unreal.MaterialProperty.MP_ROUGHNESS)
    base.out(base.scalar(mat, .25), mat, unreal.MaterialProperty.MP_SPECULAR)
    base.out(base.scalar(mat, 0), mat, unreal.MaterialProperty.MP_METALLIC)
    errors = list(MEL.recompile_material(mat))
    require(not errors, 'Hero material compilation failed: ' + str(errors))
    LIB.set_metadata_tag(mat, 'Release.Hero.Recipe', json.dumps(recipe, sort_keys=True))
    mark(mat, signature)
    if save_asset:
        save(mat)
    return mat


def prepare_assets(plan, manifest, include_cloth=False, transient=False):
    signature = version(manifest, plan)
    folder = ('/Temp/ReleaseFloorTint/V_' if transient else '/Game/Release/Hero/V_') + signature
    textures = {}
    # Palette revisions reuse the verified original texture resources. Never
    # reimport a scanned map or modify its compression/sRGB/normal settings.
    cache = {}
    for filename, digest in read_report().get('owned_asset_fingerprints', {}).items():
        file = Path(filename).resolve()
        require(file.is_relative_to((ROOT / 'Content/Release/Hero').resolve()) and sha(file) == digest,
                'Preserving edited hero asset before texture reuse')
        if file.parent.name != 'Textures':
            continue
        path = '/Game/' + file.relative_to(ROOT / 'Content').with_suffix('').as_posix()
        asset = base.load(path)
        require(isinstance(asset, unreal.Texture2D) and LIB.get_metadata_tag(asset, 'Release.Hero.Owner') == OWNER and
                LIB.get_metadata_tag(asset, 'Release.Hero.Stage') == 'Complete', 'Texture cache is not a completed owned source')
        digest = LIB.get_metadata_tag(asset, 'Release.Hero.SourceSHA256')
        require(bool(digest), 'Texture cache has no source provenance')
        cache[digest] = asset
    recipes = {entry['role']: entry for entry in plan['floor_scope']}
    if include_cloth:
        recipes['woven_panel'] = plan['cloth']
    for entry in manifest['assets']:
        if entry['role'] in recipes:
            require(not transient or all(item['sha256'] in cache for item in entry['maps']),
                    'Transient palette preview requires all unchanged saved source textures')
            textures[entry['role']] = {item['kind']: cache[item['sha256']] if item['sha256'] in cache else texture(item, folder, signature) for item in entry['maps']}
    materials = {role: material(role, recipe, textures[role], folder, signature, save_asset=not transient) for role, recipe in recipes.items()}
    return signature, folder, materials


def material_readback(mat, recipe):
    require(mat is not None and mat.get_editor_property('blend_mode') == unreal.BlendMode.BLEND_OPAQUE, 'Hero material must remain opaque')
    for property_ in [unreal.MaterialProperty.MP_BASE_COLOR, unreal.MaterialProperty.MP_NORMAL,
                      unreal.MaterialProperty.MP_ROUGHNESS, unreal.MaterialProperty.MP_SPECULAR, unreal.MaterialProperty.MP_METALLIC]:
        require(MEL.get_material_property_input_node(mat, property_) is not None, 'Hero graph lacks a required output')
    require(MEL.get_material_property_input_node(mat, unreal.MaterialProperty.MP_EMISSIVE_COLOR) is None, 'Hero surface must not be emissive')
    expressions = list(MEL.get_material_expressions(mat))
    samples = [node for node in expressions if isinstance(node, unreal.MaterialExpressionTextureSample)]
    coords = [node for node in expressions if isinstance(node, unreal.MaterialExpressionTextureCoordinate)]
    require(len(samples) == 3 and len(coords) == 1, 'Unexpected hero texture sample/UV count')
    require(abs(coords[0].get_editor_property('u_tiling') - recipe['uv_scale']) < 1e-5 and
            abs(coords[0].get_editor_property('v_tiling') - recipe['uv_scale']) < 1e-5, 'Saved hero material scale differs')
    textures = []
    for node in samples:
        tex = node.get_editor_property('texture')
        require(tex.get_editor_property('max_texture_size') == 2048, 'Hero texture cap differs')
        textures.append({'path': tex.get_path_name(), 'srgb': bool(tex.get_editor_property('srgb')),
                         'compression': str(tex.get_editor_property('compression_settings')),
                         'sampler': str(node.get_editor_property('sampler_type')),
                         'max_texture_size': int(tex.get_editor_property('max_texture_size'))})
    require(sum(row['srgb'] for row in textures) == 1, 'Expected one sRGB albedo and two linear data maps')
    tint = recipe.get('base_color_tint')
    if tint:
        vectors = [node.get_editor_property('constant') for node in expressions if isinstance(node, unreal.MaterialExpressionConstant3Vector)]
        require(sum(all(abs(getattr(value, channel) - tint[i]) < 1e-6 for i, channel in enumerate(['r', 'g', 'b'])) for value in vectors) == 1,
                'Saved linear floor tint constant differs')
    return {'material': mat.get_path_name(), 'textures': textures, 'opaque': True,
            'source_repeat_metres': recipe['repeat_metres'], 'uv_scale': recipe['uv_scale'],
            'normal_strength_recipe': recipe['normal_strength'], 'geometry_displacement': False,
            'linear_base_color_tint_recipe': recipe.get('base_color_tint', [1, 1, 1]),
            'visual_quality_accepted': False}


def eligible(actor, previous, expected=None):
    if actor.actor_has_tag('TOSOY.ManualOverride') or actor.get_name() in previous.get('inferred_manual_names', []):
        return 'Explicit or previously detected manual override'
    after = previous.get('after', {}).get(actor.get_name()) if previous.get('success') and not previous.get('reverted') else None
    if after is not None and base.state(actor) != after:
        return 'Actor differs from last generated hero state'
    if after is None and expected:
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        value = comp.get_material(expected['slot'])
        if not value or value.get_name() != expected['expected_original_material'] or not base.copied_asset_unchanged(value):
            return 'Target is not the unchanged reviewed original material slot'
    return None


def apply_floors():
    guard(write=True)
    plan, manifest = config(), source()
    old = read_report()
    for path, digest in old.get('owned_asset_fingerprints', {}).items():
        require(Path(path).exists() and sha(path) == digest, 'Preserving artist-edited hero asset')
    before_files = files()
    signature, folder, materials = prepare_assets(plan, manifest)
    require(base.LEVEL.load_level(MAP), 'Cannot open desktop hero map')
    before, lights, story = base.snapshot(), base.lighting(), base.story_refs()
    previous_record = copy.deepcopy(old.get('floors', {}))
    record = copy.deepcopy(previous_record)
    record.update(success=False, preserved_manual=[], assignments=[])
    record.setdefault('baseline', {})
    record.setdefault('inferred_manual_names', [])
    if record.get('first_baseline_file'):
        require(sha(record['first_baseline_file']) == record['first_baseline_sha256'], 'First floor baseline changed')
    else:
        directory = ROOT/'validation/release_hero_baselines'
        directory.mkdir(parents=True, exist_ok=True)
        file = directory/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f') + '_floors_before.json')
        file.write_text(json.dumps(before, indent=2), encoding='utf-8')
        record['first_baseline_file'], record['first_baseline_sha256'] = str(file), sha(file)
    for target in plan['floor_scope']:
        actor = base.find_mesh(target['mesh'])
        reason = eligible(actor, previous_record, target)
        if reason:
            record['preserved_manual'].append({'actor': actor.get_name(), 'reason': reason})
            record['inferred_manual_names'] = sorted(set(record['inferred_manual_names'] + [actor.get_name()]))
            continue
        record['baseline'].setdefault(actor.get_name(), base.state(actor))
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_material(target['slot'], materials[target['role']])
        record['assignments'].append({'actor': actor.get_name(), 'slot': target['slot'], 'role': target['role'],
                                      'material': materials[target['role']].get_path_name()})
    after = base.snapshot()
    allowed = {entry['actor']: entry['slot'] for entry in record['assignments']}
    require(set(before) == set(after), 'Floor pass added or removed an actor')
    for name in before:
        require(base.physical(before[name]) == base.physical(after[name]), 'Floor pass changed geometry/transform/collision')
        if name not in allowed:
            require(before[name] == after[name], 'Unrelated actor changed')
        else:
            for slot, mat in enumerate(before[name]['materials']):
                require(slot == allowed[name] or after[name]['materials'][slot] == mat, 'Unrequested material slot changed')
    require(lights == base.lighting() and story == base.story_refs(), 'Floor pass changed light/story state')
    check_existing(before_files)
    map_changed = before != after
    if map_changed:
        require(base.LEVEL.save_current_level(), 'Could not save bounded floor overrides')
    record.update(success=True, after={name: after[name] for name in allowed}, reverted=False,
                  complete_scope=len(allowed) == 2, original_geometry_collision_transforms_unchanged=True,
                  map_saved=map_changed, idempotent_no_map_save=not map_changed)
    old.update(success=True, signature=signature, namespace=folder, floors=record,
               material_paths={role: mat.get_path_name() for role, mat in materials.items()},
               source_manifest_sha256=sha(SOURCE / 'manifest.json'), plan_sha256=sha(PLAN),
               native_visual_reviewed=False, original_lights_story_unchanged=True)
    check_existing(before_files, changed_map=True)
    owned_dir = ROOT / 'Content/Release/Hero' / ('V_' + signature)
    old['owned_asset_fingerprints'] = {**old.get('owned_asset_fingerprints', {}),
                                     **{str(path): sha(path) for path in owned_dir.rglob('*.uasset')}}
    write_report(old)
    return old


def validate_floors():
    guard()
    data = read_report()
    require(data.get('success') and data['floors']['success'] and not data['floors'].get('reverted'), 'No applied floor scope')
    require(base.LEVEL.load_level(MAP), 'Cannot reload floor map')
    rows = []
    recipes = {entry['role']: entry for entry in config()['floor_scope']}
    for assignment in data['floors']['assignments']:
        actor = next(actor for actor in base.actors() if actor.get_name() == assignment['actor'])
        require(base.state(actor) == data['floors']['after'][actor.get_name()], 'Saved floor state differs')
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        require(comp.get_material(assignment['slot']).get_path_name() == assignment['material'], 'Saved floor override differs')
        rows.append({'actor': actor.get_name(), 'slot': assignment['slot'], 'material': assignment['material'], 'passed': True,
                     'shader_readback': material_readback(comp.get_material(assignment['slot']), recipes[assignment['role']])})
    return {'success': True, 'rows': rows, 'complete_scope': len(rows) == 2, 'visual_accepted': False, 'no_save_calls': True}


def revert_floors():
    guard(write=True)
    data = read_report()
    old = data['floors']
    require(base.LEVEL.load_level(MAP), 'Cannot open floor reversal map')
    before, lights, story, before_files = base.snapshot(), base.lighting(), base.story_refs(), files()
    restored, preserved = [], []
    for name, baseline in old['baseline'].items():
        actor = next((actor for actor in base.actors() if actor.get_name() == name), None)
        if actor is None:
            preserved.append(name)
            continue
        if eligible(actor, old):
            preserved.append(name)
            continue
        actor.get_component_by_class(unreal.StaticMeshComponent).set_editor_property('override_materials',
            [base.load(path) if path else None for path in baseline['raw_override_materials']])
        require(base.state(actor) == baseline, 'First floor override baseline did not restore')
        restored.append(name)
    after = base.snapshot()
    require(all(before[name] == after[name] for name in before if name not in restored), 'Unrelated actor changed on floor reversal')
    require(lights == base.lighting() and story == base.story_refs(), 'Reversal changed lighting/story')
    require(base.LEVEL.save_current_level(), 'Could not save floor reversal')
    check_existing(before_files, changed_map=True)
    old['reverted'] = not preserved
    old['revert_result'] = {'restored': restored, 'preserved_manual': preserved}
    write_report(data)
    return old['revert_result']


def prop_materials(data):
    prefix = '/Game/BriefTest/ArtKit/V_20261025T092615_540187/Materials/'
    premium = base.approved_materials(MAP)
    mapping = {'M_ReleaseHero_Wood': premium['wood'], 'M_ReleaseHero_Ceramic': base.load(prefix + 'M_Brief_Ceramic'),
               'M_ReleaseHero_Terracotta': base.load(prefix + 'M_Brief_Terracotta'),
               'M_ReleaseHero_Cream': base.load(prefix + 'M_Brief_CreamCloth'),
               'M_ReleaseHero_Linen': base.load(data['material_paths']['woven_panel'])}
    require(all(mapping.values()), 'Required existing/premium hero materials are missing')
    return mapping


def import_prop(entry, folder, signature, mapping):
    path = folder + '/Meshes/' + entry['name']
    mesh = unreal.load_asset(path) if LIB.does_asset_exist(path) else None
    if mesh:
        owned(mesh, signature)
        return mesh
    file = KIT / entry['file']
    require(file.resolve().is_relative_to(KIT.resolve()) and sha(file) == entry['sha256'], 'Kit mesh source changed')
    options = unreal.FbxImportUI()
    for name, value in {'import_mesh': True, 'import_materials': False, 'import_textures': False,
                         'import_as_skeletal': False, 'mesh_type_to_import': unreal.FBXImportType.FBXIT_STATIC_MESH}.items():
        options.set_editor_property(name, value)
    settings = options.get_editor_property('static_mesh_import_data')
    for name, value in {'combine_meshes': True, 'transform_vertex_to_absolute': True, 'convert_scene': True,
                         'force_front_x_axis': False, 'convert_scene_unit': True, 'auto_generate_collision': False,
                         'generate_lightmap_u_vs': True, 'build_nanite': False}.items():
        settings.set_editor_property(name, value)
    task = unreal.AssetImportTask()
    for name, value in {'filename': str(file), 'destination_path': folder + '/Meshes', 'destination_name': entry['name'],
                         'automated': True, 'replace_existing': False, 'save': False, 'factory': unreal.FbxFactory(), 'options': options}.items():
        task.set_editor_property(name, value)
    ASSETS.import_asset_tasks([task])
    mesh = unreal.load_asset(path)
    require(isinstance(mesh, unreal.StaticMesh), 'Hero detail mesh import failed')
    slots = list(mesh.get_editor_property('static_materials'))
    require(len(slots) == len(entry['materials']), 'Imported detail material slot count differs')
    for index, slot in enumerate(slots):
        imported_name = str(slot.get_editor_property('imported_material_slot_name'))
        name = imported_name if imported_name in mapping else str(slot.get_editor_property('material_slot_name'))
        require(name in mapping and name in entry['materials'], 'Unknown imported detail material slot: ' + name)
        mesh.set_material(index, mapping[name])
    mark(mesh, signature)
    save(mesh)
    return mesh


def apply_details():
    guard(write=True)
    require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseHeroDetailsReviewed'), 'Actual floor art review and -ReleaseHeroDetailsReviewed are required')
    data, plan = read_report(), config()
    require(data.get('success') and data['floors']['complete_scope'], 'Review the applied two-floor scope first')
    kit = json.loads((KIT / 'manifest.json').read_text(encoding='utf-8'))
    require(kit['semantic_groups'] == 2 and kit['triangles'] <= 12000 and all(a['collision_count'] == 0 for a in kit['assets']), 'Unexpected geometry budget/collision')
    before_files = files()
    prop_signature = hashlib.sha256((sha(KIT/'manifest.json') + data['signature']).encode()).hexdigest()[:16]
    folder = data['namespace'] + '/Detail_' + prop_signature
    for path, digest in data.get('owned_asset_fingerprints', {}).items():
        require(Path(path).exists() and sha(path) == digest, 'Preserving artist-edited hero asset')
    _, _, prepared = prepare_assets(plan, source(), include_cloth=True)
    data['material_paths'].update({role: mat.get_path_name() for role,mat in prepared.items()})
    mapping = prop_materials(data)
    meshes = {entry['name']: import_prop(entry, folder, prop_signature, mapping) for entry in kit['assets']}
    require(base.LEVEL.load_level(MAP), 'Cannot open detail target map')
    before, lights, story = base.snapshot(), base.lighting(), base.story_refs()
    record = copy.deepcopy(data.get('details', {}))
    previous = record.get('after', {})
    record.update(success=False, preserved_manual=[], assignments=[])
    record.setdefault('inferred_manual_ids', [])
    for spec in plan['props']:
        found = [actor for actor in base.actors() if actor.actor_has_tag(spec['id'])]
        require(len(found) <= 1, 'Duplicate detail stable identity')
        actor = found[0] if found else None
        if actor and (spec['id'] in record['inferred_manual_ids'] or not actor.actor_has_tag(OWNER) or actor.actor_has_tag('TOSOY.ManualOverride') or
                      actor.get_name() not in previous or base.state(actor) != previous[actor.get_name()]):
            record['preserved_manual'].append(actor.get_path_name())
            record['inferred_manual_ids'] = sorted(set(record['inferred_manual_ids'] + [spec['id']]))
            continue
        if actor is None:
            actor = base.ACTORS.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*spec['position_cm']))
        actor.set_actor_label('Release hero - ' + spec['id'].split('.')[-1])
        actor.set_editor_property('tags', [OWNER, spec['id'], 'Opening.PresentOnly', 'Opening.Decorative'])
        actor.set_actor_location(unreal.Vector(*spec['position_cm']), False, False)
        actor.set_actor_rotation(unreal.Rotator(pitch=0, yaw=spec['yaw'], roll=0), False)
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_static_mesh(meshes[spec['mesh']])
        comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        actor.set_actor_enable_collision(False)
        origin, extent = actor.get_actor_bounds(False)
        bounds = {'min': [origin.x-extent.x, origin.y-extent.y, origin.z-extent.z],
                  'max': [origin.x+extent.x, origin.y+extent.y, origin.z+extent.z]}
        require(bounds['min'][2] >= 1200 and bounds['max'][2] <= 1302 and bounds['min'][0] >= -1060 and bounds['max'][0] <= -1018,
                'Native prop bounds escape the proposed upper-wall volume; do not save')
        record['assignments'].append({'actor': actor.get_name(), 'id': spec['id'], 'native_bounds_cm': bounds})
    managers = [actor for actor in base.actors() if actor.actor_has_tag('Opening.Manager')]
    require(len(managers) == 1, 'Exactly one existing manager is required')
    manager = managers[0]
    values = list(manager.get_editor_property('PresentActors'))
    for assignment in record['assignments']:
        actor = next(actor for actor in base.actors() if actor.get_name() == assignment['actor'])
        if actor not in values:
            values.append(actor)
    manager.set_editor_property('PresentActors', values)
    after = base.snapshot()
    touched = {assignment['actor'] for assignment in record['assignments']}
    require(set(after) == set(before) | touched, 'Unexpected actor creation/removal in decorative pass')
    require(all(after[name] == state for name,state in before.items() if name not in touched), 'Original scene geometry/actor state changed')
    require(lights == base.lighting(), 'Detail pass changed light fields')
    story_after = base.story_refs()
    for name, fields in story.items():
        require(all(story_after[name][key] == value for key,value in fields.items() if key != 'PresentActors'), 'Story identity/era state changed')
    check_existing(before_files)
    require(base.LEVEL.save_current_level(), 'Could not save additive decorative details')
    check_existing(before_files, changed_map=True)
    record.update(success=True, after={name: after[name] for name in touched}, namespace=folder,
                  visual_and_mother_route_reviewed=False, original_collision_unchanged=True)
    data['details'] = record
    owned_dir = ROOT/'Content'/data['namespace'].removeprefix('/Game/')
    data['owned_asset_fingerprints'] = {**data.get('owned_asset_fingerprints', {}),
                                      **{str(path): sha(path) for path in owned_dir.rglob('*.uasset')}}
    write_report(data)
    return record


def revert_details():
    guard(write=True)
    data, plan = read_report(), config()
    old = data['details']
    require(old.get('success'), 'No generated detail scope exists')
    require(base.LEVEL.load_level(MAP), 'Cannot open decorative reversal map')
    before, lights, story, before_files = base.snapshot(), base.lighting(), base.story_refs(), files()
    removed, preserved, candidates = [], [], []
    for spec in plan['props']:
        found = [actor for actor in base.actors() if actor.actor_has_tag(spec['id'])]
        require(len(found) <= 1, 'Duplicate decorative identity; preserve all')
        if not found:
            continue
        actor = found[0]
        if (not actor.actor_has_tag(OWNER) or actor.actor_has_tag('TOSOY.ManualOverride') or
            spec['id'] in old.get('inferred_manual_ids', []) or actor.get_name() not in old.get('after', {}) or
            base.state(actor) != old['after'][actor.get_name()]):
            preserved.append(spec['id'])
            old['inferred_manual_ids'] = sorted(set(old.get('inferred_manual_ids', []) + [spec['id']]))
        else:
            candidates.append(actor)
    manager = next(actor for actor in base.actors() if actor.actor_has_tag('Opening.Manager'))
    values = list(manager.get_editor_property('PresentActors'))
    manager.set_editor_property('PresentActors', [actor for actor in values if actor not in candidates])
    for actor in candidates:
        name = actor.get_name()
        require(base.ACTORS.destroy_actor(actor), 'Could not remove unchanged owned detail')
        removed.append(name)
    after = base.snapshot()
    require(set(after) == set(before) - set(removed), 'Reversal affected another actor')
    require(all(before[name] == state for name,state in after.items()), 'Reversal changed unrelated geometry/actor state')
    require(lights == base.lighting(), 'Decorative reversal changed lighting')
    story_after = base.story_refs()
    for name, fields in story.items():
        require(all(story_after[name][key] == value for key,value in fields.items() if key != 'PresentActors'), 'Reversal changed story refs')
    check_existing(before_files)
    require(base.LEVEL.save_current_level(), 'Could not save decorative reversal')
    check_existing(before_files, changed_map=True)
    old.update(reverted=not preserved, revert_result={'removed': removed, 'preserved_manual': preserved, 'assets_retained': True})
    write_report(data)
    return old['revert_result']


if __name__ == '__main__':
    try:
        command = unreal.SystemLibrary.get_command_line()
        if unreal.SystemLibrary.parse_param(command, 'RevertReleaseHeroDetails'):
            result = revert_details()
        elif unreal.SystemLibrary.parse_param(command, 'RevertReleaseHeroFloors'):
            result = revert_floors()
        else:
            result = apply_details() if unreal.SystemLibrary.parse_param(command, 'ReleaseHeroDetailsReviewed') else apply_floors()
        if 'floors' in result:
            validate_floors()
    except Exception:
        (ROOT/'release_hero_failure.json').write_text(json.dumps({'success': False, 'error': traceback.format_exc()}, indent=2), encoding='utf-8')
        raise
    finally:
        unreal.SystemLibrary.quit_editor()
