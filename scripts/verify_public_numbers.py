#!/usr/bin/env python3
"""Read-only source and claim check; never runs models, workloads or account calls.

Prose lines use <!-- numbers: best.<scenario_id> -->, summary, or long_context.
Scenario labels, before/after order, and outcome wording bind each displayed value.
GB/GiB, percentages, input tokens and outcome fractions are checked. Code, update
counts, loss claims, model names, hardware specifications and versions need manual
review. Portable --allow-excerpts reports weaker evidence when raw files are absent;
a present source with a bad hash never falls back to an excerpt.
"""

import argparse
import hashlib
import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "reports/final48h-docs-20261029/numbers.json"
REVIEWED_SHA256 = "c969deaee6ed37e52913fbf31e349bc4e519c6d7fa5fc25e16e30244dd79207e"
NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
METRIC = re.compile(
    rf"(?<![\w.])(?P<number>[−-]?{NUMBER})(?P<scale>[kKmM]| thousand| million)?\s*-?\s*"
    r"(?P<unit>GB|GiB|%|percent\b|(?:input |prompt |server-counted )?tokens?\b)",
    re.IGNORECASE,
)
FRACTION = re.compile(r"(?<!\w)(\d+)\s*(?:/|of)\s*(\d+)(?!\w)")
SCOPE = re.compile(r"<!--\s*numbers:\s*([A-Za-z0-9_.]+)\s*-->")
PAIRING = (
    "same_inputs",
    "same_effective_batch",
    "same_objective",
    "same_seed",
    "parameter_count_unchanged",
)


class VerificationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(raw):
    def invalid(value):
        raise VerificationError(f"Non-finite JSON number: {value}")

    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def equal(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
        right, sort_keys=True, allow_nan=False
    )


def decimal(value):
    require(
        type(value) in (int, float, str, Decimal),
        "Expected a numeric value, not missing or boolean",
    )
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise VerificationError("Invalid numeric value") from error
    require(result.is_finite(), "Non-finite numeric value")
    return result


def pointer(document, path):
    require(path == "" or path.startswith("/"), f"Invalid JSON pointer: {path}")
    current = document
    for token in path.split("/")[1:] if path else []:
        require(not re.search(r"~(?![01])", token), f"Invalid pointer escape: {path}")
        token = token.replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(current, list):
                require(bool(re.fullmatch(r"0|[1-9]\d*", token)), f"Invalid array pointer: {path}")
                current = current[int(token)]
            else:
                require(isinstance(current, dict), f"Pointer traverses a scalar: {path}")
                current = current[token]
        except (KeyError, IndexError) as error:
            raise VerificationError(f"Missing source JSON pointer: {path}") from error
    return current


def contained(root, relative):
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts, "Source path escapes repository")
    result = (root / path).resolve()
    require(result.is_relative_to(root.resolve()), "Source path escapes repository")
    return result


