from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class TelemetryReading(Base):
    __tablename__ = "telemetry_readings"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[str] = mapped_column(String(100), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, index=True)
    vibration_mm_s: Mapped[float] = mapped_column(Float)
    volumetric_flow_m3_h: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    pressure_bar: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="simulator")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="running")
    severity: Mapped[str] = mapped_column(String(32))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    final_report: Mapped[str | None] = mapped_column(Text, nullable=True)
