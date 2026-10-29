"""Public origin; live work requires an explicit, verified FINAL48 demo allowance."""

import os
from pathlib import Path

import uvicorn

from headroom.api.app import ApiSettings, create_app
from headroom.api.evaluations import _campaign, _registry
from headroom.api.security import open_regular


def main():
    root = Path(__file__).resolve().parents[1]
    hostname = os.environ.get("HEADROOM_PUBLIC_HOST", "")
    if not hostname:
        raise SystemExit("HEADROOM_PUBLIC_HOST must be configured before public startup")
    if os.environ.get("HEADROOM_TRUST_CLOUDFLARED") == "true":
        raise SystemExit("The Funnel origin must not trust Cloudflare headers")
    requested = os.environ.get("HEADROOM_RUN_SUBMISSIONS_ENABLED", "false")
    if requested not in {"true", "false"}:
        raise SystemExit("Use explicit true or false; the default public mode is read-only")
    demo = None
    judge = None
    if requested == "true":
        receipt_path = os.environ.get("HEADROOM_PUBLIC_ALLOCATION_RECEIPT")
        if not receipt_path:
            raise SystemExit("The read-only default requires an explicit public allocation receipt")
        from headroom.acceptance.demo_binding import DemoAllocation

        try:
            demo = DemoAllocation(receipt_path, project_root=root)
        except (OSError, ValueError):
            raise SystemExit("The public allocation could not be verified") from None
        # Process-local selection also keeps availability observations on this pool.
        os.environ["HEADROOM_BUDGET_DB_PATH"] = demo.receipt["ledger_path"]
        os.environ["HEADROOM_DAILY_BUDGET_USD"] = demo.receipt["amounts"]["daily_limit_usd"]
        judge_receipt_path = os.environ.get("HEADROOM_JUDGE_ALLOCATION_RECEIPT")
        if judge_receipt_path:
            from headroom.acceptance.judge_binding import JudgeAllocation

            try:
                judge = JudgeAllocation(judge_receipt_path, project_root=root)
            except (OSError, ValueError):
                raise SystemExit("The judge allocation could not be verified") from None
    state = root / "runs/public-api"
    data = state / "submissions"
    source_root = root / "public-evidence"
    entries = _registry(source_root)
    # Validate every curated result before changing any published file.
    payloads = {}
    for entry in entries:
        _campaign(source_root, entry)
        relative = "published-evaluations/" + entry["id"] + ".json"
        with open_regular(source_root, relative, 2 * 1024 * 1024) as handle:
            payloads[relative] = handle.read()
    with open_regular(source_root, "public-evaluations.json", 65536) as handle:
        payloads["public-evaluations.json"] = handle.read()
    # Results first, manifest last: a restart must not publish dangling entries.
    for relative, content in payloads.items():
        destination = data / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.chmod(0o600)
        temporary.replace(destination)
    settings = ApiSettings(
        project_root=root,
        data_root=data,
        db_path=state / "headroom.db",
        run_root=state / "jobs",
        public_host=hostname,
        trust_tailscale_funnel=True,
        run_submissions_enabled=demo is not None,
        snapshot_submissions_enabled=False,
        run_submission_disabled_reason="Live analysis is temporarily paused.",
    )
    application = (
        create_app(settings, demo_allocation=demo, judge_allocation=judge)
        if judge is not None
        else create_app(settings, demo_allocation=demo)
        if demo is not None
        else create_app(settings)
    )
    uvicorn.run(application, host="127.0.0.1", port=8766, proxy_headers=False)


if __name__ == "__main__":
    main()
