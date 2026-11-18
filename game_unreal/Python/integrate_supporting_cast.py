"""Place the supporting cast in Verdant_Desktop and install the story v0.2 pass natively.

Run in the editor process with -SupportingCastIntegrate (one Unreal writer at a time).

What it writes (after copying the two assets it edits into validation/):
  * BP_OpeningActions: owned hook chains only (metadata 'Release.SupportingCastHooks'):
      - cast conversations (talk prompt + short lines) for the nine imported roles;
      - story v0.2: public chronology board, V-17 dated record and comparison pages,
        Mother's journey intention and her return callbacks;
      - C2-M04 register-consent scene with the real Enna (harbor clerk) and Tavi.
  * Verdant_Desktop: nine owned SkeletalMeshActors playing their own idle animation,
    tagged for the existing era/interaction system, plus the chronology board.
No SaveGuard/BP_OpeningSave schema change: new observations persist as
AddTrustEvent(<id>, 0) markers in the existing TrustEventIds array (HealerTrust
unchanged) and are read back from the loaded SaveRef. All 13 guarded save calls and
every pre-existing node are checked unchanged before anything is saved.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import shutil
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import opening_graph as og
import build_opening_actions as base
import integrate_quest_story_v02 as q          # proven owned-hook helpers and v0.2 tables
from release_frontend_graph import Flow, reset_function

META = 'Release.SupportingCastHooks'
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
OUT = ROOT / 'validation' / 'supporting_cast_integration' / STAMP
MAP = '/Game/Quest/Maps/Verdant_Desktop'
IMPORT = ROOT / 'supporting_cast_import_report.json'
REPORT = ROOT / 'supporting_cast_integration_report.json'
STORY_REPORT = ROOT / 'quest_story_v02_integration.json'
CAST = json.loads((ROOT / 'ContentData/supporting_cast_v1.json').read_text(encoding='utf-8'))
DATA = q.DATA
ORIGINAL = q.ORIGINAL
IDENT = json.loads((ROOT / 'ContentData/quest_identity_v02.json').read_text(encoding='utf-8'))
ARR = '/Script/Engine.KismetArrayLibrary.'
STR = '/Script/Engine.KismetStringLibrary.'
ACT = base.ACT
MATH = base.MATH
OWNER = 'Release.SupportingCastOwned'

MARK = {'chronology': 'story.v02.public_chronology', 'register': 'story.v02.order_register',
        'intent': 'story.v02.intention.', 'identity_seen': 'story.v02.identity_seen',
        'identity': 'story.v02.identity.'}
MEMBERS = {'PublicChronologyObserved': ('bool', False), 'OrderRegisterObserved': ('bool', False),
           'MotherJourneyIntention': ('int', 0), 'IdentitySceneSeen': ('bool', False),
           'IdentityRecordMethod': ('int', 0), 'IdentityCustodianAccepted': ('bool', False),
           'QuestV2FlowMarker': ('int', 0), 'QuestV2ArchivePage': ('int', 0)}
REFS = ['QuestIdentityClerkActor', 'QuestIdentityWorkerActor']
DECLS = {'SCLoadMarkers': {}, 'SCTalk': {}, 'SCPrompt': {},
         'QuestV2OpenChronology': {}, 'QuestV2AppendJournal': {}, 'QuestV2UpdateChronologyPrompt': {},
         'QuestV2ShowArchivePage': {}, 'QuestV2InspectDatedRecord': {},
         'QuestIdentityOpen': {}, 'QuestIdentityApplyWorld': {}, 'QuestIdentityJournal': {}}
INTENT_NODE = q.INTENT_NODE
INTENT_CHOICES = q.INTENT_CHOICES
ID_SCENE = IDENT['scene']
ID_START = ID_SCENE + '.start'
ID_ROWS = {row['node']: row for row in IDENT['choices']}

# Floor points (cm). Street floor follows z = 1020 - 0.1*y; a downward trace refines it.
# 'face' is the world point the NPC turns toward. Identity positions come from the
# reviewed v0.2 design (clinic / harbor shelter) plus a pre-installation harbor desk.
PLACES = {
    'HarborClerk': {'at': (-215, -790), 'face': (30, -790)},
    'Tavi': {'at': (-205, -690), 'face': (30, -700)},
    'Boatwright': {'at': (235, -985), 'face': (30, -985)},
    'Fisherwoman': {'at': (240, -1330), 'face': (30, -1330)},
    'Carpenter': {'at': (-265, -385), 'face': (30, -385)},
    'Baker': {'at': (-215, 135), 'face': (30, 135)},
    'Archivist': {'at': (-120, 1640), 'face': (0, 1450)},
    'ShrineKeeper': {'at': (540, -1330), 'face': (450, -1400)},
    'LanternKeeper': {'at': (215, 300), 'face': (30, 300)},
}
IDENTITY_POINTS = {
    'desk': [(-215, -790, 30, -790), (-205, -690, 30, -700)],
    'clinic': [(-95, 485, 60, 485), (-80, 655, 60, 655)],
    'harbor': [(205, -555, 0, -555), (205, -705, 0, -705)],
}
NAV_NODES = [(-620, 1240), (-830, 1200), (-300, 1240), (50, 1240), (50, 740), (-40, 580), (50, 400), (30, 0),
             (30, -300), (-240, -200), (-600, -200), (-45, -535), (50, -900), (50, -1400), (450, -1400)]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def long(path):
    value = str(Path(path))
    return Path(value if value.startswith('\\\\?\\') else '\\\\?\\' + value)


def sha(path):
    digest = hashlib.sha256()
    with open(long(path), 'rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def asset_file(package):
    return ROOT / 'Content' / (package.split('.')[0].removeprefix('/Game/') + ('.umap' if package == MAP else '.uasset'))


# ---------------------------------------------------------------- graph helpers
def has(flow, array_pin, marker):
    return flow.data(ARR + 'Array_Contains', TargetArray=array_pin, ItemToFind=marker)


def mark(flow, marker):
    flow.own('AddTrustEvent', EventId=marker, Amount=0)


def talk(flow, node_id, lines, title):
    flow.set('DialogueRoot', CAST['root'])
    flow.set('DialoguePartnerActor', flow.var('Target'))
    q.node_lines(flow, node_id, [tuple(x) for x in lines], title=title)


def each_method(flow, callback):
    for value in [1, 2, 3]:
        yes, flow = flow.branch(flow.eq(flow.var('IdentityRecordMethod'), value))
        callback(yes, value)
    callback(flow, 0)


def after_matching(bp, graph_name, hook_name, predicate, expected, helpers):
    g = q.graph(bp, graph_name)
    found = [n for n in g.editor.list_all_nodes() if predicate(n)]
    require(len(found) == expected, f'Expected {expected} exact {hook_name} boundaries, found {len(found)}')
    def builder(g, entry):
        flow = Flow(g, entry)
        for helper in helpers:
            flow.own(helper)
        return flow
    q.owned_after(bp, hook_name, [(g, og.pin_out(n)) for n in found], builder)


def set_place(flow, ref, point, yaw):
    valid, missing = flow.branch(flow.valid(flow.var(ref)))
    valid.call(ACT + 'K2_SetActorLocation', **{'self': valid.var(ref), 'NewLocation': unreal.Vector(*point),
                                                 'bSweep': False, 'bTeleport': True})
    rotation = valid.data(MATH + 'MakeRotator', Roll=0.0, Pitch=0.0, Yaw=float(yaw))
    valid.call(ACT + 'K2_SetActorRotation', **{'self': valid.var(ref), 'NewRotation': rotation, 'bTeleportPhysics': True})
    return q.merge(valid, missing)


# ---------------------------------------------------------------- native story graphs
def install(bp, identity_yaws):
    for name, (kind, default) in MEMBERS.items():
        og.member(bp, name, kind, default)
    for ref in REFS:
        og.member(bp, ref, og.object_type(unreal.Actor), instance_editable=True)
    for name, args in DECLS.items():
        reset_function(bp, name, args)
    og.compile_bp(bp)

    # Persistence through existing TrustEventIds markers (closed SaveGuard schema unchanged).
    f = Flow(reset_function(bp, 'SCLoadMarkers'))
    saved = f.var('TrustEventIds', f.var('SaveRef'), base.SAVE_CLASS)
    f.set('PublicChronologyObserved', has(f, saved, MARK['chronology']))
    f.set('OrderRegisterObserved', has(f, saved, MARK['register']))
    f.set('IdentitySceneSeen', has(f, saved, MARK['identity_seen']))
    f.set('MotherJourneyIntention', 0)
    f.set('IdentityRecordMethod', 0)
    for value in [1, 2, 3]:
        yes, no = f.branch(has(f, saved, MARK['intent'] + str(value)))
        yes.set('MotherJourneyIntention', value)
        f = q.merge(yes, no)
    for value in [1, 2, 3]:
        yes, no = f.branch(has(f, saved, MARK['identity'] + str(value)))
        yes.set('IdentityRecordMethod', value)
        f = q.merge(yes, no)
    f.set('IdentityCustodianAccepted', f.eq(f.var('IdentityRecordMethod'), 2))
    g = q.graph(bp, 'LoadProgress')
    assignments = [n for n in g.editor.list_all_nodes()
                   if n.get_class().get_name() == 'K2Node_VariableSet' and q.normalized_title(n) == 'setsaveref']
    require(len(assignments) == 2, 'Expected the two original LoadProgress SaveRef assignments')
    def load_after(g, entry):
        flow = Flow(g, entry)
        flow.own('SCLoadMarkers')
        return flow
    q.owned_after(bp, 'load.markers', [(g, og.pin_out(n)) for n in assignments], load_after)

    # ---- public chronology (present) and the dated V-17 record (archive pages)
    f = Flow(reset_function(bp, 'QuestV2OpenChronology'))
    present, past = f.branch(f.eq(f.var('EraIndex'), 0))
    past.notice('There is no public historical chronology on this wall in this era.')
    present.set('DocumentKind', 'chronology')
    present.set('PendingDocumentScene', '')
    present.panel(2, 'Public chronology — Order V-17', DATA['public_chronology'], 'E  Close    Esc  Pause')
    present.set('PublicChronologyObserved', True)
    mark(present, MARK['chronology'])
    present.own('SaveProgress')

    f = Flow(reset_function(bp, 'QuestV2UpdateChronologyPrompt'))
    valid, none = f.branch(f.valid(f.var('Target')))      # no tag query on an empty target
    yes, rest = valid.branch(valid.tag(valid.var('Target'), 'present.chronology'))
    yes.set('Prompt', 'E  Read the public chronology — Order V-17')

    def document_entry(g, entry):
        flow = Flow(g, entry)
        ready = flow.and_(flow.eq(flow.var('EraIndex'), 0),
                          flow.or_(flow.eq(flow.var('StormCover'), 1), flow.eq(flow.var('StormCover'), 2)))
        changed, rest = flow.branch(ready)
        clinic, harbor = changed.branch(changed.eq(changed.var('StormCover'), 1))
        for dest, scene in [(clinic, 'C2_08A'), (harbor, 'C2_08B')]:
            seen, unseen = dest.branch(dest.var('ConsequenceObserved'))
            seen.set('PendingDocumentScene', '')
            unseen.set('PendingDocumentScene', scene)
            dest = q.merge(seen, unseen)
            dest.set('DocumentKind', 'archive_v17')
            dest.set('QuestV2ArchivePage', 0)
            dest.own('QuestV2ShowArchivePage')
        return rest
    q.owned_entry(bp, 'ShowMemorialDocument', document_entry)

    f = Flow(reset_function(bp, 'QuestV2ShowArchivePage'))
    clinic, harbor = f.branch(f.eq(f.var('StormCover'), 1))
    for dest, route, scene in [(clinic, '1', 'C2_08A'), (harbor, '2', 'C2_08B')]:
        original, more = dest.branch(dest.eq(dest.var('QuestV2ArchivePage'), 0))
        original.panel(2, 'The preserved record — 1 / 3', ORIGINAL['scenes'][scene]['documents']['caption'],
                       'E  Continue    2  Inspect the dated entry    Esc  Pause')
        # The register-handling agreement made in the past shapes what this page can show.
        seen, unseen = original.branch(original.var('IdentitySceneSeen'))
        each_method(seen, lambda fl, value: fl.set('PanelText', fl.text(fl.var('PanelText'),
                    '\n\n' + base.wrap(IDENT['archive'][str(value)]))))
        dated, comparison = more.branch(more.eq(more.var('QuestV2ArchivePage'), 1))
        dated.panel(2, 'Order V-17 — 2 / 3', DATA['registers'][route], 'E  Compare the public account    Esc  Pause')
        comparison.panel(2, 'Order V-17 — 3 / 3', DATA['public_chronology'] + '\n\n' + DATA['comparison'],
                         'E  Continue / Close    Esc  Pause')
        comparison.set('OrderRegisterObserved', True)
        mark(comparison, MARK['register'])
        comparison.own('SaveProgress')

    def close_document(g, entry):
        flow = Flow(g, entry)
        next_page = flow.and_(flow.eqs(flow.var('DocumentKind'), 'archive_v17'), flow.eq(flow.var('QuestV2ArchivePage'), 1))
        yes, rest = flow.branch(next_page)
        yes.set('QuestV2ArchivePage', yes.add(yes.var('QuestV2ArchivePage'), 1))
        yes.own('QuestV2ShowArchivePage')
        return rest
    q.owned_entry(bp, 'CloseDocument', close_document)

    f = Flow(reset_function(bp, 'QuestV2InspectDatedRecord'))
    valid = f.and_(f.eq(f.var('Mode'), 2), f.and_(f.eqs(f.var('DocumentKind'), 'archive_v17'),
                                                     f.eq(f.var('QuestV2ArchivePage'), 0)))
    yes, no = f.branch(valid)
    yes.set('QuestV2ArchivePage', 1)
    yes.own('QuestV2ShowArchivePage')

    def date_input(g, entry):
        flow = Flow(g, entry)
        candidate = flow.and_(flow.eq(flow.var('Mode'), 2), flow.and_(flow.eqs(flow.var('DocumentKind'), 'archive_v17'),
                                                                      flow.eq(flow.var('QuestV2ArchivePage'), 0)))
        candidate, rest = flow.branch(candidate)
        pressed, ordinary = candidate.branch(candidate.key('Two'))
        pressed.own('QuestV2InspectDatedRecord')
        return q.merge(rest, ordinary)
    q.owned_entry(bp, 'InputFrame', date_input)

    def pause_entry(g, entry):
        flow = Flow(g, entry)
        resumed = flow.and_(flow.eq(flow.var('Mode'), 6), flow.and_(flow.eq(flow.var('PauseReturnMode'), 2),
                                                                    flow.eqs(flow.var('DocumentKind'), 'chronology')))
        yes, rest = flow.branch(resumed)
        yes.call(base.GS + 'SetGamePaused', bPaused=False)
        yes.own('QuestV2OpenChronology')
        archive_resume = rest.and_(rest.eq(rest.var('Mode'), 6), rest.and_(rest.eq(rest.var('PauseReturnMode'), 2),
                                                                         rest.eqs(rest.var('DocumentKind'), 'archive_v17')))
        yes, rest = rest.branch(archive_resume)
        yes.call(base.GS + 'SetGamePaused', bPaused=False)
        yes.own('QuestV2ShowArchivePage')
        return rest
    q.owned_entry(bp, 'CloseModal', pause_entry)

    # ---- journal
    f = Flow(reset_function(bp, 'QuestV2AppendJournal'))
    observation_page, other = f.branch(f.eq(f.var('JournalPage'), 2))
    seen, unseen = observation_page.branch(observation_page.var('PublicChronologyObserved'))
    seen.set('PanelText', seen.text(seen.var('PanelText'), '\n\n' + base.wrap(DATA['journal']['chronology'])))
    f = q.merge(seen, unseen)
    read, unread = f.branch(f.var('OrderRegisterObserved'))
    clinic, harbor = read.branch(read.eq(read.var('StormCover'), 1))
    for dest, key in [(clinic, 'record_clinic'), (harbor, 'record_harbor')]:
        dest.set('PanelText', dest.text(dest.var('PanelText'), '\n\n' + base.wrap(DATA['journal'][key] + '\n\n' + DATA['journal']['lead'])))
    f = Flow(reset_function(bp, 'QuestIdentityJournal'))
    observed, other = f.branch(f.and_(f.eq(f.var('JournalPage'), 2), f.var('IdentitySceneSeen')))
    each_method(observed, lambda fl, value: fl.set('PanelText', fl.text(fl.var('PanelText'),
                '\n\n' + base.wrap(IDENT['journal'][str(value)]))))
    after_matching(bp, 'RenderJournal', 'journal.append',
                   lambda n: n.get_class().get_name() == 'K2Node_CallFunction' and q.normalized_title(n) == 'setmode'
                   and str(og.P.get_pin_value(og.pin_in(n, 'NewMode'))) == '5', 3,
                   ['QuestV2AppendJournal', 'QuestIdentityJournal'])

    # ---- identity scene with the real Enna and Tavi
    f = Flow(reset_function(bp, 'QuestIdentityApplyWorld'))
    clinic, other = f.branch(f.eq(f.var('StormCover'), 1))
    harbor, desk = other.branch(other.eq(other.var('StormCover'), 2))
    for branch, key in [(clinic, 'clinic'), (harbor, 'harbor'), (desk, 'desk')]:
        for ref, point in zip(REFS, IDENTITY_POINTS[key]):
            branch = set_place(branch, ref, point_location(point), identity_yaws[(ref, key)])
    def world_entry(g, entry):
        flow = Flow(g, entry)
        flow.own('QuestIdentityApplyWorld')
        return flow
    q.owned_entry(bp, 'ApplyWorldState', world_entry)

    f = Flow(reset_function(bp, 'QuestIdentityOpen'))
    available = f.and_(f.eq(f.var('EraIndex'), 1), f.or_(f.eq(f.var('StormCover'), 1), f.eq(f.var('StormCover'), 2)))
    yes, no = f.branch(available)
    no.own('SCTalk')          # before a shelter exists: ordinary conversation at the harbor desk
    yes.set('DialogueRoot', ID_SCENE)
    yes.set('DialoguePartnerActor', yes.var('Target'))
    agreed, new = yes.branch(yes.data(MATH + 'Greater_IntInt', A=yes.var('IdentityRecordMethod'), B=0))
    each_method(agreed, lambda fl, value: fl.own('StartNode', NodeId=ID_SCENE + '.repeat_' + str(value)))
    new.set('IdentitySceneSeen', True)
    mark(new, MARK['identity_seen'])
    new.own('SaveProgress')
    new.own('StartNode', NodeId=ID_START)

    # ---- cast conversations and prompts
    roles = CAST['roles']
    f = Flow(reset_function(bp, 'SCTalk'))
    tail = f
    for role, row in roles.items():
        yes, tail = tail.branch(tail.tag(tail.var('Target'), row['tag']))
        if role == 'Archivist':
            reg, rest = yes.branch(yes.var('OrderRegisterObserved'))
            talk(reg, 'SC.Archivist.register', row['lines_register'], row['title'])
            chron, plain = rest.branch(rest.var('PublicChronologyObserved'))
            talk(chron, 'SC.Archivist.chronology', row['lines_chronology'], row['title'])
            talk(plain, 'SC.Archivist', row['lines'], row['title'])
        else:
            talk(yes, 'SC.' + role, row['lines'], row['title'])

    f = Flow(reset_function(bp, 'SCPrompt'))
    valid, rest = f.branch(f.valid(f.var('Target')))
    tail = valid
    for role, row in roles.items():
        yes, tail = tail.branch(tail.tag(tail.var('Target'), row['tag']))
        if role in ('HarborClerk', 'Tavi'):
            ready = yes.and_(yes.eq(yes.var('EraIndex'), 1), yes.or_(yes.eq(yes.var('StormCover'), 1),
                                                                     yes.eq(yes.var('StormCover'), 2)))
            scene, plain = yes.branch(ready)
            scene.set('Prompt', 'E  Ask about the family-contact register (optional)')
            plain.set('Prompt', row['prompt'])
        else:
            yes.set('Prompt', row['prompt'])

    g = q.graph(bp, 'UpdateStep')
    calls = [n for n in g.editor.list_all_nodes()
             if n.get_class().get_name() == 'K2Node_CallFunction' and q.normalized_title(n) == 'updatetarget']
    require(len(calls) == 1, 'Expected the original per-frame target update')
    def prompt_after(g, entry):
        flow = Flow(g, entry)
        flow.own('QuestV2UpdateChronologyPrompt')
        flow.own('SCPrompt')
        return flow
    q.owned_after(bp, 'prompt.after_target', [(g, og.pin_out(calls[0]))], prompt_after)

    def interact_entry(g, entry):
        flow = Flow(g, entry)
        flow.own('UpdateTarget')
        valid, none = flow.branch(flow.valid(flow.var('Target')))   # tags are only queried on a real target
        chron, rest = valid.branch(valid.tag(valid.var('Target'), 'present.chronology'))
        chron.own('QuestV2OpenChronology')
        ident, rest = rest.branch(rest.or_(rest.tag(rest.var('Target'), 'cast.clerk'),
                                           rest.tag(rest.var('Target'), 'cast.dockworker')))
        ident.own('QuestIdentityOpen')
        cast, rest = rest.branch(rest.tag(rest.var('Target'), 'cast.npc'))
        cast.own('SCTalk')
        return q.merge(rest, none)
    q.owned_entry(bp, 'Interact', interact_entry)

    # ---- dialogue nodes: Mother intention, return callbacks, identity scene
    def start_node(g, entry):
        flow = Flow(g, entry)
        intent, tail = flow.branch(flow.eqs(flow.g.input('NodeId'), INTENT_NODE))
        q.node_lines(intent, INTENT_NODE, [('Mother', 'What are you promising yourself when you go?')],
                     DATA['intentions'], 'A promise before yesterday')
        for node_id, row in INTENT_CHOICES.items():
            yes, tail = tail.branch(tail.eqs(tail.g.input('NodeId'), node_id))
            lines = [('Protagonist', row['label']), ('Mother', row['reply'])]
            if row['value'] == 3:
                lines += [('Protagonist', 'I have to try.'), ('Mother', 'Trying is something you can promise.')]
            q.node_lines(yes, node_id, lines, title='A promise before yesterday')
        final, tail = tail.branch(tail.eqs(tail.g.input('NodeId'), 'C2_09.continuation'))
        known, unknown = final.branch(final.var('OrderRegisterObserved'))
        for evidence_flow, evidence_lines in [(known, DATA['return_observed']), (unknown, DATA['return_unobserved'])]:
            for value in range(1, 4):
                yes, evidence_flow = evidence_flow.branch(evidence_flow.eq(evidence_flow.var('MotherJourneyIntention'), value))
                lines = q.add_lines(q.add_lines(q.add_lines([], DATA['return_common']), evidence_lines),
                                    DATA['return_intentions'][str(value)])
                lines += [(r['speaker'], r['text']) for r in ORIGINAL['nodes']['C2_09.continuation']['lines']]
                q.node_lines(yes, 'C2_09.continuation', lines, title='The lamp is still on')
            lines = q.add_lines(q.add_lines([], DATA['return_common']), evidence_lines)
            lines += [(r['speaker'], r['text']) for r in ORIGINAL['nodes']['C2_09.continuation']['lines']]
            q.node_lines(evidence_flow, 'C2_09.continuation', lines, title='The lamp is still on')
        start, tail = tail.branch(tail.eqs(tail.g.input('NodeId'), ID_START))
        show_identity(start, ID_START, IDENT['start'], IDENT['choices'])
        for node_id, row in ID_ROWS.items():
            yes, tail = tail.branch(tail.eqs(tail.g.input('NodeId'), node_id))
            show_identity(yes, node_id, row['lines'])
        for value in range(4):
            node_id = ID_SCENE + '.repeat_' + str(value)
            yes, tail = tail.branch(tail.eqs(tail.g.input('NodeId'), node_id))
            show_identity(yes, node_id, IDENT['repeat'][str(value)])
        return tail
    q.owned_entry(bp, 'StartNode', start_node)

    def choose(g, entry):
        flow = Flow(g, entry)
        intent_ready = flow.and_(flow.var('DialogueActive'), flow.and_(flow.var('DialogueWaitingChoice'),
                                 flow.eqs(flow.var('DialogueNodeId'), INTENT_NODE)))
        yes, rest = flow.branch(intent_ready)
        for index, row in enumerate(DATA['intentions'], 1):
            chosen, yes = yes.branch(yes.eq(yes.g.input('ChoiceIndex'), index))
            chosen.set('MotherJourneyIntention', row['value'])
            mark(chosen, MARK['intent'] + str(row['value']))
            chosen.own('SaveProgress')
            chosen.own('StartNode', NodeId=f'C1_INTENTION_01.choice_{index}')
        id_ready = rest.and_(rest.var('DialogueActive'), rest.and_(rest.var('DialogueWaitingChoice'),
                             rest.eqs(rest.var('DialogueNodeId'), ID_START)))
        yes, rest = rest.branch(id_ready)
        for index, row in enumerate(IDENT['choices'], 1):
            selected, yes = yes.branch(yes.eq(yes.g.input('ChoiceIndex'), index))
            selected.own('StartNode', NodeId=row['node'])   # advice is not consent; commitment waits for the end
        return rest
    q.owned_entry(bp, 'ChooseDialogue', choose)

    def finish_node(g, entry):
        flow = Flow(g, entry)
        for node_id in INTENT_CHOICES:
            yes, flow = flow.branch(flow.eqs(flow.var('DialogueNodeId'), node_id))
            yes.own('FinishScene')
        for node_id, row in ID_ROWS.items():
            yes, flow = flow.branch(flow.eqs(flow.var('DialogueNodeId'), node_id))
            fresh, committed = yes.branch(yes.eq(yes.var('IdentityRecordMethod'), 0))
            fresh.set('IdentityRecordMethod', row['method'])
            fresh.set('IdentityCustodianAccepted', row['method'] == 2)
            mark(fresh, MARK['identity'] + str(row['method']))
            fresh.own('SaveProgress')
            fresh.own('RefreshUI')
            fresh.own('FinishScene')
            committed.own('FinishScene')
        for value in range(4):
            yes, flow = flow.branch(flow.eqs(flow.var('DialogueNodeId'), ID_SCENE + '.repeat_' + str(value)))
            yes.own('FinishScene')
        cast, flow = flow.branch(flow.data(STR + 'StartsWith', SourceString=flow.var('DialogueNodeId'), InPrefix='SC.'))
        cast.own('FinishScene')
        return flow
    q.owned_entry(bp, 'FinishNode', finish_node)

    def finish_scene(g, entry):
        flow = Flow(g, entry)
        needed = flow.and_(flow.eqs(flow.var('DialogueRoot'), 'C1_08'), flow.eq(flow.var('MotherJourneyIntention'), 0))
        yes, rest = flow.branch(needed)
        yes.own('StartNode', NodeId=INTENT_NODE)
        return rest
    q.owned_entry(bp, 'FinishScene', finish_scene)

    for node, pin, value in base.MATH_LITERALS:
        og.default(node, pin, value)


def show_identity(flow, node_id, lines, choices=()):
    flow.set('DialogueNodeId', node_id)
    flow.set('DialogueActive', True)
    flow.set('DialogueWaitingChoice', False)
    flow.set('LineIndex', 0)
    flow.set('LineElapsed', 0)
    flow.set('DialogueChoiceCount', len(choices))
    for field, values in [('DialogueLines', [base.wrap(s + ': ' + t) for s, t in lines]),
                          ('DialogueSpeakers', [s for s, t in lines]), ('DialogueTexts', [t for s, t in lines])]:
        flow.set(field, flow.data(STR + 'ParseIntoArray', SourceString='|||LINE|||'.join(values),
                                  Delimiter='|||LINE|||', CullEmptyStrings=True))
    flow.set('NodeNext', '')
    flow.set('DialogueTitle', 'The name you leave behind')
    for index in range(3):
        row = choices[index] if index < len(choices) else None
        flow.set('ChoiceLabel' + str(index + 1), base.wrap(row['label'], 62) if row else '')
        flow.set('ChoiceNext' + str(index + 1), row['node'] if row else '')
    flow.own('RenderDialogueLine')


# ---------------------------------------------------------------- level placement
def street_floor(y):
    return 1020.0 - 0.1 * y


def point_location(point):
    x, y = point[0], point[1]
    return (float(x), float(y), FLOORS.get((round(x), round(y)), street_floor(y)))


FLOORS = {}


def trace_floor(world, x, y):
    # The family home's paving and plinth (x <= -200 cm, y 900..1800 cm) stand at 1011; the street
    # east of the plinth follows the formula even south of the gate (2 Nov 2026 fix: the Archivist at
    # (-120, 1640) was authored 1.5 m above the street by the earlier 'y > 1300' rule).
    guess = 1011.0 if (x <= -200 and 900 <= y <= 1800) else street_floor(y)
    result = {'guess': guess, 'z': guess, 'source': 'street formula'}
    try:
        hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, guess + 140), unreal.Vector(x, y, guess - 260),
                                                     unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [],
                                                     unreal.DrawDebugTrace.NONE, True)
        if isinstance(hit, tuple):
            hit = next((h for h in hit if isinstance(h, unreal.HitResult)), None)
        if hit is not None:
            parts = hit.to_tuple()            # BreakHitResult order: 0 blocking, 4 location, 9 actor
            blocking, location, actor = bool(parts[0]), parts[4], parts[9]
            if blocking and location is not None:
                result.update(traced_z=float(location.z), hit_actor=actor.get_actor_label() if actor else None)
                if abs(location.z - guess) <= 45:
                    result.update(z=float(location.z), source='trace')
            else:
                result['trace'] = 'no blocking hit'
    except Exception as error:
        result['trace_error'] = str(error)
    FLOORS[(round(x), round(y))] = result['z']
    return result


FORWARD_NOTES = []
MESH_FORWARD_DEG = None   # measured once from the cast's foot->toe bones; overridable by -SupportingCastForward=<deg>


def forward_yaw_offset(component):
    """Yaw (deg) of the mesh's own forward direction in actor space, from foot->toe bones."""
    if MESH_FORWARD_DEG is not None:
        return MESH_FORWARD_DEG
    try:
        def at(name):
            return component.get_socket_location(name)
        toes, heels = at('ball_l'), at('foot_l')
        dx, dy = float(toes.x - heels.x), float(toes.y - heels.y)
        if math.hypot(dx, dy) < 1.0:
            raise RuntimeError('reference pose bones not evaluated (toe-heel %.3f cm)' % math.hypot(dx, dy))
        actor_yaw = component.get_owner().get_actor_rotation().yaw
        return math.degrees(math.atan2(dy, dx)) - actor_yaw
    except Exception as error:
        FORWARD_NOTES.append(str(error))
        return 90.0  # assumption until a native cardinal capture confirms the facing


