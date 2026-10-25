import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import SessionLocal, get_session, initialize_database
from .events import EventBroker
from .models import Incident, TelemetryReading
from .orchestrator import ReliabilityOrchestrator
from .sandbox import DockerSandbox
from .schemas import IncidentResponse, TelemetryPayload
from .telemetry import TelemetryGenerator

settings = get_settings()
broker = EventBroker()
generator = TelemetryGenerator(SessionLocal, broker, settings.telemetry_interval_seconds)
orchestrator = ReliabilityOrchestrator(settings, broker, DockerSandbox(settings))
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await initialize_database()
    generator.start()
    yield
    await generator.stop()


app = FastAPI(
    title="Autonomous Industrial Site Reliability Agent",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Operator-Token"],
)


async def require_operator_token(x_operator_token: str | None = Header(default=None)) -> None:
    if settings.operator_api_token is None:
        return
    if not x_operator_token:
        raise HTTPException(status_code=401, detail="Operator authorization is required")
    if not secrets.compare_digest(x_operator_token, settings.operator_api_token):
        raise HTTPException(status_code=403, detail="Operator authorization was rejected")


async def execute_incident(incident_id: UUID, telemetry: TelemetryPayload) -> None:
    try:
        result = await orchestrator.run(incident_id, telemetry)
        async with SessionLocal() as session:
            incident = await session.get(Incident, incident_id)
            if incident:
                incident.status = "completed"
                incident.completed_at = datetime.now(UTC)
                incident.final_report = result.get("final_report")
                incident.details = result
                await session.commit()
        await broker.publish(
            "incident.completed",
            {"incident_id": str(incident_id), "report": result.get("final_report", "No final report.")},
        )
    except Exception as error:
        async with SessionLocal() as session:
            incident = await session.get(Incident, incident_id)
            if incident:
                incident.status = "failed"
                incident.completed_at = datetime.now(UTC)
                incident.final_report = str(error)
                await session.commit()
        await broker.publish("incident.failed", {"incident_id": str(incident_id), "error": str(error)})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/telemetry/latest", response_model=list[TelemetryPayload])
async def latest_telemetry(session: AsyncSession = Depends(get_session)) -> list[TelemetryPayload]:
    result = await session.execute(select(TelemetryReading).order_by(TelemetryReading.recorded_at.desc()).limit(20))
    return [
        TelemetryPayload(
            asset_id=row.asset_id,
            vibration_mm_s=row.vibration_mm_s,
            volumetric_flow_m3_h=row.volumetric_flow_m3_h,
            temperature_c=row.temperature_c,
            pressure_bar=row.pressure_bar,
            recorded_at=row.recorded_at,
            source=row.source,
        )
        for row in result.scalars()
    ]


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {
        "incident_id": str(incident.id),
        "asset_id": incident.asset_id,
        "status": incident.status,
        "severity": incident.severity,
        "detected_at": incident.detected_at,
        "completed_at": incident.completed_at,
        "final_report": incident.final_report,
        "details": incident.details,
    }


@app.post("/trigger-crisis", response_model=IncidentResponse, status_code=202)
async def trigger_crisis(
    background_tasks: BackgroundTasks,
    asset_id: str = "PUMP-101A",
    _: None = Depends(require_operator_token),
) -> IncidentResponse:
    telemetry = await generator.inject_crisis(asset_id)
    incident = Incident(
        id=uuid4(),
        asset_id=asset_id,
        status="running",
        severity="critical",
        details={"telemetry": telemetry.model_dump(mode="json")},
    )
    async with SessionLocal() as session:
        session.add(incident)
        await session.commit()
    await broker.publish(
        "incident.created",
        {"incident_id": str(incident.id), "asset_id": asset_id, "severity": "critical"},
    )
    background_tasks.add_task(execute_incident, incident.id, telemetry)
    return IncidentResponse(incident_id=incident.id, status=incident.status)


@app.websocket("/ws/live")
async def live_stream(websocket: WebSocket) -> None:
    allowed_origins = {origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()}
    if websocket.headers.get("origin") not in allowed_origins:
        await websocket.close(code=1008, reason="Untrusted WebSocket origin")
        return
    await broker.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await broker.disconnect(websocket)


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
