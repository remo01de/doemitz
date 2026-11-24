#pragma once

#include "CoreMinimal.h"
#include "Simulation/DoemitzSimulationTypes.h"
#include "Subsystems/WorldSubsystem.h"
#include "DoemitzSaveSubsystem.generated.h"

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzSaveSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Tick(float DeltaTime) override;
	virtual bool IsTickable() const override { return PendingRestore.bActive; }
	virtual TStatId GetStatId() const override;

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

	/** True while LoadCityState is waiting for World Partition cells around the loaded player location to finish streaming. */
	UFUNCTION(BlueprintPure, Category = "SaveGame")
	bool IsPendingStreamingRestore() const { return PendingRestore.bActive; }

private:
	struct FPendingStreamingRestore
	{
		bool bActive = false;
		FString SlotName;
		int32 SaveSchemaVersion = 0;
		bool bHasPlayerTransform = false;
		FVector TargetPlayerLocation = FVector::ZeroVector;
		FRotator TargetPlayerRotation = FRotator::ZeroRotator;
		bool bHasSavedInterior = false;
		FDoemitzInteriorDefinition SavedInterior;
		bool bRemovedInteriorFallback = false;
		FName PlayerInteriorId = NAME_None;
		FName PlayerInteriorPlaceId = NAME_None;
		bool bMigratingFromPreV6 = false;
		bool bRestoreGravity = false;
		float SavedGravityScale = 1.0f;
		double ElapsedSeconds = 0.0;
		double MaxWaitSeconds = 10.0;
	};

	void FinalizeLoadedGroundSnap();
	void CancelPendingRestore();

	FName LastLoadedPlayerInteriorId;
	FPendingStreamingRestore PendingRestore;
};
