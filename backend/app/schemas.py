from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GraphStage(StrEnum):
    IDLE = "Idle"
    ANOMALY_DETECTED = "AnomalyDetected"
    ROOT_CAUSE_ANALYSIS = "RootCauseAnalysis"
    MITIGATION_DRAFTING = "MitigationDrafting"
    SANDBOXED_VERIFICATION = "SandboxedVerification"
    FINAL_DEPLOY = "FinalDeploy"


class TelemetryPayload(BaseModel):
    asset_id: str = Field(min_length=1, max_length=100)
    vibration_mm_s: float = Field(ge=0)
    volumetric_flow_m3_h: float = Field(ge=0)
    temperature_c: float = Field(ge=-100, le=1000)
    pressure_bar: float = Field(ge=0)
    recorded_at: datetime
    source: str = "simulator"


class AgentThought(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: GraphStage
    summary: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class MitigationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch_id: str
    target: str
    unified_diff: str
    test_command: str
    rollback_plan: str


class SandboxResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: int = 0
    execution_mode: str


class IncidentResponse(BaseModel):
    incident_id: UUID
    status: str


class EventMessage(BaseModel):
    event: str
    timestamp: datetime
    payload: dict
