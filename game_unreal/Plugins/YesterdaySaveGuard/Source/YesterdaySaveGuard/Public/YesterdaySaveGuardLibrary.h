#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "YesterdaySaveGuardLibrary.generated.h"

class USaveGame;

UENUM(BlueprintType)
enum class EYesterdaySaveGuardResult : uint8
{
    Ok,
    RecoveredBackup,
    Missing,
    InvalidArgument,
    UnsupportedFormat,
    InvalidData,
    UnsupportedClass,
    ProtectedInvalidSlot,
    IoFailure,
    Busy
};

/** Win64, synchronous, game-thread-only. Same main pins as GameplayStatics.
 * No arbitrary GVAS file is deserialized. Game schema/invariant checks still
 * belong to the existing manager; this layer only makes decoding bounded.
 */
UCLASS()
class YESTERDAYSAVEGUARD_API UYesterdaySaveGuardLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="Yesterday|Save")
    static USaveGame* SafeLoadGameFromSlot(const FString& SlotName, int32 UserIndex);

    UFUNCTION(BlueprintCallable, Category="Yesterday|Save")
    static bool SafeSaveGameToSlot(USaveGame* SaveGameObject, const FString& SlotName, int32 UserIndex);

    /** Physical occupancy, including an invalid primary or backup. Never use
     * decode success as the New Game collision check. Does not deserialize.
     */
    UFUNCTION(BlueprintCallable, Category="Yesterday|Save")
    static bool SafeDoesSaveGameExist(const FString& SlotName, int32 UserIndex);

    // Exact-name aliases permit the installed graph editor's RetargetNodeClass
    // to change only these library owners while preserving node GUIDs/pins.
    UFUNCTION(BlueprintCallable, Category="Yesterday|Save")
    static USaveGame* LoadGameFromSlot(const FString& SlotName, int32 UserIndex);

    UFUNCTION(BlueprintCallable, Category="Yesterday|Save")
    static bool SaveGameToSlot(USaveGame* SaveGameObject, const FString& SlotName, int32 UserIndex);

    UFUNCTION(BlueprintCallable, Category="Yesterday|Save")
    static bool DoesSaveGameExist(const FString& SlotName, int32 UserIndex);

    UFUNCTION(BlueprintPure, Category="Yesterday|Save")
    static EYesterdaySaveGuardResult GetLastSaveGuardResult();

    UFUNCTION(BlueprintPure, Category="Yesterday|Save")
    static FString GetLastSaveGuardMessage();

    /** Explicit import only: exact approved historical fixture SHA-256.
     * Source is never changed; destination must be completely unoccupied.
     * No arbitrary user legacy file is eligible for this migration.
     */
    UFUNCTION(BlueprintCallable, Category="Yesterday|Save")
    static bool ImportPinnedLegacyFixture(const FString& SourceSlotName, const FString& DestinationSlotName, int32 UserIndex);
};
