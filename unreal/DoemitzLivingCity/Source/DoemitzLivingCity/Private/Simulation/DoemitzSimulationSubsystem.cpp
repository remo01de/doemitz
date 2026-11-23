#include "Simulation/DoemitzSimulationSubsystem.h"

#include "Economy/DoemitzEconomySubsystem.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "Simulation/DoemitzCitizenSubsystem.h"
#include "Tasks/DoemitzTaskSubsystem.h"
#include "Traffic/DoemitzTrafficSubsystem.h"

namespace
{
	bool IsInsidePolygon2D(const TArray<FVector2D>& Polygon, double X, double Y)
	{
		bool bInside = false;
		const int32 Num = Polygon.Num();
		for (int32 I = 0, J = Num - 1; I < Num; J = I++)
		{
			const FVector2D& A = Polygon[I];
			const FVector2D& B = Polygon[J];
			if (((A.Y > Y) != (B.Y > Y)) && (X < (B.X - A.X) * (Y - A.Y) / (B.Y - A.Y) + A.X))
			{
				bInside = !bInside;
			}
		}
		return bInside;
	}
}

bool UDoemitzSimulationSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}
	const UWorld* World = Cast<UWorld>(Outer);
	return World != nullptr && World->IsGameWorld();
}

TStatId UDoemitzSimulationSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UDoemitzSimulationSubsystem, STATGROUP_Tickables);
}

UDoemitzSimulationSubsystem* UDoemitzSimulationSubsystem::Get(const UObject* WorldContextObject)
{
	if (!WorldContextObject)
	{
		return nullptr;
	}
	const UWorld* World = WorldContextObject->GetWorld();
	return World ? World->GetSubsystem<UDoemitzSimulationSubsystem>() : nullptr;
}

void UDoemitzSimulationSubsystem::ConfigureCoreSimulation(
	double InStartMinute,
	double InBaseTimeScale,
	const TArray<FDoemitzPlaceDefinition>& InPlaces)
{
	PlacesById.Reset();
	for (const FDoemitzPlaceDefinition& Place : InPlaces)
	{
		if (!Place.PlaceId.IsNone())
		{
			PlacesById.Add(Place.PlaceId, Place);
		}
	}

	TimeOfDayMinutes = FMath::Fmod(FMath::Max(0.0, InStartMinute), 1440.0);
	BaseTimeScale = FMath::Clamp(InBaseTimeScale > 0.0 ? InBaseTimeScale : 20.0, 1.0, 3600.0);
	TimeScale = BaseTimeScale;
	DayNumber = 1;
	DayOfWeek = 0; // Monday
	CalendarWeek = 1;
	bIsConfigured = true;

	UE_LOG(LogTemp, Display, TEXT("Doemitz core simulation configured (day=%d, dow=%d, kw=%d, %.1f min, base_scale=%.1fx): %d places"),
		DayNumber, DayOfWeek, CalendarWeek, TimeOfDayMinutes, BaseTimeScale, PlacesById.Num());
}

void UDoemitzSimulationSubsystem::MarkConfigured()
{
	bIsConfigured = true;
}

void UDoemitzSimulationSubsystem::ConfigureCityMap(UTexture2D* InMapTexture, const FDoemitzMapBounds& InMapBounds)
{
	CityMapTexture = InMapTexture;
	CityMapBounds = InMapBounds;
}

void UDoemitzSimulationSubsystem::ConfigureInteriors(const TArray<FDoemitzInteriorDefinition>& InInteriors)
{
	InteriorsById.Reset();
	InteriorIdByPlace.Reset();
	for (const FDoemitzInteriorDefinition& Interior : InInteriors)
	{
		if (Interior.InteriorId.IsNone() || Interior.PlaceId.IsNone() || Interior.RoomPolygon.Num() < 3)
		{
			continue;
		}
		InteriorsById.Add(Interior.InteriorId, Interior);
		InteriorIdByPlace.Add(Interior.PlaceId, Interior.InteriorId);
	}
}

bool UDoemitzSimulationSubsystem::GetInteriorForPlace(FName PlaceId, FDoemitzInteriorDefinition& OutInterior) const
{
	if (const FName* Id = InteriorIdByPlace.Find(PlaceId))
	{
		return GetInteriorById(*Id, OutInterior);
	}
	return false;
}

