<<<<<<< HEAD
# Odoo 18 Onboarding Stack

A production-ready, containerized FastAPI + Odoo stack to **collect client details, provision Odoo databases (Community & Enterprise), and route users to the right instance** with Nginx/SSL in front. The stack is designed for Savanna Solutions’ SaaS model but is generic enough for other teams.

---

## Highlights

* **Two Editions**: Community & Enterprise, each with its own Postgres and (optionally) Redis.
* **Onboarding Web (FastAPI)**: Captures client info, then sends an edition-aware create request to Odoo.
* **Background Worker + Queue**: Redis-backed tasks for long‑running DB creation.
* **Secure Master Password**: Loaded from `.env`; never exposed to clients (read‑only UI if displayed).
* **Webhook Notifications**: (Optional) Notify admins on success/failure of DB creation.
* **Brandable UI**: Dark theme + Savanna branding hooks.
* **Dev → Prod Parity**: Same compose, different env files.

---

## Architecture

```
[ Client Browser ]
       │ submits form
       ▼
[ Onboarding Web (FastAPI) ]  ── enqueues ──>  [ Redis ]  ──>  [ Worker ]
       │                                           │           │
       │                                           │           └─ Calls Odoo /web/database/create
       │                                           │
       ├─> Edition-aware redirect ─────────────────┘
       │
       ├─> Odoo Community  ────────┐
       │                           ├──> PostgreSQL (pg_community)
       └─> Odoo Enterprise ────────┘

[ Nginx Reverse Proxy + SSL (Cloudflare in front) ]
```

### URL Pattern (recommended)

* Public onboarding portal: **`https://onboard.savannasolutions.co.zm`**
* Per-client route: **`https://enter.savannasolutions.co.zm/odoo?db=<Client_DB_Name>`**
* Optional vanity per client (automatable): **`https://enter.<client_slug>.savannasolutions.co.zm`** → reverse proxy → `enter.savannasolutions.co.zm/odoo?db=<Client_DB_Name>`

> **Note:** Vanity subdomains require **wildcard DNS** (e.g., `*.savannasolutions.co.zm`) and Nginx templating/automation.

---

## Repository Layout

```
.
├── addons_paths.txt
├── clients_schema.sql                     # SQL for onboarding DB (pg_clients)
├── docker-compose.yml
├── odoo
│   ├── community
│   │   ├── addons                         # custom/community addons
│   │   └── odoo.conf                      # community config
│   └── enterprise
│       ├── addons                         # custom/enterprise addons
│       └── odoo.conf                      # enterprise config
├── onboarding_web
│   └── app
│       ├── Dockerfile
│       ├── main.py                        # FastAPI routes & logic
│       ├── requirements.txt
│       ├── static
│       │   └── savannalogo.png            # branding asset
│       └── templates
│           ├── admin_clients.html         # admin list of onboarded clients (secure this!)
│           ├── base.html                  # shared layout (dark theme)
│           ├── creating_db.html           # progress/queue feedback
│           ├── database.html              # DB creation form (edition-aware)
│           ├── error.html                 # generic error page
│           ├── form.html                  # initial onboarding form
│           └── success.html               # success/next-steps page
├── onboarding_worker
│   ├── Dockerfile
│   ├── requirements.txt
│   └── tasks
│       ├── __init__.py
│       └── odoo_provision.py              # calls Odoo /web/database/create
└── README.md
```

---

## Prerequisites

* Docker 20+
* Docker Compose v2+
* Git
* A domain + Cloudflare (recommended) + Nginx reverse proxy

---

## Quick Start (Local)

1. **Clone**

   ```bash
   git clone https://github.com/<youruser>/odoo18-onboard-stack.git
   cd odoo18-onboard-stack
   ```
2. **Create `.env`** in the repo root:

   ```dotenv
   # ── Core ─────────────────────────────────────────────────────────────
   MASTER_PASSWORD=change_me_strong

   # Onboarding DB (clients)
   POSTGRES_USER_CLIENTS=clientadmin
   POSTGRES_PASSWORD_CLIENTS=clientpass
   POSTGRES_DB_CLIENTS=clients

   # Community DB
   POSTGRES_USER_COMMUNITY=odoo
   POSTGRES_PASSWORD_COMMUNITY=odoo
   POSTGRES_DB_COMMUNITY=community

   # Enterprise DB
   POSTGRES_USER_ENTERPRISE=odoo
   POSTGRES_PASSWORD_ENTERPRISE=odoo
   POSTGRES_DB_ENTERPRISE=enterprise

   # Redis
   REDIS_HOST=redis
   REDIS_PORT=6379

   # Webhook (optional)
   ADMIN_WEBHOOK_URL=
   ```
3. **Build & run**

   ```bash
   docker compose up -d --build
   ```
