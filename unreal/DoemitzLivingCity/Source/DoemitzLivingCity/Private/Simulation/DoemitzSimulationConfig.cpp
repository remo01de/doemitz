#include "Simulation/DoemitzSimulationConfig.h"

#include "Blueprint/UserWidget.h"
#include "Character/DoemitzCharacter.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Interaction/DoemitzInteractionComponent.h"
#include "Settings/DoemitzGraphicsSettings.h"
#include "UI/DoemitzCityMapWidget.h"
#include "UI/DoemitzClockWidget.h"
#include "UI/DoemitzTaskJournalWidget.h"

ADoemitzSimulationConfig::ADoemitzSimulationConfig()
{
	PrimaryActorTick.bCanEverTick = true;
	ClockWidgetClass = UDoemitzClockWidget::StaticClass();
}

void ADoemitzSimulationConfig::BeginPlay()
{
	Super::BeginPlay();
	PreviousActiveTimeScale = FMath::Max(1.0, TimeScale);
	if (UDoemitzSimulationSubsystem* Subsystem = GetWorld()->GetSubsystem<UDoemitzSimulationSubsystem>())
	{
		Subsystem->ConfigureSimulation(StartMinute, TimeScale, Places, Routes, Citizens);
		Subsystem->ConfigureEconomy(EconomyData);
		Subsystem->ConfigureTasks(TaskData);
		Subsystem->ConfigureCityMap(CityMapTexture, CityMapBounds);
		Subsystem->ConfigureCitizenPool(CitizenMeshVariants, CitizenLodRadiusCm);
		if (!RoadEdges.IsEmpty() && !Vehicles.IsEmpty())
		{
			Subsystem->ConfigureTrafficNetwork(TrafficSeed, RoadEdges, Vehicles, Crossings, ParkingLots);
		}
	}
	TryAttachClockHud();
}

void ADoemitzSimulationConfig::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	TryAttachClockHud();
	HandleHotkeys();
}

void ADoemitzSimulationConfig::TryAttachClockHud()
{
	if (ClockWidget || !ClockWidgetClass)
	{
		return;
	}
	UWorld* World = GetWorld();
	if (!World || !World->IsGameWorld())
	{
		return;
	}
	APlayerController* PC = World->GetFirstPlayerController();
	if (!PC || !PC->IsLocalController())
	{
		return;
	}
	ClockWidget = CreateWidget<UDoemitzClockWidget>(PC, ClockWidgetClass);
	if (ClockWidget)
	{
		ClockWidget->AddToViewport(10);
		ClockWidget->RefreshDisplay();
		UE_LOG(LogTemp, Display, TEXT("Doemitz clock HUD attached (%s)"), *ClockWidget->GetClockTextString());
	}
}

void ADoemitzSimulationConfig::UpdateCursorAndInputMode()
{
	UWorld* World = GetWorld();
	APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	if (!PC || !PC->IsLocalController())
	{
		return;
	}
	bool bInteractionOpen = false;
	if (const ADoemitzCharacter* Character = Cast<ADoemitzCharacter>(PC->GetPawn()))
	{
		if (const UDoemitzInteractionComponent* Interaction = Character->GetInteractionComponent())
		{
			bInteractionOpen = Interaction->IsMenuOpen();
		}
	}
	const bool bAnyOverlayOpen = (CityMapWidget != nullptr) || (TaskJournalWidget != nullptr) || bInteractionOpen;
	if (bAnyOverlayOpen)
	{
		PC->SetShowMouseCursor(true);
		FInputModeGameAndUI InputMode;
		InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		InputMode.SetHideCursorDuringCapture(false);
		PC->SetInputMode(InputMode);
	}
	else
	{
		PC->SetShowMouseCursor(false);
		FInputModeGameOnly GameMode;
		PC->SetInputMode(GameMode);
	}
}

void ADoemitzSimulationConfig::SetCityMapOpen(bool bOpen)
{
	if (bOpen == (CityMapWidget != nullptr))
	{
		return;
	}
	if (!bOpen)
	{
		if (CityMapWidget)
		{
			CityMapWidget->RemoveFromParent();
			CityMapWidget = nullptr;
		}
		UpdateCursorAndInputMode();
		return;
	}

	// Close other full overlays cleanly before opening map
	SetTaskJournalOpen(false);
	UWorld* World = GetWorld();
	APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	if (!PC || !PC->IsLocalController())
	{
		return;
	}
	if (ADoemitzCharacter* Character = Cast<ADoemitzCharacter>(PC->GetPawn()))
	{
		if (UDoemitzInteractionComponent* Interaction = Character->GetInteractionComponent())
		{
			if (Interaction->IsMenuOpen())
			{
				Interaction->CloseMenu();
			}
		}
	}

	CityMapWidget = CreateWidget<UDoemitzCityMapWidget>(PC, UDoemitzCityMapWidget::StaticClass());
	if (CityMapWidget)
	{
		CityMapWidget->OnCloseRequested.BindLambda([this]() { SetCityMapOpen(false); });
		CityMapWidget->AddToViewport(30);
		CityMapWidget->RefreshMapData();
		UpdateCursorAndInputMode();
	}
}

void ADoemitzSimulationConfig::ToggleCityMap()
{
	SetCityMapOpen(!IsCityMapOpen());
}

