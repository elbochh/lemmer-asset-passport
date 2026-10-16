"""Durable automatic guidance, processed inside the existing free web app."""

import asyncio
import os
from datetime import timedelta
from sqlalchemy import select, func, text, or_, and_
from .database import Session, GuidanceJob, ServiceRequest, Asset, AIRun, now
from .ai import recommend, cached_result


def enqueue(db, request):
    # Caller owns the request row, or just created it in this transaction.
    job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == request.id))
    if not job:
        job = GuidanceJob(workspace_id=request.workspace_id, request_id=request.id)
        db.add(job)
        db.flush()
    return job


def job_out(job):
    return (
        {"status": job.status, "message": job.message, "run_id": job.run_id}
        if job
        else None
    )


async def process_one(request_id=None):
    with Session() as db:
        job = db.scalar(
            select(GuidanceJob)
            .where(GuidanceJob.request_id == request_id if request_id else True)
            .where(
                or_(
                    and_(
                        GuidanceJob.status == "queued", GuidanceJob.updated_at <= now()
                    ),
                    and_(
                        GuidanceJob.status == "running",
                        GuidanceJob.updated_at < now() - timedelta(minutes=5),
                    ),
                )
            )
            .order_by(GuidanceJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        if job.attempts >= 2:
            job.status, job.message = (
                "unavailable",
                "Preparation was interrupted. You can retry from this request.",
            )
            db.commit()
            return True
        request = db.get(ServiceRequest, job.request_id)
        asset = db.get(Asset, request.asset_id)
        from .usage import workspace_context, cache_hit

        workspace_context.set(job.workspace_id)
        from .procedures import matches

        if any(
            exact
            for _, exact, _ in matches(db, job.workspace_id, asset, request.description)
        ):
            job.status, job.message = (
                "procedure",
                "An approved symptom checklist is available. Follow it without a model call; diagnosis still needs confirmation.",
            )
            job.run_id = None
            db.commit()
            return True
        cached = cached_result(db, job.workspace_id, asset, request.description)
        if cached:
            cache_hit()
            run = AIRun(
                workspace_id=job.workspace_id,
                request_id=request.id,
                mode="C",
                result={**cached, "automatic": True, "problem": request.description},
            )
            db.add(run)
            db.flush()
            job.status, job.message, job.run_id = (
                "ready",
                "Previously reviewed guidance reused. No new model call.",
                run.id,
            )
            job.updated_at = now()
            db.commit()
            return True
        from .usage import check_budget

        try:
            check_budget()
            budget_ok = True
        except RuntimeError:
            budget_ok = False
        if not os.getenv("GEMINI_API_KEY") or not budget_ok:
            job.status, job.message = (
                "unavailable",
                "Automatic guidance is unavailable or the demo’s daily AI limit has been reached. The original report is still available.",
            )
            db.commit()
            return True
        request = db.get(ServiceRequest, job.request_id)
        asset = db.get(Asset, request.asset_id)
        problem = request.description
        run = AIRun(
            workspace_id=job.workspace_id,
            request_id=request.id,
            mode="C",
            result={"status": "running", "automatic": True},
        )
        db.add(run)
        db.flush()
        job.status, job.run_id = "running", run.id
        job.attempts += 1
        job.updated_at = now()
        db.commit()
        try:
            result = await recommend(db, job.workspace_id, asset, problem, "C")
            db.refresh(job)
            db.refresh(request)
            if (
                job.run_id != run.id
                or request.description != problem
                or request.status == "Closed"
            ):
                run.result = {"status": "superseded", "automatic": True}
                db.commit()
                return True
            run.result = {**result, "problem": problem, "automatic": True}
            job.status, job.message = (
                "ready",
                "AI evidence review complete. Not human approval.",
            )
        except Exception as error:
            db.rollback()
            db.refresh(job)
            db.refresh(request)
            if (
                job.run_id != run.id
                or request.description != problem
                or request.status == "Closed"
            ):
                run.result = {"status": "superseded", "automatic": True}
                db.commit()
                return True
            message = (
                str(error)
                if isinstance(error, RuntimeError)
                else "The model review could not complete."
            )
            print(
                "Automatic guidance failed:", run.id, type(error).__name__, flush=True
            )
            run.result = {"status": "error", "automatic": True, "error": message}
            if job.attempts < 2:
                job.status, job.message = (
                    "queued",
                    "A model check could not finish. Retrying automatically once…",
                )
            else:
                job.status, job.message = (
                    "unavailable",
                    message
                    + " No unchecked recommendation was released. You can retry below.",
                )
        job.updated_at = (
            now() + timedelta(seconds=15) if job.status == "queued" else now()
        )
        db.commit()
        return True


async def worker():
    while True:
        try:
            worked = await process_one()
        except Exception as error:
            print("Guidance worker:", type(error).__name__, flush=True)
            worked = False
        await asyncio.sleep(0.2 if worked else 2)
