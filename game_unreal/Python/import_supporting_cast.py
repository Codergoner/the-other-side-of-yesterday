"""Import the reviewed Blender supporting cast into new, owned Unreal namespaces.

Run in the editor process (not a commandlet):
  UnrealEditor-Cmd.exe <project> -ExecutePythonScript="<this file>" -SupportingCastImport
      [-SupportingCastRoles=HarborClerk,Tavi]

Reads output/supporting_cast/accepted.json (the visually reviewed Blender run) and
each role's manifest from that run. Creates only /Game/Release/SC/<Role>_<sig>/ with
textures, materials rebuilt from the recorded Blender recipes, the skeletal mesh,
its own skeleton, its idle animation and a generated query physics asset.
Does not open or save any map, the story manager, saves or config.
Writes game_unreal/supporting_cast_import_report.json.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
ROOT = PROJECT.parent
sys.path.insert(0, str(PROJECT / 'Python'))
import quest_scenery as graph  # proven material-graph helpers (node/connect/output/scalar/color/sample)

ASSETS = unreal.AssetToolsHelpers.get_asset_tools()
LIB = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
OWNER = 'TOSOY.SupportingCastOwned'
SOURCE = ROOT / 'output' / 'supporting_cast'
REPORT = PROJECT / 'supporting_cast_import_report.json'
BASE = '/Game/Release/SC'
SHARED_TEX = BASE + '/Shared/Textures'


def require(test, message):
    if not test:
        raise RuntimeError(message)


def long_path(path):
    value = str(Path(path).resolve()) if not str(path).startswith('\\\\?\\') else str(path)
    return Path('\\\\?\\' + value) if not value.startswith('\\\\?\\') else Path(value)


def sha(path):
    digest = hashlib.sha256()
    with open(long_path(path), 'rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def tag(asset, role, signature, **extra):
    LIB.set_metadata_tag(asset, 'TOSOY.SC.Owner', OWNER)
    LIB.set_metadata_tag(asset, 'TOSOY.SC.Role', role)
    LIB.set_metadata_tag(asset, 'TOSOY.SC.Signature', signature)
    for key, value in extra.items():
        LIB.set_metadata_tag(asset, 'TOSOY.SC.' + key, str(value))


def owned(asset):
    return LIB.get_metadata_tag(asset, 'TOSOY.SC.Owner') == OWNER


def load(path):
    return unreal.load_asset(path) if LIB.does_asset_exist(path) else None


# ---------------------------------------------------------------- textures
def import_texture(file, kind, role, signature):
    file = Path(file)
    require(long_path(file).is_file(), 'Missing source texture: ' + str(file))
    digest = sha(file)
    stem = re.sub(r'[^A-Za-z0-9_]', '_', file.stem)[:40]
    name = 'T_SC_' + stem + '_' + digest[:8]
    path = SHARED_TEX + '/' + name
    tex = load(path)
    if tex:
        require(owned(tex) and LIB.get_metadata_tag(tex, 'TOSOY.SC.SourceSha256') == digest,
                'Preserving an unowned or different texture: ' + path)
        return tex
    task = unreal.AssetImportTask()
    for key, value in {'filename': str(file), 'destination_path': SHARED_TEX, 'destination_name': name,
                       'automated': True, 'replace_existing': False, 'save': False}.items():
        task.set_editor_property(key, value)
    ASSETS.import_asset_tasks([task])
    tex = load(path)
    require(isinstance(tex, unreal.Texture2D), 'Texture import failed: ' + str(file))
    if kind == 'normal':
        tex.set_editor_property('srgb', False)
        tex.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property('flip_green_channel', True)   # Blender/OpenGL -> Unreal/DirectX
        tex.set_editor_property('max_texture_size', 1024)
    else:
        tex.set_editor_property('srgb', True)
        tex.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
        big = any(k in file.stem.lower() for k in ('diffuse', 'skin', 'beard'))
        tex.set_editor_property('max_texture_size', 2048 if big else 1024)
    tag(tex, 'Shared', 'shared', SourceSha256=digest, SourceFile=file.name)
    return tex


# ---------------------------------------------------------------- materials
def _out(node, mat, prop, pin=''):
    graph.output(node, mat, prop, pin)


def build_material(name, recipe, folder, role, signature):
    path = folder + '/Materials/' + name
    recipe_sha = json_sha(recipe)
    mat = load(path)
    if mat:
        require(owned(mat) and LIB.get_metadata_tag(mat, 'TOSOY.SC.RecipeSha256') == recipe_sha,
                'Preserving an edited or unowned material: ' + path)
        graph.check_material_compile(mat)
        return mat
    mat = ASSETS.create_asset(name, folder + '/Materials', unreal.Material, unreal.MaterialFactoryNew())
    require(mat, 'Cannot create material ' + path)
    masked = bool(recipe.get('masked'))
    mat.set_editor_property('two_sided', bool(recipe.get('two_sided')))
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED if masked else unreal.BlendMode.BLEND_OPAQUE)
    if masked:
        mat.set_editor_property('opacity_mask_clip_value', 0.33)
    MEL.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
    MEL.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_MORPH_TARGETS)
    mode = recipe['mode']
    if mode == 'flat':
        base = graph.color(mat, recipe['color'])
        _out(base, mat, unreal.MaterialProperty.MP_BASE_COLOR)
        if recipe.get('emissive'):
            glow = graph.node(mat, 'Multiply')
            graph.connect(graph.color(mat, recipe['emissive']), glow, 'A')
            graph.connect(graph.scalar(mat, float(recipe.get('emissive_strength', 4.0))), glow, 'B')
            _out(glow, mat, unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    elif mode == 'texture':
        require(sha(recipe['texture']) == recipe['texture_sha256'], 'Texture differs from its Blender recipe: ' + recipe['texture'])
        sample = graph.sample(mat, import_texture(recipe['texture'], 'color', role, signature))
        gain = graph.node(mat, 'Multiply')
        graph.connect(sample, gain, 'A', 'RGB')
        graph.connect(graph.color(mat, recipe.get('gain', [1, 1, 1])), gain, 'B')
        _out(gain, mat, unreal.MaterialProperty.MP_BASE_COLOR)
        if masked:
            _out(sample, mat, unreal.MaterialProperty.MP_OPACITY_MASK, 'A')
    elif mode == 'lumtint':
        require(sha(recipe['texture']) == recipe['texture_sha256'], 'Texture differs from its Blender recipe: ' + recipe['texture'])
        tiling = recipe.get('tiling', [1, 1])
        uv = graph.node(mat, 'TextureCoordinate', u_tiling=float(tiling[0]), v_tiling=float(tiling[1]))
        sample = graph.sample(mat, import_texture(recipe['texture'], 'color', role, signature))
        graph.connect(uv, sample, 'UVs')
        # Same recolour as Blender: L=dot(rgb,Rec709); ((L-mean)*contrast+mean)/mean, >=0; * tint.
        luma = graph.node(mat, 'DotProduct')
        graph.connect(sample, luma, 'A', 'RGB')
        graph.connect(graph.color(mat, [0.2126, 0.7152, 0.0722]), luma, 'B')
        mean = float(recipe['mean_l'])
        chain = luma
        for op, value in [('Subtract', mean), ('Multiply', float(recipe['contrast'])), ('Add', mean),
                          ('Divide', mean), ('Max', 0.0)]:
            n = graph.node(mat, op)
            graph.connect(chain, n, 'A')
            graph.connect(graph.scalar(mat, value), n, 'B')
            chain = n
        tint = graph.node(mat, 'Multiply')
        graph.connect(chain, tint, 'A')
        graph.connect(graph.color(mat, recipe['tint']), tint, 'B')
        _out(tint, mat, unreal.MaterialProperty.MP_BASE_COLOR)
        if masked:
            _out(sample, mat, unreal.MaterialProperty.MP_OPACITY_MASK, 'A')
        if recipe.get('normal'):
            normal_sample = graph.sample(mat, import_texture(recipe['normal'], 'normal', role, signature), 'normal')
            graph.connect(uv, normal_sample, 'UVs')
            blend = graph.node(mat, 'LinearInterpolate')
            graph.connect(graph.color(mat, [0.0, 0.0, 1.0]), blend, 'A')
            graph.connect(normal_sample, blend, 'B', 'RGB')
            graph.connect(graph.scalar(mat, float(recipe.get('normal_strength', 0.6))), blend, 'Alpha')
            _out(blend, mat, unreal.MaterialProperty.MP_NORMAL)
    else:
        raise RuntimeError('Unknown material recipe mode %s for %s' % (mode, name))
    for key, prop, default in [('roughness', unreal.MaterialProperty.MP_ROUGHNESS, 0.85),
                               ('specular', unreal.MaterialProperty.MP_SPECULAR, 0.35),
                               ('metallic', unreal.MaterialProperty.MP_METALLIC, 0.0)]:
        _out(graph.scalar(mat, float(recipe.get(key, default))), mat, prop)
    graph.check_material_compile(mat)
    tag(mat, role, signature, RecipeSha256=recipe_sha)
    return mat


# ---------------------------------------------------------------- skeletal mesh
def import_fbx(fbx, folder, role, signature):
    mesh_folder = folder + '/Meshes'
    existing = [load(p) for p in LIB.list_assets(mesh_folder, recursive=True)] if LIB.does_directory_exist(mesh_folder) else []
    existing = [a for a in existing if a]
    if existing:
        require(all(owned(a) for a in existing), 'Preserving unowned mesh assets in ' + mesh_folder)
        return existing
    options = unreal.FbxImportUI()
    for key, value in {'import_mesh': True, 'import_as_skeletal': True, 'import_animations': True,
                       'import_materials': False, 'import_textures': False, 'create_physics_asset': False,
                       'automated_import_should_detect_type': False,
                       'mesh_type_to_import': unreal.FBXImportType.FBXIT_SKELETAL_MESH}.items():
        options.set_editor_property(key, value)
    mesh_data = options.get_editor_property('skeletal_mesh_import_data')
    for key, value in {'import_morph_targets': True, 'update_skeleton_reference_pose': False, 'use_t0_as_ref_pose': False,
                       'convert_scene': True, 'convert_scene_unit': True,
                       'normal_import_method': unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS}.items():
        mesh_data.set_editor_property(key, value)
    anim = options.get_editor_property('anim_sequence_import_data')
    anim.set_editor_property('use_default_sample_rate', True)
    anim.set_editor_property('animation_length', unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    task = unreal.AssetImportTask()
    for key, value in {'filename': str(fbx), 'destination_path': mesh_folder, 'destination_name': 'SK_SC_' + role,
                       'automated': True, 'replace_existing': False, 'save': False,
                       'factory': unreal.FbxFactory(), 'options': options}.items():
        task.set_editor_property(key, value)
    ASSETS.import_asset_tasks([task])
    assets = [load(str(p).split('.')[0]) for p in task.get_editor_property('imported_object_paths')]
    assets += [load(p) for p in LIB.list_assets(mesh_folder, recursive=True)]
    unique = {a.get_path_name(): a for a in assets if a}
    for asset in unique.values():
        tag(asset, role, signature)
    return list(unique.values())


def morph_names(mesh):
    try:
        return sorted(str(m.get_name()) for m in mesh.call_method('GetMorphTargetsPtrConv'))
    except Exception:
        try:
            return sorted(str(n) for n in mesh.get_editor_property('morph_targets'))
        except Exception:
            return []


def import_role(role, entry):
    manifest = Path(entry['manifest'])
    data = json.loads(long_path(manifest).read_text(encoding='utf-8'))
    require(data['success'] and data['role'] == role, 'Manifest is not a successful build of ' + role)
    require(sha(data['fbx']['path']) == data['fbx']['sha256'], role + ' FBX changed after its Blender build')
    require(data.get('export_armature_object_name') == 'Armature' and data.get('bone_count') == 53,
            role + ' is not the normalized 53-bone MPFB game-engine export')
    signature = json_sha({'fbx': data['fbx']['sha256'], 'materials': data['materials']})[:10]
    folder = BASE + '/' + role + '_' + signature
    mats = {name: build_material(name, recipe, folder, role, signature) for name, recipe in data['materials'].items()}
    imported = import_fbx(data['fbx']['path'], folder, role, signature)
    meshes = [a for a in imported if isinstance(a, unreal.SkeletalMesh)]
    anims = [a for a in imported if isinstance(a, unreal.AnimSequence)]
    skeletons = [a for a in imported if isinstance(a, unreal.Skeleton)]
    require(len(meshes) == 1, '%s: expected one skeletal mesh, found %d' % (role, len(meshes)))
    require(anims, role + ': no idle animation imported')
    mesh = meshes[0]
    anim = max(anims, key=lambda a: a.get_play_length())
    slots, assignments, unmatched = list(mesh.get_editor_property('materials')), [], []
    for slot in slots:
        slot_name = str(slot.get_editor_property('imported_material_slot_name'))
        matches = [k for k in mats if k == slot_name]
        if not matches:  # FBX may decorate slot names; take the longest recipe name that fits
            fits = [k for k in mats if slot_name.replace('.', '_').endswith(k) or slot_name.startswith(k)]
            matches = sorted(fits, key=len, reverse=True)[:1]
        if len(matches) != 1:
            unmatched.append(slot_name)
            continue
        slot.set_editor_property('material_interface', mats[matches[0]])
        assignments.append({'slot': slot_name, 'material': mats[matches[0]].get_path_name()})
    mesh.set_editor_property('materials', slots)
    require(not unmatched, '%s: material slots without a recipe: %s' % (role, unmatched))
    physics = mesh.get_editor_property('physics_asset')
    if not physics:
        subsystem = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
        physics = subsystem.create_physics_asset(mesh, False, 0)
        require(physics, role + ': query physics asset could not be generated')
        require(subsystem.is_physics_asset_compatible(mesh, physics), role + ': physics asset is not compatible')
        mesh.set_editor_property('physics_asset', physics)
        tag(physics, role, signature)
    bounds = mesh.get_bounds()
    height_cm = float(bounds.box_extent.z * 2.0)
    morphs = morph_names(mesh)
    for asset in list(mats.values()) + [mesh, anim, physics] + skeletons:
        require(LIB.save_loaded_asset(asset, False), 'Cannot save ' + asset.get_path_name())
    for path in LIB.list_assets(SHARED_TEX, recursive=False):
        asset = load(path)
        if asset:
            LIB.save_loaded_asset(asset, True)
    return {'role': role, 'display_name': data['display_name'], 'working_name': data.get('working_name'),
            'story_tag': data['story_tag'], 'era': data['era'], 'folder': folder, 'signature': signature,
            'mesh': mesh.get_path_name(), 'skeleton': skeletons[0].get_path_name() if skeletons else
            mesh.get_editor_property('skeleton').get_path_name(), 'animation': anim.get_path_name(),
            'animation_seconds': float(anim.get_play_length()), 'physics_asset': physics.get_path_name(),
            'materials': assignments, 'material_count': len(mats), 'morph_target_count': len(morphs),
            'morph_targets_sample': morphs[:8], 'native_bounds_height_cm': height_cm,
            'source_height_m': data.get('height_m'), 'source_manifest': str(manifest), 'source_manifest_sha256': sha(manifest),
            'fbx_sha256': data['fbx']['sha256'], 'source_run': data['run']}


def main():
    report = {'success': False, 'started_utc': datetime.now(timezone.utc).isoformat(), 'roles': {},
              'scope': 'Native import/compile of reviewed Blender candidates into new owned namespaces. '
                       'No map, manager, save or config change; not gameplay or visual approval.'}
    try:
        command = unreal.SystemLibrary.get_command_line()
        require(unreal.SystemLibrary.parse_param(command, 'SupportingCastImport'), 'Explicit -SupportingCastImport required')
        require(ROOT.name == 'Release_20261026', 'Only the Release_20261026 working copy may be written')
        accepted = json.loads(long_path(SOURCE / 'accepted.json').read_text(encoding='utf-8'))
        wanted = list(accepted['roles'])
        match = re.search(r'-SupportingCastRoles=([A-Za-z,]+)', command)
        if match:
            wanted = [r for r in match.group(1).split(',') if r in accepted['roles']]
        report['accepted_run'] = accepted['run']
        for role in wanted:
            try:
                report['roles'][role] = dict(import_role(role, accepted['roles'][role]), ok=True)
            except Exception:
                report['roles'][role] = {'ok': False, 'error': traceback.format_exc()}
                unreal.log_error(traceback.format_exc())
        report['success'] = all(r.get('ok') for r in report['roles'].values()) and bool(report['roles'])
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        REPORT.write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8')
        unreal.log('SUPPORTING_CAST_IMPORT_DONE ' + str(report['success']))


if __name__ == '__main__':
    try:
        main()
    finally:
        unreal.SystemLibrary.quit_editor()
