#include "YesterdaySaveGuardLibrary.h"
#include "GameFramework/SaveGame.h"
#include "Kismet/GameplayStatics.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Containers/StringConv.h"
#include "GenericPlatform/GenericPlatformFile.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformMisc.h"
#include "Hash/Blake3.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "UObject/UnrealType.h"
#include "UObject/Package.h"
#if PLATFORM_WINDOWS
#include "Windows/WindowsHWrapper.h"
#include "Windows/AllowWindowsPlatformTypes.h"
#include <bcrypt.h>
#include "Windows/HideWindowsPlatformTypes.h"
#else
// Android (Meta Quest 3) and other POSIX targets: advisory file locks and atomic rename.
#include <cerrno>
#include <cstdio>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace YesterdayGuard
{
// No native struct layout, FString archive, FName or arbitrary class name is
// decoded from the file. Header numbers are explicit little endian bytes.
constexpr uint8 Magic[8] = {'Y','D','A','Y','S','G','0','1'};
constexpr int32 HeaderSize = 48;
constexpr int32 MaxPayload = 256 * 1024;
constexpr int32 MaxString = 4096;
constexpr int32 MaxArray = 256;
constexpr int32 MaxFields = 64;
EYesterdaySaveGuardResult LastResult = EYesterdaySaveGuardResult::Missing;
FString LastMessage = TEXT("No save operation yet.");

void Result(EYesterdaySaveGuardResult Code, const TCHAR* Text)
{
    LastResult = Code;
    LastMessage = Text;
}

bool SlotPath(const FString& Slot, int32 UserIndex, FString& Out)
{
    if (!IsInGameThread() || UserIndex != 0 || Slot.IsEmpty() || Slot.Len() > 128)
        return false;
    for (TCHAR C : Slot)
        if (!((C >= 'a' && C <= 'z') || (C >= 'A' && C <= 'Z') ||
              (C >= '0' && C <= '9') || C == '_' || C == '-')) return false;
    const FString Upper = Slot.ToUpper();
    if (Upper == TEXT("CON") || Upper == TEXT("PRN") || Upper == TEXT("AUX") || Upper == TEXT("NUL") ||
        (Upper.Len() == 4 && (Upper.StartsWith(TEXT("COM")) || Upper.StartsWith(TEXT("LPT"))) && Upper[3] >= '1' && Upper[3] <= '9')) return false;
    Out = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("SaveGames"), Slot + TEXT(".sav")));
    return true;
}

#if PLATFORM_WINDOWS
FString NativePath(FString Path)
{
    // UE paths use '/', while extended-length Win32 paths require '\\'.
    // The workspace/UserDir plus GUID slot can exceed MAX_PATH.
    Path.ReplaceInline(TEXT("/"), TEXT("\\"));
    if (Path.StartsWith(TEXT("\\\\?\\"))) return Path;
    if (Path.StartsWith(TEXT("\\\\"))) return TEXT("\\\\?\\UNC\\") + Path.Mid(2);
    return TEXT("\\\\?\\") + Path;
}

// Excludes parallel editor/packaged writers that also use this guard. External
// programs are outside this contract. OPEN_ALWAYS does not truncate any save.
struct FDirectoryLock
{
    HANDLE Handle = INVALID_HANDLE_VALUE;
    explicit FDirectoryLock(const FString& SavePath)
    {
        IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
        const FString Dir = FPaths::GetPath(SavePath);
        if (PF.CreateDirectoryTree(*Dir))
            Handle = ::CreateFileW(*NativePath(Dir / TEXT("YesterdaySaveGuard.lock")), GENERIC_READ | GENERIC_WRITE,
                0, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_DELETE_ON_CLOSE, nullptr);
    }
    ~FDirectoryLock() { if (Handle != INVALID_HANDLE_VALUE) ::CloseHandle(Handle); }
    bool IsValid() const { return Handle != INVALID_HANDLE_VALUE; }
};
#else
FString NativePath(FString Path)
{
    // POSIX paths are used as the engine formats them; no extended-length prefix exists.
    return Path;
}

// Same contract on POSIX targets (Android / Meta Quest 3): an exclusive, non-blocking advisory
// flock on the same lock file. The lock releases with the descriptor, also on process death.
// The empty lock file is deliberately left in place: unlinking it could let a later writer lock a
// fresh inode while another process still holds the old one.
struct FDirectoryLock
{
    int Fd = -1;
    explicit FDirectoryLock(const FString& SavePath)
    {
        IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
        const FString Dir = FPaths::GetPath(SavePath);
        if (PF.CreateDirectoryTree(*Dir))
        {
            const FString LockPath = Dir / TEXT("YesterdaySaveGuard.lock");
            Fd = ::open(TCHAR_TO_UTF8(*LockPath), O_RDWR | O_CREAT | O_CLOEXEC, 0600);
            if (Fd >= 0 && ::flock(Fd, LOCK_EX | LOCK_NB) != 0)
            {
                ::close(Fd);
                Fd = -1;
            }
        }
    }
    ~FDirectoryLock()
    {
        if (Fd >= 0)
        {
            ::flock(Fd, LOCK_UN);
            ::close(Fd);
        }
    }
    bool IsValid() const { return Fd >= 0; }
};
#endif

bool Exists(const FString& Path)
{
    return FPlatformFileManager::Get().GetPlatformFile().FileExists(*Path);
}

