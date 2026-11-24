#include "World/DoemitzDayNightController.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/PointLight.h"
#include "Engine/SkyLight.h"
#include "Simulation/DoemitzSimulationSubsystem.h"

ADoemitzDayNightController::ADoemitzDayNightController()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;
}

void ADoemitzDayNightController::BeginPlay()
{
	Super::BeginPlay();
	UpdateLightingFromSimulation();
}

void ADoemitzDayNightController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UpdateLightingFromSimulation();
}

void ADoemitzDayNightController::UpdateLightingFromSimulation()
{
	const UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this);
	if (!Subsystem)
	{
		return;
	}

	const double TimeMinutes = Subsystem->GetTimeOfDayMinutes();
	const double DayFraction = TimeMinutes / 1440.0;
	const double AngleRad = (DayFraction - 0.25) * 2.0 * UE_DOUBLE_PI;
	CurrentSunElevationDegrees = FMath::Sin(AngleRad) * PeakSunElevationDegrees;
	const double AzimuthDegrees = FMath::Fmod(90.0 + DayFraction * 360.0, 360.0);

	const bool bIsDay = CurrentSunElevationDegrees >= 0.0;
	const float DaylightAlpha = bIsDay
		? static_cast<float>(FMath::Clamp(CurrentSunElevationDegrees / PeakSunElevationDegrees, 0.0, 1.0))
		: 0.0f;

	if (SunLight)
	{
		if (UDirectionalLightComponent* SunComp = SunLight->FindComponentByClass<UDirectionalLightComponent>())
		{
			if (bIsDay)
			{
				SunLight->SetActorRotation(FRotator(-CurrentSunElevationDegrees, AzimuthDegrees, 0.0));
				CurrentSunIntensity = FMath::Lerp(0.45f, 3.8f, DaylightAlpha);
				const FLinearColor WarmHorizon(1.0f, 0.72f, 0.46f);
				const FLinearColor NeutralDay(1.0f, 0.96f, 0.90f);
				SunComp->SetLightColor(FMath::Lerp(WarmHorizon, NeutralDay, FMath::Sqrt(DaylightAlpha)));
			}
			else
			{
				SunLight->SetActorRotation(FRotator(-25.0, FMath::Fmod(AzimuthDegrees + 180.0, 360.0), 0.0));
				CurrentSunIntensity = 0.25f;
				SunComp->SetLightColor(FLinearColor(0.45f, 0.58f, 0.85f));
			}
			SunComp->SetIntensity(CurrentSunIntensity);
		}
	}

	if (SkyLight)
	{
		if (USkyLightComponent* SkyComp = SkyLight->FindComponentByClass<USkyLightComponent>())
		{
			const float SkyIntensity = bIsDay ? FMath::Lerp(0.45f, 1.35f, DaylightAlpha) : 0.22f;
			SkyComp->SetIntensity(SkyIntensity);
		}
	}

	if (HeightFog)
	{
		if (UExponentialHeightFogComponent* FogComp = HeightFog->GetComponent())
		{
			const FLinearColor WarmHorizonFog(0.76f, 0.62f, 0.50f);
			const FLinearColor ClearDayFog(0.62f, 0.74f, 0.88f);
			const FLinearColor NightFog(0.05f, 0.08f, 0.16f);
			const FLinearColor TargetFog = bIsDay
				? FMath::Lerp(WarmHorizonFog, ClearDayFog, FMath::Sqrt(DaylightAlpha))
				: NightFog;
			FogComp->SetFogInscatteringColor(TargetFog);
		}
	}

	const float NightFactor = static_cast<float>(FMath::Clamp((-CurrentSunElevationDegrees + 6.0) / 12.0, 0.0, 1.0));
	CurrentStreetLightIntensity = NightStreetLightIntensity * NightFactor;
	const bool bLightsOn = NightFactor > 0.01f;
	for (APointLight* Lamp : StreetLights)
	{
		if (!Lamp)
		{
			continue;
		}
		if (UPointLightComponent* PointComp = Lamp->FindComponentByClass<UPointLightComponent>())
		{
			if (Lamp->IsHidden())
			{
				PointComp->SetIntensity(0.0f);
				PointComp->SetVisibility(false);
				continue;
			}
			PointComp->SetIntensity(CurrentStreetLightIntensity);
			PointComp->SetVisibility(bLightsOn);
		}
	}
}
