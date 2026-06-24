using UnrealBuildTool;
using System.Collections.Generic;

public class UE_CSAgent_demoEditorTarget : TargetRules
{
    public UE_CSAgent_demoEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_6;
        ExtraModuleNames.Add("UE_CSAgent_demo");
    }
}
