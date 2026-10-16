import os, json, hmac, hashlib, secrets, time, csv, io, asyncio
from contextlib import suppress
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import timedelta, date
from typing import Literal
from urllib.parse import urlparse
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, text
from .database import (
    Base,
    engine,
    Session,
    Workspace,
    Asset,
    ServiceRequest,
    Event,
    KnowledgeCase,
    AIRun,
    Notification,
    IntakeDocument,
    GuidanceJob,
    now,
)
from .seed import seed_workspace, TECHNICIANS, RECEPTIONISTS
from .expansion_models import SchemaVersion, ComponentRecord, AssetOwner
from .expansion import attach as attach_expansion, seed_expansion
from .ai import documents, parts_for, recommend, cached_result, GENERATOR, JUDGE

from .guidance import enqueue, job_out, worker
from .access import (
    require,
    role,
    STAFF_ROLES,
    DEMO_ADMIN,
    technician_names,
    audit,
    ensure_site,
)
from .identity import reference_key, model_name
from .history import effective_report
from .ai import POLICY, visible_result

ROOT = Path(__file__).resolve().parents[1]
SECRET = os.getenv("SESSION_SECRET")
if not SECRET:
    raise RuntimeError("SESSION_SECRET is required. Configure .env before starting.")
PROD = os.getenv("ENVIRONMENT") == "production"


@asynccontextmanager
async def lifespan(app):
    from .migrations import migrate

    migrate()
    with engine.begin() as c:
        c.execute(
            text(
                "CREATE INDEX IF NOT EXISTS case_search_idx ON knowledge_cases USING gin(to_tsvector('english', symptom || ' ' || diagnosis || ' ' || repair))"
            )
        )
    task = (
        asyncio.create_task(worker())
        if os.getenv("AUTO_GUIDANCE_WORKER", "1") == "1"
        else None
    )
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="Lemmer Asset Passport",
    version="3.0",
    lifespan=lifespan,
    docs_url=None if PROD else "/api/docs",
)


@app.middleware("http")
async def security(request, call_next):
    if (
        request.url.path in ["/api/auth/login", "/api/auth/signup"]
        and request.method == "POST"
    ):
        from .auth_limits import allow

        if not allow(request.client.host if request.client else "unknown"):
            return JSONResponse(
                {"detail": "Too many sign-in attempts. Please retry in 15 minutes."},
                status_code=429,
            )
    if request.method not in ["GET", "HEAD", "OPTIONS"]:
        origin = request.headers.get("origin")
        if (
            origin
            and urlparse(origin).hostname
            != request.headers.get("host", "").split(":")[0]
        ):
            return JSONResponse(
                {"detail": "Request origin is not allowed."}, status_code=403
            )
        if int(request.headers.get("content-length", "0")) > 3_000_000:
            return JSONResponse({"detail": "Request too large."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


def dbdep():
    with Session() as db:
        yield db


def token(wid, tech):
    s = f"{wid}|{tech}|{int(time.time()) + 60 * 60 * 24 * 30}"
    return s + "|" + hmac.new(SECRET.encode(), s.encode(), hashlib.sha256).hexdigest()


def claims(request: Request):
    with Session() as db:
        w = app.state.portal_identity(request, db)
        require(w, *STAFF_ROLES)
        return w


def cookie(response, wid, tech):
    response.set_cookie(
        "lemmer_session",
        token(wid, tech),
        httponly=True,
        secure=PROD,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )


def owned(db, cls, pk, wid, lock=False):
    q = select(cls).where(cls.id == pk, cls.workspace_id == wid)
    if lock:
        q = q.with_for_update()
    item = db.scalar(q)
    if not item:
        raise HTTPException(404, "Record not found in this workspace.")
    return item


def serialize(row):
    return {
        c.name: (v.isoformat() if hasattr(v, "isoformat") else v)
        for c in row.__table__.columns
        if (v := getattr(row, c.name)) is not None and c.name != "workspace_id"
    }


def req_out(db, r):
    data = serialize(r)
    data["guidance"] = job_out(
        db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == r.id))
    )
    data["asset"] = serialize(db.get(Asset, r.asset_id))
    data["documents"] = [
        {
            "id": d.id,
            "filename": d.filename,
            "content_type": d.content_type,
            "url": "/api/intake/documents/" + d.id + "/file",
        }
        for d in db.scalars(
            select(IntakeDocument).where(IntakeDocument.request_id == r.id)
        ).all()
    ]
    return data


