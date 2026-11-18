"""Guarded, additive Quest scenery for cloned /Game/Quest/Maps/ worlds only.

Called by the district generator as apply_scenery(world). No map is loaded,
saved, deleted or regenerated here. Shared mesh/material assets are read-only.
All lighting values are initial A/B candidates until native mobile validation.
"""
from pathlib import Path
from datetime import datetime, timezone
import json, hashlib, math, traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
DEV = ROOT.parent
SOURCE = DEV / 'output' / 'quest_scenery'
REPORT = ROOT / 'quest_scenery_report.json'
OWNED = 'TOSOY.QuestVisualOwned'
MANUAL = 'TOSOY.ManualOverride'
ASSETS = unreal.AssetToolsHelpers.get_asset_tools()
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
DEFAULT_PROFILE = 'QuestSoft'
PROFILES = {
    'QuestBalanced': {'sun': 5.0, 'sky': .85, 'pitch': -23.0, 'yaw': 135.0, 'sun_rgb': [1.0, .89, .75], 'fog': .0014},
    'QuestSoft': {'sun': 3.5, 'sky': 1.05, 'pitch': -23.0, 'yaw': 135.0, 'sun_rgb': [1.0, .92, .82], 'fog': .0014},
    'QuestGolden': {'sun': 6.5, 'sky': .75, 'pitch': -23.0, 'yaw': 135.0, 'sun_rgb': [1.0, .87, .70], 'fog': .0014},
}
FACADE_MESHES = {'SM_Home_Timber', 'SM_Home_Balcony', 'SM_Home_Details', 'SM_LeftHouse_B', 'SM_LeftHouse_C'}
WOOD_NAMES = {'M_Wood', 'M_Brief_Wood'}
LEGACY_POINT_LABELS = {'Home ground floor warm fill', 'Home upper room warm fill', 'Home stairwell warm fill', 'Home porch lantern spill'}
LIGHT_PROPS = ['intensity', 'light_color', 'visible', 'cast_shadows', 'mobility', 'indirect_lighting_intensity', 'volumetric_scattering_intensity', 'attenuation_radius', 'intensity_units', 'real_time_capture', 'source_type', 'cubemap', 'source_cubemap_angle', 'cubemap_resolution', 'lower_hemisphere_is_black', 'lower_hemisphere_color', 'atmosphere_sun_light', 'dynamic_shadow_distance_movable_light', 'dynamic_shadow_cascades']


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')


def value(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, unreal.Object):
        return v.get_path_name()
    if isinstance(v, unreal.Color):
        return [v.r, v.g, v.b, v.a]
    if isinstance(v, unreal.LinearColor):
        return [round(v.r, 6), round(v.g, 6), round(v.b, 6), round(v.a, 6)]
    return str(v)


def get(obj, field):
    try:
        return value(obj.get_editor_property(field))
    except Exception:
        return None


def xyz(v):
    return [round(v.x, 4), round(v.y, 4), round(v.z, 4)]


def state(actor):
    comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    light = actor.get_component_by_class(unreal.LightComponentBase)
    s = {'name': actor.get_name(), 'label': actor.get_actor_label(), 'class': actor.get_class().get_path_name(), 'location_cm': xyz(actor.get_actor_location()), 'rotation': [round(n, 4) for n in [actor.get_actor_rotation().pitch, actor.get_actor_rotation().yaw, actor.get_actor_rotation().roll]], 'scale': xyz(actor.get_actor_scale3d()), 'tags': sorted(str(t) for t in actor.get_editor_property('tags')), 'hidden_in_game': get(actor, 'hidden'), 'collision': actor.get_actor_enable_collision(), 'mesh': None, 'materials': []}
    if comp:
        mesh = comp.get_editor_property('static_mesh')
        s.update({'mesh': mesh.get_path_name() if mesh else None, 'materials': [comp.get_material(i).get_path_name() if comp.get_material(i) else None for i in range(comp.get_num_materials())], 'component_visible': get(comp, 'visible'), 'cast_shadow': get(comp, 'cast_shadow'), 'collision_enabled': str(comp.get_collision_enabled())})
    if light:
        s['light'] = {p: get(light, p) for p in LIGHT_PROPS if get(light, p) is not None}
    if isinstance(actor, unreal.PostProcessVolume):
        settings = actor.get_editor_property('settings')
        s['post_process'] = {p: get(settings, p) for p in ['auto_exposure_bias', 'auto_exposure_method', 'auto_exposure_apply_physical_camera_exposure', 'motion_blur_amount', 'depth_of_field_focal_distance', 'bloom_intensity']}
    if isinstance(actor, unreal.ExponentialHeightFog):
        fog = actor.get_component_by_class(unreal.ExponentialHeightFogComponent)
        s['fog'] = {p: get(fog, p) for p in ['visible', 'fog_density', 'fog_height_falloff', 'fog_inscattering_luminance', 'enable_volumetric_fog']}
    if isinstance(actor, unreal.SkyAtmosphere):
        s['atmosphere_visible'] = get(actor.get_component_by_class(unreal.SkyAtmosphereComponent), 'visible')
    return s


