#pragma once

#include "CoreMinimal.h"
#include "Economy/DoemitzEconomyDataAsset.h"
#include "Tasks/DoemitzTaskDataAsset.h"
#include "DoemitzSimulationTypes.generated.h"

namespace DoemitzSimulationUtil
{
	inline uint32 DeterministicHash(int32 Seed, FName KeyId, int32 Salt)
	{
		uint32 H = static_cast<uint32>(Seed) * 2654435761u;
		const FString Str = KeyId.ToString();
		for (TCHAR Ch : Str)
		{
			H = (H ^ static_cast<uint32>(Ch)) * 16777619u;
		}
		H = (H ^ static_cast<uint32>(Salt * 73856093)) * 2246822519u;
		H ^= (H >> 13);
		H *= 3266489917u;
		H ^= (H >> 16);
		return H;
	}
}

UENUM(BlueprintType)
enum class EDoemitzCitizenActivity : uint8
{
	Home,
	Commuting,
	Working,
	Shopping,
	Strolling
};

UENUM(BlueprintType)
enum class EDoemitzDayKind : uint8
{
	Weekday,
	Saturday,
	Sunday
};

UENUM(BlueprintType)
enum class EDoemitzYieldRule : uint8
{
	None,
	GiveWay,
	Stop
};

UENUM(BlueprintType)
enum class EDoemitzVehiclePhase : uint8
{
	Driving,
	Parking,
	Parked,
	Leaving
};

UENUM(BlueprintType)
enum class EDoemitzShiftCheckResult : uint8
{
	Ready,
	AlreadyWorking,
	NoJobAtPlace,
	JobNotAccepted,
	NotAWorkDay,
	TooEarly,
	ShiftEnded
};

UENUM(BlueprintType)
enum class EDoemitzNotificationCode : uint8
{
	None,
	PlaceClosed,
	InsufficientFunds,
	ItemPurchased,
	JobNeedsOpenPlace,
	JobAccepted,
	ShiftUnavailable,
	ShiftStarted,
	ShiftFinished,
	TaskAccepted,
	TaskParcelPickedUp,
	TaskCompleted,
	TaskMissed,
	TaskNeedsItem,
	SaveSucceeded,
	LoadSucceeded,
	NoSaveFound,
	TimeScaleChanged,
	TimePaused,
	TimeResumed,
	GraphicsProfileChanged
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzOpeningStatus
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	bool bKnown = false;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	bool bOpen = false;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	bool bAlwaysOpen = false;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	bool bHasNextChange = false;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	int32 NextChangeMinute = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	int32 NextChangeWeekday = 0;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzShiftAvailability
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Economy")
	bool bCanStart = false;

	UPROPERTY(BlueprintReadOnly, Category = "Economy")
	EDoemitzShiftCheckResult Result = EDoemitzShiftCheckResult::NoJobAtPlace;

	UPROPERTY(BlueprintReadOnly, Category = "Economy")
	int32 ShiftStartMinute = 0;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzNotificationEvent
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	EDoemitzNotificationCode Code = EDoemitzNotificationCode::None;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FName PlaceId;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FName ItemId;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FName JobId;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FName TaskId;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	int64 AmountCents = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	int64 SecondaryAmountCents = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	int32 Quantity = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	int32 MinuteValue = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	bool bFlag = false;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	EDoemitzShiftCheckResult ShiftResult = EDoemitzShiftCheckResult::Ready;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FString ParameterKey;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzMapBounds
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	double ViewMinEastM = -400.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	double ViewMinNorthM = -400.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	double ViewMaxEastM = 400.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	double ViewMaxNorthM = 400.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	int32 WidthPx = 2048;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Map")
	int32 HeightPx = 2048;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzTimeInterval
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	int32 StartMinute = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	int32 EndMinute = 1440;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzDayOpeningHours
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	TArray<FDoemitzTimeInterval> Intervals;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzPlaceDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FName PlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FString DisplayName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FName BuildingId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FName Kind;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FName EconomyCategory;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FVector AccessLocation = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FName EntranceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FVector EntranceLocation = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FString EntranceSource;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	bool bAlwaysOpen = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FString OpeningHoursSource;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	TArray<FDoemitzDayOpeningHours> WeeklyOpeningHours;
};

