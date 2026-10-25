from collections.abc import Awaitable, Callable
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from .config import Settings
from .events import EventBroker
from .sandbox import DockerSandbox
from .schemas import AgentThought, GraphStage, MitigationPatch, SandboxResult, TelemetryPayload

ANOMALY_PROMPT = "Classify telemetry threshold breaches and return structured evidence only."
RCA_PROMPT = "Identify the lowest-risk physical failure hypothesis using the supplied telemetry evidence."
MITIGATION_PROMPT = "Draft a reversible infrastructure policy patch; do not perform direct asset control."
VERIFICATION_PROMPT = "Verify the proposed patch only in a network-isolated sandbox and return captured runtime results."
DEPLOY_PROMPT = "Record an approved, human-gated deployment recommendation; never mutate production systems."


class ReliabilityState(TypedDict, total=False):
    incident_id: str
    telemetry: dict
    stage: str
    thoughts: list[dict]
    patch: dict
    verification: dict
    attempts: int
    final_report: str


class ReliabilityOrchestrator:
    def __init__(self, settings: Settings, broker: EventBroker, sandbox: DockerSandbox) -> None:
        self._settings = settings
        self._broker = broker
        self._sandbox = sandbox
        self._graph = self._build_graph()

    async def _transition(self, stage: GraphStage, state: ReliabilityState, thought: AgentThought) -> dict:
        await self._broker.publish(
            "graph.transition",
            {"incident_id": state["incident_id"], "stage": stage.value, "thought": thought.model_dump(mode="json")},
        )
        return {"stage": stage.value, "thoughts": [*state.get("thoughts", []), thought.model_dump(mode="json")]}

    async def idle(self, state: ReliabilityState) -> dict:
        return await self._transition(
            GraphStage.IDLE,
            state,
            AgentThought(stage=GraphStage.IDLE, summary="Incident accepted by control-plane workflow.", confidence=1.0),
        )

    async def anomaly_detected(self, state: ReliabilityState) -> dict:
        t = TelemetryPayload.model_validate(state["telemetry"])
        breaches = []
        if t.vibration_mm_s >= self._settings.anomaly_vibration_threshold:
            breaches.append(f"vibration {t.vibration_mm_s} mm/s exceeds {self._settings.anomaly_vibration_threshold}")
        if t.temperature_c >= self._settings.anomaly_temperature_threshold:
            breaches.append(f"temperature {t.temperature_c} C exceeds {self._settings.anomaly_temperature_threshold}")
        if t.pressure_bar >= self._settings.anomaly_pressure_threshold:
            breaches.append(f"pressure {t.pressure_bar} bar exceeds {self._settings.anomaly_pressure_threshold}")
        if t.volumetric_flow_m3_h <= self._settings.anomaly_flow_min_threshold:
            breaches.append(f"flow {t.volumetric_flow_m3_h} m3/h below {self._settings.anomaly_flow_min_threshold}")
        return await self._transition(
            GraphStage.ANOMALY_DETECTED,
            state,
            AgentThought(stage=GraphStage.ANOMALY_DETECTED, summary=ANOMALY_PROMPT, evidence=breaches, confidence=0.98),
        )

    async def root_cause_analysis(self, state: ReliabilityState) -> dict:
        return await self._transition(
            GraphStage.ROOT_CAUSE_ANALYSIS,
            state,
            AgentThought(
                stage=GraphStage.ROOT_CAUSE_ANALYSIS,
                summary=RCA_PROMPT,
                evidence=["Concurrent vibration, heat, and pressure rise with flow collapse indicates pump mechanical degradation."],
                confidence=0.86,
            ),
        )

    async def mitigation_drafting(self, state: ReliabilityState) -> dict:
        attempt = state.get("attempts", 0) + 1
        patch = MitigationPatch(
            patch_id=f"pump-protection-v{attempt}",
            target="control-plane/pump-protection-policy.yaml",
            unified_diff=(
                "--- a/control-plane/pump-protection-policy.yaml\n"
                "+++ b/control-plane/pump-protection-policy.yaml\n"
                "@@ -3,3 +3,5 @@\n"
                " safeguards:\n"
                "+  high_vibration_trip_mm_s: 11.0\n"
                "+  high_temperature_alarm_c: 115.0\n"
                "+  require_human_approval: true\n"
            ),
            test_command="python -m pytest tests/test_pump_protection.py -q",
            rollback_plan="Revert this policy revision and retain manual approval gating.",
        )
        update = await self._transition(
            GraphStage.MITIGATION_DRAFTING,
            state,
            AgentThought(stage=GraphStage.MITIGATION_DRAFTING, summary=MITIGATION_PROMPT, evidence=[patch.patch_id], confidence=0.91),
        )
        update.update({"patch": patch.model_dump(), "attempts": attempt})
        return update

    async def sandboxed_verification(self, state: ReliabilityState) -> dict:
        result = await self._sandbox.verify(MitigationPatch.model_validate(state["patch"]))
        await self._broker.publish(
            "sandbox.output",
            {"incident_id": state["incident_id"], "result": result.model_dump(mode="json")},
        )
        update = await self._transition(
            GraphStage.SANDBOXED_VERIFICATION,
            state,
            AgentThought(
                stage=GraphStage.SANDBOXED_VERIFICATION,
                summary=VERIFICATION_PROMPT,
                evidence=[result.stderr or result.stdout or "No sandbox output."],
                confidence=1.0 if result.passed else 0.0,
            ),
        )
        update["verification"] = result.model_dump()
        return update

    def verification_router(self, state: ReliabilityState) -> str:
        result = SandboxResult.model_validate(state["verification"])
        if result.passed or state.get("attempts", 0) >= 2:
            return "final_deploy"
        return "mitigation_drafting"

    async def final_deploy(self, state: ReliabilityState) -> dict:
        passed = SandboxResult.model_validate(state["verification"]).passed
        report = (
            "Verification passed. Mitigation is ready for human-approved deployment."
            if passed
            else "Verification did not pass after two attempts. Escalate to an on-call engineer; no deployment was performed."
        )
        update = await self._transition(
            GraphStage.FINAL_DEPLOY,
            state,
            AgentThought(stage=GraphStage.FINAL_DEPLOY, summary=DEPLOY_PROMPT, evidence=[report], confidence=1.0),
        )
        update["final_report"] = report
        return update

    def _build_graph(self):
        graph = StateGraph(ReliabilityState)
        graph.add_node("idle", self.idle)
        graph.add_node("anomaly_detected", self.anomaly_detected)
        graph.add_node("root_cause_analysis", self.root_cause_analysis)
        graph.add_node("mitigation_drafting", self.mitigation_drafting)
        graph.add_node("sandboxed_verification", self.sandboxed_verification)
        graph.add_node("final_deploy", self.final_deploy)
        graph.add_edge(START, "idle")
        graph.add_edge("idle", "anomaly_detected")
        graph.add_edge("anomaly_detected", "root_cause_analysis")
        graph.add_edge("root_cause_analysis", "mitigation_drafting")
        graph.add_edge("mitigation_drafting", "sandboxed_verification")
        graph.add_conditional_edges(
            "sandboxed_verification",
            self.verification_router,
            {"mitigation_drafting": "mitigation_drafting", "final_deploy": "final_deploy"},
        )
        graph.add_edge("final_deploy", END)
        return graph.compile()

    async def run(self, incident_id: UUID, telemetry: TelemetryPayload) -> ReliabilityState:
        return await self._graph.ainvoke(
            {"incident_id": str(incident_id), "telemetry": telemetry.model_dump(mode="json"), "attempts": 0}
        )
