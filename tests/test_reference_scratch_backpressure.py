"""Completed replies must not make sequential clients hit the concurrency gate."""

import concurrent.futures
import threading
import time
from types import SimpleNamespace

from headroom.lab import reference_scratch as scratch


def test_reply_cleanup_overlap_queues_next_request_without_reset(tmp_path, monkeypatch):
    monkeypatch.setattr(scratch.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12))
    broker = scratch.ReferenceScratchBroker(tmp_path / "owned", 128).start()
    release_workers = threading.Event()
    both_blocked = threading.Event()
    lock = threading.Lock()
    blocked = 0
    real_release = broker._slots.release

    def delayed_worker_release():
        nonlocal blocked
        if threading.current_thread() is not broker._thread:
            with lock:
                blocked += 1
                if blocked >= 2:
                    both_blocked.set()
            assert release_workers.wait(3)
        real_release()

    monkeypatch.setattr(broker._slots, "release", delayed_worker_release)
    client = scratch.ReferenceScratchClient(broker.socket_path, 128)
    try:
        # Both successful replies arrive before their worker cleanup gives back
        # the slot. This is a legal sequential client, not a third active RPC.
        client.create()
        client.create()
        assert both_blocked.wait(1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(client.create)
            try:
                time.sleep(0.1)
                assert not future.done(), "next sequential request was reset instead of queued"
            finally:
                release_workers.set()
            assert len(future.result(timeout=2)) == 32
    finally:
        release_workers.set()
        broker.close()
    evidence = broker.evidence()
    assert evidence["cleanup_verified"] is True
    assert evidence["requests"] == 3
    assert evidence["failed_operations"] == 0
    assert evidence["live_objects"] == evidence["live_reserved_bytes"] == 0
