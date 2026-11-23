#include "Traffic/DoemitzTrafficSubsystem.h"

#include "Algo/BinarySearch.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Simulation/DoemitzCitizenSubsystem.h"
#include "Simulation/DoemitzSaveGame.h"
#include "Simulation/DoemitzSimulationSubsystem.h"

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
	constexpr double MaxTrafficSubStepSeconds = 0.05;
	constexpr int32 MaxTrafficSubStepsPerTick = 20;
}

bool UDoemitzTrafficSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}
	const UWorld* World = Cast<UWorld>(Outer);
	return World != nullptr && World->IsGameWorld();
}

UDoemitzTrafficSubsystem* UDoemitzTrafficSubsystem::Get(const UObject* WorldContextObject)
{
	if (!WorldContextObject)
	{
		return nullptr;
	}
	const UWorld* World = WorldContextObject->GetWorld();
	return World ? World->GetSubsystem<UDoemitzTrafficSubsystem>() : nullptr;
}

void UDoemitzTrafficSubsystem::ConfigureTrafficNetwork(
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
	if (UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this))
	{
		if (VehicleRecords.Num() > 0)
		{
			Sim->MarkConfigured();
		}
	}

	UE_LOG(LogTemp, Display, TEXT("Doemitz traffic network configured: seed=%d, %d edges, %d vehicles, %d crossings, %d parking lots"),
		TrafficSeed, RoadEdgesById.Num(), VehicleRecords.Num(), Crossings.Num(), ParkingLotsById.Num());
}

bool UDoemitzTrafficSubsystem::GetCrossingLocation(FName CrossingId, FVector& OutLocation) const
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

TArray<FName> UDoemitzTrafficSubsystem::GetAllCrossingIds() const
{
	TArray<FName> Ids;
	Ids.Reserve(Crossings.Num());
	for (const FDoemitzCrossingDefinition& Crossing : Crossings)
	{
		Ids.Add(Crossing.CrossingId);
	}
	return Ids;
}

bool UDoemitzTrafficSubsystem::GetVehicleState(FName VehicleId, FDoemitzVehicleState& OutState) const
{
	if (const FVehicleRecord* Record = VehicleRecords.Find(VehicleId))
	{
		OutState = Record->State;
		return true;
	}
	return false;
}

FName UDoemitzTrafficSubsystem::GetJunctionReservation(FName NodeId) const
{
	if (const FName* Holder = JunctionReservations.Find(NodeId))
	{
		return *Holder;
	}
	return NAME_None;
}

EDoemitzYieldRule UDoemitzTrafficSubsystem::GetEdgeYieldRule(FName EdgeId) const
{
	if (const FRoadEdgeRecord* Edge = RoadEdgesById.Find(EdgeId))
	{
		return Edge->Definition.YieldRule;
	}
	return EDoemitzYieldRule::None;
}

bool UDoemitzTrafficSubsystem::SetEdgeYieldRuleForTest(FName EdgeId, EDoemitzYieldRule NewRule)
{
	if (FRoadEdgeRecord* Edge = RoadEdgesById.Find(EdgeId))
	{
		Edge->Definition.YieldRule = NewRule;
		return true;
	}
	return false;
}

bool UDoemitzTrafficSubsystem::GetParkingLotState(FName ParkingLotId, FDoemitzParkingLotState& OutState) const
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

bool UDoemitzTrafficSubsystem::SetVehicleEdgePositionForTest(
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

bool UDoemitzTrafficSubsystem::SetVehicleTargetParkingForTest(FName VehicleId, FName ParkingLotId)
{
	FVehicleRecord* Record = VehicleRecords.Find(VehicleId);
	if (!Record || !ParkingLotsById.Contains(ParkingLotId))
	{
		return false;
	}
	PlanRouteToParking(*Record, ParkingLotId);
	return true;
}

void UDoemitzTrafficSubsystem::SampleEdgePose(
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

FName UDoemitzTrafficSubsystem::ChooseNextEdge(const FVehicleRecord& Record) const
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
	const uint32 Hash = DoemitzSimulationUtil::DeterministicHash(TrafficSeed, Record.State.VehicleId, Record.State.JunctionDecisions);
	return Pool[static_cast<int32>(Hash % static_cast<uint32>(Pool.Num()))];
}

bool UDoemitzTrafficSubsystem::ComputeEdgePath(FName StartEdgeId, FName GoalEdgeId, TArray<FName>& OutPath) const
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

FName UDoemitzTrafficSubsystem::ChooseNextParkingLot(const FVehicleRecord& Record, FName ExcludeLotId) const
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
	const uint32 Hash = DoemitzSimulationUtil::DeterministicHash(TrafficSeed + 101, Record.State.VehicleId, Record.TripCounter);
	return Candidates[static_cast<int32>(Hash % static_cast<uint32>(Candidates.Num()))];
}

