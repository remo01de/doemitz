#include "UI/DoemitzPlaceMenuWidget.h"

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
#include "UI/DoemitzUiText.h"

void UDoemitzShopActionHandler::HandleBuyClicked()
{
	if (UDoemitzPlaceMenuWidget* Menu = OwnerWidget.Get())
	{
		Menu->HandleBuyItem(ItemId);
	}
}

TSharedRef<SWidget> UDoemitzPlaceMenuWidget::RebuildWidget()
{
	if (WidgetTree && !WidgetTree->RootWidget)
	{
		UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("PlaceMenuRoot"));
		WidgetTree->RootWidget = RootCanvas;

		UBorder* Panel = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("PlaceMenuPanel"));
		Panel->SetBrushColor(FLinearColor(0.06f, 0.08f, 0.11f, 0.92f));
		Panel->SetPadding(FMargin(20.0f, 16.0f));
		if (UCanvasPanelSlot* PanelSlot = RootCanvas->AddChildToCanvas(Panel))
		{
			PanelSlot->SetAnchors(FAnchors(0.5f, 0.5f, 0.5f, 0.5f));
			PanelSlot->SetAlignment(FVector2D(0.5f, 0.5f));
			PanelSlot->SetPosition(FVector2D(0.0f, 0.0f));
			PanelSlot->SetSize(FVector2D(560.0f, 560.0f));
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
		CloseBtn->OnClicked.AddDynamic(this, &UDoemitzPlaceMenuWidget::HandleCloseClicked);
		UTextBlock* CloseLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CloseLabel"));
		CloseLbl->SetText(FText::FromString(TEXT("Schlie\u00dfen [E/Esc]")));
		FSlateFontInfo BtnFont = CloseLbl->GetFont();
		BtnFont.Size = 12;
		CloseLbl->SetFont(BtnFont);
		CloseBtn->AddChild(CloseLbl);
		HeaderRow->AddChildToHorizontalBox(CloseBtn);

		SubHeaderText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("SubHeaderText"));
		SubHeaderText->SetColorAndOpacity(FSlateColor(FLinearColor(0.75f, 0.88f, 0.78f, 1.0f)));
		FSlateFontInfo SubFont = SubHeaderText->GetFont();
		SubFont.Size = 13;
		SubHeaderText->SetFont(SubFont);
		if (UVerticalBoxSlot* SubSlot = MainBox->AddChildToVerticalBox(SubHeaderText))
		{
			SubSlot->SetPadding(FMargin(0.0f, 4.0f, 0.0f, 4.0f));
		}

		RevenueText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("RevenueText"));
		RevenueText->SetColorAndOpacity(FSlateColor(FLinearColor(0.95f, 0.84f, 0.48f, 1.0f)));
		FSlateFontInfo RevFont = RevenueText->GetFont();
		RevFont.Size = 12;
		RevenueText->SetFont(RevFont);
		if (UVerticalBoxSlot* RevSlot = MainBox->AddChildToVerticalBox(RevenueText))
		{
			RevSlot->SetPadding(FMargin(0.0f, 0.0f, 0.0f, 10.0f));
		}

		TaskBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("TaskBox"));
		if (UVerticalBoxSlot* TaskSlot = MainBox->AddChildToVerticalBox(TaskBox))
		{
			TaskSlot->SetPadding(FMargin(0.0f, 2.0f, 0.0f, 10.0f));
		}

		ItemsBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("ItemsBox"));
		if (UVerticalBoxSlot* ItemsSlot = MainBox->AddChildToVerticalBox(ItemsBox))
		{
			ItemsSlot->SetPadding(FMargin(0.0f, 4.0f, 0.0f, 12.0f));
		}

		JobBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("JobBox"));
		MainBox->AddChildToVerticalBox(JobBox);
	}
	return Super::RebuildWidget();
}

void UDoemitzPlaceMenuWidget::NativeConstruct()
{
	Super::NativeConstruct();
	RefreshContents();
}

void UDoemitzPlaceMenuWidget::OpenForPlace(FName InPlaceId)
{
	CurrentPlaceId = InPlaceId;
	RefreshContents();
}

