#!/usr/bin/env bash
# ============================================================================
# Phase 7a CI action entrypoint — thin orchestrator over the headless driver.
#
# All behaviour lives in this repo (scripts/ + this action) so it is testable
# locally with Docker, not only via GitHub. The platform seam (spec §5.5):
#   - GitHub-specific surface: INPUT_* env vars, GITHUB_WORKSPACE,
#     GITHUB_OUTPUT — handled here, in bash.
#   - Platform-neutral core: scripts/ci_generate.py (driver), action/report.py
#     (JUnit -> report + repair candidates), action/export_evidence_junit.py
#     (AI-028 evidence -> JUnit) — zero GitHub imports.
#
# Phase 7a modes:
#   generate-only  — headless generation via ci_generate.py, exit code 0/1/2
#   run-existing   — pytest --junitxml + AI-028 evidence export against a
#                    caller-provided package; exit code = pytest's (referee)
#   generate-and-run — arrives in 7b; fails fast, never silently degrades.
#
# Internal self-test mode (self-test: true) boots the hermetic mock site +
# fake LLM inside the container so the full generate + run path exercises
# with zero external services (mirrors tests/test_ci_generate.py E2E).
# ============================================================================
set -euo pipefail

# The venv python is authoritative (repo requires >= 3.14; the base image's
# system python may be older). Guard here so nothing in this script depends
# on the image's PATH env surviving intact.
if [ -d "/app/.venv/bin" ] && [[ ":$PATH:" != *":/app/.venv/bin:"* ]]; then
  export PATH="/app/.venv/bin:$PATH"
fi

WORKSPACE_ROOT="${GITHUB_WORKSPACE:-/github/workspace}"
MODE="${INPUT_MODE:-generate-only}"
WS_NAME="${INPUT_WORKSPACE:-ai-test-workspace}"
RESULT_DIR="${WORKSPACE_ROOT}/${WS_NAME}/results"
SELFTEST="${INPUT_SELF_TEST:-false}"

log() { echo "[ai-test-gen] $*" >&2; }

echo_github_output() { # name value — no-op outside GitHub (local Docker runs)
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"
  fi
  log "output $1=$2"
}

# --- mode validation (7a scope: generate-only + run-existing) ---------------
case "$MODE" in
  generate-only | run-existing) ;;
  generate-and-run)
    echo "ERROR: mode 'generate-and-run' arrives in Phase 7b (PR comment, cache, verified" >&2
    echo "       adaptation). Use 'generate-only' or 'run-existing'." >&2
    echo_github_output exit_code 2
    exit 2
    ;;
  *)
    echo "ERROR: unknown mode '$MODE' — expected generate-only | run-existing" >&2
    echo_github_output exit_code 2
    exit 2
    ;;
esac

# GitHub mounts the checked-out repo here; everything runs from it so
# relative inputs (story path, ignore-file, tests) resolve against the repo.
cd "$WORKSPACE_ROOT"
mkdir -p "$RESULT_DIR"

# --- hermetic self-test: boot mock site + fake LLM inside the container -----
MOCK_PORT="${INPUT_SELF_TEST_MOCK_PORT:-8781}"
LLM_PORT="${INPUT_SELF_TEST_LLM_PORT:-9977}"

if [ "$SELFTEST" = "true" ]; then
  log "self-test: booting mock site (127.0.0.1:${MOCK_PORT}) + fake LLM (127.0.0.1:${LLM_PORT})"
  export RAG_ENABLED=0
  export FLOW_MEMORY_ENABLED=0

  python scripts/mock_server.py --port "$MOCK_PORT" --directory mock_sites/ecommerce \
    >"$RESULT_DIR/mock-server.log" 2>&1 &
  MOCK_PID=$!
  python scripts/fake_llm.py >"$RESULT_DIR/fake-llm.log" 2>&1 &
  LLM_PID=$!
  trap 'kill "$MOCK_PID" "$LLM_PID" 2>/dev/null || true' EXIT

  # Readiness: port connect for the LLM, HTTP 200 for the mock (deterministic
  # localhost — the same fail-fast probe the E2E tests use).
  python - "$MOCK_PORT" "$LLM_PORT" <<'PY'
import socket, sys, time, urllib.error, urllib.request
mock_port, llm_port = int(sys.argv[1]), int(sys.argv[2])

def wait_port(port: int, name: str) -> None:
    for _ in range(90):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return
        except OSError:
            time.sleep(1)
    raise SystemExit(f"self-test server {name} did not start on port {port}")

