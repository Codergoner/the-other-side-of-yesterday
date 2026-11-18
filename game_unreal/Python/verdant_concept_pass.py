"""Concept pass of 17 November 2026: the entrant's two reference boards and the two city atlases ("Verdant Before the
War", "Verdant Twenty Years After the War") applied to the story map. One writer job, run through
verdant/run_unreal.ps1 -NoRender with -ConceptPassApply. What it does, all of it colour, light and dressing:

  roofs      M_V_Roof fires the kit's tile map as terracotta (verdant_materials.roof, Clay 1). The landmarks keep
             their blue-green glaze through MI_V_RoofGlaze / MI_V_RoofGlaze_Present, set as material overrides on
             the campanile, cathedral and lighthouse components of Verdant_Past / Verdant_Present.
  banner     T_V_Banner_BC is the gold tree on red cloth; M_V_Banner gains Aging; one banner still hangs in the
             present (a new component of Verdant_Present, MI_V_Banner_Present).
  cloth      M_V_Cloth re-dyes the teal cloth madder red (awnings, stalls, pennants, the shop's shade).
  flowers    T_V_Foliage_BC: magenta-to-violet climber, rose and violet pots; eight more climbers on the played
             street and clinic court (a new component of Verdant_Past).
  sky        T_V_Sky_* and TC_V_SkyAmbient_* from verdant/grade_sky_concept.py: a golden hour going to sunset in the
             past, a grey-violet evening in the present.
  light      The past sun was authored (1.0, .86, .7) but unreal.Color takes b, g, r, so it shone pale blue. Both suns
             are now warm. Every light level is also brought into the range a display can show without a tonemapper,
             because the headset build has none (r.MobileHDR=False): sun, skylight, sky dome, fog and the home's lamp
             are scaled down and the desktop exposure volume goes from bias -0.7 to 0, which leaves the desktop
             picture's exposure where it was. tools/ldr_preview.py estimates the untonemapped result.

Nothing is moved, deleted or re-tagged; no collision, interaction, story actor, array or Blueprint changes. Before
anything is written the affected files are copied once to game_unreal/validation/concept_pass/original_20261117/ (the
revert: close the editor, copy them back, delete the new assets listed in applied_record.json).
"""
import hashlib
import json
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc
import verdant_materials as vm

if not vc.has_flag('ConceptPassApply'):
    raise RuntimeError('-ConceptPassApply is required (this job writes assets and the story map)')
PROJECT = vc.PROJECT
MAP = '/Game/Quest/Maps/Verdant_Desktop'
OUT = PROJECT / 'validation' / 'concept_pass'
ORIGINAL = OUT / 'original_20261117'
RECORD = OUT / 'applied_record.json'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
MEL = unreal.MaterialEditingLibrary
SETTINGS = unreal.TextureCompressionSettings
MATERIALS = vc.ROOT_PATH + '/Materials/'
MESHES = vc.ROOT_PATH + '/Meshes/'
FILES = ['Content/Verdant/Textures/%s.uasset' % t for t in ('T_V_Banner_BC', 'T_V_Foliage_BC', 'T_V_Sky_Past', 'T_V_Sky_Present',
                                                           'TC_V_SkyAmbient_Past', 'TC_V_SkyAmbient_Present')] + \
        ['Content/Verdant/Materials/%s.uasset' % m for m in ('M_V_Roof', 'M_V_Cloth', 'M_V_Banner', 'MI_V_Roof_Present', 'MI_V_Cloth_Present',
                                                             'MI_V_Sky_Past', 'MI_V_Sky_Present')] + \
        ['Content/Quest/Maps/Verdant_Desktop.umap']
NEW_ASSETS = [MATERIALS + n for n in ('MI_V_RoofGlaze', 'MI_V_RoofGlaze_Present', 'MI_V_Banner_Present', 'M_V_TreeRelief')] + ['/Game/Quest/XR/VisualPass/M_Home_RoofClay']
LANDMARKS = ('SM_V_Campanile', 'SM_V_Cathedral_Core_R', 'SM_V_Cathedral_Core_D', 'SM_V_Cathedral_South_R', 'SM_V_Cathedral_South_D',
             'SM_V_Lighthouse_R', 'SM_V_Lighthouse_D')
