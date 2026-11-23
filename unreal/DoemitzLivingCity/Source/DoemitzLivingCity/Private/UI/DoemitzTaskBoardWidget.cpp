#include "UI/DoemitzTaskBoardWidget.h"

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

TSharedRef<SWidget> UDoemitzTaskBoardWidget::RebuildWidget()
{
	if (WidgetTree && !WidgetTree->RootWidget)
	{
		UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("TaskBoardRoot"));
		WidgetTree->RootWidget = RootCanvas;

		UBorder* Panel = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("TaskBoardPanel"));
		Panel->SetBrushColor(FLinearColor(0.20f, 0.14f, 0.08f, 0.95f));
		Panel->SetPadding(FMargin(20.0f, 16.0f));
		if (UCanvasPanelSlot* PanelSlot = RootCanvas->AddChildToCanvas(Panel))
		{
			PanelSlot->SetAnchors(FAnchors(0.5f, 0.5f, 0.5f, 0.5f));
			PanelSlot->SetAlignment(FVector2D(0.5f, 0.5f));
			PanelSlot->SetPosition(FVector2D(0.0f, 0.0f));
			PanelSlot->SetSize(FVector2D(660.0f, 560.0f));
		}

		UVerticalBox* MainBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("MainBox"));
		Panel->SetContent(MainBox);

		UHorizontalBox* HeaderRow = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("HeaderRow"));
		MainBox->AddChildToVerticalBox(HeaderRow);

		UTextBlock* Title = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("TitleText"));
		Title->SetText(FText::FromString(TEXT("Aushang im Bürgerbüro")));
		Title->SetColorAndOpacity(FSlateColor(FLinearColor(0.99f, 0.94f, 0.82f, 1.0f)));
		FSlateFontInfo TitleFont = Title->GetFont();
		TitleFont.Size = 20;
		Title->SetFont(TitleFont);
		if (UHorizontalBoxSlot* TitleSlot = HeaderRow->AddChildToHorizontalBox(Title))
		{
			TitleSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
		}

		UButton* CloseBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), TEXT("CloseButton"));
		CloseBtn->OnClicked.AddDynamic(this, &UDoemitzTaskBoardWidget::HandleCloseClicked);
		UTextBlock* CloseLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CloseLabel"));
		CloseLbl->SetText(FText::FromString(TEXT("Schließen [E]")));
		FSlateFontInfo BtnFont = CloseLbl->GetFont();
		BtnFont.Size = 12;
		CloseLbl->SetFont(BtnFont);
		CloseBtn->AddChild(CloseLbl);
		HeaderRow->AddChildToHorizontalBox(CloseBtn);

		SummaryText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("SummaryText"));
		SummaryText->SetColorAndOpacity(FSlateColor(FLinearColor(0.93f, 0.86f, 0.70f, 1.0f)));
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

void UDoemitzTaskBoardWidget::NativeConstruct()
{
	Super::NativeConstruct();
	RefreshContents();
}

FString UDoemitzTaskBoardWidget::GetSummaryTextString() const
{
	return SummaryText ? SummaryText->GetText().ToString() : FString();
}

