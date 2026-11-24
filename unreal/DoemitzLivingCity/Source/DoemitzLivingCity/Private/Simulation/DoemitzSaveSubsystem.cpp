#include "Simulation/DoemitzSaveSubsystem.h"

#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Economy/DoemitzEconomySubsystem.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Simulation/DoemitzCitizenActor.h"
#include "Simulation/DoemitzCitizenSubsystem.h"
#include "Simulation/DoemitzSaveGame.h"
#include "Simulation/DoemitzSimulationSubsystem.h"
#include "Tasks/DoemitzTaskSubsystem.h"
#include "Traffic/DoemitzTrafficSubsystem.h"
#include "Traffic/DoemitzTrafficVehicle.h"
#include "World/DoemitzDayNightController.h"
#include "World/DoemitzWorldTools.h"

namespace
{
	bool IsBuildingStructureHit(const FHitResult& Hit)
	{
		const UStaticMeshComponent* SMC = Cast<UStaticMeshComponent>(Hit.GetComponent());
		const UStaticMesh* Mesh = SMC ? SMC->GetStaticMesh() : nullptr;
		if (!Mesh)
		{
			return false;
		}
		const FString MeshName = Mesh->GetName();
		return MeshName.StartsWith(TEXT("SM_Roofs"))
			|| MeshName.StartsWith(TEXT("SM_Walls"))
			|| MeshName.StartsWith(TEXT("SM_Gable"))
			|| MeshName.StartsWith(TEXT("SM_StoneTrim"))
			|| MeshName.StartsWith(TEXT("SM_TimberTrim"))
			|| MeshName.StartsWith(TEXT("SM_Doors"))
			|| MeshName.StartsWith(TEXT("SM_Window"))
			|| MeshName.StartsWith(TEXT("SM_Shutters"))
			|| MeshName.StartsWith(TEXT("SM_Flower"))
			|| MeshName.StartsWith(TEXT("SM_InteriorCeiling"))
			|| MeshName.StartsWith(TEXT("SM_InteriorFurniture"))
			|| MeshName.StartsWith(TEXT("SM_InteriorGoods"))
			|| MeshName.StartsWith(TEXT("SM_InteriorLamp"))
			|| MeshName.StartsWith(TEXT("SM_InteriorDoor"))
			|| MeshName.StartsWith(TEXT("SM_InteriorWalls"))
			|| MeshName.StartsWith(TEXT("SM_Notice"))
			|| MeshName.StartsWith(TEXT("SM_LockRailing"))
			|| MeshName.StartsWith(TEXT("SM_PierPile"));
	}

	bool TraceStaticGroundZ(UWorld* World, double WorldX, double WorldY, double ReferenceZ, double& OutGroundZ)
	{
		if (!World)
		{
			return false;
		}
		FCollisionQueryParams Params(SCENE_QUERY_STAT(DoemitzSaveGroundTrace), false);
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			if (APawn* Pawn = PC->GetPawn())
			{
				Params.AddIgnoredActor(Pawn);
			}
		}
		for (TActorIterator<ADoemitzCitizenActor> It(World); It; ++It)
		{
			Params.AddIgnoredActor(*It);
		}
		for (TActorIterator<ADoemitzTrafficVehicle> It(World); It; ++It)
		{
			Params.AddIgnoredActor(*It);
		}
		double TraceStartZ = FMath::Max(5000.0, ReferenceZ + 2000.0);
		for (int32 Iter = 0; Iter < 12 && TraceStartZ > -5000.0; ++Iter)
		{
			FHitResult Hit;
			if (!World->LineTraceSingleByChannel(
				Hit,
				FVector(WorldX, WorldY, TraceStartZ),
				FVector(WorldX, WorldY, -5000.0),
				ECC_Visibility,
				Params))
			{
				return false;
			}
			if (IsBuildingStructureHit(Hit))
			{
				if (const UPrimitiveComponent* Comp = Hit.GetComponent())
				{
					Params.AddIgnoredComponent(Comp);
				}
				TraceStartZ = Hit.ImpactPoint.Z - 5.0;
				continue;
			}
			if (Hit.ImpactNormal.Z < 0.5f)
			{
				TraceStartZ = Hit.ImpactPoint.Z - 5.0;
				continue;
			}
			OutGroundZ = Hit.ImpactPoint.Z;
			return true;
		}
		return false;
	}
}

