"""Imports the Verdant textures and meshes into /Game/Verdant and authors its materials.

Additive only: nothing outside /Game/Verdant is touched. Re-running replaces Verdant assets.
"""
import json
import sys
import time
import traceback
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(unreal.Paths.project_dir()).resolve() / 'Python'))
import verdant_common as vc
import verdant_materials as vm

REPORT = {'success': False, 'textures': 0, 'meshes': 0, 'warnings': []}
SETTINGS = unreal.TextureCompressionSettings


def task(filename, destination, name, options=None, factory=None):
    t = unreal.AssetImportTask()
    for key, value in (('filename', str(filename)), ('destination_path', destination), ('destination_name', name), ('automated', True),
                       ('save', False), ('replace_existing', True), ('replace_existing_settings', True)):
        t.set_editor_property(key, value)
    if options is not None:
        t.set_editor_property('options', options)
    if factory is not None:
        t.set_editor_property('factory', factory)
    vc.assets.import_asset_tasks([t])
    done = t.get_editor_property('imported_object_paths')
    asset = unreal.load_asset(done[0]) if done else unreal.load_asset(destination + '/' + name)
    vc.require(asset is not None, 'Import failed: ' + str(filename))
    return asset


def import_textures():
    folder = vc.SOURCE / 'textures'
    for file in sorted(folder.glob('T_V_*.png')):
        name = file.stem
        texture = task(file, vc.ROOT_PATH + '/Textures', name)
        if name.endswith('_N'):
            texture.set_editor_property('compression_settings', SETTINGS.TC_NORMALMAP)
            texture.set_editor_property('srgb', False)
            # Authored and scanned maps are DirectX convention, matching Unreal.
            texture.set_editor_property('flip_green_channel', False)
        elif name.endswith('_ARH') or name in ('T_V_Masks', 'T_V_Glass_M'):
            texture.set_editor_property('compression_settings', SETTINGS.TC_MASKS)
            texture.set_editor_property('srgb', False)
        else:
            texture.set_editor_property('compression_settings', SETTINGS.TC_BC7)
            texture.set_editor_property('srgb', True)
        vc.library.save_loaded_asset(texture)
        REPORT['textures'] += 1
    for era in ('Past', 'Present'):
        file = vc.SOURCE / 'sky' / ('Sky_%s_final.exr' % era)
        texture = task(file, vc.ROOT_PATH + '/Textures', 'T_V_Sky_' + era)
        texture.set_editor_property('compression_settings', SETTINGS.TC_HDR_COMPRESSED)
        texture.set_editor_property('srgb', False)
        texture.set_editor_property('address_x', unreal.TextureAddress.TA_WRAP)
        texture.set_editor_property('address_y', unreal.TextureAddress.TA_CLAMP)
        texture.set_editor_property('never_stream', True)
        texture.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        vc.library.save_loaded_asset(texture)
        REPORT['textures'] += 1
        cube = task(vc.SOURCE / 'sky' / ('Sky_%s_ambient.hdr' % era), vc.ROOT_PATH + '/Textures', 'TC_V_SkyAmbient_' + era)
        REPORT.setdefault('ambient_cubemaps', {})[era] = cube.get_class().get_name()
        if isinstance(cube, unreal.TextureCube):
            cube.set_editor_property('compression_settings', SETTINGS.TC_HDR)
            cube.set_editor_property('srgb', False)
        vc.library.save_loaded_asset(cube)


def mesh_filter():
    """-VerdantMeshFilter=<prefix> imports only the meshes whose name starts with the prefix."""
    for part in unreal.SystemLibrary.get_command_line().split():
        if part.lower().startswith('-verdantmeshfilter='):
            return part.split('=', 1)[1].strip('"')
    return None


def existing_materials():
    """The saved Verdant materials by slot label, for a filtered import that must not rebuild them."""
    labels = ('Masonry', 'Timber', 'Paint', 'Roof', 'Glass', 'Iron', 'Cloth', 'Leaf', 'Terracotta', 'Flat', 'Banner', 'Cobble', 'Flagstone', 'Sea', 'Sky')
    made = {label: unreal.load_asset(vc.ROOT_PATH + '/Materials/M_V_' + label) for label in labels}
    made['Rock'] = made['Ground'] = unreal.load_asset(vc.ROOT_PATH + '/Materials/M_V_Land')
    vc.require(all(made.values()), 'A saved Verdant material is missing; run the full import first')
    return made


