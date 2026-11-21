using UnrealBuildTool;

public class DoemitzLivingCity : ModuleRules
{
	public DoemitzLivingCity(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine" });
		PrivateDependencyModuleNames.Add("EnhancedInput");
	}
}
