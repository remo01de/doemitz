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

namespace
{
	constexpr double VehicleLengthCm = 390.0;
	constexpr double MinCenterSpacingCm = 680.0;
	constexpr double FollowBrakeStartCm = 1250.0;
	constexpr double JunctionApproachCm = 950.0;
	constexpr double JunctionStopLineCm = 420.0;
	constexpr double JunctionClearanceCm = 550.0;
	constexpr double PedestrianStopDistCm = 620.0;
	constexpr double PedestrianLateralCm = 185.0;
	constexpr double VehicleAccelCmPerSecSq = 260.0;
	constexpr double VehicleDecelCmPerSecSq = 550.0;

	uint32 DeterministicHash(int32 Seed, FName VehicleId, int32 DecisionIndex)
	{
		uint32 H = static_cast<uint32>(Seed) * 2654435761u;
		const FString Str = VehicleId.ToString();
		for (TCHAR Ch : Str)
		{
			H = (H ^ static_cast<uint32>(Ch)) * 16777619u;
		}
		H = (H ^ static_cast<uint32>(DecisionIndex * 73856093)) * 2246822519u;
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

	bIsConfigured = CitizenRecords.Num() > 0 || VehicleRecords.Num() > 0;
	UE_LOG(LogTemp, Display, TEXT("Doemitz simulation started at %.1f min (scale %.1fx): %d places, %d routes, %d citizens"),
		TimeOfDayMinutes, TimeScale, PlacesById.Num(), RoutesByKey.Num(), CitizenRecords.Num());
}

void UDoemitzSimulationSubsystem::ConfigureTrafficNetwork(
	int32 InTrafficSeed,
	const TArray<FDoemitzRoadEdgeDefinition>& InRoadEdges,
	const TArray<FDoemitzVehicleDefinition>& InVehicles)
{
	TrafficSeed = InTrafficSeed;
	RoadEdgesById.Reset();
	OutgoingEdgesByNode.Reset();
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
		Rec.State.CurrentEdgeId = Def.StartEdgeId;
		Rec.State.DistanceOnEdgeCm = FMath::Clamp(Def.StartDistanceCm, 0.0, FMath::Max(0.0, Edge->LengthCm - 1.0));
		Rec.State.CurrentSpeedCmPerSecond = FMath::Min(500.0, Edge->Definition.SpeedLimitCmPerSecond);
		SampleEdgePose(*Edge, Rec.State.DistanceOnEdgeCm, Rec.State.WorldLocation, Rec.State.WorldRotation);
		Rec.State.NextEdgeId = ChooseNextEdge(Rec);

		VehicleRecords.Add(Def.VehicleId, MoveTemp(Rec));
		OrderedVehicleIds.Add(Def.VehicleId);
	}

