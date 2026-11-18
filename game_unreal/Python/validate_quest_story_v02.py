"""Queued actual native PIE v0.2 acceptance, extending the four real routes.

Run with -ReleaseStoryQA -QuestStoryV2QA and a new short -UserDir. Reuses
the established real menu New Game/Continue, native dialogue/actions, camera
ray selection, committed saves, plan reversal and production NPC walks.
No new quest flags, trust values or inventory are seeded by this adaptation.
It is not packaged, continuous-input, headset or performance evidence.
"""
from pathlib import Path
import ast
import hashlib
import json
import unreal

V2_ROOT = Path(unreal.Paths.project_dir()).resolve()
V2_WRAPPER_FILE = Path(__file__).resolve()
if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'QuestStoryV2QA'):
    raise RuntimeError('Root-queued -QuestStoryV2QA is required')
V2_PARENT_FILE = V2_ROOT / 'Python/validate_release_story.py'
V2_PARENT = V2_PARENT_FILE.read_text(encoding='utf-8')
V2_TREE = ast.parse(V2_PARENT)
V2_ENDING = "exec(compile(source, str(root / 'Python/validate_brief_m2.py'), 'exec'), globals())"
if ast.get_source_segment(V2_PARENT, V2_TREE.body[-1]) != V2_ENDING:
    raise RuntimeError('Review changed established runtime harness before adapting v0.2')
V2_PREFIX, V2_SEPARATOR, V2_SUFFIX = V2_PARENT.rpartition(V2_ENDING)
if not V2_SEPARATOR or V2_SUFFIX.strip():
    raise RuntimeError('Established runtime launch is no longer the checked final statement')
V2_OLD_FILE = globals().get('__file__')
globals()['__file__'] = str(V2_PARENT_FILE)
try:
    # Builds the existing reviewed harness text and unsaved profile fixture;
    # does not register a ticker or begin gameplay until the final exec below.
    exec(compile(V2_PREFIX, str(V2_PARENT_FILE), 'exec'), globals())
finally:
    globals()['__file__'] = V2_OLD_FILE


def v2_replace(old, new):
    global source
    if source.count(old) != 1:
        raise RuntimeError('Changed v0.2 acceptance point: ' + old[:140])
    source = source.replace(old, new)


V2_HELPERS = r'''
V2_DATA=json.loads((ROOT/'ContentData/quest_story_v02.json').read_text(encoding='utf-8'))
FIELDS+=['PublicChronologyObserved','OrderRegisterObserved','MotherJourneyIntention']
for i,case in enumerate(CASES):
    case.update(journey_intent=[1,2,3,1][i],chronology_before=[False,True,True,False][i],
                chronology_after=[False,False,False,True][i],dated_record=[True,True,True,False][i])
for group in ['return_common','return_observed','return_unobserved']:
    SOURCE_LINES.update(tuple(line) for line in V2_DATA[group])
for lines in V2_DATA['return_intentions'].values():SOURCE_LINES.update(tuple(line) for line in lines)
SOURCE_LINES.add(('Mother','What are you promising yourself when you go?'))
for row in V2_DATA['intentions']:
    SOURCE_LINES.add(('Protagonist',row['label']));SOURCE_LINES.add(('Mother',row['reply']))
SOURCE_LINES.update([('Protagonist','I have to try.'),('Mother','Trying is something you can promise.')])

def v2_observe_chronology(case,stage):
    actors=tagged('present.chronology')
    check('Exactly one separately authored public chronology exists',len(actors)==1)
    actor=actors[0]
    check('Chronology has the current era visibility and native query boundary',visible(actor) and collision_enabled(actor))
    old_memorial=(bool(prop('OriginalMemorialRead')),str(prop('PriorTimelineObservation')))
    origin=actor.get_actor_location()
    attempts=[]
    for dx,dy in [(155,0),(165,-60),(165,60),(-155,0)]:
        position(unreal.Vector(origin.x+dx,origin.y+dy,1020-(origin.y+dy)*.1+98))
        yield wait(.12)
        for retry in range(8):
            aim(actor);yield wait(.04);action('UpdateTarget')
            if prop('Target')==actor:break
        attempts.append(ray_state(actor))
        if prop('Target')==actor:break
    check('Real visibility ray selects optional public chronology',prop('Target')==actor,attempts)
    action('Interact');yield wait(.05)
    check('Chronology inspection grants only its separate observed flag',
          prop('PublicChronologyObserved') and int(prop('Mode'))==2 and 'Order V-17' in str(prop('PanelText')) and
          old_memorial==(bool(prop('OriginalMemorialRead')),str(prop('PriorTimelineObservation'))),{'stage':stage})
    body=str(prop('PanelText'))
    action('OpenPause');yield wait(.04);action('CloseModal');yield wait(.04)
    check('Pausing resumes the chronology text without swapping documents',int(prop('Mode'))==2 and str(prop('PanelText'))==body)
    action('CloseDocument');yield wait(.04)
    check('Chronology reading leaves the original memorial dialogue undiscovered when skipped',
          old_memorial==(bool(prop('OriginalMemorialRead')),str(prop('PriorTimelineObservation'))))

def v2_check_return_dialogue(case):
    spoken=[row['text'] for row in S['record']['spoken_lines']]
    check('Mother return keeps the bounded city change',all(text in spoken for speaker,text in V2_DATA['return_common']))
    expected='return_observed' if case['dated_record'] else 'return_unobserved'
    check('Mother receives only the evidence the traveler actually inspected',all(text in spoken for speaker,text in V2_DATA[expected]))
    forbidden='return_unobserved' if case['dated_record'] else 'return_observed'
    exclusive=[text for speaker,text in V2_DATA[forbidden] if text not in [t for s,t in V2_DATA[expected]]]
    check('Skipped dated record does not become a false V-17 claim',not any(text in spoken for text in exclusive))
    check('Explicitly selected Mother intention receives its own return callback',
          all(text in spoken for speaker,text in V2_DATA['return_intentions'][str(case['journey_intent'])]))
    check('The original final Tomorrow exchange remains last',spoken[-3:]==[row['text'] for row in NODES['C2_09.continuation']['lines']],spoken[-5:])
'''

