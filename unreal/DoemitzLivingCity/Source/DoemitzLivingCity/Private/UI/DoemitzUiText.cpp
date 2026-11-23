#include "UI/DoemitzUiText.h"

#include "Economy/DoemitzEconomySubsystem.h"
#include "Simulation/DoemitzCitizenSubsystem.h"
#include "Tasks/DoemitzTaskSubsystem.h"

FText FDoemitzUiText::FormatCentsEur(int64 AmountCents)
{
	const bool bNegative = AmountCents < 0;
	const uint64 AbsCents = bNegative ? static_cast<uint64>(-AmountCents) : static_cast<uint64>(AmountCents);
	const uint64 Euros = AbsCents / 100;
	const uint64 Cents = AbsCents % 100;
	return FText::FromString(FString::Printf(TEXT("%s%llu,%02llu EUR"), bNegative ? TEXT("-") : TEXT(""), Euros, Cents));
}

FText FDoemitzUiText::FormatWeekdayShort(int32 DayOfWeek)
{
	static const TCHAR* ShortNames[7] = {
		TEXT("Mo"), TEXT("Di"), TEXT("Mi"), TEXT("Do"), TEXT("Fr"), TEXT("Sa"), TEXT("So")
	};
	const int32 Clamped = ((DayOfWeek % 7) + 7) % 7;
	return FText::FromString(ShortNames[Clamped]);
}

FText FDoemitzUiText::FormatTimeHHMM(int32 MinuteOfDay)
{
	const int32 Clamped = FMath::Clamp(MinuteOfDay, 0, 1439);
	return FText::FromString(FString::Printf(TEXT("%02d:%02d"), Clamped / 60, Clamped % 60));
}

FText FDoemitzUiText::FormatOpeningStatus(const FDoemitzOpeningStatus& Status)
{
	if (!Status.bKnown)
	{
		return FText::FromString(TEXT("unbekannt"));
	}
	if (Status.bAlwaysOpen)
	{
		return FText::FromString(TEXT("ge\u00f6ffnet 24/7"));
	}
	if (Status.bOpen)
	{
		if (Status.bHasNextChange)
		{
			return FText::FromString(FString::Printf(
				TEXT("ge\u00f6ffnet bis %02d:%02d"),
				Status.NextChangeMinute / 60,
				Status.NextChangeMinute % 60));
		}
		return FText::FromString(TEXT("ge\u00f6ffnet"));
	}
	if (Status.bHasNextChange)
	{
		return FText::FromString(FString::Printf(
			TEXT("geschlossen, \u00f6ffnet %s %02d:%02d"),
			*FormatWeekdayShort(Status.NextChangeWeekday).ToString(),
			Status.NextChangeMinute / 60,
			Status.NextChangeMinute % 60));
	}
	return FText::FromString(TEXT("geschlossen"));
}

FText FDoemitzUiText::FormatEntrancePrompt(const FDoemitzPlaceDefinition& Place, const FDoemitzOpeningStatus& Status)
{
	const FText StatusTxt = FormatOpeningStatus(Status);
	if (Status.bOpen)
	{
		return FText::FromString(FString::Printf(
			TEXT("E \u2013 %s (%s)"),
			*Place.DisplayName,
			*StatusTxt.ToString()));
	}
	return FText::FromString(FString::Printf(
		TEXT("%s (%s)"),
		*Place.DisplayName,
		*StatusTxt.ToString()));
}

FText FDoemitzUiText::FormatCitizenActivity(EDoemitzCitizenActivity Activity)
{
	switch (Activity)
	{
	case EDoemitzCitizenActivity::Home:
		return FText::FromString(TEXT("Zuhause"));
	case EDoemitzCitizenActivity::Commuting:
		return FText::FromString(TEXT("Unterwegs"));
	case EDoemitzCitizenActivity::Working:
		return FText::FromString(TEXT("Bei der Arbeit"));
	case EDoemitzCitizenActivity::Shopping:
		return FText::FromString(TEXT("Beim Einkaufen"));
	case EDoemitzCitizenActivity::Strolling:
		return FText::FromString(TEXT("Beim Spaziergang"));
	default:
		return FText::FromString(TEXT("In der Stadt"));
	}
}

