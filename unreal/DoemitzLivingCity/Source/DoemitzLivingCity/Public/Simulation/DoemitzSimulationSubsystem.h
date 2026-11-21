#pragma once

#include "CoreMinimal.h"
#include "Economy/DoemitzEconomyDataAsset.h"
#include "Subsystems/WorldSubsystem.h"
#include "DoemitzSimulationSubsystem.generated.h"

class ADoemitzCitizenActor;
class UStaticMesh;

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
	TArray<FVector> Points;
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
	FName CurrentEdgeId;

	UPROPERTY(BlueprintReadOnly, Category = "Traffic")
	FName NextEdgeId;

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
		const TArray<FDoemitzCrossingDefinition>& InCrossings = TArray<FDoemitzCrossingDefinition>());

	void ConfigureEconomy(const UDoemitzEconomyDataAsset* InEconomyData);

	UFUNCTION(BlueprintPure, Category = "Simulation", meta = (WorldContext = "WorldContextObject"))
	static UDoemitzSimulationSubsystem* Get(const UObject* WorldContextObject);

	UFUNCTION(BlueprintPure, Category = "Economy")
	static FString FormatCentsEur(int64 AmountCents);

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
	TArray<FDoemitzItemDefinition> GetItemsForPlace(FName PlaceId) const;

	UFUNCTION(BlueprintCallable, Category = "Economy")
	bool BuyItem(FName PlaceId, FName ItemId, int32 Quantity = 1);

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool GetJobForPlace(FName PlaceId, FDoemitzJobDefinition& OutJob) const;

	UFUNCTION(BlueprintPure, Category = "Economy")
	FName GetActiveJobId() const { return ActiveJobId; }

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool IsWorkingShift() const { return bIsWorkingShift; }

	UFUNCTION(BlueprintCallable, Category = "Economy")
	bool AcceptJob(FName PlaceId);

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool CanStartWorkShift(FName PlaceId, FString& OutReason) const;

	UFUNCTION(BlueprintCallable, Category = "Economy")
	bool StartWorkShift(FName PlaceId);

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool GetPlaceRevenue(FName PlaceId, int64& OutDailyCents, int64& OutWeeklyCents) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool GetPlaceDefinition(FName PlaceId, FDoemitzPlaceDefinition& OutPlace) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool FindNearestEntrance(const FVector& QueryLocation, double MaxRadiusCm, FDoemitzPlaceDefinition& OutPlace, double& OutDistanceCm) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	FString GetPlaceOpeningStatusText(FName PlaceId) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	double GetTimeOfDayMinutes() const { return TimeOfDayMinutes; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetDayNumber() const { return DayNumber; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetDayOfWeek() const { return DayOfWeek; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetCalendarWeek() const { return CalendarWeek; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	FString GetDayOfWeekShortName() const;

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

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetCitizenCount() const { return CitizenRecords.Num(); }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool GetCitizenState(FName CitizenId, FDoemitzCitizenState& OutState) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	TArray<FName> GetAllCitizenIds() const;

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

	UFUNCTION(BlueprintCallable, Category = "Traffic")
	bool SetVehicleEdgePositionForTest(FName VehicleId, FName EdgeId, double DistanceOnEdgeCm, double SpeedCmPerSecond = 0.0);

	UFUNCTION(BlueprintCallable, Category = "SaveGame")
	bool SaveCityState(const FString& SlotName = TEXT("DoemitzQuicksave"));

	UFUNCTION(BlueprintCallable, Category = "SaveGame")
	bool LoadCityState(const FString& SlotName = TEXT("DoemitzQuicksave"));

	UFUNCTION(BlueprintPure, Category = "SaveGame")
	bool DoesSaveExist(const FString& SlotName = TEXT("DoemitzQuicksave")) const;

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetNotification(const FString& Message, double DurationSeconds = 4.0);

	UFUNCTION(BlueprintPure, Category = "Simulation")
	FString GetLastNotification() const;

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

	struct FVehicleRecord
	{
		FDoemitzVehicleDefinition Definition;
		FDoemitzVehicleState State;
		FName ReservedNodeId;
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
	FName FindNearestDrivableEdge(const FVector& Location, double& OutDistanceCm) const;
	void UpdateTraffic(double DeltaSeconds);
	void ReleaseJunctionReservation(FVehicleRecord& Record);

	void AppendLedgerEntry(FName PlaceId, int64 AmountCents, const FString& Description);
	void AddPlaceRevenue(FName PlaceId, int64 AmountCents);
	void RecordCitizenShoppingRevenue(FName CitizenId, FName PlaceId);
	void UpdateActiveWorkShift();
	void FinishWorkShift();
	void ResetEconomyToDefaults();

	bool bIsConfigured = false;
	double TimeOfDayMinutes = 470.0;
	double TimeScale = 60.0;
	int32 DayNumber = 1;
	int32 DayOfWeek = 0; // 0 = Mo .. 6 = So
	int32 CalendarWeek = 1;
	int32 TrafficSeed = 202607;
	double CitizenLodRadiusCm = 15000.0;
	double CoarseUpdateIntervalSeconds = 1.0;
	FString LastNotification;
	double NotificationRemainingSeconds = 0.0;

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
	TMap<FName, FDoemitzJobDefinition> JobsById;
	TMap<FName, FName> JobIdByPlace;
	TArray<FDoemitzLedgerEntry> LedgerEntries;
	TMap<FName, int32> PlayerInventory;
	TMap<FName, FDoemitzPlaceRevenue> PlaceRevenues;
	TSet<FName> CitizenDailyShoppingRecorded;

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
	TMap<FName, FVehicleRecord> VehicleRecords;
	TArray<FName> OrderedVehicleIds;
	TMap<FName, FName> JunctionReservations;
};