v2_replace('LEVEL=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)',
           V2_HELPERS + '\nLEVEL=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)')
v2_replace("    if root=='C1_08':return case['departure']",
           "    if root=='C1_08':return case['departure']\n    if root=='C1_INTENTION_01':return case['journey_intent']")
v2_replace("        S['step']=case['id']+': anchored departure'", """        if case['chronology_before']:
            yield from v2_observe_chronology(case,'before departure')
        check('Predeparture chronology and storm-plaque knowledge are independent',
              bool(prop('PublicChronologyObserved'))==case['chronology_before'] and bool(prop('OriginalMemorialRead'))==case['memorial'])
        check('No shelter record or Mother intention has been inferred before it is chosen',
              not prop('OrderRegisterObserved') and int(prop('MotherJourneyIntention'))==0)
        S['step']=case['id']+': anchored departure'""")
v2_replace("        check('Departure dialogue does not travel without confirmation',int(prop('EraIndex'))==0)", """        check('Departure dialogue does not travel without confirmation',int(prop('EraIndex'))==0)
        check('The new journey intention commits only the explicitly chosen response',int(prop('MotherJourneyIntention'))==case['journey_intent'])""")
v2_replace("        yield from interact('MemorialActor')\n        action('CloseDocument');yield wait(.04)\n        yield from dialogue(case)", """        if case['chronology_after']:
            yield from v2_observe_chronology(case,'first read after return')
        check('Shelter installation and return do not manufacture V-17 knowledge',not prop('OrderRegisterObserved'))
        yield from interact('MemorialActor')
        check('Original changed-record caption remains the first readable archive page',
              int(prop('Mode'))==2 and int(prop('QuestV2ArchivePage'))==0 and not prop('OrderRegisterObserved'))
        chronology_before_record=bool(prop('PublicChronologyObserved'))
        if case['dated_record']:
            # The production 2-key action is also a public native helper; no
            # field is written by Python to manufacture record observation.
            action('QuestV2InspectDatedRecord');yield wait(.04)
            check('Optional inspection opens only the selected branch entry',int(prop('QuestV2ArchivePage'))==1 and
                  ('CLINIC REGISTER' if case['cover']==1 else 'HARBOR DEPARTURE RECORD') in str(prop('PanelText')))
            text_before_pause=str(prop('PanelText'))
            action('OpenPause');yield wait(.04);action('CloseModal');yield wait(.04)
            check('Date-entry page survives pause without losing its pending original scene',str(prop('PanelText'))==text_before_pause and int(prop('Mode'))==2)
            action('CloseDocument');yield wait(.04)
            check('Comparison opens the next lead without solving its cause',prop('OrderRegisterObserved') and int(prop('QuestV2ArchivePage'))==2 and
                  'Find the original Order V-17' in str(prop('PanelText')) and 'not proof of a conspiracy' in str(prop('PanelText')))
        else:
            check('Optional dated entry can be skipped without pretending it was read',not prop('OrderRegisterObserved'))
        action('CloseDocument');yield wait(.04)
        yield from dialogue(case)
        check('Dated-record knowledge follows optional actual inspection',bool(prop('OrderRegisterObserved'))==case['dated_record'])
        check('The comparison never invents a separate chronology inspection',bool(prop('PublicChronologyObserved'))==chronology_before_record)""")
