# F5 clean-clone setup preflight

Status: clean-clone setup, CLI checks and the rebuilt Lab image contract passed. Integrated commit 96994dd was fetched into the same clean checkout; CLI and environment-example checks passed without another install or image rebuild. **This is a free setup preflight, not evidence that the F5 live repair passed.**

Started: 2026-10-29 01:59:48 Asia/Shanghai. The whole task is limited to 90 minutes.

## Reproduction scope

- Public clone URL: https://github.com/xiaodouzi666/headroom.git
- Independent checkout: `/tmp/headroom-f5-20261029-krupo1aa/repo`.
- Initial public commit: `b2a923133f22b2a03a412780c213c76290f1f96c`.
- New README checked at: `b14f8b30526ecbf41795cc736e1e4038abaa3724`.
- Applicable parent-directory AGENTS files and tracked clone AGENTS files were checked; none were present.
- No main working tree, virtual environment, credentials, private runtime profile, or private runs/ data were copied. The new virtual environment is inside the independent checkout.
- Public package caches were reused. This is not a cache-free download benchmark.

## Completed checks

1. `uv sync --locked --python 3.12` completed with Python 3.12.3 and installed 104 packages in the independent environment. The successful cache-assisted attempt took 35.395 seconds.
2. `headroom version`, the main help, and `fix`, `diagnose`, and `watch` help all returned exit code 0. These help commands did not execute a workload.
3. The new Quickstart's s3 source exists. The dependency lock and pyproject are unchanged between the initial checkout and the new README commit.
4. `git ls-files` finds no tracked `runs/` content or `.env`; both paths are ignored. The checkout remains clean, with no actual `.env` or `runs/` directory.
5. Both required provider-key placeholders are present and blank in `.env.example`. Optional user-facing configuration coverage is being reviewed separately from internal Lab/test environment variables.

The first standard sync attempt used the account's general public-package cache and hit a 600-second observation timeout. An offline check against the existing Headroom package cache then identified a missing `python-multipart==0.0.32` wheel. A subsequent normal locked sync using that package cache fetched the missing public dependency and succeeded. These attempts remain separately recorded in [preflight.json](preflight.json); the timeout is not rewritten as a successful run.

## Lab image

The existing `headroom-lab:py312-cu124-runtime-v1` image was present, but its dependency-lock label did not match the checkout's `uv.lock`. The real read-only runtime contract rejected it. The authorized repair uses the repository's original `bash scripts/build_lab_image.sh`, not a bypass of that contract.

The script builds only the Headroom tag from a six-file allowlist context. The context excludes source, keys, runs, host caches and the host virtual environment. Its build-time checks import installed packages and execute a small CPU tensor operation; they do not initialize or query a GPU. The original build completed with exit code 0 in 1,301.531 seconds. Its dependency check and CPU tensor verification passed. The real runtime contract now accepts immutable image ID `sha256:5703e9edc41be02a69ba7bdf4eb9e5126a5f8915e1dd235ab9fe94b9a412afe5`, with lock SHA256 `fd57ad059cfde399f9de957bfca8527d69d3da0f9a7577c32bce1530c023a183`. The previous image remains available by its original ID; no unrelated image or service was changed.

## Remaining F5 acceptance

- Integrated environment-example/Runtime checks passed at 96994dd; see [integrated-check.json](integrated-check.json).
- A real s3 repair, its report, model/GPU execution, and the <= USD 0.30 acceptance remain unexecuted and require the outstanding run authorization. The CLI's explicit limit option is `--budget 0.30`; merely copying an example file does not authorize spending.
- No new allocation, `v1.0-submission` tag, or push was performed.

Exact commands, outcomes, package versions, hashes and the current build status are in [preflight.json](preflight.json).

## Integrated source check

The same independent checkout fetched commit 96994dd and passed version/fix/diagnose/watch CLI checks plus parsing of the blank-key, disabled-public-interface example configuration. Its dependency-lock hash was unchanged, so dependency installation and Lab image building were not repeated. The checkout stayed clean with no actual .env or runs directory. See [integrated-check.json](integrated-check.json). This completes the free setup checks; the required real s3 repair and submission tag remain pending.
