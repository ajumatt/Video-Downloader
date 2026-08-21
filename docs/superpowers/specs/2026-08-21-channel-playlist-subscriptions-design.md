# Channel/Playlist Subscriptions — Design

## Context

The app currently only downloads what's explicitly queued: paste a URL, it downloads once. A competitive-landscape review of other yt-dlp GUI wrappers (Tartube, MeTube, Parabolic, etc.) flagged channel/playlist **subscriptions with scheduled re-checks** — "keep a folder in sync with a channel" — as the single most common feature this app lacks.

This spec covers adding that: subscribing to a channel or playlist URL so the app periodically checks for new uploads and automatically queues them for download, using that subscription's own saved settings.

Scope, confirmed with the user during design:
- **Checks only happen while the app is open** — on launch, then on a configurable timer. No OS-level scheduling (Windows Task Scheduler, a headless entry point, etc.); if the app isn't running, subscriptions simply aren't checked until it's opened again.
- **New videos auto-queue for download** — no manual approval step per video.
- **Each subscription has its own settings snapshot** (folder, quality, subtitles, cookies, SponsorBlock, extra yt-dlp args), not a single global default.
- **The initial-catalog behavior is a per-subscription choice** made at subscribe time: only new videos going forward, the full existing back catalog, or everything from a specific date onward.
- **The check interval is a single global setting**, not per-subscription (confirmed with the user as an explicit simplifying assumption).

## Architecture

New module `videodownloader/subscriptions.py`, mirroring the existing `history.py` pattern (plain-JSON load/save, defensive on I/O errors, no new dependency). A new dotfile, `.video_downloader_subscriptions.json`, alongside the existing `.video_downloader_config.json` / `.video_downloader_history.csv` in the user's home folder (`paths.py` gains `SUBSCRIPTIONS_PATH`).

New GUI module `videodownloader/gui/subscriptions_mixin.py` (mixed into `MainWindow` alongside the existing `QueueMixin`, `HistoryMixin`-equivalent, etc.), covering:
- The Subscribe dialog (opened from a new button on the main Download card)
- The Subscriptions management window (opened from a new toolbar button)
- The periodic check-cycle scheduling and worker logic

**Rejected alternative:** using yt-dlp's own `download_archive` file plus a direct `ydl.download([channel_url])` call was considered and rejected. It would bypass the existing per-item queue entirely — subscription downloads wouldn't appear as rows in the Queue list, wouldn't get the existing per-item cancel/retry-on-403 logic, and would fight with the app's "one video at a time via the queue" model. Instead, subscriptions only ever discover new video URLs; every actual download still flows through the existing `_make_queue_item` / `_download_one_item` pipeline unchanged, so subscription-driven downloads are indistinguishable from manually queued ones (same Queue list, same progress bar, same retries, same extra-flags/SponsorBlock support).

## Components

### Data model (`subscriptions.py`)

```python
{
    "id": "<uuid>",
    "url": "...",
    "name": "...",                      # channel/playlist title, fetched at subscribe time; user-editable
    "enabled": True,
    "folder": "...", "quality": "...", "template": "...",
    "subtitles": False, "subtitle_langs": "en",
    "cookies_browser": None,
    "sponsorblock_categories": [],
    "extra_ytdlp_args": "",             # same settings shape as a queue item, see queue_mixin._current_form_settings
    "seen_video_ids": ["...", "..."],
    "last_checked": "2026-08-21T12:00:00" ,  # or null if never checked
    "last_error": None,                  # set/cleared each cycle; surfaced in the Subscriptions window
    "created_at": "2026-08-21T12:00:00",
}
```

`load_subscriptions()` / `save_subscriptions()` — same shape as `load_config`/`save_config`: read/write the whole list, swallow `OSError`/`ValueError` and fall back to `[]` on a corrupt/missing file (never crash app startup over a bad subscriptions file).

### Subscribe flow

A new **"Subscribe..."** button sits next to "Add to Queue" / "Add multiple..." on the main Download card. Clicking it:
1. Validates a URL is present (reusing the existing pattern from `_enqueue_current`).
2. Opens a small dialog (own `Toplevel`, built independently — matches the existing convention of `_open_batch_add_window` / `_open_format_picker_window`, no shared form-builder).
3. In the background (daemon thread, same pattern as `_fetch_formats_worker`), runs a **flat** extraction (`extract_flat=True`) of the URL to fetch the channel/playlist title and confirm it actually has multiple entries.
   - If extraction returns no `entries` (a single video, not a channel/playlist), the dialog shows a blocking error: "This URL doesn't look like a channel or playlist — subscriptions need a URL with multiple videos (e.g. a channel's /videos page)." Mirrors the existing format-picker's "can't list formats for a playlist URL" mismatch handling, inverted.
   - If the URL is already subscribed (exact match against stored `url` values), shows "Already subscribed to this URL" and blocks.
4. On success, shows the fetched name (editable) and three radio options for initial catalog handling:
   - **Only new videos going forward** (default) — seed `seen_video_ids` with every currently-listed video ID; download nothing immediately.
   - **Full back catalog** — seed `seen_video_ids` as empty; every currently-listed video gets queued immediately via the normal batch-enqueue path.
   - **From a specific date** (date picker appears) — walk the flat-extracted entry list **newest-first**, doing one full (non-flat) `extract_info` per video only until a video older than the cutoff date is hit, then stop (channels are assumed chronological, so this bounds the number of full-metadata fetches to roughly "videos since the cutoff," not the whole channel history). Videos at/after the cutoff get queued immediately; everything older is added to `seen_video_ids` without downloading.
