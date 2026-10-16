from datetime import timedelta
from .database import Workspace, Asset, ServiceRequest, Event, KnowledgeCase, now
import secrets

TECHNICIANS = ["Alex Morgan", "Sam Chen", "Jordan Patel"]
RECEPTIONISTS = ["Taylor Brooks"]
CASE_DATA = [
    (
        "KC-001",
        "L-1095",
        "Pump runs but will not prime. Paint is not being drawn from hopper.",
        "Inlet valve sticking after storage.",
        "Technician serviced the inlet valve after following the approved shutdown procedure.",
        ["L004-517"],
        "Priming and controlled spray test recorded by technician.",
        "Repaired",
    ),
    (
        "KC-002",
        "L-1095",
        "Pressure drops while spraying. Material returns through the return tube in spray position.",
        "PRIME/SPRAY valve did not seal.",
        "Technician replaced the confirmed faulty PRIME/SPRAY valve assembly.",
        ["L004-632"],
        "Return flow stopped in spray position; spray test passed.",
        "Repaired",
    ),
    (
        "KC-003",
        "L-1095",
        "Uneven spray and reduced flow after using material containing debris.",
        "Hopper filter screen obstructed.",
        "Technician cleaned and inspected the filter screen.",
        ["L004-501"],
        "Flow and spray pattern verified after service.",
        "Repaired",
    ),
    (
        "KC-004",
        "L-1095",
        "Low pressure after cleaning inlet valve. Problem remained.",
        "Inlet valve suspected; root cause not established.",
        "Cleaned inlet valve; symptom persisted. Further diagnosis required.",
        ["L004-517"],
        "Controlled pressure test still failed.",
        "Unresolved",
    ),
    (
        "KC-005",
        "L-65",
        "Spray gun has reduced flow while pump pressure is maintained.",
        "Gun filter obstructed.",
        "Technician serviced the model-correct filter.",
        ["L032-516"],
        "Flow test passed after servicing.",
        "Repaired",
    ),
    (
        "KC-006",
        "L-65",
        "Fluid leaks around the handle connection.",
        "Handle seal deteriorated.",
        "Technician replaced the confirmed damaged handle seal.",
        ["L032-514"],
        "Leak check passed.",
        "Repaired",
    ),
    (
        "KC-007",
        "L-1095",
        "Pump operates intermittently. Electrical supply not yet verified.",
        "Cause not confirmed.",
        "Initial visual inspection did not establish a repair. No replacement recommended. ",
        [],
        "Further electrical diagnosis by a qualified technician required.",
        "Unresolved",
    ),
    (
        "KC-008",
        "L-1095",
        "Low flow despite a clean screen; diaphragm inspected and found damaged.",
        "Diaphragm damage confirmed during inspection.",
        "Technician replaced the confirmed damaged diaphragm.",
        ["L004-527"],
        "Technician recorded successful functional verification.",
        "Repaired",
    ),
]


