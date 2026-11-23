#pragma once

#include "CoreMinimal.h"
#include "Simulation/DoemitzSimulationTypes.h"
#include "Subsystems/WorldSubsystem.h"
#include "DoemitzSimulationSubsystem.generated.h"

class UTexture2D;

/**
 * Core world simulation coordinator: owns the deterministic simulation clock (BaseTimeScale, TimeScale, calendar),
 * places & opening hours, walk-in interiors, city map bounds/texture, and notification events.
 * Ticks sibling domain subsystems (Economy, Tasks, Citizens, Traffic) in fixed deterministic order.
 */
UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzSimulationSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual bool IsTickable() const override { return bIsConfigured; }
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

	UFUNCTION(BlueprintPure, Category = "Simulation", meta = (WorldContext = "WorldContextObject"))
	static UDoemitzSimulationSubsystem* Get(const UObject* WorldContextObject);

	void ConfigureCoreSimulation(
		double InStartMinute,
		double InBaseTimeScale,
		const TArray<FDoemitzPlaceDefinition>& InPlaces);

	void ConfigureCityMap(UTexture2D* InMapTexture, const FDoemitzMapBounds& InMapBounds);
	void ConfigureInteriors(const TArray<FDoemitzInteriorDefinition>& InInteriors);
	void MarkConfigured();

	bool IsConfigured() const { return bIsConfigured; }

	// --- Clock & Calendar ---
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
	double GetBaseTimeScale() const { return BaseTimeScale; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	double GetTimeScale() const { return TimeScale; }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	double GetTimeScaleMultiplier() const { return BaseTimeScale > 0.0 ? (TimeScale / BaseTimeScale) : 0.0; }

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetTimeScale(double NewTimeScale);

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetTimeOfDayMinutes(double NewMinutes);

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetDayNumber(int32 NewDayNumber);

	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void SetDayOfWeekForTest(int32 NewDayOfWeek);

	void RestoreClockState(int32 InDayNumber, int32 InDayOfWeek, int32 InCalendarWeek, double InTimeOfDayMinutes, double InTimeScale);

	// --- Places & Opening Hours ---
	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool GetPlaceDefinition(FName PlaceId, FDoemitzPlaceDefinition& OutPlace) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool HasPlace(FName PlaceId) const { return PlacesById.Contains(PlaceId); }

	UFUNCTION(BlueprintPure, Category = "Simulation")
	TArray<FDoemitzPlaceDefinition> GetAllPlaceDefinitions() const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool FindNearestEntrance(const FVector& QueryLocation, double MaxRadiusCm, FDoemitzPlaceDefinition& OutPlace, double& OutDistanceCm) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	FDoemitzOpeningStatus GetPlaceOpeningStatus(FName PlaceId) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool IsPlaceOpen(FName PlaceId, int32 DayOfWeekIndex, double MinuteOfDay) const;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	bool IsPlaceOpenNow(FName PlaceId) const;

	bool FindOpenWindowOnDay(FName PlaceId, int32 DayOfWeekIndex, int32& OutEarliestStart, int32& OutLatestEnd) const;

	// --- Interiors (presentation data) ---
	UFUNCTION(BlueprintPure, Category = "Interior")
	int32 GetInteriorCount() const { return InteriorsById.Num(); }

	UFUNCTION(BlueprintPure, Category = "Interior")
	bool GetInteriorForPlace(FName PlaceId, FDoemitzInteriorDefinition& OutInterior) const;

	UFUNCTION(BlueprintPure, Category = "Interior")
	bool GetInteriorById(FName InteriorId, FDoemitzInteriorDefinition& OutInterior) const;

	/** Interior whose room contains the location (2D polygon test and floor..ceiling band), NAME_None outside. */
	UFUNCTION(BlueprintPure, Category = "Interior")
	FName FindInteriorAtLocation(const FVector& WorldLocation) const;

	/** Where the place menu opens: the counter inside for places with an interior, otherwise the entrance. */
	UFUNCTION(BlueprintPure, Category = "Interior")
	FVector GetPlaceInteractionLocation(FName PlaceId) const;

	UFUNCTION(BlueprintPure, Category = "Interior")
	bool FindNearestNoticeBoard(const FVector& QueryLocation, double MaxRadiusCm, FName& OutInteriorId, double& OutDistanceCm) const;

	// --- City Map ---
	UFUNCTION(BlueprintPure, Category = "Map")
	UTexture2D* GetCityMapTexture() const { return CityMapTexture.Get(); }

	UFUNCTION(BlueprintPure, Category = "Map")
	FDoemitzMapBounds GetCityMapBounds() const { return CityMapBounds; }

	UFUNCTION(BlueprintPure, Category = "Map")
	FVector2D ProjectWorldToNormalizedMap(const FVector& WorldLocationCm) const;

	// --- Structured Notification Events (formatted in UI layer) ---
	UFUNCTION(BlueprintCallable, Category = "Simulation")
	void PushNotificationEvent(const FDoemitzNotificationEvent& Event, double DurationSeconds = 4.0);

	UFUNCTION(BlueprintPure, Category = "Simulation")
	FDoemitzNotificationEvent GetLastNotificationEvent() const;

private:
	bool bIsConfigured = false;
	double TimeOfDayMinutes = 470.0;
	double BaseTimeScale = 20.0;
	double TimeScale = 20.0;
	int32 DayNumber = 1;
	int32 DayOfWeek = 0; // 0 = Mo .. 6 = So
	int32 CalendarWeek = 1;

	FDoemitzNotificationEvent LastNotificationEvent;
	double NotificationRemainingSeconds = 0.0;

	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> CityMapTexture;
	FDoemitzMapBounds CityMapBounds;

	TMap<FName, FDoemitzPlaceDefinition> PlacesById;
	TMap<FName, FDoemitzInteriorDefinition> InteriorsById;
	TMap<FName, FName> InteriorIdByPlace;
};
