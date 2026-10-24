# Pinned repository inputs

`headroom fix --repo URL --ref COMMIT --cmd 'python train.py ...'` accepts a public HTTPS github.com repository and an exact lowercase 40-character commit SHA. The API accepts the same three fields. Source is fetched without Git credential helpers, global config, hooks, submodule recursion or shell execution, then copied into a new bounded source tree. Symlinks, traversal and submodules are rejected. No setup script or package installation from the repository runs on the host.

The reviewed nanoGPT pin is `3adf61e154c3fe3fca428ad6bc3818b27a3b8291`. Its prepared tree contains only original `train.py`, `model.py`, `configurator.py`, and deterministic synthetic uint16 train/validation tokens. The historical baseline command's `--dataset=/input` is explicitly mapped to `--dataset=headroom_synthetic`; this changes dataset location, not token bytes. The manifest records both hashes and the mapping.

nanoGPT's configurator requires `--key=value` syntax. Positional configuration files, `-c` and `-m` entrypoints are not accepted. Only the pinned nanoGPT directory in Docker receives narrowly hashed static-policy allowances for its original code. Uploaded scripts never receive that profile. Patches still undergo static policy, diff, compilation and runtime verification.

General repository commands support direct scripts with interpreter flags and
local `python -m package.entry` / package `__main__.py` entrypoints. Their full
argv is retained for every Lab replay; only target-program arguments can change
during candidate/reference runs. The pinned nanoGPT profile still requires its
reviewed `train.py` entrypoint and argument grammar. An already staged local
repository uses `--source-root /absolute/project --cmd 'python -O -m pkg.train'`.
See [COMMAND_MODE.md](COMMAND_MODE.md) for CPU evidence and remaining launcher limits.

Preparation succeeds without Nebius; a repair still needs the reviewed live runtime. T1.9's successful GPU repair, 22 GB, patch-length and model-cost requirements remain pending until real model execution.
