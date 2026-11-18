"""New corrected clothing mesh on the existing normalized Mother skeleton.

Preserve prior proof files and meshes. Reuse the exact existing53-bone skeleton
and gait only after actual native compatibility/pose checks. No story NPC swap.
"""
from pathlib import Path
import json,hashlib,inspect,sys,traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/'Python'))
import import_release_unit_probe as unit
import import_release_characters as mother
import release_file_io as io
import retarget_release_characters as rt


def main():
    mother.require(ROOT.parent.name=='Release_20261026','Release copy required')
    latest=json.loads((ROOT.parent/'output/release_mother_rev7/latest.json').read_text())
    source=Path(latest['manifest']);data=json.loads(source.read_text())
    mother.require(data['success'] and data['art_revision']==7 and io.sha(data['fbx']['path'])==data['fbx']['sha256'],'Proved REV7 source required')
    prior_unit=json.loads((ROOT/'release_character_unit_probe_report.json').read_text())
    prior=prior_unit['preferred_candidate']
    old_mesh=unreal.load_asset(prior['mesh'])
    skeleton=old_mesh.get_editor_property('skeleton')
    parent='/Game/Release/MotherR7_'+data['fbx']['sha256'][:12]
    disk=ROOT/'Content'/parent.removeprefix('/Game/')
    before={str(p):io.sha(p) for p in io.files(ROOT/'Content','*.uasset')+io.files(ROOT/'Content','*.umap')+list((ROOT/'Config').glob('*.ini'))+list(ROOT.glob('*.uproject'))}
    own_report=ROOT/'release_mother_rev7_unit_report.json'
    if own_report.exists():
        value=json.loads(own_report.read_text())
        mother.require(value['success'] and value['source_manifest_sha256']==io.sha(source),'Preserving another/failed revision')
        return
    materials={name:mother.material(name,recipe,parent,'rev7_'+data['fbx']['sha256'][:12]) for name,recipe in data['material_recipes'].items()}
    # Same proved FBX importer, with explicit existing skeleton reuse. It must
    # never update the reused skeleton reference pose or save that skeleton.
    code=inspect.getsource(mother.import_fbx)
    needle="    mesh_options = options.get_editor_property('skeletal_mesh_import_data')"
    mother.require(code.count(needle)==1,'Reviewed importer changed')
    code=code.replace(needle,"    options.set_editor_property('skeleton', REUSED_SKELETON)\n"+needle)
    env=dict(mother.__dict__,REUSED_SKELETON=skeleton)
    exec(compile(code,str(ROOT/'Python/import_release_mother_rev7.py'),'exec'),env)
    old_import=mother.import_fbx
    mother.import_fbx=lambda source,folder,signature:[a for a in env['import_fbx'](source,folder,signature) if a.get_path_name().startswith(folder+'/')]
    case={'id':'R7','fbx':data['fbx']['path'],'fbx_sha256':data['fbx']['sha256'],
          'physical_morph_coordinate_preservation':data['physical_morph_coordinate_preservation'],
          'physical_pose_preservation':data['physical_pose_preservation'],
          'source_bone_names':data['rest_bone_names'],'source_bone_count':53,'unit_representation_changed':True}
    try:
        candidate=unit.import_case(case,parent,data['effective_morph_measurement']['effective_facial_morphs'],materials,None)
    finally:
        mother.import_fbx=old_import
    mesh=unreal.load_asset(candidate['mesh'])
    mother.require(mesh.get_editor_property('skeleton')==skeleton,'Existing Mother skeleton was not reused')
    # Materials created before import_case live one folder above it; save and
    # fingerprint those too, without touching reused old materials/skeleton.
    for asset in materials.values():unreal.EditorAssetLibrary.save_loaded_asset(asset)
    for path in unreal.EditorAssetLibrary.list_assets(parent+'/Textures',True):unreal.EditorAssetLibrary.save_loaded_asset(unreal.load_asset(path))
    for p,digest in before.items():mother.require(io.sha(p)==digest,'Existing native input changed: '+p)
    candidate['owned_asset_sha256']={str(p):io.sha(p) for p in io.files(disk,'*.uasset')+io.files(disk,'*.umap')}
    value={'success':True,'native_executed':True,'source_manifest':str(source),'source_manifest_sha256':io.sha(source),
           'preferred_candidate':candidate,'existing53_bone_skeleton_reused':skeleton.get_path_name(),'story_npcs_replaced':False}
    own_report.write_text(json.dumps(value,indent=2)+'\n')
    (ROOT/'release_mother_rev7_import_report.json').write_text(json.dumps(dict(candidate,success=True,native_executed=True),indent=2)+'\n')
    old_bake=ROOT/'release_mother_unit_retarget_report.json'
    baked=json.loads(old_bake.read_text())
    walk=unreal.load_asset(baked['baked']['walk'])
    idle=unreal.load_asset(candidate['animation'])
    mother.require(walk.get_editor_property('skeleton')==skeleton and idle.get_editor_property('skeleton')==skeleton,'Exact skeleton-compatible clips required')
    compatible=dict(baked)
    compatible.update(target_mesh=candidate['mesh'],source_unit_probe_report_sha256=io.sha(own_report),
        reused_bake_not_retargeted=True,original_bake_report=str(old_bake),original_bake_report_sha256=io.sha(old_bake),
        pose_evidence={'walk':rt.sample(walk,mesh,'walk',True)},baked={'walk':walk.get_path_name(),'idle':idle.get_path_name()})
    (ROOT/'release_mother_rev7_compatible_bake.json').write_text(json.dumps(compatible,indent=2)+'\n')


if __name__=='__main__':
    try:main()
    except Exception:
        (ROOT/'release_mother_rev7_import_failed.json').write_text(json.dumps({'success':False,'error':traceback.format_exc()},indent=2))
        unreal.log_error(traceback.format_exc())
    unreal.SystemLibrary.quit_editor()
