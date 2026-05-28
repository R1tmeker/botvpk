# Production Operations

## HTTPS

Use `nginx/nginx.https.example.conf` as the production reverse proxy template.

Required values:
- `MINI_APP_URL=https://your-domain.example.com`
- `API_CORS_ORIGINS=https://your-domain.example.com`
- real `BOT_TOKEN`, `JWT_SECRET`, `SUPER_ADMIN_TG_ID`
- valid Let's Encrypt certificates mounted to nginx

Mini App must be opened from Telegram over HTTPS. Local `http://localhost:*` URLs are only for development.

## Daily Database Backups

Create a backup manually:

```powershell
.\scripts\backup-postgres.ps1
```

Restore a backup:

```powershell
.\scripts\backup-postgres.ps1
.\scripts\restore-postgres.ps1 -DumpPath .\backups\vpk-zvezda-YYYYMMDD-HHMMSS.dump -ConfirmRestore
```

Windows Task Scheduler example:

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\path\to\botvpk\scripts\backup-postgres.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At 03:15
Register-ScheduledTask -TaskName "VPK Zvezda PostgreSQL backup" -Action $action -Trigger $trigger -Description "Daily pg_dump backup for VPK Zvezda"
```

Linux cron example:

```cron
15 3 * * * pwsh -NoProfile -File /opt/botvpk/scripts/backup-postgres.ps1 >> /opt/botvpk/logs/backup.log 2>&1
```

Backups are written to `backups/`, which is ignored by git. The script keeps the latest 14 dumps by default.

## Restore Check

At least once after deployment, restore the newest dump into a test database/container and run:

```powershell
docker compose exec backend alembic -c alembic.ini current
docker compose exec backend python -m compileall -q app
```

Never restore into production without a fresh backup and an explicit maintenance window.
