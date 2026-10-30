"""Draft-only CPU/stdlib contract checks. Never installs hooks or runs targets."""

import ast
import copy
import gc
import importlib.util
import json
import math
import re
import unittest
import weakref
from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = (ROOT / "draft/headroom/lab/hooks.py").read_text()
tree = ast.parse(source)
selected = []
for node in tree.body:
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id.startswith("_GROUP_") for t in node.targets
    ):
        selected.append(node)
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and (
        node.name.startswith("_optimizer_option_")
        or node.name in {"_encode_optimizer_group_option", "_OptimizerGroupOptionObserver"}
    ):
        selected.append(node)
ns = {"json": json, "math": math, "re": re, "weakref": weakref}
exec(  # noqa: S102 - Fixed locally selected report AST only; no external input.
    compile(ast.Module(body=selected, type_ignores=[]), "draft-observer-only", "exec"),
    ns,
)
Observer = ns["_OptimizerGroupOptionObserver"]
encode = ns["_encode_optimizer_group_option"]
spec = importlib.util.spec_from_file_location(
    "draft_summary", ROOT / "draft/headroom/optimizer_observations.py"
)
summary_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary_module)


class Optimizer:
    def __init__(self, **options):
        self.param_groups = [{"params": [object()], **options}]


def observe(opt, observer=None, *, stage="base_constructor_return", call=0):
    observer = observer or Observer()
    observer.observe(opt, stage=stage, call=call, identify=lambda parameter: "p00001")
    return observer


def summarize(observer, *, calls=0, constructors=1):
    return summary_module._optimizer_group_options(
        observer.snapshot(), {"p00001": 1}, calls, constructors
    )