def wait_http(url: str, name: str) -> None:
    for _ in range(90):
        try:
            urllib.request.urlopen(url, timeout=2).read(16)
            return
        except urllib.error.HTTPError:
            return  # server responded — up
        except Exception:
            time.sleep(1)
    raise SystemExit(f"self-test server {name} not serving {url}")

wait_http(f"http://127.0.0.1:{mock_port}/index.html", "mock site")
wait_port(llm_port, "fake LLM")
PY
  log "self-test servers ready"

  # Hermetic endpoints override any consumer inputs.
  export FORCE_PROVIDER=openai-local
  export FORCE_MODEL=fake-model
  export FORCE_BASE_URL="http://127.0.0.1:${LLM_PORT}/v1"
fi

# ============================================================================
# generate-only
# ============================================================================
run_generate_only() {
  log "mode=generate-only: generating tests for ${INPUT_URL} (workspace '${WS_NAME}')"

  local -a DRIVER_ARGS=(
    --story "${INPUT_STORY:?mode generate-only requires the 'story' input}"
    --url "${INPUT_URL:?mode generate-only requires the 'url' input}"
    --workspace "$WS_NAME"
    --storage-root "$WORKSPACE_ROOT"
  )
  [ "${INPUT_POM:-false}" = "true" ] && DRIVER_ARGS+=(--pom)
  [ -n "${INPUT_CREDENTIAL_PROFILE:-}" ] && DRIVER_ARGS+=(--credential-profile "$INPUT_CREDENTIAL_PROFILE")
  if [ -n "${INPUT_IGNORE_FILE:-}" ]; then
    DRIVER_ARGS+=(--ignore-file "${WORKSPACE_ROOT}/${INPUT_IGNORE_FILE}")
  fi
  [ "${INPUT_DANGER_ZONE:-false}" = "true" ] && DRIVER_ARGS+=(--danger-zone)
  [ -n "${INPUT_ALLOWED_DOMAINS:-}" ] && DRIVER_ARGS+=(--allowed-domains "$INPUT_ALLOWED_DOMAINS")
  DRIVER_ARGS+=(--provider "${FORCE_PROVIDER:-${INPUT_PROVIDER:-openai-local}}")
  [ -n "${FORCE_MODEL:-${INPUT_MODEL:-}}" ] && DRIVER_ARGS+=(--model "${FORCE_MODEL:-$INPUT_MODEL}")
  [ -n "${FORCE_BASE_URL:-${INPUT_LLM_BASE_URL:-}}" ] && DRIVER_ARGS+=(--llm-base-url "${FORCE_BASE_URL:-$INPUT_LLM_BASE_URL}")
  [ -n "${INPUT_LLM_API_KEY:-}" ] && DRIVER_ARGS+=(--llm-api-key "$INPUT_LLM_API_KEY")
  DRIVER_ARGS+=(--json)

  set +e
  DRIVER_OUTPUT="$(python scripts/ci_generate.py "${DRIVER_ARGS[@]}" 2>"$RESULT_DIR/generate.err")"
  DRIVER_RC=$?
  set -e
  printf '%s\n' "$DRIVER_OUTPUT" > "$RESULT_DIR/generate.json"

  if [ "$DRIVER_RC" -ne 0 ]; then
    echo_github_output exit_code "$DRIVER_RC"
    exit "$DRIVER_RC"
  fi

  # Last stdout line is the driver's JSON contract.
  printf '%s\n' "$DRIVER_OUTPUT" | tail -n 1 > "$RESULT_DIR/summary.json"
  python - "$RESULT_DIR/summary.json" <<'PY' || true
import json, sys
summary = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"generated {summary['test_count']} tests ({summary['conditions']} conditions, "
      f"{summary['unresolved']} unresolved) in {summary['duration_s']}s -> {summary['package']}")
PY
  echo_github_output exit_code 0
  echo_github_output package "$(python -c 'import json,sys;print(json.load(open(sys.argv[1]))["package"])' "$RESULT_DIR/summary.json")"
  echo_github_output test_count "$(python -c 'import json,sys;print(json.load(open(sys.argv[1]))["test_count"])' "$RESULT_DIR/summary.json")"
  echo_github_output report "$RESULT_DIR/summary.json"
  log "generate-only OK (exit 0)"
}