def seed_workspace(db):
    w = Workspace(share=secrets.token_urlsafe(24))
    db.add(w)
    db.flush()
    defs = [
        (
            "LM-1042",
            "L-1095 Contractor kit",
            "L-1095",
            "DEMO-1095-042",
            "Northline Painting",
            "Calgary, AB",
            "Needs service",
        ),
        (
            "LM-1043",
            "L-1095 Finishing kit",
            "L-1095",
            "DEMO-1095-043",
            "Prairie Coatings",
            "Airdrie, AB",
            "Operational",
        ),
        (
            "LM-1044",
            "L-65 Airless spray gun",
            "L-65",
            "DEMO-L65-044",
            "Summit Finishes",
            "Calgary, AB",
            "Needs service",
        ),
        (
            "LM-1045",
            "L-1095 Rental unit",
            "L-1095",
            "DEMO-1095-045",
            "Westwood Rentals",
            "Cochrane, AB",
            "In service",
        ),
        (
            "LM-1046",
            "L-65 Finishing gun",
            "L-65",
            "DEMO-L65-046",
            "Northline Painting",
            "Calgary, AB",
            "Operational",
        ),
        (
            "LM-1047",
            "L-1095 Shop unit",
            "L-1095",
            "DEMO-1095-047",
            "Lemmer Demo Shop",
            "Calgary, AB",
            "Operational",
        ),
    ]
    assets = []
    for i, (code, name, model, serial, customer, location, condition) in enumerate(
        defs
    ):
        a = Asset(
            workspace_id=w.id,
            code=code,
            name=name,
            model=model,
            serial=serial,
            customer=customer,
            location=location,
            condition=condition,
            image="/images/l-65.png" if model == "L-65" else "/images/l-1095.png",
            created_at=now() - timedelta(days=120 - i * 8),
        )
        db.add(a)
        assets.append(a)
    db.flush()
    for code, model, symptom, diagnosis, repair, parts, test, outcome in CASE_DATA:
        db.add(
            KnowledgeCase(
                workspace_id=w.id,
                code=code,
                model=model,
                symptom=symptom,
                diagnosis=diagnosis,
                repair=repair,
                parts=parts,
                test=test,
                outcome=outcome,
                created_at=now() - timedelta(days=45),
            )
        )
    events = [
        (
            0,
            30,
            "Inlet valve serviced",
            "Intermittent priming after storage",
            "Inlet valve was cleaned. Priming returned to normal.",
            ["L004-517"],
        ),
        (
            0,
            12,
            "Filter inspection completed",
            "Routine flow check",
            "Filter screen was cleaned; controlled flow test passed.",
            ["L004-501"],
        ),
        (
            1,
            20,
            "Diaphragm replaced",
            "Low pressure with confirmed diaphragm damage",
            "Diaphragm replaced following inspection. Functional test passed.",
            ["L004-527"],
        ),
        (
            2,
            45,
            "Gun filter serviced",
            "Restricted material flow",
            "Filter serviced and flow verified.",
            ["L032-516"],
        ),
        (
            3,
            8,
            "Intake assessment",
            "Intermittent operation",
            "Electrical supply requires further verification.",
            [],
        ),
        (
            4,
            15,
            "Scheduled inspection",
            "Routine inspection",
            "No fault found during inspection.",
            [],
        ),
    ]
    for idx, days, title, symptom, work, parts in events:
        db.add(
            Event(
                workspace_id=w.id,
                asset_id=assets[idx].id,
                title=title,
                actor=TECHNICIANS[idx % 3],
                created_at=now() - timedelta(days=days),
                body={
                    "symptom": symptom,
                    "diagnosis": title,
                    "work": work,
                    "parts": parts,
                    "test": "Functional check recorded in synthetic sample.",
                    "outcome": "Unresolved" if idx == 3 else "Repaired",
                    "source": "Synthetic demonstration history",
                },
            )
        )
    reqs = [
        (
            0,
            "Pump runs, but will not prime",
            "The motor runs normally, but the pump is not picking up material from the hopper. Started after the unit was stored over the weekend.",
            "Priming issue",
            "Urgent",
            "New",
            "Unassigned",
            1,
        ),
        (
            2,
            "Leak at the handle connection",
            "Small amount of material is leaking around the handle connection during use.",
            "Leak",
            "Normal",
            "In progress",
            "Sam Chen",
            3,
        ),
        (
            3,
            "Intermittent operation",
            "Pump starts intermittently. The issue appears after several minutes of operation.",
            "Will not start",
            "Normal",
            "Awaiting parts",
            "Alex Morgan",
            22,
        ),
        (
            1,
            "Pressure drops during spraying",
            "Pressure decreases when the trigger is held. Customer reports material returning through the return tube in spray position.",
            "Low pressure",
            "High",
            "New",
            "Unassigned",
            5,
        ),
        (
            5,
            "Uneven spray pattern",
            "Pattern has become uneven. Please inspect before the next scheduled job.",
            "Spray pattern",
            "Normal",
            "New",
            "Unassigned",
            8,
        ),
        (
            4,
            "Scheduled filter service",
            "Routine filter inspection and service completed.",
            "Maintenance",
            "Low",
            "Closed",
            "Jordan Patel",
            46,
        ),
    ]
    for i, (idx, title, desc, cat, priority, status, tech, hours) in enumerate(reqs):
        db.add(
            ServiceRequest(
                workspace_id=w.id,
                asset_id=assets[idx].id,
                code=f"SR-{26041 + i}",
                title=title,
                description=desc,
                category=cat,
                priority=priority,
                status=status,
                technician=tech,
                contact={
                    "name": assets[idx].customer,
                    "email": "customer@example.test",
                    "phone": "403-555-0100",
                },
                created_at=now() - timedelta(hours=hours),
                updated_at=now() - timedelta(hours=hours),
            )
        )
    db.commit()
    return w
