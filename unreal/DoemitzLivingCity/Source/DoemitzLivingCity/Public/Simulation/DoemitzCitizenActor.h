#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "DoemitzCitizenActor.generated.h"

class UCapsuleComponent;
class UStaticMesh;
class UStaticMeshComponent;

UCLASS()
class DOEMITZLIVINGCITY_API ADoemitzCitizenActor : public AActor
{
	GENERATED_BODY()

public:
	ADoemitzCitizenActor();
	virtual void Tick(float DeltaSeconds) override;

	UFUNCTION(BlueprintPure, Category = "Simulation")
	FName GetCitizenId() const { return CitizenId; }

	void AssignToCitizen(FName NewCitizenId, UStaticMesh* MeshAsset);
	void ReleaseToPool();
	void SyncFromSimulation();

protected:
	virtual void BeginPlay() override;

private:
	UPROPERTY(VisibleAnywhere, Category = "Citizen")
	TObjectPtr<UStaticMeshComponent> CitizenMesh;

	UPROPERTY(VisibleAnywhere, Category = "Citizen")
	TObjectPtr<UCapsuleComponent> CitizenCollision;

	UPROPERTY(EditInstanceOnly, Category = "Simulation")
	FName CitizenId;
};
