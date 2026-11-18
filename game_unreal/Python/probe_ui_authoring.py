"""Read native UMG authoring reflection without writing a runtime UI asset."""
import json
import traceback
import unreal

result = {}
for name in [
    'WidgetBlueprintFactory', 'WidgetBlueprint', 'WidgetTree',
    'WidgetBlueprintEditorLibrary', 'WidgetTreeEditingLibrary',
    'WidgetBlueprintLibrary', 'UserWidget', 'CanvasPanel', 'CanvasPanelSlot',
    'Overlay', 'VerticalBox', 'HorizontalBox', 'Border', 'TextBlock', 'Button',
    'SizeBox', 'ScrollBox', 'SlateFontInfo', 'BlueprintEditorLibrary',
    'BlueprintGraphEditor', 'BlueprintGraphPinLibrary',
]:
    cls = getattr(unreal, name, None)
    result[name] = {'available': bool(cls)}
    if cls:
        result[name]['members'] = [member for member in dir(cls) if not member.startswith('_')]

for cls_name, methods in {
    'WidgetBlueprintFactory': ['factory_create_new', 'create_new'],
    'CanvasPanel': ['add_child_to_canvas'],
    'Border': ['set_content', 'set_brush_color', 'set_padding'],
    'TextBlock': ['set_text', 'set_font', 'set_color_and_opacity', 'set_auto_wrap_text'],
    'BlueprintEditorLibrary': ['compile_blueprint', 'add_member_variable', 'add_event_dispatcher'],
    'BlueprintGraphEditor': ['add_component_bound_event_node', 'add_call_function_node', 'add_event_node', 'add_variable_get_node', 'add_variable_set_node'],
}.items():
    cls = getattr(unreal, cls_name, None)
    for method_name in methods:
        method = getattr(cls, method_name, None) if cls else None
        result[cls_name + '.' + method_name] = method.__doc__ if method else None

# Construct only native transient widgets, never EditorUtility widgets or saved assets.
try:
    tree = unreal.new_object(unreal.WidgetTree, outer=unreal.get_transient_package(), name='TemporaryAuthoringProbeTree')
    canvas = unreal.new_object(unreal.CanvasPanel, outer=tree, name='TemporaryProbeRoot')
    tree.set_editor_property('root_widget', canvas)
    label = unreal.new_object(unreal.TextBlock, outer=tree, name='TemporaryProbeText')
    label.set_text('Readable runtime UMG text')
    label.set_auto_wrap_text(True)
    slot = canvas.add_child_to_canvas(label)
    slot.set_position(unreal.Vector2D(30, 30))
    slot.set_size(unreal.Vector2D(520, 80))
    button = unreal.new_object(unreal.Button, outer=tree, name='TemporaryProbeButton')
    canvas.add_child_to_canvas(button)
    result['transient_tree_proof'] = {
        'root_type': tree.get_editor_property('root_widget').get_class().get_path_name(),
        'root_children': canvas.get_children_count(),
        'text': str(label.get_text()),
        'button_has_clicked_delegate': hasattr(button, 'on_clicked'),
    }
except Exception:
    result['transient_tree_error'] = traceback.format_exc()

print('UI_AUTHORING_PROBE_BEGIN')
print(json.dumps(result, default=str, indent=2))
print('UI_AUTHORING_PROBE_END')
