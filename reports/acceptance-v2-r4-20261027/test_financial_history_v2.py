"""Offline frozen-fixture tests. No SQLite, provider, GPU, or helper imports.

Run only after the R4 campaign releases the GPU and parent approves validation.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "isolated_r4_history", HERE / "audit_mvp_v2_history_v2.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def fixture():
    root = audit.ROOT
    docs, hashes = {}, {}
    for name, (path, sha) in audit.HISTORY_PINS.items():
        raw = (root / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise AssertionError("Fixture pin drift: " + name)
        docs[name] = json.loads(raw)
        hashes[path] = sha
    return {
        "funding": json.loads((root / audit.FUNDING_PATH).read_bytes()),
        "cap": json.loads((audit.OUT / "cap-review.json").read_bytes()),
        "preflight": json.loads((audit.OUT / "preflight.json").read_bytes()),
        "documents": docs,
        "hashes": hashes,
        "current_runs": copy.deepcopy(docs["after"]["budget_runs"]),
        "current_attempts": copy.deepcopy(docs["after"]["budget_attempts"]),
        "current_reviews": copy.deepcopy(docs["after"]["budget_retention_reviews"]),
    }


def item(rows, key, value):
    return next(row for row in rows if row[key] == value)


class FrozenHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = fixture()

    def evaluate(self, data):
        # Fail if someone later adds live/helper access to the pure proof.
        with (
            patch.object(
                audit, "load_helpers", side_effect=AssertionError("helper execution forbidden")
            ),
            patch.object(
                audit, "retention_snapshot", side_effect=AssertionError("SQLite access forbidden")
            ),
        ):
            return audit.financial_history_binding(**data)

    def test_original_immutable_chain_and_unknown_retention(self):
        result = self.evaluate(copy.deepcopy(self.base))
        self.assertTrue(result["accepted"], result)
        self.assertTrue(all(value is True for value in result["checks"].values()))
        self.assertEqual(result["stages"]["funding_baseline"]["runs"], 97)
        self.assertEqual(result["stages"]["funding_baseline"]["attempts"], 517)
        self.assertEqual(result["stages"]["r4_preflight"]["runs"], 115)
        self.assertEqual(result["stages"]["r4_preflight"]["attempts"], 632)
        self.assertEqual(
            result["stages"]["r4_preflight"]["conservative_charged_usd"], "9.211075556"
        )
        for field in (
            "historical_scores_used",
            "historical_results_reassessed",
            "original_funding_modified",
            "money_released",
            "new_funding",
            "provider_actual_inferred",
        ):
            self.assertIs(result[field], False)

    def test_no_input_mutation(self):
        data = copy.deepcopy(self.base)
        before = audit.canonical(data)
        self.evaluate(data)
        self.assertEqual(before, audit.canonical(data))

    def test_schema_identity_and_projection_negatives(self):
        mutations = [
            ("missing evidence", lambda d: d["documents"].pop("before")),
            ("missing pin", lambda d: d["hashes"].pop(audit.HISTORY_PINS["before"][0])),
            (
                "wrong pin",
                lambda d: d["hashes"].__setitem__(audit.HISTORY_PINS["before"][0], "0" * 64),
            ),
            ("old run dropped", lambda d: d["current_runs"].pop()),
            (
                "unknown prefixed run",
                lambda d: d["current_runs"][0].__setitem__("id", "diagnostic_probe_" + "0" * 32),
            ),
            ("old attempt dropped", lambda d: d["current_attempts"].pop()),
            ("old review dropped", lambda d: d["current_reviews"].pop(0)),
            (
                "duplicate run",
                lambda d: d["current_runs"].append(copy.deepcopy(d["current_runs"][0])),
            ),
            (
                "duplicate attempt",
                lambda d: d["current_attempts"].append(copy.deepcopy(d["current_attempts"][0])),
            ),
            (
                "duplicate review",
                lambda d: d["current_reviews"].append(copy.deepcopy(d["current_reviews"][0])),
            ),
            ("orphan attempt", lambda d: d["current_attempts"][0].__setitem__("run_id", "0" * 32)),
            ("new row field", lambda d: d["current_attempts"][0].__setitem__("unknown", 0)),
            ("changed day", lambda d: d["current_runs"][0].__setitem__("day", "2026-10-27")),
            ("changed charged", lambda d: d["current_attempts"][0].__setitem__("charged_usd", "0")),
            ("changed actual", lambda d: d["current_attempts"][0].__setitem__("actual_usd", "0")),
            ("changed bound", lambda d: d["current_attempts"][0].__setitem__("upper_usd", "1")),
            ("changed run status", lambda d: d["current_runs"][0].__setitem__("status", "active")),
            ("changed settlement", lambda d: d["current_attempts"][0].__setitem__("settled", 0)),
            ("changed dispatch", lambda d: d["current_attempts"][0].__setitem__("dispatched", 0)),
            ("malformed run row", lambda d: d["current_runs"].__setitem__(0, None)),
            ("malformed attempt row", lambda d: d["current_attempts"].__setitem__(0, None)),
            (
                "malformed historical campaign row",
                lambda d: d["documents"]["r2_campaign"]["rows"].__setitem__(0, None),
            ),
            (
                "wrong original projection",
                lambda d: d["funding"].__setitem__("runtime_ledger_projection_sha256", "0" * 64),
            ),
            (
                "rewritten original money",
                lambda d: d["funding"].__setitem__("runtime_conservative_net_usd", "9.211075556"),
            ),
            (
                "wrong original remainder",
                lambda d: d["funding"].__setitem__(
                    "remaining_runtime_lifetime_net_usd", "4.966681984"
                ),
            ),
            (
                "rewritten original count",
                lambda d: d["funding"].__setitem__("runtime_closed_runs", 115),
            ),
            (
                "wrong r2 end projection",
                lambda d: d["documents"]["r2_audit"]["finance"].__setitem__(
                    "all_time_projection_after", "0" * 64
                ),
            ),
            (
                "wrong r3 prior projection",
                lambda d: d["documents"]["r3_audit"]["finance"].__setitem__(
                    "prior_projection", "0" * 64
                ),
            ),
            (
                "wrong r3 campaign money",
                lambda d: d["documents"]["r3_audit"]["finance"]["campaign"].__setitem__(
                    "conservative_charged_usd", "0"
                ),
            ),
            (
                "duplicate historical identity",
                lambda d: d["documents"]["r2_campaign"]["rows"][0].__setitem__(
                    "run_id", d["documents"]["r2_campaign"]["rows"][1]["run_id"]
                ),
            ),
            (
                "foreign historical identity",
                lambda d: d["documents"]["r3_campaign"]["rows"][0].__setitem__("run_id", "0" * 32),
            ),
            (
                "wrong historical slot",
                lambda d: d["documents"]["r2_campaign"]["rows"][0].__setitem__(
                    "scenario_id", "unknown"
                ),
            ),
            (
                "wrong historical campaign hash",
                lambda d: d["documents"]["r2_execution"]["campaigns"][0].__setitem__(
                    "sha256", "0" * 64
                ),
            ),
            (
                "extra historical campaign",
                lambda d: d["documents"]["r3_execution"]["campaigns"].append({}),
            ),
            (
                "cap snapshot drift",
                lambda d: d["cap"]["ledger"].__setitem__("projection_sha256", "0" * 64),
            ),
            (
                "preflight snapshot drift",
                lambda d: d["preflight"]["budget_before"].__setitem__(
                    "projection_sha256", "0" * 64
                ),
            ),
            (
                "preflight history exclusions",
                lambda d: d["preflight"]["budget_before"].__setitem__(
                    "history_exclusions", ["old"]
                ),
            ),
            (
                "preflight known subtotal drift",
                lambda d: d["preflight"]["budget_before"].__setitem__("known_subtotal_usd", "0"),
            ),
            (
                "preflight unknown zeroed",
                lambda d: d["preflight"]["budget_before"].__setitem__("actual_total_usd", "0"),
            ),
            (
                "preflight count drift",
                lambda d: d["preflight"]["budget_before"].__setitem__("settled_attempts", 631),
            ),
            (
                "preflight status drift",
                lambda d: d["preflight"]["budget_before"]["charge_status_counts"].__setitem__(
                    "reviewed_retained", 1
                ),
            ),
            (
                "daily charge invented",
                lambda d: d["preflight"]["budget_before"].__setitem__("day_conservative_usd", "1"),
            ),
            (
                "pool raised",
                lambda d: d["preflight"]["budget_before"].__setitem__("all_time_limit_usd", "15"),
            ),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                data = copy.deepcopy(self.base)
                mutate(data)
                self.assertIs(self.evaluate(data)["accepted"], False)

    def test_only_one_exact_http529_metadata_review(self):
        def target(d, snapshot="after"):
            return item(d["documents"][snapshot]["budget_attempts"], "id", audit.REVIEW_ATTEMPT)

        def run(d, snapshot="after"):
            return item(d["documents"][snapshot]["budget_runs"], "id", audit.REVIEW_RUN)

        mutations = [
            (
                "wrong review target",
                lambda d: d["documents"]["receipt"].__setitem__("attempt_id", "0" * 32),
            ),
            (
                "different status",
                lambda d: d["documents"]["receipt"].__setitem__("http_status", 429),
            ),
            ("unknown set zero", lambda d: target(d).__setitem__("actual_usd", "0")),
            ("money released", lambda d: target(d).__setitem__("charged_usd", "0")),
            ("reservation lowered", lambda d: target(d).__setitem__("upper_usd", "0")),
            ("second dispatch", lambda d: target(d).__setitem__("dispatched", 2)),
            ("false exact", lambda d: target(d).__setitem__("charge_status", "exact")),
            ("wrong receipt", lambda d: target(d).__setitem__("review_sha256", "0" * 64)),
            ("wrong basis", lambda d: target(d).__setitem__("charge_basis", "forgiven")),
            (
                "halt not cleared",
                lambda d: run(d).__setitem__("halt_reason", "provider_charge_unknown"),
            ),
            ("additional run mutation", lambda d: run(d).__setitem__("limit_usd", "1")),
            (
                "second metadata mutation",
                lambda d: d["documents"]["after"]["budget_attempts"][0].__setitem__(
                    "charge_basis", "reviewed"
                ),
            ),
            (
                "review history replaced",
                lambda d: d["documents"]["after"]["budget_retention_reviews"][0].__setitem__(
                    "reviewed_at", "now"
                ),
            ),
            (
                "additional review",
                lambda d: d["documents"]["after"]["budget_retention_reviews"].append(
                    {"attempt_id": "0" * 32}
                ),
            ),
            (
                "review evidence changed",
                lambda d: d["documents"]["after"]["budget_retention_reviews"][-1].__setitem__(
                    "evidence_json", "{}"
                ),
            ),
            (
                "full attempt map missing",
                lambda d: d["documents"]["receipt"]["expected_attempts"].pop(),
            ),
            (
                "old unresolved hidden",
                lambda d: target(d, "before").__setitem__("charge_status", "upper_bound"),
            ),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                data = copy.deepcopy(self.base)
                mutate(data)
                self.assertIs(self.evaluate(data)["accepted"], False)

    def test_historical_scores_are_not_evidence(self):
        data = copy.deepcopy(self.base)
        for version in ("r2", "r3"):
            doc = data["documents"][version + "_audit"]
            doc["counts"] = {"targets": 9}
            doc["accepted_observed_campaign_gates"] = True
            doc["gates"] = {"at_least_six_targets": True}
            for row in data["documents"][version + "_campaign"]["rows"]:
                row["target_met"] = True
                row["first_cause_matches"] = True
        self.assertTrue(self.evaluate(data)["accepted"])

    def test_funding_still_requires_proven_chain_for_later_snapshot(self):
        data = audit.funding_fixture()
        data[0] = copy.deepcopy(self.base["funding"])
        data[4] = copy.deepcopy(self.base["cap"])
        self.assertFalse(audit.funding_binding(*data)["accepted"])
        proof = self.evaluate(copy.deepcopy(self.base))
        self.assertTrue(audit.funding_binding(*data, history=proof)["accepted"])
        proof["checks"]["only_exact_review_metadata_changed"] = False
        self.assertFalse(audit.funding_binding(*data, history=proof)["accepted"])

    def test_whitelisted_reader_refuses_missing_pin_before_private_reads(self):
        class Reader:
            def raw(self, path):
                return b"{}"

        with (
            patch.object(
                audit,
                "restricted_funding_bytes",
                side_effect=AssertionError("unexpected private read"),
            ),
            self.assertRaisesRegex(ValueError, "Changed or missing fixed"),
        ):
            audit.read_history_binding(Reader(), {}, {}, {}, [], [], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
