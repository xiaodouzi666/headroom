"""CPU-only host lifecycle, Docker identity and supervised recovery boundaries."""

import copy
import json
import os
import socket
from types import SimpleNamespace

import pytest

from headroom.api import queue
from headroom.lab import docker, reference_scratch
from headroom.lab import reference_scratch_lifecycle as lifecycle


@pytest.fixture
def generous_disk(monkeypatch):
    monkeypatch.setattr(
        reference_scratch.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12)
    )


def test_zero_reference_budget_does_not_create_service_or_modify_manifest(tmp_path):
    state = {}
    with lifecycle.managed_reference_scratch(tmp_path, 0, state) as endpoint:
        assert endpoint is None
    assert state == {}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("raise_inside", [False, True])
def test_managed_broker_binds_intent_and_cleans_live_objects_on_exit(
    tmp_path, generous_disk, raise_inside
):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"preserved": "host-owned"}))
    state = {}
    try:
        with lifecycle.managed_reference_scratch(tmp_path, 128, state) as endpoint:
            expected = json.loads(manifest.read_text())["owned_reference_scratch"]
            assert expected["root"] == str(tmp_path / "reference-scratch")
            assert expected["socket_path"] == str(endpoint)
            assert expected["owner_pid"] == os.getpid()
            assert state["request_verified"] is True
            assert state["cleanup_verified"] is False
            client = reference_scratch.ReferenceScratchClient(endpoint, 128)
            identity = client.create()
            client.append(identity, b"live tensor bytes")
            client.finalize(identity)
            if raise_inside:
                raise RuntimeError("synthetic target failure")
    except RuntimeError as error:
        assert raise_inside and str(error) == "synthetic target failure"
    assert state["request_verified"] is True
    assert state["cleanup_verified"] is True
    assert state["live_reserved_bytes"] == state["live_objects"] == 0
    assert state["peak_reserved_bytes"] == len(b"live tensor bytes")
    assert state["target_host_directory_access"] is False
    assert not endpoint.exists()
    assert list((tmp_path / "reference-scratch" / "objects").iterdir()) == []
    assert json.loads((tmp_path / "reference-scratch-host.json").read_text()) == state
    assert json.loads(manifest.read_text())["preserved"] == "host-owned"


def test_existing_intent_is_not_overwritten_or_marked_verified(tmp_path, generous_disk):
    previous = {"nonce": "a" * 32, "preserve": True}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"owned_reference_scratch": previous}))
    state = {}
    with (
        pytest.raises(ValueError, match="intent already exists"),
        lifecycle.managed_reference_scratch(tmp_path, 128, state),
    ):
        pytest.fail("duplicate ownership must not enter target execution")
    assert json.loads(path.read_text())["owned_reference_scratch"] == previous
    assert state["request_verified"] is False
    assert state["cleanup_verified"] is False
    assert state["live_reserved_bytes"] == state["live_objects"] == 0


def test_close_failure_cannot_claim_verified_cleanup(tmp_path, generous_disk, monkeypatch):
    (tmp_path / "manifest.json").write_text("{}")
    original_close = reference_scratch.ReferenceScratchBroker.close

    def close_then_fail(self):
        original_close(self)
        raise OSError("synthetic cleanup failure")

    monkeypatch.setattr(reference_scratch.ReferenceScratchBroker, "close", close_then_fail)
    state = {}
    with lifecycle.managed_reference_scratch(tmp_path, 128, state):
        pass
    assert state["request_verified"] is True
    assert state["cleanup_verified"] is False
    assert state["cleanup_error_type"] == "OSError"


def test_active_owner_recovery_refuses_to_delete_any_live_data(tmp_path, generous_disk):
    (tmp_path / "manifest.json").write_text("{}")
    state = {}
    with lifecycle.managed_reference_scratch(tmp_path, 128, state) as endpoint:
        client = reference_scratch.ReferenceScratchClient(endpoint, 128)
        identity = client.create()
        client.append(identity, b"do not remove")
        client.finalize(identity)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert lifecycle.recover_reference_scratch(tmp_path, manifest) is False
        assert client.read(identity, 0, 128) == b"do not remove"


