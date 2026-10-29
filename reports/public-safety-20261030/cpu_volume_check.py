"""Explicit CPU-only, small-quota Docker verification; no model/API keys."""

import json
import os
import subprocess
import uuid
from pathlib import Path

from headroom.lab import artifact_volume as av
from headroom.lab import docker
from headroom.lab.envs import HOST_ENV
from headroom.lab.runtime_image import require_runtime_image

root = Path.cwd()
report = root / "reports/public-safety-20261030"
report.mkdir(parents=True, exist_ok=True)
cache = root / ".cache/public-safety-20261030/cpu-volume"
cache.mkdir(parents=True, exist_ok=True)
runtime = require_runtime_image(root, executable=docker.docker_binary(), environment=HOST_ENV)
cases = {
    "regular": "import json; open('/out/result.json','w').write(json.dumps({'case':'regular','cpu_only':True}))",
    "byte_limit": """import os,json
n=0
try:
 with open('/out/fill','wb') as f:
  while n < 4*1024*1024:
   f.write(b'x'*65536); f.flush(); n+=65536
except OSError as e:
 err=e.errno
else:
 err=None
os.unlink('/out/fill')
open('/out/result.json','w').write(json.dumps({'case':'byte_limit','bytes_before_failure':n,'errno':err,'cpu_only':True}))
assert err==28 and n<=2*1024*1024
""",
    "inode_limit": """import os,json
names=[]
try:
 for i in range(128):
  p='/out/fill-'+str(i)
  with open(p,'w') as f: f.write('x')
  names.append(p)
except OSError as e:
 err=e.errno
else: err=None
for p in names: os.unlink(p)
open('/out/result.json','w').write(json.dumps({'case':'inode_limit','files_before_failure':len(names),'errno':err,'cpu_only':True}))
assert err==28 and len(names)<32
""",
    "symlink": "import os; os.symlink('/etc/passwd','/out/result.json')",
}
results = []
for label, code in cases.items():
    target = "headroom-lab-" + uuid.uuid4().hex
    output = cache / (label + "-" + uuid.uuid4().hex)
    output.mkdir()
    store = None
    item = {"case": label, "cpu_only": True, "quota_bytes": 2 * 1024 * 1024, "quota_inodes": 32}
    try:
        store = av.create_store(
            target,
            runtime["image_id"],
            output_path=output,
            max_bytes=2 * 1024 * 1024,
            max_inodes=32,
        )
        cmd = [
            docker.docker_binary(),
            "create",
            "--pull",
            "never",
            "--name",
            target,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "64m",
            "--cpus",
            "0.25",
            "--pids-limit",
            "16",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--mount",
            f"type=volume,source={store['volume']},destination=/out",
            "--entrypoint",
            "/opt/venv/bin/python",
            runtime["image_id"],
            "-I",
            "-S",
            "-c",
            code,
        ]
        made = subprocess.run(
            cmd, env=HOST_ENV, capture_output=True, text=True, timeout=20, check=False
        )
        if made.returncode:
            raise RuntimeError("CPU target create failed: " + made.stderr[-300:])
        ran = subprocess.run(
            [docker.docker_binary(), "start", "--attach", target],
            env=HOST_ENV,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        item["target_returncode"] = ran.returncode
        item["target_cleanup"] = docker.cleanup_container(target)["cleanup_verified"]
        try:
            item["export"] = av.export_store(store, output)
        except av.ArtifactStoreError as error:
            item["export_rejected"] = str(error)
        if (output / "result.json").is_file():
            item["output"] = json.loads((output / "result.json").read_text())
        item["pass"] = (
            ran.returncode == 0
            and item["target_cleanup"]
            and (
                ("export_rejected" in item and not list(output.iterdir()))
                if label == "symlink"
                else item.get("export", {}).get("export_verified") is True
            )
        )
    except Exception as error:  # noqa: BLE001 - retain evidence and clean all test resources
        item["pass"] = False
        item["error"] = type(error).__name__ + ": " + str(error)[:500]
    finally:
        item["final_target_cleanup"] = docker.cleanup_container(target)["cleanup_verified"]
        if store is not None:
            item["store_cleanup"] = av.cleanup_store(store)
        item["pass"] = bool(
            item.get("pass")
            and item["final_target_cleanup"]
            and item.get("store_cleanup", {}).get("cleanup_verified")
        )
        results.append(item)
        (report / "small-cpu-volume.json").write_text(
            json.dumps(
                {
                    "scope": "small CPU Docker only; no GPU, model, production request or secrets",
                    "runtime": runtime,
                    "cases": results,
                },
                indent=2,
            )
            + "\n"
        )
        print(json.dumps(item), flush=True)
assert all(x["pass"] for x in results)
