"""Ownership-aware portal and reception workflows. Robot integration is simulated."""

import hashlib, hmac, secrets, time, re
from datetime import date, timedelta
from typing import Literal
from fastapi import Request, Response, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, text
from .database import (
    Workspace,
    Asset,
    ServiceRequest,
    Event,
    KnowledgeCase,
    AIRun,
    GuidanceJob,
    now,
)
from .expansion_models import (
    Customer,
    PortalUser,
    AssetOwner,
    AssetViewer,
    PartOrder,
    Inspection,
    ComponentRecord,
    SchemaVersion,
    InspectionMedia,
)
from .catalog import BY_SKU, catalog_out, image_for, RP_PARTS
from .seed import TECHNICIANS, RECEPTIONISTS
from .access import staff_identity, STAFF_ROLES, DEMO_ADMIN, audit
from .operations_models import StaffUser
from .identity import reference_key, model_name
from .history import effective_report
from .ai import visible_result


def component_key(value):
    match = re.search(
        r"\b(?:L\d{3}-\d{3}[A-Za-z]*|TEST-PART-[A-Z0-9-]+)\b", value, re.I
    )
    return match.group(0).upper() if match else " ".join(value.lower().split())


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def password_hash(value, salt=None):
    salt = salt or secrets.token_hex(16)
    return (
        salt
        + ":"
        + hashlib.scrypt(value.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    )


def row(x):
    return {
        c.name: (v.isoformat() if hasattr(v, "isoformat") else v)
        for c in x.__table__.columns
        if (v := getattr(x, c.name)) is not None
        and c.name not in ["workspace_id", "password", "invite_hash"]
    }


class CustomerIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(default="", max_length=150)
    phone: str = Field(default="", max_length=40)
    sap_customer_code: str = Field(default="", max_length=80)
    kind: Literal["customer"] = "customer"


class AssetIn(BaseModel):
    customer_id: str
    name: str = Field(min_length=3, max_length=140)
    model: str = Field(min_length=1, max_length=100)
    manufacturer: str = Field(default="Lemmer", min_length=1, max_length=100)
    serial: str = Field(min_length=2, max_length=100)
    location: str = Field(default="Calgary", max_length=100)
    product_sku: str = Field(default="", max_length=50)
    kind: Literal["equipment", "vehicle"] = "equipment"
    vin: str = Field(default="", max_length=40)
    year: str = Field(default="", max_length=4)
    registration: str = Field(default="", max_length=30)
    sap_document_type: str = Field(default="", max_length=60)
    sap_document_number: str = Field(default="", max_length=80)
    sap_line_number: str = Field(default="", max_length=20)
    customer_confirmed: bool = False


class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=150)
    password: str = Field(min_length=10, max_length=128)
    invite: str = Field(default="", max_length=100)
    name: str = Field(default="", max_length=100)
    qr_share: str = Field(default="", max_length=80)
    qr_code: str = Field(default="", max_length=60)
    qr_token: str = Field(default="", max_length=64)

    @field_validator("email")
    @classmethod
    def email_valid(cls, v):
        v = v.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", v):
            raise ValueError("Enter a valid email address.")
        return v


class Symptom(BaseModel):
    asset_id: str
    description: str = Field(min_length=10, max_length=4000)


class Observations(BaseModel):
    observations: str = Field(min_length=10, max_length=2000)
    version: int


class OrderIn(Symptom):
    part: str = Field(min_length=2, max_length=150)
    quantity: int = Field(ge=1, le=100)
    request_id: str | None = None
    submission_id: str = Field(min_length=10, max_length=100)


class OrderUpdate(BaseModel):
    status: Literal[
        "Requested",
        "Reviewing compatibility",
        "Awaiting customer",
        "Ready",
        "Fulfilled",
        "Cancelled",
    ]
    notes: str = Field(default="", max_length=2000)


class RustReview(BaseModel):
    status: Literal["Confirmed", "Rejected", "Needs Review"]
    notes: str = Field(default="", max_length=2000)
    version: int


class VisitUpdate(BaseModel):
    status: Literal[
        "Checked in",
        "Bay preparation",
        "Ready for inspection",
        "Inspecting",
        "Findings review",
        "Treatment recorded",
        "Verification",
        "Completed",
        "Paused",
        "Failed",
        "Cancelled",
    ]
    version: int
    findings: str = Field(default="", max_length=3000)
    treatment: str = Field(default="", max_length=3000)
    verification: str = Field(default="", max_length=3000)


class ComponentIn(BaseModel):
    part: str = Field(min_length=2, max_length=150)
    installed: date
    interval_days: int | None = Field(default=None, ge=1, le=3650)
    basis: str = Field(min_length=10, max_length=1000)

    @field_validator("installed")
    @classmethod
    def past(cls, v):
        if v > date.today():
            raise ValueError("Installation cannot be in the future.")
        return v


