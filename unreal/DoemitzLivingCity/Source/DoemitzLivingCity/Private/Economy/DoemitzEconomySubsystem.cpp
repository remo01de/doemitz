#include "Economy/DoemitzEconomySubsystem.h"

#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Simulation/DoemitzSaveGame.h"
#include "Simulation/DoemitzSimulationSubsystem.h"

bool UDoemitzEconomySubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}
	const UWorld* World = Cast<UWorld>(Outer);
	return World != nullptr && World->IsGameWorld();
}

UDoemitzEconomySubsystem* UDoemitzEconomySubsystem::Get(const UObject* WorldContextObject)
{
	if (!WorldContextObject)
	{
		return nullptr;
	}
	const UWorld* World = WorldContextObject->GetWorld();
	return World ? World->GetSubsystem<UDoemitzEconomySubsystem>() : nullptr;
}

void UDoemitzEconomySubsystem::ConfigureEconomy(const UDoemitzEconomyDataAsset* InEconomyData)
{
	AssortmentsByCategory.Reset();
	ItemsById.Reset();
	JobsById.Reset();
	JobIdByPlace.Reset();
	EconomySeed = 202609;
	StartingMoneyCents = 0;

	if (InEconomyData)
	{
		EconomySeed = InEconomyData->EconomySeed;
		StartingMoneyCents = FMath::Max<int64>(0, InEconomyData->StartingMoneyCents);
		for (const FDoemitzAssortmentDefinition& Group : InEconomyData->Assortments)
		{
			if (!Group.Category.IsNone() && !Group.Items.IsEmpty())
			{
				AssortmentsByCategory.Add(Group.Category, Group.Items);
				for (const FDoemitzItemDefinition& Item : Group.Items)
				{
					if (!Item.ItemId.IsNone())
					{
						ItemsById.Add(Item.ItemId, Item);
					}
				}
			}
		}
		for (const FDoemitzJobDefinition& Job : InEconomyData->Jobs)
		{
			if (!Job.JobId.IsNone() && !Job.PlaceId.IsNone())
			{
				JobsById.Add(Job.JobId, Job);
				JobIdByPlace.Add(Job.PlaceId, Job.JobId);
			}
		}
	}

	ResetEconomyToDefaults();
	UE_LOG(LogTemp, Display, TEXT("Doemitz economy configured: start=%lld ct, %d categories, %d jobs (seed=%d)"),
		StartingMoneyCents, AssortmentsByCategory.Num(), JobsById.Num(), EconomySeed);
}

void UDoemitzEconomySubsystem::ResetEconomyToDefaults()
{
	PlayerMoneyCents = StartingMoneyCents;
	NextTransactionId = 1;
	ActiveJobId = NAME_None;
	bIsWorkingShift = false;
	ActiveShiftPlaceId = NAME_None;
	ShiftActualStartMinute = 0.0;
	LedgerEntries.Reset();
	PlayerInventory.Reset();
	PlaceRevenues.Reset();
	CitizenDailyShoppingRecorded.Reset();
}

void UDoemitzEconomySubsystem::OnDayRollover(bool bNewWeek)
{
	CitizenDailyShoppingRecorded.Reset();
	for (TPair<FName, FDoemitzPlaceRevenue>& Pair : PlaceRevenues)
	{
		Pair.Value.DailyRevenueCents = 0;
		if (bNewWeek)
		{
			Pair.Value.WeeklyRevenueCents = 0;
		}
	}
	if (bIsWorkingShift)
	{
		FinishWorkShift();
	}
}

void UDoemitzEconomySubsystem::CancelActiveWorkShiftForLoad()
{
	if (!bIsWorkingShift)
	{
		return;
	}
	bIsWorkingShift = false;
	ActiveShiftPlaceId = NAME_None;
	if (UWorld* World = GetWorld())
	{
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			PC->SetIgnoreMoveInput(false);
			if (APawn* Pawn = PC->GetPawn())
			{
				Pawn->SetActorHiddenInGame(false);
			}
		}
	}
}

void UDoemitzEconomySubsystem::SetPlayerMoneyCentsForTest(int64 NewAmountCents)
{
	PlayerMoneyCents = FMath::Max<int64>(0, NewAmountCents);
}

