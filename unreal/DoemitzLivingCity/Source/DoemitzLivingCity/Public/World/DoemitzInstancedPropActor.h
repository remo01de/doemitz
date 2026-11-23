#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "DoemitzInstancedPropActor.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;

UENUM(BlueprintType)
enum class EDoemitzPropCollisionKind : uint8
{
	Box,
	Capsule
};

/** One simple collision primitive of a prop prototype mesh, in mesh space (cm). */
USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzPropCollisionShape
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Props")
	EDoemitzPropCollisionKind Kind = EDoemitzPropCollisionKind::Box;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Props")
	FVector Center = FVector::ZeroVector;

	/** Box only: half size along X/Y/Z. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Props")
	FVector HalfExtent = FVector::ZeroVector;

	/** Capsule only (upright along Z). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Props")
	double Radius = 0.0;

	/** Capsule only: half of the total height including the hemispherical caps. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Props")
	double HalfHeight = 0.0;
};

UCLASS()
class DOEMITZLIVINGCITY_API ADoemitzInstancedPropActor : public AActor
{
	GENERATED_BODY()

public:
	ADoemitzInstancedPropActor();

	UFUNCTION(BlueprintCallable, Category = "Props")
	void SetInstances(const TArray<FTransform>& Transforms);

	/**
	 * Lamps, benches, bollards, planters and tree trunks block pawns (Sprint 13.1). They ignore the
	 * Visibility and Camera channels so ground traces, interaction traces and the camera boom pass through.
	 */
	UFUNCTION(BlueprintCallable, Category = "Props")
	void SetBlocksMovement(bool bInBlocksMovement);

	UFUNCTION(BlueprintPure, Category = "Props")
	bool BlocksMovement() const { return bBlocksMovement; }

	/**
	 * Replaces the simple collision of a prop prototype mesh with the given primitives and makes traces use
	 * them as complex collision too, so a foliage canopy never collides. Editor import helper.
	 */
	UFUNCTION(BlueprintCallable, Category = "Props")
	static int32 SetMeshCollisionShapes(UStaticMesh* Mesh, const TArray<FDoemitzPropCollisionShape>& Shapes);

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Props")
	TObjectPtr<UHierarchicalInstancedStaticMeshComponent> HismComponent;

protected:
	virtual void BeginPlay() override;

private:
	void ApplyCollision();

	UPROPERTY(EditAnywhere, Category = "Props")
	bool bBlocksMovement = false;
};
