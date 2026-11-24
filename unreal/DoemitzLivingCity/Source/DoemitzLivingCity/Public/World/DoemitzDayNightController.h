#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "DoemitzDayNightController.generated.h"

class ADirectionalLight;
class AExponentialHeightFog;
class APointLight;
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

	UFUNCTION(BlueprintPure, Category = "Environment")
	float GetActiveStreetLightIntensity() const { return CurrentStreetLightIntensity; }

	const TArray<TObjectPtr<APointLight>>& GetStreetLights() const { return StreetLights; }

	UFUNCTION(BlueprintPure, Category = "Environment")
	AExponentialHeightFog* GetHeightFog() const { return HeightFog; }

protected:
	virtual void BeginPlay() override;

private:
	UPROPERTY(EditInstanceOnly, Category = "Environment")
	TObjectPtr<ADirectionalLight> SunLight;

	UPROPERTY(EditInstanceOnly, Category = "Environment")
	TObjectPtr<ASkyLight> SkyLight;

	UPROPERTY(EditInstanceOnly, Category = "Environment")
	TObjectPtr<AExponentialHeightFog> HeightFog;

	UPROPERTY(EditInstanceOnly, Category = "Environment")
	TArray<TObjectPtr<APointLight>> StreetLights;

	UPROPERTY(EditAnywhere, Category = "Environment", meta = (ClampMin = "15", ClampMax = "85"))
	double PeakSunElevationDegrees = 60.0;

	UPROPERTY(EditAnywhere, Category = "Environment", meta = (ClampMin = "0"))
	float NightStreetLightIntensity = 3800.0f;

	double CurrentSunElevationDegrees = 45.0;
	float CurrentSunIntensity = 3.5f;
	float CurrentStreetLightIntensity = 0.0f;
};