def session_out(db, who):
    w = db.get(Workspace, who["workspace"])
    if not w:
        raise HTTPException(401, "This workspace is no longer available.")
    return {
        "technician": who["technician"],
        "technicians": technician_names(db, who["workspace"], who.get("demo", True)),
        "accounts": [
            {"name": n, "role": "reception" if n in RECEPTIONISTS else "technician"}
            for n in TECHNICIANS + RECEPTIONISTS
        ],
        "role": role(who),
        "share": w.share,
        "demo": who.get("demo", True),
        "ai_available": bool(os.getenv("GEMINI_API_KEY")),
        "models": {"generator": GENERATOR, "judge": JUDGE},
    }


@app.get("/api/health")
def health(db=Depends(dbdep)):
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "postgresql",
        "version": "3.0",
        "evidence_policy": POLICY,
    }


@app.get("/api/session")
def get_session(request: Request, db=Depends(dbdep)):
    return app.state.portal_session(request, db)


@app.post("/api/demo/start")
def start(response: Response, db=Depends(dbdep)):
    # Keep public demo resource growth bounded. Existing workspace cookies last 30 days.
    db.execute(text("SELECT pg_advisory_xact_lock(7771042)"))
    if db.scalar(select(func.count()).select_from(Workspace)) >= 200:
        raise HTTPException(429, "This demonstration has reached its workspace limit.")
    w = Workspace(share=secrets.token_urlsafe(24))
    db.add(w)
    db.flush()
    seed_expansion(db, w)
    ensure_site(db, w.id)
    db.commit()
    cookie(response, w.id, TECHNICIANS[0])
    return session_out(db, {"workspace": w.id, "technician": TECHNICIANS[0]})


class Switch(BaseModel):
    name: str


@app.post("/api/session/technician")
def switch(body: Switch, response: Response, who=Depends(claims), db=Depends(dbdep)):
    if not who.get("demo", True):
        raise HTTPException(
            403, "Account switching is only available in synthetic demos."
        )
    if body.name not in TECHNICIANS + RECEPTIONISTS + [DEMO_ADMIN]:
        raise HTTPException(403, "Technician is not approved for this demonstration.")
    cookie(response, who["workspace"], body.name)
    return session_out(
        db, {**who, "technician": body.name, "role": role({"technician": body.name})}
    )


@app.post("/api/session/logout")
def logout(response: Response):
    response.delete_cookie("lemmer_session")
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard(who=Depends(claims), db=Depends(dbdep)):
    wid = who["workspace"]
    assets = db.scalars(select(Asset).where(Asset.workspace_id == wid)).all()
    reqs = db.scalars(
        select(ServiceRequest)
        .where(ServiceRequest.workspace_id == wid)
        .order_by(ServiceRequest.created_at.desc())
    ).all()
    events = db.scalars(
        select(Event)
        .where(Event.workspace_id == wid)
        .order_by(Event.created_at.desc())
        .limit(6)
    ).all()
    return {
        "assets": [serialize(a) for a in assets],
        "requests": [req_out(db, r) for r in reqs],
        "activity": [
            {**serialize(e), "asset_code": db.get(Asset, e.asset_id).code}
            for e in events
        ],
        "knowledge_count": db.scalar(
            select(func.count())
            .select_from(KnowledgeCase)
            .where(KnowledgeCase.workspace_id == wid)
        ),
        "ai_runs": db.scalar(
            select(func.count()).select_from(AIRun).where(AIRun.workspace_id == wid)
        ),
    }


