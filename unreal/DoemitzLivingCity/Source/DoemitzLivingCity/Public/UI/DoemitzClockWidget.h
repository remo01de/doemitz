#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "DoemitzClockWidget.generated.h"

class UBorder;
class UTextBlock;

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzClockWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "UI")
	void RefreshDisplay();

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetClockTextString() const { return LastClockText.ToString(); }

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetStatusTextString() const { return LastStatusText.ToString(); }

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetMoneyTextString() const { return LastMoneyText.ToString(); }

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetActiveTaskTextString() const { return LastActiveTaskText.ToString(); }

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetNoticeTextString() const { return LastNoticeText.ToString(); }

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetInteractionPromptString() const { return LastPromptText.ToString(); }

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void NativeConstruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

private:
	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> ClockText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> StatusText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> MoneyText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> ActiveTaskText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> NoticeText;

	UPROPERTY(Transient)
	TObjectPtr<UBorder> PromptPanel;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> PromptText;

	FText LastClockText;
	FText LastStatusText;
	FText LastMoneyText;
	FText LastActiveTaskText;
	FText LastNoticeText;
	FText LastPromptText;
};
