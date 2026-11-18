using UnrealBuildTool;
public class YesterdayHarbor : ModuleRules
{
    public YesterdayHarbor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.AddRange(new string[] { "YesterdaySaveGuard", "InputCore", "UMG", "SlateCore" });
    }
}
