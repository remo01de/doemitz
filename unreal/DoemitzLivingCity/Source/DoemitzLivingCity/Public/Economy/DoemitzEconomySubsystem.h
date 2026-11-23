#pragma once

#include "CoreMinimal.h"
#include "Simulation/DoemitzSimulationTypes.h"
#include "Subsystems/WorldSubsystem.h"
#include "DoemitzEconomySubsystem.generated.h"

class UDoemitzSaveGame;

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzEconomySubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	UFUNCTION(BlueprintPure, Category = "Economy", meta = (WorldContext = "WorldContextObject"))
	static UDoemitzEconomySubsystem* Get(const UObject* WorldContextObject);

	void ConfigureEconomy(const UDoemitzEconomyDataAsset* InEconomyData);
	void ResetEconomyToDefaults();
	void OnDayRollover(bool bNewWeek);
	void UpdateActiveWorkShift();
	void CancelActiveWorkShiftForLoad();

	UFUNCTION(BlueprintPure, Category = "Economy")
	int64 GetPlayerMoneyCents() const { return PlayerMoneyCents; }

	UFUNCTION(BlueprintCallable, Category = "Economy")
	void SetPlayerMoneyCentsForTest(int64 NewAmountCents);

	UFUNCTION(BlueprintPure, Category = "Economy")
	int32 GetLedgerCount() const { return LedgerEntries.Num(); }

	UFUNCTION(BlueprintPure, Category = "Economy")
	TArray<FDoemitzLedgerEntry> GetLedgerEntries() const { return LedgerEntries; }

	UFUNCTION(BlueprintPure, Category = "Economy")
	int32 GetInventoryQuantity(FName ItemId) const;

	UFUNCTION(BlueprintPure, Category = "Economy")
	TArray<FDoemitzInventoryItem> GetAllInventoryItems() const;

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool GetItemDefinition(FName ItemId, FDoemitzItemDefinition& OutItem) const;

	UFUNCTION(BlueprintPure, Category = "Economy")
	TArray<FDoemitzItemDefinition> GetItemsForPlace(FName PlaceId) const;

	UFUNCTION(BlueprintCallable, Category = "Economy")
	bool BuyItem(FName PlaceId, FName ItemId, int32 Quantity = 1);

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool GetJobForPlace(FName PlaceId, FDoemitzJobDefinition& OutJob) const;

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool GetJobDefinition(FName JobId, FDoemitzJobDefinition& OutJob) const;

	UFUNCTION(BlueprintPure, Category = "Economy")
	FName GetActiveJobId() const { return ActiveJobId; }

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool IsWorkingShift() const { return bIsWorkingShift; }

	double GetPreShiftTimeScale() const { return PreShiftTimeScale; }

	UFUNCTION(BlueprintCallable, Category = "Economy")
	bool AcceptJob(FName PlaceId);

	UFUNCTION(BlueprintPure, Category = "Economy")
	FDoemitzShiftAvailability CheckWorkShiftAvailability(FName PlaceId) const;

	UFUNCTION(BlueprintCallable, Category = "Economy")
	bool StartWorkShift(FName PlaceId);

	UFUNCTION(BlueprintPure, Category = "Economy")
	bool GetPlaceRevenue(FName PlaceId, int64& OutDailyCents, int64& OutWeeklyCents) const;

	void RecordCitizenShoppingRevenue(FName CitizenId, FName PlaceId);
	bool ConsumeInventoryItem(FName ItemId, int32 Quantity = 1);
	void CreditTaskReward(FName PlaceId, int64 RewardCents, FName TaskId);

	void CaptureSaveState(UDoemitzSaveGame* SaveObj) const;
	void RestoreSaveState(const UDoemitzSaveGame* SaveObj, bool bMigratingFromPreV4);

private:
	void AppendLedgerEntry(FName PlaceId, int64 AmountCents, const FString& Description);
	void AddPlaceRevenue(FName PlaceId, int64 AmountCents);
	void FinishWorkShift();

	static constexpr int32 MaxLedgerEntries = 200;
	int32 EconomySeed = 202609;
	int64 StartingMoneyCents = 0;
	int64 PlayerMoneyCents = 0;
	int32 NextTransactionId = 1;
	FName ActiveJobId;
	bool bIsWorkingShift = false;
	FName ActiveShiftPlaceId;
	double ShiftActualStartMinute = 0.0;
	double PreShiftTimeScale = 20.0;

	TMap<FName, TArray<FDoemitzItemDefinition>> AssortmentsByCategory;
	TMap<FName, FDoemitzItemDefinition> ItemsById;
	TMap<FName, FDoemitzJobDefinition> JobsById;
	TMap<FName, FName> JobIdByPlace;
	TArray<FDoemitzLedgerEntry> LedgerEntries;
	TMap<FName, int32> PlayerInventory;
	TMap<FName, FDoemitzPlaceRevenue> PlaceRevenues;
	TSet<FName> CitizenDailyShoppingRecorded;
};
