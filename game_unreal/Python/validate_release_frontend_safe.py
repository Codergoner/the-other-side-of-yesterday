"""Normal/future-version frontend regression; raw corruption stays blocked.

This deliberately does NOT run the known-fatal generic raw-byte loader path.
Both unsupported profile indexes are well-formed typed ProfileVersion999
fixtures, not corruption evidence. A successful scoped report is not release
acceptance for arbitrary corrupt files or a packaged playthrough.
"""
from pathlib import Path
import unreal

root = Path(unreal.Paths.project_dir()).resolve()
if root.parent.name != 'Release_20261026':
    raise RuntimeError('Safe frontend regression refuses protected project copies')
if Path(unreal.Paths.project_saved_dir()).resolve() == (root / 'Saved').resolve():
    raise RuntimeError('A dedicated short -UserDir is required')
source = (root / 'Python/validate_release_frontend.py').read_text(encoding='utf-8')


def replace(old, new):
    global source
    if source.count(old) != 1:
        raise RuntimeError('Review changed frontend acceptance source: ' + old[:100])
    source = source.replace(old, new)


replace("    corrupt_slot = PREFIX + 'corrupt'\n", "    # RAW_CORRUPT_BLOCK_BEGIN\n    corrupt_slot = PREFIX + 'corrupt'\n")
start = source.index('    # RAW_CORRUPT_BLOCK_BEGIN\n')
end = source.index("    fixture_cdo.call_method('PointAtTestCopy', args=(S['manager'], second))", start)
source = source[:start] + "    # Raw corruption is explicitly blocked until the native guard is active.\n" + source[end:]
replace("    og.compile_bp(fixture, save=False)", """    profile_graph = og.function(fixture, 'MakeUnsupportedProfile', inputs={'Target': og.object_type('/Game/Release/Blueprints/BP_ReleaseProfile.BP_ReleaseProfile_C')})
    profile_version = profile_graph.set('ProfileVersion', 999, owner=profile_graph.input('Target'), class_path='/Game/Release/Blueprints/BP_ReleaseProfile.BP_ReleaseProfile_C')
    og.link(profile_graph.entry, og.pin_in(profile_version))
    og.compile_bp(fixture, save=False)""")
replace("""    for name in [bad_profile, bad_profile + '_recovered']:
        save_path(name).write_bytes(b'Invalid isolated QA profile index')""", """    profile_class=unreal.load_class(None,'/Game/Release/Blueprints/BP_ReleaseProfile.BP_ReleaseProfile_C')
    for name in [bad_profile, bad_profile + '_recovered']:
        unsupported=unreal.GameplayStatics.create_save_game_object(profile_class)
        fixture_cdo.call_method('MakeUnsupportedProfile',args=(unsupported,))
        if int(unsupported.get_editor_property('ProfileVersion'))!=999:raise RuntimeError('Typed unsupported profile fixture failed')
        if not unreal.GameplayStatics.save_game_to_slot(unsupported,name,0):raise RuntimeError('Typed unsupported profile fixture did not save')""")
replace("    S['step'] = 'both unreadable profile indexes'", "    S['step'] = 'both well-formed unsupported-version profile indexes'")
replace("check('Two unreadable indexes disable profile writes'", "check('Two typed future-version profile indexes disable profile writes'")
replace("check('A valid campaign can still recover after rejected loads'", "check('A valid campaign can still recover after a rejected future-version load'")
for old, new in {
    'Yesterday_Release_MenuQA_': 'YRelMenuSafe_',
    'release_frontend_validation.json': 'release_frontend_safe_validation.json',
    "'validation/release_frontend'": "'validation/release_frontend_safe'",
}.items():
    if old not in source:
        raise RuntimeError('Missing reviewed safe regression label: ' + old)
    source = source.replace(old, new)
replace("pending = None\ndeadline = 0", """REPORT['corrupt_save_tested']=False
REPORT['arbitrary_corrupt_bytes_safe']=False
REPORT['release_acceptance_complete']=False
REPORT['blocked_acceptance']=['Arbitrary-byte save/profile corruption requires the compiled native SaveGuard; stock generic loader previously asserted before Blueprint validation.']
REPORT['scope']='Native normal/future-version frontend PIE regression. Unsupported profile files are real typed schema999 objects. Raw corruption is not run.'
REPORT['native_save_guard_active']=unreal.load_class(None,'/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary') is not None
def qa_save(obj,slot,index):
    if REPORT['native_save_guard_active']:
        guard=unreal.get_default_object(unreal.load_class(None,'/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary'))
        return guard.call_method('SafeSaveGameToSlot',args=(obj,slot,index))
    return unreal.GameplayStatics.save_game_to_slot(obj,slot,index)
def qa_load(slot,index):
    if REPORT['native_save_guard_active']:
        guard=unreal.get_default_object(unreal.load_class(None,'/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary'))
        return guard.call_method('SafeLoadGameFromSlot',args=(slot,index))
    return unreal.GameplayStatics.load_game_from_slot(slot,index)
pending = None
deadline = 0""")
# Only trusted typed QA fixture writes/reads use these adapters. Raw-byte tests
# remain absent, even when a future native guard is detected.
source=source.replace('unreal.GameplayStatics.save_game_to_slot(future, future_slot, 0)', 'qa_save(future, future_slot, 0)')
source=source.replace('unreal.GameplayStatics.save_game_to_slot(unsupported,name,0)', 'qa_save(unsupported,name,0)')
source=source.replace('unreal.GameplayStatics.load_game_from_slot(PROFILE, 0)', 'qa_load(PROFILE, 0)')
exec(compile(source, str(root / 'Python/validate_release_frontend.py'), 'exec'), globals())