void UDoemitzPlaceMenuWidget::RefreshContents()
{
	UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this);
	if (!Subsystem || CurrentPlaceId.IsNone() || !WidgetTree)
	{
		return;
	}

	FDoemitzPlaceDefinition Place;
	if (!Subsystem->GetPlaceDefinition(CurrentPlaceId, Place))
	{
		return;
	}

	if (HeaderText)
	{
		HeaderText->SetText(FText::FromString(Place.DisplayName));
	}
	if (SubHeaderText)
	{
		const FText StatusTxt = FDoemitzUiText::FormatOpeningStatus(Subsystem->GetPlaceOpeningStatus(CurrentPlaceId));
		SubHeaderText->SetText(FText::FromString(FString::Printf(
			TEXT("%s  |  Konto: %s"),
			*StatusTxt.ToString(),
			*FDoemitzUiText::FormatCentsEur(Subsystem->GetPlayerMoneyCents()).ToString())));
	}
	if (RevenueText)
	{
		int64 DailyCents = 0;
		int64 WeeklyCents = 0;
		Subsystem->GetPlaceRevenue(CurrentPlaceId, DailyCents, WeeklyCents);
		RevenueText->SetText(FText::FromString(FString::Printf(
			TEXT("Tagesumsatz: %s  |  Wochenumsatz: %s"),
			*FDoemitzUiText::FormatCentsEur(DailyCents).ToString(),
			*FDoemitzUiText::FormatCentsEur(WeeklyCents).ToString())));
	}

	ActiveErrandTaskId = NAME_None;
	bActiveErrandIsDelivery = false;
	if (TaskBox)
	{
		TaskBox->ClearChildren();
		FDoemitzTaskInstance ErrandTask;
		bool bIsDelivery = false;
		if (Subsystem->GetActiveErrandForPlace(CurrentPlaceId, ErrandTask, bIsDelivery))
		{
			ActiveErrandTaskId = ErrandTask.TaskId;
			bActiveErrandIsDelivery = bIsDelivery;

			UTextBlock* TaskHdr = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			TaskHdr->SetText(FText::FromString(FString::Printf(
				TEXT("Aktiver Botengang: %s (Frist %02d:%02d)"),
				*ErrandTask.Title,
				ErrandTask.DeadlineMinute / 60,
				ErrandTask.DeadlineMinute % 60)));
			TaskHdr->SetColorAndOpacity(FSlateColor(FLinearColor(1.0f, 0.88f, 0.42f, 1.0f)));
			FSlateFontInfo Fnt = TaskHdr->GetFont();
			Fnt.Size = 13;
			TaskHdr->SetFont(Fnt);
			TaskBox->AddChildToVerticalBox(TaskHdr);

			UButton* ActionBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass());
			ActionBtn->OnClicked.AddDynamic(this, &UDoemitzPlaceMenuWidget::HandleErrandActionClicked);
			UTextBlock* ActionLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			ActionLbl->SetText(bIsDelivery
				? FText::FromString(FString::Printf(
					TEXT("%s abgeben (+%s)"),
					*ErrandTask.ParcelName,
					*FDoemitzUiText::FormatCentsEur(ErrandTask.RewardCents).ToString()))
				: FText::FromString(FString::Printf(TEXT("%s abholen"), *ErrandTask.ParcelName)));
			Fnt.Size = 12;
			ActionLbl->SetFont(Fnt);
			ActionBtn->AddChild(ActionLbl);
			TaskBox->AddChildToVerticalBox(ActionBtn);
		}
	}

	RowHandlers.Reset();
	if (ItemsBox)
	{
		ItemsBox->ClearChildren();
		const TArray<FDoemitzItemDefinition> Items = Subsystem->GetItemsForPlace(CurrentPlaceId);
		if (!Items.IsEmpty())
		{
			UTextBlock* SectionLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			SectionLbl->SetText(FText::FromString(TEXT("Sortiment (fiktive Preise):")));
			SectionLbl->SetColorAndOpacity(FSlateColor(FLinearColor(0.82f, 0.88f, 0.95f, 1.0f)));
			FSlateFontInfo SecFont = SectionLbl->GetFont();
			SecFont.Size = 13;
			SectionLbl->SetFont(SecFont);
			ItemsBox->AddChildToVerticalBox(SectionLbl);

			for (const FDoemitzItemDefinition& Item : Items)
			{
				UHorizontalBox* Row = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass());
				if (UVerticalBoxSlot* RowSlot = ItemsBox->AddChildToVerticalBox(Row))
				{
					RowSlot->SetPadding(FMargin(0.0f, 3.0f));
				}

				const int32 Owned = Subsystem->GetInventoryQuantity(Item.ItemId);
				UTextBlock* Info = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
				Info->SetText(FText::FromString(FString::Printf(
					TEXT("%s  \u2013  %s  (Inventar: %d)"),
					*Item.DisplayName,
					*FDoemitzUiText::FormatCentsEur(Item.PriceCents).ToString(),
					Owned)));
				Info->SetColorAndOpacity(FSlateColor(FLinearColor(0.92f, 0.92f, 0.92f, 1.0f)));
				FSlateFontInfo RowFont = Info->GetFont();
				RowFont.Size = 12;
				Info->SetFont(RowFont);
				if (UHorizontalBoxSlot* InfoSlot = Row->AddChildToHorizontalBox(Info))
				{
					InfoSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
				}

				UButton* BuyBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass());
				UDoemitzShopActionHandler* Handler = NewObject<UDoemitzShopActionHandler>(this);
				Handler->OwnerWidget = this;
				Handler->ItemId = Item.ItemId;
				RowHandlers.Add(Handler);
				BuyBtn->OnClicked.AddDynamic(Handler, &UDoemitzShopActionHandler::HandleBuyClicked);

				UTextBlock* BuyLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
				BuyLbl->SetText(FText::FromString(TEXT("Kaufen")));
				BuyLbl->SetFont(RowFont);
				BuyBtn->AddChild(BuyLbl);
				Row->AddChildToHorizontalBox(BuyBtn);
			}
		}
		else
		{
			UTextBlock* EmptyLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			EmptyLbl->SetText(FText::FromString(TEXT("Kein Verkaufssortiment an diesem Ort.")));
			EmptyLbl->SetColorAndOpacity(FSlateColor(FLinearColor(0.70f, 0.72f, 0.75f, 1.0f)));
			FSlateFontInfo EmptyFont = EmptyLbl->GetFont();
			EmptyFont.Size = 12;
			EmptyLbl->SetFont(EmptyFont);
			ItemsBox->AddChildToVerticalBox(EmptyLbl);
		}
	}

	if (JobBox)
	{
		JobBox->ClearChildren();
		FDoemitzJobDefinition Job;
		if (Subsystem->GetJobForPlace(CurrentPlaceId, Job))
		{
			UTextBlock* JobHeader = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
			JobHeader->SetText(FText::FromString(FString::Printf(
				TEXT("Stelle: %s (%02d:%02d\u2013%02d:%02d, %s/Std.)"),
				*Job.Title,
				Job.ShiftStartMinute / 60, Job.ShiftStartMinute % 60,
				Job.ShiftEndMinute / 60, Job.ShiftEndMinute % 60,
				*FDoemitzUiText::FormatCentsEur(Job.HourlyWageCents).ToString())));
			JobHeader->SetColorAndOpacity(FSlateColor(FLinearColor(0.78f, 0.90f, 0.98f, 1.0f)));
			FSlateFontInfo JobFont = JobHeader->GetFont();
			JobFont.Size = 13;
			JobHeader->SetFont(JobFont);
			if (UVerticalBoxSlot* JSlot = JobBox->AddChildToVerticalBox(JobHeader))
			{
				JSlot->SetPadding(FMargin(0.0f, 6.0f, 0.0f, 6.0f));
			}

			if (Subsystem->GetActiveJobId() != Job.JobId)
			{
				UButton* AcceptBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass());
				AcceptBtn->OnClicked.AddDynamic(this, &UDoemitzPlaceMenuWidget::HandleAcceptJobClicked);
				UTextBlock* AcceptLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
				AcceptLbl->SetText(FText::FromString(TEXT("Stelle annehmen")));
				AcceptLbl->SetFont(JobFont);
				AcceptBtn->AddChild(AcceptLbl);
				JobBox->AddChildToVerticalBox(AcceptBtn);
			}
			else
			{
				const FDoemitzShiftAvailability Avail = Subsystem->CheckWorkShiftAvailability(CurrentPlaceId);
				UButton* ShiftBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass());
				ShiftBtn->SetIsEnabled(Avail.bCanStart);
				ShiftBtn->OnClicked.AddDynamic(this, &UDoemitzPlaceMenuWidget::HandleStartShiftClicked);
				UTextBlock* ShiftLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
				ShiftLbl->SetText(Avail.bCanStart
					? FText::FromString(TEXT("Schicht beginnen (15x)"))
					: FText::FromString(FString::Printf(
						TEXT("Schicht nicht verf\u00fcgbar: %s"),
						*FDoemitzUiText::FormatShiftAvailability(Avail).ToString())));
				ShiftLbl->SetFont(JobFont);
				ShiftBtn->AddChild(ShiftLbl);
				JobBox->AddChildToVerticalBox(ShiftBtn);
			}
		}
	}
}