// Portable SHA-256 (FIPS 180-4) for targets without Windows CNG (Android / Meta Quest 3). It is
// compiled on every platform so the host automation test exercises exactly the code the headset
// runs against the published test vectors; Win64 production keeps the CNG path below unchanged.
struct FPortableSha256
{
    static uint32 Rotr(uint32 X, uint32 N) { return (X >> N) | (X << (32 - N)); }
    static void Compress(uint32 State[8], const uint8 Block[64])
    {
        static const uint32 K[64] = {
            0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
            0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
            0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
            0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
            0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
            0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
            0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
            0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u, 0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u };
        uint32 W[64];
        for (int32 I = 0; I < 16; ++I)
            W[I] = uint32(Block[I * 4]) << 24 | uint32(Block[I * 4 + 1]) << 16 | uint32(Block[I * 4 + 2]) << 8 | uint32(Block[I * 4 + 3]);
        for (int32 I = 16; I < 64; ++I)
        {
            const uint32 S0 = Rotr(W[I - 15], 7) ^ Rotr(W[I - 15], 18) ^ (W[I - 15] >> 3);
            const uint32 S1 = Rotr(W[I - 2], 17) ^ Rotr(W[I - 2], 19) ^ (W[I - 2] >> 10);
            W[I] = W[I - 16] + S0 + W[I - 7] + S1;
        }
        uint32 A = State[0], B = State[1], C = State[2], D = State[3], E = State[4], F = State[5], G = State[6], H = State[7];
        for (int32 I = 0; I < 64; ++I)
        {
            const uint32 T1 = H + (Rotr(E, 6) ^ Rotr(E, 11) ^ Rotr(E, 25)) + ((E & F) ^ (~E & G)) + K[I] + W[I];
            const uint32 T2 = (Rotr(A, 2) ^ Rotr(A, 13) ^ Rotr(A, 22)) + ((A & B) ^ (A & C) ^ (B & C));
            H = G; G = F; F = E; E = D + T1; D = C; C = B; B = A; A = T1 + T2;
        }
        State[0] += A; State[1] += B; State[2] += C; State[3] += D; State[4] += E; State[5] += F; State[6] += G; State[7] += H;
    }
    static void Digest(const uint8* Data, int32 Num, uint8 Out[32])
    {
        uint32 State[8] = { 0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au, 0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u };
        int32 Offset = 0;
        for (; Offset + 64 <= Num; Offset += 64) Compress(State, Data + Offset);
        uint8 Tail[128] = { 0 };
        const int32 Remaining = Num - Offset;
        if (Remaining > 0) FMemory::Memcpy(Tail, Data + Offset, Remaining);
        Tail[Remaining] = 0x80;
        const int32 TailBlocks = (Remaining + 1 + 8 > 64) ? 2 : 1;
        const uint64 Bits = uint64(Num) * 8u;
        for (int32 I = 0; I < 8; ++I) Tail[TailBlocks * 64 - 1 - I] = uint8(Bits >> (8 * I));
        Compress(State, Tail);
        if (TailBlocks == 2) Compress(State, Tail + 64);
        for (int32 I = 0; I < 8; ++I)
        {
            Out[I * 4] = uint8(State[I] >> 24); Out[I * 4 + 1] = uint8(State[I] >> 16);
            Out[I * 4 + 2] = uint8(State[I] >> 8); Out[I * 4 + 3] = uint8(State[I]);
        }
    }
};

bool HashLegacyFixtureSha256(TArray<uint8>& Bytes, FSHA256Signature& OutSignature)
{
    // FGenericPlatformMisc::GetSHA256Signature is an asserting stub on this
    // installed Windows engine. Use the verified Windows CNG API instead.
    // Inputs are already file-size bounded; every error fails closed before
    // the sole trusted legacy archive decoder is reached.
    if (Bytes.Num() <= 0 || Bytes.Num() > MaxPayload + HeaderSize) return false;
#if !PLATFORM_WINDOWS
    FPortableSha256::Digest(Bytes.GetData(), Bytes.Num(), OutSignature.Signature);
    return true;
#else
    BCRYPT_ALG_HANDLE Algorithm = nullptr;
    BCRYPT_HASH_HANDLE Hash = nullptr;
    NTSTATUS Status = ::BCryptOpenAlgorithmProvider(&Algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0);
    if (Status < 0) return false;
    // Windows7+ can allocate/free the internal hash object for this call pair.
    // The game's supported Windows version is newer; no custom crypto code.
    Status = ::BCryptCreateHash(Algorithm, &Hash, nullptr, 0, nullptr, 0, 0);
    if (Status >= 0) Status = ::BCryptHashData(Hash, Bytes.GetData(), static_cast<ULONG>(Bytes.Num()), 0);
    if (Status >= 0) Status = ::BCryptFinishHash(Hash, OutSignature.Signature, sizeof(OutSignature.Signature), 0);
    if (Hash)
    {
        const NTSTATUS Cleanup = ::BCryptDestroyHash(Hash);
        if (Cleanup < 0) Status = Cleanup;
    }
    const NTSTATUS Cleanup = ::BCryptCloseAlgorithmProvider(Algorithm, 0);
    if (Cleanup < 0) Status = Cleanup;
    return Status >= 0;
#endif
}

bool ReadBounded(const FString& Path, TArray<uint8>& Out)
{
    TUniquePtr<IFileHandle> File(FPlatformFileManager::Get().GetPlatformFile().OpenRead(*Path));
    if (!File) return false;
    const int64 Size = File->Size();
    if (Size <= 0 || Size > MaxPayload + HeaderSize) return false;
    Out.SetNumUninitialized(static_cast<int32>(Size));
    return File->Read(Out.GetData(), Size) && File->Size() == Size;
}

uint32 Read32(const uint8* P)
{
    return uint32(P[0]) | uint32(P[1]) << 8 | uint32(P[2]) << 16 | uint32(P[3]) << 24;
}
void Write32(uint8* P, uint32 V)
{
    for (int32 I = 0; I < 4; ++I) P[I] = static_cast<uint8>(V >> (8 * I));
}

bool JsonBudget(const uint8* P, int32 Size)
{
    // Bound recursion and string work BEFORE the JSON parser. Parser still
    // validates syntax/escapes/number syntax. No input is converted to FName.
    int32 Depth = 0, StringBytes = 0, Tokens = 0;
    bool InString = false, Escaped = false;
    for (int32 I = 0; I < Size; ++I)
    {
        const uint8 C = P[I];
        if (!C) return false;
        if (InString)
        {
            if (++StringBytes > MaxString * 6) return false;
            if (C < 0x20) return false;
            if (Escaped) { Escaped = false; continue; }
            if (C == '\\') { Escaped = true; continue; }
            if (C == '"') InString = false;
        }
        else if (C == '"') { InString = true; StringBytes = 0; ++Tokens; }
        else if (C == '{' || C == '[') { if (++Depth > 4) return false; ++Tokens; }
        else if (C == '}' || C == ']') { if (--Depth < 0) return false; }
        else if (C == ',') ++Tokens;
        if (Tokens > 4096) return false;
    }
    return !InString && Depth == 0;
}

