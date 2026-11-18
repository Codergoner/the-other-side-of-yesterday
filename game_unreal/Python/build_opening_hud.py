"""Build the opening's native runtime Canvas HUD inside the existing project.

This authors a normal AHUD Blueprint, not an Editor Utility widget. Gameplay
state and input ownership remain in BP_OpeningActions; the HUD only reads it.
"""
import json
import unreal

HUD_PATH = '/Game/Opening/Blueprints/BP_OpeningHUD'
LIB = unreal.BlueprintEditorLibrary
PINS = unreal.BlueprintGraphPinLibrary
MATH = '/Script/Engine.KismetMathLibrary.'


def build_hud(manager_class, asset_path=HUD_PATH, save=True):
    """Return a compiled HUD Blueprint reading the supplied manager UClass.

    Required manager fields: Prompt, PanelTitle, PanelText, PanelFooter,
    Objective, Notice (strings), Mode (int), PhotoBack (bool).
    """
    if isinstance(manager_class, str):
        manager_class = unreal.load_class(None, manager_class)
    if manager_class is None:
        raise RuntimeError('Opening HUD requires a compiled gameplay manager class')
    class_path = manager_class.get_path_name()
    bp = unreal.load_asset(asset_path) if unreal.EditorAssetLibrary.does_asset_exist(asset_path) else None
    if bp is None:
        bp = LIB.create_blueprint_asset_with_parent(asset_path, unreal.HUD)
    graph = LIB.find_event_graph(bp)
    if graph is None:
        raise RuntimeError('HUD Blueprint has no event graph')
    editor = unreal.BlueprintGraphEditor.get_graph_editor(graph)
    # UE 5.8 promotes arithmetic node signatures as pins are connected. Such
    # reconstruction can reset unconnected operand defaults, so defer their
    # final authoritative literals until every connection has been authored.
    math_literals = []
    # Rebuild only this newly authored HUD's own graph, never template assets.
    old_nodes = editor.list_all_nodes()
    if old_nodes:
        editor.remove_nodes(old_nodes)
    event = LIB.add_event_override(bp, 'ReceiveDrawHUD', unreal.IntPoint(0, 0))
    if event is None:
        raise RuntimeError('Could not override native HUD ReceiveDrawHUD')

    def inp(node, name):
        pin = LIB.find_input_pin(node, name)
        if not PINS.is_valid(pin):
            raise RuntimeError('Missing input %s on %s' % (name, LIB.get_node_title(node)))
        return pin

    def out(node, name='ReturnValue'):
        pin = LIB.find_output_pin(node, name)
        if not PINS.is_valid(pin):
            raise RuntimeError('Missing output %s on %s' % (name, LIB.get_node_title(node)))
        return pin

    def connect(a, b):
        if not PINS.try_create_connection(a, b):
            raise RuntimeError('HUD connection rejected: %s -> %s' % (PINS.get_pin_name(a), PINS.get_pin_name(b)))

    def value(pin, val):
        if isinstance(val, unreal.BlueprintGraphPin):
            connect(val, pin)
        elif not PINS.set_pin_value(pin, str(val)):
            raise RuntimeError('HUD literal rejected: %s = %s' % (PINS.get_pin_name(pin), val))

    def call(path, **values):
        node = editor.add_call_function_node(path)
        if node is None:
            raise RuntimeError('HUD function unavailable: ' + path)
        for name, val in values.items():
            value(inp(node, name), val)
            if path.startswith(MATH) and not isinstance(val, unreal.BlueprintGraphPin):
                math_literals.append((node, name, val))
        return node

    def op(name, a, b):
        return out(call(MATH + name, A=a, B=b))

    def branch(exec_pin, condition):
        node = editor.add_branch_node()
        connect(exec_pin, LIB.find_execute_pin(node))
        value(inp(node, 'Condition'), condition)
        return out(node, 'then'), out(node, 'else')

    def color(r, g, b, a=1):
        return '(R=%s,G=%s,B=%s,A=%s)' % (r, g, b, a)

    manager = call('/Script/Engine.GameplayStatics.GetActorOfClass', ActorClass=class_path)
    connect(LIB.find_then_pin(event), LIB.find_execute_pin(manager))
    manager_pin = out(manager)
    valid = out(call('/Script/Engine.KismetSystemLibrary.IsValid', Object=manager_pin))
    start, _ = branch(LIB.find_then_pin(manager), valid)
    fields = {}
    for field in ['Prompt', 'PanelTitle', 'PanelText', 'PanelFooter', 'Objective', 'Notice', 'Mode', 'PhotoBack', 'ContextLabel']:
        getter = editor.add_get_member_variable_node(field, class_path)
        if getter is None:
            raise RuntimeError('HUD manager field unavailable: ' + field)
        connect(manager_pin, inp(getter, 'self'))
        fields[field] = out(getter, field)

    sx, sy = out(event, 'SizeX'), out(event, 'SizeY')
    x_cache, y_cache = {}, {}

    def x(fraction):
        if fraction not in x_cache:
            x_cache[fraction] = out(call(MATH + 'Multiply_IntFloat', A=sx, B=fraction))
        return x_cache[fraction]

    def y(fraction):
        if fraction not in y_cache:
            y_cache[fraction] = out(call(MATH + 'Multiply_IntFloat', A=sy, B=fraction))
        return y_cache[fraction]

    # 1600x900 is the reference layout. Scale with width for readable desktop UI.
    base_scale = out(call(MATH + 'Multiply_IntFloat', A=sx, B=1 / 1600))
    ui_scale = out(call(MATH + 'FMax', A=base_scale, B=1.0))

    def scale(n):
        return op('Multiply_DoubleDouble', ui_scale, n)

    def rect(exec_pin, left, top, width, height, tint):
        node = call('/Script/Engine.HUD.DrawRect', RectColor=tint,
                    ScreenX=x(left), ScreenY=y(top), ScreenW=x(width), ScreenH=y(height))
        connect(exec_pin, LIB.find_execute_pin(node))
        return LIB.find_then_pin(node)

    def text(exec_pin, content, left, top, size=1.35, tint=None):
        node = call('/Script/Engine.HUD.DrawText', Text=content,
                    TextColor=tint or color(.94, .93, .88), ScreenX=x(left), ScreenY=y(top),
                    Font='/Engine/EngineFonts/Roboto.Roboto', Scale=scale(size), bScalePosition='false')
        connect(exec_pin, LIB.find_execute_pin(node))
        return LIB.find_then_pin(node)

    # Menu is highest priority. The manager blocks lower-priority actions.
    paused = op('EqualEqual_IntInt', fields['Mode'], 6)
    pause_path, active_path = branch(start, paused)
    pause_path = rect(pause_path, 0, 0, 1, 1, color(.015, .022, .024, .79))

    def panel(exec_pin, compact=False):
        left, width = (.51, .45) if compact else (.15, .70)
        exec_pin = rect(exec_pin, left, .13, width, .73, color(.022, .034, .037, .96))
        exec_pin = rect(exec_pin, left, .13, .004, .73, color(.42, .64, .61))
        exec_pin = text(exec_pin, fields['PanelTitle'], left + .027, .174, 1.9, color(.89, .77, .52))
        body_top = .285 if compact else .265
        if compact:
            side_text = out(call(MATH + 'SelectString', A='PHOTOGRAPH  /  REVERSE', B='PHOTOGRAPH  /  FRONT', bPickA=fields['PhotoBack']))
            exec_pin = text(exec_pin, side_text, left + .027, .233, 1.02, color(.61, .76, .73))
        exec_pin = text(exec_pin, fields['PanelText'], left + .027, body_top, 1.32)
        exec_pin = rect(exec_pin, left + .027, .753, width - .054, .0015, color(.27, .36, .35))
        exec_pin = text(exec_pin, fields['PanelFooter'], left + .027, .783, 1.10, color(.70, .79, .76))
        return exec_pin

    panel(pause_path)

    # A compact discovery objective and one transient notice are the only
    # always-visible informational elements outside the pause menu.
    active_path = rect(active_path, .018, .022, .48, .115, color(.015, .024, .026, .73))
    active_path = text(active_path, fields['ContextLabel'], .031, .035, .90, color(.78, .70, .51))
    active_path = text(active_path, fields['Objective'], .031, .068, 1.06)
    active_path = text(active_path, fields['Notice'], .031, .153, 1.08, color(.94, .80, .54))
    exploring, modal = branch(active_path, op('EqualEqual_IntInt', fields['Mode'], 0))

    # Exactly one contextual prompt, always in the same bottom-center band.
    has_prompt = out(call(MATH + 'Greater_IntInt', A=out(call('/Script/Engine.KismetStringLibrary.Len', S=fields['Prompt'])), B=0))
    prompt_path, no_prompt = branch(exploring, has_prompt)
    prompt_path = rect(prompt_path, .18, .87, .64, .068, color(.015, .024, .026, .88))
    text(prompt_path, fields['Prompt'], .205, .889, 1.32)
    text(no_prompt, 'F1  Controls', .86, .949, .92, color(.72, .77, .75))

    inspection, other_panel = branch(modal, op('EqualEqual_IntInt', fields['Mode'], 1))
    panel(inspection, compact=True)
    # Conversation stays below faces and the skyline; text documents keep the
    # larger reading surface. The character camera remains player-controlled.
    dialogue_path, other_panel = branch(other_panel, op('EqualEqual_IntInt', fields['Mode'], 3))
    dialogue_path = rect(dialogue_path, .10, .59, .80, .36, color(.022, .034, .037, .95))
    dialogue_path = rect(dialogue_path, .10, .59, .003, .36, color(.42, .64, .61))
    dialogue_path = text(dialogue_path, fields['PanelTitle'], .123, .612, 1.18, color(.89, .77, .52))
    dialogue_path = text(dialogue_path, fields['PanelText'], .123, .658, 1.16)
    text(dialogue_path, fields['PanelFooter'], .123, .915, .98, color(.70, .79, .76))
    # Modes 2..5 use a full reading panel. Transition/perspective have their
    # own authored world presentation and receive no accidental document UI.
    ordinary_modal = op('LessEqual_IntInt', fields['Mode'], 5)
    panel_path, _ = branch(other_panel, ordinary_modal)
    panel(panel_path)

    editor.add_comment_to_nodes('Read-only runtime HUD. Gameplay and input priority belong to BP_OpeningActions.', [event, manager], 40)
    # Resolve each pin again by name: earlier proxy pin indices may have been
    # invalidated by type promotion. Never replace a connected operand.
    for _ in range(2):
        for node, name, literal in math_literals:
            pin = inp(node, name)
            if not PINS.list_connected_pins(pin):
                value(pin, literal)
    compiled = LIB.compile_blueprint(bp)
    errors = editor.list_nodes_with_errors()
    if not compiled or errors:
        raise RuntimeError('Opening HUD failed compilation: ' + ', '.join(str(LIB.get_node_title(n)) for n in errors))
    if save:
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
    unreal.log('OPENING_HUD_BUILD ' + json.dumps({'asset':asset_path, 'compiled':bool(compiled), 'nodes':len(editor.list_all_nodes()), 'manager':class_path}))
    return bp


if __name__ == '__main__':
    # A transient compilation proof. It does not save or alter the gameplay HUD.
    mock = LIB.create_blueprint_asset_with_parent('/Temp/BP_OpeningHUDContractProbe', unreal.Actor)
    graph = unreal.BlueprintGraphEditor.create_and_edit_function_graph(mock, 'ContractOnly')
    for name in ['Prompt', 'PanelTitle', 'PanelText', 'PanelFooter', 'Objective', 'Notice']:
        graph.add_member_variable(name, LIB.get_basic_type_by_name('string'), '')
    graph.add_member_variable('Mode', LIB.get_basic_type_by_name('int'), '0')
    graph.add_member_variable('PhotoBack', LIB.get_basic_type_by_name('bool'), 'false')
    assert LIB.compile_blueprint(mock)
    build_hud(LIB.generated_class(mock), '/Temp/BP_OpeningHUDProof', save=False)
