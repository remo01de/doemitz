#include "World/DoemitzWorldTools.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "Engine/Engine.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Misc/PackageName.h"
#include "UObject/SavePackage.h"
#include "UObject/UnrealType.h"
#include "WorldPartition/HLOD/HLODActor.h"
#include "WorldPartition/HLOD/HLODLayer.h"
#include "WorldPartition/RuntimeHashSet/RuntimePartitionLHGrid.h"
#include "WorldPartition/RuntimeHashSet/WorldPartitionRuntimeHashSet.h"
#include "WorldPartition/WorldPartition.h"
#include "WorldPartition/WorldPartitionSubsystem.h"

namespace
{
	UObject* GetRuntimeHash(UWorld* World)
	{
		UWorldPartition* WorldPartition = World ? World->GetWorldPartition() : nullptr;
		if (!WorldPartition)
		{
			return nullptr;
		}
		const FObjectPropertyBase* HashProp = FindFProperty<FObjectPropertyBase>(UWorldPartition::StaticClass(), TEXT("RuntimeHash"));
		return HashProp ? HashProp->GetObjectPropertyValue_InContainer(WorldPartition) : nullptr;
	}

	FString NumberValue(const FProperty* Prop, const void* Container)
	{
		if (const FNumericProperty* Num = CastField<FNumericProperty>(Prop))
		{
			const void* Value = Num->ContainerPtrToValuePtr<void>(Container);
			return Num->IsFloatingPoint() ? FString::SanitizeFloat(Num->GetFloatingPointPropertyValue(Value))
			                              : FString::Printf(TEXT("%lld"), Num->GetSignedIntPropertyValue(Value));
		}
		return TEXT("?");
	}

	bool SetNumber(const FProperty* Prop, void* Container, double NewValue)
	{
		if (const FNumericProperty* Num = CastField<FNumericProperty>(Prop))
		{
			void* Value = Num->ContainerPtrToValuePtr<void>(Container);
			if (Num->IsFloatingPoint())
			{
				Num->SetFloatingPointPropertyValue(Value, NewValue);
			}
			else
			{
				Num->SetIntPropertyValue(Value, static_cast<int64>(NewValue));
			}
			return true;
		}
		return false;
	}

	/** Visit (owner object or struct memory, struct type, label) for every runtime grid of the hash. */
	void ForEachGrid(UObject* Hash, TFunctionRef<void(void*, const UStruct*, UObject*, const FString&)> Visit)
	{
		if (!Hash)
		{
			return;
		}
		// UWorldPartitionRuntimeHashSet: RuntimePartitions[i].MainLayer (URuntimePartition) has LoadingRange/CellSize
		if (const FArrayProperty* Partitions = FindFProperty<FArrayProperty>(Hash->GetClass(), TEXT("RuntimePartitions")))
		{
			const FStructProperty* Inner = CastField<FStructProperty>(Partitions->Inner);
			FScriptArrayHelper Helper(Partitions, Partitions->ContainerPtrToValuePtr<void>(Hash));
			for (int32 Index = 0; Inner && Index < Helper.Num(); ++Index)
			{
				uint8* Element = Helper.GetRawPtr(Index);
				FString Name = TEXT("partition");
				if (const FNameProperty* NameProp = FindFProperty<FNameProperty>(Inner->Struct, TEXT("Name")))
				{
					Name = NameProp->GetPropertyValue_InContainer(Element).ToString();
				}
				if (const FObjectPropertyBase* MainProp = FindFProperty<FObjectPropertyBase>(Inner->Struct, TEXT("MainLayer")))
				{
					if (UObject* Main = MainProp->GetObjectPropertyValue_InContainer(Element))
					{
						Visit(Main, Main->GetClass(), Main, Name);
					}
				}
			}
		}
#if WITH_EDITORONLY_DATA
		// UWorldPartitionRuntimeSpatialHash: Grids[i] (FSpatialHashRuntimeGrid) has CellSize/LoadingRange
		if (const FArrayProperty* Grids = FindFProperty<FArrayProperty>(Hash->GetClass(), TEXT("Grids")))
		{
			const FStructProperty* Inner = CastField<FStructProperty>(Grids->Inner);
			FScriptArrayHelper Helper(Grids, Grids->ContainerPtrToValuePtr<void>(Hash));
			for (int32 Index = 0; Inner && Index < Helper.Num(); ++Index)
			{
				uint8* Element = Helper.GetRawPtr(Index);
				FString Name = TEXT("grid");
				if (const FNameProperty* NameProp = FindFProperty<FNameProperty>(Inner->Struct, TEXT("GridName")))
				{
					Name = NameProp->GetPropertyValue_InContainer(Element).ToString();
				}
				Visit(Element, Inner->Struct, Hash, Name);
			}
		}
#endif
	}
}

