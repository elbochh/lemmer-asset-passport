"""Rust scan: simulated detector, technician review and owner visibility."""

import io, os

os.environ["AUTO_GUIDANCE_WORKER"] = "0"
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from server.main import app
from server import rust_scan
from tests.test_expansion import switch


@pytest.fixture(autouse=True)
def simulated_detector(monkeypatch):
    # API workflow tests use the deterministic simulation; the trained model
    # is exercised separately in test_local_model_on_held_out_photo.
    monkeypatch.setenv("RUST_DETECTOR", "simulated")


@pytest.fixture
def demo():
    with TestClient(app) as c:
        assert c.post("/api/demo/start").status_code == 200
        yield c


def png(color="gray"):
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, "PNG")
    return buf.getvalue()


def visit_with_before(c, color="gray"):
    vehicle = next(
        a
        for a in c.get("/api/portal/assets").json()
        if a["ownership"]["kind"] == "vehicle"
    )
    visit = c.post("/api/visits", json={"asset_id": vehicle["id"]}).json()
    r = c.post(
        f"/api/visits/{visit['id']}/media/before",
        files={"file": ("t.png", png(color), "image/png")},
    )
    assert r.status_code == 200, r.text
    return vehicle, r.json()


def test_simulation_is_deterministic_and_labelled():
    a = rust_scan.simulate(b"same bytes")
    assert a["findings"] == rust_scan.simulate(b"same bytes")["findings"]
    assert a["simulated"] is True and a["model"]["name"] == "simulation"
    assert a["review_status"] == "Pending"
    for f in a["findings"]:
        assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in f["polygon"])


def test_service_response_validation():
    ok = rust_scan.parse_service_response(
        {
            "model": {"name": "yolo11n-seg"},
            "findings": [
                {
                    "classification": "rust",
                    "confidence": 0.9,
                    "polygon": [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]],
                }
            ],
        }
    )
    assert ok["simulated"] is False and ok["area_pct"] == 25.0
    assert ok["severity"] == "Medium"
    with pytest.raises(rust_scan.DetectorError):
        rust_scan.parse_service_response({"findings": [{"polygon": [[0, 0]]}]})
    with pytest.raises(rust_scan.DetectorError):
        rust_scan.parse_service_response({})


def test_scan_requires_before_image_and_technician(demo):
    c = demo
    vehicle = next(
        a
        for a in c.get("/api/portal/assets").json()
        if a["ownership"]["kind"] == "vehicle"
    )
    visit = c.post("/api/visits", json={"asset_id": vehicle["id"]}).json()
    assert c.post(f"/api/visits/{visit['id']}/rust-scan").status_code == 422
    switch(c, "customer")
    assert c.post(f"/api/visits/{visit['id']}/rust-scan").status_code == 403


def test_scan_review_and_owner_visibility(demo):
    c = demo
    vehicle, visit = visit_with_before(c)
    scan = c.post(f"/api/visits/{visit['id']}/rust-scan")
    assert scan.status_code == 200, scan.text
    v = scan.json()
    assert v["report"]["rust_scan"]["review_status"] == "Pending"
    assert v["report"]["rust_scan"]["simulated"] is True
    # review needs the current version
    stale = c.patch(
        f"/api/visits/{visit['id']}/rust-scan/review",
        json={"status": "Confirmed", "notes": "", "version": v["version"] - 1},
    )
    assert stale.status_code == 409
    # unreviewed scan is not on the owner's passport timeline
    switch(c, "customer")
    events = c.get("/api/portal/assets/" + vehicle["id"]).json()["events"]
    assert not any("rust_scan" in e["body"] for e in events)
    switch(c, "technician")
    done = c.patch(
        f"/api/visits/{visit['id']}/rust-scan/review",
        json={"status": "Confirmed", "notes": "Checked on site", "version": v["version"]},
    )
    assert done.status_code == 200, done.text
    scan = done.json()["report"]["rust_scan"]
    assert scan["review_status"] == "Confirmed"
    assert scan["reviewed_by"] and scan["reviewed_at"]
    switch(c, "customer")
    events = c.get("/api/portal/assets/" + vehicle["id"]).json()["events"]
    assert any(e["body"].get("rust_scan", {}).get("review_status") == "Confirmed" for e in events)


