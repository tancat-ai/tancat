#!/usr/bin/env bash
# ============================================================================
# Phase 7 CI action entrypoint — thin orchestrator over the headless driver.
#
# All behaviour lives in this repo (scripts/ + this action) so it is testable
# locally with Docker, not only via GitHub. The platform seam (spec §5.5):
#   - GitHub-specific surface: INPUT_* env vars, GITHUB_WORKSPACE,
#     GITHUB_OUTPUT, GITHUB_TOKEN — handled here, in bash + ci/platform/.
#   - Platform-neutral core: scripts/ci_generate.py (driver), action/report.py
#     (JUnit -> report + repair candidates), action/export_evidence_junit.py
#     (AI-028 evidence -> JUnit), action/adapt.py (verified adaptation),
#     action/flaky_history.py (AI-011 markers), scripts/ci_slash_commands.py
#     (slash-command replies) — zero GitHub imports.
#
# Public modes (spec §5.3):
#   generate-only    — headless generation via ci_generate.py, exit 0/1/2
#   generate-and-run — generate (or cache-hit) -> pytest -> evidence JUnit ->
#                      report + flaky markers -> PR comment payload (+ post)
#                      -> exit code = pytest's (referee); adapt: true re-runs
#                      the verified adaptation engine and reports transparently
#   run-existing     — pytest --junitxml + AI-028 evidence export against a
#                      caller-provided package; exit code = pytest's
#
# Internal modes (documented, never publicized):
#   slash-command    — parse a PR-thread /adapt | /ignore comment, run the
#                      action (verified adaptation or ignore-reply payload),
#                      post the reply. Used by ci-slash-commands.yml.
#   self-test: true  — boot the hermetic mock site + fake LLM inside the
#                      container so generate/run/adapt exercise with zero
#                      external services.
#
# Never silently degrade an unimplemented mode — fail fast with a clear
# message (the generate-and-run 7a branch was the precedent; learn: true is).
# ============================================================================
set -euo pipefail

# The venv python is authoritative (repo requires >= 3.14; the base image's
# system python may be older). Guard here so nothing in this script depends
# on the image's PATH env surviving intact.
if [ -d "/app/.venv/bin" ] && [[ ":$PATH:" != *":/app/.venv/bin:"* ]]; then
  export PATH="/app/.venv/bin:$PATH"
fi

# --- inputs ---------------------------------------------------------------
# GitHub sets Docker-action input env vars with hyphens PRESERVED
# (INPUT_SELF-TEST, INPUT_LLM-BASE-URL — spaces become underscores, hyphens
# do not), and parameter expansion cannot reference hyphenated names. Read
# via printenv; fall back to the underscore spelling for local runs.
get_input() { # $1 = input name, e.g. SELF-TEST
  local hyphen="INPUT_$1"
  local underscore="INPUT_${1//-/_}"
  local value=""
  value="$(printenv "$hyphen" 2>/dev/null)" || true
  if [ -z "$value" ]; then
    value="${!underscore:-}"
  fi
  printf '%s' "$value"
}

MODE="$(get_input MODE)"
MODE="${MODE:-generate-only}"
WS_NAME="$(get_input WORKSPACE)"
WS_NAME="${WS_NAME:-ai-test-workspace}"
SELFTEST="$(get_input SELF-TEST)"
SELFTEST="${SELFTEST:-false}"
POM="$(get_input POM)"
POM="${POM:-false}"
DANGER_ZONE="$(get_input DANGER-ZONE)"
DANGER_ZONE="${DANGER_ZONE:-false}"

WORKSPACE_ROOT="${GITHUB_WORKSPACE:-/github/workspace}"
RESULT_DIR="${WORKSPACE_ROOT}/${WS_NAME}/results"

log() { echo "[ai-test-gen] $*" >&2; }

echo_github_output() { # name value — Docker actions never receive GITHUB_OUTPUT
  # from the runner, so every output is mirrored into a state file the
  # hermetic stubs read (local Docker runs and the GitHub self-test alike).
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"
  fi
  mkdir -p "$RESULT_DIR"
  printf '%s=%s\n' "$1" "$2" >> "$RESULT_DIR/action-state.txt"
  log "output $1=$2"
}

# --- mode validation --------------------------------------------------------
case "$MODE" in
  generate-only | generate-and-run | run-existing) ;;
  slash-command) ;;
  *)
    echo "ERROR: unknown mode '$MODE' — expected generate-only | generate-and-run | run-existing" >&2
    echo_github_output exit_code 2
    exit 2
    ;;
