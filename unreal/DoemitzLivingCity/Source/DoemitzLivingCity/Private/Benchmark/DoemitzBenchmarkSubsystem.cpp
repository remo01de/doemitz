#include "Benchmark/DoemitzBenchmarkSubsystem.h"

#include "Algo/BinarySearch.h"
#include "Components/PointLightComponent.h"
#include "Dom/JsonObject.h"
#include "DynamicRHI.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/PointLight.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameUserSettings.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "GenericPlatform/GenericPlatformMisc.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformFileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "RenderTimer.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Settings/DoemitzGraphicsSettings.h"
#include "Simulation/DoemitzSimulationConfig.h"
#include "Traffic/DoemitzTrafficVehicle.h"

namespace
{
	double ComputeMean(const TArray<double>& Values)
	{
		if (Values.IsEmpty())
		{
			return 0.0;
		}
		double Sum = 0.0;
		for (double V : Values)
		{
			Sum += V;
		}
		return Sum / static_cast<double>(Values.Num());
	}

	double ComputePercentile(TArray<double> SortedValues, double Percentile)
	{
		if (SortedValues.IsEmpty())
		{
			return 0.0;
		}
		SortedValues.Sort();
		const double Rank = FMath::Clamp(Percentile, 0.0, 1.0) * static_cast<double>(SortedValues.Num() - 1);
		const int32 Lower = FMath::FloorToInt(Rank);
		const int32 Upper = FMath::CeilToInt(Rank);
		if (Lower == Upper)
		{
			return SortedValues[Lower];
		}
		const double Alpha = Rank - static_cast<double>(Lower);
		return FMath::Lerp(SortedValues[Lower], SortedValues[Upper], Alpha);
	}
}

bool UDoemitzBenchmarkSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}
	const UWorld* World = Cast<UWorld>(Outer);
	return World != nullptr && World->IsGameWorld();
}

TStatId UDoemitzBenchmarkSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UDoemitzBenchmarkSubsystem, STATGROUP_Tickables);
}

void UDoemitzBenchmarkSubsystem::ApplyGraphicsProfile(const FString& InProfileName, UWorld* World)
{
	if (UDoemitzGraphicsSettings* Settings = UDoemitzGraphicsSettings::Get())
	{
		Settings->ApplyProfile(InProfileName, World, false);
	}
}

void UDoemitzBenchmarkSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);

	const TCHAR* CmdLine = FCommandLine::Get();
	FString RequestedProfile;
	if (FParse::Value(CmdLine, TEXT("DoemitzProfile="), RequestedProfile))
	{
		ProfileName = UDoemitzGraphicsSettings::NormalizeProfileName(RequestedProfile);
		ApplyGraphicsProfile(ProfileName, &InWorld);
	}
	else if (UDoemitzGraphicsSettings* Settings = UDoemitzGraphicsSettings::Get())
	{
		ProfileName = Settings->GetActiveProfileName();
		Settings->ApplyActiveProfile(&InWorld);
	}

	if (!FParse::Param(CmdLine, TEXT("DoemitzBenchmark")))
	{
		return;
	}

	FParse::Value(CmdLine, TEXT("DoemitzBenchmarkDuration="), DurationSeconds);
	FParse::Value(CmdLine, TEXT("DoemitzBenchmarkWarmup="), WarmupSeconds);
	FParse::Value(CmdLine, TEXT("DoemitzBenchmarkOut="), OutputPathOverride);
	bOpenCityMap = FParse::Param(CmdLine, TEXT("DoemitzBenchmarkOpenMap"));
	bMapOpenedForBenchmark = false;
	DurationSeconds = FMath::Max(1.0, DurationSeconds);
	WarmupSeconds = FMath::Max(0.0, WarmupSeconds);

	BuildBenchmarkRoute();
	if (RoutePoints.Num() < 2 || RouteLengthCm <= 1.0)
	{
		UE_LOG(LogTemp, Error, TEXT("Doemitz benchmark route could not be initialized."));
		return;
	}

	bBenchmarkActive = true;
	bFinished = false;
	ElapsedWarmup = 0.0;
	ElapsedBenchmark = 0.0;
	LastWallSeconds = FPlatformTime::Seconds();

	const int32 ExpectedFrames = FMath::CeilToInt(DurationSeconds * 60.0);
	FrameTimesMs.Reserve(ExpectedFrames);
	GameTimesMs.Reserve(ExpectedFrames);
	DrawTimesMs.Reserve(ExpectedFrames);
	GpuTimesMs.Reserve(ExpectedFrames);

	UE_LOG(LogTemp, Display, TEXT("Doemitz benchmark started: profile=%s warmup=%.1fs duration=%.1fs route=%.1fm"),
		*ProfileName, WarmupSeconds, DurationSeconds, RouteLengthCm / 100.0);
}

