#pragma once

#include "CoreMinimal.h"
#include "Simulation/DoemitzSimulationSubsystem.h"

/**
 * UI-layer text formatting helpers.
 * All visible player-facing German strings are created here as FText with proper umlauts,
 * keeping UDoemitzSimulationSubsystem strictly data-only.
 */
class DOEMITZLIVINGCITY_API FDoemitzUiText
{
public:
	static FText FormatCentsEur(int64 AmountCents);
	static FText FormatWeekdayShort(int32 DayOfWeek);
	static FText FormatTimeHHMM(int32 MinuteOfDay);
	static FText FormatOpeningStatus(const FDoemitzOpeningStatus& Status);
	static FText FormatEntrancePrompt(const FDoemitzPlaceDefinition& Place, const FDoemitzOpeningStatus& Status);
	static FText FormatCitizenActivity(EDoemitzCitizenActivity Activity);
	static FText FormatCitizenPrompt(const FDoemitzCitizenState& Citizen, bool bHasAvailableTask, bool bCanCompleteFetch);
	static FText FormatShiftAvailability(const FDoemitzShiftAvailability& Avail);
	static FText FormatRemainingMinutes(int32 MinutesRemaining);
	static FText FormatTaskGoal(const FDoemitzTaskInstance& Task, const UDoemitzSimulationSubsystem* Subsystem);
	static FText FormatActiveTaskHud(const FDoemitzTaskInstance& Task, const UDoemitzSimulationSubsystem* Subsystem);
	static FText FormatNotification(const FDoemitzNotificationEvent& Event, const UDoemitzSimulationSubsystem* Subsystem);
	static FText GetMapAttributionText();
	static FText FormatNoticeBoardPrompt(int32 AvailableTaskCount);
};
