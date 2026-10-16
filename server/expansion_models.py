"""Additive tables for ownership, customer access, parts and vehicle visits."""

from sqlalchemy import String, Text, JSON, DateTime, ForeignKey, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, uid, now


class Customer(Base):
    __tablename__ = "customer_accounts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    sap_customer_code: Mapped[str] = mapped_column(String, default="")
    kind: Mapped[str] = mapped_column(String, default="customer")
    invite_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)


class PortalUser(Base):
    __tablename__ = "portal_users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer_accounts.id"))
    email: Mapped[str] = mapped_column(String, unique=True)
    password: Mapped[str | None] = mapped_column(String, nullable=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class AssetOwner(Base):
    __tablename__ = "asset_owners"
    id: Mapped[str] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customer_accounts.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String, default="equipment")
    product_sku: Mapped[str] = mapped_column(String, default="")
    profile: Mapped[dict] = mapped_column(JSON, default=dict)


class PartOrder(Base):
    __tablename__ = "part_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customer_accounts.id"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"))
    request_id: Mapped[str | None] = mapped_column(
        ForeignKey("service_requests.id"), nullable=True
    )
    part: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer)
    problem: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="Requested")
    notes: Mapped[str] = mapped_column(Text, default="")
    submission_id: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)


class Inspection(Base):
    __tablename__ = "vehicle_visits"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="Checked in")
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)


class ComponentRecord(Base):
    __tablename__ = "component_installations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    part: Mapped[str] = mapped_column(String)
    installed: Mapped[str] = mapped_column(String)
    interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    basis: Mapped[str] = mapped_column(Text)
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("passport_events.id"), nullable=True
    )


class GuidanceCache(Base):
    __tablename__ = "guidance_cache"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)


class SchemaVersion(Base):
    __tablename__ = "schema_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    applied_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)


class InspectionMedia(Base):
    __tablename__ = "inspection_media"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    visit_id: Mapped[str] = mapped_column(ForeignKey("vehicle_visits.id"), index=True)
    kind: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    payload: Mapped[bytes] = mapped_column(__import__("sqlalchemy").LargeBinary)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)
