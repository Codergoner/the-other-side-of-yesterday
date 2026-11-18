#include "YesterdayDesktopWalk.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Border.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/TextBlock.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Misc/App.h"
#include "UnrealClient.h"
#include "UObject/UnrealType.h"

void UYesterdayWalkHint::NativeOnInitialized()
{
    Super::NativeOnInitialized();
    SetIsFocusable(false);
    if (!WidgetTree)
    {
        WidgetTree = NewObject<UWidgetTree>(this, TEXT("WidgetTree"));
    }
    UCanvasPanel* Canvas = WidgetTree->ConstructWidget<UCanvasPanel>();
    WidgetTree->RootWidget = Canvas;
    UBorder* Panel = WidgetTree->ConstructWidget<UBorder>();
    Panel->SetBrushColor(FLinearColor(0.025f, 0.055f, 0.06f, 0.9f));
    Panel->SetPadding(FMargin(14.0f, 9.0f));
    UCanvasPanelSlot* CanvasSlot = Canvas->AddChildToCanvas(Panel);
    CanvasSlot->SetAnchors(FAnchors(1.0f, 0.0f));
    CanvasSlot->SetAlignment(FVector2D(1.0f, 0.0f));
    CanvasSlot->SetPosition(FVector2D(-36.0f, 28.0f));
    CanvasSlot->SetAutoSize(true);
    HintText = WidgetTree->ConstructWidget<UTextBlock>();
    FSlateFontInfo Font = HintText->GetFont();
    Font.Size = 16;
    HintText->SetFont(Font);
    HintText->SetColorAndOpacity(FSlateColor(FLinearColor(0.91f, 0.91f, 0.83f)));
    HintText->SetShadowColorAndOpacity(FLinearColor(0, 0, 0, 0.6f));
    HintText->SetShadowOffset(FVector2D(1.0f, 1.0f));
    Panel->SetContent(HintText);
    SetVisibility(ESlateVisibility::HitTestInvisible);
}

void UYesterdayWalkHint::SetHint(const FText& Text)
{
    if (HintText)
    {
        HintText->SetText(Text);
    }
}

bool UYesterdayDesktopWalk::DoesSupportWorldType(EWorldType::Type WorldType) const
{
#if PLATFORM_WINDOWS
    return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
#else
    return false;
#endif
}

TStatId UYesterdayDesktopWalk::GetStatId() const
{
    RETURN_QUICK_DECLARE_CYCLE_STAT(UYesterdayDesktopWalk, STATGROUP_Tickables);
}

void UYesterdayDesktopWalk::StopWalking()
{
    bToggleWalkActive = false;
    StepSecondsRemaining = 0.0f;
    HintSeconds = 0.0f;
    if (Hint)
    {
        Hint->SetVisibility(ESlateVisibility::Collapsed);
    }
}

bool UYesterdayDesktopWalk::HasExplorationSession(UWorld* World)
{
    if (!World->GetMapName().EndsWith(TEXT("Verdant_Desktop")))
    {
        return false;
    }
    if (!StoryManager.IsValid())
    {
        AActor* Match = nullptr;
        for (TActorIterator<AActor> Actor(World); Actor; ++Actor)
        {
            if (Actor->ActorHasTag(TEXT("Opening.Manager")) &&
                Actor->GetClass()->GetPathName() == TEXT("/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C"))
            {
                if (Match)
                {
                    return false;
                }
                Match = *Actor;
            }
        }
        StoryManager = Match;
    }
    AActor* Manager = StoryManager.Get();
    if (!Manager)
    {
        return false;
    }
    // These are read-only eligibility checks. Missing or changed field types
    // fail closed; this control never sets a mode or grants a prerequisite.
    const FIntProperty* Mode = FindFProperty<FIntProperty>(Manager->GetClass(), TEXT("Mode"));
    const FBoolProperty* Menu = FindFProperty<FBoolProperty>(Manager->GetClass(), TEXT("ReleaseMenuActive"));
    const FBoolProperty* Session = FindFProperty<FBoolProperty>(Manager->GetClass(), TEXT("ReleaseSessionStarted"));
    return Mode && Menu && Session && Mode->GetPropertyValue_InContainer(Manager) == 0 &&
        !Menu->GetPropertyValue_InContainer(Manager) && Session->GetPropertyValue_InContainer(Manager);
}

