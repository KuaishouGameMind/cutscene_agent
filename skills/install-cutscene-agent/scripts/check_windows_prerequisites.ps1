[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectFile,

    [string]$UnrealEnginePath = "",

    [switch]$SkipBuildToolchainCheck
)

$ErrorActionPreference = "Stop"

function Get-ProjectEngineAssociation {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }

    try {
        $project = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
        return [string]$project.EngineAssociation
    }
    catch {
        return $null
    }
}

function Get-UnrealCandidates {
    param(
        [string]$RequestedVersion,
        [string]$ExplicitPath
    )

    $candidates = New-Object System.Collections.Generic.List[string]

    if ($ExplicitPath) {
        $candidates.Add($ExplicitPath)
    }

    if ($RequestedVersion) {
        foreach ($key in @(
            "HKLM:\SOFTWARE\EpicGames\Unreal Engine\$RequestedVersion",
            "HKLM:\SOFTWARE\WOW6432Node\EpicGames\Unreal Engine\$RequestedVersion"
        )) {
            if (Test-Path $key) {
                $installed = (Get-ItemProperty $key -ErrorAction SilentlyContinue).InstalledDirectory
                if ($installed) {
                    $candidates.Add([string]$installed)
                }
            }
        }
    }

    $buildsKey = "HKCU:\Software\Epic Games\Unreal Engine\Builds"
    if (Test-Path $buildsKey) {
        $properties = Get-ItemProperty $buildsKey -ErrorAction SilentlyContinue
        if ($properties) {
            foreach ($property in $properties.PSObject.Properties) {
                if ($property.Name -notmatch "^PS" -and $property.Value) {
                    $candidates.Add([string]$property.Value)
                }
            }
        }
    }

    if ($RequestedVersion) {
        $candidates.Add("C:\Program Files\Epic Games\UE_$RequestedVersion")
    }

    return $candidates | Where-Object { $_ } | Select-Object -Unique
}

function Find-UnrealEngine {
    param(
        [string]$RequestedVersion,
        [string]$ExplicitPath
    )

    foreach ($candidate in Get-UnrealCandidates $RequestedVersion $ExplicitPath) {
        $root = [System.IO.Path]::GetFullPath($candidate)
        $editor = Join-Path $root "Engine\Binaries\Win64\UnrealEditor.exe"
        $buildBat = Join-Path $root "Engine\Build\BatchFiles\Build.bat"

        if ((Test-Path -LiteralPath $editor -PathType Leaf) -and
            (Test-Path -LiteralPath $buildBat -PathType Leaf)) {
            $versionFile = Join-Path $root "Engine\Build\Build.version"
            $detectedVersion = $null
            if (Test-Path -LiteralPath $versionFile -PathType Leaf) {
                try {
                    $version = Get-Content -LiteralPath $versionFile -Raw | ConvertFrom-Json
                    $detectedVersion = "$($version.MajorVersion).$($version.MinorVersion)"
                }
                catch {
                    $detectedVersion = $null
                }
            }

            $requiresNumericVersionMatch = $RequestedVersion -match "^\d+\.\d+$"
            return [pscustomobject]@{
                Found = $true
                Root = $root
                Editor = $editor
                BuildBat = $buildBat
                RequestedVersion = $RequestedVersion
                DetectedVersion = $detectedVersion
                VersionMatches = (
                    -not $RequestedVersion -or
                    -not $requiresNumericVersionMatch -or
                    -not $detectedVersion -or
                    $RequestedVersion -eq $detectedVersion
                )
            }
        }
    }

    return [pscustomobject]@{
        Found = $false
        Root = $null
        Editor = $null
        BuildBat = $null
        RequestedVersion = $RequestedVersion
        DetectedVersion = $null
        VersionMatches = $false
    }
}

function Find-WindowsSdk {
    $roots = @(
        "HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows Kits\Installed Roots"
    )

    foreach ($key in $roots) {
        $kitsRoot = (Get-ItemProperty $key -ErrorAction SilentlyContinue).KitsRoot10
        if (-not $kitsRoot) {
            continue
        }

        $includeRoot = Join-Path $kitsRoot "Include"
        $versions = Get-ChildItem -LiteralPath $includeRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending

        foreach ($version in $versions) {
            if (Test-Path -LiteralPath (Join-Path $version.FullName "um\Windows.h") -PathType Leaf) {
                return [pscustomobject]@{
                    Found = $true
                    Root = $kitsRoot
                    Version = $version.Name
                }
            }
        }
    }

    return [pscustomobject]@{
        Found = $false
        Root = $null
        Version = $null
    }
}