# Light levels. "was" is the saved value on 16 November; the new value is for a display without a tonemapper.
# Colours are linear r, g, b.
LIGHT = {
    'Verdant_Sun_Past': dict(intensity=7.0, colour=(1.0, .60, .30)),
    'Verdant_Sun_Present': dict(intensity=4.6, colour=(1.0, .70, .50)),
    'Verdant_SkyLight_Past': dict(intensity=1.2),
    'Verdant_SkyLight_Present': dict(intensity=1.4),
    'Verdant_Fog_Past': dict(fog=(.30, .25, .31), sun=(.80, .46, .22)),
    'Verdant_Fog_Present': dict(fog=(.27, .27, .33), sun=(.56, .40, .28)),
    # 10.0 since the morning of 17 November (was 27.7 in code 14, 45 before the pass): trial of 27.7 / 18 / 12 / 7 / 0
    # in captures/20261116T200805_room_lamp_try; the estimate's clipped share of the first room went 35 % -> ~11 %.
    'Home ground floor warm fill': dict(intensity=10.0),
}
SKY_GAIN = {'Past': .9, 'Present': .8}
EXPOSURE_BIAS = 0.0
# Climbers: Unreal cm, yaw as the kit places them (-90 on a wall that faces +X, 0 on one that faces +Y).
CLIMBERS = [(-360, -330, 1545, -90), (-360, -760, 1590, -90), (-360, -1400, 1640, -90), (-360, -1640, 1655, -90),
            (-360, -2000, 1700, -90), (-360, -2900, 1800, -90), (-620, 50, 1500, 0), (-816, 95, 1480, -90)]
PRESENT_BANNER = (310, -600, 1214, -180)
REPORT = {'success': False, 'stamp': STAMP, 'files': {}, 'lights': {}, 'overrides': [], 'components': []}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def srgb_byte(value):
    value = max(0.0, min(1.0, value))
    encoded = value * 12.92 if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055
    return int(round(encoded * 255))


def import_task(filename, name):
    task = unreal.AssetImportTask()
    for key, value in (('filename', str(filename)), ('destination_path', vc.ROOT_PATH + '/Textures'), ('destination_name', name),
                       ('automated', True), ('save', False), ('replace_existing', True), ('replace_existing_settings', True)):
        task.set_editor_property(key, value)
    vc.assets.import_asset_tasks([task])
    asset = unreal.load_asset(vc.ROOT_PATH + '/Textures/' + name)
    vc.require(asset is not None, 'Import failed: ' + name)
    return asset


def import_textures():
    for name in ('T_V_Banner_BC', 'T_V_Foliage_BC'):
        texture = import_task(vc.SOURCE / 'textures' / (name + '.png'), name)
        texture.set_editor_property('compression_settings', SETTINGS.TC_BC7)
        texture.set_editor_property('srgb', True)
        vc.library.save_loaded_asset(texture)
    for era in ('Past', 'Present'):
        texture = import_task(vc.SOURCE / 'sky' / ('Sky_%s_concept.exr' % era), 'T_V_Sky_' + era)
        texture.set_editor_property('compression_settings', SETTINGS.TC_HDR_COMPRESSED)
        texture.set_editor_property('srgb', False)
        texture.set_editor_property('address_x', unreal.TextureAddress.TA_WRAP)
        texture.set_editor_property('address_y', unreal.TextureAddress.TA_CLAMP)
        texture.set_editor_property('never_stream', True)
        texture.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        vc.library.save_loaded_asset(texture)
        cube = import_task(vc.SOURCE / 'sky' / ('Sky_%s_concept_ambient.hdr' % era), 'TC_V_SkyAmbient_' + era)
        REPORT.setdefault('ambient_cubemaps', {})[era] = cube.get_class().get_name()
        if isinstance(cube, unreal.TextureCube):
            cube.set_editor_property('compression_settings', SETTINGS.TC_HDR)
            cube.set_editor_property('srgb', False)
        vc.library.save_loaded_asset(cube)


