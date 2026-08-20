# GitHub Actions Packaging Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows-only portable-Python bundle for Video Downloader via a PowerShell script, and publish it as a GitHub Release asset through a new GitHub Actions workflow triggered by pushing a version tag.

**Architecture:** One new build script (`scripts/package_windows.ps1`) downloads a pinned `python-build-standalone` interpreter, installs the app's dependencies into it, copies in the app source, writes a thin launcher, and zips the result. One new workflow (`.github/workflows/build-release.yml`) runs that script on `windows-latest` whenever a `v*.*.*` tag is pushed, then publishes the zip as a GitHub Release asset.

**Tech Stack:** PowerShell 7 (`pwsh`, available by default on GitHub's `windows-latest` runners), `python-build-standalone` (portable CPython distribution), GitHub Actions (`actions/checkout@v7`, `actions/upload-artifact@v7`, `softprops/action-gh-release@v3`).

**Spec:** `docs/superpowers/specs/2026-08-19-github-actions-packaging-build-design.md`

## Global Constraints

- Windows only for this pass — no macOS/Linux build jobs.
- Workflow triggers only on `push: tags: 'v*.*.*'` — no `workflow_dispatch`, no push-to-branch trigger.
- No changes to `run_video_downloader.bat` or `README.md` — the existing distribution path stays untouched.
- No `.gitignore` changes needed — the build script's staging directory is named `build/` and its output directory is named `dist/`, both already covered by existing `.gitignore` entries.
- The `python-build-standalone` release is pinned (tag `20260728`, CPython `3.12.13`, asset `cpython-3.12.13+20260728-x86_64-pc-windows-msvc-install_only.tar.gz`) — verified reachable and correct against the live GitHub API and by a full local dry run (download → extract → `pip install -r requirements.txt` → import check → launch the real app) before this plan was written. Do not substitute "latest" or a different version without re-verifying the same way.
- A real end-to-end trigger of the GitHub Actions workflow requires pushing an actual git tag, which creates a public GitHub Release. That is **out of scope for this plan's tasks** and requires the user's explicit go-ahead as a separate step after implementation — do not push a tag as part of executing this plan.

---

### Task 1: Windows packaging script

**Files:**
- Create: `scripts/package_windows.ps1`

**Interfaces:**
- Consumes: `requirements.txt`, `video_downloader.py`, `videodownloader/`, `README.md` at the repo root (all already exist).
- Produces: `dist/VideoDownloader-<version>-windows.zip`, invoked as `./scripts/package_windows.ps1 -Version "<version>"` (Task 2's workflow depends on this exact invocation and this exact output path pattern).

- [ ] **Step 1: Write the script**

Create `scripts/package_windows.ps1` with this exact content:

```powershell
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
```

- [ ] **Step 2: Run it locally and verify the build succeeds**

From the repo root:
```powershell
.\scripts\package_windows.ps1 -Version "test"
```

Expected: the script prints progress through each stage (downloading, extracting, installing dependencies, dependency check OK, copying, zipping) and ends with a line like:
```
Done. dist\VideoDownloader-test-windows.zip (44 MB)
```
with exit code 0. If any step fails, the script exits 1 with a specific `Write-Error` message identifying which stage failed — fix that stage before proceeding.

- [ ] **Step 3: Verify the zip's contents and that the bundle actually runs**

```powershell
Expand-Archive -Path "dist\VideoDownloader-test-windows.zip" -DestinationPath "dist\_verify"
Get-ChildItem "dist\_verify\VideoDownloader-test-windows"
```
Expected output includes exactly these top-level entries: `runtime`, `videodownloader`, `Launch Video Downloader.bat`, `README.md`, `video_downloader.py`. No `requirements.txt`, no dev docs (`CLAUDE.md`, `PRD.md`, etc.) should be present.

Then launch it exactly as an end user would:
```powershell
Start-Process -FilePath "dist\_verify\VideoDownloader-test-windows\Launch Video Downloader.bat" -WorkingDirectory "dist\_verify\VideoDownloader-test-windows"
Start-Sleep -Seconds 4
Get-Process -Name python -ErrorAction SilentlyContinue | Select-Object Id, Path, MainWindowTitle
```
Expected: a `python.exe` process appears whose `Path` points inside `dist\_verify\VideoDownloader-test-windows\runtime\python.exe` (confirming it's running the *bundled* interpreter, not system Python) and whose `MainWindowTitle` is `Video Downloader`. Close it afterward:
```powershell
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
```

- [ ] **Step 4: Clean up local test output**

```powershell
Remove-Item -Recurse -Force "dist"
```
`dist/` is git-ignored regardless, but there's no reason to leave scratch output sitting in the working tree.

- [ ] **Step 5: Commit**

```bash
git add scripts/package_windows.ps1
git commit -m "Add Windows packaging script for portable-Python bundle

Downloads a pinned python-build-standalone interpreter, installs
yt-dlp/sv-ttk into it, copies in the app source, and zips a
self-contained bundle with a thin launcher. Verified locally: the
script runs end-to-end, the resulting zip has the expected contents,
and the packaged app launches correctly via its bundled interpreter."
```

---

### Task 2: GitHub Actions release workflow

**Files:**
- Create: `.github/workflows/build-release.yml`

**Interfaces:**
- Consumes: `scripts/package_windows.ps1` from Task 1, invoked exactly as `./scripts/package_windows.ps1 -Version "${{ github.ref_name }}"`; consumes the fact that it produces `dist/*.zip`.
- Produces: a GitHub Release (for the pushed tag) with the built zip attached as an asset.

- [ ] **Step 1: Write the workflow file**

Create `.github/workflows/build-release.yml` with this exact content:

```yaml
name: Build and Release Windows Package

on:
  push:
    tags:
      - 'v*.*.*'

permissions:
  contents: write

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v7

      - name: Build portable Windows bundle
        shell: pwsh
        run: ./scripts/package_windows.ps1 -Version "${{ github.ref_name }}"

      - name: Upload build artifact
        uses: actions/upload-artifact@v7
        with:
          name: windows-bundle
          path: dist/*.zip

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v3
        with:
          files: dist/*.zip
          generate_release_notes: true
          fail_on_unmatched_files: true
```

- [ ] **Step 2: Validate the YAML syntax locally**

```bash
python -c "import yaml, sys; yaml.safe_load(open('.github/workflows/build-release.yml')); print('YAML OK')"
```
If `yaml` isn't installed, run `pip install pyyaml` first (a lightweight, standard package — safe to install). Expected output: `YAML OK`. If this raises a `yaml.YAMLError`, fix the indentation/syntax it points to before proceeding.

- [ ] **Step 3: Sanity-check the referenced script path exists and matches Task 1's invocation**

```bash
test -f scripts/package_windows.ps1 && echo "script exists"
grep -n "param(" scripts/package_windows.ps1
```
Expected: `script exists`, followed by the script's `param(` block showing `[string]$Version` as the first parameter — confirming the workflow's `-Version "${{ github.ref_name }}"` call matches the script's actual parameter name.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/build-release.yml
git commit -m "Add GitHub Actions workflow to build and publish the Windows package

Triggers on pushing a version tag (v*.*.*), runs the Task 1 packaging
script on windows-latest, and publishes the resulting zip as a
GitHub Release asset with auto-generated release notes."
```

---

### Task 3: Hand off for real end-to-end verification

This task has no code changes — it's the explicit stop-and-ask gate called out in the spec's verification plan and in Global Constraints above.

- [ ] **Step 1: Report completion and ask before triggering a real build**

Tell the user both new files are committed and locally verified (script runs end-to-end and produces a working, launchable bundle; workflow YAML is syntactically valid and references the right script/parameter). Then explicitly ask whether they want to push a version tag now (e.g. `git tag v0.1.0 && git push origin v0.1.0`) to trigger the real workflow and produce the first actual GitHub Release — do not push a tag without that explicit go-ahead, since it's a visible, public, semi-permanent action (Global Constraints).

## Self-Review Notes

- **Spec coverage:** Build script (Task 1) ✓, workflow triggered on tag push (Task 2) ✓, Windows-only scope (no other OS jobs added) ✓, no changes to `run_video_downloader.bat`/`README.md` (never touched by either task) ✓, no `.gitignore` changes needed (`build/`/`dist/` already covered — verified by reading the existing `.gitignore`) ✓, real-tag-push verification kept as a separate explicit approval step rather than folded into implementation (Task 3) ✓.
- **Placeholder scan:** No TBD/TODO markers; every step has literal, already-executed-and-verified commands and file content rather than descriptions of what to do.
- **Type/interface consistency:** The workflow's `-Version "${{ github.ref_name }}"` argument matches the script's `[string]$Version` parameter name exactly; the workflow's `path: dist/*.zip` / `files: dist/*.zip` match the script's actual output location (`$OutputDir` defaults to `dist`, confirmed by the script's own `Write-Host "Done. $ZipPath..."` line in Task 1 Step 2's expected output).
