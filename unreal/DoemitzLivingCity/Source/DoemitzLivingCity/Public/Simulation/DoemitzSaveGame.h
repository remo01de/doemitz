#pragma once

#include "CoreMinimal.h"
#include "Economy/DoemitzEconomyDataAsset.h"
#include "GameFramework/SaveGame.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
#include "Tasks/DoemitzTaskDataAsset.h"
#include "DoemitzSaveGame.generated.h"

USTRUCT()
struct FDoemitzSavedCitizen
{
	GENERATED_BODY()

	UPROPERTY()
	FName CitizenId;

	UPROPERTY()
	EDoemitzCitizenActivity CurrentActivity = EDoemitzCitizenActivity::Home;

	UPROPERTY()
	FName CurrentPlaceId;

	UPROPERTY()
	FName TargetPlaceId;

	UPROPERTY()
	bool bIsMoving = false;

	UPROPERTY()
	FVector WorldLocation = FVector::ZeroVector;

	UPROPERTY()
	FRotator WorldRotation = FRotator::ZeroRotator;

	UPROPERTY()
	double RouteProgressCm = 0.0;

	UPROPERTY()
	int32 ActiveScheduleIndex = 0;

	UPROPERTY()
	int32 CompletedTrips = 0;
};

USTRUCT()
struct FDoemitzSavedVehicle
{
	GENERATED_BODY()

	UPROPERTY()
	FName VehicleId;

	UPROPERTY()
	FName EdgeId;

	UPROPERTY()
	double DistanceCm = 0.0;

	UPROPERTY()
	double SpeedCmPerSecond = 0.0;

	UPROPERTY()
	int32 JunctionDecisions = 0;

	UPROPERTY()
	int32 CompletedLaps = 0;

	UPROPERTY()
	FVector WorldLocation = FVector::ZeroVector;

	// SaveSchemaVersion >= 5 parking state
	UPROPERTY()
	EDoemitzVehiclePhase Phase = EDoemitzVehiclePhase::Driving;

	UPROPERTY()
	FName TargetParkingLotId;

	UPROPERTY()
	FName CurrentParkingLotId;

	UPROPERTY()
	int32 ParkingSlotIndex = -1;

	UPROPERTY()
	double RemainingParkSeconds = 0.0;

	UPROPERTY()
	int32 TripCounter = 0;
};

USTRUCT()
struct FDoemitzSavedParkingOccupancy
{
	GENERATED_BODY()

	UPROPERTY()
	FName ParkingLotId;

	UPROPERTY()
	TArray<FName> SlotOccupants;
};

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzSaveGame : public USaveGame
{
	GENERATED_BODY()

public:
	static constexpr int32 CurrentSchemaVersion = 7;

	UPROPERTY(BlueprintReadWrite, Category = "SaveGame")
	int32 SaveSchemaVersion = CurrentSchemaVersion;

	UPROPERTY(BlueprintReadWrite, Category = "SaveGame")
	int32 DayNumber = 1;

	UPROPERTY(BlueprintReadWrite, Category = "SaveGame")
	int32 DayOfWeek = 0;

	UPROPERTY(BlueprintReadWrite, Category = "SaveGame")
	int32 CalendarWeek = 1;

	UPROPERTY(BlueprintReadWrite, Category = "SaveGame")
	double TimeOfDayMinutes = 470.0;

	UPROPERTY(BlueprintReadWrite, Category = "SaveGame")
	double TimeScale = 60.0;

	UPROPERTY()
	bool bHasPlayerTransform = false;

	UPROPERTY()
	FVector PlayerLocation = FVector::ZeroVector;

	UPROPERTY()
	FRotator PlayerRotation = FRotator::ZeroRotator;

	UPROPERTY()
	TArray<FDoemitzSavedCitizen> Citizens;

	UPROPERTY()
	TArray<FDoemitzSavedVehicle> Vehicles;

	UPROPERTY(BlueprintReadWrite, Category = "SaveGame")
	int64 PlayerMoneyCents = 0;

	UPROPERTY(BlueprintReadWrite, Category = "SaveGame")
	int32 NextTransactionId = 1;

	UPROPERTY(BlueprintReadWrite, Category = "SaveGame")
	FName ActiveJobId;

	UPROPERTY()
	TArray<FDoemitzLedgerEntry> LedgerEntries;

	UPROPERTY()
	TArray<FDoemitzInventoryItem> InventoryItems;

	UPROPERTY()
	TArray<FDoemitzPlaceRevenue> PlaceRevenues;

	// SaveSchemaVersion >= 5
	UPROPERTY()
	TArray<FDoemitzTaskInstance> Tasks;

	UPROPERTY()
	TArray<FDoemitzSavedParkingOccupancy> ParkingOccupancy;

	// SaveSchemaVersion >= 7: interior the player stood in when saving (NAME_None outdoors)
	UPROPERTY(BlueprintReadWrite, Category = "SaveGame")
	FName PlayerInteriorId;

	UPROPERTY(BlueprintReadWrite, Category = "SaveGame")
	FName PlayerInteriorPlaceId;
};
