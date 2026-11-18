"""Queued source adaptation of the established four-route native story test.

Use a new dedicated -UserDir and -ReleaseStoryQA in the release project only.
Every fresh route enters through the real menu New Game; every restart uses
its saved profile and real Continue. No direct story flag writes or load bypass.
Known v1 migration is explicitly SHA-pinned, never arbitrary raw save input.
This file is source-only until queued and does not imply a packaged playthrough.
"""
from pathlib import Path
import ast
import hashlib
import sys
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
if root.parent.name != 'Release_20261026':
    raise RuntimeError('Release acceptance refuses protected project copies')
if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'ReleaseStoryQA'):
    raise RuntimeError('A queued -ReleaseStoryQA run with a dedicated -UserDir is required')
actual_saved = Path(unreal.Paths.project_saved_dir()).resolve()
if actual_saved == (root / 'Saved').resolve():
    raise RuntimeError('Use a dedicated -UserDir; the normal project save directory is protected')

source = (root / 'Python/validate_brief_m2.py').read_text(encoding='utf-8')


def replace(old, new):
    global source
    if source.count(old) != 1:
        raise RuntimeError('Reviewed release adaptation no longer matches: ' + old[:120])
    source = source.replace(old, new)


def replace_function(name, replacement):
    global source
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError('Expected one base function: ' + name)
    node = matches[0]
    lines = source.splitlines(keepends=True)
    lines[node.lineno-1:node.end_lineno] = [replacement.rstrip() + '\n']
    source = ''.join(lines)


replace("""BASELINE_PATH=ROOT.parent/'baseline_manifest.json'
if not BASELINE_PATH.exists():raise RuntimeError('Run this harness only in the isolated illustrated-brief development copy')
BASELINE=json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
if Path(BASELINE['development_copy']).resolve()!=ROOT.parent:raise RuntimeError('Development-copy location does not match its baseline manifest')
ORIGINAL_ROOT=Path(BASELINE['original_workspace'])""", """BASELINE_PATH=ROOT.parent/'release_baseline_manifest.json'
BASELINE=json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
if Path(BASELINE['target']).resolve()!=ROOT.parent:raise RuntimeError('Release copy manifest mismatch')
ORIGINAL_ROOT=ROOT.parent.parent.parent
SAVE_DIR=Path(unreal.Paths.project_saved_dir()).resolve()/'SaveGames'
# Unreal's platform file normalizes long Win32 paths; bundled Python's normal
# Path.exists may still return false beyond MAX_PATH. Keep QA filesystem I/O
# on an extended absolute path without changing engine slot names or OS policy.
LONG_PREFIX=chr(92)*2+'?'+chr(92)
if sys.platform=='win32' and not str(SAVE_DIR).startswith(LONG_PREFIX):
    SAVE_DIR=Path(LONG_PREFIX+str(SAVE_DIR))
SAVE_DIR.mkdir(parents=True,exist_ok=True)""")

# Replace map/slot/report labels globally, with explicit match checks.
for old, new in {
    "MAP_ROOT='/Game/BriefTest/Maps/'": "MAP_ROOT='/Game/Quest/Maps/'",
    "'Quarter_FirstPerson'": "'Verdant_Desktop'",
    "'Quarter_ThirdPerson'": "'Verdant_Desktop'",
    'Yesterday_Brief_20261025': 'Yesterday_Quest_20261025',
    'Yesterday_Brief_M2_QA_': 'YRStoryQA_',
    'brief_m2_runtime_validation.json': 'release_story_runtime_validation.json',
    "'brief_m2'": "'release_story'",
    'brief_m2_qa.log': 'release_story_qa.log',
    'Native PIE illustrated-brief M2 and four-route regression': 'Native release-menu PIE four-route story regression',
    'BRIEF_M2_RUNTIME_VALIDATION': 'RELEASE_STORY_RUNTIME_VALIDATION',
}.items():
    if old not in source:
        raise RuntimeError('Base acceptance label changed: ' + old)
    source = source.replace(old, new)

