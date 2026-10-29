"""Offline Docker metadata and bounded-tar tests; no real containers or network."""

import io
import socket
import subprocess
import tarfile
from types import SimpleNamespace

import pytest

from headroom.lab import artifact_volume as volume

TARGET = "headroom-lab-" + "a" * 32
IMAGE = "sha256:" + "b" * 64


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Real network/container dispatch forbidden in unit tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(volume, "_binary", lambda: "/usr/bin/docker")


class FakeDocker:
    def __init__(self):
        self.volumes, self.containers, self.calls = {}, {}, []
        self.fail_create = False

    def inspect(self, kind, name):
        return (self.volumes if kind == "volume" else self.containers).get(name)

    def run(self, args, **kwargs):
        self.calls.append(args)
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:2] == ["volume", "create"]:
            labels = dict(
                args[index + 1].split("=", 1)
                for index, value in enumerate(args)
                if value == "--label"
            )
            options = dict(
                args[index + 1].split("=", 1)
                for index, value in enumerate(args)
                if value == "--opt"
            )
            self.volumes[args[-1]] = {
                "Name": args[-1],
                "Driver": "local",
                "Labels": labels,
                "Options": options,
                "CreatedAt": "2026-10-30T00:00:00Z",
                "Mountpoint": "/fake/" + args[-1],
            }
        elif args[0] == "create":
            if self.fail_create:
                result.returncode = 1
                return result
            labels = dict(
                args[index + 1].split("=", 1)
                for index, value in enumerate(args)
                if value == "--label"
            )
            name = args[args.index("--name") + 1]
            labels["inherited-image-label"] = "unchanged"
            self.containers[name] = {
                "Name": "/" + name,
                "Id": "c" * 64,
                "Image": IMAGE,
                "Config": {
                    "Labels": labels,
                    "Env": ["NVIDIA_VISIBLE_DEVICES=void", "CUDA_VISIBLE_DEVICES="],
                },
                "State": {"Running": False},
                "HostConfig": {
                    "NetworkMode": "none",
                    "ReadonlyRootfs": True,
                    "DeviceRequests": None,
                },
                "Mounts": [
                    {
                        "Destination": "/out",
                        "Name": volume.names(TARGET)["volume"],
                        "RW": False,
                        "Type": "volume",
                    }
                ],
            }
        elif args[0] == "start":
            next(item for item in self.containers.values() if item["Id"] == args[1])["State"][
                "Running"
            ] = True
        elif args[:2] == ["rm", "--force"]:
            name = next(name for name, item in self.containers.items() if item["Id"] == args[2])
            del self.containers[name]
        elif args[:2] == ["volume", "rm"]:
            del self.volumes[args[2]]
        else:
            raise AssertionError(args)
        return result


@pytest.fixture
def store(tmp_path, monkeypatch):
    fake = FakeDocker()
    monkeypatch.setattr(volume, "_run", fake.run)
    monkeypatch.setattr(volume, "_inspect", fake.inspect)
    output = tmp_path / "artifacts"
    output.mkdir()
    metadata = volume.create_store(
        TARGET, IMAGE, output_path=output, max_bytes=2 * 1024 * 1024, max_inodes=32
    )
    return fake, output, metadata


def test_tmpfs_has_kernel_bytes_and_inode_limits_and_readonly_keeper(store):
    fake, output, metadata = store
    options = fake.volumes[metadata["volume"]]["Options"]
    assert options["type"] == options["device"] == "tmpfs"
    assert "size=2097152" in options["o"] and "nr_inodes=32" in options["o"]
    assert all(marker in options["o"] for marker in ("nodev", "nosuid", "noexec"))
    create = next(args for args in fake.calls if args[0] == "create")
    assert "--gpus" not in create and "--privileged" not in create
    assert "NVIDIA_VISIBLE_DEVICES=void" in create and "CUDA_VISIBLE_DEVICES=" in create
    assert create[create.index("--pull") + 1] == "never"
    assert create[create.index("--network") + 1] == "none"
    assert create[create.index("--mount") + 1].endswith(",readonly")
    assert metadata == volume.discover_store(TARGET, output_path=output)
    assert volume.cleanup_store(metadata)["cleanup_verified"]
    assert volume.discover_store(TARGET, output_path=output) is None


def test_existing_store_is_not_reused_or_removed(store):
    fake, output, metadata = store
    calls = list(fake.calls)
    with pytest.raises(volume.ArtifactStoreError, match="ALREADY_EXISTS"):
        volume.create_store(TARGET, IMAGE, output_path=output)
    assert fake.calls == calls and fake.volumes[metadata["volume"]]


def test_creation_failure_cleans_owned_resources(tmp_path, monkeypatch):
    fake = FakeDocker()
    fake.fail_create = True
    monkeypatch.setattr(volume, "_run", fake.run)
    monkeypatch.setattr(volume, "_inspect", fake.inspect)
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(volume.ArtifactStoreError) as caught:
        volume.create_store(TARGET, IMAGE, output_path=output)
    assert caught.value.metadata["creation_cleanup"]["cleanup_verified"]
    assert not fake.volumes


