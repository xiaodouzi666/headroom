"""Isolated offline R5 regressions; no tests were run during the R4 freeze.

All runtime fixtures use
temporary profiles, credentials, Store and ledger; no production env/profile/DB.
"""

import hashlib
import json
import socket
from dataclasses import replace

import httpx
import pytest
from patch_fixture_helpers import anchored_fixture
from test_llm_client import completion
from test_patch import proposal

from headroom.config import SUPER_MODEL, RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.llm.client import (
    CapabilityNotVerified,
    LLMError,
    TokenFactoryClient,
    low_effort_probe_fingerprint,
)
from headroom.llm.router import LLMRouter
from headroom.patch import PatchEngine
from headroom.patch_spans import SourceSpanProposal


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("External network is forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def config(*, reviewed=False):
    caps = {
        "json_method": "json_schema",
        "reasoning_method": "chat_template_kwargs",
        "evidence": "offline baseline capability fixture",
    }
    if reviewed:
        caps.update(
            low_effort_method="chat_template_kwargs",
            low_effort_evidence="offline receipt fixture",
            low_effort_evidence_sha256="a" * 64,
        )
    models = candidate_models()
    models["super"] = replace(
        models["super"],
        output_cap_field="max_completion_tokens",
        evidence="offline cap fixture",
        capabilities=VerifiedCapabilities(**caps),
    )
    return RuntimeConfig(models=models)


MESSAGES = [{"role": "user", "content": "Return the source edit"}]


def sdk_body():
    schema = SourceSpanProposal.model_json_schema()
    return {
        "model": SUPER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON matching this schema, without markdown or commentary.\n"
                + json.dumps(schema, ensure_ascii=False, allow_nan=False),
            },
            *MESSAGES,
        ],
        "max_completion_tokens": 4000,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "headroom_response", "schema": schema},
        },
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True, "low_effort": True}},
    }


def valid_empty():
    return {"edits": [], "env_changes": {}, "cli_changes": [], "notes": []}


@pytest.mark.parametrize("bad", [0, 1, None, "true", {}, []])
def test_low_effort_flag_is_strict_boolean_before_network(bad):
    calls = []
    with (
        TokenFactoryClient(
            config=config(reviewed=True),
            transport=httpx.MockTransport(lambda r: calls.append(r)),
        ) as client,
        pytest.raises(ValueError, match="boolean"),
    ):
        client.complete("patcher", MESSAGES, reasoning=True, low_effort=bad)
    assert not calls


@pytest.mark.parametrize("bad", [True, -1, 6, 0.0, "0"])
def test_retry_limit_is_bounded_strict_integer(bad):
    with pytest.raises(ValueError):
        TokenFactoryClient(max_http_retries=bad)


@pytest.mark.parametrize(
    "override",
    [
        {"low_effort_evidence": None},
        {"low_effort_evidence_sha256": None},
        {"low_effort_evidence_sha256": "not-sha"},
        {"reasoning_method": "system_prefix"},
        {"json_method": "text"},
    ],
)
def test_low_effort_needs_independent_combination_evidence(override):
    caps = {
        "json_method": "json_schema",
        "reasoning_method": "chat_template_kwargs",
        "evidence": "old baseline",
        "low_effort_method": "chat_template_kwargs",
        "low_effort_evidence": "new receipt",
        "low_effort_evidence_sha256": "b" * 64,
    }
    caps.update(override)
    with pytest.raises(ValueError):
        VerifiedCapabilities(**caps)


def test_combination_is_not_portable_to_unreviewed_model():
    super_spec = config(reviewed=True).models["super"]
    with pytest.raises(ValueError, match="specific to Super"):
        replace(super_spec, model_id="nvidia/not-reviewed")


def test_old_profile_keeps_exact_off_wire_without_new_field():
    seen = []

    def reply(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=completion(json.dumps(valid_empty())))

    with TokenFactoryClient(config=config(), transport=httpx.MockTransport(reply)) as client:
        LLMRouter(client).chat("patcher", MESSAGES, SourceSpanProposal, reasoning=False)
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen[0]["max_completion_tokens"] == 4000


def test_reviewed_combination_is_merged_into_same_wire_dictionary():
    seen = []

    def reply(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=completion(json.dumps(valid_empty())))

    with TokenFactoryClient(
        config=config(reviewed=True), transport=httpx.MockTransport(reply)
    ) as client:
        LLMRouter(client).chat(
            "patcher", MESSAGES, SourceSpanProposal, reasoning=True, low_effort=True
        )
        assert client._sdk.max_retries == 0
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": True, "low_effort": True}
    assert "extra_body" not in seen[0]
    assert seen[0]["response_format"]["type"] == "json_schema"


