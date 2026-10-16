"""Real PostgreSQL workflow checks; each test gets a separate synthetic workspace."""

import os

os.environ["AUTO_GUIDANCE_WORKER"] = "0"
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from server.main import app
from server.database import Session, Asset
from server.ai import corpus, deterministic_checks, Recommendation


@pytest.fixture
def client():
    with TestClient(app) as c:
        assert c.post("/api/demo/start").status_code == 200
        yield c


def request_body(asset):
    return dict(
        asset_id=asset["id"],
        title="Demo prime issue",
        description="Pump runs but does not prime after storage.",
        category="Pressure / priming",
        name="Demo technician",
        email="demo@example.test",
        operating="No",
        acknowledge_open=True,
    )


def report_body(version=1):
    return dict(
        close_request=True,
        notes="Testing repair closure or further assessment where unresolved.",
        diagnosis="Worn packing confirmed",
        work="Replaced confirmed worn packing",
        parts=["L015-291"],
        test="Technician verified operation and no leakage",
        outcome="Repaired",
        inspection_date=date.today().isoformat(),
        version=version,
        submission_id="workflow-test-submission",
    )


def test_authentication_and_origin():
    with TestClient(app) as c:
        assert c.get("/api/assets").status_code == 401
        assert (
            c.post(
                "/api/demo/start", headers={"Origin": "https://unrelated.example"}
            ).status_code
            == 403
        )


def test_two_assets_and_workspace_isolation(client):
    a, b = client.get("/api/assets").json()[:2]
    share = client.get("/api/session").json()["share"]
    for item in [a, b]:
        public = client.get(f"/api/public/{share}/{item['code']}").json()
        assert public["asset"]["id"] == item["id"]
        assert "customer" not in public["asset"]
        assert all("contact" not in r for r in public["requests"])
    assert (
        client.post(
            f"/api/public/{share}/{a['code']}/requests", json=request_body(b)
        ).status_code
        == 422
    )
    with TestClient(app) as other:
        other.post("/api/demo/start")
        assert other.get("/api/assets/" + a["id"]).status_code == 404
        assert other.post("/api/requests", json=request_body(a)).status_code == 404


def test_closed_loop_and_idempotency(client):
    a, b = client.get("/api/assets").json()[:2]
    before_b = client.get("/api/assets/" + b["id"]).json()["events"]
    r = client.post("/api/requests", json=request_body(a)).json()
    path = "/api/requests/" + r["id"]
    bad = report_body()
    bad["parts"] = ["L000-000"]
    assert client.post(path + "/reports", json=bad).status_code == 422
    bad = report_body()
    bad["inspection_date"] = "2099-01-01"
    assert client.post(path + "/reports", json=bad).status_code == 422
    first = client.post(path + "/reports", json=report_body())
    assert first.status_code == 200, first.text
    second = client.post(path + "/reports", json=report_body())
    assert second.status_code == 200
    assert first.json()["event"]["id"] == second.json()["event"]["id"]
    assert first.json()["event"]["asset_id"] == a["id"]
    assert client.get(path).json()["request"]["status"] == "Closed"
    assert client.get("/api/assets/" + b["id"]).json()["events"] == before_b
    cases = client.get("/api/knowledge").json()["cases"]
    case = next(c for c in cases if c.get("event_id") == first.json()["event"]["id"])
    assert case["asset_id"] == a["id"]
    with Session() as db:
        asset = db.get(Asset, a["id"])
        assert any(
            e["id"] == "HIST-" + first.json()["event"]["id"][:8] for e in corpus(db, asset.workspace_id, asset, "C")
        )
        assert all(
            e["id"] != case["code"] for e in corpus(db, asset.workspace_id, asset, "B")
        )
        assert all(
            e["kind"] in ["manual", "catalogue"] for e in corpus(db, asset.workspace_id, asset, "A")
        )
    assert len(client.get("/api/notifications").json()) >= 2


def test_optimistic_lock_and_outcome(client):
    a = client.get("/api/assets").json()[0]
    r = client.post("/api/requests", json=request_body(a)).json()
    path = "/api/requests/" + r["id"]
    save = client.patch(
        path, json={"draft": {"diagnosis": "Investigation in progress"}, "version": 1}
    )
    assert save.status_code == 200
    assert (
        client.patch(path, json={"status": "In progress", "version": 1}).status_code
        == 409
    )
    assert (
        client.patch(path, json={"status": "Closed", "version": 2}).status_code == 422
    )
    body = report_body(2)
    body["outcome"] = "Unresolved"
    body["parts"] = []
    assert client.post(path + "/reports", json=body).status_code == 200
    assert (
        client.get("/api/assets/" + a["id"]).json()["asset"]["condition"]
        == "Needs service"
    )


