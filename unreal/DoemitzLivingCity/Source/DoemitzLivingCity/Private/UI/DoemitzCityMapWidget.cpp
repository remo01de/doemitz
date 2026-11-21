#include "UI/DoemitzCityMapWidget.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/TextBlock.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "Fonts/SlateFontInfo.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Rendering/DrawElements.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
#include "Styling/CoreStyle.h"
#include "UI/DoemitzUiText.h"

namespace
{
	constexpr float MapFrameTopMargin = 52.0f;
	constexpr float MapFrameBottomMargin = 54.0f;
	constexpr float MapFrameSideMargin = 20.0f;
	constexpr float MinZoom = 1.0f;
	constexpr float MaxZoom = 6.0f;

	void DrawFilledSquare(
		FSlateWindowElementList& OutDrawElements,
		int32 LayerId,
		const FGeometry& Geometry,
		const FVector2D& Center,
		float HalfSize,
		const FLinearColor& Color)
	{
		const FSlateBrush* WhiteBrush = FCoreStyle::Get().GetBrush(TEXT("WhiteBrush"));
		FSlateDrawElement::MakeBox(
			OutDrawElements,
			LayerId,
			Geometry.ToPaintGeometry(
				FVector2f(HalfSize * 2.0f, HalfSize * 2.0f),
				FSlateLayoutTransform(FVector2f(Center.X - HalfSize, Center.Y - HalfSize))),
			WhiteBrush,
			ESlateDrawEffect::None,
			Color);
	}
}

TSharedRef<SWidget> UDoemitzCityMapWidget::RebuildWidget()
{
	if (WidgetTree && !WidgetTree->RootWidget)
	{
		UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("CityMapRoot"));
		WidgetTree->RootWidget = RootCanvas;

		UBorder* Frame = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("CityMapFrame"));
		Frame->SetBrushColor(FLinearColor(0.05f, 0.07f, 0.09f, 0.94f));
		Frame->SetPadding(FMargin(14.0f, 10.0f));
		if (UCanvasPanelSlot* FrameSlot = RootCanvas->AddChildToCanvas(Frame))
		{
			FrameSlot->SetAnchors(FAnchors(0.06f, 0.05f, 0.94f, 0.95f));
			FrameSlot->SetOffsets(FMargin(0.0f));
		}

		UCanvasPanel* InnerCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("InnerCanvas"));
		Frame->SetContent(InnerCanvas);

		// Top bar: Title + Legend + Close button
		UHorizontalBox* TopBar = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("TopBar"));
		if (UCanvasPanelSlot* TopSlot = InnerCanvas->AddChildToCanvas(TopBar))
		{
			TopSlot->SetAnchors(FAnchors(0.0f, 0.0f, 1.0f, 0.0f));
			TopSlot->SetOffsets(FMargin(6.0f, 2.0f, 6.0f, 36.0f));
		}

		HeaderText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("HeaderText"));
		HeaderText->SetColorAndOpacity(FSlateColor(FLinearColor(0.96f, 0.94f, 0.86f, 1.0f)));
		FSlateFontInfo TitleFont = HeaderText->GetFont();
		TitleFont.Size = 15;
		HeaderText->SetFont(TitleFont);
		if (UHorizontalBoxSlot* TitleSlot = TopBar->AddChildToHorizontalBox(HeaderText))
		{
			TitleSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
		}

		UButton* CloseBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), TEXT("CloseButton"));
		CloseBtn->OnClicked.AddDynamic(this, &UDoemitzCityMapWidget::HandleCloseClicked);
		UTextBlock* CloseLbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("CloseLabel"));
		CloseLbl->SetText(FText::FromString(TEXT("Schlie\u00dfen [M/Esc]")));
		FSlateFontInfo BtnFont = CloseLbl->GetFont();
		BtnFont.Size = 11;
		CloseLbl->SetFont(BtnFont);
		CloseBtn->AddChild(CloseLbl);
		TopBar->AddChildToHorizontalBox(CloseBtn);

		// Bottom bar: Hover info (left) + mandatory OSM attribution (right)
		UHorizontalBox* BottomBar = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("BottomBar"));
		if (UCanvasPanelSlot* BotSlot = InnerCanvas->AddChildToCanvas(BottomBar))
		{
			BotSlot->SetAnchors(FAnchors(0.0f, 1.0f, 1.0f, 1.0f));
			BotSlot->SetAlignment(FVector2D(0.0f, 1.0f));
			BotSlot->SetOffsets(FMargin(6.0f, -4.0f, 6.0f, 28.0f));
		}

		HoverText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("HoverText"));
		HoverText->SetColorAndOpacity(FSlateColor(FLinearColor(0.95f, 0.88f, 0.56f, 1.0f)));
		FSlateFontInfo HoverFont = HoverText->GetFont();
		HoverFont.Size = 12;
		HoverText->SetFont(HoverFont);
		if (UHorizontalBoxSlot* HoverSlot = BottomBar->AddChildToHorizontalBox(HoverText))
		{
			HoverSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
		}

		AttributionText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("AttributionText"));
		AttributionText->SetText(FDoemitzUiText::GetMapAttributionText());
		AttributionText->SetColorAndOpacity(FSlateColor(FLinearColor(0.76f, 0.80f, 0.84f, 1.0f)));
		FSlateFontInfo AttrFont = AttributionText->GetFont();
		AttrFont.Size = 11;
		AttributionText->SetFont(AttrFont);
		BottomBar->AddChildToHorizontalBox(AttributionText);
	}
	return Super::RebuildWidget();
}

