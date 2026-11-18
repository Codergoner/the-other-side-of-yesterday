"""Prepare reviewed 59-field identity guard source; never launches native tools.

Default writes a reviewable candidate/diff only. Root may pass --apply after
phase-one native integration and route acceptance have actually passed. The
activated plugin tree is never changed by this tool; compile/verify/stage is
still required afterwards. Existing envelope/profile versions stay unchanged.
"""
from pathlib import Path
import argparse
import difflib
import hashlib
import json

RELEASE = Path(__file__).resolve().parents[1]
PLUGIN = RELEASE / 'native_save_guard/YesterdaySaveGuard'
CPP = PLUGIN / 'Source/YesterdaySaveGuard/Private/YesterdaySaveGuardLibrary.cpp'
DESCRIPTOR = PLUGIN / 'YesterdaySaveGuard.uplugin'


def once(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError('Review changed native identity migration anchor: ' + old[:110])
    return source.replace(old, new)


def candidate(source):
    old_condition = 'if (Kind == TEXT("campaign-v1") || Kind == TEXT("campaign-v2"))'
    if source.count(old_condition) != 2:
        raise RuntimeError('Exactly the reviewed schema/class conditions are required')
    source = source.replace(old_condition, 'if (Kind == TEXT("campaign-v1") || Kind == TEXT("campaign-v2") || Kind == TEXT("campaign-v3"))')
    source = once(source, 'if (Kind == TEXT("campaign-v2"))\n        {',
                  'if (Kind == TEXT("campaign-v2") || Kind == TEXT("campaign-v3"))\n        {')
    source = once(source, '''            Add(TEXT("MotherJourneyIntention"), 'I');
        }
''', '''            Add(TEXT("MotherJourneyIntention"), 'I');
        }
        if (Kind == TEXT("campaign-v3"))
        {
            Add(TEXT("IdentitySceneSeen,IdentityCustodianAccepted"), 'B');
            Add(TEXT("IdentityRecordMethod"), 'I');
        }
''')
    source = once(source, '''    if (Kind == TEXT("campaign-v1"))
    {
        // Validate the complete legacy input before migration. The expanded
        // class is itself still a closed, exactly typed 56-field schema.
        // Decode imports only the original 53 fields. The three new fields
        // retain reviewed defaults (false/false/0) instead of fabricating a
        // prior observation or promise from progress in an older build.
        TArray<FProperty*> Expanded;
        if (Collect(Class, Schema(TEXT("campaign-v2")), Expanded))
''', '''    if (Kind == TEXT("campaign-v1") || Kind == TEXT("campaign-v2"))
    {
        // Input was validated against its exact original 53/56-field schema.
        // The destination must independently match a complete reviewed schema.
        // Import only incoming fields; new observation/consent defaults remain
        // empty. Merely having an old register must not imply public consent.
        TArray<FProperty*> Expanded;
        bool IsExpanded = Collect(Class, Schema(TEXT("campaign-v3")), Expanded);
        if (!IsExpanded)
        {
            Expanded.Reset();
            IsExpanded = Collect(Class, Schema(TEXT("campaign-v2")), Expanded);
        }
        if (IsExpanded)
''')
    source = once(source, 'for (const TCHAR* Name : {TEXT("PublicChronologyObserved"), TEXT("OrderRegisterObserved")})',
                  'for (const TCHAR* Name : {TEXT("PublicChronologyObserved"), TEXT("OrderRegisterObserved"), TEXT("IdentitySceneSeen"), TEXT("IdentityCustodianAccepted")})')
    source = once(source, '''    if (FIntProperty* P = FindFProperty<FIntProperty>(Class, TEXT("MotherJourneyIntention")))
        P->SetPropertyValue_InContainer(Save, 0);
''', '''    for (const TCHAR* Name : {TEXT("MotherJourneyIntention"), TEXT("IdentityRecordMethod")})
        if (FIntProperty* P = FindFProperty<FIntProperty>(Class, Name))
            P->SetPropertyValue_InContainer(Save, 0);
''')
    source = once(source, '''        // Also permits the reviewed pre-integration 53-field class during the
        // serialized native upgrade. Never emits a partially expanded shape.
        Kind = Collect(Save->GetClass(), Schema(TEXT("campaign-v2")), Expanded)
            ? TEXT("campaign-v2") : TEXT("campaign-v1");
''', '''        // Serialized upgrades can temporarily retain a reviewed older class;
        // encoding always emits the matching complete, exact schema.
        if (Collect(Save->GetClass(), Schema(TEXT("campaign-v3")), Expanded)) Kind = TEXT("campaign-v3");
        else
        {
            Expanded.Reset();
            Kind = Collect(Save->GetClass(), Schema(TEXT("campaign-v2")), Expanded)
                ? TEXT("campaign-v2") : TEXT("campaign-v1");
        }
''')
    source = once(source, '''    if (!TestTrue(TEXT("Expanded campaign has the closed 56-field schema"), Collect(Class, Schema(TEXT("campaign-v2")), Current))) return false;
''', '''    bool CurrentValid = Collect(Class, Schema(TEXT("campaign-v3")), Current);
    if (!CurrentValid) { Current.Reset(); CurrentValid = Collect(Class, Schema(TEXT("campaign-v2")), Current); }
    if (!TestTrue(TEXT("Current campaign matches its complete reviewed schema"), CurrentValid)) return false;
''')
    source = once(source, '''    Fields->RemoveField(TEXT("MotherJourneyIntention"));
''', '''    Fields->RemoveField(TEXT("MotherJourneyIntention"));
    Fields->RemoveField(TEXT("IdentitySceneSeen"));
    Fields->RemoveField(TEXT("IdentityCustodianAccepted"));
    Fields->RemoveField(TEXT("IdentityRecordMethod"));
''')
    source = once(source, '\n#endif\n', IDENTITY_TEST + '\n#endif\n')
    return source


IDENTITY_TEST = r'''
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYesterdayGuardIdentityMigrationTest,
    "Yesterday.SaveGuard.IdentityV2Migration",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FYesterdayGuardIdentityMigrationTest::RunTest(const FString& Parameters)
{
    using namespace YesterdayGuard;
    UClass* Class = LoadClass<USaveGame>(nullptr, ClassPath(TEXT("campaign-v3")));
    if (!TestNotNull(TEXT("Actual campaign class required"), Class)) return false;
    TArray<FProperty*> Properties;
    if (!TestTrue(TEXT("Identity campaign is exactly the reviewed 59-field class"), Collect(Class, Schema(TEXT("campaign-v3")), Properties))) return false;
    TestEqual(TEXT("First guarded campaign remains 53 fields"), Schema(TEXT("campaign-v1")).Num(), 53);
    TestEqual(TEXT("Chronology revision remains 56 fields"), Schema(TEXT("campaign-v2")).Num(), 56);
    TestEqual(TEXT("Identity revision requires all 59 fields"), Schema(TEXT("campaign-v3")).Num(), 59);
    FBoolProperty* Seen = FindFProperty<FBoolProperty>(Class, TEXT("IdentitySceneSeen"));
    FBoolProperty* Custody = FindFProperty<FBoolProperty>(Class, TEXT("IdentityCustodianAccepted"));
    FIntProperty* Method = FindFProperty<FIntProperty>(Class, TEXT("IdentityRecordMethod"));
    FBoolProperty* Record = FindFProperty<FBoolProperty>(Class, TEXT("OrderRegisterObserved"));
    FIntProperty* Intention = FindFProperty<FIntProperty>(Class, TEXT("MotherJourneyIntention"));
    if (!TestNotNull(TEXT("Actual identity seen bool"), Seen) || !TestNotNull(TEXT("Actual custody bool"), Custody) ||
        !TestNotNull(TEXT("Actual identity method int"), Method) || !TestNotNull(TEXT("Actual record bool"), Record) ||
        !TestNotNull(TEXT("Actual journey intention int"), Intention)) return false;
    USaveGame* Source = NewObject<USaveGame>(GetTransientPackage(), Class);
    Seen->SetPropertyValue_InContainer(Source, true);
    Custody->SetPropertyValue_InContainer(Source, true);
    Method->SetPropertyValue_InContainer(Source, 2);
    Record->SetPropertyValue_InContainer(Source, true);
    Intention->SetPropertyValue_InContainer(Source, 3);
    TArray<uint8> Good;
    if (!TestTrue(TEXT("Actual 59-field state encodes"), Encode(Source, Good))) return false;
    USaveGame* Current = Decode(Good);
    if (!TestNotNull(TEXT("Actual identity state decodes"), Current)) return false;
    TestTrue(TEXT("Seen and keeper acceptance persist"), Seen->GetPropertyValue_InContainer(Current) && Custody->GetPropertyValue_InContainer(Current));
    TestEqual(TEXT("Sealed method persists"), Method->GetPropertyValue_InContainer(Current), 2);
    const FUTF8ToTCHAR Text(reinterpret_cast<const ANSICHAR*>(Good.GetData()+HeaderSize), Good.Num()-HeaderSize);
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(FString(Text.Length(), Text.Get())), Root)) return false;
    const TSharedPtr<FJsonObject>* Pointer = nullptr;
    if (!Root->TryGetObjectField(TEXT("fields"), Pointer)) return false;
    TSharedPtr<FJsonObject> Fields = *Pointer;
    Root->SetStringField(TEXT("kind"), TEXT("campaign-v2"));
    Fields->RemoveField(TEXT("IdentitySceneSeen"));
    Fields->RemoveField(TEXT("IdentityCustodianAccepted"));
    Fields->RemoveField(TEXT("IdentityRecordMethod"));
    auto Envelope = [&Root]()
    {
        FString Json; FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Json));
        const FTCHARToUTF8 Utf8(*Json);
        TArray<uint8> Bytes; Bytes.SetNumZeroed(HeaderSize+Utf8.Length());
        FMemory::Memcpy(Bytes.GetData(), Magic, 8); Write32(Bytes.GetData()+8, 1); Write32(Bytes.GetData()+12, Utf8.Length());
        FMemory::Memcpy(Bytes.GetData()+HeaderSize, Utf8.Get(), Utf8.Length());
        FBlake3 H; H.Update(Bytes.GetData(), 16); H.Update(Bytes.GetData()+HeaderSize, Utf8.Length());
        const auto Digest=H.Finalize(); FMemory::Memcpy(Bytes.GetData()+16, Digest.GetBytes(), 32); return Bytes;
    };
    TArray<uint8> Old = Envelope(); const TArray<uint8> Original = Old;
    USaveGame* Migrated = Decode(Old);
    if (!TestNotNull(TEXT("Exact chronology-only campaign migrates"), Migrated)) return false;
    TestTrue(TEXT("Migration does not rewrite input bytes"), Old==Original);
    TestTrue(TEXT("Actual observed V-17 record stays observed"), Record->GetPropertyValue_InContainer(Migrated));
    TestEqual(TEXT("Actual selected journey intention survives"), Intention->GetPropertyValue_InContainer(Migrated), 3);
    TestFalse(TEXT("Legacy record does not invent meeting the worker"), Seen->GetPropertyValue_InContainer(Migrated));
    TestFalse(TEXT("Legacy record does not invent a keeper accepting custody"), Custody->GetPropertyValue_InContainer(Migrated));
    TestEqual(TEXT("Legacy record defaults to UNASKED anonymous"), Method->GetPropertyValue_InContainer(Migrated), 0);
    Fields->SetBoolField(TEXT("UnexpectedConsent"), true);
    TestNull(TEXT("Unknown migration field fails closed"), Decode(Envelope()));
    Fields->RemoveField(TEXT("UnexpectedConsent"));
    Root->SetStringField(TEXT("kind"), TEXT("campaign-v3"));
    TestNull(TEXT("A new campaign cannot omit consent fields"), Decode(Envelope()));
    Fields->SetBoolField(TEXT("IdentitySceneSeen"), true);
    Fields->SetBoolField(TEXT("IdentityCustodianAccepted"), true);
    Fields->SetStringField(TEXT("IdentityRecordMethod"), TEXT("SEALED"));
    TestNull(TEXT("Wrong new consent field type fails closed"), Decode(Envelope()));
    return true;
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    original = CPP.read_text(encoding='utf-8-sig')
    revised = candidate(original)
    descriptor = json.loads(DESCRIPTOR.read_text(encoding='utf-8-sig'))
    if descriptor['Version'] != 3 or descriptor['VersionName'] != '0.2.0-story-v02':
        raise RuntimeError('Review the phase-one descriptor before preparing its next version')
    descriptor.update(Version=4, VersionName='0.2.1-identity-v02',
        Description='Strict bounded campaign-v3 snapshots with exact 53/56-field migration to the reviewed 59-field consent state. Old records never imply publication, meeting a worker, or accepted sealed-note custody. Envelope and profile versions remain unchanged; native build/test evidence is separate.')
    out = RELEASE / 'output/identity_guard_candidate'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'YesterdaySaveGuardLibrary.cpp').write_text(revised, encoding='utf-8')
    (out / 'YesterdaySaveGuard.uplugin').write_text(json.dumps(descriptor, indent=2) + '\n', encoding='utf-8')
    (out / 'identity_guard.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True), revised.splitlines(True), fromfile=str(CPP), tofile=str(CPP))), encoding='utf-8')
    if args.apply:
        proof_path = RELEASE / 'game_unreal/quest_story_v02_runtime_validation.json'
        proof = json.loads(proof_path.read_text(encoding='utf-8'))
        if not proof.get('success'):
            raise RuntimeError('Root must complete actual phase-one route acceptance before this source promotion')
        if proof.get('quest_v02_source_sha256') != hashlib.sha256((RELEASE / 'game_unreal/Python/validate_quest_story_v02.py').read_bytes()).hexdigest():
            raise RuntimeError('Phase-one proof does not match the actual current validator source')
        CPP.write_text(revised, encoding='utf-8')
        DESCRIPTOR.write_text(json.dumps(descriptor, indent=2) + '\n', encoding='utf-8')
    report = {'candidate_prepared': True, 'canonical_applied': args.apply,
              'native_compiled': False, 'native_tests_run': False, 'activated_plugin_changed': False,
              'original_cpp_sha256': hashlib.sha256(original.encode()).hexdigest(),
              'candidate_cpp_sha256': hashlib.sha256(revised.encode()).hexdigest(),
              'requires_next': 'Actual BuildSaveGuard.ps1 + VerifySaveGuardBuild.ps1 + StageSaveGuard.ps1 before identity asset installer'}
    (out / 'preparation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
