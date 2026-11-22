#include "Simulation/DoemitzSimulationSubsystem.h"

#include "Algo/BinarySearch.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Simulation/DoemitzCitizenActor.h"
#include "Simulation/DoemitzSaveGame.h"
#include "Traffic/DoemitzTrafficVehicle.h"
#include "World/DoemitzDayNightController.h"

namespace
{
	constexpr double VehicleLengthCm = 390.0;
	constexpr double MinCenterSpacingCm = 680.0;
	constexpr double FollowBrakeStartCm = 1250.0;
	constexpr double JunctionApproachCm = 950.0;
	constexpr double JunctionStopLineCm = 420.0;
	constexpr double JunctionClearanceCm = 550.0;
	constexpr double StopSignHoldSeconds = 0.8;
	constexpr double ParkingApproachToleranceCm = 320.0;
	constexpr double ParkingManeuverSeconds = 2.0;
	constexpr double PedestrianStopDistCm = 620.0;
	constexpr double PedestrianLateralCm = 185.0;
	constexpr double CrossingApproachDistCm = 900.0;
	constexpr double CrossingStopMarginCm = 320.0;
	constexpr double CrossingLateralCm = 260.0;
	constexpr double VehicleAccelCmPerSecSq = 260.0;
	constexpr double VehicleDecelCmPerSecSq = 550.0;

	bool IsBuildingStructureHit(const FHitResult& Hit)
	{
		const UStaticMeshComponent* SMC = Cast<UStaticMeshComponent>(Hit.GetComponent());
		const UStaticMesh* Mesh = SMC ? SMC->GetStaticMesh() : nullptr;
		if (!Mesh)
		{
			return false;
		}
		const FString MeshName = Mesh->GetName();
		return MeshName.StartsWith(TEXT("SM_Roofs"))
			|| MeshName.StartsWith(TEXT("SM_Walls"))
			|| MeshName.StartsWith(TEXT("SM_Gable"))
			|| MeshName.StartsWith(TEXT("SM_StoneTrim"))
			|| MeshName.StartsWith(TEXT("SM_TimberTrim"))
			|| MeshName.StartsWith(TEXT("SM_Doors"))
			|| MeshName.StartsWith(TEXT("SM_Window"))
			|| MeshName.StartsWith(TEXT("SM_Shutters"))
			|| MeshName.StartsWith(TEXT("SM_Flower"))
			|| MeshName.StartsWith(TEXT("SM_InteriorCeiling"))
			|| MeshName.StartsWith(TEXT("SM_InteriorFurniture"))
			|| MeshName.StartsWith(TEXT("SM_InteriorGoods"))
			|| MeshName.StartsWith(TEXT("SM_InteriorLamp"))
			|| MeshName.StartsWith(TEXT("SM_InteriorDoor"))
			|| MeshName.StartsWith(TEXT("SM_InteriorWalls"))
			|| MeshName.StartsWith(TEXT("SM_Notice"));
	}

	bool TraceStaticGroundZ(UWorld* World, double WorldX, double WorldY, double ReferenceZ, double& OutGroundZ)
	{
		if (!World)
		{
			return false;
		}
		FCollisionQueryParams Params(SCENE_QUERY_STAT(DoemitzSaveGroundTrace), false);
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			if (APawn* Pawn = PC->GetPawn())
			{
				Params.AddIgnoredActor(Pawn);
			}
		}
		for (TActorIterator<ADoemitzCitizenActor> It(World); It; ++It)
		{
			Params.AddIgnoredActor(*It);
		}
		for (TActorIterator<ADoemitzTrafficVehicle> It(World); It; ++It)
		{
			Params.AddIgnoredActor(*It);
		}
		double TraceStartZ = FMath::Max(5000.0, ReferenceZ + 2000.0);
		for (int32 Iter = 0; Iter < 12 && TraceStartZ > -5000.0; ++Iter)
		{
			FHitResult Hit;
			if (!World->LineTraceSingleByChannel(
				Hit,
				FVector(WorldX, WorldY, TraceStartZ),
				FVector(WorldX, WorldY, -5000.0),
				ECC_Visibility,
				Params))
			{
				return false;
			}
			if (IsBuildingStructureHit(Hit))
			{
				if (const UPrimitiveComponent* Comp = Hit.GetComponent())
				{
					Params.AddIgnoredComponent(Comp);
				}
				TraceStartZ = Hit.ImpactPoint.Z - 5.0;
				continue;
			}
			if (Hit.ImpactNormal.Z < 0.5f)
			{
				TraceStartZ = Hit.ImpactPoint.Z - 5.0;
				continue;
			}
			OutGroundZ = Hit.ImpactPoint.Z;
			return true;
		}
		return false;
	}

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

	uint32 DeterministicHash(int32 Seed, FName KeyId, int32 Salt)
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
	DayOfWeek = 0; // Monday
	CalendarWeek = 1;

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

	bIsConfigured = CitizenRecords.Num() > 0 || VehicleRecords.Num() > 0;
	UE_LOG(LogTemp, Display, TEXT("Doemitz simulation started (day=%d, dow=%d, kw=%d, %.1f min, scale=%.1fx): %d places, %d routes, %d citizens"),
		DayNumber, DayOfWeek, CalendarWeek, TimeOfDayMinutes, TimeScale, PlacesById.Num(), RoutesByKey.Num(), CitizenRecords.Num());
}

