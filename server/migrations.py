"""Additive demo migrations. Existing asset IDs and service history are preserved."""

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from .database import Base, engine
from .expansion_models import SchemaVersion
from . import operations_models


def migrate():
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(7771090)"))
        # Additive schema plus an identity-label backfill. Physical asset IDs and histories are preserved.
        Base.metadata.create_all(connection)
        connection.execute(
            text(
                "ALTER TABLE assets ADD COLUMN IF NOT EXISTS product_number VARCHAR NOT NULL DEFAULT ''"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE customer_accounts ADD COLUMN IF NOT EXISTS sap_customer_code VARCHAR NOT NULL DEFAULT ''"
            )
        )
        from .identity import model_name
        from .catalog import BY_SKU

        for sku in BY_SKU:
            connection.execute(
                text(
                    "UPDATE assets SET product_number=:sku, model=:model WHERE model=:sku AND product_number='' AND lower(manufacturer)='lemmer'"
                ),
                {"sku": sku, "model": model_name(sku)},
            )
        # Retire the external repair role without deleting owners or histories.
        # Open self-assigned visits return to reception; completed records stay intact.
        connection.execute(
            text(
                """
            UPDATE service_requests AS r
            SET technician='Unassigned', category='Customer symptom',
                version=r.version+1, updated_at=now()
            FROM asset_owners AS o, customer_accounts AS c
            WHERE o.id=r.asset_id AND c.id=o.customer_id
              AND c.kind='manufacturer' AND r.technician=c.name
              AND r.category='Organization self-service' AND r.status!='Closed'
        """
            )
        )
        connection.execute(
            text(
                "UPDATE customer_accounts SET kind='customer' WHERE kind='manufacturer'"
            )
        )
        # Database-enforced append-only audit, including accidental application writes.
        connection.execute(
            text(
                """CREATE OR REPLACE FUNCTION prevent_audit_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Audit entries are append-only'; END $$"""
            )
        )
        connection.execute(
            text("DROP TRIGGER IF EXISTS immutable_audit ON audit_entries")
        )
        connection.execute(
            text(
                "CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON audit_entries FOR EACH ROW EXECUTE FUNCTION prevent_audit_change()"
            )
        )
        for version in [
            "002-ownership-and-vehicles",
            "003-inspection-evidence",
            "004-calgary-operations",
            "005-retire-organization-repair-role",
        ]:
            connection.execute(
                insert(SchemaVersion)
                .values(id=version)
                .on_conflict_do_nothing(index_elements=["id"])
            )
