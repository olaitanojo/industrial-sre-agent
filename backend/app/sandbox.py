import asyncio
import time

import docker
from docker.errors import DockerException

from .config import Settings
from .schemas import MitigationPatch, SandboxResult


class DockerSandbox:
    """Runs an immutable, networkless verification container for a drafted patch."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def verify(self, patch: MitigationPatch) -> SandboxResult:
        if not self._settings.sandbox_enabled:
            return SandboxResult(passed=False, stderr="Sandbox disabled by configuration.", execution_mode="disabled")
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._verify_sync, patch),
                timeout=self._settings.sandbox_timeout_seconds,
            )
        except TimeoutError:
            return SandboxResult(
                passed=False,
                stderr=f"Sandbox exceeded {self._settings.sandbox_timeout_seconds} seconds.",
                execution_mode="timeout",
            )

    def _verify_sync(self, patch: MitigationPatch) -> SandboxResult:
        started = time.perf_counter()
        if len(patch.unified_diff) > 32_768:
            return SandboxResult(passed=False, stderr="Patch exceeds sandbox input limit.", execution_mode="docker")
        script = (
            "import os\n"
            "patch = os.environ['PATCH_CONTENT']\n"
            "assert patch.startswith('--- '), 'patch lacks unified-diff header'\n"
            "assert 'systemctl' not in patch, 'host service mutation is prohibited'\n"
            "assert 'rm -rf' not in patch, 'destructive command is prohibited'\n"
            "print('Policy and patch syntax checks passed')\n"
        )
        try:
            client = docker.from_env()
            logs = client.containers.run(
                image=self._settings.sandbox_image,
                command=["python", "-c", script],
                network_disabled=True,
                read_only=True,
                user="65534:65534",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                pids_limit=32,
                mem_limit="128m",
                nano_cpus=250_000_000,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=16m"},
                environment={"PATCH_CONTENT": patch.unified_diff},
                detach=False,
                remove=True,
                stdout=True,
                stderr=True,
            )
            stdout = logs.decode("utf-8", errors="replace")
            return SandboxResult(
                passed=True,
                stdout=stdout,
                exit_code=0,
                duration_ms=int((time.perf_counter() - started) * 1000),
                execution_mode="docker",
            )
        except DockerException as error:
            return SandboxResult(
                passed=False,
                stderr=f"Docker sandbox unavailable: {error}",
                exit_code=None,
                duration_ms=int((time.perf_counter() - started) * 1000),
                execution_mode="unavailable",
            )
        except Exception as error:
            return SandboxResult(
                passed=False,
                stderr=str(error),
                exit_code=1,
                duration_ms=int((time.perf_counter() - started) * 1000),
                execution_mode="docker",
            )
