#include "Simulation/DoemitzCitizenSubsystem.h"

#include "Algo/BinarySearch.h"
#include "Economy/DoemitzEconomySubsystem.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Simulation/DoemitzCitizenActor.h"
#include "Simulation/DoemitzSaveGame.h"
#include "Simulation/DoemitzSimulationSubsystem.h"

bool UDoemitzCitizenSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}
	const UWorld* World = Cast<UWorld>(Outer);
	return World != nullptr && World->IsGameWorld();
}

UDoemitzCitizenSubsystem* UDoemitzCitizenSubsystem::Get(const UObject* WorldContextObject)
{
	if (!WorldContextObject)
	{
		return nullptr;
	}
	const UWorld* World = WorldContextObject->GetWorld();
	return World ? World->GetSubsystem<UDoemitzCitizenSubsystem>() : nullptr;
}

FName UDoemitzCitizenSubsystem::MakeRouteKey(FName FromPlaceId, FName ToPlaceId)
{
	return FName(*FString::Printf(TEXT("%s->%s"), *FromPlaceId.ToString(), *ToPlaceId.ToString()));
}

int32 UDoemitzCitizenSubsystem::FindScheduleIndex(const TArray<FDoemitzScheduleEntry>& Schedule, double MinuteOfDay)
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

void UDoemitzCitizenSubsystem::ConfigureCitizens(
	const TArray<FDoemitzCitizenRoute>& InRoutes,
	const TArray<FDoemitzCitizenDefinition>& InCitizens)
{
	RoutesByKey.Reset();
	for (const FDoemitzCitizenRoute& Route : InRoutes)
	{
		if (!Route.FromPlaceId.IsNone() && !Route.ToPlaceId.IsNone() && Route.Points.Num() >= 2)
		{
			RoutesByKey.Add(MakeRouteKey(Route.FromPlaceId, Route.ToPlaceId), Route);
		}
	}

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
		ResetCitizenToCurrentSchedule(Record);

		CitizenRecords.Add(Def.CitizenId, MoveTemp(Record));
	}

	if (UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this))
	{
		if (CitizenRecords.Num() > 0)
		{
			Sim->MarkConfigured();
		}
	}

	UE_LOG(LogTemp, Display, TEXT("Doemitz citizens configured: %d routes, %d citizens"),
		RoutesByKey.Num(), CitizenRecords.Num());
}

void UDoemitzCitizenSubsystem::ConfigureCitizenPool(
	const TArray<TObjectPtr<UStaticMesh>>& InMeshVariants,
	double InLodRadiusCm)
{
	CitizenMeshVariants = InMeshVariants;
	CitizenLodRadiusCm = FMath::Max(500.0, InLodRadiusCm);

	ActiveCitizenActors.Reset();
	PooledCitizenActors.Reset();
	if (UWorld* World = GetWorld())
	{
		for (TActorIterator<ADoemitzCitizenActor> It(World); It; ++It)
		{
			ADoemitzCitizenActor* Actor = *It;
			if (!Actor)
			{
				continue;
			}
			Actor->ReleaseToPool();
			PooledCitizenActors.Add(Actor);
		}
	}

	UpdateCitizenLodPool();
}

const TArray<FDoemitzScheduleEntry>& UDoemitzCitizenSubsystem::GetActiveScheduleForDay(const FDoemitzCitizenDefinition& Def) const
{
	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	const EDoemitzDayKind Kind = Sim ? Sim->GetDayKind() : EDoemitzDayKind::Weekday;
	if (Kind == EDoemitzDayKind::Saturday && !Def.SaturdaySchedule.IsEmpty())
	{
		return Def.SaturdaySchedule;
	}
	if (Kind == EDoemitzDayKind::Sunday && !Def.SundaySchedule.IsEmpty())
	{
		return Def.SundaySchedule;
	}
	return Def.Schedule;
}