def test_normal_client_cannot_request_unreviewed_low_effort():
    with (
        TokenFactoryClient(
            config=config(), transport=httpx.MockTransport(lambda _: None)
        ) as client,
        pytest.raises(CapabilityNotVerified, match="no saved probe"),
    ):
        client.complete("patcher", MESSAGES, reasoning=True, low_effort=True)


@pytest.mark.parametrize("reasoning", [False, None])
def test_low_effort_requires_explicit_thinking(reasoning):
    with (
        TokenFactoryClient(
            config=config(reviewed=True), transport=httpx.MockTransport(lambda _: None)
        ) as client,
        pytest.raises(CapabilityNotVerified),
    ):
        client.complete("patcher", MESSAGES, reasoning=reasoning, low_effort=True)


def test_frozen_probe_does_not_forge_capability_and_cannot_dispatch_twice():
    seen = []

    def reply(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=completion(json.dumps(valid_empty())))

    unchanged = config()
    with TokenFactoryClient(
        config=unchanged,
        transport=httpx.MockTransport(reply),
        max_http_retries=0,
        low_effort_probe_request_sha256=low_effort_probe_fingerprint(sdk_body()),
    ) as client:
        router = LLMRouter(client)
        router.chat("patcher", MESSAGES, SourceSpanProposal, reasoning=True, low_effort=True)
        with pytest.raises(CapabilityNotVerified, match="one-shot frozen"):
            router.chat("patcher", MESSAGES, SourceSpanProposal, reasoning=True, low_effort=True)
    assert len(seen) == 1
    assert low_effort_probe_fingerprint(seen[0]) == low_effort_probe_fingerprint(sdk_body())
    assert unchanged.models["super"].capabilities.low_effort_method is None


def test_frozen_request_hash_rejects_changed_prompt_before_dispatch():
    seen = []
    with (
        TokenFactoryClient(
            config=config(),
            transport=httpx.MockTransport(lambda r: seen.append(r)),
            max_http_retries=0,
            low_effort_probe_request_sha256=low_effort_probe_fingerprint(sdk_body()),
        ) as client,
        pytest.raises(CapabilityNotVerified, match="differs"),
    ):
        LLMRouter(client).chat(
            "patcher",
            [{"role": "user", "content": "Different request"}],
            SourceSpanProposal,
            reasoning=True,
            low_effort=True,
        )
    assert not seen


@pytest.mark.parametrize("status", [429, 500, 529])
def test_one_shot_disables_both_retry_layers_and_retains_unknown_cost(status):
    seen, sleeps = [], []

    def reply(req):
        seen.append(req)
        return httpx.Response(status, json={"error": "not printed"})

    with TokenFactoryClient(
        config=config(),
        transport=httpx.MockTransport(reply),
        sleep=sleeps.append,
        max_http_retries=0,
        low_effort_probe_request_sha256=low_effort_probe_fingerprint(sdk_body()),
    ) as client:
        with pytest.raises(LLMError, match="attempts=1"):
            LLMRouter(client).chat(
                "patcher",
                MESSAGES,
                SourceSpanProposal,
                reasoning=True,
                low_effort=True,
            )
        assert client._sdk.max_retries == 0
        assert len(client.ledger.entries) == 1
        assert client.ledger.entries[0].cost.usd is None
    assert len(seen) == 1 and sleeps == []


def test_probe_permit_cannot_coexist_with_client_retries():
    with pytest.raises(ValueError, match="one request"):
        TokenFactoryClient(low_effort_probe_request_sha256="c" * 64)


def run_patch(tmp_path, modes, *, reviewed=True, max_repairs=3):
    source = tmp_path / "source"
    source.mkdir()
    before = "x = 1\n"
    (source / "train.py").write_text(before)
    seen = []

    def reply(req):
        body = json.loads(req.content)
        seen.append(body)
        mode = modes[min(len(seen) - 1, len(modes) - 1)]
        text = json.dumps(anchored_fixture(proposal(before, "x = 2\n"), body))
        finish = "stop"
        if mode == "length":
            finish = "length"  # Even parseable JSON must not be salvaged.
        elif mode == "empty":
            text = ""
        elif mode == "invalid":
            text = '{"edits": ['
        elif mode == "schema":
            text = "{}"
        payload = completion(text, finish=finish)
        payload["usage"]["completion_tokens_details"] = {"reasoning_tokens": 10}
        return httpx.Response(200, json=payload)

    with TokenFactoryClient(
        config=config(reviewed=reviewed), transport=httpx.MockTransport(reply)
    ) as client:
        result = PatchEngine(LLMRouter(client), max_repairs=max_repairs).generate_and_apply(
            source,
            {"fix_id": "generic-offline"},
            work_root=tmp_path / "work",
        )
    return result, seen


