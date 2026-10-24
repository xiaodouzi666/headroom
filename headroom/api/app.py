"""Local FastAPI surface; no listener or worker starts merely by importing this module."""

import asyncio
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import subprocess
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from functools import partial
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from headroom.api.availability import AvailabilityMonitor
from headroom.api.evaluations import register_evaluations
from headroom.api.queue import TERMINAL, AdmissionError, RunQueue
from headroom.api.security import ARTIFACTS, RUN_ID, job_directory, open_regular
from headroom.lab.runner import PROJECT_ROOT
from headroom.orchestrator import FixRequest, Policy
from headroom.repository import (
    command_argv,
    parse_watch_command,
    preparation_remaining,
    prepare_repository,
    validate_repository,
)
from headroom.runtime import read_live_profile
from headroom.store.db import Store
from headroom.verify.compare import parse_target
from headroom.verify.policy import scan_source_forbidden

COOKIE = "headroom_session"
MAX_SCRIPT_BYTES = 1024 * 1024
MAX_BODY_BYTES = 6 * MAX_SCRIPT_BYTES + 65536


@dataclass
class ApiSettings:
    project_root: Path = PROJECT_ROOT
    data_root: Path | None = None
    db_path: Path | None = None
    run_root: Path | None = None
    web_dist: Path | None = None
    runtime_profile: str | None = None
    runtime_configured: bool = False
    public_host: str | None = None
    trust_cloudflared: bool = False
    deadline_seconds: float = 600
    shutdown_grace_seconds: float = 5
    event_poll_seconds: float = 0.1
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]", "testserver")

    def __post_init__(self):
        self.public_host = self.public_host or os.environ.get("HEADROOM_PUBLIC_HOST")
        self.trust_cloudflared = (
            self.trust_cloudflared or os.environ.get("HEADROOM_TRUST_CLOUDFLARED") == "true"
        )
        if self.public_host:
            if (
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", self.public_host)
                or ".." in self.public_host
            ):
                raise ValueError("Public host must be a bare lowercase DNS hostname")
            self.allowed_hosts = (*self.allowed_hosts, self.public_host)
        if self.trust_cloudflared and not self.public_host:
            raise ValueError("Trusted tunnel mode requires an explicit public hostname")
        self.project_root = Path(self.project_root).resolve()
        self.data_root = Path(self.data_root or self.project_root / "runs/api").resolve()
        self.db_path = Path(self.db_path or self.project_root / "runs/headroom.db").resolve()
        self.run_root = Path(self.run_root or self.project_root / "runs/jobs").resolve()
        self.web_dist = Path(self.web_dist or self.project_root / "web/dist").resolve()
        if not 0 < self.deadline_seconds <= 600 or not 0 < self.shutdown_grace_seconds <= 10:
            raise ValueError("Deadline must be at most 600 seconds and cleanup grace at most 10")
        if not 0 < self.event_poll_seconds <= 5:
            raise ValueError("Event polling interval must be positive and at most five seconds")


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    script_text: str | None = None
    example_id: str | None = Field(default=None, max_length=100)
    repo: str | None = Field(default=None, max_length=1000)
    ref: str | None = Field(default=None, max_length=200)
    cmd: str | None = Field(default=None, max_length=2000)
    target: str = "fix-oom"
    search_mode: Literal["until_target", "bounded_pareto"] = "until_target"
    policy: Policy = Field(default_factory=Policy)
    budget: str = "0.6"


def _catalog(settings):
    root = settings.project_root
    try:
        with open_regular(root / "scenarios", "INDEX.yaml", 1024 * 1024) as handle:
            document = json.load(handle)
    except (OSError, ValueError):
        return {}
    result = {}
    for row in document.get("scenarios", []):
        identifier = row.get("id")
        if not isinstance(identifier, str) or "/" in identifier or not identifier.startswith("s"):
            continue
        relative = row.get("script")
        if relative != f"scenarios/{identifier}/train.py":
            continue
        try:
            with open_regular(
                root / "scenarios", identifier + "/train.py", MAX_SCRIPT_BYTES
            ) as handle:
                text = handle.read().decode("utf-8")
        except (OSError, ValueError, UnicodeError):
            continue
        result[identifier] = {
            "id": identifier,
            "script_text": text,
            "title": identifier.replace("_", " "),
            "expected_mode": row.get("expected_mode"),
            "root_cause": row.get("root_cause"),
            "baseline_verified": row.get("gpu_baseline_verified") is True,
        }
    return result


