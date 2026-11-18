using UnrealBuildTool;

public class YesterdaySaveGuard : ModuleRules
{
    public YesterdaySaveGuard(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.Add("Json");
        if (Target.Platform == UnrealTargetPlatform.Win64)
        {
            PublicSystemLibraries.Add("bcrypt.lib"); // Windows CNG SHA-256 for the exact pinned legacy import.
        }
        // Android (Meta Quest 3) uses the portable SHA-256 and POSIX file primitives in the library source.
    }
}
