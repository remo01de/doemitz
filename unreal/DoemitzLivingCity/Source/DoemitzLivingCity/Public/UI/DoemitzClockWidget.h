#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "DoemitzClockWidget.generated.h"

class UTextBlock;

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzClockWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "UI")
	void RefreshDisplay();

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetClockTextString() const { return LastClockString; }

	UFUNCTION(BlueprintPure, Category = "UI")
	FString GetStatusTextString() const { return LastStatusString; }

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void NativeConstruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

private:
	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> ClockText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> StatusText;

	FString LastClockString;
	FString LastStatusString;
};