void UDoemitzPlaceMenuWidget::HandleBuyItem(FName ItemId)
{
	if (UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this))
	{
		Subsystem->BuyItem(CurrentPlaceId, ItemId, 1);
		RefreshContents();
	}
}

void UDoemitzPlaceMenuWidget::HandleAcceptJobClicked()
{
	if (UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this))
	{
		Subsystem->AcceptJob(CurrentPlaceId);
		RefreshContents();
	}
}

void UDoemitzPlaceMenuWidget::HandleStartShiftClicked()
{
	if (UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this))
	{
		if (Subsystem->StartWorkShift(CurrentPlaceId))
		{
			HandleCloseClicked();
		}
		else
		{
			RefreshContents();
		}
	}
}

void UDoemitzPlaceMenuWidget::HandleErrandActionClicked()
{
	if (UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this))
	{
		if (!ActiveErrandTaskId.IsNone())
		{
			if (bActiveErrandIsDelivery)
			{
				Subsystem->DeliverTaskParcel(ActiveErrandTaskId);
			}
			else
			{
				Subsystem->PickupTaskParcel(ActiveErrandTaskId);
			}
			RefreshContents();
		}
	}
}

void UDoemitzPlaceMenuWidget::HandleCloseClicked()
{
	OnCloseRequested.ExecuteIfBound();
}