bool UDoemitzSimulationSubsystem::GetInteriorById(FName InteriorId, FDoemitzInteriorDefinition& OutInterior) const
{
	if (const FDoemitzInteriorDefinition* Found = InteriorsById.Find(InteriorId))
	{
		OutInterior = *Found;
		return true;
	}
	return false;
}

FName UDoemitzSimulationSubsystem::FindInteriorAtLocation(const FVector& WorldLocation) const
{
	for (const TPair<FName, FDoemitzInteriorDefinition>& Pair : InteriorsById)
	{
		const FDoemitzInteriorDefinition& Interior = Pair.Value;
		if (WorldLocation.Z < Interior.FloorZ - 60.0 || WorldLocation.Z > Interior.CeilingZ + 20.0)
		{
			continue;
		}
		if (IsInsidePolygon2D(Interior.RoomPolygon, WorldLocation.X, WorldLocation.Y))
		{
			return Pair.Key;
		}
	}
	return NAME_None;
}

FVector UDoemitzSimulationSubsystem::GetPlaceInteractionLocation(FName PlaceId) const
{
	FDoemitzInteriorDefinition Interior;
	if (GetInteriorForPlace(PlaceId, Interior) && !Interior.CounterLocation.IsNearlyZero())
	{
		return Interior.CounterLocation;
	}
	if (const FDoemitzPlaceDefinition* Place = PlacesById.Find(PlaceId))
	{
		return !Place->EntranceLocation.IsNearlyZero() ? Place->EntranceLocation : Place->AccessLocation;
	}
	return FVector::ZeroVector;
}

bool UDoemitzSimulationSubsystem::FindNearestNoticeBoard(const FVector& QueryLocation, double MaxRadiusCm, FName& OutInteriorId, double& OutDistanceCm) const
{
	OutInteriorId = NAME_None;
	OutDistanceCm = MaxRadiusCm;
	for (const TPair<FName, FDoemitzInteriorDefinition>& Pair : InteriorsById)
	{
		const FDoemitzInteriorDefinition& Interior = Pair.Value;
		if (!Interior.bHasNoticeBoard || FMath::Abs(QueryLocation.Z - Interior.NoticeBoardLocation.Z) > 260.0)
		{
			continue;
		}
		const double Dist2D = FVector::Dist2D(QueryLocation, Interior.NoticeBoardLocation);
		if (Dist2D <= OutDistanceCm)
		{
			OutDistanceCm = Dist2D;
			OutInteriorId = Pair.Key;
		}
	}
	return !OutInteriorId.IsNone();
}

FVector2D UDoemitzSimulationSubsystem::ProjectWorldToNormalizedMap(const FVector& WorldLocationCm) const
{
	// Coordinate contract: UE X = North (cm), UE Y = East (cm)
	const double EastM = WorldLocationCm.Y / 100.0;
	const double NorthM = WorldLocationCm.X / 100.0;
	const double SpanE = FMath::Max(1.0, CityMapBounds.ViewMaxEastM - CityMapBounds.ViewMinEastM);
	const double SpanN = FMath::Max(1.0, CityMapBounds.ViewMaxNorthM - CityMapBounds.ViewMinNorthM);
	const double U = (EastM - CityMapBounds.ViewMinEastM) / SpanE;
	const double V = (CityMapBounds.ViewMaxNorthM - NorthM) / SpanN;
	return FVector2D(U, V);
}

bool UDoemitzSimulationSubsystem::GetPlaceDefinition(FName PlaceId, FDoemitzPlaceDefinition& OutPlace) const
{
	if (const FDoemitzPlaceDefinition* Place = PlacesById.Find(PlaceId))
	{
		OutPlace = *Place;
		return true;
	}
	return false;
}

TArray<FDoemitzPlaceDefinition> UDoemitzSimulationSubsystem::GetAllPlaceDefinitions() const
{
	TArray<FDoemitzPlaceDefinition> Result;
	Result.Reserve(PlacesById.Num());
	for (const TPair<FName, FDoemitzPlaceDefinition>& Pair : PlacesById)
	{
		Result.Add(Pair.Value);
	}
	Result.Sort([](const FDoemitzPlaceDefinition& A, const FDoemitzPlaceDefinition& B) {
		return A.PlaceId.LexicalLess(B.PlaceId);
	});
	return Result;
}

