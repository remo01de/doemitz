#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
#include "DoemitzSimulationConfig.generated.h"

class UDoemitzClockWidget;

UCLASS()
class DOEMITZLIVINGCITY_API ADoemitzSimulationConfig : public AActor
{
	GENERATED_BODY()

public:
	ADoemitzSimulationConfig();
	virtual void Tick(float DeltaSeconds) override;

	UFUNCTION(BlueprintPure, Category = "UI")
	UDoemitzClockWidget* GetClockWidget() const { return ClockWidget; }

protected:
	virtual void BeginPlay() override;

private:
	void TryAttachClockHud();
	void HandleHotkeys();

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

	UPROPERTY(EditInstanceOnly, Category = "Traffic")
	int32 TrafficSeed = 202607;

	UPROPERTY(EditInstanceOnly, Category = "Traffic")
	TArray<FDoemitzRoadEdgeDefinition> RoadEdges;

	UPROPERTY(EditInstanceOnly, Category = "Traffic")
	TArray<FDoemitzVehicleDefinition> Vehicles;

	UPROPERTY(EditAnywhere, Category = "UI")
	TSubclassOf<UDoemitzClockWidget> ClockWidgetClass;

	UPROPERTY(Transient)
	TObjectPtr<UDoemitzClockWidget> ClockWidget;

	double PreviousActiveTimeScale = 60.0;
};
