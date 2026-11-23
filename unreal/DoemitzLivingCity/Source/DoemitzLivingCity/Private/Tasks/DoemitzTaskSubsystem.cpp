#include "Tasks/DoemitzTaskSubsystem.h"

#include "Economy/DoemitzEconomySubsystem.h"
#include "Engine/World.h"
#include "Simulation/DoemitzCitizenSubsystem.h"
#include "Simulation/DoemitzSaveGame.h"
#include "Simulation/DoemitzSimulationSubsystem.h"

bool UDoemitzTaskSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}
	const UWorld* World = Cast<UWorld>(Outer);
	return World != nullptr && World->IsGameWorld();
}

UDoemitzTaskSubsystem* UDoemitzTaskSubsystem::Get(const UObject* WorldContextObject)
{
	if (!WorldContextObject)
	{
		return nullptr;
	}
	const UWorld* World = WorldContextObject->GetWorld();
	return World ? World->GetSubsystem<UDoemitzTaskSubsystem>() : nullptr;
}

void UDoemitzTaskSubsystem::ConfigureTasks(const UDoemitzTaskDataAsset* InTaskData)
{
	TaskTemplates.Reset();
	Tasks.Reset();
	TaskSeed = 202610;
	DailyMinTasks = 3;
	DailyMaxTasks = 5;

	if (InTaskData)
	{
		TaskSeed = InTaskData->TaskSeed;
		DailyMinTasks = FMath::Max(1, InTaskData->DailyMinTasks);
		DailyMaxTasks = FMath::Max(DailyMinTasks, InTaskData->DailyMaxTasks);
		TaskTemplates = InTaskData->Templates;
	}

	GenerateDailyTasks();
	UE_LOG(LogTemp, Display, TEXT("Doemitz tasks configured: %d templates, %d daily tasks generated (seed=%d)"),
		TaskTemplates.Num(), Tasks.Num(), TaskSeed);
}

