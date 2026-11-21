#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "DoemitzCharacter.generated.h"

class UInputAction;

UCLASS()
class DOEMITZLIVINGCITY_API ADoemitzCharacter : public ACharacter
{
	GENERATED_BODY()

protected:
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void UnPossessed() override;

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
