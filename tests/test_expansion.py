"""End-to-end PostgreSQL checks for ownership and the new role workflows."""

import os, uuid

os.environ["AUTO_GUIDANCE_WORKER"] = "0"
import pytest
from fastapi.testclient import TestClient
from server.main import app
from server.database import Session, Asset, Event, AIRun
from server.expansion_models import GuidanceCache, Customer, PortalUser
from server.ai import cache_key, cached_result
from server.guidance import process_one


@pytest.fixture
def demo():
    with TestClient(app) as c:
        assert c.post("/api/demo/start").status_code == 200
        yield c


def switch(c, role):
    accounts = c.get("/api/session").json()["accounts"]
    account = next(
        a
        for a in accounts
        if (
            a.get("label") == "Prairie Fleet Services"
            if role == "second_customer"
            else a["role"] == role
        )
    )
    assert (
        c.post("/api/accounts/switch", json={"name": account["name"]}).status_code
        == 200
    )
    return c.get("/api/session").json()


def test_catalog_and_customer_asset_isolation(demo):
    c = demo
    catalog = c.get("/api/catalog").json()
    assert len(catalog) == 103
    assert all("L-1095" not in p["name"] for p in catalog)
    staff_assets = c.get("/api/assets").json()
    session = switch(c, "customer")
    assets = c.get("/api/portal/assets").json()
    assert len(assets) == 3
    forbidden = next(
        a for a in staff_assets if a["customer"] == "Prairie Fleet Services"
    )
    assert c.get("/api/portal/assets/" + forbidden["id"]).status_code == 404
    assert c.get("/api/assets").status_code == 403
    assert c.get("/api/knowledge").status_code == 403
    assert c.get("/api/export").status_code == 403
    assert (
        c.post(
            "/api/registry",
            json={"customer_id": "x", "name": "ABC", "model": "x", "serial": "123"},
        ).status_code
        == 403
    )
    assert c.get(f"/api/qr/{session['share']}/{forbidden['code']}").status_code == 404
    assert c.get(f"/api/qr/{session['share']}/{assets[0]['code']}").status_code == 200
    with TestClient(app) as anonymous:
        assert (
            anonymous.get(
                f"/api/public/{session['share']}/{assets[0]['code']}"
            ).status_code
            == 401
        )


def test_reception_assigns_two_assets_and_customer_signup(demo):
    c = demo
    switch(c, "reception")
    email = "test-" + uuid.uuid4().hex + "@example.test"
    customer = c.post(
        "/api/customers", json={"name": "Test owner", "email": email}
    ).json()
    for i in range(2):
        r = c.post(
            "/api/registry",
            json={
                "customer_id": customer["id"],
                "customer_confirmed": True,
                "name": f"Other brand pump {i}",
                "manufacturer": "Other maker",
                "model": "External-20",
                "serial": f"EXT-{i}",
            },
        )
        assert r.status_code == 200, r.text
    assert (
        next(x for x in c.get("/api/customers").json() if x["id"] == customer["id"])[
            "asset_count"
        ]
        == 2
    )
    invite = c.post("/api/customers/" + customer["id"] + "/invite").json()["token"]
    with TestClient(app) as customer_client:
        credentials = {
            "name": "Test owner",
            "email": email,
            "password": "Test-only-long-password",
            "invite": invite,
        }
        r = customer_client.post("/api/auth/signup", json=credentials)
        assert r.status_code == 200, r.text
        assert len(customer_client.get("/api/portal/assets").json()) == 2
        assert (
            customer_client.post(
                "/api/accounts/switch", json={"name": "Alex Morgan"}
            ).status_code
            == 403
        )
        assert customer_client.get("/api/customers").status_code == 403
        customer_client.post("/api/session/logout")
        assert customer_client.get("/api/portal/assets").status_code == 401
        assert (
            customer_client.post("/api/auth/login", json=credentials).status_code == 200
        )
        assert (
            customer_client.post(
                "/api/auth/login",
                json={**credentials, "password": "Wrong-password-test"},
            ).status_code
            == 401
        )
        assert len(customer_client.get("/api/portal/assets").json()) == 2


