"""Root-queued, additive native K2 integration for the first story v0.2 pass.

Python is authoring only. BP_OpeningActions remains the only runtime quest
owner. This does not call the original story/front-end builders, replace a
save call, create a parallel runtime, or author later islands/identity quests.
Run after the expanded native SaveGuard has compiled, with
-QuestStoryV2Write. Scene placement additionally needs a full Level Editor.
"""
from pathlib import Path
import copy
import datetime
import hashlib
import json
import re
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import opening_graph as og
import build_opening_actions as base
from release_frontend_graph import Flow, reset_function

DATA = json.loads((ROOT / 'ContentData/quest_story_v02.json').read_text(encoding='utf-8'))
ORIGINAL = json.loads((ROOT / 'ContentData/chapters_1_2_dialogue.json').read_text(encoding='utf-8'))
FIELDS = {'PublicChronologyObserved': ('bool', False),
          'OrderRegisterObserved': ('bool', False),
          'MotherJourneyIntention': ('int', 0)}
OWNED_META = 'Release.QuestStoryV02Hooks'
DECLS = {'QuestV2OpenChronology': {}, 'QuestV2AppendJournal': {},
         'QuestV2LoadFields': {}, 'QuestV2SaveFields': {},
         'QuestV2UpdateChronologyPrompt': {}, 'QuestV2ShowArchivePage': {},
         'QuestV2InspectDatedRecord': {}}
INTENT_NODE = 'C1_INTENTION_01.start'
INTENT_CHOICES = {f'C1_INTENTION_01.choice_{i}': row for i, row in enumerate(DATA['intentions'], 1)}
META_NODES = {INTENT_NODE, *INTENT_CHOICES}
MATH, STR = base.MATH, '/Script/Engine.KismetStringLibrary.'
STAMP = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
OUT = ROOT / 'validation/quest_story_v02' / STAMP


def require(value, message):
    if not value:
        raise RuntimeError(message)


def normalized_title(node):
    return re.sub(r'[\s_]+', '', str(og.L.get_node_title(node))).lower()


def graphs(bp):
    # Public reflected APIs, used by the existing native integration tooling.
    return list(og.L.list_graphs(bp))


def node_snapshot(bp, protected_only=False):
    owned = set()
    if protected_only:
        records = json.loads(unreal.EditorAssetLibrary.get_metadata_tag(bp, OWNED_META) or '{}')
        for entries in records.values():
            for source, record in entries.items():
                graph_prefix = source.rsplit(':', 1)[0].rsplit('.', 1)[0] + '.'
                owned.update(graph_prefix + name for name in record['nodes'])
    return {node.get_path_name(): node for graph in graphs(bp)
            if not protected_only or graph.get_name() not in DECLS
            for node in og.E.get_graph_editor(graph).list_all_nodes()
            if not protected_only or node.get_path_name() not in owned}


def graph(bp, name):
    found = og.L.find_graph(bp, name)
    require(found, 'Required existing graph missing: ' + name)
    return og.Graph(bp, og.E.get_graph_editor(found))


def merge(*flows):
    node = flows[0].g.set('QuestV2FlowMarker', 0)
    for flow in flows:
        og.link(flow.cur, og.pin_in(node))
    return Flow(flows[0].g, og.pin_out(node))


