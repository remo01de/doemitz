#include "World/DoemitzInstancedPropActor.h"

#include "Components/HierarchicalInstancedStaticMeshComponent.h"

ADoemitzInstancedPropActor::ADoemitzInstancedPropActor()
{
	PrimaryActorTick.bCanEverTick = false;

	HismComponent = CreateDefaultSubobject<UHierarchicalInstancedStaticMeshComponent>(TEXT("HismComponent"));
	SetRootComponent(HismComponent);
	HismComponent->SetMobility(EComponentMobility::Static);
	HismComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
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
