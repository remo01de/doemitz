#include "Simulation/DoemitzSimulationConfig.h"

#include "Blueprint/UserWidget.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "UI/DoemitzClockWidget.h"

ADoemitzSimulationConfig::ADoemitzSimulationConfig()
{
	PrimaryActorTick.bCanEverTick = true;
	ClockWidgetClass = UDoemitzClockWidget::StaticClass();
}

void ADoemitzSimulationConfig::BeginPlay()
{
	Super::BeginPlay();
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
}

void ADoemitzSimulationConfig::TryAttachClockHud()
{
	if (ClockWidget || !ClockWidgetClass)
	{
		SetActorTickEnabled(false);
		return;
	}
	UWorld* World = GetWorld();
	if (!World || !World->IsGameWorld())
	{
		SetActorTickEnabled(false);
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
	SetActorTickEnabled(false);
}
