#!/usr/bin/env python3
"""T0.5 Tavily probe: no requests unless --execute is explicitly supplied."""

import argparse
import importlib.metadata
import inspect
import json
import math
import re
import stat
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
API_BASE = "https://api.tavily.com"
CHECKPOINT_URL = "https://docs.pytorch.org/docs/2.5/checkpoint.html"
ISSUE_URL = "https://github.com/pytorch/pytorch/issues/102223"
NOT_EXECUTED = 78


def operations():
    """Exactly four requests; no retries, fallback requests, or account calls."""
    search = {
        "query": "PyTorch 2.5 torch.utils.checkpoint use_reentrant False",
        "max_results": 2,
        "include_domains": ["docs.pytorch.org", "pytorch.org", "github.com"],
        "include_answer": False,
        "include_raw_content": False,
        "include_usage": True,
        "auto_parameters": False,
        "timeout": 30,
    }
    return [
        {
            "id": "search_basic",
            "method": "search",
            "arguments": {**search, "search_depth": "basic"},
        },
        {
            "id": "search_advanced",
            "method": "search",
            "arguments": {**search, "search_depth": "advanced"},
        },
        *[
            {
                "id": name,
                "method": "extract",
                "arguments": {
                    "urls": [url],
                    "extract_depth": "basic",
                    "format": "markdown",
                    "include_usage": True,
                    "timeout": 30,
                },
            }
            for name, url in (("extract_checkpoint", CHECKPOINT_URL), ("extract_issue", ISSUE_URL))
        ],
    ]


def redact(value, secrets=()):
    """Sanitize every persisted value, including error text and API metadata."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            safe_key = redact(str(key), secrets)
            normalized = re.sub(r"[^a-z]", "", str(key).lower())
            if any(
                token in normalized
                for token in ("apikey", "authorization", "password", "secret", "headers", "cookie")
            ):
                result[safe_key] = "[REDACTED]"
            else:
                result[safe_key] = redact(item, secrets)
        return result
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                for representation in {secret, quote(secret, safe=""), quote_plus(secret)}:
                    value = value.replace(representation, "[REDACTED]")
        value = re.sub(r"(?i)\btvly-[A-Za-z0-9_-]+", "[REDACTED]", value)
        return re.sub(r"(?i)\bBearer\s+[^\s\"',}]+", "Bearer [REDACTED]", value)
    if type(value) is float and not math.isfinite(value):
        return "[NONFINITE]"
    if value is None or type(value) in (bool, int, float):
        return value
    return f"[UNSUPPORTED:{type(value).__name__}]"


def schema_of(value, depth=0):
    """Observed API field/type shape only; page content is never saved."""
    if depth > 8:
        return "depth_limit"
    if isinstance(value, dict):
        return {str(key): schema_of(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        shapes = []
        for item in value[:20]:
            shape = schema_of(item, depth + 1)
            if shape not in shapes:
                shapes.append(shape)
        return {"type": "array", "length": len(value), "item_shapes": shapes}
    return {
        type(None): "null",
        bool: "boolean",
        int: "integer",
        float: "number",
        str: "string",
    }.get(type(value), "unsupported")


def canonical_url(url):
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, "")
    )


def classify_response(operation, response):
    """A 200 response with empty/malformed/failed extraction is not success."""
    if not isinstance(response, dict):
        return "failed", "response_not_object"
    results = response.get("results")
    if not isinstance(results, list) or not results:
        return "failed", "results_missing_or_empty"
    content_field = "content" if operation["method"] == "search" else "raw_content"
    for result in results:
        if (
            not isinstance(result, dict)
            or not canonical_url(result.get("url"))
            or not isinstance(result.get(content_field), str)
            or not result[content_field].strip()
        ):
            return "failed", "malformed_or_empty_result"
    if operation["method"] == "extract":
        failures = response.get("failed_results", [])
        if not isinstance(failures, list) or failures:
            return "failed", "extract_has_failed_results"
        expected = {canonical_url(url) for url in operation["arguments"]["urls"]}
        observed = {canonical_url(result["url"]) for result in results}
        if not expected.issubset(observed):
            return "failed", "extract_requested_url_missing"
    return "succeeded", None


def response_summary(response, secrets):
    clean = redact(response, secrets)
    if not isinstance(clean, dict):
        return {"response_schema": schema_of(clean), "credits": None, "usage": None}
    results = clean.get("results")
    summaries = []
    if isinstance(results, list):
        for item in results[:20]:
            if not isinstance(item, dict):
                continue
            summaries.append(
                {
                    **{key: item[key] for key in ("url", "title", "score") if key in item},
                    **{
                        f"{key}_characters": len(item[key])
                        for key in ("content", "raw_content")
                        if isinstance(item.get(key), str)
                    },
                }
            )
    usage = clean.get("usage")
    credits = usage.get("credits") if isinstance(usage, dict) else None
    if type(credits) not in (int, float) or credits < 0 or not math.isfinite(credits):
        credits = None
    return {
        "response_schema": schema_of(clean),
        "results": summaries,
        "failed_results": clean.get("failed_results"),
        "usage": usage,
        "credits": credits,
        "credits_source": "api_usage.credits" if credits is not None else "not_reported",
        "request_id": clean.get("request_id"),
        "api_response_time": clean.get("response_time"),
    }


def read_config(env_file):
    """Use only the designated .env, without modifying os.environ or interpolating it."""
    path = Path(env_file)
    if not path.is_file():
        return (
            "",
            (),
            {
                "credential_present": False,
                "env_mode_600": False,
                "preflight_error": "env_file_missing",
            },
        )
    try:
        mode_ok = stat.S_IMODE(path.stat().st_mode) == 0o600
        values = dotenv_values(path, interpolate=False)
    except OSError:
        return (
            "",
            (),
            {
                "credential_present": False,
                "env_mode_600": False,
                "preflight_error": "env_file_unreadable",
            },
        )
    key = (values.get("TAVILY_API_KEY") or "").strip()
    secret_values = tuple(
        value
        for name, value in values.items()
        if value and any(word in name.upper() for word in ("KEY", "TOKEN", "SECRET"))
    )
    secret_values = (*secret_values, key)
    return (
        key,
        secret_values,
        {"credential_present": bool(key), "env_mode_600": mode_ok, "preflight_error": None},
    )


def sdk_metadata():
    from tavily import TavilyClient

    return {
        "distribution": "tavily-python",
        "version": importlib.metadata.version("tavily-python"),
        "search_signature": str(inspect.signature(TavilyClient.search)),
        "extract_signature": str(inspect.signature(TavilyClient.extract)),
        "source": "installed SDK inspection; not a live API observation",
    }


def real_client(api_key):
    """Only run_probe's explicit execute path calls this factory."""
    import requests
    from tavily import TavilyClient

    session = requests.Session()
    session.trust_env = False
    return TavilyClient(
        api_key=api_key,
        api_base_url=API_BASE,
        session=session,
        proxies={"http": None, "https": None},
    )