// A deliberately closed schema. Additions require source review; unsupported
// structs, objects, maps, names and delegates never reach reflection import.
TMap<FString, TCHAR> Schema(const FString& Kind)
{
    TMap<FString, TCHAR> Out;
    auto Add = [&Out](const TCHAR* Names, TCHAR Type)
    {
        TArray<FString> Parts;
        FString(Names).ParseIntoArray(Parts, TEXT(","), true);
        for (const FString& Name : Parts) Out.Add(Name, Type);
    };
    if (Kind == TEXT("campaign-v1") || Kind == TEXT("campaign-v2") || Kind == TEXT("campaign-v3"))
    {
        Add(TEXT("HomeExplored,PhotoSeen,PhotoBackSeen,LetterRead,MotherMet,MotherSpoken,MotherPromise,RepairIdentified,ComponentCollected,ComponentPlaced,WatchCalibrated,AnchorActivated,DrawerOpen,IntroSeen,PhotoExchangeDone,LetterExchangeDone,OriginalMemorialRead,DepartureDone,NeriMet,HealerMet,HealerTaskOffered,SelaMet,WaterTaken,LinenBundleReady,LinenThanksDone,CanvasRequestKnown,CanvasOffered,CanvasOwned,HealerReportDone,ConsequenceObserved,Chapter2Complete,HasDeparted,HasReturned,ReturnSignalActive,ClinicInspected,HarborInspected"), 'B');
        Add(TEXT("Chapter,SchemaVersion,MotherOpeningResponse,EraIndex,LinenState,CanvasPlan,StormCover,CurrentChapter,HealerTrust,CalibrationTests,FinalResponse"), 'I');
        Add(TEXT("Era,SafeLocationId,PriorTimelineObservation,LatestTimelineObservation"), 'S');
        Add(TEXT("ReturnClockSeconds"), 'R');
        Add(TEXT("TrustEventIds"), 'A');
        if (Kind == TEXT("campaign-v2") || Kind == TEXT("campaign-v3"))
        {
            // Additive authored story revision. These are observations and an
            // explicitly selected intention, not inferred old-save knowledge.
            Add(TEXT("PublicChronologyObserved,OrderRegisterObserved"), 'B');
            Add(TEXT("MotherJourneyIntention"), 'I');
        }
        if (Kind == TEXT("campaign-v3"))
        {
            Add(TEXT("IdentitySceneSeen,IdentityCustodianAccepted"), 'B');
            Add(TEXT("IdentityRecordMethod"), 'I');
        }
    }
    else if (Kind == TEXT("profile-v1"))
    {
        Add(TEXT("ActiveSlot"), 'S');
        Add(TEXT("ProfileVersion,ResolutionIndex,FrameCapIndex,SensitivityIndex"), 'I');
        Add(TEXT("Windowed,VSync,InvertY,LargeText,ReducedMotion,MuteWhenPaused"), 'B');
        Add(TEXT("MasterVolume,AmbienceVolume,MusicVolume"), 'R');
    }
    return Out;
}

const TCHAR* ClassPath(const FString& Kind)
{
    if (Kind == TEXT("campaign-v1") || Kind == TEXT("campaign-v2") || Kind == TEXT("campaign-v3")) return TEXT("/Game/Opening/Blueprints/BP_OpeningSave.BP_OpeningSave_C");
    if (Kind == TEXT("profile-v1")) return TEXT("/Game/Release/Blueprints/BP_ReleaseProfile.BP_ReleaseProfile_C");
    return nullptr;
}

bool PropertyType(FProperty* P, TCHAR Type)
{
    if (P->ArrayDim != 1) return false;
    if (Type == 'B') return P->IsA<FBoolProperty>();
    if (Type == 'I') return P->IsA<FIntProperty>();
    if (Type == 'S') return P->IsA<FStrProperty>();
    if (Type == 'R') return P->IsA<FDoubleProperty>() || P->IsA<FFloatProperty>();
    const FArrayProperty* A = CastField<FArrayProperty>(P);
    return Type == 'A' && A && A->Inner->IsA<FStrProperty>();
}

bool Collect(UClass* Class, const TMap<FString, TCHAR>& Allowed, TArray<FProperty*>& Out)
{
    if (!Class || !Class->IsChildOf(USaveGame::StaticClass()) || Allowed.Num() > MaxFields) return false;
    for (TFieldIterator<FProperty> It(Class, EFieldIteratorFlags::ExcludeSuper); It; ++It)
    {
        FProperty* P = *It;
        if (P->HasAnyPropertyFlags(CPF_Transient | CPF_Deprecated)) continue;
        const TCHAR* Type = Allowed.Find(P->GetName());
        if (!Type || !PropertyType(P, *Type)) return false;
        Out.Add(P);
    }
    return Out.Num() == Allowed.Num();
}

bool ValueValid(const TSharedPtr<FJsonValue>& V, TCHAR Type)
{
    if (!V) return false;
    if (Type == 'B') { bool B; return V->Type == EJson::Boolean && V->TryGetBool(B); }
    if (Type == 'S') { FString S; return V->Type == EJson::String && V->TryGetString(S) && S.Len() <= MaxString; }
    if (Type == 'I' || Type == 'R')
    {
        double N;
        if (V->Type != EJson::Number || !V->TryGetNumber(N) || !FMath::IsFinite(N)) return false;
        if (Type == 'I') return N >= MIN_int32 && N <= MAX_int32 && N == FMath::FloorToDouble(N);
        return FMath::Abs(N) <= 1.0e12;
    }
    if (Type != 'A' || V->Type != EJson::Array) return false;
    const auto& Array = V->AsArray();
    if (Array.Num() > MaxArray) return false;
    for (const auto& Item : Array) if (!ValueValid(Item, 'S')) return false;
    return true;
}

