using UnrealBuildTool;

public class DoemitzLivingCityEditorTarget : TargetRules
{
	public DoemitzLivingCityEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V7;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;
		ExtraModuleNames.Add("DoemitzLivingCity");
	}
}
