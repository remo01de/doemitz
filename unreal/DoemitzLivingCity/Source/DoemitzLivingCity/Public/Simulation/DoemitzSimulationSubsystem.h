#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "DoemitzSimulationSubsystem.generated.h"

UENUM(BlueprintType)
enum class EDoemitzCitizenActivity : uint8
{
	Home,
	Commuting,
	Working,
	Shopping,
	Strolling
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
	FVector AccessLocation = FVector::ZeroVector;
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
	TArray<FDoemitzScheduleEntry> Schedule;
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

	UFUNCTION(BlueprintPure, Category = "Simulation", meta = (WorldContext = "WorldContextObject"))
	static UDoemitzSimulationSubsystem* Get(const UObject* WorldContextObject);

	UFUNCTION(BlueprintPure, Category = "Simulation")
	double GetTimeOfDayMinutes() const { return TimeOfDayMinutes; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetDayNumber() const { return DayNumber; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	double GetTimeScale() const { return TimeScale; }

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetTimeScale(double NewTimeScale);

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetTimeOfDayMinutes(double NewMinutes);

	UFUNCTION(BlueprintPure, Category = "Simulation")
	int32 GetCitizenCount() const { return CitizenRecords.Num(); }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool GetCitizenState(FName CitizenId, FDoemitzCitizenState& OutState) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	TArray<FName> GetAllCitizenIds() const;

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
	};

	static int32 FindScheduleIndex(const TArray<FDoemitzScheduleEntry>& Schedule, double MinuteOfDay);
	static FName MakeRouteKey(FName FromPlaceId, FName ToPlaceId);
	void BuildRouteCache(FCitizenRecord& Record, FName FromPlaceId, FName DestinationPlaceId);
	void StartTrip(FCitizenRecord& Record, FName DestinationPlaceId);
	void UpdateCitizen(FCitizenRecord& Record, double DeltaSeconds);

	bool bIsConfigured = false;
	double TimeOfDayMinutes = 470.0;
	double TimeScale = 60.0;
	int32 DayNumber = 1;
	FString LastNotification;
	double NotificationRemainingSeconds = 0.0;

	TMap<FName, FDoemitzPlaceDefinition> PlacesById;
	TMap<FName, FDoemitzCitizenRoute> RoutesByKey;
	TMap<FName, FCitizenRecord> CitizenRecords;
};
