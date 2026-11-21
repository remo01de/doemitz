#include "Simulation/DoemitzSimulationSubsystem.h"

#include "Algo/BinarySearch.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Simulation/DoemitzSaveGame.h"
#include "Traffic/DoemitzTrafficVehicle.h"
#include "World/DoemitzDayNightController.h"

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

void UDoemitzSimulationSubsystem::BuildRouteCache(FCitizenRecord& Record, FName FromPlaceId, FName DestinationPlaceId)
{
	Record.ActiveRoute.Reset();
	Record.ActiveSegmentEnds.Reset();
	Record.ActiveRouteLength = 0.0;

	if (const FDoemitzCitizenRoute* Route = RoutesByKey.Find(MakeRouteKey(FromPlaceId, DestinationPlaceId)))
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
}

void UDoemitzSimulationSubsystem::StartTrip(FCitizenRecord& Record, FName DestinationPlaceId)
{
	Record.State.RouteProgressCm = 0.0;
	Record.State.TargetPlaceId = DestinationPlaceId;
	BuildRouteCache(Record, Record.State.CurrentPlaceId, DestinationPlaceId);

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

	if (NotificationRemainingSeconds > 0.0)
	{
		NotificationRemainingSeconds = FMath::Max(0.0, NotificationRemainingSeconds - static_cast<double>(DeltaTime));
		if (NotificationRemainingSeconds <= 0.0)
		{
			LastNotification.Reset();
		}
	}

	if (TimeScale <= 0.0)
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

void UDoemitzSimulationSubsystem::SetNotification(const FString& Message, double DurationSeconds)
{
	LastNotification = Message;
	NotificationRemainingSeconds = FMath::Max(0.5, DurationSeconds);
}

FString UDoemitzSimulationSubsystem::GetLastNotification() const
{
	return NotificationRemainingSeconds > 0.0 ? LastNotification : FString();
}

bool UDoemitzSimulationSubsystem::DoesSaveExist(const FString& SlotName) const
{
	return !SlotName.IsEmpty() && UGameplayStatics::DoesSaveGameExist(SlotName, 0);
}

bool UDoemitzSimulationSubsystem::SaveCityState(const FString& SlotName)
{
	if (!bIsConfigured || SlotName.IsEmpty())
	{
		return false;
	}

	UDoemitzSaveGame* SaveObj = Cast<UDoemitzSaveGame>(UGameplayStatics::CreateSaveGameObject(UDoemitzSaveGame::StaticClass()));
	if (!SaveObj)
	{
		return false;
	}

	SaveObj->DayNumber = DayNumber;
	SaveObj->TimeOfDayMinutes = TimeOfDayMinutes;
	SaveObj->TimeScale = TimeScale;

	if (UWorld* World = GetWorld())
	{
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			if (APawn* Pawn = PC->GetPawn())
			{
				SaveObj->bHasPlayerTransform = true;
				SaveObj->PlayerLocation = Pawn->GetActorLocation();
				SaveObj->PlayerRotation = Pawn->GetActorRotation();
			}
		}

		for (TActorIterator<ADoemitzTrafficVehicle> It(World); It; ++It)
		{
			const ADoemitzTrafficVehicle* Vehicle = *It;
			if (Vehicle && !Vehicle->GetVehicleId().IsNone())
			{
				FDoemitzSavedVehicle SavedVehicle;
				SavedVehicle.VehicleId = Vehicle->GetVehicleId();
				SavedVehicle.DistanceCm = Vehicle->GetDistanceAlongRoute();
				SavedVehicle.CompletedLaps = Vehicle->GetCompletedLaps();
				SaveObj->Vehicles.Add(SavedVehicle);
			}
		}
	}

	for (const TPair<FName, FCitizenRecord>& Pair : CitizenRecords)
	{
		const FDoemitzCitizenState& State = Pair.Value.State;
		FDoemitzSavedCitizen SavedCitizen;
		SavedCitizen.CitizenId = State.CitizenId;
		SavedCitizen.CurrentActivity = State.CurrentActivity;
		SavedCitizen.CurrentPlaceId = State.CurrentPlaceId;
		SavedCitizen.TargetPlaceId = State.TargetPlaceId;
		SavedCitizen.bIsMoving = State.bIsMoving;
		SavedCitizen.WorldLocation = State.WorldLocation;
		SavedCitizen.WorldRotation = State.WorldRotation;
		SavedCitizen.RouteProgressCm = State.RouteProgressCm;
		SavedCitizen.ActiveScheduleIndex = State.ActiveScheduleIndex;
		SavedCitizen.CompletedTrips = State.CompletedTrips;
		SaveObj->Citizens.Add(SavedCitizen);
	}

	const bool bSaved = UGameplayStatics::SaveGameToSlot(SaveObj, SlotName, 0);
	if (bSaved)
	{
		SetNotification(FString::Printf(TEXT("Gespeichert: %s"), *SlotName));
		UE_LOG(LogTemp, Display, TEXT("Doemitz save written to slot '%s' (Day %d, %.1f min, %d citizens, %d vehicles)"),
			*SlotName, DayNumber, TimeOfDayMinutes, SaveObj->Citizens.Num(), SaveObj->Vehicles.Num());
	}
	return bSaved;
}