def test_import_and_technician_validation(client):
    assert (
        client.post("/api/session/technician", json={"name": "Unknown"}).status_code
        == 403
    )
    assert (
        client.post("/api/session/technician", json={"name": "Sam Chen"}).status_code
        == 200
    )
    assert client.post("/api/knowledge/import",json={"cases":[]}).status_code in [403,422]
    client.post("/api/accounts/switch",json={"name":"Demo super-user"})
    case = dict(
        model="L-65",
        symptom="Air leaks around the gun trigger",
        diagnosis="Air valve issue",
        repair="Inspection recorded",
        parts=["L004-517"],
        test="Observed air leak",
        outcome="Unresolved",
    )
    assert (
        client.post("/api/knowledge/import", json={"cases": [case]}).status_code == 422
    )
    case["parts"] = []
    assert (
        client.post("/api/knowledge/import", json={"cases": [case]}).status_code == 200
    )


def test_unknown_parts_and_fabricated_citations():
    rec = Recommendation.model_validate(
        dict(
            summary="Investigate",
            causes=[
                {
                    "title": "Part issue",
                    "reason": "Inspect L000-000",
                    "source_ids": ["invented"],
                }
            ],
            checks=[],
            parts=["L000-000"],
            questions=[],
            disposition="supported",
        )
    )
    issues = deterministic_checks(rec, [{"id": "known"}], "L-1095")
    assert any("source reference" in x for x in issues)
    assert any("part" in x.lower() for x in issues)