void UDoemitzCityMapWidget::NativeConstruct()
{
	Super::NativeConstruct();
	SetVisibility(ESlateVisibility::Visible);
	RefreshMapData();
}

void UDoemitzCityMapWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);
	LastLocalSize = MyGeometry.GetLocalSize();
	RefreshMapData();
}

void UDoemitzCityMapWidget::RefreshMapData()
{
	const UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this);
	if (!Subsystem)
	{
		return;
	}

	if (!bBrushInitialized)
	{
		if (UTexture2D* Tex = Subsystem->GetCityMapTexture())
		{
			MapTextureBrush.SetResourceObject(Tex);
			MapTextureBrush.ImageSize = FVector2D(Tex->GetSizeX(), Tex->GetSizeY());
			MapTextureBrush.DrawAs = ESlateBrushDrawType::Image;
			bBrushInitialized = true;
		}
	}

	CachedCitizenCount = Subsystem->GetCitizenCount();
	CachedVehicleCount = Subsystem->GetVehicleCount();
	CachedParkingCount = Subsystem->GetParkingLotCount();

	int32 NonHomePlaces = 0;
	for (const FDoemitzPlaceDefinition& Place : Subsystem->GetAllPlaceDefinitions())
	{
		if (Place.Kind != FName(TEXT("home")))
		{
			++NonHomePlaces;
		}
	}
	CachedPlaceCount = NonHomePlaces;

	if (HeaderText)
	{
		HeaderText->SetText(FText::FromString(FString::Printf(
			TEXT("Stadtkarte \u2013 D\u00f6mitz Altstadt  |  Zoom %.0f%%  |  Mausrad: Zoom, Ziehen: Verschieben  |  Gr\u00fcn: Offen  Rot: Geschlossen  Gelb: Einwohner (%d)  Cyan: Autos (%d)  Blau: Parken (%d)"),
			ZoomLevel * 100.0f,
			CachedCitizenCount,
			CachedVehicleCount,
			CachedParkingCount)));
	}
	if (AttributionText)
	{
		AttributionText->SetText(FDoemitzUiText::GetMapAttributionText());
	}
	if (HoverText && LastHoverText.IsEmpty())
	{
		HoverText->SetText(FText::FromString(TEXT("Maus \u00fcber Ort, Parkplatz oder Einwohner bewegen f\u00fcr Details")));
	}
}