@pytest.mark.parametrize("mutation", ["root", "nonce", "max_bytes", "schema", "descriptor_type"])
def test_invalid_recovery_descriptor_never_calls_cleanup(tmp_path, monkeypatch, mutation):
    expected = {
        "schema": reference_scratch.SCHEMA,
        "root": str(tmp_path / "reference-scratch"),
        "nonce": "a" * 32,
        "max_bytes": 128,
    }
    values = {"root": "/tmp/foreign", "nonce": "../bad", "max_bytes": True, "schema": "other"}
    if mutation == "descriptor_type":
        expected = []
    else:
        expected[mutation] = values[mutation]
    monkeypatch.setattr(
        reference_scratch, "cleanup_owned_scratch", lambda *_a, **_k: pytest.fail("unsafe cleanup")
    )
    assert (
        lifecycle.recover_reference_scratch(tmp_path, {"owned_reference_scratch": expected})
        is False
    )


@pytest.fixture
def docker_arguments(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / "headroom").mkdir(parents=True)
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    output.mkdir()
    monkeypatch.setattr(
        docker, "require_runtime_image", lambda *_a, **_k: {"image_id": "sha256:fixed"}
    )
    monkeypatch.setattr(docker, "docker_binary", lambda: "/usr/bin/docker")
    monkeypatch.setattr(docker, "validated_hf_cache", lambda _: None)
    return {
        "name": "headroom-lab-" + "a" * 32,
        "project_root": project,
        "source": source,
        "output": output,
        "environment": {},
        "command": ["python3", "-m", "headroom.lab.run_target"],
        "device": "cpu",
    }


def test_docker_mounts_only_readonly_socket_not_private_tensor_directory(
    tmp_path, docker_arguments
):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    path = private / "rpc.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(path))
        path.chmod(0o600)
        arguments = docker.create_arguments(**docker_arguments, reference_scratch_socket=path)
    mounts = [arguments[i + 1] for i, value in enumerate(arguments[:-1]) if value == "--mount"]
    matching = [mount for mount in mounts if lifecycle.SOCKET_DESTINATION in mount]
    assert matching == [
        f"type=bind,source={path},destination={lifecycle.SOCKET_DESTINATION},readonly"
    ]
    assert all(f"source={private}," not in mount for mount in mounts)
    assert arguments[arguments.index("--network") + 1] == "none"
    assert arguments[arguments.index("--memory") + 1] == "32g"
    assert "--gpus" not in arguments and "--privileged" not in arguments


@pytest.mark.parametrize("kind", ["regular", "symlink", "broad_mode"])
def test_docker_rejects_nonprivate_or_linked_socket(tmp_path, docker_arguments, kind):
    path = tmp_path / "rpc.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        if kind == "regular":
            path.write_text("not a socket")
        else:
            server.bind(str(path))
        path.chmod(0o600 if kind != "broad_mode" else 0o666)
        if kind == "symlink":
            link = tmp_path / "alias.sock"
            link.symlink_to(path)
            path = link
        with pytest.raises(ValueError, match="owned private Unix socket"):
            docker.create_arguments(**docker_arguments, reference_scratch_socket=path)


@pytest.mark.parametrize("mutation", [None, "writable", "foreign", "unrequested"])
def test_owned_target_rechecks_socket_identity_and_readonly_mount(monkeypatch, mutation):
    name, target_id = "headroom-lab-" + "a" * 32, "b" * 64
    store = {"image_id": "sha256:fixed", "volume": "owned-volume"}
    args = [
        "docker",
        "create",
        "--mount",
        "type=bind,source=/owned/source,destination=/source,readonly",
    ]
    scratch_mount = {
        "Type": "bind",
        "Source": "/owned/rpc.sock",
        "Destination": lifecycle.SOCKET_DESTINATION,
        "RW": False,
    }
    details = {
        "Name": "/" + name,
        "Id": target_id,
        "Image": store["image_id"],
        "Mounts": [
            {"Source": "/owned/source", "Destination": "/source", "RW": False},
            {"Type": "volume", "Name": store["volume"], "Destination": "/out", "RW": True},
            scratch_mount,
        ],
    }
    if mutation != "unrequested":
        args += [
            "--mount",
            f"type=bind,source=/owned/rpc.sock,destination={lifecycle.SOCKET_DESTINATION},readonly",
        ]
    if mutation == "writable":
        scratch_mount["RW"] = True
    if mutation == "foreign":
        scratch_mount["Source"] = "/foreign/rpc.sock"
    monkeypatch.setattr(docker.artifact_volume, "_inspect", lambda *_: copy.deepcopy(details))
    if mutation is None:
        assert docker._owned_target(name, target_id, store, args) == details
    else:
        with pytest.raises(ValueError, match="ownership changed"):
            docker._owned_target(name, target_id, store, args)


