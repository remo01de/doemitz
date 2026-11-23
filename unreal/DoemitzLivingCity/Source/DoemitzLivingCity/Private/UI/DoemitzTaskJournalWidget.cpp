#include "UI/DoemitzTaskJournalWidget.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
#include "Tasks/DoemitzTaskSubsystem.h"
#include "UI/DoemitzUiText.h"

TSharedRef<SWidget> UDoemitzTaskJournalWidget::RebuildWidget()
{
	if (WidgetTree && !WidgetTree->RootWidget)
	{
		UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("TaskJournalRoot"));
		WidgetTree->RootWidget = RootCanvas;

		UBorder* Panel = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("TaskJournalPanel"));
		Panel->SetBrushColor(FLinearColor(0.06f, 0.08f, 0.11f, 0.93f));
		Panel->SetPadding(FMargin(20.0f, 16.0f));
		if (UCanvasPanelSlot* PanelSlot = RootCanvas->AddChildToCanvas(Panel))
		{
			PanelSlot->SetAnchors(FAnchors(0.5f, 0.5f, 0.5f, 0.5f));
			PanelSlot->SetAlignment(FVector2D(0.5f, 0.5f));
			PanelSlot->SetPosition(FVector2D(0.0f, 0.0f));
			PanelSlot->SetSize(FVector2D(620.0f, 540.0f));
		}

		UVerticalBox* MainBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("MainBox"));
		Panel->SetContent(MainBox);

		UHorizontalBox* HeaderRow = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("HeaderRow"));
		MainBox->AddChildToVerticalBox(HeaderRow);

		UTextBlock* Title = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("TitleText"));
		Title->SetText(FText::FromString(TEXT("Aufgabenbuch")));
		Title->SetColorAndOpacity(FSlateColor(FLinearColor(0.98f, 0.95f, 0.86f, 1.0f)));
		FSlateFontInfo TitleFont = Title->GetFont();
		TitleFont.Size = 20;
		Title->SetFont(TitleFont);
		if (UHorizontalBoxSlot* TitleSlot = HeaderRow->AddChildToHorizontalBox(Title))
		{
			TitleSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
		}

		UButton* CloseBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), TEXT("CloseButton"));
		CloseBtn->OnClicked.AddDynamic(this, &UDoemitzTaskJournalWidget::HandleCloseClicked);
		UTextBlock* CloseLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CloseLabel"));
		CloseLbl->SetText(FText::FromString(TEXT("Schlie\u00dfen [J/Esc]")));
		FSlateFontInfo BtnFont = CloseLbl->GetFont();
		BtnFont.Size = 12;
		CloseLbl->SetFont(BtnFont);
		CloseBtn->AddChild(CloseLbl);
		HeaderRow->AddChildToHorizontalBox(CloseBtn);

		SummaryText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("SummaryText"));
		SummaryText->SetColorAndOpacity(FSlateColor(FLinearColor(0.78f, 0.88f, 0.95f, 1.0f)));
		FSlateFontInfo SumFont = SummaryText->GetFont();
		SumFont.Size = 12;
		SummaryText->SetFont(SumFont);
		if (UVerticalBoxSlot* SumSlot = MainBox->AddChildToVerticalBox(SummaryText))
		{
			SumSlot->SetPadding(FMargin(0.0f, 4.0f, 0.0f, 10.0f));
		}

		ListBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("ListBox"));
		MainBox->AddChildToVerticalBox(ListBox);
	}
	return Super::RebuildWidget();
}

void UDoemitzTaskJournalWidget::NativeConstruct()
{
	Super::NativeConstruct();
	RefreshContents();
}

FString UDoemitzTaskJournalWidget::GetSummaryTextString() const
{
	return SummaryText ? SummaryText->GetText().ToString() : FString();
}

