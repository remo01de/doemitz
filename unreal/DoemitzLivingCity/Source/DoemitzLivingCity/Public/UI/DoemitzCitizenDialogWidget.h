#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "DoemitzCitizenDialogWidget.generated.h"

class UTextBlock;
class UVerticalBox;

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzCitizenDialogWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "UI")
	void OpenForCitizen(FName InCitizenId);

	UFUNCTION(BlueprintCallable, Category = "UI")
	void RefreshContents();

	UFUNCTION(BlueprintPure, Category = "UI")
	FName GetCurrentCitizenId() const { return CurrentCitizenId; }

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetHeaderTextString() const;

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetActivityTextString() const;

	DECLARE_DELEGATE(FOnCloseRequested);
	FOnCloseRequested OnCloseRequested;

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void NativeConstruct() override;

private:
	UFUNCTION()
	void HandleAcceptOfferedTaskClicked();

	UFUNCTION()
	void HandleCompleteFetchClicked();

	UFUNCTION()
	void HandleCloseClicked();

	FName CurrentCitizenId;
	FName OfferedTaskId;
	FName ActiveFetchTaskId;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> HeaderText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> ActivityText;

	UPROPERTY(Transient)
	TObjectPtr<UVerticalBox> TaskBox;
};