def place_cast(world, imports, actors_system):
    manager = next(a for a in actors_system.get_all_level_actors() if a.actor_has_tag('Opening.Manager'))
    existing = {}
    for actor in actors_system.get_all_level_actors():
        for tag in actor.get_editor_property('tags'):
            if str(tag).startswith('cast.') and actor.actor_has_tag(OWNER):
                existing.setdefault(str(tag), []).append(actor)
    placed, yaw_offsets = {}, {}
    for role, row in CAST['roles'].items():
        info = imports[role]
        mesh = unreal.load_asset(info['mesh'])
        anim = unreal.load_asset(info['animation'])
        require(mesh and anim, 'Imported assets missing for ' + role)
        found = existing.get(row['tag'], [])
        require(len(found) <= 1, 'Duplicate owned cast actor ' + row['tag'])
        x, y = PLACES[role]['at']
        floor = trace_floor(world, x, y)
        location = unreal.Vector(x, y, floor['z'])
        actor = found[0] if found else actors_system.spawn_actor_from_class(unreal.SkeletalMeshActor, location, unreal.Rotator())
        require(actor, 'Cannot spawn ' + role)
        actor.set_actor_location(location, False, True)
        actor.set_actor_rotation(unreal.Rotator(pitch=0.0, yaw=0.0, roll=0.0), True)
        component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
        component.set_mobility(unreal.ComponentMobility.MOVABLE)
        component.set_skeletal_mesh_asset(mesh)
        component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        component.override_animation_data(anim, True, True, 0.0, 1.0)   # own looping idle, playing
        component.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
        component.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
        component.set_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY, unreal.CollisionResponseType.ECR_BLOCK)
        component.set_editor_property('cast_shadow', True)
        offset = forward_yaw_offset(component)
        yaw_offsets[role] = offset
        fx, fy = PLACES[role]['face']
        desired = math.degrees(math.atan2(fy - y, fx - x))
        actor.set_actor_rotation(unreal.Rotator(pitch=0.0, yaw=desired - offset, roll=0.0), True)
        era_tag = 'Opening.PastOnly' if row['era'] == 'past' else 'Opening.PresentOnly'
        actor.set_editor_property('tags', [unreal.Name(t) for t in
                                           [row['tag'], 'cast.npc', 'Opening.Interactable', era_tag, OWNER]])
        actor.set_actor_label(info['display_name'] + (' — ' + info['working_name'] if info.get('working_name') else '') + ' (supporting cast)')
        actor.set_folder_path('Opening/Supporting cast')
        actor.set_actor_hidden_in_game(True)       # era presentation decides visibility at runtime
        actor.set_actor_enable_collision(False)
        nearest = min(math.hypot(x - nx, y - ny) for nx, ny in NAV_NODES)
        placed[role] = {'actor': actor, 'location': [x, y, floor['z']], 'yaw': desired - offset, 'floor': floor,
                        'mesh_forward_offset_deg': offset, 'nearest_navigation_node_cm': nearest, 'era': row['era']}
    return manager, placed, yaw_offsets


