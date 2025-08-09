# onboarding_web/app/main.py
"""
FastAPI app for the Odoo onboarding gateway.
Author: Adam ChapChap Ng'uni
Last Updated: 2025-08-09

Flow:
-----
1) "/"              -> onboarding form (company, email, edition)
2) POST "/submit"   -> save client to Postgres; route to /database/<edition>
3) "/database/*"    -> DB details form; posts to /create-db (includes hidden 'edition')
4) "/create-db"     -> Renders "creating..." page; that page calls /api/create-db
5) "/api/create-db" -> Creates DB in Odoo, returns JSON with redirect URL
6) Browser redirects to Odoo login directly (no looping /gateway step)
"""

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

import httpx
from dotenv import load_dotenv
import os, time, secrets

# ---------------------------------------------------------------------------
# Environment & App Setup
# ---------------------------------------------------------------------------
load_dotenv()

app = FastAPI()

# Mount static files and templates folder
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Database connection for onboarding form storage
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://clientadmin:clientpass@pg_clients/clients")

# Internal Odoo URLs (used for API calls inside Docker network)
ODOO_COMMUNITY_INTERNAL  = os.getenv("ODOO_COMMUNITY_URL",  "http://odoo_community:8069")
ODOO_ENTERPRISE_INTERNAL = os.getenv("ODOO_ENTERPRISE_URL", "http://odoo_enterprise:8069")

# Public Odoo URLs (used for final browser redirects)
ODOO_COMMUNITY_EXTERNAL  = os.getenv("ODOO_COMMUNITY_EXTERNAL",  "http://localhost:8069")
ODOO_ENTERPRISE_EXTERNAL = os.getenv("ODOO_ENTERPRISE_EXTERNAL", "http://localhost:8070")

# Odoo master password from environment
ODOO_MASTER_PASSWORD = os.getenv("MASTER_PASSWORD", "admin")

# SQLAlchemy setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------------------------------------------------------------------
# ORM model for client info storage
# ---------------------------------------------------------------------------
class ClientInfo(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    admin_email = Column(String, nullable=False)
    odoo_edition = Column(String, nullable=False)  # "Community" or "Enterprise"

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# In-memory state and nonce tracking
# ---------------------------------------------------------------------------
_runtime_state = {
    "last_selected_edition": None,
    "last_admin_email": None,
}

_nonces = {}  # {nonce: expiry_timestamp}

def _clean_nonces():
    """Remove expired nonces."""
    now = time.time()
    for k, v in list(_nonces.items()):
        if v < now:
            _nonces.pop(k, None)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
async def list_databases(odoo_base: str) -> list[str]:
    """
    Robust DB listing for Odoo 17/18:
      1) Try JSON-RPC (preferred in newer builds)
      2) Fall back to legacy empty form POST
    Returns [] on any error.
    """
    url = f"{odoo_base}/web/database/list"
    try:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "onboard/1.0"}) as client:
            # 1) JSON-RPC
            jr = await client.post(
                url,
                json={"jsonrpc": "2.0", "method": "call", "params": {}},
            )
            if jr.status_code == 200:
                j = jr.json()
                if isinstance(j, dict):
                    res = j.get("result", [])
                    if isinstance(res, list):
                        return res

            # 2) Legacy form fallback
            fr = await client.post(url, data={})
            if fr.status_code == 200:
                j = fr.json()
                if isinstance(j, dict):
                    res = j.get("result", [])
                    if isinstance(res, list):
                        return res
    except Exception:
        pass
    return []

def _mk_redirect(base: str, path: str) -> str:
    """Build a full URL with base + path."""
    p = path if path.startswith("/") else f"/{path}"
    return f"{base}{p}"

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
async def form_page(request: Request):
    """Render the initial company info form."""
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/submit")
async def handle_submit(
    request: Request,
    company_name: str = Form(...),
    admin_email: str = Form(...),
    odoo_edition: str = Form(...),
):
    """Handle company form submission and redirect to DB details page."""
    db = SessionLocal()
    try:
        row = ClientInfo(company_name=company_name, admin_email=admin_email, odoo_edition=odoo_edition)
        db.add(row); db.commit(); db.refresh(row)
    finally:
        db.close()

    _runtime_state["last_admin_email"] = admin_email

    ed_lower = odoo_edition.strip().lower()
    if "community" in ed_lower:
        _runtime_state["last_selected_edition"] = "Community"
        return RedirectResponse(url="/database/community", status_code=302)
    if "enterprise" in ed_lower:
        _runtime_state["last_selected_edition"] = "Enterprise"
        return RedirectResponse(url="/database/enterprise", status_code=302)
    return RedirectResponse(url="/error", status_code=302)