class Evidence:
    def __init__(self, root, document, *, allow_excerpts=False):
        self.root, self.document = Path(root), document
        self.claims = document["claims"]
        self.allow_excerpts = allow_excerpts
        self.raw, self.levels, self.values = {}, {}, {}
        self.visiting = set()

    def source(self, ref):
        relative, expected, location = ref["path"], ref["sha256"], ref["json_pointer"]
        require(bool(re.fullmatch(r"[a-f0-9]{64}", expected)), "Invalid source SHA-256")
        excerpt = self.document["source_excerpts"].get(relative)
        require(
            excerpt is not None and excerpt["sha256"] == expected, "Excerpt source hash mismatch"
        )
        require(location in excerpt["fields"], f"Missing excerpt pointer: {relative}:{location}")
        path = contained(self.root, relative)
        if relative not in self.levels:
            if path.exists():
                require(path.is_file(), f"Source is not a file: {relative}")
                raw = path.read_bytes()
                require(digest(raw) == expected, f"Source SHA-256 mismatch: {relative}")
                self.raw[relative] = (expected, parse_json(raw))
                self.levels[relative] = "raw_sha256_and_json_pointer"
            else:
                require(self.allow_excerpts, f"Missing raw source: {relative}")
                self.levels[relative] = "reviewed_excerpt_only"
        if relative in self.raw:
            actual_hash, data = self.raw[relative]
            require(actual_hash == expected, f"Conflicting source hash: {relative}")
            value = pointer(data, location)
            require(
                equal(value, excerpt["fields"][location]), f"Excerpt value mismatch: {relative}"
            )
            return value
        return excerpt["fields"][location]

    def value(self, name):
        if name in self.values:
            return self.values[name]
        require(name in self.claims, f"Unknown claim: {name}")
        require(name not in self.visiting, f"Claim dependency cycle: {name}")
        self.visiting.add(name)
        claim = self.claims[name]
        require(("source" in claim) != ("inputs" in claim), f"Ambiguous claim definition: {name}")
        if "source" in claim:
            require(
                equal(self.source(claim["source"]), claim["value"]),
                f"Source value mismatch: {name}",
            )
        else:
            require(
                decimal(self.derive(name, claim)) == decimal(claim["value"]),
                f"Derived value mismatch: {name}",
            )
        self.visiting.remove(name)
        self.values[name] = claim["value"]
        return claim["value"]

    def derive(self, name, claim):
        inputs, formula = claim["inputs"], claim["formula"]
        require(
            isinstance(inputs, list) and len(set(inputs)) == len(inputs), "Invalid claim inputs"
        )
        values = [self.value(key) for key in inputs]
        with localcontext() as context:
            context.prec = 40
            if formula in ("bytes / 1000000000", "bytes / 1073741824"):
                require(
                    inputs == [name.rsplit(".", 1)[0] + ".bytes"], f"Wrong byte binding: {name}"
                )
                return decimal(values[0]) / Decimal(formula.split(" / ")[1])
            if formula.startswith("(before_bytes-after_bytes)*100/before_bytes;"):
                require(
                    name.startswith("best.") and name.endswith(".reduction_pct"), "Wrong reduction"
                )
                scenario = name.split(".")[1]
                row = self.selected(scenario)
                prefix = f"{row['campaign']}.{scenario}"
                require(
                    inputs == [prefix + ".before.bytes", prefix + ".after.bytes"], "Wrong peak pair"
                )
                before, after = map(decimal, values)
                require(before > 0, "Nonpositive baseline peak")
                return (before - after) * 100 / before
            if formula == "length of full baseline backward-loss series":
                require(
                    inputs == [name.rsplit(".", 1)[0] + ".comparison_loss_series"],
                    "Wrong loss series",
                )
                require(isinstance(values[0], list), "Loss series is missing")
                return len(values[0])
            if formula == "first_five_backward_scalars protocol compares the first five scalars":
                require(inputs == [name.rsplit(".", 1)[0] + ".basis"], "Wrong numerical basis")
                require(
                    isinstance(values[0], str) and "first_five_backward_scalars" in values[0],
                    "Unsupported first-five comparison",
                )
                return 5
            if formula == "sum recorded end-to-end wall_seconds; not GPU time":
                campaign = name.split(".")[0]
                expected = [
                    f"{campaign}.{r['scenario_id']}.wall_seconds"
                    for r in self.campaign(campaign)["rows"]
                ]
                require(inputs == expected, "Wrong wall-time inputs")
                return sum(map(decimal, values), Decimal(0))
            if formula == "max across separate protocol-v2 campaign target counts":
                require(
                    inputs == [f"{c['id']}.targets" for c in self.document["campaigns"]],
                    "Wrong campaigns",
                )
                return max(map(decimal, values))
            if formula.startswith("sum disjoint R0–R6 campaign "):
                suffix = (
                    "known_actual_subtotal_usd"
                    if "known subtotals" in formula
                    else "conservative_charged_usd"
                )
                require(
                    inputs == [f"{c['id']}.cost.{suffix}" for c in self.document["campaigns"]],
                    "Wrong cost inputs",
                )
                return sum(map(decimal, values), Decimal(0))
            if formula.startswith("distinct scenario families with at least one target_met"):
                expected = {
                    f"{r['campaign']}.{r['scenario_id']}.target"
                    for r in self.document["historical_best"]
                }
                require(
                    set(inputs) == expected and all(value is True for value in values),
                    "Wrong historical target inputs",
                )
                return len(expected)
            if formula == "distinct successful scenarios in R4–R6 only":
                require(
                    inputs == ["R4.targets", "R5.targets", "R6.targets"], "Wrong campaign range"
                )
                return len(
                    {
                        k.split(".")[1]
                        for k in self.claims
                        if re.fullmatch(r"R[456]\.[^.]+\.target", k) and self.value(k) is True
                    }
                )
            if formula.startswith("selected best targets with 20 compared loss scalars"):
                scenarios = [r["scenario_id"] for r in self.document["historical_best"]]
                require(
                    set(inputs) == {f"best.{s}.compared_loss_count" for s in scenarios},
                    "Wrong selected loss inputs",
                )
                return sum(
                    self.value(f"best.{s}.compared_loss_count") == 20
                    and self.value(f"best.{s}.status") == "identical"
                    and all(self.value(f"best.{s}.{field}") is True for field in PAIRING)
                    for s in scenarios
                )
        raise VerificationError(f"Unsupported derivation: {name}")

    def campaign(self, name):
        matches = [c for c in self.document["campaigns"] if c["id"] == name]
        require(len(matches) == 1, f"Unknown or duplicate campaign: {name}")
        return matches[0]

    def selected(self, scenario):
        matches = [r for r in self.document["historical_best"] if r["scenario_id"] == scenario]
        require(len(matches) == 1, f"Unknown or duplicate selected scenario: {scenario}")
        return matches[0]

    def verify(self):
        for name in self.claims:
            self.value(name)
        selections = {}
        for campaign in self.document["campaigns"]:
            rows = campaign["rows"]
            require(
                len(rows) == 9 and len({r["scenario_id"] for r in rows}) == 9,
                f"Campaign must retain nine scenarios: {campaign['id']}",
            )
            require(
                campaign["scenario_ids"] == [r["scenario_id"] for r in rows],
                "Scenario list differs from campaign rows",
            )
            for row in rows:
                prefix = f"{campaign['id']}.{row['scenario_id']}"
                require(row["campaign"] == campaign["id"], "Wrong row campaign")
                require(
                    row["target_met"] is self.value(prefix + ".target"), "Wrong target projection"
                )
                for side in ("before", "after"):
                    for field in ("bytes", "status", "updates", "peak_is_exact", "step_ms"):
                        require(
                            equal(row[side][field], self.value(f"{prefix}.{side}.{field}")),
                            f"Wrong row projection: {prefix}.{side}.{field}",
                        )
                    for unit in ("GB", "GiB"):
                        expected = (
                            self.value(f"{prefix}.{side}.{unit}")
                            if row[side]["bytes"] is not None
                            else None
                        )
                        require(equal(row[side][unit], expected), "Wrong displayed unit projection")
                if row["target_met"] is True:
                    require(row["after"]["bytes"] is not None, "Target lacks measured after peak")
                    previous = selections.get(row["scenario_id"])
                    rank = (row["after"]["bytes"], -int(campaign["id"][1:]))
                    if previous is None or rank < previous[0]:
                        selections[row["scenario_id"]] = (rank, row)
        require(
            set(selections) == {r["scenario_id"] for r in self.document["historical_best"]},
            "Historical selection omits or adds successful scenarios",
        )
        for row in self.document["historical_best"]:
            chosen = selections[row["scenario_id"]][1]
            for field, value in chosen.items():
                require(
                    equal(row[field], value),
                    f"Historical selection differs: {row['scenario_id']}.{field}",
                )
            require(
                decimal(row["reduction_pct"])
                == decimal(self.value(f"best.{row['scenario_id']}.reduction_pct")),
                "Historical reduction differs",
            )
        summary = self.document["summary"]
        latest = self.campaign(summary["latest_campaign"])
        require(equal(self.document["latest"]["rows"], latest["rows"]), "Latest rows differ")
        expected_summary = {
            "fixed_denominator": 9,
            "latest_targets": self.value(latest["id"] + ".targets"),
            "latest_valid_correct_first_causes": self.value(
                latest["id"] + ".valid_correct_first_causes"
            ),
            "latest_first_causes_unknown": self.value(latest["id"] + ".first_causes_unknown"),
            "historical_target_scenarios": self.value("summary.historical_target_scenario_count"),
            "best_single_campaign_targets": self.value("summary.best_single_campaign_targets"),
        }
        for key, expected in expected_summary.items():
            require(equal(summary[key], expected), f"Summary projection differs: {key}")
        return self


