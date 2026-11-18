"""Small native graph helpers; edits only explicitly owned release hooks."""
import json
import unreal
import opening_graph as og
import build_opening_actions as base

MANAGER = base.CLASS
HUD = '/Game/Opening/Blueprints/BP_OpeningHUD.BP_OpeningHUD_C'
MATH, SYS, GS, PC, CTL = base.MATH, base.SYS, base.GS, base.PC, base.CTL
STR = '/Script/Engine.KismetStringLibrary.'
WIDGET = '/Script/UMG.WidgetBlueprintLibrary.'
GUS = '/Script/Engine.GameUserSettings.'


class Flow(base.Flow):
    scope = MANAGER

    def own(self, name, **params):
        return self.call(self.scope + ':' + name, **params)

    def branch(self, condition):
        n = self.g.branch(condition)
        og.link(self.cur, og.pin_in(n))
        return type(self)(self.g, og.pin_out(n, 'then')), type(self)(self.g, og.pin_out(n, 'else'))

    def add(self, a, b):
        return self.data(MATH + 'Add_IntInt', A=a, B=b)

    def text(self, a, b):
        return self.data(STR + 'Concat_StrStr', A=a, B=b)

    def eqs(self, a, b):
        return self.data(STR + 'EqualEqual_StrStr', A=a, B=b)

    def select(self, yes, no, condition):
        return self.data(MATH + 'SelectString', A=yes, B=no, bPickA=condition)


class HUDFlow(Flow):
    scope = HUD

    def manager(self, name):
        return self.var(name, self.var('ReleaseHUDManager'), MANAGER)


def merge(*flows):
    n = flows[0].g.set('ReleaseFlowMarker', 0)
    for f in flows:
        og.link(f.cur, og.pin_in(n))
    return type(flows[0])(flows[0].g, og.pin_out(n))


def reset_function(bp, name, inputs=None, outputs=None):
    existing = og.L.find_graph(bp, name)
    if existing:
        ed = og.E.get_graph_editor(existing)
        ed.remove_nodes([n for n in ed.list_all_nodes() if n.get_class().get_name() not in
                         ['K2Node_FunctionEntry', 'K2Node_FunctionResult']])
    return og.function(bp, name, inputs=inputs, outputs=outputs, reset=False)


