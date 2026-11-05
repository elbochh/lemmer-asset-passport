"""Owner workbook mapping and synthetic-agent evidence checks."""

import os

os.environ["AUTO_GUIDANCE_WORKER"] = "0"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from server.ai import corpus, parts_for
from server.database import Asset, Event, KnowledgeCase, ServiceRequest, Session
from server.expansion_models import ComponentRecord, Customer
from server.main import app


def test_owner_workbook_seed_counts_roles_and_relationships():
    with TestClient(app) as client:
        assert client.post("/api/demo/start").status_code == 200
        assets = client.get("/api/assets").json()
        equipment = [x for x in assets if x["code"].startswith("TEST-ASSET-")]
        assert len(equipment) == 25
        assert {x["model"] for x in equipment} == {
            f"TEST-MODEL-{number:03d}" for number in range(1, 6)
        }

        dashboard = client.get("/api/dashboard").json()
        assert len(dashboard["requests"]) == 50
        assert dashboard["knowledge_count"] == 200

        assert client.post(
            "/api/accounts/switch", json={"name": "Taylor Brooks"}
        ).status_code == 200
        assert len(client.get("/api/customers").json()) == 10

        session = client.get("/api/session").json()
        owner = next(x["name"] for x in session["accounts"] if x["role"] == "customer")
        switched = client.post("/api/accounts/switch", json={"name": owner})
        assert switched.status_code == 200
        assert len(client.get("/api/portal/assets").json()) == 4

        assert client.post(
            "/api/accounts/switch", json={"name": "Demo super-user"}
        ).status_code == 200
        operations = client.get("/api/operations").json()
        assert len(operations["cases"]) == 200
        assert len(operations["reports"]) == 50

        with Session() as db:
            workspace = db.get(Asset, equipment[0]["id"]).workspace_id
            assert db.scalar(
                select(func.count()).select_from(Customer).where(
                    Customer.workspace_id == workspace
                )
            ) == 10
            assert db.scalar(
                select(func.count()).select_from(ComponentRecord).where(
                    ComponentRecord.workspace_id == workspace
                )
            ) == 32
            assert db.scalar(
                select(func.count()).select_from(Event).where(
                    Event.workspace_id == workspace,
                    Event.kind == "attachment_reference",
                )
            ) == 30
            assert db.scalar(
                select(func.count()).select_from(ServiceRequest).where(
                    ServiceRequest.workspace_id == workspace
                )
            ) == 50
            assert db.scalar(
                select(func.count()).select_from(KnowledgeCase).where(
                    KnowledgeCase.workspace_id == workspace
                )
            ) == 200


def test_owner_synthetic_cases_are_available_to_agent_but_not_approved():
    with TestClient(app) as client:
        assert client.post("/api/demo/start").status_code == 200
        asset_data = next(
            x for x in client.get("/api/assets").json() if x["code"] == "TEST-ASSET-001"
        )
        with Session() as db:
            asset = db.get(Asset, asset_data["id"])
            evidence = corpus(db, asset.workspace_id, asset, "B")
            cases = [x for x in evidence if x["kind"] == "case"]
            assert len(cases) == 40
            assert all("not technically verified" in x["source"] for x in cases)
            assert all(x["asset_id"] is None for x in cases)
            assert "TEST-PART-M1-001" in parts_for(asset.model)
