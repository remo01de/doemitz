#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "DoemitzTaskDataAsset.generated.h"

UENUM(BlueprintType)
enum class EDoemitzTaskType : uint8
{
	Errand,
	Fetch
};

UENUM(BlueprintType)
enum class EDoemitzTaskStatus : uint8
{
	Available,
	Active,
	Completed,
	Missed
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzTaskTemplate
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName TemplateId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	EDoemitzTaskType TaskType = EDoemitzTaskType::Errand;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FString Title;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FString Description;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName PickupPlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName DeliveryPlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FString ParcelName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName RequestedItemId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName PreferredShopPlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	int32 DurationMinutes = 180;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	int64 RewardCents = 800;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FString RewardSource;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzTaskInstance
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName TaskId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName TemplateId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	EDoemitzTaskType TaskType = EDoemitzTaskType::Errand;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	EDoemitzTaskStatus Status = EDoemitzTaskStatus::Available;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FString Title;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FString Description;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName GiverCitizenId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName PickupPlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName DeliveryPlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FString ParcelName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	bool bPickedUp = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName RequestedItemId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	FName PreferredShopPlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	int32 DayNumber = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	int32 DeadlineMinute = 1020;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	int64 RewardCents = 800;
};

UCLASS(BlueprintType)
class DOEMITZLIVINGCITY_API UDoemitzTaskDataAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	int32 TaskSeed = 202610;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	int32 DailyMinTasks = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	int32 DailyMaxTasks = 5;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Tasks")
	TArray<FDoemitzTaskTemplate> Templates;
};
