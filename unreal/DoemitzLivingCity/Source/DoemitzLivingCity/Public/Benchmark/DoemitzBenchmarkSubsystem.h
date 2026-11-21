#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "DoemitzBenchmarkSubsystem.generated.h"

UCLASS()
class DOEMITZLIVINGCITY_API UDoemitzBenchmarkSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual bool IsTickable() const override { return bBenchmarkActive; }
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

	static void ApplyGraphicsProfile(const FString& ProfileName, UWorld* World);

private:
	void BuildBenchmarkRoute();
	FVector SampleRouteLocation(double DistanceCm, FVector& OutForward) const;
	void FinishBenchmark();

	bool bBenchmarkActive = false;
	bool bFinished = false;
	FString ProfileName = TEXT("Default");
	FString OutputPathOverride;

	double WarmupSeconds = 3.0;
	double DurationSeconds = 90.0;
	double ElapsedWarmup = 0.0;
	double ElapsedBenchmark = 0.0;
	double LastWallSeconds = 0.0;

	TArray<FVector> RoutePoints;
	TArray<double> SegmentEnds;
	double RouteLengthCm = 0.0;

	TArray<double> FrameTimesMs;
	TArray<double> GameTimesMs;
	TArray<double> DrawTimesMs;
	TArray<double> GpuTimesMs;
};