@pytest.mark.parametrize("bad_output", ["length", "empty", "invalid", "schema"])
def test_patch_falls_back_inside_existing_attempts(tmp_path, bad_output):
    result, seen = run_patch(tmp_path, [bad_output, "good"])
    assert result.applied and len(result.attempts) == len(seen) == 2
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": True, "low_effort": True}
    assert seen[1]["chat_template_kwargs"] == {"enable_thinking": False}
    assert all(x["max_completion_tokens"] == 4000 for x in seen)


def test_four_attempt_limit_survives_repeated_bad_output(tmp_path):
    result, seen = run_patch(tmp_path, ["length"])
    assert not result.applied and len(result.attempts) == len(seen) == 4
    assert all(x["chat_template_kwargs"] == {"enable_thinking": False} for x in seen[1:])


def test_no_remaining_attempt_means_no_extra_fallback_call(tmp_path):
    result, seen = run_patch(tmp_path, ["length"], max_repairs=0)
    assert not result.applied and len(result.attempts) == len(seen) == 1


def test_no_new_capability_preserves_current_patch_path(tmp_path):
    result, seen = run_patch(tmp_path, ["good"], reviewed=False)
    assert result.applied and len(seen) == 1
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": False}


def probe_fixture(tmp_path):
    """Build only temporary fixture state; no production paths are writable."""
    from test_client_acceptance import runtime_fixture

    from headroom.acceptance.super_low_effort import prepare_low_effort_probe

    root = tmp_path / "project"
    profile_path, env = runtime_fixture(root, prompt_ceiling=262144, authorized="2")
    profile = json.loads(profile_path.read_text())
    super_model = profile["models"]["super"]
    super_model.update(
        input_usd_per_million="0.3",
        output_usd_per_million="0.9",
        capabilities={
            "json_method": "json_schema",
            "reasoning_method": "chat_template_kwargs",
            "evidence": "offline baseline capability",
        },
    )
    super_model["billing"].update(
        max_completion_tokens=4000,
        output_cap_field="max_completion_tokens",
    )
    profile_path.write_text(json.dumps(profile))
    prepared = tmp_path / "prepared"
    prepare_low_effort_probe(prepared, profile_path, daily_limit_usd="2")
    frozen = json.loads((prepared / "freeze-template.json").read_text())
    frozen.update(
        reviewed=True, r4_terminal=True, source_revision="offline-only", reviewer="fixture"
    )
    freeze_path = prepared / "root-freeze.json"
    freeze_path.write_text(json.dumps(frozen))
    freeze_hash = hashlib.sha256(freeze_path.read_bytes()).hexdigest()
    return root, profile_path, env, prepared, freeze_path, freeze_hash


def probe_completion(req, *, reasoning=20):
    body = json.loads(req.content)
    context = json.loads(body["messages"][-1]["content"])
    doc = context["sources"]["example.py"]
    payload = valid_empty()
    payload["edits"] = [
        {
            "path": "example.py",
            "source_sha256": doc["source_sha256"],
            "start_id": doc["lines"][1]["id"],
            "end_id": doc["lines"][1]["id"],
            "new_lines": ["    if not values:", "        return 0.0", "    total = 0.0"],
        }
    ]
    response = completion(json.dumps(payload))
    response["usage"] = {
        "prompt_tokens": 100,
        "completion_tokens": 200,
        "total_tokens": 300,
        "prompt_tokens_details": {"cached_tokens": 0},
        "completion_tokens_details": {"reasoning_tokens": reasoning},
    }
    return httpx.Response(200, json=response)