@pytest.mark.parametrize("scratch_ok", [True, False])
def test_queue_recovers_scratch_only_after_target_absent_and_artifact_cleanup(
    tmp_path, monkeypatch, scratch_ok
):
    run_id, lab_id = "a" * 32, "b" * 32
    item = tmp_path / run_id / "lab" / lab_id
    item.mkdir(parents=True)
    name = "headroom-lab-" + lab_id
    store = {
        "target": name,
        "output_path": str(item / "artifacts"),
        "volume": docker.artifact_volume.names(name)["volume"],
    }
    manifest = {
        "image": docker.IMAGE,
        "command": ["python3"],
        "owned_artifact_store": store,
        "owned_reference_scratch": {"nonce": "c" * 32},
    }
    (item / "manifest.json").write_text(json.dumps(manifest))
    events = []

    def inspect_absent(*_a, **_k):
        events.append("target_absent")
        return SimpleNamespace(returncode=1, stderr="No such container: " + name, stdout="")

    def cleanup_store(value):
        assert value == store
        events.append("artifact_cleanup")
        return {"cleanup_verified": True}

    def recover(directory, value):
        assert directory == item and value == manifest
        events.append("scratch_recovery")
        return scratch_ok

    monkeypatch.setattr(queue.subprocess, "run", inspect_absent)
    monkeypatch.setattr(docker, "docker_binary", lambda: "/usr/bin/docker")
    monkeypatch.setattr(docker.artifact_volume, "cleanup_store", cleanup_store)
    monkeypatch.setattr(lifecycle, "recover_reference_scratch", recover)
    assert queue.cleanup_owned_lab(tmp_path, run_id) is scratch_ok
    assert events == ["target_absent", "artifact_cleanup", "scratch_recovery"]


def test_manifest_write_failure_cannot_authenticate_unpublished_intent(
    tmp_path, generous_disk, monkeypatch
):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    original_write = lifecycle._write

    def fail_manifest(path, value):
        if path == manifest:
            raise OSError("synthetic host manifest storage failure")
        return original_write(path, value)

    monkeypatch.setattr(lifecycle, "_write", fail_manifest)
    state = {}
    with (
        pytest.raises(OSError, match="manifest storage failure"),
        lifecycle.managed_reference_scratch(tmp_path, 128, state),
    ):
        pytest.fail("unpublished intent must not enter target execution")
    assert json.loads(manifest.read_text()) == {}
    assert state["request_verified"] is False
    assert state["cleanup_verified"] is False
    assert state["live_reserved_bytes"] == state["live_objects"] == 0


def test_start_failure_cleans_endpoint_without_authenticating_request(
    tmp_path, generous_disk, monkeypatch
):
    (tmp_path / "manifest.json").write_text("{}")
    original_start = reference_scratch.ReferenceScratchBroker.start
    endpoints = []

    def start_then_fail(self):
        original_start(self)
        endpoints.append(self.socket_path)
        raise RuntimeError("synthetic start failure")

    monkeypatch.setattr(reference_scratch.ReferenceScratchBroker, "start", start_then_fail)
    state = {}
    with (
        pytest.raises(RuntimeError, match="start failure"),
        lifecycle.managed_reference_scratch(tmp_path, 128, state),
    ):
        pytest.fail("startup failure must not enter target execution")
    assert endpoints and not endpoints[0].exists()
    assert state["request_verified"] is False
    assert state["cleanup_verified"] is False
    assert state["live_reserved_bytes"] == state["live_objects"] == 0
    assert "owned_reference_scratch" not in json.loads((tmp_path / "manifest.json").read_text())


def test_recovery_rejects_linked_root_before_touching_foreign_directory(tmp_path, monkeypatch):
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    sentinel = foreign / "keep"
    sentinel.write_text("preserve")
    root = tmp_path / "reference-scratch"
    root.symlink_to(foreign, target_is_directory=True)
    expected = {
        "schema": reference_scratch.SCHEMA,
        "root": str(root),
        "nonce": "a" * 32,
        "max_bytes": 128,
    }
    monkeypatch.setattr(
        reference_scratch, "cleanup_owned_scratch", lambda *_a, **_k: pytest.fail("foreign cleanup")
    )
    assert (
        lifecycle.recover_reference_scratch(tmp_path, {"owned_reference_scratch": expected})
        is False
    )
    assert sentinel.read_text() == "preserve"