esac

# --- inputs shared by generate modes ---------------------------------------
STORY="$(get_input STORY)"
URL="$(get_input URL)"
PROVIDER="$(get_input PROVIDER)"
MODEL="$(get_input MODEL)"
BASE_URL="$(get_input LLM-BASE-URL)"
API_KEY="$(get_input LLM-API-KEY)"
CREDENTIAL_PROFILE="$(get_input CREDENTIAL-PROFILE)"
IGNORE_FILE="$(get_input IGNORE-FILE)"
ALLOWED_DOMAINS="$(get_input ALLOWED-DOMAINS)"

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

# --- helpers ----------------------------------------------------------------

# Resolve a caller-provided path (absolute, or relative to the repo root).
resolve_path() { # $1 = input value
  case "$1" in
    /*) printf '%s' "$1" ;;
    *) printf '%s' "${WORKSPACE_ROOT}/$1" ;;
  esac
}

# Provision the evidence conftest next to a package when missing (lazy
# fixture — plain pytest packages are unaffected). CI checkouts are
# ephemeral; this is scratch-space provisioning, not mutation of tracked
# files (identical to run-existing's behaviour).
provision_conftest() { # $1 = package dir
  local PKG_DIR="$1"
  if [ ! -f "$PKG_DIR/conftest.py" ] && [ -f "$WORKSPACE_ROOT/generated_tests/conftest.py" ]; then
    cp "$WORKSPACE_ROOT/generated_tests/conftest.py" "$PKG_DIR/conftest.py"
    log "provisioned evidence conftest into $PKG_DIR"
  fi
}

# Shared pytest runner: junit.xml + AI-028 evidence JUnit + pytest.out.
# Sets PKG_DIR (the package root) for callers.
run_pytest() { # $1 = tests path (dir or file)
  local TESTS_PATH="$1"
  local PKG_DIR
  if [ -d "$TESTS_PATH" ]; then PKG_DIR="$TESTS_PATH"; else PKG_DIR="$(dirname "$TESTS_PATH")"; fi
  provision_conftest "$PKG_DIR"

  log "pytest $TESTS_PATH -> $RESULT_DIR/junit.xml"
  local PYTEST_ARGS
  PYTEST_ARGS="$(get_input PYTEST-ARGS)"
  local -a EXTRA_ARGS=()
  [ -n "$PYTEST_ARGS" ] && read -r -a EXTRA_ARGS <<< "$PYTEST_ARGS"

  set +e
  python -m pytest "$TESTS_PATH" \
    -o addopts= \
    -o pythonpath="$WORKSPACE_ROOT" \
    --browser=chromium --screenshot=only-on-failure --timeout=120 \
    -q --tb=short --no-header -p no:cacheprovider \
    --junitxml="$RESULT_DIR/junit.xml" \
    "${EXTRA_ARGS[@]}" 2>&1 | tee "$RESULT_DIR/pytest.out"
  PYTEST_RC=${PIPESTATUS[0]}
  set -e
  log "pytest exit $PYTEST_RC"

  # AI-028 evidence JUnit (sidecar-enriched; empty when no sidecars exist).
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
}

# Post a comment payload idempotently when a PR context + token exist.
# Always writes comment.md so local runs / stub steps can assert the shape.
post_comment() { # $1 = markdown body path, $2 = marker
  local BODY_FILE="$1" MARKER="$2"
  local REPO PR_NUMBER TOKEN
  REPO="$(get_input REPO)"
  PR_NUMBER="$(get_input PR-NUMBER)"
  TOKEN="$(get_input GITHUB-TOKEN)"
  cp "$BODY_FILE" "$RESULT_DIR/comment.md"
  if [ -n "$TOKEN" ] && [ -n "$REPO" ] && [ -n "$PR_NUMBER" ]; then
    log "posting comment to $REPO#$PR_NUMBER (marker: $MARKER)"
    if GITHUB_TOKEN="$TOKEN" GITHUB_REPOSITORY="$REPO" GITHUB_PR_NUMBER="$PR_NUMBER" \
        python ci/platform/github.py --body-file "$BODY_FILE" --marker "$MARKER" \
        >"$RESULT_DIR/comment-post.out" 2>"$RESULT_DIR/comment-post.err"; then
      log "comment posted: $(cat "$RESULT_DIR/comment-post.out")"
    else
      log "WARN: comment posting failed (see $RESULT_DIR/comment-post.err)"
    fi
  else
    log "comment payload written ($RESULT_DIR/comment.md); posting skipped (no PR context/token)"
  fi
}

# Referee exit-code override after verified adaptation: when adapt: true and
# EVERY failure was adapted (re-run green, nothing reverted), the run
# genuinely passed — CI reports green instead of a red X with a fix attached.
adapt_referee_exit() { # $1 = pytest rc
  local PYTEST_RC="$1"
  if [ ! -f "$RESULT_DIR/adaptation.json" ]; then
    return "$PYTEST_RC"
  fi
  python - "$PYTEST_RC" "$RESULT_DIR/adaptation.json" <<'PY'
import json, sys
rc, path = int(sys.argv[1]), sys.argv[2]
report = json.load(open(path, encoding="utf-8"))
summary = report.get("summary", {})
if summary.get("reverted", 0) == 0 and summary.get("adapted", 0) >= 1:
    print(f"adapt: all {summary['adapted']} failure(s) adapted and re-run green — exit 0")
    sys.exit(0)
print(f"adapt: {summary.get('adapted', 0)} adapted, {summary.get('reverted', 0)} reverted — referee {rc}")
sys.exit(rc)
PY
}

# ============================================================================
# generate-only
# ============================================================================
run_generate_only() {
  if [ -z "$STORY" ]; then
    echo "ERROR: mode generate-only requires the 'story' input (inline text or a path)" >&2
    echo_github_output exit_code 2
    exit 2
  fi
  if [ -z "$URL" ]; then
    echo "ERROR: mode generate-only requires the 'url' input (staging URL)" >&2
    echo_github_output exit_code 2
    exit 2
  fi
  log "mode=generate-only: generating tests for $URL (workspace '$WS_NAME')"

  local -a DRIVER_ARGS
  DRIVER_ARGS=(
    --story "$STORY"
    --url "$URL"
    --workspace "$WS_NAME"
    --storage-root "$WORKSPACE_ROOT"
  )
  [ "$POM" = "true" ] && DRIVER_ARGS+=(--pom)
  [ -n "$CREDENTIAL_PROFILE" ] && DRIVER_ARGS+=(--credential-profile "$CREDENTIAL_PROFILE")
  if [ -n "$IGNORE_FILE" ]; then
    DRIVER_ARGS+=(--ignore-file "$(resolve_path "$IGNORE_FILE")")
  fi
  [ "$DANGER_ZONE" = "true" ] && DRIVER_ARGS+=(--danger-zone)
  [ -n "$ALLOWED_DOMAINS" ] && DRIVER_ARGS+=(--allowed-domains "$ALLOWED_DOMAINS")
  DRIVER_ARGS+=(--provider "${FORCE_PROVIDER:-${PROVIDER:-openai-local}}")
  [ -n "${FORCE_MODEL:-$MODEL}" ] && DRIVER_ARGS+=(--model "${FORCE_MODEL:-$MODEL}")
  [ -n "${FORCE_BASE_URL:-$BASE_URL}" ] && DRIVER_ARGS+=(--llm-base-url "${FORCE_BASE_URL:-$BASE_URL}")
  [ -n "$API_KEY" ] && DRIVER_ARGS+=(--llm-api-key "$API_KEY")
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
# generate-and-run
# ============================================================================
run_generate_and_run() {
  if [ -z "$STORY" ]; then
    echo "ERROR: mode generate-and-run requires the 'story' input (inline text or a path)" >&2
    echo_github_output exit_code 2
    exit 2
  fi
  if [ -z "$URL" ]; then
    echo "ERROR: mode generate-and-run requires the 'url' input (staging URL)" >&2
    echo_github_output exit_code 2
    exit 2
  fi

  local LEARN
  LEARN="$(get_input LEARN)"
  if [ "$LEARN" = "true" ]; then
    echo "ERROR: learn: true is not implemented yet (7b scope ends at cache + verified" >&2
    echo "       adaptation; learning writes into the cached RAG store and arrives after)." >&2
    echo_github_output exit_code 2
    exit 2
  fi

  # --- cache (spec §7): key = sha256(story + url + model + provider + prompt-fingerprint)
  local CACHE CACHE_DIR_IN CACHE_KEY PKG_CACHE
  CACHE="$(get_input CACHE)"
  CACHE="${CACHE:-true}"
  CACHE_DIR_IN="$(get_input CACHE-DIR)"
  CACHE_DIR_IN="${CACHE_DIR_IN:-${WS_NAME}/cache}"
  local CACHE_DIR
  CACHE_DIR="$(resolve_path "$CACHE_DIR_IN")"
  CACHE_KEY="$(python action/cache_key.py --story "$STORY" --url "$URL" --model "${FORCE_MODEL:-$MODEL}" --provider "${FORCE_PROVIDER:-${PROVIDER:-openai-local}}")"
  PKG_CACHE="${CACHE_DIR}/packages/${CACHE_KEY}"
  echo_github_output cache_key "$CACHE_KEY"
  echo_github_output cache_dir "$CACHE_DIR"

  local PKG_PATH CACHE_HIT=false
  if [ "$CACHE" = "true" ] && [ -d "$PKG_CACHE" ] && [ -n "$(find "$PKG_CACHE" -name 'test_*.py' | head -n 1)" ]; then
    CACHE_HIT=true
    PKG_PATH="$PKG_CACHE"
    log "cache HIT ($CACHE_KEY) — reusing cached package $PKG_PATH, skipping generation"
  else
    log "cache MISS ($CACHE_KEY) — generating"
    # Reuse the generate-only driver block, then seed the cache.
    local DRIVER_ARGS
    DRIVER_ARGS=(
      --story "$STORY"
      --url "$URL"
      --workspace "$WS_NAME"
      --storage-root "$WORKSPACE_ROOT"
    )
    [ "$POM" = "true" ] && DRIVER_ARGS+=(--pom)
    [ -n "$CREDENTIAL_PROFILE" ] && DRIVER_ARGS+=(--credential-profile "$CREDENTIAL_PROFILE")
    if [ -n "$IGNORE_FILE" ]; then
      DRIVER_ARGS+=(--ignore-file "$(resolve_path "$IGNORE_FILE")")
    fi
    [ "$DANGER_ZONE" = "true" ] && DRIVER_ARGS+=(--danger-zone)
    [ -n "$ALLOWED_DOMAINS" ] && DRIVER_ARGS+=(--allowed-domains "$ALLOWED_DOMAINS")
    DRIVER_ARGS+=(--provider "${FORCE_PROVIDER:-${PROVIDER:-openai-local}}")
    [ -n "${FORCE_MODEL:-$MODEL}" ] && DRIVER_ARGS+=(--model "${FORCE_MODEL:-$MODEL}")
    [ -n "${FORCE_BASE_URL:-$BASE_URL}" ] && DRIVER_ARGS+=(--llm-base-url "${FORCE_BASE_URL:-$BASE_URL}")
    [ -n "$API_KEY" ] && DRIVER_ARGS+=(--llm-api-key "$API_KEY")
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
    printf '%s\n' "$DRIVER_OUTPUT" | tail -n 1 > "$RESULT_DIR/summary.json"
    PKG_PATH="$(python -c 'import json,sys;print(json.load(open(sys.argv[1]))["package"])' "$RESULT_DIR/summary.json")"
    echo_github_output package "$PKG_PATH"
    echo_github_output test_count "$(python -c 'import json,sys;print(json.load(open(sys.argv[1]))["test_count"])' "$RESULT_DIR/summary.json")"

    if [ "$CACHE" = "true" ]; then
      mkdir -p "$PKG_CACHE"
      cp -r "$PKG_PATH" "$PKG_CACHE/"
      log "cache seeded: $PKG_PATH -> $PKG_CACHE"
    fi
  fi
  echo_github_output cache_hit "$CACHE_HIT"

  # --- run (referee) --------------------------------------------------------
  run_pytest "$PKG_PATH"

  # --- report + flaky markers (AI-011 from the cached per-branch history) --
  local FLAKY_BLOCK=""
  if python action/flaky_history.py \
      --junit "$RESULT_DIR/junit.xml" \
      --history "$RESULT_DIR/../run-history.json" \
      --package "$PKG_PATH" \
      --output-flaky "$RESULT_DIR/flaky.txt" 2>"$RESULT_DIR/flaky.err"; then
    FLAKY_BLOCK="$(cat "$RESULT_DIR/flaky.txt" 2>/dev/null || true)"
  else
    log "WARN: flaky-history merge failed (see $RESULT_DIR/flaky.err)"
  fi

  if python action/report.py \
      --mode generate-and-run \
      --junit "$RESULT_DIR/junit.xml" \
      --evidence-junit "$RESULT_DIR/junit-evidence.xml" \
      --package "$PKG_PATH" \
      --workspace "$WS_NAME" \
      --url "$URL" \
      --story "$STORY" \
      --model "${FORCE_MODEL:-$MODEL}" \
      --provider "${FORCE_PROVIDER:-${PROVIDER:-openai-local}}" \
      --flaky "$RESULT_DIR/flaky.txt" \
      --output "$RESULT_DIR" 2>"$RESULT_DIR/report.err"; then
    log "report written ($RESULT_DIR/report.json)"
  else
    log "WARN: report generation failed (see $RESULT_DIR/report.err)"
  fi

  # --- verified adaptation (opt-in only: /adapt or repo-level adapt: true) --
  local ADAPT
  ADAPT="$(get_input ADAPT)"
  ADAPT="${ADAPT:-false}"
  if [ "$ADAPT" = "true" ] && [ -f "$RESULT_DIR/junit.xml" ]; then
    log "adapt: true — running verified adaptation (locator-only, assertion-gated)"
    if python action/adapt.py \
        --package "$PKG_PATH" \
        --junit "$RESULT_DIR/junit.xml" \
        --url "$URL" \
        --output "$RESULT_DIR" 2>"$RESULT_DIR/adapt.err"; then
      log "adaptation finished (see $RESULT_DIR/adaptation.json)"
    else
      log "adaptation finished with reverted patches (see $RESULT_DIR/adaptation.json)"
    fi
  fi

  # --- PR comment payload (spec §6) ----------------------------------------
  local COMMENT
  COMMENT="$(get_input COMMENT)"
  COMMENT="${COMMENT:-true}"
  if [ "$COMMENT" = "true" ]; then
    if [ -f "$RESULT_DIR/adaptation.json" ]; then
      python - "$RESULT_DIR" <<'PY'
import json, sys
from scripts.ci_slash_commands import build_adapt_reply
result_dir = sys.argv[1]
report = json.load(open(sys.argv[1] + "/adaptation.json", encoding="utf-8"))
with open(sys.argv[1] + "/report.md", "a", encoding="utf-8") as f:
    f.write("\n<details><summary>🤖 Verified adaptation</summary>\n\n")
    f.write(build_adapt_reply(report)["body"])
    f.write("\n</details>\n")
PY
    fi
    post_comment "$RESULT_DIR/report.md" "## 🤖 AI Test Generator — results"
  fi

  echo_github_output junit "$RESULT_DIR/junit.xml"
  echo_github_output report "$RESULT_DIR/report.json"
  echo_github_output exit_code "$PYTEST_RC"
  if [ "$ADAPT" = "true" ]; then
    adapt_referee_exit "$PYTEST_RC"
  fi
  log "generate-and-run finished — exit code $PYTEST_RC (referee: failures = your change)"
  exit "$PYTEST_RC"
}

# ============================================================================
# run-existing
# ============================================================================
run_existing() {
  local TESTS_INPUT
  TESTS_INPUT="$(get_input TESTS)"
  if [ -z "$TESTS_INPUT" ]; then
    echo "ERROR: mode 'run-existing' requires the 'tests' input (path to a generated" >&2
    echo "       test package directory or test file(s), relative to the repo root)" >&2
    echo_github_output exit_code 2
    exit 2
  fi

  local TESTS_PATH
  TESTS_PATH="$(resolve_path "$TESTS_INPUT")"
  if [ ! -e "$TESTS_PATH" ]; then
    echo "ERROR: tests path not found: $TESTS_PATH" >&2
    echo_github_output exit_code 2
    exit 2
  fi

  run_pytest "$TESTS_PATH"

  local URL2
  URL2="$(get_input URL)"
  if python action/report.py \
      --mode run-existing \
      --junit "$RESULT_DIR/junit.xml" \
      --evidence-junit "$RESULT_DIR/junit-evidence.xml" \
      --package "$TESTS_PATH" \
      --workspace "$WS_NAME" \
      --url "$URL2" \
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
# slash-command (INTERNAL — ci-slash-commands.yml)
# ============================================================================
run_slash_command() {
  local COMMENT_BODY
  COMMENT_BODY="$(get_input COMMENT-BODY)"
  if [ -z "$COMMENT_BODY" ]; then
    echo "ERROR: mode slash-command requires the 'comment-body' input" >&2
    echo_github_output exit_code 2
    exit 2
  fi

  # Parse the command (platform-neutral core).
  printf '%s\n' "$COMMENT_BODY" > "$RESULT_DIR/comment-body.txt"
  python scripts/ci_slash_commands.py --comment-file "$RESULT_DIR/comment-body.txt" --output "$RESULT_DIR" \
      > "$RESULT_DIR/slash-parse.out" 2> "$RESULT_DIR/slash-parse.err" || {
    log "WARN: slash-command parse failed (see $RESULT_DIR/slash-parse.err)"
    echo_github_output exit_code 2
    exit 2
  }
  local CMD TEST
  CMD="$(python -c 'import json,sys;print(json.load(open(sys.argv[1]))["command"])' "$RESULT_DIR/command.json" 2>/dev/null || true)"
  TEST="$(python -c 'import json,sys;print(json.load(open(sys.argv[1]))["test"])' "$RESULT_DIR/command.json" 2>/dev/null || true)"
  if [ -z "$CMD" ] || [ "$CMD" = "None" ]; then
    log "no slash command in comment — no-op"
    echo_github_output exit_code 0
    exit 0
  fi
  log "slash command: /$CMD $TEST"

  local TESTS_INPUT
  TESTS_INPUT="$(get_input TESTS)"
  if [ -z "$TESTS_INPUT" ]; then
    echo "ERROR: slash-command requires the 'tests' input (package path from the branch cache)" >&2
    echo_github_output exit_code 2
    exit 2
  fi
  local TESTS_PATH
  TESTS_PATH="$(resolve_path "$TESTS_INPUT")"
  if [ ! -e "$TESTS_PATH" ]; then
    echo "ERROR: tests path not found: $TESTS_PATH (cache miss? run generate-and-run on this branch first)" >&2
    echo_github_output exit_code 2
    exit 2
  fi

  # Referee: fresh pytest reproduces the failure (locator-class) + junit.
  run_pytest "$TESTS_PATH"

  local SLASH_URL
  SLASH_URL="$(get_input URL)"

  if [ "$CMD" = "adapt" ]; then
    if python action/adapt.py \
        --package "$TESTS_PATH" \
        --junit "$RESULT_DIR/junit.xml" \
        --url "$SLASH_URL" \
        --test "$TEST" \
        --output "$RESULT_DIR" 2>"$RESULT_DIR/adapt.err"; then
      log "adaptation OK (see $RESULT_DIR/adaptation.json)"
    else
      log "adaptation finished with reverted patches (see $RESULT_DIR/adaptation.json)"
    fi
    python - "$RESULT_DIR" <<'PY'
import json, sys
from scripts.ci_slash_commands import build_adapt_reply
result_dir = sys.argv[1]
report = json.load(open(result_dir + "/adaptation.json", encoding="utf-8"))
with open(result_dir + "/reply.md", "w", encoding="utf-8") as f:
    f.write(build_adapt_reply(report)["body"])
PY
  else # ignore
    python - "$TEST" "$RESULT_DIR" <<'PY'
import json, sys, xml.etree.ElementTree as ET
from scripts.ci_slash_commands import build_ignore_reply
test, result_dir = sys.argv[1], sys.argv[2]
message = ""
root = ET.parse(result_dir + "/junit.xml").getroot()
suites = [root] if root.tag == "testsuite" else list(root)
base = test.split("[", 1)[0]
for suite in suites:
    for case in suite.iter("testcase"):
        if case.get("name", "").split("[", 1)[0] != base:
            continue
        failure = case.find("failure")
        if failure is not None:
            message = failure.get("message", "") or (failure.text or "").strip()
        break
reply = build_ignore_reply(test, message)
with open(result_dir + "/reply.md", "w", encoding="utf-8") as f:
    f.write(reply["body"])
print("ignore reply rendered for", test)
PY
  fi

  post_comment "$RESULT_DIR/reply.md" "## 🤖 AI Test Generator — /$CMD"
  echo_github_output exit_code 0
  exit 0
}

# ============================================================================
case "$MODE" in
  generate-only) run_generate_only ;;
  generate-and-run) run_generate_and_run ;;
  run-existing) run_existing ;;
  slash-command) run_slash_command ;;
esac