void UDoemitzEconomySubsystem::AppendLedgerEntry(FName PlaceId, int64 AmountCents, const FString& Description)
{
	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	FDoemitzLedgerEntry Entry;
	Entry.TransactionId = NextTransactionId++;
	Entry.DayNumber = Sim ? Sim->GetDayNumber() : 1;
	Entry.DayOfWeek = Sim ? Sim->GetDayOfWeek() : 0;
	Entry.MinuteOfDay = Sim ? Sim->GetTimeOfDayMinutes() : 0.0;
	Entry.PlaceId = PlaceId;
	Entry.AmountCents = AmountCents;
	Entry.Description = Description;
	LedgerEntries.Add(MoveTemp(Entry));
	if (LedgerEntries.Num() > MaxLedgerEntries)
	{
		LedgerEntries.RemoveAt(0, LedgerEntries.Num() - MaxLedgerEntries);
	}
}

void UDoemitzEconomySubsystem::AddPlaceRevenue(FName PlaceId, int64 AmountCents)
{
	if (PlaceId.IsNone() || AmountCents <= 0)
	{
		return;
	}
	FDoemitzPlaceRevenue& Rev = PlaceRevenues.FindOrAdd(PlaceId);
	Rev.PlaceId = PlaceId;
	Rev.DailyRevenueCents += AmountCents;
	Rev.WeeklyRevenueCents += AmountCents;
}

int32 UDoemitzEconomySubsystem::GetInventoryQuantity(FName ItemId) const
{
	const int32* Qty = PlayerInventory.Find(ItemId);
	return Qty ? *Qty : 0;
}

TArray<FDoemitzInventoryItem> UDoemitzEconomySubsystem::GetAllInventoryItems() const
{
	TArray<FDoemitzInventoryItem> Result;
	Result.Reserve(PlayerInventory.Num());
	for (const TPair<FName, int32>& Pair : PlayerInventory)
	{
		if (Pair.Value > 0)
		{
			FDoemitzInventoryItem Item;
			Item.ItemId = Pair.Key;
			Item.Quantity = Pair.Value;
			Result.Add(Item);
		}
	}
	Result.Sort([](const FDoemitzInventoryItem& A, const FDoemitzInventoryItem& B) {
		return A.ItemId.LexicalLess(B.ItemId);
	});
	return Result;
}

bool UDoemitzEconomySubsystem::GetItemDefinition(FName ItemId, FDoemitzItemDefinition& OutItem) const
{
	if (const FDoemitzItemDefinition* Found = ItemsById.Find(ItemId))
	{
		OutItem = *Found;
		return true;
	}
	return false;
}

TArray<FDoemitzItemDefinition> UDoemitzEconomySubsystem::GetItemsForPlace(FName PlaceId) const
{
	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	FDoemitzPlaceDefinition Place;
	if (!Sim || !Sim->GetPlaceDefinition(PlaceId, Place))
	{
		return {};
	}
	const FName Cat = !Place.EconomyCategory.IsNone() ? Place.EconomyCategory : Place.Kind;
	if (const TArray<FDoemitzItemDefinition>* Items = AssortmentsByCategory.Find(Cat))
	{
		return *Items;
	}
	if (const TArray<FDoemitzItemDefinition>* Fallback = AssortmentsByCategory.Find(Place.Kind))
	{
		return *Fallback;
	}
	return {};
}

bool UDoemitzEconomySubsystem::BuyItem(FName PlaceId, FName ItemId, int32 Quantity)
{
	UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	if (!Sim || Quantity <= 0 || PlaceId.IsNone() || ItemId.IsNone() || !Sim->HasPlace(PlaceId))
	{
		return false;
	}
	if (!Sim->IsPlaceOpenNow(PlaceId))
	{
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::PlaceClosed;
		Ev.PlaceId = PlaceId;
		Sim->PushNotificationEvent(Ev);
		return false;
	}

	const TArray<FDoemitzItemDefinition> Items = GetItemsForPlace(PlaceId);
	const FDoemitzItemDefinition* FoundItem = Items.FindByPredicate([ItemId](const FDoemitzItemDefinition& Item) {
		return Item.ItemId == ItemId;
	});
	if (!FoundItem || FoundItem->PriceCents <= 0)
	{
		return false;
	}

	const int64 TotalCost = FoundItem->PriceCents * static_cast<int64>(Quantity);
	if (PlayerMoneyCents < TotalCost)
	{
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::InsufficientFunds;
		Ev.PlaceId = PlaceId;
		Ev.ItemId = ItemId;
		Ev.AmountCents = TotalCost;
		Ev.SecondaryAmountCents = PlayerMoneyCents;
		Sim->PushNotificationEvent(Ev);
		return false;
	}

	PlayerMoneyCents -= TotalCost;
	PlayerInventory.FindOrAdd(ItemId) += Quantity;
	AddPlaceRevenue(PlaceId, TotalCost);
	AppendLedgerEntry(PlaceId, -TotalCost, FString::Printf(TEXT("BUY:%s:%d"), *ItemId.ToString(), Quantity));

	FDoemitzNotificationEvent Ev;
	Ev.Code = EDoemitzNotificationCode::ItemPurchased;
	Ev.PlaceId = PlaceId;
	Ev.ItemId = ItemId;
	Ev.Quantity = Quantity;
	Ev.AmountCents = TotalCost;
	Sim->PushNotificationEvent(Ev);
	return true;
}

