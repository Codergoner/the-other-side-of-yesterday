"""Queued actual six consent/roof combinations plus two anonymous skips.

Run after real campaign-v3 compile/stage and identity integration, with
-ReleaseStoryQA -QuestStoryV2QA -QuestIdentityV2QA and a fresh short UserDir.
Uses native actions, real New Game/Continue, actual camera rays and guarded
committed state. It never seeds identity, consent, inventory or trust flags.
The clerk and worker are the real supporting-cast Enna (cast.clerk) and Tavi
(cast.dockworker) placed by integrate_supporting_cast.py, not placeholder actors.
"""
from pathlib import Path
import ast
import hashlib
import json
import unreal

IDENTITY_ROOT = Path(unreal.Paths.project_dir()).resolve()
if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'QuestIdentityV2QA'):
    raise RuntimeError('Root-queued -QuestIdentityV2QA is required')
IDENTITY_PARENT = IDENTITY_ROOT / 'Python/validate_quest_story_v02.py'
IDENTITY_TEXT = IDENTITY_PARENT.read_text(encoding='utf-8')
IDENTITY_TREE = ast.parse(IDENTITY_TEXT)
IDENTITY_END = "exec(compile(source, str(V2_ROOT / 'Python/validate_brief_m2.py'), 'exec'), globals())"
if ast.get_source_segment(IDENTITY_TEXT, IDENTITY_TREE.body[-1]) != IDENTITY_END:
    raise RuntimeError('Review changed phase-one harness before identity extension')
IDENTITY_PREFIX, IDENTITY_SEPARATOR, IDENTITY_SUFFIX = IDENTITY_TEXT.rpartition(IDENTITY_END)
if not IDENTITY_SEPARATOR or IDENTITY_SUFFIX.strip():
    raise RuntimeError('Phase-one harness launch is no longer the checked final statement')
IDENTITY_OLD_FILE = globals().get('__file__')
globals()['__file__'] = str(IDENTITY_PARENT)
try:
    exec(compile(IDENTITY_PREFIX, str(IDENTITY_PARENT), 'exec'), globals())
finally:
    globals()['__file__'] = IDENTITY_OLD_FILE


def identity_replace(old, new):
    global source
    if source.count(old) != 1:
        raise RuntimeError('Changed identity acceptance point: ' + old[:140])
    source = source.replace(old, new)


IDENTITY_HELPERS = r'''
IDENTITY_DATA=json.loads((ROOT/'ContentData/quest_identity_v02.json').read_text(encoding='utf-8'))
FIELDS+=['IdentitySceneSeen','IdentityRecordMethod','IdentityCustodianAccepted']
for speaker,text in IDENTITY_DATA['start']:SOURCE_LINES.add((speaker,text))
for row in IDENTITY_DATA['choices']:
    SOURCE_LINES.update(tuple(line) for line in row['lines'])
for lines in IDENTITY_DATA['repeat'].values():SOURCE_LINES.update(tuple(line) for line in lines)
original_cases=list(CASES)
CASES=[]
for cover in [1,2]:
    for method in [1,2,3]:
        template=original_cases[(0 if method!=2 else 1)+(0 if cover==1 else 2)]
        case=dict(template)
        case.update(id=('Clinic' if cover==1 else 'Harbor')+'_Identity_'+str(method),identity_method=method,
                    identity_interrupt=(cover==1 and method==2),identity_skip=False)
        CASES.append(case)
for cover in [1,2]:
    case=dict(original_cases[1 if cover==1 else 3])
    case.update(id=('Clinic' if cover==1 else 'Harbor')+'_Identity_Unasked',identity_method=0,
                identity_interrupt=False,identity_skip=True)
    CASES.append(case)

def identity_play(case):
    check('Installation does not publish a name or imply custodian consent',
          not prop('IdentitySceneSeen') and int(prop('IdentityRecordMethod'))==0 and not prop('IdentityCustodianAccepted'))
    clerks=tagged('cast.clerk');workers=tagged('cast.dockworker')
    check('One willing clerk and one adult worker exist in this era',len(clerks)==1 and len(workers)==1)
    check('The selected shelter uses the same actors, not duplicate clerks',
          clerks[0]==prop('QuestIdentityClerkActor') and workers[0]==prop('QuestIdentityWorkerActor') and
          visible(clerks[0]) and visible(workers[0]) and collision_enabled(clerks[0]) and collision_enabled(workers[0]))
    expected_y=485 if case['cover']==1 else -555
    check('The single clerk is working at the installed shelter',abs(clerks[0].get_actor_location().y-expected_y)<1)
    if case['identity_skip']:
        check('Unasked identity remains anonymous without a lost shelter',
              int(prop('IdentityRecordMethod'))==0 and not prop('IdentitySceneSeen') and int(prop('StormCover'))==case['cover'])
        return
    yield from interact('QuestIdentityClerkActor')
    yield from dialogue(case,stop_at_choice=True)
    check('Opening a conversation grants no publication or sealed-custody agreement',
          prop('IdentitySceneSeen') and int(prop('IdentityRecordMethod'))==0 and not prop('IdentityCustodianAccepted'))
    if case['identity_interrupt']:
        action('ChooseDialogue',2);yield wait(.04)
        check('Advice is not committed before the worker and keeper finish agreeing',
              int(prop('IdentityRecordMethod'))==0 and not prop('IdentityCustodianAccepted'))
        action('CloseModal');yield wait(.04)
        yield from restart_and_check(snapshot(),'identity advice interrupted before consent')
        check('Continue does not manufacture acceptance from an interrupted option',
              prop('IdentitySceneSeen') and int(prop('IdentityRecordMethod'))==0 and not prop('IdentityCustodianAccepted'))
        yield from interact('QuestIdentityClerkActor')
    yield from dialogue(case)
    check('Only completed explicit agreement commits the selected handling method',
          int(prop('IdentityRecordMethod'))==case['identity_method'] and
          bool(prop('IdentityCustodianAccepted'))==(case['identity_method']==2))
    committed=snapshot()
    yield from restart_and_check(committed,'completed identity handling agreement')
    yield from interact('QuestIdentityWorkerActor');yield from dialogue(case)
    check('Repeat conversation cannot farm trust or change a committed privacy decision',
          int(prop('IdentityRecordMethod'))==committed['IdentityRecordMethod'] and
          bool(prop('IdentityCustodianAccepted'))==committed['IdentityCustodianAccepted'] and
          int(prop('HealerTrust'))==committed['HealerTrust'] and list(prop('TrustEventIds'))==committed['TrustEventIds'])

def identity_check_archive(case):
    body=' '.join(str(prop('PanelText')).split())
    expected=' '.join(IDENTITY_DATA['archive'][str(case['identity_method'])].split())
    check('Only the agreed public handling survives in the chosen archive',expected in body)
    if case['identity_skip']:
        check('Skipped conversation never grants the worker name or public consent',
              'Tavi' not in body and not prop('IdentitySceneSeen') and int(prop('IdentityRecordMethod'))==0)
    if case['identity_method']==2:
        check('Sealed entry has explicit accepted custody and signed transfer, with no opened contents',
              prop('IdentityCustodianAccepted') and 'Enna' in body and 'Mira' in body and 'remains sealed' in body)
    check('All handling choices leave the other archive mount empty',
          visible(prop('ClinicRecordActor'))==(case['cover']==1) and visible(prop('HarborRecordActor'))==(case['cover']==2))
'''

