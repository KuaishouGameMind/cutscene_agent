using UnrealBuildTool;
using System.Collections.Generic;

public class UE_CSAgent_demoTarget : TargetRules
{
    public UE_CSAgent_demoTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_6;
        ExtraModuleNames.Add("UE_CSAgent_demo");
    }
}
