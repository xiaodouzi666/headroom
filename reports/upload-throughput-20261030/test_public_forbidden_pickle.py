"""Exact benign public GLOBAL/REDUCE fixture: no callable is ever resolved."""

import pytest

from headroom import snapshot_input

RAW = b"cbuiltins\neval\n(V1+1\ntR."


def test_exact_public_fixture_is_rejected_at_opcode_before_unpickler(monkeypatch):
    assert len(RAW) == 24
    seen = []

    class NeverConstruct:
        def __init__(self, *_args, **_kwargs):
            seen.append(True)
            raise AssertionError("Opcode check must run before any unpickler")

    monkeypatch.setattr(snapshot_input, "_PrimitiveUnpickler", NeverConstruct)
    with pytest.raises(snapshot_input.SnapshotInputError, match="^pickle_opcode_forbidden$"):
        snapshot_input._decode_pickle(RAW)
    assert not seen