void UDoemitzTaskJournalWidget::RefreshContents()
{
	const UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this);
	const UDoemitzTaskSubsystem* Tasks = UDoemitzTaskSubsystem::Get(this);
	if (!Subsystem || !Tasks || !WidgetTree || !ListBox)
	{
		return;
	}

	const TArray<FDoemitzTaskInstance> Active = Tasks->GetTasksByStatus(EDoemitzTaskStatus::Active);
	const TArray<FDoemitzTaskInstance> Completed = Tasks->GetTasksByStatus(EDoemitzTaskStatus::Completed);
	const TArray<FDoemitzTaskInstance> Missed = Tasks->GetTasksByStatus(EDoemitzTaskStatus::Missed);
	const TArray<FDoemitzTaskInstance> Available = Tasks->GetTasksByStatus(EDoemitzTaskStatus::Available);

	if (SummaryText)
	{
		SummaryText->SetText(FText::FromString(FString::Printf(
			TEXT("Aktiv: %d  |  Erledigt: %d  |  Verpasst: %d  |  Heute verf\u00fcgbar bei Einwohnern: %d"),
			Active.Num(),
			Completed.Num(),
			Missed.Num(),
			Available.Num())));
	}

	ListBox->ClearChildren();

	auto AddSection = [this, Subsystem](const FText& Header, const TArray<FDoemitzTaskInstance>& Items, const FLinearColor& HeaderColor, bool bShowGoal) {
		UTextBlock* SecLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
		SecLbl->SetText(Header);
		SecLbl->SetColorAndOpacity(FSlateColor(HeaderColor));
		FSlateFontInfo Fnt = SecLbl->GetFont();
		Fnt.Size = 14;
		SecLbl->SetFont(Fnt);
		if (UVerticalBoxSlot* S = ListBox->AddChildToVerticalBox(SecLbl))
		{
			S->SetPadding(FMargin(0.0f, 8.0f, 0.0f, 3.0f));
		}

		Fnt.Size = 11;
		if (Items.IsEmpty())
		{
			UTextBlock* Empty = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			Empty->SetText(FText::FromString(TEXT("  (keine)")));
			Empty->SetColorAndOpacity(FSlateColor(FLinearColor(0.62f, 0.65f, 0.70f, 1.0f)));
			Empty->SetFont(Fnt);
			ListBox->AddChildToVerticalBox(Empty);
			return;
		}

		for (const FDoemitzTaskInstance& Task : Items)
		{
			FString Line;
			if (bShowGoal)
			{
				const int32 RemMin = FMath::Max(0, Task.DeadlineMinute - FMath::FloorToInt(Subsystem->GetTimeOfDayMinutes()));
				Line = FString::Printf(
					TEXT("  \u2022 %s  |  %s  |  bis %02d:%02d (%s)  |  +%s"),
					*Task.Title,
					*FDoemitzUiText::FormatTaskGoal(Task, Subsystem).ToString(),
					Task.DeadlineMinute / 60,
					Task.DeadlineMinute % 60,
					*FDoemitzUiText::FormatRemainingMinutes(RemMin).ToString(),
					*FDoemitzUiText::FormatCentsEur(Task.RewardCents).ToString());
			}
			else if (Task.Status == EDoemitzTaskStatus::Completed)
			{
				Line = FString::Printf(
					TEXT("  \u2022 Tag %d: %s  (+%s)"),
					Task.DayNumber,
					*Task.Title,
					*FDoemitzUiText::FormatCentsEur(Task.RewardCents).ToString());
			}
			else
			{
				Line = FString::Printf(
					TEXT("  \u2022 Tag %d: %s  (Frist %02d:%02d verpasst)"),
					Task.DayNumber,
					*Task.Title,
					Task.DeadlineMinute / 60,
					Task.DeadlineMinute % 60);
			}
			UTextBlock* Entry = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			Entry->SetText(FText::FromString(Line));
			Entry->SetAutoWrapText(true);
			Entry->SetColorAndOpacity(FSlateColor(FLinearColor(0.90f, 0.92f, 0.94f, 1.0f)));
			Entry->SetFont(Fnt);
			if (UVerticalBoxSlot* S = ListBox->AddChildToVerticalBox(Entry))
			{
				S->SetPadding(FMargin(0.0f, 2.0f));
			}
		}
	};

	AddSection(FText::FromString(TEXT("Aktive Aufgaben")), Active, FLinearColor(0.98f, 0.86f, 0.42f, 1.0f), true);
	AddSection(FText::FromString(TEXT("Erledigte Aufgaben")), Completed, FLinearColor(0.55f, 0.92f, 0.58f, 1.0f), false);
	AddSection(FText::FromString(TEXT("Verpasste Aufgaben")), Missed, FLinearColor(0.92f, 0.48f, 0.44f, 1.0f), false);
}

void UDoemitzTaskJournalWidget::HandleCloseClicked()
{
	OnCloseRequested.ExecuteIfBound();
}
