#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "DoemitzTrafficVehicle.generated.h"

class UBoxComponent;
class UStaticMeshComponent;

struct FDoemitzVehicleMotion
{
	bool Initialize(const TArray<FVector>& Route, double StartDistance);
	FTransform Sample(const TArray<FVector>& Route, double SampleDistance) const;
	void Advance(double TravelDistance);

	double Length = 0.0;
	double Distance = 0.0;
	int32 CompletedLaps = 0;

private:
	TArray<double> SegmentEnds;
};

UCLASS()
class DOEMITZLIVINGCITY_API ADoemitzTrafficVehicle : public AActor
{
	GENERATED_BODY()

public:
	ADoemitzTrafficVehicle();
	virtual void Tick(float DeltaSeconds) override;

	UFUNCTION(BlueprintPure, Category = "Traffic")
	double GetDistanceAlongRoute() const { return Motion.Distance; }

	UFUNCTION(BlueprintPure, Category = "Traffic")
	int32 GetCompletedLaps() const { return Motion.CompletedLaps; }

protected:
	virtual void BeginPlay() override;

private:
	UPROPERTY(VisibleAnywhere, Category = "Vehicle")
	TObjectPtr<UStaticMeshComponent> VehicleMesh;

	UPROPERTY(VisibleAnywhere, Category = "Vehicle")
	TObjectPtr<UBoxComponent> VehicleCollision;

	UPROPERTY(EditInstanceOnly, Category = "Traffic")
	FName VehicleId;

	UPROPERTY(EditInstanceOnly, Category = "Traffic")
	FName RouteId;

	UPROPERTY(EditInstanceOnly, Category = "Traffic", meta = (Units = "cm/s", ClampMin = "1"))
	double SpeedCmPerSecond = 500.0;

	UPROPERTY(EditInstanceOnly, Category = "Traffic", meta = (Units = "cm", ClampMin = "0"))
	double StartDistanceCm = 0.0;

	UPROPERTY(EditInstanceOnly, Category = "Traffic")
	TArray<FVector> RoutePoints;

	FDoemitzVehicleMotion Motion;
};