def owned_after(bp, name, sources, builder):
    """Insert owned chains after stable exec outputs; leave their nodes intact.

    Metadata owns only new nodes and remembers the original destinations.
    A second integration removes/replaces only the earlier owned chains.
    External edits to owned passthroughs fail before their links are changed.
    """
    records = json.loads(unreal.EditorAssetLibrary.get_metadata_tag(bp, OWNED_META) or '{}')
    records.setdefault(name, {})
    for g, source in sources:
        source_node = og.P.get_owning_node(source)
        source_pin = str(og.P.get_pin_name(source))
        key = source_node.get_path_name() + ':' + source_pin
        nodes = {n.get_name(): n for n in g.editor.list_all_nodes()}
        old = records[name].get(key)
        if old:
            require(old['pass_node'] in nodes, 'Owned story hook was manually changed: ' + key)
            last = og.pin_out(nodes[old['pass_node']], old['pass_pin'])
            destinations = list(og.P.list_connected_pins(last))
            g.editor.remove_nodes([nodes[n] for n in old['nodes'] if n in nodes])
        else:
            destinations = list(og.P.list_connected_pins(source))
        og.P.break_pin_links(source)
        before = {n.get_name() for n in g.editor.list_all_nodes()}
        flow = builder(g, source)
        for destination in destinations:
            og.link(flow.cur, destination)
        added = [n for n in g.editor.list_all_nodes() if n.get_name() not in before]
        records[name][key] = {'nodes': [n.get_name() for n in added],
                              'pass_node': og.P.get_owning_node(flow.cur).get_name(),
                              'pass_pin': str(og.P.get_pin_name(flow.cur))}
    unreal.EditorAssetLibrary.set_metadata_tag(bp, OWNED_META, json.dumps(records))


def owned_entry(bp, name, builder):
    g = graph(bp, name)
    owned_after(bp, 'entry.' + name, [(g, g.entry)], builder)


def node_lines(flow, node_id, lines, choices=(), title='Conversation'):
    """Use the existing manual dialogue renderer and existing input dispatch."""
    flow.set('DialogueNodeId', node_id)
    flow.set('DialogueActive', True)
    flow.set('DialogueWaitingChoice', False)
    flow.set('LineIndex', 0)
    flow.set('LineElapsed', 0)
    flow.set('DialogueChoiceCount', len(choices))
    for field, values in [('DialogueLines', [base.wrap(s + ': ' + t) for s, t in lines]),
                          ('DialogueSpeakers', [s for s, t in lines]),
                          ('DialogueTexts', [t for s, t in lines])]:
        if base.vpin(values):
            flow.set(field, values)
        else:
            flow.set(field, flow.data(STR + 'ParseIntoArray', SourceString='|||LINE|||'.join(values),
                                      Delimiter='|||LINE|||', CullEmptyStrings=True))
    flow.set('NodeNext', '')
    flow.set('DialogueTitle', title)
    for index in range(3):
        row = choices[index] if index < len(choices) else None
        flow.set('ChoiceLabel' + str(index + 1), base.wrap(row['label'], 62) if row else '')
        flow.set('ChoiceNext' + str(index + 1), f'C1_INTENTION_01.choice_{index+1}' if row else '')
    flow.own('RenderDialogueLine')


def add_lines(lines, values):
    return lines + [(speaker, text) for speaker, text in values]