def test_rejected_scan_never_reaches_owner(demo):
    c = demo
    vehicle, visit = visit_with_before(c, "red")
    v = c.post(f"/api/visits/{visit['id']}/rust-scan").json()
    r = c.patch(
        f"/api/visits/{visit['id']}/rust-scan/review",
        json={"status": "Rejected", "notes": "", "version": v["version"]},
    ).json()
    report = {
        "findings": "Synthetic corrosion example.",
        "treatment": "Simulated coating applied.",
        "verification": "Simulated verification.",
    }
    version = r["version"]
    for status in [
        "Bay preparation", "Ready for inspection", "Inspecting", "Findings review",
        "Treatment recorded", "Verification", "Completed",
    ]:
        resp = c.patch(f"/api/visits/{visit['id']}", json={**report, "version": version, "status": status})
        assert resp.status_code == 200, resp.text
        version += 1
    switch(c, "customer")
    events = c.get("/api/portal/assets/" + vehicle["id"]).json()["events"]
    assert not any("rust_scan" in e["body"] for e in events)


def test_service_url_normalisation():
    assert rust_scan._service_url("host:10000") == "http://host:10000/detect"
    assert rust_scan._service_url("https://x.onrender.com/") == "https://x.onrender.com/detect"
    assert rust_scan._service_url("https://x.com/custom") == "https://x.com/custom"


def test_ai_suggestion_template_is_labelled_and_grounded():
    from server import ai_suggest, rust_scan

    scan = rust_scan.simulate(b"x" * 64)
    out = ai_suggest.template(scan)
    assert set(out) == {"findings", "treatment", "verification"}
    assert all(out.values())


def test_work_report_shows_only_confirmed_work_to_account_holders(demo):
    c = demo
    share = c.get("/api/session").json()["share"]
    vehicle, visit = visit_with_before(c, "red")
    v = c.post(f"/api/visits/{visit['id']}/rust-scan").json()
    c.post(f"/api/visits/{visit['id']}/ai-suggestion")
    url = f"/api/work/{share}/{vehicle['code']}"
    with TestClient(app) as anon:  # no account, no cookie
        assert anon.get(url).status_code in (401, 403)
    assert c.get(f"/api/work/{share}/NOPE").status_code == 404
    assert c.get(f"/api/work/bad/{vehicle['code']}").status_code == 404
    # unreviewed scan is not shown
    assert not any(w["rust_review"] for w in c.get(url).json()["work"])
    c.patch(
        f"/api/visits/{visit['id']}/rust-scan/review",
        json={"status": "Confirmed", "notes": "ok", "version": v["version"] + 1},
    )
    body = c.get(url).json()
    assert any(w["rust_review"] for w in body["work"])
    text = str(body)
    assert "ai_suggestion" not in text and "reviewed_by" not in text
    assert "customer" not in body["asset"]


def test_work_report_includes_equipment_repairs(demo):
    c = demo
    share = c.get("/api/session").json()["share"]
    target = None
    for a in c.get("/api/portal/assets").json():
        events = c.get("/api/portal/assets/" + a["id"]).json()["events"]
        if any(e["body"].get("work") for e in events):
            target = a
            break
    assert target, "seed data has no equipment repair"
    work = c.get(f"/api/work/{share}/{target['code']}").json()["work"]
    assert any(w["kind"] == "service" and w["work"] for w in work)


def review(c, visit, status, version, notes=""):
    return c.patch(
        f"/api/visits/{visit['id']}/rust-scan/review",
        json={"status": status, "notes": notes, "version": version},
    )


