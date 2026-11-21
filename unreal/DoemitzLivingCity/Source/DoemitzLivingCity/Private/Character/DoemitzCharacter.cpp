#include "Character/DoemitzCharacter.h"

#include "EnhancedInputComponent.h"
#include "GameFramework/CharacterMovementComponent.h"

void ADoemitzCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	UEnhancedInputComponent* EnhancedInput = Cast<UEnhancedInputComponent>(PlayerInputComponent);
	if (EnhancedInput && SprintAction)
	{
		EnhancedInput->BindAction(SprintAction, ETriggerEvent::Started, this, &ADoemitzCharacter::StartSprint);
		EnhancedInput->BindAction(SprintAction, ETriggerEvent::Completed, this, &ADoemitzCharacter::StopSprint);
		EnhancedInput->BindAction(SprintAction, ETriggerEvent::Canceled, this, &ADoemitzCharacter::StopSprint);
	}
}

void ADoemitzCharacter::UnPossessed()
{
	StopSprint();
	Super::UnPossessed();
}

void ADoemitzCharacter::StartSprint()
{
	if (!bIsSprinting)
	{
		UCharacterMovementComponent* Movement = GetCharacterMovement();
		PreviousWalkSpeed = Movement->MaxWalkSpeed;
		Movement->MaxWalkSpeed = FMath::Max(PreviousWalkSpeed, SprintSpeed);
		bIsSprinting = true;
	}
}

void ADoemitzCharacter::StopSprint()
{
	if (bIsSprinting)
	{
		GetCharacterMovement()->MaxWalkSpeed = PreviousWalkSpeed;
		bIsSprinting = false;
	}
}