void UDoemitzBenchmarkSubsystem::BuildBenchmarkRoute()
{
	// Fixed Altstadt benchmark route: Goethestrasse -> Rathausplatz -> Festungszugang (An der Festung)
	// Coordinates in Unreal cm (X = North * 100, Y = East * 100, Z = 180 cm)
	RoutePoints = {
		FVector(-13001.7,   5429.4, 180.0),
		FVector(-14081.7,   5126.1, 180.0),
		FVector(-15617.4,   3777.3, 180.0),
		FVector(-20535.1,   -958.6, 180.0),
		FVector(-22824.7,  -3662.3, 180.0),
		FVector(-19564.1,  -6611.1, 180.0),
		FVector(-17979.8,  -8036.9, 180.0),
		FVector(-16132.9,  -9792.9, 180.0),
		FVector(-15269.2, -10529.8, 180.0),
		FVector(-14587.1, -11037.7, 180.0),
		FVector(-14988.9, -12133.3, 180.0),
		FVector(-14465.1, -14146.4, 180.0),
		FVector(-13659.3, -15798.7, 180.0),
		FVector(-13107.4, -16650.6, 180.0),
		FVector(-12589.4, -17131.5, 180.0),
		FVector(-11862.1, -17415.8, 180.0),
		FVector(-11418.6, -17495.7, 180.0)
	};

	SegmentEnds.Reset();
	double Cumulative = 0.0;
	for (int32 Index = 0; Index + 1 < RoutePoints.Num(); ++Index)
	{
		Cumulative += FMath::Max(FVector::Distance(RoutePoints[Index], RoutePoints[Index + 1]), UE_KINDA_SMALL_NUMBER);
		SegmentEnds.Add(Cumulative);
	}
	RouteLengthCm = Cumulative;
}

FVector UDoemitzBenchmarkSubsystem::SampleRouteLocation(double DistanceCm, FVector& OutForward) const
{
	const double Clamped = FMath::Clamp(DistanceCm, 0.0, RouteLengthCm);
	const int32 SegIndex = FMath::Clamp(
		Algo::UpperBound(SegmentEnds, Clamped),
		0,
		SegmentEnds.Num() - 1);
	const double SegStart = SegIndex == 0 ? 0.0 : SegmentEnds[SegIndex - 1];
	const double SegLen = FMath::Max(SegmentEnds[SegIndex] - SegStart, UE_KINDA_SMALL_NUMBER);
	const double Alpha = FMath::Clamp((Clamped - SegStart) / SegLen, 0.0, 1.0);
	const FVector& A = RoutePoints[SegIndex];
	const FVector& B = RoutePoints[SegIndex + 1];
	OutForward = (B - A).GetSafeNormal();
	return FMath::Lerp(A, B, Alpha);
}

