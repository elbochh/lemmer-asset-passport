"""Rust scan: simulated detector, technician review and owner visibility."""

import io, os

os.environ["AUTO_GUIDANCE_WORKER"] = "0"
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from server.main import app
from server import rust_scan
from tests.test_expansion import switch


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