def place_chronology_board(actors_system, manager):
    existing = [a for a in actors_system.get_all_level_actors() if a.actor_has_tag('present.chronology')]
    require(len(existing) <= 1, 'Duplicate public chronology board')
    if existing:
        board = existing[0]
    else:
        board = actors_system.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(-209, 1575, 1145), unreal.Rotator())
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
        component.set_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY, unreal.CollisionResponseType.ECR_BLOCK)
        board.set_editor_property('tags', [unreal.Name(t) for t in
                                           ['Opening.Interactable', 'Opening.PresentOnly', 'present.chronology', OWNER]])
        board.set_folder_path('Opening/Story v0.2')
    return board


# ---------------------------------------------------------------- main
def main():
    report = {'success': False, 'run': STAMP, 'runtime': 'Native Blueprints',
              'persistence': 'TrustEventIds markers via AddTrustEvent(id, 0); SaveGuard schema unchanged',
              'markers': MARK, 'scope': 'Authoring + compile + saved assets. Not a PIE, packaged or visual approval.'}
    settings = promotion = None
    prior_meta, prior_decls = q.OWNED_META, q.DECLS
    try:
        command = unreal.SystemLibrary.get_command_line()
        require(unreal.SystemLibrary.parse_param(command, 'SupportingCastIntegrate'), 'Explicit -SupportingCastIntegrate required')
        import re
        forced = re.search(r'-SupportingCastForward=(-?[0-9.]+)', command)
        if forced:
            global MESH_FORWARD_DEG
            MESH_FORWARD_DEG = float(forced.group(1))
            report['mesh_forward_source'] = 'command line (native cardinal capture review)'
        report['mesh_forward_deg'] = MESH_FORWARD_DEG
        require(ROOT.parent.name == 'Release_20261026', 'Only the Release_20261026 copy may be written')
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        actors_system = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        require(not levels.is_in_play_in_editor(), 'Exit PIE first')
        imports = json.loads(IMPORT.read_text(encoding='utf-8'))
        require(imports['success'] and all(imports['roles'][r]['ok'] for r in CAST['roles']), 'Successful native cast import required')
        imports = imports['roles']
        bp_path, map_file = base.PATH, asset_file(MAP)
        bp_file = ROOT / 'Content/Opening/Blueprints/BP_OpeningActions.uasset'
        OUT.mkdir(parents=True, exist_ok=True)
        for file in [bp_file, map_file]:
            shutil.copyfile(long(file), long(OUT / (file.name + '.before')))
        report['backup'] = str(OUT)
        report['before_sha256'] = {str(bp_file): sha(bp_file), str(map_file): sha(map_file)}

        q.OWNED_META, q.DECLS = META, DECLS
        settings = unreal.get_default_object(unreal.load_class(None, '/Script/BlueprintGraph.BlueprintEditorSettings'))
        promotion = settings.get_editor_property('bEnableTypePromotion')
        settings.set_editor_property('bEnableTypePromotion', False)

        require(levels.load_level(MAP), 'Cannot load ' + MAP)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        manager, placed, offsets = place_cast(world, imports, actors_system)
        manager_name = manager.get_name()
        identity_yaws = {}
        for key, points in IDENTITY_POINTS.items():
            for ref, role, (x, y, fx, fy) in zip(REFS, ['HarborClerk', 'Tavi'], points):
                trace_floor(world, x, y)
                identity_yaws[(ref, key)] = math.degrees(math.atan2(fy - y, fx - x)) - offsets[role]

        bp = unreal.load_asset(bp_path)
        require(bp, 'Story manager Blueprint missing')
        before = q.node_snapshot(bp, protected_only=True)
        import release_mother_integration as shared     # canonical 13-call guarded save audit (GUIDs + all pin links)
        audit = shared.GraphAudit(OUT / 'guard_nodes')
        guard_before = audit.guarded_calls(bp)
        require(len(guard_before) == 13, 'Expected the 13 reviewed native guard calls')
        base.MATH_LITERALS.clear()
        install(bp, identity_yaws)
        after = q.node_snapshot(bp)
        removed = [path for path in before if path not in after]
        require(not removed, 'Existing native nodes were removed: ' + str(removed[:5]))
        audit.cache.clear()
        guard_after = audit.guarded_calls(bp)
        require(json.dumps(guard_before, sort_keys=True) == json.dumps(guard_after, sort_keys=True),
                'Native guarded save calls (GUIDs, owners or pin links) changed')
        report['guarded_save_calls'] = guard_after
        report['manager_compile'] = og.compile_bp(bp, save=True)
        report.update(existing_node_count=len(before), original_nodes_preserved=True, native_guard_calls_preserved=13,
                      owned_hook_metadata=json.loads(unreal.EditorAssetLibrary.get_metadata_tag(bp, META) or '{}'))

        manager = next(a for a in actors_system.get_all_level_actors()
                       if a.get_name() == manager_name and a.actor_has_tag('Opening.Manager'))
        board = place_chronology_board(actors_system, manager)
        cast_actors = [p['actor'] for p in placed.values()]
        past = list(manager.get_editor_property('PastActors'))
        present = list(manager.get_editor_property('PresentActors'))
        for role, entry in placed.items():
            target = past if entry['era'] == 'past' else present
            if entry['actor'] not in target:
                target.append(entry['actor'])
        if board not in present:
            present.append(board)
        manager.set_editor_property('PastActors', past)
        manager.set_editor_property('PresentActors', present)
        manager.set_editor_property('QuestIdentityClerkActor', placed['HarborClerk']['actor'])
        manager.set_editor_property('QuestIdentityWorkerActor', placed['Tavi']['actor'])
        require(levels.save_current_level(), 'Cannot save ' + MAP)
        report['placements'] = {role: {k: v for k, v in entry.items() if k != 'actor'} | {'actor': entry['actor'].get_path_name()}
                                for role, entry in placed.items()}
        report['identity_points'] = {f'{ref}:{key}': {'point': list(point_location(p)), 'yaw': identity_yaws[(ref, key)]}
                                     for key, points in IDENTITY_POINTS.items() for ref, p in zip(REFS, points)}
        report['chronology_board'] = board.get_path_name()
        report['forward_measurement_notes'] = FORWARD_NOTES[:9]
        report['after_sha256'] = {str(bp_file): sha(bp_file), str(map_file): sha(map_file)}
        report['manager_asset_sha256'] = sha(bp_file)
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    finally:
        q.OWNED_META, q.DECLS = prior_meta, prior_decls
        if settings is not None and promotion is not None:
            settings.set_editor_property('bEnableTypePromotion', promotion)
        REPORT.write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8')
        if report['success']:
            # The read-only additive audit accepts exactly this story pass's one extra key query ('Two').
            STORY_REPORT.write_text(json.dumps({
                'success': True, 'revision': DATA['revision'], 'installed_by': 'integrate_supporting_cast.py',
                'runtime': 'Native Blueprints', 'saved_fields': [], 'persistence': report['persistence'],
                'markers': MARK, 'manager_asset_sha256': report['manager_asset_sha256'],
                'scope': ['V-17 chronology and record', 'Mother journey intention and return callbacks',
                          'C2-M04 register consent scene with Enna and Tavi'],
                'native_playtests': 'not run by this installer'}, indent=2) + '\n', encoding='utf-8')
        unreal.log('SUPPORTING_CAST_INTEGRATE_DONE ' + str(report['success']))


if __name__ == '__main__':
    try:
        main()
    finally:
        unreal.SystemLibrary.quit_editor()