@app.get("/api/assets")
def assets(who=Depends(claims), db=Depends(dbdep)):
    return [
        serialize(a)
        for a in db.scalars(
            select(Asset)
            .where(Asset.workspace_id == who["workspace"])
            .order_by(Asset.code)
        ).all()
    ]


class NewAsset(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    serial: str = Field(min_length=2, max_length=100)
    customer: str = Field(min_length=2, max_length=100)
    location: str = Field(min_length=2, max_length=100)


@app.post("/api/assets")
def new_asset(body: NewAsset, who=Depends(claims), db=Depends(dbdep)):
    require(who, "reception", "superuser")
    db.execute(text("SELECT pg_advisory_xact_lock(7771043)"))
    count = db.scalar(
        select(func.count())
        .select_from(Asset)
        .where(Asset.workspace_id == who["workspace"])
    )
    if count >= 50:
        raise HTTPException(429, "Demo asset limit reached.")
    a = Asset(
        workspace_id=who["workspace"],
        code=f"LM-{1042 + count}",
        **body.model_dump(),
        image="/images/l-1095.png" if body.model == "L-1095" else "/images/l-65.png",
    )
    db.add(a)
    db.commit()
    return serialize(a)


@app.get("/api/assets/{asset_id}")
def asset_detail(asset_id: str, who=Depends(claims), db=Depends(dbdep)):
    a = owned(db, Asset, asset_id, who["workspace"])
    return {
        "asset": serialize(a),
        "events": [
            (
                {**serialize(e), "body": effective_report(db, e)}
                if e.kind == "service"
                else serialize(e)
            )
            for e in db.scalars(
                select(Event)
                .where(Event.asset_id == a.id)
                .order_by(Event.created_at.desc())
            ).all()
        ],
        "requests": [
            serialize(r)
            for r in db.scalars(
                select(ServiceRequest)
                .where(ServiceRequest.asset_id == a.id)
                .order_by(ServiceRequest.created_at.desc())
            ).all()
        ],
        "documents": (
            documents(reference_key(a)) if a.manufacturer.lower() == "lemmer" else []
        ),
        "parts": (
            parts_for(reference_key(a)) if a.manufacturer.lower() == "lemmer" else {}
        ),
    }


@app.get("/api/requests/{request_id}")
def request_detail(request_id: str, who=Depends(claims), db=Depends(dbdep)):
    r = owned(db, ServiceRequest, request_id, who["workspace"])
    a = asset_detail(r.asset_id, who, db)
    runs = db.scalars(
        select(AIRun)
        .where(AIRun.request_id == r.id)
        .order_by(AIRun.created_at.desc())
        .limit(10)
    ).all()
    return {
        "request": req_out(db, r),
        "events": a["events"],
        "parts": a["parts"],
        "runs": (
            [{**serialize(x), "result": visible_result(x.result)} for x in runs]
            if role(who) in ["technician", "superuser"]
            else []
        ),
    }


@app.post("/api/requests/{request_id}/guidance")
def ensure_guidance(request_id: str, who=Depends(claims), db=Depends(dbdep)):
    if role(who) not in ["technician", "superuser"]:
        raise HTTPException(403, "Guidance is for the technician workspace.")
    r = owned(db, ServiceRequest, request_id, who["workspace"], True)
    job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == r.id))
    if job and job.status == "ready" and job.run_id:
        old_run = db.get(AIRun, job.run_id)
        if old_run and old_run.result.get("policy_version") != POLICY:
            job.status = "queued"
            job.run_id = None
            job.attempts = 0
            job.updated_at = now()
    if not job:
        previous = db.scalar(
            select(AIRun)
            .where(AIRun.request_id == r.id, AIRun.mode == "C")
            .order_by(AIRun.created_at.desc())
        )
        job = enqueue(db, r)
        if (
            previous
            and previous.result.get("recommendation")
            and previous.result.get("policy_version") == POLICY
        ):
            job.status, job.run_id, job.message = (
                "ready",
                previous.id,
                "Evidence review complete.",
            )
    db.commit()
    return job_out(job)