void UDoemitzTaskSubsystem::GenerateDailyTasks()
{
	Tasks.RemoveAll([](const FDoemitzTaskInstance& T) {
		return T.Status == EDoemitzTaskStatus::Available;
	});

	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	const UDoemitzCitizenSubsystem* Citizens = UDoemitzCitizenSubsystem::Get(this);
	if (!Sim || !Citizens || TaskTemplates.IsEmpty() || Citizens->GetCitizenCount() == 0)
	{
		return;
	}

	const int32 DayNumber = Sim->GetDayNumber();
	const int32 DayOfWeek = Sim->GetDayOfWeek();
	const double TimeOfDayMinutes = Sim->GetTimeOfDayMinutes();

	struct FScoredTemplate
	{
		const FDoemitzTaskTemplate* Template = nullptr;
		uint32 Score = 0;
		int32 DeadlineMinute = 1020;
	};
	TArray<FScoredTemplate> EligibleErrands;
	TArray<FScoredTemplate> EligibleFetches;

	for (const FDoemitzTaskTemplate& Tpl : TaskTemplates)
	{
		int32 Deadline = 1020;
		if (Tpl.TaskType == EDoemitzTaskType::Errand)
		{
			int32 PickStart = 0, PickEnd = 0, DelStart = 0, DelEnd = 0;
			if (!Sim->FindOpenWindowOnDay(Tpl.PickupPlaceId, DayOfWeek, PickStart, PickEnd) ||
				!Sim->FindOpenWindowOnDay(Tpl.DeliveryPlaceId, DayOfWeek, DelStart, DelEnd))
			{
				continue;
			}
			const int32 BaseStart = FMath::Max(PickStart, FMath::FloorToInt(TimeOfDayMinutes));
			if (BaseStart + 30 > PickEnd || BaseStart + 30 > DelEnd)
			{
				continue;
			}
			Deadline = FMath::Min(DelEnd, FMath::Max(BaseStart + Tpl.DurationMinutes, DelStart + 90));
			FScoredTemplate Entry;
			Entry.Template = &Tpl;
			Entry.Score = DoemitzSimulationUtil::DeterministicHash(TaskSeed, Tpl.TemplateId, DayNumber * 37 + 11);
			Entry.DeadlineMinute = Deadline;
			EligibleErrands.Add(Entry);
		}
		else
		{
			int32 ShopStart = 0, ShopEnd = 0;
			if (!Sim->FindOpenWindowOnDay(Tpl.PreferredShopPlaceId, DayOfWeek, ShopStart, ShopEnd))
			{
				continue;
			}
			const int32 BaseStart = FMath::Max(ShopStart, FMath::FloorToInt(TimeOfDayMinutes));
			if (BaseStart + 30 > ShopEnd)
			{
				continue;
			}
			Deadline = FMath::Min(ShopEnd, BaseStart + Tpl.DurationMinutes);
			FScoredTemplate Entry;
			Entry.Template = &Tpl;
			Entry.Score = DoemitzSimulationUtil::DeterministicHash(TaskSeed, Tpl.TemplateId, DayNumber * 37 + 23);
			Entry.DeadlineMinute = Deadline;
			EligibleFetches.Add(Entry);
		}
	}

	auto SortByScore = [](const FScoredTemplate& A, const FScoredTemplate& B) {
		if (A.Score != B.Score)
		{
			return A.Score < B.Score;
		}
		return A.Template->TemplateId.LexicalLess(B.Template->TemplateId);
	};
	EligibleErrands.Sort(SortByScore);
	EligibleFetches.Sort(SortByScore);

	const int32 Span = FMath::Max(1, DailyMaxTasks - DailyMinTasks + 1);
	const uint32 CountHash = DoemitzSimulationUtil::DeterministicHash(TaskSeed, FName(TEXT("DailyCount")), DayNumber);
	const int32 TargetCount = DailyMinTasks + static_cast<int32>(CountHash % static_cast<uint32>(Span));

	TArray<FScoredTemplate> Selected;
	int32 ErrIdx = 0;
	int32 FetIdx = 0;
	while (Selected.Num() < TargetCount && (ErrIdx < EligibleErrands.Num() || FetIdx < EligibleFetches.Num()))
	{
		if (ErrIdx < EligibleErrands.Num())
		{
			Selected.Add(EligibleErrands[ErrIdx++]);
		}
		if (Selected.Num() < TargetCount && FetIdx < EligibleFetches.Num())
		{
			Selected.Add(EligibleFetches[FetIdx++]);
		}
	}

	TArray<FName> SortedCitizens = Citizens->GetAllCitizenIds();
	TSet<FName> UsedCitizens;

	for (int32 i = 0; i < Selected.Num(); ++i)
	{
		const FScoredTemplate& Pick = Selected[i];
		const FDoemitzTaskTemplate& Tpl = *Pick.Template;

		FName GiverId = NAME_None;
		if (!SortedCitizens.IsEmpty())
		{
			const uint32 CitHash = DoemitzSimulationUtil::DeterministicHash(TaskSeed, Tpl.TemplateId, DayNumber * 97 + i);
			const int32 StartIdx = static_cast<int32>(CitHash % static_cast<uint32>(SortedCitizens.Num()));
			for (int32 Offset = 0; Offset < SortedCitizens.Num(); ++Offset)
			{
				const FName Candidate = SortedCitizens[(StartIdx + Offset) % SortedCitizens.Num()];
				if (!UsedCitizens.Contains(Candidate))
				{
					GiverId = Candidate;
					UsedCitizens.Add(Candidate);
					break;
				}
			}
		}

		FDoemitzTaskInstance Inst;
		Inst.TaskId = FName(*FString::Printf(TEXT("task:%d:%s"), DayNumber, *Tpl.TemplateId.ToString()));
		Inst.TemplateId = Tpl.TemplateId;
		Inst.TaskType = Tpl.TaskType;
		Inst.Status = EDoemitzTaskStatus::Available;
		Inst.Title = Tpl.Title;
		Inst.Description = Tpl.Description;
		Inst.GiverCitizenId = GiverId;
		Inst.PickupPlaceId = Tpl.PickupPlaceId;
		Inst.DeliveryPlaceId = Tpl.DeliveryPlaceId;
		Inst.ParcelName = Tpl.ParcelName;
		Inst.bPickedUp = false;
		Inst.RequestedItemId = Tpl.RequestedItemId;
		Inst.PreferredShopPlaceId = Tpl.PreferredShopPlaceId;
		Inst.DayNumber = DayNumber;
		Inst.DeadlineMinute = Pick.DeadlineMinute;
		Inst.RewardCents = Tpl.RewardCents;

		const bool bAlreadyExists = Tasks.ContainsByPredicate([&Inst](const FDoemitzTaskInstance& Existing) {
			return Existing.TaskId == Inst.TaskId;
		});
		if (!bAlreadyExists)
		{
			Tasks.Add(MoveTemp(Inst));
		}
	}
}

TArray<FDoemitzTaskInstance> UDoemitzTaskSubsystem::GetTasksByStatus(EDoemitzTaskStatus Status) const
{
	TArray<FDoemitzTaskInstance> Out;
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status == Status)
		{
			Out.Add(Task);
		}
	}
	return Out;
}

bool UDoemitzTaskSubsystem::GetTaskById(FName TaskId, FDoemitzTaskInstance& OutTask) const
{
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.TaskId == TaskId)
		{
			OutTask = Task;
			return true;
		}
	}
	return false;
}

bool UDoemitzTaskSubsystem::GetPrimaryActiveTask(FDoemitzTaskInstance& OutTask) const
{
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status == EDoemitzTaskStatus::Active)
		{
			OutTask = Task;
			return true;
		}
	}
	return false;
}

