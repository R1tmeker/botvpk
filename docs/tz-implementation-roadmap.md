# TZ Implementation Roadmap

Source document: `C:/Users/vlad-/Desktop/TZ_VPK_Zvezda_obedinennoe.docx`.

## Scope

The final target is a full VPK Zvezda information system:

- FastAPI backend with Telegram initData authentication and JWT.
- PostgreSQL 15+ as the primary storage.
- SQLAlchemy 2.0 async ORM and Alembic migrations.
- React 18 + TypeScript + Vite Telegram Mini App.
- aiogram 3.x Telegram bot connected to the same data model.
- Docker Compose with PostgreSQL, backend, frontend and nginx.
- Role-based authorization, audit log, reports, file upload checks and HTTPS-ready deployment.

## Current Progress

- Privacy hardening for the existing repository is staged.
- PostgreSQL ORM models exist for all 31 tables from TZ section 6.
- Alembic initial migration is wired to the SQLAlchemy metadata.
- FastAPI application is registered with CORS and rate limit middleware.
- Telegram WebApp `initData` auth, JWT, role dependencies, audit helper and upload validation are implemented.
- API modules now have working first-pass logic for auth, public content, join applications, candidate events, schedule, attendance, normatives, learning, notifications, announcements, appeals, squads, users, promo, dashboard settings, reports, files and admin sections.
- Docker Compose includes PostgreSQL, backend API, DB-first bot, frontend and nginx.
- React/Vite Mini App has a role-aware interface, VPK Zvezda palette, local logo and PNG icons.
- Mini App now includes public onboarding, candidate dashboard, role-aware tabs, dashboard customization, normative submissions, reports and admin overview screens wired to API hooks.
- `backend/app/bot.py` provides an aiogram 3 DB-first bot connected to PostgreSQL.
- The DB-first bot supports `/join` FSM application intake plus event response and absence reason FSM.
- Local Docker check passed for `postgres`, `backend`, `bot`, `frontend`, `nginx`; the bot was verified in `DRYRUN=true` mode.
- Daily backup and restore scripts are documented in `docs/production-ops.md`.

## Completed in Session 6 (May 2026 — Security audit + bot unification)

- Critical RBAC vulnerabilities fixed: role whitelist on application accept, file IDOR protection,
  export squad filtering, settings key whitelist.
- RBAC integrity: squad-ownership checks on schedule templates, user edit, admin/users squad scoping.
- Admin panel extended: appeals, candidate events, normatives, learning materials management tabs;
  search, status filters, delete confirmations, audit log filters.
- **Bot unification complete**: legacy CSV bot (`bot/`, `main.py`, CSV data files) removed.
  Single bot is `backend/app/bot.py` (DB-first, connected to PostgreSQL).
- **CSV→DB migration complete**: all 27 members from `data/members.csv` migrated to `users` table.
  Three squads created. No legacy role codes remain in DB. Idempotency verified.
- Single role model: `backend/app/roles.py` only. No legacy role mapping needed.

## Not Complete Yet

- Telegram polling with a real renewed bot token still needs a production smoke test.
- Production HTTPS/Let's Encrypt setup still needs environment-specific deployment configuration.
- `audit_log.ip_address` not populated (low priority, requires Request injection to all endpoints).
- Optional: CHECK constraints / Enum on `users.role_code` and `status_code` columns.
