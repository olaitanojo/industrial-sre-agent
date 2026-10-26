# Autonomous Industrial Site Reliability Agent

The Autonomous Industrial Site Reliability Agent is a full-stack, cyber-physical reliability simulation platform. It generates refinery-style asset telemetry, detects dangerous operating conditions, runs a cyclic LangGraph remediation workflow, verifies a reversible policy patch inside a restricted Docker sandbox, and streams every stage to a live web dashboard.

It is designed as a **control-plane and decision-support system**. It does not directly control pumps, valves, PLCs, or any physical equipment. Its final output is a human-gated mitigation recommendation; production infrastructure is never mutated automatically.

## What it can do

- Simulate high-frequency industrial measurements for vibration, volumetric flow, temperature, and pressure across multiple assets.
- Persist readings and incidents in TimescaleDB/PostgreSQL, with telemetry stored as a hypertable for time-series queries.
- Inject deterministic severe anomalies through a chaos-engineering endpoint.
- Detect threshold breaches and assemble structured telemetry evidence.
- Run a strict remediation cycle:
  `Idle → AnomalyDetected → RootCauseAnalysis → MitigationDrafting → SandboxedVerification → FinalDeploy`
- Loop from sandbox verification back to mitigation drafting when verification fails, with a bounded retry count.
- Produce Pydantic-validated agent thoughts, mitigation patches, sandbox results, and incident records.
- Validate remediation patches inside a short-lived Docker container with networking disabled, a read-only root filesystem, dropped Linux capabilities, resource limits, and captured stdout/stderr.
- Stream telemetry, graph transitions, agent reasoning records, incident completion, and sandbox logs over WebSockets.
- Present a Next.js dashboard with live metrics, a graph execution matrix, incident status, sandbox output, and a protected **Trigger Crisis** action.
## FDE and cyber-physical positioning

This project demonstrates the core shape of a forward-deployed reliability platform for industrial environments:

- **Petroleum and process context:** vibration, flow, temperature, and pressure are representative measurements for pumps, compressors, heaters, pipelines, and process units.
- **Infrastructure context:** the platform treats telemetry anomalies as operational incidents, produces an auditable mitigation plan, validates it in a constrained execution environment, and leaves real production changes behind a human approval boundary.
- **Scaling context:** TimescaleDB provides time-series storage, Redis supports control-plane expansion, Docker Compose packages the services, and the Vercel/Linux split separates the user interface from the privileged sandbox host.
- **Workflow context:** LangGraph models specialized roles for detection, analysis, mitigation, verification, and final recommendation. The current implementation is deterministic and role-structured; a future integration can replace individual nodes with independently prompted LLM agents and domain-specific tools when true multi-model or multi-agent autonomy is required.

## Industries and example operators

The architecture is applicable wherever a physical asset fleet emits continuous telemetry and remediation must be safe, reviewable, and operationally traceable. The companies below are examples of potential users, **not customers, partners, or endorsements**.

| Industry | Example operational use | Representative operators and companies |
| --- | --- | --- |
| Upstream oil and gas | Artificial-lift pump health, compressor vibration, wellsite pressure anomalies | SLB, Halliburton, Baker Hughes, Chevron, ExxonMobil, Shell, Saudi Aramco |
| Refining and petrochemicals | Crude-unit pump degradation, heater excursions, compressor surge precursors, utility-system reliability | Phillips 66, Valero, bp, Shell, Dow, BASF, SABIC |
| LNG and midstream | Pipeline throughput loss, gas-compression reliability, cryogenic process alarms | Cheniere, Williams, Kinder Morgan, Enbridge, Equinor, QatarEnergy |
| Power generation and utilities | Turbine auxiliary systems, boiler feedwater pumps, transformer thermal alarms, grid-support assets | NextEra Energy, Duke Energy, National Grid, EDF, Siemens Energy, GE Vernova |
| Mining and metals | Mill and slurry-pump reliability, conveyor and crusher vibration, plant water systems | BHP, Rio Tinto, Anglo American, Freeport-McMoRan, Vale |
| Water, wastewater, and chemicals | Treatment-train pumps, dosing skids, filtration systems, pressure and flow excursions | Veolia, Suez, Xylem, Ecolab, Air Liquide |
| Manufacturing and industrial automation | Motor, compressor, robotic-cell, and utility telemetry with controlled maintenance recommendations | Siemens, Schneider Electric, Honeywell, ABB, Rockwell Automation |

## System architecture

```text
Next.js dashboard on Vercel
        │ HTTPS + WSS
        ▼
Nginx TLS reverse proxy on dedicated Linux host
        │ loopback only
        ▼
FastAPI control plane ──────── Redis
        │
        ├── TimescaleDB/PostgreSQL telemetry and incidents
        ├── async telemetry generator
        ├── LangGraph remediation workflow
        └── Docker SDK sandbox
              └── networkless, unprivileged verification container
```

The production API is published only to `127.0.0.1:8000`; Nginx terminates TLS and upgrades WebSocket connections. PostgreSQL and Redis remain on an internal Docker network. The API alone also joins an ingress bridge so its loopback binding can be reached by Nginx without exposing data services.

## Remediation workflow

1. **Idle** accepts an incident into the control-plane workflow.
2. **AnomalyDetected** compares telemetry against configured vibration, temperature, pressure, and flow thresholds.
3. **RootCauseAnalysis** produces a structured failure hypothesis using the supplied evidence.
4. **MitigationDrafting** builds a reversible infrastructure policy patch and rollback plan.
5. **SandboxedVerification** sends that patch to the isolated Docker verifier.
6. **FinalDeploy** records one of two outcomes:
   - verification passed and the mitigation is ready for **human-approved** deployment;
   - verification failed after retries and the incident must be escalated.

