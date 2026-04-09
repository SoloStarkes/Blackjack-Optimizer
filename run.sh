#!/usr/bin/env bash
# run.sh — Install Python deps, run tests, and start the Blackjack Optimizer API.
#
# Usage:
#   chmod +x run.sh
#   ./run.sh              # install deps + run fast tests + start server
#   ./run.sh --no-install # skip pip install
#   ./run.sh --no-test    # skip tests, start server immediately
#   ./run.sh --full-test  # run ALL 614 tests (~5-6 min) before starting
#   ./run.sh --no-install --no-test  # flags may be combined

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }

# ── Script root (works when called from any directory) ────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Parse flags ───────────────────────────────────────────────────────────────
SKIP_INSTALL=false
SKIP_TEST=false
FULL_TEST=false

for arg in "$@"; do
  case "$arg" in
    --no-install) SKIP_INSTALL=true ;;
    --no-test)    SKIP_TEST=true    ;;
    --full-test)  FULL_TEST=true    ;;
    *)
      error "Unknown flag: $arg"
      echo "Usage: $0 [--no-install] [--no-test] [--full-test]"
      exit 1
      ;;
  esac
done

# ── Python version check ──────────────────────────────────────────────────────
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
  error "python3 not found. Install Python 3.11+ and retry."
  exit 1
fi

PY_VER=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 || ("$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11) ]]; then
  warn "Python $PY_VER detected — Python 3.11+ is recommended."
fi
info "Using Python $PY_VER at $("$PYTHON" -c 'import sys; print(sys.executable)')"

# ── Install dependencies ──────────────────────────────────────────────────────
if [[ "$SKIP_INSTALL" == false ]]; then
  if [[ -f requirements.txt ]]; then
    info "Installing dependencies from requirements.txt…"
    "$PYTHON" -m pip install --quiet --upgrade -r requirements.txt
  else
    info "No requirements.txt found — installing packages directly…"
    "$PYTHON" -m pip install --quiet --upgrade \
      "fastapi[standard]>=0.135" "uvicorn[standard]>=0.44" \
      "numpy>=1.26" "pydantic>=2" "httpx>=0.28" "pytest>=9"
  fi
  success "Dependencies installed."
else
  info "Skipping dependency installation (--no-install)."
fi

# ── Verify critical imports ───────────────────────────────────────────────────
MISSING=()
for pkg in fastapi uvicorn numpy pydantic; do
  "$PYTHON" -c "import $pkg" 2>/dev/null || MISSING+=("$pkg")
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
  error "Missing packages: ${MISSING[*]}. Run without --no-install to fix."
  exit 1
fi

# ── Run tests ─────────────────────────────────────────────────────────────────
if [[ "$SKIP_TEST" == false ]]; then
  echo ""
  if [[ "$FULL_TEST" == true ]]; then
    info "Running full test suite (614 tests — this takes ~5-6 minutes)…"
    TEST_TARGETS="backend/tests/"
  else
    info "Running fast tests (engine + strategy + API, ~30 seconds)…"
    info "  Use --full-test to run all 614 tests."
    TEST_TARGETS="backend/tests/test_engine.py backend/tests/test_strategy.py backend/tests/test_api.py"
  fi

  if "$PYTHON" -m pytest $TEST_TARGETS -q --tb=short; then
    success "Tests passed."
  else
    error "Tests failed. Fix the errors above before starting the server."
    error "To skip tests and start anyway, run:  $0 --no-test"
    exit 1
  fi
else
  info "Skipping tests (--no-test)."
fi

# ── Print startup banner ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║       BLACKJACK OPTIMIZER  ·  API SERVER         ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${BOLD}API${RESET}       http://localhost:8000"
echo -e "  ${BOLD}Docs${RESET}      http://localhost:8000/docs"
echo -e "  ${BOLD}Health${RESET}    http://localhost:8000/health"
echo ""
echo -e "  ${BOLD}Frontend${RESET}  serve with:"
echo -e "            python -m http.server 5500 --directory frontend"
echo -e "            then open  http://localhost:5500/app.jsx"
echo ""
echo -e "  Press ${BOLD}Ctrl-C${RESET} to stop."
echo ""

# ── Start the server ──────────────────────────────────────────────────────────
# --app-dir . ensures Python resolves the 'backend' package from the repo root.
exec "$PYTHON" -m uvicorn backend.api:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --reload-dir backend \
  --log-level info
