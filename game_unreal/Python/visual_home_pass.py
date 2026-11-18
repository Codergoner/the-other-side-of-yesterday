"""Competition visual pass on the family home (11 November 2026): material overrides, warm interior light, dressing.

Data driven by output/verdant/visual_home_job.json:
  {"label", "materials": [{"actor", "slot", "instance", "parent", "scalars", "vectors"} | {"actor", "slot", "material"}],
   "lights": [{"label", "intensity", "color": [r,g,b], "radius"}],
   "dressing": [{"name", "mesh", "location": [cm], "rotation": [pitch,yaw,roll], "scale": [..], "materials": [..], "shadow": bool}],
   "views": [{"id", "pos": [cm], "target": [cm], "fov"}]}

Modes (run through verdant/run_unreal.ps1, one writer at a time):
  (default)            preview: apply in memory, capture the views, save NOTHING (new assets stay unsaved and are discarded).
  -VisualHomeApply     apply, save the new material instances and the map; backup of the map and a revert record are written first.
  -VisualHomeRevert    restore the recorded material slots and light values, remove the dressing actors, save the map.
Only material slots, three light values and new non-colliding dressing actors change. No story actor, tag, collision,
transform, era array or Blueprint is touched. Evidence: game_unreal/validation/visual_pass/<stamp>_<label>/.
"""
import hashlib
import json
import shutil
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
RELEASE = PROJECT.parent
assert RELEASE.name == 'Release_20261026'
CMD = unreal.SystemLibrary.get_command_line().lower()
APPLY = '-visualhomeapply' in CMD
REVERT = '-visualhomerevert' in CMD
JOB = json.loads((RELEASE / 'output' / 'verdant' / 'visual_home_job.json').read_text(encoding='utf-8-sig'))
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
OUT = PROJECT / 'validation' / 'visual_pass' / (STAMP + '_' + JOB.get('label', 'preview'))
OUT.mkdir(parents=True, exist_ok=True)
MAP = '/Game/Quest/Maps/Verdant_Desktop'
MAP_FILE = PROJECT / 'Content' / 'Quest' / 'Maps' / 'Verdant_Desktop.umap'
PASS_PATH = '/Game/Quest/XR/VisualPass'
RECORD = PROJECT / 'validation' / 'visual_pass' / 'applied_record.json'
TAG = 'Quest.VisualPass'
WIDTH, HEIGHT = JOB.get('width', 1600), JOB.get('height', 900)
MEL = unreal.MaterialEditingLibrary
LIB = unreal.EditorAssetLibrary
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
REPORT = {'success': False, 'mode': 'apply' if APPLY else 'revert' if REVERT else 'preview', 'label': JOB.get('label'), 'map': MAP,
          'material_changes': [], 'light_changes': [], 'dressing': [], 'images': [], 'new_assets': [], 'level_saved': False}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def by_name(name):
    for actor in actors.get_all_level_actors():
        if actor.get_name() == name or actor.get_actor_label() == name:
            return actor
    raise RuntimeError('Missing actor ' + name)


def expression(material, cls, x, y, **fields):
    node = MEL.create_material_expression(material, cls, x, y)
    for key, value in fields.items():
        node.set_editor_property(key, value)
    return node


