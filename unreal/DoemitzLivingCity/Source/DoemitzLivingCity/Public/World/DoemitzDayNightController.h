#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "DoemitzDayNightController.generated.h"

class ADirectionalLight;
class ASkyLight;

UCLASS()
class DOEMITZLIVINGCITY_API ADoemitzDayNightController : public AActor
{
	GENERATED_BODY()

public:
	ADoemitzDayNightController();
	virtual void Tick(float DeltaSeconds) override;

	UFUNCTION(BlueprintCallable, Category = "Environment")
	void UpdateLightingFromSimulation();

	UFUNCTION(BlueprintPure, Category = "Environment")
	double GetSunElevationDegrees() const { return CurrentSunElevationDegrees; }

	UFUNCTION(BlueprintPure, Category = "Environment")
	bool IsDaytime() const { return CurrentSunElevationDegrees >= 0.0; }

	UFUNCTION(BlueprintPure, Category = "Environment")
	float GetCurrentSunIntensity() const { return CurrentSunIntensity; }

protected:
	virtual void BeginPlay() override;

private:
	UPROPERTY(EditInstanceOnly, Category = "Environment")
	TObjectPtr<ADirectionalLight> SunLight;

	UPROPERTY(EditInstanceOnly, Category = "Environment")
	TObjectPtr<ASkyLight> SkyLight;

	UPROPERTY(EditAnywhere, Category = "Environment", meta = (ClampMin = "15", ClampMax = "85"))
	double PeakSunElevationDegrees = 60.0;

	double CurrentSunElevationDegrees = 45.0;
	float CurrentSunIntensity = 3.5f;
};
