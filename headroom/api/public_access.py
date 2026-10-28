"""Public demo input and client-address boundaries."""

import ipaddress
import secrets
from decimal import Decimal

from fastapi import HTTPException


def judge_authorized(settings, request):
    configured = settings.judge_token
    supplied = request.headers.get("authorization", "")
    prefix = "Bearer "
    return bool(
        configured
        and supplied.startswith(prefix)
        and secrets.compare_digest(supplied[len(prefix) :].encode(), configured.encode())
    )


def client_address(settings, request):
    peer = request.client.host if request.client else "unknown"
    if settings.trust_tailscale_funnel:
        # Tailscale 1.104.4 overwrites these headers in its Rewrite callback.
        # The listener must remain loopback-only; never trust an internet peer.
        if peer not in {"127.0.0.1", "::1"}:
            raise HTTPException(403, "This public service requires its HTTPS tunnel")
        if (
            request.headers.get("tailscale-funnel-request") != "?1"
            or request.headers.get("x-forwarded-proto") != "https"
            or request.headers.get("x-forwarded-host", "").lower().removesuffix(":443")
            != settings.public_host
        ):
            raise HTTPException(400, "The public request is missing tunnel information")
        values = request.headers.getlist("x-forwarded-for")
        if len(values) != 1:
            raise HTTPException(400, "The public request has an invalid client address")
        try:
            return str(ipaddress.ip_address(values[0]))
        except ValueError:
            raise HTTPException(400, "The public request has an invalid client address") from None
    if settings.trust_cloudflared and peer in {"127.0.0.1", "::1"}:
        try:
            return str(ipaddress.ip_address(request.headers.get("cf-connecting-ip", "")))
        except ValueError:
            raise HTTPException(
                400, "Trusted tunnel request lacks a valid client address"
            ) from None
    return peer


def protect_public_submission(settings, request, submission):
    """Only examples are anonymous; a judge may supply a script, never a repository."""
    if not settings.public_host:
        return submission
    if any(value is not None for value in (submission.repo, submission.ref, submission.cmd)):
        raise HTTPException(403, "The public demo accepts examples or judge-provided scripts")
    if submission.script_text is not None and not judge_authorized(settings, request):
        raise HTTPException(
            401,
            "A judge access token is required to submit your own script",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Public callers cannot raise the server's per-run allowance.
    return submission.model_copy(
        update={"budget": str(min(settings.public_run_budget, Decimal(submission.budget)))}
    )
