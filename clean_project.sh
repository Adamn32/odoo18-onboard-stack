#!/usr/bin/env bash
# Purpose: Clean repo cruft for odoo18-onboard-stack WITHOUT touching data volumes.
# Default is DRY-RUN; pass --apply to actually delete.
# Adam: every action is commented for clarity.

set -Eeuo pipefail
APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

# helper to print vs run
run(){ if [[ $APPLY -eq 1 ]]; then eval "$1"; else echo "[dry-run] $1"; fi }

echo "== Sanity: ensure we're in the project root =="
for f in docker-compose.yml onboarding_web odoo README.md; do
  [[ -e "$f" ]] && { ok=1; break; } || true
done
[[ ${ok:-0} -eq 1 ]] || { echo "Run me from the project root"; exit 1; }

echo "== Protect .env and important files =="
# Keep a copy of .env in /tmp just in case
[[ -f .env ]] && run "cp -a .env /tmp/odoo18-onboard-stack.env.$(date +%Y%m%d-%H%M%S)"

echo "== Remove typical junk: caches, temp files, editor swp, macOS cruft =="
PATTERNS=( "__pycache__" "*.py[co]" ".pytest_cache" ".mypy_cache" ".ruff_cache" ".DS_Store" "Thumbs.db" "*.swp" "*.swo" "*.pid" "*.tmp" )
for p in "${PATTERNS[@]}"; do
  # files
  if [[ $APPLY -eq 1 ]]; then
    find . -type f -name "$p" -print -delete 2>/dev/null || true
  else
    find . -type f -name "$p" -print 2>/dev/null || true
  fi
  # dirs
  if [[ $APPLY -eq 1 ]]; then
    find . -type d -name "$p" -print0 2>/dev/null | xargs -0 -r rm -rf
  else
    find . -type d -name "$p" -print 2>/dev/null || true
  fi
done

echo "== Remove local build artifacts if present (never required in backup) =="
for d in node_modules .venv venv dist build *.egg-info; do
  if compgen -G "$d" > /dev/null; then
    run "rm -rf $d"
  fi
done

echo "== Nginx audit (read-only) =="
if docker compose ps --format '{{.Service}}' | grep -qx nginx_proxy; then
  # Show vhost list and server_name lines so you can spot dupes
  docker compose exec nginx_proxy sh -lc 'ls -1 /etc/nginx/conf.d/*.conf || true'
  docker compose exec nginx_proxy sh -lc 'for f in /etc/nginx/conf.d/*.conf; do [ -e "$f" ] || continue; awk "/server_name/ {gsub(/\t+/,\" \"); print FILENAME\":\", \$0}" "$f"; done'
else
  echo "No nginx_proxy service found via compose; skipping audit."
fi

echo "== Docker prune (safe: dangling only; won’t touch named volumes) =="
docker system df || true
if [[ $APPLY -eq 1 ]]; then
  docker container prune -f || true
  docker image  prune -f || true
  docker volume ls -qf dangling=true | xargs -r docker volume rm
else
  echo "[dry-run] docker container prune -f"
  echo "[dry-run] docker image prune -f"
  echo "[dry-run] docker volume ls -qf dangling=true | xargs -r docker volume rm"
fi
docker system df || true

echo "== Big files (>100MB) still in repo (inspect manually) =="
find . -type f -size +100M -print 2>/dev/null || true

echo "Done. Re-run with --apply to execute deletions."