def actors():
    return list(ACTORS.get_all_level_actors())


def tags(actor, *items):
    old = [str(t) for t in actor.get_editor_property('tags')]
    actor.set_editor_property('tags', [unreal.Name(t) for t in old + [t for t in items if t not in old]])


def unique(id):
    found = [a for a in actors() if a.actor_has_tag(id)]
    if len(found) > 1:
        raise RuntimeError('Duplicate Quest scenery stable ID: ' + id)
    return found[0] if found else None


def map_path(world):
    if DEV.name != 'Release_20261026':
        raise RuntimeError('Release scenery may run only in Release_20261026')
    name = world.get_path_name().split('.')[0]
    if not name.startswith('/Game/Quest/Maps/'):
        raise RuntimeError('Scenery refuses to modify a non-Quest map: ' + name)
    if world != EDITOR.get_editor_world():
        raise RuntimeError('Expected the active editor world, not a PIE or foreign world')
    return name


def initial_reference():
    # Resolve a local copied validation record, never old absolute import metadata.
    candidates = sorted((ROOT / 'validation' / 'brief_art').glob('*/Quarter_FirstPerson_after.json'))
    return json.loads(candidates[-1].read_text(encoding='utf-8')) if candidates else {}


def material_target(mesh_name):
    # The family house is split into shell, floors, porch, furniture, stairs,
    # ruin, roof and details. Known wood/plaster slots need the same palette in
    # every group; stone, roof tile, fabric, glass and hardware remain intact.
    return mesh_name.startswith('SM_Home_') or mesh_name in FACADE_MESHES


def material_key(mesh_name, material):
    if mesh_name == 'SM_Sea':
        return 'water'
    if not material_target(mesh_name):
        return None
    name = material.get_name()
    if name in WOOD_NAMES:
        return 'timber'
    if name in {'M_Plaster', 'M_HomePlaster'}:
        return 'plaster'
    if material.get_path_name().startswith('/Game/Quest/Scenery/'):
        return {'M_QuestTimber': 'timber', 'M_QuestLimewash': 'plaster'}.get(name)
    return None


def comparable(s):
    # Cloned world paths and ownership tags differ legitimately; compare content.
    return {k: s.get(k) for k in ['location_cm', 'rotation', 'scale', 'mesh', 'materials', 'hidden_in_game'] if k in s}


def states_match(current, previous):
    # One-time fingerprint schema migration for fields not recorded before the
    # photographic pass. Once stored, artist changes to them stay protected.
    normalized = dict(current)
    if 'light' in current and 'light' in previous:
        normalized['light'] = dict(current['light'])
        for field in ['source_cubemap_angle', 'cubemap_resolution']:
            if field not in previous['light']:
                normalized['light'].pop(field, None)
    return normalized == previous