bool Parse(const TArray<uint8>& Bytes, UClass*& Class, TSharedPtr<FJsonObject>& Values, TArray<FProperty*>& Properties)
{
    if (Bytes.Num() < HeaderSize || FMemory::Memcmp(Bytes.GetData(), Magic, 8) != 0 || Read32(Bytes.GetData()+8) != 1) return false;
    const uint32 Size = Read32(Bytes.GetData()+12);
    if (Size == 0 || Size > MaxPayload || Size != uint32(Bytes.Num() - HeaderSize)) return false;
    FBlake3 Hash;
    Hash.Update(Bytes.GetData(), 16);
    Hash.Update(Bytes.GetData()+HeaderSize, Size);
    const FBlake3Hash Digest = Hash.Finalize();
    if (FMemory::Memcmp(Digest.GetBytes(), Bytes.GetData()+16, 32) != 0) return false;
    if (!JsonBudget(Bytes.GetData()+HeaderSize, Size)) return false;
    const FUTF8ToTCHAR Text(reinterpret_cast<const ANSICHAR*>(Bytes.GetData()+HeaderSize), Size);
    const FString Json(Text.Length(), Text.Get());
    TSharedPtr<FJsonObject> Root;
    const auto Reader = TJsonReaderFactory<>::Create(Json);
    FString Kind;
    const TSharedPtr<FJsonObject>* Fields = nullptr;
    if (!FJsonSerializer::Deserialize(Reader, Root) || !Root || Root->Values.Num() != 2 ||
        !Root->TryGetStringField(TEXT("kind"), Kind) || !Root->TryGetObjectField(TEXT("fields"), Fields)) return false;
    const TCHAR* Path = ClassPath(Kind);
    if (!Path) return false;
    const auto Allowed = Schema(Kind);
    Values = *Fields;
    if (!Values || Values->Values.Num() != Allowed.Num()) return false;
    // Query through the public FStringView API. UE5.8 JSON map keys use shared
    // string storage, not FString; no internal-key cast or FName is needed.
    // Exact count plus every required field also rejects unknown fields.
    for (const auto& Pair : Allowed)
    {
        if (!ValueValid(Values->TryGetField(Pair.Key), Pair.Value)) return false;
    }
    // Only a fixed, compiled-in path can be loaded; never an input class name.
    Class = LoadClass<USaveGame>(nullptr, Path);
    if (Kind == TEXT("campaign-v1") || Kind == TEXT("campaign-v2"))
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
        {
            for (FProperty* P : Expanded)
                if (Allowed.Contains(P->GetName())) Properties.Add(P);
            return Properties.Num() == Allowed.Num();
        }
    }
    return Collect(Class, Allowed, Properties);
}

USaveGame* Decode(const TArray<uint8>& Bytes)
{
    UClass* Class = nullptr;
    TSharedPtr<FJsonObject> Fields;
    TArray<FProperty*> Properties;
    if (!Parse(Bytes, Class, Fields, Properties)) return nullptr;
    USaveGame* Save = NewObject<USaveGame>(GetTransientPackage(), Class);
    // Canonical migration defaults are explicit; an accidental editor change
    // to a SaveGame CDO must not manufacture knowledge in an old campaign.
    for (const TCHAR* Name : {TEXT("PublicChronologyObserved"), TEXT("OrderRegisterObserved"), TEXT("IdentitySceneSeen"), TEXT("IdentityCustodianAccepted")})
        if (FBoolProperty* P = FindFProperty<FBoolProperty>(Class, Name))
            P->SetPropertyValue_InContainer(Save, false);
    for (const TCHAR* Name : {TEXT("MotherJourneyIntention"), TEXT("IdentityRecordMethod")})
        if (FIntProperty* P = FindFProperty<FIntProperty>(Class, Name))
            P->SetPropertyValue_InContainer(Save, 0);
    for (FProperty* P : Properties)
    {
        void* Data = P->ContainerPtrToValuePtr<void>(Save);
        const auto V = Fields->TryGetField(P->GetName());
        if (!V) return nullptr; // Parse already verified every closed-schema field.
        if (auto* B = CastField<FBoolProperty>(P)) B->SetPropertyValue(Data, V->AsBool());
        else if (auto* I = CastField<FIntProperty>(P)) I->SetPropertyValue(Data, static_cast<int32>(V->AsNumber()));
        else if (auto* S = CastField<FStrProperty>(P)) S->SetPropertyValue(Data, V->AsString());
        else if (auto* D = CastField<FDoubleProperty>(P)) D->SetPropertyValue(Data, V->AsNumber());
        else if (auto* F = CastField<FFloatProperty>(P)) F->SetPropertyValue(Data, static_cast<float>(V->AsNumber()));
        else if (auto* A = CastField<FArrayProperty>(P))
        {
            FScriptArrayHelper Helper(A, Data);
            Helper.Resize(V->AsArray().Num());
            FStrProperty* Inner = CastFieldChecked<FStrProperty>(A->Inner); // trusted reflected type checked in Collect
            for (int32 N = 0; N < Helper.Num(); ++N) Inner->SetPropertyValue(Helper.GetRawPtr(N), V->AsArray()[N]->AsString());
        }
    }
    return Save;
}

bool Encode(USaveGame* Save, TArray<uint8>& Bytes)
{
    if (!IsValid(Save)) return false;
    FString Kind;
    if (Save->GetClass()->GetPathName() == ClassPath(TEXT("campaign-v2")))
    {
        TArray<FProperty*> Expanded;
        // Serialized upgrades can temporarily retain a reviewed older class;
        // encoding always emits the matching complete, exact schema.
        if (Collect(Save->GetClass(), Schema(TEXT("campaign-v3")), Expanded)) Kind = TEXT("campaign-v3");
        else
        {
            Expanded.Reset();
            Kind = Collect(Save->GetClass(), Schema(TEXT("campaign-v2")), Expanded)
                ? TEXT("campaign-v2") : TEXT("campaign-v1");
        }
    }
    else if (Save->GetClass()->GetPathName() == ClassPath(TEXT("profile-v1"))) Kind = TEXT("profile-v1");
    if (Kind.IsEmpty()) return false;
    const auto Allowed = Schema(Kind);
    TArray<FProperty*> Properties;
    if (!Collect(Save->GetClass(), Allowed, Properties)) return false;
    auto Fields = MakeShared<FJsonObject>();
    for (FProperty* P : Properties)
    {
        const void* Data = P->ContainerPtrToValuePtr<void>(Save);
        TSharedPtr<FJsonValue> V;
        if (auto* B = CastField<FBoolProperty>(P)) V = MakeShared<FJsonValueBoolean>(B->GetPropertyValue(Data));
        else if (auto* I = CastField<FIntProperty>(P)) V = MakeShared<FJsonValueNumber>(I->GetPropertyValue(Data));
        else if (auto* S = CastField<FStrProperty>(P)) V = MakeShared<FJsonValueString>(S->GetPropertyValue(Data));
        else if (auto* D = CastField<FDoubleProperty>(P)) V = MakeShared<FJsonValueNumber>(D->GetPropertyValue(Data));
        else if (auto* F = CastField<FFloatProperty>(P)) V = MakeShared<FJsonValueNumber>(F->GetPropertyValue(Data));
        else if (auto* A = CastField<FArrayProperty>(P))
        {
            FScriptArrayHelper Helper(A, Data);
            if (Helper.Num() > MaxArray) return false;
            TArray<TSharedPtr<FJsonValue>> Array;
            auto* Inner = CastFieldChecked<FStrProperty>(A->Inner);
            for (int32 N = 0; N < Helper.Num(); ++N) Array.Add(MakeShared<FJsonValueString>(Inner->GetPropertyValue(Helper.GetRawPtr(N))));
            V = MakeShared<FJsonValueArray>(Array);
        }
        if (!ValueValid(V, Allowed.FindChecked(P->GetName()))) return false;
        Fields->SetField(P->GetName(), V);
    }
    auto Root = MakeShared<FJsonObject>();
    Root->SetStringField(TEXT("kind"), Kind);
    Root->SetObjectField(TEXT("fields"), Fields);
    FString Text;
    if (!FJsonSerializer::Serialize(Root, TJsonWriterFactory<>::Create(&Text))) return false;
    const FTCHARToUTF8 Utf8(*Text);
    if (Utf8.Length() <= 0 || Utf8.Length() > MaxPayload) return false;
    Bytes.SetNumZeroed(HeaderSize + Utf8.Length());
    FMemory::Memcpy(Bytes.GetData(), Magic, 8);
    Write32(Bytes.GetData()+8, 1);
    Write32(Bytes.GetData()+12, Utf8.Length());
    FMemory::Memcpy(Bytes.GetData()+HeaderSize, Utf8.Get(), Utf8.Length());
    FBlake3 Hash;
    Hash.Update(Bytes.GetData(), 16);
    Hash.Update(Bytes.GetData()+HeaderSize, Utf8.Length());
    const FBlake3Hash Digest = Hash.Finalize();
    FMemory::Memcpy(Bytes.GetData()+16, Digest.GetBytes(), 32);
    UClass* CheckClass = nullptr;
    TSharedPtr<FJsonObject> CheckFields;
    TArray<FProperty*> CheckProperties;
    return Parse(Bytes, CheckClass, CheckFields, CheckProperties);
}

