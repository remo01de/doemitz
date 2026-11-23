#include "UI/DoemitzCitizenDialogWidget.h"

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
#include "Economy/DoemitzEconomySubsystem.h"
#include "Simulation/DoemitzCitizenSubsystem.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
#include "Tasks/DoemitzTaskSubsystem.h"
#include "UI/DoemitzUiText.h"

TSharedRef<SWidget> UDoemitzCitizenDialogWidget::RebuildWidget()
{
	if (WidgetTree && !WidgetTree->RootWidget)
	{
		UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("CitizenDialogRoot"));
		WidgetTree->RootWidget = RootCanvas;

		UBorder* Panel = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("CitizenDialogPanel"));
		Panel->SetBrushColor(FLinearColor(0.06f, 0.08f, 0.11f, 0.93f));
		Panel->SetPadding(FMargin(20.0f, 16.0f));
		if (UCanvasPanelSlot* PanelSlot = RootCanvas->AddChildToCanvas(Panel))
		{
			PanelSlot->SetAnchors(FAnchors(0.5f, 0.5f, 0.5f, 0.5f));
			PanelSlot->SetAlignment(FVector2D(0.5f, 0.5f));
			PanelSlot->SetPosition(FVector2D(0.0f, 0.0f));
			PanelSlot->SetSize(FVector2D(520.0f, 340.0f));
		}

		UVerticalBox* MainBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("MainBox"));
		Panel->SetContent(MainBox);

		UHorizontalBox* HeaderRow = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("HeaderRow"));
		MainBox->AddChildToVerticalBox(HeaderRow);

		HeaderText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("HeaderText"));
		HeaderText->SetColorAndOpacity(FSlateColor(FLinearColor(0.98f, 0.95f, 0.86f, 1.0f)));
		FSlateFontInfo TitleFont = HeaderText->GetFont();
		TitleFont.Size = 20;
		HeaderText->SetFont(TitleFont);
		if (UHorizontalBoxSlot* TitleSlot = HeaderRow->AddChildToHorizontalBox(HeaderText))
		{
			TitleSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
		}

		UButton* CloseBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), TEXT("CloseButton"));
		CloseBtn->OnClicked.AddDynamic(this, &UDoemitzCitizenDialogWidget::HandleCloseClicked);
		UTextBlock* CloseLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CloseLabel"));
		CloseLbl->SetText(FText::FromString(TEXT("Schlie\u00dfen [E/Esc]")));
		FSlateFontInfo BtnFont = CloseLbl->GetFont();
		BtnFont.Size = 12;
		CloseLbl->SetFont(BtnFont);
		CloseBtn->AddChild(CloseLbl);
		HeaderRow->AddChildToHorizontalBox(CloseBtn);

		ActivityText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("ActivityText"));
		ActivityText->SetColorAndOpacity(FSlateColor(FLinearColor(0.78f, 0.88f, 0.96f, 1.0f)));
		FSlateFontInfo ActFont = ActivityText->GetFont();
		ActFont.Size = 13;
		ActivityText->SetFont(ActFont);
		if (UVerticalBoxSlot* ActSlot = MainBox->AddChildToVerticalBox(ActivityText))
		{
			ActSlot->SetPadding(FMargin(0.0f, 6.0f, 0.0f, 12.0f));
		}

		TaskBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("TaskBox"));
		MainBox->AddChildToVerticalBox(TaskBox);
	}
	return Super::RebuildWidget();
}

void UDoemitzCitizenDialogWidget::NativeConstruct()
{
	Super::NativeConstruct();
	RefreshContents();
}

void UDoemitzCitizenDialogWidget::OpenForCitizen(FName InCitizenId)
{
	CurrentCitizenId = InCitizenId;
	RefreshContents();
}

FString UDoemitzCitizenDialogWidget::GetHeaderTextString() const
{
	return HeaderText ? HeaderText->GetText().ToString() : FString();
}

FString UDoemitzCitizenDialogWidget::GetActivityTextString() const
{
	return ActivityText ? ActivityText->GetText().ToString() : FString();
}