def materials():
    roof = vm.roof()
    cloth = vm.cloth()
    banner = vm.banner()
    vm.instance(roof, 'MI_V_Roof_Present', {'Aging': .7})
    vm.instance(cloth, 'MI_V_Cloth_Present', {'Aging': .75})
    made = {'glaze': vm.instance(roof, 'MI_V_RoofGlaze', {'Clay': 0.0}),
            'glaze_present': vm.instance(roof, 'MI_V_RoofGlaze_Present', {'Clay': 0.0, 'Aging': .7}),
            'banner_present': vm.instance(banner, 'MI_V_Banner_Present', {'Aging': .85})}
    for era in ('Past', 'Present'):
        sky = unreal.load_asset(MATERIALS + 'MI_V_Sky_' + era)
        REPORT.setdefault('sky_gain', {})[era] = {'was': MEL.get_material_instance_scalar_parameter_value(sky, 'SkyGain'), 'now': SKY_GAIN[era]}
        MEL.set_material_instance_scalar_parameter_value(sky, 'SkyGain', SKY_GAIN[era])
        vc.library.save_loaded_asset(sky)
    return made


def home_roof(actors):
    """The family home's own roof (SM_Home_Slate, the Quest-era blue M_Roof) beside a terracotta street: the same
    fired tile, projected in world space because the home mesh has neither the kit's roof UVs nor its vertex
    colours. One slot on one actor; the previous material is recorded."""
    saved = vm.PATH
    vm.PATH = '/Game/Quest/XR/VisualPass'
    try:
        g = vm.Graph('M_Home_RoofClay', True)
        wp, n = g.world(), g.vnormal()
        uv = g.custom('''
// Courses run across the slope, laps point down it, on either side of the ridge.
float2 uv = abs(N.x) > abs(N.y) ? float2(P.y, P.x * sign(N.x)) : float2(P.x, P.y * sign(N.y));
return uv / Tile;
''', {'P': wp, 'N': n, 'Tile': g.scalar('TileCm', 250)}, vm.FLOAT2)
        b, nm, m = g.sample('T_V_RoofTile_BC', uv), g.normal('T_V_RoofTile_N', uv), g.masks('T_V_RoofTile_ARH', uv)
        broad = g.masks('T_V_Masks', g.custom('return P.xy / 2600.0;', {'P': wp}, vm.FLOAT2))
        speck = g.masks('T_V_Masks', g.custom('return P.xy / 330.0 + float2(.19, .67);', {'P': wp}, vm.FLOAT2))
        colour = g.custom('''
float t = saturate(dot(B, float3(.3, .6, .1)) / .2);
float3 c = lerp(ClayDark.rgb, ClayLight.rgb, t) * lerp(.78, 1.16, Broad) * lerp(.84, 1.1, Speck);
c = lerp(c, c * float3(1.14, 1.04, .9), smoothstep(.6, .8, Speck) * .5);
c = lerp(c, dot(c, float3(.3, .6, .1)) * float3(1.08, .95, .86), .05 + Aging * .42);
c = lerp(c, float3(.26, .27, .18), Aging * smoothstep(.45, .8, Broad) * .55);
return c * (1.0 - Aging * .22);
''', {'B': b, 'Broad': (broad, 'R'), 'Speck': (speck, 'B'), 'Aging': g.scalar('Aging', .3),
      'ClayLight': g.vector('ClayLight', (.58, .17, .065, 1)), 'ClayDark': g.vector('ClayDark', (.2, .048, .02, 1))})
        g.out(vm.BC, colour)
        g.out(vm.NRM, nm)
        g.out(vm.ROUGH, g.custom('return saturate(R * .5 + .42);', {'R': (m, 'G')}, vm.FLOAT1))
        clay = g.done()
    finally:
        vm.PATH = saved
    actor = next((a for a in actors if a.get_actor_label() == 'SM_Home_Slate'), None)
    vc.require(actor is not None, 'Missing SM_Home_Slate')
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    vc.require(component.get_num_materials() == 1, 'SM_Home_Slate has %d slots' % component.get_num_materials())
    current = component.get_material(0)
    previous = json.loads(RECORD.read_text(encoding='utf-8')).get('home_roof', {}) if RECORD.exists() else {}
    REPORT['home_roof'] = {'actor': actor.get_name(), 'label': 'SM_Home_Slate', 'slot': 0,
                           'before': previous.get('before') or (current.get_path_name() if current else None), 'after': clay.get_path_name()}
    component.set_material(0, clay)


RELIEF_CENTRE, RELIEF_SIZE, RELIEF_DEPTH = (-855.0, 385.0, 1326.0), 68.0, 10.0