@app.get("/api/requests/{request_id}/guidance")
def guidance_status(request_id: str, who=Depends(claims), db=Depends(dbdep)):
    require(who, "technician", "superuser")
    owned(db, ServiceRequest, request_id, who["workspace"])
    job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == request_id))
    run = db.get(AIRun, job.run_id) if job and job.run_id else None
    return {
        "guidance": job_out(job),
        "result": visible_result(run.result) if run and job.status == "ready" else None,
    }


class NewRequest(BaseModel):
    asset_id: str
    title: str = Field(min_length=4, max_length=140)
    description: str = Field(min_length=10, max_length=4000)
    category: str = Field(max_length=80)
    priority: Literal["Low", "Normal", "High", "Urgent"] = "Normal"
    operating: Literal["Yes", "No", "Intermittently", "Unknown / Not assessed"] = (
        "Unknown / Not assessed"
    )
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(max_length=150)
    phone: str = Field(max_length=40, default="")


def create_request(body, wid, db):
    a = owned(db, Asset, body.asset_id, wid)
    db.execute(text("SELECT pg_advisory_xact_lock(7771044)"))
    n = db.scalar(
        select(func.count())
        .select_from(ServiceRequest)
        .where(ServiceRequest.workspace_id == wid)
    )
    if n >= 100:
        raise HTTPException(429, "Demo request limit reached.")
    r = ServiceRequest(
        workspace_id=wid,
        asset_id=a.id,
        code=f"SR-{26041 + n}",
        title=body.title,
        description=body.description,
        category=body.category,
        priority=body.priority,
        operating=body.operating,
        contact={"name": body.name, "email": body.email, "phone": body.phone},
    )
    db.add(r)
    db.flush()
    enqueue(db, r)
    a.condition = "Needs service"
    db.add(
        Event(
            workspace_id=wid,
            asset_id=a.id,
            request_id=r.id,
            kind="request",
            title="Service requested",
            actor=body.name,
            body={"description": body.description, "reference": r.code},
        )
    )
    db.add(
        Notification(
            workspace_id=wid,
            request_id=r.id,
            subject=f"We received your request · {r.code}",
            recipient=body.email,
            body=f"Your service request for {a.model}, asset {a.code}, has been received. Our technicians will review: {r.title}. This is a demo email preview; no email has been sent.",
        )
    )
    db.commit()
    return req_out(db, r)


@app.post("/api/requests")
def new_request(body: NewRequest, who=Depends(claims), db=Depends(dbdep)):
    return create_request(body, who["workspace"], db)


class RequestUpdate(BaseModel):
    status: (
        Literal[
            "New",
            "In progress",
            "Awaiting diagnosis",
            "Awaiting approval",
            "Awaiting parts",
            "Awaiting customer",
            "Closed",
        ]
        | None
    ) = None
    technician: str | None = None
    draft: dict | None = None
    version: int


@app.patch("/api/requests/{request_id}")
def update_request(
    request_id: str, body: RequestUpdate, who=Depends(claims), db=Depends(dbdep)
):
    r = owned(db, ServiceRequest, request_id, who["workspace"], True)
    if r.version != body.version:
        raise HTTPException(
            409, "This request changed in another window. Reload it before saving."
        )
    before_update = {
        "status": r.status,
        "technician": r.technician,
        "draft": r.draft,
        "version": r.version,
    }
    if body.status == "Closed":
        raise HTTPException(422, "Finalize a service report to close a request.")
    if body.draft is not None:
        require(who, "technician", "superuser")
    if body.technician and body.technician not in technician_names(
        db, who["workspace"], who.get("demo", True)
    ) + ["Unassigned"]:
        raise HTTPException(422, "Choose an approved technician.")
    if body.status and body.status != r.status:
        db.add(
            Event(
                workspace_id=who["workspace"],
                asset_id=r.asset_id,
                request_id=r.id,
                kind="status",
                title=f"Status changed to {body.status}",
                actor=who["technician"],
                body={"from": r.status, "to": body.status},
            )
        )
        r.status = body.status
    if body.technician is not None:
        r.technician = body.technician
    if body.draft is not None:
        if len(json.dumps(body.draft)) > 15000:
            raise HTTPException(422, "Draft is too large.")
        r.draft = body.draft
    audit(
        db,
        who,
        "Update service request",
        r.id,
        before_update,
        {
            "status": r.status,
            "technician": r.technician,
            "draft": r.draft,
            "version": r.version + 1,
        },
        "Staff updated request",
    )
    r.version += 1
    r.updated_at = now()
    db.commit()
    return req_out(db, r)


