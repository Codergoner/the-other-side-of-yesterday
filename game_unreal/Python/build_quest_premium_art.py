"""Guarded photographic CC0 sky/material pass; queue after the active cook exits.

Only new /Game/Quest/PremiumArt assets are authored. Existing geometry, shared
materials, sun, actor transforms, collision and story references are preserved.
apply_premium() does not save a map. build_all() is the explicit queued writer.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy, hashlib, json, sys, traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import quest_scenery as base

SOURCE = ROOT.parent / 'output' / 'premium_sources'
REPORT = ROOT / 'quest_premium_art_report.json'
OWNED = 'TOSOY.QuestPremiumArtOwned'
STABLE_PREFIX = 'quest.premium.override.'
MAPS = ['/Game/Quest/Maps/Verdant_Desktop', '/Game/Quest/Maps/Verdant_VR']
POLICY = {
    'schema': 1, 'sky_intensity_scale': .10, 'cube_rotation_degrees': 0.0,
    'visible_sky_u_rotation': 0.0, 'plaster_normal_strength': .15,
    'wood_normal_strength': .30,
    'plaster_linear_gain': [2.1430, 2.0127, 1.7162],
    'wood_linear_gain': [4.6709, 4.4506, 3.8043],
    'plaster_roughness_scale_bias': [.35, .60],
    'wood_roughness_scale_bias': [.40, .50],
    'ao_strength': .20,
}
ASSETS = unreal.AssetToolsHelpers.get_asset_tools()
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVEL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def sha(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def read_report():
    return json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {'schema_version': 1, 'maps': {}}


def enabled_for_map(path):
    row = read_report().get('maps', {}).get(path, {})
    return bool(row.get('enabled') and row.get('success'))


def manifest():
    if ROOT.parent.name != 'Quest_20261025':
        raise RuntimeError('Premium art is restricted to the protected Quest copy')
    data = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    if data.get('material_set_count') != 2 or data.get('asset_count') != 3:
        raise RuntimeError('Expected exactly two PBR sets and one pure-sky HDRI')
    if data['license']['license'] != 'CC0 1.0 Universal':
        raise RuntimeError('Unexpected staged source license')
    if data['cooked_texture_memory_estimate']['total_bytes'] > 40 * 1024 * 1024:
        raise RuntimeError('Staged texture policy exceeds 40 MiB')
    for entry in data['files']:
        file = Path(entry['local_file']).resolve()
        if not file.is_relative_to(SOURCE.resolve()) or not file.is_file() or sha(file) != entry['sha256']:
            raise RuntimeError('Premium source changed or missing: ' + str(file))
    return data


def namespaces(data):
    source_id = hashlib.sha256(json.dumps([e['sha256'] for e in data['files']], sort_keys=True).encode()).hexdigest()[:12]
    shader_id = sha(Path(__file__))[:12]
    return '/Game/Quest/PremiumArt/Data_' + source_id, '/Game/Quest/PremiumArt/Shader_' + shader_id


def role_entry(data, asset, role):
    return next(e for e in data['files'] if e['asset'] == asset and e['role'] == role)


def source_guid(texture):
    try:
        return str(texture.call_method('Blueprint_GetTextureSourceIdString'))
    except Exception:
        return ''


def import_texture(entry, data_folder, name, kind, cap):
    path = data_folder + '/' + name
    texture = base.load(path)
    if texture:
        marker = unreal.EditorAssetLibrary.get_metadata_tag(texture, 'TOSOY.Premium.BuildState')
        if marker == 'Complete':
            saved_guid = unreal.EditorAssetLibrary.get_metadata_tag(texture, 'TOSOY.Premium.SourceGuid')
            if saved_guid and source_guid(texture) != saved_guid:
                raise RuntimeError('Preserving artist-edited premium texture source: ' + path)
            if texture.get_editor_property('max_texture_size') != cap or bool(texture.get_editor_property('srgb')) != (kind == 'color'):
                raise RuntimeError('Preserving changed premium texture import settings: ' + path)
            return texture
        if marker not in {'', 'Building'}:
            raise RuntimeError('Unknown existing texture ownership state: ' + path)
    else:
        task = unreal.AssetImportTask()
        for key, value in {'filename': entry['local_file'], 'destination_path': data_folder,
                           'destination_name': name, 'automated': True,
                           'replace_existing': False, 'save': False}.items():
            task.set_editor_property(key, value)
        ASSETS.import_asset_tasks([task])
        texture = base.load(path)
    expected = unreal.TextureCube if kind == 'hdr' else unreal.Texture2D
    if not isinstance(texture, expected):
        raise RuntimeError('Unexpected premium texture type in ' + path)
    unreal.EditorAssetLibrary.set_metadata_tag(texture, 'TOSOY.Premium.BuildState', 'Building')
    unreal.EditorAssetLibrary.set_metadata_tag(texture, 'TOSOY.Premium.Owner', OWNED)
    texture.set_editor_property('max_texture_size', cap)
    texture.set_editor_property('srgb', kind == 'color')
    compression = unreal.TextureCompressionSettings.TC_NORMALMAP if kind == 'normal' else unreal.TextureCompressionSettings.TC_MASKS if kind == 'mask' else unreal.TextureCompressionSettings.TC_HDR_COMPRESSED if kind == 'hdr' else unreal.TextureCompressionSettings.TC_DEFAULT
    texture.set_editor_property('compression_settings', compression)
    if kind == 'normal':
        texture.set_editor_property('flip_green_channel', False)  # Official DirectX normal source.
    if kind == 'hdr':
        texture.set_editor_property('never_stream', True)
    if entry['role'] == 'visible_sky_ldr':
        texture.set_editor_property('address_x', unreal.TextureAddress.TA_WRAP)
        texture.set_editor_property('address_y', unreal.TextureAddress.TA_CLAMP)
    unreal.EditorAssetLibrary.set_metadata_tag(texture, 'TOSOY.Premium.SourceSHA256', entry['sha256'])
    unreal.EditorAssetLibrary.set_metadata_tag(texture, 'TOSOY.Premium.SourceGuid', source_guid(texture))
    unreal.EditorAssetLibrary.set_metadata_tag(texture, 'TOSOY.Premium.BuildState', 'Complete')
    unreal.EditorAssetLibrary.save_loaded_asset(texture)
    return texture


def textures(data, data_folder):
    result = {}
    for asset, key in [('white_plaster_02', 'plaster'), ('fine_grained_wood', 'wood')]:
        for role, kind, cap in [('base_color', 'color', 2048), ('normal_dx', 'normal', 1024), ('ao_rough_metal', 'mask', 1024)]:
            name = 'T_PH_' + asset + '_' + role
            result[key + '_' + role] = import_texture(role_entry(data, asset, role), data_folder, name, kind, cap)
    result['sky_ldr'] = import_texture(role_entry(data, 'belfast_sunset_puresky', 'visible_sky_ldr'), data_folder, 'T_PH_BelfastSunset_LDR', 'color', 2048)
    result['sky_hdr'] = import_texture(role_entry(data, 'belfast_sunset_puresky', 'hdri'), data_folder, 'T_PH_BelfastSunset_HDRCube', 'hdr', 512)
    return result


def required_properties(key):
    if key == 'sky':
        return [unreal.MaterialProperty.MP_EMISSIVE_COLOR]
    return [unreal.MaterialProperty.MP_BASE_COLOR, unreal.MaterialProperty.MP_NORMAL,
            unreal.MaterialProperty.MP_ROUGHNESS, unreal.MaterialProperty.MP_METALLIC,
            unreal.MaterialProperty.MP_SPECULAR, unreal.MaterialProperty.MP_AMBIENT_OCCLUSION]


def complete(material, key):
    return all(unreal.MaterialEditingLibrary.get_material_property_input_node(material, p) for p in required_properties(key))


def mask(material, expression, channels):
    result = base.node(material, 'ComponentMask', r='r' in channels, g='g' in channels, b='b' in channels, a=False)
    base.connect(expression, result, '')
    return result


def material_assets(tex, shader_folder):
    result = {}
    for key, name in [('plaster', 'M_PhotoQuestLimewash'), ('wood', 'M_PhotoQuestTimber'), ('sky', 'M_PhotoQuestSky')]:
        material = base.load(shader_folder + '/' + name)
        if material:
            marker = unreal.EditorAssetLibrary.get_metadata_tag(material, 'TOSOY.Premium.BuildState')
            if complete(material, key):
                base.check_material_compile(material)
                result[key] = material
                continue
            if marker not in {'', 'Building'}:
                raise RuntimeError('Preserving edited completed premium material: ' + material.get_path_name())
            unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
        else:
            material = ASSETS.create_asset(name, shader_folder, unreal.Material, unreal.MaterialFactoryNew())
        if not material:
            raise RuntimeError('Cannot create premium material ' + name)
        unreal.EditorAssetLibrary.set_metadata_tag(material, 'TOSOY.Premium.Owner', OWNED)
        unreal.EditorAssetLibrary.set_metadata_tag(material, 'TOSOY.Premium.BuildState', 'Building')
        material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
        if key == 'sky':
            material.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
            material.set_editor_property('two_sided', True)
            material.set_editor_property('is_sky', True)
            uv = base.node(material, 'TextureCoordinate')
            # The existing sphere's U is -UE yaw/2pi and FBX imports V flipped.
            # UE HDR longlat cube uses U=frac(yaw/2pi+.75), V=acos(Z)/pi.
            # Thus this reuses correct mesh UVs without atan/acos per pixel.
            neg_u = base.node(material, 'Multiply')
            base.connect(mask(material, uv, 'r'), neg_u, 'A')
            base.connect(base.scalar(material, -1), neg_u, 'B')
            shifted_u = base.node(material, 'Add')
            base.connect(neg_u, shifted_u, 'A')
            base.connect(base.scalar(material, .75 + POLICY['visible_sky_u_rotation']), shifted_u, 'B')
            coords = base.node(material, 'AppendVector')
            base.connect(shifted_u, coords, 'A')
            base.connect(mask(material, uv, 'g'), coords, 'B')
            sample = base.sample(material, tex['sky_ldr'])
            base.connect(coords, sample, 'UVs')
            base.output(sample, material, unreal.MaterialProperty.MP_EMISSIVE_COLOR, 'RGB')
        else:
            material.set_editor_property('fully_rough', False)
            uv = base.node(material, 'TextureCoordinate', u_tiling=2.0 if key == 'plaster' else 10.0 / 3.0,
                           v_tiling=2.0 if key == 'plaster' else 10.0 / 3.0)
            sample = base.sample(material, tex[key + '_base_color'])
            base.connect(uv, sample, 'UVs')
            gain = base.node(material, 'Multiply')
            base.connect(sample, gain, 'A', 'RGB')
            base.connect(base.color(material, POLICY['plaster_linear_gain' if key == 'plaster' else 'wood_linear_gain']), gain, 'B')
            albedo = base.node(material, 'Clamp', min_default=0.0, max_default=.85)
            base.connect(gain, albedo, '')
            base.output(albedo, material, unreal.MaterialProperty.MP_BASE_COLOR)
            normal = base.sample(material, tex[key + '_normal_dx'], 'normal')
            base.connect(uv, normal, 'UVs')
            strength = POLICY['plaster_normal_strength' if key == 'plaster' else 'wood_normal_strength']
            softened = base.node(material, 'Multiply')
            base.connect(normal, softened, 'A', 'RGB')
            base.connect(base.color(material, [strength, strength, 1]), softened, 'B')
            normalized = base.node(material, 'Normalize')
            base.connect(softened, normalized, '')
            base.output(normalized, material, unreal.MaterialProperty.MP_NORMAL)
            arm = base.sample(material, tex[key + '_ao_rough_metal'], 'mask')
            base.connect(uv, arm, 'UVs')
            scale, bias = POLICY[key + '_roughness_scale_bias']
            rough_scale = base.node(material, 'Multiply')
            base.connect(arm, rough_scale, 'A', 'G')
            base.connect(base.scalar(material, scale), rough_scale, 'B')
            rough = base.node(material, 'Add')
            base.connect(rough_scale, rough, 'A')
            base.connect(base.scalar(material, bias), rough, 'B')
            base.output(rough, material, unreal.MaterialProperty.MP_ROUGHNESS)
            ao = base.node(material, 'LinearInterpolate')
            base.connect(base.scalar(material, 1), ao, 'A')
            base.connect(arm, ao, 'B', 'R')
            base.connect(base.scalar(material, POLICY['ao_strength']), ao, 'Alpha')
            base.output(ao, material, unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
            base.output(base.scalar(material, 0), material, unreal.MaterialProperty.MP_METALLIC)
            base.output(base.scalar(material, .25 if key == 'plaster' else .30), material, unreal.MaterialProperty.MP_SPECULAR)
        if not complete(material, key):
            raise RuntimeError('Incomplete premium material ' + name)
        base.check_material_compile(material)
        unreal.EditorAssetLibrary.set_metadata_tag(material, 'TOSOY.Premium.BuildState', 'Complete')
        unreal.EditorAssetLibrary.save_loaded_asset(material)
        result[key] = material
    return result


def state(actor):
    result = base.state(actor)
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    if component:
        result['raw_override_materials'] = [m.get_path_name() if m else None for m in component.get_editor_property('override_materials')]
    return result


def gameplay_state():
    result = {}
    for actor in base.actors():
        if isinstance(actor, unreal.WorldSettings):
            continue
        result[actor.get_name()] = {'location': base.xyz(actor.get_actor_location()),
            'rotation': [round(v, 4) for v in [actor.get_actor_rotation().pitch, actor.get_actor_rotation().yaw, actor.get_actor_rotation().roll]],
            'scale': base.xyz(actor.get_actor_scale3d()), 'collision': actor.get_actor_enable_collision()}
    return result


def source_material_key(material):
    if not material.get_path_name().startswith(('/Game/Harbor/', '/Game/Home/', '/Game/BriefTest/ArtKit/', '/Game/Quest/Scenery/', '/Game/Quest/PremiumArt/')):
        return None
    name = material.get_name()
    if name in {'M_Plaster', 'M_HomePlaster', 'M_QuestLimewash', 'M_PhotoQuestLimewash'}:
        return 'plaster'
    if name in {'M_Wood', 'M_Brief_Wood', 'M_QuestTimber', 'M_PhotoQuestTimber'}:
        return 'wood'
    return None


def owned_asset_hashes(data_folder, shader_folder):
    result = {}
    for package in [data_folder, shader_folder]:
        directory = ROOT / 'Content' / package.removeprefix('/Game/')
        for file in directory.rglob('*.uasset'):
            result[str(file.relative_to(ROOT)).replace('\\', '/')] = sha(file)
    return result


def canonical_for_base_refresh(snapshot):
    result = copy.deepcopy(snapshot)
    # Exactly the fields the base lighting pass intentionally resets. Keep
    # cubemap rotation/resolution and all artist fields in the comparison.
    if 'light' in result:
        for field in ['cubemap', 'intensity', 'source_type']:
            result['light'].pop(field, None)
    return result


def editable(actor, record, previous, reference, base_record=None):
    name = actor.get_name()
    reason = None
    if actor.actor_has_tag(base.MANUAL):
        reason = base.MANUAL
    elif name in record['inferred_manual_names']:
        reason = 'Previously detected artist change'
    elif base_record and name in base_record.get('inferred_manual_names', []):
        reason = 'Base generator preserved this artist-edited actor'
    elif name in previous:
        current, expected = state(actor), previous[name]
        if base_record and name in base_record.get('touched_names', []):
            current, expected = canonical_for_base_refresh(current), canonical_for_base_refresh(expected)
        if current != expected:
            reason = 'Actor differs from premium after-snapshot'
    elif name in reference and not base.states_match(base.state(actor), reference[name]):
        reason = 'Actor differs from saved base-scenery after-snapshot'
    elif name not in reference and not actor.actor_has_tag(OWNED):
        reason = 'No trusted first baseline for this actor'
    if reason:
        record['preserved_manual'].append({'actor': actor.get_path_name(), 'reason': reason})
        if name not in record['inferred_manual_names']:
            record['inferred_manual_names'].append(name)
        return False
    record['baseline'].setdefault(name, state(actor))
    return True


def add_owned_tag(actor):
    stable = STABLE_PREFIX + actor.get_name()
    duplicates = [a for a in base.actors() if a.actor_has_tag(stable)]
    if len(duplicates) > 1 or duplicates and duplicates[0] != actor:
        raise RuntimeError('Duplicate premium override stable ID ' + stable)
    base.tags(actor, OWNED, stable)


def apply_sky_light(actor, cube, intensity, sky_scale_override=None):
    light = actor.get_component_by_class(unreal.SkyLightComponent)
    light.set_editor_property('source_type', unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
    light.set_editor_property('cubemap', cube)
    light.set_editor_property('real_time_capture', False)
    light.set_editor_property('source_cubemap_angle', POLICY['cube_rotation_degrees'])
    light.set_editor_property('cubemap_resolution', 128)
    scale = POLICY['sky_intensity_scale'] if sky_scale_override is None else float(sky_scale_override)
    light.set_intensity(intensity * scale)


def sync_base_after(path, touched, enabled):
    if not base.REPORT.exists():
        return
    data = json.loads(base.REPORT.read_text(encoding='utf-8'))
    if path not in data.get('maps', {}):
        raise RuntimeError('No base scenery record for premium delegation')
    row = data['maps'][path]
    for actor in base.actors():
        if actor.get_name() in touched:
            row.setdefault('after', {})[actor.get_name()] = base.state(actor)
    row['premium_art_delegation'] = {'enabled': enabled, 'report': str(REPORT), 'owned_tag': OWNED}
    base.REPORT.write_text(json.dumps(data, indent=2), encoding='utf-8')


def measure_resources(world, data=None):
    data = data or manifest()
    data_folder, _ = namespaces(data)
    rows = []
    for path in unreal.EditorAssetLibrary.list_assets(data_folder, recursive=True, include_folder=False):
        texture = base.load(path)
        if not isinstance(texture, unreal.Texture):
            continue
        row = {'path': texture.get_path_name(), 'class': texture.get_class().get_name(),
               'max_texture_size': texture.get_editor_property('max_texture_size'),
               'compression': str(texture.get_editor_property('compression_settings'))}
        try:
            size = texture.call_method('Blueprint_GetBuiltTextureSize')
            row['built_platform_size'] = [int(size.x), int(size.y), int(size.z)]
            row['built_platform_gpu_bytes'] = int(texture.call_method('Blueprint_GetMemorySize'))
            row['source_disk_and_memory_bytes'] = str(texture.call_method('Blueprint_GetTextureSourceDiskAndMemorySize'))
        except Exception as error:
            row['resource_query_error'] = str(error)
        rows.append(row)
    unreal.SystemLibrary.execute_console_command(world, 'ListTextures -CSV -ALPHASORT')
    return {'scope': 'Current host/preview built platform-data sizes; not actual Quest GPU residency or measured Android cook sizes',
            'native_texture_rows': rows, 'queried_total_gpu_platform_bytes': sum(r.get('built_platform_gpu_bytes', 0) for r in rows),
            'native_console_command': 'ListTextures -CSV -ALPHASORT',
            'android_full_mip_policy_estimate': data['cooked_texture_memory_estimate']}


def apply_premium(world, base_record=None):
    path = base.map_path(world)
    data = manifest()
    data_folder, shader_folder = namespaces(data)
    all_report = read_report()
    old = all_report['maps'].get(path, {})
    previous = old.get('after', {}) if old.get('success') and old.get('enabled') else {}
    base_saved = json.loads(base.REPORT.read_text(encoding='utf-8'))['maps'].get(path, {}) if base.REPORT.exists() else {}
    reference = base_record.get('after', {}) if base_record else base_saved.get('after', {})
    record = {'success': False, 'enabled': False, 'map': path,
        'run': datetime.now(timezone.utc).isoformat(), 'data_namespace': data_folder, 'shader_namespace': shader_folder,
        'baseline': old.get('baseline', {}), 'inferred_manual_names': old.get('inferred_manual_names', []),
        'preserved_manual': [], 'material_overrides': [], 'touched_names': [], 'sky_light_changes': [],
        'policy': POLICY, 'provider': 'Poly Haven', 'license': 'CC0 1.0 Universal',
        'source_manifest': str(SOURCE / 'manifest.json'), 'native_visual_or_headset_validation': False}
    before_gameplay = gameplay_state()
    sun_before = {a.get_name(): base.state(a) for a in base.actors() if isinstance(a, unreal.DirectionalLight)}
    record['shared_input_sha_before'] = base.shared_asset_hashes()
    try:
        changed_owned = [p for p, expected in old.get('owned_asset_sha_after', {}).items() if not (ROOT / p).is_file() or sha(ROOT / p) != expected]
        if changed_owned:
            raise RuntimeError('Preserving edited premium assets; source apply stopped: ' + ', '.join(changed_owned))
        tex = textures(data, data_folder)
        mats = material_assets(tex, shader_folder)
        skies = [a for a in base.actors() if a.actor_has_tag('quest.visual.sky_dome')]
        skylights = [a for a in base.actors() if isinstance(a, unreal.SkyLight)]
        if len(skies) != 1 or len(skylights) != 1:
            raise RuntimeError('Expected one existing sky dome and skylight; no actor creation is allowed')
        for actor in base.actors():
            component = actor.get_component_by_class(unreal.StaticMeshComponent)
            mesh = component.get_editor_property('static_mesh') if component else None
            is_sky = actor == skies[0]
            if not mesh or not (is_sky or base.material_target(mesh.get_name())):
                continue
            assignments = [(0, 'sky')] if is_sky else [(i, source_material_key(component.get_material(i))) for i in range(component.get_num_materials()) if component.get_material(i)]
            assignments = [(i, key) for i, key in assignments if key]
            if not assignments or not editable(actor, record, previous, reference, base_record):
                continue
            for i, key in assignments:
                original = component.get_material(i)
                component.set_material(i, mats[key])
                record['material_overrides'].append({'actor': actor.get_path_name(), 'slot': i,
                    'from': original.get_path_name() if original else None, 'to': mats[key].get_path_name()})
            add_owned_tag(actor)
            record['touched_names'].append(actor.get_name())
        light_actor = skylights[0]
        if editable(light_actor, record, previous, reference, base_record):
            apply_sky_light(light_actor, tex['sky_hdr'], base.PROFILES[base.DEFAULT_PROFILE]['sky'])
            add_owned_tag(light_actor)
            record['touched_names'].append(light_actor.get_name())
            record['sky_light_changes'].append({'actor': light_actor.get_path_name(), 'cube': tex['sky_hdr'].get_path_name(), 'intensity': base.PROFILES[base.DEFAULT_PROFILE]['sky'] * POLICY['sky_intensity_scale']})
        if gameplay_state() != before_gameplay:
            raise RuntimeError('Premium art changed an actor transform or collision state')
        if sun_before != {a.get_name(): base.state(a) for a in base.actors() if isinstance(a, unreal.DirectionalLight)}:
            raise RuntimeError('Premium art changed the existing sun')
        touched = set(record['touched_names']) | set(previous)
        record['after'] = {a.get_name(): state(a) for a in base.actors() if a.get_name() in touched}
        record['shared_input_sha_after'] = {p: sha(ROOT / p) for p in record['shared_input_sha_before']}
        record['shared_inputs_unchanged'] = record['shared_input_sha_before'] == record['shared_input_sha_after']
        if not record['shared_inputs_unchanged']:
            raise RuntimeError('A shared source asset changed during premium authoring')
        record['actor_transforms_and_collision_unchanged'] = True
        record['single_sun_unchanged'] = True
        record['resources'] = measure_resources(world, data)
        record['owned_asset_sha_after'] = owned_asset_hashes(data_folder, shader_folder)
        record['enabled'] = record['success'] = True
        # During a base build its caller owns report serialization. Standalone
        # premium authoring updates the base fingerprint after delegation.
        if base_record is None:
            sync_base_after(path, touched, True)
    except Exception:
        record['error'] = traceback.format_exc()
        raise
    finally:
        if not record['success'] and old.get('enabled') and old.get('success'):
            old['last_failed_attempt'] = record
            all_report['maps'][path] = old  # Keep saved map fingerprints after a failed unsaved attempt.
        else:
            all_report['maps'][path] = record
        REPORT.write_text(json.dumps(all_report, indent=2), encoding='utf-8')
    return record


def preview_lighting(world, base_record, sky_scale_override=None):
    """Unsaved capture helper; never writes reports/assets/maps."""
    path = base.map_path(world)
    old = read_report().get('maps', {}).get(path, {})
    if not old.get('enabled') or not old.get('success'):
        return {'enabled': False}
    cube = base.load(old['sky_light_changes'][0]['cube']) if old.get('sky_light_changes') else None
    if not isinstance(cube, unreal.TextureCube):
        raise RuntimeError('Saved premium HDR cube is unavailable')
    result = {'enabled': True, 'baseline': {}, 'inferred_manual_names': list(old.get('inferred_manual_names', [])), 'preserved_manual': []}
    for actor in base.actors():
        if isinstance(actor, unreal.SkyLight) and editable(actor, result, old.get('after', {}), {}, base_record):
            apply_sky_light(actor, cube, base_record['lighting_values']['sky'], sky_scale_override)
            result['sky_scale_override'] = sky_scale_override
            result['applied_sky_intensity'] = actor.get_component_by_class(unreal.SkyLightComponent).get_editor_property('intensity')
    return result


def revert_premium(world):
    """Restore baseline component overrides/tags/skylight on unchanged actors."""
    path = base.map_path(world)
    data = read_report()
    old = data['maps'][path]
    result = {'baseline': old['baseline'], 'inferred_manual_names': list(old.get('inferred_manual_names', [])), 'preserved_manual': [], 'restored': []}
    for actor in base.actors():
        name = actor.get_name()
        baseline = old['baseline'].get(name)
        if not baseline or name not in old.get('after', {}) or not editable(actor, result, old['after'], {}):
            continue
        related = list(state(actor).get('materials', []))
        if isinstance(actor, unreal.SkyLight):
            related.append(state(actor).get('light', {}).get('cubemap'))
        changed_asset = False
        for asset in related:
            if not asset or not asset.startswith('/Game/Quest/PremiumArt/'):
                continue
            relative = 'Content/' + asset.split('.')[0].removeprefix('/Game/') + '.uasset'
            expected = old.get('owned_asset_sha_after', {}).get(relative)
            if expected and (not (ROOT / relative).is_file() or sha(ROOT / relative) != expected):
                result['preserved_manual'].append({'actor': actor.get_path_name(), 'reason': 'Referenced premium asset was edited'})
                changed_asset = True
                break
        if changed_asset:
            continue
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        if component:
            component.set_editor_property('override_materials', [base.load(p) if p else None for p in baseline.get('raw_override_materials', [])])
        if isinstance(actor, unreal.SkyLight):
            light = actor.get_component_by_class(unreal.SkyLightComponent)
            before = baseline['light']
            light.set_editor_property('source_type', unreal.SkyLightSourceType.SLS_CAPTURED_SCENE if 'CAPTURED_SCENE' in before.get('source_type', '') else unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
            light.set_editor_property('cubemap', base.load(before['cubemap']) if before.get('cubemap') else None)
            light.set_editor_property('source_cubemap_angle', float(before.get('source_cubemap_angle', 0)))
            light.set_editor_property('cubemap_resolution', int(before.get('cubemap_resolution', 128)))
            light.set_editor_property('real_time_capture', bool(before.get('real_time_capture', False)))
            light.set_intensity(float(before['intensity']))
        actor.set_editor_property('tags', [unreal.Name(t) for t in baseline['tags']])
        result['restored'].append(name)
    old['enabled'] = False
    old['revert'] = result
    data['maps'][path] = old
    REPORT.write_text(json.dumps(data, indent=2), encoding='utf-8')
    sync_base_after(path, result['restored'], False)
    return result


def build_all():
    if '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError('Use full editor -ExecutePythonScript; no commandlet UI access')
    if LEVEL.is_in_play_in_editor():
        raise RuntimeError('Premium authoring must run outside PIE')
    protected_files = [ROOT / 'YesterdayHarbor.uproject', *(ROOT / 'Config').glob('*.ini')]
    for folder in ['Harbor', 'Home', 'BriefTest']:
        protected_files.extend((ROOT / 'Content' / folder).rglob('*.umap'))
    protected = {str(file): sha(file) for file in protected_files if file.is_file()}
    report = {'success': False, 'maps': [], 'protected_before': protected,
              'scope': 'Versioned CC0 sky and known house/frontage material slots; no gameplay edits'}
    try:
        for path in MAPS:
            if not unreal.EditorAssetLibrary.does_asset_exist(path) or not LEVEL.load_level(path):
                raise RuntimeError('Existing production map is unavailable: ' + path)
            row = apply_premium(EDITOR.get_editor_world())
            if not LEVEL.save_current_level():
                raise RuntimeError('Cannot save guarded premium map ' + path)
            report['maps'].append({'path': path, 'material_assignments': len(row['material_overrides']),
                'manual_preserved': row['preserved_manual'], 'actor_transforms_and_collision_unchanged': row['actor_transforms_and_collision_unchanged'],
                'single_sun_unchanged': row['single_sun_unchanged'], 'shader_namespace': row['shader_namespace']})
        report['protected_after'] = {file: sha(Path(file)) for file in protected}
        report['protected_inputs_unchanged'] = protected == report['protected_after']
        if not report['protected_inputs_unchanged']:
            raise RuntimeError('A protected project, configuration or non-Quest map changed')
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        (ROOT / 'quest_premium_build_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('QUEST_PREMIUM_ART_COMPLETE ' + json.dumps(report['maps']), flush=True)
    return report


def calibrate_saved_sky():
    """Persist the native A/B-selected light scale without touching materials."""
    if ROOT.parent.name != 'Quest_20261025' or '-run=pythonscript' in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError('Use the protected Quest full editor for calibration')
    data = read_report()
    result = {'success': False, 'selected_scale': POLICY['sky_intensity_scale'],
              'evidence': str(ROOT / 'quest_premium_sky_probe_report.json'), 'maps': []}
    try:
        for path in MAPS:
            old = data['maps'][path]
            if not old.get('enabled') or not old.get('success') or not LEVEL.load_level(path):
                raise RuntimeError('Saved premium map unavailable for calibration: ' + path)
            if any(not (ROOT / p).is_file() or sha(ROOT / p) != expected for p, expected in old['owned_asset_sha_after'].items()):
                raise RuntimeError('Preserving edited premium assets; calibration stopped')
            world = EDITOR.get_editor_world()
            before = gameplay_state()
            sun = {a.get_name(): base.state(a) for a in base.actors() if isinstance(a, unreal.DirectionalLight)}
            guard = {'baseline': old['baseline'], 'inferred_manual_names': list(old.get('inferred_manual_names', [])), 'preserved_manual': []}
            lights = [a for a in base.actors() if isinstance(a, unreal.SkyLight)]
            if len(lights) != 1 or not editable(lights[0], guard, old['after'], {}):
                raise RuntimeError('Skylight is manually edited; calibration preserved it')
            actor = lights[0]
            intensity = base.PROFILES[base.DEFAULT_PROFILE]['sky'] * POLICY['sky_intensity_scale']
            actor.get_component_by_class(unreal.SkyLightComponent).set_intensity(intensity)
            if before != gameplay_state() or sun != {a.get_name(): base.state(a) for a in base.actors() if isinstance(a, unreal.DirectionalLight)}:
                raise RuntimeError('Calibration changed gameplay transforms/collision or sun')
            old['after'][actor.get_name()] = state(actor)
            old['policy'] = dict(POLICY)
            old['sky_light_changes'][0]['intensity'] = intensity
            old['calibration_evidence'] = result['evidence']
            data['maps'][path] = old
            REPORT.write_text(json.dumps(data, indent=2), encoding='utf-8')
            sync_base_after(path, [actor.get_name()], True)
            if not LEVEL.save_current_level():
                raise RuntimeError('Cannot save calibrated premium map ' + path)
            result['maps'].append({'path': path, 'saved': True, 'sky_intensity': intensity,
                                  'materials_unchanged': True, 'sun_and_gameplay_unchanged': True})
        result['success'] = True
    except Exception:
        result['error'] = traceback.format_exc()
        raise
    finally:
        (ROOT / 'quest_premium_calibration_report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    try:
        if '-questpremiumcalibrate' in unreal.SystemLibrary.get_command_line().lower():
            calibrate_saved_sky()
        else:
            build_all()
    except Exception:
        unreal.log_error('QUEST_PREMIUM_ART_FAILED\n' + traceback.format_exc())
    finally:
        unreal.SystemLibrary.quit_editor()