bool UDoemitzEconomySubsystem::GetJobForPlace(FName PlaceId, FDoemitzJobDefinition& OutJob) const
{
	if (const FName* JobId = JobIdByPlace.Find(PlaceId))
	{
		if (const FDoemitzJobDefinition* Job = JobsById.Find(*JobId))
		{
			OutJob = *Job;
			return true;
		}
	}
	return false;
}

bool UDoemitzEconomySubsystem::GetJobDefinition(FName JobId, FDoemitzJobDefinition& OutJob) const
{
	if (const FDoemitzJobDefinition* Job = JobsById.Find(JobId))
	{
		OutJob = *Job;
		return true;
	}
	return false;
}

bool UDoemitzEconomySubsystem::AcceptJob(FName PlaceId)
{
	UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	FDoemitzJobDefinition Job;
	if (!Sim || !GetJobForPlace(PlaceId, Job))
	{
		return false;
	}
	if (!Sim->IsPlaceOpenNow(PlaceId))
	{
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::JobNeedsOpenPlace;
		Ev.PlaceId = PlaceId;
		Sim->PushNotificationEvent(Ev);
		return false;
	}
	ActiveJobId = Job.JobId;
	FDoemitzNotificationEvent Ev;
	Ev.Code = EDoemitzNotificationCode::JobAccepted;
	Ev.PlaceId = PlaceId;
	Ev.JobId = Job.JobId;
	Ev.AmountCents = Job.HourlyWageCents;
	Sim->PushNotificationEvent(Ev);
	return true;
}

FDoemitzShiftAvailability UDoemitzEconomySubsystem::CheckWorkShiftAvailability(FName PlaceId) const
{
	FDoemitzShiftAvailability Out;
	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	if (!Sim)
	{
		return Out;
	}
	if (bIsWorkingShift)
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::AlreadyWorking;
		return Out;
	}
	FDoemitzJobDefinition Job;
	if (!GetJobForPlace(PlaceId, Job))
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::NoJobAtPlace;
		return Out;
	}
	Out.ShiftStartMinute = Job.ShiftStartMinute;
	if (ActiveJobId != Job.JobId)
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::JobNotAccepted;
		return Out;
	}
	if (!Job.WorkDays.Contains(Sim->GetDayOfWeek()))
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::NotAWorkDay;
		return Out;
	}
	const double TimeOfDayMinutes = Sim->GetTimeOfDayMinutes();
	const double EarliestStart = FMath::Max(0.0, static_cast<double>(Job.ShiftStartMinute) - 30.0);
	if (TimeOfDayMinutes < EarliestStart)
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::TooEarly;
		return Out;
	}
	if (TimeOfDayMinutes >= static_cast<double>(Job.ShiftEndMinute))
	{
		Out.bCanStart = false;
		Out.Result = EDoemitzShiftCheckResult::ShiftEnded;
		return Out;
	}
	Out.bCanStart = true;
	Out.Result = EDoemitzShiftCheckResult::Ready;
	return Out;
}