void UDoemitzTaskBoardWidget::RefreshContents()
{
	const UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this);
	const UDoemitzTaskSubsystem* Tasks = UDoemitzTaskSubsystem::Get(this);
	OfferedTaskIds.Reset();
	if (!Subsystem || !Tasks)
	{
		return;
	}
	const TArray<FDoemitzTaskInstance> Offers = Tasks->GetTasksByStatus(EDoemitzTaskStatus::Available);
	for (const FDoemitzTaskInstance& Task : Offers)
	{
		if (OfferedTaskIds.Num() >= MaxRows)
		{
			break;
		}
		OfferedTaskIds.Add(Task.TaskId);
	}

	if (SummaryText)
	{
		SummaryText->SetText(FText::FromString(FString::Printf(
			TEXT("Heute ausgehängt: %d Aufgabe(n). Annehmen trägt sie ins Aufgabenbuch [J] ein."),
			OfferedTaskIds.Num())));
	}
	if (!WidgetTree || !ListBox)
	{
		return;
	}
	ListBox->ClearChildren();

	if (OfferedTaskIds.IsEmpty())
	{
		UTextBlock* Empty = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
		Empty->SetText(FText::FromString(TEXT("Zurzeit hängen keine Aufgaben aus.")));
		Empty->SetColorAndOpacity(FSlateColor(FLinearColor(0.80f, 0.75f, 0.66f, 1.0f)));
		ListBox->AddChildToVerticalBox(Empty);
		return;
	}

	static const FName HandlerNames[MaxRows] = {
		GET_FUNCTION_NAME_CHECKED(UDoemitzTaskBoardWidget, HandleAccept0),
		GET_FUNCTION_NAME_CHECKED(UDoemitzTaskBoardWidget, HandleAccept1),
		GET_FUNCTION_NAME_CHECKED(UDoemitzTaskBoardWidget, HandleAccept2),
		GET_FUNCTION_NAME_CHECKED(UDoemitzTaskBoardWidget, HandleAccept3),
		GET_FUNCTION_NAME_CHECKED(UDoemitzTaskBoardWidget, HandleAccept4),
		GET_FUNCTION_NAME_CHECKED(UDoemitzTaskBoardWidget, HandleAccept5),
	};

	for (int32 Row = 0; Row < OfferedTaskIds.Num(); ++Row)
	{
		FDoemitzTaskInstance Task;
		if (!Tasks->GetTaskById(OfferedTaskIds[Row], Task))
		{
			continue;
		}
		UHorizontalBox* RowBox = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass());
		UTextBlock* Line = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
		Line->SetText(FText::FromString(FString::Printf(
			TEXT("%s\n%s  |  bis %02d:%02d  |  +%s"),
			*Task.Title,
			*FDoemitzUiText::FormatTaskGoal(Task, Subsystem).ToString(),
			Task.DeadlineMinute / 60,
			Task.DeadlineMinute % 60,
			*FDoemitzUiText::FormatCentsEur(Task.RewardCents).ToString())));
		Line->SetAutoWrapText(true);
		Line->SetColorAndOpacity(FSlateColor(FLinearColor(0.97f, 0.95f, 0.90f, 1.0f)));
		FSlateFontInfo Fnt = Line->GetFont();
		Fnt.Size = 11;
		Line->SetFont(Fnt);
		if (UHorizontalBoxSlot* LineSlot = RowBox->AddChildToHorizontalBox(Line))
		{
			LineSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
			LineSlot->SetPadding(FMargin(0.0f, 0.0f, 10.0f, 0.0f));
		}
		UButton* AcceptBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass());
		FScriptDelegate Delegate;
		Delegate.BindUFunction(this, HandlerNames[Row]);
		AcceptBtn->OnClicked.Add(Delegate);
		UTextBlock* AcceptLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
		AcceptLbl->SetText(FText::FromString(TEXT("Annehmen")));
		AcceptLbl->SetFont(Fnt);
		AcceptBtn->AddChild(AcceptLbl);
		RowBox->AddChildToHorizontalBox(AcceptBtn);
		if (UVerticalBoxSlot* RowSlot = ListBox->AddChildToVerticalBox(RowBox))
		{
			RowSlot->SetPadding(FMargin(0.0f, 4.0f));
		}
	}
}

bool UDoemitzTaskBoardWidget::AcceptOfferAtIndex(int32 Index)
{
	UDoemitzTaskSubsystem* Tasks = UDoemitzTaskSubsystem::Get(this);
	if (!Tasks || !OfferedTaskIds.IsValidIndex(Index))
	{
		return false;
	}
	const bool bAccepted = Tasks->AcceptTask(OfferedTaskIds[Index]);
	RefreshContents();
	return bAccepted;
}

void UDoemitzTaskBoardWidget::HandleCloseClicked()
{
	OnCloseRequested.ExecuteIfBound();
}

void UDoemitzTaskBoardWidget::HandleAccept0() { AcceptOfferAtIndex(0); }
void UDoemitzTaskBoardWidget::HandleAccept1() { AcceptOfferAtIndex(1); }
void UDoemitzTaskBoardWidget::HandleAccept2() { AcceptOfferAtIndex(2); }
void UDoemitzTaskBoardWidget::HandleAccept3() { AcceptOfferAtIndex(3); }
void UDoemitzTaskBoardWidget::HandleAccept4() { AcceptOfferAtIndex(4); }
void UDoemitzTaskBoardWidget::HandleAccept5() { AcceptOfferAtIndex(5); }
