"""Customer ownership, removed repair access and conditional guidance candidates."""

import os, asyncio

os.environ["AUTO_GUIDANCE_WORKER"] = "0"
from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from server.main import app
from server.database import (
    Session,
    Asset,
    Event,
    KnowledgeCase,
    GuidanceJob,
    AIRun,
    ServiceRequest,
    now,
)
from server.ai import corpus, Recommendation, Judgment, PartCandidate, JudgeCheck
from server.expansion_models import AssetOwner


@pytest.fixture
def demo():
    with TestClient(app) as c:
        assert c.post("/api/demo/start").status_code == 200
        yield c


def switch(c, role):
    account = next(
        a
        for a in c.get("/api/session").json()["accounts"]
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


def start(c):
    switch(c, "second_customer")
    a = c.get("/api/portal/assets").json()[0]
    r = c.post(
        "/api/portal/symptoms",
        json={
            "asset_id": a["id"],
            "description": "Low pressure during application; no diagnosis confirmed.",
        },
    )
    assert r.status_code == 200, r.text
    return a, r.json()


def test_removed_role_migrates_without_losing_assets_or_history(demo):
    from server.expansion_models import Customer
    from server.migrations import migrate

    c = demo
    a, r = start(c)
    with Session() as db:
        owner = db.get(AssetOwner, a["id"])
        account = db.get(Customer, owner.customer_id)
        account.kind = "manufacturer"  # Simulate an account from the old release.
        req = db.get(ServiceRequest, r["id"])
        req.technician, req.category = account.name, "Organization self-service"
        event = Event(
            workspace_id=account.workspace_id,
            asset_id=a["id"],
            kind="service",
            title="Previously recorded repair",
            actor=account.name,
            body={"diagnosis": "Preserved finding"},
        )
        db.add(event)
        db.commit()
        event_id, customer_id = event.id, account.id
    migrate()
    migrate()  # Startup migration remains safe to repeat.
    assert c.get("/api/session").json()["role"] == "customer"
    assert all(
        x["role"] != "manufacturer" for x in c.get("/api/session").json()["accounts"]
    )
    passport = c.get("/api/portal/assets/" + a["id"]).json()
    assert passport["asset"]["id"] == a["id"]
    assert any(e["id"] == event_id for e in passport["events"])
    assert (
        next(x for x in passport["requests"] if x["id"] == r["id"])["technician"]
        == "Unassigned"
    )
    with Session() as db:
        assert db.get(Customer, customer_id).kind == "customer"
        assert db.get(ServiceRequest, r["id"]).version == r["version"] + 1
    for method, suffix in [
        ("get", ""),
        ("post", "/prepare"),
        ("post", "/draft"),
        ("post", "/reports"),
        ("post", "/observations"),
    ]:
        response = getattr(c, method)("/api/repairs/" + r["id"] + suffix)
        assert response.status_code in (404, 405)
    assert c.get("/api/repairs").status_code == 404
    assert not any(route.path.startswith("/api/repairs") for route in app.routes)
    assert c.get("/api/requests/" + r["id"]).status_code == 403
    switch(c, "reception")
    assert (
        c.post(
            "/api/customers", json={"name": "Removed role", "kind": "manufacturer"}
        ).status_code
        == 422
    )
    assert (
        c.get("/api/requests/" + r["id"]).json()["request"]["technician"]
        == "Unassigned"
    )


def test_unavailable_is_visible_and_retry_is_bounded(demo):
    c = demo
    a, r = start(c)
    with Session() as db:
        job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == r["id"]))
        job.status = "unavailable"
        job.message = "Free model quota exhausted"
        job.updated_at = now()
        db.commit()
    req = c.get("/api/portal/assets/" + a["id"]).json()["requests"][0]
    assert req["guidance_job"]["status"] == "unavailable"
    assert req["guidance"] is None
    assert c.post("/api/portal/requests/" + r["id"] + "/retry").status_code == 429
    with Session() as db:
        job = db.scalar(select(GuidanceJob).where(GuidanceJob.request_id == r["id"]))
        job.updated_at = now() - timedelta(minutes=2)
        db.commit()
    assert (
        c.post("/api/portal/requests/" + r["id"] + "/retry").json()["status"]
        == "queued"
    )


def test_customer_evidence_and_request_isolation(demo):
    c = demo
    assets = c.get("/api/assets").json()
    forbidden = next(a for a in assets if a["code"] == "LM-1042")
    a, r = start(c)
    with Session() as db:
        asset = db.get(Asset, a["id"])
        db.add(
            KnowledgeCase(
                workspace_id=asset.workspace_id,
                code="PRIVATE-CASE",
                model=asset.model,
                symptom="Low pressure",
                diagnosis="Private other account fault",
                repair="Private other account work",
                parts=[],
                test="Private",
                outcome="Repaired",
                source="Private",
                asset_id=forbidden["id"],
            )
        )
        db.commit()
        assert not any(
            e["id"] == "PRIVATE-CASE"
            for e in corpus(db, asset.workspace_id, asset, "C")
        )
    switch(c, "technician")
    other = next(
        x
        for x in c.get("/api/dashboard").json()["requests"]
        if x["asset_id"] == forbidden["id"]
    )
    switch(c, "second_customer")
    assert c.get("/api/repairs/" + other["id"]).status_code == 404
    assert c.get("/api/requests/" + other["id"]).status_code == 403