class PartLine(BaseModel):
    part: str = Field(min_length=1, max_length=150)
    quantity: int = Field(ge=1, le=1000)
    action: Literal["Used", "Replaced", "Requested"] = "Used"


class Report(BaseModel):
    diagnosis: str = Field(min_length=5, max_length=3000)
    work: str = Field(min_length=5, max_length=4000)
    parts: list[str] = Field(default_factory=list, max_length=20)
    part_lines: list[PartLine] = Field(default_factory=list, max_length=20)
    parts_replaced: bool = False
    test: str = Field(min_length=5, max_length=3000)
    outcome: Literal[
        "Repaired", "Partially repaired", "Unresolved", "Not repaired", "No fault found"
    ]
    notes: str = Field(default="", max_length=2000)
    inspection_date: str = Field(max_length=30)

    @field_validator("inspection_date")
    @classmethod
    def validate_date(cls, value):
        if date.fromisoformat(value) > date.today():
            raise ValueError("Inspection date cannot be in the future.")
        return value

    close_request: bool = False
    submission_id: str = Field(min_length=10, max_length=100)
    version: int


@app.post("/api/requests/{request_id}/reports")
def report(request_id: str, body: Report, who=Depends(claims), db=Depends(dbdep)):
    if role(who) not in ["technician", "superuser"]:
        raise HTTPException(403, "A technician must record the actual repair outcome.")
    return save_report(request_id, body, who, db)


