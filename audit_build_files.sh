#!/usr/bin/env bash
# Purpose: Find (and optionally delete) UNREFERENCED Dockerfiles and requirements*.txt
# Scope: Works off docker-compose.yml build contexts + Dockerfiles actually used.
# Default: DRY-RUN. Pass --apply to really delete.
# Adam: every step is commented for clarity.

set -Eeuo pipefail
APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1
ROOT="$(pwd)"

run(){ if [[ $APPLY -eq 1 ]]; then eval "$1"; else echo "[dry-run] $1"; fi }

echo "== Sanity: ensure we're in the project root =="
[[ -f docker-compose.yml ]] || { echo "No docker-compose.yml here"; exit 1; }

echo "== Derive USED build contexts and Dockerfiles from docker-compose.yml =="
# Grab all 'context:' values (one per buildable service)
mapfile -t CONTEXTS < <(awk -F: '/^[[:space:]]*context:[[:space:]]*/{sub(/^[[:space:]]*/,"",$2); gsub(/[\"\047]/,"",$2); print $2}' docker-compose.yml | sed 's/[[:space:]]*$//')
# Grab any explicit 'dockerfile:' entries
mapfile -t DOCKERFILE_HINTS < <(awk -F: '/^[[:space:]]*dockerfile:[[:space:]]*/{sub(/^[[:space:]*/,"",$2); gsub(/[\"\047]/,"",$2); print $2}' docker-compose.yml | sed 's/[[:space:]]*$//')

# Build the canonical set of "used" Dockerfile paths:
# - default to <context>/Dockerfile for each context
# - include any dockerfile hints as either absolute or relative to the compose file
declare -A USED_DFILES=()
for ctx in "${CONTEXTS[@]}"; do
  # normalize ./ and trailing slashes
  p="${ctx%/}/Dockerfile"
  [[ -e "$p" ]] && USED_DFILES["$(realpath -m "$p")"]=1
done
for hint in "${DOCKERFILE_HINTS[@]}"; do
  if [[ "$hint" = /* ]]; then
    [[ -e "$hint" ]] && USED_DFILES["$(realpath -m "$hint")"]=1
  else
    # try as relative to repo root
    [[ -e "$hint" ]] && USED_DFILES["$(realpath -m "$hint")"]=1
    # also try as relative to each context (common case)
    for ctx in "${CONTEXTS[@]}"; do
      cand="${ctx%/}/$hint"
      [[ -e "$cand" ]] && USED_DFILES["$(realpath -m "$cand")"]=1
    done
  fi
done

echo "== All Dockerfiles in repo =="
mapfile -t ALL_DFILES < <(find . -type f \( -iname 'Dockerfile' -o -iname 'Dockerfile.*' \) -print | sort)
for f in "${ALL_DFILES[@]}"; do echo "DF: $f"; done

echo "== Marking USED Dockerfiles (by Compose) =="
for k in "${!USED_DFILES[@]}"; do echo "USED: ${k#$ROOT/}"; done | sort

echo "== Compute UNUSED Dockerfiles =="
declare -a UNUSED_DFILES=()
for f in "${ALL_DFILES[@]}"; do
  rp="$(realpath -m "$f")"
  if [[ -z "${USED_DFILES[$rp]:-}" ]]; then
    UNUSED_DFILES+=("$f")
  fi
done
if ((${#UNUSED_DFILES[@]})); then
  echo "-- Candidates to remove (Dockerfiles not referenced by Compose) --"
  printf '%s\n' "${UNUSED_DFILES[@]}"
else
  echo "No unreferenced Dockerfiles detected."
fi

echo
echo "== Locate requirements files =="
mapfile -t ALL_REQS < <(find . -type f -iregex '.*/\(requirements\(-.*\)\?\|reqs\|pip-requirements\)\.txt' -print | sort)
for r in "${ALL_REQS[@]}"; do echo "REQ: $r"; done

echo "== Mark requirements used by USED Dockerfiles =="
declare -A USED_REQS=()
# Scan only Dockerfiles the compose build actually uses
for df in "${!USED_DFILES[@]}"; do
  [[ -f "$df" ]] || continue
  # Grep for requirements usage patterns
  while IFS= read -r line; do
    # extract potential filenames following '-r' or COPY statements
    for cand in $line; do
      case "$cand" in
        *.txt)
          # resolve relative to Dockerfile directory
          base="$(dirname "$df")/$cand"
          if [[ -f "$base" ]]; then USED_REQS["$(realpath -m "$base")"]=1; fi
          # also consider repo-root relative
          if [[ -f "$cand" ]]; then USED_REQS["$(realpath -m "$cand")"]=1; fi
        ;;
      esac
    done
  done < <(grep -iE 'requirements|pip install -r|COPY .*requirements' "$df" || true)
done
for k in "${!USED_REQS[@]}"; do echo "USED_REQ: ${k#$ROOT/}"; done | sort

echo "== Compute UNUSED requirements files =="
declare -a UNUSED_REQS=()
for r in "${ALL_REQS[@]}"; do
  rp="$(realpath -m "$r")"
  if [[ -z "${USED_REQS[$rp]:-}" ]]; then
    UNUSED_REQS+=("$r")
  fi
done
if ((${#UNUSED_REQS[@]})); then
  echo "-- Candidates to remove (requirements*.txt not referenced by USED Dockerfiles) --"
  printf '%s\n' "${UNUSED_REQS[@]}"
else
  echo "No unreferenced requirements files detected."
fi

echo
if [[ $APPLY -eq 1 ]]; then
  echo "== Deleting candidates (be sure you reviewed the lists above) =="
  for f in "${UNUSED_DFILES[@]}"; do run "rm -f '$f'"; done
  for r in "${UNUSED_REQS[@]}"; do run "rm -f '$r'"; done
else
  echo "Dry-run only. Re-run with --apply to delete the candidates shown."
fi