FString UDoemitzCityMapWidget::GetAttributionTextString() const
{
	return AttributionText ? AttributionText->GetText().ToString() : FDoemitzUiText::GetMapAttributionText().ToString();
}

void UDoemitzCityMapWidget::SetZoomLevelForTest(float NewZoom)
{
	ZoomLevel = FMath::Clamp(NewZoom, MinZoom, MaxZoom);
	FVector2D MapOrigin, MapSize;
	ComputeMapRect(LastLocalSize, MapOrigin, MapSize);
	ClampPanOffset(MapSize);
	RefreshMapData();
}

FVector2D UDoemitzCityMapWidget::GetPlayerNormalizedPosition() const
{
	const UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this);
	const UWorld* World = GetWorld();
	if (!Subsystem || !World)
	{
		return FVector2D(0.5, 0.5);
	}
	if (const APlayerController* PC = World->GetFirstPlayerController())
	{
		if (const APawn* Pawn = PC->GetPawn())
		{
			return Subsystem->ProjectWorldToNormalizedMap(Pawn->GetActorLocation());
		}
	}
	return FVector2D(0.5, 0.5);
}

bool UDoemitzCityMapWidget::GetCitizenNormalizedPosition(FName CitizenId, FVector2D& OutNormPos) const
{
	const UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this);
	FDoemitzCitizenState State;
	if (!Subsystem || !Subsystem->GetCitizenState(CitizenId, State))
	{
		return false;
	}
	OutNormPos = Subsystem->ProjectWorldToNormalizedMap(State.WorldLocation);
	return true;
}

void UDoemitzCityMapWidget::ComputeMapRect(const FVector2D& WidgetLocalSize, FVector2D& OutOrigin, FVector2D& OutSize) const
{
	const float FrameLeft = WidgetLocalSize.X * 0.06f + MapFrameSideMargin;
	const float FrameTop = WidgetLocalSize.Y * 0.05f + MapFrameTopMargin;
	const float FrameW = FMath::Max(100.0f, WidgetLocalSize.X * 0.88f - MapFrameSideMargin * 2.0f);
	const float FrameH = FMath::Max(100.0f, WidgetLocalSize.Y * 0.90f - MapFrameTopMargin - MapFrameBottomMargin);
	const float SquareSide = FMath::Min(FrameW, FrameH);
	OutOrigin = FVector2D(FrameLeft + (FrameW - SquareSide) * 0.5f, FrameTop + (FrameH - SquareSide) * 0.5f);
	OutSize = FVector2D(SquareSide, SquareSide);
}

FVector2D UDoemitzCityMapWidget::NormToLocal(const FVector2D& NormUV, const FVector2D& MapOrigin, const FVector2D& MapSize) const
{
	const FVector2D Center = MapOrigin + MapSize * 0.5f;
	const FVector2D ScaledSize = MapSize * ZoomLevel;
	const FVector2D TopLeft = Center - ScaledSize * 0.5f + PanOffsetPx;
	return TopLeft + FVector2D(NormUV.X * ScaledSize.X, NormUV.Y * ScaledSize.Y);
}

void UDoemitzCityMapWidget::ClampPanOffset(const FVector2D& MapSize)
{
	const float MaxPanX = FMath::Max(0.0f, MapSize.X * (ZoomLevel - 1.0f) * 0.5f);
	const float MaxPanY = FMath::Max(0.0f, MapSize.Y * (ZoomLevel - 1.0f) * 0.5f);
	PanOffsetPx.X = FMath::Clamp(PanOffsetPx.X, -MaxPanX, MaxPanX);
	PanOffsetPx.Y = FMath::Clamp(PanOffsetPx.Y, -MaxPanY, MaxPanY);
}

