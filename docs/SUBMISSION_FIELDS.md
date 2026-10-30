# Devpost submission fields

Submission record and field reference for [FINAL_48H, F7](FINAL_48H.md). The project description remains in [DEVPOST.md](DEVPOST.md).

## Submitted — 2026-10-30

The main submission session observed Devpost **Submitted** at approximately **03:51 UTC / 11:51 Beijing** on October 30, 2026, and retained its confirmation screenshot. This is an observed approximate time, not an invented server timestamp.

- Entry: [Headroom on Devpost](https://devpost.com/software/headroom-8vfuwj).
- Public video: [Headroom — GPU Memory Diagnosis & Verified Repairs](https://www.youtube.com/watch?v=aaXF60LryWI). The main session verified Public visibility and playback.
- Final uploaded v3 source file: SHA-256 1732b5d992e9946f624f98a02b0d2dede4a0e008be6d437a39797097abbf2e3a; 16,383,275 bytes; 166.92 seconds; 1920×1080, 25 fps, H.264/AAC. These values come from the main session's final-video review receipt; this documentation task did not re-encode or rehash that local file. The SHA identifies the uploaded source file, not YouTube's transcoded streams.

Submission does not change the recorded repair scores, saved-snapshot failures or remaining development work. The [post-submission inventory](../reports/post-submission-inventory-20261030/README.md) separates those obligations from the completed delivery.

## Fields

| Devpost field | Value or source |
|---|---|
| Project name | Headroom |
| Tagline | Copy the Tagline from [DEVPOST.md](DEVPOST.md). |
| Project description | Copy the seven sections from Inspiration through What's next in [DEVPOST.md](DEVPOST.md), retaining its current Limitations when preparing the form. |
| Built With | Nebius Token Factory, NVIDIA Nemotron 3 Ultra, NVIDIA Nemotron 3 Super, NVIDIA Nemotron 3 Nano, Tavily, PyTorch, CUDA, Docker, FastAPI, React |
| Track | **Coding and Agentic Engineering Track** |
| Feedback | Use the first five paragraphs of [FEEDBACK.md](FEEDBACK.md), as requested by F7. |
| Demo URL | [Headroom public demo](https://headroom.tail45186b.ts.net/) |
| Repository URL | [Headroom source](https://github.com/xiaodouzi666/headroom) |
| Video URL | [Public YouTube demonstration](https://www.youtube.com/watch?v=aaXF60LryWI) — Public visibility and playback verified in the submission session. |
| Testing instructions | Use the current instructions below; the credential is delivered privately and is never included in this public file. |

The final video is linked above. Production instructions remain in [FINAL_48H, §4](FINAL_48H.md), and the [media index](media/final/README.md) preserves the original recordings and handoff. Toolchain smoke clips remain separate from the submitted video.

## Version source for judges

The existing `v1.0-submission` tag points to [2969195](https://github.com/xiaodouzi666/headroom/tree/2969195a0924e713a8b10339d61fe21575ded39d), an earlier submission snapshot retained after the clean-checkout work. The current [main branch](https://github.com/xiaodouzi666/headroom/tree/main) contains the subsequent frontend and gallery fixes; the judges' repository link should use main. The existing tag is not moved or replaced. Each measured run keeps its recorded source revision, so this version note does not change historical results.

## Testing instructions — current public site

> Open https://headroom.tail45186b.ts.net/ without signing in. Read the homepage, then open Results from the navigation to inspect the nine-scenario evaluation table and its recorded outcomes. Open Verified runs to inspect four historical repairs and two unsuccessful cases, including cited allocation stacks, patches and verification details. Results also includes the measured diagnosis comparison. To start a new GPU repair, choose Run an example, select the s3 evaluation-loop example, and click Start analysis. Anonymous access allows one attempt per IP per hour. With the privately supplied judge token, examples and scripts have no hourly run-count quota; both routes retain queue, runtime, resource and spending limits. New runs can succeed or fail. On Home, choose Diagnose my snapshot, select a stored server capture and start a new Nebius analysis with the same token. The capture stays on the server and no GPU workload is run. Uploading an external capture is an optional separate route. A successful recorded browser run is also available as Browser demonstration in Results. The source, setup instructions and result documentation are available at https://github.com/xiaodouzi666/headroom.

Opening the gallery and Results only reads existing evidence. Clicking Start analysis launches a real GPU and model job.

## Judge-only script workflow

The implemented interface is **Run → Judge access token → Use an example or Paste a script → Start analysis**. The token is sent in the Authorization header, not a query string or project description. Anonymous examples need no token. Token possession selects the server-controlled judge allowance; it is not identity verification. The token stays only in page memory and is cleared after submission or refresh.

The current application supports preset GPU runs, judge scripts, and saved-capture analysis. The latter uses either an explicitly shared server capture ID or an external upload, with the same judge-token, queue, cost and isolation protections. See [server-capture verification](../reports/server-capture-20261030/). Anonymous access retains one attempt/IP/hour; valid-token access has no hourly run-count quota. Both share one active job, at most two waiting/preparing jobs, a 480-second admission-to-execution deadline and a $0.30 net per-run limit. The effective judging total/day ceiling is $20.92 net under the [gift-only extension](../reports/public-security-20261030/credit-activation.json); the original $6.61 net receipt and historical accounting are preserved. This is finite existing funding, not unlimited spending or a provider billing hard guarantee.

Ordinary script uploads keep a 30-second window. Authenticated external snapshot uploads allow at most 360 seconds inside the same total 480-second task deadline and three-slot limit. Server-stored examples require only a small identifier request; their capture bytes stay on the server. Each target output is bounded to 512 MiB / 4,096 inodes. Public storage uses a 16 GiB application-scope admission threshold and an 8 GiB free-space floor after a 1 GiB reservation; it is not a whole-machine disk quota. Queue, GPU availability and sandbox protections still apply. These are current capabilities, not a promise of unrestricted judging-period access.

The official [Testing requirement](https://nebiusglobalaihackathon.devpost.com/rules) requires free access for the organizers and judges through the end of judging. If access is private, its credentials belong in the testing instructions. At the earlier pre-submission checkpoint, the organizer had not yet clarified the retained limits. The new Manager reply and revised judging dates are recorded in the [official requirements review](../reports/submission-final-review-20261030/requirements-review.md); reasonable abuse protection with capacity sufficient for a full judging pass is conditionally accepted, not an unconditional certification of this installation. The submission session checked the private attachment location and supplied the actual credential only through that channel; do not paste it into publicly visible text. Local Chrome access was restored on 2026-10-29. The actual Additional info page is labelled for judges and organizers; country is explicitly public. No dedicated Testing instructions field is present. Its Upload a File control is the available private attachment location. Frank approved uploading the existing judge credential and testing instructions. The file was saved in that private attachment control and its filename verified after reopening the form. The public Home image was also saved as the thumbnail and image-gallery item. On 2026-10-30, the same credential and revised instructions were saved as judge-testing-instructions-20261030-v3.txt and verified after reopening Additional info; that pre-submission checkpoint still showed DRAFT / 3 of 5 steps. The later Submitted observation above supersedes that state.

## Judge credential handoff

`HEADROOM_JUDGE_TOKEN={{PRIVATE_JUDGE_TOKEN}}` is a documentation placeholder naming the server-side setting. A real credential is privately configured on the server; its value is never stored in this document. This document enables no feature.

Supply any eventual credential through a private channel whose visibility has been checked. Do not commit it here or add it to a public Devpost description, URL, screenshot or video. If the form's Testing instructions are public, include the access instructions and a private handoff contact/method there instead of the secret itself.

## Submission verification

The authorized submission session completed the form and observed Submitted; its public entry and video are recorded above. Final publication does not certify every feature or acceptance target. Keep the private credential out of public story text, URLs, images and source.

## Historical draft prepared — 2026-10-29 (superseded)

[Headroom project preview](https://devpost.com/software/headroom-8vfuwj) at this earlier checkpoint contained the saved name, tagline, current story, technology tags and both public links. The entry then said DRAFT / 3 of 5 steps; no Submitted confirmation existed at that checkpoint. The separate technical feedback fields are saved, with the actual question mapping and proposed subjective ratings in [the draft report](../reports/devpost-draft-20261029/README.md). Personal eligibility and career-value answers are saved. Moderate learning is saved and no IRL event city is selected, matching Frank's explicit answers. The final video was still pending and the final Rules/Terms checkbox had not yet been selected. These historical observations are superseded by the submitted record above. Do not infer submission from the existence of a project page.
