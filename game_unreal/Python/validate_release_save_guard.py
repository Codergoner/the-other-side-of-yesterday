"""Queued actual native guard faults in a dedicated short QA UserDir.

Only guard APIs deserialize. Raw generic GameplayStatics loaders are forbidden.
Creates an unsaved setter fixture for a typed profile pointer, never story
flags. Existing saves/assets/config are hashed and preserved. No activation.
Editor proof only: no packaged crash, disk-full or power-loss claim.
"""
from pathlib import Path
import datetime
import hashlib
import json
import sys
import traceback
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
SAVE = Path(unreal.Paths.project_saved_dir()).resolve() / 'SaveGames'
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
PREFIX = 'YSGQA_' + STAMP + '_'
OUT = PROJECT / 'validation/release_save_guard' / STAMP
REPORT_PATH = PROJECT / 'release_save_guard_validation.json'
PROFILE_CLASS = '/Game/Release/Blueprints/BP_ReleaseProfile.BP_ReleaseProfile_C'
REPORT = {'success':False,'run':STAMP,'checks':[], 'native_executed':False,
          'packaged_build_tested':False,'power_loss_tested':False,'disk_full_tested':False,
          'scope':'Actual native bounded save APIs and same-directory recovery; only owned QA faults',
          'qa_save_directory':str(SAVE),'qa_prefix':PREFIX}


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
def write():
    OUT.mkdir(parents=True,exist_ok=True)
    text=json.dumps(REPORT,indent=2,default=str)
    REPORT_PATH.write_text(text,encoding='utf-8'); (OUT/'validation.json').write_text(text,encoding='utf-8')
def check(label, ok, details=None):
    REPORT['checks'].append({'name':label,'passed':bool(ok),'details':details});write()
    if not ok:raise AssertionError(label)
def file(slot):
    if not str(slot).startswith(PREFIX):raise RuntimeError('QA refuses file writes outside its unique prefix')
    return SAVE/(str(slot)+'.sav')
def call(name,*args):return GUARD.call_method(name,args=tuple(args))
def load(slot):return call('SafeLoadGameFromSlot',slot,0)
def save(obj,slot):return call('SafeSaveGameToSlot',obj,slot,0)
def exists(slot):return call('SafeDoesSaveGameExist',slot,0)


