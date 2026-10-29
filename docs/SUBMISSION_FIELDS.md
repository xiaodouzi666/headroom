# Devpost submission fields

Preparation checklist for [FINAL_48H, F7](FINAL_48H.md). This file does not record a submitted entry. The project description remains in [DEVPOST.md](DEVPOST.md).

## Fields

| Devpost field | Value or source |
|---|---|
| Project name | Headroom |
| Tagline | Copy the Tagline from [DEVPOST.md](DEVPOST.md). |
| Project description | Copy the seven sections from Inspiration through What's next in [DEVPOST.md](DEVPOST.md), retaining its current Limitations when preparing the form. |
| Built With | Nebius Token Factory, NVIDIA Nemotron 3 Ultra, NVIDIA Nemotron 3 Super, NVIDIA Nemotron 3 Nano, Tavily, PyTorch, CUDA, Docker, FastAPI, React |
| Track | **Coding and Agentic Engineering** |
| Feedback | Use the first five paragraphs of [FEEDBACK.md](FEEDBACK.md), as requested by F7. |
| Demo URL | [Headroom public demo](https://headroom.tail45186b.ts.net/) |
| Repository URL | [Headroom source](https://github.com/xiaodouzi666/headroom) |
| Video URL | `{{PUBLIC_YOUTUBE_URL}}` — replace after Frank reviews the final video, uploads it as Public and verifies playback. |
| Testing instructions | Use the current instructions below. Replace them with the enabled-feature version only after its listed prerequisites are verified. |

Video production instructions are in [FINAL_48H, §4](FINAL_48H.md). The current [media index](media/final/README.md) records available assets and missing prerequisites. A toolchain smoke clip is not the submission video.

## Testing instructions — current public site

> Open https://headroom.tail45186b.ts.net/ without signing in. Read the homepage, then open Results from the navigation to inspect the nine-scenario evaluation table and its recorded outcomes. Open Verified runs to inspect four historical repairs and two unsuccessful cases, including cited allocation stacks, patches and verification details. Results also includes the measured diagnosis comparison. To start a new GPU repair, choose Run an example, select the s3 evaluation-loop example, and click Start analysis. One live run per IP per hour is allowed; new runs can succeed or fail. Snapshot uploads remain paused. A successful recorded browser run is also available as Browser demonstration in Results. The source, setup instructions and result documentation are available at https://github.com/xiaodouzi666/headroom.

Opening the gallery and Results only reads existing evidence. Clicking Start analysis launches a real GPU and model job.

## Testing instructions — template after feature enablement

**Use only after live validation.** A (the explicit run-pool authorization) and C (the public gallery permission) are complete; the gallery is published and the private judge credential is configured. Complete the actual live checks, then verify the deployed controls, access method and rate limit. Fill the placeholders only from the deployed, tested flow.

> Open https://headroom.tail45186b.ts.net/ without signing in. Open Verified runs to inspect the published historical cases; Verified runs needs no token. To start a new repair, follow `{{VERIFIED_LIVE_ENTRY_STEPS}}` and choose the s3 eval-loop example. The limit is one live run per IP per hour. Inspect the resulting timeline, diagnosis, patch and numerical comparison; a new run may succeed or fail, and its actual outcome is displayed. For the enabled judge-only workflow, use `{{VERIFIED_JUDGE_ACCESS_STEPS}}` with the credential supplied through `{{PRIVATE_CREDENTIAL_HANDOFF}}`. If a live run is unavailable, the recorded cases and Results remain available to inspect.

Before using this version, record the verified example URL or entry steps, a genuine new run ID, the actual judge access method and the current limit in the private handoff. Do not present a prepared historical case as a newly executed run.

## Judge credential handoff

`HEADROOM_JUDGE_TOKEN={{PRIVATE_JUDGE_TOKEN}}` is a documentation placeholder naming the server-side setting. A real credential is privately configured on the server; its value is never stored in this document. This document enables no feature.

Supply any eventual credential through a private channel whose visibility has been checked. Do not commit it here or add it to a public Devpost description, URL, screenshot or video. If the form's Testing instructions are public, include the access instructions and a private handoff contact/method there instead of the secret itself.

## Submission verification

Frank completes the submission after the final video and chosen testing instructions are ready. Record the actual Devpost project URL and Submitted confirmation, and open the demo, repository and Public YouTube links from the submitted entry. No Submitted confirmation is recorded by this file.