FDoemitzScheduleEntry UDoemitzCitizenSubsystem::ResolveDesiredEntry(const FDoemitzCitizenDefinition& Def, int32& OutIndex) const
{
	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	const TArray<FDoemitzScheduleEntry>& ActiveSchedule = GetActiveScheduleForDay(Def);
	if (ActiveSchedule.IsEmpty())
	{
		OutIndex = 0;
		FDoemitzScheduleEntry Fallback;
		Fallback.Activity = EDoemitzCitizenActivity::Home;
		Fallback.PlaceId = Def.HomePlaceId;
		return Fallback;
	}

	const double TimeOfDayMinutes = Sim ? Sim->GetTimeOfDayMinutes() : 470.0;
	const int32 BaseIndex = FindScheduleIndex(ActiveSchedule, TimeOfDayMinutes);
	for (int32 Offset = 0; Offset < ActiveSchedule.Num(); ++Offset)
	{
		const int32 CandidateIndex = (BaseIndex + Offset) % ActiveSchedule.Num();
		const FDoemitzScheduleEntry& Candidate = ActiveSchedule[CandidateIndex];
		if (Candidate.Activity == EDoemitzCitizenActivity::Shopping && Sim && !Sim->IsPlaceOpenNow(Candidate.PlaceId))
		{
			continue;
		}
		OutIndex = CandidateIndex;
		return Candidate;
	}

	OutIndex = 0;
	FDoemitzScheduleEntry HomeFallback;
	HomeFallback.Activity = EDoemitzCitizenActivity::Home;
	HomeFallback.PlaceId = Def.HomePlaceId;
	return HomeFallback;
}

void UDoemitzCitizenSubsystem::ResetCitizenToCurrentSchedule(FCitizenRecord& Record)
{
	int32 InitialIndex = 0;
	const FDoemitzScheduleEntry Entry = ResolveDesiredEntry(Record.Definition, InitialIndex);
	Record.State.ActiveScheduleIndex = InitialIndex;
	Record.State.CurrentActivity = Entry.Activity;
	Record.State.CurrentPlaceId = Entry.PlaceId;
	Record.State.TargetPlaceId = Entry.PlaceId;
	Record.State.bIsMoving = false;
	Record.State.bIsPausedForDialog = false;
	Record.State.RouteProgressCm = 0.0;
	Record.ActiveRoute.Reset();
	Record.ActiveSegmentEnds.Reset();
	Record.ActiveRouteLength = 0.0;
	Record.CoarseAccumulatedSeconds = 0.0;
	if (const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this))
	{
		FDoemitzPlaceDefinition Place;
		if (Sim->GetPlaceDefinition(Entry.PlaceId, Place))
		{
			Record.State.WorldLocation = Place.AccessLocation;
		}
	}
}

void UDoemitzCitizenSubsystem::BuildRouteSegments(FCitizenRecord& Record)
{
	Record.ActiveSegmentEnds.Reset();
	Record.ActiveRouteLength = 0.0;
	double Cumulative = 0.0;
	for (int32 Index = 0; Index + 1 < Record.ActiveRoute.Num(); ++Index)
	{
		const double SegLen = FVector::Distance(Record.ActiveRoute[Index], Record.ActiveRoute[Index + 1]);
		Cumulative += FMath::Max(SegLen, UE_KINDA_SMALL_NUMBER);
		Record.ActiveSegmentEnds.Add(Cumulative);
	}
	Record.ActiveRouteLength = Cumulative;
}

void UDoemitzCitizenSubsystem::BuildRouteCache(FCitizenRecord& Record, FName FromPlaceId, FName DestinationPlaceId)
{
	Record.ActiveRoute.Reset();
	Record.ActiveSegmentEnds.Reset();
	Record.ActiveRouteLength = 0.0;

	if (const FDoemitzCitizenRoute* Route = RoutesByKey.Find(MakeRouteKey(FromPlaceId, DestinationPlaceId)))
	{
		Record.ActiveRoute = Route->Points;
	}
	else if (const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this))
	{
		FDoemitzPlaceDefinition DestPlace;
		if (Sim->GetPlaceDefinition(DestinationPlaceId, DestPlace))
		{
			Record.ActiveRoute = { Record.State.WorldLocation, DestPlace.AccessLocation };
		}
	}

	BuildRouteSegments(Record);
}

