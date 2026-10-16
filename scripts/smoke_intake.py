"""Verify live paper extraction and a receptionist-to-technician handoff."""

import sys, json, time
from pathlib import Path
import httpx

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
with httpx.Client(base_url=url, timeout=160) as c:
    c.post("/api/demo/start").raise_for_status()
    c.post("/api/session/technician", json={"name": "Taylor Brooks"}).raise_for_status()
    scan = Path("public/images/demo-rustproofing-intake.pdf").read_bytes()
    r = c.post(
        "/api/intake/documents",
        files={"file": ("sample-intake.pdf", scan, "application/pdf")},
    )
    r.raise_for_status()
    doc = r.json()
    assert not doc.get("extraction_error"), doc.get("extraction_error")
    facts = doc["extracted"]
    assert facts["asset_code"] == "LM-1042" and facts["serial"] == "DEMO-RP-1042", (
        facts
    )
    assert "packing" in facts["problem"].lower()
    print("PASS Live paper transcription: asset, serial and symptom", flush=True)
    a = next(a for a in c.get("/api/assets").json() if a["code"] == facts["asset_code"])
    payload = {
        "asset_id": a["id"],
        "name": facts["contact_name"] or facts["customer"],
        "email": facts["email"],
        "phone": facts["phone"],
        "title": facts["problem"][:100],
        "description": facts["problem"],
        "category": "General service",
        "operating": "No",
        "technician": "Sam Chen",
        "document_id": doc["id"],
        "reviewed": True,
        "submission_id": "live-intake-" + doc["id"],
        "intake_notes": facts["notes"],
    }
    r = c.post("/api/intake/handoff", json=payload)
    r.raise_for_status()
    request = r.json()
    c.post("/api/session/technician", json={"name": "Sam Chen"}).raise_for_status()
    mine = [
        r
        for r in c.get("/api/dashboard").json()["requests"]
        if r["technician"] == "Sam Chen"
    ]
    assert any(r["id"] == request["id"] for r in mine)
    detail = c.get("/api/requests/" + request["id"]).json()
    assert detail["request"]["documents"][0]["id"] == doc["id"]
    original = c.get(doc["url"])
    assert original.status_code == 200 and original.content == scan
    assert any(e["kind"] == "intake" for e in detail["events"])
    print(
        "PASS Assigned technician receives reviewed problem, notes and unchanged original scan",
        flush=True,
    )
    assert request["guidance"]["status"] in ["queued", "running"]
    # Only read status: never call recommend or ensure-guidance. Reception alone must trigger it.
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        guidance = c.get("/api/requests/" + request["id"] + "/guidance").json()
        if guidance["guidance"]["status"] in ["ready", "unavailable"]:
            break
        time.sleep(3)
    assert guidance["guidance"]["status"] == "ready", guidance
    assert guidance["result"]["automatic"] is True
    assert guidance["result"]["judge"] and guidance["result"]["evidence"]
    print(
        "PASS Guidance and separate judge delivered automatically, without any technician recommendation action",
        flush=True,
    )
    Path(".local/intake-live-validation.json").write_text(
        json.dumps(
            {
                "url": url,
                "request_id": request["id"],
                "automatic_verdict": guidance["result"]["verdict"],
                "extraction": facts,
                "checks": [
                    "live extraction",
                    "reviewed handoff",
                    "assigned queue",
                    "original bytes identical",
                    "intake history",
                    "automatic guidance and separate judge, no technician trigger",
                ],
            },
            indent=2,
        )
    )
