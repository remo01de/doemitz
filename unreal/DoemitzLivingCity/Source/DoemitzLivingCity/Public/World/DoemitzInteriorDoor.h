#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "DoemitzInteriorDoor.generated.h"

class UStaticMeshComponent;

/**
 * Street door of a walk-in interior (Sprint 13). The actor origin is the hinge; the generated leaf mesh is
 * authored relative to it. The door swings inward when the player approaches and the place is open, and it
 * always lets a player out from the inside. While it moves or stands open it has no collision.
 */
UCLASS()
class DOEMITZLIVINGCITY_API ADoemitzInteriorDoor : public AActor
{
	GENERATED_BODY()

public:
	ADoemitzInteriorDoor();

	virtual void Tick(float DeltaSeconds) override;

	/** Advance the door towards its wanted state (also callable from verification scripts). */
	UFUNCTION(BlueprintCallable, Category = "Interior")
	void UpdateDoorState(float DeltaSeconds);

	UFUNCTION(BlueprintPure, Category = "Interior")
	bool WantsOpen() const;

	UFUNCTION(BlueprintPure, Category = "Interior")
	double GetOpenAlpha() const;

	UFUNCTION(BlueprintPure, Category = "Interior")
	bool IsFullyClosed() const { return FMath::Abs(CurrentYawDegrees) < 0.5; }

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Interior")
	TObjectPtr<USceneComponent> HingeRoot;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Interior")
	TObjectPtr<UStaticMeshComponent> DoorLeaf;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FName PlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FName InteriorId;

	/** Middle of the door opening (world, cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FVector DoorCenter = FVector::ZeroVector;

	/** Horizontal unit vector pointing into the room (world). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	FVector InwardDirection = FVector::ForwardVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	double OpenYawDegrees = -95.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior", meta = (Units = "cm"))
	double TriggerRadiusCm = 280.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interior")
	double SwingDegreesPerSecond = 240.0;

private:
	double CurrentYawDegrees = 0.0;
};
