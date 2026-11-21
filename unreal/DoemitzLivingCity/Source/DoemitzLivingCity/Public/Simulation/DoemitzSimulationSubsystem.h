#pragma once

#include "CoreMinimal.h"
#include "Economy/DoemitzEconomyDataAsset.h"
#include "Subsystems/WorldSubsystem.h"
#include "Tasks/DoemitzTaskDataAsset.h"
#include "DoemitzSimulationSubsystem.generated.h"

class ADoemitzCitizenActor;
class UStaticMesh;
class UTexture2D;

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

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzSimulationSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual bool IsTickable() const override { return bIsConfigured; }
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

	void ConfigureSimulation(
		double InStartMinute,
		double InTimeScale,
		const TArray<FDoemitzPlaceDefinition>& InPlaces,
		const TArray<FDoemitzCitizenRoute>& InRoutes,
		const TArray<FDoemitzCitizenDefinition>& InCitizens);

	void ConfigureCitizenPool(
		const TArray<TObjectPtr<UStaticMesh>>& InMeshVariants,
		double InLodRadiusCm = 15000.0);

	void ConfigureTrafficNetwork(
		int32 InTrafficSeed,
		const TArray<FDoemitzRoadEdgeDefinition>& InRoadEdges,
		const TArray<FDoemitzVehicleDefinition>& InVehicles,
		const TArray<FDoemitzCrossingDefinition>& InCrossings = TArray<FDoemitzCrossingDefinition>(),
		const TArray<FDoemitzParkingLotDefinition>& InParkingLots = TArray<FDoemitzParkingLotDefinition>());

	void ConfigureEconomy(const UDoemitzEconomyDataAsset* InEconomyData);
	void ConfigureTasks(const UDoemitzTaskDataAsset* InTaskData);
	void ConfigureCityMap(UTexture2D* InMapTexture, const FDoemitzMapBounds& InMapBounds);

	UFUNCTION(BlueprintPure, Category = "Simulation", meta = (WorldContext = "WorldContextObject"))
	static UDoemitzSimulationSubsystem* Get(const UObject* WorldContextObject);

	UFUNCTION(BlueprintPure, Category = "Map")
	UTexture2D* GetCityMapTexture() const { return CityMapTexture.Get(); }

	UFUNCTION(BlueprintPure, Category = "Map")
	FDoemitzMapBounds GetCityMapBounds() const { return CityMapBounds; }

	UFUNCTION(BlueprintPure, Category = "Map")
	FVector2D ProjectWorldToNormalizedMap(const FVector& WorldLocationCm) const;

	// --- Economy ---
	UFUNCTION(BlueprintPure, Category = "Economy")
	int64 GetPlayerMoneyCents() const { return PlayerMoneyCents; }

	UFUNCTION(BlueprintCallable, Category = "Economy")
	void SetPlayerMoneyCentsForTest(int64 NewAmountCents);

	UFUNCTION(BlueprintPure, Category = "Economy")
	int32 GetLedgerCount() const { return LedgerEntries.Num(); }

	UFUNCTION(BlueprintPure, Category = "Economy")
	TArray<FDoemitzLedgerEntry> GetLedgerEntries() const { return LedgerEntries; }

	UFUNCTION(BlueprintPure, Category = "Economy")
	int32 GetInventoryQuantity(FName ItemId) const;

	UFUNCTION(BlueprintPure, Category = "Economy")
	TArray<FDoemitzInventoryItem> GetAllInventoryItems() const;

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool GetItemDefinition(FName ItemId, FDoemitzItemDefinition& OutItem) const;

	UFUNCTION(BlueprintPure, Category = "Economy")
	TArray<FDoemitzItemDefinition> GetItemsForPlace(FName PlaceId) const;

	UFUNCTION(BlueprintCallable, Category = "Economy")
	bool BuyItem(FName PlaceId, FName ItemId, int32 Quantity = 1);

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool GetJobForPlace(FName PlaceId, FDoemitzJobDefinition& OutJob) const;

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool GetJobDefinition(FName JobId, FDoemitzJobDefinition& OutJob) const;

	UFUNCTION(BlueprintPure, Category = "Economy")
	FName GetActiveJobId() const { return ActiveJobId; }

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool IsWorkingShift() const { return bIsWorkingShift; }

	UFUNCTION(BlueprintCallable, Category = "Economy")
	bool AcceptJob(FName PlaceId);

	UFUNCTION(BlueprintPure, Category = "Economy")
	FDoemitzShiftAvailability CheckWorkShiftAvailability(FName PlaceId) const;

	UFUNCTION(BlueprintCallable, Category = "Economy")
	bool StartWorkShift(FName PlaceId);

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool GetPlaceRevenue(FName PlaceId, int64& OutDailyCents, int64& OutWeeklyCents) const;

	// --- Tasks ---
	UFUNCTION(BlueprintPure, Category = "Tasks")
	TArray<FDoemitzTaskInstance> GetAllTasks() const { return Tasks; }

	UFUNCTION(BlueprintPure, Category = "Tasks")
	TArray<FDoemitzTaskInstance> GetTasksByStatus(EDoemitzTaskStatus Status) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetTaskById(FName TaskId, FDoemitzTaskInstance& OutTask) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetPrimaryActiveTask(FDoemitzTaskInstance& OutTask) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetTaskOfferedByCitizen(FName CitizenId, FDoemitzTaskInstance& OutTask) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetActiveFetchTaskForCitizen(FName CitizenId, FDoemitzTaskInstance& OutTask) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetActiveErrandForPlace(FName PlaceId, FDoemitzTaskInstance& OutTask, bool& bOutIsDelivery) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetActiveTaskTargetLocation(FVector& OutWorldLocation, FName& OutTargetPlaceId, FName& OutTargetCitizenId) const;

	UFUNCTION(BlueprintCallable, Category = "Tasks")
	bool AcceptTask(FName TaskId);

	UFUNCTION(BlueprintCallable, Category = "Tasks")
	bool PickupTaskParcel(FName TaskId);

	UFUNCTION(BlueprintCallable, Category = "Tasks")
	bool DeliverTaskParcel(FName TaskId);

	UFUNCTION(BlueprintCallable, Category = "Tasks")
	bool CompleteFetchTask(FName TaskId);

	UFUNCTION(BlueprintCallable, Category = "Tasks")
	void CheckTaskDeadlines();

	// --- Places & Time ---
	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool GetPlaceDefinition(FName PlaceId, FDoemitzPlaceDefinition& OutPlace) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	TArray<FDoemitzPlaceDefinition> GetAllPlaceDefinitions() const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool FindNearestEntrance(const FVector& QueryLocation, double MaxRadiusCm, FDoemitzPlaceDefinition& OutPlace, double& OutDistanceCm) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	FDoemitzOpeningStatus GetPlaceOpeningStatus(FName PlaceId) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	double GetTimeOfDayMinutes() const { return TimeOfDayMinutes; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetDayNumber() const { return DayNumber; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetDayOfWeek() const { return DayOfWeek; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetCalendarWeek() const { return CalendarWeek; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	EDoemitzDayKind GetDayKind() const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	double GetTimeScale() const { return TimeScale; }

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetTimeScale(double NewTimeScale);

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetTimeOfDayMinutes(double NewMinutes);

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetDayNumber(int32 NewDayNumber);

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetDayOfWeekForTest(int32 NewDayOfWeek);

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool IsPlaceOpen(FName PlaceId, int32 DayOfWeekIndex, double MinuteOfDay) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool IsPlaceOpenNow(FName PlaceId) const;

	// --- Citizens ---
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

	// --- Traffic & Parking ---
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
	TArray<FName> GetAllVehicleIds() const;

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

	// --- SaveGame ---
	UFUNCTION(BlueprintCallable, Category = "SaveGame")
	bool SaveCityState(const FString& SlotName = TEXT("DoemitzQuicksave"));

	UFUNCTION(BlueprintCallable, Category = "SaveGame")
	bool LoadCityState(const FString& SlotName = TEXT("DoemitzQuicksave"));

	UFUNCTION(BlueprintPure, Category = "SaveGame")
	bool DoesSaveExist(const FString& SlotName = TEXT("DoemitzQuicksave")) const;

	// --- Structured Notification Events (formatted in UI layer) ---
	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void PushNotificationEvent(const FDoemitzNotificationEvent& Event, double DurationSeconds = 4.0);

	UFUNCTION(BlueprintPure, Category = "Simulation")
	FDoemitzNotificationEvent GetLastNotificationEvent() const;

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
		TArray<FName> SlotOccupants; // size = max(1, SlotLocations.Num()), NAME_None when free
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

	static int32 FindScheduleIndex(const TArray<FDoemitzScheduleEntry>& Schedule, double MinuteOfDay);
	static FName MakeRouteKey(FName FromPlaceId, FName ToPlaceId);
	const TArray<FDoemitzScheduleEntry>& GetActiveScheduleForDay(const FDoemitzCitizenDefinition& Def) const;
	FDoemitzScheduleEntry ResolveDesiredEntry(const FDoemitzCitizenDefinition& Def, int32& OutIndex) const;
	void ResetCitizenToCurrentSchedule(FCitizenRecord& Record);
	void BuildRouteCache(FCitizenRecord& Record, FName FromPlaceId, FName DestinationPlaceId);
	void StartTrip(FCitizenRecord& Record, FName DestinationPlaceId);
	void UpdateCitizen(FCitizenRecord& Record, double DeltaSeconds);
	void UpdateCitizenLodPool();
	ADoemitzCitizenActor* AcquirePooledCitizenActor(const FCitizenRecord& Record);
	void ReleaseCitizenActor(FName CitizenId);

	void SampleEdgePose(const FRoadEdgeRecord& Edge, double DistanceCm, FVector& OutLocation, FRotator& OutRotation) const;
	FName ChooseNextEdge(const FVehicleRecord& Record) const;
	bool ComputeEdgePath(FName StartEdgeId, FName GoalEdgeId, TArray<FName>& OutPath) const;
	FName ChooseNextParkingLot(const FVehicleRecord& Record, FName ExcludeLotId) const;
	void PlanRouteToParking(FVehicleRecord& Record, FName ParkingLotId);
	int32 TryReserveParkingSlot(FName ParkingLotId, FName VehicleId, FVector& OutSlotLocation);
	void ReleaseParkingSlot(FVehicleRecord& Record);
	FName FindNearestDrivableEdge(const FVector& Location, double& OutDistanceCm) const;
	void UpdateTraffic(double DeltaSeconds);
	void ReleaseJunctionReservation(FVehicleRecord& Record);

	void AppendLedgerEntry(FName PlaceId, int64 AmountCents, const FString& Description);
	void AddPlaceRevenue(FName PlaceId, int64 AmountCents);
	void RecordCitizenShoppingRevenue(FName CitizenId, FName PlaceId);
	void UpdateActiveWorkShift();
	void FinishWorkShift();
	void ResetEconomyToDefaults();

	void GenerateDailyTasks();
	bool FindOpenWindowOnDay(FName PlaceId, int32 DayOfWeekIndex, int32& OutEarliestStart, int32& OutLatestEnd) const;

	bool bIsConfigured = false;
	double TimeOfDayMinutes = 470.0;
	double TimeScale = 60.0;
	int32 DayNumber = 1;
	int32 DayOfWeek = 0; // 0 = Mo .. 6 = So
	int32 CalendarWeek = 1;
	int32 TrafficSeed = 202607;
	double CitizenLodRadiusCm = 15000.0;
	double CoarseUpdateIntervalSeconds = 1.0;

	FDoemitzNotificationEvent LastNotificationEvent;
	double NotificationRemainingSeconds = 0.0;

	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> CityMapTexture;
	FDoemitzMapBounds CityMapBounds;

	static constexpr int32 MaxLedgerEntries = 200;
	int32 EconomySeed = 202609;
	int64 StartingMoneyCents = 0;
	int64 PlayerMoneyCents = 0;
	int32 NextTransactionId = 1;
	FName ActiveJobId;
	bool bIsWorkingShift = false;
	FName ActiveShiftPlaceId;
	double ShiftActualStartMinute = 0.0;
	double PreShiftTimeScale = 60.0;
	TMap<FName, TArray<FDoemitzItemDefinition>> AssortmentsByCategory;
	TMap<FName, FDoemitzItemDefinition> ItemsById;
	TMap<FName, FDoemitzJobDefinition> JobsById;
	TMap<FName, FName> JobIdByPlace;
	TArray<FDoemitzLedgerEntry> LedgerEntries;
	TMap<FName, int32> PlayerInventory;
	TMap<FName, FDoemitzPlaceRevenue> PlaceRevenues;
	TSet<FName> CitizenDailyShoppingRecorded;

	int32 TaskSeed = 202610;
	int32 DailyMinTasks = 3;
	int32 DailyMaxTasks = 5;
	TArray<FDoemitzTaskTemplate> TaskTemplates;
	TArray<FDoemitzTaskInstance> Tasks;

	TMap<FName, FDoemitzPlaceDefinition> PlacesById;
	TMap<FName, FDoemitzCitizenRoute> RoutesByKey;
	TMap<FName, FCitizenRecord> CitizenRecords;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMesh>> CitizenMeshVariants;

	UPROPERTY(Transient)
	TMap<FName, TObjectPtr<ADoemitzCitizenActor>> ActiveCitizenActors;

	UPROPERTY(Transient)
	TArray<TObjectPtr<ADoemitzCitizenActor>> PooledCitizenActors;

	TMap<FName, FRoadEdgeRecord> RoadEdgesById;
	TMap<FName, TArray<FName>> OutgoingEdgesByNode;
	TArray<FDoemitzCrossingDefinition> Crossings;
	TMap<FName, FParkingLotRecord> ParkingLotsById;
	TArray<FName> OrderedParkingLotIds;
	TMap<FName, FVehicleRecord> VehicleRecords;
	TArray<FName> OrderedVehicleIds;
	TMap<FName, FName> JunctionReservations;
};
