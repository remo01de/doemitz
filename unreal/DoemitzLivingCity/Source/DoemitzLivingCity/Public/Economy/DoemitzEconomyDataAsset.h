#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "DoemitzEconomyDataAsset.generated.h"

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzItemDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FName ItemId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FString DisplayName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int64 PriceCents = 100;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FString PriceSource;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzAssortmentDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FName Category;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	TArray<FDoemitzItemDefinition> Items;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzJobDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FName JobId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FName PlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FString Title;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int32 ShiftStartMinute = 540;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int32 ShiftEndMinute = 780;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int64 HourlyWageCents = 1400;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	TArray<int32> WorkDays;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FString WageSource;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzLedgerEntry
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int32 TransactionId = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int32 DayNumber = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int32 DayOfWeek = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	double MinuteOfDay = 0.0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FName PlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int64 AmountCents = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FString Description;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzInventoryItem
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FName ItemId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int32 Quantity = 0;
};

USTRUCT(BlueprintType)
struct DOEMITZLIVINGCITY_API FDoemitzPlaceRevenue
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FName PlaceId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int64 DailyRevenueCents = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int64 WeeklyRevenueCents = 0;
};

UCLASS(BlueprintType)
class DOEMITZLIVINGCITY_API UDoemitzEconomyDataAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int32 EconomySeed = 202609;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	int64 StartingMoneyCents = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	FString StartingMoneySource;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	TArray<FDoemitzAssortmentDefinition> Assortments;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Economy")
	TArray<FDoemitzJobDefinition> Jobs;
};