bool ValidEnvelope(const TArray<uint8>& Bytes)
{
    UClass* Class = nullptr;
    TSharedPtr<FJsonObject> Fields;
    TArray<FProperty*> Properties;
    return Parse(Bytes, Class, Fields, Properties);
}

bool WriteVerified(const FString& Path, const TArray<uint8>& Bytes)
{
    TUniquePtr<IFileHandle> File(FPlatformFileManager::Get().GetPlatformFile().OpenWrite(*Path, false, false));
    if (!File || !File->Write(Bytes.GetData(), Bytes.Num()) || !File->Flush(true)) return false;
    File.Reset();
    TArray<uint8> Check;
    return ReadBounded(Path, Check) && Check == Bytes && ValidEnvelope(Check);
}

bool ReplaceFile(const FString& Destination, const FString& Temp)
{
#if PLATFORM_WINDOWS
    return ::MoveFileExW(*NativePath(Temp), *NativePath(Destination), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
#else
    // rename(2) replaces the destination atomically on POSIX; the directory entry is then synced
    // so the committed name survives power loss like MOVEFILE_WRITE_THROUGH on Windows.
    if (::rename(TCHAR_TO_UTF8(*Temp), TCHAR_TO_UTF8(*Destination)) != 0) return false;
    const int Dir = ::open(TCHAR_TO_UTF8(*FPaths::GetPath(Destination)), O_RDONLY | O_CLOEXEC);
    if (Dir >= 0) { ::fsync(Dir); ::close(Dir); }
    return true;
#endif
}

bool RenameWithoutReplace(const FString& Source, const FString& Destination)
{
#if PLATFORM_WINDOWS
    return ::MoveFileExW(*NativePath(Source), *NativePath(Destination), MOVEFILE_WRITE_THROUGH) != 0;
#else
    // The NDK API level in use has no rename-without-replace primitive. The destination carries a
    // fresh GUID suffix, so an occupancy check followed by rename keeps the no-overwrite rule.
    if (Exists(Destination)) return false;
    return ::rename(TCHAR_TO_UTF8(*Source), TCHAR_TO_UTF8(*Destination)) == 0;
#endif
}

bool Commit(const FString& Path, const TArray<uint8>& Bytes)
{
    const FString Backup = Path + TEXT(".bak");
    TArray<uint8> Prior, PriorBackup;
    const bool HadPrimary = Exists(Path), HadBackup = Exists(Backup);
    if ((HadPrimary && (!ReadBounded(Path, Prior) || !ValidEnvelope(Prior))) ||
        (!HadPrimary && HadBackup && (!ReadBounded(Backup, PriorBackup) || !ValidEnvelope(PriorBackup))))
    {
        Result(EYesterdaySaveGuardResult::ProtectedInvalidSlot, TEXT("Existing unsupported or invalid save preserved. Choose a separate new slot."));
        return false;
    }
    const FString Suffix = FGuid::NewGuid().ToString(EGuidFormats::Digits);
    const FString Temp = Path + TEXT(".tmp_") + Suffix;
    if (!WriteVerified(Temp, Bytes))
    {
        Result(EYesterdaySaveGuardResult::IoFailure, TEXT("Save staging or read-back failed; existing save preserved."));
        return false;
    }
    if (HadPrimary)
    {
        if (HadBackup && (!ReadBounded(Backup, PriorBackup) || !ValidEnvelope(PriorBackup)))
        {
            // Do not delete damaged recovery evidence. Rename without replace.
            const FString Preserved = Path + TEXT(".rejected_") + Suffix;
            if (!RenameWithoutReplace(Backup, Preserved))
            {
                Result(EYesterdaySaveGuardResult::IoFailure, TEXT("Invalid backup could not be preserved; existing primary retained."));
                return false;
            }
        }
        const FString BackupTemp = Backup + TEXT(".tmp_") + Suffix;
        if (!WriteVerified(BackupTemp, Prior) || !ReplaceFile(Backup, BackupTemp))
        {
            Result(EYesterdaySaveGuardResult::IoFailure, TEXT("Verified recovery copy could not be committed; existing primary retained."));
            return false;
        }
    }
    if (!ReplaceFile(Path, Temp))
    {
        Result(EYesterdaySaveGuardResult::IoFailure, TEXT("Save replacement failed; prior valid recovery retained."));
        return false;
    }
    TArray<uint8> Check;
    if (!ReadBounded(Path, Check) || Check != Bytes || !ValidEnvelope(Check))
    {
        Result(EYesterdaySaveGuardResult::IoFailure, TEXT("Committed save failed final verification; recovery copy retained."));
        return false;
    }
    Result(EYesterdaySaveGuardResult::Ok, TEXT("Save and read-back verified."));
    return true;
}
}