bool UDoemitzSaveSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}
	const UWorld* World = Cast<UWorld>(Outer);
	return World != nullptr && World->IsGameWorld();
}

TStatId UDoemitzSaveSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UDoemitzSaveSubsystem, STATGROUP_Tickables);
}

void UDoemitzSaveSubsystem::CancelPendingRestore()
{
	if (!PendingRestore.bActive)
	{
		return;
	}
	if (PendingRestore.bRestoreGravity)
	{
		if (UWorld* World = GetWorld())
		{
			if (APlayerController* PC = World->GetFirstPlayerController())
			{
				if (ACharacter* Char = Cast<ACharacter>(PC->GetPawn()))
				{
					if (UCharacterMovementComponent* Move = Char->GetCharacterMovement())
					{
						Move->GravityScale = PendingRestore.SavedGravityScale;
					}
				}
			}
		}
	}
	PendingRestore = FPendingStreamingRestore();
}

void UDoemitzSaveSubsystem::FinalizeLoadedGroundSnap()
{
	UWorld* World = GetWorld();
	UDoemitzSimulationSubsystem* Sim = World ? World->GetSubsystem<UDoemitzSimulationSubsystem>() : nullptr;
	if (!World || !Sim)
	{
		CancelPendingRestore();
		return;
	}

	if (PendingRestore.bHasPlayerTransform)
	{
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			if (APawn* Pawn = PC->GetPawn())
			{
				FVector RestoredPlayerLoc = PendingRestore.TargetPlayerLocation;
				double GroundZ = RestoredPlayerLoc.Z;
				double HalfHeight = 96.0;
				if (const ACharacter* Char = Cast<ACharacter>(Pawn))
				{
					if (const UCapsuleComponent* Cap = Char->GetCapsuleComponent())
					{
						HalfHeight = Cap->GetScaledCapsuleHalfHeight() + 4.0;
					}
				}
				LastLoadedPlayerInteriorId = NAME_None;

				if (PendingRestore.bRemovedInteriorFallback)
				{
					FDoemitzPlaceDefinition Place;
					if (Sim->GetPlaceDefinition(PendingRestore.PlayerInteriorPlaceId, Place))
					{
						RestoredPlayerLoc = !Place.EntranceLocation.IsNearlyZero() ? Place.EntranceLocation : Place.AccessLocation;
					}
					if (TraceStaticGroundZ(World, RestoredPlayerLoc.X, RestoredPlayerLoc.Y, RestoredPlayerLoc.Z, GroundZ))
					{
						RestoredPlayerLoc.Z = GroundZ + HalfHeight;
					}
				}
				else if (PendingRestore.bHasSavedInterior)
				{
					const FDoemitzInteriorDefinition& SavedInterior = PendingRestore.SavedInterior;
					RestoredPlayerLoc.Z = FMath::Max(SavedInterior.FloorZ + HalfHeight, FMath::Min(RestoredPlayerLoc.Z, SavedInterior.CeilingZ - 20.0));
					FHitResult FloorHit;
					FCollisionQueryParams FloorParams(SCENE_QUERY_STAT(DoemitzInteriorLoadTrace), false, Pawn);
					if (World->LineTraceSingleByChannel(
						FloorHit,
						FVector(RestoredPlayerLoc.X, RestoredPlayerLoc.Y, SavedInterior.CeilingZ - 15.0),
						FVector(RestoredPlayerLoc.X, RestoredPlayerLoc.Y, SavedInterior.FloorZ - 100.0),
						ECC_Visibility,
						FloorParams) && FloorHit.ImpactNormal.Z > 0.5f)
					{
						RestoredPlayerLoc.Z = FloorHit.ImpactPoint.Z + HalfHeight;
					}
					else
					{
						RestoredPlayerLoc.Z = SavedInterior.FloorZ + HalfHeight;
					}
					LastLoadedPlayerInteriorId = PendingRestore.PlayerInteriorId;
				}
				else if (PendingRestore.bMigratingFromPreV6)
				{
					if (TraceStaticGroundZ(World, RestoredPlayerLoc.X, RestoredPlayerLoc.Y, RestoredPlayerLoc.Z, GroundZ))
					{
						RestoredPlayerLoc.Z = GroundZ + HalfHeight;
					}
				}
				else if (TraceStaticGroundZ(World, RestoredPlayerLoc.X, RestoredPlayerLoc.Y, RestoredPlayerLoc.Z, GroundZ) && GroundZ > RestoredPlayerLoc.Z + 25.0)
				{
					RestoredPlayerLoc.Z = GroundZ + HalfHeight;
				}

				Pawn->SetActorLocationAndRotation(RestoredPlayerLoc, PendingRestore.TargetPlayerRotation, false, nullptr, ETeleportType::TeleportPhysics);
				if (ACharacter* Char = Cast<ACharacter>(Pawn))
				{
					if (UCharacterMovementComponent* Move = Char->GetCharacterMovement())
					{
						if (PendingRestore.bRestoreGravity)
						{
							Move->GravityScale = PendingRestore.SavedGravityScale;
						}
						Move->StopMovementImmediately();
					}
				}
			}
		}
	}

	if (UDoemitzCitizenSubsystem* Citizens = World->GetSubsystem<UDoemitzCitizenSubsystem>())
	{
		Citizens->UpdateCitizenLodPool();
		Citizens->SyncAllActiveCitizenActors();
	}

	const double Elapsed = PendingRestore.ElapsedSeconds;
	const FString Slot = PendingRestore.SlotName;
	PendingRestore = FPendingStreamingRestore();
	if (Elapsed > 0.0)
	{
		UE_LOG(LogTemp, Display, TEXT("Doemitz save load streaming finalized for slot '%s' after %.2fs"), *Slot, Elapsed);
	}
}

void UDoemitzSaveSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	if (!PendingRestore.bActive)
	{
		return;
	}
	UWorld* World = GetWorld();
	if (!World)
	{
		CancelPendingRestore();
		return;
	}
	PendingRestore.ElapsedSeconds += FMath::Max(0.0, static_cast<double>(DeltaTime));

	const bool bStreamingReady = UDoemitzWorldTools::IsStreamingCompleted(World);
	bool bGroundReady = false;
	if (bStreamingReady)
	{
		double ProbeZ = 0.0;
		if (PendingRestore.bHasSavedInterior)
		{
			FHitResult FloorHit;
			FCollisionQueryParams FloorParams(SCENE_QUERY_STAT(DoemitzInteriorLoadReady), false);
			if (APlayerController* PC = World->GetFirstPlayerController())
			{
				if (APawn* Pawn = PC->GetPawn())
				{
					FloorParams.AddIgnoredActor(Pawn);
				}
			}
			bGroundReady = World->LineTraceSingleByChannel(
				FloorHit,
				FVector(PendingRestore.TargetPlayerLocation.X, PendingRestore.TargetPlayerLocation.Y, PendingRestore.SavedInterior.CeilingZ - 15.0),
				FVector(PendingRestore.TargetPlayerLocation.X, PendingRestore.TargetPlayerLocation.Y, PendingRestore.SavedInterior.FloorZ - 100.0),
				ECC_Visibility,
				FloorParams) && FloorHit.ImpactNormal.Z > 0.5f;
		}
		else
		{
			bGroundReady = TraceStaticGroundZ(
				World,
				PendingRestore.TargetPlayerLocation.X,
				PendingRestore.TargetPlayerLocation.Y,
				PendingRestore.TargetPlayerLocation.Z,
				ProbeZ);
		}
	}

	if ((bStreamingReady && bGroundReady) || PendingRestore.ElapsedSeconds >= PendingRestore.MaxWaitSeconds)
	{
		if (PendingRestore.bMigratingFromPreV6 && !PendingRestore.SlotName.IsEmpty())
		{
			if (const UDoemitzSaveGame* SaveObj = Cast<UDoemitzSaveGame>(UGameplayStatics::LoadGameFromSlot(PendingRestore.SlotName, 0)))
			{
				if (UDoemitzCitizenSubsystem* Citizens = World->GetSubsystem<UDoemitzCitizenSubsystem>())
				{
					Citizens->RestoreSaveState(
						SaveObj,
						true,
						[World](double X, double Y, double RefZ, double& OutZ) {
							return TraceStaticGroundZ(World, X, Y, RefZ, OutZ);
						});
				}
			}
		}
		FinalizeLoadedGroundSnap();
	}
}

UDoemitzSaveSubsystem* UDoemitzSaveSubsystem::Get(const UObject* WorldContextObject)
{
	if (!WorldContextObject)
	{
		return nullptr;
	}
	const UWorld* World = WorldContextObject->GetWorld();
	return World ? World->GetSubsystem<UDoemitzSaveSubsystem>() : nullptr;
}

