"""Validated helpers for Unreal 5.8 native Blueprint graph authoring.

This module is editor-time only. Generated Blueprints contain native K2 nodes,
so gameplay does not depend on Python. Existing assets are reused by default.
"""
import json
import unreal

L = unreal.BlueprintEditorLibrary
P = unreal.BlueprintGraphPinLibrary
E = unreal.BlueprintGraphEditor
CREATED = []
UNSET = object()


class GraphError(RuntimeError):
    pass


def class_(value):
    """Resolve a native Python class, Blueprint, UClass or class object path."""
    if isinstance(value, str):
        result = unreal.load_class(None, value)
        if result is None:
            asset = unreal.load_asset(value)
            result = L.generated_class(asset) if isinstance(asset, unreal.Blueprint) else asset
        if result is None:
            raise GraphError('Cannot load class: '+value)
        return result
    if isinstance(value, unreal.Blueprint):
        result = L.generated_class(value)
        if result is None:
            raise GraphError('Blueprint must be compiled before resolving its class: '+value.get_path_name())
        return result
    return value


def class_path(value):
    value = class_(value)
    if hasattr(value, 'static_class') and isinstance(value, type):
        value = value.static_class()
    return value.get_path_name()


def type_(name):
    aliases = {'float':'real','double':'real','boolean':'bool','integer':'int','str':'string'}
    name = aliases.get(name, name)
    if name not in ['int','int64','byte','bool','real','name','string','text']:
        raise GraphError('Unknown primitive Blueprint type: '+str(name))
    return L.get_basic_type_by_name(name)


def object_type(cls):
    return L.get_object_reference_type(class_(cls))


def class_type(cls):
    return L.get_class_reference_type(class_(cls))


def struct_type(value):
    aliases = {'vector':'/Script/CoreUObject.Vector','rotator':'/Script/CoreUObject.Rotator',
               'transform':'/Script/CoreUObject.Transform','color':'/Script/CoreUObject.LinearColor',
               'linear_color':'/Script/CoreUObject.LinearColor','hit':'/Script/Engine.HitResult'}
    if isinstance(value, str):
        value = unreal.load_object(None, aliases.get(value,value))
    elif isinstance(value, type) and hasattr(value,'static_struct'):
        value = value.static_struct()
    if value is None:
        raise GraphError('Missing script struct')
    return L.get_struct_type(value)


def array_type(contained):
    return L.get_array_type(type_(contained) if isinstance(contained,str) else contained)


def set_type(contained):
    return L.get_set_type(type_(contained) if isinstance(contained,str) else contained)


def map_type(key, value):
    return L.get_map_type(type_(key) if isinstance(key,str) else key,
                          type_(value) if isinstance(value,str) else value)


def literal(value):
    if value is None:
        return 'None'
    if isinstance(value,bool):
        return 'true' if value else 'false'
    if isinstance(value,unreal.Vector):
        return '(X=%s,Y=%s,Z=%s)'%(value.x,value.y,value.z)
    if isinstance(value,unreal.Rotator):
        return '%s,%s,%s'%(value.pitch,value.yaw,value.roll)
    if isinstance(value,unreal.LinearColor):
        return '(R=%s,G=%s,B=%s,A=%s)'%(value.r,value.g,value.b,value.a)
    if isinstance(value,type) and hasattr(value,'static_class'):
        return value.static_class().get_path_name()
    if isinstance(value,unreal.Object):
        return value.get_path_name()
    if isinstance(value,(list,tuple)):
        return '('+','.join(json.dumps(v,ensure_ascii=False) if isinstance(v,str) else literal(v) for v in value)+')'
    return str(value)


def blueprint(path, parent=unreal.Actor):
    bp = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    if bp is not None:
        if not isinstance(bp,unreal.Blueprint):
            raise GraphError('Existing asset is not a Blueprint: '+path)
    else:
        bp = L.create_blueprint_asset_with_parent(path,class_(parent))
        if bp is None:
            raise GraphError('Cannot create Blueprint: '+path)
    if bp not in CREATED:
        CREATED.append(bp)
    return bp