replace("REPORT['protected_save_digests_before']={str(p):hash_file(p) for p in PROTECTED_SAVE_PATHS}", """# Preserve every pre-existing campaign and legacy fixture, including backups.
for folder in [ROOT/'Saved/SaveGames', SAVE_DIR,
               ROOT.parent.parent/'Quest_20261025/game_unreal/Saved/SaveGames',
               ROOT.parent.parent/'Brief_20261025/game_unreal/Saved/SaveGames',
               ORIGINAL_ROOT/'game_unreal/Saved/SaveGames',
               Path.home()/'AppData/Local/YesterdayHarbor/Saved/SaveGames']:
    if folder.exists():
        PROTECTED_SAVE_PATHS.extend(p for p in folder.iterdir() if p.is_file() and '.sav' in p.name)
PROTECTED_SAVE_PATHS=list(dict.fromkeys(PROTECTED_SAVE_PATHS))
REPORT['protected_save_digests_before']={str(p):hash_file(p) for p in PROTECTED_SAVE_PATHS}
PROTECTED_ASSETS=list((ROOT/'Config').glob('*.ini'))+list((ROOT/'Content/Quest/Maps').glob('*.umap'))
PROTECTED_ASSETS += [ROOT/('Content/'+p) for p in [
    'Opening/Blueprints/BP_OpeningActions.uasset','Opening/Blueprints/BP_OpeningHUD.uasset',
    'Opening/Blueprints/BP_OpeningSave.uasset','Release/Blueprints/BP_ReleaseProfile.uasset']]
REPORT['protected_assets_before']={str(p):hash_file(p) for p in PROTECTED_ASSETS}
REPORT['save_directory']=str(SAVE_DIR)
REPORT['entry_policy']='Actual menu New Game/Continue; profile/save-prefix overrides only. No story flags seeded.'
REPORT['native_save_guard_active']=unreal.load_class(None,'/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary') is not None
REPORT['corrupt_save_tested']=False
REPORT['base_harness_sha256']=hashlib.sha256((ROOT/'Python/validate_brief_m2.py').read_bytes()).hexdigest()
REPORT['adaptation_source_sha256']=hashlib.sha256((ROOT/'Python/validate_release_story.py').read_bytes()).hexdigest()
""")

replace_function('ready', '''def ready():
    world=EDITOR.get_game_world()
    if world is None:return False
    pawn=unreal.GameplayStatics.get_player_character(world,0)
    if pawn is None or pawn.get_controller() is None:return False
    S.update(world=world,pawn=pawn,controller=pawn.get_controller(),
             camera=unreal.GameplayStatics.get_player_camera_manager(world,0),manager=find_manager(world))
    if not prop('ReleaseBooted') or prop('Player') is None or S['camera'] is None:return False
    requested=S.get('menu_entry')
    if requested:
        if not prop('ReleaseMenuActive') or int(prop('ReleaseMenuScreen'))!=0:return False
        if S.get('legacy_pending'):
            destination=S['legacy_destination']
            if REPORT['native_save_guard_active']:
                # Only the exact approved fixture is eligible; import writes a
                # new envelope destination and never touches its raw source.
                guard=unreal.get_default_object(unreal.load_class(None,'/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary'))
                imported=guard.call_method('ImportPinnedLegacyFixture',args=(S['legacy_source'],destination,0))
                if not imported:raise RuntimeError('Pinned native fixture import failed')
            profile=unreal.GameplayStatics.create_save_game_object(unreal.load_class(None,PROFILE_CLASS))
            PROFILE_SETTER.call_method('SetProfilePointer',args=(profile,destination))
            if REPORT['native_save_guard_active']:
                saved=guard.call_method('SafeSaveGameToSlot',args=(profile,S['profile_slot'],0))
            else:
                saved=unreal.GameplayStatics.save_game_to_slot(profile,S['profile_slot'],0)
            if not saved:raise RuntimeError('Isolated legacy QA profile could not be saved')
            action('ReleaseReadProfile');action('ReleaseCheckContinue')
            S['legacy_pending']=False
        if requested=='continue' and not prop('ReleaseContinueAvailable'):
            raise RuntimeError('Actual Continue is unavailable for isolated profile '+S['profile_slot'])
        if requested=='new' and prop('ReleaseContinueAvailable'):
            raise RuntimeError('A supposedly fresh QA profile already has progress')
        # Real frontend entry handlers are also the visible row actions. No
        # ReleaseLoadApproved edits or direct LoadProgress calls are allowed.
        action('ReleaseNewGame' if requested=='new' else 'ReleaseContinue')
        S['menu_entry']=None
        slot=str(prop('SaveSlot'))
        if not slot.startswith(S['campaign_prefix']):raise RuntimeError('Frontend selected a slot outside the QA namespace: '+slot)
        S['record']['slot']=slot
        S['record'].setdefault('menu_entries',[]).append({'action':requested,'slot':slot,'profile':str(prop('ReleaseProfileSlot'))})
    return bool(prop('ReleaseSessionStarted'))
''')