bool UDoemitzSaveSubsystem::DoesSaveExist(const FString& SlotName) const
{
	return !SlotName.IsEmpty() && UGameplayStatics::DoesSaveGameExist(SlotName, 0);
}

bool UDoemitzSaveSubsystem::SaveCityState(const FString& SlotName)
{
	UWorld* World = GetWorld();
	UDoemitzSimulationSubsystem* Sim = World ? World->GetSubsystem<UDoemitzSimulationSubsystem>() : nullptr;
	if (!Sim || !Sim->IsConfigured() || SlotName.IsEmpty())
	{
		return false;
	}

	UDoemitzSaveGame* SaveObj = Cast<UDoemitzSaveGame>(UGameplayStatics::CreateSaveGameObject(UDoemitzSaveGame::StaticClass()));
	if (!SaveObj)
	{
		return false;
	}

	UDoemitzEconomySubsystem* Economy = World->GetSubsystem<UDoemitzEconomySubsystem>();
	UDoemitzTaskSubsystem* Tasks = World->GetSubsystem<UDoemitzTaskSubsystem>();
	UDoemitzCitizenSubsystem* Citizens = World->GetSubsystem<UDoemitzCitizenSubsystem>();
	UDoemitzTrafficSubsystem* Traffic = World->GetSubsystem<UDoemitzTrafficSubsystem>();

	SaveObj->SaveSchemaVersion = UDoemitzSaveGame::CurrentSchemaVersion;
	SaveObj->DayNumber = Sim->GetDayNumber();
	SaveObj->DayOfWeek = Sim->GetDayOfWeek();
	SaveObj->CalendarWeek = Sim->GetCalendarWeek();
	SaveObj->TimeOfDayMinutes = Sim->GetTimeOfDayMinutes();
	SaveObj->TimeScale = (Economy && Economy->IsWorkingShift()) ? Economy->GetPreShiftTimeScale() : Sim->GetTimeScale();

	if (Economy)
	{
		Economy->CaptureSaveState(SaveObj);
	}
	if (Tasks)
	{
		Tasks->CaptureSaveState(SaveObj);
	}
	if (Traffic)
	{
		Traffic->CaptureSaveState(SaveObj);
	}
	if (Citizens)
	{
		Citizens->CaptureSaveState(SaveObj);
	}

	if (APlayerController* PC = World->GetFirstPlayerController())
	{
		if (APawn* Pawn = PC->GetPawn())
		{
			SaveObj->bHasPlayerTransform = true;
			SaveObj->PlayerLocation = Pawn->GetActorLocation();
			SaveObj->PlayerRotation = Pawn->GetActorRotation();
			SaveObj->PlayerInteriorId = Sim->FindInteriorAtLocation(Pawn->GetActorLocation());
			FDoemitzInteriorDefinition Interior;
			if (!SaveObj->PlayerInteriorId.IsNone() && Sim->GetInteriorById(SaveObj->PlayerInteriorId, Interior))
			{
				SaveObj->PlayerInteriorPlaceId = Interior.PlaceId;
			}
		}
	}

	const bool bSaved = UGameplayStatics::SaveGameToSlot(SaveObj, SlotName, 0);
	if (bSaved)
	{
		FDoemitzNotificationEvent Ev;
		Ev.Code = EDoemitzNotificationCode::SaveSucceeded;
		Ev.ParameterKey = SlotName;
		Sim->PushNotificationEvent(Ev);
		UE_LOG(LogTemp, Display, TEXT("Doemitz save v%d written to slot '%s' (Day %d, %.1f min, %d citizens, %d vehicles, %d tasks)"),
			SaveObj->SaveSchemaVersion, *SlotName, SaveObj->DayNumber, SaveObj->TimeOfDayMinutes,
			SaveObj->Citizens.Num(), SaveObj->Vehicles.Num(), SaveObj->Tasks.Num());
	}
	return bSaved;
}