def test_probe_uses_existing_ledger_and_promotion_remains_manual(tmp_path, monkeypatch):
    from headroom.acceptance.super_low_effort import execute_low_effort_probe
    from headroom.runtime import _verify_low_effort_evidence, read_live_profile

    root, profile_path, env, prepared, freeze, digest = probe_fixture(tmp_path)
    seen = []

    def reply(req):
        seen.append(req)
        return probe_completion(req)

    artifact = tmp_path / "probe-result"
    report = execute_low_effort_probe(
        prepared,
        freeze,
        artifact,
        expected_freeze_sha256=digest,
        execute=True,
        live_authorized=True,
        project_root=root,
        env_file=env,
        transport=httpx.MockTransport(reply),
    )
    assert len(seen) == 1 and report["accepted"]
    assert report["server_recognition_verified"] is False
    assert report["relative_reasoning_reduction_verified"] is False
    assert report["auto_promoted"] is False
    original = read_live_profile(profile_path)
    assert original.models["super"].capabilities.get("low_effort_method") is None
    receipt = artifact / "capability-report.json"
    receipt_hash = hashlib.sha256(receipt.read_bytes()).hexdigest()
    candidate = original.model_copy(deep=True)
    candidate.models["super"].capabilities.update(
        low_effort_method="chat_template_kwargs",
        low_effort_evidence=str(receipt),
        low_effort_evidence_sha256=receipt_hash,
    )
    candidate.runtime_config()
    monkeypatch.setattr("headroom.runtime.PROJECT_ROOT", tmp_path)
    assert report["provenance"] == "offline_fixture"
    assert report["ledger_path"] == ".cache/budget.db"
    assert report["store_path"] == "runs/acceptance/headroom.db"
    assert len(report["budget_attempt_id"]) == 32
    with pytest.raises(Exception, match="reviewed request combination"):
        _verify_low_effort_evidence(candidate)
    receipt.write_text(receipt.read_text() + " ")
    with pytest.raises(Exception, match="hash differs"):
        _verify_low_effort_evidence(candidate)


@pytest.mark.parametrize("reasoning", [0, None])
def test_200_without_positive_reasoning_is_not_promoted(tmp_path, reasoning):
    from headroom.acceptance.super_low_effort import execute_low_effort_probe

    root, _, env, prepared, freeze, digest = probe_fixture(tmp_path)
    artifact = tmp_path / "probe-result"
    with pytest.raises(ValueError, match="required complete"):
        execute_low_effort_probe(
            prepared,
            freeze,
            artifact,
            expected_freeze_sha256=digest,
            execute=True,
            live_authorized=True,
            project_root=root,
            env_file=env,
            transport=httpx.MockTransport(lambda req: probe_completion(req, reasoning=reasoning)),
        )
    report = json.loads((artifact / "capability-report.json").read_text())
    assert report["accepted"] is False


def test_unknown_http_charge_is_retained_and_no_second_dispatch(tmp_path):
    from headroom.acceptance.super_low_effort import execute_low_effort_probe

    root, _, env, prepared, freeze, digest = probe_fixture(tmp_path)
    artifact = tmp_path / "probe-result"
    seen = []

    def reply(req):
        seen.append(req)
        return httpx.Response(529, json={"error": "offline unavailable"})

    with pytest.raises(LLMError, match="HTTP 529"):
        execute_low_effort_probe(
            prepared,
            freeze,
            artifact,
            expected_freeze_sha256=digest,
            execute=True,
            live_authorized=True,
            project_root=root,
            env_file=env,
            transport=httpx.MockTransport(reply),
        )
    runtime = json.loads((artifact / "runtime.json").read_text())
    assert len(seen) == len(runtime["calls"]) == 1
    assert runtime["calls"][0]["cost_usd"] is None
    assert runtime["calls"][0]["reservation_usd"] == "0.0822432"
    assert runtime["calls"][0]["billing_status"] == "unresolved"


def test_unreviewed_freeze_template_cannot_open_runtime(tmp_path):
    from headroom.acceptance.super_low_effort import execute_low_effort_probe

    root, _, env, prepared, _, _ = probe_fixture(tmp_path)
    freeze = prepared / "freeze-template.json"
    digest = hashlib.sha256(freeze.read_bytes()).hexdigest()
    artifact = tmp_path / "probe-result"
    with pytest.raises(ValueError, match="freeze receipt"):
        execute_low_effort_probe(
            prepared,
            freeze,
            artifact,
            expected_freeze_sha256=digest,
            execute=True,
            live_authorized=True,
            project_root=root,
            env_file=env,
            transport=httpx.MockTransport(lambda _: None),
        )
    assert not artifact.exists()


