#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
#include "DoemitzSimulationConfig.generated.h"

class UDoemitzCityMapWidget;
class UDoemitzClockWidget;
class UDoemitzEconomyDataAsset;
class UDoemitzTaskDataAsset;
class UDoemitzTaskJournalWidget;
class UStaticMesh;
class UTexture2D;

UCLASS()
class DOEMITZLIVINGCITY_API ADoemitzSimulationConfig : public AActor
{
	GENERATED_BODY()

public:
	ADoemitzSimulationConfig();
	virtual void Tick(float DeltaSeconds) override;

	UFUNCTION(BlueprintPure, Category = "UI")
	UDoemitzClockWidget* GetClockWidget() const { return ClockWidget; }

	UFUNCTION(BlueprintCallable, Category = "UI")
	void SetCityMapOpen(bool bOpen);

	UFUNCTION(BlueprintCallable, Category = "UI")
	void ToggleCityMap();

	UFUNCTION(BlueprintPure, Category = "UI")
	bool IsCityMapOpen() const { return CityMapWidget != nullptr; }

	UFUNCTION(BlueprintPure, Category = "UI")
	UDoemitzCityMapWidget* GetCityMapWidget() const { return CityMapWidget; }

	UFUNCTION(BlueprintCallable, Category = "UI")
	void SetTaskJournalOpen(bool bOpen);

	UFUNCTION(BlueprintCallable, Category = "UI")
	void ToggleTaskJournal();

	UFUNCTION(BlueprintPure, Category = "UI")
	bool IsTaskJournalOpen() const { return TaskJournalWidget != nullptr; }

	UFUNCTION(BlueprintPure, Category = "UI")
	UDoemitzTaskJournalWidget* GetTaskJournalWidget() const { return TaskJournalWidget; }

protected:
	virtual void BeginPlay() override;

private:
	void TryAttachClockHud();
	void HandleHotkeys();
	void UpdateCursorAndInputMode();

	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	double StartMinute = 470.0;

	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	double TimeScale = 60.0;

	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	TArray<FDoemitzPlaceDefinition> Places;

	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	TArray<FDoemitzCitizenRoute> Routes;

	UPROPERTY(EditInstanceOnly, Category = "Interior")
	TArray<FDoemitzInteriorDefinition> Interiors;

	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	TArray<FDoemitzCitizenDefinition> Citizens;

	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	TArray<TObjectPtr<UStaticMesh>> CitizenMeshVariants;

	UPROPERTY(EditInstanceOnly, Category = "Simulation", meta = (Units = "cm"))
	double CitizenLodRadiusCm = 15000.0;

	UPROPERTY(EditInstanceOnly, Category = "Traffic")
	int32 TrafficSeed = 202607;

	UPROPERTY(EditInstanceOnly, Category = "Traffic")
	TArray<FDoemitzRoadEdgeDefinition> RoadEdges;

	UPROPERTY(EditInstanceOnly, Category = "Traffic")
	TArray<FDoemitzVehicleDefinition> Vehicles;

	UPROPERTY(EditInstanceOnly, Category = "Traffic")
	TArray<FDoemitzCrossingDefinition> Crossings;

	UPROPERTY(EditInstanceOnly, Category = "Traffic")
	TArray<FDoemitzParkingLotDefinition> ParkingLots;

	UPROPERTY(EditInstanceOnly, Category = "Economy")
	TObjectPtr<UDoemitzEconomyDataAsset> EconomyData;

	UPROPERTY(EditInstanceOnly, Category = "Tasks")
	TObjectPtr<UDoemitzTaskDataAsset> TaskData;

	UPROPERTY(EditInstanceOnly, Category = "Map")
	TObjectPtr<UTexture2D> CityMapTexture;

	UPROPERTY(EditInstanceOnly, Category = "Map")
	FDoemitzMapBounds CityMapBounds;

	UPROPERTY(EditAnywhere, Category = "UI")
	TSubclassOf<UDoemitzClockWidget> ClockWidgetClass;

	UPROPERTY(Transient)
	TObjectPtr<UDoemitzClockWidget> ClockWidget;

	UPROPERTY(Transient)
	TObjectPtr<UDoemitzCityMapWidget> CityMapWidget;

	UPROPERTY(Transient)
	TObjectPtr<UDoemitzTaskJournalWidget> TaskJournalWidget;

	double PreviousActiveTimeScale = 60.0;
};