bool UDoemitzSimulationSubsystem::FindNearestEntrance(
	const FVector& QueryLocation,
	double MaxRadiusCm,
	FDoemitzPlaceDefinition& OutPlace,
	double& OutDistanceCm) const
{
	const FDoemitzPlaceDefinition* BestPlace = nullptr;
	double BestDist = MaxRadiusCm;
	bool bBestIsNonHome = false;

	for (const TPair<FName, FDoemitzPlaceDefinition>& Pair : PlacesById)
	{
		const FDoemitzPlaceDefinition& Place = Pair.Value;
		FVector EntLoc = !Place.EntranceLocation.IsNearlyZero() ? Place.EntranceLocation : Place.AccessLocation;
		if (const FName* InteriorId = InteriorIdByPlace.Find(Place.PlaceId))
		{
			const FDoemitzInteriorDefinition* Interior = InteriorsById.Find(*InteriorId);
			const FVector Counter = Interior ? Interior->CounterLocation : FVector::ZeroVector;
			const bool bAtCounter = !Counter.IsNearlyZero() &&
				FMath::Abs(QueryLocation.Z - Counter.Z) <= 260.0 &&
				FVector::Dist2D(QueryLocation, Counter) <= MaxRadiusCm;
			if (bAtCounter)
			{
				EntLoc = Counter;
			}
			else if (IsPlaceOpenNow(Place.PlaceId))
			{
				continue; // open: the door opens and the menu waits at the counter inside
			}
		}
		if (FMath::Abs(QueryLocation.Z - EntLoc.Z) > 260.0)
		{
			continue;
		}
		const double Dist2D = FVector::Dist2D(QueryLocation, EntLoc);
		if (Dist2D > MaxRadiusCm)
		{
			continue;
		}
		const bool bIsNonHome = Place.Kind != FName(TEXT("home"));
		if (!BestPlace ||
			(bIsNonHome && !bBestIsNonHome && Dist2D <= BestDist + 40.0) ||
			(bIsNonHome == bBestIsNonHome && Dist2D < BestDist))
		{
			BestPlace = &Place;
			BestDist = Dist2D;
			bBestIsNonHome = bIsNonHome;
		}
	}

	if (BestPlace)
	{
		OutPlace = *BestPlace;
		OutDistanceCm = BestDist;
		return true;
	}
	OutDistanceCm = MaxRadiusCm;
	return false;
}

FDoemitzOpeningStatus UDoemitzSimulationSubsystem::GetPlaceOpeningStatus(FName PlaceId) const
{
	FDoemitzOpeningStatus Status;
	const FDoemitzPlaceDefinition* Place = PlacesById.Find(PlaceId);
	if (!Place)
	{
		return Status;
	}
	Status.bKnown = true;
	if (Place->bAlwaysOpen || Place->WeeklyOpeningHours.IsEmpty())
	{
		Status.bOpen = true;
		Status.bAlwaysOpen = true;
		return Status;
	}

	const int32 CurDay = FMath::Clamp(DayOfWeek, 0, 6);
	const double CurMin = FMath::Fmod(FMath::Max(0.0, TimeOfDayMinutes), 1440.0);

	if (Place->WeeklyOpeningHours.IsValidIndex(CurDay))
	{
		for (const FDoemitzTimeInterval& Iv : Place->WeeklyOpeningHours[CurDay].Intervals)
		{
			if (CurMin >= static_cast<double>(Iv.StartMinute) && CurMin < static_cast<double>(Iv.EndMinute))
			{
				Status.bOpen = true;
				Status.bHasNextChange = true;
				Status.NextChangeMinute = Iv.EndMinute;
				Status.NextChangeWeekday = CurDay;
				return Status;
			}
		}
	}

	Status.bOpen = false;
	for (int32 Offset = 0; Offset < 7; ++Offset)
	{
		const int32 CheckDay = (CurDay + Offset) % 7;
		if (!Place->WeeklyOpeningHours.IsValidIndex(CheckDay))
		{
			continue;
		}
		for (const FDoemitzTimeInterval& Iv : Place->WeeklyOpeningHours[CheckDay].Intervals)
		{
			if (Offset == 0 && static_cast<double>(Iv.StartMinute) <= CurMin)
			{
				continue;
			}
			Status.bHasNextChange = true;
			Status.NextChangeMinute = Iv.StartMinute;
			Status.NextChangeWeekday = CheckDay;
			return Status;
		}
	}
	return Status;
}