class DraftTests(unittest.TestCase):
    def test_actual_values_typed_and_absent_is_not_default(self):
        result = summarize(observe(Optimizer(lr=0.02, momentum=0, foreach=None, nesterov=False)))
        self.assertEqual(result["status"], "observed")
        values = result["configurations"][0]["present"]
        self.assertEqual(
            values,
            {
                "lr": ["float", 0.02],
                "momentum": ["int", 0],
                "foreach": ["none", None],
                "nesterov": ["bool", False],
            },
        )
        self.assertNotIn("weight_decay", values)
        self.assertIn("No completed-update", result["scope"])

    def test_pre_step_mutation_has_distinct_actual_configuration(self):
        opt = Optimizer(lr=0.1)
        observer = observe(opt)
        opt.param_groups[0]["lr"] = 0.05
        observe(opt, observer, stage="step_pre", call=1)
        values = [
            item["present"]["lr"][1] for item in summarize(observer, calls=1)["configurations"]
        ]
        self.assertEqual(values, [0.1, 0.05])

    def test_repeated_steps_do_not_duplicate_identical_group_records(self):
        opt = Optimizer(lr=0.1)
        observer = observe(opt)
        for i in range(20):
            observe(opt, observer, stage="step_pre", call=i + 1)
        raw = observer.snapshot()
        self.assertEqual(len(raw["groups"]), 2)
        self.assertEqual(raw["groups"][1]["observations"], 20)
        self.assertEqual(len(raw["configurations"]), 1)
        self.assertEqual(summarize(observer, calls=20)["events"]["step_pre"], 20)

    def test_pair_container_and_scalar_types_preserved(self):
        self.assertEqual(encode("betas", (0.9, 0.99)), ["tuple", [["float", 0.9], ["float", 0.99]]])
        self.assertEqual(encode("betas", [0.9, 0.99]), ["list", [["float", 0.9], ["float", 0.99]]])
        self.assertEqual(encode("betas", (True, 0.99)), ["unsupported", None])
        self.assertEqual(encode("betas", (0.9,)), ["unsupported", None])

    def test_no_tensor_or_arbitrary_object_conversion(self):
        class Untouchable:
            def __float__(self):
                raise AssertionError("converted")

            def __repr__(self):
                raise AssertionError("repr")

            def item(self):
                raise AssertionError("read tensor")

        for value in [Untouchable(), "private-value", {"secret": "private-value"}]:
            with self.subTest(kind=type(value).__name__):
                observer = observe(Optimizer(lr=value))
                self.assertEqual(summarize(observer)["status"], "partial")
                self.assertEqual(
                    observer.snapshot()["configurations"][0]["present"]["lr"], ["unsupported", None]
                )
                self.assertNotIn("private-value", json.dumps(observer.snapshot()))

    def test_unknown_options_counted_but_no_names_or_values_copied(self):
        result = summarize(observe(Optimizer(lr=0.1, private_label="private-value")))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["configurations"][0]["unrecognized_option_keys"], 1)
        text = json.dumps(result)
        self.assertNotIn("private-value", text)
        self.assertNotIn("private_label", text)

    def test_float_limits_and_integer_exact_boundary(self):
        for value in [math.nan, math.inf, -math.inf, 2**63, -(2**63) - 1]:
            with self.subTest(value=type(value).__name__):
                self.assertEqual(encode("lr", value), ["unsupported", None])
        self.assertEqual(encode("lr", -(2**63)), ["int", -(2**63)])
        self.assertEqual(json.loads(json.dumps(encode("lr", -0.0)))[1], -0.0)
        self.assertEqual(encode("lr", 1.7976931348623157e308), ["float", 1.7976931348623157e308])

    def test_scalar_subclasses_not_coerced(self):
        class Number(float):
            pass

        self.assertEqual(encode("lr", Number(0.1)), ["unsupported", None])

    def test_group_bound_and_unsupported_containers_fail_only_observer(self):
        for groups in [
            [{"params": []}] * 65,
            (),
            [{"params": [], **{str(i): i for i in range(65)}}],
        ]:
            opt = Optimizer()
            opt.param_groups = groups
            observer = observe(opt)
            self.assertFalse(observer.snapshot()["complete"])
            self.assertTrue(observer.snapshot()["stopped_at_limit_or_error"])

    def test_parameter_token_bound_and_no_strong_references(self):
        opt = Optimizer(lr=0.1)
        observer = Observer()
        observer.observe(
            opt, stage="base_constructor_return", call=0, identify=lambda p: "private-value"
        )
        self.assertFalse(observer.snapshot()["complete"])
        self.assertNotIn("private-value", json.dumps(observer.snapshot()))
        opt = Optimizer(lr=0.1)
        observer = observe(opt)
        ref = weakref.ref(opt)
        del opt
        gc.collect()
        self.assertIsNone(ref())

    def test_native_deadline_not_swallowed(self):
        class Deadline(BaseException):
            pass

        def identify(p):
            raise Deadline()

        with self.assertRaises(Deadline):
            Observer().observe(
                Optimizer(), stage="base_constructor_return", call=0, identify=identify
            )

    def test_group_values_not_mutated(self):
        opt = Optimizer(lr=0.1, betas=(0.9, 0.99))
        before = dict(opt.param_groups[0])
        observe(opt)
        self.assertEqual(opt.param_groups[0], before)

    def test_capture_missing_stays_unknown(self):
        self.assertEqual(summary_module._optimizer_group_options(None, {}, 0, 0), "not_captured")

    def test_malformed_metadata_not_exposed(self):
        base = observe(Optimizer(lr=0.1)).snapshot()
        mutations = [
            lambda r: r["configurations"][0]["present"].update(lr=[[], 0.1]),
            lambda r: r["groups"][0].update(stage=[]),
            lambda r: r["groups"][0].update(parameter_ids=["unknown"]),
            lambda r: r["groups"][0].update(first_call=1),
            lambda r: r["events"].update(step_pre=True),
            lambda r: r["configurations"][0]["present"].update(private_label=["float", 0.1]),
            lambda r: r["configurations"][0]["present"].update(lr=["float", math.nan]),
        ]
        for mutation in mutations:
            raw = copy.deepcopy(base)
            mutation(raw)
            with self.subTest(mutation=mutations.index(mutation)):
                self.assertEqual(
                    summary_module._optimizer_group_options(raw, {"p00001": 1}, 0, 1)["status"],
                    "unverified",
                )

    def test_context_overflow_retains_no_partial_claim(self):
        opt = Optimizer(**{key: 0.1 for key in ns["_GROUP_OPTIONS"]})
        observer = observe(opt)
        opt.param_groups[0]["lr"] = 0.2
        observe(opt, observer, stage="step_pre", call=1)
        result = summarize(observer, calls=1)
        self.assertEqual(result["status"], "unverified")
        self.assertNotIn("configurations", result)

    def test_raw_byte_refusal_does_not_commit_oversize_config(self):
        old = ns["_GROUP_MAX_RAW_BYTES"]
        ns["_GROUP_MAX_RAW_BYTES"] = 1024
        try:
            opt = Optimizer(**{key: 0.1 for key in ns["_GROUP_OPTIONS"]})
            observer = observe(opt)
            raw = observer.snapshot()
            self.assertFalse(raw["complete"])
            self.assertTrue(raw["stopped_at_limit_or_error"])
            self.assertLessEqual(len(json.dumps(raw).encode()), 1024)
            self.assertEqual(raw["configurations"], [])
            self.assertEqual(raw["groups"], [])
        finally:
            ns["_GROUP_MAX_RAW_BYTES"] = old

    def test_record_refusal_does_not_commit_new_config(self):
        old = ns["_GROUP_MAX_RECORDS"]
        ns["_GROUP_MAX_RECORDS"] = 1
        try:
            opt = Optimizer(lr=0.1)
            observer = observe(opt)
            opt.param_groups[0]["lr"] = 0.2
            observe(opt, observer, stage="step_pre", call=1)
            self.assertEqual(len(observer.snapshot()["configurations"]), 1)
            self.assertFalse(observer.snapshot()["complete"])
        finally:
            ns["_GROUP_MAX_RECORDS"] = old

    def test_source_mismatch_cannot_expose_options(self):
        result = {
            "protocol": "headroom.lab.v1",
            "run_id": "1" * 32,
            "optimizer_update_observation": {
                "protocol": "headroom.optimizer_updates.v1",
                "group_options": observe(Optimizer(lr=0.1)).snapshot(),
            },
            "pairing_capture": {"source_contract": {"source_sha256": "a" * 64}},
        }
        summary = summary_module.runtime_optimizer_observations(
            result, [{"path": "train.py", "sha256": "b" * 64}], script="train.py"
        )
        self.assertEqual(summary["status"], "unverified")
        self.assertEqual(summary["optimizer_group_hyperparameters"], "not_captured")

    def test_real_old_zero_step_capture_parity_and_synthetic_extension_bound(self):
        from importlib.util import module_from_spec, spec_from_file_location

        production_spec = spec_from_file_location(
            "old_summary", Path("headroom/optimizer_observations.py")
        )
        production = module_from_spec(production_spec)
        production_spec.loader.exec_module(production)
        base = Path(
            "runs/repair-followup/execution-r15-20261030/jobs/5d1ec8f0e41145d5a643c062b17e5f14"
        )
        selected = json.loads(
            (base / "lab/05e95a18625f4eb594676d66d2af9765/result.json").read_text()
        )
        evidence = json.loads((base / "evidence/before/evidence.json").read_text())
        old = production.runtime_optimizer_observations(
            selected, evidence["sources"], script="train.py"
        )
        current = summary_module.runtime_optimizer_observations(
            selected, evidence["sources"], script="train.py"
        )
        self.assertEqual(current, old)
        # This is synthetic metadata, never written back to historical capture.
        selected = copy.deepcopy(selected)
        opt = Optimizer(
            lr=0.01,
            momentum=0.9,
            weight_decay=0.0001,
            dampening=0,
            nesterov=False,
            maximize=False,
            foreach=None,
            differentiable=False,
            fused=None,
        )
        observer = observe(opt)
        selected["optimizer_update_observation"]["group_options"] = observer.snapshot()
        current = summary_module.runtime_optimizer_observations(
            selected, evidence["sources"], script="train.py"
        )
        self.assertEqual(current["status"], "partial")
        self.assertEqual(current["logical_updates"], 0)
        self.assertFalse(current["parameter_update_sets_complete"])
        self.assertEqual(current["optimizer_group_hyperparameters"]["status"], "observed")
        self.assertLessEqual(
            len(json.dumps(current, ensure_ascii=True, allow_nan=False).encode()), 3072
        )


if __name__ == "__main__":
    unittest.main()