void UDoemitzBenchmarkSubsystem::Tick(float DeltaTime)
{
	if (!bBenchmarkActive || bFinished)
	{
		return;
	}

	const double NowSeconds = FPlatformTime::Seconds();
	const double WallDeltaSeconds = FMath::Max(0.0, NowSeconds - LastWallSeconds);
	LastWallSeconds = NowSeconds;

	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	const double Progress = ElapsedWarmup < WarmupSeconds
		? 0.0
		: FMath::Clamp(ElapsedBenchmark / DurationSeconds, 0.0, 1.0);

	FVector Forward = FVector::ForwardVector;
	const FVector TargetLocation = SampleRouteLocation(Progress * RouteLengthCm, Forward);
	const FRotator LookRotation(FMath::Clamp(-5.0, -89.0, 89.0), Forward.Rotation().Yaw, 0.0);

	if (APlayerController* PC = World->GetFirstPlayerController())
	{
		if (APawn* Pawn = PC->GetPawn())
		{
			if (ACharacter* Character = Cast<ACharacter>(Pawn))
			{
				if (UCharacterMovementComponent* MoveComp = Character->GetCharacterMovement())
				{
					MoveComp->SetMovementMode(MOVE_Flying);
					MoveComp->Velocity = FVector::ZeroVector;
				}
			}
			Pawn->SetActorLocationAndRotation(
				TargetLocation,
				FRotator(0.0, LookRotation.Yaw, 0.0),
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
		}
		PC->SetControlRotation(LookRotation);
	}

	if (bOpenCityMap && !bMapOpenedForBenchmark)
	{
		for (TActorIterator<ADoemitzSimulationConfig> It(World); It; ++It)
		{
			if (ADoemitzSimulationConfig* Config = *It)
			{
				Config->SetCityMapOpen(true);
				if (Config->IsCityMapOpen())
				{
					bMapOpenedForBenchmark = true;
				}
				break;
			}
		}
	}

	if (ElapsedWarmup < WarmupSeconds)
	{
		ElapsedWarmup += WallDeltaSeconds;
		return;
	}

	if (WallDeltaSeconds > 0.0)
	{
		FrameTimesMs.Add(WallDeltaSeconds * 1000.0);
		GameTimesMs.Add(FPlatformTime::ToMilliseconds(GGameThreadTime));
		DrawTimesMs.Add(FPlatformTime::ToMilliseconds(GRenderThreadTime));
		GpuTimesMs.Add(FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles(0)));
	}

	ElapsedBenchmark += WallDeltaSeconds;
	if (ElapsedBenchmark >= DurationSeconds)
	{
		FinishBenchmark();
	}
}