def import_meshes(materials):
    manifest = json.loads((vc.SOURCE / 'kit_manifest.json').read_text(encoding='utf-8'))
    folder = vc.SOURCE / 'meshes'
    prefix = mesh_filter()
    if prefix:
        manifest = {name: row for name, row in manifest.items() if name.startswith(prefix)}
        REPORT['mesh_filter'] = prefix
    for name in sorted(manifest):
        options = unreal.FbxImportUI()
        for key, value in (('import_mesh', True), ('import_as_skeletal', False), ('import_materials', False), ('import_textures', False),
                           ('automated_import_should_detect_type', False), ('mesh_type_to_import', unreal.FBXImportType.FBXIT_STATIC_MESH)):
            options.set_editor_property(key, value)
        data = options.get_editor_property('static_mesh_import_data')
        for key, value in (('combine_meshes', True), ('auto_generate_collision', False), ('generate_lightmap_u_vs', False), ('remove_degenerates', True),
                           ('convert_scene', True), ('convert_scene_unit', True), ('force_front_x_axis', False), ('transform_vertex_to_absolute', True)):
            data.set_editor_property(key, value)
        data.set_editor_property('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        data.set_editor_property('vertex_color_import_option', unreal.VertexColorImportOption.REPLACE)
        mesh = task(folder / (name + '.fbx'), vc.ROOT_PATH + '/Meshes', name, options, unreal.FbxFactory())
        slots = mesh.get_editor_property('static_materials')
        for index, slot in enumerate(slots):
            label = str(slot.get_editor_property('material_slot_name')).replace('M_V_', '').split('_')[0]
            material = materials.get(label)
            if material is None:
                REPORT['warnings'].append('%s: no material for slot %s' % (name, label))
                continue
            mesh.set_material(index, material)
        body = mesh.get_editor_property('body_setup')
        if body is not None:
            # Land meshes are walked on; story-set props stand in for interactable and blocking actors on
            # the story map, so they collide with their triangles too. Kit and dressing meshes stay
            # collision-free (the maps place invisible colliders for them).
            walkable = name in ('SM_V_Land_Near', 'SM_V_Land_Far', 'SM_V_Land_Surfaces', 'SM_V_Land_Walls', 'SM_V_Land_Ramps') or name.startswith('SM_V_Story_')
            body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if walkable
                                     else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
        triangles = manifest[name]['triangles']
        if triangles > 400 and not name.startswith('SM_V_Land') and name not in ('SM_V_Sea', 'SM_V_SkyDome'):
            try:
                rows = [unreal.EditorScriptingMeshReductionSettings(percent_triangles=p, screen_size=sz) for p, sz in ((1.0, 1.0), (.5, .22), (.2, .07))]
                reduction = unreal.EditorScriptingMeshReductionOptions(auto_compute_lod_screen_size=False, reduction_settings=rows)
                made = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).set_lods(mesh, reduction)
                REPORT.setdefault('lods', {})[name] = made
            except Exception as problem:
                REPORT['warnings'].append('%s: LOD generation skipped (%s)' % (name, str(problem)[:160]))
        vc.library.save_loaded_asset(mesh)
        REPORT['meshes'] += 1
        if REPORT['meshes'] % 20 == 0:
            vc.log('meshes', REPORT['meshes'], '/', len(manifest))


start = time.monotonic()
try:
    if not vc.has_flag('VerdantMeshesOnly'):
        import_textures()
        vc.log('textures', REPORT['textures'])
    if mesh_filter():
        made = existing_materials()
        vc.log('materials reused for filtered import')
    else:
        made, present, sky_past, sky_present = vm.build_all()
        vc.log('materials ok')
    import_meshes(made)
    REPORT['success'] = True
except Exception:
    REPORT['error'] = traceback.format_exc()
REPORT['seconds'] = round(time.monotonic() - start, 1)
vc.write_json(vc.EVIDENCE / 'import_report.json', REPORT)
vc.log('import finished', json.dumps({k: v for k, v in REPORT.items() if k != 'warnings'})[:900], 'warnings', len(REPORT['warnings']))
unreal.SystemLibrary.quit_editor()
