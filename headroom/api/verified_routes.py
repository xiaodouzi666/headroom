"""Read-only routes for explicitly enabled, curated historical runs."""

import hashlib
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import ValidationError

from headroom.api.security import RUN_ID, open_regular
from headroom.api.verified import load_verified

DOWNLOAD_TYPES = {
    "patch": ("patch.diff", "text/plain; charset=utf-8"),
    "report_json": ("report.json", "application/json"),
    "report_markdown": ("report.md", "text/plain; charset=utf-8"),
}


def register_verified(app, settings):
    root = Path(settings.project_root) / "public-evidence"

    def catalog():
        if not settings.verified_runs_enabled:
            raise HTTPException(404, "Verified runs are not available")
        try:
            return load_verified(root)
        except (OSError, ValueError, ValidationError):
            raise HTTPException(503, "Published run evidence is temporarily unavailable") from None

    @app.get("/api/verified")
    def verified_runs():
        document = catalog().model_dump()
        document["publication_status"] = "published"
        for run in document["runs"]:
            for kind, asset in run["downloads"].items():
                asset["url"] = f"/api/verified/{run['run_id']}/download/{kind}"
        return document

    @app.get("/api/verified/{run_id}/download/{kind}")
    def verified_download(run_id: str, kind: str):
        document = catalog()
        if not RUN_ID.fullmatch(run_id) or kind not in DOWNLOAD_TYPES:
            raise HTTPException(404, "Published artifact not found")
        run = next((row for row in document.runs if row.run_id == run_id), None)
        if run is None:
            # Only the fixed, previously published catalog is eligible. Never
            # discover private historical runs or serve loose files by run ID.
            try:
                history = load_verified(root, historical=True)
            except FileNotFoundError:
                history = None
            except (OSError, ValueError, ValidationError):
                raise HTTPException(503, "Published artifact is temporarily unavailable") from None
            if history is not None:
                run = next((row for row in history.runs if row.run_id == run_id), None)
        if run is None or kind not in run.downloads:
            raise HTTPException(404, "Published artifact not found")
        asset = run.downloads[kind]
        try:
            with open_regular(root, asset.path, max_bytes=8 * 1024 * 1024) as handle:
                raw = handle.read()
            if len(raw) != asset.bytes or hashlib.sha256(raw).hexdigest() != asset.sha256:
                raise ValueError("Artifact changed after publication")
        except (OSError, ValueError):
            raise HTTPException(503, "Published artifact is temporarily unavailable") from None
        filename, media_type = DOWNLOAD_TYPES[kind]
        return Response(
            raw,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{run_id}-{filename}"'},
        )
