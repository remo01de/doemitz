#include "World/DoemitzWorldTools.h"

#include "Engine/Engine.h"
#include "Engine/World.h"
#include "UObject/UnrealType.h"
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
	return Report;
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
