# Build the launcher, install it into a game folder, and report the result.
#
# build_exe.ps1 produces an exe; this is everything after that. Installing by
# hand is four steps and the fourth is finding the self-check report inside a
# folder named after an install hash, which is easy to get wrong and tedious
# to repeat.
#
#   .\deploy.ps1                        # uses MO_RANDOMIZER_GAME_ROOT
#   .\deploy.ps1 -GameRoot "D:\...\Command & Conquer Red Alert II MO"
#   .\deploy.ps1 -SkipBuild             # reinstall the staged exe
#   .\deploy.ps1 -NoInstall             # build and self-check, leave the game alone

param(
    [string]$GameRoot = $env:MO_RANDOMIZER_GAME_ROOT,
    [string]$BuildScript,
    [switch]$SkipBuild,
    [switch]$NoInstall
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
# build_exe.ps1 runs a bare `python -c "from randomizer..."` preflight, so the
# repository has to be the working directory whoever invoked this was in.
Set-Location -LiteralPath $repo

if (-not $NoInstall -and -not $GameRoot) {
    Write-Output 'Game folder unknown. Pass -GameRoot, or set MO_RANDOMIZER_GAME_ROOT.'
    exit 2
}

# build_exe.ps1 pins the Python and Tcl/Tk the release is built against. A
# maintainer whose toolchain differs keeps build_exe.local.ps1 beside it,
# gitignored, and that is preferred when present so a working machine needs no
# flag and a clean checkout still builds the released configuration.
if (-not $BuildScript) {
    $local = Join-Path $repo 'build_exe.local.ps1'
    $BuildScript = if (Test-Path $local) { $local }
                   else { Join-Path $repo 'build_exe.ps1' }
}
Write-Output "building with $(Split-Path -Leaf $BuildScript)"

# Not dist\ itself: build_exe.ps1 builds into dist\ and then copies the result
# to -Output, so staging there asks it to copy a file over itself.
$stagingDir = Join-Path $repo 'dist\deploy'
$staging = Join-Path $stagingDir 'MentalOmegaRandomizer.exe'
$log = Join-Path $stagingDir 'build.log'

if (-not $SkipBuild) {
    New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
    if (Test-Path $staging) { Remove-Item -LiteralPath $staging -Force }
    # PyInstaller's own --clean deletes build/ mid-run and fails outright if a
    # scanner still has base_library.zip open from the previous build. Clear it
    # first, and give the file system a moment when something is still holding
    # on, rather than surfacing a WinError 32 as a build failure.
    $buildDir = Join-Path $repo 'build'
    foreach ($attempt in 1..5) {
        if (-not (Test-Path $buildDir)) { break }
        try {
            Remove-Item -LiteralPath $buildDir -Recurse -Force -ErrorAction Stop
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    # Windows PowerShell wraps a native command's stderr in ErrorRecords, which
    # trips ErrorActionPreference='Stop' on ordinary PyInstaller chatter. Let
    # this one call report failure through its exit code instead.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & powershell -NoProfile -ExecutionPolicy Bypass `
        -File $BuildScript -Output $staging > $log 2>&1
    $buildCode = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($buildCode -ne 0 -or -not (Test-Path $staging)) {
        Write-Output 'BUILD FAILED - last lines:'
        Get-Content $log -Tail 20
        exit 1
    }
    Write-Output (Get-Content $log -Tail 1)
}

if (-not $NoInstall) {
    $installed = Join-Path $GameRoot 'MentalOmegaRandomizer.exe'
    # Windows refuses to delete a running exe but allows renaming one, so an
    # open launcher keeps working and picks this up when it next starts.
    if (Test-Path $installed) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        Rename-Item -LiteralPath $installed -NewName "MentalOmegaRandomizer.exe.old-$stamp"
        Write-Output "previous build kept as MentalOmegaRandomizer.exe.old-$stamp"
    }
    Copy-Item -LiteralPath $staging -Destination $installed -Force
    $target = $installed
} else {
    $target = $staging
}

& $target --self-check | Out-Null
$code = $LASTEXITCODE

# The report lands under a per-installation folder, so find it rather than
# assume which one.
$report = Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'MentalOmegaRandomizer') `
    -Recurse -Filter 'self_check.json' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $report) {
    Write-Output "self-check exit=$code, no report found"
    exit 1
}

$d = Get-Content $report.FullName -Raw | ConvertFrom-Json
$failed = @($d.PSObject.Properties |
    Where-Object { $_.Name -like '*_valid' -and $_.Value -eq $false } |
    ForEach-Object { $_.Name })
Write-Output "passed=$($d.passed)  version=$($d.app_version)  exit=$code"
if ($d.traceback) {
    Write-Output ($d.traceback -split "`n" | Select-Object -Last 1)
}
if ($failed.Count) {
    Write-Output "FAILED: $($failed -join ', ')"
}
Write-Output $d.game_files_summary
if (-not $d.passed) { exit 1 }
