#pragma once

#include "CoreMinimal.h"
#include "Simulation/DoemitzSimulationTypes.h"
#include "Subsystems/WorldSubsystem.h"
#include "DoemitzTaskSubsystem.generated.h"

class UDoemitzSaveGame;

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzTaskSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	UFUNCTION(BlueprintPure, Category = "Tasks", meta = (WorldContext = "WorldContextObject"))
	static UDoemitzTaskSubsystem* Get(const UObject* WorldContextObject);

	void ConfigureTasks(const UDoemitzTaskDataAsset* InTaskData);
	void GenerateDailyTasks();

	UFUNCTION(BlueprintPure, Category = "Tasks")
	TArray<FDoemitzTaskInstance> GetAllTasks() const { return Tasks; }

	UFUNCTION(BlueprintPure, Category = "Tasks")
	TArray<FDoemitzTaskInstance> GetTasksByStatus(EDoemitzTaskStatus Status) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetTaskById(FName TaskId, FDoemitzTaskInstance& OutTask) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetPrimaryActiveTask(FDoemitzTaskInstance& OutTask) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetTaskOfferedByCitizen(FName CitizenId, FDoemitzTaskInstance& OutTask) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetActiveFetchTaskForCitizen(FName CitizenId, FDoemitzTaskInstance& OutTask) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetActiveErrandForPlace(FName PlaceId, FDoemitzTaskInstance& OutTask, bool& bOutIsDelivery) const;

	UFUNCTION(BlueprintPure, Category = "Tasks")
	bool GetActiveTaskTargetLocation(FVector& OutWorldLocation, FName& OutTargetPlaceId, FName& OutTargetCitizenId) const;

	UFUNCTION(BlueprintCallable, Category = "Tasks")
	bool AcceptTask(FName TaskId);

	UFUNCTION(BlueprintCallable, Category = "Tasks")
	bool PickupTaskParcel(FName TaskId);

	UFUNCTION(BlueprintCallable, Category = "Tasks")
	bool DeliverTaskParcel(FName TaskId);

	UFUNCTION(BlueprintCallable, Category = "Tasks")
	bool CompleteFetchTask(FName TaskId);

	UFUNCTION(BlueprintCallable, Category = "Tasks")
	void CheckTaskDeadlines();

	void CaptureSaveState(UDoemitzSaveGame* SaveObj) const;
	void RestoreSaveState(const UDoemitzSaveGame* SaveObj, bool bMigratingFromPreV5);

private:
	int32 TaskSeed = 202610;
	int32 DailyMinTasks = 3;
	int32 DailyMaxTasks = 5;
	TArray<FDoemitzTaskTemplate> TaskTemplates;
	TArray<FDoemitzTaskInstance> Tasks;
};