def save_report(request_id, body, who, db):
    r = owned(db, ServiceRequest, request_id, who["workspace"], True)
    existing = db.scalar(
        select(Event).where(
            Event.request_id == r.id,
            Event.body["submission_id"].as_string() == body.submission_id,
        )
    )
    if existing:
        return {"event": serialize(existing), "request": req_out(db, r)}
    if r.version != body.version:
        raise HTTPException(409, "This request changed. Reload before finalizing.")
    if r.status == "Closed":
        raise HTTPException(
            409, "Reopen the request before adding another service visit."
        )
    a = db.get(Asset, r.asset_id)
    if (
        body.outcome in ["Unresolved", "Not repaired", "Partially repaired"]
        and len(body.notes.strip()) < 5
    ):
        raise HTTPException(
            422,
            "Record why the equipment remains unrepaired or partially repaired in notes.",
        )
    if body.part_lines:
        if len({p.part for p in body.part_lines}) != len(body.part_lines):
            raise HTTPException(
                422, "Combine duplicate parts into one line with a quantity."
            )
        body.parts = [p.part for p in body.part_lines if p.action != "Requested"]
    reference = (
        parts_for(reference_key(a)) if a.manufacturer.lower() == "lemmer" else {}
    )
    if reference and any(
        p not in reference for p in (body.parts + [x.part for x in body.part_lines])
    ):
        raise HTTPException(
            422, "One or more parts are not in this model’s verified reference."
        )
    data = body.model_dump(exclude={"version", "close_request"})
    data["parts_reference_status"] = (
        "Manufacturer reference checked"
        if reference
        else "Technician-entered; manufacturer reference unavailable"
    )
    data["symptom"] = r.description
    data["source"] = "Technician-recorded demo event"
    e = Event(
        workspace_id=who["workspace"],
        asset_id=r.asset_id,
        request_id=r.id,
        title=body.diagnosis,
        body=data,
        actor=who["technician"],
    )
    db.add(e)
    db.flush()
    db.add(
        KnowledgeCase(
            workspace_id=who["workspace"],
            code="CASE-" + e.id[:8].upper(),
            model=reference_key(a),
            symptom=r.description,
            diagnosis=body.diagnosis,
            repair=body.work,
            parts=body.parts,
            test=body.test,
            outcome=body.outcome,
            source="Technician-recorded demo repair",
            asset_id=a.id,
            event_id=e.id,
        )
    )
    installed_parts = (
        [p.part for p in body.part_lines if p.action == "Replaced"]
        if body.part_lines
        else (body.parts if body.parts_replaced else [])
    )
    if installed_parts:
        from .expansion import component_key

        for part in installed_parts:
            previous = next(
                (
                    x
                    for x in db.scalars(
                        select(ComponentRecord)
                        .where(
                            ComponentRecord.asset_id == a.id,
                            ComponentRecord.installed < body.inspection_date,
                        )
                        .order_by(ComponentRecord.installed.desc())
                    )
                    if component_key(x.part) == component_key(part)
                ),
                None,
            )
            interval = (
                (
                    date.fromisoformat(body.inspection_date)
                    - date.fromisoformat(previous.installed)
                ).days
                if previous
                else None
            )
            basis = (
                f"Observed {interval}-day interval between two recorded installations. Inspection estimate only, not guaranteed part life."
                if interval
                else "Technician confirmed installation; no previous dated installation is available."
            )
            db.add(
                ComponentRecord(
                    workspace_id=who["workspace"],
                    asset_id=a.id,
                    part=part,
                    installed=body.inspection_date,
                    interval_days=interval,
                    basis=basis,
                    event_id=e.id,
                )
            )
    audit(
        db,
        who,
        "Record service report",
        e.id,
        {},
        {"request_id": r.id, "outcome": body.outcome, "closed": body.close_request},
        "Technician confirmed actual findings; reusable knowledge still requires review",
    )
    r.status = "Closed" if body.close_request else "In progress"
    r.technician = who["technician"]
    r.draft = {}
    if r.status == "Closed":
        job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == r.id))
        if job and job.status in ["queued", "running", "unavailable"]:
            job.status, job.run_id, job.message = (
                "completed",
                None,
                "Repair completed. The recorded outcome is now in the passport.",
            )
            job.updated_at = now()
    r.updated_at = now()
    r.version += 1
    a.condition = (
        "Operational"
        if body.outcome in ["Repaired", "No fault found"]
        and body.close_request
        and not db.scalar(
            select(ServiceRequest.id)
            .where(
                ServiceRequest.asset_id == a.id,
                ServiceRequest.id != r.id,
                ServiceRequest.status != "Closed",
            )
            .limit(1)
        )
        else "Needs service"
    )
    db.add(
        Notification(
            workspace_id=who["workspace"],
            request_id=r.id,
            subject=f"Service update · {r.code}",
            recipient=r.contact.get("email", ""),
            body=f"{a.code}: {body.outcome}. Diagnosis: {body.diagnosis}. Work: {body.work}. Test: {body.test}. This is a demo email preview; no email has been sent.",
        )
    )
    db.commit()
    return {"event": serialize(e), "request": req_out(db, r)}


class AIInput(BaseModel):
    problem: str = Field(min_length=10, max_length=4000)
    mode: Literal["A", "B", "C"] = "C"


