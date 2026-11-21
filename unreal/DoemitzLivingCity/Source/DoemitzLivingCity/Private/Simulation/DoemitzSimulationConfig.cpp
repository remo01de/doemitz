#include "Simulation/DoemitzSimulationConfig.h"

#include "Blueprint/UserWidget.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "UI/DoemitzClockWidget.h"

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

	if (PC->WasInputKeyJustPressed(EKeys::F5))
	{
		Subsystem->SaveCityState();
	}
	else if (PC->WasInputKeyJustPressed(EKeys::F9))
	{
		if (!Subsystem->LoadCityState())
		{
			Subsystem->SetNotification(TEXT("Kein Spielstand vorhanden"));
		}
	}
	else if (PC->WasInputKeyJustPressed(EKeys::One))
	{
		PreviousActiveTimeScale = 60.0;
		Subsystem->SetTimeScale(60.0);
		Subsystem->SetNotification(TEXT("Zeit: 1x"));
	}
	else if (PC->WasInputKeyJustPressed(EKeys::Two))
	{
		PreviousActiveTimeScale = 300.0;
		Subsystem->SetTimeScale(300.0);
		Subsystem->SetNotification(TEXT("Zeit: 5x"));
	}
	else if (PC->WasInputKeyJustPressed(EKeys::Three))
	{
		PreviousActiveTimeScale = 900.0;
		Subsystem->SetTimeScale(900.0);
		Subsystem->SetNotification(TEXT("Zeit: 15x"));
	}
	else if (PC->WasInputKeyJustPressed(EKeys::P))
	{
		if (Subsystem->GetTimeScale() > 0.0)
		{
			PreviousActiveTimeScale = Subsystem->GetTimeScale();
			Subsystem->SetTimeScale(0.0);
			Subsystem->SetNotification(TEXT("Zeit: Pause"));
		}
		else
		{
			Subsystem->SetTimeScale(FMath::Max(60.0, PreviousActiveTimeScale));
			Subsystem->SetNotification(TEXT("Zeit: Fortgesetzt"));
		}
	}
}
