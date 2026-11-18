"""Read-only inspection in the separate template staging project only."""
from pathlib import Path
import json
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
assert root.name == 'template_inspection', 'Never run this probe in the production project'
bp = unreal.load_asset('/Game/XRFramework/Blueprints/BP_XRPawn')
assert isinstance(bp, unreal.Blueprint), 'Installed XRFramework pawn did not load'
sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
lib = unreal.SubobjectDataBlueprintFunctionLibrary
components = []
attachments = {}
for handle in sub.k2_gather_subobject_data_for_blueprint(bp):
    data = lib.get_data(handle)
    obj = lib.get_object_for_blueprint(data, bp)
    entry = {'variable': str(lib.get_variable_name(data)), 'class': obj.get_class().get_path_name() if obj else None}
    if isinstance(obj, unreal.SceneComponent):
        parent_handle = lib.get_parent_handle(data)
        entry['parent_variable'] = str(lib.get_variable_name(lib.get_data(parent_handle))) if lib.is_handle_valid(parent_handle) else None
        entry['relative_location'] = str(obj.get_editor_property('relative_location'))
        entry['relative_rotation'] = str(obj.get_editor_property('relative_rotation'))
        entry['relative_scale'] = str(obj.get_editor_property('relative_scale3d'))
        parent = obj.get_attach_parent()
        entry['parent'] = parent.get_name() if parent else None
    if isinstance(obj, unreal.MotionControllerComponent):
        entry['motion_source'] = str(obj.get_editor_property('motion_source'))
    if isinstance(obj, unreal.SkeletalMeshComponent):
        entry['skeletal_mesh'] = str(obj.get_editor_property('skeletal_mesh_asset'))
        v = obj.get_editor_property('relative_location')
        r = obj.get_editor_property('relative_rotation')
        s = obj.get_editor_property('relative_scale3d')
        attachments[entry['variable']] = {'location_cm': [v.x, v.y, v.z],
                                          'rotation_degrees': {'pitch': r.pitch, 'yaw': r.yaw, 'roll': r.roll},
                                          'scale': [s.x, s.y, s.z], 'parent_variable': entry['parent_variable']}
    components.append(entry)
report = {'success': True, 'project': str(root), 'pawn': bp.get_path_name(),
          'attachments': attachments, 'components': components, 'saved_assets': False}
(root / 'native_attachment_inspection.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
unreal.log('EPIC_XR_TEMPLATE_INSPECTION ' + json.dumps(report))