void UDoemitzCitizenSubsystem::StartTrip(FCitizenRecord& Record, FName DestinationPlaceId)
{
	const bool bWasMoving = Record.State.bIsMoving && Record.ActiveRoute.Num() >= 2 && Record.ActiveRouteLength > 1.0;
	const FVector StartWorldLoc = Record.State.WorldLocation;
	const FName PrevFromPlaceId = Record.State.CurrentPlaceId;
	const FName PrevTargetPlaceId = Record.State.TargetPlaceId;
	const TArray<FVector> PrevRoute = bWasMoving ? Record.ActiveRoute : TArray<FVector>();
	const TArray<double> PrevSegEnds = bWasMoving ? Record.ActiveSegmentEnds : TArray<double>();
	const double PrevProgress = Record.State.RouteProgressCm;
	const double PrevLength = Record.ActiveRouteLength;

	Record.State.RouteProgressCm = 0.0;
	Record.State.TargetPlaceId = DestinationPlaceId;

	bool bBuiltContinuousFromCurrentLoc = false;
	if (bWasMoving && !PrevSegEnds.IsEmpty())
	{
		const int32 CurSegIndex = FMath::Clamp(
			Algo::UpperBound(PrevSegEnds, PrevProgress),
			0,
			PrevSegEnds.Num() - 1);

		auto AppendUnique = [](TArray<FVector>& OutPts, const FVector& Pt) {
			if (OutPts.IsEmpty() || FVector::DistSquared(OutPts.Last(), Pt) > 1.0)
			{
				OutPts.Add(Pt);
			}
		};

		TArray<FVector> Combined;
		Combined.Add(StartWorldLoc);

		if (DestinationPlaceId == PrevFromPlaceId)
		{
			// Turning around mid-trip back to origin along the already-walked road polyline (no teleport).
			for (int32 i = CurSegIndex; i >= 0; --i)
			{
				AppendUnique(Combined, PrevRoute[i]);
			}
			bBuiltContinuousFromCurrentLoc = Combined.Num() >= 2;
		}
		else
		{
			const FDoemitzCitizenRoute* FromTargetRoute = RoutesByKey.Find(MakeRouteKey(PrevTargetPlaceId, DestinationPlaceId));
			const FDoemitzCitizenRoute* FromOriginRoute = RoutesByKey.Find(MakeRouteKey(PrevFromPlaceId, DestinationPlaceId));
			const bool bUseTargetRoute = (FromTargetRoute != nullptr) &&
				(FromOriginRoute == nullptr || PrevProgress > PrevLength * 0.5);

			if (bUseTargetRoute)
			{
				for (int32 i = CurSegIndex + 1; i < PrevRoute.Num(); ++i)
				{
					AppendUnique(Combined, PrevRoute[i]);
				}
				for (const FVector& Pt : FromTargetRoute->Points)
				{
					AppendUnique(Combined, Pt);
				}
				bBuiltContinuousFromCurrentLoc = Combined.Num() >= 2;
			}
			else if (FromOriginRoute != nullptr)
			{
				for (int32 i = CurSegIndex; i >= 0; --i)
				{
					AppendUnique(Combined, PrevRoute[i]);
				}
				for (const FVector& Pt : FromOriginRoute->Points)
				{
					AppendUnique(Combined, Pt);
				}
				bBuiltContinuousFromCurrentLoc = Combined.Num() >= 2;
			}
		}

		if (bBuiltContinuousFromCurrentLoc)
		{
			Record.ActiveRoute = MoveTemp(Combined);
			BuildRouteSegments(Record);
		}
	}

	if (!bBuiltContinuousFromCurrentLoc)
	{
		BuildRouteCache(Record, PrevFromPlaceId, DestinationPlaceId);
	}

	if (Record.ActiveRouteLength <= 1.0)
	{
		Record.State.CurrentPlaceId = DestinationPlaceId;
		Record.State.bIsMoving = false;
		if (const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this))
		{
			FDoemitzPlaceDefinition DestPlace;
			if (Sim->GetPlaceDefinition(DestinationPlaceId, DestPlace))
			{
				Record.State.WorldLocation = DestPlace.AccessLocation;
			}
		}
		return;
	}

	Record.State.bIsMoving = true;
	Record.State.CurrentActivity = EDoemitzCitizenActivity::Commuting;
	Record.State.WorldLocation = bBuiltContinuousFromCurrentLoc ? StartWorldLoc : Record.ActiveRoute[0];
	const FVector Dir = Record.ActiveRoute[1] - Record.ActiveRoute[0];
	if (!Dir.IsNearlyZero())
	{
		Record.State.WorldRotation = Dir.Rotation();
	}
}

