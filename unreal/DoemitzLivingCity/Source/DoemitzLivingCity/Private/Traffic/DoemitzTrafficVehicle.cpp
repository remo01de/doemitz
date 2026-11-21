#include "Traffic/DoemitzTrafficVehicle.h"

#include "Algo/BinarySearch.h"
#include "Components/BoxComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"

bool FDoemitzVehicleMotion::Initialize(const TArray<FVector>& Route, double StartDistance)
{
	if (Route.Num() < 3 || !FMath::IsFinite(StartDistance) || StartDistance < 0.0)
	{
		return false;
	}

	SegmentEnds.Reset(Route.Num());
	Length = 0.0;
	for (int32 Index = 0; Index < Route.Num(); ++Index)
	{
		const double SegmentLength = FVector::Distance(Route[Index], Route[(Index + 1) % Route.Num()]);
		if (!FMath::IsFinite(SegmentLength) || SegmentLength <= UE_KINDA_SMALL_NUMBER)
		{
			return false;
		}
		Length += SegmentLength;
		SegmentEnds.Add(Length);
	}
	Distance = FMath::Fmod(StartDistance, Length);
	CompletedLaps = 0;
	return true;
}

FTransform FDoemitzVehicleMotion::Sample(const TArray<FVector>& Route, double SampleDistance) const
{
	const double Wrapped = FMath::Fmod(SampleDistance, Length);
	const int32 Index = FMath::Clamp(Algo::UpperBound(SegmentEnds, Wrapped), 0, Route.Num() - 1);
	const double SegmentStart = Index == 0 ? 0.0 : SegmentEnds[Index - 1];
	const FVector& Start = Route[Index];
	const FVector& End = Route[(Index + 1) % Route.Num()];
	const double Fraction = (Wrapped - SegmentStart) / (SegmentEnds[Index] - SegmentStart);
	return FTransform((End - Start).Rotation(), FMath::Lerp(Start, End, Fraction));
}

void FDoemitzVehicleMotion::Advance(double TravelDistance)
{
	const double NewDistance = Distance + TravelDistance;
	CompletedLaps += FMath::FloorToInt(NewDistance / Length);
	Distance = FMath::Fmod(NewDistance, Length);
}

ADoemitzTrafficVehicle::ADoemitzTrafficVehicle()
{
	PrimaryActorTick.bCanEverTick = true;

	VehicleMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("VehicleMesh"));
	SetRootComponent(VehicleMesh);
	VehicleMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	VehicleCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("VehicleCollision"));
	VehicleCollision->SetupAttachment(VehicleMesh);
	VehicleCollision->SetRelativeLocation(FVector(0, 0, 65));
	VehicleCollision->SetBoxExtent(FVector(195, 88, 65));
	VehicleCollision->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	VehicleCollision->SetCollisionResponseToAllChannels(ECR_Ignore);
	VehicleCollision->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
	VehicleCollision->SetGenerateOverlapEvents(false);
}

void ADoemitzTrafficVehicle::BeginPlay()
{
	Super::BeginPlay();
	if (VehicleId.IsNone() || RouteId.IsNone() || !FMath::IsFinite(SpeedCmPerSecond) ||
		SpeedCmPerSecond <= 0.0 || !Motion.Initialize(RoutePoints, StartDistanceCm))
	{
		UE_LOG(LogTemp, Error, TEXT("Traffic vehicle %s has invalid route configuration"), *GetName());
		SetActorTickEnabled(false);
		return;
	}

	SetActorTransform(Motion.Sample(RoutePoints, Motion.Distance));
	UE_LOG(LogTemp, Display, TEXT("Traffic vehicle %s started on %s (%.1f m)"),
		*VehicleId.ToString(), *RouteId.ToString(), Motion.Length / 100.0);
}

void ADoemitzTrafficVehicle::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const double TravelDistance = SpeedCmPerSecond * DeltaSeconds;
	const FTransform NextPose = Motion.Sample(RoutePoints, Motion.Distance + TravelDistance);

	const FVector CenterOffset = VehicleCollision->GetRelativeLocation();
	const FVector SweepStart = GetActorTransform().TransformPosition(CenterOffset);
	const FVector SweepEnd = NextPose.TransformPosition(CenterOffset + FVector(60, 0, 0));
	const FCollisionObjectQueryParams Pawns(ECC_Pawn);
	const FCollisionQueryParams Query(SCENE_QUERY_STAT(DoemitzTrafficVehicle), false, this);
	FHitResult Hit;
	if (GetWorld()->SweepSingleByObjectType(Hit, SweepStart, SweepEnd, NextPose.GetRotation(), Pawns,
		FCollisionShape::MakeBox(VehicleCollision->GetScaledBoxExtent()), Query))
	{
		return;
	}

	const int32 PreviousLaps = Motion.CompletedLaps;
	Motion.Advance(TravelDistance);
	SetActorTransform(NextPose);
	if (Motion.CompletedLaps != PreviousLaps)
	{
		UE_LOG(LogTemp, Display, TEXT("Traffic vehicle %s crossed the route start on %s (lap %d)"),
			*VehicleId.ToString(), *RouteId.ToString(), Motion.CompletedLaps);
	}
}

void ADoemitzTrafficVehicle::RestoreMotionState(double NewDistanceCm, int32 NewCompletedLaps)
{
	if (Motion.Length <= 0.0 || !FMath::IsFinite(NewDistanceCm) || NewDistanceCm < 0.0)
	{
		return;
	}
	Motion.Distance = FMath::Fmod(NewDistanceCm, Motion.Length);
	Motion.CompletedLaps = FMath::Max(0, NewCompletedLaps);
	SetActorTransform(Motion.Sample(RoutePoints, Motion.Distance));
}