void UDoemitzSimulationSubsystem::ConfigureCitizenPool(
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

bool UDoemitzSimulationSubsystem::GetCitizenPresentationTransform(FName CitizenId, FVector& OutLocation, FRotator& OutRotation) const
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
	const FName* InteriorId = InteriorIdByPlace.Find(Record->State.CurrentPlaceId);
	const FDoemitzInteriorDefinition* Interior = InteriorId ? InteriorsById.Find(*InteriorId) : nullptr;
	if (!Interior || Interior->StandSpots.IsEmpty() || !IsPlaceOpenNow(Record->State.CurrentPlaceId))
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
	for (int32 Idx = 0; Idx < Interior->StandSpots.Num(); ++Idx)
	{
		(Interior->StandSpots[Idx].Role == FName(TEXT("staff")) ? StaffSpots : CustomerSpots).Add(Idx);
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
	const FDoemitzStandSpot& Spot = Interior->StandSpots[SpotIndex];
	OutLocation = Spot.Location;
	OutRotation = FRotator(0.0, Spot.YawDegrees, 0.0);
	return true;
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

void UDoemitzSimulationSubsystem::ConfigureTrafficNetwork(
	int32 InTrafficSeed,
	const TArray<FDoemitzRoadEdgeDefinition>& InRoadEdges,
	const TArray<FDoemitzVehicleDefinition>& InVehicles,
	const TArray<FDoemitzCrossingDefinition>& InCrossings,
	const TArray<FDoemitzParkingLotDefinition>& InParkingLots)
{
	TrafficSeed = InTrafficSeed;
	RoadEdgesById.Reset();
	OutgoingEdgesByNode.Reset();
	Crossings = InCrossings;
	ParkingLotsById.Reset();
	OrderedParkingLotIds.Reset();
	VehicleRecords.Reset();
	OrderedVehicleIds.Reset();
	JunctionReservations.Reset();

	for (const FDoemitzRoadEdgeDefinition& Def : InRoadEdges)
	{
		if (Def.EdgeId.IsNone() || Def.FromNodeId.IsNone() || Def.ToNodeId.IsNone() || Def.Points.Num() < 2)
		{
			continue;
		}
		FRoadEdgeRecord Rec;
		Rec.Definition = Def;
		double Cumulative = 0.0;
		for (int32 i = 0; i + 1 < Def.Points.Num(); ++i)
		{
			Cumulative += FMath::Max(FVector::Distance(Def.Points[i], Def.Points[i + 1]), UE_KINDA_SMALL_NUMBER);
			Rec.SegmentEnds.Add(Cumulative);
		}
		Rec.LengthCm = Cumulative;
		if (Rec.LengthCm <= 1.0)
		{
			continue;
		}
		const FVector StartVec = Def.Points[1] - Def.Points[0];
		Rec.StartDir2D = FVector2D(StartVec.X, StartVec.Y).GetSafeNormal();
		const FVector EndVec = Def.Points.Last() - Def.Points[Def.Points.Num() - 2];
		Rec.EndDir2D = FVector2D(EndVec.X, EndVec.Y).GetSafeNormal();

		RoadEdgesById.Add(Def.EdgeId, MoveTemp(Rec));
		OutgoingEdgesByNode.FindOrAdd(Def.FromNodeId).Add(Def.EdgeId);
	}

	for (TPair<FName, TArray<FName>>& Pair : OutgoingEdgesByNode)
	{
		Pair.Value.Sort(FNameLexicalLess());
	}

	for (const FDoemitzParkingLotDefinition& LotDef : InParkingLots)
	{
		if (LotDef.ParkingLotId.IsNone() || !RoadEdgesById.Contains(LotDef.AccessEdgeId))
		{
			continue;
		}
		FParkingLotRecord LotRec;
		LotRec.Definition = LotDef;
		const int32 SlotCount = FMath::Max(1, LotDef.SlotLocations.Num() > 0 ? LotDef.SlotLocations.Num() : LotDef.Capacity);
		LotRec.SlotOccupants.Init(NAME_None, SlotCount);
		ParkingLotsById.Add(LotDef.ParkingLotId, MoveTemp(LotRec));
		OrderedParkingLotIds.Add(LotDef.ParkingLotId);
	}
	OrderedParkingLotIds.Sort(FNameLexicalLess());

	for (const FDoemitzVehicleDefinition& Def : InVehicles)
	{
		if (Def.VehicleId.IsNone())
		{
			continue;
		}
		const FRoadEdgeRecord* Edge = RoadEdgesById.Find(Def.StartEdgeId);
		if (!Edge)
		{
			UE_LOG(LogTemp, Warning, TEXT("Traffic vehicle %s start edge %s not found"),
				*Def.VehicleId.ToString(), *Def.StartEdgeId.ToString());
			continue;
		}

		FVehicleRecord Rec;
		Rec.Definition = Def;
		Rec.State.VehicleId = Def.VehicleId;
		Rec.State.Phase = EDoemitzVehiclePhase::Driving;
		Rec.State.CurrentEdgeId = Def.StartEdgeId;
		Rec.State.DistanceOnEdgeCm = FMath::Clamp(Def.StartDistanceCm, 0.0, FMath::Max(0.0, Edge->LengthCm - 1.0));
		Rec.State.CurrentSpeedCmPerSecond = FMath::Min(500.0, Edge->Definition.SpeedLimitCmPerSecond);
		SampleEdgePose(*Edge, Rec.State.DistanceOnEdgeCm, Rec.State.WorldLocation, Rec.State.WorldRotation);
		if (!OrderedParkingLotIds.IsEmpty())
		{
			const FName TargetLot = ChooseNextParkingLot(Rec, NAME_None);
			PlanRouteToParking(Rec, TargetLot);
		}
		if (Rec.State.NextEdgeId.IsNone())
		{
			Rec.State.NextEdgeId = ChooseNextEdge(Rec);
		}

		VehicleRecords.Add(Def.VehicleId, MoveTemp(Rec));
		OrderedVehicleIds.Add(Def.VehicleId);
	}

	OrderedVehicleIds.Sort(FNameLexicalLess());
	bIsConfigured = CitizenRecords.Num() > 0 || VehicleRecords.Num() > 0;
	UE_LOG(LogTemp, Display, TEXT("Doemitz traffic network configured: seed=%d, %d edges, %d vehicles, %d crossings, %d parking lots"),
		TrafficSeed, RoadEdgesById.Num(), VehicleRecords.Num(), Crossings.Num(), ParkingLotsById.Num());
}

void UDoemitzSimulationSubsystem::ConfigureEconomy(const UDoemitzEconomyDataAsset* InEconomyData)
{
	AssortmentsByCategory.Reset();
	ItemsById.Reset();
	JobsById.Reset();
	JobIdByPlace.Reset();
	EconomySeed = 202609;
	StartingMoneyCents = 0;

	if (InEconomyData)
	{
		EconomySeed = InEconomyData->EconomySeed;
		StartingMoneyCents = FMath::Max<int64>(0, InEconomyData->StartingMoneyCents);
		for (const FDoemitzAssortmentDefinition& Group : InEconomyData->Assortments)
		{
			if (!Group.Category.IsNone() && !Group.Items.IsEmpty())
			{
				AssortmentsByCategory.Add(Group.Category, Group.Items);
				for (const FDoemitzItemDefinition& Item : Group.Items)
				{
					if (!Item.ItemId.IsNone())
					{
						ItemsById.Add(Item.ItemId, Item);
					}
				}
			}
		}
		for (const FDoemitzJobDefinition& Job : InEconomyData->Jobs)
		{
			if (!Job.JobId.IsNone() && !Job.PlaceId.IsNone())
			{
				JobsById.Add(Job.JobId, Job);
				JobIdByPlace.Add(Job.PlaceId, Job.JobId);
			}
		}
	}

	ResetEconomyToDefaults();
	UE_LOG(LogTemp, Display, TEXT("Doemitz economy configured: start=%lld ct, %d categories, %d jobs (seed=%d)"),
		StartingMoneyCents, AssortmentsByCategory.Num(), JobsById.Num(), EconomySeed);
}

void UDoemitzSimulationSubsystem::ConfigureTasks(const UDoemitzTaskDataAsset* InTaskData)
{
	TaskTemplates.Reset();
	Tasks.Reset();
	TaskSeed = 202610;
	DailyMinTasks = 3;
	DailyMaxTasks = 5;

	if (InTaskData)
	{
		TaskSeed = InTaskData->TaskSeed;
		DailyMinTasks = FMath::Max(1, InTaskData->DailyMinTasks);
		DailyMaxTasks = FMath::Max(DailyMinTasks, InTaskData->DailyMaxTasks);
		TaskTemplates = InTaskData->Templates;
	}

	GenerateDailyTasks();
	UE_LOG(LogTemp, Display, TEXT("Doemitz tasks configured: %d templates, %d daily tasks generated (seed=%d)"),
		TaskTemplates.Num(), Tasks.Num(), TaskSeed);
}

void UDoemitzSimulationSubsystem::ResetEconomyToDefaults()
{
	PlayerMoneyCents = StartingMoneyCents;
	NextTransactionId = 1;
	ActiveJobId = NAME_None;
	bIsWorkingShift = false;
	ActiveShiftPlaceId = NAME_None;
	ShiftActualStartMinute = 0.0;
	LedgerEntries.Reset();
	PlayerInventory.Reset();
	PlaceRevenues.Reset();
	CitizenDailyShoppingRecorded.Reset();
}

void UDoemitzSimulationSubsystem::SetPlayerMoneyCentsForTest(int64 NewAmountCents)
{
	PlayerMoneyCents = FMath::Max<int64>(0, NewAmountCents);
}

void UDoemitzSimulationSubsystem::AppendLedgerEntry(FName PlaceId, int64 AmountCents, const FString& Description)
{
	FDoemitzLedgerEntry Entry;
	Entry.TransactionId = NextTransactionId++;
	Entry.DayNumber = DayNumber;
	Entry.DayOfWeek = DayOfWeek;
	Entry.MinuteOfDay = TimeOfDayMinutes;
	Entry.PlaceId = PlaceId;
	Entry.AmountCents = AmountCents;
	Entry.Description = Description;
	LedgerEntries.Add(MoveTemp(Entry));
	if (LedgerEntries.Num() > MaxLedgerEntries)
	{
		LedgerEntries.RemoveAt(0, LedgerEntries.Num() - MaxLedgerEntries);
	}
}

void UDoemitzSimulationSubsystem::AddPlaceRevenue(FName PlaceId, int64 AmountCents)
{
	if (PlaceId.IsNone() || AmountCents <= 0)
	{
		return;
	}
	FDoemitzPlaceRevenue& Rev = PlaceRevenues.FindOrAdd(PlaceId);
	Rev.PlaceId = PlaceId;
	Rev.DailyRevenueCents += AmountCents;
	Rev.WeeklyRevenueCents += AmountCents;
}

int32 UDoemitzSimulationSubsystem::GetInventoryQuantity(FName ItemId) const
{
	const int32* Qty = PlayerInventory.Find(ItemId);
	return Qty ? *Qty : 0;
}

TArray<FDoemitzInventoryItem> UDoemitzSimulationSubsystem::GetAllInventoryItems() const
{
	TArray<FDoemitzInventoryItem> Result;
	Result.Reserve(PlayerInventory.Num());
	for (const TPair<FName, int32>& Pair : PlayerInventory)
	{
		if (Pair.Value > 0)
		{
			FDoemitzInventoryItem Item;
			Item.ItemId = Pair.Key;
			Item.Quantity = Pair.Value;
			Result.Add(Item);
		}
	}
	Result.Sort([](const FDoemitzInventoryItem& A, const FDoemitzInventoryItem& B) {
		return A.ItemId.LexicalLess(B.ItemId);
	});
	return Result;
}

bool UDoemitzSimulationSubsystem::GetItemDefinition(FName ItemId, FDoemitzItemDefinition& OutItem) const
{
	if (const FDoemitzItemDefinition* Found = ItemsById.Find(ItemId))
	{
		OutItem = *Found;
		return true;
	}
	return false;
}

TArray<FDoemitzItemDefinition> UDoemitzSimulationSubsystem::GetItemsForPlace(FName PlaceId) const
{
	const FDoemitzPlaceDefinition* Place = PlacesById.Find(PlaceId);
	if (!Place)
	{
		return {};
	}
	const FName Cat = !Place->EconomyCategory.IsNone() ? Place->EconomyCategory : Place->Kind;
	if (const TArray<FDoemitzItemDefinition>* Items = AssortmentsByCategory.Find(Cat))
	{
		return *Items;
	}
	if (const TArray<FDoemitzItemDefinition>* Fallback = AssortmentsByCategory.Find(Place->Kind))
	{
		return *Fallback;
	}
	return {};
}

bool UDoemitzSimulationSubsystem::BuyItem(FName PlaceId, FName ItemId, int32 Quantity)
{
	if (Quantity <= 0 || PlaceId.IsNone() || ItemId.IsNone())
	{
		return false;
	}
	const FDoemitzPlaceDefinition* Place = PlacesById.Find(PlaceId);
	if (!Place)
	{
		return false;
	}
	if (!IsPlaceOpenNow(PlaceId))
	{
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::PlaceClosed;
		Ev.PlaceId = PlaceId;
		PushNotificationEvent(Ev);
		return false;
	}

	const TArray<FDoemitzItemDefinition> Items = GetItemsForPlace(PlaceId);
	const FDoemitzItemDefinition* FoundItem = Items.FindByPredicate([ItemId](const FDoemitzItemDefinition& Item) {
		return Item.ItemId == ItemId;
	});
	if (!FoundItem || FoundItem->PriceCents <= 0)
	{
		return false;
	}

	const int64 TotalCost = FoundItem->PriceCents * static_cast<int64>(Quantity);
	if (PlayerMoneyCents < TotalCost)
	{
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::InsufficientFunds;
		Ev.PlaceId = PlaceId;
		Ev.ItemId = ItemId;
		Ev.AmountCents = TotalCost;
		Ev.SecondaryAmountCents = PlayerMoneyCents;
		PushNotificationEvent(Ev);
		return false;
	}

	PlayerMoneyCents -= TotalCost;
	PlayerInventory.FindOrAdd(ItemId) += Quantity;
	AddPlaceRevenue(PlaceId, TotalCost);
	AppendLedgerEntry(PlaceId, -TotalCost, FString::Printf(TEXT("BUY:%s:%d"), *ItemId.ToString(), Quantity));

	FDoemitzNotificationEvent Ev;
	Ev.Code = EDoemitzNotificationCode::ItemPurchased;
	Ev.PlaceId = PlaceId;
	Ev.ItemId = ItemId;
	Ev.Quantity = Quantity;
	Ev.AmountCents = TotalCost;
	PushNotificationEvent(Ev);
	return true;
}

bool UDoemitzSimulationSubsystem::GetJobForPlace(FName PlaceId, FDoemitzJobDefinition& OutJob) const
{
	if (const FName* JobId = JobIdByPlace.Find(PlaceId))
	{
		if (const FDoemitzJobDefinition* Job = JobsById.Find(*JobId))
		{
			OutJob = *Job;
			return true;
		}
	}
	return false;
}

bool UDoemitzSimulationSubsystem::GetJobDefinition(FName JobId, FDoemitzJobDefinition& OutJob) const
{
	if (const FDoemitzJobDefinition* Job = JobsById.Find(JobId))
	{
		OutJob = *Job;
		return true;
	}
	return false;
}

bool UDoemitzSimulationSubsystem::AcceptJob(FName PlaceId)
{
	FDoemitzJobDefinition Job;
	if (!GetJobForPlace(PlaceId, Job))
	{
		return false;
	}
	if (!IsPlaceOpenNow(PlaceId))
	{
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::JobNeedsOpenPlace;
		Ev.PlaceId = PlaceId;
		PushNotificationEvent(Ev);
		return false;
	}
	ActiveJobId = Job.JobId;
	FDoemitzNotificationEvent Ev;
	Ev.Code = EDoemitzNotificationCode::JobAccepted;
	Ev.PlaceId = PlaceId;
	Ev.JobId = Job.JobId;
	Ev.AmountCents = Job.HourlyWageCents;
	PushNotificationEvent(Ev);
	return true;
}

FDoemitzShiftAvailability UDoemitzSimulationSubsystem::CheckWorkShiftAvailability(FName PlaceId) const
{
	FDoemitzShiftAvailability Out;
	if (bIsWorkingShift)
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::AlreadyWorking;
		return Out;
	}
	FDoemitzJobDefinition Job;
	if (!GetJobForPlace(PlaceId, Job))
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::NoJobAtPlace;
		return Out;
	}
	Out.ShiftStartMinute = Job.ShiftStartMinute;
	if (ActiveJobId != Job.JobId)
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::JobNotAccepted;
		return Out;
	}
	if (!Job.WorkDays.Contains(DayOfWeek))
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::NotAWorkDay;
		return Out;
	}
	const double EarliestStart = FMath::Max(0.0, static_cast<double>(Job.ShiftStartMinute) - 30.0);
	if (TimeOfDayMinutes < EarliestStart)
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::TooEarly;
		return Out;
	}
	if (TimeOfDayMinutes >= static_cast<double>(Job.ShiftEndMinute))
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::ShiftEnded;
		return Out;
	}
	Out.bCanStart = true;
	Out.Result = EDoemitzShiftCheckResult::Ready;
	return Out;
}

bool UDoemitzSimulationSubsystem::StartWorkShift(FName PlaceId)
{
	const FDoemitzShiftAvailability Avail = CheckWorkShiftAvailability(PlaceId);
	if (!Avail.bCanStart)
	{
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::ShiftUnavailable;
		Ev.PlaceId = PlaceId;
		Ev.ShiftResult = Avail.Result;
		Ev.MinuteValue = Avail.ShiftStartMinute;
		PushNotificationEvent(Ev);
		return false;
	}
	FDoemitzJobDefinition Job;
	if (!GetJobForPlace(PlaceId, Job))
	{
		return false;
	}

	bIsWorkingShift = true;
	ActiveShiftPlaceId = PlaceId;
	ShiftActualStartMinute = FMath::Max(TimeOfDayMinutes, static_cast<double>(Job.ShiftStartMinute));
	PreShiftTimeScale = TimeScale > 0.0 ? TimeScale : 60.0;
	TimeScale = 900.0; // 15x fast-forward during shift

	if (UWorld* World = GetWorld())
	{
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			PC->SetIgnoreMoveInput(true);
			if (APawn* Pawn = PC->GetPawn())
			{
				Pawn->SetActorHiddenInGame(true);
			}
		}
	}

	FDoemitzNotificationEvent Ev;
	Ev.Code = EDoemitzNotificationCode::ShiftStarted;
	Ev.PlaceId = PlaceId;
	Ev.JobId = Job.JobId;
	Ev.MinuteValue = Job.ShiftEndMinute;
	PushNotificationEvent(Ev);
	return true;
}

void UDoemitzSimulationSubsystem::UpdateActiveWorkShift()
{
	if (!bIsWorkingShift)
	{
		return;
	}
	const FDoemitzJobDefinition* Job = JobsById.Find(ActiveJobId);
	if (!Job)
	{
		FinishWorkShift();
		return;
	}
	if (TimeOfDayMinutes >= static_cast<double>(Job->ShiftEndMinute))
	{
		FinishWorkShift();
	}
}

void UDoemitzSimulationSubsystem::FinishWorkShift()
{
	if (!bIsWorkingShift)
	{
		return;
	}
	bIsWorkingShift = false;
	TimeScale = FMath::Max(60.0, PreShiftTimeScale);

	if (UWorld* World = GetWorld())
	{
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			PC->SetIgnoreMoveInput(false);
			if (APawn* Pawn = PC->GetPawn())
			{
				Pawn->SetActorHiddenInGame(false);
			}
		}
	}

	if (const FDoemitzJobDefinition* Job = JobsById.Find(ActiveJobId))
	{
		const double ScheduledMinutes = FMath::Max(1.0, static_cast<double>(Job->ShiftEndMinute - Job->ShiftStartMinute));
		const double WorkedMinutes = FMath::Clamp(static_cast<double>(Job->ShiftEndMinute) - ShiftActualStartMinute, 0.0, ScheduledMinutes);
		const int64 PayCents = FMath::RoundToInt64((static_cast<double>(Job->HourlyWageCents) * WorkedMinutes) / 60.0);
		if (PayCents > 0)
		{
			PlayerMoneyCents += PayCents;
			AppendLedgerEntry(Job->PlaceId, PayCents, FString::Printf(TEXT("WAGE:%s"), *Job->JobId.ToString()));
		}
		const bool bLate = ShiftActualStartMinute > static_cast<double>(Job->ShiftStartMinute) + 0.5;
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::ShiftFinished;
		Ev.JobId = Job->JobId;
		Ev.AmountCents = PayCents;
		Ev.bFlag = bLate;
		PushNotificationEvent(Ev);
	}
	ActiveShiftPlaceId = NAME_None;
}

