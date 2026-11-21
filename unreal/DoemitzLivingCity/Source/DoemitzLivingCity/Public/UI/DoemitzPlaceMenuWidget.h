#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "DoemitzPlaceMenuWidget.generated.h"

class UButton;
class UDoemitzPlaceMenuWidget;
class UTextBlock;
class UVerticalBox;

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzShopActionHandler : public UObject
{
	GENERATED_BODY()

public:
	UPROPERTY()
	TWeakObjectPtr<UDoemitzPlaceMenuWidget> OwnerWidget;

	UPROPERTY()
	FName ItemId;

	UFUNCTION()
	void HandleBuyClicked();
};

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzPlaceMenuWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "UI")
	void OpenForPlace(FName InPlaceId);

	UFUNCTION(BlueprintCallable, Category = "UI")
	void RefreshContents();

	UFUNCTION(BlueprintPure, Category = "UI")
	FName GetCurrentPlaceId() const { return CurrentPlaceId; }

	void HandleBuyItem(FName ItemId);

	DECLARE_DELEGATE(FOnCloseRequested);
	FOnCloseRequested OnCloseRequested;

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void NativeConstruct() override;

private:
	UFUNCTION()
	void HandleCloseClicked();

	UFUNCTION()
	void HandleAcceptJobClicked();

	UFUNCTION()
	void HandleStartShiftClicked();

	UFUNCTION()
	void HandleErrandActionClicked();

	FName CurrentPlaceId;
	FName ActiveErrandTaskId;
	bool bActiveErrandIsDelivery = false;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> HeaderText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> SubHeaderText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> RevenueText;

	UPROPERTY(Transient)
	TObjectPtr<UVerticalBox> TaskBox;

	UPROPERTY(Transient)
	TObjectPtr<UVerticalBox> ItemsBox;

	UPROPERTY(Transient)
	TObjectPtr<UVerticalBox> JobBox;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UDoemitzShopActionHandler>> RowHandlers;
};