def receipt_fixture(tmp_path, monkeypatch):
    from test_client_acceptance import runtime_fixture

    from headroom import runtime

    project = tmp_path / "project"
    profile_path, _ = runtime_fixture(project)
    profile = runtime.read_live_profile(profile_path)
    report = {
        "scope": "super_low_effort_schema_code_probe_v1",
        "provenance": "live",  # Synthetic metadata fixture, not a live call.
        "accepted": True,
        "verdict": "request_combination_usable_in_one_sample",
        "finish_reason": "stop",
        "response_model": profile.models["super"].model_id,
        "base_url": profile.base_url,
        "profile_model_compatibility": profile.models["super"].model_dump(exclude={"capabilities"}),
        "reasoning_tokens": 10,
        "completion_tokens": 100,
    }
    receipt = project / "reports" / "receipt.json"
    receipt.parent.mkdir()
    receipt.write_text(json.dumps(report))
    profile.models["super"].capabilities.update(
        json_method="json_schema",
        reasoning_method="chat_template_kwargs",
        evidence="offline baseline capability",
        low_effort_method="chat_template_kwargs",
        low_effort_evidence=str(receipt),
        low_effort_evidence_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(runtime, "PROJECT_ROOT", project)
    return runtime, project, profile, receipt


@pytest.mark.parametrize("absolute", [False, True])
def test_receipt_accepts_only_paths_beneath_project(tmp_path, monkeypatch, absolute):
    runtime, project, profile, receipt = receipt_fixture(tmp_path, monkeypatch)
    if not absolute:
        profile.models["super"].capabilities["low_effort_evidence"] = str(
            receipt.relative_to(project)
        )
    runtime._verify_low_effort_evidence(profile)


def test_receipt_rejects_outside_absolute_path_even_with_correct_hash(tmp_path, monkeypatch):
    runtime, _, profile, receipt = receipt_fixture(tmp_path, monkeypatch)
    outside = tmp_path / "outside.json"
    outside.write_bytes(receipt.read_bytes())
    profile.models["super"].capabilities["low_effort_evidence"] = str(outside)
    with pytest.raises(Exception, match="within the project"):
        runtime._verify_low_effort_evidence(profile)


def test_receipt_rejects_parent_traversal(tmp_path, monkeypatch):
    runtime, _, profile, _ = receipt_fixture(tmp_path, monkeypatch)
    profile.models["super"].capabilities["low_effort_evidence"] = "../outside.json"
    with pytest.raises(Exception, match="within the project"):
        runtime._verify_low_effort_evidence(profile)


@pytest.mark.parametrize("directory", [False, True])
def test_receipt_rejects_symlink_leaf_and_parent(tmp_path, monkeypatch, directory):
    runtime, project, profile, receipt = receipt_fixture(tmp_path, monkeypatch)
    if directory:
        link = project / "linked-reports"
        link.symlink_to(receipt.parent, target_is_directory=True)
        target = link / receipt.name
    else:
        target = project / "linked.json"
        target.symlink_to(receipt)
    profile.models["super"].capabilities["low_effort_evidence"] = str(target)
    with pytest.raises((OSError, ValueError)):
        runtime._verify_low_effort_evidence(profile)


def test_old_profile_bytes_dict_and_financial_bound_do_not_drift(tmp_path):
    from test_client_acceptance import runtime_fixture

    from headroom.runtime import read_live_profile

    path, _ = runtime_fixture(tmp_path / "project", prompt_ceiling=262144)
    before_bytes = path.read_bytes()
    before_json = json.loads(before_bytes)
    profile = read_live_profile(path)
    before_model = profile.model_dump()
    config = profile.runtime_config()
    body = {"model": SUPER_MODEL, "messages": MESSAGES, "max_tokens": 400}
    before_bound = profile.models["super"].billing.upper_usd(config.model_for("patcher"), body)
    after = read_live_profile(path)
    after_config = after.runtime_config()
    after_bound = after.models["super"].billing.upper_usd(after_config.model_for("patcher"), body)
    assert path.read_bytes() == before_bytes
    assert json.loads(path.read_bytes()) == before_json
    assert profile.model_dump() == after.model_dump() == before_model
    assert "low_effort_method" not in before_model["models"]["super"]["capabilities"]
    assert before_bound == after_bound
    assert after_config.model_for("patcher").capabilities.low_effort_method is None


@pytest.mark.parametrize("changed_field", ["schema", "schema_system_message"])
def test_frozen_probe_binds_router_schema_and_injected_system_message(changed_field):
    frozen = sdk_body()
    if changed_field == "schema":
        frozen["response_format"]["json_schema"]["schema"]["description"] = "different schema"
    else:
        frozen["messages"][0]["content"] += "\nExtra injected instruction"
    seen = []
    with (
        TokenFactoryClient(
            config=config(),
            transport=httpx.MockTransport(lambda r: seen.append(r)),
            max_http_retries=0,
            low_effort_probe_request_sha256=low_effort_probe_fingerprint(frozen),
        ) as client,
        pytest.raises(CapabilityNotVerified, match="differs"),
    ):
        LLMRouter(client).chat(
            "patcher",
            MESSAGES,
            SourceSpanProposal,
            reasoning=True,
            low_effort=True,
        )
    assert not seen


def test_restarting_probe_with_new_artifact_directory_cannot_resend(tmp_path):
    from headroom.acceptance.super_low_effort import execute_low_effort_probe

    root, _, env, prepared, freeze, digest = probe_fixture(tmp_path)
    seen = []

    def reply(req):
        seen.append(req)
        return probe_completion(req)

    args = {
        "expected_freeze_sha256": digest,
        "execute": True,
        "live_authorized": True,
        "project_root": root,
        "env_file": env,
        "transport": httpx.MockTransport(reply),
    }
    execute_low_effort_probe(prepared, freeze, tmp_path / "result-one", **args)
    with pytest.raises(ValueError, match="already claimed"):
        execute_low_effort_probe(prepared, freeze, tmp_path / "result-two", **args)
    assert len(seen) == 1
    assert (prepared / ".dispatch-claim.json").is_file()


def test_copied_prepared_directory_cannot_reuse_frozen_probe(tmp_path):
    import shutil

    from headroom.acceptance.super_low_effort import execute_low_effort_probe

    root, _, env, prepared, freeze, digest = probe_fixture(tmp_path)
    copied = tmp_path / "copied"
    shutil.copytree(prepared, copied)
    with pytest.raises(ValueError, match="freeze receipt"):
        execute_low_effort_probe(
            copied,
            freeze,
            tmp_path / "result",
            expected_freeze_sha256=digest,
            execute=True,
            live_authorized=True,
            project_root=root,
            env_file=env,
            transport=httpx.MockTransport(lambda _: None),
        )
    assert not (copied / ".dispatch-claim.json").exists()


def test_concurrent_probe_helpers_share_one_durable_claim(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from headroom.acceptance.super_low_effort import execute_low_effort_probe

    root, _, env, prepared, freeze, digest = probe_fixture(tmp_path)
    seen = []

    def reply(req):
        seen.append(req)
        return probe_completion(req)

    def attempt(index):
        try:
            return execute_low_effort_probe(
                prepared,
                freeze,
                tmp_path / ("result-" + str(index)),
                expected_freeze_sha256=digest,
                execute=True,
                live_authorized=True,
                project_root=root,
                env_file=env,
                transport=httpx.MockTransport(reply),
            )["accepted"]
        except ValueError as error:
            assert "already claimed" in str(error)
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, [1, 2]))
    assert sorted(results) == [False, True]
    assert len(seen) == 1


