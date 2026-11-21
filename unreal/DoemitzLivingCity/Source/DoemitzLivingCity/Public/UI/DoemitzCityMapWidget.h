#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Styling/SlateBrush.h"
#include "DoemitzCityMapWidget.generated.h"

class UBorder;
class UButton;
class UTextBlock;

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzCityMapWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "UI")
	void RefreshMapData();

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetAttributionTextString() const;

	UFUNCTION(BlueprintPure, Category = "UI")
	float GetZoomLevel() const { return ZoomLevel; }

	UFUNCTION(BlueprintCallable, Category = "UI")
	void SetZoomLevelForTest(float NewZoom);

	UFUNCTION(BlueprintPure, Category = "UI")
	int32 GetCitizenMarkerCount() const { return CachedCitizenCount; }

	UFUNCTION(BlueprintPure, Category = "UI")
	int32 GetPlaceMarkerCount() const { return CachedPlaceCount; }

	UFUNCTION(BlueprintPure, Category = "UI")
	int32 GetVehicleMarkerCount() const { return CachedVehicleCount; }

	UFUNCTION(BlueprintPure, Category = "UI")
	int32 GetParkingMarkerCount() const { return CachedParkingCount; }

	UFUNCTION(BlueprintPure, Category = "UI")
	FVector2D GetPlayerNormalizedPosition() const;

	UFUNCTION(BlueprintPure, Category = "UI")
	bool GetCitizenNormalizedPosition(FName CitizenId, FVector2D& OutNormPos) const;

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetHoverTextString() const { return LastHoverText.ToString(); }

	DECLARE_DELEGATE(FOnCloseRequested);
	FOnCloseRequested OnCloseRequested;

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void NativeConstruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;
	virtual int32 NativePaint(
		const FPaintArgs& Args,
		const FGeometry& AllottedGeometry,
		const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements,
		int32 LayerId,
		const FWidgetStyle& InWidgetStyle,
		bool bParentEnabled) const override;
	virtual FReply NativeOnMouseWheel(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent) override;
	virtual FReply NativeOnMouseButtonDown(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent) override;
	virtual FReply NativeOnMouseButtonUp(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent) override;
	virtual FReply NativeOnMouseMove(const FGeometry& InGeometry, const FPointerEvent& InMouseEvent) override;

private:
	UFUNCTION()
	void HandleCloseClicked();

	void ComputeMapRect(const FVector2D& WidgetLocalSize, FVector2D& OutOrigin, FVector2D& OutSize) const;
	FVector2D NormToLocal(const FVector2D& NormUV, const FVector2D& MapOrigin, const FVector2D& MapSize) const;
	void ClampPanOffset(const FVector2D& MapSize);
	void UpdateHoverAtLocalPosition(const FVector2D& LocalPos, const FVector2D& WidgetLocalSize);

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> HeaderText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> HoverText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> AttributionText;

	FSlateBrush MapTextureBrush;
	bool bBrushInitialized = false;

	float ZoomLevel = 1.0f;
	FVector2D PanOffsetPx = FVector2D::ZeroVector;
	bool bIsDragging = false;
	FVector2D LastDragLocalPos = FVector2D::ZeroVector;
	FVector2D LastLocalSize = FVector2D(820.0f, 760.0f);

	int32 CachedCitizenCount = 0;
	int32 CachedPlaceCount = 0;
	int32 CachedVehicleCount = 0;
	int32 CachedParkingCount = 0;
	FText LastHoverText;
};
