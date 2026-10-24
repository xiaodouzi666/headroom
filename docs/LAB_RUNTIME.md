# Portable Lab Python runtime

The Lab image owns Python 3.12 and its dependencies under `/opt/lab-venv`. Its
`/opt/venv` symlink is an internal compatibility alias for previously recorded
commands. The host virtual environment is not mounted or executed in the Lab.
A host CLI installed using uv-managed Python, Conda, or system Python therefore
does not need the same interpreter path or standard-library layout as the image.
The host still needs a working locked Headroom installation and Docker access.

## Build from a clean clone

After `uv sync --locked --python 3.12`, run the existing command:

```sh
bash scripts/build_lab_image.sh
```

The wrapper selects the already-synced project Python with `uv run --no-sync`,
not whichever system `python3` happens to be installed. It explicitly disables
dotenv loading and runs that bootstrap offline.

The build script exports production dependencies from the checked-in `uv.lock`
with `uv export --frozen --offline --no-dev --no-emit-project`. It neither updates
the lock nor installs/downloads a host interpreter. Every exported distribution
has an exact version and SHA-256 hashes. Installation inside the image uses
`pip --require-hashes --only-binary=:all:` and the two reviewed public package
indexes. No editable project installation or source distribution build is used.
The exported production graph is shared with the host lock, including the
existing Transformers and Accelerate fixture dependencies; it has no separate
floating Lab resolver.

Dependency downloads and OS package installation require public network access
**during image construction only**. They do not access model APIs, credentials,
weights, or datasets. Model execution and training are not performed during the
build. The build checks Python, locked package versions, CUDA *build metadata*,
and a tiny CPU tensor calculation. It does not query or initialize a GPU.
The base OS is Ubuntu 24.04; Python package hashes are pinned, while OS security
package updates may change the resulting image digest. Each built image has its
own actual image ID and records the source lock hash. The OS layer is not claimed
to be bit-for-bit reproducible.

The new image tag is `headroom-lab:py312-cu124-runtime-v1`. Existing old images and
historical captures are not removed. A failed build does not switch or overwrite
the old Lab tag. A successful new build does not itself start a job or enable a
live runtime profile.

## Reviewable build context

Each invocation retains a small context under `.cache/lab-build/<unique-id>/`.
The build sends that directory, never the repository root. Its whitelist is:

- `Dockerfile`
- `requirements.txt`
- `verify_runtime.py`
- `lock.sha256`
- `.dockerignore`
- `context.json` (local review manifest, excluded from the Docker payload)

The manifest records file hashes and the locked dependency count. The deny-first
`.dockerignore` includes only the four required build files. `.env`, host `.venv`,
`runs`, project source, account caches, tokenizer caches and model assets never
enter the context. Host credential and custom index environment variables are
not inherited by the offline lock exporter. Unsupported source/index references
and unlocked requirement lines fail before Docker is invoked.

To prepare and inspect these files without a build or download:

```sh
bash scripts/build_lab_image.sh --prepare-only
```

Keep a retained context and its build log when reproducing a failed build. There
is no automatic image or build-cache prune. The image contains several GB of
PyTorch/CUDA dependencies; allow additional temporary build disk space. The
Docker daemon stores these layers in its own data directory, which may differ
from the repository filesystem.

## Local runtime preflight

Before constructing a Lab container, the host checks local image metadata for
the self-contained runtime contract and the current `uv.lock` SHA-256. An old,
missing, or stale image produces an actionable rebuild message; the check does
not pull images, mount a host virtual environment, contact a provider, or run a
GPU workload. Changing the lock requires rebuilding the image. Container
metadata records the actual image identity for later inspection.

The source snapshot and the Headroom capture package are mounted separately,
read-only, as before. Runtime network isolation, limits, unprivileged execution,
output ownership and cleanup requirements remain enforced by the Lab runner.
The image fixes interpreter/dependency portability; it does not grant model
access, prove CUDA behavior on a new GPU, or complete the model-driven repair
acceptance gate. A CPU smoke check is only execution/capture evidence.

## Existing scenario acceptance helpers

`scripts/check_scenario_smoke.py` and `scripts/check_gpu_baselines.py` use the
same runtime-image contract and verified image digest. They no longer bind a
host `.venv` into Docker. The CPU helper remains a CPU plumbing check; the GPU
helper retains its explicit full-size telemetry and acceptance rules. This
change does not rewrite previous reports or launch either class of workload.