def install_graphs(bp, save):
    for owner in (bp, save):
        for name, (kind, default) in FIELDS.items():
            og.member(owner, name, kind, default)
    og.member(bp, 'QuestV2FlowMarker', 'int', 0)
    og.member(bp, 'QuestV2ArchivePage', 'int', 0)
    for name, args in DECLS.items():
        reset_function(bp, name, args)
    og.compile_bp(save)
    og.compile_bp(bp)

    flow = Flow(reset_function(bp, 'QuestV2SaveFields'))
    for name in FIELDS:
        flow.set(name, flow.var(name), flow.var('SaveRef'), base.SAVE_CLASS)
    flow = Flow(reset_function(bp, 'QuestV2LoadFields'))
    for name in FIELDS:
        flow.set(name, flow.var(name, flow.var('SaveRef'), base.SAVE_CLASS))

    def save_entry(g, entry):
        flow = Flow(g, entry)
        flow.own('QuestV2SaveFields')
        return flow
    owned_entry(bp, '_SaveCopy', save_entry)

    # Every existing load/new-save assignment gets a read from its actual new
    # SaveRef. Switching slots cannot retain another campaign's v0.2 knowledge.
    g = graph(bp, 'LoadProgress')
    assignments = [n for n in g.editor.list_all_nodes()
                   if n.get_class().get_name() == 'K2Node_VariableSet'
                   and normalized_title(n) == 'setsaveref']
    require(len(assignments) == 2, 'Expected the two original LoadProgress SaveRef assignments')
    def load_after(g, entry):
        flow = Flow(g, entry)
        flow.own('QuestV2LoadFields')
        return flow
    owned_after(bp, 'load.fields', [(g, og.pin_out(n)) for n in assignments], load_after)

    flow = Flow(reset_function(bp, 'QuestV2OpenChronology'))
    present, past = flow.branch(flow.eq(flow.var('EraIndex'), 0))
    past.notice('There is no public historical chronology on this wall in this era.')
    present.set('DocumentKind', 'chronology')
    present.set('PendingDocumentScene', '')
    present.panel(2, 'Public chronology — Order V-17', DATA['public_chronology'], 'E  Close    Esc  Pause')
    # A flag means this panel was actually opened, not inferred from a shelter.
    present.set('PublicChronologyObserved', True)
    present.own('SaveProgress')

    def interact_entry(g, entry):
        flow = Flow(g, entry)
        flow.own('UpdateTarget')
        yes, rest = flow.branch(flow.and_(flow.valid(flow.var('Target')),
                                         flow.tag(flow.var('Target'), 'present.chronology')))
        yes.own('QuestV2OpenChronology')
        return rest
    owned_entry(bp, 'Interact', interact_entry)

    flow = Flow(reset_function(bp, 'QuestV2UpdateChronologyPrompt'))
    yes, rest = flow.branch(flow.and_(flow.valid(flow.var('Target')),
                                      flow.tag(flow.var('Target'), 'present.chronology')))
    yes.set('Prompt', 'E  Read the public chronology — Order V-17')
    def prompt_after(g, entry):
        flow = Flow(g, entry)
        flow.own('QuestV2UpdateChronologyPrompt')
        return flow
    g = graph(bp, 'UpdateStep')
    calls = [n for n in g.editor.list_all_nodes()
             if n.get_class().get_name() == 'K2Node_CallFunction' and normalized_title(n) == 'updatetarget']
    require(len(calls) == 1, 'Expected the original per-frame target update')
    owned_after(bp, 'prompt.after_target', [(g, og.pin_out(calls[0]))], prompt_after)

    def document_entry(g, entry):
        flow = Flow(g, entry)
        ready = flow.and_(flow.eq(flow.var('EraIndex'), 0),
                          flow.or_(flow.eq(flow.var('StormCover'), 1), flow.eq(flow.var('StormCover'), 2)))
        changed, rest = flow.branch(ready)
        clinic, harbor = changed.branch(changed.eq(changed.var('StormCover'), 1))
        for dest, route, scene in [(clinic, '1', 'C2_08A'), (harbor, '2', 'C2_08B')]:
            seen, unseen = dest.branch(dest.var('ConsequenceObserved'))
            seen.set('PendingDocumentScene', '')
            unseen.set('PendingDocumentScene', scene)
            dest = merge(seen, unseen)
            dest.set('DocumentKind', 'memorial')
            dest.set('DocumentKind', 'archive_v17')
            dest.set('QuestV2ArchivePage', 0)
            dest.own('QuestV2ShowArchivePage')
        return rest
    owned_entry(bp, 'ShowMemorialDocument', document_entry)

    flow = Flow(reset_function(bp, 'QuestV2ShowArchivePage'))
    clinic, harbor = flow.branch(flow.eq(flow.var('StormCover'), 1))
    for dest, route, scene in [(clinic, '1', 'C2_08A'), (harbor, '2', 'C2_08B')]:
        original, more = dest.branch(dest.eq(dest.var('QuestV2ArchivePage'), 0))
        original.panel(2, 'The preserved record — 1 / 3', ORIGINAL['scenes'][scene]['documents']['caption'],
                       'E  Continue    2  Inspect the dated entry    Esc  Pause')
        dated, comparison = more.branch(more.eq(more.var('QuestV2ArchivePage'), 1))
        dated.panel(2, 'Order V-17 — 2 / 3', DATA['registers'][route],
                    'E  Compare the public account    Esc  Pause')
        comparison.panel(2, 'Order V-17 — 3 / 3', DATA['public_chronology'] + '\n\n' + DATA['comparison'],
                         'E  Continue / Close    Esc  Pause')
        comparison.set('OrderRegisterObserved', True)
        comparison.own('SaveProgress')

    def close_document(g, entry):
        flow = Flow(g, entry)
        next_page = flow.and_(flow.eqs(flow.var('DocumentKind'), 'archive_v17'),
                              flow.eq(flow.var('QuestV2ArchivePage'), 1))
        yes, rest = flow.branch(next_page)
        yes.set('QuestV2ArchivePage', yes.add(yes.var('QuestV2ArchivePage'), 1))
        yes.own('QuestV2ShowArchivePage')
        return rest
    owned_entry(bp, 'CloseDocument', close_document)

    flow = Flow(reset_function(bp, 'QuestV2InspectDatedRecord'))
    valid = flow.and_(flow.eq(flow.var('Mode'), 2),
                      flow.and_(flow.eqs(flow.var('DocumentKind'), 'archive_v17'),
                                flow.eq(flow.var('QuestV2ArchivePage'), 0)))
    yes, no = flow.branch(valid)
    yes.set('QuestV2ArchivePage', 1)
    yes.own('QuestV2ShowArchivePage')
    def date_input(g, entry):
        flow = Flow(g, entry)
        candidate = flow.and_(flow.eq(flow.var('Mode'), 2),
                              flow.and_(flow.eqs(flow.var('DocumentKind'), 'archive_v17'),
                                        flow.eq(flow.var('QuestV2ArchivePage'), 0)))
        candidate, rest = flow.branch(candidate)
        pressed, ordinary = candidate.branch(candidate.key('Two'))
        pressed.own('QuestV2InspectDatedRecord')
        return merge(rest, ordinary)
    owned_entry(bp, 'InputFrame', date_input)

    def pause_entry(g, entry):
        flow = Flow(g, entry)
        resumed = flow.and_(flow.eq(flow.var('Mode'), 6),
                            flow.and_(flow.eq(flow.var('PauseReturnMode'), 2),
                                      flow.eqs(flow.var('DocumentKind'), 'chronology')))
        yes, rest = flow.branch(resumed)
        yes.call(base.GS + 'SetGamePaused', bPaused=False)
        yes.own('QuestV2OpenChronology')
        archive_resume = rest.and_(rest.eq(rest.var('Mode'), 6),
                                  rest.and_(rest.eq(rest.var('PauseReturnMode'), 2),
                                            rest.eqs(rest.var('DocumentKind'), 'archive_v17')))
        yes, rest = rest.branch(archive_resume)
        yes.call(base.GS + 'SetGamePaused', bPaused=False)
        # Re-render the exact page because the pause screen overwrites PanelText.
        yes.own('QuestV2ShowArchivePage')
        return rest
    owned_entry(bp, 'CloseModal', pause_entry)

    def start_node(g, entry):
        flow = Flow(g, entry)
        intent, tail = flow.branch(flow.eqs(flow.g.input('NodeId'), INTENT_NODE))
        node_lines(intent, INTENT_NODE, [('Mother', 'What are you promising yourself when you go?')],
                   DATA['intentions'], 'A promise before yesterday')
        for node_id, row in INTENT_CHOICES.items():
            yes, tail = tail.branch(tail.eqs(tail.g.input('NodeId'), node_id))
            lines = [('Protagonist', row['label']), ('Mother', row['reply'])]
            if row['value'] == 3:
                lines += [('Protagonist', 'I have to try.'), ('Mother', 'Trying is something you can promise.')]
            node_lines(yes, node_id, lines, title='A promise before yesterday')
        final, tail = tail.branch(tail.eqs(tail.g.input('NodeId'), 'C2_09.continuation'))
        # The old completion node ID and its original ending lines survive.
        # None of the new lines claims a pre-departure sign was inspected.
        known, unknown = final.branch(final.var('OrderRegisterObserved'))
        for evidence_flow, evidence_lines in [(known, DATA['return_observed']),
                                               (unknown, DATA['return_unobserved'])]:
            for value in range(1, 4):
                yes, evidence_flow = evidence_flow.branch(evidence_flow.eq(evidence_flow.var('MotherJourneyIntention'), value))
                lines = add_lines([], DATA['return_common'])
                lines = add_lines(lines, evidence_lines)
                lines = add_lines(lines, DATA['return_intentions'][str(value)])
                lines += [(row['speaker'], row['text']) for row in ORIGINAL['nodes']['C2_09.continuation']['lines']]
                node_lines(yes, 'C2_09.continuation', lines, title='The lamp is still on')
            # Unasked/legacy intent, plus a defensive unknown-enum fallback,
            # makes no promise-specific claim and never stalls the ending.
            lines = add_lines([], DATA['return_common'])
            lines = add_lines(lines, evidence_lines)
            lines += [(row['speaker'], row['text']) for row in ORIGINAL['nodes']['C2_09.continuation']['lines']]
            node_lines(evidence_flow, 'C2_09.continuation', lines, title='The lamp is still on')
        return tail
    owned_entry(bp, 'StartNode', start_node)

    def choose(g, entry):
        flow = Flow(g, entry)
        valid = flow.and_(flow.var('DialogueActive'), flow.and_(flow.var('DialogueWaitingChoice'),
                          flow.eqs(flow.var('DialogueNodeId'), INTENT_NODE)))
        yes, rest = flow.branch(valid)
        # Invalid key indices consume no choice and earn no trust.
        for index, row in enumerate(DATA['intentions'], 1):
            chosen, yes = yes.branch(yes.eq(yes.g.input('ChoiceIndex'), index))
            chosen.set('MotherJourneyIntention', row['value'])
            chosen.own('SaveProgress')
            chosen.own('StartNode', NodeId=f'C1_INTENTION_01.choice_{index}')
        return rest
    owned_entry(bp, 'ChooseDialogue', choose)

    def finish_node(g, entry):
        flow = Flow(g, entry)
        for node_id in INTENT_CHOICES:
            yes, flow = flow.branch(flow.eqs(flow.var('DialogueNodeId'), node_id))
            yes.own('FinishScene')
        return flow
    owned_entry(bp, 'FinishNode', finish_node)

    def finish_scene(g, entry):
        flow = Flow(g, entry)
        needed = flow.and_(flow.eqs(flow.var('DialogueRoot'), 'C1_08'),
                           flow.eq(flow.var('MotherJourneyIntention'), 0))
        yes, rest = flow.branch(needed)
        yes.own('StartNode', NodeId=INTENT_NODE)
        return rest
    owned_entry(bp, 'FinishScene', finish_scene)

    flow = Flow(reset_function(bp, 'QuestV2AppendJournal'))
    observation_page, other = flow.branch(flow.eq(flow.var('JournalPage'), 2))
    seen, unseen = observation_page.branch(observation_page.var('PublicChronologyObserved'))
    seen.set('PanelText', seen.text(seen.var('PanelText'), '\n\n' + base.wrap(DATA['journal']['chronology'])))
    flow = merge(seen, unseen)
    read, unread = flow.branch(flow.var('OrderRegisterObserved'))
    clinic, harbor = read.branch(read.eq(read.var('StormCover'), 1))
    for dest, key in [(clinic, 'record_clinic'), (harbor, 'record_harbor')]:
        extra = '\n\n' + base.wrap(DATA['journal'][key] + '\n\n' + DATA['journal']['lead'])
        dest.set('PanelText', dest.text(dest.var('PanelText'), extra))
    g = graph(bp, 'RenderJournal')
    endings = [n for n in g.editor.list_all_nodes()
               if n.get_class().get_name() == 'K2Node_CallFunction' and normalized_title(n) == 'setmode'
               and str(og.P.get_pin_value(og.pin_in(n, 'NewMode'))) == '5']
    require(len(endings) == 3, 'Expected the original three journal-page display endings')
    def journal_after(g, entry):
        flow = Flow(g, entry)
        flow.own('QuestV2AppendJournal')
        return flow
    owned_after(bp, 'journal.append', [(g, og.pin_out(n)) for n in endings], journal_after)
    # Match the existing builder's reliable type-promotion literal repair.
    for node, pin, value in base.MATH_LITERALS:
        og.default(node, pin, value)
    return bp, save


