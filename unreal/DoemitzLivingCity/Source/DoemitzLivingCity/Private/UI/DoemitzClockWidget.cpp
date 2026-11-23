#include "UI/DoemitzClockWidget.h"

#include "Blueprint/WidgetTree.h"
#include "Character/DoemitzCharacter.h"
#include "Components/Border.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "Economy/DoemitzEconomySubsystem.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Interaction/DoemitzInteractionComponent.h"
#include "Settings/DoemitzGraphicsSettings.h"
#include "Simulation/DoemitzCitizenSubsystem.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
#include "Tasks/DoemitzTaskSubsystem.h"
#include "UI/DoemitzUiText.h"

TSharedRef<SWidget> UDoemitzClockWidget::RebuildWidget()
{
	if (WidgetTree && !WidgetTree->RootWidget)
	{
		UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("RootCanvas"));
		WidgetTree->RootWidget = RootCanvas;

		UBorder* Panel = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("ClockPanel"));
		Panel->SetBrushColor(FLinearColor(0.06f, 0.07f, 0.09f, 0.78f));
		Panel->SetPadding(FMargin(14.0f, 10.0f));
		if (UCanvasPanelSlot* PanelSlot = RootCanvas->AddChildToCanvas(Panel))
		{
			PanelSlot->SetAnchors(FAnchors(0.0f, 0.0f, 0.0f, 0.0f));
			PanelSlot->SetPosition(FVector2D(20.0f, 20.0f));
			PanelSlot->SetAutoSize(true);
		}

		UVerticalBox* VBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("ContentBox"));
		Panel->SetContent(VBox);

		ClockText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("ClockText"));
		ClockText->SetColorAndOpacity(FSlateColor(FLinearColor(0.96f, 0.94f, 0.88f, 1.0f)));
		FSlateFontInfo ClockFont = ClockText->GetFont();
		ClockFont.Size = 20;
		ClockText->SetFont(ClockFont);
		VBox->AddChildToVerticalBox(ClockText);

		StatusText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("StatusText"));
		StatusText->SetColorAndOpacity(FSlateColor(FLinearColor(0.82f, 0.86f, 0.90f, 1.0f)));
		FSlateFontInfo StatusFont = StatusText->GetFont();
		StatusFont.Size = 13;
		StatusText->SetFont(StatusFont);
		VBox->AddChildToVerticalBox(StatusText);

		MoneyText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("MoneyText"));
		MoneyText->SetColorAndOpacity(FSlateColor(FLinearColor(0.68f, 0.94f, 0.68f, 1.0f)));
		FSlateFontInfo MoneyFont = MoneyText->GetFont();
		MoneyFont.Size = 13;
		MoneyText->SetFont(MoneyFont);
		VBox->AddChildToVerticalBox(MoneyText);

		ActiveTaskText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("ActiveTaskText"));
		ActiveTaskText->SetColorAndOpacity(FSlateColor(FLinearColor(1.0f, 0.88f, 0.42f, 1.0f)));
		FSlateFontInfo TaskFont = ActiveTaskText->GetFont();
		TaskFont.Size = 12;
		ActiveTaskText->SetFont(TaskFont);
		ActiveTaskText->SetVisibility(ESlateVisibility::Collapsed);
		VBox->AddChildToVerticalBox(ActiveTaskText);

		NoticeText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("NoticeText"));
		NoticeText->SetColorAndOpacity(FSlateColor(FLinearColor(0.95f, 0.82f, 0.45f, 1.0f)));
		FSlateFontInfo NoticeFont = NoticeText->GetFont();
		NoticeFont.Size = 11;
		NoticeText->SetFont(NoticeFont);
		VBox->AddChildToVerticalBox(NoticeText);

		// Bottom-center interaction prompt bar
		PromptPanel = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("PromptPanel"));
		PromptPanel->SetBrushColor(FLinearColor(0.05f, 0.08f, 0.12f, 0.86f));
		PromptPanel->SetPadding(FMargin(18.0f, 10.0f));
		PromptPanel->SetVisibility(ESlateVisibility::Collapsed);
		if (UCanvasPanelSlot* PromptSlot = RootCanvas->AddChildToCanvas(PromptPanel))
		{
			PromptSlot->SetAnchors(FAnchors(0.5f, 1.0f, 0.5f, 1.0f));
			PromptSlot->SetAlignment(FVector2D(0.5f, 1.0f));
			PromptSlot->SetPosition(FVector2D(0.0f, -42.0f));
			PromptSlot->SetAutoSize(true);
		}

		PromptText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("PromptText"));
		PromptText->SetColorAndOpacity(FSlateColor(FLinearColor(0.98f, 0.96f, 0.88f, 1.0f)));
		FSlateFontInfo PromptFont = PromptText->GetFont();
		PromptFont.Size = 16;
		PromptText->SetFont(PromptFont);
		PromptPanel->SetContent(PromptText);
	}
	return Super::RebuildWidget();
}

void UDoemitzClockWidget::NativeConstruct()
{
	Super::NativeConstruct();
	RefreshDisplay();
}

void UDoemitzClockWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);
	RefreshDisplay();
}

