"""Supervisor recovery must clean only this job's verified artifact resources."""

import json
import subprocess
from uuid import uuid4

import pytest

from headroom.api.queue import cleanup_owned_lab
from headroom.lab import docker


@pytest.mark.parametrize(
    "case", ["present", "absent", "discover", "store_failure", "wrong_volume", "wrong_id"]
)
def test_owned_quota_store_recovery(tmp_path, monkeypatch, case):
    run_id, lab_id = uuid4().hex, uuid4().hex
    directory = tmp_path / run_id / "lab" / lab_id
    directory.mkdir(parents=True)
    target = "headroom-lab-" + lab_id
    ident, image = "c" * 64, "sha256:" + "d" * 64
    store = {
        "target": target,
        "output_path": str(directory / "artifacts"),
        "volume": docker.artifact_volume.names(target)["volume"],
        "image_id": image,
    }
    manifest = {"image": docker.IMAGE, "command": ["python"], "owned_target_id": ident}
    if case != "discover":
        manifest["owned_artifact_store"] = store
    (directory / "manifest.json").write_text(json.dumps(manifest))
    calls = []
    details = {
        "Name": "/" + target,
        "Id": "e" * 64 if case == "wrong_id" else ident,
        "Image": image,
        "Mounts": [
            {"Destination": "/source", "Source": str(directory / "source"), "RW": False},
            {
                "Destination": "/out",
                "Type": "volume",
                "Name": "foreign" if case == "wrong_volume" else store["volume"],
                "RW": True,
            },
        ],
    }
    monkeypatch.setattr(docker, "docker_binary", lambda: "docker")
    monkeypatch.setattr(docker.artifact_volume, "discover_store", lambda *a, **k: store)

    def inspect(args, **kwargs):
        if case in {"absent", "discover"}:
            return subprocess.CompletedProcess(args, 1, "", "No such container: " + target)
        return subprocess.CompletedProcess(args, 0, json.dumps([details]), "")

    monkeypatch.setattr(subprocess, "run", inspect)
    monkeypatch.setattr(
        docker,
        "cleanup_container",
        lambda value: calls.append(("target", value)) or {"cleanup_verified": True},
    )
    monkeypatch.setattr(
        docker.artifact_volume,
        "cleanup_store",
        lambda value: (
            calls.append(("store", value["volume"]))
            or {"cleanup_verified": case != "store_failure"}
        ),
    )
    result = cleanup_owned_lab(tmp_path, run_id)
    assert result is (case not in {"store_failure", "wrong_volume", "wrong_id"})
    if case in {"wrong_volume", "wrong_id"}:
        assert calls == []
    elif case in {"absent", "discover"}:
        assert calls == [("store", store["volume"])]
    else:
        assert calls == [("target", ident), ("store", store["volume"])]