def test_overlapping_regions_are_counted_once():
    square = [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]
    assert rust_scan.union_area_pct([square]) == 25.0
    assert rust_scan.union_area_pct([square, square]) == 25.0
    shifted = [[0.25, 0], [0.75, 0], [0.75, 0.5], [0.25, 0.5]]
    assert rust_scan.union_area_pct([square, shifted]) == 37.5


def test_customer_never_sees_unconfirmed_scan_on_visits(demo):
    c = demo
    vehicle, visit = visit_with_before(c)
    v = c.post(f"/api/visits/{visit['id']}/rust-scan").json()
    for status in ["Pending", "Rejected", "Needs Review"]:
        if status != "Pending":
            v = review(c, visit, status, v["version"]).json()
        switch(c, "customer")
        visits = c.get("/api/portal/assets/" + vehicle["id"]).json()["visits"]
        assert not any("rust_scan" in x["report"] for x in visits), status
        switch(c, "technician")
    assert review(c, visit, "Confirmed", v["version"]).status_code == 200
    switch(c, "customer")
    visits = c.get("/api/portal/assets/" + vehicle["id"]).json()["visits"]
    assert any(x["report"].get("rust_scan") for x in visits)


def test_confirmed_scan_is_final_and_recorded_once(demo):
    c = demo
    vehicle, visit = visit_with_before(c)
    v = c.post(f"/api/visits/{visit['id']}/rust-scan").json()
    v = review(c, visit, "Confirmed", v["version"]).json()
    assert review(c, visit, "Confirmed", v["version"]).status_code == 409
    assert review(c, visit, "Rejected", v["version"]).status_code == 409
    assert c.post(f"/api/visits/{visit['id']}/rust-scan").status_code == 409
    events = c.get("/api/portal/assets/" + vehicle["id"]).json()["events"]
    assert sum(1 for e in events if "rust_scan" in e["body"]) == 1


def test_new_photo_replaces_scan_and_allows_another_confirmed_area(demo):
    c = demo
    vehicle, visit = visit_with_before(c, "gray")
    v = c.post(f"/api/visits/{visit['id']}/rust-scan").json()
    first_media = v["report"]["rust_scan"]["source_media_id"]
    v = review(c, visit, "Confirmed", v["version"]).json()
    # A new photo: the old scan leaves the visit (its passport event stays).
    r = c.post(
        f"/api/visits/{visit['id']}/media/before",
        files={"file": ("t.png", png("blue"), "image/png")},
    )
    assert "rust_scan" not in r.json()["report"]
    v = c.post(f"/api/visits/{visit['id']}/rust-scan").json()
    assert v["report"]["rust_scan"]["source_media_id"] != first_media
    assert review(c, visit, "Confirmed", v["version"]).status_code == 200
    events = c.get("/api/portal/assets/" + vehicle["id"]).json()["events"]
    sources = {
        e["body"]["rust_scan"]["source_media_id"]
        for e in events
        if "rust_scan" in e["body"]
    }
    assert len(sources) == 2


def test_unconfirmed_scan_is_dropped_when_photo_changes(demo):
    c = demo
    _, visit = visit_with_before(c, "gray")
    c.post(f"/api/visits/{visit['id']}/rust-scan")
    r = c.post(
        f"/api/visits/{visit['id']}/media/before",
        files={"file": ("t.png", png("green"), "image/png")},
    )
    assert "rust_scan" not in r.json()["report"]


def test_completion_record_does_not_repeat_confirmed_scan(demo):
    c = demo
    vehicle, visit = visit_with_before(c)
    v = c.post(f"/api/visits/{visit['id']}/rust-scan").json()
    version = review(c, visit, "Confirmed", v["version"]).json()["version"]
    report = {
        "findings": "Synthetic corrosion example.",
        "treatment": "Simulated coating applied.",
        "verification": "Simulated verification.",
    }
    for status in [
        "Bay preparation", "Ready for inspection", "Inspecting", "Findings review",
        "Treatment recorded", "Verification", "Completed",
    ]:
        r = c.patch(f"/api/visits/{visit['id']}", json={**report, "version": version, "status": status})
        assert r.status_code == 200, r.text
        version += 1
    events = c.get("/api/portal/assets/" + vehicle["id"]).json()["events"]
    assert sum(1 for e in events if "rust_scan" in e["body"]) == 1
    assert any(e["title"] == "Simulated rustproofing visit completed" for e in events)


