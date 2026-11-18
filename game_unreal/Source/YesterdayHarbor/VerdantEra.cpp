#include "VerdantEra.h"

#include "Components/SceneComponent.h"
#include "Components/SkyLightComponent.h"
#include "Engine/Engine.h"
#include "Engine/SkyLight.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Actor.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "YesterdayDesktopWalk.h"

static const FName PastTag(TEXT("Verdant.Past"));
static const FName PresentTag(TEXT("Verdant.Present"));

static void SetActorEra(AActor* Actor, bool bShow)
{
    Actor->SetActorHiddenInGame(!bShow);
    Actor->SetActorEnableCollision(bShow);
#if WITH_EDITOR
    Actor->SetIsTemporarilyHiddenInEditor(!bShow);
#endif
    TArray<USceneComponent*> Components;
    Actor->GetComponents<USceneComponent>(Components);
    for (USceneComponent* Component : Components)
    {
        Component->SetVisibility(bShow, false);
    }
}

int32 UVerdantEraLibrary::ApplyEra(UObject* WorldContext, bool bPast)
{
    UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContext, EGetWorldErrorMode::ReturnNull) : nullptr;
    if (!World)
    {
        return 0;
    }
    int32 Changed = 0;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        const bool bIsPast = It->ActorHasTag(PastTag);
        if (bIsPast || It->ActorHasTag(PresentTag))
        {
            SetActorEra(*It, bIsPast == bPast);
            ++Changed;
        }
    }
    if (Changed > 0)
    {
        for (TActorIterator<ASkyLight> It(World); It; ++It)
        {
            if (USkyLightComponent* Sky = It->GetLightComponent())
            {
                Sky->RecaptureSky();
            }
        }
    }
    return Changed;
}

bool UVerdantEraSubsystem::DoesSupportWorldType(EWorldType::Type WorldType) const
{
    return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

TStatId UVerdantEraSubsystem::GetStatId() const
{
    RETURN_QUICK_DECLARE_CYCLE_STAT(UVerdantEraSubsystem, STATGROUP_Tickables);
}

void UVerdantEraSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
    Super::OnWorldBeginPlay(InWorld);
    FString Requested;
    bool bStartPast = true;
    if (FParse::Value(FCommandLine::Get(), TEXT("VerdantEra="), Requested))
    {
        bStartPast = !Requested.Equals(TEXT("Present"), ESearchCase::IgnoreCase);
    }
    bHasEras = UVerdantEraLibrary::ApplyEra(&InWorld, bStartPast) > 0;
    bPast = bStartPast;
    HintSeconds = bHasEras ? 7.0f : 0.0f;
}

void UVerdantEraSubsystem::SetEra(bool bNewPast)
{
    if (bHasEras && bNewPast != bPast)
    {
        UVerdantEraLibrary::ApplyEra(GetWorld(), bNewPast);
        bPast = bNewPast;
        HintSeconds = 3.0f;
    }
}

void UVerdantEraSubsystem::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);
    if (!bHasEras)
    {
        return;
    }
    UWorld* World = GetWorld();
    APlayerController* Controller = World ? World->GetFirstPlayerController() : nullptr;
    if (!Controller || !Controller->IsLocalController() || Controller->IsPaused())
    {
        return;
    }
    if (Controller->WasInputKeyJustPressed(EKeys::T))
    {
        SetEra(!bPast);
    }
    if (!Hint)
    {
        Hint = CreateWidget<UYesterdayWalkHint>(Controller);
        if (Hint)
        {
            Hint->AddToViewport(20);
        }
    }
    if (Hint)
    {
        if (HintSeconds > 0.0f)
        {
            Hint->SetHint(FText::FromString(bPast ? TEXT("Verdant - the past     T  Switch timeline")
                                                  : TEXT("Verdant - the present     T  Switch timeline")));
            Hint->SetVisibility(ESlateVisibility::HitTestInvisible);
            HintSeconds = FMath::Max(0.0f, HintSeconds - DeltaTime);
        }
        else
        {
            Hint->SetVisibility(ESlateVisibility::Collapsed);
        }
    }
}

void UVerdantEraSubsystem::Deinitialize()
{
    if (Hint)
    {
        Hint->RemoveFromParent();
        Hint = nullptr;
    }
    Super::Deinitialize();
}
