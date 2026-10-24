"""Build-time CPU-only environment verification, independent of project source or credentials."""

import importlib.metadata
import json
import platform
import sys
from pathlib import Path

import torch

assert sys.version_info[:2] == (3, 12), "Lab requires image-owned Python 3.12"
assert Path(sys.prefix) == Path("/opt/lab-venv"), "Lab venv must belong to the image"
assert torch.__version__ == "2.5.1+cu124"
assert torch.version.cuda == "12.4"  # Build metadata only; never query/initialize a GPU.
assert importlib.metadata.version("transformers") == "4.46.3"
assert importlib.metadata.version("accelerate") == "1.1.1"
assert (torch.tensor([2.0], device="cpu") * 3).item() == 6
report = {
    "runtime_contract": "python312-self-contained-v1",
    "python": platform.python_version(),
    "executable": sys.executable,
    "prefix": sys.prefix,
    "uv_lock_sha256": Path("/opt/headroom-lab/lock.sha256").read_text().strip(),
    "torch": torch.__version__,
    "cuda_build": torch.version.cuda,
    "transformers": importlib.metadata.version("transformers"),
    "accelerate": importlib.metadata.version("accelerate"),
    "cpu_tensor_check": True,
    "gpu_executed": False,
}
Path("/opt/headroom-lab/runtime.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report), flush=True)
