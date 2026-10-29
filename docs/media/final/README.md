# Final demo media preparation

Status: **Parts 1–6 delivered for local editing** on 2026-10-29. Part 6 supplies four updated-font page and completed-result clips, totaling **120.08 seconds**, with the header status light removed. It shows existing real results; it is not a new live execution. Part 4 remains the original recording of the actual successful s3 submission and execution. Part 5 retains the unsuccessful F5 environment-recovery test. The final edited, narrated submission video and its public URL are still pending.

## Current recording handoff

The current Home still image and Part 6 clips include the 2026-10-29 readability update. Use Part 6 for the latest Home, Verified runs, Results and completed s3 detail shots. Parts 1–5 retain their original typography and measured results; keep Part 4 for evidence of the actual live submission and execution. None of these raw clips is the final edited video.

Frank's latest direction: Codex records each implemented user-facing feature as
separate real-operation clips; Opus edits, narrates and captions the final
submission demo on Frank's local computer. Server-side Claude Code login is
not required for this division of work.

Raw clips go in `docs/media/final/clips/` with a manifest of their source URL,
capture time, dimensions, duration and any real run ID. The raw clips are source
footage, not the finished competition video. The capture script must operate
the actual interface, and a failed live outcome stays visible in the footage.
A new live run must be recorded when executed; showing a historical run cannot
stand in for it.

Capture coverage: Home, historical Verified runs, an actual new repair with
timeline and result details, cited allocation stacks, patch and verification,
Sources and downloads, snapshot upload/diagnosis, Watch-triggered execution,
and Results. Preserve the original 1920×1080 and ≤170-second final edit target.
Only measured outcomes may be used in narration. Frank supplies the final
public video URL after local editing and review.

## Assets and links

| Item | Location | Current state |
|---|---|---|
| Public Headroom website | https://headroom.tail45186b.ts.net/ | Existing public demo URL. |
| Public repository | https://github.com/xiaodouzi666/headroom | Existing source repository. |
| Home screenshot | [home.png](home.png) | Updated from the verified readability release on 2026-10-29; see [capture evidence](../../../reports/frontend-readability-20261029/README.md). |
| Genuine CUDA OOM traceback | [oom-traceback.txt](oom-traceback.txt) | Complete, byte-identical copy of a preserved s1 capture. |
| Historical gallery data | [verified-runs.json](../../../public-evidence/verified-runs.json) | Published: four historical successes and two failures; see the publication receipt. |
| Intended gallery page | https://headroom.tail45186b.ts.net/verified | Publicly verified in Chrome, including an expandable allocation-stack citation. |
| First s3 live attempt | 12150a5b0cf445378edb784e6cc6c091 | Failed before Ultra; original recording retained in Part 2. |
| New successful s3 live run | d9926ee7bb624e7fb22540bbc4c92cdc | One actual submission completed with target met and cleanup confirmed; Part 4 contains the full recording. This is separate from R7. |
| Recording environment evidence | [preparation.json](../../../reports/final48h-media-20261029/preparation.json) | Official image pulled and isolated Python container checked; package-import availability is recorded separately. |
| Final narration numbers | [RESULTS.md](../../RESULTS.md) | Read the final current summary before writing narration; do not reuse unverified placeholder numbers from the storyboard. |

## OOM provenance

- Scenario: `s1_batch_too_big`.
- Historical repair run: `810e0803757740dfaaa65fd4ecd2adf9`.
- Baseline capture: `88c750285bea486db86ce30d197a1ebf`; recorded status: `oom`.
- Source: `runs/evaluation/live/20261027T022818939585Z-151818b1/jobs/810e0803757740dfaaa65fd4ecd2adf9/lab/88c750285bea486db86ce30d197a1ebf/artifacts/traceback.txt`.
- Source and destination SHA256: `06a76fa597e670e9345f05490d9da9ae2e8b7247e289414b0c7534e6b6e57d7c`.
- Size: 3,867 bytes. No lines were removed, changed, or invented.
- The original `stderr.log` is empty: the runner captured the exception in `artifacts/traceback.txt`. Present this as a historical captured traceback, not a new terminal execution or a nonempty stderr recording.
- The copied text was checked for common credential patterns and reviewed. It contains container paths, not private host home paths. The source run and workload were not changed.

## Recording environment

