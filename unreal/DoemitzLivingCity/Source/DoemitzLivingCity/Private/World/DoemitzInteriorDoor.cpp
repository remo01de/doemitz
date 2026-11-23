#include "World/DoemitzInteriorDoor.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Economy/DoemitzEconomySubsystem.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Simulation/DoemitzSimulationSubsystem.h"

ADoemitzInteriorDoor::ADoemitzInteriorDoor()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.0f;

	HingeRoot = CreateDefaultSubobject<USceneComponent>(TEXT("HingeRoot"));
	SetRootComponent(HingeRoot);
	HingeRoot->SetMobility(EComponentMobility::Movable);

	DoorLeaf = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("DoorLeaf"));
	DoorLeaf->SetupAttachment(HingeRoot);
	DoorLeaf->SetMobility(EComponentMobility::Movable);
	DoorLeaf->SetCollisionProfileName(TEXT("BlockAll"));
	DoorLeaf->SetCanEverAffectNavigation(false);
	DoorLeaf->bAffectDistanceFieldLighting = false;
}

void ADoemitzInteriorDoor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UpdateDoorState(DeltaSeconds);
}

bool ADoemitzInteriorDoor::WantsOpen() const
{
	const UWorld* World = GetWorld();
	const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	if (!Pawn)
	{
		return false;
	}
	const FVector PawnLoc = Pawn->GetActorLocation();
	if (FVector::Dist2D(PawnLoc, DoorCenter) > TriggerRadiusCm || FMath::Abs(PawnLoc.Z - DoorCenter.Z) > 300.0)
	{
		return false;
	}
	const UDoemitzSimulationSubsystem* Subsystem = World->GetSubsystem<UDoemitzSimulationSubsystem>();
	if (!Subsystem)
	{
		return true;
	}
	if (const UDoemitzEconomySubsystem* Economy = World->GetSubsystem<UDoemitzEconomySubsystem>())
	{
		if (Economy->IsWorkingShift())
		{
			return false;
		}
	}
	// Leaving is always possible; entering only while the place is open.
	const FVector Offset = PawnLoc - DoorCenter;
	const bool bOnInsideSide = (Offset.X * InwardDirection.X + Offset.Y * InwardDirection.Y) > 0.0;
	return bOnInsideSide || Subsystem->IsPlaceOpenNow(PlaceId);
}

double ADoemitzInteriorDoor::GetOpenAlpha() const
{
	return FMath::Abs(OpenYawDegrees) > KINDA_SMALL_NUMBER ? FMath::Clamp(CurrentYawDegrees / OpenYawDegrees, 0.0, 1.0) : 0.0;
}

void ADoemitzInteriorDoor::UpdateDoorState(float DeltaSeconds)
{
	const double Target = WantsOpen() ? OpenYawDegrees : 0.0;
	const double MaxStep = SwingDegreesPerSecond * FMath::Max(0.0, static_cast<double>(DeltaSeconds));
	CurrentYawDegrees += FMath::Clamp(Target - CurrentYawDegrees, -MaxStep, MaxStep);
	if (DoorLeaf)
	{
		DoorLeaf->SetRelativeRotation(FRotator(0.0, CurrentYawDegrees, 0.0));
		// Only a fully closed leaf blocks; a swinging or open leaf never pushes or traps the player.
		DoorLeaf->SetCollisionEnabled(IsFullyClosed() ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
	}
}
