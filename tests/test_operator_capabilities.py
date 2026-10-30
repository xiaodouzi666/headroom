"""Owned optional metadata reaches both real SDK request builders without granting a repair."""

import builtins
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from test_diagnosis_bounded_repair import evidence, payload, provider_client
from test_orchestrator import search_run

from headroom import operator_capabilities as capabilities
from headroom.diagnose import diagnose_with_router, validate_diagnosis
from headroom.diagnosis_protocol import FINAL48_DIAGNOSIS_ONLY
from headroom.llm.router import LLMRouter
from headroom.solver_context import MAX_SOLVER_CONTEXT_BYTES, solver_prompt_context
from headroom.verify.policy import check_source_changes


def test_catalog_binds_only_the_exact_owned_module_and_not_target_applicability():
    catalog = capabilities.runtime_operator_catalog()
    assert catalog["status"] == "owned_source_verified"
    assert catalog["current_target_applicability"] == "unverified"
    assert catalog["current_runtime_availability"] == "unverified"
    assert len(json.dumps(catalog, ensure_ascii=True).encode()) <= capabilities.MAX_CATALOG_BYTES
    operator = catalog["operators"][0]
    source = Path(capabilities.__file__).parent / "optim/in_backward_adamw.py"
    assert operator["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert operator["python_import"] == (
        "from headroom.optim.in_backward_adamw import AdamWInBackward"
    )
    assert "external" in json.dumps(catalog["runtime_scope"]).lower()
    text = json.dumps(catalog)
    for required in (
        "2.5.1",
        "FP32",
        "AdamW",
        "clipping",
        "GradScaler",
        "distributed",
        "source contract",
    ):
        assert required in text
    for historical in ("s7_", "control-20261025", "22.601", "13.792", "target_met"):
        assert historical not in text
    # A consumer cannot mutate the next request's metadata.
    operator["requires"].clear()
    assert capabilities.runtime_operator_catalog()["operators"][0]["requires"]


def test_metadata_does_not_read_environment_or_import_optimizer_code(monkeypatch):
    original_import = builtins.__import__

    def no_torch(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise AssertionError("metadata must not import the optimizer or torch")
        return original_import(name, *args, **kwargs)

    class NoEnvironment(dict):
        def __getitem__(self, key):
            raise AssertionError("metadata must not read environment")

        def get(self, *args):
            raise AssertionError("metadata must not read environment")

        def __iter__(self):
            raise AssertionError("metadata must not enumerate environment")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", no_torch)
        patch.setattr(os, "environ", NoEnvironment())
        patch.setattr(os, "getenv", lambda *args: pytest.fail("environment lookup"))
        catalog = capabilities.runtime_operator_catalog()
    assert catalog["status"] == "owned_source_verified"


@pytest.mark.parametrize("kind", ["file_link", "directory_link", "changed", "missing", "fifo"])
def test_unverified_or_unsafe_owned_source_does_not_advertise_an_operator(
    tmp_path, monkeypatch, kind
):
    original = Path(capabilities.__file__).parent / "optim/in_backward_adamw.py"
    source = original.read_bytes()
    root = tmp_path / "package"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "in_backward_adamw.py").write_bytes(source)
    if kind == "directory_link":
        (root / "optim").symlink_to(outside, target_is_directory=True)
    else:
        (root / "optim").mkdir()
        target = root / "optim/in_backward_adamw.py"
        if kind == "file_link":
            target.symlink_to(outside / "in_backward_adamw.py")
        elif kind == "changed":
            target.write_bytes(source + b"\n# DIFFERENT_SOURCE_MUST_NOT_LEAK\n")
        elif kind == "fifo":
            os.mkfifo(target)
    monkeypatch.setattr(capabilities, "_PACKAGE_ROOT", root)
    catalog = capabilities.runtime_operator_catalog()
    assert catalog["status"] == "unavailable_or_unverified"
    assert catalog["operators"] == []
    assert "DIFFERENT_SOURCE_MUST_NOT_LEAK" not in json.dumps(catalog)
    assert str(outside) not in json.dumps(catalog)


def test_owned_source_reader_stays_bounded(monkeypatch):
    monkeypatch.setattr(capabilities, "MAX_OPERATOR_SOURCE_BYTES", 8)
    assert capabilities.runtime_operator_catalog()["operators"] == []