def test_model_info_is_staff_only(demo):
    c = demo
    r = c.get("/api/rust-scan/model")
    assert r.status_code == 200 and r.json()["simulated"] is True
    switch(c, "customer")
    assert c.get("/api/rust-scan/model").status_code == 403


SAMPLE = rust_scan.MODEL_DIR.parent.parent / "public/images/rust-samples/rust-sample-1.jpg"


@pytest.mark.skipif(
    not (rust_scan.MODEL_PATH.exists() and SAMPLE.exists()),
    reason="trained model not installed",
)
def test_local_model_on_held_out_photo(monkeypatch):
    monkeypatch.setenv("RUST_DETECTOR", "local")
    result = rust_scan.detect(SAMPLE.read_bytes(), "image/jpeg")
    assert result["simulated"] is False
    assert result["findings"], "the held-out sample contains labelled rust"
    for f in result["findings"]:
        x1, y1, x2, y2 = f["box"]
        assert 0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1
        assert f["confidence"] >= result["model"]["threshold"] - 0.005
    # A flat grey picture has no rust texture to find.
    assert rust_scan.detect(png("gray"), "image/png")["findings"] == []
    info = rust_scan.model_info()
    assert info["mode"] == "local" and info["metrics"]["test"]["images"] > 0


def test_customer_never_receives_ai_wording(demo):
    c = demo
    vehicle, visit = visit_with_before(c)
    c.post(f"/api/visits/{visit['id']}/rust-scan")
    assert c.post(f"/api/visits/{visit['id']}/ai-suggestion").status_code == 200
    switch(c, "customer")
    visits = c.get("/api/portal/assets/" + vehicle["id"]).json()["visits"]
    assert not any("ai_suggestion" in x["report"] for x in visits)


def test_new_photo_discards_ai_wording_from_old_scan(demo):
    c = demo
    _, visit = visit_with_before(c)
    c.post(f"/api/visits/{visit['id']}/rust-scan")
    c.post(f"/api/visits/{visit['id']}/ai-suggestion")
    r = c.post(
        f"/api/visits/{visit['id']}/media/before",
        files={"file": ("t.png", png("yellow"), "image/png")},
    )
    assert "ai_suggestion" not in r.json()["report"]


def test_public_work_report_hides_internal_notes_and_shows_amendments(demo):
    from server.database import Session, Event, Workspace
    from sqlalchemy import select

    c = demo
    share = c.get("/api/session").json()["share"]
    with Session() as db:
        ws = db.scalar(select(Workspace).where(Workspace.share == share))
        e = db.scalars(
            select(Event).where(Event.workspace_id == ws.id, Event.kind == "service")
        ).first()
        from server.database import Asset

        code = db.get(Asset, e.asset_id).code
        e.body = {**e.body, "work": "Original work wording.", "notes": "INTERNAL-ONLY note"}
        db.add(
            Event(
                workspace_id=ws.id,
                asset_id=e.asset_id,
                kind="amendment",
                title="Report amended",
                actor="Test",
                body={"original_event_id": e.id, "reason": "typo",
                      "changes": {"work": "Corrected work wording."}},
            )
        )
        db.commit()
    with TestClient(app) as anon:  # the report needs an account
        assert anon.get(f"/api/work/{share}/{code}").status_code in (401, 403)
    assert c.get(f"/api/work/{share}/NOPE").status_code == 404
    text = str(c.get(f"/api/work/{share}/{code}").json())
    assert "INTERNAL-ONLY" not in text
    assert "Corrected work wording." in text and "Original work wording." not in text
