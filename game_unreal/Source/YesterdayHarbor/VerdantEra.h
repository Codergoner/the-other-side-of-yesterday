#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Subsystems/WorldSubsystem.h"
#include "VerdantEra.generated.h"

class UYesterdayWalkHint;

/**
 * Swaps the two timelines of a map that carries Verdant.Past / Verdant.Present actor tags.
 * Maps without those tags are untouched, so the story maps never reach this code path.
 */
UCLASS()
class UVerdantEraLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /** Shows one timeline and hides the other, including collision, lights and sky capture. */
    UFUNCTION(BlueprintCallable, Category="Verdant", meta=(WorldContext="WorldContext"))
    static int32 ApplyEra(UObject* WorldContext, bool bPast);
};

/** T switches timeline while exploring; the player stays exactly where they are standing. */
UCLASS()
class UVerdantEraSubsystem : public UTickableWorldSubsystem
{
    GENERATED_BODY()

public:
    virtual void OnWorldBeginPlay(UWorld& InWorld) override;
    virtual void Tick(float DeltaTime) override;
    virtual TStatId GetStatId() const override;
    virtual void Deinitialize() override;

    UFUNCTION(BlueprintCallable, Category="Verdant")
    void SetEra(bool bNewPast);

    UFUNCTION(BlueprintPure, Category="Verdant")
    bool IsPast() const { return bPast; }

protected:
    virtual bool DoesSupportWorldType(EWorldType::Type WorldType) const override;

private:
    UPROPERTY(Transient)
    TObjectPtr<UYesterdayWalkHint> Hint;

    bool bHasEras = false;
    bool bPast = true;
    float HintSeconds = 0.0f;
};