4. **Visit**

   * Onboarding portal: `http://localhost:8000`
   * Odoo Community: `http://localhost:8069`
   * Odoo Enterprise: `http://localhost:8070`

---

## Onboarding Flow (What Happens)

1. Client fills **Onboarding Web** form (company, email, edition).
2. Server enqueues a task on **Redis**; **Worker** picks it up.
3. Worker calls **Odoo** `/web/database/create` with `MASTER_PASSWORD` (from `.env`).
4. On success, client is redirected to the correct **/web/login** with `?db=<name>`.
5. Optional: **Webhook** notifies admin.

---

## Configuration

### Environment Variables

| Variable            | Purpose                                                 |
| ------------------- | ------------------------------------------------------- |
| `MASTER_PASSWORD`   | Odoo master password (never exposed to clients).        |
| `POSTGRES_*`        | Credentials/names for clients/community/enterprise DBs. |
| `REDIS_*`           | Redis connection for queue.                             |
| `ADMIN_WEBHOOK_URL` | If set, worker posts JSON status updates here.          |

### Odoo Config (`odoo.conf`)

Ensure each edition’s `odoo.conf` points to its respective Postgres and sets `dbfilter` to allow multi‑tenant by DB name.

### Nginx + Cloudflare (Prod)

* Terminate TLS at Cloudflare or Nginx (Full/Strict recommended).
* Map:

  * `onboard.savannasolutions.co.zm` → onboarding web
  * `enter.savannasolutions.co.zm` → Odoo reverse proxy (8069/8070)
* (Optional) **Vanity subdomains** per client using wildcard DNS + templated Nginx server blocks.

---

## Common Operations

### Admin Clients View (internal)

* Route (example): `/admin/clients` → renders `admin_clients.html` from the onboarding web.
* Purpose: quick audit of client signups and statuses.
* **Secure it** with one or more: basic auth (behind Nginx), IP allowlist, or JWT session.

### Rebuild Odoo Web Assets / Fix UI glitches (e.g., Owl asset issues)

```bash
# Community
docker exec -it odoo_community odoo -d <DB_NAME> -u all --stop-after-init
# Enterprise
docker exec -it odoo_enterprise odoo -d <DB_NAME> -u all --stop-after-init
```

### Fix Addon Permissions (host → containers)

```bash
sudo chown -R 101:0 ./odoo/community/addons ./odoo/enterprise/addons
sudo chmod -R 775     ./odoo/community/addons ./odoo/enterprise/addons
```

### Inspect Logs

```bash
docker logs -f onboarding_web
docker logs -f onboarding_worker
```

### Access Postgres shells

```bash
# Clients DB
docker exec -it pg_clients psql -U "$POSTGRES_USER_CLIENTS" -d "$POSTGRES_DB_CLIENTS"
# Community
docker exec -it pg_community psql -U "$POSTGRES_USER_COMMUNITY" -d "$POSTGRES_DB_COMMUNITY"
# Enterprise
docker exec -it pg_enterprise psql -U "$POSTGRES_USER_ENTERPRISE" -d "$POSTGRES_DB_ENTERPRISE"
```

### List Clients (example query)

```sql
SELECT id, company_name, contact_email, edition, created_at
FROM clients
ORDER BY created_at DESC;
```

## Deployment Checklist

* [ ] Strong `.env` values; store secrets safely.
* [ ] Cloudflare DNS + TLS mode set to **Full (Strict)**.
* [ ] Nginx reverse proxy with security headers & gzip.
* [ ] PostgreSQL backups (daily + retained, test restores).
* [ ] Monitoring/alerts for container health and disk space.
* [ ] Webhook to Slack/Teams for provisioning results.

---

## Troubleshooting

* **`role "odoo" does not exist` when psql into `pg_clients`:**
  Use the **clients** DB user (e.g., `clientadmin`) defined in `.env`. Each Postgres has its **own** users.
* **Assets not loading / icons broken:** Rebuild assets (see above) and clear browser cache.
* **Custom module won’t install:** Fix permissions to UID `101:0` and ensure module dependencies are present.
* **Enterprise features missing:** Confirm you’re on `odoo_enterprise` and licensing is valid.

---

## Security Notes

* Never expose the Odoo master password to end users.
* Restrict `/web/database/manager` in production (IP allowlist or auth gate).
* Enforce HTTPS end‑to‑end; prefer Cloudflare WAF & rate limiting.
* Keep base images updated; rebuild regularly.

---

## Roadmap

* Automated **vanity subdomain** issuance (DNS API + Nginx templating).
* Admin UI to view queue status and client records.
* One‑click backup/restore per client DB.

---

## License

MIT (see `LICENSE`).

## Author

**Adam ChapChap Ng’uni** — IT Systems Administrator & Cybersecurity Consultant
=======
# odoo18-onboard-stack
>>>>>>> origin/main