def test_production_frontend_routes_do_not_shadow_assets(client):
    for path in [
        "/assets",
        "/assets/example-id",
        "/requests/example-id",
        "/passport/example/example",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    html = client.get("/").text
    import re

    script = re.search(r'src="(/static/[^\"]+\.js)"', html).group(1)
    assert client.get(script).status_code == 200


def test_global_ai_budget_limit(client, monkeypatch):
    monkeypatch.setenv("AI_DAILY_LIMIT", "0")
    r = client.get("/api/dashboard").json()["requests"][0]
    response = client.post(
        "/api/requests/" + r["id"] + "/recommend",
        json={"problem": "The pump will not prime after storage.", "mode": "C"},
    )
    assert response.status_code == 429
    assert "No paid fallback" in response.json()["detail"]


def test_uncertain_judge_cannot_release_speculative_causes(client, monkeypatch):
    import asyncio
    import server.ai as ai
    from server.database import Session, Asset

    a = client.get("/api/assets").json()[0]

    async def fake_retrieve(db, query, items):
        return items, "Test evidence"

    async def fake_model(model, system, prompt, schema):
        if schema is ai.Recommendation:
            return schema.model_validate(
                dict(
                    summary="Speculative explanation",
                    causes=[
                        {
                            "title": "Invented controller",
                            "reason": "No direct evidence",
                            "source_ids": ["CAT-L015-201"],
                        }
                    ],
                    checks=[],
                    parts=[],
                    questions=["Confirm what equipment is displaying the error."],
                    disposition="needs_information",
                )
            )
        return schema.model_validate(
            dict(
                verdict="needs_information",
                reason="Unknown symptom",
                checks=[
                    {
                        "criterion": "Evidence",
                        "status": "unknown",
                        "reason": "No matching history",
                    }
                ],
            )
        )

    monkeypatch.setattr(ai, "retrieve", fake_retrieve)
    monkeypatch.setattr(ai, "model_json", fake_model)
    with Session() as db:
        asset = db.get(Asset, a["id"])
        result = asyncio.run(
            ai.recommend(db, asset.workspace_id, asset, "Unrecognized display symptom")
        )
    assert result["verdict"] == "unsupported"
    assert not result["recommendation"]["causes"]
    assert not result["recommendation"]["checks"]
    assert not result["recommendation"]["parts"]
    assert result["recommendation"]["questions"]


def test_reception_handoff_original_and_roles(client, monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("AI_DAILY_LIMIT", "0")
    scan = Path("public/images/demo-service-paper.png").read_bytes()
    assert (
        client.post(
            "/api/intake/documents", files={"file": ("paper.png", scan, "image/png")}
        ).status_code
        == 403
    )
    switch = client.post("/api/session/technician", json={"name": "Taylor Brooks"})
    assert switch.status_code == 200 and switch.json()["role"] == "reception"
    upload = client.post(
        "/api/intake/documents", files={"file": ("paper.png", scan, "image/png")}
    )
    assert upload.status_code == 200, upload.text
    doc = upload.json()
    assert "extraction_error" in doc
    a = client.get("/api/assets").json()[0]
    body = {
        **request_body(a),
        "technician": "Sam Chen",
        "document_id": doc["id"],
        "reviewed": False,
        "submission_id": "reception-workflow-test",
        "intake_notes": "Hose received with pump.",
    }
    assert client.post("/api/intake/handoff", json=body).status_code == 422
    body["reviewed"] = True
    sent = client.post("/api/intake/handoff", json=body)
    assert sent.status_code == 200, sent.text
    r = sent.json()
    assert r["technician"] == "Sam Chen" and r["documents"][0]["id"] == doc["id"]
    assert client.post("/api/intake/handoff", json=body).json()["id"] == r["id"]
    assert (
        client.post(
            "/api/requests/" + r["id"] + "/reports", json=report_body()
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/requests/" + r["id"] + "/recommend",
            json={"problem": "The pump will not prime."},
        ).status_code
        == 403
    )
    client.post("/api/session/technician", json={"name": "Sam Chen"})
    detail = client.get("/api/requests/" + r["id"]).json()
    assert detail["request"]["documents"][0]["filename"] == "paper.png"
    assert any(
        e["kind"] == "intake" and e["body"]["notes"] == "Hose received with pump."
        for e in detail["events"]
    )
    original = client.get(doc["url"])
    assert original.status_code == 200 and original.content == scan
    assert (
        client.post(
            "/api/requests/" + r["id"] + "/reports", json=report_body()
        ).status_code
        == 200
    )
    with TestClient(app) as other:
        assert other.get(doc["url"]).status_code == 401
        other.post("/api/demo/start")
        assert other.get(doc["url"]).status_code == 404


def test_intake_rejects_invalid_file_and_cross_workspace_document(client, monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("AI_DAILY_LIMIT", "0")
    client.post("/api/session/technician", json={"name": "Taylor Brooks"})
    assert (
        client.post(
            "/api/intake/documents",
            files={"file": ("fake.png", b"not an image", "image/png")},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/intake/documents",
            files={"file": ("huge.png", b"x" * 2_500_001, "image/png")},
        ).status_code
        == 413
    )
    upload = client.post(
        "/api/intake/documents",
        files={
            "file": (
                "paper.png",
                Path("public/images/demo-service-paper.png").read_bytes(),
                "image/png",
            )
        },
    ).json()
    with TestClient(app) as other:
        other.post("/api/demo/start")
        other.post("/api/session/technician", json={"name": "Taylor Brooks"})
        a = other.get("/api/assets").json()[0]
        body = {
            **request_body(a),
            "technician": "Alex Morgan",
            "document_id": upload["id"],
            "reviewed": True,
            "submission_id": "wrong-workspace-doc",
        }
        assert other.post("/api/intake/handoff", json=body).status_code == 404


def test_pdf_intake_page_limit_and_original(client, monkeypatch):
    import io
    from pypdf import PdfWriter

    monkeypatch.setenv("AI_DAILY_LIMIT", "0")
    client.post("/api/session/technician", json={"name": "Taylor Brooks"})
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    buf = io.BytesIO()
    writer.write(buf)
    response = client.post(
        "/api/intake/documents",
        files={"file": ("paper.pdf", buf.getvalue(), "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["content_type"] == "application/pdf"
    assert client.get(response.json()["url"]).content == buf.getvalue()
    for _ in range(5):
        writer.add_blank_page(width=600, height=800)
    buf = io.BytesIO()
    writer.write(buf)
    assert (
        client.post(
            "/api/intake/documents",
            files={"file": ("too-many.pdf", buf.getvalue(), "application/pdf")},
        ).status_code
        == 422
    )


def test_automatic_guidance_handoff_is_durable_and_idempotent(client, monkeypatch):
    import asyncio
    from server import guidance
    from server.database import GuidanceJob, AIRun

    monkeypatch.setenv("AI_DAILY_LIMIT", "100000")
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    calls = []

    async def checked(db, workspace, asset, problem, mode):
        calls.append((asset.id, problem, mode))
        return {
            "recommendation": {"summary": "Reviewed fixture"},
            "policy_version": __import__("server.ai",fromlist=["POLICY"]).POLICY,
            "verdict": "needs_information",
        }

    monkeypatch.setattr(guidance, "recommend", checked)
    client.post("/api/session/technician", json={"name": "Taylor Brooks"})
    asset = client.get("/api/assets").json()[0]
    body = {
        **request_body(asset),
        "technician": "Sam Chen",
        "reviewed": True,
        "submission_id": "automatic-handoff-test",
    }
    r = client.post("/api/intake/handoff", json=body).json()
    assert r["guidance"]["status"] == "queued"
    assert client.post("/api/intake/handoff", json=body).json()["id"] == r["id"]
    assert client.post("/api/requests/" + r["id"] + "/guidance").status_code == 403
    # Processing starts from the persisted reception handoff, without technician interaction.
    assert asyncio.run(guidance.process_one(r["id"]))
    assert not asyncio.run(guidance.process_one(r["id"]))
    assert calls == [(asset["id"], body["description"], "C")]
    client.post("/api/session/technician", json={"name": "Sam Chen"})
    for _ in range(2):
        assert (
            client.post("/api/requests/" + r["id"] + "/guidance").json()["status"]
            == "ready"
        )
    delivered = client.get("/api/requests/" + r["id"] + "/guidance").json()
    assert delivered["result"]["automatic"] is True
    assert delivered["result"]["verdict"] == "needs_information"
    with Session() as db:
        assert (
            len(
                db.scalars(
                    select(GuidanceJob).where(GuidanceJob.request_id == r["id"])
                ).all()
            )
            == 1
        )
        assert (
            len(db.scalars(select(AIRun).where(AIRun.request_id == r["id"])).all()) == 1
        )
    with TestClient(app) as other:
        other.post("/api/demo/start")
        assert other.get("/api/requests/" + r["id"] + "/guidance").status_code == 404


def test_automatic_guidance_honors_budget_and_releases_no_unchecked_result(
    client, monkeypatch
):
    import asyncio
    from server import guidance

    monkeypatch.setenv("AI_DAILY_LIMIT", "0")
    asset = client.get("/api/assets").json()[0]
    r = client.post("/api/requests", json=request_body(asset)).json()

    async def forbidden(*args):
        pytest.fail("Quota must prevent all model calls")

    monkeypatch.setattr(guidance, "recommend", forbidden)
    asyncio.run(guidance.process_one(r["id"]))
    response = client.get("/api/requests/" + r["id"] + "/guidance").json()
    assert (
        response["guidance"]["status"] == "unavailable" and response["result"] is None
    )
    assert "limit" in response["guidance"]["message"]
    monkeypatch.setenv("AI_DAILY_LIMIT", "100000")
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")

    async def failed(*args):
        raise RuntimeError("Simulated judge failure")

    monkeypatch.setattr(guidance, "recommend", failed)
    r = client.post("/api/requests", json=request_body(asset)).json()
    asyncio.run(guidance.process_one(r["id"]))
    response = client.get("/api/requests/" + r["id"] + "/guidance").json()
    assert response["guidance"]["status"] == "queued" and response["result"] is None
    # The retry is delayed, bounded, and still releases no unchecked content.
    assert not asyncio.run(guidance.process_one(r["id"]))
    from server.database import GuidanceJob, now

    with Session() as db:
        job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == r["id"]))
        job.updated_at = now()
        db.commit()
    asyncio.run(guidance.process_one(r["id"]))
    response = client.get("/api/requests/" + r["id"] + "/guidance").json()
    assert (
        response["guidance"]["status"] == "unavailable" and response["result"] is None
    )
    assert not asyncio.run(guidance.process_one(r["id"]))


def test_interrupted_automatic_guidance_recovers_with_bounded_attempts(
    client, monkeypatch
):
    import asyncio
    from datetime import timedelta
    from server import guidance
    from server.database import GuidanceJob, now

    monkeypatch.setenv("AI_DAILY_LIMIT", "100000")
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")

    async def checked(*args):
        return {
            "recommendation": {"summary": "Recovered fixture"},
            "verdict": "supported",
        }

    monkeypatch.setattr(guidance, "recommend", checked)
    asset = client.get("/api/assets").json()[0]
    r = client.post("/api/requests", json=request_body(asset)).json()
    with Session() as db:
        job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == r["id"]))
        job.status, job.attempts, job.updated_at = (
            "running",
            1,
            now() - timedelta(minutes=6),
        )
        db.commit()
    assert asyncio.run(guidance.process_one(r["id"]))
    assert (
        client.get("/api/requests/" + r["id"] + "/guidance").json()["guidance"][
            "status"
        ]
        == "ready"
    )
    with Session() as db:
        job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == r["id"]))
        job.status, job.updated_at = "running", now() - timedelta(minutes=6)
        db.commit()
    assert asyncio.run(guidance.process_one(r["id"]))
    assert (
        client.get("/api/requests/" + r["id"] + "/guidance").json()["guidance"][
            "status"
        ]
        == "unavailable"
    )