/** Sprint 13: walk-in ground-floor interior of a place (presentation data, generated offline). */
USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzStandSpot
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FVector Location = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	double YawDegrees = 0.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FName Role;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzInteriorDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FName InteriorId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FName PlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FName RoomType;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FString DisplayName;

	/** Room outline (world XY in cm) used for the "player is inside" test. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	TArray<FVector2D> RoomPolygon;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior", meta = (Units = "cm"))
	double FloorZ = 0.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior", meta = (Units = "cm"))
	double CeilingZ = 0.0;

	/** Customer side of the counter: the place menu opens here instead of at the street door. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FVector CounterLocation = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	bool bHasNoticeBoard = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FVector NoticeBoardLocation = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FVector DoorOutsideLocation = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FVector DoorInsideLocation = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	TArray<FDoemitzStandSpot> StandSpots;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzCitizenRoute
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FName FromPlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FName ToPlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	TArray<FVector> Points;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzScheduleEntry
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	int32 StartMinute = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	EDoemitzCitizenActivity Activity = EDoemitzCitizenActivity::Home;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FName PlaceId;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzCitizenDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FName CitizenId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FString DisplayName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FName HomePlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	FName WorkPlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation", meta = (Units = "cm/s"))
	double WalkSpeedCmPerSecond = 135.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	int32 CoatVariantIndex = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	TArray<FDoemitzScheduleEntry> Schedule;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	TArray<FDoemitzScheduleEntry> SaturdaySchedule;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Simulation")
	TArray<FDoemitzScheduleEntry> SundaySchedule;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzCitizenState
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FName CitizenId;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FString DisplayName;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FName HomePlaceId;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FName WorkPlaceId;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	EDoemitzCitizenActivity CurrentActivity = EDoemitzCitizenActivity::Home;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FName CurrentPlaceId;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FName TargetPlaceId;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	bool bIsMoving = false;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	bool bIsHighDetail = false;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	bool bIsPausedForDialog = false;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FVector WorldLocation = FVector::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	FRotator WorldRotation = FRotator::ZeroRotator;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	double RouteProgressCm = 0.0;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	int32 ActiveScheduleIndex = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Simulation")
	int32 CompletedTrips = 0;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzCrossingDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FName CrossingId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FVector Location = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic", meta = (Units = "cm"))
	double TriggerRadiusCm = 350.0;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzRoadEdgeDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FName EdgeId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FName FromNodeId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FName ToNodeId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	bool bOneWay = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	bool bDeadEnd = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic", meta = (Units = "cm"))
	double WidthCm = 600.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic", meta = (Units = "cm/s"))
	double SpeedLimitCmPerSecond = 833.33;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	EDoemitzYieldRule YieldRule = EDoemitzYieldRule::None;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FName YieldSignId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	TArray<FVector> Points;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzParkingLotDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FName ParkingLotId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FString DisplayName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FVector Location = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	int32 Capacity = 4;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FString CapacitySource;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FName AccessEdgeId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic", meta = (Units = "cm"))
	double AccessDistanceCm = 0.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	TArray<FVector> SlotLocations;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzParkingLotState
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	FName ParkingLotId;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	FString DisplayName;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	FVector Location = FVector::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	int32 Capacity = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	int32 OccupiedCount = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	TArray<FName> OccupiedByVehicles;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzVehicleDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FName VehicleId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic")
	FName StartEdgeId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Traffic", meta = (Units = "cm"))
	double StartDistanceCm = 0.0;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzVehicleState
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	FName VehicleId;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	EDoemitzVehiclePhase Phase = EDoemitzVehiclePhase::Driving;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	FName CurrentEdgeId;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	FName NextEdgeId;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	FName TargetParkingLotId;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	FName CurrentParkingLotId;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	int32 ParkingSlotIndex = -1;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	double RemainingParkSeconds = 0.0;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	double DistanceOnEdgeCm = 0.0;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	double CurrentSpeedCmPerSecond = 0.0;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	FVector WorldLocation = FVector::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	FRotator WorldRotation = FRotator::ZeroRotator;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	int32 JunctionDecisions = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	bool bYieldingForRightOfWay = false;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	bool bYieldingForPrioritySign = false;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	bool bStoppingForStopSign = false;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	bool bYieldingForVehicle = false;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	bool bYieldingForPedestrian = false;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	bool bYieldingForCrossing = false;
};
