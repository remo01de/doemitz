#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "DoemitzInstancedPropActor.generated.h"

class UHierarchicalInstancedStaticMeshComponent;

UCLASS()
class DOEMITZLIVINGCITY_API ADoemitzInstancedPropActor : public AActor
{
	GENERATED_BODY()

public:
	ADoemitzInstancedPropActor();

	UFUNCTION(BlueprintCallable, Category = "Props")
	void SetInstances(const TArray<FTransform>& Transforms);

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Props")
	TObjectPtr<UHierarchicalInstancedStaticMeshComponent> HismComponent;
};