void ADoemitzSimulationConfig::SetTaskJournalOpen(bool bOpen)
{
	if (bOpen == (TaskJournalWidget != nullptr))
	{
		return;
	}
	if (!bOpen)
	{
		if (TaskJournalWidget)
		{
			TaskJournalWidget->RemoveFromParent();
			TaskJournalWidget = nullptr;
		}
		UpdateCursorAndInputMode();
		return;
	}

	SetCityMapOpen(false);
	UWorld* World = GetWorld();
	APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	if (!PC || !PC->IsLocalController())
	{
		return;
	}
	if (ADoemitzCharacter* Character = Cast<ADoemitzCharacter>(PC->GetPawn()))
	{
		if (UDoemitzInteractionComponent* Interaction = Character->GetInteractionComponent())
		{
			if (Interaction->IsMenuOpen())
			{
				Interaction->CloseMenu();
			}
		}
	}

	TaskJournalWidget = CreateWidget<UDoemitzTaskJournalWidget>(PC, UDoemitzTaskJournalWidget::StaticClass());
	if (TaskJournalWidget)
	{
		TaskJournalWidget->OnCloseRequested.BindLambda([this]() { SetTaskJournalOpen(false); });
		TaskJournalWidget->AddToViewport(25);
		TaskJournalWidget->RefreshContents();
		UpdateCursorAndInputMode();
	}
}

void ADoemitzSimulationConfig::ToggleTaskJournal()
{
	SetTaskJournalOpen(!IsTaskJournalOpen());
}

void ADoemitzSimulationConfig::HandleHotkeys()
{
	UWorld* World = GetWorld();
	if (!World || !World->IsGameWorld())
	{
		return;
	}
	APlayerController* PC = World->GetFirstPlayerController();
	if (!PC || !PC->IsLocalController())
	{
		return;
	}
	UDoemitzSimulationSubsystem* Subsystem = World->GetSubsystem<UDoemitzSimulationSubsystem>();
	if (!Subsystem)
	{
		return;
	}

	if (PC->WasInputKeyJustPressed(EKeys::M))
	{
		ToggleCityMap();
	}
	else if (PC->WasInputKeyJustPressed(EKeys::J))
	{
		ToggleTaskJournal();
	}
	else if (PC->WasInputKeyJustPressed(EKeys::E))
	{
		if (IsCityMapOpen())
		{
			SetCityMapOpen(false);
		}
		else if (IsTaskJournalOpen())
		{
			SetTaskJournalOpen(false);
		}
		else if (ADoemitzCharacter* Character = Cast<ADoemitzCharacter>(PC->GetPawn()))
		{
			if (UDoemitzInteractionComponent* Interaction = Character->GetInteractionComponent())
			{
				Interaction->TryInteract();
			}
		}
	}
	else if (PC->WasInputKeyJustPressed(EKeys::Escape))
	{
		if (IsCityMapOpen())
		{
			SetCityMapOpen(false);
		}
		else if (IsTaskJournalOpen())
		{
			SetTaskJournalOpen(false);
		}
		else if (ADoemitzCharacter* Character = Cast<ADoemitzCharacter>(PC->GetPawn()))
		{
			if (UDoemitzInteractionComponent* Interaction = Character->GetInteractionComponent())
			{
				if (Interaction->IsMenuOpen())
				{
					Interaction->CloseMenu();
				}
			}
		}
	}
	else if (PC->WasInputKeyJustPressed(EKeys::F5))
	{
		Subsystem->SaveCityState();
	}
	else if (PC->WasInputKeyJustPressed(EKeys::F7))
	{
		if (UDoemitzGraphicsSettings* GraphicsSettings = UDoemitzGraphicsSettings::Get())
		{
			const FString NewProfile = GraphicsSettings->ToggleProfile(World);
			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::GraphicsProfileChanged;
			Ev.ParameterKey = NewProfile;
			Subsystem->PushNotificationEvent(Ev);
		}
	}
	else if (PC->WasInputKeyJustPressed(EKeys::F9))
	{
		if (!Subsystem->LoadCityState())
		{
			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::NoSaveFound;
			Subsystem->PushNotificationEvent(Ev);
		}
	}
	else if (PC->WasInputKeyJustPressed(EKeys::One))
	{
		PreviousActiveTimeScale = 60.0;
		Subsystem->SetTimeScale(60.0);
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::TimeScaleChanged;
		Ev.ParameterKey = TEXT("1x");
		Subsystem->PushNotificationEvent(Ev);
	}
	else if (PC->WasInputKeyJustPressed(EKeys::Two))
	{
		PreviousActiveTimeScale = 300.0;
		Subsystem->SetTimeScale(300.0);
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::TimeScaleChanged;
		Ev.ParameterKey = TEXT("5x");
		Subsystem->PushNotificationEvent(Ev);
	}
	else if (PC->WasInputKeyJustPressed(EKeys::Three))
	{
		PreviousActiveTimeScale = 900.0;
		Subsystem->SetTimeScale(900.0);
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::TimeScaleChanged;
		Ev.ParameterKey = TEXT("15x");
		Subsystem->PushNotificationEvent(Ev);
	}
	else if (PC->WasInputKeyJustPressed(EKeys::P))
	{
		FDoemitzNotificationEvent Ev;
		if (Subsystem->GetTimeScale() > 0.0)
		{
			PreviousActiveTimeScale = Subsystem->GetTimeScale();
			Subsystem->SetTimeScale(0.0);
			Ev.Code = EDoemitzNotificationCode::TimePaused;
		}
		else
		{
			Subsystem->SetTimeScale(FMath::Max(60.0, PreviousActiveTimeScale));
			Ev.Code = EDoemitzNotificationCode::TimeResumed;
		}
		Subsystem->PushNotificationEvent(Ev);
	}
}