def run_probe(
    *, execute=False, env_file=ROOT / ".env", report_dir=ROOT / "reports", client_factory=None
):
    key, secrets, preflight = read_config(env_file)
    report = {
        "task": "T0.5",
        "schema_version": 1,
        "mode": "execute" if execute else "dry_run",
        "created_at": datetime.now(UTC).isoformat(),
        "api_base": API_BASE,
        "preflight": preflight,
        "sdk": sdk_metadata(),
        "attempted_requests": 0,
        "api_checks_passed": False,
        "task_accepted": False,
        "task_acceptance_note": "Requires real successful probes and two factual FEEDBACK entries.",
        "operations": [],
        "credits_total_reported": None,
    }
    selected = operations()
    reason = (
        "execute_flag_required"
        if not execute
        else "missing_credential"
        if not key
        else "env_permissions_must_be_600"
        if not preflight["env_mode_600"]
        else None
    )
    code = NOT_EXECUTED
    if reason:
        report.update(status="not_executed", reason=reason)
        report["operations"] = [
            {
                **op,
                "status": "not_executed",
                "reason": reason,
                "elapsed_seconds": None,
                "credits": None,
            }
            for op in selected
        ]
    else:
        client = None
        try:
            client = (client_factory or real_client)(key)
            for operation in selected:
                started = time.monotonic()
                entry = {**operation, "status": "failed", "credits": None}
                report["attempted_requests"] += 1
                try:
                    response = getattr(client, operation["method"])(**operation["arguments"])
                    entry["status"], entry["reason"] = classify_response(operation, response)
                    entry.update(response_summary(response, secrets))
                except Exception as error:  # noqa: BLE001 - persist sanitized SDK errors at this boundary
                    entry.update(
                        reason="request_exception",
                        error_type=type(error).__name__,
                        error=str(redact(str(error), secrets))[:2000],
                    )
                entry["elapsed_seconds"] = time.monotonic() - started
                report["operations"].append(entry)
        except Exception as error:  # noqa: BLE001 - persist sanitized SDK errors at this boundary
            report["initialization_error"] = {
                "type": type(error).__name__,
                "message": str(redact(str(error), secrets))[:2000],
            }
            report["operations"] = [
                {
                    **op,
                    "status": "not_executed",
                    "reason": "client_initialization_failed",
                    "elapsed_seconds": None,
                    "credits": None,
                }
                for op in selected
            ]
        finally:
            session = getattr(client, "session", None)
            if session is not None:
                try:
                    session.close()
                except Exception as error:  # noqa: BLE001 - persist sanitized SDK errors at this boundary
                    report["client_close_error"] = str(redact(str(error), secrets))[:2000]
        passed = len(report["operations"]) == 4 and all(
            entry["status"] == "succeeded" for entry in report["operations"]
        )
        report.update(api_checks_passed=passed, status="succeeded" if passed else "failed")
        credits = [entry.get("credits") for entry in report["operations"]]
        if len(credits) == 4 and all(value is not None for value in credits):
            report["credits_total_reported"] = sum(credits)
        code = 0 if passed else 1
    report["exit_code"] = code
    report = redact(report, secrets)
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"probe-tavily-{timestamp}-{uuid.uuid4().hex[:8]}.json"
    with path.open("x") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return code, path, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="Send the four specified API requests"
    )
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args(argv)
    code, path, report = run_probe(
        execute=args.execute, env_file=args.env_file, report_dir=args.report_dir
    )
    print(
        json.dumps(
            {
                "report": str(path),
                "status": report["status"],
                "attempted_requests": report["attempted_requests"],
                "api_checks_passed": report["api_checks_passed"],
                "task_accepted": False,
            }
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