def test_parts_request_handoff_idempotence_and_access(demo):
    c = demo
    switch(c, "customer")
    a = c.get("/api/portal/assets").json()[0]
    r = c.post(
        "/api/portal/symptoms",
        json={
            "asset_id": a["id"],
            "description": "Fluid seeps around the needle packing after use.",
        },
    )
    assert r.status_code == 200, r.text
    req = r.json()
    assert req["guidance"]["status"] == "queued"
    body = {
        "asset_id": a["id"],
        "description": req["description"],
        "request_id": req["id"],
        "part": "L015-291",
        "quantity": 1,
        "submission_id": "same-submission-123",
    }
    first = c.post("/api/parts-requests", json=body)
    assert first.status_code == 200, first.text
    second = c.post("/api/parts-requests", json=body)
    assert first.json()["id"] == second.json()["id"]
    assert len(c.get("/api/parts-requests").json()) == 1
    switch(c, "second_customer")
    assert c.get("/api/parts-requests").json() == []
    assert (
        c.post(
            "/api/parts-requests",
            json={**body, "submission_id": "other-submission-123"},
        ).status_code
        == 404
    )
    switch(c, "reception")
    order = c.get("/api/parts-requests").json()[0]
    assert order["asset"]["id"] == a["id"]
    assert order["problem"] == req["description"]
    assert (
        c.patch(
            "/api/parts-requests/" + order["id"],
            json={
                "status": "Reviewing compatibility",
                "notes": "Checking the exact gun variant.",
            },
        ).status_code
        == 200
    )
    switch(c, "customer")
    assert (
        c.get("/api/parts-requests").json()[0]["notes"]
        == "Checking the exact gun variant."
    )


def test_vehicle_state_machine_and_persistent_report(demo):
    c = demo
    assets = c.get("/api/portal/assets").json()
    v = next(a for a in assets if a["ownership"]["kind"] == "vehicle")
    first = c.post("/api/visits", json={"asset_id": v["id"]}).json()
    assert c.post("/api/visits", json={"asset_id": v["id"]}).json()["id"] == first["id"]
    path = "/api/visits/" + first["id"]
    assert c.patch(path, json={"version": 1, "status": "Completed"}).status_code == 422
    report = {
        "findings": "Synthetic corrosion example at rear crossmember.",
        "treatment": "Simulated coating applied.",
        "verification": "Simulated before/after comparison recorded.",
    }
    for version, status in enumerate(
        [
            "Bay preparation",
            "Ready for inspection",
            "Inspecting",
            "Findings review",
            "Treatment recorded",
            "Verification",
            "Completed",
        ],
        1,
    ):
        r = c.patch(path, json={**report, "version": version, "status": status})
        assert r.status_code == 200, r.text
    assert (
        c.patch(path, json={**report, "version": 7, "status": "Completed"}).status_code
        == 409
    )
    switch(c, "customer")
    detail = c.get("/api/portal/assets/" + v["id"]).json()
    event = next(
        e for e in detail["events"] if e["body"].get("visit_id") == first["id"]
    )
    assert event["body"]["simulated"] is True
    assert event["body"]["before"] and event["body"]["after"]
    assert c.post("/api/visits", json={"asset_id": v["id"]}).status_code == 403


def test_maintenance_basis_and_cache_invalidation(demo):
    c = demo
    a = c.get("/api/assets").json()[0]
    d = c.get("/api/portal/assets/" + a["id"]).json()
    assert d["maintenance"][0]["interval_days"] == 120
    assert "Synthetic" in d["maintenance"][0]["basis"]
    with Session() as db:
        asset = db.get(Asset, a["id"])
        key = cache_key(db, asset.workspace_id, asset, "same symptoms")
        db.add(
            GuidanceCache(
                id=key, result={"verdict": "supported", "recommendation": {"parts": []}}
            )
        )
        db.commit()
        assert (
            cached_result(db, asset.workspace_id, asset, " same   symptoms ")[
                "cache_hit"
            ]
            is True
        )
        assert (
            cached_result(db, asset.workspace_id, asset, "different symptoms") is None
        )
        db.add(
            Event(
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                kind="service",
                title="Changed history",
                actor="Test technician",
                body={"outcome": "Unresolved"},
            )
        )
        db.commit()
        assert cached_result(db, asset.workspace_id, asset, "same symptoms") is None


def test_cache_works_without_api_key(demo, monkeypatch):
    import asyncio

    c = demo
    a = c.get("/api/assets").json()[0]
    r = c.post(
        "/api/requests",
        json={
            "asset_id": a["id"],
            "title": "Repeat symptom",
            "description": "Matching repeat symptoms",
            "category": "Test",
            "name": "Demo customer",
            "email": "test@example.test",
        },
    ).json()
    with Session() as db:
        asset = db.get(Asset, a["id"])
        key = cache_key(db, asset.workspace_id, asset, r["description"])
        db.add(
            GuidanceCache(
                id=key,
                result={
                    "verdict": "supported",
                    "recommendation": {"summary": "Previously reviewed", "parts": []},
                },
            )
        )
        db.commit()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert asyncio.run(process_one(r["id"])) is True
    status = c.get("/api/requests/" + r["id"] + "/guidance").json()
    assert status["guidance"]["status"] == "ready"
    with Session() as db:
        from sqlalchemy import select

        run = db.scalar(select(AIRun).where(AIRun.request_id == r["id"]))
        assert run.result["cache_hit"] is True


