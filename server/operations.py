"""Calgary administration, reviewed procedures, corrections and print handoff."""

from datetime import date
from typing import Literal
from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, func
from .database import (
    Asset,
    ServiceRequest,
    Event,
    KnowledgeCase,
    AIRun,
    IntakeDocument,
    GuidanceJob,
    now,
)
from .expansion_models import Customer, AssetOwner, PortalUser
from .operations_models import StaffUser, Procedure, ProcedureRun, AuditEntry, AIUsage
from .access import require, audit, ensure_site, STAFF_ROLES, technician_names
from .procedures import matches, applicable
from .identity import reference_key
from .history import effective_report


class Step(BaseModel):
    question: str = Field(min_length=5, max_length=1500)
    yes: int = Field(ge=-1)
    no: int = Field(ge=-1)
    unknown: int = Field(ge=-1)
    # -1 completes the checklist. It never establishes diagnosis or authorizes repair.


class Reference(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    passage: str = Field(min_length=5, max_length=3000)
    url: str = Field(default="", max_length=1000)
    page: str = Field(default="Unknown", max_length=80)
    revision: str = Field(default="Unknown", max_length=100)

    @model_validator(mode="after")
    def safe_url(self):
        if self.url and not self.url.startswith(("https://", "http://")):
            raise ValueError("Use an http(s) source link.")
        return self


class ProcedureIn(BaseModel):
    title: str = Field(min_length=5, max_length=150)
    manufacturer: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    product_number: str = Field(default="", max_length=60)
    symptoms: list[str] = Field(min_length=1, max_length=30)
    steps: list[Step] = Field(min_length=1, max_length=30)
    references: list[Reference] = Field(min_length=1, max_length=20)
    solution: str = Field(min_length=5, max_length=3000)
    synthetic: bool = True
    customer_visible: bool = False
    source_case_id: str | None = None
    previous_id: str | None = None

    @model_validator(mode="after")
    def validate_graph(self):
        if any(not x.strip() or len(x) > 300 for x in self.symptoms):
            raise ValueError("Each symptom needs 1–300 characters.")
        for i, step in enumerate(self.steps):
            if any(
                t != -1 and not i < t < len(self.steps)
                for t in [step.yes, step.no, step.unknown]
            ):
                raise ValueError(
                    "A step must point forward to a valid step or -1 to finish."
                )
        return self


class Review(BaseModel):
    status: Literal["Approved", "Rejected", "Retired"]
    reason: str = Field(min_length=10, max_length=2000)
    privacy_checked: bool = False
    technical_checked: bool = False


class Answer(BaseModel):
    answer: Literal["yes", "no", "unknown"]
    observation: str = Field(min_length=3, max_length=2000)
    version: int


class StaffIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=150)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["reception", "technician", "superuser"]


class AccessChange(BaseModel):
    role: Literal["reception", "technician", "superuser"]
    active: bool
    reason: str = Field(min_length=10, max_length=1000)


class Correction(BaseModel):
    kind: Literal["asset", "customer", "report"]
    changes: dict
    reason: str = Field(min_length=10, max_length=1000)
    expected: dict