FString UDoemitzWorldTools::DescribeStreamingGrid(UObject* WorldContextObject)
{
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull) : nullptr;
	UObject* Hash = GetRuntimeHash(World);
	if (!Hash)
	{
		return TEXT("ERROR: no World Partition runtime hash");
	}
	FString Report = Hash->GetClass()->GetName() + TEXT(":");
	ForEachGrid(Hash, [&Report](void* Container, const UStruct* Type, UObject*, const FString& Name)
	{
		const FProperty* Cell = Type->FindPropertyByName(TEXT("CellSize"));
		const FProperty* Range = Type->FindPropertyByName(TEXT("LoadingRange"));
		Report += FString::Printf(TEXT(" %s cell=%s range=%s;"), *Name,
			Cell ? *NumberValue(Cell, Container) : TEXT("-"), Range ? *NumberValue(Range, Container) : TEXT("-"));
	});
#if WITH_EDITORONLY_DATA
	if (const FArrayProperty* Partitions = FindFProperty<FArrayProperty>(Hash->GetClass(), TEXT("RuntimePartitions")))
	{
		FScriptArrayHelper Helper(Partitions, Partitions->ContainerPtrToValuePtr<void>(Hash));
		for (int32 Index = 0; Index < Helper.Num(); ++Index)
		{
			const FRuntimePartitionDesc* Desc = reinterpret_cast<const FRuntimePartitionDesc*>(Helper.GetRawPtr(Index));
			if (!Desc)
			{
				continue;
			}
			for (const FRuntimePartitionHLODSetup& HLOD : Desc->HLODSetups)
			{
				if (HLOD.PartitionLayer)
				{
					const FProperty* Cell = HLOD.PartitionLayer->GetClass()->FindPropertyByName(TEXT("CellSize"));
					const FProperty* Range = HLOD.PartitionLayer->GetClass()->FindPropertyByName(TEXT("LoadingRange"));
					Report += FString::Printf(TEXT(" HLOD[%s] cell=%s range=%s layers=%d;"),
						*HLOD.Name.ToString(),
						Cell ? *NumberValue(Cell, HLOD.PartitionLayer) : TEXT("-"),
						Range ? *NumberValue(Range, HLOD.PartitionLayer) : TEXT("-"),
						HLOD.HLODLayers.Num());
				}
			}
		}
	}
#endif
	int32 HLODActorCount = 0;
	for (TActorIterator<AWorldPartitionHLOD> It(World); It; ++It)
	{
		if (IsValid(*It))
		{
			++HLODActorCount;
		}
	}
	Report += FString::Printf(TEXT(" hlod_actors=%d;"), HLODActorCount);
	return Report;
}

