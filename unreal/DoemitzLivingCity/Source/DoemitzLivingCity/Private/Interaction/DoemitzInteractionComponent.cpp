#include "Interaction/DoemitzInteractionComponent.h"

#include "Blueprint/UserWidget.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
#include "UI/DoemitzCitizenDialogWidget.h"
#include "UI/DoemitzPlaceMenuWidget.h"
#include "UI/DoemitzTaskBoardWidget.h"
#include "UI/DoemitzUiText.h"

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
	NearestCitizenId = NAME_None;
	NearestNoticeBoardInteriorId = NAME_None;
	bNearestPlaceOpen = false;
	CurrentPromptText = FText::GetEmpty();

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

	const FVector QueryLoc = Owner->GetActorLocation();

	FDoemitzPlaceDefinition Place;
	double PlaceDistCm = InteractionRadiusCm + 1.0;
	const bool bHasPlace = Subsystem->FindNearestEntrance(QueryLoc, InteractionRadiusCm, Place, PlaceDistCm);

	FDoemitzCitizenState Citizen;
	double CitizenDistCm = InteractionRadiusCm + 1.0;
	const bool bHasCitizen = Subsystem->FindNearestCitizen(QueryLoc, InteractionRadiusCm, Citizen, CitizenDistCm);

	FName BoardInteriorId;
	double BoardDistCm = InteractionRadiusCm + 1.0;
	const bool bHasBoard = Subsystem->FindNearestNoticeBoard(QueryLoc, InteractionRadiusCm, BoardInteriorId, BoardDistCm);

	if (!bHasPlace && !bHasCitizen && !bHasBoard)
	{
		return;
	}

	// Notice board (Aushang) wins when it is the closest target
	if (bHasBoard && (!bHasPlace || BoardDistCm < PlaceDistCm) && (!bHasCitizen || BoardDistCm < CitizenDistCm))
	{
		NearestNoticeBoardInteriorId = BoardInteriorId;
		CurrentPromptText = FDoemitzUiText::FormatNoticeBoardPrompt(Subsystem->GetTasksByStatus(EDoemitzTaskStatus::Available).Num());
		return;
	}
	if (!bHasPlace && !bHasCitizen)
	{
		return;
	}

	// Choose whichever target is closer within the 2 m radius
	if (bHasCitizen && (!bHasPlace || CitizenDistCm < PlaceDistCm))
	{
		NearestCitizenId = Citizen.CitizenId;
		FDoemitzTaskInstance Offered;
		const bool bHasOffer = Subsystem->GetTaskOfferedByCitizen(Citizen.CitizenId, Offered);
		FDoemitzTaskInstance ActiveFetch;
		const bool bCanCompleteFetch = Subsystem->GetActiveFetchTaskForCitizen(Citizen.CitizenId, ActiveFetch) &&
			Subsystem->GetInventoryQuantity(ActiveFetch.RequestedItemId) >= 1;
		CurrentPromptText = FDoemitzUiText::FormatCitizenPrompt(Citizen, bHasOffer, bCanCompleteFetch);
		return;
	}

	NearestPlaceId = Place.PlaceId;
	NearestEntranceId = Place.EntranceId;
	const FDoemitzOpeningStatus Status = Subsystem->GetPlaceOpeningStatus(Place.PlaceId);
	bNearestPlaceOpen = Status.bOpen;
	CurrentPromptText = FDoemitzUiText::FormatEntrancePrompt(Place, Status);
}

bool UDoemitzInteractionComponent::TryInteract()
{
	if (ActiveMenuWidget || ActiveCitizenDialogWidget || ActiveTaskBoardWidget)
	{
		CloseMenu();
		return true;
	}

	RefreshNearestEntrance();
	if (NearestPlaceId.IsNone() && NearestCitizenId.IsNone() && NearestNoticeBoardInteriorId.IsNone())
	{
		return false;
	}

	UWorld* World = GetWorld();
	UDoemitzSimulationSubsystem* Subsystem = World ? World->GetSubsystem<UDoemitzSimulationSubsystem>() : nullptr;
	APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	if (!Subsystem || !PC || !PC->IsLocalController())
	{
		return false;
	}

	// Notice board in the Bürgerbüro (Sprint 13)
	if (!NearestNoticeBoardInteriorId.IsNone())
	{
		ActiveTaskBoardWidget = CreateWidget<UDoemitzTaskBoardWidget>(PC, UDoemitzTaskBoardWidget::StaticClass());
		if (!ActiveTaskBoardWidget)
		{
			return false;
		}
		ActiveTaskBoardWidget->OnCloseRequested.BindUObject(this, &UDoemitzInteractionComponent::CloseMenu);
		ActiveTaskBoardWidget->AddToViewport(20);
		ActiveTaskBoardWidget->RefreshContents();

		PC->SetShowMouseCursor(true);
		FInputModeGameAndUI InputMode;
		InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		InputMode.SetHideCursorDuringCapture(false);
		PC->SetInputMode(InputMode);
		return true;
	}

	// Citizen dialog interaction (Milestone 4)
	if (!NearestCitizenId.IsNone())
	{
		ActiveCitizenDialogWidget = CreateWidget<UDoemitzCitizenDialogWidget>(PC, UDoemitzCitizenDialogWidget::StaticClass());
		if (!ActiveCitizenDialogWidget)
		{
			return false;
		}
		ActiveDialogCitizenId = NearestCitizenId;
		Subsystem->SetCitizenDialogPaused(ActiveDialogCitizenId, true);
		ActiveCitizenDialogWidget->OnCloseRequested.BindUObject(this, &UDoemitzInteractionComponent::CloseMenu);
		ActiveCitizenDialogWidget->OpenForCitizen(ActiveDialogCitizenId);
		ActiveCitizenDialogWidget->AddToViewport(20);

		PC->SetShowMouseCursor(true);
		FInputModeGameAndUI InputMode;
		InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		InputMode.SetHideCursorDuringCapture(false);
		PC->SetInputMode(InputMode);
		return true;
	}

	// Place entrance interaction
	if (!bNearestPlaceOpen)
	{
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::PlaceClosed;
		Ev.PlaceId = NearestPlaceId;
		Subsystem->PushNotificationEvent(Ev);
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
	if (ActiveCitizenDialogWidget)
	{
		ActiveCitizenDialogWidget->RemoveFromParent();
		ActiveCitizenDialogWidget = nullptr;
	}
	if (ActiveTaskBoardWidget)
	{
		ActiveTaskBoardWidget->RemoveFromParent();
		ActiveTaskBoardWidget = nullptr;
	}
	if (!ActiveDialogCitizenId.IsNone())
	{
		if (UWorld* World = GetWorld())
		{
			if (UDoemitzSimulationSubsystem* Subsystem = World->GetSubsystem<UDoemitzSimulationSubsystem>())
			{
				Subsystem->SetCitizenDialogPaused(ActiveDialogCitizenId, false);
			}
		}
		ActiveDialogCitizenId = NAME_None;
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
