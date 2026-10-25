import asyncio
import random
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker

from .events import EventBroker
from .models import TelemetryReading
from .schemas import TelemetryPayload


class TelemetryGenerator:
    def __init__(self, session_factory: async_sessionmaker, broker: EventBroker, interval: float) -> None:
        self._sessions = session_factory
        self._broker = broker
        self._interval = interval
        self._assets = ("PUMP-101A", "PUMP-101B", "CRUDE-HEATER-201", "COMPRESSOR-301")
        self._task: asyncio.Task[None] | None = None

    def _normal_reading(self, asset_id: str) -> TelemetryPayload:
        return TelemetryPayload(
            asset_id=asset_id,
            vibration_mm_s=round(random.normalvariate(3.2, 0.45), 2),
            volumetric_flow_m3_h=round(random.normalvariate(102.0, 4.0), 2),
            temperature_c=round(random.normalvariate(78.0, 2.5), 2),
            pressure_bar=round(random.normalvariate(98.0, 3.0), 2),
            recorded_at=datetime.now(UTC),
        )

    async def store(self, reading: TelemetryPayload) -> None:
        async with self._sessions() as session:
            session.add(TelemetryReading(**reading.model_dump()))
            await session.commit()
        await self._broker.publish("telemetry.reading", reading.model_dump(mode="json"))

    async def inject_crisis(self, asset_id: str = "PUMP-101A") -> TelemetryPayload:
        reading = TelemetryPayload(
            asset_id=asset_id,
            vibration_mm_s=18.7,
            volumetric_flow_m3_h=51.2,
            temperature_c=132.4,
            pressure_bar=171.8,
            recorded_at=datetime.now(UTC),
            source="chaos-engineering",
        )
        await self.store(reading)
        await self._broker.publish("telemetry.crisis_injected", reading.model_dump(mode="json"))
        return reading

    async def _run(self) -> None:
        while True:
            for asset_id in self._assets:
                await self.store(self._normal_reading(asset_id))
            await asyncio.sleep(self._interval)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="telemetry-generator")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