def parent_material(name, world_xy):
    """Owned simple surface: Base * Tint * Brightness, a normal map, scalar roughness. UVs are the mesh UVs times UVScale, or
    world XY divided by TileCm for floors (the home meshes carry no baked vertex data, which the Verdant kit shaders need)."""
    path = PASS_PATH + '/' + name
    if LIB.does_asset_exist(path):
        return unreal.load_asset(path)
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, PASS_PATH, unreal.Material, unreal.MaterialFactoryNew())
    REPORT['new_assets'].append(path)
    if world_xy:
        position = expression(material, unreal.MaterialExpressionWorldPosition, -1200, 0)
        mask = expression(material, unreal.MaterialExpressionComponentMask, -1000, 0, r=True, g=True, b=False, a=False)
        MEL.connect_material_expressions(position, '', mask, '')
        tile = expression(material, unreal.MaterialExpressionScalarParameter, -1000, 160, parameter_name='TileCm', default_value=200.0)
        uv = expression(material, unreal.MaterialExpressionDivide, -800, 0)
        MEL.connect_material_expressions(mask, '', uv, 'A')
        MEL.connect_material_expressions(tile, '', uv, 'B')
    else:
        coordinate = expression(material, unreal.MaterialExpressionTextureCoordinate, -1000, 0)
        scale = expression(material, unreal.MaterialExpressionScalarParameter, -1000, 160, parameter_name='UVScale', default_value=1.0)
        uv = expression(material, unreal.MaterialExpressionMultiply, -800, 0)
        MEL.connect_material_expressions(coordinate, '', uv, 'A')
        MEL.connect_material_expressions(scale, '', uv, 'B')
    base = expression(material, unreal.MaterialExpressionTextureSampleParameter2D, -560, -120, parameter_name='Base',
                      texture=unreal.load_asset('/Game/Verdant/Textures/T_V_Plaster_BC'))
    normal = expression(material, unreal.MaterialExpressionTextureSampleParameter2D, -560, 220, parameter_name='Normal',
                        texture=unreal.load_asset('/Game/Verdant/Textures/T_V_Plaster_N'), sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    MEL.connect_material_expressions(uv, '', base, 'UVs')
    MEL.connect_material_expressions(uv, '', normal, 'UVs')
    tint = expression(material, unreal.MaterialExpressionVectorParameter, -560, -360, parameter_name='Tint', default_value=unreal.LinearColor(1, 1, 1, 1))
    brightness = expression(material, unreal.MaterialExpressionScalarParameter, -340, -360, parameter_name='Brightness', default_value=1.0)
    tinted = expression(material, unreal.MaterialExpressionMultiply, -300, -160)
    MEL.connect_material_expressions(base, 'RGB', tinted, 'A')
    MEL.connect_material_expressions(tint, '', tinted, 'B')
    lit = expression(material, unreal.MaterialExpressionMultiply, -140, -160)
    MEL.connect_material_expressions(tinted, '', lit, 'A')
    MEL.connect_material_expressions(brightness, '', lit, 'B')
    MEL.connect_material_property(lit, '', unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(normal, 'RGB', unreal.MaterialProperty.MP_NORMAL)
    roughness = expression(material, unreal.MaterialExpressionScalarParameter, -340, 60, parameter_name='Roughness', default_value=0.85)
    MEL.connect_material_property(roughness, '', unreal.MaterialProperty.MP_ROUGHNESS)
    glow = expression(material, unreal.MaterialExpressionScalarParameter, -340, 420, parameter_name='Glow', default_value=0.0)
    emissive = expression(material, unreal.MaterialExpressionMultiply, -140, 420)
    MEL.connect_material_expressions(tinted, '', emissive, 'A')
    MEL.connect_material_expressions(glow, '', emissive, 'B')
    MEL.connect_material_property(emissive, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(material)
    return material


def instance(spec):
    if 'material' in spec:
        asset = unreal.load_asset(spec['material'])
        if asset is None:
            raise RuntimeError('Missing material ' + spec['material'])
        return asset
    path = PASS_PATH + '/' + spec['instance']
    if LIB.does_asset_exist(path):
        mi = unreal.load_asset(path)
    else:
        mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(spec['instance'], PASS_PATH, unreal.MaterialInstanceConstant,
                                                                     unreal.MaterialInstanceConstantFactoryNew())
        REPORT['new_assets'].append(path)
    if spec['parent'] in ('M_Home_Surface', 'M_Home_Floor'):
        parent = parent_material(spec['parent'], spec['parent'] == 'M_Home_Floor')
    else:
        parent = unreal.load_asset(spec['parent'])
    if parent is None:
        raise RuntimeError('Missing parent ' + spec['parent'])
    MEL.set_material_instance_parent(mi, parent)
    for key, value in (spec.get('scalars') or {}).items():
        MEL.set_material_instance_scalar_parameter_value(mi, key, float(value))
    for key, value in (spec.get('vectors') or {}).items():
        MEL.set_material_instance_vector_parameter_value(mi, key, unreal.LinearColor(*value))
    for key, value in (spec.get('textures') or {}).items():
        texture = unreal.load_asset(value)
        if texture is None:
            raise RuntimeError('Missing texture ' + value)
        MEL.set_material_instance_texture_parameter_value(mi, key, texture)
    MEL.update_material_instance(mi)
    return mi


def apply_materials():
    for spec in JOB.get('materials', []):
        actor = by_name(spec['actor'])
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        before = component.get_material(spec['slot'])
        material = instance(spec)
        component.set_material(spec['slot'], material)
        REPORT['material_changes'].append({'actor': actor.get_name(), 'label': actor.get_actor_label(), 'slot': spec['slot'],
                                           'before': before.get_path_name() if before else None, 'after': material.get_path_name()})


def apply_lights():
    for spec in JOB.get('lights', []):
        actor = by_name(spec['label'])
        light = actor.get_component_by_class(unreal.LightComponent)
        color = light.get_editor_property('light_color')
        before = {'intensity': float(light.get_editor_property('intensity')), 'color': [color.r, color.g, color.b],
                  'radius': float(light.get_editor_property('attenuation_radius')), 'visible': bool(light.is_visible()), 'location': [actor.get_actor_location().x, actor.get_actor_location().y, actor.get_actor_location().z]}
        light.set_editor_property('intensity', float(spec['intensity']))
        if 'color' in spec:
            light.set_editor_property('light_color', unreal.Color(r=int(spec['color'][0]), g=int(spec['color'][1]), b=int(spec['color'][2]), a=255))
        if 'radius' in spec:
            light.set_editor_property('attenuation_radius', float(spec['radius']))
        if 'location' in spec:
            actor.set_actor_location(unreal.Vector(*spec['location']), False, False)
        light.set_editor_property('cast_shadows', False)
        light.set_visibility(True, False)
        light.set_editor_property('visible', True)
        REPORT['light_changes'].append({'label': actor.get_actor_label(), 'name': actor.get_name(), 'before': before,
                                        'after': {k: spec[k] for k in ('intensity', 'color', 'radius', 'location') if k in spec}})


def remove_dressing():
    removed = 0
    for actor in list(actors.get_all_level_actors()):
        if TAG in [str(t) for t in actor.get_editor_property('tags')]:
            actors.destroy_actor(actor)
            removed += 1
    return removed


def apply_dressing():
    REPORT['dressing_removed_first'] = remove_dressing()
    for spec in JOB.get('dressing', []):
        mesh = unreal.load_asset(spec['mesh'])
        if mesh is None:
            raise RuntimeError('Missing mesh ' + spec['mesh'])
        rotation = spec.get('rotation', [0, 0, 0])
        actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*spec['location']),
                                              unreal.Rotator(pitch=rotation[0], yaw=rotation[1], roll=rotation[2]))
        actor.set_actor_label(spec['name'])
        actor.set_actor_scale3d(unreal.Vector(*spec.get('scale', [1, 1, 1])))
        actor.set_editor_property('tags', [unreal.Name(TAG), unreal.Name('Opening.Decorative')])
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        component.set_static_mesh(mesh)
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        component.set_collision_profile_name('NoCollision')
        component.set_editor_property('cast_shadow', bool(spec.get('shadow', False)))
        component.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
        for index, item in enumerate(spec.get('materials', [])):
            if item is not None:
                component.set_material(index, instance(item) if isinstance(item, dict) else unreal.load_asset(item))
        actor.set_actor_enable_collision(False)
        origin, extent = actor.get_actor_bounds(False)
        REPORT['dressing'].append({'name': spec['name'], 'mesh': spec['mesh'], 'location': spec['location'], 'scale': spec.get('scale', [1, 1, 1]),
                                   'bounds_origin': [round(origin.x, 1), round(origin.y, 1), round(origin.z, 1)], 'bounds_extent': [round(extent.x, 1), round(extent.y, 1), round(extent.z, 1)]})


def hide_past():
    """Preview captures show the present era the way ApplyWorldState does at New Game."""
    for actor in actors.get_all_level_actors():
        tags = [str(t) for t in actor.get_editor_property('tags')]
        if 'Opening.PastOnly' in tags:
            actor.set_is_temporarily_hidden_in_editor(True)
        elif 'Opening.PresentOnly' in tags and not any(t in tags for t in ('Opening.ClinicCover', 'Opening.HarborCover', 'Opening.ClinicRecord', 'Opening.HarborRecord')):
            if not bool(actor.get_editor_property('hidden')) or actor.get_class().get_name() in ('DirectionalLight', 'SkyLight', 'ExponentialHeightFog'):
                actor.set_is_temporarily_hidden_in_editor(False)


class Session:
    def __init__(self):
        self.phase = 'load'
        self.index = 0
        self.frames = 0
        self.done = False
        self.handle = None

    def start(self):
        unreal.EditorPythonScripting.set_keep_python_script_alive(True)
        self.handle = unreal.register_slate_post_tick_callback(self.tick)

    def tick(self, _delta):
        if self.done:
            return
        try:
            self.step()
        except Exception:
            self.finish(traceback.format_exc())

    def setup(self):
        if not levels.load_level(MAP):
            raise RuntimeError('Cannot load ' + MAP)
        self.world = editor.get_editor_world()
        REPORT['map_sha256_before'] = digest(MAP_FILE)
        if REVERT:
            record = json.loads(RECORD.read_text(encoding='utf-8'))
            for row in record['material_changes']:
                component = by_name(row['actor']).get_component_by_class(unreal.StaticMeshComponent)
                component.set_material(row['slot'], unreal.load_asset(row['before']) if row['before'] else None)
            for row in record['light_changes']:
                actor = by_name(row['name'])
                light = actor.get_component_by_class(unreal.LightComponent)
                light.set_editor_property('intensity', row['before']['intensity'])
                light.set_editor_property('attenuation_radius', row['before']['radius'])
                c = row['before']['color']
                light.set_editor_property('light_color', unreal.Color(r=int(c[0]), g=int(c[1]), b=int(c[2]), a=255))
                actor.set_actor_location(unreal.Vector(*row['before']['location']), False, False)
                light.set_visibility(bool(row['before'].get('visible', False)), False)
                light.set_editor_property('visible', bool(row['before'].get('visible', False)))
            REPORT['dressing_removed'] = remove_dressing()
            REPORT['reverted_record'] = str(RECORD)
        else:
            apply_materials()
            apply_lights()
            apply_dressing()
        if JOB.get('list_meshes'):
            registry = unreal.AssetRegistryHelpers.get_asset_registry()
            REPORT['meshes'] = sorted(str(d.package_name) for root in JOB['list_meshes'] for d in registry.get_assets_by_path(root, recursive=True)
                                      if str(d.asset_class_path.asset_name) == 'StaticMesh')
        hide_past()
        self.capture = actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 3000))
        self.component = self.capture.get_component_by_class(unreal.SceneCaptureComponent2D)
        self.target = unreal.RenderingLibrary.create_render_target2d(self.world, WIDTH, HEIGHT, unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                                                     unreal.LinearColor(0, 0, 0, 1), False, False)
        self.target.set_editor_property('target_gamma', 2.2)
        for field, value in [('texture_target', self.target), ('capture_every_frame', False), ('capture_on_movement', False),
                             ('always_persist_rendering_state', True), ('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR),
                             ('post_process_blend_weight', 0.0)]:
            self.component.set_editor_property(field, value)

    def step(self):
        if self.phase == 'load':
            self.phase = 'loading'  # compiling a material pumps the editor tick: never enter setup twice
            self.setup()
            self.phase = 'warmup'
            self.started = time.monotonic()
        elif self.phase == 'warmup':
            if time.monotonic() - self.started > JOB.get('warmup_seconds', 30):
                self.phase = 'view'
        elif self.phase == 'view':
            views = JOB.get('views', [])
            if self.index >= len(views):
                self.finish(None)
                return
            self.view = views[self.index]
            position, target = unreal.Vector(*self.view['pos']), unreal.Vector(*self.view['target'])
            self.capture.set_actor_location(position, False, False)
            self.capture.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(position, target), False)
            self.component.set_editor_property('fov_angle', self.view.get('fov', 90))
            unreal.AutomationLibrary.finish_loading_before_screenshot()
            self.frames = 0
            self.phase = 'settle'
        elif self.phase == 'settle':
            self.component.capture_scene()
            self.frames += 1
            if self.frames >= JOB.get('settle_frames', 30):
                name = '%02d_%s.png' % (self.index, self.view['id'])
                unreal.RenderingLibrary.export_render_target(self.world, self.target, str(OUT), name)
                REPORT['images'].append(str(OUT / name))
                self.index += 1
                self.phase = 'view'

    def finish(self, error):
        self.done = True
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
        try:
            actors.destroy_actor(self.capture)
        except Exception:
            pass
        try:
            if error is None and (APPLY or REVERT):
                backup = OUT / ('Verdant_Desktop.umap.before_' + REPORT['mode'])
                shutil.copy2(MAP_FILE, backup)
                REPORT['map_backup'] = str(backup)
                for actor in actors.get_all_level_actors():
                    actor.set_is_temporarily_hidden_in_editor(False)
                for path in REPORT['new_assets']:
                    if not LIB.save_asset(path, False):
                        raise RuntimeError('Cannot save ' + path)
                if not levels.save_current_level():
                    raise RuntimeError('Cannot save the map')
                REPORT['level_saved'] = True
                REPORT['map_sha256_after'] = digest(MAP_FILE)
                if APPLY:
                    previous = json.loads(RECORD.read_text(encoding='utf-8')) if RECORD.exists() else None
                    record = {'applied_utc': STAMP, 'job': JOB, 'material_changes': REPORT['material_changes'], 'light_changes': REPORT['light_changes'],
                              'dressing': REPORT['dressing'], 'map_backup': str(backup), 'map_sha256_before': REPORT['map_sha256_before'],
                              'map_sha256_after': REPORT['map_sha256_after']}
                    if previous:
                        # Keep the ORIGINAL before-values across repeated applies so a revert goes back to the pre-pass map.
                        first = {(r['actor'], r['slot']): r['before'] for r in previous['material_changes']}
                        for row in record['material_changes']:
                            row['before'] = first.get((row['actor'], row['slot']), row['before'])
                        first_light = {r['name']: r['before'] for r in previous['light_changes']}
                        for row in record['light_changes']:
                            row['before'] = first_light.get(row['name'], row['before'])
                        record['first_map_backup'] = previous.get('first_map_backup', previous.get('map_backup'))
                        record['first_map_sha256_before'] = previous.get('first_map_sha256_before', previous.get('map_sha256_before'))
                    RECORD.write_text(json.dumps(record, indent=1), encoding='utf-8')
        except Exception:
            error = traceback.format_exc()
        REPORT['success'] = error is None
        REPORT['error'] = error
        (OUT / 'report.json').write_text(json.dumps(REPORT, indent=1, default=str), encoding='utf-8')
        unreal.log('VERDANT visual home pass ' + ('ok ' if error is None else 'FAILED ') + str(OUT))
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()


Session().start()