void UDoemitzClockWidget::RefreshDisplay()
{
	const UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this);
	if (!Subsystem)
	{
		return;
	}

	const int32 TotalMinutes = FMath::FloorToInt(Subsystem->GetTimeOfDayMinutes()) % 1440;
	const int32 Hours = TotalMinutes / 60;
	const int32 Minutes = TotalMinutes % 60;
	const double Scale = Subsystem->GetTimeScale();
	const double Multiplier = Subsystem->GetTimeScaleMultiplier();
	const FString SpeedLabel = Scale <= 0.0
		? TEXT("Pause")
		: FString::Printf(TEXT("%.0fx"), FMath::Max(1.0, Multiplier));
	const FString DayShort = FDoemitzUiText::FormatWeekdayShort(Subsystem->GetDayOfWeek()).ToString();
	LastClockText = FText::FromString(FString::Printf(
		TEXT("%s, Tag %d  |  %02d:%02d  (%s)"),
		*DayShort,
		Subsystem->GetDayNumber(),
		Hours,
		Minutes,
		*SpeedLabel));

	const UDoemitzCitizenSubsystem* Citizens = UDoemitzCitizenSubsystem::Get(this);
	const UDoemitzEconomySubsystem* Economy = UDoemitzEconomySubsystem::Get(this);
	const UDoemitzTaskSubsystem* Tasks = UDoemitzTaskSubsystem::Get(this);

	int32 MovingCount = 0;
	const TArray<FName> CitizenIds = Citizens ? Citizens->GetAllCitizenIds() : TArray<FName>();
	for (const FName& Id : CitizenIds)
	{
		FDoemitzCitizenState State;
		if (Citizens && Citizens->GetCitizenState(Id, State) && State.bIsMoving)
		{
			MovingCount += 1;
		}
	}
	const FString ProfileLabel = UDoemitzGraphicsSettings::Get()
		? UDoemitzGraphicsSettings::Get()->GetActiveProfileShortLabel()
		: TEXT("Low");
	LastStatusText = FText::FromString(FString::Printf(
		TEXT("D\u00f6mitz  |  %d Einwohner (%d unterwegs, %d nah)  |  Grafik: %s"),
		CitizenIds.Num(),
		MovingCount,
		Citizens ? Citizens->GetActiveCitizenActorCount() : 0,
		*ProfileLabel));

	LastMoneyText = FText::FromString(FString::Printf(
		TEXT("Konto: %s%s"),
		*FDoemitzUiText::FormatCentsEur(Economy ? Economy->GetPlayerMoneyCents() : 0).ToString(),
		(Economy && Economy->IsWorkingShift()) ? TEXT("  |  Schicht aktiv") : TEXT("")));

	FDoemitzTaskInstance ActiveTask;
	if (Tasks && Tasks->GetPrimaryActiveTask(ActiveTask))
	{
		LastActiveTaskText = FDoemitzUiText::FormatActiveTaskHud(ActiveTask, Subsystem);
	}
	else
	{
		LastActiveTaskText = FText::GetEmpty();
	}

	const FDoemitzNotificationEvent NoticeEv = Subsystem->GetLastNotificationEvent();
	const FText FormattedNotice = FDoemitzUiText::FormatNotification(NoticeEv, Subsystem);
	LastNoticeText = FormattedNotice.IsEmpty()
		? FText::FromString(TEXT("M Karte  |  J Aufgaben  |  E Interaktion  |  F5/F9 Speichern/Laden  |  F7 Grafik  |  1/2/3/P Zeit"))
		: FormattedNotice;

	LastPromptText = FText::GetEmpty();
	if (UWorld* World = GetWorld())
	{
		if (const APlayerController* PC = World->GetFirstPlayerController())
		{
			if (const ADoemitzCharacter* Character = Cast<ADoemitzCharacter>(PC->GetPawn()))
			{
				if (const UDoemitzInteractionComponent* Interaction = Character->GetInteractionComponent())
				{
					if (Interaction->HasInteractableTarget() && !Interaction->IsMenuOpen())
					{
						LastPromptText = Interaction->GetInteractionPromptText();
					}
				}
			}
		}
	}

	if (ClockText)
	{
		ClockText->SetText(LastClockText);
	}
	if (StatusText)
	{
		StatusText->SetText(LastStatusText);
	}
	if (MoneyText)
	{
		MoneyText->SetText(LastMoneyText);
	}
	if (ActiveTaskText)
	{
		if (!LastActiveTaskText.IsEmpty())
		{
			ActiveTaskText->SetText(LastActiveTaskText);
			ActiveTaskText->SetVisibility(ESlateVisibility::SelfHitTestInvisible);
		}
		else
		{
			ActiveTaskText->SetVisibility(ESlateVisibility::Collapsed);
		}
	}
	if (NoticeText)
	{
		NoticeText->SetText(LastNoticeText);
	}
	if (PromptPanel && PromptText)
	{
		if (!LastPromptText.IsEmpty())
		{
			PromptText->SetText(LastPromptText);
			PromptPanel->SetVisibility(ESlateVisibility::SelfHitTestInvisible);
		}
		else
		{
			PromptPanel->SetVisibility(ESlateVisibility::Collapsed);
		}
	}
}