void UDoemitzCitizenSubsystem::UpdateCitizen(FCitizenRecord& Record, double TravelSeconds)
{
	if (Record.State.bIsPausedForDialog)
	{
		return;
	}

	int32 DesiredIndex = 0;
	const FDoemitzScheduleEntry DesiredEntry = ResolveDesiredEntry(Record.Definition, DesiredIndex);
	Record.State.ActiveScheduleIndex = DesiredIndex;

	if (DesiredEntry.PlaceId != Record.State.TargetPlaceId)
	{
		StartTrip(Record, DesiredEntry.PlaceId);
	}

	UDoemitzEconomySubsystem* Economy = UDoemitzEconomySubsystem::Get(this);
	if (!Record.State.bIsMoving)
	{
		Record.State.CurrentActivity = DesiredEntry.Activity;
		if (DesiredEntry.Activity == EDoemitzCitizenActivity::Shopping && Economy)
		{
			Economy->RecordCitizenShoppingRevenue(Record.State.CitizenId, Record.State.CurrentPlaceId);
		}
		return;
	}

	const double Speed = FMath::Max(10.0, Record.Definition.WalkSpeedCmPerSecond);
	Record.State.RouteProgressCm += Speed * FMath::Max(0.0, TravelSeconds);

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
		if (DesiredEntry.Activity == EDoemitzCitizenActivity::Shopping && Economy)
		{
			Economy->RecordCitizenShoppingRevenue(Record.State.CitizenId, Record.State.CurrentPlaceId);
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

void UDoemitzCitizenSubsystem::StepCitizens(double DeltaSeconds, double TimeScale, double BaseTimeScale)
{
	if (CitizenRecords.IsEmpty() || DeltaSeconds <= 0.0 || TimeScale <= 0.0)
	{
		return;
	}

	UpdateCitizenLodPool();

	// Hybrid time scale (Sprint 15):
	// - Visible (high-detail <= 150 m) citizens walk at natural real-time speed scaled by fast-forward multiplier (TimeScale / BaseTimeScale).
	// - Off-screen (coarse > 150 m) citizens travel in true game time (DeltaSeconds * TimeScale) so city-wide commutes arrive on schedule.
	const double TimeMultiplier = BaseTimeScale > 0.0 ? (TimeScale / BaseTimeScale) : 1.0;

	for (TPair<FName, FCitizenRecord>& Pair : CitizenRecords)
	{
		FCitizenRecord& Record = Pair.Value;
		if (Record.State.bIsHighDetail)
		{
			UpdateCitizen(Record, DeltaSeconds * TimeMultiplier);
		}
		else
		{
			Record.CoarseAccumulatedSeconds += DeltaSeconds;
			if (Record.CoarseAccumulatedSeconds >= CoarseUpdateIntervalSeconds)
			{
				const double Step = Record.CoarseAccumulatedSeconds;
				Record.CoarseAccumulatedSeconds = 0.0;
				UpdateCitizen(Record, Step * TimeScale);
			}
		}
	}
}

ADoemitzCitizenActor* UDoemitzCitizenSubsystem::AcquirePooledCitizenActor(const FCitizenRecord& Record)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return nullptr;
	}

	ADoemitzCitizenActor* Actor = nullptr;
	while (!PooledCitizenActors.IsEmpty() && !IsValid(Actor))
	{
		Actor = PooledCitizenActors.Pop().Get();
	}

	if (!IsValid(Actor))
	{
		FActorSpawnParameters SpawnParams;
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Actor = World->SpawnActor<ADoemitzCitizenActor>(
			ADoemitzCitizenActor::StaticClass(),
			Record.State.WorldLocation,
			Record.State.WorldRotation,
			SpawnParams);
	}

	if (IsValid(Actor))
	{
		UStaticMesh* MeshAsset = nullptr;
		if (!CitizenMeshVariants.IsEmpty())
		{
			const int32 VariantIdx = ((Record.Definition.CoatVariantIndex % CitizenMeshVariants.Num()) + CitizenMeshVariants.Num()) % CitizenMeshVariants.Num();
			MeshAsset = CitizenMeshVariants[VariantIdx].Get();
		}
		Actor->AssignToCitizen(Record.State.CitizenId, MeshAsset);
		ActiveCitizenActors.Add(Record.State.CitizenId, Actor);
	}
	return Actor;
}