void UDoemitzSimulationSubsystem::RecordCitizenShoppingRevenue(FName CitizenId, FName PlaceId)
{
	if (CitizenId.IsNone() || PlaceId.IsNone() || !IsPlaceOpenNow(PlaceId))
	{
		return;
	}
	const FName DailyKey(*FString::Printf(TEXT("%s@%s"), *CitizenId.ToString(), *PlaceId.ToString()));
	if (CitizenDailyShoppingRecorded.Contains(DailyKey))
	{
		return;
	}
	const TArray<FDoemitzItemDefinition> Items = GetItemsForPlace(PlaceId);
	if (Items.IsEmpty())
	{
		return;
	}
	CitizenDailyShoppingRecorded.Add(DailyKey);
	const uint32 Hash = DeterministicHash(
		EconomySeed,
		CitizenId,
		DayNumber * 131 + static_cast<int32>(FCrc::StrCrc32(*PlaceId.ToString())));
	const FDoemitzItemDefinition& Picked = Items[static_cast<int32>(Hash % static_cast<uint32>(Items.Num()))];
	const int32 Qty = 1 + static_cast<int32>((Hash >> 8) % 2);
	AddPlaceRevenue(PlaceId, Picked.PriceCents * static_cast<int64>(Qty));
}

bool UDoemitzSimulationSubsystem::GetPlaceRevenue(FName PlaceId, int64& OutDailyCents, int64& OutWeeklyCents) const
{
	if (const FDoemitzPlaceRevenue* Rev = PlaceRevenues.Find(PlaceId))
	{
		OutDailyCents = Rev->DailyRevenueCents;
		OutWeeklyCents = Rev->WeeklyRevenueCents;
		return true;
	}
	OutDailyCents = 0;
	OutWeeklyCents = 0;
	return PlacesById.Contains(PlaceId);
}

// ============================================================================
// Daily Tasks (Milestone 3)
// ============================================================================

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

void UDoemitzSimulationSubsystem::GenerateDailyTasks()
{
	// Remove stale unaccepted Available tasks from earlier days
	Tasks.RemoveAll([](const FDoemitzTaskInstance& T) {
		return T.Status == EDoemitzTaskStatus::Available;
	});

	if (TaskTemplates.IsEmpty() || CitizenRecords.IsEmpty())
	{
		return;
	}

	// Collect eligible templates whose places actually open on the current DayOfWeek
	struct FScoredTemplate
	{
		const FDoemitzTaskTemplate* Template = nullptr;
		uint32 Score = 0;
		int32 DeadlineMinute = 1020;
	};
	TArray<FScoredTemplate> EligibleErrands;
	TArray<FScoredTemplate> EligibleFetches;

	for (const FDoemitzTaskTemplate& Tpl : TaskTemplates)
	{
		int32 Deadline = 1020;
		if (Tpl.TaskType == EDoemitzTaskType::Errand)
		{
			int32 PickStart = 0, PickEnd = 0, DelStart = 0, DelEnd = 0;
			if (!FindOpenWindowOnDay(Tpl.PickupPlaceId, DayOfWeek, PickStart, PickEnd) ||
				!FindOpenWindowOnDay(Tpl.DeliveryPlaceId, DayOfWeek, DelStart, DelEnd))
			{
				continue;
			}
			const int32 BaseStart = FMath::Max(PickStart, FMath::FloorToInt(TimeOfDayMinutes));
			if (BaseStart + 30 > PickEnd || BaseStart + 30 > DelEnd)
			{
				continue;
			}
			Deadline = FMath::Min(DelEnd, FMath::Max(BaseStart + Tpl.DurationMinutes, DelStart + 90));
			FScoredTemplate Entry;
			Entry.Template = &Tpl;
			Entry.Score = DeterministicHash(TaskSeed, Tpl.TemplateId, DayNumber * 37 + 11);
			Entry.DeadlineMinute = Deadline;
			EligibleErrands.Add(Entry);
		}
		else
		{
			int32 ShopStart = 0, ShopEnd = 0;
			if (!FindOpenWindowOnDay(Tpl.PreferredShopPlaceId, DayOfWeek, ShopStart, ShopEnd))
			{
				continue;
			}
			const int32 BaseStart = FMath::Max(ShopStart, FMath::FloorToInt(TimeOfDayMinutes));
			if (BaseStart + 30 > ShopEnd)
			{
				continue;
			}
			Deadline = FMath::Min(ShopEnd, BaseStart + Tpl.DurationMinutes);
			FScoredTemplate Entry;
			Entry.Template = &Tpl;
			Entry.Score = DeterministicHash(TaskSeed, Tpl.TemplateId, DayNumber * 37 + 23);
			Entry.DeadlineMinute = Deadline;
			EligibleFetches.Add(Entry);
		}
	}

	auto SortByScore = [](const FScoredTemplate& A, const FScoredTemplate& B) {
		if (A.Score != B.Score)
		{
			return A.Score < B.Score;
		}
		return A.Template->TemplateId.LexicalLess(B.Template->TemplateId);
	};
	EligibleErrands.Sort(SortByScore);
	EligibleFetches.Sort(SortByScore);

	const int32 Span = FMath::Max(1, DailyMaxTasks - DailyMinTasks + 1);
	const uint32 CountHash = DeterministicHash(TaskSeed, FName(TEXT("DailyCount")), DayNumber);
	const int32 TargetCount = DailyMinTasks + static_cast<int32>(CountHash % static_cast<uint32>(Span));

	// Interleave errands and fetches so every day reliably has both types when available
	TArray<FScoredTemplate> Selected;
	int32 ErrIdx = 0;
	int32 FetIdx = 0;
	while (Selected.Num() < TargetCount && (ErrIdx < EligibleErrands.Num() || FetIdx < EligibleFetches.Num()))
	{
		if (ErrIdx < EligibleErrands.Num())
		{
			Selected.Add(EligibleErrands[ErrIdx++]);
		}
		if (Selected.Num() < TargetCount && FetIdx < EligibleFetches.Num())
		{
			Selected.Add(EligibleFetches[FetIdx++]);
		}
	}

	TArray<FName> SortedCitizens;
	CitizenRecords.GetKeys(SortedCitizens);
	SortedCitizens.Sort(FNameLexicalLess());
	TSet<FName> UsedCitizens;

	for (int32 i = 0; i < Selected.Num(); ++i)
	{
		const FScoredTemplate& Pick = Selected[i];
		const FDoemitzTaskTemplate& Tpl = *Pick.Template;

		// Pick a deterministic citizen not already offering a task today (prefer Anna/Bernd/Clara/Dieter for first tasks)
		FName GiverId = NAME_None;
		if (!SortedCitizens.IsEmpty())
		{
			const uint32 CitHash = DeterministicHash(TaskSeed, Tpl.TemplateId, DayNumber * 97 + i);
			const int32 StartIdx = static_cast<int32>(CitHash % static_cast<uint32>(SortedCitizens.Num()));
			for (int32 Offset = 0; Offset < SortedCitizens.Num(); ++Offset)
			{
				const FName Candidate = SortedCitizens[(StartIdx + Offset) % SortedCitizens.Num()];
				if (!UsedCitizens.Contains(Candidate))
				{
					GiverId = Candidate;
					UsedCitizens.Add(Candidate);
					break;
				}
			}
		}

		FDoemitzTaskInstance Inst;
		Inst.TaskId = FName(*FString::Printf(TEXT("task:%d:%s"), DayNumber, *Tpl.TemplateId.ToString()));
		Inst.TemplateId = Tpl.TemplateId;
		Inst.TaskType = Tpl.TaskType;
		Inst.Status = EDoemitzTaskStatus::Available;
		Inst.Title = Tpl.Title;
		Inst.Description = Tpl.Description;
		Inst.GiverCitizenId = GiverId;
		Inst.PickupPlaceId = Tpl.PickupPlaceId;
		Inst.DeliveryPlaceId = Tpl.DeliveryPlaceId;
		Inst.ParcelName = Tpl.ParcelName;
		Inst.bPickedUp = false;
		Inst.RequestedItemId = Tpl.RequestedItemId;
		Inst.PreferredShopPlaceId = Tpl.PreferredShopPlaceId;
		Inst.DayNumber = DayNumber;
		Inst.DeadlineMinute = Pick.DeadlineMinute;
		Inst.RewardCents = Tpl.RewardCents;

		const bool bAlreadyExists = Tasks.ContainsByPredicate([&Inst](const FDoemitzTaskInstance& Existing) {
			return Existing.TaskId == Inst.TaskId;
		});
		if (!bAlreadyExists)
		{
			Tasks.Add(MoveTemp(Inst));
		}
	}
}

TArray<FDoemitzTaskInstance> UDoemitzSimulationSubsystem::GetTasksByStatus(EDoemitzTaskStatus Status) const
{
	TArray<FDoemitzTaskInstance> Out;
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status == Status)
		{
			Out.Add(Task);
		}
	}
	return Out;
}

bool UDoemitzSimulationSubsystem::GetTaskById(FName TaskId, FDoemitzTaskInstance& OutTask) const
{
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.TaskId == TaskId)
		{
			OutTask = Task;
			return true;
		}
	}
	return false;
}

bool UDoemitzSimulationSubsystem::GetPrimaryActiveTask(FDoemitzTaskInstance& OutTask) const
{
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status == EDoemitzTaskStatus::Active)
		{
			OutTask = Task;
			return true;
		}
	}
	return false;
}

bool UDoemitzSimulationSubsystem::GetTaskOfferedByCitizen(FName CitizenId, FDoemitzTaskInstance& OutTask) const
{
	if (CitizenId.IsNone())
	{
		return false;
	}
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status == EDoemitzTaskStatus::Available && Task.GiverCitizenId == CitizenId)
		{
			OutTask = Task;
			return true;
		}
	}
	return false;
}

bool UDoemitzSimulationSubsystem::GetActiveFetchTaskForCitizen(FName CitizenId, FDoemitzTaskInstance& OutTask) const
{
	if (CitizenId.IsNone())
	{
		return false;
	}
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status == EDoemitzTaskStatus::Active &&
			Task.TaskType == EDoemitzTaskType::Fetch &&
			Task.GiverCitizenId == CitizenId)
		{
			OutTask = Task;
			return true;
		}
	}
	return false;
}

bool UDoemitzSimulationSubsystem::GetActiveErrandForPlace(FName PlaceId, FDoemitzTaskInstance& OutTask, bool& bOutIsDelivery) const
{
	bOutIsDelivery = false;
	if (PlaceId.IsNone())
	{
		return false;
	}
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status == EDoemitzTaskStatus::Active && Task.TaskType == EDoemitzTaskType::Errand)
		{
			if (!Task.bPickedUp && Task.PickupPlaceId == PlaceId)
			{
				OutTask = Task;
				bOutIsDelivery = false;
				return true;
			}
			if (Task.bPickedUp && Task.DeliveryPlaceId == PlaceId)
			{
				OutTask = Task;
				bOutIsDelivery = true;
				return true;
			}
		}
	}
	return false;
}

bool UDoemitzSimulationSubsystem::GetActiveTaskTargetLocation(FVector& OutWorldLocation, FName& OutTargetPlaceId, FName& OutTargetCitizenId) const
{
	OutTargetPlaceId = NAME_None;
	OutTargetCitizenId = NAME_None;
	FDoemitzTaskInstance Active;
	if (!GetPrimaryActiveTask(Active))
	{
		return false;
	}

	if (Active.TaskType == EDoemitzTaskType::Errand)
	{
		const FName TargetPlace = Active.bPickedUp ? Active.DeliveryPlaceId : Active.PickupPlaceId;
		if (const FDoemitzPlaceDefinition* Place = PlacesById.Find(TargetPlace))
		{
			OutWorldLocation = !Place->EntranceLocation.IsNearlyZero() ? Place->EntranceLocation : Place->AccessLocation;
			OutTargetPlaceId = TargetPlace;
			return true;
		}
		return false;
	}

	// Fetch task: if player does not yet own the item, point to preferred shop; otherwise point to giver citizen
	if (GetInventoryQuantity(Active.RequestedItemId) < 1)
	{
		if (const FDoemitzPlaceDefinition* Shop = PlacesById.Find(Active.PreferredShopPlaceId))
		{
			OutWorldLocation = !Shop->EntranceLocation.IsNearlyZero() ? Shop->EntranceLocation : Shop->AccessLocation;
			OutTargetPlaceId = Active.PreferredShopPlaceId;
			return true;
		}
	}
	if (const FCitizenRecord* Cit = CitizenRecords.Find(Active.GiverCitizenId))
	{
		OutWorldLocation = Cit->State.WorldLocation;
		OutTargetCitizenId = Active.GiverCitizenId;
		return true;
	}
	return false;
}

bool UDoemitzSimulationSubsystem::AcceptTask(FName TaskId)
{
	for (FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.TaskId == TaskId && Task.Status == EDoemitzTaskStatus::Available)
		{
			Task.Status = EDoemitzTaskStatus::Active;
			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::TaskAccepted;
			Ev.TaskId = Task.TaskId;
			Ev.MinuteValue = Task.DeadlineMinute;
			PushNotificationEvent(Ev);
			return true;
		}
	}
	return false;
}

bool UDoemitzSimulationSubsystem::PickupTaskParcel(FName TaskId)
{
	for (FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.TaskId == TaskId &&
			Task.Status == EDoemitzTaskStatus::Active &&
			Task.TaskType == EDoemitzTaskType::Errand &&
			!Task.bPickedUp)
		{
			if (!IsPlaceOpenNow(Task.PickupPlaceId))
			{
				FDoemitzNotificationEvent Ev;
				Ev.Code = EDoemitzNotificationCode::PlaceClosed;
				Ev.PlaceId = Task.PickupPlaceId;
				PushNotificationEvent(Ev);
				return false;
			}
			Task.bPickedUp = true;
			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::TaskParcelPickedUp;
			Ev.TaskId = Task.TaskId;
			Ev.PlaceId = Task.DeliveryPlaceId;
			PushNotificationEvent(Ev);
			return true;
		}
	}
	return false;
}