void UDoemitzTrafficSubsystem::PlanRouteToParking(FVehicleRecord& Record, FName ParkingLotId)
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

int32 UDoemitzTrafficSubsystem::TryReserveParkingSlot(FName ParkingLotId, FName VehicleId, FVector& OutSlotLocation)
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

void UDoemitzTrafficSubsystem::ReleaseParkingSlot(FVehicleRecord& Record)
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

FName UDoemitzTrafficSubsystem::FindNearestDrivableEdge(const FVector& Location, double& OutDistanceCm) const
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

void UDoemitzTrafficSubsystem::ReleaseJunctionReservation(FVehicleRecord& Record)
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

void UDoemitzTrafficSubsystem::StepTraffic(double DeltaSeconds, double TimeMultiplier)
{
	if (OrderedVehicleIds.IsEmpty() || DeltaSeconds <= 0.0 || TimeMultiplier <= 0.0)
	{
		return;
	}

	// Scale traffic simulation time proportionally with fast-forward multiplier (1x/5x/15x),
	// sub-stepping at <= 0.05 s so vehicles never overshoot junctions, stop signs, or crossings.
	const double ScaledDelta = DeltaSeconds * FMath::Clamp(TimeMultiplier, 0.0, 20.0);
	const int32 SubSteps = FMath::Clamp(FMath::CeilToInt(ScaledDelta / MaxTrafficSubStepSeconds), 1, MaxTrafficSubStepsPerTick);
	const double SubDt = ScaledDelta / static_cast<double>(SubSteps);
	for (int32 Step = 0; Step < SubSteps; ++Step)
	{
		UpdateTrafficSubStep(SubDt);
	}
}

void UDoemitzTrafficSubsystem::UpdateTrafficSubStep(double DeltaSeconds)
{
	TArray<FVector> PedestrianLocations;
	if (UWorld* World = GetWorld())
	{
		if (const APlayerController* PC = World->GetFirstPlayerController())
		{
			if (const APawn* Pawn = PC->GetPawn())
			{
				PedestrianLocations.Add(Pawn->GetActorLocation());
			}
		}
		if (const UDoemitzCitizenSubsystem* Citizens = World->GetSubsystem<UDoemitzCitizenSubsystem>())
		{
			Citizens->CollectCitizenWorldLocations(PedestrianLocations);
		}
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
				const uint32 ParkHash = DoemitzSimulationUtil::DeterministicHash(TrafficSeed + 303, VehicleId, Record->TripCounter);
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

		// 2. Car-following distance & 2D anti-penetration against active vehicles
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

		// 3. Priority signs (give_way / stop) overriding Right-before-Left & junction reservation
		const FName ApproachNode = Edge->Definition.ToNodeId;
		if (RemainingOnEdge <= JunctionApproachCm && !ApproachNode.IsNone())
		{
			const bool bMeStopSign = (Edge->Definition.YieldRule == EDoemitzYieldRule::Stop);
			const bool bMeYieldSign = (Edge->Definition.YieldRule != EDoemitzYieldRule::None);

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
						if (bMeYieldSign && !bOtherYieldSign)
						{
							bMustYieldRightOfWay = true;
							bYieldDueToSign = true;
							break;
						}
						if (!bMeYieldSign && bOtherYieldSign)
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

void UDoemitzTrafficSubsystem::CaptureSaveState(UDoemitzSaveGame* SaveObj) const
{
	if (!SaveObj)
	{
		return;
	}
	SaveObj->ParkingOccupancy.Reset();
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
	SaveObj->Vehicles.Reset();
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
}

void UDoemitzTrafficSubsystem::RestoreSaveState(const UDoemitzSaveGame* SaveObj, bool bMigratingFromV1, bool bMigratingFromPreV5)
{
	if (!SaveObj)
	{
		return;
	}

	for (TPair<FName, FParkingLotRecord>& LotPair : ParkingLotsById)
	{
		for (FName& Occ : LotPair.Value.SlotOccupants)
		{
			Occ = NAME_None;
		}
	}

	JunctionReservations.Reset();
	if (VehicleRecords.IsEmpty())
	{
		return;
	}

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