replace_function('begin_case', '''def begin_case(case,legacy_fixture=None):
    path=MAP_ROOT+case['map']
    if not LEVEL.load_level(path):raise RuntimeError('Cannot load '+path)
    manager=find_manager(EDITOR.get_editor_world());original=manager.get_editor_property('SaveSlot')
    if str(original)!=EXPECTED_DEFAULT_SLOT:raise RuntimeError('Unexpected protected map default slot: '+str(original))
    # Full case labels stay in reports/screenshots; short filenames also fit a
    # stricter future native slot-length cap and Windows filesystem paths.
    case_token='Legacy' if legacy_fixture else str(CASES.index(case)+1)
    namespace=TEST_SLOT_PREFIX+STAMP+'_'+case_token
    profile_slot=namespace+'_Profile'
    campaign_prefix=namespace+'_'
    original_values={n:manager.get_editor_property(n) for n in ['ReleaseProfileSlot','ReleaseSavePrefix']}
    if any((SAVE_DIR/(profile_slot+s)).exists() for s in ['.sav','.sav.bak']):raise RuntimeError('QA profile already occupied')
    S['editor_override']=(manager,original_values)
    S['current_map']=path
    manager.set_editor_property('ReleaseProfileSlot',profile_slot)
    manager.set_editor_property('ReleaseSavePrefix',campaign_prefix)
    record={'case':case,'map':path,'slot':None,'checks':[],'spoken_lines':[],'ray_selections':[],
            'profile_slot':profile_slot,'original_save_slot':str(original),
            'original_save_digest_before':hash_file(ROOT/'Saved/SaveGames'/(str(original)+'.sav')),
            'baseline_campaign_digest_before':hash_file(ROOT/'Saved/SaveGames/Yesterday_Opening_v1.sav')}
    S.update(record=record,last_line=None,accelerated=False,profile_slot=profile_slot,
             campaign_prefix=campaign_prefix,menu_entry='continue' if legacy_fixture else 'new',legacy_pending=bool(legacy_fixture))
    if legacy_fixture:
        digest=hash_file(legacy_fixture)
        if digest!='0f698bb9c4a003a7aa2883af39317161a1e38290ca388626231bce5f1caf94e8':raise RuntimeError('Unapproved raw legacy fixture')
        source_slot=namespace+'_RawLegacy'
        destination_slot=namespace+'_Legacy' if REPORT['native_save_guard_active'] else source_slot
        destination=SAVE_DIR/(source_slot+'.sav')
        if destination.exists():raise RuntimeError('Refusing to overwrite any legacy QA input')
        destination.write_bytes(legacy_fixture.read_bytes())
        if hash_file(destination)!=digest:raise RuntimeError('Legacy fixture copy mismatch')
        S.update(legacy_source=source_slot,legacy_destination=destination_slot)
        record['legacy_fixture']={'source':str(legacy_fixture),'sha256':digest,'test_copy':str(destination),
                                  'policy':'Exact SHA-pinned trusted fixture; never arbitrary corrupt input'}
    LEVEL.editor_request_begin_play()
''')

replace_function('restore_override', '''def restore_override():
    pair=S.get('editor_override')
    if pair:
        for name,value in pair[1].items():
            try:pair[0].set_editor_property(name,value)
            except Exception:REPORT.setdefault('cleanup_errors',[]).append(traceback.format_exc())
        S['editor_override']=None
''')

