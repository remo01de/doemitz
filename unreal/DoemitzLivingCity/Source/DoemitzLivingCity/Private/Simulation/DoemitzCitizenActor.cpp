#include "Simulation/DoemitzCitizenActor.h"

#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Simulation/DoemitzSimulationSubsystem.h"

ADoemitzCitizenActor::ADoemitzCitizenActor()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;

	CitizenMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CitizenMesh"));
	SetRootComponent(CitizenMesh);
	CitizenMesh->SetMobility(EComponentMobility::Movable);
	CitizenMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	CitizenCollision = CreateDefaultSubobject<UCapsuleComponent>(TEXT("CitizenCollision"));
	CitizenCollision->SetupAttachment(CitizenMesh);
	CitizenCollision->SetRelativeLocation(FVector(0.0, 0.0, 88.0));
	CitizenCollision->InitCapsuleSize(30.0f, 88.0f);
	CitizenCollision->SetCollisionObjectType(ECC_Pawn);
	CitizenCollision->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	CitizenCollision->SetCollisionResponseToAllChannels(ECR_Ignore);
	CitizenCollision->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
	CitizenCollision->SetGenerateOverlapEvents(false);
}

void ADoemitzCitizenActor::BeginPlay()
{
	Super::BeginPlay();
	SyncFromSimulation();
}

void ADoemitzCitizenActor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	SyncFromSimulation();
}

void ADoemitzCitizenActor::AssignToCitizen(FName NewCitizenId, UStaticMesh* MeshAsset)
{
	CitizenId = NewCitizenId;
	if (CitizenMesh && MeshAsset && CitizenMesh->GetStaticMesh() != MeshAsset)
	{
		CitizenMesh->SetStaticMesh(MeshAsset);
	}
	SetActorHiddenInGame(false);
	SetActorEnableCollision(true);
	SetActorTickEnabled(true);
	SyncFromSimulation();
}

void ADoemitzCitizenActor::ReleaseToPool()
{
	CitizenId = NAME_None;
	SetActorHiddenInGame(true);
	SetActorEnableCollision(false);
	SetActorTickEnabled(false);
}

void ADoemitzCitizenActor::SyncFromSimulation()
{
	if (CitizenId.IsNone())
	{
		return;
	}
	if (const UDoemitzSimulationSubsystem* Subsystem = GetWorld()->GetSubsystem<UDoemitzSimulationSubsystem>())
	{
		FVector Location;
		FRotator Rotation;
		if (Subsystem->GetCitizenPresentationTransform(CitizenId, Location, Rotation))
		{
			SetActorLocationAndRotation(Location, Rotation, false);
		}
	}
}
