# GitHub Actions Packaging Build — Design

## Context

`video_downloader.py` (a Tkinter app wrapping yt-dlp) is currently distributed as "clone the repo, double-click `run_video_downloader.bat`," which installs Python system-wide (needs admin) before launching. An earlier multi-agent production-readiness review recommended, as a follow-up (not bundled into that review's bug-fix pass), shipping a **portable-Python bundle** instead of a frozen executable — because freezing (PyInstaller/Nuitka/etc.) would require decoupling yt-dlp into a subprocess-invoked binary just to keep the app's self-update mechanism working, which is a real rewrite. A portable bundle needs zero application code changes: it's still a real `pip`/`site-packages` environment, so `pip install --upgrade yt-dlp` and the app's existing restart-after-update flow both keep working unmodified.

This spec covers building that portable bundle via a new GitHub Actions pipeline. Scope, confirmed with the user:
- **Windows only** for this first pass (README already calls Windows the primary/most-tested platform; macOS/Linux keep their current "pip install yourself" path).
- **Triggered by pushing a version tag** (`v*.*.*`) — not on every push, not manual-only.
- **CI pipeline only** — this pass does not touch `run_video_downloader.bat` or `README.md`. Those stay exactly as they are; switching users over to the new bundle is a separate future decision.

## Architecture

Two new files, nothing else in the repo changes:
- `scripts/package_windows.ps1` — the build script. Runs locally (for testing) or in CI. Produces `dist/VideoDownloader-<version>-windows.zip`.
- `.github/workflows/build-release.yml` — triggers the script on a tag push and publishes the result as a GitHub Release asset.

`dist/` is already covered by the existing `.gitignore` (`dist/` is listed from the earlier scaffold), so build output is never committed.

## Components

### `scripts/package_windows.ps1`

Parameters: `-Version` (string; in CI this is the pushed tag name via `github.ref_name`, e.g. `v0.1.0`; defaults to `dev` for local test runs) and `-OutputDir` (defaults to `dist`).

Steps:
1. Resolve the repo root relative to the script's own location (so it works regardless of the caller's working directory).
2. Download a **pinned** `python-build-standalone` release (Windows x86_64, `install_only` build) — pinned to a specific release tag and Python version, not "latest," so builds stay reproducible. The exact current release tag/asset filename gets verified against the real GitHub releases API at implementation time rather than guessed from memory.
3. Extract the archive into a clean staging directory as `runtime/`.
4. Run `runtime\python.exe -m pip install -r requirements.txt` — installs yt-dlp and sv-ttk into that bundled interpreter's own site-packages, so the zip is self-contained (offline-capable except for the app's own ffmpeg self-download, which is unchanged).
5. Verify the install: run `runtime\python.exe -c "import yt_dlp, sv_ttk"` inside the bundle and fail the build loudly if it errors.
6. Copy `video_downloader.py`, `videodownloader/` (excluding `__pycache__`), and `README.md` into the staging directory. Nothing else from the repo ships: `requirements.txt` is unnecessary since dependencies are already installed into `runtime/`, and the dev-facing docs (`CLAUDE.md`, `PRD.md`, `SECURITY.md`, `plan.md`, `.env.example`) aren't relevant to an end user of the packaged app.
7. Write a new thin launcher, `Launch Video Downloader.bat`, into the staging directory — *only inside the packaged zip*, distinct from the repo's existing `run_video_downloader.bat`:
   ```bat
   @echo off
   cd /d "%~dp0"
   runtime\python.exe video_downloader.py
   if not %errorlevel%==0 pause
   ```
   No Python-detection/install logic needed — the interpreter is already bundled.
8. Zip the staging directory into `<OutputDir>\VideoDownloader-<version>-windows.zip` via `Compress-Archive`.
9. Print the final zip path and size.

Error handling: every step that can fail (download, extraction, pip install, the post-install import check) checks its result explicitly and calls `exit 1` with a clear message on failure, so a broken environment fails the build loudly instead of silently producing a bad zip. The temp download archive is cleaned up after extraction.

### `.github/workflows/build-release.yml`

```yaml
name: Build and Release Windows Package

on:
  push:
    tags:
      - 'v*.*.*'

permissions:
  contents: write   # needed to create a Release

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build portable Windows bundle
        shell: pwsh
        run: ./scripts/package_windows.ps1 -Version "${{ github.ref_name }}"
      - name: Upload build artifact
        uses: actions/upload-artifact@v4
        with:
          name: windows-bundle
          path: dist/*.zip
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/*.zip
          generate_release_notes: true
```

Action version pins (`actions/checkout@v4`, `actions/upload-artifact@v4`, `softprops/action-gh-release@v2`) get double-checked as still-current/valid at implementation time.

## Data flow

Tag push (`vX.Y.Z`) → Actions triggers on `windows-latest` → checkout → `package_windows.ps1` runs (download python-build-standalone → extract → `pip install` deps into it → copy app source in → write the bundle-only launcher → zip) → zip uploaded as both a workflow artifact and a GitHub Release asset attached to that tag, with auto-generated release notes from the commits since the last tag.

## Error handling

- The build script fails loudly (non-zero exit) on any step failure, so the CI job fails visibly.
- If the build step fails, the artifact-upload and release-creation steps don't run — no broken Release ever gets published.
- No retry logic — this is a low-frequency, human-triggered build (a deliberate tag push), not a hot path. A failure just means fix and push a new tag (or delete/re-push the same tag).

## Testing / verification plan

1. **Local dry run on this machine** (Windows): run `scripts/package_windows.ps1 -Version test` directly, producing `dist/VideoDownloader-test-windows.zip`.
2. Extract that zip to a scratch folder and run `Launch Video Downloader.bat`. Confirm via `Get-Process`/path inspection that the running `python.exe` is the bundled one (not system Python), confirm yt-dlp/sv-ttk import successfully, and screenshot the launched app for visual confirmation — the same verification style used throughout this project's earlier work.
3. Delete the local test zip/extracted folder afterward (it's git-ignored regardless, but no need to leave scratch output lying around).
4. **The GitHub Actions workflow itself is only verified end-to-end by an actual tag push**, which creates a real public GitHub Release. That happens as its own explicit approval step after implementation — not bundled into "did the code get written."

## Explicitly out of scope for this spec

- macOS/Linux bundles (future work, per the original packaging analysis's Phase 1/Phase 2 split).
- A `workflow_dispatch` manual trigger (user chose tag-push-only).
- Any change to `run_video_downloader.bat`, `README.md`, or the current "clone + double-click" distribution path.
- Code signing / SmartScreen mitigation.
- Any change to the app's own self-update mechanism — it continues to work unmodified inside the bundle since the bundle is a real `pip`/`site-packages` environment, not a frozen executable.