void UDoemitzCitizenDialogWidget::RefreshContents()
{
	UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this);
	UDoemitzCitizenSubsystem* Citizens = UDoemitzCitizenSubsystem::Get(this);
	UDoemitzEconomySubsystem* Economy = UDoemitzEconomySubsystem::Get(this);
	UDoemitzTaskSubsystem* Tasks = UDoemitzTaskSubsystem::Get(this);
	if (!Subsystem || !Citizens || CurrentCitizenId.IsNone() || !WidgetTree)
	{
		return;
	}

	FDoemitzCitizenState State;
	if (!Citizens->GetCitizenState(CurrentCitizenId, State))
	{
		return;
	}

	if (HeaderText)
	{
		HeaderText->SetText(FText::FromString(State.DisplayName));
	}

	if (ActivityText)
	{
		FDoemitzPlaceDefinition Place;
		const FName RelevantPlaceId = State.bIsMoving ? State.TargetPlaceId : State.CurrentPlaceId;
		const FString PlaceName = Subsystem->GetPlaceDefinition(RelevantPlaceId, Place)
			? Place.DisplayName
			: RelevantPlaceId.ToString();
		const FText ActText = FDoemitzUiText::FormatCitizenActivity(State.CurrentActivity);
		ActivityText->SetText(FText::FromString(FString::Printf(
			TEXT("T\u00e4tigkeit: %s  (%s: %s)"),
			*ActText.ToString(),
			State.bIsMoving ? TEXT("Ziel") : TEXT("Ort"),
			*PlaceName)));
	}

	OfferedTaskId = NAME_None;
	ActiveFetchTaskId = NAME_None;

	if (TaskBox)
	{
		TaskBox->ClearChildren();

		FDoemitzTaskInstance ActiveFetch;
		if (Tasks && Tasks->GetActiveFetchTaskForCitizen(CurrentCitizenId, ActiveFetch))
		{
			ActiveFetchTaskId = ActiveFetch.TaskId;
			FDoemitzItemDefinition Item;
			const FString ItemName = (Economy && Economy->GetItemDefinition(ActiveFetch.RequestedItemId, Item))
				? Item.DisplayName
				: ActiveFetch.RequestedItemId.ToString();
			const int32 OwnedQty = Economy ? Economy->GetInventoryQuantity(ActiveFetch.RequestedItemId) : 0;

			UTextBlock* Title = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			Title->SetText(FText::FromString(FString::Printf(
				TEXT("Offene Besorgung: %s (Lohn: +%s)"),
				*ActiveFetch.Title,
				*FDoemitzUiText::FormatCentsEur(ActiveFetch.RewardCents).ToString())));
			Title->SetColorAndOpacity(FSlateColor(FLinearColor(0.98f, 0.86f, 0.42f, 1.0f)));
			FSlateFontInfo Fnt = Title->GetFont();
			Fnt.Size = 14;
			Title->SetFont(Fnt);
			TaskBox->AddChildToVerticalBox(Title);

			UTextBlock* Info = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			Info->SetText(FText::FromString(FString::Printf(
				TEXT("Gew\u00fcnschter Artikel: %s (im Inventar: %d)"),
				*ItemName,
				OwnedQty)));
			Info->SetColorAndOpacity(FSlateColor(FLinearColor(0.90f, 0.90f, 0.90f, 1.0f)));
			Fnt.Size = 12;
			Info->SetFont(Fnt);
			if (UVerticalBoxSlot* S = TaskBox->AddChildToVerticalBox(Info))
			{
				S->SetPadding(FMargin(0.0f, 4.0f, 0.0f, 8.0f));
			}

			UButton* DeliverBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass());
			DeliverBtn->SetIsEnabled(OwnedQty >= 1);
			DeliverBtn->OnClicked.AddDynamic(this, &UDoemitzCitizenDialogWidget::HandleCompleteFetchClicked);
			UTextBlock* DeliverLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			DeliverLbl->SetText(FText::FromString(OwnedQty >= 1
				? TEXT("Besorgung \u00fcbergeben")
				: TEXT("Artikel erst im Laden kaufen")));
			DeliverLbl->SetFont(Fnt);
			DeliverBtn->AddChild(DeliverLbl);
			TaskBox->AddChildToVerticalBox(DeliverBtn);
		}

		FDoemitzTaskInstance Offered;
		if (Tasks && Tasks->GetTaskOfferedByCitizen(CurrentCitizenId, Offered))
		{
			OfferedTaskId = Offered.TaskId;
			UTextBlock* OfferTitle = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			OfferTitle->SetText(FText::FromString(FString::Printf(
				TEXT("Aufgabenangebot: %s"),
				*Offered.Title)));
			OfferTitle->SetColorAndOpacity(FSlateColor(FLinearColor(0.68f, 0.95f, 0.68f, 1.0f)));
			FSlateFontInfo Fnt = OfferTitle->GetFont();
			Fnt.Size = 14;
			OfferTitle->SetFont(Fnt);
			if (UVerticalBoxSlot* S = TaskBox->AddChildToVerticalBox(OfferTitle))
			{
				S->SetPadding(FMargin(0.0f, 8.0f, 0.0f, 4.0f));
			}

			UTextBlock* OfferDesc = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			OfferDesc->SetText(FText::FromString(Offered.Description));
			OfferDesc->SetAutoWrapText(true);
			OfferDesc->SetColorAndOpacity(FSlateColor(FLinearColor(0.90f, 0.92f, 0.95f, 1.0f)));
			Fnt.Size = 12;
			OfferDesc->SetFont(Fnt);
			TaskBox->AddChildToVerticalBox(OfferDesc);

			UTextBlock* OfferMeta = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			OfferMeta->SetText(FText::FromString(FString::Printf(
				TEXT("Frist: %02d:%02d Uhr  |  Belohnung: +%s (fiktive Annahme)"),
				Offered.DeadlineMinute / 60,
				Offered.DeadlineMinute % 60,
				*FDoemitzUiText::FormatCentsEur(Offered.RewardCents).ToString())));
			OfferMeta->SetColorAndOpacity(FSlateColor(FLinearColor(0.95f, 0.85f, 0.48f, 1.0f)));
			OfferMeta->SetFont(Fnt);
			if (UVerticalBoxSlot* S = TaskBox->AddChildToVerticalBox(OfferMeta))
			{
				S->SetPadding(FMargin(0.0f, 4.0f, 0.0f, 8.0f));
			}

			UButton* AcceptBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass());
			AcceptBtn->OnClicked.AddDynamic(this, &UDoemitzCitizenDialogWidget::HandleAcceptOfferedTaskClicked);
			UTextBlock* AcceptLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			AcceptLbl->SetText(FText::FromString(TEXT("Aufgabe annehmen")));
			AcceptLbl->SetFont(Fnt);
			AcceptBtn->AddChild(AcceptLbl);
			TaskBox->AddChildToVerticalBox(AcceptBtn);
		}

		if (OfferedTaskId.IsNone() && ActiveFetchTaskId.IsNone())
		{
			UTextBlock* NoTask = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			NoTask->SetText(FText::FromString(TEXT("Derzeit kein Aufgabenangebot. Sch\u00f6nen Tag noch in D\u00f6mitz!")));
			NoTask->SetColorAndOpacity(FSlateColor(FLinearColor(0.75f, 0.78f, 0.82f, 1.0f)));
			FSlateFontInfo Fnt = NoTask->GetFont();
			Fnt.Size = 12;
			NoTask->SetFont(Fnt);
			TaskBox->AddChildToVerticalBox(NoTask);
		}
	}
}

void UDoemitzCitizenDialogWidget::HandleAcceptOfferedTaskClicked()
{
	if (UDoemitzTaskSubsystem* Tasks = UDoemitzTaskSubsystem::Get(this))
	{
		if (!OfferedTaskId.IsNone() && Tasks->AcceptTask(OfferedTaskId))
		{
			RefreshContents();
		}
	}
}

void UDoemitzCitizenDialogWidget::HandleCompleteFetchClicked()
{
	if (UDoemitzTaskSubsystem* Tasks = UDoemitzTaskSubsystem::Get(this))
	{
		if (!ActiveFetchTaskId.IsNone() && Tasks->CompleteFetchTask(ActiveFetchTaskId))
		{
			RefreshContents();
		}
	}
}

void UDoemitzCitizenDialogWidget::HandleCloseClicked()
{
	OnCloseRequested.ExecuteIfBound();
}
