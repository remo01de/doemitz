#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "DoemitzInteractionComponent.generated.h"

class UDoemitzCitizenDialogWidget;
class UDoemitzPlaceMenuWidget;
class UDoemitzTaskBoardWidget;

UCLASS(ClassGroup = (Doemitz), meta = (BlueprintSpawnableComponent))
class DOEMITZLIVINGCITY_API UDoemitzInteractionComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UDoemitzInteractionComponent();

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	UFUNCTION(BlueprintCallable, Category = "Interaction")
	void RefreshNearestEntrance();

	UFUNCTION(BlueprintCallable, Category = "Interaction")
	bool TryInteract();

	UFUNCTION(BlueprintCallable, Category = "Interaction")
	void CloseMenu();

	UFUNCTION(BlueprintPure, Category = "Interaction")
	bool HasInteractableEntrance() const { return !NearestPlaceId.IsNone(); }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	bool HasInteractableCitizen() const { return !NearestCitizenId.IsNone(); }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	bool HasInteractableTarget() const { return !NearestPlaceId.IsNone() || !NearestCitizenId.IsNone() || !NearestNoticeBoardInteriorId.IsNone(); }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	bool HasInteractableNoticeBoard() const { return !NearestNoticeBoardInteriorId.IsNone(); }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	bool IsTaskBoardOpen() const { return ActiveTaskBoardWidget != nullptr; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	UDoemitzTaskBoardWidget* GetActiveTaskBoardWidget() const { return ActiveTaskBoardWidget; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	FName GetNearestPlaceId() const { return NearestPlaceId; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	FName GetNearestEntranceId() const { return NearestEntranceId; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	FName GetNearestCitizenId() const { return NearestCitizenId; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	bool IsNearestPlaceOpen() const { return bNearestPlaceOpen; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	FText GetInteractionPromptText() const { return CurrentPromptText; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	FString GetInteractionPrompt() const { return CurrentPromptText.ToString(); }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	bool IsMenuOpen() const { return ActiveMenuWidget != nullptr || ActiveCitizenDialogWidget != nullptr || ActiveTaskBoardWidget != nullptr; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	bool IsCitizenDialogOpen() const { return ActiveCitizenDialogWidget != nullptr; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	UDoemitzPlaceMenuWidget* GetActiveMenuWidget() const { return ActiveMenuWidget; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	UDoemitzCitizenDialogWidget* GetActiveCitizenDialogWidget() const { return ActiveCitizenDialogWidget; }

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction", meta = (Units = "cm"))
	double InteractionRadiusCm = 200.0;

private:
	FName NearestPlaceId;
	FName NearestEntranceId;
	FName NearestCitizenId;
	FName NearestNoticeBoardInteriorId;
	FName ActiveDialogCitizenId;
	bool bNearestPlaceOpen = false;
	FText CurrentPromptText;

	UPROPERTY(Transient)
	TObjectPtr<UDoemitzPlaceMenuWidget> ActiveMenuWidget;

	UPROPERTY(Transient)
	TObjectPtr<UDoemitzCitizenDialogWidget> ActiveCitizenDialogWidget;

	UPROPERTY(Transient)
	TObjectPtr<UDoemitzTaskBoardWidget> ActiveTaskBoardWidget;
};
