# onboarding_web/app/main.py
"""
FastAPI app for the Odoo onboarding gateway.

Author: Adam ChapChap Ng'uni
Last Updated: 2025-08-09 19:55 CAT

What changed (this revision):
- Added db_name support end-to-end:
  * ORM model now includes db_name
  * /submit captures and validates db_name from form.html
  * /database/* pre-fills db_name and renders it read-only
  * /create-db & /api/create-db use the carried db_name
- Added light-touch migration to ensure db_name column exists.

Flow
----
1) "/"              -> onboarding form (company, email, edition, db_name)
2) POST "/submit"   -> save client; route to /database/<edition>
3) "/database/*"    -> DB details form (db_name read-only); posts to /create-db
4) "/create-db"     -> Renders "creating..." page; that page calls /api/create-db
5) "/api/create-db" -> Calls Odoo to create DB; returns JSON redirect URL
"""

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import create_engine, Column, Integer, String, text
from sqlalchemy.orm import sessionmaker, declarative_base

import httpx
from dotenv import load_dotenv
import os, time, secrets

# ---------------------------------------------------------------------------
# Environment & App Setup
# ---------------------------------------------------------------------------
load_dotenv()
app = FastAPI()

# Serve static assets and Jinja2 templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Onboarding PostgreSQL (client intake DB)
# Default matches docker-compose service names.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://clientadmin:clientpass@pg_clients/clients")

# Odoo internal URLs (container network) for API calls
ODOO_COMMUNITY_INTERNAL  = os.getenv("ODOO_COMMUNITY_URL",  "http://odoo_community:8069")
ODOO_ENTERPRISE_INTERNAL = os.getenv("ODOO_ENTERPRISE_URL", "http://odoo_enterprise:8069")

# Public Odoo URLs (browser redirects)
ODOO_COMMUNITY_EXTERNAL  = os.getenv("ODOO_COMMUNITY_EXTERNAL",  "http://localhost:8069")
ODOO_ENTERPRISE_EXTERNAL = os.getenv("ODOO_ENTERPRISE_EXTERNAL", "http://localhost:8070")

# Odoo master password (read from .env; never shown to the user)
ODOO_MASTER_PASSWORD = os.getenv("MASTER_PASSWORD", "admin")

# SQLAlchemy session & base
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------------------------------------------------------------------
# ORM model for client intake storage
# ---------------------------------------------------------------------------
class ClientInfo(Base):
    __tablename__ = "clients"
    id            = Column(Integer, primary_key=True, index=True)
    company_name  = Column(String, nullable=False)
    admin_email   = Column(String, nullable=False)
    odoo_edition  = Column(String, nullable=False)  # "Community" or "Enterprise"
    db_name       = Column(String, nullable=False)  # Database name (<=63 chars)

# Create table if it doesn't exist
Base.metadata.create_all(bind=engine)