void UDoemitzCitizenSubsystem::ReleaseCitizenActor(FName CitizenId)
{
	TObjectPtr<ADoemitzCitizenActor> Removed;
	if (ActiveCitizenActors.RemoveAndCopyValue(CitizenId, Removed))
	{
		if (IsValid(Removed.Get()))
		{
			Removed->ReleaseToPool();
			PooledCitizenActors.Add(Removed);
		}
	}
}

void UDoemitzCitizenSubsystem::UpdateCitizenLodPool()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	FVector PlayerLoc = FVector::ZeroVector;
	bool bHasPlayer = false;
	if (const APlayerController* PC = World->GetFirstPlayerController())
	{
		if (const APawn* Pawn = PC->GetPawn())
		{
			PlayerLoc = Pawn->GetActorLocation();
			bHasPlayer = true;
		}
	}
	if (!bHasPlayer)
	{
		return;
	}

	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	const double TimeScale = Sim ? Sim->GetTimeScale() : 20.0;
	const double RadiusSq = CitizenLodRadiusCm * CitizenLodRadiusCm;
	for (TPair<FName, FCitizenRecord>& Pair : CitizenRecords)
	{
		FCitizenRecord& Record = Pair.Value;
		const double DistSq2D = FVector::DistSquared2D(PlayerLoc, Record.State.WorldLocation);
		const bool bShouldBeHighDetail = DistSq2D <= RadiusSq;
		const bool bWasHighDetail = Record.State.bIsHighDetail;
		Record.State.bIsHighDetail = bShouldBeHighDetail;

		if (bShouldBeHighDetail)
		{
			if (!bWasHighDetail && Record.CoarseAccumulatedSeconds > 0.0 && TimeScale > 0.0)
			{
				const double Pending = Record.CoarseAccumulatedSeconds;
				Record.CoarseAccumulatedSeconds = 0.0;
				UpdateCitizen(Record, Pending * TimeScale);
			}
			TObjectPtr<ADoemitzCitizenActor>* Existing = ActiveCitizenActors.Find(Pair.Key);
			if (!Existing || !IsValid(Existing->Get()))
			{
				ActiveCitizenActors.Remove(Pair.Key);
				AcquirePooledCitizenActor(Record);
			}
		}
		else
		{
			if (ActiveCitizenActors.Contains(Pair.Key))
			{
				ReleaseCitizenActor(Pair.Key);
			}
		}
	}
}