def tree_relief(actors):
    """"A carved tree appears on a stone wall near a lantern and flowers" (the atlas). One stone slab on the
    clinic's front over the door, beside its wall lantern and under the window box, standing in both eras: a 60 cm
    block set into the wall on the shared vegetation holder, no collision, no shadow. The carving is the banner's
    own tree, read from the banner map, cut into limestone with what is left of its gilding."""
    g = vm.Graph('M_V_TreeRelief')
    wp, n = g.world(), g.vnormal()
    centre, size = g.vector('Centre', (*RELIEF_CENTRE, 1)), g.scalar('SizeCm', RELIEF_SIZE)
    q = g.custom('return float2(C.y - P.y, C.z - P.z) / Size + .5;', {'P': wp, 'C': centre, 'Size': size}, vm.FLOAT2)
    uv_a = g.custom('return float2(.5 + (Q.x - .5) * .96, .535 + (Q.y - .5) * .52);', {'Q': q}, vm.FLOAT2)
    uv_b = g.custom('return float2(.5 + (Q.x - .5) * .96, .535 + (Q.y - .5) * .52) + float2(.007, -.004);', {'Q': q}, vm.FLOAT2)
    tree_a, tree_b = g.sample('T_V_Banner_BC', uv_a), g.sample('T_V_Banner_BC', uv_b)
    stone = g.sample('T_V_Limestone_BC', g.custom('return float2(P.y + P.x, -P.z) / 260.0 + float2(.37, .21);', {'P': wp}, vm.FLOAT2))
    g.out(vm.BC, g.custom('''
// Only the face that looks at the court is carved; the slab's edges are plain stone.
float face = saturate((N.x - .8) * 10.0);
float edge = max(abs(Q.x - .5), abs(Q.y - .5));
float inside = (1.0 - smoothstep(.42, .44, edge)) * face;
float cut = smoothstep(.04, .13, A.g) * inside;
float lit = (smoothstep(.04, .13, A.g) - smoothstep(.04, .13, B.g)) * inside;
float3 c = Stone * float3(1.06, 1.0, .92);
// The sunk field of the panel, the groove round it, then the tree cut into the field.
c *= lerp(1.0, .8, inside);
c *= 1.0 - smoothstep(.42, .44, edge) * (1.0 - smoothstep(.45, .47, edge)) * .45 * face;
c *= 1.0 - cut * .5;
c += max(lit, 0.0) * .22 - max(-lit, 0.0) * .1;
return lerp(c, Gilt.rgb * (.6 + Stone.r), cut * Gilding);
''', {'A': tree_a, 'B': tree_b, 'Q': q, 'N': n, 'Stone': stone, 'Gilt': g.vector('Gilt', (.7, .43, .1, 1)), 'Gilding': g.scalar('Gilding', .72)}))
    g.out(vm.ROUGH, g.scalar('Roughness', .86))
    g.out(vm.SPEC, g.scalar('Specular', .25))
    material = g.done()
    holder = next(a for a in actors if a.get_actor_label() == 'Verdant_Vegetation')
    component = next((c for c in holder.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == 'Concept_TreeRelief'), None)
    created = component is None
    if created:
        component = vc.add_component(holder, unreal.StaticMeshComponent, 'Concept_TreeRelief')
    component.set_editor_property('static_mesh', unreal.load_asset('/Engine/BasicShapes/Cube'))
    component.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
    component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    component.set_editor_property('cast_shadow', False)
    component.set_world_location_and_rotation(unreal.Vector(*RELIEF_CENTRE), unreal.Rotator(roll=0, pitch=0, yaw=0), False, False)
    component.set_world_scale3d(unreal.Vector(RELIEF_DEPTH / 100, RELIEF_SIZE / 100, RELIEF_SIZE / 100))
    component.set_material(0, material)
    REPORT['components'].append({'actor': 'Verdant_Vegetation', 'component': 'Concept_TreeRelief', 'mesh': 'Cube', 'created': created,
                                 'centre': list(RELIEF_CENTRE), 'size_cm': RELIEF_SIZE, 'material': material.get_path_name()})


def era_of(actor):
    tags = [str(t) for t in actor.get_editor_property('tags')]
    return 'Past' if 'Opening.PastOnly' in tags else 'Present' if 'Opening.PresentOnly' in tags else 'Shared'