def test_reviewed_candidates_require_judge_approval_and_no_guessed_probability(
    demo, monkeypatch
):
    import server.ai as ai

    a = demo.get("/api/assets").json()[0]

    async def retrieve(db, q, items):
        return [
            {
                "id": "CASE-1",
                "kind": "case",
                "asset_id": a["id"],
                "content": "Packing wear; L015-291 packing replacement corrected seepage",
                "model": a["model"],
            }
        ], "test"

    async def model(model, system, prompt, schema, *args):
        if schema is Recommendation:
            return Recommendation(
                summary="Confirm the location of seepage.",
                disposition="needs_information",
                questions=["Where does fluid appear?"],
                part_candidates=[
                    PartCandidate(
                        part="L015-291",
                        reason="Prior matching packing repair",
                        confirm_with="Record whether seepage is at the needle packing.",
                        source_ids=["CASE-1"],
                    )
                ],
            )
        return Judgment(
            verdict="needs_information",
            reason="Conditional only",
            checks=[
                JudgeCheck(
                    criterion="Evidence",
                    status="pass",
                    reason="History supports the hypothesis",
                )
            ],
            approved_candidates=["L015-291"],
        )

    monkeypatch.setattr(ai, "retrieve", retrieve)
    monkeypatch.setattr(ai, "model_json", model)
    with Session() as db:
        asset = db.get(Asset, a["id"])
        result = asyncio.run(
            ai.recommend(db, asset.workspace_id, asset, "packing seepage")
        )
        assert result["verdict"] == "needs_information"
        assert result["recommendation"]["parts"] == []
        assert result["part_candidates"][0]["probability"] is None
        assert result["part_candidates"][0]["confidence_interval"] is None
        assert len(result["part_candidates"]) == 1
        db.rollback()

    async def fail(*args):
        if args[3] is Recommendation:
            return await model(*args)
        return Judgment(
            verdict="unsupported",
            reason="Not supported",
            checks=[
                JudgeCheck(criterion="Evidence", status="fail", reason="No support")
            ],
            approved_candidates=["L015-291"],
        )

    monkeypatch.setattr(ai, "model_json", fail)
    with Session() as db:
        asset = db.get(Asset, a["id"])
        result = asyncio.run(
            ai.recommend(db, asset.workspace_id, asset, "different symptom")
        )
        assert (
            result["part_candidates"] == []
            and result["recommendation"]["part_candidates"] == []
        )


def test_changed_observations_supersede_running_job(demo, monkeypatch):
    import server.guidance as g

    c = demo
    a, r = start(c)

    async def changed(db, w, asset, problem, mode):
        with Session() as other:
            req = other.get(ServiceRequest, r["id"])
            req.description += " New observation"
            req.version += 1
            job = other.scalar(
                select(GuidanceJob).where(GuidanceJob.request_id == r["id"])
            )
            job.status = "queued"
            job.run_id = None
            job.attempts = 0
            other.commit()
        return {"verdict": "supported", "recommendation": {"summary": "Old result"}}

    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    monkeypatch.setenv("AI_DAILY_LIMIT", "10000")
    monkeypatch.setattr(g, "recommend", changed)
    assert asyncio.run(g.process_one(r["id"]))
    d = next(
        x
        for x in c.get("/api/portal/assets/" + a["id"]).json()["requests"]
        if x["id"] == r["id"]
    )
    assert d["guidance_job"]["status"] == "queued" and d["guidance"] is None


def test_owner_can_answer_questions_without_opening_another_request(demo):
    c = demo
    switch(c, "customer")
    a = c.get("/api/portal/assets").json()[0]
    r = c.post(
        "/api/portal/symptoms",
        json={
            "asset_id": a["id"],
            "description": "Low pressure while spraying material.",
        },
    ).json()
    path = "/api/portal/requests/" + r["id"] + "/observations"
    assert (
        c.post(
            path,
            json={
                "version": r["version"],
                "observations": "The reading drops during flow, but not at rest.",
            },
        ).status_code
        == 200
    )
    updated = next(
        x
        for x in c.get("/api/portal/assets/" + a["id"]).json()["requests"]
        if x["id"] == r["id"]
    )
    assert updated["guidance_job"]["status"] == "queued"
    assert updated["version"] == r["version"] + 1
    switch(c, "second_customer")
    assert (
        c.post(
            path,
            json={
                "version": updated["version"],
                "observations": "Attempt from another owner account.",
            },
        ).status_code
        == 404
    )