int32 UDoemitzCityMapWidget::NativePaint(
	const FPaintArgs& Args,
	const FGeometry& AllottedGeometry,
	const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements,
	int32 LayerId,
	const FWidgetStyle& InWidgetStyle,
	bool bParentEnabled) const
{
	int32 MaxLayer = Super::NativePaint(Args, AllottedGeometry, MyCullingRect, OutDrawElements, LayerId, InWidgetStyle, bParentEnabled);
	const UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this);
	if (!Subsystem)
	{
		return MaxLayer;
	}

	const FVector2D LocalSize = AllottedGeometry.GetLocalSize();
	FVector2D MapOrigin, MapSize;
	ComputeMapRect(LocalSize, MapOrigin, MapSize);

	// Clip all map drawing cleanly to the square map viewport
	const FSlateClippingZone ClipZone(AllottedGeometry.MakeChild(MapSize, FSlateLayoutTransform(MapOrigin)));
	OutDrawElements.PushClip(ClipZone);

	const FVector2D Center = MapOrigin + MapSize * 0.5f;
	const FVector2D ScaledSize = MapSize * ZoomLevel;
	const FVector2D ImageTopLeft = Center - ScaledSize * 0.5f + PanOffsetPx;

	// 1. Offline rendered top-down city map texture
	++MaxLayer;
	if (bBrushInitialized)
	{
		FSlateDrawElement::MakeBox(
			OutDrawElements,
			MaxLayer,
			AllottedGeometry.ToPaintGeometry(FVector2f(ScaledSize), FSlateLayoutTransform(FVector2f(ImageTopLeft))),
			&MapTextureBrush,
			ESlateDrawEffect::None,
			FLinearColor::White);
	}
	else
	{
		const FSlateBrush* WhiteBrush = FCoreStyle::Get().GetBrush(TEXT("WhiteBrush"));
		FSlateDrawElement::MakeBox(
			OutDrawElements,
			MaxLayer,
			AllottedGeometry.ToPaintGeometry(FVector2f(MapSize), FSlateLayoutTransform(FVector2f(MapOrigin))),
			WhiteBrush,
			ESlateDrawEffect::None,
			FLinearColor(0.16f, 0.24f, 0.14f, 1.0f));
	}

	// 2. Parking lots (blue square with "P")
	++MaxLayer;
	const FSlateFontInfo SmallFont = FCoreStyle::GetDefaultFontStyle("Bold", 8);
	for (FName LotId : Subsystem->GetAllParkingLotIds())
	{
		FDoemitzParkingLotState Lot;
		if (!Subsystem->GetParkingLotState(LotId, Lot))
		{
			continue;
		}
		const FVector2D Pt = NormToLocal(Subsystem->ProjectWorldToNormalizedMap(Lot.Location), MapOrigin, MapSize);
		DrawFilledSquare(OutDrawElements, MaxLayer, AllottedGeometry, Pt, 6.0f, FLinearColor(0.14f, 0.42f, 0.85f, 0.95f));
		FSlateDrawElement::MakeText(
			OutDrawElements,
			MaxLayer + 1,
			AllottedGeometry.ToPaintGeometry(FVector2f(12.0f, 12.0f), FSlateLayoutTransform(FVector2f(Pt.X - 3.5f, Pt.Y - 5.5f))),
			TEXT("P"),
			SmallFont,
			ESlateDrawEffect::None,
			FLinearColor::White);
	}

	// 3. Places (colored by opening status: green = open, red = closed)
	MaxLayer += 2;
	for (const FDoemitzPlaceDefinition& Place : Subsystem->GetAllPlaceDefinitions())
	{
		if (Place.Kind == FName(TEXT("home")))
		{
			continue;
		}
		const FVector Loc = !Place.EntranceLocation.IsNearlyZero() ? Place.EntranceLocation : Place.AccessLocation;
		const FVector2D Pt = NormToLocal(Subsystem->ProjectWorldToNormalizedMap(Loc), MapOrigin, MapSize);
		const FDoemitzOpeningStatus Status = Subsystem->GetPlaceOpeningStatus(Place.PlaceId);
		const FLinearColor Color = Status.bOpen
			? FLinearColor(0.20f, 0.84f, 0.36f, 0.95f)
			: FLinearColor(0.84f, 0.24f, 0.22f, 0.85f);
		DrawFilledSquare(OutDrawElements, MaxLayer, AllottedGeometry, Pt, 4.5f, FLinearColor(0.05f, 0.05f, 0.05f, 0.85f));
		DrawFilledSquare(OutDrawElements, MaxLayer + 1, AllottedGeometry, Pt, 3.2f, Color);
	}

	// 4. All 30 citizens (purely from simulation state, including off-pool citizens without Actors!)
	MaxLayer += 2;
	for (FName CitizenId : Subsystem->GetAllCitizenIds())
	{
		FDoemitzCitizenState Cit;
		if (!Subsystem->GetCitizenState(CitizenId, Cit))
		{
			continue;
		}
		const FVector2D Pt = NormToLocal(Subsystem->ProjectWorldToNormalizedMap(Cit.WorldLocation), MapOrigin, MapSize);
		FDoemitzTaskInstance Offered;
		const bool bHasOffer = Subsystem->GetTaskOfferedByCitizen(CitizenId, Offered);
		const FLinearColor CitColor = bHasOffer
			? FLinearColor(1.0f, 0.78f, 0.12f, 1.0f)
			: FLinearColor(0.95f, 0.88f, 0.42f, 0.90f);
		DrawFilledSquare(OutDrawElements, MaxLayer, AllottedGeometry, Pt, bHasOffer ? 4.2f : 2.8f, CitColor);
	}

	// 5. All 8 vehicles (cyan when driving, muted blue-gray when parked)
	++MaxLayer;
	for (FName VehicleId : Subsystem->GetAllVehicleIds())
	{
		FDoemitzVehicleState Veh;
		if (!Subsystem->GetVehicleState(VehicleId, Veh))
		{
			continue;
		}
		const FVector2D Pt = NormToLocal(Subsystem->ProjectWorldToNormalizedMap(Veh.WorldLocation), MapOrigin, MapSize);
		const FLinearColor VehColor = (Veh.Phase == EDoemitzVehiclePhase::Parked)
			? FLinearColor(0.45f, 0.65f, 0.78f, 0.85f)
			: FLinearColor(0.22f, 0.92f, 0.98f, 0.98f);
		DrawFilledSquare(OutDrawElements, MaxLayer, AllottedGeometry, Pt, 3.5f, VehColor);
	}

	// 6. Active task target marker (bright golden diamond + crosshair)
	++MaxLayer;
	FVector TaskTargetLoc;
	FName TaskPlaceId, TaskCitizenId;
	if (Subsystem->GetActiveTaskTargetLocation(TaskTargetLoc, TaskPlaceId, TaskCitizenId))
	{
		const FVector2D Pt = NormToLocal(Subsystem->ProjectWorldToNormalizedMap(TaskTargetLoc), MapOrigin, MapSize);
		const TArray<FVector2D> Diamond = {
			Pt + FVector2D(0.0, -10.0),
			Pt + FVector2D(10.0, 0.0),
			Pt + FVector2D(0.0, 10.0),
			Pt + FVector2D(-10.0, 0.0),
			Pt + FVector2D(0.0, -10.0)
		};
		FSlateDrawElement::MakeLines(
			OutDrawElements,
			MaxLayer,
			AllottedGeometry.ToPaintGeometry(),
			Diamond,
			ESlateDrawEffect::None,
			FLinearColor(1.0f, 0.85f, 0.10f, 1.0f),
			true,
			2.5f);
	}

	// 7. Player marker with facing direction arrow (UE X=North -> Map -Y, UE Y=East -> Map +X)
	++MaxLayer;
	if (const UWorld* World = GetWorld())
	{
		if (const APlayerController* PC = World->GetFirstPlayerController())
		{
			if (const APawn* Pawn = PC->GetPawn())
			{
				const FVector2D Pt = NormToLocal(Subsystem->ProjectWorldToNormalizedMap(Pawn->GetActorLocation()), MapOrigin, MapSize);
				const float YawRad = FMath::DegreesToRadians(Pawn->GetActorRotation().Yaw);
				const FVector2D Fwd(FMath::Sin(YawRad), -FMath::Cos(YawRad));
				const FVector2D Right(-Fwd.Y, Fwd.X);

				const TArray<FVector2D> Arrow = {
					Pt + Fwd * 11.0,
					Pt - Fwd * 6.0 + Right * 6.5,
					Pt - Fwd * 2.5,
					Pt - Fwd * 6.0 - Right * 6.5,
					Pt + Fwd * 11.0
				};
				FSlateDrawElement::MakeLines(
					OutDrawElements,
					MaxLayer,
					AllottedGeometry.ToPaintGeometry(),
					Arrow,
					ESlateDrawEffect::None,
					FLinearColor::White,
					true,
					2.5f);
				DrawFilledSquare(OutDrawElements, MaxLayer + 1, AllottedGeometry, Pt, 2.5f, FLinearColor(0.20f, 1.0f, 0.55f, 1.0f));
			}
		}
	}

	OutDrawElements.PopClip();
	return MaxLayer + 2;
}