def member(bp,name,pin_type,default=UNSET,instance_editable=False):
    """Declare only absent variables; existing defaults and references survive."""
    if isinstance(pin_type,str):
        pin_type = type_(pin_type)
    names = [str(n) for n in L.list_member_variable_names(bp,False)]
    if name not in names:
        graph = L.find_event_graph(bp)
        editor = E.get_graph_editor(graph) if graph else E.create_and_edit_function_graph(bp,'_OpeningVariableDeclarations')
        if not editor.add_member_variable(name,pin_type,'' if default is UNSET else literal(default)):
            raise GraphError('Cannot declare '+bp.get_name()+'.'+name)
    if instance_editable:
        L.set_blueprint_variable_instance_editable(bp,name,True)
    return name


def pin_names(node):
    return {'inputs':[str(P.get_pin_name(p)) for p in L.list_input_pins(node)],
            'outputs':[str(P.get_pin_name(p)) for p in L.list_output_pins(node)]}


def _checked(pin, context):
    if pin is None or not P.is_valid(pin):
        raise GraphError('Invalid graph pin: '+context)
    return pin


def pin_in(node,name=None):
    if isinstance(node,unreal.BlueprintGraphPin):
        return _checked(node,'input pin')
    if isinstance(node,tuple):
        return pin_in(node[0],node[1])
    if name is None:
        pin = L.find_execute_pin(node)
    else:
        pin = L.find_input_pin(node,name)
    return _checked(pin,'%s input %s; available=%s'%(node.get_name(),name,pin_names(node)))


def pin_out(node,name=None):
    if isinstance(node,unreal.BlueprintGraphPin):
        return _checked(node,'output pin')
    if isinstance(node,tuple):
        return pin_out(node[0],node[1])
    pin = L.find_output_pin(node,name) if name is not None else L.find_then_pin(node)
    return _checked(pin,'%s output %s; available=%s'%(node.get_name(),name,pin_names(node)))


def value_pin(node,name=None):
    if isinstance(node,unreal.BlueprintGraphPin):
        return _checked(node,'value pin')
    if isinstance(node,tuple):
        return value_pin(node[0],node[1])
    if name is not None:
        return pin_out(node,name)
    pin = L.find_result_pin(node)
    if P.is_valid(pin):
        return pin
    candidates = [p for p in L.list_output_pins(node) if str(P.get_pin_name(p)) not in ['then','else','execute']]
    if len(candidates) == 1:
        return candidates[0]
    raise GraphError('Specify data output for %s: %s'%(node.get_name(),pin_names(node)))


def link(*args):
    """link(output_pin,input_pin), or link(source,'Out',target,'In')."""
    if len(args) == 2:
        a,b = args
        a = _checked(a,'source') if isinstance(a,unreal.BlueprintGraphPin) else value_pin(a)
        b = _checked(b,'target') if isinstance(b,unreal.BlueprintGraphPin) else pin_in(b)
    elif len(args) == 4:
        a,an,b,bn = args
        a,b = pin_out(a,an),pin_in(b,bn)
    else:
        raise TypeError('link takes 2 pins or source, output_name, target, input_name')
    existing = list(P.list_connected_pins(a))
    if any(P.is_same_native_pin(p,b) for p in existing):
        return b
    if existing and P.get_pin_direction(a)==unreal.EdGraphPinDirection.EGPD_OUTPUT:
        try:
            is_exec = json.loads(P.get_pin_type_as_json_schema(a)).get('type')=='exec'
        except Exception:
            is_exec = str(P.get_pin_type_display_string(a)).lower()=='exec'
        if is_exec:
            destinations = ['%s.%s'%(P.get_owning_node(p).get_name(),P.get_pin_name(p)) for p in existing]
            raise GraphError('Refusing silent execution rewiring: %s.%s already connects to %s; '
                'use an explicit branch join or sequence instead of reusing a pre-branch flow.'%(
                P.get_owning_node(a).get_name(),P.get_pin_name(a),destinations))
    if not P.try_create_connection(a,b):
        raise GraphError('Cannot link %s.%s (%s) -> %s.%s (%s)'%(
            P.get_owning_node(a).get_name(),P.get_pin_name(a),P.get_pin_type_display_string(a),
            P.get_owning_node(b).get_name(),P.get_pin_name(b),P.get_pin_type_display_string(b)))
    return b


