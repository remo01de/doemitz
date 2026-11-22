#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "DoemitzTaskBoardWidget.generated.h"

class UTextBlock;
class UVerticalBox;

/** Sprint 13: notice board (Aushang) in the Rathaus Bürgerbüro listing today's task offers. */
UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzTaskBoardWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "UI")
	void RefreshContents();

	UFUNCTION(BlueprintPure, Category = "UI")
	int32 GetOfferCount() const { return OfferedTaskIds.Num(); }

	UFUNCTION(BlueprintPure, Category = "UI")
	FName GetOfferTaskId(int32 Index) const { return OfferedTaskIds.IsValidIndex(Index) ? OfferedTaskIds[Index] : NAME_None; }

	/** Accept the offer shown in row Index (same as clicking its button). */
	UFUNCTION(BlueprintCallable, Category = "UI")
	bool AcceptOfferAtIndex(int32 Index);

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetSummaryTextString() const;

	DECLARE_DELEGATE(FOnCloseRequested);
	FOnCloseRequested OnCloseRequested;

	static constexpr int32 MaxRows = 6;

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void NativeConstruct() override;

private:
	UFUNCTION()
	void HandleCloseClicked();
	UFUNCTION()
	void HandleAccept0();
	UFUNCTION()
	void HandleAccept1();
	UFUNCTION()
	void HandleAccept2();
	UFUNCTION()
	void HandleAccept3();
	UFUNCTION()
	void HandleAccept4();
	UFUNCTION()
	void HandleAccept5();

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> SummaryText;

	UPROPERTY(Transient)
	TObjectPtr<UVerticalBox> ListBox;

	TArray<FName> OfferedTaskIds;
};