void UDoemitzCitizenSubsystem::SyncAllActiveCitizenActors()
{
	for (TPair<FName, TObjectPtr<ADoemitzCitizenActor>>& Pair : ActiveCitizenActors)
	{
		if (IsValid(Pair.Value.Get()))
		{
			Pair.Value->SyncFromSimulation();
		}
	}
}

bool UDoemitzCitizenSubsystem::GetCitizenState(FName CitizenId, FDoemitzCitizenState& OutState) const
{
	if (const FCitizenRecord* Record = CitizenRecords.Find(CitizenId))
	{
		OutState = Record->State;
		return true;
	}
	return false;
}

TArray<FName> UDoemitzCitizenSubsystem::GetAllCitizenIds() const
{
	TArray<FName> Ids;
	CitizenRecords.GetKeys(Ids);
	Ids.Sort(FNameLexicalLess());
	return Ids;
}

void UDoemitzCitizenSubsystem::CollectCitizenWorldLocations(TArray<FVector>& OutLocations) const
{
	OutLocations.Reserve(OutLocations.Num() + CitizenRecords.Num());
	for (const TPair<FName, FCitizenRecord>& Pair : CitizenRecords)
	{
		OutLocations.Add(Pair.Value.State.WorldLocation);
	}
}

bool UDoemitzCitizenSubsystem::FindNearestCitizen(
	const FVector& QueryLocation,
	double MaxRadiusCm,
	FDoemitzCitizenState& OutCitizen,
	double& OutDistanceCm) const
{
	const FCitizenRecord* BestRec = nullptr;
	double BestDist = MaxRadiusCm;
	for (const TPair<FName, FCitizenRecord>& Pair : CitizenRecords)
	{
		const FCitizenRecord& Rec = Pair.Value;
		FVector ShownLoc = Rec.State.WorldLocation;
		FRotator ShownRot;
		GetCitizenPresentationTransform(Pair.Key, ShownLoc, ShownRot);
		if (FMath::Abs(QueryLocation.Z - ShownLoc.Z) > 260.0)
		{
			continue;
		}
		const double Dist2D = FVector::Dist2D(QueryLocation, ShownLoc);
		if (Dist2D <= BestDist)
		{
			BestDist = Dist2D;
			BestRec = &Rec;
		}
	}
	if (BestRec)
	{
		OutCitizen = BestRec->State;
		OutDistanceCm = BestDist;
		return true;
	}
	OutDistanceCm = MaxRadiusCm;
	return false;
}

bool UDoemitzCitizenSubsystem::SetCitizenDialogPaused(FName CitizenId, bool bPaused)
{
	FCitizenRecord* Rec = CitizenRecords.Find(CitizenId);
	if (!Rec)
	{
		return false;
	}
	Rec->State.bIsPausedForDialog = bPaused;
	return true;
}

bool UDoemitzCitizenSubsystem::IsCitizenDialogPaused(FName CitizenId) const
{
	if (const FCitizenRecord* Rec = CitizenRecords.Find(CitizenId))
	{
		return Rec->State.bIsPausedForDialog;
	}
	return false;
}

bool UDoemitzCitizenSubsystem::IsCitizenHighDetail(FName CitizenId) const
{
	if (const FCitizenRecord* Record = CitizenRecords.Find(CitizenId))
	{
		return Record->State.bIsHighDetail;
	}
	return false;
}

bool UDoemitzCitizenSubsystem::GetCitizenActorLocation(FName CitizenId, FVector& OutLocation) const
{
	if (const TObjectPtr<ADoemitzCitizenActor>* ActorPtr = ActiveCitizenActors.Find(CitizenId))
	{
		if (IsValid(ActorPtr->Get()))
		{
			OutLocation = (*ActorPtr)->GetActorLocation();
			return true;
		}
	}
	return false;
}

void UDoemitzCitizenSubsystem::SetCitizenLodRadiusCm(double NewRadiusCm)
{
	CitizenLodRadiusCm = FMath::Max(100.0, NewRadiusCm);
	UpdateCitizenLodPool();
}