def test_bounded_ultra_sdk_request_receives_catalog_without_extra_call_or_cap():
    requests = []
    source = evidence()
    before = copy.deepcopy(source)
    with provider_client([payload()], requests) as client:
        result = diagnose_with_router(
            LLMRouter(client),
            "Measured source and stacks",
            evidence=source,
            goal="reclaim",
            policy={},
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )
    assert result.ready_for_patch
    assert len(requests) == 1
    assert requests[0]["max_tokens"] == 2000
    assert requests[0]["chat_template_kwargs"] == {"enable_thinking": False}
    received = json.loads(requests[0]["messages"][-1]["content"])
    assert received["runtime_operator_catalog"] == capabilities.runtime_operator_catalog()
    assert source == before
    assert requests[0].get("tools") is None


def test_both_real_sdk_request_paths_receive_the_same_optional_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "ENV_SECRET_CATALOG_TEST")
    result, store, calls, _, _ = search_run(
        tmp_path,
        [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 20, "target": True}],
    )
    try:
        assert result["target_met"]
        assert len(calls) == 2
        ultra = json.loads(calls[0]["messages"][-1]["content"])
        patch = json.loads(calls[1]["messages"][-1]["content"])
        assert (
            ultra["runtime_operator_catalog"]
            == patch["evidence_context"]["runtime_operator_catalog"]
            == capabilities.runtime_operator_catalog()
        )
        assert calls[0].get("tools") is None and calls[1].get("tools") is None
        assert "ENV_SECRET_CATALOG_TEST" not in json.dumps(calls)
        # This unrelated fixture repair remains unrelated: the host did not substitute an optimizer.
        assert "AdamWInBackward" not in patch["plan_step"]["description"]
    finally:
        store.close()


def test_operator_metadata_does_not_clear_missing_preconditions_or_precision_policy():
    source = evidence()
    source["runtime_operator_catalog"] = capabilities.runtime_operator_catalog()
    answer = payload()
    answer["needs_more_info"] = True
    answer["evidence_requests"] = [
        {
            "field": "optimizer.gradient_clipping",
            "reason": "ambiguous",
            "detail": "The actual global-gradient operations remain unknown.",
            "blocking_scope": "current_plan",
            "blocked_plan_ids": ["fix"],
        }
    ]
    checked = validate_diagnosis(answer, evidence=source, policy={})
    assert checked.valid and not checked.ready_for_patch
    assert checked.diagnosis.needs_more_info
    answer = payload()
    answer["plan"][0]["description"] = "Switch source computation to bf16."
    checked = validate_diagnosis(answer, evidence=source, policy={})
    assert not checked.ready_for_patch
    assert "NUMERICS_CHANGE_FORBIDDEN" in {issue.code for issue in checked.issues}


def test_external_runtime_and_non_adamw_are_never_automatically_certified():
    context = solver_prompt_context(
        execution_context={
            "runtime": "user_owned_external_gpu",
            "optimizer": "SGD",
            "gradient_clipping": 1.0,
        }
    )
    catalog = context["runtime_operator_catalog"]
    assert catalog["current_target_applicability"] == "unverified"
    assert catalog["current_runtime_availability"] == "unverified"
    assert "Not a conversion of SGD" in catalog["operators"][0]["limits"]


def test_catalog_is_inside_the_same_wire_bound_and_paired_history_trimming():
    catalog = capabilities.runtime_operator_catalog()
    result = solver_prompt_context(
        execution_context={"script": "entry.py"},
        candidate_evidence=[{"round": i, "notes": "x" * 9000} for i in range(1, 7)],
        verification_feedback=[{"round": i, "notes": ["y" * 5000]} for i in range(1, 7)],
    )
    assert result["runtime_operator_catalog"] == catalog
    assert len(json.dumps(result, ensure_ascii=True).encode()) <= MAX_SOLVER_CONTEXT_BYTES
    availability = result["solver_context_availability"]
    assert not availability["complete"]
    assert (
        availability["omitted_unknown"]["candidate_rounds"]
        == availability["omitted_unknown"]["verification_rounds"]
    )


def test_generic_integration_uses_existing_patch_policy_and_still_needs_runtime_checks():
    before = (
        "import torch\n"
        "model = torch.nn.Linear(2, 2)\n"
        "optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, foreach=False)\n"
        "optimizer.zero_grad(set_to_none=True)\n"
        "loss = model(torch.ones(2, 2)).square().mean()\n"
        "loss.backward()\n"
        "optimizer.step()\n"
    )
    after = "from headroom.optim.in_backward_adamw import AdamWInBackward\n" + before.replace(
        "torch.optim.AdamW(", "AdamWInBackward("
    )
    checked = check_source_changes({"train.py": before}, {"train.py": after})
    assert checked.allowed
    assert checked.requires_runtime_verification
    assert capabilities.runtime_operator_catalog()["current_target_applicability"] == "unverified"