function Find-VisualStudioToolchain {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) {
        return [pscustomobject]@{
            Found = $false
            Reason = "vswhere.exe was not found."
            Version = $null
            Root = $null
            MSBuild = $null
            Compiler = $null
            WindowsSdk = Find-WindowsSdk
        }
    }

    $installationsJson = & $vswhere `
        -products * `
        -version "[17.8,18.0)" `
        -requires Microsoft.VisualStudio.Workload.NativeGame `
        -format json

    $installations = $installationsJson | ConvertFrom-Json
    $installation = $installations |
        Sort-Object installationVersion -Descending |
        Select-Object -First 1

    if (-not $installation) {
        return [pscustomobject]@{
            Found = $false
            Reason = "Visual Studio 2022 17.8+ with Game development with C++ was not found."
            Version = $null
            Root = $null
            MSBuild = $null
            Compiler = $null
            WindowsSdk = Find-WindowsSdk
        }
    }

    $root = [string]$installation.installationPath
    $msbuild = Join-Path $root "MSBuild\Current\Bin\MSBuild.exe"
    $msvcRoot = Join-Path $root "VC\Tools\MSVC"
    $compiler = Get-ChildItem -LiteralPath $msvcRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object {
            $candidate = Join-Path $_.FullName "bin\Hostx64\x64\cl.exe"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                Get-Item -LiteralPath $candidate
            }
        } |
        Select-Object -First 1

    $sdk = Find-WindowsSdk
    $complete = (
        (Test-Path -LiteralPath $msbuild -PathType Leaf) -and
        ($null -ne $compiler) -and
        $sdk.Found
    )

    return [pscustomobject]@{
        Found = $complete
        Reason = if ($complete) { $null } else { "Visual Studio was found, but MSBuild, MSVC x64, or Windows SDK is incomplete." }
        Version = [string]$installation.installationVersion
        Root = $root
        MSBuild = if (Test-Path -LiteralPath $msbuild) { $msbuild } else { $null }
        Compiler = if ($compiler) { $compiler.FullName } else { $null }
        WindowsSdk = $sdk
    }
}

$resolvedProject = $null
try {
    $resolvedProject = (Resolve-Path -LiteralPath $ProjectFile).Path
}
catch {
    $resolvedProject = [System.IO.Path]::GetFullPath($ProjectFile)
}

$engineAssociation = Get-ProjectEngineAssociation $resolvedProject
$unreal = Find-UnrealEngine $engineAssociation $UnrealEnginePath
$toolchain = if ($SkipBuildToolchainCheck) {
    [pscustomobject]@{
        Found = $true
        Skipped = $true
        Reason = "Build toolchain check was explicitly skipped."
        Version = $null
        Root = $null
        MSBuild = $null
        Compiler = $null
        WindowsSdk = $null
    }
}
else {
    $result = Find-VisualStudioToolchain
    $result | Add-Member -NotePropertyName Skipped -NotePropertyValue $false
    $result
}

$missing = New-Object System.Collections.Generic.List[string]
$actions = New-Object System.Collections.Generic.List[string]

if (-not (Test-Path -LiteralPath $resolvedProject -PathType Leaf)) {
    $missing.Add("UE project file")
    $actions.Add("Provide a valid .uproject path.")
}

if (-not $unreal.Found) {
    $versionLabel = if ($engineAssociation) { $engineAssociation } else { "the project-required version" }
    $missing.Add("Unreal Engine $versionLabel")
    $actions.Add("Install Unreal Engine $versionLabel with Epic Games Launcher, or rerun with -UnrealEnginePath <path>.")
}
elseif (-not $unreal.VersionMatches) {
    $missing.Add("Matching Unreal Engine version")
    $actions.Add("Use Unreal Engine $engineAssociation or explicitly confirm that $($unreal.DetectedVersion) is compatible.")
}

if (-not $toolchain.Found) {
    $missing.Add("Visual Studio C++ build toolchain")
    $actions.Add("Install Visual Studio 2022 17.8+ with Game development with C++, MSVC v143 x64/x86 tools, and Windows 10/11 SDK.")
}

$ready = ($missing.Count -eq 0)
$result = [ordered]@{
    Ready = $ready
    ProjectFile = $resolvedProject
    EngineAssociation = $engineAssociation
    UnrealEngine = $unreal
    BuildToolchain = $toolchain
    Missing = @($missing)
    SuggestedActions = @($actions)
}

$result | ConvertTo-Json -Depth 8

if (-not $ready) {
    exit 2
}
