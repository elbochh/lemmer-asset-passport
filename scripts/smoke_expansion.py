"""Validate the hosted v2 workflows with synthetic data and no required model calls."""

import sys, uuid, json
from pathlib import Path
import httpx

url = sys.argv[1]
checks = []


def check(name, ok):
    assert ok, name
    checks.append(name)
    print("PASS", name, flush=True)


with httpx.Client(base_url=url, timeout=160) as c:
    check(
        "PostgreSQL v3 health",
        c.get("/api/health").json().get("version") == "3.0",
    )
    r = c.post("/api/demo/start")
    r.raise_for_status()
    session = c.get("/api/session").json()
    accounts = session["accounts"]

    def switch(role):
        a = next(a for a in accounts if (a.get("label") == "Fictional Customer 002" if role == "second_customer" else a["role"] == role))
        c.post("/api/accounts/switch", json={"name": a["name"]}).raise_for_status()

    check(
        "Four roles available",
        {a["role"] for a in accounts}
        == {"technician", "reception", "customer", "superuser"},
    )
    catalog = c.get("/api/catalog").json()
    check("103 rustproofing listings", len(catalog) == 103)
    check("Local catalogue photo", c.get(catalog[0]["image"]).status_code == 200)
    assets = c.get("/api/portal/assets").json()
    v = next(a for a in assets if a["ownership"]["kind"] == "vehicle")
    a = next(a for a in assets if a["code"] == "TEST-ASSET-001")
    other = next(a for a in assets if a["customer"] == "Fictional Customer 002")
    visit = c.post("/api/visits", json={"asset_id": v["id"]}).json()
    path = "/api/visits/" + visit["id"]
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
        r = c.patch(
            path,
            json={
                "version": version,
                "status": status,
                "findings": "Synthetic rear crossmember corrosion example",
                "treatment": "Simulated coating only",
                "verification": "Simulated comparison recorded, no hardware connected",
            },
        )
        r.raise_for_status()
    check("Vehicle visit completes persistently", r.json()["status"] == "Completed")
    switch("customer")
    own = c.get("/api/portal/assets").json()
    check("Customer sees own equipment and vehicle", len(own) == 4)
    check(
        "Other customer asset blocked",
        c.get("/api/portal/assets/" + other["id"]).status_code == 404,
    )
    check("Staff API blocked", c.get("/api/assets").status_code == 403)
    check(
        "QR resolves owned asset",
        c.get(f"/api/qr/{session['share']}/{a['code']}").json()["id"] == a["id"],
    )
    detail = c.get("/api/portal/assets/" + v["id"]).json()
    check(
        "Vehicle report visible to its owner",
        any(e["body"].get("visit_id") == visit["id"] for e in detail["events"]),
    )
    body = {
        "asset_id": a["id"],
        "description": "Synthetic packing seepage; request branch compatibility review",
        "part": "TEST-PART-M1-001",
        "quantity": 1,
        "submission_id": str(uuid.uuid4()),
    }
    order = c.post("/api/parts-requests", json=body)
    order.raise_for_status()
    order = order.json()
    check(
        "Parts request deduplicates",
        c.post("/api/parts-requests", json=body).json()["id"] == order["id"],
    )
    switch("second_customer")
    check("Organization isolated", c.get("/api/parts-requests").json() == [])
    switch("reception")
    orders = c.get("/api/parts-requests").json()
    check(
        "Reception receives owner and asset details",
        any(
            x["id"] == order["id"] and x["asset"]["id"] == a["id"] and x["customer"]
            for x in orders
        ),
    )
    customer = c.get("/api/customers").json()[0]
    for i in range(2):
        r = c.post(
            "/api/registry",
            json={
                "customer_id": customer["id"],
                "customer_confirmed": True,
                "name": f"Demo third-party pump {i}",
                "manufacturer": "Demo manufacturer",
                "model": "Demo-20",
                "serial": "TEST-" + uuid.uuid4().hex[:8],
            },
        )
        r.raise_for_status()
    check(
        "Reception assigns two third-party assets to existing owner",
        next(x for x in c.get("/api/customers").json() if x["id"] == customer["id"])[
            "asset_count"
        ]
        == customer["asset_count"] + 2,
    )
    with httpx.Client(base_url=url, timeout=160) as anon:
        check(
            "Anonymous QR history protected",
            anon.get(f"/api/public/{session['share']}/{a['code']}").status_code == 401,
        )
Path(".local/expansion-cloud-validation.json").write_text(
    json.dumps({"url": url, "checks": checks}, indent=2)
)
print("Hosted ownership and vehicle workflow checks complete.")