void UDoemitzBenchmarkSubsystem::FinishBenchmark()
{
	bFinished = true;
	bBenchmarkActive = false;

	const double MeanMs = ComputeMean(FrameTimesMs);
	const double P50Ms = ComputePercentile(FrameTimesMs, 0.50);
	const double P95Ms = ComputePercentile(FrameTimesMs, 0.95);
	const double P99Ms = ComputePercentile(FrameTimesMs, 0.99);
	const double MinMs = ComputePercentile(FrameTimesMs, 0.0);
	const double MaxMs = ComputePercentile(FrameTimesMs, 1.0);

	const double MeanFps = MeanMs > 0.0 ? (1000.0 / MeanMs) : 0.0;
	const double P95Fps = P95Ms > 0.0 ? (1000.0 / P95Ms) : 0.0;
	const double P99Fps = P99Ms > 0.0 ? (1000.0 / P99Ms) : 0.0;

	const double GameMeanMs = ComputeMean(GameTimesMs);
	const double GameP95Ms = ComputePercentile(GameTimesMs, 0.95);
	const double DrawMeanMs = ComputeMean(DrawTimesMs);
	const double DrawP95Ms = ComputePercentile(DrawTimesMs, 0.95);
	const double GpuMeanMs = ComputeMean(GpuTimesMs);
	const double GpuP95Ms = ComputePercentile(GpuTimesMs, 0.95);

	int32 ResX = 0;
	int32 ResY = 0;
	if (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
	{
		const FIntPoint Size = GEngine->GameViewport->Viewport->GetSizeXY();
		ResX = Size.X;
		ResY = Size.Y;
	}

	int32 VehicleCount = 0;
	if (UWorld* World = GetWorld())
	{
		for (TActorIterator<ADoemitzTrafficVehicle> It(World); It; ++It)
		{
			++VehicleCount;
		}
	}

	const FString Timestamp = FDateTime::UtcNow().ToString(TEXT("%Y%m%d_%H%M%S"));
	FString OutFile = OutputPathOverride;
	if (OutFile.IsEmpty())
	{
		const FString BenchDir = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Benchmarks"));
		IFileManager::Get().MakeDirectory(*BenchDir, true);
		OutFile = FPaths::Combine(BenchDir, FString::Printf(TEXT("benchmark_%s_%s.json"), *ProfileName, *Timestamp));
	}
	else
	{
		IFileManager::Get().MakeDirectory(*FPaths::GetPath(OutFile), true);
	}

	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("profile"), ProfileName);
	Root->SetStringField(TEXT("route"), TEXT("Goethestrasse -> Rathausplatz -> Festungszugang"));
	Root->SetNumberField(TEXT("route_length_m"), RouteLengthCm / 100.0);
	Root->SetNumberField(TEXT("warmup_seconds"), WarmupSeconds);
	Root->SetNumberField(TEXT("duration_seconds"), ElapsedBenchmark);
	Root->SetNumberField(TEXT("frame_count"), FrameTimesMs.Num());
	Root->SetNumberField(TEXT("resolution_width"), ResX);
	Root->SetNumberField(TEXT("resolution_height"), ResY);
	Root->SetNumberField(TEXT("vehicle_count"), VehicleCount);
	Root->SetBoolField(TEXT("city_map_open"), bMapOpenedForBenchmark);
	Root->SetStringField(TEXT("cpu"), FPlatformMisc::GetCPUBrand());
	Root->SetStringField(TEXT("gpu"), FPlatformMisc::GetPrimaryGPUBrand());
	Root->SetStringField(TEXT("timestamp_utc"), FDateTime::UtcNow().ToIso8601());

	TSharedRef<FJsonObject> FrametimeObj = MakeShared<FJsonObject>();
	FrametimeObj->SetNumberField(TEXT("mean_ms"), MeanMs);
	FrametimeObj->SetNumberField(TEXT("p50_ms"), P50Ms);
	FrametimeObj->SetNumberField(TEXT("p95_ms"), P95Ms);
	FrametimeObj->SetNumberField(TEXT("p99_ms"), P99Ms);
	FrametimeObj->SetNumberField(TEXT("min_ms"), MinMs);
	FrametimeObj->SetNumberField(TEXT("max_ms"), MaxMs);
	Root->SetObjectField(TEXT("frametime"), FrametimeObj);

	TSharedRef<FJsonObject> FpsObj = MakeShared<FJsonObject>();
	FpsObj->SetNumberField(TEXT("mean"), MeanFps);
	FpsObj->SetNumberField(TEXT("p95_equivalent"), P95Fps);
	FpsObj->SetNumberField(TEXT("p99_equivalent"), P99Fps);
	Root->SetObjectField(TEXT("fps"), FpsObj);

	TSharedRef<FJsonObject> StatUnitObj = MakeShared<FJsonObject>();
	StatUnitObj->SetNumberField(TEXT("game_mean_ms"), GameMeanMs);
	StatUnitObj->SetNumberField(TEXT("game_p95_ms"), GameP95Ms);
	StatUnitObj->SetNumberField(TEXT("draw_mean_ms"), DrawMeanMs);
	StatUnitObj->SetNumberField(TEXT("draw_p95_ms"), DrawP95Ms);
	StatUnitObj->SetNumberField(TEXT("gpu_mean_ms"), GpuMeanMs);
	StatUnitObj->SetNumberField(TEXT("gpu_p95_ms"), GpuP95Ms);
	Root->SetObjectField(TEXT("stat_unit"), StatUnitObj);

	FString OutputJson;
	const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputJson);
	FJsonSerializer::Serialize(Root, Writer);
	FFileHelper::SaveStringToFile(OutputJson, *OutFile, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);

	UE_LOG(LogTemp, Display,
		TEXT("DOEMITZ_BENCHMARK_OK: profile=%s res=%dx%d frames=%d mean_fps=%.2f mean_ms=%.2f p95_ms=%.2f p99_ms=%.2f game_ms=%.2f draw_ms=%.2f gpu_ms=%.2f file=%s"),
		*ProfileName, ResX, ResY, FrameTimesMs.Num(), MeanFps, MeanMs, P95Ms, P99Ms, GameMeanMs, DrawMeanMs, GpuMeanMs, *OutFile);

	FGenericPlatformMisc::RequestExit(false);
}
