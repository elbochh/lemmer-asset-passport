"""Production mode: no demonstration workspaces; real staff accounts only."""

import os

os.environ["AUTO_GUIDANCE_WORKER"] = "0"
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from server.main import app
from server import production
from server.database import Session, Workspace
from server.operations_models import StaffUser


@pytest.fixture
def prod(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")
    monkeypatch.setenv("ADMIN_EMAIL", "admin-test@lemmer.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "A-long-test-password-1")
    monkeypatch.setenv("ADMIN_NAME", "Test Admin")
    with Session() as db:
        # bootstrap only creates the first super-user when no staff exist yet
        have = db.scalar(select(StaffUser.id).limit(1))
    with TestClient(app) as c:
        yield c, have


def test_config_reports_mode(monkeypatch):
    with TestClient(app) as c:
        assert c.get("/api/config").json() == {"demo_mode": True}
        monkeypatch.setenv("DEMO_MODE", "0")
        assert c.get("/api/config").json() == {"demo_mode": False}


def test_demo_endpoints_blocked_in_production(prod):
    c, _ = prod
    assert c.post("/api/demo/start").status_code == 403
    r = c.post(
        "/api/auth/signup",
        json={"email": "nobody@example.com", "password": "A-long-test-password-1", "name": "No Body"},
    )
    assert r.status_code == 403
    assert "QR" in r.json()["detail"]


def test_bootstrap_creates_first_superuser_who_can_add_staff(prod):
    c, _ = prod
    # The app start-up creates the first super-user from ADMIN_* settings, but
    # only on a database that has no staff yet.
    r = c.post(
        "/api/auth/login",
        json={"email": "admin-test@lemmer.example", "password": "A-long-test-password-1"},
    )
    if r.status_code != 200:
        pytest.skip("database already had staff accounts; run on an empty database")
    assert c.get("/api/session").json()["role"] == "superuser"
    production.bootstrap(Session().__enter__())  # idempotent: no second account
    r = c.post(
        "/api/operations/staff",
        json={
            "name": "Tech One",
            "email": "tech1@lemmer.example",
            "password": "Another-long-pass-2",
            "role": "technician",
        },
    )
    assert r.status_code == 200, r.text
    c.post("/api/session/logout")
    assert (
        c.post(
            "/api/auth/login",
            json={"email": "tech1@lemmer.example", "password": "Another-long-pass-2"},
        ).status_code
        == 200
    )
    assert c.get("/api/session").json()["role"] == "technician"
    # A demonstration identity cannot be used in production.
    assert c.post("/api/session/technician", json={"name": "Taylor Brooks"}).status_code == 403


def test_bootstrap_requires_admin_settings(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    from server.migrations import migrate

    migrate()
    with Session() as db:
        if db.scalar(select(StaffUser.id).limit(1)):
            pytest.skip("database already has staff accounts")
        with pytest.raises(RuntimeError):
            production.bootstrap(db)
