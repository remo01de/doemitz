using UnrealBuildTool;

public class DoemitzLivingCityTarget : TargetRules
{
	public DoemitzLivingCityTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V7;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;
		ExtraModuleNames.Add("DoemitzLivingCity");
	}
}
