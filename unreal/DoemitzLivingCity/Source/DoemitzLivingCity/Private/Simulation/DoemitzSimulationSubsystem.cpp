#include "Simulation/DoemitzSimulationSubsystem.h"

#include "Algo/BinarySearch.h"
#include "Engine/World.h"

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

FName UDoemitzSimulationSubsystem::MakeRouteKey(FName FromPlaceId, FName ToPlaceId)
{
	return FName(*FString::Printf(TEXT("%s->%s"), *FromPlaceId.ToString(), *ToPlaceId.ToString()));
}

int32 UDoemitzSimulationSubsystem::FindScheduleIndex(const TArray<FDoemitzScheduleEntry>& Schedule, double MinuteOfDay)
{
	int32 BestIndex = 0;
	for (int32 Index = 0; Index < Schedule.Num(); ++Index)
	{
		if (MinuteOfDay >= static_cast<double>(Schedule[Index].StartMinute))
		{
			BestIndex = Index;
		}
		else
		{
			break;
		}
	}
	return BestIndex;
}

void UDoemitzSimulationSubsystem::ConfigureSimulation(
	double InStartMinute,
	double InTimeScale,
	const TArray<FDoemitzPlaceDefinition>& InPlaces,
	const TArray<FDoemitzCitizenRoute>& InRoutes,
	const TArray<FDoemitzCitizenDefinition>& InCitizens)
{
	PlacesById.Reset();
	for (const FDoemitzPlaceDefinition& Place : InPlaces)
	{
		if (!Place.PlaceId.IsNone())
		{
			PlacesById.Add(Place.PlaceId, Place);
		}
	}

	RoutesByKey.Reset();
	for (const FDoemitzCitizenRoute& Route : InRoutes)
	{
		if (!Route.FromPlaceId.IsNone() && !Route.ToPlaceId.IsNone() && Route.Points.Num() >= 2)
		{
			RoutesByKey.Add(MakeRouteKey(Route.FromPlaceId, Route.ToPlaceId), Route);
		}
	}

	TimeOfDayMinutes = FMath::Fmod(FMath::Max(0.0, InStartMinute), 1440.0);
	TimeScale = FMath::Clamp(InTimeScale, 0.0, 3600.0);
	DayNumber = 1;

	CitizenRecords.Reset();
	for (const FDoemitzCitizenDefinition& Def : InCitizens)
	{
		if (Def.CitizenId.IsNone() || Def.Schedule.IsEmpty())
		{
			continue;
		}

		FCitizenRecord Record;
		Record.Definition = Def;
		Record.State.CitizenId = Def.CitizenId;
		Record.State.DisplayName = Def.DisplayName;
		Record.State.HomePlaceId = Def.HomePlaceId;
		Record.State.WorkPlaceId = Def.WorkPlaceId;

		const int32 InitialIndex = FindScheduleIndex(Def.Schedule, TimeOfDayMinutes);
		const FDoemitzScheduleEntry& Entry = Def.Schedule[InitialIndex];
		Record.State.ActiveScheduleIndex = InitialIndex;
		Record.State.CurrentActivity = Entry.Activity;
		Record.State.CurrentPlaceId = Entry.PlaceId;
		Record.State.TargetPlaceId = Entry.PlaceId;
		Record.State.bIsMoving = false;
		if (const FDoemitzPlaceDefinition* Place = PlacesById.Find(Entry.PlaceId))
		{
			Record.State.WorldLocation = Place->AccessLocation;
		}

		CitizenRecords.Add(Def.CitizenId, MoveTemp(Record));
	}

	bIsConfigured = CitizenRecords.Num() > 0;
	UE_LOG(LogTemp, Display, TEXT("Doemitz simulation started at %.1f min (scale %.1fx): %d places, %d routes, %d citizens"),
		TimeOfDayMinutes, TimeScale, PlacesById.Num(), RoutesByKey.Num(), CitizenRecords.Num());
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
	}
}

bool UDoemitzSimulationSubsystem::GetCitizenState(FName CitizenId, FDoemitzCitizenState& OutState) const
{
	if (const FCitizenRecord* Record = CitizenRecords.Find(CitizenId))
	{
		OutState = Record->State;
		return true;
	}
	return false;
}

TArray<FName> UDoemitzSimulationSubsystem::GetAllCitizenIds() const
{
	TArray<FName> Ids;
	CitizenRecords.GetKeys(Ids);
	return Ids;
}

