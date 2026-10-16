"""Hosted regression check: four roles, customer ownership and no external repair API."""

import argparse
import json
from pathlib import Path
import httpx

p = argparse.ArgumentParser()
p.add_argument("url")
args = p.parse_args()
checks = []


def check(name, ok):
    assert ok, name
    checks.append(name)
    print("PASS", name, flush=True)


with httpx.Client(base_url=args.url, timeout=120) as c:
    check(
        "Current role policy deployed",
        c.get("/api/health").json()["evidence_policy"] == "5.2-calgary-roles",
    )
    c.post("/api/demo/start").raise_for_status()
    accounts = c.get("/api/session").json()["accounts"]
    check(
        "Exactly four supported roles",
        {a["role"] for a in accounts}
        == {"technician", "reception", "customer", "superuser"},
    )
    owner = next(a for a in accounts if a.get("label") == "Prairie Fleet Services")
    check("Business owner has customer access", owner["role"] == "customer")
    c.post("/api/accounts/switch", json={"name": owner["name"]}).raise_for_status()
    assets = c.get("/api/portal/assets").json()
    check("Business equipment remains accessible", bool(assets))
    a = assets[0]
    r = c.post(
        "/api/portal/symptoms",
        json={
            "asset_id": a["id"],
            "description": "Synthetic access test: request workshop inspection.",
        },
    )
    r.raise_for_status()
    r = r.json()
    check("Customer request goes to reception", r["technician"] == "Unassigned")
    check("External repair queue removed", c.get("/api/repairs").status_code == 404)
    check(
        "External repair detail removed",
        c.get("/api/repairs/" + r["id"]).status_code == 404,
    )
    check(
        "External repair write endpoints removed",
        all(
            c.post("/api/repairs/" + r["id"] + suffix, json={}).status_code
            in (404, 405)
            for suffix in ["/prepare", "/draft", "/reports", "/observations"]
        ),
    )
    check(
        "Customer cannot open staff repair detail",
        c.get("/api/requests/" + r["id"]).status_code == 403,
    )
    other = next(
        x for x in accounts if x["role"] == "customer" and x["name"] != owner["name"]
    )
    c.post("/api/accounts/switch", json={"name": other["name"]}).raise_for_status()
    check(
        "Other owner cannot see equipment",
        c.get("/api/portal/assets/" + a["id"]).status_code == 404,
    )
    staff = next(x for x in accounts if x["role"] == "reception")
    c.post("/api/accounts/switch", json={"name": staff["name"]}).raise_for_status()
    check(
        "Reception sees request for assignment",
        c.get("/api/requests/" + r["id"]).json()["request"]["technician"]
        == "Unassigned",
    )
    check(
        "Cannot create retired role",
        c.post(
            "/api/customers", json={"name": "Removed role test", "kind": "manufacturer"}
        ).status_code
        == 422,
    )

Path(".local/reports/role-removal-hosted-checks.json").write_text(
    json.dumps({"url": args.url, "checks": checks}, indent=2)
)