@pytest.mark.parametrize(
    "change",
    [
        "target_active",
        "volume_nonce",
        "volume_identity",
        "keeper_id",
        "keeper_rw",
        "keeper_gpu_env",
    ],
)
def test_cleanup_and_export_refuse_changed_ownership(store, change):
    fake, output, metadata = store
    if change == "target_active":
        fake.containers[TARGET] = {"Name": "/" + TARGET}
    elif change == "volume_nonce":
        fake.volumes[metadata["volume"]]["Labels"][volume.LABEL + ".nonce"] = "d" * 32
    elif change == "volume_identity":
        fake.volumes[metadata["volume"]]["CreatedAt"] = "changed"
    elif change == "keeper_id":
        fake.containers[metadata["keeper"]]["Id"] = "d" * 64
    elif change == "keeper_gpu_env":
        fake.containers[metadata["keeper"]]["Config"]["Env"] = [
            "NVIDIA_VISIBLE_DEVICES=all",
            "CUDA_VISIBLE_DEVICES=",
        ]
    else:
        fake.containers[metadata["keeper"]]["Mounts"][0]["RW"] = True
    count = len(fake.calls)
    assert volume.cleanup_store(metadata)["cleanup_verified"] is False
    assert len(fake.calls) == count
    with pytest.raises(volume.ArtifactStoreError):
        volume.export_store(metadata, output)


def archive(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as handle:
        for name, kind, data in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(data) if kind in (tarfile.REGTYPE, tarfile.AREGTYPE) else 0
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                member.linkname = "/etc/passwd"
            handle.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def test_export_preserves_expected_capture_bytes(tmp_path):
    raw = archive(
        [
            (".", tarfile.DIRTYPE, b""),
            ("result.json", tarfile.REGTYPE, b'{"real":true}'),
            ("processes", tarfile.DIRTYPE, b""),
            ("processes/123", tarfile.DIRTYPE, b""),
            ("processes/123/snapshot.pickle", tarfile.REGTYPE, b"DATA-ONLY-NOT-UNPICKLED"),
        ]
    )
    result = volume._export_tar(io.BytesIO(raw), tmp_path, max_bytes=1024, max_inodes=16)
    assert result["export_verified"]
    assert (tmp_path / "result.json").read_bytes() == b'{"real":true}'
    assert (tmp_path / "processes/123/snapshot.pickle").read_bytes() == b"DATA-ONLY-NOT-UNPICKLED"


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../result.json", tarfile.REGTYPE),
        ("/result.json", tarfile.REGTYPE),
        ("result.json", tarfile.SYMTYPE),
        ("result.json", tarfile.LNKTYPE),
        ("result.json", tarfile.FIFOTYPE),
        ("result.json", tarfile.CHRTYPE),
        ("result.json", tarfile.BLKTYPE),
        ("result.json", tarfile.GNUTYPE_SPARSE),
        ("unrelated.bin", tarfile.REGTYPE),
        ("processes/../../result.json", tarfile.REGTYPE),
        ("offloaded-tensors", tarfile.DIRTYPE),
        (".result.json.123.tmp", tarfile.REGTYPE),
    ],
)
def test_untrusted_archive_members_are_rejected(tmp_path, name, kind):
    raw = archive([(name, kind, b"data")])
    with pytest.raises((volume.ArtifactStoreError, tarfile.TarError)):
        volume._export_tar(io.BytesIO(raw), tmp_path, max_bytes=1024, max_inodes=16)


@pytest.mark.parametrize("kind", ["duplicate", "bytes", "entries", "raw_stream"])
def test_export_enforces_aggregate_limits(tmp_path, kind):
    if kind == "duplicate":
        raw = archive([("result.json", tarfile.REGTYPE, b"a")] * 2)
        options = {"max_bytes": 1024, "max_inodes": 16}
    elif kind == "bytes":
        raw = archive(
            [
                ("result.json", tarfile.REGTYPE, b"a" * 600),
                ("env.json", tarfile.REGTYPE, b"b" * 600),
            ]
        )
        options = {"max_bytes": 1024, "max_inodes": 16}
    elif kind == "entries":
        raw = archive([(".", tarfile.DIRTYPE, b"")] * 17)
        options = {"max_bytes": 1024, "max_inodes": 16}
    else:
        reader = volume._LimitedReader(io.BytesIO(b"a" * 100), 10)
        with pytest.raises(volume.ArtifactStoreError):
            reader.read(100)
        return
    with pytest.raises(volume.ArtifactStoreError):
        volume._export_tar(io.BytesIO(raw), tmp_path, **options)


def test_safe_stream_is_published_atomically_and_bad_stream_is_not(store, monkeypatch):
    _, output, metadata = store
    raw = archive([("result.json", tarfile.REGTYPE, b"{}")])

    def popen(args, **kwargs):
        assert args == ["/usr/bin/docker", "cp", metadata["keeper_id"] + ":/out/.", "-"]
        assert kwargs["stderr"] == subprocess.DEVNULL
        return SimpleNamespace(stdout=io.BytesIO(raw), pid=123, poll=lambda: 0, wait=lambda **_: 0)

    monkeypatch.setattr(subprocess, "Popen", popen)
    assert volume.export_store(metadata, output)["export_verified"]
    assert (output / "result.json").read_bytes() == b"{}"
    (output / "result.json").unlink()
    raw = archive([("result.json", tarfile.REGTYPE, b"{}"), ("evil.bin", tarfile.REGTYPE, b"x")])
    with pytest.raises(volume.ArtifactStoreError):
        volume.export_store(metadata, output)
    assert list(output.iterdir()) == []
    assert not list(output.parent.glob(".artifact-export-*"))