# The installed first pass records v0.2 observations/intentions as zero-trust once-only
# markers in the same TrustEventIds set. They are separated from the two authored trust
# rewards here and must reflect only what this route explicitly did.
v2_replace("""        events=list(prop('TrustEventIds'))
        check('Authored relationship rewards are unique and never force 100 trust',len(events)==len(set(map(str,events))) and len(events)==2 and int(prop('HealerTrust'))==30)""",
           """        events=[str(e) for e in prop('TrustEventIds')]
        markers=[e for e in events if e.startswith('story.v02.')]
        rewards=[e for e in events if not e.startswith('story.v02.')]
        check('Authored relationship rewards are unique and never force 100 trust',len(events)==len(set(events)) and len(rewards)==2 and int(prop('HealerTrust'))==30,{'rewards':rewards,'markers':markers})
        expected_markers=['story.v02.intention.'+str(case['journey_intent'])]+(['story.v02.public_chronology'] if case['chronology_before'] else [])
        check('v0.2 markers carry no trust and reflect only the explicit intention and chronology inspection',
              sorted(markers)==sorted(expected_markers) and int(prop('HealerTrust'))==30,{'markers':markers,'expected':expected_markers})""")
v2_replace("        check('Every honest final response leads to chapter completion',prop('Chapter2Complete') and int(prop('EraIndex'))==0 and int(prop('FinalResponse'))==case['ending'])",
           """        check('Every honest final response leads to chapter completion',prop('Chapter2Complete') and int(prop('EraIndex'))==0 and int(prop('FinalResponse'))==case['ending'])
        v2_check_return_dialogue(case)""")
v2_replace("        check('Final journal preserves the appropriate timeline perspective',(JOURNAL_OBSERVED if case['memorial'] else JOURNAL_UNOBSERVED) in journal)",
           """        check('Final journal preserves the appropriate timeline perspective',(JOURNAL_OBSERVED if case['memorial'] else JOURNAL_UNOBSERVED) in journal)
        check('Journal represents chronology and dated record as separate observations',
              ('PUBLIC ACCOUNT OBSERVED' in journal)==bool(prop('PublicChronologyObserved')) and
              ('Find the original Order V-17' in journal)==case['dated_record'])""")
# New release source copy is the provenance authority for deliberately amended
# dialogue. The original supplied text, IDs and prior regression remain intact.
v2_replace("REPORT['adaptation_source_sha256']=hashlib.sha256((ROOT/'Python/validate_release_story.py').read_bytes()).hexdigest()",
           """REPORT['adaptation_source_sha256']=hashlib.sha256((ROOT/'Python/validate_release_story.py').read_bytes()).hexdigest()
REPORT['quest_v02_source_sha256']=hashlib.sha256((ROOT/'Python/validate_quest_story_v02.py').read_bytes()).hexdigest()
REPORT['quest_v02_content_sha256']=hashlib.sha256((ROOT/'ContentData/quest_story_v02.json').read_bytes()).hexdigest()
REPORT['revision_scope']='Four actual routes, three explicit journey intentions, separate chronology inspection/skip/return read, optional dated-record skip, native committed reloads, uncertainty and original Tomorrow ending.'""")
for old, new in [('release_story_runtime_validation.json', 'quest_story_v02_runtime_validation.json'),
                 ("'release_story'", "'quest_story_v02'"), ('YRStoryQA_', 'YRV02QA_')]:
    if old not in source:
        raise RuntimeError('Runtime output label changed: ' + old)
    source = source.replace(old, new)
ast.parse(source)
exec(compile(source, str(V2_ROOT / 'Python/validate_brief_m2.py'), 'exec'), globals())