def editable(actor, record, previous, reference):
    name = actor.get_name()
    reason = None
    if actor.actor_has_tag(MANUAL):
        reason = MANUAL
    elif name in record.get('inferred_manual_names', []):
        reason = 'Previously detected external change'
    elif name in previous and not states_match(state(actor), previous[name]):
        reason = 'Actor changed since last Quest scenery snapshot'
    elif name not in previous and name in reference and comparable(state(actor)) != comparable(reference[name]):
        reason = 'Actor differs from copied Brief baseline'
    if reason:
        if name not in record['inferred_manual_names']:
            record['inferred_manual_names'].append(name)
        record['preserved_manual'].append({'actor': actor.get_path_name(), 'reason': reason})
        return False
    record['baseline'].setdefault(name, state(actor))
    return True


def prop(obj, field, setting, record):
    try:
        obj.set_editor_property(field, setting)
        return True
    except Exception as error:
        record['unsupported_optional_properties'].append({'object': obj.get_path_name() if isinstance(obj, unreal.Object) else type(obj).__name__, 'property': field, 'error': str(error)})
        return False


def load(path):
    return unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None


def source_file(relative):
    p = (SOURCE / relative).resolve()
    if not p.is_relative_to(SOURCE.resolve()) or not p.exists():
        raise RuntimeError('Invalid or missing local scenery source ' + relative)
    return p


def shared_asset_hashes():
    """Byte baselines for shared assets receiving component-only overrides."""
    found = {}
    for actor in actors():
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        mesh = component.get_editor_property('static_mesh') if component else None
        if not mesh or not (material_target(mesh.get_name()) or mesh.get_name() in {'SM_Sea', 'SM_DistantMountains'}):
            continue
        for asset in [mesh] + [component.get_material(i) for i in range(component.get_num_materials())]:
            if not asset:
                continue
            package = asset.get_path_name().split('.')[0]
            if not package.startswith('/Game/') or package.startswith('/Game/Quest/'):
                continue
            file = ROOT / 'Content' / (package.removeprefix('/Game/') + '.uasset')
            if file.exists():
                found[str(file.relative_to(ROOT)).replace('\\', '/')] = hashlib.sha256(file.read_bytes()).hexdigest()
    return found


def texture(file, folder, kind):
    path = folder + '/Textures/' + file.stem
    result = load(path)
    if result:
        return result
    task = unreal.AssetImportTask()
    for key, v in {'filename': str(file), 'destination_path': folder + '/Textures', 'destination_name': file.stem, 'automated': True, 'replace_existing': False, 'save': True}.items():
        task.set_editor_property(key, v)
    ASSETS.import_asset_tasks([task])
    result = load(path)
    if not isinstance(result, unreal.Texture):
        raise RuntimeError('Cannot import texture ' + str(file))
    result.set_editor_property('srgb', kind == 'color')
    if kind == 'normal':
        result.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
        result.set_editor_property('flip_green_channel', True)
    elif kind == 'mask':
        result.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_MASKS)
    unreal.EditorAssetLibrary.save_loaded_asset(result)
    return result


def node(mat, name, **props):
    n = unreal.MaterialEditingLibrary.create_material_expression(mat, getattr(unreal, 'MaterialExpression' + name), -400, 0)
    for k, v in props.items():
        n.set_editor_property(k, v)
    return n


def connect(a, b, pin, output=''):
    library = unreal.MaterialEditingLibrary
    if library.connect_material_expressions(a, output, b, pin):
        return
    inputs = [str(n) for n in library.get_material_expression_input_names(b)]
    outputs = [str(n) for n in library.get_material_expression_output_names(a)]
    # UE shortens a unary "Input" graph pin to NAME_None. It is safe to
    # select the first input automatically only when there is exactly one.
    if pin and len(inputs) == 1 and library.connect_material_expressions(a, output, b, ''):
        return
    raise RuntimeError('Cannot connect material expression: ' + json.dumps({
        'source': a.get_class().get_name(), 'requested_output': output,
        'available_outputs': outputs, 'destination': b.get_class().get_name(),
        'requested_input': pin, 'available_inputs': inputs}))


def output(a, mat, property, pin=''):
    if not unreal.MaterialEditingLibrary.connect_material_property(a, pin, property):
        raise RuntimeError('Cannot connect material property ' + str(property))


def scalar(mat, number):
    return node(mat, 'Constant', r=float(number))