void UYesterdayDesktopWalk::UpdateHint(APlayerController* Controller, float DeltaTime)
{
    if (!Hint)
    {
        Hint = CreateWidget<UYesterdayWalkHint>(Controller);
        if (Hint)
        {
            Hint->AddToViewport(20);
        }
    }
    if (!Hint)
    {
        return;
    }
    if (bToggleWalkActive)
    {
        Hint->SetHint(FText::FromString(TEXT("Walking - G / WASD to stop")));
        Hint->SetVisibility(ESlateVisibility::HitTestInvisible);
    }
    else if (HintSeconds > 0.0f)
    {
        Hint->SetHint(FText::FromString(TEXT("G  Toggle walking     H  Step forward     WASD  Stop / move")));
        Hint->SetVisibility(ESlateVisibility::HitTestInvisible);
        HintSeconds = FMath::Max(0.0f, HintSeconds - DeltaTime);
    }
    else
    {
        Hint->SetVisibility(ESlateVisibility::Collapsed);
    }
}

void UYesterdayDesktopWalk::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);
    UWorld* World = GetWorld();
    APlayerController* Controller = World ? World->GetFirstPlayerController() : nullptr;
    ACharacter* Character = Controller ? Cast<ACharacter>(Controller->GetPawn()) : nullptr;
    UGameViewportClient* ViewportClient = World ? World->GetGameViewport() : nullptr;
    FViewport* Viewport = ViewportClient ? ViewportClient->Viewport : nullptr;
    if (!World || !World->HasBegunPlay() || !Controller || !Controller->IsLocalController() ||
        !Character || !Character->IsLocallyControlled() || Controller->IsPaused() ||
        Controller->IsMoveInputIgnored() || !FApp::HasFocus() || !Viewport ||
        !Viewport->HasFocus() || !Viewport->IsForegroundWindow() || !HasExplorationSession(World))
    {
        StopWalking();
        return;
    }
    if (LastCharacter.Get() != Character || LastController.Get() != Controller)
    {
        StopWalking();
        LastCharacter = Character;
        LastController = Controller;
        bFirstHintShown = false;
    }
    if (!bFirstHintShown)
    {
        bFirstHintShown = true;
        HintSeconds = 6.0f;
    }
    const FKey CancelKeys[] = {EKeys::W, EKeys::A, EKeys::S, EKeys::D,
        EKeys::E, EKeys::F, EKeys::Q, EKeys::Tab, EKeys::Escape, EKeys::F1, EKeys::F10,
        EKeys::SpaceBar, EKeys::LeftControl, EKeys::One, EKeys::Two, EKeys::Three};
    bool bCancel = false;
    for (const FKey& Key : CancelKeys)
    {
        bCancel |= Controller->WasInputKeyJustPressed(Key) || Controller->IsInputKeyDown(Key);
    }
    bCancel |= FMath::Abs(Controller->GetInputAnalogKeyState(EKeys::Gamepad_LeftX)) > 0.15f ||
        FMath::Abs(Controller->GetInputAnalogKeyState(EKeys::Gamepad_LeftY)) > 0.15f;
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    if (bCancel || !Movement || !Movement->IsMovingOnGround())
    {
        StopWalking();
    }
    else if (Controller->WasInputKeyJustPressed(EKeys::G))
    {
        StepSecondsRemaining = 0.0f;
        bToggleWalkActive = !bToggleWalkActive;
        HintSeconds = bToggleWalkActive ? 0.0f : 2.0f;
    }
    else if (Controller->WasInputKeyJustPressed(EKeys::H) && StepSecondsRemaining <= 0.0f)
    {
        // One bounded input pulse. Repeated presses during this step are ignored.
        // CharacterMovement still owns acceleration, braking, and collision.
        bToggleWalkActive = false;
        StepSecondsRemaining = 0.23f;
        HintSeconds = 2.5f;
    }
    if (bToggleWalkActive || StepSecondsRemaining > 0.0f)
    {
        const FRotator YawOnly(0.0f, Controller->GetControlRotation().Yaw, 0.0f);
        Character->AddMovementInput(YawOnly.Vector(), 1.0f, false);
        StepSecondsRemaining = FMath::Max(0.0f, StepSecondsRemaining - DeltaTime);
    }
    UpdateHint(Controller, DeltaTime);
}

void UYesterdayDesktopWalk::Deinitialize()
{
    StopWalking();
    if (Hint)
    {
        Hint->RemoveFromParent();
        Hint = nullptr;
    }
    StoryManager.Reset();
    LastCharacter.Reset();
    LastController.Reset();
    Super::Deinitialize();
}