bool UDoemitzEconomySubsystem::StartWorkShift(FName PlaceId)
{
	UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	if (!Sim)
	{
		return false;
	}
	const FDoemitzShiftAvailability Avail = CheckWorkShiftAvailability(PlaceId);
	if (!Avail.bCanStart)
	{
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::ShiftUnavailable;
		Ev.PlaceId = PlaceId;
		Ev.ShiftResult = Avail.Result;
		Ev.MinuteValue = Avail.ShiftStartMinute;
		Sim->PushNotificationEvent(Ev);
		return false;
	}
	FDoemitzJobDefinition Job;
	if (!GetJobForPlace(PlaceId, Job))
	{
		return false;
	}

	bIsWorkingShift = true;
	ActiveShiftPlaceId = PlaceId;
	ShiftActualStartMinute = FMath::Max(Sim->GetTimeOfDayMinutes(), static_cast<double>(Job.ShiftStartMinute));
	const double BaseScale = Sim->GetBaseTimeScale();
	PreShiftTimeScale = Sim->GetTimeScale() > 0.0 ? Sim->GetTimeScale() : BaseScale;
	Sim->SetTimeScale(BaseScale * 15.0); // 15x fast-forward relative to BaseTimeScale during shift

	if (UWorld* World = GetWorld())
	{
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			PC->SetIgnoreMoveInput(true);
			if (APawn* Pawn = PC->GetPawn())
			{
				Pawn->SetActorHiddenInGame(true);
			}
		}
	}

	FDoemitzNotificationEvent Ev;
	Ev.Code = EDoemitzNotificationCode::ShiftStarted;
	Ev.PlaceId = PlaceId;
	Ev.JobId = Job.JobId;
	Ev.MinuteValue = Job.ShiftEndMinute;
	Sim->PushNotificationEvent(Ev);
	return true;
}

void UDoemitzEconomySubsystem::UpdateActiveWorkShift()
{
	if (!bIsWorkingShift)
	{
		return;
	}
	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	const FDoemitzJobDefinition* Job = JobsById.Find(ActiveJobId);
	if (!Sim || !Job)
	{
		FinishWorkShift();
		return;
	}
	if (Sim->GetTimeOfDayMinutes() >= static_cast<double>(Job->ShiftEndMinute))
	{
		FinishWorkShift();
	}
}

void UDoemitzEconomySubsystem::FinishWorkShift()
{
	if (!bIsWorkingShift)
	{
		return;
	}
	bIsWorkingShift = false;

	UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	if (Sim)
	{
		Sim->SetTimeScale(FMath::Max(Sim->GetBaseTimeScale(), PreShiftTimeScale));
	}

	if (UWorld* World = GetWorld())
	{
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			PC->SetIgnoreMoveInput(false);
			if (APawn* Pawn = PC->GetPawn())
			{
				Pawn->SetActorHiddenInGame(false);
			}
		}
	}

	if (const FDoemitzJobDefinition* Job = JobsById.Find(ActiveJobId))
	{
		const double ScheduledMinutes = FMath::Max(1.0, static_cast<double>(Job->ShiftEndMinute - Job->ShiftStartMinute));
		const double WorkedMinutes = FMath::Clamp(static_cast<double>(Job->ShiftEndMinute) - ShiftActualStartMinute, 0.0, ScheduledMinutes);
		const int64 PayCents = FMath::RoundToInt64((static_cast<double>(Job->HourlyWageCents) * WorkedMinutes) / 60.0);
		if (PayCents > 0)
		{
			PlayerMoneyCents += PayCents;
			AppendLedgerEntry(Job->PlaceId, PayCents, FString::Printf(TEXT("WAGE:%s"), *Job->JobId.ToString()));
		}
		if (Sim)
		{
			const bool bLate = ShiftActualStartMinute > static_cast<double>(Job->ShiftStartMinute) + 0.5;
			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::ShiftFinished;
			Ev.JobId = Job->JobId;
			Ev.AmountCents = PayCents;
			Ev.bFlag = bLate;
			Sim->PushNotificationEvent(Ev);
		}
	}
	ActiveShiftPlaceId = NAME_None;
}