def color(mat, rgb):
    return node(mat, 'Constant3Vector', constant=unreal.LinearColor(*rgb, 1))


def linear(rgb):
    return [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in [c / 255 for c in rgb]]


def sample(mat, tex, kind='color'):
    n = node(mat, 'TextureSample', texture=tex)
    if kind != 'color':
        n.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if kind == 'normal' else unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    return n


def vertex_channel(mat, vertex, channels):
    # VertexColor's first output is RGBA in this installed editor, not a named
    # RGB output. Explicit masks also avoid relying on its channel labels.
    mask = node(mat, 'ComponentMask', r='r' in channels, g='g' in channels,
                b='b' in channels, a='a' in channels)
    connect(vertex, mask, '')
    return mask


def required_material_properties(key):
    if key == 'sky':
        return [unreal.MaterialProperty.MP_EMISSIVE_COLOR]
    result = [unreal.MaterialProperty.MP_BASE_COLOR, unreal.MaterialProperty.MP_ROUGHNESS,
              unreal.MaterialProperty.MP_METALLIC, unreal.MaterialProperty.MP_SPECULAR]
    if key in {'water', 'plaster'}:
        result.append(unreal.MaterialProperty.MP_NORMAL)
    return result


def material_connections_complete(mat, key):
    return all(unreal.MaterialEditingLibrary.get_material_property_input_node(mat, p)
               for p in required_material_properties(key))


def check_material_compile(mat):
    # UE 5.8 returns compiler errors, rather than a boolean, from this call.
    errors = unreal.MaterialEditingLibrary.recompile_material(mat)
    if errors:
        raise RuntimeError('Quest material compiler errors in ' + mat.get_path_name() + ': ' + '; '.join(str(e) for e in errors))


