#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "DoemitzCharacter.generated.h"

class UDoemitzInteractionComponent;
class UInputAction;

UCLASS()
class DOEMITZLIVINGCITY_API ADoemitzCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	ADoemitzCharacter();

	UFUNCTION(BlueprintPure, Category = "Interaction")
	UDoemitzInteractionComponent* GetInteractionComponent() const { return InteractionComponent; }

protected:
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void UnPossessed() override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Interaction")
	TObjectPtr<UDoemitzInteractionComponent> InteractionComponent;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Input")
	TObjectPtr<UInputAction> SprintAction;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Movement", meta = (ClampMin = "0.0", Units = "cm/s"))
	float SprintSpeed = 750.0f;

private:
	void StartSprint();
	void StopSprint();

	float PreviousWalkSpeed = 0.0f;
	bool bIsSprinting = false;
};
