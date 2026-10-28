"""Public-number checks must reject plausible but incorrectly attributed numbers."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "public_numbers", Path(__file__).parents[1] / "scripts/verify_public_numbers.py"
)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


@pytest.fixture
def recorded(tmp_path):
    raw = {
        "before": 10000000000,
        "after": 4000000000,
        "evidence": 268920,
        "probe": 500029,
        "targets": 2,
        "causes": 3,
        "best": 3,
        "historical": 5,
    }
    payload = json.dumps(raw).encode()
    (tmp_path / "raw.json").write_bytes(payload)
    sha = checker.digest(payload)
    document = {
        "schema": "headroom.final48h.numbers.v1",
        "claims": {},
        "source_excerpts": {"raw.json": {"sha256": sha, "fields": {}}},
        "historical_best": [
            {"scenario_id": "s3_eval_no_grad_missing", "campaign": "R6"},
            {"scenario_id": "s4_loss_accumulation_graph", "campaign": "R6"},
        ],
        "summary": {"latest_campaign": "R6", "fixed_denominator": 9},
    }

    def direct(name, key, unit=None):
        pointer = "/" + key
        document["source_excerpts"]["raw.json"]["fields"][pointer] = raw[key]
        document["claims"][name] = {
            "value": raw[key],
            "unit": unit,
            "source": {"path": "raw.json", "sha256": sha, "json_pointer": pointer},
        }

    for scenario in ("s3_eval_no_grad_missing", "s4_loss_accumulation_graph"):
        prefix = "R6." + scenario
        for side, expected in (("before", "10"), ("after", "4")):
            direct(f"{prefix}.{side}.bytes", side, "bytes")
            document["claims"][f"{prefix}.{side}.GB"] = {
                "value": expected,
                "unit": "GB",
                "inputs": [f"{prefix}.{side}.bytes"],
                "formula": "bytes / 1000000000",
            }
        document["claims"][f"best.{scenario}.reduction_pct"] = {
            "value": "60",
            "unit": "percent",
            "inputs": [prefix + ".before.bytes", prefix + ".after.bytes"],
            "formula": "(before_bytes-after_bytes)*100/before_bytes; OOM baseline is observed partial-run peak",
        }
    for name, key in {
        "long_context.real_evidence_provider_input_tokens": "evidence",
        "long_context.largest_successful_server_prompt_tokens": "probe",
        "R6.targets": "targets",
        "R6.valid_correct_first_causes": "causes",
        "summary.best_single_campaign_targets": "best",
        "summary.historical_target_scenario_count": "historical",
    }.items():
        direct(name, key)
    return tmp_path, document


def evidence(recorded, **options):
    root, document = recorded
    result = checker.Evidence(root, document, **options)
    for key in document["claims"]:
        result.value(key)
    return result


def test_source_values_and_calculated_metrics_accept_correct_bound_row(recorded):
    item = evidence(recorded)
    row = "| s3 | 10.00 GB → 4.00 GB (−60.0%) | <!-- numbers: best.s3_eval_no_grad_missing -->"
    claims = checker.verify_line(item, row)
    assert [c["claim"] for c in claims] == [
        "R6.s3_eval_no_grad_missing.before.GB",
        "R6.s3_eval_no_grad_missing.after.GB",
        "best.s3_eval_no_grad_missing.reduction_pct",
    ]
    assert item.levels == {"raw.json": "raw_sha256_and_json_pointer"}


@pytest.mark.parametrize(
    "row,reason",
    [
        ("s3 60.0% <!-- numbers: best.s4_loss_accumulation_graph -->", "Scenario label"),
        (
            "s3 4.00 GB → 10.00 GB <!-- numbers: best.s3_eval_no_grad_missing -->",
            "Unsupported numeric",
        ),
        (
            "s3 peak memory fell 61.0% <!-- numbers: best.s3_eval_no_grad_missing -->",
            "Unsupported numeric",
        ),
        ("s3 10.00 GB <!-- numbers: best.s3_eval_no_grad_missing -->", "Single peak"),
        ("s3 R5 60.0% <!-- numbers: best.s3_eval_no_grad_missing -->", "campaign differs"),
        ("s3 60.0%", "no number scope"),
        ("s3 60.0% <!-- numbers: best.unseen -->", "Unknown"),
        (
            "s3 60.0% <!-- numbers: best.s3_eval_no_grad_missing --> <!-- numbers: summary -->",
            "Multiple",
        ),
        ("s3 -10.00 GB → 4.00 GB <!-- numbers: best.s3_eval_no_grad_missing -->", "Negative"),
    ],
)
def test_wrong_number_or_binding_fails_even_when_another_claim_has_same_value(
    recorded, row, reason
):
    with pytest.raises(checker.VerificationError, match=reason):
        checker.verify_line(evidence(recorded), row)


def test_token_roles_cannot_be_swapped(recorded):
    valid = (
        "Ultra accepted 268,920 input tokens in authentic evidence and "
        "500,029 input tokens in a retrieval probe. <!-- numbers: long_context -->"
    )
    assert len(checker.verify_line(evidence(recorded), valid)) == 2
    for invalid in (
        valid.replace("268,920", "500,029"),
        valid.replace("500,029", "1M"),
        valid.replace("500,029", "1 million"),
        valid.replace("authentic evidence", "a retrieval probe"),
        valid + " Another request accepted 999,999 tokens.",
    ):
        with pytest.raises(checker.VerificationError):
            checker.verify_line(evidence(recorded), invalid)


def test_summary_fractions_use_semantics_instead_of_matching_any_count(recorded):
    valid = (
        "Across seven recorded campaigns, 5 of 9 distinct scenarios met targets. "
        "The best single campaign reached 3 of 9. The latest campaign reached 2 of 9, "
        "with 3 of 9 valid correct first-cause diagnoses. <!-- numbers: summary -->"
    )
    assert len(checker.verify_line(evidence(recorded), valid)) == 4
    for invalid in (
        valid.replace("latest campaign reached 2", "latest campaign reached 3"),
        valid.replace("5 of 9", "5 of 8"),
        valid.replace("valid correct first-cause diagnoses", "other measured results"),
    ):
        with pytest.raises(checker.VerificationError):
            checker.verify_line(evidence(recorded), invalid)


def test_raw_hash_mismatch_never_falls_back(recorded):
    root, _ = recorded
    (root / "raw.json").write_text('{"before": 1}')
    with pytest.raises(checker.VerificationError, match="SHA-256 mismatch"):
        evidence(recorded, allow_excerpts=True)


def test_missing_raw_requires_explicit_fallback_and_labels_it(recorded):
    root, _ = recorded
    (root / "raw.json").unlink()
    with pytest.raises(checker.VerificationError, match="Missing raw source"):
        evidence(recorded)
    portable = evidence(recorded, allow_excerpts=True)
    assert portable.levels == {"raw.json": "reviewed_excerpt_only"}
    assert portable.raw == {}


def test_claim_and_excerpt_tampering_do_not_match_existing_source(recorded):
    _, document = recorded
    document["claims"]["R6.targets"]["value"] = 3
    document["source_excerpts"]["raw.json"]["fields"]["/targets"] = 3
    with pytest.raises(checker.VerificationError, match="Excerpt value mismatch"):
        evidence(recorded)


def test_missing_json_pointer_is_not_treated_as_null(recorded):
    _, document = recorded
    claim = document["claims"]["R6.targets"]
    claim["source"]["json_pointer"] = "/missing"
    claim["value"] = None
    document["source_excerpts"]["raw.json"]["fields"]["/missing"] = None
    with pytest.raises(checker.VerificationError, match="Missing source JSON pointer"):
        evidence(recorded)


def test_derived_result_and_dependency_both_checked(recorded):
    _, document = recorded
    claim_name = "R6.s3_eval_no_grad_missing.before.GB"
    document["claims"][claim_name]["value"] = "11"
    with pytest.raises(checker.VerificationError, match="Derived value mismatch"):
        evidence(recorded)
    document["claims"][claim_name]["value"] = "4"
    document["claims"][claim_name]["inputs"] = ["R6.s3_eval_no_grad_missing.after.bytes"]
    with pytest.raises(checker.VerificationError, match="Wrong byte binding"):
        evidence(recorded)


def test_reduction_cannot_borrow_another_scenario_same_peak_values(recorded):
    _, document = recorded
    document["claims"]["best.s3_eval_no_grad_missing.reduction_pct"]["inputs"] = [
        "R6.s4_loss_accumulation_graph.before.bytes",
        "R6.s4_loss_accumulation_graph.after.bytes",
    ]
    with pytest.raises(checker.VerificationError, match="Wrong peak pair"):
        evidence(recorded)


def test_manifest_digest_rejects_joint_claim_and_excerpt_change(recorded):
    root, document = recorded
    original = json.dumps(document).encode()
    document["claims"]["R6.targets"]["value"] = 3
    document["source_excerpts"]["raw.json"]["fields"]["/targets"] = 3
    (root / "numbers.json").write_text(json.dumps(document))
    with pytest.raises(checker.VerificationError, match="reviewed SHA-256"):
        checker.verify(
            root, "numbers.json", [], expected_sha256=checker.digest(original), allow_excerpts=True
        )


def test_duplicate_json_keys_and_escaped_pointers():
    with pytest.raises(checker.VerificationError, match="Duplicate"):
        checker.parse_json('{"v": 1, "v": 2}')
    assert checker.pointer({"a/b": {"~x": [7]}}, "/a~1b/~0x/0") == 7
    with pytest.raises(checker.VerificationError, match="Invalid pointer"):
        checker.pointer({"a": 1}, "/a~2")


def test_scanning_checks_link_text_but_excludes_code_and_link_targets(recorded):
    text = (
        "# Results\n"
        "| [s3](reports/500029-tokens.json) | 10.00 GB → 4.00 GB (−60.0%) | "
        "<!-- numbers: best.s3_eval_no_grad_missing -->\n"
        + "\x60\x60\x60python\nprint('99 GB')\n\x60\x60\x60\n"
        + "Example flag: \x60--memory 99 GB\x60.\n"
    )
    checked, errors = checker.verify_documents(evidence(recorded), [("README.md", text.encode())])
    assert errors == [] and len(checked[0]["checked_lines"]) == 1
    _, errors = checker.verify_documents(
        evidence(recorded), [("README.md", (text + "A new result saved 99%.\n").encode())]
    )
    assert errors[0]["error"] == "Empirical numeric claim has no number scope"


def test_source_paths_cannot_leave_checkout(recorded):
    _, document = recorded
    claim = document["claims"]["R6.targets"]
    source = document["source_excerpts"].pop("raw.json")
    document["source_excerpts"]["../outside.json"] = source
    claim["source"]["path"] = "../outside.json"
    with pytest.raises(checker.VerificationError, match="escapes repository"):
        checker.Evidence(recorded[0], document).value("R6.targets")


@pytest.mark.parametrize("value", [None, True, float("nan"), "Infinity"])
def test_missing_and_nonfinite_values_are_not_zero(value):
    with pytest.raises(checker.VerificationError):
        checker.decimal(value)


def test_matching_value_for_unrelated_metric_is_rejected(recorded):
    with pytest.raises(checker.VerificationError, match="memory reduction"):
        checker.verify_line(
            evidence(recorded),
            "s3 diagnosis accuracy was 60.0% <!-- numbers: best.s3_eval_no_grad_missing -->",
        )
    with pytest.raises(checker.VerificationError, match="latest campaign"):
        checker.verify_line(
            evidence(recorded),
            "The best single campaign had 3 of 9 valid correct first-cause diagnoses. "
            "<!-- numbers: summary -->",
        )


def test_explicit_before_after_labels_cannot_reverse_measurement_meaning(recorded):
    with pytest.raises(checker.VerificationError, match="contradicts pair order"):
        checker.verify_line(
            evidence(recorded),
            "s3 after 10.00 GB → before 4.00 GB <!-- numbers: best.s3_eval_no_grad_missing -->",
        )


@pytest.fixture
def public_checkout(tmp_path):
    """Use the actual current documents and reviewed manifest, never edit originals."""
    repository = Path(__file__).parents[1]
    for relative in (
        checker.MANIFEST,
        "README.md",
        "docs/DEVPOST.md",
        "reports/t1.3-acceptance-20261025.json",
    ):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / relative, destination)
    return tmp_path


def run_cli(checkout):
    output = checkout / "number-check.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "scripts/verify_public_numbers.py"),
            "--root",
            str(checkout),
            "--allow-excerpts",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, json.loads(output.read_text())


def test_real_public_checkout_cli_labels_portable_evidence(public_checkout):
    completed, result = run_cli(public_checkout)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert result["passed"] is True
    assert result["evidence_level"] == "mixed_raw_and_reviewed_excerpts"
    assert result["verified_source_files"] == 1
    assert result["excerpt_only_source_files"] == 78
    assert result["automatic_documents"] == ["README.md", "docs/DEVPOST.md"]
    assert result["related_documents_not_scanned"] == ["docs/RESULTS.md", "docs/FEEDBACK.md"]
    assert [d["checked_numeric_values"] for d in result["documents"]] == [21, 9]


@pytest.mark.parametrize(
    "old,new,reason",
    [
        ("−73.4%", "−96.1%", "Unsupported numeric value"),
        (
            "numbers: best.s3_eval_no_grad_missing",
            "numbers: best.s8_two_models_resident",
            "Scenario label",
        ),
    ],
)
def test_real_readme_file_tampering_fails_complete_cli(public_checkout, old, new, reason):
    readme = public_checkout / "README.md"
    content = readme.read_text()
    assert content.count(old) == 1
    readme.write_text(content.replace(old, new))
    completed, result = run_cli(public_checkout)
    assert completed.returncode == 1
    assert result["passed"] is False
    assert any(e.get("document") == "README.md" and reason in e["error"] for e in result["errors"])


def test_real_source_file_tampering_fails_cli_even_with_excerpt_fallback(public_checkout):
    source = public_checkout / "reports/t1.3-acceptance-20261025.json"
    source.write_bytes(source.read_bytes() + b" ")
    completed, result = run_cli(public_checkout)
    assert completed.returncode == 1
    assert result["passed"] is False
    assert "Source SHA-256 mismatch" in result["errors"][0]["error"]