@app.get("/database/community")
async def database_community(request: Request):
    """Render DB creation form for Community edition."""
    _runtime_state["last_selected_edition"] = "Community"
    return templates.TemplateResponse("database.html", {"request": request, "edition": "Community"})

@app.get("/database/enterprise")
async def database_enterprise(request: Request):
    """Render DB creation form for Enterprise edition."""
    _runtime_state["last_selected_edition"] = "Enterprise"
    return templates.TemplateResponse("database.html", {"request": request, "edition": "Enterprise"})

@app.post("/create-db")
async def create_db_page(
    request: Request,
    db_name: str = Form(...),
    db_password: str = Form(...),
    phone: str = Form(""),
    lang: str = Form(...),
    country: str = Form(...),
    demo: bool = Form(False),
    edition: str = Form(None),
    admin_login: str = Form(None),
):
    """
    Render the "Creating..." page with a nonce token to avoid duplicate requests.
    """
    selected = (edition or _runtime_state.get("last_selected_edition") or "Community").strip()
    is_enterprise = selected.lower().startswith("enter")
    odoo_internal = ODOO_ENTERPRISE_INTERNAL if is_enterprise else ODOO_COMMUNITY_INTERNAL

    # Validate DB name
    safe_name = (db_name or "").lower()
    if not safe_name or not all(c.islower() or c.isdigit() or c == '_' for c in safe_name):
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": "Invalid database name.",
             "details": "Use lowercase letters, numbers, and underscores only."},
            status_code=400,
        )

    # If DB exists already -> redirect straight to Odoo login
    existing = await list_databases(odoo_internal)
    if safe_name in existing:
        ext_base = ODOO_ENTERPRISE_EXTERNAL if is_enterprise else ODOO_COMMUNITY_EXTERNAL
        return RedirectResponse(_mk_redirect(ext_base, f"/web/login?db={safe_name}"), status_code=302)

    # Create one-time nonce
    _clean_nonces()
    nonce = secrets.token_urlsafe(24)
    _nonces[nonce] = time.time() + 300  # expires in 5 mins

    # Render creating page with no-cache headers
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
    Endpoint called by JS on the "Creating..." page to actually create the DB in Odoo.
    Returns JSON with either success+redirect URL or error.
    """
    data = await request.json()
    nonce = data.get("nonce")
    _clean_nonces()
    if not nonce or nonce not in _nonces:
        return JSONResponse({"ok": False, "error": "Expired or invalid request (nonce)."}, status_code=409)
    _nonces.pop(nonce, None)

    safe_name   = (data.get("db_name") or "").lower()
    db_password = data.get("db_password") or ""
    phone       = data.get("phone") or ""
    lang        = data.get("lang") or "en_US"
    country     = data.get("country") or "ZM"
    demo        = bool(data.get("demo") or False)
    edition     = (data.get("edition") or "Community").strip()
    admin_login = (data.get("admin_login") or _runtime_state.get("last_admin_email") or "admin").strip()

    if not safe_name or not all(c.islower() or c.isdigit() or c == '_' for c in safe_name):
        return JSONResponse({"ok": False, "error": "Invalid database name."}, status_code=400)

    is_enterprise = edition.lower().startswith("enter")
    odoo_internal = ODOO_ENTERPRISE_INTERNAL if is_enterprise else ODOO_COMMUNITY_INTERNAL

    # Idempotency check before creating
    existing = await list_databases(odoo_internal)
    if safe_name in existing:
        ext_base = ODOO_ENTERPRISE_EXTERNAL if is_enterprise else ODOO_COMMUNITY_EXTERNAL
        return JSONResponse({"ok": True, "redirect": _mk_redirect(ext_base, f"/web/login?db={safe_name}")})

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
            resp = await client.post(create_url, data=payload)
    except httpx.RequestError as e:
        return JSONResponse({"ok": False, "error": f"Network error to Odoo: {e}"}, status_code=502)

    # Final check after creation attempt
    existing = await list_databases(odoo_internal)
    if safe_name in existing:
        ext_base = ODOO_ENTERPRISE_EXTERNAL if is_enterprise else ODOO_COMMUNITY_EXTERNAL
        return JSONResponse({"ok": True, "redirect": _mk_redirect(ext_base, f"/web/login?db={safe_name}")})

    return JSONResponse({"ok": False, "error": f"Odoo error HTTP {resp.status_code}"}, status_code=502)

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
    """Health check endpoint."""
    return {"status": "ok"}