replace("fixture=ROOT/'Saved/SaveGames/Yesterday_Automation_A_v1_20261024T151953_576332_FirstPerson.sav'",
        "fixture=ROOT.parent.parent/'Brief_20261025/game_unreal/Saved/SaveGames/Yesterday_Automation_A_v1_20261024T151953_576332_FirstPerson.sav'")
replace("slot=str(prop('SaveSlot'));save_file=ROOT/'Saved/SaveGames'/(slot+'.sav')",
        "slot=str(prop('SaveSlot'));save_file=SAVE_DIR/(slot+'.sav')")
replace("LEVEL.editor_request_begin_play();yield until(ready,'restarted native game for '+label)",
        "S['menu_entry']='continue'\n    LEVEL.editor_request_begin_play();yield until(ready,'restarted actual menu Continue for '+label)")

# Source-only hook for the small genuine ending-journal feature. Never use
# OpenJournal behind the still-active menu, which would test invisible text.
replace("""        if int(prop('Mode'))!=0:action('CloseModal')
        action('OpenJournal');yield wait(.05)
        action('TurnJournal',1);action('TurnJournal',1);yield wait(.05)
        journal=' '.join(str(prop('PanelText')).split())
        check('Final journal preserves the appropriate timeline perspective',(JOURNAL_OBSERVED if case['memorial'] else JOURNAL_UNOBSERVED) in journal)
        yield screenshot('Final_Journal')
        action('CloseModal')
        completed=snapshot();yield from restart_and_check(completed,'completed present consequence')""", """        check('Ending explicitly names the playable scope and gates world input',
              prop('ReleaseMenuActive') and int(prop('Mode'))==8 and int(prop('ReleaseMenuScreen'))==3 and
              str(prop('ReleaseMenuTitle'))=='End of Chapters I–II — Early Playable' and
              S['controller'].is_move_input_ignored() and S['controller'].is_look_input_ignored())
        yield screenshot('Ending_Menu')
        # This deliberately fails until a real visible Review journal action
        # exists. The harness never changes menu flags or seeds an escape.
        rows=[str(prop('ReleaseRow'+str(i))) for i in range(int(prop('ReleaseMenuCount')))]
        if 'Review journal' not in rows:raise RuntimeError('End screen needs a real Review journal row before the retained final-journal acceptance can pass')
        yield wait(.2)
        action('ReleaseSelect',rows.index('Review journal'),True);yield wait(.08)
        if prop('ReleaseMenuActive') or int(prop('Mode'))!=5:raise RuntimeError('Review journal did not enter the visible native journal')
        action('TurnJournal',1);action('TurnJournal',1);yield wait(.05)
        journal=' '.join(str(prop('PanelText')).split())
        check('Final journal preserves the appropriate timeline perspective',(JOURNAL_OBSERVED if case['memorial'] else JOURNAL_UNOBSERVED) in journal)
        yield screenshot('Final_Journal')
        action('OpenPause');yield wait(.05)
        if int(prop('Mode'))!=6 or not prop('ReleaseReviewingJournal'):raise RuntimeError('Ending journal did not pause normally')
        action('CloseModal');yield wait(.05)
        if int(prop('Mode'))!=5 or prop('ReleaseMenuActive') or not prop('ReleaseReviewingJournal'):raise RuntimeError('Pause resume must retain the visible ending journal')
        if ' '.join(str(prop('PanelText')).split())!=journal:raise RuntimeError('Ending journal page changed while paused')
        action('CloseModal');yield wait(.05)
        if not prop('ReleaseMenuActive') or int(prop('ReleaseMenuScreen'))!=3:raise RuntimeError('Journal close must return to the ending menu')
        completed=snapshot();yield from restart_and_check(completed,'completed present consequence')
        check('Completed Continue reopens the ending menu without replacing its campaign',
              prop('ReleaseMenuActive') and int(prop('ReleaseMenuScreen'))==3 and int(prop('Mode'))==8 and
              str(prop('ReleaseMenuTitle'))=='End of Chapters I–II — Early Playable' and
              str(prop('SaveSlot'))==S['record']['slot'])""")