def attach(
    app,
    dbdep,
    secret,
    cookie,
    session_out,
    create_request,
    NewRequest,
):
    def identity(request, db):
        try:
            wid, name, expiry, sig = request.cookies.get("lemmer_session", "").split(
                "|"
            )
            raw = f"{wid}|{name}|{expiry}"
            if int(expiry) < time.time() or not hmac.compare_digest(
                sig, hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
            ):
                raise ValueError()
            member = staff_identity(db, wid, name)
            if member:
                return member
            u = (
                db.get(PortalUser, name.removeprefix("@"))
                if name.startswith("@")
                else None
            )
            if not u or u.workspace_id != wid:
                raise ValueError()
            c = db.get(Customer, u.customer_id)
            return {
                "workspace": wid,
                "technician": c.name,
                "role": "customer",
                "customer_id": c.id,
                "user_id": u.id,
                "demo": u.demo,
            }
        except (ValueError, TypeError):
            raise HTTPException(401, "Please sign in to your account.")

    def who(request: Request, db=Depends(dbdep)):
        return identity(request, db)

    def staff(w, role=None):
        if w["role"] not in ([role, "superuser"] if role else STAFF_ROLES):
            raise HTTPException(
                403, "This action requires an authorized staff account."
            )

    def own(db, cls, key, w):
        x = db.get(cls, key)
        if not x or x.workspace_id != w["workspace"]:
            raise HTTPException(404, "Record not found.")
        return x

    def permitted(db, key, w):
        a = own(db, Asset, key, w)
        link = db.get(AssetOwner, key)
        if w["role"] not in STAFF_ROLES and (
            not link or link.customer_id != w["customer_id"]
        ):
            raise HTTPException(404, "Asset not found in your account.")
        return a, link

    def customer_visit(v, w):
        """A visit as its viewer may see it: customers never see AI wording or
        unreviewed/rejected rust-scan output, only scans a technician confirmed."""
        out = row(v)
        if w["role"] not in STAFF_ROLES:
            scan = out.get("report", {}).get("rust_scan")
            hidden = {"ai_suggestion"}
            if scan and scan.get("review_status") != "Confirmed":
                hidden.add("rust_scan")
            out["report"] = {
                k: val for k, val in out["report"].items() if k not in hidden
            }
        return out

    def work_token(asset):
        """Unguessable per-asset key carried by the customer QR code (not stored)."""
        return hmac.new(
            secret.encode(), ("work:" + asset.id).encode(), hashlib.sha256
        ).hexdigest()[:24]

    def qr_asset(db, share, code, token):
        ws = db.scalar(select(Workspace).where(Workspace.share == share))
        a = (
            db.scalar(
                select(Asset).where(Asset.workspace_id == ws.id, Asset.code == code)
            )
            if ws
            else None
        )
        if not a or not hmac.compare_digest(token or "", work_token(a)):
            raise HTTPException(404, "This QR code is not valid. Ask Lemmer for a new one.")
        return ws, a

    def output_session(request, db):
        w = identity(request, db)
        if w["role"] in STAFF_ROLES:
            result = session_out(db, w)
        else:
            ws = db.get(Workspace, w["workspace"])
            result = {
                "technician": w["technician"],
                "role": w["role"],
                "demo": w["demo"],
                "share": ws.share,
                "technicians": TECHNICIANS,
                "accounts": [],
                "ai_available": True,
            }
        if w["demo"]:
            accounts = [
                {"name": n, "role": "reception" if n in RECEPTIONISTS else "technician"}
                for n in TECHNICIANS + RECEPTIONISTS
            ]
            accounts.append({"name": DEMO_ADMIN, "role": "superuser"})
            for u in db.scalars(
                select(PortalUser).where(
                    PortalUser.workspace_id == w["workspace"], PortalUser.demo == True
                )
            ):
                c = db.get(Customer, u.customer_id)
                accounts.append(
                    {"name": "@" + u.id, "label": c.name, "role": "customer"}
                )
            result["accounts"] = accounts
        result["legacy_workspace"] = w["role"] in [
            "reception",
            "technician",
        ] and not db.scalar(
            select(AssetOwner.id)
            .where(AssetOwner.workspace_id == w["workspace"])
            .limit(1)
        )
        result["account_value"] = w.get("account_value") or (
            "@" + w["user_id"] if "user_id" in w else w["technician"]
        )
        return result

    app.state.portal_session = output_session
    app.state.portal_identity = identity

    @app.get("/api/catalog")
    def catalog():
        return catalog_out()

    @app.post("/api/accounts/switch")
    def switch(body: dict, response: Response, w=Depends(who), db=Depends(dbdep)):
        if not w["demo"]:
            raise HTTPException(
                403, "Role switching is only available for synthetic demo accounts."
            )
        name = body.get("name", "")
        if name not in TECHNICIANS + RECEPTIONISTS + [DEMO_ADMIN]:
            u = db.get(PortalUser, name.removeprefix("@"))
            if not u or not u.demo or u.workspace_id != w["workspace"]:
                raise HTTPException(403, "Unknown demo account.")
        cookie(response, w["workspace"], name)
        return {"ok": True}

    @app.post("/api/auth/signup")
    def signup(body: Credentials, response: Response, db=Depends(dbdep)):
        db.execute(text("SELECT pg_advisory_xact_lock(7771080)"))
        if db.scalar(select(StaffUser).where(StaffUser.email == body.email)):
            raise HTTPException(
                409, "An account already uses that email. Sign in instead."
            )
        existing = db.scalar(select(PortalUser).where(PortalUser.email == body.email))
        if existing and not body.invite:
            raise HTTPException(
                409, "An account already uses that email. Sign in instead."
            )
        if existing and (
            not existing.password
            or not hmac.compare_digest(
                password_hash(body.password, existing.password.split(":")[0]),
                existing.password,
            )
        ):
            raise HTTPException(
                401, "Use your existing account password to accept this invitation."
            )
        if body.invite:
            c = db.scalar(
                select(Customer)
                .where(Customer.invite_hash == digest(body.invite))
                .with_for_update()
            )
            if not c:
                raise HTTPException(422, "This invitation is invalid or already used.")
            if c.email and c.email.lower() != body.email:
                raise HTTPException(422, "Use the email address on the invitation.")
            c.invite_hash = None
        elif body.qr_token:
            # Created from a work-report QR: the account joins the asset's workspace
            # and can only read that asset's completed work.
            if existing:
                raise HTTPException(
                    409, "An account already uses that email. Sign in instead."
                )
            if len(body.name.strip()) < 2:
                raise HTTPException(422, "Enter your name.")
            ws, qa = qr_asset(db, body.qr_share, body.qr_code, body.qr_token)
            c = Customer(workspace_id=ws.id, name=body.name, email=body.email)
            db.add(c)
            db.flush()
            db.add(AssetViewer(asset_id=qa.id, customer_id=c.id))
        else:
            if len(body.name.strip()) < 2:
                raise HTTPException(422, "Enter your name.")
            if db.scalar(select(func.count()).select_from(Workspace)) >= 200:
                raise HTTPException(429, "Demo account limit reached.")
            ws = Workspace(share=secrets.token_urlsafe(24))
            db.add(ws)
            db.flush()
            c = Customer(workspace_id=ws.id, name=body.name, email=body.email)
            db.add(c)
            db.flush()
        if existing:
            if db.scalar(
                select(AssetOwner)
                .where(AssetOwner.customer_id == existing.customer_id)
                .limit(1)
            ):
                raise HTTPException(
                    409,
                    "Your existing account already has assets. Ask reception to coordinate the account link.",
                )
            u = existing
            u.workspace_id = c.workspace_id
            u.customer_id = c.id
        else:
            u = PortalUser(
                workspace_id=c.workspace_id,
                customer_id=c.id,
                email=body.email,
                password=password_hash(body.password),
                demo=False,
            )
            db.add(u)
        db.commit()
        cookie(response, c.workspace_id, "@" + u.id)
        return {"ok": True}

    @app.post("/api/auth/login")
    def login(body: Credentials, response: Response, db=Depends(dbdep)):
        member = db.scalar(select(StaffUser).where(StaffUser.email == body.email))
        if member:
            candidate = password_hash(body.password, member.password.split(":")[0])
            if not member.active or not hmac.compare_digest(candidate, member.password):
                raise HTTPException(401, "Email or password is incorrect.")
            cookie(
                response,
                member.workspace_id,
                "!" + member.id + ":" + str(member.session_version),
            )
            return {"ok": True}
        # Fixed-cost password verification also runs for unknown accounts.
        u = db.scalar(select(PortalUser).where(PortalUser.email == body.email))
        salt = u.password.split(":")[0] if u and u.password else "0" * 32
        candidate = password_hash(body.password, salt)
        if not u or not u.password or not hmac.compare_digest(candidate, u.password):
            raise HTTPException(401, "Email or password is incorrect.")
        cookie(response, u.workspace_id, "@" + u.id)
        return {"ok": True}

    @app.get("/api/customers")
    def customers(w=Depends(who), db=Depends(dbdep)):
        staff(w)
        return [
            {
                **row(c),
                "asset_codes": list(
                    db.scalars(
                        select(Asset.code)
                        .join(AssetOwner, AssetOwner.id == Asset.id)
                        .where(AssetOwner.customer_id == c.id)
                    )
                ),
                "asset_count": db.scalar(
                    select(func.count())
                    .select_from(AssetOwner)
                    .where(AssetOwner.customer_id == c.id)
                ),
            }
            for c in db.scalars(
                select(Customer)
                .where(Customer.workspace_id == w["workspace"])
                .order_by(Customer.name)
            )
        ]

    @app.post("/api/customers")
    def add_customer(body: CustomerIn, w=Depends(who), db=Depends(dbdep)):
        staff(w, "reception")
        if (
            db.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.workspace_id == w["workspace"])
            )
            >= 100
        ):
            raise HTTPException(429, "Demo customer limit reached.")
        if body.sap_customer_code and db.scalar(
            select(Customer).where(
                Customer.workspace_id == w["workspace"],
                Customer.sap_customer_code == body.sap_customer_code,
            )
        ):
            raise HTTPException(
                409, "SAP customer code already exists. Use that customer account."
            )
        c = Customer(workspace_id=w["workspace"], **body.model_dump())
        db.add(c)
        db.commit()
        return row(c)

    @app.post("/api/customers/{key}/invite")
    def invite(key: str, w=Depends(who), db=Depends(dbdep)):
        staff(w, "reception")
        c = own(db, Customer, key, w)
        if db.scalar(
            select(PortalUser).where(
                PortalUser.customer_id == c.id, PortalUser.demo == False
            )
        ):
            raise HTTPException(409, "This customer already has a login.")
        token = secrets.token_urlsafe(32)
        c.invite_hash = digest(token)
        db.commit()
        return {
            "token": token,
            "path": "/?invite=" + token,
            "message": "Share this private invitation with the intended customer. No message has been sent.",
        }

    @app.post("/api/registry")
    def register(body: AssetIn, w=Depends(who), db=Depends(dbdep)):
        staff(w, "reception")
        c = own(db, Customer, body.customer_id, w)
        if body.kind == "equipment" and not body.customer_confirmed:
            raise HTTPException(
                422, "Confirm the selected equipment owner before registering."
            )
        if body.product_sku and body.product_sku not in BY_SKU:
            raise HTTPException(422, "Unknown catalogue product.")
        db.execute(text("SELECT pg_advisory_xact_lock(7771043)"))
        count = db.scalar(
            select(func.count())
            .select_from(Asset)
            .where(Asset.workspace_id == w["workspace"])
        )
        if count >= 50:
            raise HTTPException(429, "Demo asset limit reached.")
        a = Asset(
            workspace_id=w["workspace"],
            code="LM-" + secrets.token_hex(3).upper(),
            name=body.name,
            model=model_name(body.product_sku, body.model),
            product_number=body.product_sku,
            manufacturer="Lemmer" if body.product_sku else body.manufacturer,
            serial=body.serial,
            customer=c.name,
            location=body.location,
            image=(
                "/images/vehicle.svg"
                if body.kind == "vehicle"
                else image_for(body.product_sku)
            ),
        )
        db.add(a)
        db.flush()
        db.add(
            AssetOwner(
                id=a.id,
                workspace_id=w["workspace"],
                customer_id=c.id,
                kind=body.kind,
                product_sku=body.product_sku,
                profile={
                    "vin": body.vin,
                    "year": body.year,
                    "registration": body.registration,
                    "sap_sale": {
                        "document_type": body.sap_document_type,
                        "document_number": body.sap_document_number,
                        "line_number": body.sap_line_number,
                        "method": "Manual reference only",
                    },
                },
            )
        )
        db.add(
            Event(
                workspace_id=w["workspace"],
                asset_id=a.id,
                kind="registration",
                title="Asset registered to customer",
                actor=w["technician"],
                body={"customer_id": c.id, "customer_name": c.name},
            )
        )
        db.commit()
        return row(a)

    @app.get("/api/portal/assets")
    def portal_assets(w=Depends(who), db=Depends(dbdep)):
        q = (
            select(Asset, AssetOwner)
            .join(AssetOwner, Asset.id == AssetOwner.id)
            .where(Asset.workspace_id == w["workspace"])
        )
        if "customer_id" in w:
            q = q.where(AssetOwner.customer_id == w["customer_id"])
        return [{**row(a), "ownership": row(o)} for a, o in db.execute(q)]

    @app.get("/api/portal/assets/{key}")
    def portal_asset(key: str, w=Depends(who), db=Depends(dbdep)):
        a, link = permitted(db, key, w)
        events = []
        for e in db.scalars(
            select(Event)
            .where(Event.asset_id == a.id)
            .order_by(Event.created_at.desc())
        ):
            # Original scans and internal intake notes are deliberately staff-only.
            if e.kind == "service":
                report_body = effective_report(db, e)
                events.append(
                    {
                        "id": e.id,
                        "title": e.title,
                        "created_at": e.created_at.isoformat(),
                        "body": {
                            k: report_body[k]
                            for k in [
                                "diagnosis",
                                "work",
                                "parts",
                                "test",
                                "outcome",
                                "inspection_date",
                                "part_lines",
                            ]
                            if k in report_body
                        },
                    }
                )
            elif e.kind == "inspection":
                events.append(row(e))
        requests = []
        for r in db.scalars(
            select(ServiceRequest)
            .where(ServiceRequest.asset_id == a.id)
            .order_by(ServiceRequest.created_at.desc())
        ):
            from .guidance import job_out

            job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == r.id))
            run = (
                db.get(AIRun, job.run_id)
                if job and job.status == "ready" and job.run_id
                else None
            )
            guidance = None
            if run and run.result.get("verdict"):
                result = visible_result(run.result)
                # Customer wording uses no private cross-customer case content or scans.
                guidance = {
                    "verdict": result["verdict"],
                    "parts": (
                        result.get("recommendation", {}).get("parts", [])
                        if result["verdict"] == "supported"
                        else []
                    ),
                    "summary": (
                        "Evidence review complete. Check the observations and any candidate parts below before deciding on a replacement."
                        if result["verdict"] == "supported"
                        else "More information or a technician assessment is needed."
                    ),
                    "cache_hit": result.get("cache_hit", False),
                }
                guidance["steps"] = (
                    [
                        x["text"]
                        for x in result.get("recommendation", {}).get(
                            "owner_guidance", []
                        )
                    ]
                    if result["verdict"] == "supported"
                    else []
                )
                visible = {
                    e["id"]
                    for e in result.get("evidence", [])
                    if e.get("owner_visible")
                }
                guidance["candidates"] = [
                    c
                    for c in result.get("part_candidates", [])
                    if all(x in visible for x in c["source_ids"])
                ]
                guidance["questions"] = (
                    result.get("recommendation", {}).get("questions", [])
                    if all(e.get("owner_visible") for e in result.get("evidence", []))
                    else [
                        "What readings, operating conditions and visible symptoms can you add to this report?"
                    ]
                )
            requests.append(
                {
                    "id": r.id,
                    "code": r.code,
                    "description": r.description,
                    "status": r.status,
                    "technician": r.technician,
                    "guidance": guidance,
                    "guidance_job": job_out(job),
                    "version": r.version,
                }
            )
        estimates = []
        latest = {}
        for x in db.scalars(
            select(ComponentRecord)
            .where(ComponentRecord.asset_id == a.id)
            .order_by(ComponentRecord.installed.desc())
        ):
            latest.setdefault(component_key(x.part), x)
        for x in latest.values():
            d = row(x)
            if x.interval_days:
                due = date.fromisoformat(x.installed) + timedelta(days=x.interval_days)
                d.update(
                    review_date=due.isoformat(), days_left=(due - date.today()).days
                )
            estimates.append(d)
        from .ai import parts_for, documents

        references = (
            [
                {"title": d["title"], "url": d["url"]}
                for d in documents(reference_key(a))
            ]
            if a.manufacturer.lower() == "lemmer"
            else []
        )
        released = []
        for e in db.scalars(
            select(Event).where(Event.asset_id == a.id, Event.kind == "document_shared")
        ):
            released.append(
                {
                    "id": e.body["document_id"],
                    "title": e.body["filename"],
                    "url": "/api/owner-documents/" + e.body["document_id"],
                }
            )
        return {
            "released_documents": released,
            "references": references,
            "asset": row(a),
            "ownership": row(link) if link else None,
            "events": events,
            "requests": requests,
            "maintenance": estimates,
            "parts": parts_for(reference_key(a)),
            "visits": [
                customer_visit(v, w)
                for v in db.scalars(
                    select(Inspection)
                    .where(Inspection.asset_id == a.id)
                    .order_by(Inspection.created_at.desc())
                )
            ],
        }

    @app.post("/api/portal/symptoms")
    def symptom(body: Symptom, w=Depends(who), db=Depends(dbdep)):
        a, link = permitted(db, body.asset_id, w)
        if "customer_id" not in w:
            raise HTTPException(403, "Use staff intake to create a service request.")
        c = db.get(Customer, w["customer_id"])
        request = NewRequest(
            asset_id=a.id,
            title=body.description[:100],
            description=body.description,
            category="Customer symptom",
            name=c.name,
            email=c.email,
            phone=c.phone,
        )
        created = create_request(request, w["workspace"], db)
        return created

    def retry_job(r, db, force=False):
        from .guidance import enqueue, job_out

        job = enqueue(db, r)
        if force or job.status == "unavailable":
            if not force and (now() - job.updated_at).total_seconds() < 60:
                raise HTTPException(
                    429, "Please wait one minute before retrying the model service."
                )
            job.status, job.run_id, job.attempts, job.message = (
                "queued",
                None,
                0,
                "Preparing an evidence review…",
            )
            job.updated_at = now()
        db.commit()
        return job_out(job)

    @app.post("/api/portal/requests/{key}/retry")
    def owner_retry(key: str, w=Depends(who), db=Depends(dbdep)):
        r = db.scalar(
            select(ServiceRequest)
            .where(
                ServiceRequest.id == key, ServiceRequest.workspace_id == w["workspace"]
            )
            .with_for_update()
        )
        if not r:
            raise HTTPException(404, "Request not found.")
        permitted(db, r.asset_id, w)
        if r.status == "Closed":
            raise HTTPException(409, "This request is completed.")
        return retry_job(r, db)

    @app.post("/api/portal/requests/{key}/observations")
    def owner_observations(
        key: str, body: Observations, w=Depends(who), db=Depends(dbdep)
    ):
        r = db.scalar(
            select(ServiceRequest)
            .where(
                ServiceRequest.id == key, ServiceRequest.workspace_id == w["workspace"]
            )
            .with_for_update()
        )
        if not r:
            raise HTTPException(404, "Request not found.")
        permitted(db, r.asset_id, w)
        return update_observations(r, body, db)

    def update_observations(r, body, db):
        if r.status == "Closed" or r.version != body.version:
            raise HTTPException(
                409, "This repair changed or is completed. Refresh the workspace."
            )
        description = r.description + "\nAdditional observations: " + body.observations
        if len(description) > 4000:
            raise HTTPException(
                422, "The report is full. Start a new repair for additional findings."
            )
        r.description, r.version, r.updated_at = description, r.version + 1, now()
        return retry_job(r, db, True)

    @app.get("/api/parts-requests")
    def orders(w=Depends(who), db=Depends(dbdep)):
        q = (
            select(PartOrder)
            .where(PartOrder.workspace_id == w["workspace"])
            .order_by(PartOrder.created_at.desc())
        )
        if "customer_id" in w:
            q = q.where(PartOrder.customer_id == w["customer_id"])
        return [
            {
                **row(o),
                "customer": row(db.get(Customer, o.customer_id)),
                "asset": row(db.get(Asset, o.asset_id)),
            }
            for o in db.scalars(q)
        ]

    @app.post("/api/parts-requests")
    def order(body: OrderIn, w=Depends(who), db=Depends(dbdep)):
        a, link = permitted(db, body.asset_id, w)
        if not link:
            raise HTTPException(422, "Assign this asset to a customer first.")
        db.execute(text("SELECT pg_advisory_xact_lock(7771081)"))
        submission = digest(w["workspace"] + link.customer_id + body.submission_id)
        old = db.scalar(select(PartOrder).where(PartOrder.submission_id == submission))
        if old:
            return row(old)
        if body.request_id:
            r = own(db, ServiceRequest, body.request_id, w)
            if r.asset_id != a.id:
                raise HTTPException(
                    422, "Service request does not belong to this asset."
                )
        if (
            db.scalar(
                select(func.count())
                .select_from(PartOrder)
                .where(PartOrder.workspace_id == w["workspace"])
            )
            >= 200
        ):
            raise HTTPException(429, "Demo parts request limit reached.")
        o = PartOrder(
            workspace_id=w["workspace"],
            customer_id=link.customer_id,
            asset_id=a.id,
            request_id=body.request_id,
            part=body.part,
            quantity=body.quantity,
            problem=body.description,
            submission_id=submission,
        )
        db.add(o)
        db.commit()
        return row(o)

    @app.patch("/api/parts-requests/{key}")
    def update_order(key: str, body: OrderUpdate, w=Depends(who), db=Depends(dbdep)):
        staff(w, "reception")
        o = own(db, PartOrder, key, w)
        o.status = body.status
        o.notes = body.notes
        db.commit()
        return row(o)

    @app.post("/api/portal/assets/{key}/components")
    def component(key: str, body: ComponentIn, w=Depends(who), db=Depends(dbdep)):
        staff(w, "technician")
        a, _ = permitted(db, key, w)
        c = ComponentRecord(
            workspace_id=w["workspace"],
            asset_id=a.id,
            **{**body.model_dump(), "installed": body.installed.isoformat()},
        )
        db.add(c)
        db.commit()
        return row(c)

    @app.get("/api/visits")
    def visits(w=Depends(who), db=Depends(dbdep)):
        staff(w)
        return [
            {**row(v), "asset": row(db.get(Asset, v.asset_id))}
            for v in db.scalars(
                select(Inspection)
                .where(Inspection.workspace_id == w["workspace"])
                .order_by(Inspection.created_at.desc())
            )
        ]

    @app.post("/api/visits")
    def new_visit(body: dict, w=Depends(who), db=Depends(dbdep)):
        staff(w)
        a, link = permitted(db, body.get("asset_id", ""), w)
        if not link or link.kind != "vehicle":
            raise HTTPException(422, "Select a vehicle passport.")
        db.execute(text("SELECT pg_advisory_xact_lock(7771082)"))
        existing = db.scalar(
            select(Inspection).where(
                Inspection.asset_id == a.id,
                Inspection.status.not_in(["Completed", "Cancelled", "Failed"]),
            )
        )
        if existing:
            return row(existing)
        if (
            db.scalar(
                select(func.count())
                .select_from(Inspection)
                .where(Inspection.workspace_id == w["workspace"])
            )
            >= 100
        ):
            raise HTTPException(429, "Demo visit limit reached.")
        v = Inspection(
            workspace_id=w["workspace"],
            asset_id=a.id,
            report={
                "source": "Simulated workflow; no robot connected",
                "before": "/images/inspection-before.svg",
                "after": None,
            },
        )
        db.add(v)
        db.commit()
        return row(v)

    @app.post("/api/visits/{key}/media/{kind}")
    async def upload_visit_image(
        key: str,
        kind: Literal["before", "after"],
        file: UploadFile = File(...),
        w=Depends(who),
        db=Depends(dbdep),
    ):
        staff(w, "technician")
        v = own(db, Inspection, key, w)
        if v.status in ["Completed", "Cancelled", "Failed"]:
            raise HTTPException(
                409, "This visit is closed. Start a new visit to add evidence."
            )
        raw = await file.read(2_500_001)
        if not raw or len(raw) > 2_500_000:
            raise HTTPException(413, "Use a JPG or PNG smaller than 2.5 MB.")
        from .intake import validate_file

        content_type = validate_file(raw)
        if not content_type.startswith("image/"):
            raise HTTPException(422, "Use a JPG or PNG inspection image.")
        db.execute(text("SELECT pg_advisory_xact_lock(7771083)"))
        if (
            db.scalar(select(func.count()).select_from(InspectionMedia)) >= 200
            or db.scalar(
                select(func.count())
                .select_from(InspectionMedia)
                .where(InspectionMedia.workspace_id == w["workspace"])
            )
            >= 20
        ):
            raise HTTPException(429, "Demo inspection image limit reached.")
        db.refresh(v, with_for_update=True)
        if v.status in ["Completed", "Cancelled", "Failed"]:
            raise HTTPException(409, "This visit was closed while uploading.")
        media = InspectionMedia(
            workspace_id=w["workspace"],
            visit_id=v.id,
            kind=kind,
            content_type=content_type,
            payload=raw,
        )
        db.add(media)
        db.flush()
        report = {
            **v.report,
            kind: "/api/visit-media/" + media.id,
            kind + "_source": "Uploaded by technician",
        }
        if kind == "before":
            # A scan (and wording suggested from it) describes the previous
            # picture; drop both so old regions are never drawn over, or
            # confirmed against, the new one. A confirmed scan is kept
            # permanently in its own passport timeline event.
            report.pop("rust_scan", None)
            report.pop("ai_suggestion", None)
        v.report = report
        v.version += 1
        db.commit()
        return row(v)

    @app.get("/api/visit-media/{key}")
    def visit_image(key: str, w=Depends(who), db=Depends(dbdep)):
        media = own(db, InspectionMedia, key, w)
        v = db.get(Inspection, media.visit_id)
        permitted(db, v.asset_id, w)
        return Response(
            media.payload,
            media_type=media.content_type,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/rust-scan/model")
    def rust_scan_model(w=Depends(who)):
        """Which detector is active, how it was evaluated and its limitations."""
        from .rust_scan import model_info

        staff(w)
        return model_info()

    @app.post("/api/visits/{key}/rust-scan")
    def rust_scan(key: str, w=Depends(who), db=Depends(dbdep)):
        """Scan the visit's 'before' image for rust. The result is a suggestion."""
        from .rust_scan import detect, DetectorError

        staff(w, "technician")
        v = own(db, Inspection, key, w)
        db.refresh(v, with_for_update=True)
        if v.status in ["Completed", "Cancelled", "Failed"]:
            raise HTTPException(409, "This visit is closed. Start a new visit.")
        if (v.report.get("rust_scan") or {}).get("review_status") == "Confirmed":
            raise HTTPException(
                409,
                "This photo's scan is confirmed and recorded on the passport. "
                "Upload a new photo to scan another area.",
            )
        source = str(v.report.get("before") or "")
        if not source.startswith("/api/visit-media/"):
            raise HTTPException(
                422, "Upload a 'before' inspection image before running a rust scan."
            )
        media = own(db, InspectionMedia, source.rsplit("/", 1)[1], w)
        try:
            result = detect(media.payload, media.content_type)
        except DetectorError as exc:
            raise HTTPException(503, str(exc))
        result["source_media_id"] = media.id
        v.report = {**v.report, "rust_scan": result}
        v.version += 1
        db.commit()
        return row(v)

    @app.post("/api/visits/{key}/ai-suggestion")
    def ai_suggestion(key: str, w=Depends(who), db=Depends(dbdep)):
        """AI-suggested findings/treatment/verification, kept apart from the technician's record."""
        from .ai_suggest import suggest

        staff(w, "technician")
        v = own(db, Inspection, key, w)
        db.refresh(v, with_for_update=True)
        if v.status in ["Completed", "Cancelled", "Failed"]:
            raise HTTPException(409, "This visit is closed. Start a new visit.")
        scan = v.report.get("rust_scan")
        if not scan:
            raise HTTPException(422, "Run a rust scan first.")
        v.report = {**v.report, "ai_suggestion": suggest(scan)}
        v.version += 1
        db.commit()
        return row(v)

    @app.patch("/api/visits/{key}/rust-scan/review")
    def rust_scan_review(
        key: str, body: RustReview, w=Depends(who), db=Depends(dbdep)
    ):
        """Technician decision on a rust scan: who decided and when is recorded."""
        staff(w, "technician")
        v = own(db, Inspection, key, w)
        db.refresh(v, with_for_update=True)
        if v.version != body.version:
            raise HTTPException(409, "Visit changed. Reload before saving.")
        if v.status in ["Completed", "Cancelled", "Failed"]:
            raise HTTPException(409, "This visit is closed. Start a new visit.")
        scan = v.report.get("rust_scan")
        if not scan:
            raise HTTPException(422, "Run a rust scan first.")
        if scan.get("review_status") == "Confirmed":
            # The confirmed result is already on the owner's passport timeline;
            # changing it here would leave the two records disagreeing.
            raise HTTPException(
                409, "This scan is already confirmed and recorded on the passport."
            )
        from datetime import datetime, timezone

        scan = {
            **scan,
            "review_status": body.status,
            "review_notes": body.notes.strip(),
            "reviewed_by": w["technician"],
            "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        v.report = {**v.report, "rust_scan": scan}
        v.version += 1
        if body.status == "Confirmed":
            # Only technician-confirmed results reach the passport timeline
            # (which owners can see); unreviewed AI output stays on the visit.
            db.add(
                Event(
                    workspace_id=w["workspace"],
                    asset_id=v.asset_id,
                    kind="inspection",
                    title=(
                        "Rust scan confirmed by technician (simulated detector)"
                        if scan["simulated"]
                        else "Rust scan confirmed by technician"
                    ),
                    actor=w["technician"],
                    body={"visit_id": v.id, "rust_scan": scan},
                )
            )
        db.commit()
        return row(v)

    @app.patch("/api/visits/{key}")
    def visit(key: str, body: VisitUpdate, w=Depends(who), db=Depends(dbdep)):
        staff(w, "technician")
        v = own(db, Inspection, key, w)
        db.refresh(v, with_for_update=True)
        if v.version != body.version:
            raise HTTPException(409, "Visit changed. Reload before saving.")
        if v.status in ["Completed", "Cancelled", "Failed"]:
            raise HTTPException(409, "This visit is closed. Create a new visit.")
        stages = [
            "Checked in",
            "Bay preparation",
            "Ready for inspection",
            "Inspecting",
            "Findings review",
            "Treatment recorded",
            "Verification",
            "Completed",
        ]
        if body.status not in ["Paused", "Failed", "Cancelled"]:
            old = (
                v.report.get("resume_status", "Checked in")
                if v.status == "Paused"
                else v.status
            )
            if stages.index(body.status) not in [
                stages.index(old),
                min(stages.index(old) + 1, len(stages) - 1),
            ]:
                raise HTTPException(
                    422, "Complete the current stage before proceeding."
                )
        if (
            body.status
            in ["Findings review", "Treatment recorded", "Verification", "Completed"]
            and not body.findings.strip()
        ):
            raise HTTPException(422, "Record inspection findings first.")
        if (
            body.status in ["Treatment recorded", "Verification", "Completed"]
            and not body.treatment.strip()
        ):
            raise HTTPException(
                422, "Record treatment or explain why none was performed."
            )
        if body.status == "Completed" and not body.verification.strip():
            raise HTTPException(422, "Record verification before completion.")
        v.report = {
            **v.report,
            **body.model_dump(exclude={"status", "version"}),
            "resume_status": (
                v.status if v.status != "Paused" else v.report.get("resume_status")
            ),
            "after": v.report.get("after")
            or (
                "/images/inspection-after.svg"
                if body.status in ["Verification", "Completed"]
                else None
            ),
        }
        v.status = body.status
        v.version += 1
        if body.status == "Completed":
            db.add(
                Event(
                    workspace_id=w["workspace"],
                    asset_id=v.asset_id,
                    kind="inspection",
                    title="Simulated rustproofing visit completed",
                    actor=w["technician"],
                    body={
                        # AI wording and unreviewed or rejected scans stay off the
                        # passport. Confirmed scans already have their own
                        # timeline event, so they are not repeated here.
                        **{
                            k: val
                            for k, val in v.report.items()
                            if k not in ["rust_scan", "ai_suggestion"]
                        },
                        "visit_id": v.id,
                        "simulated": True,
                    },
                )
            )
        db.commit()
        return row(v)

    @app.get("/api/assets/{key}/work-qr")
    def work_qr(key: str, w=Depends(who), db=Depends(dbdep)):
        staff(w)
        a = own(db, Asset, key, w)
        return {"token": work_token(a)}

    @app.post("/api/work/{share}/{code}/join")
    def work_join(share: str, code: str, token: str, w=Depends(who), db=Depends(dbdep)):
        """A signed-in customer who scanned the asset's QR gets read access to it."""
        ws, a = qr_asset(db, share, code, token)
        if w["role"] == "customer" and w["workspace"] == ws.id:
            if not db.get(AssetViewer, (a.id, w["customer_id"])):
                db.add(AssetViewer(asset_id=a.id, customer_id=w["customer_id"]))
                db.commit()
        return {"ok": True}

    @app.get("/api/work/{share}/{code}")
    def work_report(share: str, code: str, w=Depends(who), db=Depends(dbdep)):
        """Read-only view of the technician's confirmed work for the asset owner or staff.

        Only what the technician recorded or confirmed is shown. No customer
        details, location, technician names or unreviewed AI output.
        """
        ws = db.scalar(select(Workspace).where(Workspace.share == share))
        a = (
            db.scalar(
                select(Asset).where(Asset.workspace_id == ws.id, Asset.code == code)
            )
            if ws
            else None
        )
        if not a or w["workspace"] != ws.id:
            raise HTTPException(404, "Work report not found. Check the QR code.")
        if w["role"] not in STAFF_ROLES:  # customers: the owner or a QR-granted viewer
            owner = db.get(AssetOwner, a.id)
            viewer = db.get(AssetViewer, (a.id, w["customer_id"]))
            if not viewer and not (owner and owner.customer_id == w["customer_id"]):
                raise HTTPException(404, "Work report not found. Check the QR code.")
        events = db.scalars(
            select(Event)
            .where(Event.asset_id == a.id, Event.kind.in_(["inspection", "service"]))
            .order_by(Event.created_at.desc())
            .limit(20)
        ).all()
        items = []
        for e in events:
            # Service reports show their latest amended wording, as on the passport.
            b = (effective_report(db, e) if e.kind == "service" else e.body) or {}
            scan = b.get("rust_scan") or {}
            if scan.get("review_status") != "Confirmed":
                scan = None
            items.append(
                {
                    "date": e.created_at.isoformat(),
                    "kind": e.kind,
                    "title": e.title,
                    "symptom": str(b.get("symptom") or "")[:1000],
                    "work": str(b.get("work") or "")[:2000],
                    "test": str(b.get("test") or "")[:1000],
                    "outcome": str(b.get("outcome") or "")[:60],
                    "parts": [str(x)[:80] for x in (b.get("parts") or [])][:20],
                    "findings": str(b.get("findings") or "")[:2000],
                    "treatment": str(b.get("treatment") or "")[:2000],
                    "verification": str(b.get("verification") or "")[:2000],
                    "rust_review": (
                        {
                            "regions": len(scan.get("findings", [])),
                            "area_pct": scan.get("area_pct"),
                            "severity": scan.get("severity"),
                            "reviewed_at": scan.get("reviewed_at"),
                            "notes": str(scan.get("review_notes") or "")[:1000],
                            "model": (scan.get("model") or {}).get("name"),
                        }
                        if scan
                        else None
                    ),
                }
            )
        return {"asset": {"name": a.name, "code": a.code}, "work": items}

    @app.get("/api/qr/{share}/{code}")
    def resolve_qr(share: str, code: str, w=Depends(who), db=Depends(dbdep)):
        ws = db.scalar(select(Workspace).where(Workspace.share == share))
        if not ws or ws.id != w["workspace"]:
            raise HTTPException(404, "This passport is not assigned to your account.")
        a = db.scalar(
            select(Asset).where(Asset.workspace_id == ws.id, Asset.code == code)
        )
        if not a:
            raise HTTPException(404, "Passport not found.")
        permitted(db, a.id, w)
        return {"id": a.id}


def seed_expansion(db, w):
    """Seed a new workspace from the owner's synthetic workbook dataset."""
    from .owner_dataset import seed_owner_dataset

    seeded = seed_owner_dataset(db, w)
    first_customer = seeded["customers"]["TEST-CUST-001"]
    a = Asset(
        workspace_id=w.id,
        code="VH-1001",
        name="Synthetic workflow vehicle",
        model="Transit",
        manufacturer="Ford",
        serial="DEMO-VEHICLE-001",
        customer=first_customer.name,
        location="Calgary bay 1",
        image="/images/vehicle.svg",
        condition="Inspection due",
    )
    db.add(a)
    db.flush()
    db.add(
        AssetOwner(
            id=a.id,
            workspace_id=w.id,
            customer_id=first_customer.id,
            kind="vehicle",
            profile={
                "vin": "DEMO VIN · not a real vehicle",
                "year": "2021",
                "registration": "DEMO-01",
            },
        )
    )
    db.add(
        Inspection(
            workspace_id=w.id,
            asset_id=a.id,
            status="Completed",
            created_at=now() - timedelta(days=180),
            report={
                "source": "Synthetic previous visit",
                "findings": "Illustrative surface corrosion around rear crossmember.",
                "treatment": "Simulated treatment recorded.",
                "verification": "Simulated before/after comparison.",
                "before": "/images/inspection-before.svg",
                "after": "/images/inspection-after.svg",
            },
        )
    )
    db.commit()
