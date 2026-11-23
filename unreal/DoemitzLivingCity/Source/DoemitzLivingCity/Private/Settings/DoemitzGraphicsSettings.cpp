#include "Settings/DoemitzGraphicsSettings.h"

#include "Components/PointLightComponent.h"
#include "Engine/Engine.h"
#include "Engine/PointLight.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameUserSettings.h"
#include "HAL/IConsoleManager.h"
#include "World/DoemitzDayNightController.h"

namespace
{
	void SetCVarInt(const TCHAR* Name, int32 Value)
	{
		if (IConsoleVariable* Var = IConsoleManager::Get().FindConsoleVariable(Name))
		{
			Var->Set(Value, ECVF_SetByGameSetting);
		}
	}

	void SetCVarFloat(const TCHAR* Name, float Value)
	{
		if (IConsoleVariable* Var = IConsoleManager::Get().FindConsoleVariable(Name))
		{
			Var->Set(Value, ECVF_SetByGameSetting);
		}
	}
}

UDoemitzGraphicsSettings* UDoemitzGraphicsSettings::Get()
{
	static TWeakObjectPtr<UDoemitzGraphicsSettings> Instance;
	if (!Instance.IsValid())
	{
		UDoemitzGraphicsSettings* Settings = NewObject<UDoemitzGraphicsSettings>(GetTransientPackage(), TEXT("DoemitzGraphicsSettings"));
		Settings->AddToRoot();
		Settings->LoadConfig(UDoemitzGraphicsSettings::StaticClass(), *GGameUserSettingsIni);
		Settings->GraphicsProfile = NormalizeProfileName(Settings->GraphicsProfile);
		Settings->ActiveProfileName = Settings->GraphicsProfile;
		Instance = Settings;
	}
	return Instance.Get();
}

FString UDoemitzGraphicsSettings::NormalizeProfileName(const FString& InProfileName)
{
	if (InProfileName.Equals(HighProfileName, ESearchCase::IgnoreCase) ||
		InProfileName.Equals(TEXT("High"), ESearchCase::IgnoreCase))
	{
		return HighProfileName;
	}
	return LowProfileName;
}

EDoemitzGraphicsProfile UDoemitzGraphicsSettings::GetActiveProfile() const
{
	return GetActiveProfileName().Equals(HighProfileName, ESearchCase::IgnoreCase)
		? EDoemitzGraphicsProfile::High
		: EDoemitzGraphicsProfile::Low;
}

FString UDoemitzGraphicsSettings::GetActiveProfileShortLabel() const
{
	return GetActiveProfile() == EDoemitzGraphicsProfile::High ? TEXT("High") : TEXT("Low");
}

void UDoemitzGraphicsSettings::ApplyActiveProfile(UWorld* World)
{
	ApplyProfile(GetActiveProfileName(), World, false);
}

FString UDoemitzGraphicsSettings::ToggleProfile(UWorld* World)
{
	const FString NextProfile = (GetActiveProfile() == EDoemitzGraphicsProfile::Low)
		? FString(HighProfileName)
		: FString(LowProfileName);
	ApplyProfile(NextProfile, World, true);
	return NextProfile;
}

