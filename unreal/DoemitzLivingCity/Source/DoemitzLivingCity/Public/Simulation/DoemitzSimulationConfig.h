#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
#include "DoemitzSimulationConfig.generated.h"

UCLASS()
class DOEMITZLIVINGCITY_API ADoemitzSimulationConfig : public AActor
{
	GENERATED_BODY()

public:
	ADoemitzSimulationConfig();

protected:
	virtual void BeginPlay() override;

private:
	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	double StartMinute = 470.0;

	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	double TimeScale = 60.0;

	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	TArray<FDoemitzPlaceDefinition> Places;

	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	TArray<FDoemitzCitizenRoute> Routes;

	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	TArray<FDoemitzCitizenDefinition> Citizens;
};