def default(node,name,value=UNSET):
    if isinstance(node,unreal.BlueprintGraphPin):
        pin,value = node,name
    else:
        pin = pin_in(node,name)
    _checked(pin,'literal target')
    if not P.set_pin_value(pin,literal(value)):
        raise GraphError('Invalid literal %r for %s.%s'%(value,P.get_owning_node(pin).get_name(),P.get_pin_name(pin)))
    return node


def chain(*nodes):
    for a,b in zip(nodes,nodes[1:]):
        link(pin_out(a),pin_in(b))
    return nodes[-1] if nodes else None


class Graph:
    def __init__(self,bp,editor):
        self.bp,self.editor = bp,editor
        self.entry = editor.find_graph_entry_pin()
        self.entry_node = P.get_owning_node(self.entry) if P.is_valid(self.entry) else None
        self.result = None
        self._index = 0

    def _node(self,node,label):
        if node is None:
            raise GraphError('Cannot create '+label+' in '+self.editor.get_graph().get_path_name())
        self._index += 1
        L.set_node_pos(node,unreal.IntPoint(200+(self._index%7)*290,(self._index//7)*240))
        return node

    def input(self,name):
        if self.entry_node is None:
            raise GraphError('Not a function graph')
        return pin_out(self.entry_node,name)

    def output(self,name,value=UNSET):
        if self.result is None:
            raise GraphError('Graph has no result node')
        if value is not UNSET:
            if isinstance(value,unreal.BlueprintGraphPin):
                link(value,pin_in(self.result,name))
            else:
                default(self.result,name,value)
        return pin_in(self.result,name)

    def call(self,function_path,defaults=None,**kwargs):
        node = self._node(self.editor.add_call_function_node(function_path),function_path)
        for name,value in dict(defaults or {},**kwargs).items():
            default(node,name,value)
        return node

    def custom_call(self,name,class_path=None,owner=None,defaults=None):
        path = name if class_path is None else globals()['class_path'](class_path)+':'+name
        node = self.call(path,defaults)
        if owner is not None:
            link(value_pin(owner),pin_in(node,'self'))
        return node

    def get(self,name,owner=None,class_path=''):
        node = self._node(self.editor.add_get_member_variable_node(name,class_path),'get '+name)
        if owner is not None:
            link(value_pin(owner),pin_in(node,'self'))
        return node

    def set(self,name,value=UNSET,owner=None,class_path=''):
        node = self._node(self.editor.add_set_member_variable_node(name,class_path),'set '+name)
        if owner is not None:
            link(value_pin(owner),pin_in(node,'self'))
        if value is not UNSET:
            link(value,pin_in(node,name)) if isinstance(value,unreal.BlueprintGraphPin) else default(node,name,value)
        return node

    def branch(self,condition=UNSET):
        node = self._node(self.editor.add_branch_node(),'branch')
        if condition is not UNSET:
            link(condition,pin_in(node,'Condition')) if isinstance(condition,unreal.BlueprintGraphPin) else default(node,'Condition',condition)
        return node

    def event(self,name):
        node = self.editor.find_event_node(name)
        return self._node(node if node else L.add_event_override(self.bp,name,unreal.IntPoint(0,0)),'event '+name)

    def custom_event(self,name):
        return self._node(self.editor.add_custom_event_node(name),'custom event '+name)

    def node(self,name,context_pins=None,declaring_class=None):
        return self._node(self.editor.create_node_from_name(name,unreal.Vector2D(200,200),list(context_pins or []),class_(declaring_class) if declaring_class else None),name)

    def available(self,contains=None,context_pins=None):
        names = list(self.editor.list_available_nodes(list(context_pins or [])))
        return [n for n in names if contains.lower() in n.lower()] if contains else names

    def cast(self,cls,object_pin):
        """Spawn a native dynamic-cast node using the actual action database name."""
        wanted = class_path(cls).split('.')[-1].removesuffix('_C').replace('_','').lower()
        choices = self.available('CastTo',[value_pin(object_pin)])
        matching = [n for n in choices if n.rsplit('|',1)[-1].replace('_','').lower() == 'castto'+wanted]
        if len(matching) == 1:
            node = self.node(matching[0])
        else:
            # New, unsaved Blueprint classes are not necessarily present in the
            # action database yet. Create an existing native cast, then use the
            # supported retarget API to reconstruct it for the requested class.
            all_casts = self.available('CastTo')
            preferred = [('CastToLocalPlayerSaveGame',unreal.LocalPlayerSaveGame),('CastToHUD',unreal.HUD),
                         ('CastToActor',unreal.Actor),('CastToPlayerController',unreal.PlayerController)]
            fallback = next(((n,old) for suffix,old in preferred for n in all_casts if n.rsplit('|',1)[-1]==suffix),None)
            if fallback is None:
                raise GraphError('No native cast template is available for '+wanted)
            template,old_class = fallback
            node = self.node(template)
            if not self.editor.retarget_node_class(node,old_class,class_(cls)):
                raise GraphError('Cannot retarget native dynamic cast to '+class_path(cls))
        link(value_pin(object_pin),pin_in(node,'Object'))
        return node

    def cast_value(self,node):
        pin = next((p for p in L.list_output_pins(node) if str(P.get_pin_name(p)).startswith('As')),None)
        return _checked(pin,'dynamic-cast result')

    def class_literal(self,node,name,cls):
        return default(node,name,class_path(cls))

    def finish(self,save=False):
        return compile_bp(self.bp,save=save)

    link = staticmethod(link)
    default = staticmethod(default)
    chain = staticmethod(chain)
    inp = staticmethod(pin_in)
    out = staticmethod(value_pin)
    exec_out = staticmethod(pin_out)


def function(bp,name,inputs=None,outputs=None,pure=False,reset=True):
    existing = L.find_graph(bp,name)
    if existing and reset:
        L.remove_function_graph(bp,name)
        existing = None
    editor = E.get_graph_editor(existing) if existing else E.create_and_edit_function_graph(bp,name)
    if editor is None:
        raise GraphError('Cannot edit function '+name)
    graph = Graph(bp,editor)
    if not existing:
        for param,kind in (inputs or {}).items():
            editor.add_graph_input_parameter(param,type_(kind) if isinstance(kind,str) else kind)
        for param,kind in (outputs or {}).items():
            graph.result = editor.add_graph_output_parameter(param,type_(kind) if isinstance(kind,str) else kind)
    else:
        graph.result = next((n for n in editor.list_all_nodes() if n.get_class().get_name()=='K2Node_FunctionResult'),None)
    editor.set_is_pure_function(pure)
    editor.set_function_is_public()
    return graph


def events(bp):
    graph = L.find_event_graph(bp)
    if graph is None:
        raise GraphError('Blueprint has no event graph: '+bp.get_path_name())
    return Graph(bp,E.get_graph_editor(graph))


def compile_bp(bp,save=False,raise_on_error=True):
    compiled = L.compile_blueprint(bp)
    errors,warnings = [],[]
    for graph in L.list_graphs(bp):
        editor = E.get_graph_editor(graph)
        for kind,target in [(editor.list_nodes_with_errors,errors),(editor.list_nodes_with_warnings,warnings)]:
            for node in kind():
                try: message = node.get_editor_property('error_msg')
                except Exception: message = ''
                target.append({'graph':graph.get_name(),'node':node.get_name(),'title':str(L.get_node_title(node)),'message':str(message)})
    report = {'asset':bp.get_path_name(),'compiled':bool(compiled),'errors':errors,'warnings':warnings}
    if compiled and not errors and save:
        if not unreal.EditorAssetLibrary.save_loaded_asset(bp):
            raise GraphError('Cannot save '+bp.get_path_name())
    if (not compiled or errors) and raise_on_error:
        raise GraphError('Blueprint compilation failed:\n'+json.dumps(report,indent=2))
    return report


def compile_all(blueprints=None,save=False,raise_on_error=True):
    reports = [compile_bp(bp,save=save,raise_on_error=False) for bp in (CREATED if blueprints is None else blueprints)]
    if raise_on_error and any(not r['compiled'] or r['errors'] for r in reports):
        raise GraphError('Blueprint compilation failures:\n'+json.dumps(reports,indent=2))
    return reports


# Short aliases for scripts that favor functional graph construction.
bp = blueprint
obj_type = object_type
native_call = Graph.call
connect = link
