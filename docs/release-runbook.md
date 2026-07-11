# botvpk production release runbook

## Local preproduction

The isolated stand uses synthetic users, dedicated volumes, dry-run bots and test-only secrets:

```bash
docker compose --project-name botvpk-preprod \
  --env-file .env.preprod.example \
  -f docker-compose.yml -f docker-compose.preprod.yml up --build
```

Open `http://127.0.0.1:8082`. Synthetic website accounts use Telegram IDs `990000001` (participant), `990000002` (commander) and `990000003` (super admin); the password is `Preprod!12345`.

Run the isolated backup/restore check before release:

```bash
bash scripts/verify-backup-restore.sh
```

The optional load checks require a valid `vpk_session` value from the preproduction browser:

```bash
VPK_SESSION=... python scripts/load_api.py
VPK_SESSION=... python scripts/load_sse.py
```

## One-time server bootstrap

Run `bootstrap-server.sh` only on a new server. It creates `/opt/botvpk/shared/.env`, maintenance files and release directories. Fill `SITE_URL`, `MINI_APP_URL`, VK, Web Push and Sentry values after bootstrap. Secrets and uploads never live in a release directory.

## Automated release

The GitHub environment must contain `SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`, `SERVER_USER`, `SERVER_HOST` and `DEPLOY_PATH`. A push to `main`:

1. runs Ruff, PostgreSQL/Redis integration tests, frontend tests, audits and migration checks;
2. builds SHA-tagged backend/frontend images in GHCR and scans them with Trivy;
3. uploads only release manifests into `releases/<sha>`;
4. invokes `deploy.sh <sha>`.

The deploy script enables maintenance, freezes API/bots, verifies PostgreSQL and uploads backups, migrates, starts all health-checked services, runs smoke tests, atomically changes `current`, and only then disables maintenance.

## Rollback

Any deploy error triggers the trap in `deploy.sh`: application writers stop, the pre-migration database dump is restored, the previous SHA images are started, the `current` symlink is restored, and maintenance is removed only after the rollback attempt. Keep maintenance active and restore manually from `/opt/botvpk/shared/backups/<sha>` if the automatic rollback itself reports an error.

After opening traffic, watch Sentry, HTTP 5xx/p95, Redis/PostgreSQL readiness, notification delivery errors and both bot heartbeats for 24 hours. Repeat the audit after seven days.
