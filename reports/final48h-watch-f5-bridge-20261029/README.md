# Watch and F5 private execution bridges

Offline implementation is frozen. The final focused suite passed **97 tests,
with 12 real CPU Watch tests deselected, in 53.76 seconds**. This includes all
**25 new bridge tests**; these counts overlap. Source hashes were unchanged
through the run, outer DNS/socket guard attempts were zero, Ruff/format passed,
and the five-file Gitleaks scan had zero findings.

## Watch contract

headroom.acceptance.watch_binding.prepare_watch_intent(command, *, source_root,
device='cuda', max_steps=20, max_seconds=120, seed=1337, fix_options=None) returns
the shared feature intent: kind watch, profile/run/daily limits, and a payload
with original argv, canonical queued FixRequest and bounded source-file hashes.
Only directly mapped Python entrypoints are supported by this fixed acceptance
path; ordinary Watch keeps its broader capture behavior.

load_watch_feature_context(path, *, command, source_root, device, max_steps,
max_seconds, seed, fix_options) reads exactly {binding, intent} from a current
owner's 0600 regular nonsymlink leaf, bounded to 1 MiB. It rebuilds the intended
command/source and verifies the claimed F3b/watch-s1 slot before any Lab call.
The fixed original source is allocation.project_root/scenarios/s1_batch_too_big/train.py.

run_bound_watch(..., intent=intent, allocation_child_binding=binding) returns
the existing Watch outcome. It fixes the Watch directory to
allocation.project_root/runs/watch/child_run_id and uses exclusive creation
before capture. Reusing that child, including after a non-OOM observation,
cannot capture again; an alternate run root is rejected. The new private
watch_id parameter defaults to None for ordinary Watch.

Repair uses the actual captured source and manifest, verifies the normalized
container argv, complete file map, controls, CUDA OOM and cleanup, then calls
normal run_fix with the assigned child run ID and Services.budget_factory.
The normal accounting path retains open_run/close_run and final cost checks.
Every reservation rechecks feature receipt/profile/DB and captured source.
No offline runtime_factory is used by the production helper.

The controller owns claim/settlement. A normal function return is not proof of
repair success. Before finish_feature_child, confirm terminal execution, the
original Lab cleanup flag, and owned repair-job cleanup using the existing
cleanup_owned_lab path for watch_directory/fix and the assigned child run ID.
Unknown cleanup must remain false. A non-OOM capture remains capture-only.
Do not erase reservations, claim a replacement child, or force a failed run
into successful acceptance.

## F5 contract

cli_execution.prepare_feature_fix_intent(request, *, checkout) prepares kind
fix for the fixed s3 source in a separate clean Git checkout. It pins its commit,
all Headroom Python sources, pyproject.toml, uv.lock, and the complete actual
fixed-s3 Lab-copy file set. Extra files are rejected even if Git ignores them.

Pass the claimed child and intent through
supervise_evaluation_run(..., allocation_child_binding=binding,
feature_intent=intent, preparation=None). The worker uses that checkout's own
.venv/bin/headroom. Its child environment removes PYTHONPATH and PYTHONHOME;
load_context must observe the actual imported package inside the declared
checkout. The original allocation's absolute reviewed profile and database are
accepted, but request/profile/caps/run ID must match the receipt. Every reserve
rechecks the actual clean checkout, not just stored hashes. Existing 480-second
supervision and owned cleanup remain unchanged.

The isolated positive test used a temporary committed checkout and its own venv
console; its dependencies and offline test hooks were fixture-controlled. It
proved the imported headroom.__file__ was inside that checkout and inherited
PYTHONPATH/PYTHONHOME were absent. It does not claim a new real F5 Quickstart
acceptance or a newly installed production environment.

## Review fixes and retained evidence

Two independent F5 review findings were repaired: ignored torch.py/json.py
modules could otherwise alter the copied workload, and tracked code/source
changes after before_run needed refusal on the next reservation. Negative tests
cover both. A final once-only Watch review added exclusive child-directory
consumption; duplicate context and changed run-root attempts are refused.

The initial combined selection excluded only four names containing
real_cpu_docker and accidentally selected eight other real_cpu tests. The outer
process guard refused their Docker launch before execution. The failure log is
retained; the final selection excludes all twelve real_cpu cases. The earlier
96-test pre-once stage is also retained, not added to final counts.

No real allocation/profile, production ledger, provider request, GPU workload,
Watch container execution, public flag or project commit was created or changed.
All budget writes were in temporary offline fixtures. The actual feature runs,
normal private credentials, clean-checkout refresh and human authorization
remain separate steps. Receipt JSON records exact source and artifact hashes.
