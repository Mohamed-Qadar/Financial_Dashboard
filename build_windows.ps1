<#
.SYNOPSIS
  Builds the Windows desktop application, the installer and the portable ZIP.

.DESCRIPTION
  Steps: tests -> icon -> PyInstaller (one-folder) -> portable ZIP -> Inno Setup installer -> SHA256SUMS.
  Works in Windows PowerShell 5.1 and PowerShell 7. Used locally and by the GitHub Actions workflow.

.PARAMETER Python
  Python interpreter to use (default: the project build venv, then "python" on PATH).
.PARAMETER SkipTests
  Do not run the test-suite first.
.PARAMETER SkipInstaller
  Build only the executable folder and the portable ZIP.

.EXAMPLE
  .\build_windows.ps1
  .\build_windows.ps1 -SkipTests
#>
[CmdletBinding()]
param(
    [string]$Python = "",
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

# "Continue" on purpose: Windows PowerShell 5.1 turns every stderr line of a
# native program (PyInstaller logs to stderr) into a terminating error under
# "Stop". Every native call below is followed by an explicit exit-code check.
$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Run-Native {
    # Runs a native executable, streams its output as plain text, returns the exit code.
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) { Write-Host $_.Exception.Message } else { Write-Host $_ }
    }
    return [int]$LASTEXITCODE
}

# --- interpreter --------------------------------------------------------------
if (-not $Python) {
    if (Test-Path ".venv-build\Scripts\python.exe") { $Python = ".venv-build\Scripts\python.exe" }
    else { $Python = "python" }
}
$Python = (Resolve-Path $Python -ErrorAction SilentlyContinue).Path
if (-not $Python) { $Python = "python" }
Step "Using Python: $Python"
& $Python --version
$version = (& $Python -c "import config; print(config.APP_VERSION)").Trim()
Write-Host "Application version: $version"

# --- tests --------------------------------------------------------------------
if (-not $SkipTests) {
    Step "Running test-suite"
    if ((Run-Native $Python @("-m", "pytest", "-q")) -ne 0) { throw "Tests failed - build aborted." }
}

# --- icon ---------------------------------------------------------------------
Step "Generating application icon"
if ((Run-Native $Python @("tools\make_icon.py")) -ne 0) { throw "Icon generation failed." }

# --- PyInstaller --------------------------------------------------------------
Step "Building executable with PyInstaller"
if (Test-Path "dist\DailyMoneyTransferManager") { Remove-Item "dist\DailyMoneyTransferManager" -Recurse -Force }
if ((Run-Native $Python @("-m", "PyInstaller", "--noconfirm", "--clean", "desktop.spec")) -ne 0) { throw "PyInstaller failed." }
$exe = "dist\DailyMoneyTransferManager\DailyMoneyTransferManager.exe"
if (-not (Test-Path $exe)) { throw "Expected output not found: $exe" }
$size = [math]::Round((Get-ChildItem "dist\DailyMoneyTransferManager" -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "Executable folder size: $size MB"

# --- portable ZIP -------------------------------------------------------------
Step "Creating portable ZIP"
$portableDir = "dist\DailyMoneyTransferManager-Portable"
$portableZip = "dist\DailyMoneyTransferManager-Portable.zip"
if (Test-Path $portableDir) { Remove-Item $portableDir -Recurse -Force }
if (Test-Path $portableZip) { Remove-Item $portableZip -Force }
Copy-Item "dist\DailyMoneyTransferManager" $portableDir -Recurse
@(
    "Daily Money Transfer Manager 2026 - portable edition $version",
    "",
    "This marker file keeps all data (database, backups, exports, logs) in the",
    "'data' folder next to DailyMoneyTransferManager.exe instead of %LOCALAPPDATA%.",
    "Delete this file to switch back to the per-user data folder."
) | Set-Content -Path "$portableDir\portable.txt" -Encoding ASCII
Compress-Archive -Path "$portableDir\*" -DestinationPath $portableZip -CompressionLevel Optimal
Remove-Item $portableDir -Recurse -Force
Write-Host "Portable ZIP: $portableZip"

# --- Inno Setup ---------------------------------------------------------------
if (-not $SkipInstaller) {
    Step "Building installer with Inno Setup"
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $iscc = $null
    foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { $iscc = $c; break } }
    if (-not $iscc) {
        $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($cmd) { $iscc = $cmd.Source }
    }
    if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) not found. Install it from https://jrsoftware.org/isinfo.php or run with -SkipInstaller." }
    New-Item -ItemType Directory -Force "dist\installer" | Out-Null
    if ((Run-Native $iscc @("/DMyAppVersion=$version", "/Qp", "installer.iss")) -ne 0) { throw "Inno Setup failed." }
    Write-Host "Installer: dist\installer\DailyMoneyTransferManager-Setup.exe"
}

# --- checksums ----------------------------------------------------------------
Step "Writing SHA256SUMS.txt"
$artifacts = @($portableZip)
if (Test-Path "dist\installer\DailyMoneyTransferManager-Setup.exe") { $artifacts += "dist\installer\DailyMoneyTransferManager-Setup.exe" }
$lines = foreach ($f in $artifacts) {
    $h = (Get-FileHash -Algorithm SHA256 -Path $f).Hash.ToLower()
    "$h  $(Split-Path $f -Leaf)"
}
# LF line endings, no BOM: the conventional sha256sum format ("sha256sum -c SHA256SUMS.txt" works).
[IO.File]::WriteAllText((Join-Path $PSScriptRoot "dist\SHA256SUMS.txt"), (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
Get-Content "dist\SHA256SUMS.txt"

Step "Done"
Get-ChildItem $artifacts | Select-Object Name, @{n="MB";e={[math]::Round($_.Length/1MB,1)}} | Format-Table -AutoSize