def place_chronology_boards():
    """Bounded new prop only; preserve every old actor and manager reference."""
    import build_opening_scene as scene
    actor_system = scene.ACTORS
    result = []
    for map_path in ['/Game/Quest/Maps/Verdant_Desktop', '/Game/Quest/Maps/Verdant_VR']:
        # Only the existing current release maps are authored.
        if not unreal.EditorAssetLibrary.does_asset_exist(map_path):
            continue
        require(scene.LEVELS.load_level(map_path), 'Cannot load ' + map_path)
        managers = [a for a in actor_system.get_all_level_actors() if a.actor_has_tag('Opening.Manager')]
        require(len(managers) == 1, 'Expected one authoritative story manager in ' + map_path)
        existing = [a for a in actor_system.get_all_level_actors() if a.actor_has_tag('present.chronology')]
        require(len(existing) <= 1, 'Duplicate public chronology board in ' + map_path)
        if existing:
            board = existing[0]
        else:
            # Adjacent to, rather than replacing, the original memorial. Cuboid
            # is a bounded prop placeholder; the native document is readable.
            board = actor_system.spawn_actor_from_class(unreal.StaticMeshActor,
                     unreal.Vector(-209, 1575, 1145), unreal.Rotator())
            require(board, 'Cannot create chronology board')
            board.set_actor_label('Public chronology — Order V-17')
            board.set_actor_scale3d(unreal.Vector(.10, 1.10, 1.20))
            component = board.get_component_by_class(unreal.StaticMeshComponent)
            component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Cube'))
            material = unreal.load_asset('/Game/Home/Materials/M_HomeLinen')
            if material:
                component.set_material(0, material)
            component.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
            component.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
            component.set_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY,
                                                       unreal.CollisionResponseType.ECR_BLOCK)
            board.set_editor_property('tags', [unreal.Name(t) for t in
                ['Opening.Interactable', 'Opening.PresentOnly', 'present.chronology', 'Release.QuestStoryV02Owned']])
            board.set_folder_path('Opening/Story v0.2')
        present_actors = list(managers[0].get_editor_property('PresentActors'))
        if board not in present_actors:
            managers[0].set_editor_property('PresentActors', present_actors + [board])
        require(scene.LEVELS.save_current_level(), 'Cannot save chronology board in ' + map_path)
        result.append({'map': map_path, 'actor': board.get_path_name(), 'position_cm': [-209, 1575, 1145]})
    require(len(result) == 2, 'Both release play maps are required; no map was silently created')
    return result


