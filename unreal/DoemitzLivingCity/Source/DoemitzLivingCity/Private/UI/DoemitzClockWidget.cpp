#include "UI/DoemitzClockWidget.h"

#include "Blueprint/WidgetTree.h"
#include "Character/DoemitzCharacter.h"
#include "Components/Border.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Interaction/DoemitzInteractionComponent.h"
#include "Settings/DoemitzGraphicsSettings.h"
#include "Simulation/DoemitzSimulationSubsystem.h"

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
	const FString SpeedLabel = Scale <= 0.0
		? TEXT("Pause")
		: FString::Printf(TEXT("%.0fx"), FMath::Max(1.0, Scale / 60.0));
	const FString DayShort = Subsystem->GetDayOfWeekShortName();
	LastClockString = FString::Printf(
		TEXT("%s, Tag %d  |  %02d:%02d  (%s)"),
		*DayShort,
		Subsystem->GetDayNumber(),
		Hours,
		Minutes,
		*SpeedLabel);

	int32 MovingCount = 0;
	const TArray<FName> CitizenIds = Subsystem->GetAllCitizenIds();
	for (const FName& Id : CitizenIds)
	{
		FDoemitzCitizenState State;
		if (Subsystem->GetCitizenState(Id, State) && State.bIsMoving)
		{
			MovingCount += 1;
		}
	}
	const FString ProfileLabel = UDoemitzGraphicsSettings::Get()
		? UDoemitzGraphicsSettings::Get()->GetActiveProfileShortLabel()
		: TEXT("Low");
	LastStatusString = FString::Printf(
		TEXT("Doemitz Altstadt  |  %d Einwohner (%d unterwegs, %d nah)  |  Grafik: %s"),
		CitizenIds.Num(),
		MovingCount,
		Subsystem->GetActiveCitizenActorCount(),
		*ProfileLabel);

	LastMoneyString = FString::Printf(
		TEXT("Konto: %s%s"),
		*UDoemitzSimulationSubsystem::FormatCentsEur(Subsystem->GetPlayerMoneyCents()),
		Subsystem->IsWorkingShift() ? TEXT("  |  Schicht aktiv") : TEXT(""));

	const FString ActiveNotice = Subsystem->GetLastNotification();
	LastNoticeString = ActiveNotice.IsEmpty()
		? TEXT("E Interaktion  |  F5 Speichern  |  F9 Laden  |  F7 Grafik  |  1/2/3/P Zeit")
		: ActiveNotice;

	LastPromptString.Reset();
	if (UWorld* World = GetWorld())
	{
		if (const APlayerController* PC = World->GetFirstPlayerController())
		{
			if (const ADoemitzCharacter* Character = Cast<ADoemitzCharacter>(PC->GetPawn()))
			{
				if (const UDoemitzInteractionComponent* Interaction = Character->GetInteractionComponent())
				{
					if (Interaction->HasInteractableEntrance() && !Interaction->IsMenuOpen())
					{
						LastPromptString = Interaction->GetInteractionPrompt();
					}
				}
			}
		}
	}

	if (ClockText)
	{
		ClockText->SetText(FText::FromString(LastClockString));
	}
	if (StatusText)
	{
		StatusText->SetText(FText::FromString(LastStatusString));
	}
	if (MoneyText)
	{
		MoneyText->SetText(FText::FromString(LastMoneyString));
	}
	if (NoticeText)
	{
		NoticeText->SetText(FText::FromString(LastNoticeString));
	}
	if (PromptPanel && PromptText)
	{
		if (!LastPromptString.IsEmpty())
		{
			PromptText->SetText(FText::FromString(LastPromptString));
			PromptPanel->SetVisibility(ESlateVisibility::SelfHitTestInvisible);
		}
		else
		{
			PromptPanel->SetVisibility(ESlateVisibility::Collapsed);
		}
	}
}
