#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "DoemitzSaveSubsystem.generated.h"

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzSaveSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	UFUNCTION(BlueprintPure, Category = "SaveGame", meta = (WorldContext = "WorldContextObject"))
	static UDoemitzSaveSubsystem* Get(const UObject* WorldContextObject);

	UFUNCTION(BlueprintCallable, Category = "SaveGame")
	bool SaveCityState(const FString& SlotName = TEXT("DoemitzQuicksave"));

	UFUNCTION(BlueprintCallable, Category = "SaveGame")
	bool LoadCityState(const FString& SlotName = TEXT("DoemitzQuicksave"));

	UFUNCTION(BlueprintPure, Category = "SaveGame")
	bool DoesSaveExist(const FString& SlotName = TEXT("DoemitzQuicksave")) const;

	UFUNCTION(BlueprintPure, Category = "SaveGame")
	FName GetLastLoadedPlayerInteriorId() const { return LastLoadedPlayerInteriorId; }

private:
	FName LastLoadedPlayerInteriorId;
};