def attach(app, dbdep, claims, owned, serialize, req_out):
    def admin(w):
        require(w, "superuser")

    @app.get("/api/operations")
    def overview(w=Depends(claims), db=Depends(dbdep)):
        admin(w)
        site = ensure_site(db, w["workspace"])
        db.commit()
        return {
            "location": "Calgary",
            "company": "Lemmer",
            "staff": [
                {k: v for k, v in serialize(u).items() if k != "password"}
                for u in db.scalars(
                    select(StaffUser).where(StaffUser.workspace_id == w["workspace"])
                )
            ],
            "audit": [
                serialize(x)
                for x in db.scalars(
                    select(AuditEntry)
                    .where(AuditEntry.workspace_id == w["workspace"])
                    .order_by(AuditEntry.created_at.desc())
                    .limit(100)
                )
            ],
            "cases": [
                serialize(x)
                for x in db.scalars(
                    select(KnowledgeCase).where(
                        KnowledgeCase.workspace_id == w["workspace"]
                    )
                )
            ],
            "reports": [
                {**serialize(e), "body": effective_report(db, e)}
                for e in db.scalars(
                    select(Event)
                    .where(
                        Event.workspace_id == w["workspace"], Event.kind == "service"
                    )
                    .order_by(Event.created_at.desc())
                    .limit(100)
                )
            ],
            "site_id": site.id,
        }

    @app.post("/api/operations/staff")
    def add_staff(b: StaffIn, w=Depends(claims), db=Depends(dbdep)):
        admin(w)
        from sqlalchemy import text

        db.execute(text("SELECT pg_advisory_xact_lock(7771080)"))
        from .expansion import password_hash
        import re

        email = b.email.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise HTTPException(422, "Enter a valid email.")
        site = ensure_site(db, w["workspace"])
        if db.scalar(select(StaffUser).where(StaffUser.email == email)) or db.scalar(
            select(PortalUser).where(PortalUser.email == email)
        ):
            raise HTTPException(409, "Email already registered.")
        if b.name in technician_names(db, w["workspace"]) or b.name in [
            "Taylor Brooks",
            "Demo super-user",
        ]:
            raise HTTPException(409, "Use a unique staff display name for assignment.")
        if (
            db.scalar(
                select(func.count())
                .select_from(StaffUser)
                .where(StaffUser.workspace_id == w["workspace"])
            )
            >= 30
        ):
            raise HTTPException(429, "Demo staff limit reached.")
        u = StaffUser(
            workspace_id=w["workspace"],
            location_id=site.id,
            name=b.name,
            email=email,
            password=password_hash(b.password),
            role=b.role,
        )
        db.add(u)
        db.flush()
        audit(
            db,
            w,
            "Create staff account",
            u.id,
            {},
            {"name": u.name, "role": u.role, "email": u.email},
            "Super-user created Calgary account",
        )
        db.commit()
        return {"id": u.id}

    @app.patch("/api/operations/staff/{key}")
    def access(key: str, b: AccessChange, w=Depends(claims), db=Depends(dbdep)):
        admin(w)
        u = owned(db, StaffUser, key, w["workspace"], True)
        if u.id == w.get("staff_id") and (not b.active or b.role != "superuser"):
            raise HTTPException(422, "You cannot remove your own super-user access.")
        before = {"role": u.role, "active": u.active}
        u.role, u.active = b.role, b.active
        u.session_version += 1
        audit(
            db,
            w,
            "Change access",
            key,
            before,
            {"role": u.role, "active": u.active},
            b.reason,
        )
        db.commit()
        return {"ok": True}

    @app.post("/api/operations/corrections/{key}")
    def correction(key: str, b: Correction, w=Depends(claims), db=Depends(dbdep)):
        admin(w)
        cls = {"asset": Asset, "customer": Customer, "report": Event}[b.kind]
        obj = owned(db, cls, key, w["workspace"], True)
        allowed = {
            "asset": {"name", "serial", "model", "product_number", "manufacturer"},
            "customer": {"name", "email", "phone", "sap_customer_code"},
            "report": {"diagnosis", "work", "test", "outcome", "notes"},
        }[b.kind]
        if (
            not b.changes
            or set(b.changes) - allowed
            or any(
                not isinstance(v, str) or not v.strip() or len(v) > 3000
                for v in b.changes.values()
            )
        ):
            raise HTTPException(422, "Choose permitted fields with nonempty text.")
        if b.kind == "report" and obj.kind != "service":
            raise HTTPException(422, "Only a service report can be amended here.")
        before = {
            k: (
                effective_report(db, obj).get(k, "")
                if b.kind == "report"
                else getattr(obj, k)
            )
            for k in b.changes
        }
        if before != b.expected:
            raise HTTPException(409, "The record changed. Reload before correcting it.")
        if b.kind == "report":
            if "outcome" in b.changes and b.changes["outcome"] not in [
                "Repaired",
                "Partially repaired",
                "Unresolved",
                "Not repaired",
                "No fault found",
            ]:
                raise HTTPException(422, "Invalid outcome.")
            source_case = db.scalar(
                select(KnowledgeCase).where(KnowledgeCase.event_id == obj.id)
            )
            if source_case:
                for proc in db.scalars(
                    select(Procedure).where(
                        Procedure.source_case_id == source_case.id,
                        Procedure.status == "Approved",
                    )
                ):
                    proc.status = "Retired"
                    audit(
                        db,
                        w,
                        "Retire affected procedure",
                        proc.id,
                        {"status": "Approved"},
                        {"status": "Retired"},
                        "Source repair amended; a new human review is required",
                    )
            db.add(
                Event(
                    workspace_id=w["workspace"],
                    asset_id=obj.asset_id,
                    request_id=obj.request_id,
                    kind="amendment",
                    title="Correction to service report",
                    actor=w["technician"],
                    body={
                        "original_event_id": obj.id,
                        "before": before,
                        "changes": b.changes,
                        "reason": b.reason,
                    },
                )
            )
        else:
            for k, v in b.changes.items():
                setattr(obj, k, v.strip())
            if b.kind == "customer" and "name" in b.changes:
                for a in db.scalars(
                    select(Asset)
                    .join(AssetOwner, AssetOwner.id == Asset.id)
                    .where(AssetOwner.customer_id == obj.id)
                ):
                    a.customer = obj.name
        audit(db, w, "Correct " + b.kind, key, before, b.changes, b.reason)
        db.commit()
        return {
            "ok": True,
            "message": "Correction recorded. Original reports remain unchanged; the amendment is shown alongside them.",
        }

    @app.get("/api/procedures")
    def library(w=Depends(claims), db=Depends(dbdep)):
        require(w, "technician", "superuser")
        return [
            serialize(p)
            for p in db.scalars(
                select(Procedure)
                .where(Procedure.workspace_id == w["workspace"])
                .order_by(Procedure.created_at.desc())
            )
            if w["role"] == "superuser"
            or p.status == "Approved"
            or p.author == w["technician"]
        ]

    @app.post("/api/procedures")
    def proposal(b: ProcedureIn, w=Depends(claims), db=Depends(dbdep)):
        require(w, "technician", "superuser")
        from sqlalchemy import text

        db.execute(text("SELECT pg_advisory_xact_lock(7771112)"))
        if b.source_case_id:
            owned(db, KnowledgeCase, b.source_case_id, w["workspace"])
        values = b.model_dump(exclude={"previous_id"})
        if b.previous_id:
            old = owned(db, Procedure, b.previous_id, w["workspace"])
            values["family_id"] = old.family_id
            values["version"] = 1 + db.scalar(
                select(func.max(Procedure.version)).where(
                    Procedure.family_id == old.family_id,
                    Procedure.workspace_id == w["workspace"],
                )
            )
        if (
            db.scalar(
                select(func.count())
                .select_from(Procedure)
                .where(Procedure.workspace_id == w["workspace"])
            )
            >= 100
        ):
            raise HTTPException(429, "Demo procedure limit reached.")
        p = Procedure(workspace_id=w["workspace"], author=w["technician"], **values)
        db.add(p)
        db.flush()
        audit(
            db,
            w,
            "Propose procedure",
            p.id,
            {},
            {"title": p.title, "version": p.version},
            "Submitted for human technical and privacy review",
        )
        db.commit()
        return serialize(p)

    @app.post("/api/procedures/{key}/review")
    def review(key: str, b: Review, w=Depends(claims), db=Depends(dbdep)):
        admin(w)
        from sqlalchemy import text

        db.execute(text("SELECT pg_advisory_xact_lock(7771112)"))
        p = owned(db, Procedure, key, w["workspace"], True)
        if b.status == "Approved" and (
            p.status != "Pending review"
            or not b.privacy_checked
            or not b.technical_checked
        ):
            raise HTTPException(
                422,
                "Review applicability, steps, source support and removal of private customer information before approval.",
            )
        if b.status == "Rejected" and p.status != "Pending review":
            raise HTTPException(422, "Only a pending proposal can be rejected.")
        if b.status == "Retired" and p.status != "Approved":
            raise HTTPException(422, "Only an approved procedure can be retired.")
        before = {"status": p.status}
        if b.status == "Approved":
            for other in db.scalars(
                select(Procedure)
                .where(
                    Procedure.family_id == p.family_id,
                    Procedure.workspace_id == w["workspace"],
                    Procedure.status == "Approved",
                )
                .with_for_update()
            ):
                other.status = "Retired"
                audit(
                    db,
                    w,
                    "Supersede procedure",
                    other.id,
                    {"status": "Approved"},
                    {"status": "Retired"},
                    "Replaced by version " + str(p.version),
                )
        p.status = b.status
        p.reviewer = w["technician"]
        p.review_reason = b.reason
        p.reviewed_at = now()
        audit(
            db,
            w,
            "Review procedure",
            key,
            before,
            {"status": p.status, "version": p.version},
            b.reason,
        )
        # Changed approved evidence invalidates delivered guidance, including saved jobs.
        for asset in db.scalars(
            select(Asset).where(Asset.workspace_id == w["workspace"])
        ):
            if applicable(p, asset):
                for job in db.scalars(
                    select(GuidanceJob)
                    .join(ServiceRequest, ServiceRequest.id == GuidanceJob.request_id)
                    .where(
                        ServiceRequest.asset_id == asset.id,
                        ServiceRequest.status != "Closed",
                    )
                ):
                    job.status = "queued"
                    job.run_id = None
                    job.attempts = 0
                    job.updated_at = now()
                    job.message = "Approved knowledge changed; refreshing guidance."

        db.commit()
        return serialize(p)

    @app.get("/api/requests/{key}/procedures")
    def suggestions(key: str, w=Depends(claims), db=Depends(dbdep)):
        r = owned(db, ServiceRequest, key, w["workspace"])
        a = db.get(Asset, r.asset_id)
        return {
            "procedures": [
                {**serialize(p), "exact_symptom": exact, "keyword_score": score}
                for p, exact, score in matches(db, w["workspace"], a, r.description)
            ],
            "runs": [
                serialize(x)
                for x in db.scalars(
                    select(ProcedureRun)
                    .where(ProcedureRun.request_id == r.id)
                    .order_by(ProcedureRun.created_at.desc())
                )
            ],
        }

    @app.post("/api/requests/{key}/procedures/{pid}/start")
    def begin(key: str, pid: str, w=Depends(claims), db=Depends(dbdep)):
        require(w, "technician", "superuser")
        r = owned(db, ServiceRequest, key, w["workspace"], True)
        p = owned(db, Procedure, pid, w["workspace"])
        if r.status == "Closed":
            raise HTTPException(409, "Request is closed.")
        if p.status != "Approved" or not applicable(p, db.get(Asset, r.asset_id)):
            raise HTTPException(
                422, "An approved procedure for this exact equipment is required."
            )
        existing = db.scalar(
            select(ProcedureRun).where(
                ProcedureRun.request_id == key,
                ProcedureRun.procedure_id == pid,
                ProcedureRun.status == "In progress",
            )
        )
        if existing:
            return serialize(existing)
        run = ProcedureRun(
            workspace_id=w["workspace"],
            request_id=key,
            procedure_id=pid,
            actor=w["technician"],
        )
        db.add(run)
        db.flush()
        audit(
            db,
            w,
            "Start approved procedure",
            run.id,
            {},
            {"procedure_id": pid, "request_id": key},
            "Technician selected applicable symptom; diagnosis still unconfirmed",
        )
        db.commit()
        return serialize(run)

    @app.post("/api/procedure-runs/{key}/answer")
    def answer(key: str, b: Answer, w=Depends(claims), db=Depends(dbdep)):
        require(w, "technician", "superuser")
        run = owned(db, ProcedureRun, key, w["workspace"], True)
        p = db.get(Procedure, run.procedure_id)
        r = db.get(ServiceRequest, run.request_id)
        if (
            run.version != b.version
            or run.status != "In progress"
            or p.status != "Approved"
            or r.status == "Closed"
        ):
            raise HTTPException(
                409, "Checklist changed, closed or retired. Reload before continuing."
            )
        i = run.current_step
        next_step = p.steps[i][b.answer]
        run.answers = [
            *run.answers,
            {
                "step": i,
                "answer": b.answer,
                "observation": b.observation,
                "actor": w["technician"],
                "at": now().isoformat(),
            },
        ]
        run.current_step = next_step
        run.version += 1
        if next_step == -1:
            run.status = "Completed"
        db.add(
            Event(
                workspace_id=w["workspace"],
                asset_id=r.asset_id,
                request_id=r.id,
                kind="observation",
                title="Approved checklist observation",
                actor=w["technician"],
                body={
                    "procedure_id": p.id,
                    "procedure_version": p.version,
                    "step": i,
                    "answer": b.answer,
                    "observation": b.observation,
                },
            )
        )
        db.commit()
        return serialize(run)

    @app.get("/api/requests/{key}/receipt")
    def receipt(key: str, w=Depends(claims), db=Depends(dbdep)):
        r = owned(db, ServiceRequest, key, w["workspace"])
        return req_out(db, r)

    @app.get("/api/operations/usage")
    def usage(w=Depends(claims), db=Depends(dbdep)):
        admin(w)
        from .usage import limits

        return {
            "limits": limits(),
            "records": [
                serialize(x)
                for x in db.scalars(
                    select(AIUsage)
                    .where(AIUsage.workspace_id == w["workspace"])
                    .order_by(AIUsage.created_at.desc())
                    .limit(150)
                )
            ],
            "notes": "Each provider HTTP request, including generation, judging, extraction and embedding, reserves capacity before it starts. No paid fallback. Token usage unavailable from the provider remains unknown. Currency billing is not inferred from token counts.",
        }

    @app.post("/api/intake/documents/{key}/share")
    def share_document(key: str, b: dict, w=Depends(claims), db=Depends(dbdep)):
        require(w, "reception", "superuser")
        d = owned(db, IntakeDocument, key, w["workspace"], True)
        if not d.request_id or b.get("reviewed_for_customer") is not True:
            raise HTTPException(
                422, "Review this document for customer visibility after handoff."
            )
        r = db.get(ServiceRequest, d.request_id)
        db.add(
            Event(
                workspace_id=w["workspace"],
                asset_id=r.asset_id,
                request_id=r.id,
                kind="document_shared",
                title="Document released to equipment owner",
                actor=w["technician"],
                body={"document_id": d.id, "filename": d.filename},
            )
        )
        audit(
            db,
            w,
            "Release customer document",
            d.id,
            {},
            {"customer_visible": True},
            "Reception confirmed document is suitable for its owner",
        )
        db.commit()
        return {"ok": True}

    @app.get("/api/owner-documents/{key}")
    def owner_document(key: str, request: Request, db=Depends(dbdep)):
        w = app.state.portal_identity(request, db)
        d = owned(db, IntakeDocument, key, w["workspace"])
        r = db.get(ServiceRequest, d.request_id) if d.request_id else None
        link = db.get(AssetOwner, r.asset_id) if r else None
        if (
            not link
            or w.get("customer_id") != link.customer_id
            or not db.scalar(
                select(Event).where(
                    Event.kind == "document_shared",
                    Event.request_id == r.id,
                    Event.body["document_id"].as_string() == d.id,
                )
            )
        ):
            raise HTTPException(404, "Document not available.")
        return Response(
            d.payload,
            media_type=d.content_type,
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "private, no-store",
            },
        )