FReply UDoemitzCityMapWidget::NativeOnMouseWheel(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent)
{
	const float WheelDelta = InMouseEvent.GetWheelDelta();
	if (FMath::IsNearlyZero(WheelDelta))
	{
		return FReply::Unhandled();
	}

	const FVector2D LocalSize = InGeometry.GetLocalSize();
	FVector2D MapOrigin, MapSize;
	ComputeMapRect(LocalSize, MapOrigin, MapSize);

	const float OldZoom = ZoomLevel;
	const float Factor = WheelDelta > 0.0f ? 1.2f : (1.0f / 1.2f);
	ZoomLevel = FMath::Clamp(ZoomLevel * Factor, MinZoom, MaxZoom);

	const FVector2D CursorLocal = InGeometry.AbsoluteToLocal(InMouseEvent.GetScreenSpacePosition());
	const FVector2D Center = MapOrigin + MapSize * 0.5f;
	const FVector2D CursorRel = CursorLocal - Center - PanOffsetPx;
	const float ScaleRatio = ZoomLevel / FMath::Max(0.01f, OldZoom);
	PanOffsetPx -= CursorRel * (ScaleRatio - 1.0f);
	ClampPanOffset(MapSize);
	RefreshMapData();
	return FReply::Handled();
}

FReply UDoemitzCityMapWidget::NativeOnMouseButtonDown(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent)
{
	if (InMouseEvent.GetEffectingButton() == EKeys::LeftMouseButton || InMouseEvent.GetEffectingButton() == EKeys::RightMouseButton)
	{
		bIsDragging = true;
		LastDragLocalPos = InGeometry.AbsoluteToLocal(InMouseEvent.GetScreenSpacePosition());
		return FReply::Handled().CaptureMouse(TakeWidget());
	}
	return FReply::Unhandled();
}