def _public_run(row):
    fields = (
        "run_id",
        "status",
        "created_at",
        "updated_at",
        "target",
        "search_mode",
        "policy",
        "target_met",
        "reason",
        "provenance",
        "elapsed_seconds",
        "api_worker_finished",
        "api_cleanup_verified",
        "api_admitted_at",
        "api_deadline_at",
        "api_execution_limit_seconds",
        "api_cleanup_grace_seconds",
        "api_report_pending",
        "api_report_ready",
        "api_report_error",
    )
    return {key: row.get(key) for key in fields if key in row}


def _stream_file(handle):
    try:
        while chunk := handle.read(65536):
            yield chunk
    finally:
        handle.close()


def _prepare_submission(settings, submission, source, run_id, *, deadline):
    preparation_remaining(deadline)
    repository_input = submission.repo is not None
    folder = settings.data_root / "uploads" / run_id
    profile, arguments, execution_argv = None, [], None
    if repository_input:
        prepared = prepare_repository(
            submission.repo, submission.ref, submission.cmd, destination=folder, deadline=deadline
        )
        scanned = scan_source_forbidden(
            prepared.source_root, source_profile=prepared.source_profile, sandboxed=True
        )
        if not scanned.allowed:
            raise ValueError("Repository source rejected by static policy")
        folder, script = prepared.source_root, prepared.script
        profile, arguments = prepared.source_profile, list(prepared.script_args)
        execution_argv = list(prepared.execution_argv)
    else:
        folder.mkdir(parents=True, exist_ok=False, mode=0o700)
        script = folder / "train.py"
        with script.open("x") as handle:
            handle.write(source)
    preparation_remaining(deadline)
    return FixRequest(
        script=str(script),
        source_root=str(folder),
        source_profile=profile,
        script_args=arguments,
        execution_argv=execution_argv,
        repository_mode=repository_input,
        target=submission.target,
        search_mode=submission.search_mode,
        policy=submission.policy,
        budget_usd=submission.budget,
        max_steps=20,
        max_seconds=180,
        device="cuda",
        runtime_profile=settings.runtime_profile,
    )