bool UDoemitzTaskSubsystem::GetTaskOfferedByCitizen(FName CitizenId, FDoemitzTaskInstance& OutTask) const
{
	if (CitizenId.IsNone())
	{
		return false;
	}
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status == EDoemitzTaskStatus::Available && Task.GiverCitizenId == CitizenId)
		{
			OutTask = Task;
			return true;
		}
	}
	return false;
}

bool UDoemitzTaskSubsystem::GetActiveFetchTaskForCitizen(FName CitizenId, FDoemitzTaskInstance& OutTask) const
{
	if (CitizenId.IsNone())
	{
		return false;
	}
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status == EDoemitzTaskStatus::Active &&
			Task.TaskType == EDoemitzTaskType::Fetch &&
			Task.GiverCitizenId == CitizenId)
		{
			OutTask = Task;
			return true;
		}
	}
	return false;
}

bool UDoemitzTaskSubsystem::GetActiveErrandForPlace(FName PlaceId, FDoemitzTaskInstance& OutTask, bool& bOutIsDelivery) const
{
	bOutIsDelivery = false;
	if (PlaceId.IsNone())
	{
		return false;
	}
	for (const FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status == EDoemitzTaskStatus::Active && Task.TaskType == EDoemitzTaskType::Errand)
		{
			if (!Task.bPickedUp && Task.PickupPlaceId == PlaceId)
			{
				OutTask = Task;
				bOutIsDelivery = false;
				return true;
			}
			if (Task.bPickedUp && Task.DeliveryPlaceId == PlaceId)
			{
				OutTask = Task;
				bOutIsDelivery = true;
				return true;
			}
		}
	}
	return false;
}

bool UDoemitzTaskSubsystem::GetActiveTaskTargetLocation(FVector& OutWorldLocation, FName& OutTargetPlaceId, FName& OutTargetCitizenId) const
{
	OutTargetPlaceId = NAME_None;
	OutTargetCitizenId = NAME_None;
	FDoemitzTaskInstance Active;
	if (!GetPrimaryActiveTask(Active))
	{
		return false;
	}

	const UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	if (Active.TaskType == EDoemitzTaskType::Errand)
	{
		const FName TargetPlace = Active.bPickedUp ? Active.DeliveryPlaceId : Active.PickupPlaceId;
		FDoemitzPlaceDefinition Place;
		if (Sim && Sim->GetPlaceDefinition(TargetPlace, Place))
		{
			OutWorldLocation = !Place.EntranceLocation.IsNearlyZero() ? Place.EntranceLocation : Place.AccessLocation;
			OutTargetPlaceId = TargetPlace;
			return true;
		}
		return false;
	}

	const UDoemitzEconomySubsystem* Economy = UDoemitzEconomySubsystem::Get(this);
	if (!Economy || Economy->GetInventoryQuantity(Active.RequestedItemId) < 1)
	{
		FDoemitzPlaceDefinition Shop;
		if (Sim && Sim->GetPlaceDefinition(Active.PreferredShopPlaceId, Shop))
		{
			OutWorldLocation = !Shop.EntranceLocation.IsNearlyZero() ? Shop.EntranceLocation : Shop.AccessLocation;
			OutTargetPlaceId = Active.PreferredShopPlaceId;
			return true;
		}
	}
	if (const UDoemitzCitizenSubsystem* Citizens = UDoemitzCitizenSubsystem::Get(this))
	{
		FDoemitzCitizenState Cit;
		if (Citizens->GetCitizenState(Active.GiverCitizenId, Cit))
		{
			OutWorldLocation = Cit.WorldLocation;
			OutTargetCitizenId = Active.GiverCitizenId;
			return true;
		}
	}
	return false;
}

bool UDoemitzTaskSubsystem::AcceptTask(FName TaskId)
{
	UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	for (FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.TaskId == TaskId && Task.Status == EDoemitzTaskStatus::Available)
		{
			Task.Status = EDoemitzTaskStatus::Active;
			if (Sim)
			{
				FDoemitzNotificationEvent Ev;
				Ev.Code = EDoemitzNotificationCode::TaskAccepted;
				Ev.TaskId = Task.TaskId;
				Ev.MinuteValue = Task.DeadlineMinute;
				Sim->PushNotificationEvent(Ev);
			}
			return true;
		}
	}
	return false;
}