def material_assets(manifest, folder, record):
    textures = {key: texture(source_file(file), folder, 'normal' if 'normal' in key else 'mask' if key == 'cloud' else 'color') for key, file in manifest['textures'].items()}
    result = {}
    for key, name in [('land', 'M_QuestDistantLand'), ('water', 'M_QuestWater'), ('timber', 'M_QuestTimber'), ('plaster', 'M_QuestLimewash'), ('sky', 'M_QuestCoastalSky')]:
        mat = load(folder + '/Materials/' + name)
        if mat:
            marker = unreal.EditorAssetLibrary.get_metadata_tag(mat, 'TOSOY.QuestScenery.BuildState')
            if material_connections_complete(mat, key):
                check_material_compile(mat)
                result[key] = mat
                continue
            if marker not in {'', 'Building'}:
                raise RuntimeError('Preserving an edited completed Quest material with missing inputs: ' + mat.get_path_name())
            # A failed first authoring run can leave an incomplete asset. Only
            # that current manifest's versioned, unfinished graph is repaired.
            unreal.MaterialEditingLibrary.delete_all_material_expressions(mat)
            record.setdefault('repaired_incomplete_materials', []).append(mat.get_path_name())
        else:
            mat = ASSETS.create_asset(name, folder + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
        if not mat:
            raise RuntimeError('Cannot create versioned material ' + name)
        unreal.EditorAssetLibrary.set_metadata_tag(mat, 'TOSOY.QuestScenery.BuildState', 'Building')
        unreal.EditorAssetLibrary.set_metadata_tag(mat, 'TOSOY.QuestScenery.Owner', OWNED)
        if key == 'sky':
            mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
            mat.set_editor_property('two_sided', True)
            prop(mat, 'is_sky', True, record)
            vc = node(mat, 'VertexColor')
            gradient = node(mat, 'LinearInterpolate')
            connect(color(mat, linear([223, 191, 148])), gradient, 'A')
            connect(color(mat, linear([92, 145, 181])), gradient, 'B')
            connect(vertex_channel(mat, vc, 'r'), gradient, 'Alpha')
            uv = node(mat, 'TextureCoordinate', u_tiling=3.0, v_tiling=2.0)
            pan = node(mat, 'Panner', speed_x=.0006, speed_y=.00015)
            connect(uv, pan, 'Coordinate')
            clouds = sample(mat, textures['cloud'], 'mask')
            connect(pan, clouds, 'UVs')
            cloud_weight = node(mat, 'Multiply')
            connect(clouds, cloud_weight, 'A', 'R')
            connect(vertex_channel(mat, vc, 'g'), cloud_weight, 'B')
            cloud_mix = node(mat, 'LinearInterpolate')
            connect(gradient, cloud_mix, 'A')
            connect(color(mat, linear([240, 218, 186])), cloud_mix, 'B')
            connect(cloud_weight, cloud_mix, 'Alpha')
            # A tiny analytic sun disc aligns with the common -23/135 sun.
            position = node(mat, 'WorldPosition')
            direction = node(mat, 'Normalize')
            connect(position, direction, '')
            dot = node(mat, 'DotProduct')
            connect(direction, dot, 'A')
            connect(color(mat, [.650895, -.650895, .390731]), dot, 'B')
            edge = node(mat, 'Subtract')
            connect(dot, edge, 'A')
            connect(scalar(mat, .99994), edge, 'B')
            gain = node(mat, 'Multiply')
            connect(edge, gain, 'A')
            connect(scalar(mat, 25000), gain, 'B')
            disc = node(mat, 'Clamp', min_default=0.0, max_default=1.0)
            connect(gain, disc, '')
            final = node(mat, 'LinearInterpolate')
            connect(cloud_mix, final, 'A')
            connect(color(mat, [1.0, .86, .59]), final, 'B')
            connect(disc, final, 'Alpha')
            output(final, mat, unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        else:
            roughness, specular = (.97, .15) if key == 'land' else (.30, .25) if key == 'water' else (.80, .32) if key == 'timber' else (.90, .25)
            output(scalar(mat, roughness), mat, unreal.MaterialProperty.MP_ROUGHNESS)
            output(scalar(mat, 0), mat, unreal.MaterialProperty.MP_METALLIC)
            output(scalar(mat, specular), mat, unreal.MaterialProperty.MP_SPECULAR)
            if key == 'land':
                tint = node(mat, 'Multiply')
                connect(color(mat, linear([146, 159, 166])), tint, 'A')
                connect(vertex_channel(mat, node(mat, 'VertexColor'), 'rgb'), tint, 'B')
                output(tint, mat, unreal.MaterialProperty.MP_BASE_COLOR)
                prop(mat, 'fully_rough', True, record)
            elif key == 'water':
                output(color(mat, linear([31, 89, 101])), mat, unreal.MaterialProperty.MP_BASE_COLOR)
                uv = node(mat, 'TextureCoordinate', u_tiling=.24, v_tiling=.24)
                pan = node(mat, 'Panner', speed_x=.008, speed_y=.003)
                connect(uv, pan, 'Coordinate')
                normal = sample(mat, textures['water_normal'], 'normal')
                connect(pan, normal, 'UVs')
                output(normal, mat, unreal.MaterialProperty.MP_NORMAL, 'RGB')
            else:
                output(sample(mat, textures[key]), mat, unreal.MaterialProperty.MP_BASE_COLOR, 'RGB')
                if key == 'plaster':
                    output(sample(mat, textures['plaster_normal'], 'normal'), mat, unreal.MaterialProperty.MP_NORMAL, 'RGB')
                prop(mat, 'fully_rough', True, record)
        if not material_connections_complete(mat, key):
            raise RuntimeError('Quest material is missing a required output: ' + mat.get_path_name())
        check_material_compile(mat)
        unreal.EditorAssetLibrary.set_metadata_tag(mat, 'TOSOY.QuestScenery.BuildState', 'Complete')
        unreal.EditorAssetLibrary.save_loaded_asset(mat)
        result[key] = mat
    return result


def mesh_assets(manifest, folder, materials):
    result = {}
    for entry in manifest['assets']:
        name = entry['name']
        path = folder + '/Meshes/' + name
        asset = load(path)
        if not asset:
            options = unreal.FbxImportUI()
            for k, v in {'import_mesh': True, 'import_as_skeletal': False, 'import_materials': False, 'import_textures': False, 'automated_import_should_detect_type': False, 'mesh_type_to_import': unreal.FBXImportType.FBXIT_STATIC_MESH}.items():
                options.set_editor_property(k, v)
            data = options.get_editor_property('static_mesh_import_data')
            for k, v in {'combine_meshes': True, 'transform_vertex_to_absolute': True, 'convert_scene': True, 'convert_scene_unit': True, 'force_front_x_axis': False, 'auto_generate_collision': False, 'generate_lightmap_u_vs': True, 'build_nanite': False, 'remove_degenerates': True, 'vertex_color_import_option': unreal.VertexColorImportOption.REPLACE, 'normal_import_method': unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS}.items():
                data.set_editor_property(k, v)
            task = unreal.AssetImportTask()
            for k, v in {'filename': str(source_file(entry['file'])), 'destination_path': folder + '/Meshes', 'destination_name': name, 'automated': True, 'replace_existing': False, 'save': True, 'factory': unreal.FbxFactory(), 'options': options}.items():
                task.set_editor_property(k, v)
            ASSETS.import_asset_tasks([task])
            asset = load(path)
            if not isinstance(asset, unreal.StaticMesh):
                raise RuntimeError('Expected versioned static mesh ' + path)
            asset.set_material(0, materials['land' if 'Land' in name else 'sky'])
            unreal.EditorAssetLibrary.save_loaded_asset(asset)
        result[name] = asset
    return result


def new_mesh(id, label, mesh, record, previous, reference, template=None):
    actor = unique(id)
    if actor and (not actor.actor_has_tag(OWNED) or not editable(actor, record, previous, reference)):
        return None
    if not actor:
        actor = ACTORS.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    tags(actor, OWNED, id, 'Opening.Decorative')
    actor.set_actor_label(label)
    actor.set_folder_path('Quest/Scenery')
    if template:
        actor.set_actor_transform(template.get_actor_transform(), False, False)
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    component.set_mobility(unreal.ComponentMobility.STATIC)
    component.set_static_mesh(mesh)
    component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    component.set_editor_property('cast_shadow', False)
    actor.set_actor_enable_collision(False)
    actor.set_actor_hidden_in_game(False)
    record['touched_names'].append(actor.get_name())
    record['owned_additions'].append(actor.get_path_name())
    return actor


def apply_materials_and_land(meshes, mats, record, previous, reference):
    original_land = []
    for actor in actors():
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        mesh = component.get_editor_property('static_mesh') if component else None
        if not mesh or actor.actor_has_tag(OWNED):
            continue
        name = mesh.get_name()
        if not (material_target(name) or name in {'SM_Sea', 'SM_DistantMountains'}):
            continue
        if not editable(actor, record, previous, reference):
            continue
        if name == 'SM_DistantMountains':
            original_land.append(actor)
            continue
        for i in range(component.get_num_materials()):
            old = component.get_material(i)
            if not old:
                continue
            key = material_key(name, old)
            if key:
                component.set_material(i, mats[key])
                record['material_overrides'].append({'actor': actor.get_path_name(), 'slot': i, 'from': old.get_path_name(), 'to': mats[key].get_path_name()})
        record['touched_names'].append(actor.get_name())
    if len(original_land) > 1:
        raise RuntimeError('Multiple source distant-land actors; refusing ambiguous replacement')
    if original_land:
        old = original_land[0]
        distant_mesh = meshes['SM_QuestDistantLand']
        if ROOT.parent.name == 'Release_20261026' and record.get('map') == '/Game/Quest/Maps/Verdant_Desktop':
            import release_distant_ridges
            distant_mesh = release_distant_ridges.preferred_mesh(distant_mesh)
        created = new_mesh('quest.visual.distant_land', 'Quest - rounded coastal massifs', distant_mesh, record, previous, reference, old)
        if created:
            old.set_actor_hidden_in_game(True)
            old.get_component_by_class(unreal.StaticMeshComponent).set_visibility(False)
            record['touched_names'].append(old.get_name())
    new_mesh('quest.visual.sky_dome', 'Quest - coastal sky gradient and slow clouds', meshes['SM_QuestSkyDome'], record, previous, reference)


def lighting(world, name, record, previous, reference):
    if name not in PROFILES:
        raise ValueError('Unknown lighting profile ' + name)
    profile = PROFILES[name]
    cubemap = load('/Engine/MapTemplates/Sky/DaylightAmbientCubemap')
    if not isinstance(cubemap, unreal.TextureCube):
        raise RuntimeError('Required installed Engine daylight cubemap was not loadable')
    suns, skylights = 0, 0
    for actor in actors():
        if not isinstance(actor, (unreal.DirectionalLight, unreal.SkyLight, unreal.PointLight, unreal.PostProcessVolume, unreal.SkyAtmosphere, unreal.ExponentialHeightFog)):
            continue
        if not editable(actor, record, previous, reference):
            continue
        if isinstance(actor, unreal.DirectionalLight):
            light = actor.get_component_by_class(unreal.DirectionalLightComponent)
            if actor.get_actor_label() == 'Soft sky bounce fill':
                light.set_intensity(0)
                light.set_visibility(False)
                light.set_editor_property('cast_shadows', False)
                record['disabled_legacy_lights'].append(actor.get_path_name())
            else:
                suns += 1
                if suns > 1:
                    raise RuntimeError('More than one main sun; refusing ambiguous lighting edit')
                actor.set_actor_rotation(unreal.Rotator(pitch=profile['pitch'], yaw=profile['yaw'], roll=0), False)
                light.set_mobility(unreal.ComponentMobility.MOVABLE)
                light.set_visibility(True)
                light.set_intensity(profile['sun'])
                light.set_light_color(unreal.LinearColor(*profile['sun_rgb'], 1))
                light.set_editor_property('cast_shadows', True)
                prop(light, 'dynamic_shadow_distance_movable_light', 12000.0, record)
                prop(light, 'dynamic_shadow_cascades', 2, record)
                prop(light, 'volumetric_scattering_intensity', 0.0, record)
        elif isinstance(actor, unreal.SkyLight):
            skylights += 1
            if skylights > 1:
                raise RuntimeError('More than one skylight; refusing ambiguous lighting edit')
            light = actor.get_component_by_class(unreal.SkyLightComponent)
            light.set_mobility(unreal.ComponentMobility.MOVABLE)
            light.set_editor_property('source_type', unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
            light.set_editor_property('cubemap', cubemap)
            light.set_editor_property('real_time_capture', False)
            light.set_editor_property('lower_hemisphere_is_black', False)
            light.set_editor_property('cast_shadows', False)
            light.set_visibility(True)
            light.set_intensity(profile['sky'])
        elif isinstance(actor, unreal.PointLight):
            light = actor.get_component_by_class(unreal.PointLightComponent)
            if actor.get_actor_label() in LEGACY_POINT_LABELS:
                light.set_intensity(0)
                light.set_visibility(False)
                light.set_editor_property('cast_shadows', False)
                record['disabled_legacy_lights'].append(actor.get_path_name())
        elif isinstance(actor, unreal.PostProcessVolume):
            settings = actor.get_editor_property('settings')
            for field, setting in {'auto_exposure_method': unreal.AutoExposureMethod.AEM_MANUAL, 'auto_exposure_bias': 0.0, 'auto_exposure_apply_physical_camera_exposure': False, 'motion_blur_amount': 0.0, 'bloom_intensity': 0.0}.items():
                prop(settings, 'override_' + field, True, record)
                prop(settings, field, setting, record)
            actor.set_editor_property('settings', settings)
        elif isinstance(actor, unreal.SkyAtmosphere):
            # A conventional authored mobile sky; no volumetric cloud dependency.
            actor.set_actor_hidden_in_game(True)
            component = actor.get_component_by_class(unreal.SkyAtmosphereComponent)
            component.set_visibility(False)
        elif isinstance(actor, unreal.ExponentialHeightFog):
            component = actor.get_component_by_class(unreal.ExponentialHeightFogComponent)
            prop(component, 'fog_density', profile['fog'], record)
            prop(component, 'fog_height_falloff', .25, record)
            prop(component, 'fog_inscattering_luminance', unreal.LinearColor(*linear([191, 184, 167]), 1), record)
            prop(component, 'enable_volumetric_fog', False, record)
        record['touched_names'].append(actor.get_name())
    if suns != 1 or skylights != 1:
        record['notes'].append('Expected one editable sun and skylight; preserved manual actors may require manual calibration.')
    record['lighting_profile'] = name
    record['lighting_values'] = dict(profile, cubemap=cubemap.get_path_name())


def apply_scenery(world, lighting_profile=DEFAULT_PROFILE):
    path = map_path(world)
    manifest = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    folder = '/Game/Quest/Scenery/V_' + manifest['build_stamp']
    all_report = json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {'schema_version': 1, 'maps': {}}
    old = all_report['maps'].get(path, {})
    record = {'success': False, 'map': path, 'run': stamp(), 'asset_namespace': folder, 'baseline': old.get('baseline', {}), 'inferred_manual_names': old.get('inferred_manual_names', []), 'preserved_manual': [], 'unsupported_optional_properties': [], 'owned_additions': [], 'material_overrides': [], 'disabled_legacy_lights': [], 'touched_names': [], 'notes': ['Initial mobile LDR calibration candidates; native mobile preview and headset testing remain required.', 'Unbaked single dynamic sun plus IBL; no claim of baked indirect light or headset frame rate.', 'Original terrain actor is hidden; original shared meshes/materials are not changed.']}
    previous, reference = old.get('after', {}), initial_reference()
    record['shared_asset_sha_before'] = shared_asset_hashes()
    try:
        mats = material_assets(manifest, folder, record)
        meshes = mesh_assets(manifest, folder, mats)
        apply_materials_and_land(meshes, mats, record, previous, reference)
        lighting(world, lighting_profile, record, previous, reference)
        import build_quest_premium_art as premium
        if premium.enabled_for_map(path):
            before_premium = {a.get_name(): state(a) for a in actors() if a.get_name() in set(record['touched_names']) | set(previous)}
            delegated = dict(record, after=before_premium)
            record['premium_art'] = premium.apply_premium(world, base_record=delegated)
            record['premium_art_delegation'] = {'enabled': True, 'report': str(premium.REPORT), 'owned_tag': premium.OWNED}
        unreal.EditorAssetLibrary.save_directory(folder, only_if_is_dirty=True, recursive=True)
        touched = set(record['touched_names']) | set(previous)
        record['after'] = {a.get_name(): state(a) for a in actors() if a.get_name() in touched}
        record['shared_asset_sha_after'] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in record['shared_asset_sha_before']}
        record['shared_assets_unchanged'] = record['shared_asset_sha_before'] == record['shared_asset_sha_after']
        if not record['shared_assets_unchanged']:
            raise RuntimeError('A shared input asset changed unexpectedly during Quest scenery application')
        record['success'] = True
    except Exception:
        record['error'] = traceback.format_exc()
        if previous:
            record['after'] = previous  # Map save has not occurred; retain its last saved fingerprint.
        raise
    finally:
        all_report['maps'][path] = record
        REPORT.write_text(json.dumps(all_report, indent=2), encoding='utf-8')
    return record


def set_lighting_profile(world, name):
    """Reapply only lighting for sequential native A/B captures; never saves map."""
    path = map_path(world)
    all_report = json.loads(REPORT.read_text(encoding='utf-8'))
    old = all_report['maps'][path]
    record = {'baseline': old['baseline'], 'inferred_manual_names': old.get('inferred_manual_names', []), 'preserved_manual': [], 'unsupported_optional_properties': [], 'disabled_legacy_lights': [], 'touched_names': [], 'notes': []}
    lighting(world, name, record, old.get('after', {}), initial_reference())
    import build_quest_premium_art as premium
    if premium.enabled_for_map(path):
        record['premium_preview_lighting'] = premium.preview_lighting(world, record)
    old.update({k: v for k, v in record.items() if k != 'baseline'})
    touched = set(old.get('after', {})) | set(record['touched_names'])
    old['after'] = {a.get_name(): state(a) for a in actors() if a.get_name() in touched}
    REPORT.write_text(json.dumps(all_report, indent=2), encoding='utf-8')
    return record
