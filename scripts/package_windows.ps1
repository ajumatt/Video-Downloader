<#
.SYNOPSIS
    Builds a portable Windows bundle for Video Downloader: a pinned
    python-build-standalone interpreter with yt-dlp/sv-ttk pre-installed,
    plus the app source and a thin launcher, zipped for distribution.
.PARAMETER Version
    Version string used in the output zip filename (e.g. "v0.1.0").
    Defaults to "dev" for local test runs.
.PARAMETER OutputDir
    Directory the final zip is written to. Defaults to "dist".
#>
param(
    [string]$Version = "dev",
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

# --- Pinned python-build-standalone release --------------------------------
$PbsReleaseTag = "20260728"
$PythonVersion = "3.12.13"
$PbsAssetName = "cpython-$PythonVersion+$PbsReleaseTag-x86_64-pc-windows-msvc-install_only.tar.gz"
$PbsUrl = "https://github.com/astral-sh/python-build-standalone/releases/download/$PbsReleaseTag/$PbsAssetName"

# --- Paths -------------------------------------------------------------------
$RepoRoot = Split-Path -Parent $PSScriptRoot
$StageDir = Join-Path $RepoRoot "build"
$BundleName = "VideoDownloader-$Version-windows"
$BundleDir = Join-Path $StageDir $BundleName
$RuntimeDir = Join-Path $BundleDir "runtime"
$DownloadPath = Join-Path $StageDir $PbsAssetName

Write-Host "== Video Downloader Windows packaging =="
Write-Host "Version: $Version"
Write-Host "Python:  $PythonVersion (python-build-standalone $PbsReleaseTag)"

# --- Clean staging area -------------------------------------------------------
if (Test-Path $StageDir) {
    Remove-Item -Recurse -Force $StageDir
}
New-Item -ItemType Directory -Path $BundleDir | Out-Null

# --- Download the interpreter --------------------------------------------------
Write-Host "Downloading $PbsAssetName ..."
try {
    Invoke-WebRequest -Uri $PbsUrl -OutFile $DownloadPath -UseBasicParsing
} catch {
    Write-Error "Failed to download python-build-standalone from $PbsUrl : $_"
    exit 1
}
if (-not (Test-Path $DownloadPath) -or (Get-Item $DownloadPath).Length -eq 0) {
    Write-Error "Downloaded file is missing or empty: $DownloadPath"
    exit 1
}

# --- Extract ---------------------------------------------------------------------
Write-Host "Extracting interpreter..."
$ExtractDir = Join-Path $StageDir "pbs_extract"
New-Item -ItemType Directory -Path $ExtractDir | Out-Null
tar -xzf $DownloadPath -C $ExtractDir
if ($LASTEXITCODE -ne 0) {
    Write-Error "tar extraction failed with exit code $LASTEXITCODE"
    exit 1
}
$ExtractedPython = Join-Path $ExtractDir "python"
if (-not (Test-Path (Join-Path $ExtractedPython "python.exe"))) {
    Write-Error "Expected python.exe not found after extraction at $ExtractedPython"
    exit 1
}
Move-Item $ExtractedPython $RuntimeDir
Remove-Item $DownloadPath -Force
Remove-Item -Recurse -Force $ExtractDir

$PythonExe = Join-Path $RuntimeDir "python.exe"

# --- Install dependencies into the bundled interpreter ----------------------------
Write-Host "Installing dependencies (yt-dlp, sv-ttk) into the bundle..."
& $PythonExe -m pip install --no-warn-script-location -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed with exit code $LASTEXITCODE"
    exit 1
}

# --- Verify the bundle can import its dependencies ---------------------------------
& $PythonExe -c "import yt_dlp, sv_ttk, tkinter"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Post-install import check failed - the bundle is broken"
    exit 1
}
Write-Host "Dependency check OK."

# --- Copy app source -----------------------------------------------------------------
Write-Host "Copying application source..."
Copy-Item (Join-Path $RepoRoot "video_downloader.py") $BundleDir
Copy-Item (Join-Path $RepoRoot "README.md") $BundleDir
Copy-Item (Join-Path $RepoRoot "videodownloader") $BundleDir -Recurse
Get-ChildItem -Path $BundleDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# --- Write the bundle launcher --------------------------------------------------------
$LauncherContent = @"
@echo off
cd /d "%~dp0"
runtime\python.exe video_downloader.py
if not %errorlevel%==0 pause
"@
Set-Content -Path (Join-Path $BundleDir "Launch Video Downloader.bat") -Value $LauncherContent -Encoding ASCII

# --- Zip it up ---------------------------------------------------------------------------
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}
$ZipPath = Join-Path $OutputDir "$BundleName.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Write-Host "Zipping to $ZipPath ..."
Compress-Archive -Path $BundleDir -DestinationPath $ZipPath

# --- Clean up staging, report result ------------------------------------------------------
Remove-Item -Recurse -Force $StageDir
$ZipSize = (Get-Item $ZipPath).Length / 1MB
Write-Host "Done. $ZipPath ($([math]::Round($ZipSize, 1)) MB)"