identity_replace('LEVEL=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)',
                 IDENTITY_HELPERS + '\nLEVEL=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)')
identity_replace("    if root=='C1_INTENTION_01':return case['journey_intent']",
                 "    if root=='C1_INTENTION_01':return case['journey_intent']\n    if root=='C2_IDENTITY_01':return case['identity_method']")
identity_replace("        history=snapshot();yield from interact(other,False)",
                 "        yield from identity_play(case)\n        history=snapshot();yield from interact(other,False)")
# The consent scene runs before the phase-one marker audit; its own zero-trust markers
# (scene seen, committed method) are expected there for every non-skip combination.
identity_replace("        expected_markers=['story.v02.intention.'+str(case['journey_intent'])]+(['story.v02.public_chronology'] if case['chronology_before'] else [])",
                 "        expected_markers=['story.v02.intention.'+str(case['journey_intent'])]+(['story.v02.public_chronology'] if case['chronology_before'] else [])+([] if case['identity_skip'] else ['story.v02.identity_seen','story.v02.identity.'+str(case['identity_method'])])")
identity_replace("        chronology_before_record=bool(prop('PublicChronologyObserved'))",
                 "        identity_check_archive(case)\n        chronology_before_record=bool(prop('PublicChronologyObserved'))")
identity_replace("        v2_check_return_dialogue(case)", """        v2_check_return_dialogue(case)
        if case['identity_skip']:
            check('Skipping the optional cast never produces name-specific protagonist knowledge',
                  not any('Tavi' in row['text'] for row in S['record']['spoken_lines']))
        check('Optional identity work never unlocks later perspective or a no-intervention shortcut',
              int(prop('HealerTrust'))==30 and int(prop('StormCover'))==case['cover'])""")
identity_replace("REPORT['quest_v02_content_sha256']=hashlib.sha256((ROOT/'ContentData/quest_story_v02.json').read_bytes()).hexdigest()",
                 """REPORT['quest_v02_content_sha256']=hashlib.sha256((ROOT/'ContentData/quest_story_v02.json').read_bytes()).hexdigest()
REPORT['identity_source_sha256']=hashlib.sha256((ROOT/'Python/validate_quest_identity_v02.py').read_bytes()).hexdigest()
REPORT['identity_content_sha256']=hashlib.sha256((ROOT/'ContentData/quest_identity_v02.json').read_bytes()).hexdigest()
REPORT['identity_acceptance']='Six roof/consent combinations, two anonymous skips, interrupted sealed advice, committed Continue, repeat nonfarming, single clerk relocation, public-only exhibits and sealed custody reference.'""")
for old, new in [('quest_story_v02_runtime_validation.json', 'quest_identity_v02_runtime_validation.json'),
                 ("'quest_story_v02'", "'quest_identity_v02'"), ('YRV02QA_', 'YRI02QA_')]:
    if old not in source:
        raise RuntimeError('Identity output label changed: ' + old)
    source = source.replace(old, new)
ast.parse(source)
exec(compile(source, str(IDENTITY_ROOT / 'Python/validate_brief_m2.py'), 'exec'), globals())