def main():
    global GUARD
    if PROJECT.parent.name!='Release_20261026' or SAVE.parent==(PROJECT/'Saved').resolve():
        raise RuntimeError('Use the release copy and a new short dedicated -UserDir')
    guard_class=unreal.load_class(None,'/Script/YesterdaySaveGuard.YesterdaySaveGuardLibrary')
    if not guard_class:raise RuntimeError('Actual compiled and activated guard required')
    GUARD=unreal.get_default_object(guard_class)
    REPORT['native_executed']=True
    SAVE.mkdir(parents=True,exist_ok=True)
    before_saves={str(p):sha(p) for p in SAVE.iterdir() if p.is_file()}
    protected=list((PROJECT/'Content').rglob('*.uasset'))+list((PROJECT/'Content').rglob('*.umap'))
    protected+=list((PROJECT/'Config').glob('*.ini'))+list(PROJECT.glob('*.uproject'))
    before_assets={str(p):sha(p) for p in protected}
    REPORT['protected_saves_before']=before_saves;REPORT['protected_assets_before']=before_assets
    sys.path.insert(0,str(PROJECT/'Python'))
    import opening_graph as og
    profile_class=unreal.load_class(None,PROFILE_CLASS)
    profile=unreal.GameplayStatics.create_save_game_object(profile_class)
    for name in ['MasterVolume','AmbienceVolume','MusicVolume','MuteWhenPaused']:
        profile.get_editor_property(name)
    fixture=og.blueprint('/Temp/BP_SaveGuardFixture_'+STAMP,unreal.Actor)
    graph=og.function(fixture,'SetPointer',inputs={'Target':og.object_type(PROFILE_CLASS),'Slot':'string'})
    setter=graph.set('ActiveSlot',graph.input('Slot'),owner=graph.input('Target'),class_path=PROFILE_CLASS)
    og.link(graph.entry,og.pin_in(setter));og.compile_bp(fixture,save=False)
    fixture_cdo=unreal.get_default_object(og.L.generated_class(fixture))
    def pointed(value):
        obj=unreal.GameplayStatics.create_save_game_object(profile_class)
        fixture_cdo.call_method('SetPointer',args=(obj,value));return obj
    first,second=pointed('QA_First'),pointed('QA_Second')
    slot=PREFIX+'Roundtrip'
    check('New QA slot is physically unoccupied',not exists(slot))
    check('First guarded14-field profile save succeeds',save(first,slot))
    initial=file(slot).read_bytes()
    check('Actual file has versioned guard magic instead of raw GVAS',initial[:8]==b'YDAYSG01')
    loaded=load(slot)
    check('Actual profile object and values roundtrip',loaded is not None and str(loaded.get_editor_property('ActiveSlot'))=='QA_First' and abs(float(loaded.get_editor_property('MasterVolume'))-.8)<.0001)
    check('Second guarded save succeeds',save(second,slot))
    backup=Path(str(file(slot))+'.bak')
    check('Previous verified checkpoint exists as exact backup',backup.exists() and backup.read_bytes()==initial)
    check('Current checkpoint loads separately',str(load(slot).get_editor_property('ActiveSlot'))=='QA_Second')
    raw_cases={'Empty':b'', 'KnownFatalGenericBytes':b'Invalid isolated QA save; never a player file',
               'RawGVAS':b'GVAS'+b'\xff'*128, 'TooLarge':b'X'*(262144+49),
               'Truncated':initial[:47], 'PayloadBitFlip':initial[:-1]+bytes([initial[-1]^1])}
    for name,raw in raw_cases.items():
        bad=PREFIX+name; path=file(bad)
        if path.exists():raise RuntimeError('Refusing occupied QA fault slot')
        path.write_bytes(raw);digest=sha(path)
        check(name+': physical occupancy is retained',exists(bad))
        check(name+': actual native load rejects without deserializing garbage',load(bad) is None)
        check(name+': invalid original cannot be overwritten',not save(first,bad) and sha(path)==digest)
    check('Invalid path and Windows device names fail closed',exists('../outside') and exists('CON') and not call('SafeSaveGameToSlot',first,'CON',0))
    check('Nonzero platform user fails closed',call('SafeLoadGameFromSlot',slot,1) is None)
    # Damaged primary/valid backup must not authorize an overwrite.
    file(slot).write_bytes(raw_cases['KnownFatalGenericBytes']);corrupt_sha=sha(file(slot));backup_sha=sha(backup)
    recovered=load(slot)
    result=str(call('GetLastSaveGuardResult'))
    check('Valid previous checkpoint is actually recovered',recovered is not None and str(recovered.get_editor_property('ActiveSlot'))=='QA_First' and 'RECOVERED_BACKUP' in result.upper())
    check('Recovery loading preserves both original files',sha(file(slot))==corrupt_sha and sha(backup)==backup_sha)
    check('Recovered data cannot overwrite its corrupt primary',not save(recovered,slot) and sha(file(slot))==corrupt_sha and sha(backup)==backup_sha)
    recovered_slot=PREFIX+'SeparateRecovery'
    check('A separate recovery slot can save and reload the verified object',save(recovered,recovered_slot) and str(load(recovered_slot).get_editor_property('ActiveSlot'))=='QA_First')
    backup.write_bytes(b'Invalid isolated QA backup');both={str(p):sha(p) for p in [file(slot),backup]}
    check('Both damaged files return recoverably without becoming unoccupied',load(slot) is None and exists(slot))
    check('Both damaged files remain byte-identical after refused write',not save(first,slot) and all(sha(Path(p))==digest for p,digest in both.items()))
    # Invalid backup evidence is retained while a valid primary can advance.
    slot2=PREFIX+'BadBackup';check('Backup fixture primary writes',save(first,slot2) and save(second,slot2))
    backup2=Path(str(file(slot2))+'.bak');bad_backup=b'Preserve this invalid recovery evidence'
    backup2.write_bytes(bad_backup)
    check('Valid primary advances while preserving invalid backup evidence',save(first,slot2) and any(p.read_bytes()==bad_backup for p in SAVE.glob(file(slot2).name+'.rejected_*')))
    check('Replacement backup contains the last valid primary',str(load(slot2).get_editor_property('ActiveSlot'))=='QA_First' and backup2.exists())
    # A held primary handle blocks Windows replacement; old bytes must survive.
    prior=sha(file(slot2))
    with file(slot2).open('rb') as held:
        held.read(1)
        check('Actual Windows replacement failure returns false and retains primary',not save(second,slot2) and sha(file(slot2))==prior)
    check('Valid checkpoint still loads after replacement failure',str(load(slot2).get_editor_property('ActiveSlot'))=='QA_First')
    # Explicit migration is the ONLY guarded route through raw GVAS decoding.
    source=PROJECT.parent.parent/'Brief_20261025/game_unreal/Saved/SaveGames/Yesterday_Automation_A_v1_20261024T151953_576332_FirstPerson.sav'
    digest='0f698bb9c4a003a7aa2883af39317161a1e38290ca388626231bce5f1caf94e8'
    check('Protected trusted legacy fixture still has the approved hash',sha(source)==digest)
    raw_slot=PREFIX+'PinnedRaw';file(raw_slot).write_bytes(source.read_bytes())
    destination=PREFIX+'ImportedV1'
    check('Exact approved legacy fixture imports to a separate envelope',call('ImportPinnedLegacyFixture',raw_slot,destination,0) and file(destination).read_bytes()[:8]==b'YDAYSG01')
    old=load(destination)
    check('Imported actual campaign retains v1 schema and source bytes',old is not None and int(old.get_editor_property('SchemaVersion'))==1 and sha(file(raw_slot))==digest and sha(source)==digest)
    check('Pinned import never replaces an occupied destination',not call('ImportPinnedLegacyFixture',raw_slot,destination,0))
    altered=PREFIX+'WrongLegacy';file(altered).write_bytes(source.read_bytes()+b'X')
    check('Unapproved legacy bytes are rejected before native archive parsing',not call('ImportPinnedLegacyFixture',altered,PREFIX+'NeverCreated',0) and not file(PREFIX+'NeverCreated').exists())
    REPORT['native_executed']=True
    REPORT['protected_saves_unchanged']=all(sha(Path(p))==h for p,h in before_saves.items())
    REPORT['protected_assets_unchanged']=all(sha(Path(p))==h for p,h in before_assets.items())
    check('Existing assets/config/maps/saves are preserved',REPORT['protected_saves_unchanged'] and REPORT['protected_assets_unchanged'])
    REPORT['success']=True;write()


if __name__=='__main__':
    try:main()
    except Exception:REPORT['error']=traceback.format_exc();write();unreal.log_error(REPORT['error'])
    unreal.SystemLibrary.quit_editor()
