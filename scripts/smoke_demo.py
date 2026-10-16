"""Exercise an isolated synthetic workspace on a deployed demo; never print credentials."""

import argparse, json, time
from pathlib import Path
from datetime import date
import httpx

p = argparse.ArgumentParser()
p.add_argument("url")
p.add_argument("--live-ai", action="store_true")
args = p.parse_args()
record = {"url": args.url, "date": date.today().isoformat(), "checks": []}


def check(name, condition):
    assert condition, name
    record["checks"].append(name)
    print("PASS", name, flush=True)


with httpx.Client(base_url=args.url, timeout=160, follow_redirects=True) as c:
    check("PostgreSQL health", c.get("/api/health").json()["database"] == "postgresql")
    for route in [
        "/",
        "/assets",
        "/assets/direct-refresh-test",
        "/requests/direct-refresh-test",
    ]:
        r = c.get(route)
        check(
            "SPA route " + route,
            r.status_code == 200 and "text/html" in r.headers["content-type"],
        )
    session = c.post("/api/demo/start")
    check("Create demo workspace", session.status_code == 200)
    check(
        "HTTP-only secure session cookie",
        "HttpOnly" in session.headers["set-cookie"]
        and "Secure" in session.headers["set-cookie"],
    )
    assets = c.get("/api/assets").json()
    a = next(x for x in assets if x["code"] == "LM-1042")
    b = next(x for x in assets if x["code"] == "LM-1043")
    share = session.json()["share"]
    for item in [a, b]:
        public = c.get(f"/api/public/{share}/{item['code']}").json()
        check("QR binds " + item["code"], public["asset"]["id"] == item["id"])
    before = c.get("/api/assets/" + b["id"]).json()["events"]
    new = c.post(
        "/api/requests",
        json={
            "asset_id": a["id"],
            "title": "Demo validation: gun leaks at the needle packing",
            "description": "Fluid seeps at the needle packing after storage.",
            "category": "Leak",
            "operating": "No",
            "name": "Demo validation technician",
            "email": "demo@example.test",
        },
    )
    check("Create asset-specific request", new.status_code == 200)
    req = new.json()
    path = "/api/requests/" + req["id"]
    report = {
        "diagnosis": "Demo: needle packing wear confirmed",
        "work": "Demo: technician inspected and replaced the worn needle packing",
        "parts": ["L015-291"],
        "test": "Demo: controlled leak and flow test passed",
        "outcome": "Repaired",
        "inspection_date": date.today().isoformat(),
        "version": req["version"],
        "submission_id": "azure-validation-" + req["id"],
    }
    res = c.post(path + "/reports", json=report)
    check("Finalize report", res.status_code == 200)
    event = res.json()["event"]
    check(
        "Idempotent repeat",
        c.post(path + "/reports", json=report).json()["event"]["id"] == event["id"],
    )
    check(
        "Second asset unaffected",
        c.get("/api/assets/" + b["id"]).json()["events"] == before,
    )
    check(
        "Closed report persists on reread",
        c.get(path).json()["request"]["status"] == "Closed",
    )
    cases = c.get("/api/knowledge").json()["cases"]
    case = next(x for x in cases if x.get("event_id") == event["id"])
    check("Report becomes correct asset knowledge", case["asset_id"] == a["id"])
    check("Workspace export", c.get("/api/export").status_code == 200)
    if args.live_ai:
        ai = c.post(
            path + "/recommend",
            json={
                "problem": "The motor runs normally but the gun leaks at the needle packing after storage. Consider the most recent recorded repair.",
                "mode": "C",
            },
        )
        check("Live generator and judge complete", ai.status_code == 200)
        result = ai.json()
        record["live_ai"] = result
        check(
            "New repair retrieved",
            any(
                x.get("record_id") == case["id"] or x["id"] == "HIST-" + event["id"][:8]
                for x in result["evidence"]
            ),
        )
        check(
            "Independent model identifiers",
            result["models"]["generator"] != result["models"]["judge"],
        )
        odd = c.post(
            path + "/recommend",
            json={
                "problem": "A holographic panel displays QUANTUM-77. This equipment symptom is absent from the provided records.",
                "mode": "C",
            },
        )
        check("Unfamiliar problem processed", odd.status_code == 200)
        value = odd.json()
        record["unknown_problem"] = value
        check(
            "Unfamiliar problem withheld",
            value["verdict"] != "supported"
            and not value["recommendation"]["causes"]
            and not value["recommendation"]["parts"],
        )
    out = Path(".local")
    out.mkdir(exist_ok=True)
    (out / "cloud-validation.json").write_text(json.dumps(record, indent=2))
print("Deployment validation complete.", flush=True)
