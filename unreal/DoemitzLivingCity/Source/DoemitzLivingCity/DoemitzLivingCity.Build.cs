using UnrealBuildTool;

public class DoemitzLivingCity : ModuleRules
{
	public DoemitzLivingCity(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine" });
		PrivateDependencyModuleNames.AddRange(new[] { "AssetRegistry", "EnhancedInput", "InputCore", "UMG", "Slate", "SlateCore", "RenderCore", "RHI", "Json", "JsonUtilities" });
	}
}