bool UDoemitzSimulationSubsystem::FindOpenWindowOnDay(FName PlaceId, int32 DayOfWeekIndex, int32& OutEarliestStart, int32& OutLatestEnd) const
{
	const FDoemitzPlaceDefinition* Place = PlacesById.Find(PlaceId);
	if (!Place)
	{
		return false;
	}
	if (Place->bAlwaysOpen || Place->WeeklyOpeningHours.IsEmpty())
	{
		OutEarliestStart = 480;
		OutLatestEnd = 1260;
		return true;
	}
	const int32 ClampedDay = ((DayOfWeekIndex % 7) + 7) % 7;
	if (!Place->WeeklyOpeningHours.IsValidIndex(ClampedDay) || Place->WeeklyOpeningHours[ClampedDay].Intervals.IsEmpty())
	{
		return false;
	}
	int32 Earliest = 1440;
	int32 Latest = 0;
	for (const FDoemitzTimeInterval& Iv : Place->WeeklyOpeningHours[ClampedDay].Intervals)
	{
		Earliest = FMath::Min(Earliest, Iv.StartMinute);
		Latest = FMath::Max(Latest, Iv.EndMinute);
	}
	if (Earliest >= Latest)
	{
		return false;
	}
	OutEarliestStart = Earliest;
	OutLatestEnd = Latest;
	return true;
}

EDoemitzDayKind UDoemitzSimulationSubsystem::GetDayKind() const
{
	if (DayOfWeek == 5)
	{
		return EDoemitzDayKind::Saturday;
	}
	if (DayOfWeek == 6)
	{
		return EDoemitzDayKind::Sunday;
	}
	return EDoemitzDayKind::Weekday;
}

void UDoemitzSimulationSubsystem::SetTimeScale(double NewTimeScale)
{
	if (FMath::IsFinite(NewTimeScale))
	{
		TimeScale = FMath::Clamp(NewTimeScale, 0.0, 3600.0);
	}
}

void UDoemitzSimulationSubsystem::SetTimeOfDayMinutes(double NewMinutes)
{
	if (FMath::IsFinite(NewMinutes) && NewMinutes >= 0.0)
	{
		TimeOfDayMinutes = FMath::Fmod(NewMinutes, 1440.0);
		if (UWorld* World = GetWorld())
		{
			if (UDoemitzTaskSubsystem* Tasks = World->GetSubsystem<UDoemitzTaskSubsystem>())
			{
				Tasks->CheckTaskDeadlines();
			}
		}
	}
}

void UDoemitzSimulationSubsystem::SetDayNumber(int32 NewDayNumber)
{
	DayNumber = FMath::Max(1, NewDayNumber);
	DayOfWeek = (DayNumber - 1) % 7;
	CalendarWeek = 1 + ((DayNumber - 1) / 7);
}

void UDoemitzSimulationSubsystem::SetDayOfWeekForTest(int32 NewDayOfWeek)
{
	DayOfWeek = ((NewDayOfWeek % 7) + 7) % 7;
}

void UDoemitzSimulationSubsystem::RestoreClockState(
	int32 InDayNumber,
	int32 InDayOfWeek,
	int32 InCalendarWeek,
	double InTimeOfDayMinutes,
	double InTimeScale)
{
	DayNumber = FMath::Max(1, InDayNumber);
	DayOfWeek = ((InDayOfWeek % 7) + 7) % 7;
	CalendarWeek = FMath::Max(1, InCalendarWeek);
	TimeOfDayMinutes = FMath::Fmod(FMath::Max(0.0, InTimeOfDayMinutes), 1440.0);
	TimeScale = FMath::Clamp(InTimeScale, 0.0, 3600.0);
}