@pytest.mark.parametrize("provenance", ["offline_fixture", None, "LIVE", 1])
def test_nonlive_receipt_cannot_enable_live_capability(tmp_path, monkeypatch, provenance):
    from headroom.llm.admission import RuntimeNotReady

    runtime, _, profile, receipt = receipt_fixture(tmp_path, monkeypatch)
    report = json.loads(receipt.read_text())
    if provenance is None:
        report.pop("provenance")
    else:
        report["provenance"] = provenance
    receipt.write_text(json.dumps(report))
    profile.models["super"].capabilities["low_effort_evidence_sha256"] = hashlib.sha256(
        receipt.read_bytes()
    ).hexdigest()
    with pytest.raises(RuntimeNotReady, match="reviewed request combination"):
        runtime._verify_low_effort_evidence(profile)


def test_mock_probe_report_explicitly_retains_offline_provenance(tmp_path):
    from headroom.acceptance.super_low_effort import execute_low_effort_probe

    root, _, env, prepared, freeze, digest = probe_fixture(tmp_path)
    artifact = tmp_path / "offline-evidence"
    report = execute_low_effort_probe(
        prepared,
        freeze,
        artifact,
        expected_freeze_sha256=digest,
        execute=True,
        live_authorized=True,
        project_root=root,
        env_file=env,
        transport=httpx.MockTransport(probe_completion),
    )
    assert report["accepted"] is True
    assert report["provenance"] == "offline_fixture"
    assert (
        json.loads((artifact / "capability-report.json").read_text())["provenance"]
        == "offline_fixture"
    )
