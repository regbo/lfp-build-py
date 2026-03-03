# Requires PowerShell
$ErrorActionPreference = "Stop"

$LfpBuildRepoUrlDefault = "https://github.com/regbo/lfp-build-py.git"
# NOTE: The package metadata name is "lfp-build" (not "lfp-build-py").
$LfpBuildSpecDefault = "lfp-build @ git+$LfpBuildRepoUrlDefault"

function Ensure-Home {
    if ($env:HOME -and (Test-Path $env:HOME)) {
        return $env:HOME
    }

    # Prefer USERPROFILE when available
    if ($env:USERPROFILE -and (Test-Path $env:USERPROFILE)) {
        $env:HOME = $env:USERPROFILE
        return $env:HOME
    }

    # Fall back to TEMP\home
    $fallback = Join-Path $env:TEMP "home"
    New-Item -ItemType Directory -Force -Path $fallback | Out-Null
    $env:HOME = $fallback
    $env:USERPROFILE = $fallback
    return $env:HOME
}

function Ensure-BinPath {
    param([string]$HomeDir)

    $localBin = Join-Path $HomeDir ".local\bin"
    New-Item -ItemType Directory -Force -Path $localBin | Out-Null

    if ($env:PATH -notlike "*$localBin*") {
        $env:PATH = "$localBin;$env:PATH"
    }

    return $localBin
}

$homeDir = Ensure-Home
$localBin = Ensure-BinPath -HomeDir $homeDir

function Install-Pixi {
    if (Get-Command pixi -ErrorAction SilentlyContinue) {
        return
    }

    # Install pixi into $HOME\.local\bin by setting PIXI_HOME to $HOME\.local.
    $env:PIXI_HOME = (Join-Path $homeDir ".local")
    $env:PIXI_NO_PATH_UPDATE = "1"

    powershell -ExecutionPolicy Bypass -Command "irm -useb https://pixi.sh/install.ps1 | iex"

    $pixiBin = Join-Path $env:PIXI_HOME "bin"
    if (Test-Path $pixiBin) {
        $env:PATH = "$pixiBin;$env:PATH"
    }
}

function Install-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        return
    }

    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"

    $cargoBin = Join-Path $homeDir ".cargo\bin"
    if (Test-Path $cargoBin) {
        $env:PATH = "$cargoBin;$env:PATH"
    }
}

function Install-Git {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        return
    }
    if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
        throw "pixi is required to install git"
    }

    # Install git via pixi global tools. With PIXI_HOME set to $HOME\.local,
    # binaries land in $HOME\.local\bin.
    pixi global install --channel conda-forge git
}

function Install-LfpBuild {
    $spec = $env:LFP_BUILD_SPEC
    if (-not $spec) { $spec = $LfpBuildSpecDefault }

    uv tool install "$spec"
}

function Activate-PixiShellHook {
    if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
        return
    }

    # Best-effort activation. Note: piping this script to iex still runs in the
    # current PowerShell session, so it can update the environment.
    try {
        $hook = pixi shell-hook --shell powershell 2>$null
        if ($hook) {
            $hook | Out-String | Invoke-Expression
        }
    } catch {
        # ignore
    }
}

Install-Pixi
Install-Uv
Install-Git
Install-LfpBuild
Activate-PixiShellHook

Write-Host "lfp-build is installed. Try: lfp-build --help"