bool UDoemitzSaveSubsystem::LoadCityState(const FString& SlotName)
{
	UWorld* World = GetWorld();
	UDoemitzSimulationSubsystem* Sim = World ? World->GetSubsystem<UDoemitzSimulationSubsystem>() : nullptr;
	if (!Sim || !Sim->IsConfigured() || !DoesSaveExist(SlotName))
	{
		return false;
	}

	const UDoemitzSaveGame* SaveObj = Cast<UDoemitzSaveGame>(UGameplayStatics::LoadGameFromSlot(SlotName, 0));
	if (!SaveObj || SaveObj->SaveSchemaVersion < 1 || SaveObj->SaveSchemaVersion > UDoemitzSaveGame::CurrentSchemaVersion)
	{
		return false;
	}

	const bool bMigratingFromV1 = (SaveObj->SaveSchemaVersion == 1);
	const bool bMigratingFromPreV3 = (SaveObj->SaveSchemaVersion < 3);
	const bool bMigratingFromPreV4 = (SaveObj->SaveSchemaVersion < 4);
	const bool bMigratingFromPreV5 = (SaveObj->SaveSchemaVersion < 5);
	const bool bMigratingFromPreV6 = (SaveObj->SaveSchemaVersion < 6);

	UDoemitzEconomySubsystem* Economy = World->GetSubsystem<UDoemitzEconomySubsystem>();
	UDoemitzTaskSubsystem* Tasks = World->GetSubsystem<UDoemitzTaskSubsystem>();
	UDoemitzCitizenSubsystem* Citizens = World->GetSubsystem<UDoemitzCitizenSubsystem>();
	UDoemitzTrafficSubsystem* Traffic = World->GetSubsystem<UDoemitzTrafficSubsystem>();

	if (Economy)
	{
		Economy->CancelActiveWorkShiftForLoad();
	}

	const int32 RestoredDayNumber = FMath::Max(1, SaveObj->DayNumber);
	const int32 RestoredDayOfWeek = bMigratingFromPreV3 ? 0 : (((SaveObj->DayOfWeek % 7) + 7) % 7);
	const int32 RestoredCalendarWeek = bMigratingFromPreV3 ? (1 + ((RestoredDayNumber - 1) / 7)) : FMath::Max(1, SaveObj->CalendarWeek);
	Sim->RestoreClockState(RestoredDayNumber, RestoredDayOfWeek, RestoredCalendarWeek, SaveObj->TimeOfDayMinutes, SaveObj->TimeScale);

	if (Economy)
	{
		Economy->RestoreSaveState(SaveObj, bMigratingFromPreV4);
	}
	if (Tasks)
	{
		Tasks->RestoreSaveState(SaveObj, bMigratingFromPreV5);
	}
	if (Citizens)
	{
		Citizens->RestoreSaveState(
			SaveObj,
			bMigratingFromPreV6,
			[World](double X, double Y, double RefZ, double& OutZ) {
				return TraceStaticGroundZ(World, X, Y, RefZ, OutZ);
			});
	}
	if (Traffic)
	{
		Traffic->RestoreSaveState(SaveObj, bMigratingFromV1, bMigratingFromPreV5);
	}

	if (SaveObj->bHasPlayerTransform)
	{
		CancelPendingRestore();
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			if (APawn* Pawn = PC->GetPawn())
			{
				FDoemitzInteriorDefinition SavedInterior;
				const bool bHasSavedInterior = SaveObj->SaveSchemaVersion >= 7 &&
					!SaveObj->PlayerInteriorId.IsNone() &&
					Sim->GetInteriorById(SaveObj->PlayerInteriorId, SavedInterior);
				const bool bRemovedInteriorFallback = SaveObj->SaveSchemaVersion >= 7 &&
					!SaveObj->PlayerInteriorId.IsNone() && !bHasSavedInterior;

				FVector TargetLoc = SaveObj->PlayerLocation;
				if (bRemovedInteriorFallback)
				{
					FDoemitzPlaceDefinition Place;
					if (Sim->GetPlaceDefinition(SaveObj->PlayerInteriorPlaceId, Place))
					{
						TargetLoc = !Place.EntranceLocation.IsNearlyZero() ? Place.EntranceLocation : Place.AccessLocation;
					}
				}

				const double JumpDistCm = FVector::Dist2D(Pawn->GetActorLocation(), TargetLoc);
				// Move player immediately so World Partition updates streaming sources around the destination cell.
				Pawn->SetActorLocationAndRotation(TargetLoc, SaveObj->PlayerRotation, false, nullptr, ETeleportType::TeleportPhysics);

				PendingRestore = FPendingStreamingRestore();
				PendingRestore.bActive = true;
				PendingRestore.SlotName = SlotName;
				PendingRestore.SaveSchemaVersion = SaveObj->SaveSchemaVersion;
				PendingRestore.bHasPlayerTransform = true;
				PendingRestore.TargetPlayerLocation = TargetLoc;
				PendingRestore.TargetPlayerRotation = SaveObj->PlayerRotation;
				PendingRestore.bHasSavedInterior = bHasSavedInterior;
				PendingRestore.SavedInterior = SavedInterior;
				PendingRestore.bRemovedInteriorFallback = bRemovedInteriorFallback;
				PendingRestore.PlayerInteriorId = SaveObj->PlayerInteriorId;
				PendingRestore.PlayerInteriorPlaceId = SaveObj->PlayerInteriorPlaceId;
				PendingRestore.bMigratingFromPreV6 = bMigratingFromPreV6;
				PendingRestore.ElapsedSeconds = 0.0;

				// Check if destination ground/interior is already loaded in World Partition (same cell / within LoadingRange).
				const bool bStreamingReady = UDoemitzWorldTools::IsStreamingCompleted(World);
				bool bDestinationLoaded = false;
				if (bStreamingReady && JumpDistCm < 25000.0)
				{
					if (bHasSavedInterior)
					{
						FHitResult FloorHit;
						FCollisionQueryParams FloorParams(SCENE_QUERY_STAT(DoemitzInteriorLoadProbe), false, Pawn);
						bDestinationLoaded = World->LineTraceSingleByChannel(
							FloorHit,
							FVector(TargetLoc.X, TargetLoc.Y, SavedInterior.CeilingZ - 15.0),
							FVector(TargetLoc.X, TargetLoc.Y, SavedInterior.FloorZ - 100.0),
							ECC_Visibility,
							FloorParams) && FloorHit.ImpactNormal.Z > 0.5f;
					}
					else
					{
						double ProbeZ = 0.0;
						bDestinationLoaded = TraceStaticGroundZ(World, TargetLoc.X, TargetLoc.Y, TargetLoc.Z, ProbeZ);
					}
				}

				if (bDestinationLoaded)
				{
					FinalizeLoadedGroundSnap();
				}
				else
				{
					// Cross-cell load (Sprint 16): suspend gravity until World Partition finishes streaming destination cells,
					// then snap cleanly onto the loaded terrain/interior floor in Tick().
					if (ACharacter* Char = Cast<ACharacter>(Pawn))
					{
						if (UCharacterMovementComponent* Move = Char->GetCharacterMovement())
						{
							PendingRestore.SavedGravityScale = Move->GravityScale;
							PendingRestore.bRestoreGravity = true;
							Move->GravityScale = 0.0f;
							Move->StopMovementImmediately();
						}
					}
					LastLoadedPlayerInteriorId = bHasSavedInterior ? SaveObj->PlayerInteriorId : NAME_None;
					UE_LOG(LogTemp, Display, TEXT("Doemitz save load waiting for World Partition streaming (jump %.0f cm, slot '%s')"),
						JumpDistCm, *SlotName);
				}
			}
		}
	}

	for (TActorIterator<ADoemitzTrafficVehicle> It(World); It; ++It)
	{
		if (ADoemitzTrafficVehicle* Vehicle = *It)
		{
			Vehicle->SyncFromSimulation();
		}
	}

	for (TActorIterator<ADoemitzDayNightController> It(World); It; ++It)
	{
		if (ADoemitzDayNightController* Controller = *It)
		{
			Controller->UpdateLightingFromSimulation();
		}
	}

	if (Citizens)
	{
		Citizens->UpdateCitizenLodPool();
		Citizens->SyncAllActiveCitizenActors();
	}

	if (bMigratingFromPreV6)
	{
		UE_LOG(LogTemp, Display, TEXT("Migrated SaveGame v%d -> v%d (terrain height migration) for slot '%s'"),
			SaveObj->SaveSchemaVersion, UDoemitzSaveGame::CurrentSchemaVersion, *SlotName);
	}

	FDoemitzNotificationEvent Ev;
	Ev.Code = EDoemitzNotificationCode::LoadSucceeded;
	Ev.ParameterKey = SlotName;
	Sim->PushNotificationEvent(Ev);
	UE_LOG(LogTemp, Display, TEXT("Doemitz save v%d loaded from slot '%s' (Day %d, dow %d, KW %d, %.1f min, %d tasks)"),
		SaveObj->SaveSchemaVersion, *SlotName, Sim->GetDayNumber(), Sim->GetDayOfWeek(),
		Sim->GetCalendarWeek(), Sim->GetTimeOfDayMinutes(), Tasks ? Tasks->GetAllTasks().Num() : 0);
	return true;
}