FReply UDoemitzCityMapWidget::NativeOnMouseButtonUp(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent)
{
	if (bIsDragging)
	{
		bIsDragging = false;
		return FReply::Handled().ReleaseMouseCapture();
	}
	return FReply::Unhandled();
}

FReply UDoemitzCityMapWidget::NativeOnMouseMove(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent)
{
	const FVector2D LocalSize = InGeometry.GetLocalSize();
	const FVector2D LocalPos = InGeometry.AbsoluteToLocal(InMouseEvent.GetScreenSpacePosition());
	FVector2D MapOrigin, MapSize;
	ComputeMapRect(LocalSize, MapOrigin, MapSize);

	if (bIsDragging)
	{
		const FVector2D Delta = LocalPos - LastDragLocalPos;
		LastDragLocalPos = LocalPos;
		PanOffsetPx += Delta;
		ClampPanOffset(MapSize);
		return FReply::Handled();
	}

	UpdateHoverAtLocalPosition(LocalPos, LocalSize);
	return FReply::Handled();
}

void UDoemitzCityMapWidget::UpdateHoverAtLocalPosition(const FVector2D& LocalPos, const FVector2D& WidgetLocalSize)
{
	const UDoemitzSimulationSubsystem* Subsystem = UDoemitzSimulationSubsystem::Get(this);
	if (!Subsystem)
	{
		return;
	}
	FVector2D MapOrigin, MapSize;
	ComputeMapRect(WidgetLocalSize, MapOrigin, MapSize);

	double BestDist = 14.0;
	FText BestText;

	for (const FDoemitzPlaceDefinition& Place : Subsystem->GetAllPlaceDefinitions())
	{
		if (Place.Kind == FName(TEXT("home")))
		{
			continue;
		}
		const FVector Loc = !Place.EntranceLocation.IsNearlyZero() ? Place.EntranceLocation : Place.AccessLocation;
		const FVector2D Pt = NormToLocal(Subsystem->ProjectWorldToNormalizedMap(Loc), MapOrigin, MapSize);
		const double D = FVector2D::Distance(LocalPos, Pt);
		if (D < BestDist)
		{
			BestDist = D;
			const FText OpenTxt = FDoemitzUiText::FormatOpeningStatus(Subsystem->GetPlaceOpeningStatus(Place.PlaceId));
			BestText = FText::FromString(FString::Printf(TEXT("%s  \u00b7  %s"), *Place.DisplayName, *OpenTxt.ToString()));
		}
	}

	for (FName LotId : Subsystem->GetAllParkingLotIds())
	{
		FDoemitzParkingLotState Lot;
		if (!Subsystem->GetParkingLotState(LotId, Lot))
		{
			continue;
		}
		const FVector2D Pt = NormToLocal(Subsystem->ProjectWorldToNormalizedMap(Lot.Location), MapOrigin, MapSize);
		const double D = FVector2D::Distance(LocalPos, Pt);
		if (D < BestDist)
		{
			BestDist = D;
			BestText = FText::FromString(FString::Printf(
				TEXT("%s  \u00b7  %d/%d Pl\u00e4tze belegt"),
				*Lot.DisplayName,
				Lot.OccupiedCount,
				Lot.Capacity));
		}
	}

	for (FName CitizenId : Subsystem->GetAllCitizenIds())
	{
		FDoemitzCitizenState Cit;
		if (!Subsystem->GetCitizenState(CitizenId, Cit))
		{
			continue;
		}
		const FVector2D Pt = NormToLocal(Subsystem->ProjectWorldToNormalizedMap(Cit.WorldLocation), MapOrigin, MapSize);
		const double D = FVector2D::Distance(LocalPos, Pt);
		if (D < BestDist)
		{
			BestDist = D;
			FDoemitzTaskInstance Offered;
			const bool bOffer = Subsystem->GetTaskOfferedByCitizen(CitizenId, Offered);
			BestText = FText::FromString(FString::Printf(
				TEXT("%s  \u00b7  %s%s"),
				*Cit.DisplayName,
				*FDoemitzUiText::FormatCitizenActivity(Cit.CurrentActivity).ToString(),
				bOffer ? TEXT("  \u00b7  Aufgabe verf\u00fcgbar") : TEXT("")));
		}
	}

	LastHoverText = BestText;
	if (HoverText)
	{
		HoverText->SetText(BestText.IsEmpty()
			? FText::FromString(TEXT("Maus \u00fcber Ort, Parkplatz oder Einwohner bewegen f\u00fcr Details"))
			: BestText);
	}
}

void UDoemitzCityMapWidget::HandleCloseClicked()
{
	OnCloseRequested.ExecuteIfBound();
}
