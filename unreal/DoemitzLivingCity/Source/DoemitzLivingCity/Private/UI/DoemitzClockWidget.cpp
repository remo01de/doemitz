#include "UI/DoemitzClockWidget.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Border.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
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
	LastClockString = FString::Printf(TEXT("Tag %d  |  %02d:%02d"), Subsystem->GetDayNumber(), Hours, Minutes);

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
	LastStatusString = FString::Printf(TEXT("Doemitz Altstadt  |  %d Einwohner (%d unterwegs)"), CitizenIds.Num(), MovingCount);

	if (ClockText)
	{
		ClockText->SetText(FText::FromString(LastClockString));
	}
	if (StatusText)
	{
		StatusText->SetText(FText::FromString(LastStatusString));
	}
}