FText FDoemitzUiText::FormatCitizenPrompt(const FDoemitzCitizenState& Citizen, bool bHasAvailableTask, bool bCanCompleteFetch)
{
	const FString ActivityStr = FormatCitizenActivity(Citizen.CurrentActivity).ToString();
	if (bCanCompleteFetch)
	{
		return FText::FromString(FString::Printf(
			TEXT("E \u2013 %s (%s \u00b7 Besorgung \u00fcbergeben)"),
			*Citizen.DisplayName,
			*ActivityStr));
	}
	if (bHasAvailableTask)
	{
		return FText::FromString(FString::Printf(
			TEXT("E \u2013 %s (%s \u00b7 Aufgabe verf\u00fcgbar)"),
			*Citizen.DisplayName,
			*ActivityStr));
	}
	return FText::FromString(FString::Printf(
		TEXT("E \u2013 %s (%s)"),
		*Citizen.DisplayName,
		*ActivityStr));
}

FText FDoemitzUiText::FormatShiftAvailability(const FDoemitzShiftAvailability& Avail)
{
	switch (Avail.Result)
	{
	case EDoemitzShiftCheckResult::Ready:
		return FText::FromString(TEXT("Bereit"));
	case EDoemitzShiftCheckResult::AlreadyWorking:
		return FText::FromString(TEXT("Schicht l\u00e4uft bereits"));
	case EDoemitzShiftCheckResult::NoJobAtPlace:
		return FText::FromString(TEXT("Keine Stelle an diesem Ort"));
	case EDoemitzShiftCheckResult::JobNotAccepted:
		return FText::FromString(TEXT("Stelle noch nicht angenommen"));
	case EDoemitzShiftCheckResult::NotAWorkDay:
		return FText::FromString(TEXT("Heute kein Arbeitstag"));
	case EDoemitzShiftCheckResult::TooEarly:
		return FText::FromString(FString::Printf(
			TEXT("Schicht beginnt erst um %02d:%02d"),
			Avail.ShiftStartMinute / 60,
			Avail.ShiftStartMinute % 60));
	case EDoemitzShiftCheckResult::ShiftEnded:
		return FText::FromString(TEXT("Heutige Schicht bereits vorbei"));
	default:
		return FText::FromString(TEXT("Nicht verf\u00fcgbar"));
	}
}

FText FDoemitzUiText::FormatRemainingMinutes(int32 MinutesRemaining)
{
	const int32 Clamped = FMath::Max(0, MinutesRemaining);
	const int32 Hours = Clamped / 60;
	const int32 Mins = Clamped % 60;
	if (Hours > 0)
	{
		return FText::FromString(FString::Printf(TEXT("noch %d Std. %02d Min."), Hours, Mins));
	}
	return FText::FromString(FString::Printf(TEXT("noch %d Min."), Mins));
}

FText FDoemitzUiText::FormatTaskGoal(const FDoemitzTaskInstance& Task, const UDoemitzSimulationSubsystem* Subsystem)
{
	if (!Subsystem)
	{
		return FText::FromString(Task.Title);
	}
	if (Task.TaskType == EDoemitzTaskType::Errand)
	{
		FDoemitzPlaceDefinition Place;
		if (!Task.bPickedUp)
		{
			const FString PlaceName = Subsystem->GetPlaceDefinition(Task.PickupPlaceId, Place)
				? Place.DisplayName
				: Task.PickupPlaceId.ToString();
			return FText::FromString(FString::Printf(TEXT("Abholen (%s): %s"), *Task.ParcelName, *PlaceName));
		}
		const FString PlaceName = Subsystem->GetPlaceDefinition(Task.DeliveryPlaceId, Place)
			? Place.DisplayName
			: Task.DeliveryPlaceId.ToString();
		return FText::FromString(FString::Printf(TEXT("Abgeben (%s): %s"), *Task.ParcelName, *PlaceName));
	}

	const UDoemitzEconomySubsystem* Economy = UDoemitzEconomySubsystem::Get(Subsystem);
	const UDoemitzCitizenSubsystem* Citizens = UDoemitzCitizenSubsystem::Get(Subsystem);

	FDoemitzItemDefinition Item;
	const FString ItemName = (Economy && Economy->GetItemDefinition(Task.RequestedItemId, Item))
		? Item.DisplayName
		: Task.RequestedItemId.ToString();
	const int32 OwnedQty = Economy ? Economy->GetInventoryQuantity(Task.RequestedItemId) : 0;
	if (OwnedQty < 1)
	{
		FDoemitzPlaceDefinition Shop;
		const FString ShopName = Subsystem->GetPlaceDefinition(Task.PreferredShopPlaceId, Shop)
			? Shop.DisplayName
			: Task.PreferredShopPlaceId.ToString();
		return FText::FromString(FString::Printf(TEXT("Kaufen: %s (%s)"), *ItemName, *ShopName));
	}
	FDoemitzCitizenState Cit;
	const FString CitName = (Citizens && Citizens->GetCitizenState(Task.GiverCitizenId, Cit))
		? Cit.DisplayName
		: Task.GiverCitizenId.ToString();
	return FText::FromString(FString::Printf(TEXT("%s zu %s bringen"), *ItemName, *CitName));
}