bool UDoemitzSimulationSubsystem::DeliverTaskParcel(FName TaskId)
{
	for (FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.TaskId == TaskId &&
			Task.Status == EDoemitzTaskStatus::Active &&
			Task.TaskType == EDoemitzTaskType::Errand &&
			Task.bPickedUp)
		{
			if (!IsPlaceOpenNow(Task.DeliveryPlaceId))
			{
				FDoemitzNotificationEvent Ev;
				Ev.Code = EDoemitzNotificationCode::PlaceClosed;
				Ev.PlaceId = Task.DeliveryPlaceId;
				PushNotificationEvent(Ev);
				return false;
			}
			Task.Status = EDoemitzTaskStatus::Completed;
			PlayerMoneyCents += Task.RewardCents;
			AppendLedgerEntry(Task.DeliveryPlaceId, Task.RewardCents, FString::Printf(TEXT("TASK:%s"), *Task.TaskId.ToString()));

			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::TaskCompleted;
			Ev.TaskId = Task.TaskId;
			Ev.AmountCents = Task.RewardCents;
			PushNotificationEvent(Ev);
			return true;
		}
	}
	return false;
}

bool UDoemitzSimulationSubsystem::CompleteFetchTask(FName TaskId)
{
	for (FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.TaskId == TaskId &&
			Task.Status == EDoemitzTaskStatus::Active &&
			Task.TaskType == EDoemitzTaskType::Fetch)
		{
			int32* QtyPtr = PlayerInventory.Find(Task.RequestedItemId);
			if (!QtyPtr || *QtyPtr < 1)
			{
				FDoemitzNotificationEvent Ev;
				Ev.Code = EDoemitzNotificationCode::TaskNeedsItem;
				Ev.TaskId = Task.TaskId;
				Ev.ItemId = Task.RequestedItemId;
				PushNotificationEvent(Ev);
				return false;
			}
			*QtyPtr -= 1;
			if (*QtyPtr <= 0)
			{
				PlayerInventory.Remove(Task.RequestedItemId);
			}
			Task.Status = EDoemitzTaskStatus::Completed;
			PlayerMoneyCents += Task.RewardCents;
			AppendLedgerEntry(Task.PreferredShopPlaceId, Task.RewardCents, FString::Printf(TEXT("TASK:%s"), *Task.TaskId.ToString()));

			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::TaskCompleted;
			Ev.TaskId = Task.TaskId;
			Ev.AmountCents = Task.RewardCents;
			PushNotificationEvent(Ev);
			return true;
		}
	}
	return false;
}

void UDoemitzSimulationSubsystem::CheckTaskDeadlines()
{
	for (FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status != EDoemitzTaskStatus::Active)
		{
			continue;
		}
		const bool bExpired = (DayNumber > Task.DayNumber) ||
			(DayNumber == Task.DayNumber && TimeOfDayMinutes >= static_cast<double>(Task.DeadlineMinute));
		if (bExpired)
		{
			Task.Status = EDoemitzTaskStatus::Missed;
			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::TaskMissed;
			Ev.TaskId = Task.TaskId;
			PushNotificationEvent(Ev);
		}
	}
}

// ============================================================================
// Places, Opening Status & Calendar
// ============================================================================

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

// ============================================================================
// Citizens & Dialog Pause
// ============================================================================

