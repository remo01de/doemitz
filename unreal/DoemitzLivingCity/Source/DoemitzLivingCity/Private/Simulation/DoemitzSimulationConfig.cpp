#include "Simulation/DoemitzSimulationConfig.h"

#include "Engine/World.h"

ADoemitzSimulationConfig::ADoemitzSimulationConfig()
{
	PrimaryActorTick.bCanEverTick = false;
}

void ADoemitzSimulationConfig::BeginPlay()
{
	Super::BeginPlay();
	if (UDoemitzSimulationSubsystem* Subsystem = GetWorld()->GetSubsystem<UDoemitzSimulationSubsystem>())
	{
		Subsystem->ConfigureSimulation(StartMinute, TimeScale, Places, Routes, Citizens);
	}
}
