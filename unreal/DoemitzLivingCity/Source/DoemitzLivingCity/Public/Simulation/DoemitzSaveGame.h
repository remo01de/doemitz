#pragma once

#include "CoreMinimal.h"
#include "GameFramework/SaveGame.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
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
	double DistanceCm = 0.0;

	UPROPERTY()
	int32 CompletedLaps = 0;
};

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzSaveGame : public USaveGame
{
	GENERATED_BODY()

public:
	UPROPERTY()
	int32 SaveSchemaVersion = 1;

	UPROPERTY()
	int32 DayNumber = 1;

	UPROPERTY()
	double TimeOfDayMinutes = 470.0;

	UPROPERTY()
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
};
