"""Phase-two identity persistence for the installed v0.2 first pass (root writer queue only).

The supporting-cast pass (integrate_supporting_cast.py, hook metadata
'Release.SupportingCastHooks') already installed the C2-M04 register-consent scene with
the real Enna (cast.clerk) and Tavi (cast.dockworker); its v0.2 state lived only in
TrustEventIds markers because the staged guard was still campaign-v2 (56 fields).

This phase requires the actually compiled, verified and staged campaign-v3 guard
(59-field schema; canonical native_save_guard source byte-identical to the activated
plugin) and then, on top of the installed pass:
  * adds the six v0.2 fields to BP_OpeningSave so its closed schema is exactly campaign-v3
    (PublicChronologyObserved, OrderRegisterObserved, MotherJourneyIntention,
    IdentitySceneSeen, IdentityRecordMethod, IdentityCustodianAccepted);
  * SCSaveFields (new): copies the six manager members into SaveRef at the start of the
    existing _SaveCopy, owned under the same hook metadata;
  * SCLoadMarkers (rebuilt in place, same name and callers): the saved fields are the
    authority; the marker records of earlier first-pass saves are still honoured, so an
    explicit earlier agreement is never lost and no consent is manufactured from absence;
  * QuestV2ShowArchivePage (rebuilt in place): the preserved record's first page shows the
    agreed public handling, including the anonymous headcount when nobody asked
    (reviewed test designs 7 and 10 in QUEST_AND_STORY_DESIGN_v02.md section 13).
It places no actors, seeds no consent, changes no other hook topology and launches no
native tool. Run with -QuestIdentityV2Write after tools/StageSaveGuard.ps1 -Stage.
Re-running integrate_supporting_cast.py later resets SCLoadMarkers to markers only;
run this script again afterwards.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import sys
import traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import opening_graph as og
import build_opening_actions as base
import integrate_quest_story_v02 as q
import integrate_supporting_cast as sc
from release_frontend_graph import Flow, reset_function

STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
OUT = ROOT / 'validation' / 'quest_identity_v02' / STAMP
REPORT_PATH = ROOT / 'quest_identity_v02_integration.json'
FIELDS = {'PublicChronologyObserved': ('bool', False), 'OrderRegisterObserved': ('bool', False),
          'MotherJourneyIntention': ('int', 0), 'IdentitySceneSeen': ('bool', False),
          'IdentityRecordMethod': ('int', 0), 'IdentityCustodianAccepted': ('bool', False)}
DECLS = dict(sc.DECLS, SCSaveFields={})
MARK = sc.MARK
GUARD_RELATIVE = Path('YesterdaySaveGuard/Source/YesterdaySaveGuard/Private/YesterdaySaveGuardLibrary.cpp')
EXPECTED_SCHEMA_FIELDS = 59


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guard_schema(text):
    """Field names the staged guard accepts for campaign-v3 (all nested Add() calls of the campaign block)."""
    block = re.search(r'if \(Kind == TEXT\("campaign-v1"\) \|\| Kind == TEXT\("campaign-v2"\) \|\| Kind == TEXT\("campaign-v3"\)\)\s*\{(.*?)\n    \}\n    else if', text, re.S)
    require(block, 'Staged guard source has no campaign-v1/v2/v3 schema block')
    names = {}
    for group, kind in re.findall(r'Add\(TEXT\("([^"]+)"\), \'([BISRA])\'\);', block.group(1)):
        for name in group.split(','):
            require(name not in names, 'Duplicate guard schema field ' + name)
            names[name] = kind
    return names


def field(flow, name):
    return flow.var(name, flow.var('SaveRef'), base.SAVE_CLASS)


def install(bp, save):
    for name, (kind, default) in FIELDS.items():
        og.member(save, name, kind, default)
        og.member(bp, name, kind, default)          # already declared by the first pass; idempotent
    og.compile_bp(save)
    reset_function(bp, 'SCSaveFields', {})
    og.compile_bp(bp)

    # Saved fields: manager -> SaveRef before the original _SaveCopy body copies the rest.
    f = Flow(reset_function(bp, 'SCSaveFields'))
    for name in FIELDS:
        f.set(name, f.var(name), f.var('SaveRef'), base.SAVE_CLASS)

    def save_entry(g, entry):
        flow = Flow(g, entry)
        flow.own('SCSaveFields')
        return flow
    q.owned_entry(bp, '_SaveCopy', save_entry)

    # Load: fields are authoritative; earlier marker-only records are honoured, never invented.
    f = Flow(reset_function(bp, 'SCLoadMarkers'))
    saved = f.var('TrustEventIds', f.var('SaveRef'), base.SAVE_CLASS)
    f.set('PublicChronologyObserved', f.or_(field(f, 'PublicChronologyObserved'), sc.has(f, saved, MARK['chronology'])))
    f.set('OrderRegisterObserved', f.or_(field(f, 'OrderRegisterObserved'), sc.has(f, saved, MARK['register'])))
    f.set('IdentitySceneSeen', f.or_(field(f, 'IdentitySceneSeen'), sc.has(f, saved, MARK['identity_seen'])))
    f.set('MotherJourneyIntention', field(f, 'MotherJourneyIntention'))
    f.set('IdentityRecordMethod', field(f, 'IdentityRecordMethod'))
    for member, prefix in [('MotherJourneyIntention', MARK['intent']), ('IdentityRecordMethod', MARK['identity'])]:
        for value in [1, 2, 3]:
            yes, no = f.branch(f.and_(f.eq(f.var(member), 0), sc.has(f, saved, prefix + str(value))))
            yes.set(member, value)
            f = q.merge(yes, no)
    f.set('IdentityCustodianAccepted', f.or_(field(f, 'IdentityCustodianAccepted'), f.eq(f.var('IdentityRecordMethod'), 2)))

    # Preserved record, page 1: the agreed handling is part of the record itself.
    f = Flow(reset_function(bp, 'QuestV2ShowArchivePage'))
    clinic, harbor = f.branch(f.eq(f.var('StormCover'), 1))
    for dest, route, scene in [(clinic, '1', 'C2_08A'), (harbor, '2', 'C2_08B')]:
        original, more = dest.branch(dest.eq(dest.var('QuestV2ArchivePage'), 0))
        original.panel(2, 'The preserved record — 1 / 3', sc.ORIGINAL['scenes'][scene]['documents']['caption'],
                       'E  Continue    2  Inspect the dated entry    Esc  Pause')
        sc.each_method(original, lambda fl, value: fl.set('PanelText', fl.text(fl.var('PanelText'),
                       '\n\n' + base.wrap(sc.IDENT['archive'][str(value)]))))
        dated, comparison = more.branch(more.eq(more.var('QuestV2ArchivePage'), 1))
        dated.panel(2, 'Order V-17 — 2 / 3', sc.DATA['registers'][route], 'E  Compare the public account    Esc  Pause')
        comparison.panel(2, 'Order V-17 — 3 / 3', sc.DATA['public_chronology'] + '\n\n' + sc.DATA['comparison'],
                         'E  Continue / Close    Esc  Pause')
        comparison.set('OrderRegisterObserved', True)
        sc.mark(comparison, MARK['register'])
        comparison.own('SaveProgress')
    for node, pin, value in base.MATH_LITERALS:
        og.default(node, pin, value)


def main():
    report = {'success': False, 'run': STAMP, 'revision': sc.IDENT['revision'], 'runtime': 'Native Blueprints',
              'phase': 'two: campaign-v3 saved fields on top of the installed supporting-cast first pass',
              'saved_fields': list(FIELDS), 'identity_methods': ['UNASKED', 'PUBLIC_CONSENT', 'SEALED_CONSENT', 'NO_PERSONAL_ENTRY'],
              'persistence': 'Six BP_OpeningSave fields copied by SCSaveFields in _SaveCopy and read by SCLoadMarkers after '
                             'each LoadProgress SaveRef assignment; TrustEventIds markers remain written and are honoured for '
                             'earlier first-pass saves (field OR marker, never implied consent).',
              'amendments': ['QuestV2ShowArchivePage page 1 now appends the agreed handling exhibit for every method, '
                             'including the anonymous headcount when the conversation was never had'],
              'native_runtime_tested': False, 'private_packet_contents_authored': False,
              'still_unimplemented': ['supporting quest bank', 'no-intervention route', 'later islands'],
              'scope': 'Authoring + compile + saved assets. Not a PIE, packaged or visual approval.'}
    settings = promotion = None
    prior_meta, prior_decls = q.OWNED_META, q.DECLS
    try:
        require(ROOT.parent.name == 'Release_20261026', 'Protected source copies')
        require(unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'QuestIdentityV2Write'), 'Root writer queue required')
        require(not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor(), 'Exit PIE first')
        first_pass = json.loads((ROOT / 'supporting_cast_integration_report.json').read_text(encoding='utf-8'))
        require(first_pass['success'] and first_pass.get('markers') == MARK, 'Actually installed first pass (supporting cast) is required')
        canonical = ROOT.parent / 'native_save_guard' / GUARD_RELATIVE
        activated = ROOT / 'Plugins' / GUARD_RELATIVE
        text = canonical.read_text(encoding='utf-8-sig')
        require('campaign-v3' in text, 'Actual reviewed 59-field guard is not authored')
        require(sha(canonical) == sha(activated), 'Compile/verify/stage the identity guard before expanding saved assets')
        descriptor = json.loads((ROOT / 'Plugins/YesterdaySaveGuard/YesterdaySaveGuard.uplugin').read_text(encoding='utf-8-sig'))
        require(int(descriptor['Version']) >= 4 and descriptor.get('Installed'), 'Activated plugin is not the verified installed identity build')
        require(unreal.load_class(None, '/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary'), 'Native guard module must be loaded')
        schema = guard_schema(text)
        require(len(schema) == EXPECTED_SCHEMA_FIELDS and all(n in schema for n in FIELDS), 'Staged guard schema is not the reviewed 59-field campaign-v3')
        report['guard'] = {'descriptor_version': descriptor['Version'], 'version_name': descriptor.get('VersionName'),
                           'activated_cpp_sha256': sha(activated), 'schema_fields': len(schema)}

        bp_file = ROOT / 'Content/Opening/Blueprints/BP_OpeningActions.uasset'
        save_file = ROOT / 'Content/Opening/Blueprints/BP_OpeningSave.uasset'
        require(sha(bp_file) == first_pass['manager_asset_sha256'], 'Manager changed since the installed first pass; rerun that pass first')
        OUT.mkdir(parents=True, exist_ok=True)
        for file in [bp_file, save_file]:
            shutil.copyfile(sc.long(file), sc.long(OUT / (file.name + '.before')))
        report['backup'] = str(OUT)
        report['before_sha256'] = {str(bp_file): sha(bp_file), str(save_file): sha(save_file)}

        q.OWNED_META, q.DECLS = sc.META, DECLS
        settings = unreal.get_default_object(unreal.load_class(None, '/Script/BlueprintGraph.BlueprintEditorSettings'))
        promotion = settings.get_editor_property('bEnableTypePromotion')
        settings.set_editor_property('bEnableTypePromotion', False)
        bp, save = unreal.load_asset(base.PATH), unreal.load_asset(base.SAVE_PATH)
        require(bp and save, 'Existing story assets required')
        before = q.node_snapshot(bp, protected_only=True)
        import release_mother_integration as shared
        audit = shared.GraphAudit(OUT / 'guard_nodes')
        guard_before = audit.guarded_calls(bp)
        require(len(guard_before) == 13, 'Expected the 13 reviewed native guard calls')
        base.MATH_LITERALS.clear()
        install(bp, save)
        after = q.node_snapshot(bp)
        removed = [path for path in before if path not in after]
        require(not removed, 'Existing native nodes were removed: ' + str(removed[:5]))
        audit.cache.clear()
        guard_after = audit.guarded_calls(bp)
        require(json.dumps(guard_before, sort_keys=True) == json.dumps(guard_after, sort_keys=True),
                'Native guarded save calls (GUIDs, owners or pin links) changed')
        report['save_compile'] = og.compile_bp(save, save=True)
        report['manager_compile'] = og.compile_bp(bp, save=True)
        members = sorted(str(n) for n in og.L.list_member_variable_names(save, False))
        report['save_class_members'] = members
        report['schema_parity'] = {'guard_campaign_v3_fields': sorted(schema), 'save_members_match_guard_schema': sorted(schema) == members}
        require(report['schema_parity']['save_members_match_guard_schema'], 'BP_OpeningSave members do not equal the staged guard campaign-v3 schema')
        hooks = json.loads(unreal.EditorAssetLibrary.get_metadata_tag(bp, sc.META) or '{}')
        report['owned_hook_entry_savecopy'] = hooks.get('entry._SaveCopy')
        report.update(existing_node_count=len(before), original_nodes_preserved=True, native_guard_calls_preserved=13,
                      after_sha256={str(bp_file): sha(bp_file), str(save_file): sha(save_file)},
                      manager_asset_sha256=sha(bp_file), save_asset_sha256=sha(save_file), success=True)
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    finally:
        q.OWNED_META, q.DECLS = prior_meta, prior_decls
        if settings is not None and promotion is not None:
            settings.set_editor_property('bEnableTypePromotion', promotion)
        REPORT_PATH.write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8')
        if report['success']:
            story_path = ROOT / 'quest_story_v02_integration.json'
            story = json.loads(story_path.read_text(encoding='utf-8'))
            story.update(manager_asset_sha256=report['manager_asset_sha256'], saved_fields=list(FIELDS),
                         persistence=report['persistence'],
                         phase_two={'installed_by': 'integrate_quest_identity_v02.py', 'run': STAMP,
                                    'save_asset_sha256': report['save_asset_sha256'], 'guard': report['guard']})
            story_path.write_text(json.dumps(story, indent=2) + '\n', encoding='utf-8')
        unreal.log('QUEST_IDENTITY_V02_INTEGRATE_DONE ' + str(report['success']))


if __name__ == '__main__':
    try:
        main()
    finally:
        unreal.SystemLibrary.quit_editor()