void UDoemitzEconomySubsystem::RecordCitizenShoppingRevenue(FName CitizenId, FName PlaceId)
{
	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	if (!Sim || CitizenId.IsNone() || PlaceId.IsNone() || !Sim->IsPlaceOpenNow(PlaceId))
	{
		return;
	}
	const FName DailyKey(*FString::Printf(TEXT("%s@%s"), *CitizenId.ToString(), *PlaceId.ToString()));
	if (CitizenDailyShoppingRecorded.Contains(DailyKey))
	{
		return;
	}
	const TArray<FDoemitzItemDefinition> Items = GetItemsForPlace(PlaceId);
	if (Items.IsEmpty())
	{
		return;
	}
	CitizenDailyShoppingRecorded.Add(DailyKey);
	const uint32 Hash = DoemitzSimulationUtil::DeterministicHash(
		EconomySeed,
		CitizenId,
		Sim->GetDayNumber() * 131 + static_cast<int32>(FCrc::StrCrc32(*PlaceId.ToString())));
	const FDoemitzItemDefinition& Picked = Items[static_cast<int32>(Hash % static_cast<uint32>(Items.Num()))];
	const int32 Qty = 1 + static_cast<int32>((Hash >> 8) % 2);
	AddPlaceRevenue(PlaceId, Picked.PriceCents * static_cast<int64>(Qty));
}

bool UDoemitzEconomySubsystem::ConsumeInventoryItem(FName ItemId, int32 Quantity)
{
	if (Quantity <= 0 || ItemId.IsNone())
	{
		return false;
	}
	int32* QtyPtr = PlayerInventory.Find(ItemId);
	if (!QtyPtr || *QtyPtr < Quantity)
	{
		return false;
	}
	*QtyPtr -= Quantity;
	if (*QtyPtr <= 0)
	{
		PlayerInventory.Remove(ItemId);
	}
	return true;
}

void UDoemitzEconomySubsystem::CreditTaskReward(FName PlaceId, int64 RewardCents, FName TaskId)
{
	if (RewardCents > 0)
	{
		PlayerMoneyCents += RewardCents;
		AppendLedgerEntry(PlaceId, RewardCents, FString::Printf(TEXT("TASK:%s"), *TaskId.ToString()));
	}
}

bool UDoemitzEconomySubsystem::GetPlaceRevenue(FName PlaceId, int64& OutDailyCents, int64& OutWeeklyCents) const
{
	if (const FDoemitzPlaceRevenue* Rev = PlaceRevenues.Find(PlaceId))
	{
		OutDailyCents = Rev->DailyRevenueCents;
		OutWeeklyCents = Rev->WeeklyRevenueCents;
		return true;
	}
	OutDailyCents = 0;
	OutWeeklyCents = 0;
	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	return Sim ? Sim->HasPlace(PlaceId) : false;
}

void UDoemitzEconomySubsystem::CaptureSaveState(UDoemitzSaveGame* SaveObj) const
{
	if (!SaveObj)
	{
		return;
	}
	SaveObj->PlayerMoneyCents = PlayerMoneyCents;
	SaveObj->NextTransactionId = NextTransactionId;
	SaveObj->ActiveJobId = ActiveJobId;
	SaveObj->LedgerEntries = LedgerEntries;
	SaveObj->InventoryItems = GetAllInventoryItems();
	SaveObj->PlaceRevenues.Reset();
	for (const TPair<FName, FDoemitzPlaceRevenue>& Pair : PlaceRevenues)
	{
		SaveObj->PlaceRevenues.Add(Pair.Value);
	}
}

void UDoemitzEconomySubsystem::RestoreSaveState(const UDoemitzSaveGame* SaveObj, bool bMigratingFromPreV4)
{
	if (!SaveObj)
	{
		return;
	}
	if (bMigratingFromPreV4)
	{
		ResetEconomyToDefaults();
		return;
	}
	PlayerMoneyCents = FMath::Max<int64>(0, SaveObj->PlayerMoneyCents);
	NextTransactionId = FMath::Max(1, SaveObj->NextTransactionId);
	ActiveJobId = SaveObj->ActiveJobId;
	LedgerEntries = SaveObj->LedgerEntries;
	if (LedgerEntries.Num() > MaxLedgerEntries)
	{
		LedgerEntries.RemoveAt(0, LedgerEntries.Num() - MaxLedgerEntries);
	}
	PlayerInventory.Reset();
	for (const FDoemitzInventoryItem& Item : SaveObj->InventoryItems)
	{
		if (!Item.ItemId.IsNone() && Item.Quantity > 0)
		{
			PlayerInventory.Add(Item.ItemId, Item.Quantity);
		}
	}
	PlaceRevenues.Reset();
	for (const FDoemitzPlaceRevenue& Rev : SaveObj->PlaceRevenues)
	{
		if (!Rev.PlaceId.IsNone())
		{
			PlaceRevenues.Add(Rev.PlaceId, Rev);
		}
	}
	CitizenDailyShoppingRecorded.Reset();
}