# Light-touch migration: ensure db_name column & index exist for old deployments
with engine.begin() as conn:
    conn.execute(text("""
        ALTER TABLE clients
        ADD COLUMN IF NOT EXISTS db_name VARCHAR(63) NOT NULL DEFAULT '';
    """))
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public' AND indexname = 'idx_clients_db_name'
            ) THEN
                CREATE INDEX idx_clients_db_name ON clients (db_name);
            END IF;
        END$$;
    """))

# ---------------------------------------------------------------------------
# Simple in-memory state (acts like a session cache for the next step)
# NOTE: This is fine for a single-instance demo. For production, use server-side sessions.
# ---------------------------------------------------------------------------
_runtime_state: dict[str, str | None] = {
    "last_selected_edition": None,
    "last_admin_email": None,
    "last_db_name": None,
}

# One-time nonces to prevent duplicate creation on refresh
_nonces: dict[str, float] = {}  # {nonce: expiry_timestamp}

def _clean_nonces() -> None:
    """Remove expired nonces."""
    now = time.time()
    for k, v in list(_nonces.items()):
        if v < now:
            _nonces.pop(k, None)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def list_databases(odoo_base: str) -> list[str]:
    """
    Robust DB listing for Odoo 17/18:
      1) Try JSON-RPC body
      2) Fallback to legacy empty-form POST
    Returns [] on any error.
    """
    url = f"{odoo_base}/web/database/list"
    try:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "onboard/1.0"}) as client:
            # Preferred JSON-RPC
            r = await client.post(url, json={"jsonrpc": "2.0", "method": "call", "params": {}})
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and isinstance(j.get("result"), list):
                    return j["result"]
            # Fallback legacy
            r = await client.post(url, data={})
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and isinstance(j.get("result"), list):
                    return j["result"]
    except Exception:
        pass
    return []

def _mk_redirect(base: str, path: str) -> str:
    """Build a full URL with base + path."""
    return f"{base}{path if path.startswith('/') else '/' + path}"

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
async def form_page(request: Request):
    """Initial company info form."""
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/submit")
async def handle_submit(
    request: Request,
    company_name: str = Form(...),   # Company name from form.html
    db_name:      str = Form(...),   # Database name (required here)
    admin_email:  str = Form(...),   # Admin email address
    odoo_edition: str = Form(...),   # Odoo edition: "Community" or "Enterprise"
):
    """
    Handle company form submission.
    - Validates db_name (lowercase, numbers, underscores only)
    - Stores client info in PostgreSQL onboarding DB
    - Saves db_name and email in runtime state for next step
    - Redirects user to appropriate /database/<edition> page
    """
    # Normalize/validate db_name
    safe_name = (db_name or "").lower().strip()
    if not safe_name or not all(c.islower() or c.isdigit() or c == "_" for c in safe_name):
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "message": "Invalid database name.",
                "details": "Use lowercase letters, numbers, and underscores only."
            },
            status_code=400,
        )

    # Persist intake data
    db = SessionLocal()
    try:
        row = ClientInfo(
            company_name=company_name.strip(),
            admin_email=admin_email.strip(),
            odoo_edition=odoo_edition.strip(),
            db_name=safe_name,
        )
        db.add(row)
        db.commit()
    finally:
        db.close()

    # Carry values to the next page
    _runtime_state["last_admin_email"] = admin_email.strip()
    _runtime_state["last_db_name"]     = safe_name

    # Route to the correct edition page
    ed = odoo_edition.strip().lower()
    if "enterprise" in ed:
        _runtime_state["last_selected_edition"] = "Enterprise"
        return RedirectResponse("/database/enterprise", status_code=302)

    _runtime_state["last_selected_edition"] = "Community"
    return RedirectResponse("/database/community", status_code=302)

@app.get("/database/community")
async def database_community(request: Request):
    """Render DB creation form for Community (db_name is read-only)."""
    _runtime_state["last_selected_edition"] = "Community"
    return templates.TemplateResponse(
        "database.html",
        {
            "request": request,
            "edition": "Community",
            "last_db_name": _runtime_state.get("last_db_name", ""),
        },
    )

@app.get("/database/enterprise")
async def database_enterprise(request: Request):
    """Render DB creation form for Enterprise (db_name is read-only)."""
    _runtime_state["last_selected_edition"] = "Enterprise"
    return templates.TemplateResponse(
        "database.html",
        {
            "request": request,
            "edition": "Enterprise",
            "last_db_name": _runtime_state.get("last_db_name", ""),
        },
    )

@app.post("/create-db")
async def create_db_page(
    request: Request,
    db_name: str = Form(None),          # May arrive from read-only field; fallback to state
    db_password: str = Form(...),
    phone: str = Form(""),
    lang: str = Form(...),
    country: str = Form(...),
    demo: bool = Form(False),
    edition: str = Form(None),
    admin_login: str = Form(None),
):
    """
    Render the "Creating..." page with a one-time nonce; the page will call /api/create-db.
    """
    selected = (edition or _runtime_state.get("last_selected_edition") or "Community").strip()
    is_enterprise = selected.lower().startswith("enter")

    # Respect carried name if form didn't include it (it should).
    safe_name = (db_name or _runtime_state.get("last_db_name") or "").lower()
    if not safe_name or not all(c.islower() or c.isdigit() or c == "_" for c in safe_name):
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": "Invalid database name.",
             "details": "Use lowercase letters, numbers, and underscores only."},
            status_code=400,
        )

    odoo_internal = ODOO_ENTERPRISE_INTERNAL if is_enterprise else ODOO_COMMUNITY_INTERNAL

    # Short-circuit: DB already exists -> send to login
    existing = await list_databases(odoo_internal)
    if safe_name in existing:
        ext_base = ODOO_ENTERPRISE_EXTERNAL if is_enterprise else ODOO_COMMUNITY_EXTERNAL
        return RedirectResponse(_mk_redirect(ext_base, f"/web/login?db={safe_name}"), status_code=302)

    # One-time nonce for the async API call
    _clean_nonces()
    nonce = secrets.token_urlsafe(24)
    _nonces[nonce] = time.time() + 300  # 5 minutes

    # Render creating page with payload & cache-busters
    resp = templates.TemplateResponse(
        "creating_db.html",
        {
            "request": request,
            "db_name": safe_name,
            "edition": "Enterprise" if is_enterprise else "Community",
            "is_enterprise": is_enterprise,
            "payload": {
                "db_name": safe_name,
                "db_password": db_password,
                "phone": phone or "",
                "lang": lang or "en_US",
                "country": country or "ZM",
                "demo": bool(demo),
                "edition": "Enterprise" if is_enterprise else "Community",
                "admin_login": (admin_login or _runtime_state.get("last_admin_email") or "admin").strip(),
                "nonce": nonce,
            },
        },
    )
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.post("/api/create-db")
async def api_create_db(request: Request):
    """
    Called by JS on the "Creating..." page to create the DB in Odoo.
    Returns JSON: { ok: bool, redirect?: str, error?: str }
    """
    data = await request.json()
    nonce = data.get("nonce")
    _clean_nonces()
    if not nonce or nonce not in _nonces:
        return JSONResponse({"ok": False, "error": "Expired or invalid request (nonce)."}, status_code=409)
    _nonces.pop(nonce, None)  # Consume the nonce

    safe_name   = (data.get("db_name") or "").lower()
    db_password = data.get("db_password") or ""
    phone       = data.get("phone") or ""
    lang        = data.get("lang") or "en_US"
    country     = data.get("country") or "ZM"
    demo        = bool(data.get("demo") or False)
    edition     = (data.get("edition") or "Community").strip()
    admin_login = (data.get("admin_login") or _runtime_state.get("last_admin_email") or "admin").strip()

    if not safe_name or not all(c.islower() or c.isdigit() or c == "_" for c in safe_name):
        return JSONResponse({"ok": False, "error": "Invalid database name."}, status_code=400)

    is_enterprise = edition.lower().startswith("enter")
    odoo_internal = ODOO_ENTERPRISE_INTERNAL if is_enterprise else ODOO_COMMUNITY_INTERNAL

    # Idempotency: re-check before creating
    existing = await list_databases(odoo_internal)
    if safe_name in existing:
        ext_base = ODOO_ENTERPRISE_EXTERNAL if is_enterprise else ODOO_COMMUNITY_EXTERNAL
        return JSONResponse({"ok": True, "redirect": _mk_redirect(ext_base, f"/web/login?db={safe_name}")})

    # Odoo create DB POST payload (form-encoded)
    payload = {
        "master_pwd": ODOO_MASTER_PASSWORD,
        "name": safe_name,
        "login": admin_login,
        "password": db_password,
        "lang": lang,
        "country_code": country,
        "phone": phone,
        "demo": "true" if demo else "false",
    }

    create_url = f"{odoo_internal}/web/database/create"
    try:
        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
            r = await client.post(create_url, data=payload)
    except httpx.RequestError as e:
        return JSONResponse({"ok": False, "error": f"Network error to Odoo: {e}"}, status_code=502)

    # Final verification after creation attempt
    existing = await list_databases(odoo_internal)
    if safe_name in existing:
        ext_base = ODOO_ENTERPRISE_EXTERNAL if is_enterprise else ODOO_COMMUNITY_EXTERNAL
        return JSONResponse({"ok": True, "redirect": _mk_redirect(ext_base, f"/web/login?db={safe_name}")})

    return JSONResponse({"ok": False, "error": f"Odoo error HTTP {r.status_code}"}, status_code=502)

@app.get("/admin/clients")
async def admin_clients(request: Request):
    """Admin view to list all clients."""
    db = SessionLocal()
    try:
        rows = db.query(ClientInfo).all()
    finally:
        db.close()
    return templates.TemplateResponse("admin_clients.html", {"request": request, "clients": rows})

@app.get("/error")
async def error(request: Request):
    """Generic error page."""
    return templates.TemplateResponse("error.html", {"request": request})

@app.get("/healthz")
async def healthz():
    """Liveness probe."""
    return {"status": "ok"}