USaveGame* UYesterdaySaveGuardLibrary::SafeLoadGameFromSlot(const FString& SlotName, int32 UserIndex)
{
    using namespace YesterdayGuard;
    FString Path;
    if (!SlotPath(SlotName, UserIndex, Path)) { Result(EYesterdaySaveGuardResult::InvalidArgument, TEXT("Only safe slot names and local user 0 on the game thread are supported.")); return nullptr; }
    FDirectoryLock Lock(Path);
    if (!Lock.IsValid()) { Result(EYesterdaySaveGuardResult::Busy, TEXT("Save directory is busy or inaccessible.")); return nullptr; }
    TArray<uint8> Bytes;
    if (ReadBounded(Path, Bytes))
        if (USaveGame* Save = Decode(Bytes)) { Result(EYesterdaySaveGuardResult::Ok, TEXT("Save integrity and bounded schema verified.")); return Save; }
    Bytes.Reset();
    if (ReadBounded(Path + TEXT(".bak"), Bytes))
        if (USaveGame* Save = Decode(Bytes)) { Result(EYesterdaySaveGuardResult::RecoveredBackup, TEXT("Loaded verified previous checkpoint. Primary file preserved; save to a separate recovery slot.")); return Save; }
    const bool Occupied = Exists(Path) || Exists(Path + TEXT(".bak"));
    Result(Occupied ? EYesterdaySaveGuardResult::UnsupportedFormat : EYesterdaySaveGuardResult::Missing,
        Occupied ? TEXT("Save is unsupported or damaged and was preserved. Start a separate playthrough or select a verified recovery.") : TEXT("No save exists in this slot."));
    return nullptr;
}

bool UYesterdaySaveGuardLibrary::SafeSaveGameToSlot(USaveGame* SaveGameObject, const FString& SlotName, int32 UserIndex)
{
    using namespace YesterdayGuard;
    FString Path;
    if (!SlotPath(SlotName, UserIndex, Path)) { Result(EYesterdaySaveGuardResult::InvalidArgument, TEXT("Invalid save slot, user or thread.")); return false; }
    FDirectoryLock Lock(Path);
    if (!Lock.IsValid()) { Result(EYesterdaySaveGuardResult::Busy, TEXT("Save directory is busy or inaccessible.")); return false; }
    TArray<uint8> Bytes;
    if (!Encode(SaveGameObject, Bytes)) { Result(EYesterdaySaveGuardResult::UnsupportedClass, TEXT("Save class, fields or values are outside the reviewed primitive schema.")); return false; }
    return Commit(Path, Bytes);
}

bool UYesterdaySaveGuardLibrary::SafeDoesSaveGameExist(const FString& SlotName, int32 UserIndex)
{
    using namespace YesterdayGuard;
    FString Path;
    if (!SlotPath(SlotName, UserIndex, Path)) { Result(EYesterdaySaveGuardResult::InvalidArgument, TEXT("Invalid occupancy query; caller must not allocate this slot.")); return true; }
    const bool Occupied = Exists(Path) || Exists(Path + TEXT(".bak"));
    Result(Occupied ? EYesterdaySaveGuardResult::Ok : EYesterdaySaveGuardResult::Missing,
        Occupied ? TEXT("Slot is physically occupied; integrity was not checked.") : TEXT("Slot is unoccupied."));
    return Occupied;
}

EYesterdaySaveGuardResult UYesterdaySaveGuardLibrary::GetLastSaveGuardResult() { return YesterdayGuard::LastResult; }
FString UYesterdaySaveGuardLibrary::GetLastSaveGuardMessage() { return YesterdayGuard::LastMessage; }

USaveGame* UYesterdaySaveGuardLibrary::LoadGameFromSlot(const FString& SlotName, int32 UserIndex)
{ return SafeLoadGameFromSlot(SlotName, UserIndex); }
bool UYesterdaySaveGuardLibrary::SaveGameToSlot(USaveGame* SaveGameObject, const FString& SlotName, int32 UserIndex)
{ return SafeSaveGameToSlot(SaveGameObject, SlotName, UserIndex); }
bool UYesterdaySaveGuardLibrary::DoesSaveGameExist(const FString& SlotName, int32 UserIndex)
{ return SafeDoesSaveGameExist(SlotName, UserIndex); }

