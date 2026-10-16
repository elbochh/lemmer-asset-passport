import os
from datetime import datetime, timezone
from uuid import uuid4
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Integer,
    UniqueConstraint,
    LargeBinary,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

load_dotenv()
URL = os.getenv("DATABASE_URL", "postgresql+psycopg://localhost:55432/lemmer_demo")
engine = create_engine(URL, pool_pre_ping=True, pool_size=3, max_overflow=2)
Session = sessionmaker(engine, expire_on_commit=False)


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    share: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("workspace_id", "code"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    code: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    product_number: Mapped[str] = mapped_column(String, default="")
    manufacturer: Mapped[str] = mapped_column(String, default="Lemmer")
    serial: Mapped[str] = mapped_column(String)
    customer: Mapped[str] = mapped_column(String)
    location: Mapped[str] = mapped_column(String)
    condition: Mapped[str] = mapped_column(String, default="Operational")
    image: Mapped[str] = mapped_column(String, default="/images/l-1095.png")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    __table_args__ = (UniqueConstraint("workspace_id", "code"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    code: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String)
    priority: Mapped[str] = mapped_column(String, default="Normal")
    status: Mapped[str] = mapped_column(String, default="New")
    operating: Mapped[str] = mapped_column(String, default="No")
    contact: Mapped[dict] = mapped_column(JSON, default=dict)
    technician: Mapped[str] = mapped_column(String, default="Unassigned")
    draft: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Event(Base):
    __tablename__ = "passport_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    request_id: Mapped[str | None] = mapped_column(
        ForeignKey("service_requests.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String, default="service")
    title: Mapped[str] = mapped_column(String)
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    actor: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class KnowledgeCase(Base):
    __tablename__ = "knowledge_cases"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    code: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    symptom: Mapped[str] = mapped_column(Text)
    diagnosis: Mapped[str] = mapped_column(Text)
    repair: Mapped[str] = mapped_column(Text)
    parts: Mapped[list] = mapped_column(JSON, default=list)
    test: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, default="Synthetic demonstration case")
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("passport_events.id"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AIRun(Base):
    __tablename__ = "ai_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    request_id: Mapped[str | None] = mapped_column(
        ForeignKey("service_requests.id"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String, default="C")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("service_requests.id"))
    subject: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    recipient: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Embedding(Base):
    __tablename__ = "embeddings"
    content_hash: Mapped[str] = mapped_column(String, primary_key=True)
    values: Mapped[list] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String, default="gemini-embedding-001")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IntakeDocument(Base):
    __tablename__ = "intake_documents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    request_id: Mapped[str | None] = mapped_column(
        ForeignKey("service_requests.id"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    actor: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GuidanceJob(Base):
    __tablename__ = "guidance_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("service_requests.id"), unique=True
    )
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    message: Mapped[str] = mapped_column(
        Text, default="Preparing guidance automatically."
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("ai_runs.id"), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
