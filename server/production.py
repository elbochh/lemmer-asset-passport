"""Production mode: no demonstration workspaces, real staff accounts only.

DEMO_MODE=1 (default) keeps the public demonstration behaviour.
DEMO_MODE=0 turns it off: one company workspace is created on first start and
the first super-user comes from ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_NAME.
The super-user then creates the other staff accounts in the app.
"""

import os, re, secrets
from fastapi import HTTPException
from sqlalchemy import select, func


def is_demo() -> bool:
    return os.getenv("DEMO_MODE", "1") != "0"


def forbid_in_production(message="This action is only available in the demonstration."):
    if not is_demo():
        raise HTTPException(403, message)


def staff_limit() -> int:
    return 30 if is_demo() else 500


def bootstrap(db):
    """Create the company workspace and first super-user. Safe to run on every start."""
    from .database import Workspace
    from .operations_models import StaffUser
    from .access import ensure_site
    from .expansion import password_hash

    if is_demo():
        return
    if db.scalar(select(StaffUser.id).limit(1)):
        return
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    name = os.getenv("ADMIN_NAME", "").strip() or "Administrator"
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(password) < 10:
        raise RuntimeError(
            "Production mode (DEMO_MODE=0) needs ADMIN_EMAIL and an ADMIN_PASSWORD "
            "of at least 10 characters to create the first super-user."
        )
    ws = db.scalar(select(Workspace).limit(1))
    if not ws:
        ws = Workspace(share=secrets.token_urlsafe(24))
        db.add(ws)
        db.flush()
    site = ensure_site(db, ws.id)
    db.add(
        StaffUser(
            workspace_id=ws.id,
            location_id=site.id,
            name=name,
            email=email,
            password=password_hash(password),
            role="superuser",
        )
    )
    db.commit()
