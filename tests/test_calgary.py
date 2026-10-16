"""Calgary acceptance: staff authorization, approval boundaries, persistence and costs."""

import os, uuid, asyncio

os.environ["AUTO_GUIDANCE_WORKER"] = "0"
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from server.main import app
from server.database import Session, Asset, ServiceRequest, Event, AIRun
from server.operations_models import Procedure, AuditEntry, AIUsage
from server.ai import corpus
from server.access import DEMO_ADMIN


@pytest.fixture
def c():
    with TestClient(app) as c:
        assert c.post("/api/demo/start").status_code == 200
        yield c


def switch(c, name):
    r = c.post("/api/accounts/switch", json={"name": name})
    assert r.status_code == 200, r.text


def asset(c):
    return c.get("/api/assets").json()[0]


def new(c, a=None):
    a = a or asset(c)
    r = c.post(
        "/api/requests",
        json={
            "asset_id": a["id"],
            "title": "Packing area observation",
            "description": "Fluid seeps around the needle packing after use.",
            "category": "Inspection",
            "name": "Demo client",
            "email": "",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def proposal(a):
    return {
        "title": "Synthetic packing observation checklist",
        "manufacturer": a["manufacturer"],
        "model": a["model"],
        "product_number": a["product_number"],
        "symptoms": ["Fluid seeps around the needle packing after use."],
        "steps": [
            {
                "question": "Is the exact source of visible seepage recorded without operating the equipment?",
                "yes": 1,
                "no": -1,
                "unknown": -1,
            },
            {
                "question": "Has a technician recorded the actual diagnosis separately?",
                "yes": -1,
                "no": -1,
                "unknown": -1,
            },
        ],
        "solution": "Synthetic workflow only. Record an actual diagnosis and verify before a replacement decision.",
        "references": [
            {
                "title": "Synthetic training fixture",
                "passage": "This checklist is a workflow demonstration; no replacement is authorized.",
                "page": "Unknown",
                "revision": "Demo 1",
            }
        ],
        "synthetic": True,
    }


def approve(c, p):
    switch(c, DEMO_ADMIN)
    r = c.post(
        "/api/procedures/" + p["id"] + "/review",
        json={
            "status": "Approved",
            "reason": "Checked synthetic workflow, equipment and absence of private data.",
            "technical_checked": True,
            "privacy_checked": True,
        },
    )
    assert r.status_code == 200, r.text


def test_calgary_superuser_and_named_staff_revocation(c):
    assert c.get("/api/operations").status_code == 403
    switch(c, DEMO_ADMIN)
    assert c.get("/api/session").json()["role"] == "superuser"
    ops = c.get("/api/operations").json()
    assert ops["location"] == "Calgary"
    credentials = {
        "email": uuid.uuid4().hex + "@example.test",
        "password": "Private-test-password-123",
    }
    user = c.post(
        "/api/operations/staff",
        json={
            **credentials,
            "name": "Named " + uuid.uuid4().hex[:8],
            "role": "reception",
        },
    ).json()
    with TestClient(app) as named:
        assert named.post("/api/auth/login", json=credentials).status_code == 200
        assert named.get("/api/session").json()["role"] == "reception"
        assert named.get("/api/session").json()["demo"] is False
        assert named.get("/api/operations").status_code == 403
        assert (
            named.post("/api/accounts/switch", json={"name": DEMO_ADMIN}).status_code
            == 403
        )
        assert (
            named.post("/api/session/technician", json={"name": DEMO_ADMIN}).status_code
            == 403
        )
        assert named.get("/api/knowledge").status_code == 403
        assert (
            c.patch(
                "/api/operations/staff/" + user["id"],
                json={
                    "role": "reception",
                    "active": False,
                    "reason": "Disable account for access test.",
                },
            ).status_code
            == 200
        )
        assert named.get("/api/session").status_code == 401
    # Customer accounts cannot access super-user operations.
    external = next(
        x["name"]
        for x in c.get("/api/session").json()["accounts"]
        if x.get("label") == "Prairie Fleet Services"
    )
    switch(c, external)
    assert c.get("/api/operations").status_code == 403


def test_procedure_human_review_exact_match_and_no_calls(c, monkeypatch):
    a = asset(c)
    r = new(c, a)
    path = "/api/requests/" + r["id"]
    p = c.post("/api/procedures", json=proposal(a)).json()
    assert p["status"] == "Pending review"
    assert c.get(path + "/procedures").json()["procedures"] == []
    assert (
        c.post(
            "/api/procedures/" + p["id"] + "/review",
            json={"status": "Approved", "reason": "Not authorized reviewer"},
        ).status_code
        == 403
    )
    switch(c, DEMO_ADMIN)
    assert (
        c.post(
            "/api/procedures/" + p["id"] + "/review",
            json={"status": "Approved", "reason": "Missing review confirmations"},
        ).status_code
        == 422
    )
    approve(c, p)
    switch(c, "Alex Morgan")
    offered = c.get(path + "/procedures").json()["procedures"]
    assert offered[0]["exact_symptom"] is True
    from server import guidance

    async def forbidden(*a, **kw):
        raise AssertionError("Approved exact symptom should not invoke AI")

    monkeypatch.setattr(guidance, "recommend", forbidden)
    asyncio.run(guidance.process_one(r["id"]))
    assert c.get(path + "/guidance").json()["guidance"]["status"] == "procedure"
    run = c.post(path + "/procedures/" + p["id"] + "/start").json()
    first = c.post(
        "/api/procedure-runs/" + run["id"] + "/answer",
        json={
            "version": 1,
            "answer": "yes",
            "observation": "Visible source documented, equipment remained off.",
        },
    )
    assert first.status_code == 200 and first.json()["current_step"] == 1
    assert (
        c.post(
            "/api/procedure-runs/" + run["id"] + "/answer",
            json={"version": 1, "answer": "yes", "observation": "Duplicate answer"},
        ).status_code
        == 409
    )
    last = c.post(
        "/api/procedure-runs/" + run["id"] + "/answer",
        json={
            "version": 2,
            "answer": "unknown",
            "observation": "Diagnosis not yet confirmed.",
        },
    ).json()
    assert last["status"] == "Completed" and len(last["answers"]) == 2
    assert c.get(path).json()["request"]["status"] != "Closed"
    with Session() as db:
        ar = db.get(Asset, a["id"])
        assert any(
            x["kind"] == "procedure" for x in corpus(db, ar.workspace_id, ar, "B")
        )


def test_approval_versions_retirement_and_wrong_equipment(c):
    a = asset(c)
    r = new(c, a)
    p = c.post("/api/procedures", json=proposal(a)).json()
    approve(c, p)
    other = c.get("/api/assets").json()[1]
    other_r = new(c, other)
    assert (
        c.post(
            "/api/requests/" + other_r["id"] + "/procedures/" + p["id"] + "/start"
        ).status_code
        == 422
    )
    run = c.post(
        "/api/requests/" + r["id"] + "/procedures/" + p["id"] + "/start"
    ).json()
    p2 = c.post("/api/procedures", json={**proposal(a), "previous_id": p["id"]}).json()
    assert p2["version"] == 2
    approve(c, p2)
    assert (
        c.post(
            "/api/procedure-runs/" + run["id"] + "/answer",
            json={
                "version": 1,
                "answer": "yes",
                "observation": "Outdated version test",
            },
        ).status_code
        == 409
    )
    assert (
        len(c.get("/api/requests/" + r["id"] + "/procedures").json()["procedures"]) == 1
    )


def test_intake_open_warning_unassigned_receipt_and_photos(c, monkeypatch):
    a = asset(c)
    switch(c, "Taylor Brooks")
    monkeypatch.setenv("AI_DAILY_LIMIT", "0")
    b = {
        "asset_id": a["id"],
        "title": "New service visit",
        "description": "Customer describes visible seepage.",
        "category": "General",
        "name": "Delivery person",
        "email": "",
        "technician": "Unassigned",
        "reviewed": True,
        "submission_id": str(uuid.uuid4()),
        "accessories": "Gun and cup",
        "visible_damage": "Not assessed",
        "dropoff_role": "Employee of owner",
        "customer_instructions": "Call before replacing parts.",
    }
    assert c.post("/api/intake/handoff", json=b).status_code == 409
    from pathlib import Path

    upload = c.post(
        "/api/intake/documents?purpose=photo",
        files={
            "file": (
                "intake.png",
                Path("public/images/demo-service-paper.png").read_bytes(),
                "image/png",
            )
        },
    )
    assert upload.status_code == 200
    b.update(acknowledge_open=True, photo_ids=[upload.json()["id"]])
    result = c.post("/api/intake/handoff", json=b)
    assert result.status_code == 200, result.text
    r = result.json()
    assert (
        r["technician"] == "Unassigned" and r["operating"] == "Unknown / Not assessed"
    )
    assert c.post("/api/intake/handoff", json=b).json()["id"] == r["id"]
    receipt = c.get("/api/requests/" + r["id"] + "/receipt").json()
    assert (
        receipt["asset"]["model"] == "RP-460HD"
        and receipt["asset"]["product_number"] == "L015-201"
    )
    assert len(receipt["documents"]) == 1
    assert c.get("/api/requests/" + r["id"] + "/guidance").status_code == 403
    assert (
        c.patch(
            "/api/requests/" + r["id"],
            json={"version": 1, "draft": {"diagnosis": "Pretend repair"}},
        ).status_code
        == 403
    )


def test_sap_customer_lookup_wallet_confirmation_and_separate_ids(c):
    switch(c, "Taylor Brooks")
    customer = c.post(
        "/api/customers", json={"name": "SAP demo client", "sap_customer_code": "C-123"}
    ).json()
    b = {
        "customer_id": customer["id"],
        "name": "Workshop rustproof gun",
        "model": "RP-460HD",
        "product_sku": "L015-201",
        "serial": "ONE",
        "sap_document_type": "Invoice",
        "sap_document_number": "INV-123",
        "sap_line_number": "1",
    }
    assert c.post("/api/registry", json=b).status_code == 422
    first = c.post("/api/registry", json={**b, "customer_confirmed": True}).json()
    second = c.post(
        "/api/registry", json={**b, "serial": "TWO", "customer_confirmed": True}
    ).json()
    assert first["code"] != second["code"] and first["id"] != second["id"]
    found = next(x for x in c.get("/api/customers").json() if x["id"] == customer["id"])
    assert (
        found["asset_count"] == 2
        and first["code"] in found["asset_codes"]
        and found["sap_customer_code"] == "C-123"
    )
    assert (
        c.post(
            "/api/customers",
            json={"name": "Duplicate SAP client", "sap_customer_code": "C-123"},
        ).status_code
        == 409
    )
    assert (
        c.get("/api/portal/assets/" + first["id"]).json()["ownership"]["profile"][
            "sap_sale"
        ]["document_number"]
        == "INV-123"
    )


def test_reports_quantities_open_default_and_amendment_audit(c):
    a = asset(c)
    r = new(c, a)
    path = "/api/requests/" + r["id"]
    b = {
        "diagnosis": "Packing wear confirmed",
        "work": "Documented actual replacement",
        "part_lines": [{"part": "L015-291", "quantity": 2, "action": "Replaced"}],
        "test": "Observed leak test completed",
        "outcome": "Repaired",
        "inspection_date": date.today().isoformat(),
        "submission_id": str(uuid.uuid4()),
        "version": r["version"],
    }
    bad = {
        **b,
        "part_lines": [{"part": "L015-291", "quantity": 0, "action": "Replaced"}],
    }
    assert c.post(path + "/reports", json=bad).status_code == 422
    res = c.post(path + "/reports", json=b)
    assert res.status_code == 200, res.text
    event = res.json()["event"]
    assert (
        event["body"]["part_lines"][0]["quantity"] == 2
        and res.json()["request"]["status"] == "In progress"
    )
    switch(c, DEMO_ADMIN)
    correction = {
        "kind": "report",
        "changes": {"diagnosis": "Packing damage, corrected finding"},
        "expected": {"diagnosis": "Packing wear confirmed"},
        "reason": "Technician corrected the recorded diagnosis.",
    }
    assert (
        c.post(
            "/api/operations/corrections/" + event["id"], json=correction
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/operations/corrections/" + event["id"], json=correction
        ).status_code
        == 409
    )
    e = next(
        e
        for e in c.get("/api/assets/" + a["id"]).json()["events"]
        if e["id"] == event["id"]
    )
    assert e["body"]["diagnosis"] == "Packing damage, corrected finding"
    with Session() as db:
        assert db.get(Event, event["id"]).body["diagnosis"] == "Packing wear confirmed"
        log = db.scalar(
            select(AuditEntry).where(
                AuditEntry.object_id == event["id"],
                AuditEntry.action == "Correct report",
            )
        )
        with pytest.raises(Exception):
            db.execute(text("DELETE FROM audit_entries WHERE id=:id"), {"id": log.id})
        db.rollback()


def test_pending_cases_do_not_leak_to_other_assets(c):
    a = asset(c)
    b = c.get("/api/assets").json()[1]
    with Session() as db:
        aa = db.get(Asset, a["id"])
        bb = db.get(Asset, b["id"])
        other = corpus(db, aa.workspace_id, bb, "C")
        assert all(x.get("asset_id") != aa.id for x in other)
        assert not any(x["kind"] == "case" for x in other)


def test_usage_reservation_limits_errors_and_cache(c, monkeypatch):
    from server.usage import reserve, finish, workspace_context, cache_hit

    a = asset(c)
    with Session() as db:
        wid = db.get(Asset, a["id"]).workspace_id
    workspace_context.set(wid)
    monkeypatch.setenv("AI_WORKSPACE_DAILY_LIMIT", "1")
    monkeypatch.setenv("AI_PROVIDER_DAILY_LIMIT", "100000")
    monkeypatch.setenv("AI_TOKEN_DAILY_LIMIT", "100000000")
    key = reserve("judge", "fake", 1000)
    finish(key, "error", 0.2)
    cache_hit()
    with pytest.raises(RuntimeError, match="Daily model request limit"):
        reserve("generation", "fake", 1000)
    switch(c, DEMO_ADMIN)
    rows = c.get("/api/operations/usage").json()["records"]
    assert {r["status"] for r in rows} == {"error", "cache_hit"}


def test_customer_document_release_and_cross_customer_isolation(c, monkeypatch):
    from pathlib import Path

    a = asset(c)
    switch(c, "Taylor Brooks")
    monkeypatch.setenv("AI_DAILY_LIMIT", "0")
    scan = c.post(
        "/api/intake/documents?purpose=photo",
        files={
            "file": (
                "paper.png",
                Path("public/images/demo-service-paper.png").read_bytes(),
                "image/png",
            )
        },
    ).json()
    b = {
        "asset_id": a["id"],
        "title": "Documentation example",
        "description": "Record visible symptom for workshop assessment.",
        "category": "General",
        "name": "Demo owner",
        "email": "",
        "technician": "Unassigned",
        "reviewed": True,
        "acknowledge_open": True,
        "submission_id": str(uuid.uuid4()),
        "document_id": scan["id"],
    }
    r = c.post("/api/intake/handoff", json=b).json()
    accounts = c.get("/api/session").json()["accounts"]
    owner = next(x["name"] for x in accounts if x["role"] == "customer")
    other = next(
        x["name"] for x in accounts if x.get("label") == "Prairie Fleet Services"
    )
    switch(c, owner)
    assert c.get("/api/owner-documents/" + scan["id"]).status_code == 404
    assert c.get(scan["url"]).status_code == 403
    switch(c, "Taylor Brooks")
    assert (
        c.post(
            "/api/intake/documents/" + scan["id"] + "/share",
            json={"reviewed_for_customer": False},
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/intake/documents/" + scan["id"] + "/share",
            json={"reviewed_for_customer": True},
        ).status_code
        == 200
    )
    switch(c, owner)
    assert c.get("/api/owner-documents/" + scan["id"]).status_code == 200
    assert (
        c.get("/api/portal/assets/" + a["id"]).json()["released_documents"][0]["id"]
        == scan["id"]
    )
    switch(c, other)
    assert c.get("/api/owner-documents/" + scan["id"]).status_code == 404


def test_approval_and_corrections_cannot_cross_workspace(c):
    a = asset(c)
    p = c.post("/api/procedures", json=proposal(a)).json()
    with TestClient(app) as other:
        other.post("/api/demo/start")
        switch(other, DEMO_ADMIN)
        assert (
            other.post(
                "/api/procedures/" + p["id"] + "/review",
                json={
                    "status": "Approved",
                    "reason": "Attempt across company boundary",
                    "technical_checked": True,
                    "privacy_checked": True,
                },
            ).status_code
            == 404
        )
        assert (
            other.post(
                "/api/operations/corrections/" + a["id"],
                json={
                    "kind": "asset",
                    "changes": {"serial": "Changed"},
                    "expected": {"serial": a["serial"]},
                    "reason": "Attempt across company boundary",
                },
            ).status_code
            == 404
        )


def test_pdf_page_limit_and_empty_unknown_extraction(c, monkeypatch):
    import io
    from pypdf import PdfWriter

    switch(c, "Taylor Brooks")
    monkeypatch.setenv("AI_DAILY_LIMIT", "0")
    for pages in [5, 6]:
        pdf = PdfWriter()
        for _ in range(pages):
            pdf.add_blank_page(width=612, height=792)
        buff = io.BytesIO()
        pdf.write(buff)
        result = c.post(
            "/api/intake/documents",
            files={"file": ("blank.pdf", buff.getvalue(), "application/pdf")},
        )
        assert result.status_code == (200 if pages == 5 else 422)
        if pages == 5:
            assert (
                result.json()["extracted"] == {} and "extraction_error" in result.json()
            )


def test_concurrent_reads_and_ai_reservation_limits(c, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from server.usage import workspace_context, reserve, finish

    with Session() as db:
        wid = db.get(Asset, asset(c)["id"]).workspace_id
    cookie = c.cookies.get("lemmer_session")

    def read(_):
        with TestClient(app) as reader:
            reader.cookies.set("lemmer_session", cookie)
            return reader.get("/api/dashboard").status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        assert list(pool.map(read, range(10))) == [200] * 10
    monkeypatch.setenv("AI_CONCURRENCY", "1")
    monkeypatch.setenv("AI_PROVIDER_DAILY_LIMIT", "100000")
    monkeypatch.setenv("AI_TOKEN_DAILY_LIMIT", "100000000")
    monkeypatch.setenv("AI_WORKSPACE_DAILY_LIMIT", "100000")

    def attempt(_):
        workspace_context.set(wid)
        try:
            return reserve("generation", "test-no-network", 100)
        except RuntimeError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(x is not None for x in results) == 1
    for key in results:
        if key:
            finish(key, "cancelled_test", 0)


def test_parts_listing_cannot_become_diagnostic_evidence_even_if_judge_passes():
    from server.ai import Recommendation, deterministic_checks

    rec = Recommendation.model_validate(
        {
            "summary": "Possible loose packing nut",
            "disposition": "supported",
            "causes": [
                {
                    "title": "Loose nut",
                    "reason": "Compression may be low",
                    "source_ids": ["DOC-PARTS"],
                }
            ],
            "part_candidates": [
                {
                    "part": "L015-292",
                    "reason": "Nut might be faulty",
                    "confirm_with": "Inspect the nut",
                    "source_ids": ["DOC-PARTS"],
                }
            ],
        }
    )
    evidence = [
        {"id": "DOC-PARTS", "kind": "manual", "content": "| L015-292 | Packing nut |"}
    ]
    problems = deterministic_checks(rec, evidence, "L015-201")
    assert any("listing" in p for p in problems)
    assert any("no" in p.lower() or "insufficient" in p.lower() for p in problems)


def test_old_policy_cannot_release_previous_unsafe_suggestions():
    from server.ai import visible_result

    result = visible_result(
        {
            "policy_version": "4.1",
            "verdict": "supported",
            "recommendation": {
                "summary": "Replace a part",
                "causes": [{"title": "Old guess"}],
            },
            "part_candidates": [{"part": "Old part"}],
        }
    )
    assert (
        result["verdict"] == "unsupported"
        and not result["part_candidates"]
        and not result["recommendation"]["causes"]
    )
