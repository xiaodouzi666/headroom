"""One reviewed incremental build; same old dependency records plus Ruff."""

import hashlib
import json
import subprocess
import time
from pathlib import Path

R = Path("/home/xiaodouzi/workspace/headroom")
O = R / "reports/acceptance-v2-r3-20261025"
P = json.loads((O / "image-incremental-plan.json").read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ident(tag):
    return json.loads(subprocess.check_output(["docker", "image", "inspect", tag], text=True))[0]


def packages(tag):
    code = "import importlib.metadata as m,json; print(json.dumps({d.metadata['Name'].lower().replace('_','-'):d.version for d in m.distributions()},sort_keys=True))"
    return json.loads(
        subprocess.check_output(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--entrypoint",
                "/opt/lab-venv/bin/python",
                tag,
                "-I",
                "-c",
                code,
            ],
            text=True,
        )
    )


assert ident(P["base_tag"])["Id"] == P["base_image_id"]
assert sha(R / "uv.lock") == P["uv_lock_sha256"]
for item in P["files"]:
    assert sha(R / item["path"]) == item["sha256"]
before = packages(P["base_tag"])
start = time.monotonic()
cmd = [
    "docker",
    "build",
    "--tag",
    "headroom-lab:py312-cu124-runtime-v1",
    "--build-arg",
    "HEADROOM_LOCK_SHA256=" + P["uv_lock_sha256"],
    str(R / P["context"]),
]
result = subprocess.run(cmd, check=False)
receipt = {
    "build_exit_code": result.returncode,
    "elapsed_seconds": time.monotonic() - start,
    "base_image_id": P["base_image_id"],
    "context": P["context"],
    "uv_lock_sha256": P["uv_lock_sha256"],
    "no_model_or_gpu": True,
}
if result.returncode == 0:
    doc = ident("headroom-lab:py312-cu124-runtime-v1")
    after = packages(doc["Id"])
    changed = {
        k: [before.get(k), after.get(k)]
        for k in before.keys() | after.keys()
        if before.get(k) != after.get(k)
    }
    assert changed == {"ruff": [None, "0.17.2"]}, changed
    assert ident(P["base_tag"])["Id"] == P["base_image_id"]
    assert doc["Config"]["Labels"]["org.headroom.uv-lock-sha256"] == P["uv_lock_sha256"]
    assert doc["Config"]["Labels"]["org.headroom.lab-runtime"] == "python312-self-contained-v1"
    assert doc["Config"]["User"] == "65534:65534"
    receipt.update(
        image_id=doc["Id"],
        user=doc["Config"]["User"],
        package_changes=changed,
        all_previous_package_versions_unchanged=True,
        base_tag_unchanged=True,
        verified=True,
    )
with (O / "image-incremental-result.json").open("x") as f:
    json.dump(receipt, f, indent=2)
    f.write("\n")
print(json.dumps(receipt), flush=True)
raise SystemExit(result.returncode)
