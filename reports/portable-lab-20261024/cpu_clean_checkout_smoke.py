"""Actual CPU Lab from an isolated candidate checkout with no local virtual environment."""

import argparse
import json
import os
import platform
import runpy
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
runpy.run_path(
    str(REPOSITORY / "reports/pareto-interfaces-20261024/offline_tests.py"), run_name="guard_only"
)

SOURCE = """import json
import os
import sys
import torch
print(json.dumps({"executable": sys.executable, "prefix": sys.prefix,
                  "real_prefix": os.path.realpath(sys.prefix), "torch": torch.__version__}), flush=True)
torch.manual_seed(1337)
model = torch.nn.Linear(2, 1)
optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
x = torch.tensor([[1.0, 2.0], [2.0, 1.0]], device="cpu")
y = torch.tensor([[0.0], [1.0]], device="cpu")
for step in range(10):
    optimizer.zero_grad()
    loss = ((model(x) - y) ** 2).mean()
    loss.backward()
    optimizer.step()
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    assert not (checkout / ".venv").exists() and not (checkout / ".venv").is_symlink()
    assert not (checkout / ".env").exists()
    sys.path.insert(0, str(checkout))
    from headroom.lab import runner
    from headroom.lab.runtime_image import IMAGE, lock_digest

    assert runner.PROJECT_ROOT == checkout, (runner.PROJECT_ROOT, checkout)
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.output / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text(SOURCE)
    document = {
        "host_executable": sys.executable,
        "host_executable_resolved": os.path.realpath(sys.executable),
        "host_prefix": sys.prefix,
        "host_python": platform.python_version(),
        "checkout": str(checkout),
        "checkout_has_venv": False,
        "image": IMAGE,
        "uv_lock_sha256": lock_digest(checkout),
        "gpu_executed": False,
        "provider_called": False,
        "runs": [],
    }
    for name, call in (
        (
            "script",
            lambda: runner.run_script(
                script,
                source_root=source,
                run_root=args.output / "runs-script",
                device="cpu",
                max_steps=3,
                max_seconds=20,
            ),
        ),
        (
            "module",
            lambda: runner.run_argv(
                source,
                ["python", "-u", "-m", "train"],
                run_root=args.output / "runs-module",
                device="cpu",
                max_steps=3,
                max_seconds=20,
            ),
        ),
    ):
        result = call()
        saved = Path(result["run_dir"])
        text = (saved / "stdout.log").read_text()
        runtime = next(json.loads(line) for line in text.splitlines() if '"real_prefix"' in line)
        document["runs"].append({"mode": name, "result": result, "runtime": runtime})
        (args.output / "receipt.json").write_text(json.dumps(document, indent=2) + "\n")
        assert result["status"] == "completed", result
        assert result["steps"] == 3 and len(result["loss_series"]) == 3, result
        assert result["capture_complete"] is True and result["cleanup_verified"] is True
        assert runtime["real_prefix"] == "/opt/lab-venv", runtime
        assert runtime["torch"] == "2.5.1+cu124"
    document["passed"] = True
    (args.output / "receipt.json").write_text(json.dumps(document, indent=2) + "\n")
    print(
        json.dumps(
            {
                "passed": True,
                "receipt": str(args.output / "receipt.json"),
                "runs": len(document["runs"]),
            }
        )
    )


if __name__ == "__main__":
    main()