const TArray<FDoemitzScheduleEntry>& UDoemitzSimulationSubsystem::GetActiveScheduleForDay(const FDoemitzCitizenDefinition& Def) const
{
	const EDoemitzDayKind Kind = GetDayKind();
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

FDoemitzScheduleEntry UDoemitzSimulationSubsystem::ResolveDesiredEntry(const FDoemitzCitizenDefinition& Def, int32& OutIndex) const
{
	const TArray<FDoemitzScheduleEntry>& ActiveSchedule = GetActiveScheduleForDay(Def);
	if (ActiveSchedule.IsEmpty())
	{
		OutIndex = 0;
		FDoemitzScheduleEntry Fallback;
		Fallback.Activity = EDoemitzCitizenActivity::Home;
		Fallback.PlaceId = Def.HomePlaceId;
		return Fallback;
	}

	const int32 BaseIndex = FindScheduleIndex(ActiveSchedule, TimeOfDayMinutes);
	for (int32 Offset = 0; Offset < ActiveSchedule.Num(); ++Offset)
	{
		const int32 CandidateIndex = (BaseIndex + Offset) % ActiveSchedule.Num();
		const FDoemitzScheduleEntry& Candidate = ActiveSchedule[CandidateIndex];
		if (Candidate.Activity == EDoemitzCitizenActivity::Shopping && !IsPlaceOpenNow(Candidate.PlaceId))
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

void UDoemitzSimulationSubsystem::ResetCitizenToCurrentSchedule(FCitizenRecord& Record)
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
	if (const FDoemitzPlaceDefinition* Place = PlacesById.Find(Entry.PlaceId))
	{
		Record.State.WorldLocation = Place->AccessLocation;
	}
}

bool UDoemitzSimulationSubsystem::FindNearestCitizen(
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

bool UDoemitzSimulationSubsystem::SetCitizenDialogPaused(FName CitizenId, bool bPaused)
{
	FCitizenRecord* Rec = CitizenRecords.Find(CitizenId);
	if (!Rec)
	{
		return false;
	}
	Rec->State.bIsPausedForDialog = bPaused;
	return true;
}

bool UDoemitzSimulationSubsystem::IsCitizenDialogPaused(FName CitizenId) const
{
	if (const FCitizenRecord* Rec = CitizenRecords.Find(CitizenId))
	{
		return Rec->State.bIsPausedForDialog;
	}
	return false;
}

bool UDoemitzSimulationSubsystem::IsCitizenHighDetail(FName CitizenId) const
{
	if (const FCitizenRecord* Record = CitizenRecords.Find(CitizenId))
	{
		return Record->State.bIsHighDetail;
	}
	return false;
}

bool UDoemitzSimulationSubsystem::GetCitizenActorLocation(FName CitizenId, FVector& OutLocation) const
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

void UDoemitzSimulationSubsystem::SetCitizenLodRadiusCm(double NewRadiusCm)
{
	CitizenLodRadiusCm = FMath::Max(100.0, NewRadiusCm);
	UpdateCitizenLodPool();
}

bool UDoemitzSimulationSubsystem::SetCitizenAtPlaceForTest(FName CitizenId, FName PlaceId, EDoemitzCitizenActivity Activity)
{
	FCitizenRecord* Record = CitizenRecords.Find(CitizenId);
	const FDoemitzPlaceDefinition* Place = PlacesById.Find(PlaceId);
	if (!Record || !Place)
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
	Record->State.WorldLocation = Place->AccessLocation;
	return true;
}

bool UDoemitzSimulationSubsystem::SetCitizenPositionForTest(FName CitizenId, const FVector& NewLocation)
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

bool UDoemitzSimulationSubsystem::GetCrossingLocation(FName CrossingId, FVector& OutLocation) const
{
	for (const FDoemitzCrossingDefinition& Crossing : Crossings)
	{
		if (Crossing.CrossingId == CrossingId)
		{
			OutLocation = Crossing.Location;
			return true;
		}
	}
	return false;
}

TArray<FName> UDoemitzSimulationSubsystem::GetAllCrossingIds() const
{
	TArray<FName> Ids;
	Ids.Reserve(Crossings.Num());
	for (const FDoemitzCrossingDefinition& Crossing : Crossings)
	{
		Ids.Add(Crossing.CrossingId);
	}
	return Ids;
}

ADoemitzCitizenActor* UDoemitzSimulationSubsystem::AcquirePooledCitizenActor(const FCitizenRecord& Record)
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

void UDoemitzSimulationSubsystem::ReleaseCitizenActor(FName CitizenId)
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

void UDoemitzSimulationSubsystem::UpdateCitizenLodPool()
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
			if (!bWasHighDetail && Record.CoarseAccumulatedSeconds > 0.0)
			{
				const double Pending = Record.CoarseAccumulatedSeconds;
				Record.CoarseAccumulatedSeconds = 0.0;
				UpdateCitizen(Record, Pending);
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
		CheckTaskDeadlines();
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
	Ids.Sort(FNameLexicalLess());
	return Ids;
}

// ============================================================================
// Traffic, Priority Signs (Milestone 6) & Parking (Milestone 7)
// ============================================================================

bool UDoemitzSimulationSubsystem::GetVehicleState(FName VehicleId, FDoemitzVehicleState& OutState) const
{
	if (const FVehicleRecord* Record = VehicleRecords.Find(VehicleId))
	{
		OutState = Record->State;
		return true;
	}
	return false;
}

TArray<FName> UDoemitzSimulationSubsystem::GetAllVehicleIds() const
{
	return OrderedVehicleIds;
}

FName UDoemitzSimulationSubsystem::GetJunctionReservation(FName NodeId) const
{
	if (const FName* Holder = JunctionReservations.Find(NodeId))
	{
		return *Holder;
	}
	return NAME_None;
}

EDoemitzYieldRule UDoemitzSimulationSubsystem::GetEdgeYieldRule(FName EdgeId) const
{
	if (const FRoadEdgeRecord* Edge = RoadEdgesById.Find(EdgeId))
	{
		return Edge->Definition.YieldRule;
	}
	return EDoemitzYieldRule::None;
}

bool UDoemitzSimulationSubsystem::SetEdgeYieldRuleForTest(FName EdgeId, EDoemitzYieldRule NewRule)
{
	if (FRoadEdgeRecord* Edge = RoadEdgesById.Find(EdgeId))
	{
		Edge->Definition.YieldRule = NewRule;
		return true;
	}
	return false;
}

bool UDoemitzSimulationSubsystem::GetParkingLotState(FName ParkingLotId, FDoemitzParkingLotState& OutState) const
{
	const FParkingLotRecord* Rec = ParkingLotsById.Find(ParkingLotId);
	if (!Rec)
	{
		return false;
	}
	OutState.ParkingLotId = Rec->Definition.ParkingLotId;
	OutState.DisplayName = Rec->Definition.DisplayName;
	OutState.Location = Rec->Definition.Location;
	OutState.Capacity = Rec->Definition.Capacity;
	OutState.OccupiedByVehicles.Reset();
	for (FName Vid : Rec->SlotOccupants)
	{
		if (!Vid.IsNone())
		{
			OutState.OccupiedByVehicles.Add(Vid);
		}
	}
	OutState.OccupiedCount = OutState.OccupiedByVehicles.Num();
	return true;
}

bool UDoemitzSimulationSubsystem::SetVehicleEdgePositionForTest(
	FName VehicleId,
	FName EdgeId,
	double DistanceOnEdgeCm,
	double SpeedCmPerSecond)
{
	FVehicleRecord* Record = VehicleRecords.Find(VehicleId);
	const FRoadEdgeRecord* Edge = RoadEdgesById.Find(EdgeId);
	if (!Record || !Edge)
	{
		return false;
	}
	ReleaseJunctionReservation(*Record);
	ReleaseParkingSlot(*Record);
	Record->State.Phase = EDoemitzVehiclePhase::Driving;
	Record->State.CurrentParkingLotId = NAME_None;
	Record->State.TargetParkingLotId = NAME_None;
	Record->State.ParkingSlotIndex = -1;
	Record->State.RemainingParkSeconds = 0.0;
	Record->PlannedEdges.Reset();
	Record->bCompletedStopAtEdge = false;
	Record->StopHoldElapsedSeconds = 0.0;
	Record->State.CurrentEdgeId = EdgeId;
	Record->State.DistanceOnEdgeCm = FMath::Clamp(DistanceOnEdgeCm, 0.0, FMath::Max(0.0, Edge->LengthCm - 1.0));
	Record->State.CurrentSpeedCmPerSecond = FMath::Max(0.0, SpeedCmPerSecond);
	Record->State.NextEdgeId = ChooseNextEdge(*Record);
	SampleEdgePose(*Edge, Record->State.DistanceOnEdgeCm, Record->State.WorldLocation, Record->State.WorldRotation);
	return true;
}

bool UDoemitzSimulationSubsystem::SetVehicleTargetParkingForTest(FName VehicleId, FName ParkingLotId)
{
	FVehicleRecord* Record = VehicleRecords.Find(VehicleId);
	if (!Record || !ParkingLotsById.Contains(ParkingLotId))
	{
		return false;
	}
	PlanRouteToParking(*Record, ParkingLotId);
	return true;
}

void UDoemitzSimulationSubsystem::SampleEdgePose(
	const FRoadEdgeRecord& Edge,
	double DistanceCm,
	FVector& OutLocation,
	FRotator& OutRotation) const
{
	const double Clamped = FMath::Clamp(DistanceCm, 0.0, Edge.LengthCm);
	const int32 SegIndex = FMath::Clamp(
		Algo::UpperBound(Edge.SegmentEnds, Clamped),
		0,
		Edge.SegmentEnds.Num() - 1);
	const double SegStart = SegIndex == 0 ? 0.0 : Edge.SegmentEnds[SegIndex - 1];
	const double SegLen = FMath::Max(Edge.SegmentEnds[SegIndex] - SegStart, UE_KINDA_SMALL_NUMBER);
	const double Alpha = FMath::Clamp((Clamped - SegStart) / SegLen, 0.0, 1.0);

	const FVector& A = Edge.Definition.Points[SegIndex];
	const FVector& B = Edge.Definition.Points[SegIndex + 1];
	FVector Pos = FMath::Lerp(A, B, Alpha);
	const FVector Dir = (B - A).GetSafeNormal();
	if (!Dir.IsNearlyZero())
	{
		OutRotation = Dir.Rotation();
		OutRotation.Roll = 0.0;
		if (!Edge.Definition.bOneWay)
		{
			const double LaneOffset = FMath::Min(140.0, Edge.Definition.WidthCm * 0.22);
			FVector2D Right2D(-Dir.Y, Dir.X);
			if (Right2D.Normalize())
			{
				Pos.X += Right2D.X * LaneOffset;
				Pos.Y += Right2D.Y * LaneOffset;
			}
		}
	}
	OutLocation = Pos;
}

FName UDoemitzSimulationSubsystem::ChooseNextEdge(const FVehicleRecord& Record) const
{
	const FRoadEdgeRecord* CurrentEdge = RoadEdgesById.Find(Record.State.CurrentEdgeId);
	if (!CurrentEdge)
	{
		return NAME_None;
	}
	const TArray<FName>* Outgoing = OutgoingEdgesByNode.Find(CurrentEdge->Definition.ToNodeId);
	if (!Outgoing || Outgoing->IsEmpty())
	{
		return NAME_None;
	}

	TArray<FName> Preferred;
	TArray<FName> Fallback;
	for (FName CandidateId : *Outgoing)
	{
		const FRoadEdgeRecord* Candidate = RoadEdgesById.Find(CandidateId);
		if (!Candidate || Candidate->Definition.bDeadEnd)
		{
			continue;
		}
		Fallback.Add(CandidateId);
		if (Candidate->Definition.ToNodeId != CurrentEdge->Definition.FromNodeId)
		{
			Preferred.Add(CandidateId);
		}
	}

	const TArray<FName>& Pool = !Preferred.IsEmpty() ? Preferred : Fallback;
	if (Pool.IsEmpty())
	{
		return NAME_None;
	}
	const uint32 Hash = DeterministicHash(TrafficSeed, Record.State.VehicleId, Record.State.JunctionDecisions);
	return Pool[static_cast<int32>(Hash % static_cast<uint32>(Pool.Num()))];
}

bool UDoemitzSimulationSubsystem::ComputeEdgePath(FName StartEdgeId, FName GoalEdgeId, TArray<FName>& OutPath) const
{
	OutPath.Reset();
	if (StartEdgeId.IsNone() || GoalEdgeId.IsNone() || StartEdgeId == GoalEdgeId)
	{
		return StartEdgeId == GoalEdgeId && !StartEdgeId.IsNone();
	}
	const FRoadEdgeRecord* StartEdge = RoadEdgesById.Find(StartEdgeId);
	const FRoadEdgeRecord* GoalEdge = RoadEdgesById.Find(GoalEdgeId);
	if (!StartEdge || !GoalEdge)
	{
		return false;
	}

	// Simple deterministic Dijkstra over directed road edges (graph has ~170 edges -> microseconds)
	TMap<FName, double> DistByEdge;
	TMap<FName, FName> PrevEdge;
	TSet<FName> Visited;
	DistByEdge.Add(StartEdgeId, 0.0);

	while (true)
	{
		FName BestEdge = NAME_None;
		double BestDist = TNumericLimits<double>::Max();
		for (const TPair<FName, double>& Pair : DistByEdge)
		{
			if (!Visited.Contains(Pair.Key) && Pair.Value < BestDist)
			{
				BestDist = Pair.Value;
				BestEdge = Pair.Key;
			}
		}
		if (BestEdge.IsNone() || BestEdge == GoalEdgeId)
		{
			break;
		}
		Visited.Add(BestEdge);

		const FRoadEdgeRecord* Cur = RoadEdgesById.Find(BestEdge);
		if (!Cur)
		{
			continue;
		}
		const TArray<FName>* Outgoing = OutgoingEdgesByNode.Find(Cur->Definition.ToNodeId);
		if (!Outgoing)
		{
			continue;
		}
		for (FName NextId : *Outgoing)
		{
			const FRoadEdgeRecord* NextRec = RoadEdgesById.Find(NextId);
			if (!NextRec || (NextRec->Definition.bDeadEnd && NextId != GoalEdgeId))
			{
				continue;
			}
			const double NewDist = BestDist + NextRec->LengthCm;
			const double* Existing = DistByEdge.Find(NextId);
			if (!Existing || NewDist < *Existing)
			{
				DistByEdge.Add(NextId, NewDist);
				PrevEdge.Add(NextId, BestEdge);
			}
		}
	}

	if (!PrevEdge.Contains(GoalEdgeId))
	{
		return false;
	}
	FName Cursor = GoalEdgeId;
	while (Cursor != StartEdgeId)
	{
		OutPath.Add(Cursor);
		const FName* Parent = PrevEdge.Find(Cursor);
		if (!Parent)
		{
			OutPath.Reset();
			return false;
		}
		Cursor = *Parent;
	}
	Algo::Reverse(OutPath);
	return true;
}

FName UDoemitzSimulationSubsystem::ChooseNextParkingLot(const FVehicleRecord& Record, FName ExcludeLotId) const
{
	if (OrderedParkingLotIds.IsEmpty())
	{
		return NAME_None;
	}
	TArray<FName> Candidates;
	for (FName LotId : OrderedParkingLotIds)
	{
		if (LotId != ExcludeLotId || OrderedParkingLotIds.Num() == 1)
		{
			Candidates.Add(LotId);
		}
	}
	const uint32 Hash = DeterministicHash(TrafficSeed + 101, Record.State.VehicleId, Record.TripCounter);
	return Candidates[static_cast<int32>(Hash % static_cast<uint32>(Candidates.Num()))];
}

void UDoemitzSimulationSubsystem::PlanRouteToParking(FVehicleRecord& Record, FName ParkingLotId)
{
	Record.State.TargetParkingLotId = ParkingLotId;
	Record.PlannedEdges.Reset();
	const FParkingLotRecord* Lot = ParkingLotsById.Find(ParkingLotId);
	if (!Lot)
	{
		return;
	}
	if (Record.State.CurrentEdgeId != Lot->Definition.AccessEdgeId)
	{
		ComputeEdgePath(Record.State.CurrentEdgeId, Lot->Definition.AccessEdgeId, Record.PlannedEdges);
	}
	if (!Record.PlannedEdges.IsEmpty())
	{
		Record.State.NextEdgeId = Record.PlannedEdges[0];
	}
	else
	{
		Record.State.NextEdgeId = ChooseNextEdge(Record);
	}
}

int32 UDoemitzSimulationSubsystem::TryReserveParkingSlot(FName ParkingLotId, FName VehicleId, FVector& OutSlotLocation)
{
	FParkingLotRecord* Lot = ParkingLotsById.Find(ParkingLotId);
	if (!Lot)
	{
		return -1;
	}
	for (int32 i = 0; i < Lot->SlotOccupants.Num(); ++i)
	{
		if (Lot->SlotOccupants[i].IsNone() || Lot->SlotOccupants[i] == VehicleId)
		{
			Lot->SlotOccupants[i] = VehicleId;
			OutSlotLocation = Lot->Definition.SlotLocations.IsValidIndex(i)
				? Lot->Definition.SlotLocations[i]
				: Lot->Definition.Location;
			return i;
		}
	}
	return -1;
}

void UDoemitzSimulationSubsystem::ReleaseParkingSlot(FVehicleRecord& Record)
{
	if (!Record.State.CurrentParkingLotId.IsNone())
	{
		if (FParkingLotRecord* Lot = ParkingLotsById.Find(Record.State.CurrentParkingLotId))
		{
			for (FName& Occupant : Lot->SlotOccupants)
			{
				if (Occupant == Record.State.VehicleId)
				{
					Occupant = NAME_None;
				}
			}
		}
	}
	Record.State.CurrentParkingLotId = NAME_None;
	Record.State.ParkingSlotIndex = -1;
}

FName UDoemitzSimulationSubsystem::FindNearestDrivableEdge(const FVector& Location, double& OutDistanceCm) const
{
	FName BestEdgeId = NAME_None;
	double BestDistSq = TNumericLimits<double>::Max();
	double BestAlongCm = 0.0;

	for (const TPair<FName, FRoadEdgeRecord>& Pair : RoadEdgesById)
	{
		const FRoadEdgeRecord& Edge = Pair.Value;
		if (Edge.Definition.bDeadEnd)
		{
			continue;
		}
		double Cumulative = 0.0;
		for (int32 i = 0; i + 1 < Edge.Definition.Points.Num(); ++i)
		{
			const FVector& A = Edge.Definition.Points[i];
			const FVector& B = Edge.Definition.Points[i + 1];
			const FVector Closest = FMath::ClosestPointOnSegment(Location, A, B);
			const double DistSq = FVector::DistSquared2D(Location, Closest);
			if (DistSq < BestDistSq)
			{
				BestDistSq = DistSq;
				BestEdgeId = Pair.Key;
				BestAlongCm = Cumulative + FVector::Dist2D(A, Closest);
			}
			Cumulative += FVector::Distance(A, B);
		}
	}
	OutDistanceCm = BestAlongCm;
	return BestEdgeId;
}

void UDoemitzSimulationSubsystem::ReleaseJunctionReservation(FVehicleRecord& Record)
{
	if (!Record.ReservedNodeId.IsNone())
	{
		if (const FName* Holder = JunctionReservations.Find(Record.ReservedNodeId))
		{
			if (*Holder == Record.State.VehicleId)
			{
				JunctionReservations.Remove(Record.ReservedNodeId);
			}
		}
		Record.ReservedNodeId = NAME_None;
	}
}

void UDoemitzSimulationSubsystem::UpdateTraffic(double DeltaSeconds)
{
	if (OrderedVehicleIds.IsEmpty())
	{
		return;
	}

	TArray<FVector> PedestrianLocations;
	PedestrianLocations.Reserve(CitizenRecords.Num() + 1);
	if (UWorld* World = GetWorld())
	{
		if (const APlayerController* PC = World->GetFirstPlayerController())
		{
			if (const APawn* Pawn = PC->GetPawn())
			{
				PedestrianLocations.Add(Pawn->GetActorLocation());
			}
		}
	}
	for (const TPair<FName, FCitizenRecord>& Pair : CitizenRecords)
	{
		PedestrianLocations.Add(Pair.Value.State.WorldLocation);
	}

	TArray<FVector> OccupiedCrossings;
	if (!Crossings.IsEmpty())
	{
		for (const FDoemitzCrossingDefinition& Crossing : Crossings)
		{
			const double TriggerSq = Crossing.TriggerRadiusCm * Crossing.TriggerRadiusCm;
			for (const FVector& PedPos : PedestrianLocations)
			{
				if (FVector::DistSquared2D(PedPos, Crossing.Location) <= TriggerSq)
				{
					OccupiedCrossings.Add(Crossing.Location);
					break;
				}
			}
		}
	}

	for (FName VehicleId : OrderedVehicleIds)
	{
		FVehicleRecord* Record = VehicleRecords.Find(VehicleId);
		if (!Record)
		{
			continue;
		}

		// Handle Parking / Parked / Leaving phases
		if (Record->State.Phase == EDoemitzVehiclePhase::Parking)
		{
			Record->ManeuverProgress = FMath::Min(1.0, Record->ManeuverProgress + (DeltaSeconds / ParkingManeuverSeconds));
			Record->State.WorldLocation = FMath::Lerp(Record->ManeuverStartLocation, Record->ManeuverEndLocation, Record->ManeuverProgress);
			Record->State.WorldRotation = FMath::Lerp(Record->ManeuverStartRotation, Record->ManeuverEndRotation, Record->ManeuverProgress);
			Record->State.CurrentSpeedCmPerSecond = 0.0;
			if (Record->ManeuverProgress >= 1.0)
			{
				Record->State.Phase = EDoemitzVehiclePhase::Parked;
				const uint32 ParkHash = DeterministicHash(TrafficSeed + 303, VehicleId, Record->TripCounter);
				Record->State.RemainingParkSeconds = 12.0 + static_cast<double>(ParkHash % 20);
			}
			continue;
		}

		if (Record->State.Phase == EDoemitzVehiclePhase::Parked)
		{
			Record->State.CurrentSpeedCmPerSecond = 0.0;
			Record->State.RemainingParkSeconds = FMath::Max(0.0, Record->State.RemainingParkSeconds - DeltaSeconds);
			if (Record->State.RemainingParkSeconds <= 0.0)
			{
				const FParkingLotRecord* Lot = ParkingLotsById.Find(Record->State.CurrentParkingLotId);
				const FRoadEdgeRecord* AccessEdge = Lot ? RoadEdgesById.Find(Lot->Definition.AccessEdgeId) : nullptr;
				if (Lot && AccessEdge)
				{
					FVector RoadLoc;
					FRotator RoadRot;
					SampleEdgePose(*AccessEdge, Lot->Definition.AccessDistanceCm, RoadLoc, RoadRot);

					// Check road is clear before pulling out
					bool bRoadClear = true;
					for (FName OtherId : OrderedVehicleIds)
					{
						if (OtherId == VehicleId)
						{
							continue;
						}
						const FVehicleRecord* Other = VehicleRecords.Find(OtherId);
						if (Other && Other->State.Phase != EDoemitzVehiclePhase::Parked &&
							FVector::Dist2D(Other->State.WorldLocation, RoadLoc) < MinCenterSpacingCm)
						{
							bRoadClear = false;
							break;
						}
					}

					if (bRoadClear)
					{
						Record->State.Phase = EDoemitzVehiclePhase::Leaving;
						Record->ManeuverProgress = 0.0;
						Record->ManeuverStartLocation = Record->State.WorldLocation;
						Record->ManeuverStartRotation = Record->State.WorldRotation;
						Record->ManeuverEndLocation = RoadLoc;
						Record->ManeuverEndRotation = RoadRot;
						Record->State.CurrentEdgeId = Lot->Definition.AccessEdgeId;
						Record->State.DistanceOnEdgeCm = FMath::Clamp(Lot->Definition.AccessDistanceCm, 0.0, FMath::Max(0.0, AccessEdge->LengthCm - 1.0));
					}
				}
			}
			continue;
		}

		if (Record->State.Phase == EDoemitzVehiclePhase::Leaving)
		{
			Record->ManeuverProgress = FMath::Min(1.0, Record->ManeuverProgress + (DeltaSeconds / ParkingManeuverSeconds));
			Record->State.WorldLocation = FMath::Lerp(Record->ManeuverStartLocation, Record->ManeuverEndLocation, Record->ManeuverProgress);
			Record->State.WorldRotation = FMath::Lerp(Record->ManeuverStartRotation, Record->ManeuverEndRotation, Record->ManeuverProgress);
			if (Record->ManeuverProgress >= 1.0)
			{
				const FName LeftLot = Record->State.CurrentParkingLotId;
				ReleaseParkingSlot(*Record);
				Record->TripCounter += 1;
				Record->State.Phase = EDoemitzVehiclePhase::Driving;
				Record->State.CurrentSpeedCmPerSecond = 120.0;
				Record->bCompletedStopAtEdge = false;
				Record->StopHoldElapsedSeconds = 0.0;
				const FName NextLot = ChooseNextParkingLot(*Record, LeftLot);
				PlanRouteToParking(*Record, NextLot);
			}
			continue;
		}

		// --- Driving phase ---
		const FRoadEdgeRecord* Edge = RoadEdgesById.Find(Record->State.CurrentEdgeId);
		if (!Edge)
		{
			continue;
		}

		if (!Record->ReservedNodeId.IsNone() &&
			Record->ReservedNodeId == Edge->Definition.FromNodeId &&
			Record->State.DistanceOnEdgeCm >= JunctionClearanceCm)
		{
			ReleaseJunctionReservation(*Record);
		}

		// Check if arrived at target parking lot's access edge & distance
		if (!Record->State.TargetParkingLotId.IsNone())
		{
			if (const FParkingLotRecord* TargetLot = ParkingLotsById.Find(Record->State.TargetParkingLotId))
			{
				if (Record->State.CurrentEdgeId == TargetLot->Definition.AccessEdgeId &&
					FMath::Abs(Record->State.DistanceOnEdgeCm - TargetLot->Definition.AccessDistanceCm) <= ParkingApproachToleranceCm)
				{
					FVector SlotLoc;
					const int32 SlotIdx = TryReserveParkingSlot(Record->State.TargetParkingLotId, VehicleId, SlotLoc);
					if (SlotIdx >= 0)
					{
						ReleaseJunctionReservation(*Record);
						Record->State.Phase = EDoemitzVehiclePhase::Parking;
						Record->State.CurrentParkingLotId = Record->State.TargetParkingLotId;
						Record->State.ParkingSlotIndex = SlotIdx;
						Record->State.CurrentSpeedCmPerSecond = 0.0;
						Record->PlannedEdges.Reset();
						Record->ManeuverProgress = 0.0;
						Record->ManeuverStartLocation = Record->State.WorldLocation;
						Record->ManeuverStartRotation = Record->State.WorldRotation;
						Record->ManeuverEndLocation = SlotLoc;
						const FVector ToSlot = SlotLoc - Record->State.WorldLocation;
						Record->ManeuverEndRotation = ToSlot.IsNearlyZero() ? Record->State.WorldRotation : ToSlot.Rotation();
						continue;
					}
					else
					{
						// Lot full: pick another parking lot
						Record->TripCounter += 1;
						const FName AltLot = ChooseNextParkingLot(*Record, Record->State.TargetParkingLotId);
						PlanRouteToParking(*Record, AltLot);
					}
				}
			}
		}

		if (Record->State.NextEdgeId.IsNone())
		{
			if (!Record->PlannedEdges.IsEmpty())
			{
				Record->State.NextEdgeId = Record->PlannedEdges[0];
			}
			else
			{
				Record->State.NextEdgeId = ChooseNextEdge(*Record);
			}
		}

		const double EdgeLimitCmPerSec = FMath::Clamp(Edge->Definition.SpeedLimitCmPerSecond, 200.0, 1400.0);
		double DesiredSpeed = EdgeLimitCmPerSec;
		Record->State.bYieldingForRightOfWay = false;
		Record->State.bYieldingForPrioritySign = false;
		Record->State.bStoppingForStopSign = false;
		Record->State.bYieldingForVehicle = false;
		Record->State.bYieldingForPedestrian = false;
		Record->State.bYieldingForCrossing = false;

		const double RemainingOnEdge = Edge->LengthCm - Record->State.DistanceOnEdgeCm;
		const FVector MyForward = Record->State.WorldRotation.Vector().GetSafeNormal2D();
		const FVector MyRight(-MyForward.Y, MyForward.X, 0.0);

		// 1. Pedestrian & Player yielding (direct path + occupied crossings)
		for (const FVector& PedPos : PedestrianLocations)
		{
			const FVector Delta = PedPos - Record->State.WorldLocation;
			const double FwdDist = FVector::DotProduct(Delta, MyForward);
			const double LatDist = FMath::Abs(FVector::DotProduct(Delta, MyRight));
			if (FwdDist > -50.0 && FwdDist < PedestrianStopDistCm && LatDist < PedestrianLateralCm)
			{
				DesiredSpeed = 0.0;
				Record->State.bYieldingForPedestrian = true;
				break;
			}
		}
		for (const FVector& CrossingLoc : OccupiedCrossings)
		{
			const FVector Delta = CrossingLoc - Record->State.WorldLocation;
			const double FwdDist = FVector::DotProduct(Delta, MyForward);
			const double LatDist = FMath::Abs(FVector::DotProduct(Delta, MyRight));
			if (FwdDist > 0.0 && FwdDist < CrossingApproachDistCm && LatDist < CrossingLateralCm)
			{
				const double StopDist = FMath::Max(0.0, FwdDist - CrossingStopMarginCm);
				if (StopDist <= 30.0)
				{
					DesiredSpeed = 0.0;
				}
				else
				{
					DesiredSpeed = FMath::Min(DesiredSpeed, FMath::Sqrt(2.0 * VehicleDecelCmPerSecSq * StopDist));
				}
				Record->State.bYieldingForPedestrian = true;
				Record->State.bYieldingForCrossing = true;
			}
		}

		// 2. Car-following distance & 2D anti-penetration against active (non-parked) vehicles
		for (FName OtherId : OrderedVehicleIds)
		{
			if (OtherId == VehicleId)
			{
				continue;
			}
			const FVehicleRecord* Other = VehicleRecords.Find(OtherId);
			if (!Other || Other->State.Phase == EDoemitzVehiclePhase::Parked || Other->State.Phase == EDoemitzVehiclePhase::Parking)
			{
				continue;
			}

			if (Other->State.Phase == EDoemitzVehiclePhase::Driving &&
				Other->State.CurrentEdgeId == Record->State.CurrentEdgeId &&
				Other->State.DistanceOnEdgeCm > Record->State.DistanceOnEdgeCm)
			{
				const double Gap = Other->State.DistanceOnEdgeCm - Record->State.DistanceOnEdgeCm;
				if (Gap <= MinCenterSpacingCm)
				{
					DesiredSpeed = 0.0;
					Record->State.bYieldingForVehicle = true;
				}
				else if (Gap < FollowBrakeStartCm)
				{
					const double Factor = (Gap - MinCenterSpacingCm) / (FollowBrakeStartCm - MinCenterSpacingCm);
					DesiredSpeed = FMath::Min(DesiredSpeed, EdgeLimitCmPerSec * Factor);
					Record->State.bYieldingForVehicle = true;
				}
			}
			else if (Other->State.Phase == EDoemitzVehiclePhase::Driving &&
				!Record->State.NextEdgeId.IsNone() &&
				Other->State.CurrentEdgeId == Record->State.NextEdgeId)
			{
				const double Gap = RemainingOnEdge + Other->State.DistanceOnEdgeCm;
				if (Gap <= MinCenterSpacingCm)
				{
					DesiredSpeed = 0.0;
					Record->State.bYieldingForVehicle = true;
				}
				else if (Gap < FollowBrakeStartCm)
				{
					const double Factor = (Gap - MinCenterSpacingCm) / (FollowBrakeStartCm - MinCenterSpacingCm);
					DesiredSpeed = FMath::Min(DesiredSpeed, EdgeLimitCmPerSec * Factor);
					Record->State.bYieldingForVehicle = true;
				}
			}

			const FVector Delta = Other->State.WorldLocation - Record->State.WorldLocation;
			const double FwdDist = FVector::DotProduct(Delta, MyForward);
			const double LatDist = FMath::Abs(FVector::DotProduct(Delta, MyRight));
			if (FwdDist > 0.0 && FwdDist < MinCenterSpacingCm && LatDist < 220.0)
			{
				DesiredSpeed = 0.0;
				Record->State.bYieldingForVehicle = true;
			}
		}

		// 3. Priority signs (give_way / stop) overriding Right-before-Left (Rechts vor links) & junction reservation
		const FName ApproachNode = Edge->Definition.ToNodeId;
		if (RemainingOnEdge <= JunctionApproachCm && !ApproachNode.IsNone())
		{
			const bool bMeStopSign = (Edge->Definition.YieldRule == EDoemitzYieldRule::Stop);
			const bool bMeYieldSign = (Edge->Definition.YieldRule != EDoemitzYieldRule::None);

			// Full stop requirement for highway=stop before entering junction
			bool bNeedsMandatoryStop = false;
			if (bMeStopSign && !Record->bCompletedStopAtEdge)
			{
				bNeedsMandatoryStop = true;
				Record->State.bStoppingForStopSign = true;
				Record->State.bYieldingForPrioritySign = true;
				Record->State.bYieldingForRightOfWay = true;
				if (RemainingOnEdge <= JunctionStopLineCm + 90.0 && Record->State.CurrentSpeedCmPerSecond <= 15.0)
				{
					Record->StopHoldElapsedSeconds += DeltaSeconds;
					if (Record->StopHoldElapsedSeconds >= StopSignHoldSeconds)
					{
						Record->bCompletedStopAtEdge = true;
						bNeedsMandatoryStop = false;
						Record->State.bStoppingForStopSign = false;
					}
				}
			}

			const FName* CurrentHolder = JunctionReservations.Find(ApproachNode);
			bool bCanProceed = !bNeedsMandatoryStop && (CurrentHolder != nullptr && *CurrentHolder == VehicleId);

			if (!bNeedsMandatoryStop && !bCanProceed)
			{
				if (CurrentHolder != nullptr && *CurrentHolder != VehicleId)
				{
					Record->State.bYieldingForRightOfWay = true;
					if (bMeYieldSign)
					{
						Record->State.bYieldingForPrioritySign = true;
					}
				}
				else
				{
					bool bMustYieldRightOfWay = false;
					bool bYieldDueToSign = false;
					const FVector2D MyInDir = Edge->EndDir2D;
					const FVector2D MyRight2D(-MyInDir.Y, MyInDir.X);

					for (FName OtherId : OrderedVehicleIds)
					{
						if (OtherId == VehicleId)
						{
							continue;
						}
						const FVehicleRecord* Other = VehicleRecords.Find(OtherId);
						if (!Other || Other->State.Phase != EDoemitzVehiclePhase::Driving)
						{
							continue;
						}
						const FRoadEdgeRecord* OtherEdge = RoadEdgesById.Find(Other->State.CurrentEdgeId);
						if (!OtherEdge || OtherEdge->Definition.ToNodeId != ApproachNode)
						{
							continue;
						}
						const double OtherRemaining = OtherEdge->LengthCm - Other->State.DistanceOnEdgeCm;
						if (OtherRemaining > JunctionApproachCm)
						{
							continue;
						}

						const bool bOtherYieldSign = (OtherEdge->Definition.YieldRule != EDoemitzYieldRule::None);
						// Priority sign overrides Rechts vor links
						if (bMeYieldSign && !bOtherYieldSign)
						{
							bMustYieldRightOfWay = true;
							bYieldDueToSign = true;
							break;
						}
						if (!bMeYieldSign && bOtherYieldSign)
						{
							// I have priority over the yielding vehicle even if it approaches from my right
							continue;
						}

						// Neither or both have a sign: standard Rechts vor links
						const FVector2D OtherInDir = OtherEdge->EndDir2D;
						const FVector2D OtherRight2D(-OtherInDir.Y, OtherInDir.X);
						const bool bOtherFromMyRight = FVector2D::DotProduct(-OtherInDir, MyRight2D) > 0.35;
						const bool bMeFromOtherRight = FVector2D::DotProduct(-MyInDir, OtherRight2D) > 0.35;

						if (bOtherFromMyRight && !bMeFromOtherRight)
						{
							bMustYieldRightOfWay = true;
							break;
						}
						if (bOtherFromMyRight == bMeFromOtherRight)
						{
							if (OtherRemaining + 100.0 < RemainingOnEdge ||
								(FMath::Abs(OtherRemaining - RemainingOnEdge) <= 100.0 && OtherId.LexicalLess(VehicleId)))
							{
								bMustYieldRightOfWay = true;
								break;
							}
						}
					}

					if (bMustYieldRightOfWay)
					{
						Record->State.bYieldingForRightOfWay = true;
						Record->State.bYieldingForPrioritySign = bYieldDueToSign;
					}
					else
					{
						ReleaseJunctionReservation(*Record);
						JunctionReservations.Add(ApproachNode, VehicleId);
						Record->ReservedNodeId = ApproachNode;
						bCanProceed = true;
					}
				}
			}

			if (!bCanProceed)
			{
				const double StopDist = FMath::Max(0.0, RemainingOnEdge - JunctionStopLineCm);
				if (StopDist <= 25.0)
				{
					DesiredSpeed = 0.0;
				}
				else
				{
					DesiredSpeed = FMath::Min(DesiredSpeed, FMath::Sqrt(2.0 * VehicleDecelCmPerSecSq * StopDist));
				}
			}
		}

		// 4. Smooth acceleration / braking integration
		if (DesiredSpeed > Record->State.CurrentSpeedCmPerSecond)
		{
			Record->State.CurrentSpeedCmPerSecond = FMath::Min(
				DesiredSpeed,
				Record->State.CurrentSpeedCmPerSecond + VehicleAccelCmPerSecSq * DeltaSeconds);
		}
		else
		{
			Record->State.CurrentSpeedCmPerSecond = FMath::Max(
				DesiredSpeed,
				Record->State.CurrentSpeedCmPerSecond - VehicleDecelCmPerSecSq * DeltaSeconds);
		}

		double StepDist = Record->State.CurrentSpeedCmPerSecond * DeltaSeconds;
		if (Record->State.bYieldingForRightOfWay || Record->State.bYieldingForVehicle || Record->State.bYieldingForPedestrian)
		{
			if (DesiredSpeed <= 1.0)
			{
				StepDist = 0.0;
				Record->State.CurrentSpeedCmPerSecond = 0.0;
			}
		}

		// Advance along current edge and transition through junctions
		Record->State.DistanceOnEdgeCm += StepDist;
		while (Edge && Record->State.DistanceOnEdgeCm >= Edge->LengthCm)
		{
			const double Overflow = Record->State.DistanceOnEdgeCm - Edge->LengthCm;
			FName ChosenNext = Record->State.NextEdgeId;
			if (ChosenNext.IsNone())
			{
				ChosenNext = ChooseNextEdge(*Record);
			}
			const FRoadEdgeRecord* NextEdge = RoadEdgesById.Find(ChosenNext);
			if (!NextEdge)
			{
				Record->State.DistanceOnEdgeCm = FMath::Max(0.0, Edge->LengthCm - 1.0);
				Record->State.CurrentSpeedCmPerSecond = 0.0;
				break;
			}

			Record->State.CurrentEdgeId = ChosenNext;
			Record->State.DistanceOnEdgeCm = Overflow;
			Record->State.JunctionDecisions += 1;
			Record->bCompletedStopAtEdge = false;
			Record->StopHoldElapsedSeconds = 0.0;
			Edge = NextEdge;

			if (!Record->PlannedEdges.IsEmpty() && Record->PlannedEdges[0] == ChosenNext)
			{
				Record->PlannedEdges.RemoveAt(0);
			}
			if (!Record->PlannedEdges.IsEmpty())
			{
				Record->State.NextEdgeId = Record->PlannedEdges[0];
			}
			else
			{
				Record->State.NextEdgeId = ChooseNextEdge(*Record);
			}
		}

		if (Edge)
		{
			SampleEdgePose(*Edge, Record->State.DistanceOnEdgeCm, Record->State.WorldLocation, Record->State.WorldRotation);
		}
	}
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

	if (!Record.State.bIsMoving)
	{
		Record.State.CurrentActivity = DesiredEntry.Activity;
		if (DesiredEntry.Activity == EDoemitzCitizenActivity::Shopping)
		{
			RecordCitizenShoppingRevenue(Record.State.CitizenId, Record.State.CurrentPlaceId);
		}
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
		if (DesiredEntry.Activity == EDoemitzCitizenActivity::Shopping)
		{
			RecordCitizenShoppingRevenue(Record.State.CitizenId, Record.State.CurrentPlaceId);
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
			LastNotificationEvent = FDoemitzNotificationEvent();
		}
	}

	if (TimeScale <= 0.0)
	{
		return;
	}

	const double ClampedDelta = FMath::Min(static_cast<double>(DeltaTime), 0.1);
	const double SimMinutesDelta = (static_cast<double>(DeltaTime) * TimeScale) / 60.0;
	TimeOfDayMinutes += SimMinutesDelta;
	bool bDayRolledOver = false;
	while (TimeOfDayMinutes >= 1440.0)
	{
		TimeOfDayMinutes -= 1440.0;
		DayNumber += 1;
		DayOfWeek = (DayOfWeek + 1) % 7;
		bDayRolledOver = true;
		CitizenDailyShoppingRecorded.Reset();
		for (TPair<FName, FDoemitzPlaceRevenue>& Pair : PlaceRevenues)
		{
			Pair.Value.DailyRevenueCents = 0;
			if (DayOfWeek == 0)
			{
				Pair.Value.WeeklyRevenueCents = 0;
			}
		}
		if (DayOfWeek == 0)
		{
			CalendarWeek += 1;
		}
		if (bIsWorkingShift)
		{
			FinishWorkShift();
		}
	}

	CheckTaskDeadlines();
	if (bDayRolledOver)
	{
		GenerateDailyTasks();
	}

	UpdateActiveWorkShift();
	UpdateCitizenLodPool();

	for (TPair<FName, FCitizenRecord>& Pair : CitizenRecords)
	{
		FCitizenRecord& Record = Pair.Value;
		if (Record.State.bIsHighDetail)
		{
			UpdateCitizen(Record, ClampedDelta);
		}
		else
		{
			Record.CoarseAccumulatedSeconds += ClampedDelta;
			if (Record.CoarseAccumulatedSeconds >= CoarseUpdateIntervalSeconds)
			{
				const double Step = Record.CoarseAccumulatedSeconds;
				Record.CoarseAccumulatedSeconds = 0.0;
				UpdateCitizen(Record, Step);
			}
		}
	}

	UpdateTraffic(ClampedDelta);
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

// ============================================================================
// SaveGame v5 + Migration v1..v4 (Milestone 8)
// ============================================================================

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

	SaveObj->SaveSchemaVersion = UDoemitzSaveGame::CurrentSchemaVersion;
	SaveObj->DayNumber = DayNumber;
	SaveObj->DayOfWeek = DayOfWeek;
	SaveObj->CalendarWeek = CalendarWeek;
	SaveObj->TimeOfDayMinutes = TimeOfDayMinutes;
	SaveObj->TimeScale = bIsWorkingShift ? PreShiftTimeScale : TimeScale;
	SaveObj->PlayerMoneyCents = PlayerMoneyCents;
	SaveObj->NextTransactionId = NextTransactionId;
	SaveObj->ActiveJobId = ActiveJobId;
	SaveObj->LedgerEntries = LedgerEntries;
	SaveObj->InventoryItems = GetAllInventoryItems();
	SaveObj->Tasks = Tasks;
	for (const TPair<FName, FDoemitzPlaceRevenue>& Pair : PlaceRevenues)
	{
		SaveObj->PlaceRevenues.Add(Pair.Value);
	}
	for (FName LotId : OrderedParkingLotIds)
	{
		if (const FParkingLotRecord* Lot = ParkingLotsById.Find(LotId))
		{
			FDoemitzSavedParkingOccupancy Occ;
			Occ.ParkingLotId = LotId;
			Occ.SlotOccupants = Lot->SlotOccupants;
			SaveObj->ParkingOccupancy.Add(MoveTemp(Occ));
		}
	}

	if (UWorld* World = GetWorld())
	{
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			if (APawn* Pawn = PC->GetPawn())
			{
				SaveObj->bHasPlayerTransform = true;
				SaveObj->PlayerLocation = Pawn->GetActorLocation();
				SaveObj->PlayerRotation = Pawn->GetActorRotation();
				SaveObj->PlayerInteriorId = FindInteriorAtLocation(Pawn->GetActorLocation());
				if (const FDoemitzInteriorDefinition* Interior = InteriorsById.Find(SaveObj->PlayerInteriorId))
				{
					SaveObj->PlayerInteriorPlaceId = Interior->PlaceId;
				}
			}
		}
	}

	if (!VehicleRecords.IsEmpty())
	{
		for (FName VehicleId : OrderedVehicleIds)
		{
			if (const FVehicleRecord* Rec = VehicleRecords.Find(VehicleId))
			{
				FDoemitzSavedVehicle SavedVehicle;
				SavedVehicle.VehicleId = Rec->State.VehicleId;
				SavedVehicle.EdgeId = Rec->State.CurrentEdgeId;
				SavedVehicle.DistanceCm = Rec->State.DistanceOnEdgeCm;
				SavedVehicle.SpeedCmPerSecond = Rec->State.CurrentSpeedCmPerSecond;
				SavedVehicle.JunctionDecisions = Rec->State.JunctionDecisions;
				SavedVehicle.WorldLocation = Rec->State.WorldLocation;
				SavedVehicle.Phase = Rec->State.Phase;
				SavedVehicle.TargetParkingLotId = Rec->State.TargetParkingLotId;
				SavedVehicle.CurrentParkingLotId = Rec->State.CurrentParkingLotId;
				SavedVehicle.ParkingSlotIndex = Rec->State.ParkingSlotIndex;
				SavedVehicle.RemainingParkSeconds = Rec->State.RemainingParkSeconds;
				SavedVehicle.TripCounter = Rec->TripCounter;
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
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::SaveSucceeded;
		Ev.ParameterKey = SlotName;
		PushNotificationEvent(Ev);
		UE_LOG(LogTemp, Display, TEXT("Doemitz save v%d written to slot '%s' (Day %d, %.1f min, %d citizens, %d vehicles, %d tasks)"),
			SaveObj->SaveSchemaVersion, *SlotName, DayNumber, TimeOfDayMinutes, SaveObj->Citizens.Num(), SaveObj->Vehicles.Num(), SaveObj->Tasks.Num());
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
	if (!SaveObj || SaveObj->SaveSchemaVersion < 1 || SaveObj->SaveSchemaVersion > UDoemitzSaveGame::CurrentSchemaVersion)
	{
		return false;
	}

	const bool bMigratingFromV1 = (SaveObj->SaveSchemaVersion == 1);
	const bool bMigratingFromPreV3 = (SaveObj->SaveSchemaVersion < 3);
	const bool bMigratingFromPreV4 = (SaveObj->SaveSchemaVersion < 4);
	const bool bMigratingFromPreV5 = (SaveObj->SaveSchemaVersion < 5);
	const bool bMigratingFromPreV6 = (SaveObj->SaveSchemaVersion < 6);

	if (bIsWorkingShift)
	{
		bIsWorkingShift = false;
		ActiveShiftPlaceId = NAME_None;
		if (UWorld* World = GetWorld())
		{
			if (APlayerController* PC = World->GetFirstPlayerController())
			{
				PC->SetIgnoreMoveInput(false);
				if (APawn* Pawn = PC->GetPawn())
				{
					Pawn->SetActorHiddenInGame(false);
				}
			}
		}
	}

	DayNumber = FMath::Max(1, SaveObj->DayNumber);
	if (bMigratingFromPreV3)
	{
		DayOfWeek = 0;
		CalendarWeek = 1 + ((DayNumber - 1) / 7);
	}
	else
	{
		DayOfWeek = ((SaveObj->DayOfWeek % 7) + 7) % 7;
		CalendarWeek = FMath::Max(1, SaveObj->CalendarWeek);
	}
	TimeOfDayMinutes = FMath::Fmod(FMath::Max(0.0, SaveObj->TimeOfDayMinutes), 1440.0);
	TimeScale = FMath::Clamp(SaveObj->TimeScale, 0.0, 3600.0);

	if (bMigratingFromPreV4)
	{
		ResetEconomyToDefaults();
	}
	else
	{
		PlayerMoneyCents = FMath::Max<int64>(0, SaveObj->PlayerMoneyCents);
		NextTransactionId = FMath::Max(1, SaveObj->NextTransactionId);
		ActiveJobId = SaveObj->ActiveJobId;
		LedgerEntries = SaveObj->LedgerEntries;
		if (LedgerEntries.Num() > MaxLedgerEntries)
		{
			LedgerEntries.RemoveAt(0, LedgerEntries.Num() - MaxLedgerEntries);
		}
		PlayerInventory.Reset();
		for (const FDoemitzInventoryItem& Item : SaveObj->InventoryItems)
		{
			if (!Item.ItemId.IsNone() && Item.Quantity > 0)
			{
				PlayerInventory.Add(Item.ItemId, Item.Quantity);
			}
		}
		PlaceRevenues.Reset();
		for (const FDoemitzPlaceRevenue& Rev : SaveObj->PlaceRevenues)
		{
			if (!Rev.PlaceId.IsNone())
			{
				PlaceRevenues.Add(Rev.PlaceId, Rev);
			}
		}
		CitizenDailyShoppingRecorded.Reset();
	}

	// Tasks (v5+; v1..v4 migration leaves tasks empty)
	if (bMigratingFromPreV5)
	{
		Tasks.Reset();
	}
	else
	{
		Tasks = SaveObj->Tasks;
	}

	UWorld* LoadWorld = GetWorld();
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
				if (TraceStaticGroundZ(LoadWorld, RestoredLoc.X, RestoredLoc.Y, RestoredLoc.Z, GroundZ))
				{
					RestoredLoc.Z = GroundZ;
				}
				else if (const FDoemitzPlaceDefinition* Place = PlacesById.Find(Saved.CurrentPlaceId))
				{
					RestoredLoc.Z = Place->AccessLocation.Z;
				}
			}
			else if (TraceStaticGroundZ(LoadWorld, RestoredLoc.X, RestoredLoc.Y, RestoredLoc.Z, GroundZ) && GroundZ > RestoredLoc.Z + 25.0)
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

	// Clear parking occupancy before restoring vehicles
	for (TPair<FName, FParkingLotRecord>& LotPair : ParkingLotsById)
	{
		for (FName& Occ : LotPair.Value.SlotOccupants)
		{
			Occ = NAME_None;
		}
	}

	JunctionReservations.Reset();
	if (!VehicleRecords.IsEmpty())
	{
		for (TPair<FName, FVehicleRecord>& Pair : VehicleRecords)
		{
			Pair.Value.ReservedNodeId = NAME_None;
			Pair.Value.PlannedEdges.Reset();
			Pair.Value.bCompletedStopAtEdge = false;
			Pair.Value.StopHoldElapsedSeconds = 0.0;
		}

		TMap<FName, FDoemitzSavedVehicle> SavedVehiclesById;
		for (const FDoemitzSavedVehicle& SavedVehicle : SaveObj->Vehicles)
		{
			SavedVehiclesById.Add(SavedVehicle.VehicleId, SavedVehicle);
		}

		for (FName VehicleId : OrderedVehicleIds)
		{
			FVehicleRecord* Rec = VehicleRecords.Find(VehicleId);
			if (!Rec)
			{
				continue;
			}

			const FDoemitzSavedVehicle* Saved = SavedVehiclesById.Find(VehicleId);
			if (!Saved && bMigratingFromV1 && VehicleId == FName(TEXT("altstadt_vehicle_01")))
			{
				Saved = SavedVehiclesById.Find(FName(TEXT("altstadt_compact_01")));
			}
			if (!Saved)
			{
				// Newly added vehicles (e.g. v4 had 5 vehicles -> v5 has 8) start driving cleanly
				Rec->State.Phase = EDoemitzVehiclePhase::Driving;
				Rec->State.CurrentParkingLotId = NAME_None;
				Rec->State.ParkingSlotIndex = -1;
				Rec->State.RemainingParkSeconds = 0.0;
				if (!OrderedParkingLotIds.IsEmpty())
				{
					PlanRouteToParking(*Rec, ChooseNextParkingLot(*Rec, NAME_None));
				}
				continue;
			}

			FName TargetEdgeId = Saved->EdgeId;
			double TargetDistCm = Saved->DistanceCm;
			if (bMigratingFromV1 || TargetEdgeId.IsNone() || !RoadEdgesById.Contains(TargetEdgeId))
			{
				if (!Saved->WorldLocation.IsNearlyZero())
				{
					TargetEdgeId = FindNearestDrivableEdge(Saved->WorldLocation, TargetDistCm);
				}
				if (TargetEdgeId.IsNone() || !RoadEdgesById.Contains(TargetEdgeId))
				{
					TargetEdgeId = Rec->Definition.StartEdgeId;
					if (const FRoadEdgeRecord* FallbackEdge = RoadEdgesById.Find(TargetEdgeId))
					{
						TargetDistCm = FMath::Fmod(FMath::Max(0.0, Saved->DistanceCm), FMath::Max(1.0, FallbackEdge->LengthCm));
					}
				}
			}

			if (const FRoadEdgeRecord* Edge = RoadEdgesById.Find(TargetEdgeId))
			{
				Rec->State.CurrentEdgeId = TargetEdgeId;
				Rec->State.DistanceOnEdgeCm = FMath::Clamp(TargetDistCm, 0.0, FMath::Max(0.0, Edge->LengthCm - 1.0));
				Rec->State.CurrentSpeedCmPerSecond = Saved->SpeedCmPerSecond > 0.0
					? Saved->SpeedCmPerSecond
					: FMath::Min(500.0, Edge->Definition.SpeedLimitCmPerSecond);
				Rec->State.JunctionDecisions = FMath::Max(0, Saved->JunctionDecisions);

				if (bMigratingFromPreV5)
				{
					Rec->State.Phase = EDoemitzVehiclePhase::Driving;
					Rec->State.CurrentParkingLotId = NAME_None;
					Rec->State.ParkingSlotIndex = -1;
					Rec->State.RemainingParkSeconds = 0.0;
					Rec->TripCounter = 0;
					SampleEdgePose(*Edge, Rec->State.DistanceOnEdgeCm, Rec->State.WorldLocation, Rec->State.WorldRotation);
					if (!OrderedParkingLotIds.IsEmpty())
					{
						PlanRouteToParking(*Rec, ChooseNextParkingLot(*Rec, NAME_None));
					}
					else
					{
						Rec->State.NextEdgeId = ChooseNextEdge(*Rec);
					}
				}
				else
				{
					Rec->TripCounter = FMath::Max(0, Saved->TripCounter);
					Rec->State.Phase = Saved->Phase;
					Rec->State.TargetParkingLotId = Saved->TargetParkingLotId;
					Rec->State.CurrentParkingLotId = Saved->CurrentParkingLotId;
					Rec->State.ParkingSlotIndex = Saved->ParkingSlotIndex;
					Rec->State.RemainingParkSeconds = FMath::Max(0.0, Saved->RemainingParkSeconds);

					if (Rec->State.Phase == EDoemitzVehiclePhase::Parked || Rec->State.Phase == EDoemitzVehiclePhase::Parking)
					{
						if (FParkingLotRecord* Lot = ParkingLotsById.Find(Rec->State.CurrentParkingLotId))
						{
							const int32 Idx = FMath::Clamp(Rec->State.ParkingSlotIndex, 0, Lot->SlotOccupants.Num() - 1);
							Lot->SlotOccupants[Idx] = VehicleId;
							Rec->State.ParkingSlotIndex = Idx;
							Rec->State.Phase = EDoemitzVehiclePhase::Parked;
							Rec->State.CurrentSpeedCmPerSecond = 0.0;
							Rec->State.WorldLocation = Lot->Definition.SlotLocations.IsValidIndex(Idx)
								? Lot->Definition.SlotLocations[Idx]
								: Lot->Definition.Location;
						}
						else
						{
							Rec->State.Phase = EDoemitzVehiclePhase::Driving;
							SampleEdgePose(*Edge, Rec->State.DistanceOnEdgeCm, Rec->State.WorldLocation, Rec->State.WorldRotation);
						}
					}
					else
					{
						Rec->State.Phase = EDoemitzVehiclePhase::Driving;
						Rec->State.CurrentParkingLotId = NAME_None;
						Rec->State.ParkingSlotIndex = -1;
						SampleEdgePose(*Edge, Rec->State.DistanceOnEdgeCm, Rec->State.WorldLocation, Rec->State.WorldRotation);
						if (!Rec->State.TargetParkingLotId.IsNone() && ParkingLotsById.Contains(Rec->State.TargetParkingLotId))
						{
							PlanRouteToParking(*Rec, Rec->State.TargetParkingLotId);
						}
						else if (!OrderedParkingLotIds.IsEmpty())
						{
							PlanRouteToParking(*Rec, ChooseNextParkingLot(*Rec, NAME_None));
						}
						else
						{
							Rec->State.NextEdgeId = ChooseNextEdge(*Rec);
						}
					}
				}
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
					FVector RestoredPlayerLoc = SaveObj->PlayerLocation;
					double GroundZ = RestoredPlayerLoc.Z;
					double HalfHeight = 96.0;
					if (const ACharacter* Char = Cast<ACharacter>(Pawn))
					{
						if (const UCapsuleComponent* Cap = Char->GetCapsuleComponent())
						{
							HalfHeight = Cap->GetScaledCapsuleHalfHeight() + 4.0;
						}
					}
					LastLoadedPlayerInteriorId = NAME_None;
					const FDoemitzInteriorDefinition* SavedInterior = SaveObj->SaveSchemaVersion >= 7 && !SaveObj->PlayerInteriorId.IsNone()
						? InteriorsById.Find(SaveObj->PlayerInteriorId)
						: nullptr;
					if (SaveObj->SaveSchemaVersion >= 7 && !SaveObj->PlayerInteriorId.IsNone() && !SavedInterior)
					{
						// The interior was removed from the configuration: put the player at that place's entrance.
						if (const FDoemitzPlaceDefinition* Place = PlacesById.Find(SaveObj->PlayerInteriorPlaceId))
						{
							RestoredPlayerLoc = !Place->EntranceLocation.IsNearlyZero() ? Place->EntranceLocation : Place->AccessLocation;
						}
						if (TraceStaticGroundZ(World, RestoredPlayerLoc.X, RestoredPlayerLoc.Y, RestoredPlayerLoc.Z, GroundZ))
						{
							RestoredPlayerLoc.Z = GroundZ + HalfHeight;
						}
					}
					else if (SavedInterior)
					{
						// Trace from just under the ceiling so the floor, not the upper storey or roof, is found.
						RestoredPlayerLoc.Z = FMath::Max(SavedInterior->FloorZ + HalfHeight, FMath::Min(RestoredPlayerLoc.Z, SavedInterior->CeilingZ - 20.0));
						FHitResult FloorHit;
						FCollisionQueryParams FloorParams(SCENE_QUERY_STAT(DoemitzInteriorLoadTrace), false, Pawn);
						if (World->LineTraceSingleByChannel(
							FloorHit,
							FVector(RestoredPlayerLoc.X, RestoredPlayerLoc.Y, SavedInterior->CeilingZ - 15.0),
							FVector(RestoredPlayerLoc.X, RestoredPlayerLoc.Y, SavedInterior->FloorZ - 100.0),
							ECC_Visibility,
							FloorParams) && FloorHit.ImpactNormal.Z > 0.5f)
						{
							RestoredPlayerLoc.Z = FloorHit.ImpactPoint.Z + HalfHeight;
						}
						else
						{
							RestoredPlayerLoc.Z = SavedInterior->FloorZ + HalfHeight;
						}
						LastLoadedPlayerInteriorId = SaveObj->PlayerInteriorId;
					}
					else if (bMigratingFromPreV6)
					{
						if (TraceStaticGroundZ(World, RestoredPlayerLoc.X, RestoredPlayerLoc.Y, RestoredPlayerLoc.Z, GroundZ))
						{
							RestoredPlayerLoc.Z = GroundZ + HalfHeight;
						}
					}
					else if (TraceStaticGroundZ(World, RestoredPlayerLoc.X, RestoredPlayerLoc.Y, RestoredPlayerLoc.Z, GroundZ) && GroundZ > RestoredPlayerLoc.Z + 25.0)
					{
						// Guard against pre-11.1 saves whose player position lay below a bridge deck
						RestoredPlayerLoc.Z = GroundZ + HalfHeight;
					}
					Pawn->SetActorLocationAndRotation(RestoredPlayerLoc, SaveObj->PlayerRotation, false, nullptr, ETeleportType::TeleportPhysics);
				}
			}
		}

		for (TActorIterator<ADoemitzTrafficVehicle> It(World); It; ++It)
		{
			if (ADoemitzTrafficVehicle* Vehicle = *It)
			{
				Vehicle->SyncFromSimulation();
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

	UpdateCitizenLodPool();
	for (TPair<FName, TObjectPtr<ADoemitzCitizenActor>>& Pair : ActiveCitizenActors)
	{
		if (IsValid(Pair.Value.Get()))
		{
			Pair.Value->SyncFromSimulation();
		}
	}

	if (bMigratingFromPreV6)
	{
		UE_LOG(LogTemp, Display, TEXT("Migrated SaveGame v%d -> v%d (terrain height migration) for slot '%s'"),
			SaveObj->SaveSchemaVersion, UDoemitzSaveGame::CurrentSchemaVersion, *SlotName);
	}

	FDoemitzNotificationEvent Ev;
	Ev.Code = EDoemitzNotificationCode::LoadSucceeded;
	Ev.ParameterKey = SlotName;
	PushNotificationEvent(Ev);
	UE_LOG(LogTemp, Display, TEXT("Doemitz save v%d loaded from slot '%s' (Day %d, dow %d, KW %d, %.1f min, %d tasks)"),
		SaveObj->SaveSchemaVersion, *SlotName, DayNumber, DayOfWeek, CalendarWeek, TimeOfDayMinutes, Tasks.Num());
	return true;
}
