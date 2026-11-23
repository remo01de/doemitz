#pragma once

#include "CoreMinimal.h"
#include "Simulation/DoemitzSimulationTypes.h"
#include "Subsystems/WorldSubsystem.h"
#include "DoemitzCitizenSubsystem.generated.h"

class ADoemitzCitizenActor;
class UDoemitzSaveGame;
class UStaticMesh;

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzCitizenSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	UFUNCTION(BlueprintPure, Category = "Simulation", meta = (WorldContext = "WorldContextObject"))
	static UDoemitzCitizenSubsystem* Get(const UObject* WorldContextObject);

	void ConfigureCitizens(
		const TArray<FDoemitzCitizenRoute>& InRoutes,
		const TArray<FDoemitzCitizenDefinition>& InCitizens);

	void ConfigureCitizenPool(
		const TArray<TObjectPtr<UStaticMesh>>& InMeshVariants,
		double InLodRadiusCm = 15000.0);

	void StepCitizens(double DeltaSeconds, double TimeScale, double BaseTimeScale);

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetCitizenCount() const { return CitizenRecords.Num(); }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool GetCitizenState(FName CitizenId, FDoemitzCitizenState& OutState) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	TArray<FName> GetAllCitizenIds() const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool FindNearestCitizen(const FVector& QueryLocation, double MaxRadiusCm, FDoemitzCitizenState& OutCitizen, double& OutDistanceCm) const;

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	bool SetCitizenDialogPaused(FName CitizenId, bool bPaused);

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool IsCitizenDialogPaused(FName CitizenId) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetActiveCitizenActorCount() const { return ActiveCitizenActors.Num(); }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetPooledCitizenActorCount() const { return PooledCitizenActors.Num(); }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool IsCitizenHighDetail(FName CitizenId) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool GetCitizenActorLocation(FName CitizenId, FVector& OutLocation) const;

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetCitizenLodRadiusCm(double NewRadiusCm);

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	bool SetCitizenPositionForTest(FName CitizenId, const FVector& NewLocation);

	/** Test helper: the citizen has arrived at PlaceId with the given activity (no walking). */
	UFUNCTION(BlueprintCallable, Category = "Simulation")
	bool SetCitizenAtPlaceForTest(FName CitizenId, FName PlaceId, EDoemitzCitizenActivity Activity);

	/** Where the citizen actor is shown: a stand spot inside an interior while shopping/working there, else the simulated position. */
	UFUNCTION(BlueprintPure, Category = "Interior")
	bool GetCitizenPresentationTransform(FName CitizenId, FVector& OutLocation, FRotator& OutRotation) const;

	void CollectCitizenWorldLocations(TArray<FVector>& OutLocations) const;
	void UpdateCitizenLodPool();
	void SyncAllActiveCitizenActors();

	void CaptureSaveState(UDoemitzSaveGame* SaveObj) const;
	void RestoreSaveState(
		const UDoemitzSaveGame* SaveObj,
		bool bMigratingFromPreV6,
		TFunctionRef<bool(double, double, double, double&)> GroundZResolver);

private:
	struct FCitizenRecord
	{
		FDoemitzCitizenDefinition Definition;
		FDoemitzCitizenState State;
		TArray<FVector> ActiveRoute;
		TArray<double> ActiveSegmentEnds;
		double ActiveRouteLength = 0.0;
		double CoarseAccumulatedSeconds = 0.0;
	};

	static int32 FindScheduleIndex(const TArray<FDoemitzScheduleEntry>& Schedule, double MinuteOfDay);
	static FName MakeRouteKey(FName FromPlaceId, FName ToPlaceId);
	const TArray<FDoemitzScheduleEntry>& GetActiveScheduleForDay(const FDoemitzCitizenDefinition& Def) const;
	FDoemitzScheduleEntry ResolveDesiredEntry(const FDoemitzCitizenDefinition& Def, int32& OutIndex) const;
	void ResetCitizenToCurrentSchedule(FCitizenRecord& Record);
	void BuildRouteSegments(FCitizenRecord& Record);
	void BuildRouteCache(FCitizenRecord& Record, FName FromPlaceId, FName DestinationPlaceId);
	void StartTrip(FCitizenRecord& Record, FName DestinationPlaceId);
	void UpdateCitizen(FCitizenRecord& Record, double TravelSeconds);
	ADoemitzCitizenActor* AcquirePooledCitizenActor(const FCitizenRecord& Record);
	void ReleaseCitizenActor(FName CitizenId);

	double CitizenLodRadiusCm = 15000.0;
	double CoarseUpdateIntervalSeconds = 1.0;

	TMap<FName, FDoemitzCitizenRoute> RoutesByKey;
	TMap<FName, FCitizenRecord> CitizenRecords;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMesh>> CitizenMeshVariants;

	UPROPERTY(Transient)
	TMap<FName, TObjectPtr<ADoemitzCitizenActor>> ActiveCitizenActors;

	UPROPERTY(Transient)
	TArray<TObjectPtr<ADoemitzCitizenActor>> PooledCitizenActors;
};
