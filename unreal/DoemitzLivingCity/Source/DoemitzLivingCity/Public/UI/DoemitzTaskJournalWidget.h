#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "DoemitzTaskJournalWidget.generated.h"

class UTextBlock;
class UVerticalBox;

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzTaskJournalWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "UI")
	void RefreshContents();

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetSummaryTextString() const;

	DECLARE_DELEGATE(FOnCloseRequested);
	FOnCloseRequested OnCloseRequested;

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void NativeConstruct() override;

private:
	UFUNCTION()
	void HandleCloseClicked();

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> SummaryText;

	UPROPERTY(Transient)
	TObjectPtr<UVerticalBox> ListBox;
};