bool UDoemitzCitizenSubsystem::SetCitizenAtPlaceForTest(FName CitizenId, FName PlaceId, EDoemitzCitizenActivity Activity)
{
	FCitizenRecord* Record = CitizenRecords.Find(CitizenId);
	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	FDoemitzPlaceDefinition Place;
	if (!Record || !Sim || !Sim->GetPlaceDefinition(PlaceId, Place))
	{
		return false;
	}
	Record->State.CurrentPlaceId = PlaceId;
	Record->State.TargetPlaceId = PlaceId;
	Record->State.CurrentActivity = Activity;
	Record->State.bIsMoving = false;
	Record->State.RouteProgressCm = 0.0;
	Record->ActiveRoute.Reset();
	Record->ActiveSegmentEnds.Reset();
	Record->ActiveRouteLength = 0.0;
	Record->State.WorldLocation = Place.AccessLocation;
	return true;
}

bool UDoemitzCitizenSubsystem::SetCitizenPositionForTest(FName CitizenId, const FVector& NewLocation)
{
	FCitizenRecord* Record = CitizenRecords.Find(CitizenId);
	if (!Record)
	{
		return false;
	}
	Record->State.WorldLocation = NewLocation;
	Record->State.bIsMoving = false;
	if (TObjectPtr<ADoemitzCitizenActor>* ActorPtr = ActiveCitizenActors.Find(CitizenId))
	{
		if (IsValid(ActorPtr->Get()))
		{
			(*ActorPtr)->SetActorLocation(NewLocation, false);
		}
	}
	return true;
}

bool UDoemitzCitizenSubsystem::GetCitizenPresentationTransform(FName CitizenId, FVector& OutLocation, FRotator& OutRotation) const
{
	const FCitizenRecord* Record = CitizenRecords.Find(CitizenId);
	if (!Record)
	{
		return false;
	}
	OutLocation = Record->State.WorldLocation;
	OutRotation = Record->State.WorldRotation;
	const EDoemitzCitizenActivity Activity = Record->State.CurrentActivity;
	if (Record->State.bIsMoving || Record->State.bIsPausedForDialog ||
		(Activity != EDoemitzCitizenActivity::Shopping && Activity != EDoemitzCitizenActivity::Working))
	{
		return true;
	}
	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	FDoemitzInteriorDefinition Interior;
	if (!Sim || !Sim->GetInteriorForPlace(Record->State.CurrentPlaceId, Interior) ||
		Interior.StandSpots.IsEmpty() || !Sim->IsPlaceOpenNow(Record->State.CurrentPlaceId))
	{
		return true;
	}
	// Deterministic slot: staff (Work) take staff spots first, customers fill the rest in citizen-id order.
	TArray<FName> Workers;
	TArray<FName> Customers;
	for (const TPair<FName, FCitizenRecord>& Pair : CitizenRecords)
	{
		const FDoemitzCitizenState& Other = Pair.Value.State;
		if (Other.bIsMoving || Other.CurrentPlaceId != Record->State.CurrentPlaceId)
		{
			continue;
		}
		if (Other.CurrentActivity == EDoemitzCitizenActivity::Working)
		{
			Workers.Add(Pair.Key);
		}
		else if (Other.CurrentActivity == EDoemitzCitizenActivity::Shopping)
		{
			Customers.Add(Pair.Key);
		}
	}
	Workers.Sort(FNameLexicalLess());
	Customers.Sort(FNameLexicalLess());
	TArray<int32> StaffSpots;
	TArray<int32> CustomerSpots;
	for (int32 Idx = 0; Idx < Interior.StandSpots.Num(); ++Idx)
	{
		(Interior.StandSpots[Idx].Role == FName(TEXT("staff")) ? StaffSpots : CustomerSpots).Add(Idx);
	}
	int32 SpotIndex = INDEX_NONE;
	if (Activity == EDoemitzCitizenActivity::Working)
	{
		const int32 Rank = Workers.IndexOfByKey(CitizenId);
		if (StaffSpots.IsValidIndex(Rank))
		{
			SpotIndex = StaffSpots[Rank];
		}
		else if (CustomerSpots.IsValidIndex(Rank - StaffSpots.Num() + Customers.Num()))
		{
			SpotIndex = CustomerSpots[Rank - StaffSpots.Num() + Customers.Num()];
		}
	}
	else
	{
		const int32 Rank = Customers.IndexOfByKey(CitizenId);
		if (CustomerSpots.IsValidIndex(Rank))
		{
			SpotIndex = CustomerSpots[Rank];
		}
	}
	if (SpotIndex == INDEX_NONE)
	{
		return true; // more visitors than visible spots: stay at the simulated position outside
	}
	const FDoemitzStandSpot& Spot = Interior.StandSpots[SpotIndex];
	OutLocation = Spot.Location;
	OutRotation = FRotator(0.0, Spot.YawDegrees, 0.0);
	return true;
}