def landmark_roofs(actors, made):
    for actor in actors:
        if actor.get_actor_label() not in ('Verdant_Past', 'Verdant_Present'):
            continue
        era = era_of(actor)
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            if mesh is None or mesh.get_name() not in LANDMARKS:
                continue
            for slot in range(component.get_num_materials()):
                current = component.get_material(slot)
                if current is None or current.get_name() not in ('M_V_Roof', 'MI_V_Roof_Present', 'MI_V_RoofGlaze', 'MI_V_RoofGlaze_Present'):
                    continue
                target = made['glaze_present'] if era == 'Present' else made['glaze']
                component.set_material(slot, target)
                REPORT['overrides'].append({'actor': actor.get_actor_label(), 'mesh': mesh.get_name(), 'slot': slot, 'was': current.get_name(), 'now': target.get_name()})
    vc.require(len(REPORT['overrides']) == 8, 'Expected 8 landmark roof slots, found %d' % len(REPORT['overrides']))


def lights(actors):
    seen = set()
    for actor in actors:
        label = actor.get_actor_label()
        spec = LIGHT.get(label)
        if spec is None:
            continue
        seen.add(label)
        row = REPORT['lights'].setdefault(label, {})
        for cls in (unreal.DirectionalLightComponent, unreal.SkyLightComponent, unreal.PointLightComponent):
            for component in actor.get_components_by_class(cls):
                row['intensity'] = {'was': component.get_editor_property('intensity'), 'now': spec['intensity']}
                component.set_editor_property('intensity', spec['intensity'])
                if 'colour' in spec:
                    old = component.get_editor_property('light_color')
                    row['colour_srgb_rgb'] = {'was': [old.r, old.g, old.b], 'now': [srgb_byte(v) for v in spec['colour']]}
                    r, g, b = (srgb_byte(v) for v in spec['colour'])
                    component.set_editor_property('light_color', unreal.Color(r=r, g=g, b=b, a=255))
                    check = component.get_editor_property('light_color')
                    vc.require((check.r, check.g, check.b) == (r, g, b), 'Sun colour did not take: %s' % label)
        for component in actor.get_components_by_class(unreal.ExponentialHeightFogComponent):
            for field, key in (('fog_inscattering_luminance', 'fog'), ('directional_inscattering_luminance', 'sun')):
                old = component.get_editor_property(field)
                row[field] = {'was': [round(old.r, 3), round(old.g, 3), round(old.b, 3)], 'now': list(spec[key])}
                component.set_editor_property(field, unreal.LinearColor(*spec[key], 1))
    vc.require(seen == set(LIGHT), 'Lights not found: %s' % sorted(set(LIGHT) - seen))
    for actor in actors:
        if isinstance(actor, unreal.PostProcessVolume) and actor.get_actor_label() == 'Verdant_Exposure':
            settings = actor.get_editor_property('settings')
            REPORT['exposure_bias'] = {'was': settings.get_editor_property('auto_exposure_bias'), 'now': EXPOSURE_BIAS}
            settings.set_editor_property('override_auto_exposure_bias', True)
            settings.set_editor_property('auto_exposure_bias', EXPOSURE_BIAS)
            actor.set_editor_property('settings', settings)
    vc.require('exposure_bias' in REPORT, 'Verdant_Exposure not found')


def dressing_component(actor, name, mesh_name, rows, overrides=None):
    """A collision-free instanced component on an existing era holder: the story's own era switch hides and shows
    the holder, so nothing new enters the manager's arrays."""
    component = next((c for c in actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent) if c.get_name() == name), None)
    created = component is None
    if created:
        component = vc.add_component(actor, unreal.HierarchicalInstancedStaticMeshComponent, name)
    mesh = unreal.load_asset(MESHES + mesh_name)
    vc.require(mesh is not None, 'Missing mesh ' + mesh_name)
    component.set_editor_property('static_mesh', mesh)
    component.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
    component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    component.set_editor_property('cast_shadow', False)
    component.set_cull_distances(14000, 22000)
    component.clear_instances()
    transforms = [unreal.Transform(location=unreal.Vector(x, y, z), rotation=unreal.Rotator(roll=0, pitch=0, yaw=yaw), scale=unreal.Vector(s, s, s))
                  for x, y, z, yaw, s in rows]
    indices = component.add_instances(transforms, True, True)
    vc.require(len(indices) == len(rows), 'Instance count mismatch for ' + name)
    for slot, material in (overrides or {}).items():
        component.set_material(slot, material)
    REPORT['components'].append({'actor': actor.get_actor_label(), 'component': name, 'mesh': mesh_name, 'instances': len(rows), 'created': created,
                                 'materials': [component.get_material(i).get_name() for i in range(component.get_num_materials())]})
    return component