# ============================================================================
# run-existing
# ============================================================================
run_existing() {
  local TESTS_INPUT="${INPUT_TESTS:-}"
  if [ -z "$TESTS_INPUT" ]; then
    echo "ERROR: mode 'run-existing' requires the 'tests' input (path to a generated" >&2
    echo "       test package directory or test file(s), relative to the repo root)" >&2
    echo_github_output exit_code 2
    exit 2
  fi

  local TESTS_PATH
  case "$TESTS_INPUT" in
    /*) TESTS_PATH="$TESTS_INPUT" ;;
    *) TESTS_PATH="${WORKSPACE_ROOT}/${TESTS_INPUT}" ;;
  esac
  if [ ! -e "$TESTS_PATH" ]; then
    echo "ERROR: tests path not found: $TESTS_PATH" >&2
    echo_github_output exit_code 2
    exit 2
  fi

  # Evidence conftest: generated packages use @pytest.mark.evidence +
  # evidence_tracker, whose fixture ships in generated_tests/conftest.py. Copy
  # it next to the package when missing so sidecars are written (lazy fixture —
  # plain pytest packages are unaffected). CI checkouts are ephemeral; this is
  # scratch-space provisioning, not mutation of a user's tracked files.
  local PKG_DIR
  if [ -d "$TESTS_PATH" ]; then PKG_DIR="$TESTS_PATH"; else PKG_DIR="$(dirname "$TESTS_PATH")"; fi
  if [ ! -f "$PKG_DIR/conftest.py" ] && [ -f "$WORKSPACE_ROOT/generated_tests/conftest.py" ]; then
    cp "$WORKSPACE_ROOT/generated_tests/conftest.py" "$PKG_DIR/conftest.py"
    log "provisioned evidence conftest into $PKG_DIR"
  fi

  log "mode=run-existing: pytest $TESTS_PATH -> $RESULT_DIR/junit.xml"
  local -a PYTEST_ARGS=()
  [ -n "${INPUT_PYTEST_ARGS:-}" ] && read -r -a PYTEST_ARGS <<< "$INPUT_PYTEST_ARGS"

  set +e
  python -m pytest "$TESTS_PATH" \
    -o addopts= \
    -o pythonpath="$WORKSPACE_ROOT" \
    --browser=chromium --screenshot=only-on-failure --timeout=120 \
    -q --tb=short --no-header -p no:cacheprovider \
    --junitxml="$RESULT_DIR/junit.xml" \
    "${PYTEST_ARGS[@]}" 2>&1 | tee "$RESULT_DIR/pytest.out"
  PYTEST_RC=${PIPESTATUS[0]}
  set -e
  log "pytest exit $PYTEST_RC"

  # AI-028 evidence JUnit (sidecar-enriched; empty when no sidecars exist).
  # Sidecars land in <package>/evidence/ (EvidenceTracker writes next to the
  # test files), and a generated package may be a subdirectory of the tests
  # input — scan recursively from the package root.
  local SIDECARS
  SIDECARS="$(find "$PKG_DIR" -name '*.evidence.json' 2>/dev/null | head -n 1 || true)"
  if [ -n "$SIDECARS" ]; then
    if python action/export_evidence_junit.py \
        --evidence-dir "$PKG_DIR" \
        --output "$RESULT_DIR/junit-evidence.xml" \
        --suite-name "ai-test-generator" 2>"$RESULT_DIR/evidence-export.err"; then
      log "evidence JUnit written ($RESULT_DIR/junit-evidence.xml)"
    else
      log "WARN: evidence JUnit export failed (see $RESULT_DIR/evidence-export.err)"
    fi
  else
    log "no evidence sidecars under $PKG_DIR — skipping evidence JUnit (raw junit.xml still emitted)"
  fi

  # Report: counts + repair-candidate marking (spec §8/7a) — the comment
  # payload shape the self-test workflow asserts; 7b posts it as a PR comment.
  if python action/report.py \
      --mode run-existing \
      --junit "$RESULT_DIR/junit.xml" \
      --evidence-junit "$RESULT_DIR/junit-evidence.xml" \
      --package "$TESTS_PATH" \
      --workspace "$WS_NAME" \
      --output "$RESULT_DIR" 2>"$RESULT_DIR/report.err"; then
    log "report written ($RESULT_DIR/report.json)"
  else
    log "WARN: report generation failed (see $RESULT_DIR/report.err)"
  fi

  echo_github_output exit_code "$PYTEST_RC"
  echo_github_output junit "$RESULT_DIR/junit.xml"
  echo_github_output report "$RESULT_DIR/report.json"
  log "run-existing finished — exit code $PYTEST_RC (referee: failures = your change)"
  exit "$PYTEST_RC"
}

# ============================================================================
case "$MODE" in
  generate-only) run_generate_only ;;
  run-existing) run_existing ;;
esac