@app.post("/api/requests/{request_id}/recommend")
async def recommendation(
    request_id: str, body: AIInput, who=Depends(claims), db=Depends(dbdep)
):
    if role(who) not in ["technician", "superuser"]:
        raise HTTPException(
            403, "Switch to a technician account to request service guidance."
        )
    r = owned(db, ServiceRequest, request_id, who["workspace"])
    from .usage import workspace_context

    workspace_context.set(who["workspace"])
    a = db.get(Asset, r.asset_id)
    cached = cached_result(db, who["workspace"], a, body.problem, body.mode)
    if cached:
        from .usage import cache_hit

        cache_hit()
        run = AIRun(
            workspace_id=who["workspace"],
            request_id=r.id,
            mode=body.mode,
            result={**cached, "problem": body.problem},
        )
        db.add(run)
        db.flush()
        if body.mode == "C":
            job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == r.id))
            if job and job.status not in ["queued", "running"]:
                job.status, job.run_id, job.message = (
                    "ready",
                    run.id,
                    "Previous evidence review reused.",
                )
                job.updated_at = now()
        db.commit()
        return {**cached, "run_id": run.id}
    from .usage import check_budget

    try:
        check_budget()
    except RuntimeError as e:
        raise HTTPException(429, str(e))
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(
            503,
            "Live AI is not configured. You can still search cases and complete service reports.",
        )
    run = AIRun(
        workspace_id=who["workspace"],
        request_id=r.id,
        mode=body.mode,
        result={"status": "running"},
    )
    db.add(run)
    db.commit()
    try:
        result = await recommend(db, who["workspace"], a, body.problem, body.mode)
        result["problem"] = body.problem
        run.result = result
        if body.mode == "C":
            job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == r.id))
            if job and job.status not in ["queued", "running"]:
                job.status, job.run_id, job.message = (
                    "ready",
                    run.id,
                    "Evidence review complete.",
                )
                job.updated_at = now()
        db.commit()
        return {**result, "run_id": run.id}
    except Exception as e:
        db.rollback()
        run = db.get(AIRun, run.id)
        msg = (
            str(e)
            if isinstance(e, RuntimeError)
            else "The recommendation could not be checked. Please retry later. No unreviewed recommendation was released."
        )
        run.result = {"error": msg}
        db.commit()
        raise HTTPException(503, msg)


@app.get("/api/knowledge")
def knowledge(who=Depends(claims), db=Depends(dbdep)):
    require(who, "technician", "superuser")
    return {
        "documents": [
            d
            for model in sorted(
                {
                    reference_key(a)
                    for a in db.scalars(
                        select(Asset).where(
                            Asset.workspace_id == who["workspace"],
                            Asset.manufacturer == "Lemmer",
                        )
                    )
                }
            )
            for d in documents(model)
        ],
        "cases": [
            {
                **serialize(c),
                "model": model_name(c.model, c.model),
                "product_number": c.model if c.model.startswith("L0") else "",
                "review_status": "Asset record only; reusable procedure requires human review",
            }
            for c in db.scalars(
                select(KnowledgeCase)
                .where(KnowledgeCase.workspace_id == who["workspace"])
                .order_by(KnowledgeCase.created_at.desc())
            ).all()
        ],
    }


class ImportCase(BaseModel):
    model: str = Field(min_length=1, max_length=100)
    symptom: str = Field(min_length=10, max_length=4000)
    diagnosis: str = Field(min_length=3, max_length=3000)
    repair: str = Field(min_length=3, max_length=4000)
    parts: list[str] = Field(default_factory=list, max_length=20)
    test: str = Field(min_length=3, max_length=3000)
    outcome: Literal[
        "Repaired", "Partially repaired", "Unresolved", "Not repaired", "No fault found"
    ]


class ImportBody(BaseModel):
    cases: list[ImportCase] = Field(min_length=1, max_length=100)