5. On "Subscribe," the current main-form settings (`_current_form_settings()`) are captured into the new subscription record alongside the URL/name/catalog choice, saved via `save_subscriptions()`, and (for the backlog/date modes) the qualifying videos are enqueued through the existing `_enqueue_batch`-style path.

### Subscriptions management window

Opened via a new toolbar button next to "History." A `ttk.Treeview` listing all subscriptions (Name, videos downloaded, last checked, status — showing `last_error` when set), plus:
- **Remove selected** — deletes the subscription record entirely (its `seen_video_ids` history goes with it; re-subscribing later starts fresh).
- **Enable / Disable** toggle — pausing skips it in future check cycles without losing `seen_video_ids`.
- **Check now** — runs one check cycle for the selected subscription immediately, bypassing the timer.
- **Edit settings...** — a small dialog with the same settings fields, editing the stored snapshot directly (not tied to the live main-form state).

The check-interval control (a dropdown, e.g. 15/30/60/120 minutes) lives in this window's header, the same way "Concurrent downloads" sits in the Queue card's header — not on the main Download card, and persisted via the existing `config.py`.

### Check cycle

Scheduled via `self.root.after(interval_ms, self._run_subscription_check_cycle)`, re-scheduling itself at the end of each run (new pattern for this app — the existing yt-dlp/app-update checks are one-shot-at-launch-plus-manual-button, not a recurring timer). First run fires a few seconds after the window opens (matching the existing update-check's non-blocking-at-startup behavior), not instantly on `_build_ui`.

For each **enabled** subscription, a background daemon thread:
1. Runs a flat extraction of the subscription's URL.
2. Diffs returned video IDs against `seen_video_ids` (pure set difference — no new yt-dlp calls needed beyond the one flat extraction, since flat mode already returns IDs without per-video metadata).
3. For each new ID, builds a queue item via the existing `_make_queue_item` (using that subscription's stored settings) and appends it to `self.download_queue`, then calls `_maybe_start_queue_workers()` — identical to how a manual batch-add enqueues.
4. Updates `seen_video_ids` (adds the new IDs), `last_checked`, and `last_error` (cleared on success), then persists via `save_subscriptions()`.
5. Logs a summary line to the Activity Log, e.g. "3 new videos found: {name}" (only when count > 0, to avoid log noise on every empty check).

Checks for different subscriptions run concurrently — they're metadata reads, not downloads, so they don't compete with the "Concurrent downloads" setting, which continues to govern actual download concurrency once items land in the queue.

## Data flow

```
Timer fires (or "Check now") ─▶ for each enabled subscription (parallel threads):
  flat-extract(url) ─▶ diff IDs vs seen_video_ids ─▶ new IDs found?
     no  ─▶ update last_checked, save, done
     yes ─▶ build queue items (subscription's settings) ─▶ append to download_queue
            ─▶ _maybe_start_queue_workers() ─▶ existing per-item download pipeline
            ─▶ update seen_video_ids + last_checked, save, log summary
```

## Error handling

- **Extraction failure** (deleted channel, network down, transient block): caught, logged to the Activity Log and stored in `last_error`, surfaced in the Subscriptions window. No auto-removal — a subscription is only removed by explicit user action. Retried on the next scheduled cycle.
- **Corrupt/missing subscriptions file:** `load_subscriptions()` returns `[]`, same defensive pattern as `load_config`/`read_history` — never blocks app startup.
- **Shutdown mid-check:** check threads are daemon threads, same as the existing download workers — they die with the process, no special cleanup needed.
- **Known, accepted limitation:** many subscriptions checking concurrently could theoretically trigger site-side rate limiting. Not addressed in this pass — a realistic ceiling for this personal-use tool is tens of subscriptions, not hundreds. Called out here rather than silently ignored.

## Testing / verification plan

- **Unit tests** (pytest, extending the `tests/` directory introduced for extra-flags passthrough) against pure logic, with no real network calls:
  - ID-diffing: given a fake list of entries and a `seen_video_ids` set, confirm only the unseen ones are returned.
  - Newest-first date-cutoff walk: given a fake ordered entry list and a cutoff date, confirm it stops at the first entry older than the cutoff and returns the correct qualifying subset.
  - `load_subscriptions`/`save_subscriptions` round-trip, and defensive fallback on a corrupt file.
- **Manual/screenshot verification** for the Tk wiring (dialogs, toolbar button, Subscriptions window, timer-driven enqueue showing up in the Queue list) — the same approach used for the extra-flags feature, given no reliable native-Windows GUI click-automation tool is available in this environment. Any gap in click-through coverage will be stated explicitly rather than implied as covered.

## Explicitly out of scope for this pass

- True background/OS-level scheduling (checking while the app isn't running).
- Per-subscription check intervals (one global interval for all subscriptions).
- A shared settings-form-builder refactor between the main Download card and the Subscribe/Edit-settings dialogs (each dialog builds its own widgets, matching existing convention).
- Rate-limiting/throttling of concurrent subscription checks.
- Editing `seen_video_ids` directly (e.g. "mark as unseen to re-download") — removing and re-subscribing is the only reset path for now.
