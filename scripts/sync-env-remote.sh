#!/bin/bash
#
# sync-env-remote.sh - Push .env files to a remote machine via scp
#
# Usage:
#   sync-env-remote.sh user@host /local/repo /remote/repo [--dry-run] [--file .env.local]
#
# Examples:
#   sync-env-remote.sh deploy@winbox ~/GitHub/trivalley /c/Projects/trivalley
#   sync-env-remote.sh deploy@winbox ~/GitHub/trivalley /c/Projects/trivalley --dry-run
#   sync-env-remote.sh deploy@winbox ~/GitHub/trivalley /c/Projects/trivalley --file temporal/.env.local

set -euo pipefail

REMOTE=""
LOCAL_DIR=""
REMOTE_DIR=""
DRY_RUN=false
FILE_FILTER=""

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            echo "Usage: $(basename "$0") user@host /local/repo /remote/repo [options]"
            echo ""
            echo "Push .env files to a remote machine via scp, preserving relative paths."
            echo ""
            echo "Options:"
            echo "  --dry-run          Preview files without copying"
            echo "  --file PATH        Push only a specific file (basename or relative path)"
            echo "  -h, --help         Show this help"
            echo ""
            echo "Examples:"
            echo "  $(basename "$0") deploy@winbox ~/GitHub/trivalley /c/Projects/trivalley"
            echo "  $(basename "$0") deploy@winbox ~/GitHub/trivalley /c/Projects/trivalley --dry-run"
            echo "  $(basename "$0") deploy@winbox ~/GitHub/trivalley /c/Projects/trivalley --file temporal/.env.local"
            exit 0 ;;
        --dry-run)  DRY_RUN=true; shift ;;
        --file)     FILE_FILTER="$2"; shift 2 ;;
        -*)         echo "Unknown flag: $1" >&2; exit 1 ;;
        *)
            if [[ -z "$REMOTE" ]]; then
                REMOTE="$1"
            elif [[ -z "$LOCAL_DIR" ]]; then
                LOCAL_DIR="$1"
            elif [[ -z "$REMOTE_DIR" ]]; then
                REMOTE_DIR="$1"
            else
                echo "Unexpected argument: $1" >&2; exit 1
            fi
            shift ;;
    esac
done

if [[ -z "$REMOTE" || -z "$LOCAL_DIR" || -z "$REMOTE_DIR" ]]; then
    echo "Usage: $(basename "$0") user@host /local/repo /remote/repo [--dry-run] [--file path]"
    exit 1
fi

LOCAL_DIR="${LOCAL_DIR%/}"
REMOTE_DIR="${REMOTE_DIR%/}"

# Convert /c/... to C:/... for Windows compatibility
if [[ "$REMOTE_DIR" =~ ^/([a-zA-Z])/ ]]; then
    drive=$(echo "${BASH_REMATCH[1]}" | tr '[:lower:]' '[:upper:]')
    REMOTE_DIR="${drive}:${REMOTE_DIR:2}"
fi

# Find .env files, same filtering as cproj
SKIP_DIRS="node_modules|\.venv|venv|__pycache__|\.git"

files=()
while IFS= read -r -d '' f; do
    rel="${f#"$LOCAL_DIR"/}"

    # Skip files in ignored directories
    if echo "$rel" | grep -qE "(^|/)($SKIP_DIRS)/"; then
        continue
    fi

    # Skip .example files
    if [[ "$rel" == *.example ]]; then
        continue
    fi

    # Apply --file filter
    if [[ -n "$FILE_FILTER" ]]; then
        if [[ "$FILE_FILTER" == */* ]]; then
            [[ "$rel" != "$FILE_FILTER" ]] && continue
        else
            [[ "$(basename "$rel")" != "$FILE_FILTER" ]] && continue
        fi
    fi

    files+=("$rel")
done < <(find "$LOCAL_DIR" -name '.env' -o -name '.env.*' | tr '\n' '\0')

if [[ ${#files[@]} -eq 0 ]]; then
    echo "No .env files found"
    exit 0
fi

echo "Remote: $REMOTE"
echo "Source: $LOCAL_DIR"
echo "Dest:   $REMOTE_DIR"
echo ""
echo "Files to push:"
for f in "${files[@]}"; do
    echo "  $f"
done
echo ""

if $DRY_RUN; then
    echo "[DRY RUN] No files copied"
    exit 0
fi

read -rp "Push ${#files[@]} file(s)? [y/N] " confirm
if [[ "$confirm" != "y" ]]; then
    echo "Aborted"
    exit 0
fi

# Shared SSH connection: first call authenticates, subsequent calls reuse it
CTRL_SOCKET=$(mktemp -u /tmp/sync-env-ssh-XXXXXX)
SSH_OPTS=(-o "ControlMaster=auto" -o "ControlPath=$CTRL_SOCKET" -o "ControlPersist=60")
cleanup() { ssh -o "ControlPath=$CTRL_SOCKET" -O exit "$REMOTE" 2>/dev/null; }
trap cleanup EXIT

failed=0
for f in "${files[@]}"; do
    remote_path="$REMOTE_DIR/$f"
    remote_dir="$(dirname "$remote_path")"

    # Ensure remote directory exists (no -p flag; Windows cmd mkdir creates intermediates by default)
    ssh "${SSH_OPTS[@]}" "$REMOTE" "mkdir \"$remote_dir\"" || true
    if scp "${SSH_OPTS[@]}" -q "$LOCAL_DIR/$f" "$REMOTE:$remote_path"; then
        echo "  ok  $f"
    else
        echo "  FAIL  $f" >&2
        ((failed++))
    fi
done

echo ""
echo "Pushed $((${#files[@]} - failed))/${#files[@]} file(s)"
[[ $failed -gt 0 ]] && exit 1 || exit 0
