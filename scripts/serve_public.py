"""Public origin; live work requires an explicit, verified FINAL48 demo allowance."""

import os
import shutil
from pathlib import Path

import uvicorn

from headroom.api.app import ApiSettings, create_app


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
    state = root / "runs/public-api"
    data = state / "submissions"
    for relative in (
        "public-evaluations.json",
        "published-evaluations/r6-20261027.json",
        "published-evaluations/r5-20261027.json",
    ):
        source = root / "public-evidence" / relative
        destination = data / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Only curated, versioned evidence is copied; never private API state.
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copyfile(source, temporary)
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
    application = create_app(settings, demo_allocation=demo) if demo else create_app(settings)
    uvicorn.run(application, host="127.0.0.1", port=8766, proxy_headers=False)


if __name__ == "__main__":
    main()
