using UnrealBuildTool;
public class YesterdayHarborEditorTarget : TargetRules
{
    public YesterdayHarborEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V7;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;
        ExtraModuleNames.Add("YesterdayHarbor");
    }
}
