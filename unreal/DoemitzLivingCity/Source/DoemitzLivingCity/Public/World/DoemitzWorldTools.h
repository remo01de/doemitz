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

	/** Read-only report of the current runtime grid and HLOD setup (works in editor and PIE worlds). */
	UFUNCTION(BlueprintCallable, Category = "Doemitz|World", meta = (WorldContext = "WorldContextObject"))
	static FString DescribeStreamingGrid(UObject* WorldContextObject);

	/**
	 * Ensure the project UHLODLayer asset exists (Instancing) and configure the World Partition
	 * default HLOD layer and MainPartition HLOD setup (Sprint 16).
	 * Editor only; returns a report starting with "HLOD_SETUP_OK:" or "ERROR:".
	 */
	UFUNCTION(BlueprintCallable, Category = "Doemitz|World", meta = (WorldContext = "WorldContextObject"))
	static FString ConfigureHLODSetup(UObject* WorldContextObject, const FString& HLODLayerAssetPath, int32 HLODCellSizeCm, int32 HLODLoadingRangeCm);

	/**
	 * Count currently loaded streamed terrain tiles, city cell meshes, World Partition HLOD actors,
	 * and unique loaded cell keys ("cX_Y") in the given world (works in editor and PIE).
	 */
	UFUNCTION(BlueprintCallable, Category = "Doemitz|World", meta = (WorldContext = "WorldContextObject"))
	static void GetStreamingActorCounts(
		UObject* WorldContextObject,
		int32& OutLoadedTerrainTiles,
		int32& OutLoadedCellMeshes,
		int32& OutLoadedHLODActors,
		TArray<FString>& OutLoadedCellKeys);

	/** True when World Partition streaming has no pending cells around the streaming sources. */
	UFUNCTION(BlueprintCallable, Category = "Doemitz|World", meta = (WorldContext = "WorldContextObject"))
	static bool IsStreamingCompleted(UObject* WorldContextObject);
};
