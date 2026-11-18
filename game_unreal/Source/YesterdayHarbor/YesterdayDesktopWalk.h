#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Subsystems/WorldSubsystem.h"
#include "YesterdayDesktopWalk.generated.h"

class ACharacter;
class APlayerController;
class UTextBlock;

/** Small, noninteractive hint for the ordinary desktop accessibility control. */
UCLASS()
class UYesterdayWalkHint : public UUserWidget
{
    GENERATED_BODY()

public:
    void SetHint(const FText& Text);

protected:
    virtual void NativeOnInitialized() override;

private:
    UPROPERTY(Transient)
    TObjectPtr<UTextBlock> HintText;
};

/**
 * Optional G toggle and H short step for normal forward walking. Neither steers the camera,
 * places a pawn, changes collision/speed, or writes narrative/save state.
 */
UCLASS()
class UYesterdayDesktopWalk : public UTickableWorldSubsystem
{
    GENERATED_BODY()

public:
    virtual void Tick(float DeltaTime) override;
    virtual TStatId GetStatId() const override;
    virtual bool IsTickableWhenPaused() const override { return true; }
    virtual void Deinitialize() override;

    UFUNCTION(BlueprintPure, Category="Accessibility")
    bool IsToggleWalkActive() const { return bToggleWalkActive; }

protected:
    virtual bool DoesSupportWorldType(EWorldType::Type WorldType) const override;

private:
    void StopWalking();
    bool HasExplorationSession(UWorld* World);
    void UpdateHint(APlayerController* Controller, float DeltaTime);

    UPROPERTY(Transient)
    bool bToggleWalkActive = false;

    UPROPERTY(Transient)
    float StepSecondsRemaining = 0.0f;

    UPROPERTY(Transient)
    TObjectPtr<UYesterdayWalkHint> Hint;

    TWeakObjectPtr<AActor> StoryManager;
    TWeakObjectPtr<ACharacter> LastCharacter;
    TWeakObjectPtr<APlayerController> LastController;
    bool bFirstHintShown = false;
    float HintSeconds = 0.0f;
};