FString UDoemitzWorldTools::ConfigureHLODSetup(UObject* WorldContextObject, const FString& HLODLayerAssetPath, int32 HLODCellSizeCm, int32 HLODLoadingRangeCm)
{
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull) : nullptr;
	UWorldPartition* WorldPartition = World ? World->GetWorldPartition() : nullptr;
	if (!WorldPartition)
	{
		return TEXT("ERROR: no World Partition");
	}
	if (HLODLayerAssetPath.IsEmpty())
	{
		return TEXT("ERROR: empty HLODLayerAssetPath");
	}

	const FString PackagePath = FPackageName::ObjectPathToPackageName(HLODLayerAssetPath);
	const FString AssetName = FPackageName::GetLongPackageAssetName(PackagePath);
	UHLODLayer* HLODLayer = LoadObject<UHLODLayer>(nullptr, *FString::Printf(TEXT("%s.%s"), *PackagePath, *AssetName));
	if (!HLODLayer)
	{
		UPackage* LayerPackage = CreatePackage(*PackagePath);
		if (!LayerPackage)
		{
			return TEXT("ERROR: could not create HLODLayer package");
		}
		LayerPackage->FullyLoad();
		HLODLayer = NewObject<UHLODLayer>(LayerPackage, *AssetName, RF_Public | RF_Standalone);
		if (!HLODLayer)
		{
			return TEXT("ERROR: could not create UHLODLayer object");
		}
		FAssetRegistryModule::AssetCreated(HLODLayer);
	}

	HLODLayer->Modify();
	HLODLayer->SetLayerType(EHLODLayerType::Instancing);
	HLODLayer->MarkPackageDirty();

	// Save the HLODLayer asset package immediately so WorldPartitionHLODsBuilder can load it from disk.
	UPackage* LayerPackage = HLODLayer->GetOutermost();
	const FString PackageFilename = FPackageName::LongPackageNameToFilename(LayerPackage->GetName(), FPackageName::GetAssetPackageExtension());
	FSavePackageArgs SaveArgs;
	SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
	SaveArgs.SaveFlags = SAVE_NoError;
	if (!UPackage::SavePackage(LayerPackage, HLODLayer, *PackageFilename, SaveArgs))
	{
		return FString::Printf(TEXT("ERROR: could not save HLODLayer to %s"), *PackageFilename);
	}

	UWorldPartitionRuntimeHashSet* HashSet = Cast<UWorldPartitionRuntimeHashSet>(GetRuntimeHash(World));
	if (!HashSet)
	{
		return TEXT("ERROR: expected UWorldPartitionRuntimeHashSet");
	}
	const FArrayProperty* PartitionsProp = FindFProperty<FArrayProperty>(HashSet->GetClass(), TEXT("RuntimePartitions"));
	if (!PartitionsProp)
	{
		return TEXT("ERROR: RuntimePartitions property not found");
	}

	WorldPartition->Modify();
	WorldPartition->SetDefaultHLODLayer(HLODLayer);
	HashSet->Modify();

	FScriptArrayHelper Helper(PartitionsProp, PartitionsProp->ContainerPtrToValuePtr<void>(HashSet));
	if (Helper.Num() == 0)
	{
		return TEXT("ERROR: RuntimePartitions is empty");
	}

	FRuntimePartitionDesc* MainDesc = reinterpret_cast<FRuntimePartitionDesc*>(Helper.GetRawPtr(0));
	if (!MainDesc || !MainDesc->MainLayer)
	{
		return TEXT("ERROR: MainPartition has no MainLayer");
	}

	MainDesc->HLODSetups.Reset();
	FRuntimePartitionHLODSetup& Setup = MainDesc->HLODSetups.AddDefaulted_GetRef();
	Setup.Name = HLODLayer->GetFName();
	Setup.RowDisplayName = HLODLayer->GetFName();
	Setup.HLODLayers.Add(HLODLayer);
	Setup.bIsSpatiallyLoaded = true;

	URuntimePartitionLHGrid* HLODGrid = NewObject<URuntimePartitionLHGrid>(HashSet, NAME_None);
	HLODGrid->SetDefaultValues();
	HLODGrid->Name = Setup.Name;
	HLODGrid->bBlockOnSlowStreaming = false;
	HLODGrid->bClientOnlyVisible = true;
	HLODGrid->Priority = 0;
	HLODGrid->HLODIndex = 0;
	HLODGrid->LoadingRange = FMath::Max(HLODLoadingRangeCm, 51200);
	if (const FProperty* CellProp = HLODGrid->GetClass()->FindPropertyByName(TEXT("CellSize")))
	{
		SetNumber(CellProp, HLODGrid, FMath::Max(HLODCellSizeCm, 25600));
	}
	Setup.PartitionLayer = HLODGrid;

	WorldPartition->MarkPackageDirty();
	HashSet->MarkPackageDirty();
	return FString::Printf(
		TEXT("HLOD_SETUP_OK: layer=%s cell=%d range=%d"),
		*HLODLayer->GetName(),
		FMath::Max(HLODCellSizeCm, 25600),
		FMath::Max(HLODLoadingRangeCm, 51200));
