"""Read-only reflection probe; does not modify or save project assets."""
import json
import sys
from pathlib import Path
import unreal
sys.path.insert(0,str(Path(__file__).resolve().parent))

data = {}
for name in ['BlueprintEditorLibrary','BlueprintGraphEditor','BlueprintGraphPinLibrary','BlueprintGraphPin','K2Node_CallFunction','EdGraph','MemberReference']:
    cls = getattr(unreal,name,None)
    data[name] = {'available':cls is not None}
    if cls:
        data[name]['members'] = [member for member in dir(cls) if not member.startswith('_')]
for name in ['get_graph_editor','create_and_edit_function_graph','add_call_function_node','create_node_from_name','add_custom_event_node','add_member_variable','add_graph_input_parameter']:
    cls = getattr(unreal,'BlueprintGraphEditor',None)
    method = getattr(cls,name,None) if cls else None
    data['doc.'+name] = method.__doc__ if method else None
bp = unreal.load_asset('/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter')
if bp:
    data['graphs'] = unreal.BlueprintEditorLibrary.list_graph_names(bp)
    data['members'] = unreal.BlueprintEditorLibrary.list_member_variable_names(bp)
    graph = unreal.BlueprintEditorLibrary.find_event_graph(bp)
    data['event_graph'] = graph.get_path_name() if graph else None
    if graph:
        editor = unreal.BlueprintGraphEditor.get_graph_editor(graph)
        nodes = editor.list_all_nodes()
        data['existing_nodes'] = []
        for node in nodes[:8]:
            pins = unreal.BlueprintEditorLibrary.list_all_pins(node)
            data['existing_nodes'].append({'class':node.get_class().get_path_name(),'title':unreal.BlueprintEditorLibrary.get_node_title(node),'pins':[{'name':str(unreal.BlueprintGraphPinLibrary.get_pin_name(pin)),'direction':str(unreal.BlueprintGraphPinLibrary.get_pin_direction(pin)),'value':unreal.BlueprintGraphPinLibrary.get_pin_value(pin)} for pin in pins]})
        data['available_nodes_first_25'] = editor.list_available_nodes([])[:25]
try:
    # The /Temp package remains unsaved. Existing gameplay assets are untouched.
    lib = unreal.BlueprintEditorLibrary
    pins = unreal.BlueprintGraphPinLibrary
    probe = lib.create_blueprint_asset_with_parent('/Temp/BP_AuthoringFeasibilityProbe',unreal.Actor)
    func = unreal.BlueprintGraphEditor.create_and_edit_function_graph(probe,'ProbeValueAction')
    number_type = lib.get_basic_type_by_name('int')
    assert func.add_member_variable('ProbeValue',number_type,'0')
    lib.compile_blueprint(probe)
    setter = func.add_set_member_variable_node('ProbeValue')
    getter = func.add_get_member_variable_node('ProbeValue')
    result = func.add_graph_output_parameter('Value',number_type)
    assert pins.set_pin_value(lib.find_input_pin(setter,'ProbeValue'),'73')
    assert pins.try_create_connection(func.find_graph_entry_pin(),lib.find_execute_pin(setter))
    assert pins.try_create_connection(lib.find_then_pin(setter),lib.find_execute_pin(result))
    assert pins.try_create_connection(lib.find_output_pin(getter,'ProbeValue'),lib.find_input_pin(result,'Value'))
    compiled = lib.compile_blueprint(probe)
    cdo = unreal.get_default_object(lib.generated_class(probe))
    before = cdo.get_editor_property('ProbeValue')
    returned = cdo.call_method('ProbeValueAction')
    after = cdo.get_editor_property('ProbeValue')
    data['working_proof'] = {'compiled':compiled,'before':before,'returned':returned,'after':after,'graph_nodes':len(func.list_all_nodes()),'saved':False}
    assert compiled and before == 0 and returned == 73 and after == 73
except Exception:
    import traceback
    data['working_proof_error'] = traceback.format_exc()
try:
    import opening_graph as og
    save_bp = og.blueprint('/Temp/BP_AuthoringSave',unreal.SaveGame)
    og.member(save_bp,'Completed',og.type_('bool'),False)
    og.compile_bp(save_bp)
    dsl_bp = og.blueprint('/Temp/BP_AuthoringDSL',unreal.Actor)
    og.member(dsl_bp,'Counter',og.type_('int'),0)
    og.compile_bp(dsl_bp)
    action = og.function(dsl_bp,'CounterAction',outputs={'Result':'int'})
    set_counter = action.set('Counter',37)
    get_counter = action.get('Counter')
    action.link(action.out(get_counter),action.output('Result'))
    action.chain(action.entry,set_counter,action.result)
    accidental_successor = action.set('Counter',99)
    try:
        og.link(action.entry,og.pin_in(accidental_successor))
        data['exec_rewire_guard'] = False
    except og.GraphError as exc:
        data['exec_rewire_guard'] = True
        data['exec_rewire_guard_message'] = str(exc)
    action.editor.remove_nodes([accidental_successor])
    og.compile_bp(dsl_bp)
    actor_cdo = unreal.get_default_object(og.L.generated_class(dsl_bp))
    data['dsl_counter_result'] = actor_cdo.call_method('CounterAction')
    cast_fn = og.function(dsl_bp,'CastSaveAction',inputs={'Loaded':og.object_type(unreal.SaveGame)},outputs={'Saved':og.object_type(save_bp)})
    data['available_save_casts'] = cast_fn.available('AuthoringSave',[cast_fn.input('Loaded')])
    cast = cast_fn.cast(save_bp,cast_fn.input('Loaded'))
    data['dynamic_cast_pins'] = og.pin_names(cast)
    cast_result = next(p for p in og.L.list_output_pins(cast) if str(og.P.get_pin_name(p)).startswith('As'))
    cast_fn.link(cast_result,cast_fn.output('Saved'))
    cast_fn.chain(cast_fn.entry,cast,cast_fn.result)
    og.compile_bp(dsl_bp)
    save_instance = unreal.GameplayStatics.create_save_game_object(og.class_(save_bp))
    actor_cdo = unreal.get_default_object(og.L.generated_class(dsl_bp))
    returned = actor_cdo.call_method('CastSaveAction',args=(save_instance,))
    data['dsl_dynamic_cast_runtime'] = {'returned_class':returned.get_class().get_path_name(),'expected_class':og.class_path(save_bp),'same_instance':returned==save_instance}
    factory = og.function(dsl_bp,'CreateSaveAction',outputs={'Saved':og.object_type(save_bp)})
    create = factory.call('/Script/Engine.GameplayStatics.CreateSaveGameObject')
    factory.class_literal(create,'SaveGameClass',save_bp)
    data['determined_output_type'] = og.P.get_pin_type_display_string(factory.out(create))
    factory.chain(factory.entry,create,factory.result)
    factory.link(factory.out(create),factory.output('Saved'))
    data['dsl_compile_report'] = og.compile_bp(dsl_bp)
    actor_cdo = unreal.get_default_object(og.L.generated_class(dsl_bp))
    created = actor_cdo.call_method('CreateSaveAction')
    data['dsl_class_literal_runtime'] = {'class':created.get_class().get_path_name(),'correct':created.get_class()==save_instance.get_class()}
    data['dsl_success'] = data['dsl_counter_result']==37 and returned==save_instance and data['dsl_class_literal_runtime']['correct']
except Exception:
    import traceback
    data['dsl_error'] = traceback.format_exc()
print('AUTHORING_PROBE_BEGIN')
print(json.dumps(data,default=str,indent=2))
print('AUTHORING_PROBE_END')