FText FDoemitzUiText::FormatActiveTaskHud(const FDoemitzTaskInstance& Task, const UDoemitzSimulationSubsystem* Subsystem)
{
	if (!Subsystem)
	{
		return FText::GetEmpty();
	}
	const int32 RemMin = FMath::Max(0, Task.DeadlineMinute - FMath::FloorToInt(Subsystem->GetTimeOfDayMinutes()));
	const FText GoalText = FormatTaskGoal(Task, Subsystem);
	const FText RemText = FormatRemainingMinutes(RemMin);
	return FText::FromString(FString::Printf(
		TEXT("Aufgabe: %s  |  %s  |  bis %02d:%02d (%s)"),
		*Task.Title,
		*GoalText.ToString(),
		Task.DeadlineMinute / 60,
		Task.DeadlineMinute % 60,
		*RemText.ToString()));
}

FText FDoemitzUiText::FormatNotification(const FDoemitzNotificationEvent& Event, const UDoemitzSimulationSubsystem* Subsystem)
{
	if (Event.Code == EDoemitzNotificationCode::None)
	{
		return FText::GetEmpty();
	}

	const UDoemitzEconomySubsystem* Economy = Subsystem ? UDoemitzEconomySubsystem::Get(Subsystem) : nullptr;
	const UDoemitzTaskSubsystem* Tasks = Subsystem ? UDoemitzTaskSubsystem::Get(Subsystem) : nullptr;

	auto GetPlaceName = [Subsystem](FName PlaceId) -> FString {
		FDoemitzPlaceDefinition Place;
		if (Subsystem && Subsystem->GetPlaceDefinition(PlaceId, Place))
		{
			return Place.DisplayName;
		}
		return PlaceId.ToString();
	};
	auto GetItemName = [Economy](FName ItemId) -> FString {
		FDoemitzItemDefinition Item;
		if (Economy && Economy->GetItemDefinition(ItemId, Item))
		{
			return Item.DisplayName;
		}
		return ItemId.ToString();
	};
	auto GetJobTitle = [Economy](FName JobId) -> FString {
		FDoemitzJobDefinition Job;
		if (Economy && Economy->GetJobDefinition(JobId, Job))
		{
			return Job.Title;
		}
		return JobId.ToString();
	};
	auto GetTaskTitle = [Tasks](FName TaskId) -> FString {
		FDoemitzTaskInstance Task;
		if (Tasks && Tasks->GetTaskById(TaskId, Task))
		{
			return Task.Title;
		}
		return TaskId.ToString();
	};

	switch (Event.Code)
	{
	case EDoemitzNotificationCode::PlaceClosed:
	{
		const FText OpenTxt = Subsystem ? FormatOpeningStatus(Subsystem->GetPlaceOpeningStatus(Event.PlaceId)) : FText::FromString(TEXT("geschlossen"));
		return FText::FromString(FString::Printf(TEXT("%s ist geschlossen (%s)"), *GetPlaceName(Event.PlaceId), *OpenTxt.ToString()));
	}
	case EDoemitzNotificationCode::InsufficientFunds:
		return FText::FromString(FString::Printf(
			TEXT("Nicht genug Geld f\u00fcr %s (%s ben\u00f6tigt, Konto %s)"),
			*GetItemName(Event.ItemId),
			*FormatCentsEur(Event.AmountCents).ToString(),
			*FormatCentsEur(Event.SecondaryAmountCents).ToString()));
	case EDoemitzNotificationCode::ItemPurchased:
		return FText::FromString(FString::Printf(
			TEXT("Gekauft: %dx %s (-%s)"),
			Event.Quantity,
			*GetItemName(Event.ItemId),
			*FormatCentsEur(Event.AmountCents).ToString()));
	case EDoemitzNotificationCode::JobNeedsOpenPlace:
		return FText::FromString(TEXT("Stelle kann nur w\u00e4hrend der \u00d6ffnungszeiten angenommen werden"));
	case EDoemitzNotificationCode::JobAccepted:
		return FText::FromString(FString::Printf(
			TEXT("Stelle angenommen: %s (%s/Std.)"),
			*GetJobTitle(Event.JobId),
			*FormatCentsEur(Event.AmountCents).ToString()));
	case EDoemitzNotificationCode::ShiftUnavailable:
	{
		FDoemitzShiftAvailability Avail;
		Avail.Result = Event.ShiftResult;
		Avail.ShiftStartMinute = Event.MinuteValue;
		return FormatShiftAvailability(Avail);
	}
	case EDoemitzNotificationCode::ShiftStarted:
		return FText::FromString(FString::Printf(
			TEXT("Schicht gestartet: %s (bis %02d:%02d, 15x)"),
			*GetJobTitle(Event.JobId),
			Event.MinuteValue / 60,
			Event.MinuteValue % 60));
	case EDoemitzNotificationCode::ShiftFinished:
		return FText::FromString(FString::Printf(
			TEXT("Schicht beendet: +%s%s"),
			*FormatCentsEur(Event.AmountCents).ToString(),
			Event.bFlag ? TEXT(" (anteilig wegen Versp\u00e4tung)") : TEXT("")));
	case EDoemitzNotificationCode::TaskAccepted:
		return FText::FromString(FString::Printf(
			TEXT("Aufgabe angenommen: %s (bis %02d:%02d)"),
			*GetTaskTitle(Event.TaskId),
			Event.MinuteValue / 60,
			Event.MinuteValue % 60));
	case EDoemitzNotificationCode::TaskParcelPickedUp:
		return FText::FromString(FString::Printf(
			TEXT("Abgeholt! Jetzt abgeben bei: %s"),
			*GetPlaceName(Event.PlaceId)));
	case EDoemitzNotificationCode::TaskCompleted:
		return FText::FromString(FString::Printf(
			TEXT("Aufgabe erledigt: %s (+%s)"),
			*GetTaskTitle(Event.TaskId),
			*FormatCentsEur(Event.AmountCents).ToString()));
	case EDoemitzNotificationCode::TaskMissed:
		return FText::FromString(FString::Printf(
			TEXT("Frist verpasst: %s (ohne Belohnung abgebrochen)"),
			*GetTaskTitle(Event.TaskId)));
	case EDoemitzNotificationCode::TaskNeedsItem:
		return FText::FromString(FString::Printf(
			TEXT("Artikel ben\u00f6tigt: %s"),
			*GetItemName(Event.ItemId)));
	case EDoemitzNotificationCode::SaveSucceeded:
		return FText::FromString(FString::Printf(TEXT("Gespeichert: %s"), *Event.ParameterKey));
	case EDoemitzNotificationCode::LoadSucceeded:
		return FText::FromString(FString::Printf(TEXT("Geladen: %s"), *Event.ParameterKey));
	case EDoemitzNotificationCode::NoSaveFound:
		return FText::FromString(TEXT("Kein Spielstand vorhanden"));
	case EDoemitzNotificationCode::TimeScaleChanged:
		return FText::FromString(FString::Printf(TEXT("Zeit: %s"), *Event.ParameterKey));
	case EDoemitzNotificationCode::TimePaused:
		return FText::FromString(TEXT("Zeit: Pause"));
	case EDoemitzNotificationCode::TimeResumed:
		return FText::FromString(TEXT("Zeit: Fortgesetzt"));
	case EDoemitzNotificationCode::GraphicsProfileChanged:
		return FText::FromString(FString::Printf(TEXT("Grafikprofil: %s"), *Event.ParameterKey));
	default:
		return FText::GetEmpty();
	}
}

FText FDoemitzUiText::GetMapAttributionText()
{
	return FText::FromString(TEXT("Kartendaten \u00a9 OpenStreetMap contributors, ODbL 1.0  |  Geobasisdaten (DGM1/LoD2) \u00a9 GeoBasis-DE/M-V 2025/2026"));
}

FText FDoemitzUiText::FormatNoticeBoardPrompt(int32 AvailableTaskCount)
{
	return FText::FromString(FString::Printf(
		TEXT("E – Aushang lesen (%d Aufgabe%s heute)"),
		AvailableTaskCount,
		AvailableTaskCount == 1 ? TEXT("") : TEXT("n")));
}