void UDoemitzSimulationSubsystem::StartTrip(FCitizenRecord& Record, FName DestinationPlaceId)
{
	Record.ActiveRoute.Reset();
	Record.ActiveSegmentEnds.Reset();
	Record.ActiveRouteLength = 0.0;
	Record.State.RouteProgressCm = 0.0;
	Record.State.TargetPlaceId = DestinationPlaceId;

	if (const FDoemitzCitizenRoute* Route = RoutesByKey.Find(MakeRouteKey(Record.State.CurrentPlaceId, DestinationPlaceId)))
	{
		Record.ActiveRoute = Route->Points;
	}
	else if (const FDoemitzPlaceDefinition* DestPlace = PlacesById.Find(DestinationPlaceId))
	{
		Record.ActiveRoute = { Record.State.WorldLocation, DestPlace->AccessLocation };
	}

	double Cumulative = 0.0;
	for (int32 Index = 0; Index + 1 < Record.ActiveRoute.Num(); ++Index)
	{
		const double SegLen = FVector::Distance(Record.ActiveRoute[Index], Record.ActiveRoute[Index + 1]);
		Cumulative += FMath::Max(SegLen, UE_KINDA_SMALL_NUMBER);
		Record.ActiveSegmentEnds.Add(Cumulative);
	}
	Record.ActiveRouteLength = Cumulative;

	if (Record.ActiveRouteLength <= 1.0)
	{
		Record.State.CurrentPlaceId = DestinationPlaceId;
		Record.State.bIsMoving = false;
		if (const FDoemitzPlaceDefinition* DestPlace = PlacesById.Find(DestinationPlaceId))
		{
			Record.State.WorldLocation = DestPlace->AccessLocation;
		}
		return;
	}

	Record.State.bIsMoving = true;
	Record.State.CurrentActivity = EDoemitzCitizenActivity::Commuting;
	Record.State.WorldLocation = Record.ActiveRoute[0];
	Record.State.WorldRotation = (Record.ActiveRoute[1] - Record.ActiveRoute[0]).Rotation();
}

void UDoemitzSimulationSubsystem::UpdateCitizen(FCitizenRecord& Record, double DeltaSeconds)
{
	const TArray<FDoemitzScheduleEntry>& Schedule = Record.Definition.Schedule;
	const int32 DesiredIndex = FindScheduleIndex(Schedule, TimeOfDayMinutes);
	const FDoemitzScheduleEntry& DesiredEntry = Schedule[DesiredIndex];
	Record.State.ActiveScheduleIndex = DesiredIndex;

	if (DesiredEntry.PlaceId != Record.State.TargetPlaceId)
	{
		StartTrip(Record, DesiredEntry.PlaceId);
	}

	if (!Record.State.bIsMoving)
	{
		Record.State.CurrentActivity = DesiredEntry.Activity;
		return;
	}

	const double Speed = FMath::Max(10.0, Record.Definition.WalkSpeedCmPerSecond);
	Record.State.RouteProgressCm += Speed * DeltaSeconds;

	if (Record.State.RouteProgressCm >= Record.ActiveRouteLength || Record.ActiveSegmentEnds.IsEmpty())
	{
		Record.State.bIsMoving = false;
		Record.State.CurrentPlaceId = Record.State.TargetPlaceId;
		Record.State.CurrentActivity = DesiredEntry.Activity;
		Record.State.RouteProgressCm = Record.ActiveRouteLength;
		Record.State.CompletedTrips += 1;
		if (!Record.ActiveRoute.IsEmpty())
		{
			Record.State.WorldLocation = Record.ActiveRoute.Last();
		}
		return;
	}

	const int32 SegIndex = FMath::Clamp(
		Algo::UpperBound(Record.ActiveSegmentEnds, Record.State.RouteProgressCm),
		0,
		Record.ActiveSegmentEnds.Num() - 1);
	const double SegStart = SegIndex == 0 ? 0.0 : Record.ActiveSegmentEnds[SegIndex - 1];
	const double SegLen = FMath::Max(Record.ActiveSegmentEnds[SegIndex] - SegStart, UE_KINDA_SMALL_NUMBER);
	const double Alpha = FMath::Clamp((Record.State.RouteProgressCm - SegStart) / SegLen, 0.0, 1.0);
	const FVector& A = Record.ActiveRoute[SegIndex];
	const FVector& B = Record.ActiveRoute[SegIndex + 1];
	Record.State.WorldLocation = FMath::Lerp(A, B, Alpha);
	const FVector Dir = B - A;
	if (!Dir.IsNearlyZero())
	{
		Record.State.WorldRotation = Dir.Rotation();
	}
}

void UDoemitzSimulationSubsystem::Tick(float DeltaTime)
{
	if (!bIsConfigured || DeltaTime <= 0.0f)
	{
		return;
	}

	const double SimMinutesDelta = (static_cast<double>(DeltaTime) * TimeScale) / 60.0;
	TimeOfDayMinutes += SimMinutesDelta;
	while (TimeOfDayMinutes >= 1440.0)
	{
		TimeOfDayMinutes -= 1440.0;
		DayNumber += 1;
	}

	// Citizens walk at real-world speed in world space (independent of clock compression,
	// so walking looks natural when observed in real time).
	for (TPair<FName, FCitizenRecord>& Pair : CitizenRecords)
	{
		UpdateCitizen(Pair.Value, static_cast<double>(DeltaTime));
	}
}