@app.post("/api/knowledge/import")
def import_cases(body: ImportBody, who=Depends(claims), db=Depends(dbdep)):
    require(who, "superuser")
    db.execute(text("SELECT pg_advisory_xact_lock(7771046)"))
    count = db.scalar(
        select(func.count())
        .select_from(KnowledgeCase)
        .where(KnowledgeCase.workspace_id == who["workspace"])
    )
    if count + len(body.cases) > 300:
        raise HTTPException(429, "Demo knowledge limit reached.")
    for c in body.cases:
        if any(p not in parts_for(c.model) for p in c.parts):
            raise HTTPException(
                422, "An imported part does not match the selected model reference."
            )
        db.add(
            KnowledgeCase(
                workspace_id=who["workspace"],
                code="IMP-" + secrets.token_hex(4).upper(),
                source="Imported demonstration case; not independently validated",
                **c.model_dump(),
            )
        )
    db.commit()
    return {"imported": len(body.cases)}


@app.get("/api/notifications")
def notifications(who=Depends(claims), db=Depends(dbdep)):
    return [
        serialize(n)
        for n in db.scalars(
            select(Notification)
            .where(Notification.workspace_id == who["workspace"])
            .order_by(Notification.created_at.desc())
        ).all()
    ]


@app.get("/api/export")
def export(who=Depends(claims), db=Depends(dbdep)):
    require(who, "superuser")
    result = {
        cls.__tablename__: [
            serialize(r)
            for r in db.scalars(
                select(cls).where(cls.workspace_id == who["workspace"])
            ).all()
        ]
        for cls in [Asset, ServiceRequest, Event, KnowledgeCase, AIRun]
    }
    return Response(
        json.dumps(result, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="lemmer-demo-export.json"'
        },
    )


def public_asset(db, share, code):
    w = db.scalar(select(Workspace).where(Workspace.share == share))
    a = (
        db.scalar(select(Asset).where(Asset.workspace_id == w.id, Asset.code == code))
        if w
        else None
    )
    if not a:
        raise HTTPException(404, "Passport not found. Check the QR code or link.")
    return w, a


@app.get("/api/public/{share}/{code}")
def passport(share: str, code: str, request: Request, db=Depends(dbdep)):
    who = app.state.portal_identity(request, db)
    w, a = public_asset(db, share, code)
    link = db.get(AssetOwner, a.id)
    if who["workspace"] != w.id or (
        "customer_id" in who and (not link or link.customer_id != who["customer_id"])
    ):
        raise HTTPException(404, "Passport not assigned to this account.")
    # Public QR view deliberately excludes contact information and internal repair details.
    return {
        "asset": {
            k: v for k, v in serialize(a).items() if k not in ["customer", "location"]
        },
        "documents": [
            {"title": d["title"], "url": d["url"]} for d in documents(reference_key(a))
        ],
        "requests": [
            {
                "code": r.code,
                "status": r.status,
                "title": r.title,
                "created_at": r.created_at.isoformat(),
            }
            for r in db.scalars(
                select(ServiceRequest).where(ServiceRequest.asset_id == a.id)
            ).all()
        ],
    }


@app.post("/api/public/{share}/{code}/requests")
def public_request(
    share: str, code: str, body: NewRequest, request: Request, db=Depends(dbdep)
):
    passport(share, code, request, db)
    w, a = public_asset(db, share, code)
    if body.asset_id != a.id:
        raise HTTPException(422, "The request does not match this Passport.")
    r = create_request(body, w.id, db)
    return {"code": r["code"], "status": r["status"]}


from .intake import attach_intake_routes

attach_intake_routes(app, dbdep, claims, owned, req_out, NewRequest)
attach_expansion(
    app,
    dbdep,
    SECRET,
    cookie,
    session_out,
    create_request,
    NewRequest,
)

from .operations import attach as attach_operations

attach_operations(app, dbdep, claims, owned, serialize, req_out)

if (ROOT / "dist/static").exists():
    app.mount(
        "/static", StaticFiles(directory=ROOT / "dist/static"), name="static-assets"
    )
app.mount("/images", StaticFiles(directory=ROOT / "public/images"), name="images")


@app.get("/{path:path}")
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "API endpoint not found.")
    if (ROOT / "dist/index.html").exists():
        return FileResponse(ROOT / "dist/index.html")
    return {"message": "Frontend development server: http://127.0.0.1:5173"}