def dressing(actors, made):
    past = next(a for a in actors if a.get_actor_label() == 'Verdant_Past')
    present = next(a for a in actors if a.get_actor_label() == 'Verdant_Present')
    dressing_component(past, 'Concept_Climbers', 'SM_V_Bougainvillea', [(x, y, z, yaw, .9) for x, y, z, yaw in CLIMBERS])
    banner_mesh = unreal.load_asset(MESHES + 'SM_V_Banner')
    overrides = {}
    for slot, entry in enumerate(banner_mesh.get_editor_property('static_materials')):
        material = entry.get_editor_property('material_interface')
        if material is not None and material.get_name() == 'M_V_Banner':
            overrides[slot] = made['banner_present']
        elif material is not None and material.get_name() == 'M_V_Timber':
            overrides[slot] = unreal.load_asset(MATERIALS + 'MI_V_Timber_Present')
    vc.require(any(m == made['banner_present'] for m in overrides.values()), 'SM_V_Banner has no banner slot')
    x, y, z, yaw = PRESENT_BANNER
    dressing_component(present, 'Concept_Banner', 'SM_V_Banner', [(x, y, z, yaw, 1.0)], overrides)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before = {f: digest(PROJECT / f) for f in FILES}
    if not ORIGINAL.exists():
        ORIGINAL.mkdir(parents=True)
        for f in FILES:
            target = ORIGINAL / f
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT / f, target)
        vc.write_json(ORIGINAL / 'sha256.json', before)
        REPORT['original_backup_written'] = True
    import_textures()
    made = materials()
    vc.require(vc.levels.load_level(MAP), 'Cannot load ' + MAP)
    actors = list(vc.actors.get_all_level_actors())
    counts = {'actors': len(actors)}
    landmark_roofs(actors, made)
    lights(actors)
    dressing(actors, made)
    home_roof(actors)
    tree_relief(actors)
    vc.require(len(list(vc.actors.get_all_level_actors())) == counts['actors'], 'The actor count changed')
    vc.require(vc.levels.save_current_level(), 'Cannot save the map')
    REPORT['actors'] = counts['actors']
    REPORT['files'] = {f: {'before': before[f], 'after': digest(PROJECT / f)} for f in FILES}
    REPORT['new_assets'] = NEW_ASSETS
    REPORT['original_backup'] = str(ORIGINAL)
    REPORT['settings'] = {'light': LIGHT, 'sky_gain': SKY_GAIN, 'exposure_bias': EXPOSURE_BIAS, 'climbers': CLIMBERS, 'present_banner': PRESENT_BANNER}
    REPORT['success'] = True


def keep_was(new, old):
    """A re-run must go on recording the values of 16 November as "was", not the values of the run before it."""
    if isinstance(new, dict) and isinstance(old, dict):
        if 'was' in new and 'was' in old:
            new['was'] = old['was']
        for key in new:
            if key in old:
                keep_was(new[key], old[key])
    elif isinstance(new, list) and isinstance(old, list):
        for a, b in zip(new, old):
            keep_was(a, b)


try:
    main()
    if RECORD.exists():
        earlier = json.loads(RECORD.read_text(encoding='utf-8'))
        for key in ('lights', 'sky_gain', 'exposure_bias', 'overrides'):
            keep_was(REPORT.get(key), earlier.get(key))
        REPORT['files'] = {f: {'before': earlier.get('files', {}).get(f, {}).get('before', row['before']), 'after': row['after']} for f, row in REPORT['files'].items()}
except Exception:
    REPORT['success'] = False
    REPORT['error'] = traceback.format_exc()
if REPORT['success']:
    vc.write_json(RECORD, REPORT)
vc.write_json(OUT / (STAMP + '_report.json'), REPORT)
vc.log('concept pass finished', json.dumps({'success': REPORT['success'], 'overrides': len(REPORT['overrides']), 'components': REPORT['components'],
                                            'error': (REPORT.get('error') or '')[-900:]}))
unreal.SystemLibrary.quit_editor()