#else
	return TEXT("ERROR: editor only");
#endif
}

void UDoemitzWorldTools::GetStreamingActorCounts(
	UObject* WorldContextObject,
	int32& OutLoadedTerrainTiles,
	int32& OutLoadedCellMeshes,
	int32& OutLoadedHLODActors,
	TArray<FString>& OutLoadedCellKeys)
{
	OutLoadedTerrainTiles = 0;
	OutLoadedCellMeshes = 0;
	OutLoadedHLODActors = 0;
	OutLoadedCellKeys.Reset();

	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull) : nullptr;
	if (!World)
	{
		return;
	}

	TSet<FString> UniqueCells;
	for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
	{
		const AStaticMeshActor* Actor = *It;
		if (!IsValid(Actor))
		{
			continue;
		}
		const UStaticMeshComponent* SMC = Actor->GetStaticMeshComponent();
		const UStaticMesh* Mesh = SMC ? SMC->GetStaticMesh() : nullptr;
		if (!Mesh)
		{
			continue;
		}
		const FString MeshName = Mesh->GetName();
		if (MeshName.StartsWith(TEXT("SM_Terrain_")))
		{
			++OutLoadedTerrainTiles;
		}
		else
		{
			const int32 CellPos = MeshName.Find(TEXT("__c"));
			if (CellPos != INDEX_NONE)
			{
				++OutLoadedCellMeshes;
				UniqueCells.Add(MeshName.Mid(CellPos + 2)); // "cX_Y"
			}
		}
	}

	for (TActorIterator<AWorldPartitionHLOD> It(World); It; ++It)
	{
		if (IsValid(*It))
		{
			++OutLoadedHLODActors;
		}
	}

	OutLoadedCellKeys = UniqueCells.Array();
	OutLoadedCellKeys.Sort();
}

FString UDoemitzWorldTools::ConfigureStreamingGrid(UObject* WorldContextObject, int32 CellSizeCm, int32 LoadingRangeCm)
{
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull) : nullptr;
	UObject* Hash = GetRuntimeHash(World);
	if (!Hash)
	{
		return TEXT("ERROR: no World Partition runtime hash");
	}
	int32 Changed = 0;
	FString Report = Hash->GetClass()->GetName() + TEXT(":");
	ForEachGrid(Hash, [&](void* Container, const UStruct* Type, UObject* Owner, const FString& Name)
	{
		const FProperty* Cell = Type->FindPropertyByName(TEXT("CellSize"));
		const FProperty* Range = Type->FindPropertyByName(TEXT("LoadingRange"));
		const FString Before = FString::Printf(TEXT("%s/%s"), Cell ? *NumberValue(Cell, Container) : TEXT("-"),
			Range ? *NumberValue(Range, Container) : TEXT("-"));
		Owner->Modify();
		if (Cell && CellSizeCm > 0 && SetNumber(Cell, Container, CellSizeCm))
		{
			++Changed;
		}
		if (Range && LoadingRangeCm > 0 && SetNumber(Range, Container, LoadingRangeCm))
		{
			++Changed;
		}
		Report += FString::Printf(TEXT(" %s %s -> %s/%s;"), *Name, *Before,
			Cell ? *NumberValue(Cell, Container) : TEXT("-"), Range ? *NumberValue(Range, Container) : TEXT("-"));
	});
	if (Changed == 0)
	{
		return TEXT("ERROR: no runtime grid found in ") + Report;
	}
	Hash->MarkPackageDirty();
	return Report;
#else
	return TEXT("ERROR: editor only");
#endif
}

bool UDoemitzWorldTools::IsStreamingCompleted(UObject* WorldContextObject)
{
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull) : nullptr;
	if (!World || !World->GetWorldPartition())
	{
		return true;
	}
	if (UWorldPartitionSubsystem* Subsystem = World->GetSubsystem<UWorldPartitionSubsystem>())
	{
		return Subsystem->IsAllStreamingCompleted();
	}
	return true;
}