replace("REPORT['protected_saves_unchanged']=REPORT['protected_save_digests_after']==REPORT['protected_save_digests_before']",
        """REPORT['protected_saves_unchanged']=REPORT['protected_save_digests_after']==REPORT['protected_save_digests_before']
    REPORT['protected_assets_after']={str(p):hash_file(p) for p in PROTECTED_ASSETS}
    REPORT['protected_assets_unchanged']=REPORT['protected_assets_after']==REPORT['protected_assets_before']""")
replace("and REPORT['protected_saves_unchanged']\n    write()",
        "and REPORT['protected_saves_unchanged'] and REPORT['protected_assets_unchanged'] and not REPORT.get('cleanup_errors')\n    write()")

# Queue screenshots and protect callbacks against nested Slate ticks.
replace("    check('Photo exchange discovers the source photograph',prop('PhotoSeen') and int(prop('Mode'))==1)",
        """    check('Photo exchange discovers the source photograph',prop('PhotoSeen') and int(prop('Mode'))==1)
    photo_adoption=ROOT/'release_family_photo_report.json'
    if photo_adoption.is_file():
        photo_evidence=json.loads(photo_adoption.read_text())
        check('Photo review uses the adopted real prop material',photo_evidence['success'] and
              prop('PhotoActor').get_component_by_class(unreal.StaticMeshComponent).get_material(0).get_path_name()==photo_evidence['assigned']['InspectionMaterial'])
        yield wait(.25)
        yield screenshot('FamilyPhoto_Front')""")
replace("    check('Photograph reverse uses the supplied inscription',ORIGINAL_BACK in str(prop('PanelText')))",
        """    check('Photograph reverse uses the supplied inscription',ORIGINAL_BACK in str(prop('PanelText')))
    if photo_adoption.is_file():
        check('Photo flip uses the original-inscription reverse material',
              prop('PhotoActor').get_component_by_class(unreal.StaticMeshComponent).get_material(0).get_path_name()==photo_evidence['assigned']['PhotoBackInspectionMaterial'])
        yield wait(.25)
        yield screenshot('FamilyPhoto_Reverse')""")
replace("unreal.SystemLibrary.execute_console_command(S['world'],'shot showui filename=\"'+str(path).replace('\\\\','/')+'\" -nosuffix')",
        "unreal.SystemLibrary.execute_console_command(S['world'],'HighResShot 1920x1080 filename=\"'+str(path).replace('\\\\','/')+'\"')")
# The isolated -UserDir owns the actual current log; project Saved may contain
# an unrelated earlier commandlet log from another native queue stage.
replace("log_path=ROOT/'Saved/Logs/release_story_qa.log'\n    if not log_path.exists():log_path=ROOT/'Saved/Logs/YesterdayHarbor.log'",
        "log_path=Path(unreal.Paths.project_log_dir())/'YesterdayHarbor.log'")
replace('runner=scenario()', "ReleaseTickGuard=False\nrunner=scenario()")
replace('global pending,deadline', 'global pending,deadline,ReleaseTickGuard\n    if ReleaseTickGuard:return\n    ReleaseTickGuard=True')
replace('except Exception:finish(traceback.format_exc())',
        'except Exception:finish(traceback.format_exc())\n    finally:ReleaseTickGuard=False')

# Unsaved fixture helper sets only the QA profile's active pointer; it cannot
# write story flags and is never saved or cooked. Native properties retain
# their production edit flags.
sys.path.insert(0, str(root / 'Python'))
import opening_graph as og
PROFILE_CLASS = '/Game/Release/Blueprints/BP_ReleaseProfile.BP_ReleaseProfile_C'
fixture = og.blueprint('/Temp/BP_ReleaseStoryProfileFixture', unreal.Actor)
graph = og.function(fixture, 'SetProfilePointer', inputs={'Target': og.object_type(PROFILE_CLASS), 'Slot': 'string'})
setter = graph.set('ActiveSlot', graph.input('Slot'), owner=graph.input('Target'), class_path=PROFILE_CLASS)
og.link(graph.entry, og.pin_in(setter))
og.compile_bp(fixture, save=False)
PROFILE_SETTER = unreal.get_default_object(og.L.generated_class(fixture))

exec(compile(source, str(root / 'Python/validate_brief_m2.py'), 'exec'), globals())
