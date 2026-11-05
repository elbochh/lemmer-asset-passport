"""Load the owner's fictional v3 workbook into a new isolated demo workspace."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .database import Asset, Event, KnowledgeCase, ServiceRequest
from .expansion_models import (
    AssetOwner,
    ComponentRecord,
    Customer,
    PortalUser,
)
from .seed import TECHNICIANS


DATA_PATH = Path(__file__).with_name("data") / "owner_synthetic_v3.json"
SOURCE = "Owner-provided synthetic test data; not technically verified"


def dataset():
    return json.loads(DATA_PATH.read_text())


def test_parts(model):
    """Fictional part identifiers supplied for this model in the test workbook."""
    result = {}
    for row in dataset()["troubleshooting"]:
        if row["equipment_model"] == model and row["part_number"]:
            result[row["part_number"]] = row["part_description"]
    return result


def _instant(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def seed_owner_dataset(db, workspace):
    """Seed customers, equipment, history and test evidence without approving it."""
    data = dataset()
    customers = {}
    for row in data["customers"]:
        customer = Customer(
            workspace_id=workspace.id,
            name=row["company_name"],
            email=row["email"] or "",
            phone=row["phone"] or "",
            sap_customer_code=row["customer_id"],
            kind="customer",
            created_at=_instant("2026-10-08"),
        )
        db.add(customer)
        db.flush()
        customers[row["customer_id"]] = customer
        db.add(
            PortalUser(
                workspace_id=workspace.id,
                customer_id=customer.id,
                # PortalUser.email is globally unique across isolated demo
                # workspaces. Preserve the workbook address on Customer and use
                # a generated .invalid identifier for persona switching.
                email=f"{customer.id}@example.invalid",
                demo=True,
            )
        )

    assets = {}
    for row in data["assets"]:
        customer = customers[row["customer_id"]]
        asset = Asset(
            workspace_id=workspace.id,
            code=row["asset_id"],
            name=f'{row["equipment_model"]} test asset',
            model=row["equipment_model"],
            product_number="",
            manufacturer=row["manufacturer"],
            serial=row["serial_number"],
            customer=customer.name,
            location=row["location"],
            condition=(
                "Needs service"
                if row["operating_status"] == "Awaiting service"
                else "Operational"
            ),
            image="/images/equipment.svg",
            created_at=_instant(row["commissioning_date"]),
        )
        db.add(asset)
        db.flush()
        assets[row["asset_id"]] = asset
        db.add(
            AssetOwner(
                id=asset.id,
                workspace_id=workspace.id,
                customer_id=customer.id,
                kind="equipment",
                product_sku="",
                profile={
                    "source_asset_id": row["asset_id"],
                    "qr_value": row["qr_barcode_value"],
                    "equipment_type": row["equipment_type"],
                    "build_date": row["build_date"],
                    "commissioning_date": row["commissioning_date"],
                    "data_status": row["data_status"],
                },
            )
        )

    records = {row["record_id"]: row for row in data["troubleshooting"]}
    customer_by_asset = {
        row["asset_id"]: customers[row["customer_id"]] for row in data["assets"]
    }
    for row in data["troubleshooting"]:
        db.add(
            KnowledgeCase(
                workspace_id=workspace.id,
                code=row["record_id"],
                model=row["equipment_model"],
                symptom=row["symptom"],
                diagnosis=row["possible_issue"],
                repair=row["solution"],
                parts=[row["part_number"]] if row["part_number"] else [],
                test=row["diagnostic_check"] + " " + row["repair_verification"],
                outcome="Synthetic test scenario",
                source=(
                    f'{SOURCE}; {row["manual_document_reference"]}; '
                    f'version {row["record_version"]}'
                ),
                created_at=_instant("2026-10-08"),
            )
        )

    usage_by_service = {}
    for row in data["parts_used"]:
        usage_by_service.setdefault(row["service_id"], []).append(row)

    requests = {}
    for index, row in enumerate(data["service_history"]):
        asset = assets[row["asset_id"]]
        customer = customer_by_asset[row["asset_id"]]
        record = records[row["troubleshooting_record_id"]]
        technician = TECHNICIANS[index % len(TECHNICIANS)]
        pending = row["outcome"] == "Pending verification"
        request = ServiceRequest(
            workspace_id=workspace.id,
            asset_id=asset.id,
            code=row["service_id"],
            title=row["reported_symptom"],
            description=(
                f'{row["reported_symptom"]}. Source record '
                f'{row["troubleshooting_record_id"]}; fictional test event.'
            ),
            category=record["issue_category"],
            priority="Normal",
            status="In progress" if pending else "Closed",
            operating="Unknown / Not assessed" if pending else "Yes",
            contact={
                "name": customer.name,
                "email": customer.email,
                "phone": customer.phone,
            },
            technician=technician,
            created_at=_instant(row["service_date"]),
            updated_at=_instant(row["service_date"]),
        )
        db.add(request)
        db.flush()
        requests[row["service_id"]] = request
        parts = usage_by_service.get(row["service_id"], [])
        event = Event(
            workspace_id=workspace.id,
            asset_id=asset.id,
            request_id=request.id,
            kind="service",
            title=row["reported_symptom"],
            actor=technician,
            created_at=_instant(row["service_date"]),
            body={
                "symptom": row["reported_symptom"],
                "diagnosis": row["confirmed_cause"],
                "work": row["work_performed"],
                "parts": [x["part_number"] for x in parts],
                "part_usage": [
                    {
                        "id": x["part_usage_id"],
                        "part": x["part_number"],
                        "description": x["part_description"],
                        "quantity": x["quantity"],
                    }
                    for x in parts
                ],
                "test": records[row["troubleshooting_record_id"]][
                    "repair_verification"
                ],
                "outcome": row["outcome"],
                "notes": row["technician_notes"],
                "inspection_date": row["service_date"],
                "next_service_due": row["next_service_due"],
                "source_record_id": row["troubleshooting_record_id"],
                "source_technician_label": row["technician"],
                "source": SOURCE,
            },
        )
        db.add(event)
        db.flush()
        for part in parts:
            db.add(
                ComponentRecord(
                    workspace_id=workspace.id,
                    asset_id=asset.id,
                    part=f'{part["part_number"]} · {part["part_description"]}',
                    installed=row["service_date"],
                    interval_days=None,
                    basis=(
                        "Fictional part-use record from the owner-provided synthetic "
                        "workbook; not a manufacturer lifetime."
                    ),
                    event_id=event.id,
                )
            )

    for row in data["attachments"]:
        db.add(
            Event(
                workspace_id=workspace.id,
                asset_id=assets[row["asset_id"]].id,
                request_id=(
                    requests[row["service_id"]].id if row["service_id"] else None
                ),
                kind="attachment_reference",
                title=f'Synthetic {row["file_type"].lower()} placeholder',
                actor="Dataset import",
                created_at=_instant(row["upload_date"]),
                body={
                    "attachment_id": row["attachment_id"],
                    "placeholder_url": row["photo_document_link"],
                    "description": row["description"],
                    "data_status": row["data_status"],
                    "file_available": False,
                    "source": SOURCE,
                },
            )
        )

    return {"customers": customers, "assets": assets}
