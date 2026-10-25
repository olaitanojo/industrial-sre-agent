from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.config import Settings
from app.events import EventBroker
from app.orchestrator import ReliabilityOrchestrator
from app.schemas import SandboxResult, TelemetryPayload


class PassingSandbox:
    async def verify(self, _patch):
        return SandboxResult(passed=True, stdout="verified", exit_code=0, execution_mode="test")


class FailingSandbox:
    def __init__(self):
        self.calls = 0

    async def verify(self, _patch):
        self.calls += 1
        return SandboxResult(passed=False, stderr="test failure", exit_code=1, execution_mode="test")


def crisis_reading() -> TelemetryPayload:
    return TelemetryPayload(
        asset_id="PUMP-101A",
        vibration_mm_s=18.7,
        volumetric_flow_m3_h=51.2,
        temperature_c=132.4,
        pressure_bar=171.8,
        recorded_at=datetime.now(UTC),
        source="test",
    )


@pytest.mark.asyncio
async def test_graph_completes_after_passing_sandbox():
    graph = ReliabilityOrchestrator(Settings(), EventBroker(), PassingSandbox())
    result = await graph.run(uuid4(), crisis_reading())

    assert result["stage"] == "FinalDeploy"
    assert result["verification"]["passed"] is True
    assert "human-approved" in result["final_report"]


@pytest.mark.asyncio
async def test_graph_loops_after_failed_sandbox():
    sandbox = FailingSandbox()
    graph = ReliabilityOrchestrator(Settings(), EventBroker(), sandbox)
    result = await graph.run(uuid4(), crisis_reading())

    assert sandbox.calls == 2
    assert result["attempts"] == 2
    assert result["verification"]["passed"] is False
    assert "no deployment" in result["final_report"]
