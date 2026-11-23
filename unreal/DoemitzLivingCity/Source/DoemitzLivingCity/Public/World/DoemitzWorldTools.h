#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "DoemitzWorldTools.generated.h"

/** Editor helpers for the generated Altstadt map (Sprint 14: World Partition streaming setup). */
UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzWorldTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Set cell size and loading range of the map's World Partition runtime grids (runtime hash set partitions or
	 * spatial hash grids, found through reflection because they are not exposed to scripting). Editor only;
	 * returns a report "class: name cell/range -> cell/range; ..." or an error text starting with "ERROR".
	 */
	UFUNCTION(BlueprintCallable, Category = "Doemitz|World", meta = (WorldContext = "WorldContextObject"))
	static FString ConfigureStreamingGrid(UObject* WorldContextObject, int32 CellSizeCm, int32 LoadingRangeCm);

	/** Read-only report of the current runtime grid settings (works in editor and PIE worlds). */
	UFUNCTION(BlueprintCallable, Category = "Doemitz|World", meta = (WorldContext = "WorldContextObject"))
	static FString DescribeStreamingGrid(UObject* WorldContextObject);

	/** True when World Partition streaming has no pending cells around the streaming sources. */
	UFUNCTION(BlueprintCallable, Category = "Doemitz|World", meta = (WorldContext = "WorldContextObject"))
	static bool IsStreamingCompleted(UObject* WorldContextObject);
};