The current sample root-cause model identifies concurrent high vibration, heat, pressure rise, and flow collapse as a pump mechanical-degradation pattern. It is deterministic simulation logic, not a replacement for a qualified process-safety analysis.

## Sandbox isolation

The verifier does not mount the application checkout or production credentials into its test container. Each verification container uses:

- `network_disabled=true`
- read-only root filesystem
- user `65534:65534`
- `cap_drop=ALL`
- `no-new-privileges`
- PID, CPU, memory, and input-size limits
- a configurable wall-clock timeout

The control plane needs Docker socket access to create those containers. A Docker socket is host-privileged, so deploy this component only on a dedicated, access-controlled host. The sandbox restrictions reduce patch execution risk but do not make a Docker-socket workload safe for a shared multi-tenant machine.

## Repository layout

```text
backend/                    FastAPI application, telemetry, LangGraph, and sandbox
backend/app/static/         Development dashboard served by FastAPI
frontend/                   Production Next.js dashboard deployed to Vercel
ops/setup-server.sh         Ubuntu server bootstrap: Docker, UFW, Nginx, and Certbot
docker-compose.yml          Shared application and data-service definition
docker-compose.dev.yml      Local port exposure override
docker-compose.prod.yml     Production hardening and loopback-only API publication
.github/workflows/deploy.yml  Vercel and Linux-host deployment workflow
```

## Local development

### Prerequisites

- Docker Desktop with Docker Compose v2
- Python 3.12+ for local backend tests
- Node.js 20+ for the Next.js frontend

### Start the simulation

```powershell path=null start=null
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Open:

- Dashboard: `http://localhost:8000`
- FastAPI OpenAPI documentation: `http://localhost:8000/docs`
- Health endpoint: `http://localhost:8000/health`

Development intentionally leaves the operator token unset so the local dashboard can exercise the crisis route. Production requires the operator token.

### Trigger a simulated crisis

From the dashboard, select **Trigger Crisis**. The system inserts a critical `PUMP-101A` reading, creates an incident, publishes WebSocket events, runs the graph, and stores the outcome.

For local API testing:

```powershell path=null start=null
Invoke-WebRequest -UseBasicParsing -Method Post http://localhost:8000/trigger-crisis
```

## API and live-stream surface

| Endpoint | Purpose | Production access |
| --- | --- | --- |
| `GET /health` | Liveness response: `{"status":"ok"}` | Public through Nginx |
| `GET /api/telemetry/latest` | Most recent telemetry readings | CORS limited to the configured frontend origin |
| `GET /api/incidents/{incident_id}` | Incident state, structured workflow output, and final report | Public through Nginx |
| `POST /trigger-crisis` | Creates a critical simulated incident | Requires `X-Operator-Token` in production |
| `WS /ws/live` | Telemetry, graph, sandbox, and incident event stream | Validates the configured frontend `Origin` |

The Next.js route `/api/trigger-crisis` holds the operator token server-side and proxies the request to FastAPI. The browser never receives that token.

## Tests

Create a Python environment and run the workflow tests:

```powershell path=null start=null
python -m pip install -r backend/requirements.txt
python -m pytest backend/tests -q
```

The tests cover both the happy path and sandbox-failure retry cycle.

Validate the production frontend:

```powershell path=null start=null
cd frontend
npm ci
npm run lint
npm run build
npm audit --omit=dev --audit-level=high
```

## Production deployment

Current production endpoints:

- Frontend: `https://industrial-sre-agent.vercel.app`
- API: `https://api.deenojo.dev`
- WebSocket: `wss://api.deenojo.dev/ws/live`

The GitHub Actions workflow deploys on pushes to `main` or `master`:

1. It lints, builds, and deploys the Next.js artifact to Vercel with the official Vercel CLI.
2. It packages the backend, verifies the release checksum on the Linux host, recreates the hardened Compose stack, waits for the API health check, and prunes dangling images.

The workflow uses a protected GitHub `production` environment. Required secret names are:

- `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`
- `PRODUCTION_API_URL`, `PRODUCTION_WS_URL`, `OPERATOR_API_TOKEN`
- `PROD_SSH_HOST`, `PROD_SSH_PORT`, `PROD_SSH_USER`, `PROD_SSH_PRIVATE_KEY`, `PROD_SSH_KNOWN_HOSTS`
- `PROD_DEPLOY_PATH`
- `PROD_BACKEND_ENV_B64`

`PROD_BACKEND_ENV_B64` is a Base64-encoded finalized production environment file. It contains the generated PostgreSQL, Redis, and operator secrets and must never be committed.

### Ubuntu host bootstrap

`ops/setup-server.sh` prepares an Ubuntu 22.04 or 24.04 host by installing Docker Engine and Compose v2 from Docker's official repository, configuring UFW, setting Docker DNS, installing Nginx, configuring WebSocket proxy timeouts, requesting a Let’s Encrypt certificate, and enabling renewal.

```bash path=null start=null
sudo ./ops/setup-server.sh api.example.com operations@example.com ubuntu
```

Use a real fully-qualified domain that already resolves to the host’s public IP. The script fails safely before certificate issuance if public DNS is not ready.

## Operational and security notes

- The telemetry source is simulated. Connect real OT/ICS data only through a reviewed, read-only integration boundary.
- The current agent creates recommendations and patches; it does not actuate a physical process.
- Keep the backend host dedicated because Docker socket access is powerful.
- Use a monitored email address for the Let’s Encrypt registration contact.
- The current GitHub-hosted SSH deployment model requires inbound SSH from GitHub runners. A future self-hosted runner or AWS Systems Manager design can eliminate that public SSH requirement.
- Rotate GitHub, Vercel, database, Redis, operator, and SSH credentials according to your organization’s incident-response policy.
