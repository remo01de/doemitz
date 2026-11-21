#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "DoemitzGraphicsSettings.generated.h"

UENUM(BlueprintType)
enum class EDoemitzGraphicsProfile : uint8
{
	Low UMETA(DisplayName = "DoemitzLow"),
	High UMETA(DisplayName = "DoemitzHigh")
};

UCLASS(Config = GameUserSettings, DefaultConfig, BlueprintType)
class DOEMITZLIVINGCITY_API UDoemitzGraphicsSettings : public UObject
{
	GENERATED_BODY()

public:
	static constexpr const TCHAR* LowProfileName = TEXT("DoemitzLow");
	static constexpr const TCHAR* HighProfileName = TEXT("DoemitzHigh");

	UFUNCTION(BlueprintPure, Category = "Settings")
	static UDoemitzGraphicsSettings* Get();

	UFUNCTION(BlueprintPure, Category = "Settings")
	FString GetSavedProfileName() const { return GraphicsProfile; }

	UFUNCTION(BlueprintPure, Category = "Settings")
	FString GetActiveProfileName() const { return ActiveProfileName.IsEmpty() ? GraphicsProfile : ActiveProfileName; }

	UFUNCTION(BlueprintPure, Category = "Settings")
	EDoemitzGraphicsProfile GetActiveProfile() const;

	UFUNCTION(BlueprintPure, Category = "Settings")
	FString GetActiveProfileShortLabel() const;

	UFUNCTION(BlueprintCallable, Category = "Settings")
	void ApplyActiveProfile(UWorld* World);

	UFUNCTION(BlueprintCallable, Category = "Settings")
	void ApplyProfile(const FString& InProfileName, UWorld* World, bool bSaveToConfig = false);

	UFUNCTION(BlueprintCallable, Category = "Settings")
	FString ToggleProfile(UWorld* World);

	static FString NormalizeProfileName(const FString& InProfileName);

private:
	UPROPERTY(Config)
	FString GraphicsProfile = TEXT("DoemitzLow");

	UPROPERTY(Transient)
	FString ActiveProfileName;
};
