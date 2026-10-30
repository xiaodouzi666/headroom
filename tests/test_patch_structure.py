"""Regression for losing the outer update loop while introducing microbatches."""

from headroom.patch_spans import source_span_document
from headroom.patch_structure import step_call_enclosures


def test_optimizer_step_has_outer_update_anchor_not_inner_microbatch(tmp_path):
    p = tmp_path / "train.py"
    p.write_text(
        "for step in range(20):\n    optimizer.zero_grad()\n    for chunk in inputs.chunk(4):\n        loss(chunk).backward()\n    optimizer.step()\n    emit(step)\n"
    )
    doc = source_span_document(tmp_path, "train.py")
    anchors = step_call_enclosures({"train.py": doc})
    assert len(anchors) == 1
    anchor = anchors[0]
    assert anchor["source_sha256"] == doc["source_sha256"]
    assert anchor["enclosing_loops"] == [
        {"start_id": "L000001", "end_id": "L000006", "kind": "For"}
    ]
    assert anchor["step_call_id"] == "L000005"
    assert anchor["syntactic_only"] is True


def test_defined_but_not_called_function_does_not_borrow_outer_loop(tmp_path):
    p = tmp_path / "train.py"
    p.write_text(
        "for step in range(20):\n    def later():\n        optimizer.step()\n    callback = later\n"
    )
    assert step_call_enclosures({"train.py": source_span_document(tmp_path, "train.py")}) == []


def test_deep_ast_drops_partial_file_metadata(tmp_path):
    p = tmp_path / "train.py"
    p.write_text("for i in range(20):\n    optimizer.step()\nx = " + "+".join(["a"] * 1500) + "\n")
    assert step_call_enclosures({"train.py": source_span_document(tmp_path, "train.py")}) == []


def test_anchor_count_is_bounded(tmp_path):
    p = tmp_path / "train.py"
    p.write_text("for i in range(20):\n" + "    optimizer.step()\n" * 30)
    assert len(step_call_enclosures({"train.py": source_span_document(tmp_path, "train.py")})) == 12