def rendered_line(line):
    text = SCOPE.sub("", line)
    text = re.sub(r"<!--.*?-->", "", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\x60[^\x60]*\x60", "", text)
    return text.replace("**", "").replace("__", "")


def clause(text, start, end):
    boundaries = list(re.finditer(r"[.;]|,\s*with\b|\s+and\s+", text))
    left = max((m.end() for m in boundaries if m.end() <= start), default=0)
    right = min((m.start() for m in boundaries if m.start() >= end), default=len(text))
    return text[left:right].lower()


def rounded_match(observed, expected):
    raw = observed.replace(",", "").replace("−", "-")
    places = len(raw.split(".", 1)[1]) if "." in raw else 0
    with localcontext() as context:
        context.prec = 60
        rounded = decimal(expected).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return abs(decimal(raw)) == rounded


ABLATION_PATH = "reports/ablation-20261028/ablation.json"
ABLATION_SHA256 = "609b4077ed7c008a650daec2f0f02271352b59a89ccfaf7320427df92fc0880a"


def verify_ablation_line(evidence, line, scope):
    raw = contained(evidence.root, ABLATION_PATH).read_bytes()
    require(digest(raw) == ABLATION_SHA256, "Ablation source changed")
    study = parse_json(raw)
    evidence.levels[ABLATION_PATH] = "raw_sha256_and_json_pointer"
    require(study["completed_all_requests"] is True, "Ablation is incomplete")
    condition = scope.removeprefix("ablation.")
    rows = [row for row in study["conditions"] if row["condition"] == condition]
    require(len(rows) == 1, "Unknown ablation condition")
    row = rows[0]
    require(row["denominator"] == 9 and row["attempted"] == 9, "Ablation denominator changed")
    labels = {
        "full_ultra": "Full evidence + Ultra",
        "traceback_ultra": "Traceback + memory summary + Ultra",
        "full_super": "Full evidence + Super",
    }
    expected = (
        f"| {labels[condition]} | {row['first_cause_matches']}/9 | "
        f"{row['valid_correct_first_causes']}/9 | "
        f"{row['mean_provider_input_tokens']:,.0f} | {chr(36)}{row['total_cost_usd']} | "
        f"{row['mean_latency_seconds']:.3f} s |"
    )
    require(SCOPE.sub("", line).strip() == expected, "Ablation row differs from measured data")
    return [
        {
            "claim": f"ablation.{condition}.{field}",
            "value": row[field],
            "source": ABLATION_PATH,
            "source_sha256": ABLATION_SHA256,
            "json_pointer": f"/conditions/{study['conditions'].index(row)}/{field}",
        }
        for field in (
            "denominator",
            "first_cause_matches",
            "valid_correct_first_causes",
            "mean_provider_input_tokens",
            "total_cost_usd",
            "mean_latency_seconds",
        )
    ]


def verify_line(evidence, line):
    scopes = SCOPE.findall(line)
    require(len(scopes) <= 1, "Multiple number scopes on one line")
    if scopes and scopes[0].startswith("ablation."):
        return verify_ablation_line(evidence, line, scopes[0])
    text = rendered_line(line)
    metrics, fractions = list(METRIC.finditer(text)), list(FRACTION.finditer(text))
    if not metrics and not fractions:
        require(not scopes, "Number scope has no checked metric")
        return []
    require(bool(scopes), "Empirical numeric claim has no number scope")
    scope, result = scopes[0], []
    if scope.startswith("best."):
        scenario = scope.removeprefix("best.")
        row = evidence.selected(scenario)
        label = scenario.split("_", 1)[0]
        require(
            set(re.findall(r"\bs[1-8]\b", text, re.IGNORECASE)) == {label},
            "Scenario label does not match number scope",
        )
        require(not fractions, "Fractions require an explicit summary scope")
        campaigns = set(re.findall(r"\bR[0-6]\b", text))
        require(
            not campaigns or campaigns == {row["campaign"]},
            "Scenario campaign differs from selected source",
        )
        peaks = [m for m in metrics if m["unit"].upper() in {"GB", "GIB"}]
        require(len(peaks) in (0, 1, 2), "Expected at most a before/after peak pair")
        percentages = [m for m in metrics if m["unit"].lower() in {"%", "percent"}]
        require(len(percentages) <= 1, "Only one memory reduction is supported per scenario line")
        for metric in metrics:
            unit = metric["unit"].lower()
            if unit in {"gb", "gib"}:
                require(not metric["number"].startswith(("-", "−")), "Negative memory value")
                side = ("before", "after")[peaks.index(metric)] if len(peaks) == 2 else None
                if side is not None:
                    preceding = text[: metric.start()]
                    # Explicit labels must agree with the before/after pair order.
                    labels = list(re.finditer(r"\b(before|after)\b", preceding, re.IGNORECASE))
                    if labels and (not peaks.index(metric) or labels[-1].start() > peaks[0].end()):
                        require(
                            labels[-1][1].lower() == side,
                            "Explicit peak label contradicts pair order",
                        )
                if side is None:
                    context = clause(text, metric.start(), metric.end())
                    labels = [word for word in ("before", "after") if word in context]
                    require(len(labels) == 1, "Single peak needs an explicit before or after label")
                    side = labels[0]
                key = f"{row['campaign']}.{scenario}.{side}.{'GB' if unit == 'gb' else 'GiB'}"
            else:
                require(unit in {"%", "percent"}, "Unsupported metric for scenario scope")
                context = clause(text, metric.start(), metric.end())
                require(
                    len(peaks) == 2
                    or bool(
                        re.search(
                            r"(?:peak memory|memory peak).*(?:fell|drop|reduc|lower)|"
                            r"(?:peak|memory) (?:reduction|saving)",
                            context,
                        )
                    ),
                    "Percentage must describe memory reduction, not another scenario metric",
                )
                key = f"best.{scenario}.reduction_pct"
            expected = evidence.value(key)
            require(metric["scale"] is None, "Scaled memory/percentage notation is unsupported")
            require(
                rounded_match(metric["number"], expected), f"Unsupported numeric value for {key}"
            )
            result.append({"claim": key, "display": metric.group(), "value": expected})
    elif scope == "long_context":
        require(
            not fractions and all("token" in m["unit"].lower() for m in metrics),
            "Long-context scope only supports input-token claims",
        )
        for metric in metrics:
            context = clause(text, metric.start(), metric.end())
            if "evidence" in context and not any(
                word in context for word in ("retrieval", "probe")
            ):
                key = "long_context.real_evidence_provider_input_tokens"
            elif (
                any(word in context for word in ("retrieval", "probe"))
                and "evidence" not in context
            ):
                require(
                    not any(word in context for word in ("reject", "900k", "nominal")),
                    "Rejected requests need a separate reviewed claim",
                )
                key = "long_context.largest_successful_server_prompt_tokens"
            else:
                raise VerificationError(
                    "Input tokens need unambiguous evidence or retrieval context"
                )
            require(
                decimal(metric["number"].replace(",", ""))
                * {"": 1, "k": 1000, "m": 1000000, " thousand": 1000, " million": 1000000}[
                    (metric["scale"] or "").lower()
                ]
                == decimal(evidence.value(key)),
                f"Unsupported token count for {key}",
            )
            result.append({"claim": key, "display": metric.group(), "value": evidence.value(key)})
    elif scope == "summary":
        require(not metrics, "Summary scope only supports outcome fractions")
        summary = evidence.document["summary"]
        latest = summary["latest_campaign"]
        for fraction in fractions:
            context = clause(text, fraction.start(), fraction.end())
            if "first-cause" in context or "first cause" in context:
                require(
                    "best" not in context and "histor" not in context,
                    "First-cause fraction must describe the latest campaign",
                )
                key = latest + ".valid_correct_first_causes"
            elif "best single campaign" in context:
                key = "summary.best_single_campaign_targets"
            elif "distinct scenario" in context and (
                "histor" in context or "across seven recorded campaigns" in context
            ):
                require("target" in context, "Historical fraction must describe target scenarios")
                key = "summary.historical_target_scenario_count"
            elif "latest campaign" in context:
                key = latest + ".targets"
            else:
                raise VerificationError("Outcome fraction has no supported semantic binding")
            require(int(fraction[2]) == summary["fixed_denominator"], "Unsupported denominator")
            require(
                decimal(fraction[1]) == decimal(evidence.value(key)), f"Wrong outcome count: {key}"
            )
            result.append(
                {
                    "claim": key,
                    "display": fraction.group(),
                    "value": evidence.value(key),
                    "denominator": summary["fixed_denominator"],
                }
            )
    else:
        raise VerificationError(f"Unknown number scope: {scope}")
    return result


def verify_documents(evidence, documents):
    checked, errors = [], []
    for path, raw in documents:
        fenced, rows = False, []
        for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if re.match(r"^\s*(\x60{3}|~~~)", line):
                fenced = not fenced
                continue
            if fenced:
                continue
            try:
                claims = verify_line(evidence, line)
                if claims:
                    rows.append({"line": number, "claims": claims})
            except VerificationError as error:
                errors.append({"document": path, "line": number, "error": str(error)})
        checked.append(
            {
                "path": path,
                "sha256": digest(raw),
                "checked_numeric_values": sum(len(row["claims"]) for row in rows),
                "checked_lines": rows,
            }
        )
    return checked, errors


def verify(root, manifest_path, docs, *, expected_sha256, allow_excerpts=False):
    raw = contained(root, manifest_path).read_bytes()
    require(digest(raw) == expected_sha256, "Manifest differs from reviewed SHA-256")
    document = parse_json(raw)
    require(document["schema"] == "headroom.final48h.numbers.v1", "Unsupported manifest schema")
    evidence = Evidence(root, document, allow_excerpts=allow_excerpts).verify()
    checked, errors = verify_documents(
        evidence, [(n, contained(root, n).read_bytes()) for n in docs]
    )
    levels = list(evidence.levels.values())
    raw_count, excerpt_count = (
        levels.count("raw_sha256_and_json_pointer"),
        levels.count("reviewed_excerpt_only"),
    )
    return {
        "schema": "headroom.public-number-check.v1",
        "passed": not errors,
        "evidence_level": "all_raw_sources"
        if not excerpt_count
        else "mixed_raw_and_reviewed_excerpts"
        if raw_count
        else "reviewed_excerpts_only",
        "manifest": {"path": manifest_path, "sha256": digest(raw)},
        "verified_source_files": raw_count,
        "excerpt_only_source_files": excerpt_count,
        "claims_checked": len(evidence.values),
        "derived_claims_checked": sum("inputs" in c for c in document["claims"].values()),
        "sources": evidence.levels,
        "documents": checked,
        "errors": errors,
        "scope": "Scoped prose GB/GiB, percentages, input tokens, outcome fractions, and complete ablation rows including cost and elapsed time.",
        "automatic_documents": list(docs),
        "related_documents_not_scanned": [
            name for name in ("docs/RESULTS.md", "docs/FEEDBACK.md") if name not in docs
        ],
        "limitations": [
            (
                "FINAL_48H F4 requires automatic README numeric checking; DEVPOST is an "
                "additional check. RESULTS and FEEDBACK are not automatically checked unless "
                "explicitly supplied and given supported claim bindings."
            ),
            (
                "Non-numeric conclusions, updates/loss equivalence, model names, versions, hardware "
                "specifications and code examples need manual review."
            ),
            "Excerpt fallback verifies the pinned public excerpt, not the absent raw source bytes.",
            "Sentence meaning beyond the explicit scenario/metric binding requires manual review.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--numbers", default=MANIFEST)
    parser.add_argument("--expected-manifest-sha256", default=REVIEWED_SHA256)
    parser.add_argument("--allow-excerpts", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("documents", nargs="*", default=["README.md", "docs/DEVPOST.md"])
    args = parser.parse_args()
    try:
        result = verify(
            args.root,
            args.numbers,
            args.documents,
            expected_sha256=args.expected_manifest_sha256,
            allow_excerpts=args.allow_excerpts,
        )
    except (VerificationError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        result = {
            "schema": "headroom.public-number-check.v1",
            "passed": False,
            "errors": [{"error": str(error)}],
        }
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
        print(
            json.dumps(
                {k: result.get(k) for k in ("passed", "evidence_level", "claims_checked", "errors")}
            )
        )
    else:
        print(encoded, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