bool UDoemitzTaskSubsystem::PickupTaskParcel(FName TaskId)
{
	UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	if (!Sim)
	{
		return false;
	}
	for (FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.TaskId == TaskId &&
			Task.Status == EDoemitzTaskStatus::Active &&
			Task.TaskType == EDoemitzTaskType::Errand &&
			!Task.bPickedUp)
		{
			if (!Sim->IsPlaceOpenNow(Task.PickupPlaceId))
			{
				FDoemitzNotificationEvent Ev;
				Ev.Code = EDoemitzNotificationCode::PlaceClosed;
				Ev.PlaceId = Task.PickupPlaceId;
				Sim->PushNotificationEvent(Ev);
				return false;
			}
			Task.bPickedUp = true;
			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::TaskParcelPickedUp;
			Ev.TaskId = Task.TaskId;
			Ev.PlaceId = Task.DeliveryPlaceId;
			Sim->PushNotificationEvent(Ev);
			return true;
		}
	}
	return false;
}

bool UDoemitzTaskSubsystem::DeliverTaskParcel(FName TaskId)
{
	UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	UDoemitzEconomySubsystem* Economy = UDoemitzEconomySubsystem::Get(this);
	if (!Sim || !Economy)
	{
		return false;
	}
	for (FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.TaskId == TaskId &&
			Task.Status == EDoemitzTaskStatus::Active &&
			Task.TaskType == EDoemitzTaskType::Errand &&
			Task.bPickedUp)
		{
			if (!Sim->IsPlaceOpenNow(Task.DeliveryPlaceId))
			{
				FDoemitzNotificationEvent Ev;
				Ev.Code = EDoemitzNotificationCode::PlaceClosed;
				Ev.PlaceId = Task.DeliveryPlaceId;
				Sim->PushNotificationEvent(Ev);
				return false;
			}
			Task.Status = EDoemitzTaskStatus::Completed;
			Economy->CreditTaskReward(Task.DeliveryPlaceId, Task.RewardCents, Task.TaskId);

			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::TaskCompleted;
			Ev.TaskId = Task.TaskId;
			Ev.AmountCents = Task.RewardCents;
			Sim->PushNotificationEvent(Ev);
			return true;
		}
	}
	return false;
}

bool UDoemitzTaskSubsystem::CompleteFetchTask(FName TaskId)
{
	UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	UDoemitzEconomySubsystem* Economy = UDoemitzEconomySubsystem::Get(this);
	if (!Sim || !Economy)
	{
		return false;
	}
	for (FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.TaskId == TaskId &&
			Task.Status == EDoemitzTaskStatus::Active &&
			Task.TaskType == EDoemitzTaskType::Fetch)
		{
			if (!Economy->ConsumeInventoryItem(Task.RequestedItemId, 1))
			{
				FDoemitzNotificationEvent Ev;
				Ev.Code = EDoemitzNotificationCode::TaskNeedsItem;
				Ev.TaskId = Task.TaskId;
				Ev.ItemId = Task.RequestedItemId;
				Sim->PushNotificationEvent(Ev);
				return false;
			}
			Task.Status = EDoemitzTaskStatus::Completed;
			Economy->CreditTaskReward(Task.PreferredShopPlaceId, Task.RewardCents, Task.TaskId);

			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::TaskCompleted;
			Ev.TaskId = Task.TaskId;
			Ev.AmountCents = Task.RewardCents;
			Sim->PushNotificationEvent(Ev);
			return true;
		}
	}
	return false;
}

void UDoemitzTaskSubsystem::CheckTaskDeadlines()
{
	UDoemitzSimulationSubsystem* Sim = UDoemitzSimulationSubsystem::Get(this);
	if (!Sim)
	{
		return;
	}
	const int32 DayNumber = Sim->GetDayNumber();
	const double TimeOfDayMinutes = Sim->GetTimeOfDayMinutes();
	for (FDoemitzTaskInstance& Task : Tasks)
	{
		if (Task.Status != EDoemitzTaskStatus::Active)
		{
			continue;
		}
		const bool bExpired = (DayNumber > Task.DayNumber) ||
			(DayNumber == Task.DayNumber && TimeOfDayMinutes >= static_cast<double>(Task.DeadlineMinute));
		if (bExpired)
		{
			Task.Status = EDoemitzTaskStatus::Missed;
			FDoemitzNotificationEvent Ev;
			Ev.Code = EDoemitzNotificationCode::TaskMissed;
			Ev.TaskId = Task.TaskId;
			Sim->PushNotificationEvent(Ev);
		}
	}
}

void UDoemitzTaskSubsystem::CaptureSaveState(UDoemitzSaveGame* SaveObj) const
{
	if (!SaveObj)
	{
		return;
	}
	SaveObj->Tasks = Tasks;
}

void UDoemitzTaskSubsystem::RestoreSaveState(const UDoemitzSaveGame* SaveObj, bool bMigratingFromPreV5)
{
	if (!SaveObj)
	{
		return;
	}
	if (bMigratingFromPreV5)
	{
		Tasks.Reset();
	}
	else
	{
		Tasks = SaveObj->Tasks;
	}
}