void UDoemitzCitizenSubsystem::CaptureSaveState(UDoemitzSaveGame* SaveObj) const
{
	if (!SaveObj)
	{
		return;
	}
	SaveObj->Citizens.Reset();
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
}

void UDoemitzCitizenSubsystem::RestoreSaveState(
	const UDoemitzSaveGame* SaveObj,
	bool bMigratingFromPreV6,
	TFunctionRef<bool(double, double, double, double&)> GroundZResolver)
{
	if (!SaveObj)
	{
		return;
	}
	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	TSet<FName> RestoredCitizenIds;
	for (const FDoemitzSavedCitizen& Saved : SaveObj->Citizens)
	{
		if (FCitizenRecord* Record = CitizenRecords.Find(Saved.CitizenId))
		{
			RestoredCitizenIds.Add(Saved.CitizenId);
			Record->State.CurrentActivity = Saved.CurrentActivity;
			Record->State.CurrentPlaceId = Saved.CurrentPlaceId;
			Record->State.TargetPlaceId = Saved.TargetPlaceId;
			Record->State.bIsMoving = Saved.bIsMoving;
			Record->State.bIsPausedForDialog = false;
			FVector RestoredLoc = Saved.WorldLocation;
			double GroundZ = RestoredLoc.Z;
			if (bMigratingFromPreV6)
			{
				if (GroundZResolver(RestoredLoc.X, RestoredLoc.Y, RestoredLoc.Z, GroundZ))
				{
					RestoredLoc.Z = GroundZ;
				}
				else if (Sim)
				{
					FDoemitzPlaceDefinition Place;
					if (Sim->GetPlaceDefinition(Saved.CurrentPlaceId, Place))
					{
						RestoredLoc.Z = Place.AccessLocation.Z;
					}
				}
			}
			else if (GroundZResolver(RestoredLoc.X, RestoredLoc.Y, RestoredLoc.Z, GroundZ) && GroundZ > RestoredLoc.Z + 25.0)
			{
				// Guard against pre-11.1 saves whose saved position lay in a bridge dip below the deck
				RestoredLoc.Z = GroundZ;
			}
			Record->State.WorldLocation = RestoredLoc;
			Record->State.WorldRotation = Saved.WorldRotation;
			Record->State.RouteProgressCm = FMath::Max(0.0, Saved.RouteProgressCm);
			Record->State.ActiveScheduleIndex = Saved.ActiveScheduleIndex;
			Record->State.CompletedTrips = FMath::Max(0, Saved.CompletedTrips);
			Record->CoarseAccumulatedSeconds = 0.0;
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

	for (TPair<FName, FCitizenRecord>& Pair : CitizenRecords)
	{
		if (!RestoredCitizenIds.Contains(Pair.Key))
		{
			ResetCitizenToCurrentSchedule(Pair.Value);
		}
	}
}
