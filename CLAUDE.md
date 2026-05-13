# Odoo 18 Onboarding Stack — CLAUDE.md

## Project Overview
FastAPI + Odoo 18 onboarding stack. Collects client details via a 2-step web form, provisions Odoo databases (Community/Enterprise), and redirects users to their instance.

## Architecture
- **FastAPI** (`onboarding_web/app/main.py`) — intake forms, API, DB migrations
- **pg_clients** — Postgres for intake records (clients table)
- **Odoo 18** (Community & Enterprise) — each with its own Postgres
- **Docker Compose profiles**: `core` (Odoo+Postgres), `onboarding` (web+clients DB)
- **Background worker** (`onboarding_worker/`) — optional Celery/odoorpc tasks (not wired in compose)

## Key Files

| File | Purpose |
|------|---------|
| `onboarding_web/app/main.py` | All FastAPI routes, ORM, migrations (single file) |
| `onboarding_web/app/templates/` | Jinja2 templates (dark Savanna theme) |
| `onboarding_web/app/static/sslogo.png` | Branding asset |
| `docker-compose.yml` | All services with profile labels |
| `onboarding_worker/tasks/__init__.py` | Celery app + `create_odoo_company` task |
| `onboarding_worker/tasks/odoo_provision.py` | odoorpc company provisioning |

## ORM Model (`ClientInfo`)
```python
class ClientInfo(Base):
    __tablename__ = "clients"
    id               = Column(Integer, primary_key=True)
    company_name     = Column(String, nullable=False)
    admin_email      = Column(String, nullable=False)
    odoo_edition     = Column(String, nullable=False)
    db_name          = Column(String, nullable=False)
    domain_name      = Column(Boolean, default=False)
    name_domain_name = Column(String, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
```

## Routes
- `GET /` — Step 1 form
- `POST /submit` — Persist intake, redirect to step 2
- `GET /database/{community,enterprise}` — Step 2 form (read-only DB name)
- `POST /create-db` — Validate, generate nonce, render creating page
- `POST /api/create-db` — JSON API (nonce-gated), calls Odoo `/web/database/create`
- `GET /admin/clients` — Admin list
- `GET /success` / `/error` — Result pages
- `GET /healthz` — Health check

## Conventions

### Code style
- No comments in production code unless needed for clarity
- Single-file FastAPI app (`main.py`) — keep routes in `@app` decorator order
- SQLAlchemy auto-migrations at startup via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- Type hints on all route parameters

### UI/UX
- Dark theme: `--bg:#06080f`, `--accent:#00a8ff`, `--panel:#0b1220`
- Card-based layout with `.card:before` gradient accent bar
- Logo: `/static/sslogo.png` — referenced as `{{ url_for('static', path='sslogo.png') }}`
- Responsive breakpoint at 520px / 640px

### Database naming
- DB names: lowercase + digits + underscores only (validated both client+server side)
- Template uses `pattern="[a-z0-9_]+"` + JS lower-casing enforcement

### Security
- Master password from env `MASTER_PASSWORD`, never in HTML/JS
- `/api/create-db` is nonce-gated (`secrets.token_urlsafe(24)`, 5-min expiry)
- No CSRF on form pages (intake forms only)

## Docker
- `--profile core` — Odoo Community + Enterprise + their Postgres instances
- `--profile onboarding` — FastAPI web + pg_clients
- Web container has hot-reload via `UVICORN_RELOAD=1`

## Common Commands
```bash
# Start everything
docker compose --profile core up -d
docker compose --profile onboarding up -d --build

# Logs
docker compose logs -f onboarding_web

# DB access
docker exec -it pg_clients psql -U clientadmin -d clients
```

## Gotchas
- `_runtime_state` is in-memory dict — not suitable for multi-replica deployments
- No dependency version pins in requirements.txt — pin before prod
- worker code is NOT wired into docker-compose.yml (Redis + worker services missing)
- `odoo_conf/` directory is gitignored but required for compose mounts