bool UDoemitzSimulationSubsystem::LoadCityState(const FString& SlotName)
{
	if (!bIsConfigured || !DoesSaveExist(SlotName))
	{
		return false;
	}

	const UDoemitzSaveGame* SaveObj = Cast<UDoemitzSaveGame>(UGameplayStatics::LoadGameFromSlot(SlotName, 0));
	if (!SaveObj || SaveObj->SaveSchemaVersion != 1)
	{
		return false;
	}

	DayNumber = FMath::Max(1, SaveObj->DayNumber);
	TimeOfDayMinutes = FMath::Fmod(FMath::Max(0.0, SaveObj->TimeOfDayMinutes), 1440.0);
	TimeScale = FMath::Clamp(SaveObj->TimeScale, 0.0, 3600.0);

	for (const FDoemitzSavedCitizen& Saved : SaveObj->Citizens)
	{
		if (FCitizenRecord* Record = CitizenRecords.Find(Saved.CitizenId))
		{
			Record->State.CurrentActivity = Saved.CurrentActivity;
			Record->State.CurrentPlaceId = Saved.CurrentPlaceId;
			Record->State.TargetPlaceId = Saved.TargetPlaceId;
			Record->State.bIsMoving = Saved.bIsMoving;
			Record->State.WorldLocation = Saved.WorldLocation;
			Record->State.WorldRotation = Saved.WorldRotation;
			Record->State.RouteProgressCm = FMath::Max(0.0, Saved.RouteProgressCm);
			Record->State.ActiveScheduleIndex = Saved.ActiveScheduleIndex;
			Record->State.CompletedTrips = FMath::Max(0, Saved.CompletedTrips);
			if (Record->State.bIsMoving)
			{
				BuildRouteCache(*Record, Record->State.CurrentPlaceId, Record->State.TargetPlaceId);
			}
			else
			{
				Record->ActiveRoute.Reset();
				Record->ActiveSegmentEnds.Reset();
				Record->ActiveRouteLength = 0.0;
			}
		}
	}

	if (UWorld* World = GetWorld())
	{
		if (SaveObj->bHasPlayerTransform)
		{
			if (APlayerController* PC = World->GetFirstPlayerController())
			{
				if (APawn* Pawn = PC->GetPawn())
				{
					Pawn->SetActorLocationAndRotation(SaveObj->PlayerLocation, SaveObj->PlayerRotation, false, nullptr, ETeleportType::TeleportPhysics);
				}
			}
		}

		TMap<FName, FDoemitzSavedVehicle> SavedVehiclesById;
		for (const FDoemitzSavedVehicle& SavedVehicle : SaveObj->Vehicles)
		{
			SavedVehiclesById.Add(SavedVehicle.VehicleId, SavedVehicle);
		}
		for (TActorIterator<ADoemitzTrafficVehicle> It(World); It; ++It)
		{
			if (ADoemitzTrafficVehicle* Vehicle = *It)
			{
				if (const FDoemitzSavedVehicle* SavedVehicle = SavedVehiclesById.Find(Vehicle->GetVehicleId()))
				{
					Vehicle->RestoreMotionState(SavedVehicle->DistanceCm, SavedVehicle->CompletedLaps);
				}
			}
		}

		for (TActorIterator<ADoemitzDayNightController> It(World); It; ++It)
		{
			if (ADoemitzDayNightController* Controller = *It)
			{
				Controller->UpdateLightingFromSimulation();
			}
		}
	}

	SetNotification(FString::Printf(TEXT("Geladen: %s"), *SlotName));
	UE_LOG(LogTemp, Display, TEXT("Doemitz save loaded from slot '%s' (Day %d, %.1f min)"),
		*SlotName, DayNumber, TimeOfDayMinutes);
	return true;
}
