"""Dedicated read-only public origin; live workers remain disabled."""

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
    if os.environ.get("HEADROOM_RUN_SUBMISSIONS_ENABLED", "false") != "false":
        raise SystemExit("This public launcher permits read-only operation only")
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
        run_submissions_enabled=False,
        snapshot_submissions_enabled=False,
        verified_runs_enabled=False,
        run_submission_disabled_reason="Live analysis is temporarily paused.",
    )
    uvicorn.run(create_app(settings), host="127.0.0.1", port=8766, proxy_headers=False)


if __name__ == "__main__":
    main()