def test_inspection_image_access_and_owner_guidance_sources(demo):
    import io
    from PIL import Image
    from server.ai import Recommendation, deterministic_checks

    c = demo
    vehicle = next(
        a
        for a in c.get("/api/portal/assets").json()
        if a["ownership"]["kind"] == "vehicle"
    )
    visit = c.post("/api/visits", json={"asset_id": vehicle["id"]}).json()
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "gray").save(buf, "PNG")
    upload = c.post(
        "/api/visits/" + visit["id"] + "/media/before",
        files={"file": ("test.png", buf.getvalue(), "image/png")},
    )
    assert upload.status_code == 200, upload.text
    url = upload.json()["report"]["before"]
    assert c.get(url).content == buf.getvalue()
    switch(c, "second_customer")
    assert c.get(url).status_code == 404
    switch(c, "customer")
    assert c.get(url).status_code == 200
    assert (
        c.post(
            "/api/visits/" + visit["id"] + "/media/after",
            files={"file": ("test.png", buf.getvalue(), "image/png")},
        ).status_code
        == 403
    )
    rec = Recommendation(
        summary="Owner guidance",
        owner_guidance=[{"text": "A private claim", "source_ids": ["private"]}],
        disposition="supported",
    )
    issues = deterministic_checks(
        rec, [{"id": "private", "owner_visible": False}], "L015-201"
    )
    assert any("owner-visible" in x for x in issues)


def test_existing_signup_can_accept_reception_invitation(demo):
    c = demo
    switch(c, "reception")
    email = "link-" + uuid.uuid4().hex + "@example.test"
    credentials = {
        "name": "Existing signup",
        "email": email,
        "password": "Test-only-long-password",
    }
    with TestClient(app) as owner:
        assert owner.post("/api/auth/signup", json=credentials).status_code == 200
        customer = c.post(
            "/api/customers", json={"name": "Existing signup", "email": email}
        ).json()
        asset = c.post(
            "/api/registry",
            json={
                "customer_id": customer["id"],
                "customer_confirmed": True,
                "name": "Customer pump",
                "model": "External",
                "manufacturer": "Other",
                "serial": "12345",
            },
        ).json()
        invite = c.post("/api/customers/" + customer["id"] + "/invite").json()["token"]
        assert (
            owner.post(
                "/api/auth/signup",
                json={
                    **credentials,
                    "invite": invite,
                    "password": "Wrong-password-123",
                },
            ).status_code
            == 401
        )
        assert (
            owner.post(
                "/api/auth/signup", json={**credentials, "invite": invite}
            ).status_code
            == 200
        )
        assert owner.get("/api/portal/assets").json()[0]["id"] == asset["id"]
        assert (
            owner.post("/api/accounts/switch", json={"name": "Alex Morgan"}).status_code
            == 403
        )


def test_repair_installation_updates_estimate_and_keeps_identity(demo):
    from datetime import date

    c = demo
    a = c.get("/api/assets").json()[0]
    r = c.post(
        "/api/requests",
        json={
            "asset_id": a["id"],
            "title": "Packing follow-up",
            "description": "Fluid seeps around the needle packing after use.",
            "category": "Leak",
            "name": "Demo owner",
            "email": "demo@example.test",
        },
    ).json()
    body = {
        "diagnosis": "Worn packing confirmed",
        "work": "Technician replaced the worn packing",
        "parts": ["L015-291"],
        "parts_replaced": True,
        "test": "Leak check passed",
        "outcome": "Repaired",
        "inspection_date": date.today().isoformat(),
        "submission_id": "replacement-ledger-test",
        "version": 1,
    }
    first = c.post("/api/requests/" + r["id"] + "/reports", json=body)
    assert first.status_code == 200, first.text
    assert c.post("/api/requests/" + r["id"] + "/reports", json=body).status_code == 200
    outlook = c.get("/api/portal/assets/" + a["id"]).json()["maintenance"]
    assert len(outlook) == 1
    assert outlook[0]["installed"] == date.today().isoformat()
    assert outlook[0]["interval_days"] == 90
    assert "Observed" in outlook[0]["basis"]
