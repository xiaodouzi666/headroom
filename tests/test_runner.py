"""Real CPU Docker checks for the Lab trust boundary and execution contract."""

import json
import time
from pathlib import Path

import pytest

from headroom.lab.runner import run_command, run_script

TRAINING = """import random
import numpy as np
import torch
from torch import nn
torch.set_num_threads(1)
model = nn.Linear(8, 1)
optimizer = torch.optim.AdamW(model.parameters(), lr=0.01)
for index in range(100):
    x = torch.randn(8, 8) + random.random() + float(np.random.random())
    optimizer.zero_grad(set_to_none=True)
    loss = model(x).square().mean()
    loss.backward()
    optimizer.step()
print("UNEXPECTED_FINISHED_100_STEPS")
"""


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    return root


def test_adamw_steps_and_all_three_seeds_are_deterministic(source, tmp_path):
    script = source / "train.py"
    script.write_text(TRAINING)
    runs = [
        run_script(script, device="cpu", run_root=tmp_path / "runs", max_steps=20, seed=seed)
        for seed in (1337, 1337, 1338)
    ]
    for result in runs:
        assert result["status"] == "completed", result
        assert result["steps"] == 20
        assert len(result["loss_series"]) == 20
        assert result["cleanup_verified"]
    assert runs[0]["loss_series"][:5] == runs[1]["loss_series"][:5]
    assert runs[0]["loss_series"][:5] != runs[2]["loss_series"][:5]


def test_command_mode_captures_real_optimizer_steps(source, tmp_path):
    (source / "train.py").write_text(TRAINING)
    result = run_command(
        source, ["python", "train.py"], device="cpu", run_root=tmp_path / "runs", max_steps=7
    )
    assert result["status"] == "completed", result
    assert result["steps"] == 7
    assert len(result["loss_series"]) == 7
    assert result["cleanup_verified"]


def test_keys_absent_and_source_read_only(source, tmp_path, monkeypatch):
    for name in ("NEBIUS_API_KEY", "TAVILY_API_KEY", "HF_TOKEN", "UNRELATED_SECRET"):
        monkeypatch.setenv(name, "canary-never-a-real-credential")
    (source / ".env").write_text("ONLY_A_TEST_CANARY=do-not-copy\n")
    script = source / "check.py"
    script.write_text("""import json, os
from pathlib import Path
keys = {key: os.environ.get(key) for key in
        ("NEBIUS_API_KEY", "TAVILY_API_KEY", "HF_TOKEN", "UNRELATED_SECRET")}
assert all(value is None for value in keys.values()), "environment leak"
assert not Path("/source/.env").exists(), "source secret copied"
assert not Path("/runtime/.env").exists(), "runtime root mounted"
try:
    Path("/source/unexpected.txt").write_text("unsafe")
except OSError:
    readonly = True
else:
    readonly = False
assert readonly, "source writable"
Path("/out/boundary-check.json").write_text(json.dumps({"keys":keys,"readonly":readonly}))
""")
    result = run_script(script, device="cpu", run_root=tmp_path / "runs")
    assert result["status"] == "completed", result
    boundary = json.loads((Path(result["artifact_dir"]) / "boundary-check.json").read_text())
    assert all(value is None for value in boundary["keys"].values())
    assert boundary["readonly"]
    assert result["cleanup_verified"]
    assert not (source / "unexpected.txt").exists()


def test_cpu_out_of_memory_is_an_error(source, tmp_path):
    script = source / "cpu_oom.py"
    script.write_text('import torch\nraise torch.OutOfMemoryError("CPU out of memory")\n')
    result = run_script(script, device="cpu", run_root=tmp_path / "runs")
    assert result["status"] == "error", result
    assert result["cleanup_verified"]


def test_infinite_loop_timeout_30_seconds_cleans_container_and_children(source, tmp_path):
    script = source / "forever.py"
    script.write_text("""import subprocess, sys, time
from pathlib import Path
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(180)"])
Path("/out/child-started.txt").write_text(str(child.pid))
while True:
    time.sleep(1)
""")
    started = time.monotonic()
    result = run_script(script, device="cpu", run_root=tmp_path / "runs", max_seconds=30)
    elapsed = time.monotonic() - started
    assert result["status"] == "timeout", result
    assert result.get("reason") == "TIMEOUT", result
    assert result["cleanup_verified"], result
    assert (Path(result["artifact_dir"]) / "child-started.txt").exists()
    assert 29 <= elapsed < 65, elapsed


def test_full_cpp_symbolization_dependency_is_available_without_cuda(source, tmp_path):
    script = source / "symbolize.py"
    script.write_text("""import json
from pathlib import Path
import torch
from torch.utils._traceback import CapturedTraceback
assert not torch.cuda.is_initialized()
frames = CapturedTraceback.extract(cpp=True).format()
assert len(frames) > 0
assert not torch.cuda.is_initialized()
Path("/out/symbolizer.json").write_text(json.dumps({"frames":len(frames),"cuda_initialized":False}))
""")
    result = run_script(script, device="cpu", run_root=tmp_path / "runs")
    assert result["status"] == "completed", result
    assert result["cleanup_verified"]
    details = json.loads((Path(result["artifact_dir"]) / "symbolizer.json").read_text())
    assert details["frames"] > 0
    assert details["cuda_initialized"] is False