bool UDoemitzSimulationSubsystem::IsPlaceOpen(FName PlaceId, int32 DayOfWeekIndex, double MinuteOfDay) const
{
	const FDoemitzPlaceDefinition* Place = PlacesById.Find(PlaceId);
	if (!Place)
	{
		return false;
	}
	if (Place->bAlwaysOpen || Place->WeeklyOpeningHours.IsEmpty())
	{
		return true;
	}
	const int32 ClampedDay = ((DayOfWeekIndex % 7) + 7) % 7;
	if (!Place->WeeklyOpeningHours.IsValidIndex(ClampedDay))
	{
		return true;
	}
	const double WrappedMin = FMath::Fmod(FMath::Max(0.0, MinuteOfDay), 1440.0);
	for (const FDoemitzTimeInterval& Interval : Place->WeeklyOpeningHours[ClampedDay].Intervals)
	{
		if (WrappedMin >= static_cast<double>(Interval.StartMinute) &&
			WrappedMin < static_cast<double>(Interval.EndMinute))
		{
			return true;
		}
	}
	return false;
}

bool UDoemitzSimulationSubsystem::IsPlaceOpenNow(FName PlaceId) const
{
	return IsPlaceOpen(PlaceId, DayOfWeek, TimeOfDayMinutes);
}

void UDoemitzSimulationSubsystem::Tick(float DeltaTime)
{
	if (!bIsConfigured || DeltaTime <= 0.0f)
	{
		return;
	}

	if (NotificationRemainingSeconds > 0.0)
	{
		NotificationRemainingSeconds = FMath::Max(0.0, NotificationRemainingSeconds - static_cast<double>(DeltaTime));
		if (NotificationRemainingSeconds <= 0.0)
		{
			LastNotificationEvent = FDoemitzNotificationEvent();
		}
	}

	if (TimeScale <= 0.0)
	{
		return;
	}

	UWorld* World = GetWorld();
	UDoemitzEconomySubsystem* Economy = World ? World->GetSubsystem<UDoemitzEconomySubsystem>() : nullptr;
	UDoemitzTaskSubsystem* Tasks = World ? World->GetSubsystem<UDoemitzTaskSubsystem>() : nullptr;
	UDoemitzCitizenSubsystem* Citizens = World ? World->GetSubsystem<UDoemitzCitizenSubsystem>() : nullptr;
	UDoemitzTrafficSubsystem* Traffic = World ? World->GetSubsystem<UDoemitzTrafficSubsystem>() : nullptr;

	// 1. Advance world clock & process day rollovers
	const double ClampedDelta = FMath::Min(static_cast<double>(DeltaTime), 0.1);
	const double SimMinutesDelta = (static_cast<double>(DeltaTime) * TimeScale) / 60.0;
	TimeOfDayMinutes += SimMinutesDelta;
	bool bDayRolledOver = false;
	while (TimeOfDayMinutes >= 1440.0)
	{
		TimeOfDayMinutes -= 1440.0;
		DayNumber += 1;
		DayOfWeek = (DayOfWeek + 1) % 7;
		const bool bNewWeek = (DayOfWeek == 0);
		if (bNewWeek)
		{
			CalendarWeek += 1;
		}
		bDayRolledOver = true;
		if (Economy)
		{
			Economy->OnDayRollover(bNewWeek);
		}
	}

	// 2. Tasks & Economy work shift
	if (Tasks)
	{
		Tasks->CheckTaskDeadlines();
		if (bDayRolledOver)
		{
			Tasks->GenerateDailyTasks();
		}
	}
	if (Economy)
	{
		Economy->UpdateActiveWorkShift();
	}

	// 3. Citizens (hybrid time scale: visible = WalkSpeed * dt * Multiplier, off-screen = WalkSpeed * dt * TimeScale)
	const double TimeMultiplier = GetTimeScaleMultiplier();
	if (Citizens)
	{
		Citizens->StepCitizens(ClampedDelta, TimeScale, BaseTimeScale);
	}

	// 4. Traffic (scales cleanly with TimeMultiplier via sub-stepping)
	if (Traffic)
	{
		Traffic->StepTraffic(ClampedDelta, TimeMultiplier);
	}
}

void UDoemitzSimulationSubsystem::PushNotificationEvent(const FDoemitzNotificationEvent& Event, double DurationSeconds)
{
	LastNotificationEvent = Event;
	NotificationRemainingSeconds = FMath::Max(0.5, DurationSeconds);
}

FDoemitzNotificationEvent UDoemitzSimulationSubsystem::GetLastNotificationEvent() const
{
	return NotificationRemainingSeconds > 0.0 ? LastNotificationEvent : FDoemitzNotificationEvent();
}