def wrap_entry(bp, name, builder, is_event=False):
    """Own only a new entry chain, leaving every original node/GUID intact."""
    g = og.events(bp) if is_event else og.Graph(bp, og.E.get_graph_editor(og.L.find_graph(bp, name)))
    entry = og.pin_out(g.event(name)) if is_event else g.entry
    ed = g.editor
    raw = unreal.EditorAssetLibrary.get_metadata_tag(bp, 'Release.FrontendHooks')
    records = json.loads(raw) if raw else {}
    record = records.get(name)
    if record:
        nodes = {n.get_name(): n for n in ed.list_all_nodes()}
        if record['pass_node'] not in nodes:
            raise RuntimeError('Release hook was manually changed: ' + name)
        original = list(og.P.list_connected_pins(og.pin_out(nodes[record['pass_node']], record['pass_pin'])))
        ed.remove_nodes([nodes[n] for n in record['nodes'] if n in nodes])
    else:
        original = list(og.P.list_connected_pins(entry))
    og.P.break_pin_links(entry)
    before = {n.get_name() for n in ed.list_all_nodes()}
    passthrough = builder(g, entry)
    for destination in original:
        og.link(passthrough.cur, destination)
    new = [n for n in ed.list_all_nodes() if n.get_name() not in before]
    for i, n in enumerate(new):
        og.L.set_node_pos(n, unreal.IntPoint(-5000 + i % 6 * 280, -2400 + i // 6 * 230))
    records[name] = {'nodes': [n.get_name() for n in new],
                     'pass_node': og.P.get_owning_node(passthrough.cur).get_name(),
                     'pass_pin': str(og.P.get_pin_name(passthrough.cur))}
    unreal.EditorAssetLibrary.set_metadata_tag(bp, 'Release.FrontendHooks', json.dumps(records))


def append_save_callback(bp):
    """After the existing SaveSucceeded assignment, persist the profile pointer."""
    g = og.Graph(bp, og.E.get_graph_editor(og.L.find_graph(bp, '_SaveCopy')))
    nodes = g.editor.list_all_nodes()
    if any('releasecommitprofile' in str(og.L.get_node_title(n)).replace(' ', '').lower() for n in nodes):
        return
    matches = [n for n in nodes if str(og.L.get_node_title(n)).replace(' ', '').replace('_', '').lower() == 'setsavesucceeded']
    if len(matches) != 1:
        raise RuntimeError('Expected one existing SaveSucceeded assignment')
    source = og.pin_out(matches[0])
    downstream = list(og.P.list_connected_pins(source))
    og.P.break_pin_links(source)
    callback = g.call(MANAGER + ':ReleaseCommitProfile')
    og.link(source, og.pin_in(callback))
    for pin in downstream:
        og.link(og.pin_out(callback), pin)


def scale_existing_hud(hud):
    """Multiply existing DrawText scales, preserving layout and old graph IDs."""
    g = og.events(hud)
    records = unreal.EditorAssetLibrary.get_metadata_tag(hud, 'Release.TextScalePatched')
    if records == '1':
        return
    nodes = g.editor.list_all_nodes()
    managers = [n for n in nodes if str(og.L.get_node_title(n)).replace(' ', '').lower() == 'getactorofclass']
    if len(managers) != 1:
        raise RuntimeError('Original HUD manager lookup changed')
    manager = og.value_pin(managers[0])
    scale = og.value_pin(g.get('ReleaseTextScale', owner=manager, class_path=MANAGER), 'ReleaseTextScale')
    count = 0
    for node in nodes:
        if str(og.L.get_node_title(node)).replace(' ', '').lower() != 'drawtext':
            continue
        pin = og.pin_in(node, 'Scale')
        original = list(og.P.list_connected_pins(pin))
        if len(original) != 1:
            raise RuntimeError('Original HUD text scale changed')
        og.P.break_pin_links(pin)
        multiply = g.call(MATH + 'Multiply_DoubleDouble')
        og.link(original[0], og.pin_in(multiply, 'A'))
        og.link(scale, og.pin_in(multiply, 'B'))
        og.link(og.value_pin(multiply), pin)
        count += 1
    if count < 5:
        raise RuntimeError('Original HUD text nodes were not found')
    unreal.EditorAssetLibrary.set_metadata_tag(hud, 'Release.TextScalePatched', '1')


def build_menu_hud(hud, manager):
    og.member(hud, 'ReleaseHUDManager', og.object_type(manager))
    og.member(hud, 'ReleaseFlowMarker', 'int', 0)
    signatures = {'ReleaseDrawMenu': {'SizeX': 'int', 'SizeY': 'int'},
                  'ReleaseHitBox': {'BoxName': 'name', 'Activate': 'bool'}}
    for name, params in signatures.items():
        reset_function(hud, name, params)
    og.compile_bp(hud)
    f = HUDFlow(reset_function(hud, 'ReleaseDrawMenu', signatures['ReleaseDrawMenu']))
    found = f.data(GS + 'GetActorOfClass', ActorClass=MANAGER)
    cast = f.g.cast(manager, found)
    og.link(f.cur, og.pin_in(cast))
    f = HUDFlow(f.g, og.pin_out(cast))
    f.set('ReleaseHUDManager', f.g.cast_value(cast))
    sx, sy = f.g.input('SizeX'), f.g.input('SizeY')

    def x(k): return f.data(MATH + 'Multiply_IntFloat', A=sx, B=k)
    def y(k): return f.data(MATH + 'Multiply_IntFloat', A=sy, B=k)
    def color(r, g, b, a=1): return unreal.LinearColor(r, g, b, a)
    def rect(flow, left, top, width, height, tint):
        flow.call('/Script/Engine.HUD.DrawRect', RectColor=tint, ScreenX=x(left), ScreenY=top,
                  ScreenW=x(width), ScreenH=y(height))
    def text(flow, value, left, top, size=1.35, tint=None):
        viewport_scale = flow.data(MATH + 'Multiply_IntFloat', A=sx, B=1 / 1600)
        scale = flow.data(MATH + 'Multiply_DoubleDouble', A=viewport_scale, B=flow.manager('ReleaseTextScale'))
        scale = flow.data(MATH + 'Multiply_DoubleDouble', A=scale, B=size)
        flow.call('/Script/Engine.HUD.DrawText', Text=value, TextColor=tint or color(.94, .93, .88),
                  ScreenX=x(left), ScreenY=top, Font='/Engine/EngineFonts/Roboto.Roboto', Scale=scale, bScalePosition=False)

    rect(f, 0, y(0), 1, 1, color(.008, .015, .02, .87))
    rect(f, .16, y(.08), .68, .85, color(.018, .034, .038, .98))
    text(f, 'THE OTHER SIDE OF YESTERDAY', .205, y(.115), 1.85, color(.88, .76, .49))
    text(f, f.manager('ReleaseMenuTitle'), .205, y(.175), 1.4)
    text(f, f.manager('ReleaseMenuBody'), .205, y(.225), 1.15)
    for index in range(10):
        visible, hidden = f.branch(f.data(MATH + 'Greater_IntInt', A=f.manager('ReleaseMenuCount'), B=index))
        compact = visible.eq(visible.manager('ReleaseMenuCount'), 10)
        row_step = visible.data(MATH + 'SelectFloat', A=.052, B=.062, bPickA=compact)
        row_offset = visible.data(MATH + 'Multiply_DoubleDouble', A=row_step, B=float(index))
        top_fraction = visible.data(MATH + 'Add_DoubleDouble', A=visible.manager('ReleaseMenuTop'), B=row_offset)
        top = visible.data(MATH + 'Multiply_IntFloat', A=sy, B=top_fraction)
        selected = visible.eq(visible.manager('ReleaseMenuSelection'), index)
        tint = visible.data(MATH + 'SelectColor', A=color(.10, .22, .23), B=color(.036, .075, .08), bPickA=selected)
        row_height = visible.data(MATH + 'SelectFloat', A=.045, B=.054, bPickA=compact)
        pixel_height = visible.data(MATH + 'Multiply_IntFloat', A=sy, B=row_height)
        visible.call('/Script/Engine.HUD.DrawRect', RectColor=tint, ScreenX=x(.20), ScreenY=top,
                     ScreenW=x(.60), ScreenH=pixel_height)
        offset = visible.data(MATH + 'Add_DoubleDouble', A=top, B=y(.008))
        label = visible.manager('ReleaseRow' + str(index))
        label = visible.select(visible.text('> ', label), visible.text('  ', label), selected)
        text(visible, label, .22, offset, 1.32)
        position = visible.data(MATH + 'MakeVector2D', X=x(.20), Y=top)
        size = visible.data(MATH + 'MakeVector2D', X=x(.60), Y=pixel_height)
        visible.call('/Script/Engine.HUD.AddHitBox', Position=position, Size=size,
                     InName='ReleaseRow' + str(index), bConsumesInput=True, Priority=100)
        f = merge(visible, hidden)
    text(f, f.manager('ReleaseMenuStatus'), .205, y(.855), 1.02, color(.91, .76, .48))
    text(f, 'Mouse or Up/Down + Enter   |   Esc Back', .205, y(.895), 1.0, color(.69, .78, .75))

    f = HUDFlow(reset_function(hud, 'ReleaseHitBox', signatures['ReleaseHitBox']))
    found = f.data(GS + 'GetActorOfClass', ActorClass=MANAGER)
    cast = f.g.cast(manager, found)
    og.link(f.cur, og.pin_in(cast))
    f = HUDFlow(f.g, og.pin_out(cast))
    owner = f.g.cast_value(cast)
    active, no = f.branch(f.var('ReleaseMenuActive', owner, MANAGER))
    name = active.data(STR + 'Conv_NameToString', InName=active.g.input('BoxName'))
    tail = active
    for index in range(10):
        yes, tail = tail.branch(tail.eqs(name, 'ReleaseRow' + str(index)))
        yes.call(MANAGER + ':ReleaseSelect', **{'self': owner, 'Index': index, 'Activate': yes.g.input('Activate')})
    event_graph = og.events(hud)
    for event_name, activate in [('ReceiveHitBoxClick', True), ('ReceiveHitBoxBeginCursorOver', False)]:
        event = event_graph.event(event_name)
        outgoing = list(og.P.list_connected_pins(og.pin_out(event)))
        if outgoing:
            continue
        call = event_graph.call(HUD + ':ReleaseHitBox', Activate=activate)
        og.link(og.pin_out(event), og.pin_in(call))
        og.link(og.value_pin(event, 'BoxName'), og.pin_in(call, 'BoxName'))

    def draw_hook(g, entry):
        f = HUDFlow(g, entry)
        found = f.data(GS + 'GetActorOfClass', ActorClass=MANAGER)
        cast = f.g.cast(manager, found)
        og.link(f.cur, og.pin_in(cast))
        good = HUDFlow(g, og.pin_out(cast))
        bad = HUDFlow(g, og.pin_out(cast, 'CastFailed'))
        menu, normal = good.branch(good.var('ReleaseMenuActive', good.g.cast_value(cast), MANAGER))
        event = g.editor.find_event_node('ReceiveDrawHUD')
        menu.own('ReleaseDrawMenu', SizeX=og.value_pin(event, 'SizeX'), SizeY=og.value_pin(event, 'SizeY'))
        hint, rest = normal.branch(normal.eq(normal.var('Mode', normal.g.cast_value(cast), MANAGER), 0))
        sx, sy = og.value_pin(event, 'SizeX'), og.value_pin(event, 'SizeY')
        hint.call('/Script/Engine.HUD.DrawText', Text='F10  Main menu', TextColor=unreal.LinearColor(.75, .79, .76, 1),
                  ScreenX=hint.data(MATH + 'Multiply_IntFloat', A=sx, B=.03),
                  ScreenY=hint.data(MATH + 'Multiply_IntFloat', A=sy, B=.956),
                  Font='/Engine/EngineFonts/Roboto.Roboto', Scale=1.0, bScalePosition=False)
        normal = merge(hint, rest)
        return merge(normal, bad)
    wrap_entry(hud, 'ReceiveDrawHUD', draw_hook, is_event=True)
