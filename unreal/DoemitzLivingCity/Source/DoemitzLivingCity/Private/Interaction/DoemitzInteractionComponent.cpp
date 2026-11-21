#include "Interaction/DoemitzInteractionComponent.h"

#include "Blueprint/UserWidget.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
#include "UI/DoemitzPlaceMenuWidget.h"

UDoemitzInteractionComponent::UDoemitzInteractionComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
}

void UDoemitzInteractionComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	RefreshNearestEntrance();
}

void UDoemitzInteractionComponent::RefreshNearestEntrance()
{
	NearestPlaceId = NAME_None;
	NearestEntranceId = NAME_None;
	NearestPlaceDisplayName.Reset();
	bNearestPlaceOpen = false;
	CurrentPrompt.Reset();

	AActor* Owner = GetOwner();
	UWorld* World = GetWorld();
	if (!Owner || !World || !World->IsGameWorld())
	{
		return;
	}

	UDoemitzSimulationSubsystem* Subsystem = World->GetSubsystem<UDoemitzSimulationSubsystem>();
	if (!Subsystem || Subsystem->IsWorkingShift())
	{
		return;
	}

	FDoemitzPlaceDefinition Place;
	double DistCm = 0.0;
	if (!Subsystem->FindNearestEntrance(Owner->GetActorLocation(), InteractionRadiusCm, Place, DistCm))
	{
		return;
	}

	NearestPlaceId = Place.PlaceId;
	NearestEntranceId = Place.EntranceId;
	NearestPlaceDisplayName = Place.DisplayName;
	bNearestPlaceOpen = Subsystem->IsPlaceOpenNow(Place.PlaceId);
	const FString StatusText = Subsystem->GetPlaceOpeningStatusText(Place.PlaceId);

	if (bNearestPlaceOpen)
	{
		CurrentPrompt = FString::Printf(TEXT("E - %s (%s)"), *Place.DisplayName, *StatusText);
	}
	else
	{
		CurrentPrompt = FString::Printf(TEXT("%s (%s)"), *Place.DisplayName, *StatusText);
	}
}

bool UDoemitzInteractionComponent::TryInteract()
{
	if (ActiveMenuWidget)
	{
		CloseMenu();
		return true;
	}

	RefreshNearestEntrance();
	if (NearestPlaceId.IsNone())
	{
		return false;
	}

	UWorld* World = GetWorld();
	UDoemitzSimulationSubsystem* Subsystem = World ? World->GetSubsystem<UDoemitzSimulationSubsystem>() : nullptr;
	if (!Subsystem)
	{
		return false;
	}

	if (!bNearestPlaceOpen)
	{
		Subsystem->SetNotification(FString::Printf(
			TEXT("%s ist geschlossen (%s)"),
			*NearestPlaceDisplayName,
			*Subsystem->GetPlaceOpeningStatusText(NearestPlaceId)));
		return false;
	}

	APlayerController* PC = World->GetFirstPlayerController();
	if (!PC || !PC->IsLocalController())
	{
		return false;
	}

	ActiveMenuWidget = CreateWidget<UDoemitzPlaceMenuWidget>(PC, UDoemitzPlaceMenuWidget::StaticClass());
	if (!ActiveMenuWidget)
	{
		return false;
	}

	ActiveMenuWidget->OnCloseRequested.BindUObject(this, &UDoemitzInteractionComponent::CloseMenu);
	ActiveMenuWidget->OpenForPlace(NearestPlaceId);
	ActiveMenuWidget->AddToViewport(20);

	PC->SetShowMouseCursor(true);
	FInputModeGameAndUI InputMode;
	InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	InputMode.SetHideCursorDuringCapture(false);
	PC->SetInputMode(InputMode);
	return true;
}

void UDoemitzInteractionComponent::CloseMenu()
{
	if (ActiveMenuWidget)
	{
		ActiveMenuWidget->RemoveFromParent();
		ActiveMenuWidget = nullptr;
	}
	if (UWorld* World = GetWorld())
	{
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			PC->SetShowMouseCursor(false);
			FInputModeGameOnly GameMode;
			PC->SetInputMode(GameMode);
		}
	}
}
