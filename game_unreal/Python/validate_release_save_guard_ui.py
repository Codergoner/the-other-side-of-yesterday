"""Queued real menu recovery policy test after verified native owner wiring.

Only unique QA campaign/profile bytes are damaged, and only native guarded
loaders read them. Existing user files/assets remain protected. Editor proof,
not packaged proof or a universal claim about arbitrary possible byte strings.
"""
from pathlib import Path
import unreal

root=Path(unreal.Paths.project_dir()).resolve()
if not unreal.load_class(None,'/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary'):
    raise RuntimeError('Native guard must be loaded before any raw UI fault test')
safe_path=root/'Python/validate_release_frontend_safe.py'
safe=safe_path.read_text(encoding='utf-8')
ending="exec(compile(source, str(root / 'Python/validate_release_frontend.py'), 'exec'), globals())"
if safe.count(ending)!=1:raise RuntimeError('Review changed safe frontend adaptation')
exec(compile(safe.replace(ending,'GUARD_UI_BASE_SOURCE=source'),str(safe_path),'exec'),globals())
source=GUARD_UI_BASE_SOURCE
helpers='''
def guarded_recovery_ui(second):
    if not str(second).startswith(PREFIX):raise RuntimeError('Refusing a fault outside the owned QA slot prefix')
    # Real normal commits make a verified recovery generation, without seeding
    # story fields or manufacturing a different narrative state.
    call('SaveProgress');call('SaveProgress');yield wait(.1)
    path=save_path(second);backup=Path(str(path)+'.bak')
    if not backup.exists():raise RuntimeError('Guarded campaign has no verified previous checkpoint')
    call('OpenPause');call('ReleaseShowMain');yield wait(.2)
    path.write_bytes(b'Invalid isolated QA save; never a player file')
    bad_sha=sha(path);backup_sha=sha(backup)
    click(1);yield wait(.2)
    check('Recovered campaign cannot silently Continue into an unsavable primary',prop('ReleaseMenuActive') and not prop('ReleaseContinueAvailable') and not prop('ReleaseWriteAllowed') and prop('ReleaseGuardCampaignRecoveryBlocked'))
    check('Blocked backup Continue explains the preserved file and separate New Game','backup' in str(prop('ReleaseMenuStatus')).lower() and 'cannot safely save' in str(prop('ReleaseMenuStatus')).lower() and prop('ReleaseProfileWritable'))
    call('ReleaseValidateCandidate')
    check('Structural validation cannot override recovered-campaign rejection',not prop('ReleaseCandidateValid') and prop('ReleaseGuardCampaignRecoveryBlocked'))
    call('SaveProgress')
    check('Blocked Continue preserves damaged primary and verified backup bytes',sha(path)==bad_sha and sha(backup)==backup_sha)
    click(0);yield until(lambda:not prop('ReleaseMenuActive') and prop('IntroActive'),'separate New Game after damaged campaign')
    third=str(prop('SaveSlot'))
    check('Safe New Game stays available and creates a separate guarded campaign',third!=second and third.startswith(PREFIX) and save_path(third).read_bytes()[:8]==b'YDAYSG01' and sha(path)==bad_sha)
    call('SkipRecollections');call('SaveProgress');call('SaveProgress');yield wait(.1)
    profile_path=save_path(PROFILE);profile_backup=Path(str(profile_path)+'.bak')
    if not profile_backup.exists():raise RuntimeError('Guarded profile has no verified previous generation')
    profile_path.write_bytes(b'Invalid isolated QA profile index')
    profile_bad_sha=sha(profile_path);profile_backup_sha=sha(profile_backup)
    LEVEL.editor_request_end_play();yield until(lambda:not LEVEL.is_in_play_in_editor(),'stop before actual backup-profile boot')
    start(PROFILE);yield until(ready,'actual boot from verified profile backup');restore()
    check('Backup profile boot is read-only while retaining a supported campaign',prop('ReleaseMenuActive') and not prop('ReleaseProfileWritable') and prop('ReleaseContinueAvailable'))
    before={str(p):sha(p) for p in profile_path.parent.iterdir() if p.is_file() and p.name.startswith(PREFIX)}
    click(0);yield wait(.2)
    after={str(p):sha(p) for p in profile_path.parent.iterdir() if p.is_file() and p.name.startswith(PREFIX)}
    check('Read-only backup index cannot create an unreachable New Game',before==after and not prop('ReleaseSessionStarted'))
    yield screenshot('BackupProfileReadOnly')
    click(1);yield wait(.2)
    call('SaveProgress');yield wait(.1)
    check('Supported existing campaign can save while corrupt index remains preserved',not prop('ReleaseMenuActive') and prop('ReleaseWriteAllowed') and prop('SaveSucceeded') and str(prop('SaveSlot'))==third and sha(profile_path)==profile_bad_sha and sha(profile_backup)==profile_backup_sha)
    REPORT['raw_corrupt_fixtures_tested']=2
    REPORT['raw_corrupt_fixtures_rejected_or_recovered_with_preservation']=True

'''
if source.count('def scenario():')!=1:raise RuntimeError('Expected one reviewed frontend scenario')
source=source.replace('def scenario():',helpers+'\ndef scenario():')
marker="    check('A valid campaign can still recover after a rejected future-version load', prop('ReleaseWriteAllowed') and not prop('ReleaseMenuActive') and prop('IntroSeen'))"
if source.count(marker)!=1:raise RuntimeError('Review changed future-version recovery checkpoint')
source=source.replace(marker,marker+'\n    yield from guarded_recovery_ui(second)')
source=source.replace('release_frontend_safe_validation.json','release_save_guard_ui_validation.json')
source=source.replace("'validation/release_frontend_safe'","'validation/release_save_guard_ui'")
source=source.replace('YRelMenuSafe_','YGuardUI_')
source=source.replace("REPORT['corrupt_save_tested']=False","REPORT['corrupt_save_tested']=True")
source=source.replace("REPORT['arbitrary_corrupt_bytes_safe']=False","REPORT['raw_fixture_scope']='Two exact owned QA byte faults through the real guarded menu; no universal arbitrary-input or packaged claim'")
source=source.replace("REPORT['blocked_acceptance']=['Arbitrary-byte save/profile corruption requires the compiled native SaveGuard; stock generic loader previously asserted before Blueprint validation.']",
                      "REPORT['blocked_acceptance']=['Separate packaged Development/Shipping recovery testing remains pending.']")
exec(compile(source,str(root/'Python/validate_release_frontend.py'),'exec'),globals())
