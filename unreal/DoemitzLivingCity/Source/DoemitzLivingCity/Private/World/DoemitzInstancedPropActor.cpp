#include "World/DoemitzInstancedPropActor.h"

#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"

ADoemitzInstancedPropActor::ADoemitzInstancedPropActor()
{
	PrimaryActorTick.bCanEverTick = false;

	HismComponent = CreateDefaultSubobject<UHierarchicalInstancedStaticMeshComponent>(TEXT("HismComponent"));
	SetRootComponent(HismComponent);
	HismComponent->SetMobility(EComponentMobility::Static);
	HismComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	HismComponent->SetCanEverAffectNavigation(false);
	HismComponent->SetCullDistances(0, 18000);
}

void ADoemitzInstancedPropActor::SetInstances(const TArray<FTransform>& Transforms)
{
	if (!HismComponent)
	{
		return;
	}
	HismComponent->ClearInstances();
	if (!Transforms.IsEmpty())
	{
		HismComponent->AddInstances(Transforms, false, true);
	}
}

void ADoemitzInstancedPropActor::SetBlocksMovement(const bool bInBlocksMovement)
{
	bBlocksMovement = bInBlocksMovement;
	ApplyCollision();
}

void ADoemitzInstancedPropActor::BeginPlay()
{
	Super::BeginPlay();
	ApplyCollision();
}

void ADoemitzInstancedPropActor::ApplyCollision()
{
	if (!HismComponent)
	{
		return;
	}
	if (!bBlocksMovement)
	{
		HismComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		return;
	}
	// Query-only is enough for character movement sweeps and avoids physics simulation bodies.
	HismComponent->SetCollisionProfileName(UCollisionProfile::CustomCollisionProfileName);
	HismComponent->SetCollisionObjectType(ECC_WorldStatic);
	HismComponent->SetCollisionResponseToAllChannels(ECR_Block);
	HismComponent->SetCollisionResponseToChannel(ECC_Visibility, ECR_Ignore);
	HismComponent->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	HismComponent->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
}

int32 ADoemitzInstancedPropActor::SetMeshCollisionShapes(UStaticMesh* Mesh, const TArray<FDoemitzPropCollisionShape>& Shapes)
{
	if (!Mesh)
	{
		return 0;
	}
	Mesh->CreateBodySetup();
	UBodySetup* Body = Mesh->GetBodySetup();
	if (!Body)
	{
		return 0;
	}
#if WITH_EDITOR
	Mesh->Modify();
	Body->Modify();
#endif
	Body->RemoveSimpleCollision();
	for (const FDoemitzPropCollisionShape& Shape : Shapes)
	{
		if (Shape.Kind == EDoemitzPropCollisionKind::Capsule)
		{
			const double Radius = FMath::Max(1.0, Shape.Radius);
			const double CylinderLength = FMath::Max(0.0, 2.0 * Shape.HalfHeight - 2.0 * Radius);
			FKSphylElem Elem(static_cast<float>(Radius), static_cast<float>(CylinderLength));
			Elem.Center = Shape.Center;
			Body->AggGeom.SphylElems.Add(Elem);
		}
		else
		{
			FKBoxElem Elem(
				static_cast<float>(2.0 * Shape.HalfExtent.X),
				static_cast<float>(2.0 * Shape.HalfExtent.Y),
				static_cast<float>(2.0 * Shape.HalfExtent.Z));
			Elem.Center = Shape.Center;
			Body->AggGeom.BoxElems.Add(Elem);
		}
	}
	Body->CollisionTraceFlag = Shapes.IsEmpty() ? CTF_UseDefault : CTF_UseSimpleAsComplex;
	Body->InvalidatePhysicsData();
	Body->CreatePhysicsMeshes();
#if WITH_EDITOR
	Mesh->PostEditChange();
#endif
	Mesh->MarkPackageDirty();
	return Body->AggGeom.GetElementCount();
}
