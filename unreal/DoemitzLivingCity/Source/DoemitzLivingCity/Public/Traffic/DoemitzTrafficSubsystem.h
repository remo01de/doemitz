#pragma once

#include "CoreMinimal.h"
#include "Simulation/DoemitzSimulationTypes.h"
#include "Subsystems/WorldSubsystem.h"
#include "DoemitzTrafficSubsystem.generated.h"

class UDoemitzSaveGame;

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzTrafficSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	UFUNCTION(BlueprintPure, Category = "Traffic", meta = (WorldContext = "WorldContextObject"))
	static UDoemitzTrafficSubsystem* Get(const UObject* WorldContextObject);

	void ConfigureTrafficNetwork(
		int32 InTrafficSeed,
		const TArray<FDoemitzRoadEdgeDefinition>& InRoadEdges,
		const TArray<FDoemitzVehicleDefinition>& InVehicles,
		const TArray<FDoemitzCrossingDefinition>& InCrossings = TArray<FDoemitzCrossingDefinition>(),
		const TArray<FDoemitzParkingLotDefinition>& InParkingLots = TArray<FDoemitzParkingLotDefinition>());

	void StepTraffic(double DeltaSeconds, double TimeMultiplier);

	UFUNCTION(BlueprintPure, Category = "Traffic")
	int32 GetVehicleCount() const { return VehicleRecords.Num(); }

	UFUNCTION(BlueprintPure, Category = "Traffic")
	int32 GetRoadEdgeCount() const { return RoadEdgesById.Num(); }

	UFUNCTION(BlueprintPure, Category = "Traffic")
	int32 GetCrossingCount() const { return Crossings.Num(); }

	UFUNCTION(BlueprintPure, Category = "Traffic")
	bool GetCrossingLocation(FName CrossingId, FVector& OutLocation) const;

	UFUNCTION(BlueprintPure, Category = "Traffic")
	TArray<FName> GetAllCrossingIds() const;

	UFUNCTION(BlueprintPure, Category = "Traffic")
	bool GetVehicleState(FName VehicleId, FDoemitzVehicleState& OutState) const;

	UFUNCTION(BlueprintPure, Category = "Traffic")
	TArray<FName> GetAllVehicleIds() const { return OrderedVehicleIds; }

	UFUNCTION(BlueprintPure, Category = "Traffic")
	FName GetJunctionReservation(FName NodeId) const;

	UFUNCTION(BlueprintPure, Category = "Traffic")
	EDoemitzYieldRule GetEdgeYieldRule(FName EdgeId) const;

	UFUNCTION(BlueprintCallable, Category = "Traffic")
	bool SetEdgeYieldRuleForTest(FName EdgeId, EDoemitzYieldRule NewRule);

	UFUNCTION(BlueprintPure, Category = "Traffic")
	int32 GetParkingLotCount() const { return ParkingLotsById.Num(); }

	UFUNCTION(BlueprintPure, Category = "Traffic")
	TArray<FName> GetAllParkingLotIds() const { return OrderedParkingLotIds; }

	UFUNCTION(BlueprintPure, Category = "Traffic")
	bool GetParkingLotState(FName ParkingLotId, FDoemitzParkingLotState& OutState) const;

	UFUNCTION(BlueprintCallable, Category = "Traffic")
	bool SetVehicleEdgePositionForTest(FName VehicleId, FName EdgeId, double DistanceOnEdgeCm, double SpeedCmPerSecond = 0.0);

	UFUNCTION(BlueprintCallable, Category = "Traffic")
	bool SetVehicleTargetParkingForTest(FName VehicleId, FName ParkingLotId);

	void CaptureSaveState(UDoemitzSaveGame* SaveObj) const;
	void RestoreSaveState(const UDoemitzSaveGame* SaveObj, bool bMigratingFromV1, bool bMigratingFromPreV5);

private:
	struct FRoadEdgeRecord
	{
		FDoemitzRoadEdgeDefinition Definition;
		TArray<double> SegmentEnds;
		double LengthCm = 0.0;
		FVector2D StartDir2D = FVector2D(1.0, 0.0);
		FVector2D EndDir2D = FVector2D(1.0, 0.0);
	};

	struct FParkingLotRecord
	{
		FDoemitzParkingLotDefinition Definition;
		TArray<FName> SlotOccupants;
	};

	struct FVehicleRecord
	{
		FDoemitzVehicleDefinition Definition;
		FDoemitzVehicleState State;
		FName ReservedNodeId;
		TArray<FName> PlannedEdges;
		int32 TripCounter = 0;
		bool bCompletedStopAtEdge = false;
		double StopHoldElapsedSeconds = 0.0;
		double ManeuverProgress = 0.0;
		FVector ManeuverStartLocation = FVector::ZeroVector;
		FRotator ManeuverStartRotation = FRotator::ZeroRotator;
		FVector ManeuverEndLocation = FVector::ZeroVector;
		FRotator ManeuverEndRotation = FRotator::ZeroRotator;
	};

	void SampleEdgePose(const FRoadEdgeRecord& Edge, double DistanceCm, FVector& OutLocation, FRotator& OutRotation) const;
	FName ChooseNextEdge(const FVehicleRecord& Record) const;
	bool ComputeEdgePath(FName StartEdgeId, FName GoalEdgeId, TArray<FName>& OutPath) const;
	FName ChooseNextParkingLot(const FVehicleRecord& Record, FName ExcludeLotId) const;
	void PlanRouteToParking(FVehicleRecord& Record, FName ParkingLotId);
	int32 TryReserveParkingSlot(FName ParkingLotId, FName VehicleId, FVector& OutSlotLocation);
	void ReleaseParkingSlot(FVehicleRecord& Record);
	FName FindNearestDrivableEdge(const FVector& Location, double& OutDistanceCm) const;
	void UpdateTrafficSubStep(double DeltaSeconds);
	void ReleaseJunctionReservation(FVehicleRecord& Record);

	int32 TrafficSeed = 202607;
	TMap<FName, FRoadEdgeRecord> RoadEdgesById;
	TMap<FName, TArray<FName>> OutgoingEdgesByNode;
	TArray<FDoemitzCrossingDefinition> Crossings;
	TMap<FName, FParkingLotRecord> ParkingLotsById;
	TArray<FName> OrderedParkingLotIds;
	TMap<FName, FVehicleRecord> VehicleRecords;
	TArray<FName> OrderedVehicleIds;
	TMap<FName, FName> JunctionReservations;
};
