# Devpost submission fields

Preparation checklist for [FINAL_48H, F7](FINAL_48H.md). This file does not record a submitted entry. The project description remains in [DEVPOST.md](DEVPOST.md).

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
| Video URL | `{{PUBLIC_YOUTUBE_URL}}` — replace after Frank reviews the final video, uploads it as Public and verifies playback. |
| Testing instructions | Use the current instructions below and resolve the judge-access requirements before submitting. |

Video production instructions are in [FINAL_48H, §4](FINAL_48H.md). The current [media index](media/final/README.md) records available assets and missing prerequisites. A toolchain smoke clip is not the submission video.

## Testing instructions — current public site

> Open https://headroom.tail45186b.ts.net/ without signing in. Read the homepage, then open Results from the navigation to inspect the nine-scenario evaluation table and its recorded outcomes. Open Verified runs to inspect four historical repairs and two unsuccessful cases, including cited allocation stacks, patches and verification details. Results also includes the measured diagnosis comparison. To start a new GPU repair, choose Run an example, select the s3 evaluation-loop example, and click Start analysis. One live run per IP per hour is allowed; new runs can succeed or fail. Snapshot uploads remain paused. A successful recorded browser run is also available as Browser demonstration in Results. The source, setup instructions and result documentation are available at https://github.com/xiaodouzi666/headroom.

Opening the gallery and Results only reads existing evidence. Clicking Start analysis launches a real GPU and model job.

## Judge-only script workflow

The implemented interface is **Run → Paste a script → Python training script → Judge access token → Start analysis**. The token is sent in the Authorization header, not a query string or project description. The public examples need no token. The current judge-script path still shares the public request and spending limits.

The site's current configuration reports preset runs and judge scripts enabled, snapshot uploads disabled, and a maximum of one run per IP per hour. These are current capabilities, not a promise of unrestricted judging-period access.

The official [Testing requirement](https://nebiusglobalaihackathon.devpost.com/rules) requires free access for the organizers and judges through the end of judging. If access is private, its credentials belong in the testing instructions. The current limits and finite demo allowance have not been confirmed to satisfy that requirement. Before final submission, verify the visibility of the Devpost testing field and provide the actual credential through the field intended for judges; do not paste it into publicly visible text. Local Chrome access was restored on 2026-10-29. The actual Additional info page is labelled for judges and organizers; country is explicitly public. No dedicated Testing instructions field is present. Its Upload a File control is the available private attachment location. Frank approved uploading the existing judge credential and testing instructions. The file was saved in that private attachment control and its filename verified after reopening the form. The public Home image was also saved as the thumbnail and image-gallery item.

## Judge credential handoff

`HEADROOM_JUDGE_TOKEN={{PRIVATE_JUDGE_TOKEN}}` is a documentation placeholder naming the server-side setting. A real credential is privately configured on the server; its value is never stored in this document. This document enables no feature.

Supply any eventual credential through a private channel whose visibility has been checked. Do not commit it here or add it to a public Devpost description, URL, screenshot or video. If the form's Testing instructions are public, include the access instructions and a private handoff contact/method there instead of the secret itself.

## Submission verification

Frank completes the submission after the final video and chosen testing instructions are ready. Record the actual Devpost project URL and Submitted confirmation, and open the demo, repository and Public YouTube links from the submitted entry. No Submitted confirmation is recorded by this file.

## Actual draft prepared — 2026-10-29

[Headroom project preview](https://devpost.com/software/headroom-8vfuwj) now contains the saved name, tagline, current story, technology tags and both public links. The hackathon entry still says DRAFT / 3 of 5 steps; no Submitted confirmation exists. The separate technical feedback fields are saved, with the actual question mapping and proposed subjective ratings in [the draft report](../reports/devpost-draft-20261029/README.md). Personal eligibility and career-value answers are saved. Moderate learning is saved and no IRL event city is selected, matching Frank's explicit answers. The final video remains pending. The final Rules/Terms checkbox has not been selected. Do not infer submission from the existence of a project page.