The official [Playwright Python Docker guide](https://playwright.dev/python/docs/docker) specifies `mcr.microsoft.com/playwright/python:v1.64.1-noble`. This fixed version was selected instead of an unversioned tag. The pull completed successfully. Docker reported and image inspection confirmed immutable digest `sha256:330d401ae23c905896a0c26c66c36fc971b621519e7b11b435a8328d7bf6e031`. The container check used that digest, not the mutable tag. Exact commands and output are in the preparation receipt.

The image supplies browsers and system dependencies; its documentation says the Python Playwright package must be installed separately. The isolated check ran Python 3.12.3; `import playwright` was unavailable, as expected for the base image. Install the matching `playwright==1.64.1` package inside the future recording environment. No package was installed on the host or in this check. A version check and import check are environment tests only: they do not prove that a browser recording has been produced or that the complete video toolchain is ready.

No host repository or workload mount, GPU access, model call, judge token, browser profile, production service change, or paid API is part of this preparation.

## Isolated toolchain smoke — 2026-10-29

The derived test image now has matching Playwright Python **1.64.1**, Chromium
**156.0.8078.4**, ffmpeg/ffprobe **6.1.1-3ubuntu5**, and edge-tts **7.3.1**.
It is separate from the project environment; pyproject.toml and uv.lock were not
changed. Tested image ID: `sha256:983d2a4e654e9d55ca0f73d7fbf25306fa94d7de34878e741957c4c1d7eac8ff`
(tag: `headroom-final48-video-tools:toolchain-smoke`).

An ephemeral Docker browser recorded an inline **TOOLCHAIN SMOKE** page with
explicit 1920×1080 viewport and recording dimensions. Browser networking was
disabled. edge-tts successfully generated a neutral test sentence with
`en-US-AndrewNeural`, rate `-5%`; only this test sentence was sent online.
ffmpeg burned its SRT subtitles and combined the sample into a **6.312-second,
1920×1080 H.264/AAC** clip. This is a synthetic tool check, not project footage.

Receipt, versions and retained initial permission failures:
[toolchain report](../../../reports/final48h-media-toolchain-20261029/README.md)
and [receipt.json](../../../reports/final48h-media-toolchain-20261029/receipt.json).
The scripts and smoke outputs stay in `.cache/final48-video-tools/`; they are
not final-video assets. No host browser profile, credential, project source,
GPU or model API was used.

This completes only the tested toolchain path. The final edit remains Opus's work on Frank's computer. Codex records the raw
feature clips under the current handoff above.

## Narration checks before recording

The original storyboard is a production outline, not evidence for numbers that
have not been measured. Read the current RESULTS summary and each chosen run
before recording narration.

- Segment 1 may animate the preserved OOM text, but identify its historical
  capture in the asset index. It is not a newly executed terminal session.
- Segment 3 must show the actual newly triggered live run and its resulting
  measurements. Do not pre-write its patch, percentage, update count or numerical
  result from an older s3 success. Preserve the new run ID even if repair fails.
- For historical examples, s3 has twenty identical compared losses with matched
  pairing; s4 compares the first five reference losses; s2 is tolerance-based;
  s8 has incomplete workload pairing. Candidate update count is not the count of
  compared baseline/reference samples.
- There are currently five distinct historical target-success scenarios across
  separate campaigns. The best single campaign has three; the latest fixed-nine
  campaign, R7, has one. The later individual s3 demo does not change R7's 1/9.
  These are different measurements and must not be merged into a new success rate.
- Diagnosis-only ablation is measured: primary-category scores are 6/9, 2/9 and 6/9; complete valid diagnosis scores are 4/9, 2/9 and 4/9. These are not repair scores.
- The separate strict/bf16 s2 tests and HF Trainer attempt did not meet their requirements. A statically accepted HF configuration edit is not a verified repair; see the final R7 report.
- The evidence requests with 268,920 and 500,029 provider-counted input tokens
  establish observed request handling, not a measured one-million-token maximum.
- Campaign invoice totals are incomplete. Omit the storyboard's fixed
  two-dollar-per-campaign claim and GPU-time claim unless new evidence supports
  the exact recorded statement.

## Remaining before video handoff

1. Completed: C authorized and the reviewed gallery is public, with four repair cards and two failures. Evidence: [publication receipt](../../../reports/verified-publication-20261029/README.md).
2. A new s3 live demonstration completed successfully and is indexed in Part 4; the first failure remains in Part 2. The live entry is operator-controlled and budget-limited. Recording one successful run does not establish that submissions are currently enabled or authorize further runs. Judge credentials remain a separate private handoff.
3. Codex records actual feature clips and supplies their manifest; Opus then performs local editing, narration, subtitles and timing. The isolated toolchain smoke does not validate the final video.
4. Verify the final video is 1920×1080, has audio, lasts at most 170 seconds, and uses the current factual results. Record its path, duration, and real live-run ID here.
5. Keep generated MP4, WebM, and MP3 files out of Git. The main task owns the requested ignore rules.

The gallery and actual live-run recording are available as editing material. Full F6 sign-off still requires the main task to confirm all five FINAL_48H prerequisites, including the judge entry and private credential handoff; the final video remains Opus's work.

### Homepage refresh — 2026-10-29

`home.png` now shows the actual published read-only homepage from physical Chrome after the ab8b4f3 product build. The gallery and live analysis are visibly unavailable pending the separate confirmations. This image is a website screenshot, not evidence of a new live run, and does not complete F6. Source and browser checks: reports/final48h-product-view-20261029/deployment.json and reports/final48h-product-browser-20261029/layout.json.

## First raw clip delivery — 2026-10-29

Six unedited feature clips are stored under the ignored directory
`clips/20261028T224943Z/`. The MP4 copies are all 1920×1080 at 25 fps and have
no audio, so Opus can edit and narrate them locally. Their combined raw duration
is 284.20 seconds; this is source footage, not the final ≤170-second edit.

| Clip | Duration | Evidence |
| --- | ---: | --- |
| Home overview | 35.60 s | Actual read-only page at capture time |
| Six historical cards | 56.04 s | Four successes and two failures |
| Historical s3 details | 56.80 s | Cited stack, patch, verification and real download |
| Historical s8 details | 60.60 s | Cited stack, patch, verification and real download |
| Historical s2 Sources | 35.96 s | Actual retained Tavily sources |
| Historical result table | 39.20 s | Earlier campaign; replace with the final updated Results footage |

The folder includes per-action timestamps, screenshots, the original WebM files
and ffprobe results. This capture made only GET/HEAD requests, with no model or
GPU invocation. The later new s3 run is now in Part 4; historical clips are
not its proof.

Transfer bundle: `clips/headroom-demo-clips-part1-20261029.zip`,
11,683,840 bytes, SHA256
`f0d6b83e59df01666c9eba83e54a21aac7ebf5d5078337ab1f02f165a0ca3b68`.
The bundle contains six MP4s, safe metadata, editing notes and public patch
downloads. It excludes browser owner sessions and judge credentials.

## Part 2 — real failed live attempt

clips/headroom-part2-real-failed-attempt-20261029.zip preserves run 12150a5b0cf445378edb784e6cc6c091: one browser submission, a completed GPU baseline, one Nano request, then a stop before Ultra diagnosis. This is a **failed attempt**, not a new repair success. The archive includes the original WebM, an 85.40-second 1920×1080 MP4, the unchanged recorder receipt and an explanation of the recovered database completion flags. No audio has been added.

Archive SHA256: 34e0ce0a6ff52b7bc4a2987d730125d9f80b7a3eae12ee0287b4bc11fcf4bc1d. The same bytes were delivered to Frank's local Downloads/Headroom-demo-materials/ alongside Part 1. Cookies and private session files are excluded.

The failure clip is available for honest failure coverage or debugging; do not pair it with narration claiming that this run produced the historical s3 patch. The published diagnosis comparison now has measured results in reports/ablation-20261028/; the earlier Part 1 Results clip shows the historical evaluation only.

## Part 3 — measured diagnosis comparison

The actual updated Results page was recorded after the obsolete comparison copy was fixed.
Source folder: `clips/part3-results-20261028T232201Z/`.
The MP4 is 37.44 seconds, 1920×1080 at 25 fps, without audio. Capture made only
GET/HEAD requests: no submission, model call or GPU run. The table distinguishes
primary-category scores (6/9, 2/9, 6/9) from complete valid diagnosis scores
(4/9, 2/9, 4/9), and retains the single-pass measurement limitations.

Bundle: `clips/headroom-demo-clips-part3-results-20261029.zip`, 6,500,838 bytes.
SHA256: `6fcb10d1f2fa6a84fc43845f9c85d5194285d6f54cc60bc8f1024bfc41691560`.
Verified identical bytes are in Frank's local `Downloads/Headroom-demo-materials/`.
Part 3 preserves the earlier measured diagnosis comparison. Its repair campaign
table predates R7. Use Part 5 for the current Results page, including R7 and the
same diagnosis comparison; keep this earlier footage as history.

## Part 4 — actual live feature recordings

Delivered archive: `clips/headroom-demo-clips-part4-live-features-20261029.zip`
(57,524,069 bytes; 48 files across six clips). SHA256:
`eb5cec406e8a1be3685cccff2e9319fa6ad360f16c0c8119eacbeaff62f1c857`.

Verified identical bytes are on Frank's Mac at:
`/Users/liujunjun/Downloads/Headroom-demo-materials/headroom-demo-clips-part4-live-features-20261029.zip`.
Unpack this archive alongside Parts 1–3 for local Opus editing. Its
`part4-live-features-20261029/README.md` and `manifest.json` describe the footage
and hashes. Each clip includes 1920×1080, 25 fps silent MP4/WebM, screenshots and
a capture receipt. Owner sessions, cookies, judge tokens, .env files and private
allocation bindings are excluded; the text/metadata secret scan found no leaks.

| Package folder | Duration | What the footage actually proves |
| --- | ---: | --- |
| `01-snapshot-s2-cli` | 22.12 s | Real `needs_human / diagnosis_unavailable` output; the command had already returned when filmed. |
| `02-snapshot-nanogpt-cli` | 22.20 s | Real `failed / diagnosis_unavailable` output; also filmed after the command returned. |
| `03-snapshot-web` | 44.32 s | One real upload, run `8fcd4570a96145ceb0244c0190d95635`; `needs_human`, no diagnosis or patch, no hardware verification. |
| `04-clean-s3-initial-failure` | 20.88 s | Original F5 attempt attached while running; it stopped at `runtime_not_ready` before provider/GPU calls. This is not a successful clean-install test. |
| `05-watch-s1` | 270.64 s | Attached while running; actual CUDA OOM capture and final failed result. About 252 s of empty-output waiting precede the controller's output. |
| `06-s3-live-after-budget-fix` | 117.60 s | One real new s3 submission, run `d9926ee7bb624e7fb22540bbc4c92cdc`; completed, target met, worker finished and cleanup verified. |

The new s3 recording shows the actual UI reporting **2.436 GB → 0.648 GB**
and **73.379%** peak reduction, plus the model timeline, cited allocation stack,
expanded patch, verification and Sources. The displayed unavailable cost is
preserved. Its owner-scoped run URL is
`https://headroom.tail45186b.ts.net/runs/d9926ee7bb624e7fb22540bbc4c92cdc`;
the delivered video can be edited without obtaining its owner session.
This single demo is separate from the frozen R7 campaign: **R7 remains 1/9,
below the unchanged 6/9 threshold**. Do not add the demo to R7's numerator.

Both snapshot CLI clips visibly say “Existing output display; command had
already returned”. They are truthful views of original output, not live command
execution. Watch and the original F5 clip followed real controller output while
running. No CLI was launched by the output viewer; final scrolling only navigates
retained text. None of the snapshot, Watch or original F5 failure clips may be
narrated as a verified repair. Any later recovery must be indexed separately.

The first Snapshot Web recorder was blocked locally before forwarding a POST;
its original failure remains at `clips/snapshot-web/20261028T235032Z-execute/`.
Part 4 uses the subsequent, single actual upload. The first failed s3 run remains
in Part 2. No failed artifact or retry-protection marker was replaced.

## Part 5 — final Results, current Home and F5 recovery

Delivered archive: `clips/headroom-demo-clips-part5-final-pages-and-f5-20261029.zip`,
20,634,115 bytes, 21 files, three clips. SHA256:
`56a6cbd380320d3b7b3c4ec7c04f6ece4f46a95baf36483f520961e1f898a0ec`.
Identical verified bytes are on Frank's Mac at
`/Users/liujunjun/Downloads/Headroom-demo-materials/headroom-demo-clips-part5-final-pages-and-f5-20261029.zip`.
Its manifest binds the media, screenshots and capture receipts; the metadata
secret scan found no leaks. No cookie, owner session, judge token, .env or
private allocation binding is packaged.

| Package folder | Duration | Recorded state |
| --- | ---: | --- |
| `01-final-results` | 56.16 s | Current R7: nine rows and explicit **1 of 9** banner, raw 7/9 versus valid-correct 5/9, diagnosis comparison, then Watch failure and the separate browser s3 success. |
| `02-current-home` | 12.48 s | Gallery and prepared-example entry enabled at capture time; snapshot submission disabled. The example form's Start analysis button was checked as enabled and never clicked. |
| `03-clean-s3-recovery` | 59.00 s | Actual F5 recovery output, run `bd5bc2173ef1452aaabebcd5fd76bfb3`; `needs_human` and `target_met=false`. It is not successful clean-environment repair acceptance. |

All three are silent 1920×1080, 25 fps MP4/WebM. The two page clips allowed only
same-origin GET/HEAD and made no submission or model/GPU call. The CLI viewer
had networking disabled and did not launch the tested command. It attached
while the recovery controller was active, displayed already-arrived bytes
immediately, then followed later real output through the terminal result and
final scroll. The viewer's file-arrival timing is not original terminal emission
timing. The original zero-call F5 failure remains in Part 4.

Use Part 5's Home and Results in the final edit instead of the older page states.
The successful live s3 operation itself remains Part 4 / `06-s3-live-after-budget-fix`.
The newly recorded Results page shows that success as a separate demonstration;
**R7 remains 1/9 and below the unchanged 6/9 threshold**. The F5 recovery
allowed the actual test to run, but did not produce a verified repair.

Sources retained on azuki:
- `clips/results-final/20261029T002737Z/`
- `clips/home-current/20261029T002825Z/`
- `clips/cli-output/20261029T002444Z-clean-s3-env-recovery/`

The earlier Results take and locally failed setup takes remain in their original
directories. The packaged final takes are complete. This recording verifies
desktop footage only; it does not claim a mobile acceptance result. Raw source
footage still requires Opus's local edit, narration and captions.

## Latest gallery refresh — 2026-10-29

Delivered separately as `clips/headroom-gallery-refresh-20261029.zip`:
16,170,066 bytes, 14 files, SHA256
`febc63add2414f0f55b1b0b7e6d5e39c021101fcf6aaf22b43d0d92cfa03f0f6`.
Identical verified bytes are on Frank's Mac at
`/Users/liujunjun/Downloads/Headroom-demo-materials/headroom-gallery-refresh-20261029.zip`.
This **42.84-second**, silent 1920×1080 / 25 fps MP4/WebM shows the refreshed
public gallery. It includes the capture receipt, hash manifest and nine screenshots.

- The s3 Browser demo card now uses `d9926ee7bb624e7fb22540bbc4c92cdc`.
  The actual UI shows **73.38%** peak reduction, **20 compared loss samples**
  and **20 completed optimizer updates**.
- The retained-graph s4 card now uses R7 run `e8213706570e478f9845e49e24c2b54b`.
  It shows **89.77%** peak reduction, **five compared backward-loss scalars**
  against an original-workload offload reference, and **20 completed updates**.
  Five comparisons must not be described as twenty.
- Both cards show actual expanded, bound initial-diagnosis stacks and selected
  diffs. The recorder checked the two patch response hashes against the published
  catalog. The gallery remains four recorded repairs and two failures.

Source take: `clips/gallery-refresh/20261029T004321Z/`. All eight requests were
successful GETs. No new job, model request, GPU workload or DOM-content change
was introduced. The package metadata secret scan found no leaks.

Use this addition for current gallery shots. **Part 1's gallery is historical
footage of the earlier card sources** and remains unchanged, as do all old clips
and archives. The actual live s3 execution is still Part 4; browsing its published
card is not another execution. R7 remains 1/9. This is raw local-editing material,
not a newly generated final submission video.

### Local Opus editing brief

Make a **1920×1080 final video of at most 170 seconds (2:50), safely below
three minutes**, with audible English narration and matching captions. Use the
existing clips; editing does not require another model/GPU run or server login.
A compact sequence is:

1. 0:00–0:12: a real OOM excerpt. Label historical traceback displays or use
   Watch's recorded OOM; do not imply that the display itself re-executes training.
2. 0:12–0:28: Part 5 Home and the capture → diagnose → patch → verify workflow.
3. 0:28–1:40: Part 4's new s3 run. Cut or clearly accelerate waiting, then keep
   the actual peak, stack, patch and verification readable at normal speed.
   Preserve run ID `d9926ee7bb624e7fb22540bbc4c92cdc`.
4. 1:40–2:00: historical gallery and the snapshot/Watch limitations. These
   failed attempts demonstrate honest failure reporting, not repair coverage.
5. 2:00–2:35: Part 5's actual current Results page: the fixed-nine 1/9 banner,
   valid correct first causes 5/9, raw category matches 7/9, and the separate
   diagnosis comparison. Keep the independent browser s3 demonstration separate
   from R7; use [R7's report](../../../reports/r7-20261029/README.md) for narration.
6. 2:35–2:50: repository, Apache 2.0 and the real Quickstart.

Narration must distinguish the ablation's category scores **6/9, 2/9, 6/9**
from complete-valid scores **4/9, 2/9, 4/9**, and both from repair success.
Do not claim successful precision tiers, universal snapshot diagnosis, a
one-million-token measurement, a fixed campaign cost, or an overall 6/9 pass.
Mention NVIDIA Nemotron 3 Ultra, Nebius Token Factory and Tavily accurately.
Read [RESULTS](../../RESULTS.md) before recording final narration.

Before delivery, check duration, 1920×1080 dimensions, audio and subtitle timing.
The final MP4, duration, public video URL and Devpost submission state are still
to be recorded by the main task after Frank reviews the local edit.


## Part 6 — readable page and completed-result refresh

Delivered archive: `clips/headroom-demo-clips-part6-readability-20261029.zip`,
**47,549,749 bytes**, 53 files. SHA256:
`67d8f3d74d9811be7d59990515c244cb65e06c9c36eeb56d56fb0dfa9befcca5`.
The archive and its JSON receipt are in Frank's local
`Downloads/Headroom-demo-materials/`; the local ZIP hash was independently
checked against the server receipt. See the [public delivery receipt](../../../reports/final48h-readability-clips-20261029/delivery.json).

The four recommended clips total **120.08 seconds**, each at 1920×1080,
25 fps and without audio, with both MP4 and original WebM available.
They show the actual published interface from readability revision `e6cf7a2`:
larger body text, readable labels and no header breathing light. No page text,
result, animation or synthetic data was inserted during capture.

| Folder | Duration | Recorded content |
| --- | ---: | --- |
| `01-home` | 19.76 s | Current Home and product workflow. |
| `02-verified` | 26.60 s | Historical gallery, including successful and unsolved cards. |
| `03-results` | 24.20 s | R7 fixed-nine result, diagnosis comparison and the separate existing s3 demo. |
| `04-existing-s3-details-retry` | 49.52 s | Existing completed s3 timeline, chart, diagnosis, allocation stack, diff, verification and Sources. |

These are **existing real result displays, not a new live execution**. The s3
run is `d9926ee7bb624e7fb22540bbc4c92cdc`; Part 4's
`06-s3-live-after-budget-fix` remains the genuine recording of its submission
and execution. Use Part 6 as readable replacement page/detail shots and retain
Part 4's actual live-start footage. The earlier editing brief's Home/Results
shot references may now use Part 6; its evidence and narration limits still
apply. R7 remains 1/9 against the unchanged 6/9 gate.

The extra `04-existing-s3-details` folder preserves the first, 46.64-second
partial attempt and its error receipt. A recording selector matched a hidden
stack block; one authorized retry selected visible content and completed.
The partial attempt is not included in the 120.08-second recommended total
and does not establish complete diff/verification coverage. The first three
clips and all earlier packages remain unchanged.

The package includes its own README, capture/action receipts, source URLs,
run ID, screenshots, media properties and per-file SHA256 manifest.
Only GET/HEAD reached Headroom: no submission, model call, GPU run, upload or
service restart occurred. Exact matching against existing private credential
values found no leaks, and the final package-folder gitleaks scan passed.
No owner session, cookie, judge token, environment file or private allocation
binding is included. Editing the delivered media needs no server credentials.

The local Chinese editing note is `README-最新剪辑交接-Part6.txt` in the same
Downloads folder. Opus still needs to produce and validate the final narrated,
captioned video at 1920×1080 and at most 170 seconds; Frank then supplies its
public URL for the final submission.