def main():
    report = {'success': False, 'revision': DATA['revision'], 'runtime': 'Native Blueprints',
              'source_only_until_this_writer_runs': True, 'native_playtests': 'not run by this installer',
              'saved_fields': list(FIELDS), 'scope': ['V-17 chronology and record', 'Mother journey intention and return callbacks'],
              'not_implemented': ['optional dockworker identity scene', 'supporting quest bank', 'no-intervention route', 'later islands']}
    settings = None
    promotion = None
    try:
        require(ROOT.parent.name == 'Release_20261026', 'Protected original or Quest project')
        require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'QuestStoryV2Write'),
                'Root serialized asset writer queue required: -QuestStoryV2Write')
        require(unreal.load_class(None, '/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary'),
                'The reviewed expanded SaveGuard plugin must be compiled and active')
        guard_relative = Path('YesterdaySaveGuard/Source/YesterdaySaveGuard/Private/YesterdaySaveGuardLibrary.cpp')
        canonical = ROOT.parent / 'native_save_guard' / guard_relative
        activated = ROOT / 'Plugins' / guard_relative
        require(hashlib.sha256(canonical.read_bytes()).digest() == hashlib.sha256(activated.read_bytes()).digest(),
                'Expanded guard source must pass the real compile/verify/stage pipeline before asset integration')
        OUT.mkdir(parents=True, exist_ok=True)
        settings = unreal.get_default_object(unreal.load_class(None, '/Script/BlueprintGraph.BlueprintEditorSettings'))
        promotion = settings.get_editor_property('bEnableTypePromotion')
        settings.set_editor_property('bEnableTypePromotion', False)
        bp, save = unreal.load_asset(base.PATH), unreal.load_asset(base.SAVE_PATH)
        require(bp and save, 'Actual original story assets are required')
        before = node_snapshot(bp, protected_only=True)
        # Public T3D snapshots verify the exact native guard call GUIDs and pins.
        import integrate_release_save_guard as guard_audit
        guard_audit.OUT = OUT / 'guard_nodes'
        guard_audit.EXPORT_CACHE.clear()
        guard_nodes = {path: n for path, n in before.items()
                       if n.get_class().get_name() == 'K2Node_CallFunction'
                       and 'save' in normalized_title(n)
                       and guard_audit.reference(n)[0] == '/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary'}
        guard_before = {path: {'guid': guard_audit.guid(n), 'pins': guard_audit.pins(n)}
                        for path, n in guard_nodes.items()}
        require(len(guard_nodes) == 13, 'Expected the 13 current reviewed native guard calls')
        manager_file = ROOT / 'Content/Opening/Blueprints/BP_OpeningActions.uasset'
        report['baseline_manager_sha256'] = hashlib.sha256(manager_file.read_bytes()).hexdigest()
        base.MATH_LITERALS.clear()
        install_graphs(bp, save)
        after = node_snapshot(bp)
        # Earlier owned v0.2 nodes may be replaced on an idempotent second pass;
        # every pre-v0.2 native node remains the same UObject, not reconstructed.
        owned_raw = unreal.EditorAssetLibrary.get_metadata_tag(bp, OWNED_META)
        report['owned_hook_metadata'] = json.loads(owned_raw or '{}')
        removed = [path for path in before if path not in after]
        require(not removed, 'Existing native nodes were removed: ' + str(removed[:5]))
        guard_audit.EXPORT_CACHE.clear()
        guard_after = {path: {'guid': guard_audit.guid(after[path]), 'pins': guard_audit.pins(after[path])}
                       for path in guard_nodes}
        require(guard_before == guard_after, 'Native guard call GUIDs/pins changed')
        report.update(existing_node_count=len(before), original_nodes_preserved=not removed,
                      native_guard_calls_preserved=len(guard_nodes), native_guard_snapshots=guard_before)
        og.compile_bp(save, save=True)
        report['manager_compile'] = og.compile_bp(bp, save=True)
        if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'QuestStoryV2GraphsOnly'):
            report['chronology_boards'] = place_chronology_boards()
        report['success'] = True
        report['source_only_until_this_writer_runs'] = False
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        if settings is not None and promotion is not None:
            settings.set_editor_property('bEnableTypePromotion', promotion)
        (ROOT / 'quest_story_v02_integration.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')


if __name__ == '__main__':
    main()
