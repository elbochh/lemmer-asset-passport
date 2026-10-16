"""Explicit staff roles. Customer accounts never acquire staff permissions."""

from fastapi import HTTPException
from sqlalchemy import select
from .database import Workspace
from .operations_models import Company, Location, StaffUser, AuditEntry
from .seed import TECHNICIANS, RECEPTIONISTS

DEMO_ADMIN = "Demo super-user"
STAFF_ROLES = ["reception", "technician", "superuser"]


def role(w):
    return w.get("role") or (
        "superuser"
        if w["technician"] == DEMO_ADMIN
        else "reception" if w["technician"] in RECEPTIONISTS else "technician"
    )


def require(w, *roles):
    if role(w) not in roles:
        raise HTTPException(403, "This action is not permitted for your role.")


def ensure_site(db, wid):
    from sqlalchemy import text

    db.execute(text("SELECT pg_advisory_xact_lock(7771110)"))
    company = db.scalar(select(Company).where(Company.workspace_id == wid))
    if not company:
        company = Company(workspace_id=wid)
        db.add(company)
        db.flush()
        db.add(Location(company_id=company.id, name="Calgary"))
        db.flush()
    return db.scalar(select(Location).where(Location.company_id == company.id))


def staff_identity(db, wid, key):
    if key in TECHNICIANS + RECEPTIONISTS + [DEMO_ADMIN]:
        if not db.get(Workspace, wid):
            raise ValueError()
        return {
            "workspace": wid,
            "technician": key,
            "role": role({"technician": key}),
            "demo": True,
        }
    if not key.startswith("!"):
        return None
    uid, version = key[1:].split(":")
    u = db.get(StaffUser, uid)
    if (
        not u
        or not u.active
        or u.workspace_id != wid
        or u.session_version != int(version)
    ):
        raise ValueError()
    return {
        "workspace": wid,
        "technician": u.name,
        "role": u.role,
        "demo": False,
        "staff_id": u.id,
        "location_id": u.location_id,
        "account_value": key,
    }


def technician_names(db, wid, demo=True):
    return (TECHNICIANS if demo else []) + list(
        db.scalars(
            select(StaffUser.name).where(
                StaffUser.workspace_id == wid,
                StaffUser.active == True,
                StaffUser.role == "technician",
            )
        )
    )


def audit(db, w, action, key, before, after, reason):
    db.add(
        AuditEntry(
            workspace_id=w["workspace"],
            actor=w["technician"],
            actor_id=w.get("staff_id", "demo:" + w["technician"]),
            action=action,
            object_id=key,
            before=before,
            after=after,
            reason=reason,
        )
    )
