# Autonomous Industrial Site Reliability Agent

An air-gapped, cyclic remediation platform for simulated industrial telemetry.

## Run

Install Docker Desktop, then run:

```powershell path=null start=null
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Open `http://localhost:8000`. Select **Trigger Crisis** to insert a severe telemetry anomaly and run the LangGraph remediation cycle. API documentation is at `http://localhost:8000/docs`.

## Security model

The API creates short-lived verification containers through the Docker socket. Each sandbox uses an explicitly selected image with networking disabled, `cap_drop=ALL`, `no-new-privileges`, a read-only root filesystem, no user namespace privileges, a PID/memory/CPU limit, and an execution timeout. The host Docker socket is inherently privileged; deploy this architecture only on a dedicated control-plane host with Docker authorization controls. Never mount production secrets or production infrastructure credentials into this service.

## Test

```powershell path=null start=null
python -m pip install -r backend/requirements.txt
python -m pytest backend/tests -q
```

## Production deployment

The Vercel application is in `frontend/`; the FastAPI control plane remains on a dedicated Linux host. The production Compose override publishes the API only at `127.0.0.1:8000`. Terminate TLS and proxy WebSocket upgrades at the host reverse proxy, with the public backend origin exposed over HTTPS and WSS.

The GitHub Actions workflow is `.github/workflows/deploy.yml`. Configure its protected `production` environment with these repository secrets:

- `VERCEL_TOKEN`, `VERCEL_ORG_ID`, and `VERCEL_PROJECT_ID`: Vercel CLI credentials and linked project identifiers.
- `PRODUCTION_API_URL`: the complete HTTPS backend origin.
- `PRODUCTION_WS_URL`: the complete WSS backend origin.
- `OPERATOR_API_TOKEN`: a high-entropy token shared only by the Vercel server runtime and FastAPI backend.
- `PROD_SSH_HOST`, `PROD_SSH_PORT`, `PROD_SSH_USER`, `PROD_SSH_PRIVATE_KEY`, and `PROD_SSH_KNOWN_HOSTS`: deployment host address, account, private key, and pinned host public key line.
- `PROD_DEPLOY_PATH`: absolute release root owned by the deployment user.
- `PROD_BACKEND_ENV_B64`: the Base64 encoding of the finalized `.env.production` file. It must contain concrete high-entropy database, Redis, operator-token, database URL, and Vercel frontend-origin values; do not commit that file.

The Vercel deployment uses the supported `vercel pull`, `vercel build --prod`, and `vercel deploy --prebuilt --prod` CLI sequence. The workflow intentionally uses the official CLI rather than an unmaintained third-party deploy action.