def create_app(settings=None, *, worker=None, worker_mode=None, availability_monitor=None):
    settings = settings or ApiSettings()
    settings.data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    settings.run_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    store = Store(settings.db_path)
    mode = worker_mode or ("thread" if worker is not None else "process")
    if mode not in {"thread", "process"} or (mode == "thread" and worker is None):
        raise ValueError("Thread mode is only available with an explicit offline test worker")
    queue = RunQueue(
        store,
        run_root=settings.run_root,
        admission_path=settings.data_root / "admissions.db",
        worker=worker,
        mode=mode,
        deadline=settings.deadline_seconds,
        grace=settings.shutdown_grace_seconds,
    )
    catalog = _catalog(settings)
    availability = availability_monitor or AvailabilityMonitor(
        settings, enabled=worker is None, profile_loader=read_live_profile
    )

    @asynccontextmanager
    async def lifespan(_):
        queue.start()
        availability.snapshot()
        try:
            yield
        finally:
            availability.close()
            queue.close()
            if (
                not queue.thread.is_alive()
                and not queue.expiry_thread.is_alive()
                and not queue.preparing
            ):
                store.close()

    app = FastAPI(title="Headroom", lifespan=lifespan)
    # Starlette excludes text/event-stream, preserving immediate SSE delivery.
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.state.store, app.state.queue, app.state.settings = store, queue, settings
    app.state.availability = availability
    register_evaluations(app, settings.data_root)

    @app.middleware("http")
    async def local_session(request, call_next):
        token = request.cookies.get(COOKIE, "")
        fresh = not bool(RUN_ID.fullmatch(token))
        if fresh:
            token = secrets.token_hex(16)
        request.state.owner = hashlib.sha256(token.encode()).hexdigest()
        response = await call_next(request)
        if fresh:
            response.set_cookie(
                COOKIE,
                token,
                httponly=True,
                samesite="strict",
                secure=bool(settings.public_host),
                max_age=86400,
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def accessible(run_id, request):
        if not RUN_ID.fullmatch(run_id):
            raise HTTPException(404, "Run not found")
        row = store.get_run(run_id)
        if row is None or (
            row.get("api_owner") != request.state.owner and not row.get("public_replay")
        ):
            raise HTTPException(404, "Run not found")
        return row

    @app.post("/api/runs", status_code=202)
    async def submit(request: Request):
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.url.netloc:
            raise HTTPException(403, "Cross-origin submissions are not allowed")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_BODY_BYTES:
                raise HTTPException(413, "Request exceeds upload limit")
        try:
            submission = Submission.model_validate_json(bytes(data))
            parse_target(submission.target)
            budget = Decimal(submission.budget)
            if not budget.is_finite() or not Decimal(0) < budget <= Decimal(5):
                raise ValueError("Budget must be positive and at most 5 USD")
        except (ValidationError, ValueError, InvalidOperation):
            raise HTTPException(400, "Invalid run request or budget") from None
        repository_input = any(
            value is not None for value in (submission.repo, submission.ref, submission.cmd)
        )
        if repository_input:
            if (
                not all((submission.repo, submission.ref, submission.cmd))
                or submission.script_text is not None
                or submission.example_id is not None
            ):
                raise HTTPException(400, "Repository input requires exactly repo, ref, cmd")
            try:
                validate_repository(submission.repo, submission.ref)
                parsed = parse_watch_command(command_argv(submission.cmd))
                if not parsed.repair_supported:
                    raise ValueError(parsed.repair_reason)
            except (ValueError, TypeError):
                raise HTTPException(
                    400,
                    "Use a public GitHub URL, exact commit SHA and a supported Python script/module argv",
                ) from None
            source = None
        else:
            if (submission.script_text is None) == (submission.example_id is None):
                raise HTTPException(400, "Provide exactly one of script_text or example_id")
            if submission.example_id is not None:
                example = catalog.get(submission.example_id)
                if example is None:
                    raise HTTPException(400, "Unknown example")
                source = example["script_text"]
            else:
                source = submission.script_text
            try:
                source_bytes = source.encode("utf-8")
            except UnicodeError:
                raise HTTPException(400, "Script must contain valid UTF-8 text") from None
            if not source_bytes or len(source_bytes) > MAX_SCRIPT_BYTES:
                raise HTTPException(413, "Script must be nonempty UTF-8 text of at most 1 MiB")
            scanned = scan_source_forbidden({"train.py": source})
            if not scanned.allowed:
                raise HTTPException(
                    400,
                    {
                        "reason": "Script rejected by static policy",
                        "issues": [
                            {"code": i.code, "message": i.message, "line": i.line}
                            for i in scanned.issues
                        ],
                    },
                )
        run_id = uuid4().hex

        prepare = partial(_prepare_submission, settings, submission, source, run_id)

        client_ip = request.client.host if request.client else "unknown"
        if settings.trust_cloudflared and client_ip in {"127.0.0.1", "::1"}:
            try:
                client_ip = str(ipaddress.ip_address(request.headers.get("cf-connecting-ip", "")))
            except ValueError:
                raise HTTPException(
                    400, "Trusted tunnel request lacks a valid client address"
                ) from None
        try:
            position = await asyncio.to_thread(
                queue.submit,
                run_id,
                {
                    "kind": "repository"
                    if repository_input
                    else ("example" if submission.example_id else "upload"),
                    "example_id": submission.example_id,
                    "target": submission.target,
                    "search_mode": submission.search_mode,
                    "policy": submission.policy.model_dump(),
                },
                request.state.owner,
                client_ip,
                prepare,
            )
        except AdmissionError as error:
            raise HTTPException(error.status, str(error), headers={"Retry-After": "60"}) from None
        except (OSError, ValueError, subprocess.SubprocessError):
            raise HTTPException(
                400, "Repository preparation or static policy validation failed"
            ) from None
        return {
            "run_id": run_id,
            "status": "queued",
            "queue_position": position,
            "run_url": f"/api/runs/{run_id}",
            "events_url": f"/api/runs/{run_id}/events",
        }

    @app.get("/api/runs")
    def runs(request: Request):
        rows = [
            _public_run(r)
            for r in store.list_runs(1000)
            if r.get("api_owner") == request.state.owner
        ]
        return {"runs": rows, "queue": queue.snapshot()}

    @app.get("/api/runs/{run_id}")
    def run(run_id: str, request: Request):
        row = accessible(run_id, request)
        result = _public_run(row)
        result["usage"] = store.usage(run_id)
        result["artifacts"] = {}
        for name, (relative, _) in ARTIFACTS.items():
            try:
                with open_regular(job_directory(settings.run_root, run_id), relative):
                    result["artifacts"][name] = f"/api/runs/{run_id}/{name}"
            except (OSError, ValueError):
                continue
        return result

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, request: Request):
        accessible(run_id, request)
        try:
            after = int(
                request.headers.get("last-event-id", request.query_params.get("after", "0"))
            )
            if after < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "Invalid Last-Event-ID") from None

        async def stream():
            cursor = after
            idle = 0
            while not await request.is_disconnected():
                rows = store.events(run_id, after_sequence=cursor)
                for row in rows:
                    cursor = row["sequence"]
                    payload = {k: row[k] for k in ("sequence", "kind", "data", "created_at")}
                    yield f"id: {cursor}\nevent: {row['kind']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                state = store.get_run(run_id)
                if not state.get("api_report_pending", False) and (
                    state.get("api_worker_finished")
                    or (state.get("public_replay") is True and state["status"] in TERMINAL)
                    or (queue.snapshot()["halted"] and state["status"] in TERMINAL)
                ):
                    # Re-read after observing terminal state to include events committed
                    # between the first query and the final status update.
                    tail = store.events(run_id, after_sequence=cursor)
                    for row in tail:
                        cursor = row["sequence"]
                        payload = {k: row[k] for k in ("sequence", "kind", "data", "created_at")}
                        yield f"id: {cursor}\nevent: {row['kind']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    yield (
                        "event: stream.end\ndata: "
                        + json.dumps(
                            {
                                "status": state["status"],
                                "cleanup_verified": state.get("api_cleanup_verified"),
                                "last_event_id": cursor,
                            }
                        )
                        + "\n\n"
                    )
                    return
                idle += 1
                if idle % 100 == 0:
                    yield ": keepalive\n\n"
                await asyncio.sleep(settings.event_poll_seconds)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    @app.get("/api/runs/{run_id}/{artifact}")
    def download(run_id: str, artifact: str, request: Request):
        accessible(run_id, request)
        if artifact not in ARTIFACTS:
            raise HTTPException(404, "Artifact not found")
        relative, media = ARTIFACTS[artifact]
        try:
            handle = open_regular(job_directory(settings.run_root, run_id), relative)
        except (OSError, ValueError):
            raise HTTPException(404, "Artifact unavailable") from None
        return StreamingResponse(
            _stream_file(handle),
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{artifact}"'},
        )

    @app.get("/api/runs/{run_id}/configurations/{tier}/{artifact}")
    def configuration_download(run_id: str, tier: str, artifact: str, request: Request):
        accessible(run_id, request)
        media = {
            "patch.diff": "text/plain",
            "env.sh": "text/plain",
            "cli.json": "application/json",
            "manifest.json": "application/json",
        }
        if not re.fullmatch(r"round-0[1-6]", tier) or artifact not in media:
            raise HTTPException(404, "Configuration artifact not found")
        try:
            handle = open_regular(
                job_directory(settings.run_root, run_id), f"configurations/{tier}/{artifact}"
            )
        except (OSError, ValueError):
            raise HTTPException(404, "Configuration artifact unavailable") from None
        return StreamingResponse(
            _stream_file(handle),
            media_type=media[artifact],
            headers={"Content-Disposition": f'attachment; filename="{tier}-{artifact}"'},
        )

    @app.get("/api/examples")
    def examples():
        return {
            "examples": [
                {k: v for k, v in row.items() if k != "script_text"} for row in catalog.values()
            ]
        }

    @app.get("/api/usage")
    def usage(request: Request):
        rows = [row for row in store.list_runs(1000) if row.get("api_owner") == request.state.owner]
        items = [{"run_id": row["run_id"], **store.usage(row["run_id"])} for row in rows]
        unknown = sum(item["unknown_cost_calls"] for item in items)
        with localcontext() as context:
            context.prec = 220
            subtotal = sum((Decimal(item["known_cost_usd"]) for item in items), Decimal(0))
        return {
            "runs": items,
            "scope": "current_session",
            "calls": sum(item["calls"] for item in items),
            "known_cost_usd": str(subtotal),
            "total_cost_usd": None if unknown else str(subtotal),
            "unknown_cost_calls": unknown,
            "complete": unknown == 0,
            "local_budget": availability.snapshot()["local_budget"],
        }

    @app.get("/api/replays")
    def replays():
        rows = [
            _public_run(row)
            for row in store.list_runs(1000)
            if row.get("public_replay") is True and row["status"] in TERMINAL
        ]
        return {
            "replays": rows,
            "count": len(rows),
            "note": "Only explicitly curated existing runs are listed; no synthetic replay is invented.",
        }

    @app.get("/api/health")
    def health():
        store.list_runs(1)
        observed = availability.snapshot()
        return {
            "status": "ok",
            "db": "ok",
            "queue": queue.snapshot(),
            **observed,
            "deployment": "public_host_configured" if settings.public_host else "localhost",
            "authentication": "local_session_only",
        }

    if settings.web_dist.is_dir():

        @app.get("/{path:path}")
        def web(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Not found")
            relative = path or "index.html"
            try:
                handle = open_regular(settings.web_dist, relative, 16 * 1024 * 1024)
            except (OSError, ValueError):
                if Path(relative).suffix:
                    raise HTTPException(404, "Not found") from None
                try:
                    handle = open_regular(settings.web_dist, "index.html", 16 * 1024 * 1024)
                    relative = "index.html"
                except (OSError, ValueError):
                    raise HTTPException(404, "Not found") from None
            return StreamingResponse(
                _stream_file(handle),
                media_type=mimetypes.guess_type(relative)[0] or "application/octet-stream",
            )

    return app


def main():
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000, proxy_headers=False)


if __name__ == "__main__":
    main()
