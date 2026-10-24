# Headroom development checkpoint — 2026-10-24

Server: azuki:/home/xiaodouzi/workspace/headroom
Repository: https://github.com/xiaodouzi666/headroom
Status: implementation checkpoint; the original project and competition submission are not fully accepted.

## Delivered implementation

- Isolated allocator capture and evidence; Ultra diagnosis, bounded Super patching, verification, six-round keep/revert search, Pareto export and Nano stack annotations.
- SQLite events/reports, per-attempt reservations, per-run/daily/total budget guards, unknown-charge handling and high-precision monetary comparisons.
- Real Tavily search/extraction with version-aware sources and persistent 24-hour cache; pinned nanoGPT/HF/ViT/T5 fixtures; Docker Watch for argv, Python scripts/modules/inline commands and interpreter options.
- FastAPI/SSE, one-worker queue, per-IP admissions, safe downloads and four-page responsive React application. Five explicitly labeled real GPU baseline replays and eight real UI screenshots are included.
- Explicit policy planning/matrices and main/ablation evaluation tooling, with per-policy statistics and unknown-value denominators. Default/strict are currently equivalent; that original-plan ambiguity remains visible.
- Deployment/health templates, README/architecture/results/feedback, English Devpost draft, video storyboard and judge-readiness review. No public deployment or formal submission has been performed.

## Verified evidence

| Check | Result | Evidence |
|---|---|---|
| Full backend offline/CPU regression | 718 passed,107.57s | reports/full-tests-20261024T030133Z.json and .log |
| Frontend | 27 passed; strict typecheck and production build pass | reports/web-verification-20261024.json |
| Mobile Lighthouse | Home90/90/90; real baseline Run89/98/89 | reports/lighthouse-20261024.json |
| Real GPU baselines | 12/12 expected outcomes;5OOM,7completed20; full capture and cleanup | reports/evaluation-baselines-20261024.json |
| Report numeric consistency | 7 reports,87 GB/GiB/% values pass | scripts/check_report_numbers.py against existing runs/jobs |
| Tavily component | 4 live methods,3 credits; repeat cache0calls/credits | reports/research-component-20261024T022414Z.json |
| Tavily account total | 6/1000 used,994 remaining; pay-as-you-go off | reports/tavily-account-after-research-20261024.json |

Source hashes and combined validation receipt: reports/final-validation-20261024.json. Ruff and whitespace checks pass. Historical failed tests, invalid Lighthouse paths, old performance failures and raw runs remain preserved. Accessibility scored96; the unexplained Home Speed Index around33s is retained as a measurement caveat, not hidden by the aggregate Performance score.

## What still prevents original acceptance

1. **Nebius access and approved spending:** NEBIUS_API_KEY and the reviewed live runtime profile remain absent. No authenticated Nebius inference, real generated GPU repair, long-context/cost validation, final main benchmark or ablation result is claimed. Configuring a key is distinct from confirming credits and authorizing spending.
2. **Unchanged plan gates:** s2 optimizer-state share39.8715% is below the original40%; the s2 baseline already fits22GB, so the prescribed two-round gate remains unresolved. Thresholds and fixtures were not changed to force success. Numerical/parameter/precision gates remain intact.
3. **T2.7 environment:** independent user/network namespaces are rejected with EPERM. See reports/t2.7-isolation-preflight-20261024.json. Docker component checks do not certify the separate subprocess comparison; no unsafe host fallback was enabled.
4. **Watch boundary:** arbitrary argv can be observed in Docker, but only a reliably replayable script automatically enters repair. Unmapped module/inline/native entrypoints return needs_human after confirmed CUDA OOM; missing capture stays unknown. Normal exit codes are preserved.
5. **Owner/external deliverables:** design package/approval, domain/Cloudflare, real public access/restart/alert validation, model-backed repair screenshots, owner video recording/publication and formal Devpost submission. The600s watchdog covers worker execution; repository preparation and queue wait are outside that bound, so whole-request ten-minute acceptance is not claimed.

No v0.9-eval/v1.0 release tag, public tunnel, notification automation or final submission was created.

## Can self-funding start Nebius work earlier?

Yes, if the pending review is only the Builders/hackathon promotional grant and the Token Factory account itself can complete normal onboarding. Official billing supports card-backed accounts and manual top-ups available immediately. Payment is not documented as bypassing an account-level review.

A top-up is not a hard spending cap: negative balances can trigger automatic card charges at a threshold or monthly settlement. No top-up or paid inference was authorized or performed by the feasibility question. See docs/ACCOUNT_SETUP.md and docs/RUNTIME.md for the prepared hidden-input key importer, actual-access checks and explicit spending boundary.

Official references: https://docs.tokenfactory.nebius.com/other-capabilities/billing-new and https://docs.tokenfactory.nebius.com/quickstart .

## Handoff

All code, dependencies, runs and media remain on azuki. Interim per-phase summaries/handoffs0–5 are saved in reports/; each explicitly preserves incomplete acceptance gates. Only this small plain-text report may be copied to the Mac:

```sh
scp -P 40022 xiaodouzi@azuki.ubj.ink:/home/xiaodouzi/workspace/headroom/reports/handoff-development-20261024.md ~/Downloads/
```

The original docs/PLAN.md is unchanged: e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56.
