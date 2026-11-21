#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "DoemitzInteractionComponent.generated.h"

class UDoemitzPlaceMenuWidget;

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
	FName GetNearestPlaceId() const { return NearestPlaceId; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	FName GetNearestEntranceId() const { return NearestEntranceId; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	bool IsNearestPlaceOpen() const { return bNearestPlaceOpen; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	FString GetInteractionPrompt() const { return CurrentPrompt; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	bool IsMenuOpen() const { return ActiveMenuWidget != nullptr; }

	UFUNCTION(BlueprintPure, Category = "Interaction")
	UDoemitzPlaceMenuWidget* GetActiveMenuWidget() const { return ActiveMenuWidget; }

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction", meta = (Units = "cm"))
	double InteractionRadiusCm = 200.0;

private:
	FName NearestPlaceId;
	FName NearestEntranceId;
	FString NearestPlaceDisplayName;
	bool bNearestPlaceOpen = false;
	FString CurrentPrompt;

	UPROPERTY(Transient)
	TObjectPtr<UDoemitzPlaceMenuWidget> ActiveMenuWidget;
};
