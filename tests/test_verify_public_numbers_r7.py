"""CLI checks mutate actual published-document copies, not just checker helper outputs."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_verify_public_numbers import checker


@pytest.fixture
def current_checkout(tmp_path):
    repository = Path(__file__).parents[1]
    supplement = checker.parse_json((repository / checker.SUPPLEMENT).read_bytes())
    paths = {
        checker.MANIFEST,
        checker.SUPPLEMENT,
        checker.ABLATION_PATH,
        "README.md",
        "docs/DEVPOST.md",
        *supplement["sources"],
    }
    for relative in paths:
        source, destination = repository / relative, tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            shutil.copyfile(source, destination)
    assert "Across eight recorded campaigns" in (tmp_path / "README.md").read_text()
    return tmp_path


def cli(root, *, reviewed_update=False, extra=()):
    output = root / "result.json"
    args = [
        sys.executable,
        str(Path(__file__).parents[1] / "scripts/verify_public_numbers.py"),
        "--root",
        str(root),
        "--allow-excerpts",
        "--supplement",
        checker.SUPPLEMENT,
        "--output",
        str(output),
    ]
    if reviewed_update:
        args += [
            "--expected-supplement-sha256",
            checker.digest((root / checker.SUPPLEMENT).read_bytes()),
        ]
    result = subprocess.run([*args, *extra], capture_output=True, text=True, check=False)
    return result, json.loads(output.read_text())


def change_supplement(root, mutate):
    path = root / checker.SUPPLEMENT
    document = json.loads(path.read_text())
    mutate(document)
    path.write_text(json.dumps(document))


def test_current_real_readme_and_devpost_verify_with_versioned_sources(current_checkout):
    completed, result = cli(current_checkout)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert result["passed"]
    assert result["supplement"]["summary"] == {
        "recorded_campaigns": 8,
        "historical_target_scenarios": 5,
        "best_single_campaign_targets": 3,
        "latest_targets": 1,
        "latest_valid_correct_first_causes": 5,
        "latest_raw_category_matches": 7,
        "fixed_denominator": 9,
        "minimum_targets": 6,
    }
    selected = next(
        x
        for x in result["supplement"]["historical_best_selection"]
        if x["scenario_id"].startswith("s4_")
    )
    assert selected["run_id"] == "e8213706570e478f9845e49e24c2b54b"
    assert result["related_documents_not_scanned"] == ["docs/RESULTS.md", "docs/FEEDBACK.md"]
    assert result["automatic_documents"] == ["README.md", "docs/DEVPOST.md"]
    assert result["excerpt_only_source_files"] > 0  # Legacy raw artifacts are not copied here.


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        ("**5 of 9** valid correct", "**7 of 9** valid correct", "Wrong outcome count"),
        ("matches were **7 of 9**", "matches were **5 of 9**", "Wrong outcome count"),
        (
            "Across eight recorded campaigns",
            "Across seven recorded campaigns",
            "Wrong campaign count",
        ),
        ("<!-- numbers: summary -->", "<!-- numbers: long_context -->", "Long-context scope"),
    ],
)
def test_real_readme_semantic_score_or_scope_tampering_fails(current_checkout, old, new, reason):
    path = current_checkout / "README.md"
    text = path.read_text()
    assert text.count(old) == 1
    path.write_text(text.replace(old, new))
    completed, result = cli(current_checkout)
    assert completed.returncode == 1 and not result["passed"]
    assert any(e.get("document") == "README.md" and reason in e["error"] for e in result["errors"])


def test_supplement_hash_cannot_be_changed_silently(current_checkout):
    path = current_checkout / checker.SUPPLEMENT
    path.write_bytes(path.read_bytes() + b" ")
    completed, result = cli(current_checkout)
    assert completed.returncode == 1
    assert "Supplement differs from reviewed SHA" in result["errors"][0]["error"]


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("base", "base manifest binding"),
        ("pointer", "source binding"),
        ("source_hash", "source index"),
        ("derivation", "derived value"),
        ("inputs", "derivation"),
        ("old_tie", "selection/tie"),
    ],
)
def test_reviewed_supplement_still_rejects_wrong_binding_or_derivation(
    current_checkout, mutation, reason
):
    def mutate(doc):
        if mutation == "base":
            doc["base_manifest"]["sha256"] = "0" * 64
        elif mutation == "pointer":
            claim = doc["claims"]["latest.raw_category_matches"]
            claim["source"]["json_pointer"] = (
                "/fixed_nine/first_cause_scoring/valid_correct_first_causes"
            )
            claim["value"] = 5
        elif mutation == "source_hash":
            doc["claims"]["latest.raw_category_matches"]["source"]["sha256"] = "0" * 64
        elif mutation == "derivation":
            doc["claims"]["summary.campaign_count"]["value"] = 7
        elif mutation == "inputs":
            doc["claims"]["best.s4.before_GB"]["inputs"] = [
                "latest.s4_loss_accumulation_graph.after_bytes"
            ]
        else:
            selected = next(
                x for x in doc["historical_best_selection"] if x["scenario_id"].startswith("s4_")
            )
            selected["run_id"] = selected["previous_run_id"]

    change_supplement(current_checkout, mutate)
    # Supply the altered file's checksum: content validation must fail beyond the outer pin.
    completed, result = cli(current_checkout, reviewed_update=True)
    assert completed.returncode == 1 and not result["passed"]
    assert reason in result["errors"][0]["error"]


def test_present_changed_source_never_uses_excerpt_fallback(current_checkout):
    doc = json.loads((current_checkout / checker.SUPPLEMENT).read_text())
    source = current_checkout / doc["latest_source"]["path"]
    source.write_bytes(source.read_bytes() + b" ")
    completed, result = cli(current_checkout)
    assert completed.returncode == 1
    assert "Supplement source SHA-256 mismatch" in result["errors"][0]["error"]


def test_expired_upload_uses_only_explicitly_labelled_pinned_excerpt(current_checkout):
    doc = json.loads((current_checkout / checker.SUPPLEMENT).read_text())
    uploads = [path for path in doc["sources"] if path.startswith("runs/uploads/")]
    for name in uploads:
        path = current_checkout / name
        if path.exists():
            path.unlink()
    completed, result = cli(current_checkout)
    assert completed.returncode == 0
    assert all(
        result["supplement"]["sources"][name] == "reviewed_supplement_excerpt_only"
        for name in uploads
    )
    assert result["evidence_level"] == "mixed_raw_and_reviewed_excerpts"


@pytest.mark.parametrize("value", ["1e999", "-1e999", "NaN", "Infinity"])
def test_nonfinite_json_cannot_enter_evidence(value):
    with pytest.raises(checker.VerificationError, match="Non-finite"):
        checker.parse_json('{"value":' + value + "}")
