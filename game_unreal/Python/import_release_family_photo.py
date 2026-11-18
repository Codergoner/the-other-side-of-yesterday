"""Bounded photo prop update: one slot and two instance material references.

No graph, story/save field, object identity, transform or collision change. The
generated image is a diegetic prop, never gameplay evidence or an NPC substitute.
Full editor, root native queue and -ReleasePhotoWrite required.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import build_release_art as base
import release_file_io as io

DEV = ROOT.parent
MAP = '/Game/Quest/Maps/Verdant_Desktop'
MAP_FILE = ROOT / 'Content/Quest/Maps/Verdant_Desktop.umap'
SOURCE = DEV / 'output/story_props/family_photo'
REPORT = ROOT / 'release_family_photo_report.json'
OWNER = 'TOSOY.ReleaseFamilyPhoto'


def files():
    values = io.files(ROOT/'Content', '*.uasset') + io.files(ROOT/'Content', '*.umap')
    values += list((ROOT/'Config').glob('*.ini')) + list(ROOT.glob('*.uproject'))
    values += io.files(ROOT/'Saved/SaveGames', '*.sav')
    return {str(p): io.sha(p) for p in values}


def mark(asset, sig):
    unreal.EditorAssetLibrary.set_metadata_tag(asset, 'Release.Photo.Owner', OWNER)
    unreal.EditorAssetLibrary.set_metadata_tag(asset, 'Release.Photo.Signature', sig)


def material(name, texture, folder, sig, inspection):
    path = folder + '/' + name
    mat = unreal.load_asset(path)
    if mat:
        base.require(unreal.EditorAssetLibrary.get_metadata_tag(mat, 'Release.Photo.Signature') == sig,
                     'Preserving a changed/unowned photo material')
        return mat
    mat = base.ASSETS.create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())
    base.require(mat is not None, 'Cannot create photo material')
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('two_sided', False)
    mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT if inspection else unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    sample = base.node(mat, 'TextureSample', texture=texture,
                       sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    base.out(sample, mat, unreal.MaterialProperty.MP_EMISSIVE_COLOR if inspection else unreal.MaterialProperty.MP_BASE_COLOR, 'RGB')
    if not inspection:
        base.out(base.scalar(mat, .88), mat, unreal.MaterialProperty.MP_ROUGHNESS)
        base.out(base.scalar(mat, .15), mat, unreal.MaterialProperty.MP_SPECULAR)
    base.require(not list(base.MEL.recompile_material(mat)), 'Photo material compilation failed')
    mark(mat, sig)
    base.require(unreal.EditorAssetLibrary.save_loaded_asset(mat), 'Photo material save failed')
    return mat


def refs(manager):
    result = base.story_refs()
    return result


def main():
    base.guard()
    base.require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleasePhotoWrite'),
                 'Root queue and explicit photo write flag required')
    provenance = json.loads((SOURCE/'provenance.json').read_text(encoding='utf-8'))
    source = Path(provenance['project_asset']).resolve()
    base.require(source.is_relative_to(SOURCE.resolve()) and io.sha(source).lower() == provenance['sha256'].lower(), 'Photo source provenance differs')
    base.require(provenance['width'] == 1448 and provenance['height'] == 1086 and provenance['not_gameplay'], 'Unexpected photo source')
    sig = provenance['sha256'][:16].lower()
    folder = '/Game/Release/StoryProps/Photo_' + sig
    before_files = files()
    base.require(base.LEVEL.load_level(MAP), 'Cannot load desktop map')
    before_actors = base.snapshot()
    before_lights = base.lighting()
    managers = [a for a in base.actors() if a.actor_has_tag('Opening.Manager')]
    base.require(len(managers) == 1, 'Exactly one story manager required')
    manager = managers[0]
    photo = manager.get_editor_property('PhotoActor')
    base.require(photo and photo.actor_has_tag('home.photo'), 'Stable photo actor reference required')
    comp = photo.get_component_by_class(unreal.StaticMeshComponent)
    before_refs = refs(manager)
    original = {'photo_material': comp.get_material(0).get_path_name(),
                'InspectionMaterial': manager.get_editor_property('InspectionMaterial').get_path_name(),
                'PhotoBackInspectionMaterial': manager.get_editor_property('PhotoBackInspectionMaterial').get_path_name()}
    old = json.loads(REPORT.read_text()) if REPORT.exists() else None
    if old and old.get('success'):
        base.require(old['source_sha256'].lower() == provenance['sha256'].lower(), 'Existing photo adoption has another source')
        base.require(base.state(photo) == old['photo_after'], 'Preserving a manually edited photo actor')
        for name, path in old['assigned'].items():
            actual = comp.get_material(0) if name == 'photo_material' else manager.get_editor_property(name)
            base.require(actual.get_path_name() == path, 'Preserving an edited photo material reference')
        for path, digest in old['owned_assets'].items():
            base.require(io.sha(path) == digest, 'Preserving edited owned photo content')
        return dict(old, repeated_without_save=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    backup = ROOT/'validation/release_family_photo'/stamp
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(io.io_path(MAP_FILE), backup/'Verdant_Desktop.before.umap')
    texture_path = folder + '/T_FamilyPhoto'
    texture = unreal.load_asset(texture_path)
    if not texture:
        task = unreal.AssetImportTask()
        for name, value in {'filename': str(source), 'destination_path': folder,
                            'destination_name': 'T_FamilyPhoto', 'automated': True,
                            'replace_existing': False, 'save': False}.items():
            task.set_editor_property(name, value)
        base.ASSETS.import_asset_tasks([task])
        texture = unreal.load_asset(texture_path)
        base.require(isinstance(texture, unreal.Texture2D), 'Native photo import failed')
        texture.set_editor_property('srgb', True)
        texture.set_editor_property('max_texture_size', 1024)
        texture.set_editor_property('power_of_two_mode', unreal.TexturePowerOfTwoSetting.RESIZE_TO_SPECIFIC_RESOLUTION)
        texture.set_editor_property('resize_during_build_x', 1024)
        texture.set_editor_property('resize_during_build_y', 1024)
        mark(texture, sig)
        base.require(unreal.EditorAssetLibrary.save_loaded_asset(texture), 'Photo texture save failed')
    # Reuse the original reverse's actual native texture, without editing it.
    reverse = unreal.load_asset(original['PhotoBackInspectionMaterial'])
    reverse_textures = list(base.MEL.get_used_textures(reverse))
    base.require(len(reverse_textures) == 1, 'Expected exactly one existing inscription texture')
    world = material('M_FamilyPhotoWorld', texture, folder, sig, False)
    front = material('M_FamilyPhotoInspect', texture, folder, sig, True)
    back = material('M_FamilyPhotoReverse', reverse_textures[0], folder, sig, True)
    comp.set_material(0, world)
    manager.set_editor_property('InspectionMaterial', front)
    manager.set_editor_property('PhotoBackInspectionMaterial', back)
    after_actors = base.snapshot()
    base.require(set(before_actors) == set(after_actors), 'Photo update changed actor roster')
    for name, prior in before_actors.items():
        after = after_actors[name]
        if name == photo.get_name():
            base.require(base.physical(prior) == base.physical(after), 'Photo transform/collision/identity changed')
        else:
            base.require(prior == after, 'Unrelated actor changed: ' + name)
    base.require(before_lights == base.lighting() and before_refs == refs(manager), 'Photo update changed lighting or narrative references')
    base.require(base.LEVEL.save_current_level(), 'Cannot save photo adoption')
    base.require(base.LEVEL.load_level(MAP), 'Cannot reload photo adoption')
    photo = next(a for a in base.actors() if a.actor_has_tag('home.photo'))
    base.require(base.state(photo) == after_actors[photo.get_name()], 'Saved photo readback differs')
    after_files = files()
    for path, digest in before_files.items():
        base.require(Path(path) == MAP_FILE or after_files.get(path) == digest, 'Unrelated existing file changed: ' + path)
    own_disk = ROOT/'Content/Release/StoryProps'/('Photo_' + sig)
    result = {'success': True, 'native_executed': True, 'map': MAP, 'source_sha256': provenance['sha256'],
              'namespace': folder, 'generated_prop_texture_not_footage': True, 'story_or_graph_changed': False,
              'inspection_policy': 'Opaque unlit RGB1, depth-tested; replaces inherited translucent emissive2200 workaround only on two desktop instance refs.',
              'original': original, 'photo_after': base.state(photo), 'backup': str(backup),
              'assigned': {'photo_material': world.get_path_name(), 'InspectionMaterial': front.get_path_name(), 'PhotoBackInspectionMaterial': back.get_path_name()},
              'reverse_texture': reverse_textures[0].get_path_name(),
              'owned_assets': {str(p): io.sha(p) for p in io.files(own_disk, '*.uasset')},
              'visual_inspection_passed': False, 'unrelated_files_unchanged': True}
    REPORT.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    try:
        main()
    except Exception:
        (ROOT/'release_family_photo_failed.json').write_text(json.dumps({'success': False, 'error': traceback.format_exc()}, indent=2), encoding='utf-8')
        unreal.log_error(traceback.format_exc())
    finally:
        unreal.SystemLibrary.quit_editor()
