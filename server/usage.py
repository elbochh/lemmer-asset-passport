"""Global and per-workspace reservations before every external model request.
A database advisory lock makes limits work across concurrent web workers.
"""

import os, time
from datetime import timedelta
from contextvars import ContextVar
from sqlalchemy import select, func, text
from .database import Session, now
from .operations_models import AIUsage

workspace_context = ContextVar("ai_workspace", default=None)


def limits():
    return {
        "provider_calls_per_day": int(
            os.getenv("AI_PROVIDER_DAILY_LIMIT", os.getenv("AI_DAILY_LIMIT", "90"))
        ),
        "workspace_calls_per_day": int(os.getenv("AI_WORKSPACE_DAILY_LIMIT", "30")),
        "reserved_tokens_per_day": int(os.getenv("AI_TOKEN_DAILY_LIMIT", "1000000")),
        "concurrent_provider_calls": int(os.getenv("AI_CONCURRENCY", "2")),
        "paid_fallback": False,
        "pricing_mode": "Free-tier key required; provider billing is controlled in the provider account, not inferred by this app.",
    }


def reserve(operation, model, tokens):
    limit = limits()
    wid = workspace_context.get()
    with Session() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(7771115)"))
        day = now() - timedelta(days=1)
        q = select(AIUsage).where(
            AIUsage.created_at >= day, AIUsage.status != "cache_hit"
        )
        rows = list(db.scalars(q))
        if len(rows) >= limit["provider_calls_per_day"] or (
            wid
            and sum(x.workspace_id == wid for x in rows)
            >= limit["workspace_calls_per_day"]
        ):
            raise RuntimeError(
                "Daily model request limit reached. Approved procedures and service records remain available."
            )
        if (
            sum(x.reserved_tokens for x in rows) + tokens
            > limit["reserved_tokens_per_day"]
        ):
            raise RuntimeError(
                "Daily model token reservation limit reached. Use the approved library or record findings manually."
            )
        if (
            sum(
                x.status == "reserved" and x.created_at > now() - timedelta(minutes=3)
                for x in rows
            )
            >= limit["concurrent_provider_calls"]
        ):
            raise RuntimeError(
                "Model processing is busy. Please retry later; normal service work remains available."
            )
        if tokens > 100000:
            raise RuntimeError(
                "Evidence exceeds the bounded model input size. Narrow the source set."
            )
        entry = AIUsage(
            workspace_id=wid, operation=operation, model=model, reserved_tokens=tokens
        )
        db.add(entry)
        db.commit()
        return entry.id


def finish(key, status, elapsed, metadata=None):
    metadata = metadata or {}
    with Session() as db:
        x = db.get(AIUsage, key)
        x.status = status
        x.latency_ms = int(elapsed * 1000)
        x.input_tokens = metadata.get("promptTokenCount")
        x.output_tokens = metadata.get("candidatesTokenCount")
        db.commit()


def cache_hit(model="guidance"):
    with Session() as db:
        db.add(
            AIUsage(
                workspace_id=workspace_context.get(),
                operation="cache",
                model=model,
                status="cache_hit",
            )
        )
        db.commit()


def check_budget():
    """Early UX check; reserve() still enforces the same limits atomically per call."""
    limit = limits()
    wid = workspace_context.get()
    with Session() as db:
        rows = list(
            db.scalars(
                select(AIUsage).where(
                    AIUsage.created_at >= now() - timedelta(days=1),
                    AIUsage.status != "cache_hit",
                )
            )
        )
        if (
            len(rows) >= limit["provider_calls_per_day"]
            or (
                wid
                and sum(x.workspace_id == wid for x in rows)
                >= limit["workspace_calls_per_day"]
            )
            or sum(x.reserved_tokens for x in rows) >= limit["reserved_tokens_per_day"]
        ):
            raise RuntimeError(
                "Daily model processing limit reached. Approved procedures, records and manual work remain available. No paid fallback was used."
            )