	OrderedVehicleIds.Sort(FNameLexicalLess());
	bIsConfigured = CitizenRecords.Num() > 0 || VehicleRecords.Num() > 0;
	UE_LOG(LogTemp, Display, TEXT("Doemitz traffic network configured: seed=%d, %d edges, %d vehicles"),
		TrafficSeed, RoadEdgesById.Num(), VehicleRecords.Num());
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
	Record->State.CurrentEdgeId = EdgeId;
	Record->State.DistanceOnEdgeCm = FMath::Clamp(DistanceOnEdgeCm, 0.0, FMath::Max(0.0, Edge->LengthCm - 1.0));
	Record->State.CurrentSpeedCmPerSecond = FMath::Max(0.0, SpeedCmPerSecond);
	Record->State.NextEdgeId = ChooseNextEdge(*Record);
	SampleEdgePose(*Edge, Record->State.DistanceOnEdgeCm, Record->State.WorldLocation, Record->State.WorldRotation);
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
		// Right-hand driving lane offset on two-way streets (UE: X=North, Y=East -> Right=(-Dir.Y, Dir.X))
		if (!Edge.Definition.bOneWay)
		{
			const double LaneOffset = FMath::Min(140.0, Edge.Definition.WidthCm * 0.22);
			Pos.X += -Dir.Y * LaneOffset;
			Pos.Y += Dir.X * LaneOffset;
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
		// Avoid immediate 180-degree U-turn back along the same road segment when alternatives exist
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

	// Gather player and citizen locations once per frame for pedestrian yielding
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

	for (FName VehicleId : OrderedVehicleIds)
	{
		FVehicleRecord* Record = VehicleRecords.Find(VehicleId);
		if (!Record)
		{
			continue;
		}
		const FRoadEdgeRecord* Edge = RoadEdgesById.Find(Record->State.CurrentEdgeId);
		if (!Edge)
		{
			continue;
		}

		// Release junction reservation once safely clear of the previous junction
		if (!Record->ReservedNodeId.IsNone() &&
			Record->ReservedNodeId == Edge->Definition.FromNodeId &&
			Record->State.DistanceOnEdgeCm >= JunctionClearanceCm)
		{
			ReleaseJunctionReservation(*Record);
		}

		if (Record->State.NextEdgeId.IsNone())
		{
			Record->State.NextEdgeId = ChooseNextEdge(*Record);
		}

		const double EdgeLimitCmPerSec = FMath::Clamp(Edge->Definition.SpeedLimitCmPerSecond, 200.0, 1400.0);
		double DesiredSpeed = EdgeLimitCmPerSec;
		Record->State.bYieldingForRightOfWay = false;
		Record->State.bYieldingForVehicle = false;
		Record->State.bYieldingForPedestrian = false;

		const double RemainingOnEdge = Edge->LengthCm - Record->State.DistanceOnEdgeCm;
		const FVector MyForward = Record->State.WorldRotation.Vector().GetSafeNormal2D();
		const FVector MyRight(-MyForward.Y, MyForward.X, 0.0);

		// 1. Pedestrian & Player yielding
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

		// 2. Car-following distance & 2D anti-penetration against all other vehicles
		for (FName OtherId : OrderedVehicleIds)
		{
			if (OtherId == VehicleId)
			{
				continue;
			}
			const FVehicleRecord* Other = VehicleRecords.Find(OtherId);
			if (!Other)
			{
				continue;
			}

			// Same-edge ahead check
			if (Other->State.CurrentEdgeId == Record->State.CurrentEdgeId &&
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
			// Next-edge entrance check (don't enter junction if target edge start is occupied)
			else if (!Record->State.NextEdgeId.IsNone() &&
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

			// General 2D forward clearance check to guarantee zero overlap at junctions or merges
			const FVector Delta = Other->State.WorldLocation - Record->State.WorldLocation;
			const double FwdDist = FVector::DotProduct(Delta, MyForward);
			const double LatDist = FMath::Abs(FVector::DotProduct(Delta, MyRight));
			if (FwdDist > 0.0 && FwdDist < MinCenterSpacingCm && LatDist < 220.0)
			{
				DesiredSpeed = 0.0;
				Record->State.bYieldingForVehicle = true;
			}
		}

		// 3. Right-before-left (Rechts vor links) & junction reservation
		const FName ApproachNode = Edge->Definition.ToNodeId;
		if (RemainingOnEdge <= JunctionApproachCm && !ApproachNode.IsNone())
		{
			const FName* CurrentHolder = JunctionReservations.Find(ApproachNode);
			bool bCanProceed = (CurrentHolder != nullptr && *CurrentHolder == VehicleId);

			if (!bCanProceed)
			{
				if (CurrentHolder != nullptr && *CurrentHolder != VehicleId)
				{
					Record->State.bYieldingForRightOfWay = true;
				}
				else
				{
					// Check other vehicles approaching the exact same junction node
					bool bMustYieldRightOfWay = false;
					const FVector2D MyInDir = Edge->EndDir2D;
					const FVector2D MyRight2D(-MyInDir.Y, MyInDir.X);

					for (FName OtherId : OrderedVehicleIds)
					{
						if (OtherId == VehicleId)
						{
							continue;
						}
						const FVehicleRecord* Other = VehicleRecords.Find(OtherId);
						if (!Other)
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
							// Symmetric conflict tie-breaker: closer vehicle wins, then deterministic ID order
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
			Edge = NextEdge;
			Record->State.NextEdgeId = ChooseNextEdge(*Record);
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

	const double ClampedDelta = FMath::Min(static_cast<double>(DeltaTime), 0.1);
	const double SimMinutesDelta = (static_cast<double>(DeltaTime) * TimeScale) / 60.0;
	TimeOfDayMinutes += SimMinutesDelta;
	while (TimeOfDayMinutes >= 1440.0)
	{
		TimeOfDayMinutes -= 1440.0;
		DayNumber += 1;
	}

	for (TPair<FName, FCitizenRecord>& Pair : CitizenRecords)
	{
		UpdateCitizen(Pair.Value, ClampedDelta);
	}

	UpdateTraffic(ClampedDelta);
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

	SaveObj->SaveSchemaVersion = UDoemitzSaveGame::CurrentSchemaVersion;
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
				SaveObj->Vehicles.Add(SavedVehicle);
			}
		}
	}
	else if (UWorld* World = GetWorld())
	{
		for (TActorIterator<ADoemitzTrafficVehicle> It(World); It; ++It)
		{
			const ADoemitzTrafficVehicle* Vehicle = *It;
			if (Vehicle && !Vehicle->GetVehicleId().IsNone())
			{
				FDoemitzSavedVehicle SavedVehicle;
				SavedVehicle.VehicleId = Vehicle->GetVehicleId();
				SavedVehicle.DistanceCm = Vehicle->GetDistanceAlongRoute();
				SavedVehicle.CompletedLaps = Vehicle->GetCompletedLaps();
				SavedVehicle.WorldLocation = Vehicle->GetActorLocation();
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
		UE_LOG(LogTemp, Display, TEXT("Doemitz save v%d written to slot '%s' (Day %d, %.1f min, %d citizens, %d vehicles)"),
			SaveObj->SaveSchemaVersion, *SlotName, DayNumber, TimeOfDayMinutes, SaveObj->Citizens.Num(), SaveObj->Vehicles.Num());
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
	if (!SaveObj || (SaveObj->SaveSchemaVersion != 1 && SaveObj->SaveSchemaVersion != UDoemitzSaveGame::CurrentSchemaVersion))
	{
		return false;
	}

	const bool bMigratingFromV1 = (SaveObj->SaveSchemaVersion == 1);
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

	JunctionReservations.Reset();
	if (!VehicleRecords.IsEmpty())
	{
		for (TPair<FName, FVehicleRecord>& Pair : VehicleRecords)
		{
			Pair.Value.ReservedNodeId = NAME_None;
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
			// Schema v1 migration: legacy altstadt_compact_01 maps to altstadt_vehicle_01
			if (!Saved && bMigratingFromV1 && VehicleId == FName(TEXT("altstadt_vehicle_01")))
			{
				Saved = SavedVehiclesById.Find(FName(TEXT("altstadt_compact_01")));
			}
			if (!Saved)
			{
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
				Rec->State.NextEdgeId = ChooseNextEdge(*Rec);
				SampleEdgePose(*Edge, Rec->State.DistanceOnEdgeCm, Rec->State.WorldLocation, Rec->State.WorldRotation);
			}
		}

		if (bMigratingFromV1)
		{
			UE_LOG(LogTemp, Display, TEXT("Migrated SaveGame v1 -> v2 for slot '%s'"), *SlotName);
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

		if (VehicleRecords.IsEmpty())
		{
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
		}
		else
		{
			for (TActorIterator<ADoemitzTrafficVehicle> It(World); It; ++It)
			{
				if (ADoemitzTrafficVehicle* Vehicle = *It)
				{
					Vehicle->SyncFromSimulation();
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
	UE_LOG(LogTemp, Display, TEXT("Doemitz save v%d loaded from slot '%s' (Day %d, %.1f min)"),
		SaveObj->SaveSchemaVersion, *SlotName, DayNumber, TimeOfDayMinutes);
	return true;
}