void UDoemitzGraphicsSettings::ApplyProfile(const FString& InProfileName, UWorld* World, bool bSaveToConfig)
{
	const FString Normalized = NormalizeProfileName(InProfileName);
	ActiveProfileName = Normalized;
	if (bSaveToConfig)
	{
		GraphicsProfile = Normalized;
		SaveConfig(CPF_Config, *GGameUserSettingsIni);
	}

	if (Normalized.Equals(LowProfileName, ESearchCase::IgnoreCase))
	{
		if (GEngine)
		{
			if (UGameUserSettings* Settings = GEngine->GetGameUserSettings())
			{
				Settings->SetOverallScalabilityLevel(0);
				Settings->SetViewDistanceQuality(1);
				Settings->SetAntiAliasingQuality(1);
				Settings->SetShadowQuality(1);
				Settings->SetGlobalIlluminationQuality(0);
				Settings->SetReflectionQuality(0);
				Settings->SetPostProcessingQuality(0);
				Settings->SetTextureQuality(1);
				Settings->SetVisualEffectQuality(0);
				Settings->SetFoliageQuality(1);
				Settings->SetShadingQuality(0);
				Settings->ApplyNonResolutionSettings();
			}
		}

		// Disable expensive UE5 defaults for integrated GPUs (Iris Xe): Lumen GI/Reflections, VSM, Hardware RT
		SetCVarInt(TEXT("r.DynamicGlobalIlluminationMethod"), 0);
		SetCVarInt(TEXT("r.ReflectionMethod"), 0);
		SetCVarInt(TEXT("r.Shadow.Virtual.Enable"), 0);
		SetCVarInt(TEXT("r.Lumen.DiffuseIndirect.Allow"), 0);
		SetCVarInt(TEXT("r.Lumen.Reflections.Allow"), 0);
		SetCVarInt(TEXT("r.DistanceFieldAO"), 0);
		SetCVarInt(TEXT("r.AmbientOcclusionLevels"), 0);
		SetCVarInt(TEXT("r.VolumetricFog"), 0);
		SetCVarInt(TEXT("r.VolumetricCloud"), 0);
		SetCVarInt(TEXT("r.BloomQuality"), 0);
		SetCVarInt(TEXT("r.MotionBlurQuality"), 0);
		SetCVarInt(TEXT("r.Shadow.CSM.MaxCascades"), 2);
		SetCVarInt(TEXT("r.Shadow.MaxResolution"), 1024);
		SetCVarFloat(TEXT("r.Shadow.RadiusThreshold"), 0.05f);
		SetCVarInt(TEXT("r.AntiAliasingMethod"), 1); // FXAA instead of TSR
		SetCVarFloat(TEXT("r.ScreenPercentage"), 100.0f);

		// Reduce ONLY street light count and attenuation radius for integrated GPU budget;
		// interior ceiling lights stay always visible at their configured brightness/radius.
		if (World)
		{
			TArray<APointLight*> StreetLights;
			for (TActorIterator<ADoemitzDayNightController> It(World); It; ++It)
			{
				if (const ADoemitzDayNightController* Controller = *It)
				{
					for (const TObjectPtr<APointLight>& Lamp : Controller->GetStreetLights())
					{
						if (APointLight* Light = Lamp.Get())
						{
							StreetLights.AddUnique(Light);
						}
					}
				}
			}
			int32 LightIndex = 0;
			int32 ActiveLights = 0;
			for (APointLight* Light : StreetLights)
			{
				if (UPointLightComponent* Comp = Light->FindComponentByClass<UPointLightComponent>())
				{
					Comp->SetCastShadows(false);
					if ((LightIndex % 3) != 0)
					{
						Comp->SetVisibility(false);
						Light->SetActorHiddenInGame(true);
					}
					else
					{
						Comp->SetVisibility(true);
						Light->SetActorHiddenInGame(false);
						Comp->SetAttenuationRadius(FMath::Min(Comp->AttenuationRadius, 700.0f));
						Comp->MaxDrawDistance = 4500.0f;
						Comp->MaxDistanceFadeRange = 1000.0f;
						++ActiveLights;
					}
					++LightIndex;
				}
			}
			UE_LOG(LogTemp, Display, TEXT("DoemitzLow profile applied: %d/%d street point lights kept active (interior lights untouched)"), ActiveLights, LightIndex);
		}
		else
		{
			UE_LOG(LogTemp, Display, TEXT("DoemitzLow profile applied"));
		}
	}
	else
	{
		if (GEngine)
		{
			if (UGameUserSettings* Settings = GEngine->GetGameUserSettings())
			{
				Settings->SetOverallScalabilityLevel(3);
				Settings->ApplyNonResolutionSettings();
			}
		}
		SetCVarInt(TEXT("r.DynamicGlobalIlluminationMethod"), 1);
		SetCVarInt(TEXT("r.ReflectionMethod"), 1);
		SetCVarInt(TEXT("r.Shadow.Virtual.Enable"), 1);
		SetCVarInt(TEXT("r.Lumen.DiffuseIndirect.Allow"), 1);
		SetCVarInt(TEXT("r.Lumen.Reflections.Allow"), 1);
		SetCVarInt(TEXT("r.AntiAliasingMethod"), 4); // TSR

		if (World)
		{
			TArray<APointLight*> StreetLights;
			for (TActorIterator<ADoemitzDayNightController> It(World); It; ++It)
			{
				if (const ADoemitzDayNightController* Controller = *It)
				{
					for (const TObjectPtr<APointLight>& Lamp : Controller->GetStreetLights())
					{
						if (APointLight* Light = Lamp.Get())
						{
							StreetLights.AddUnique(Light);
						}
					}
				}
			}
			int32 LightIndex = 0;
			for (APointLight* Light : StreetLights)
			{
				if (UPointLightComponent* Comp = Light->FindComponentByClass<UPointLightComponent>())
				{
					Comp->SetVisibility(true);
					Light->SetActorHiddenInGame(false);
					Comp->SetAttenuationRadius(950.0f);
					Comp->MaxDrawDistance = 0.0f;
					Comp->MaxDistanceFadeRange = 0.0f;
					++LightIndex;
				}
			}
			UE_LOG(LogTemp, Display, TEXT("DoemitzHigh profile applied: %d street point lights active (interior lights untouched)"), LightIndex);
		}
		else
		{
			UE_LOG(LogTemp, Display, TEXT("DoemitzHigh profile applied"));
		}
	}
}