bool UYesterdaySaveGuardLibrary::ImportPinnedLegacyFixture(const FString& SourceSlotName, const FString& DestinationSlotName, int32 UserIndex)
{
    using namespace YesterdayGuard;
    FString Source, Destination;
    if (!SlotPath(SourceSlotName, UserIndex, Source) || !SlotPath(DestinationSlotName, UserIndex, Destination) || Source == Destination)
    { Result(EYesterdaySaveGuardResult::InvalidArgument, TEXT("Legacy import requires separate safe source and destination slots.")); return false; }
    FDirectoryLock Lock(Source);
    if (!Lock.IsValid()) { Result(EYesterdaySaveGuardResult::Busy, TEXT("Save directory is busy or inaccessible.")); return false; }
    if (Exists(Destination) || Exists(Destination + TEXT(".bak")))
    { Result(EYesterdaySaveGuardResult::ProtectedInvalidSlot, TEXT("Legacy import destination is occupied; no file changed.")); return false; }
    TArray<uint8> Legacy;
    FSHA256Signature Signature;
    if (!ReadBounded(Source, Legacy) || !HashLegacyFixtureSha256(Legacy, Signature) ||
        !Signature.ToString().Equals(TEXT("0f698bb9c4a003a7aa2883af39317161a1e38290ca388626231bce5f1caf94e8"), ESearchCase::IgnoreCase))
    { Result(EYesterdaySaveGuardResult::UnsupportedFormat, TEXT("Raw legacy file is not the exact approved fixture; it was preserved without deserialization.")); return false; }
    // The sole raw-GVAS decoder call in this module: immutable SHA-256-pinned
    // trusted historical fixture, not merely a matching magic/version header.
    USaveGame* Save = UGameplayStatics::LoadGameFromMemory(Legacy);
    TArray<uint8> Envelope;
    if (!Save || !Encode(Save, Envelope))
    { Result(EYesterdaySaveGuardResult::InvalidData, TEXT("Approved fixture is incompatible with the current reviewed class; source preserved.")); return false; }
    return Commit(Destination, Envelope);
}

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYesterdayGuardDecodeTest,
    "Yesterday.SaveGuard.BoundedDecoder", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FYesterdayGuardDecodeTest::RunTest(const FString& Parameters)
{
    using namespace YesterdayGuard;
    TArray<uint8> KnownShaInput = {'a', 'b', 'c'};
    FSHA256Signature KnownSha;
    if (!TestTrue(TEXT("Actual Windows CNG SHA-256 succeeds without engine stub"), HashLegacyFixtureSha256(KnownShaInput, KnownSha))) return false;
    TestEqual(TEXT("SHA-256 known abc vector"), KnownSha.ToString(), FString(TEXT("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")));
    // The headset (non-Windows) path is validated on the host against the published vectors.
    FSHA256Signature Portable;
    FPortableSha256::Digest(KnownShaInput.GetData(), KnownShaInput.Num(), Portable.Signature);
    TestEqual(TEXT("Portable SHA-256 abc vector"), Portable.ToString(), FString(TEXT("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")));
    const ANSICHAR* TwoBlocks = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
    FPortableSha256::Digest(reinterpret_cast<const uint8*>(TwoBlocks), FCStringAnsi::Strlen(TwoBlocks), Portable.Signature);
    TestEqual(TEXT("Portable SHA-256 two-block padding vector"), Portable.ToString(), FString(TEXT("248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1")));
    const uint8 Empty[1] = { 0 };
    FPortableSha256::Digest(Empty, 0, Portable.Signature);
    TestEqual(TEXT("Portable SHA-256 empty vector"), Portable.ToString(), FString(TEXT("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")));
    TArray<uint8> Long; Long.Init(0x61, 1000);
    FPortableSha256::Digest(Long.GetData(), Long.Num(), Portable.Signature);
    TestEqual(TEXT("Portable SHA-256 1000 x 'a' vector"), Portable.ToString(), FString(TEXT("41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3")));
    UClass* Class = LoadClass<USaveGame>(nullptr, ClassPath(TEXT("profile-v1")));
    if (!TestNotNull(TEXT("Actual release profile class is required"), Class)) return false;
    USaveGame* Profile = NewObject<USaveGame>(GetTransientPackage(), Class);
    TArray<uint8> Good;
    if (!TestTrue(TEXT("Current reviewed class encodes"), Encode(Profile, Good))) return false;
    TestNotNull(TEXT("Bounded profile round-trip constructs actual class"), Decode(Good));
    TestTrue(TEXT("No payload overrun"), Good.Num() <= HeaderSize + MaxPayload);
    auto Rehash = [](TArray<uint8>& Blob)
    {
        FBlake3 H; H.Update(Blob.GetData(), 16); H.Update(Blob.GetData()+HeaderSize, Blob.Num()-HeaderSize);
        const auto Digest = H.Finalize(); FMemory::Memcpy(Blob.GetData()+16, Digest.GetBytes(), 32);
    };
    for (int32 N : {0, 1, 7, 15, 47, 48})
    {
        TArray<uint8> Cut; Cut.Append(Good.GetData(), N);
        TestNull(FString::Printf(TEXT("Truncation %d returns null"), N), Decode(Cut));
    }
    TArray<uint8> Bad = Good; Bad.Last() ^= 1;
    TestNull(TEXT("Changed payload fails integrity"), Decode(Bad));
    Bad = Good; Write32(Bad.GetData()+12, MAX_uint32);
    TestNull(TEXT("Declared huge payload fails bounds"), Decode(Bad));
    Bad = Good; Write32(Bad.GetData()+8, 999); Rehash(Bad);
    TestNull(TEXT("Future envelope version rejected even with consistent hash"), Decode(Bad));
    Bad.Init(0x41, 128); Bad[0]='G'; Bad[1]='V'; Bad[2]='A'; Bad[3]='S';
    TestNull(TEXT("Raw GVAS never reaches native archive decoder"), Decode(Bad));
    const ANSICHAR* Nested = "{\"x\":[[[[[[]]]]]]}";
    TestFalse(TEXT("Excessive JSON depth rejected before parser"), JsonBudget(reinterpret_cast<const uint8*>(Nested), FCStringAnsi::Strlen(Nested)));
    TestFalse(TEXT("Traversal slot rejected"), [] { FString Path; return SlotPath(TEXT("../campaign"),0,Path); }());
    TestFalse(TEXT("Windows device slot rejected"), [] { FString Path; return SlotPath(TEXT("CON"),0,Path); }());
    TestFalse(TEXT("Nonzero platform user rejected"), [] { FString Path; return SlotPath(TEXT("campaign"),1,Path); }());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYesterdayGuardStoryV2MigrationTest,
    "Yesterday.SaveGuard.StoryV2Migration",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FYesterdayGuardStoryV2MigrationTest::RunTest(const FString& Parameters)
{
    using namespace YesterdayGuard;
    UClass* Class = LoadClass<USaveGame>(nullptr, ClassPath(TEXT("campaign-v2")));
    if (!TestNotNull(TEXT("Actual campaign class is required"), Class)) return false;
    TArray<FProperty*> Current;
    bool CurrentValid = Collect(Class, Schema(TEXT("campaign-v3")), Current);
    if (!CurrentValid) { Current.Reset(); CurrentValid = Collect(Class, Schema(TEXT("campaign-v2")), Current); }
    if (!TestTrue(TEXT("Current campaign matches its complete reviewed schema"), CurrentValid)) return false;
    TestEqual(TEXT("Legacy schema stays exactly 53 fields"), Schema(TEXT("campaign-v1")).Num(), 53);
    TestEqual(TEXT("New schema is exactly 56 fields"), Schema(TEXT("campaign-v2")).Num(), 56);
    FBoolProperty* HasReturned = FindFProperty<FBoolProperty>(Class, TEXT("HasReturned"));
    FIntProperty* StormCover = FindFProperty<FIntProperty>(Class, TEXT("StormCover"));
    FBoolProperty* PublicChronology = FindFProperty<FBoolProperty>(Class, TEXT("PublicChronologyObserved"));
    FBoolProperty* OrderRegister = FindFProperty<FBoolProperty>(Class, TEXT("OrderRegisterObserved"));
    FIntProperty* JourneyIntention = FindFProperty<FIntProperty>(Class, TEXT("MotherJourneyIntention"));
    if (!TestNotNull(TEXT("HasReturned is an actual bool property"), HasReturned) ||
        !TestNotNull(TEXT("StormCover is an actual int property"), StormCover) ||
        !TestNotNull(TEXT("PublicChronologyObserved is an actual bool property"), PublicChronology) ||
        !TestNotNull(TEXT("OrderRegisterObserved is an actual bool property"), OrderRegister) ||
        !TestNotNull(TEXT("MotherJourneyIntention is an actual int property"), JourneyIntention)) return false;
    USaveGame* Source = NewObject<USaveGame>(GetTransientPackage(), Class);
    HasReturned->SetPropertyValue_InContainer(Source, true);
    StormCover->SetPropertyValue_InContainer(Source, 2);
    PublicChronology->SetPropertyValue_InContainer(Source, true);
    OrderRegister->SetPropertyValue_InContainer(Source, true);
    JourneyIntention->SetPropertyValue_InContainer(Source, 3);
    TArray<uint8> CurrentBytes;
    if (!TestTrue(TEXT("Current campaign encodes"), Encode(Source, CurrentBytes))) return false;
    USaveGame* RoundTrip = Decode(CurrentBytes);
    if (!TestNotNull(TEXT("Current campaign decodes"), RoundTrip)) return false;
    TestTrue(TEXT("Chronology observation persists"), PublicChronology->GetPropertyValue_InContainer(RoundTrip));
    TestTrue(TEXT("Register observation persists"), OrderRegister->GetPropertyValue_InContainer(RoundTrip));
    TestEqual(TEXT("Selected intention persists"), JourneyIntention->GetPropertyValue_InContainer(RoundTrip), 3);

    // Construct an exact old guarded envelope, not a native GVAS archive.
    const FUTF8ToTCHAR Text(reinterpret_cast<const ANSICHAR*>(CurrentBytes.GetData()+HeaderSize), CurrentBytes.Num()-HeaderSize);
    TSharedPtr<FJsonObject> Root;
    if (!TestTrue(TEXT("Read the test's own encoded JSON"), FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(FString(Text.Length(), Text.Get())), Root))) return false;
    const TSharedPtr<FJsonObject>* FieldsPointer = nullptr;
    if (!Root->TryGetObjectField(TEXT("fields"), FieldsPointer)) return false;
    TSharedPtr<FJsonObject> Fields = *FieldsPointer;
    Root->SetStringField(TEXT("kind"), TEXT("campaign-v1"));
    Fields->RemoveField(TEXT("PublicChronologyObserved"));
    Fields->RemoveField(TEXT("OrderRegisterObserved"));
    Fields->RemoveField(TEXT("MotherJourneyIntention"));
    Fields->RemoveField(TEXT("IdentitySceneSeen"));
    Fields->RemoveField(TEXT("IdentityCustodianAccepted"));
    Fields->RemoveField(TEXT("IdentityRecordMethod"));
    auto Envelope = [](const TSharedPtr<FJsonObject>& Value)
    {
        FString Json;
        FJsonSerializer::Serialize(Value, TJsonWriterFactory<>::Create(&Json));
        const FTCHARToUTF8 Utf8(*Json);
        TArray<uint8> Blob;
        Blob.SetNumZeroed(HeaderSize + Utf8.Length());
        FMemory::Memcpy(Blob.GetData(), Magic, 8);
        Write32(Blob.GetData()+8, 1);
        Write32(Blob.GetData()+12, Utf8.Length());
        FMemory::Memcpy(Blob.GetData()+HeaderSize, Utf8.Get(), Utf8.Length());
        FBlake3 H; H.Update(Blob.GetData(), 16); H.Update(Blob.GetData()+HeaderSize, Utf8.Length());
        const auto Digest = H.Finalize();
        FMemory::Memcpy(Blob.GetData()+16, Digest.GetBytes(), 32);
        return Blob;
    };
    TArray<uint8> LegacyBytes = Envelope(Root);
    const TArray<uint8> UntouchedLegacyBytes = LegacyBytes;
    USaveGame* Migrated = Decode(LegacyBytes);
    if (!TestNotNull(TEXT("Exact old envelope migrates into actual expanded class"), Migrated)) return false;
    TestTrue(TEXT("Legacy input bytes are unchanged"), LegacyBytes == UntouchedLegacyBytes);
    TestTrue(TEXT("Original return flag preserved"), HasReturned->GetPropertyValue_InContainer(Migrated));
    TestEqual(TEXT("Original shelter route preserved"), StormCover->GetPropertyValue_InContainer(Migrated), 2);
    TestFalse(TEXT("Old saves do not invent chronology knowledge"), PublicChronology->GetPropertyValue_InContainer(Migrated));
    TestFalse(TEXT("Old saves do not invent register knowledge"), OrderRegister->GetPropertyValue_InContainer(Migrated));
    TestEqual(TEXT("Old saves do not invent a selected promise"), JourneyIntention->GetPropertyValue_InContainer(Migrated), 0);
    TArray<uint8> UpgradedBytes;
    TestTrue(TEXT("An explicit later save emits the expanded envelope"), Encode(Migrated, UpgradedBytes));

    // Migration must never become permissive missing/unknown/type acceptance.
    Fields->SetBoolField(TEXT("UnknownMigratedFlag"), true);
    TestNull(TEXT("Unknown legacy fields still fail closed"), Decode(Envelope(Root)));
    Fields->RemoveField(TEXT("UnknownMigratedFlag"));
    Fields->RemoveField(TEXT("HasReturned"));
    TestNull(TEXT("Missing original field still fails closed"), Decode(Envelope(Root)));
    Fields->SetStringField(TEXT("HasReturned"), TEXT("true"));
    TestNull(TEXT("Wrong original field type still fails closed"), Decode(Envelope(Root)));
    Fields->SetBoolField(TEXT("HasReturned"), true);
    Root->SetStringField(TEXT("kind"), TEXT("campaign-v2"));
    TestNull(TEXT("New envelopes cannot omit new required fields"), Decode(Envelope(Root)));
    Root->SetStringField(TEXT("kind"), TEXT("campaign-v999"));
    TestNull(TEXT("Unsupported future campaign schemas are rejected"), Decode(Envelope(Root)));
    return true;
}
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

#endif
