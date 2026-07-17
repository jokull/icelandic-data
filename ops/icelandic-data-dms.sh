#!/bin/bash
#
# Dead-man's-switch for the icelandic-data source-health checks.
#
# WHY THIS EXISTS
# GitHub cannot alert you that GitHub stopped. Scheduled runs can be dropped
# entirely during high load (documented, no backfill, no guarantee), and
# scheduled workflows in public repos are auto-disabled after 60 days of
# repository inactivity. Both fail closed and quiet: no run, no failure, no
# email. Only something outside GitHub can notice the silence.
#
# WHAT IT WATCHES
# Each health run appends an observation and commits it to the health-history
# branch. A fresh commit there means the monitor ran. A stale one means it
# stopped — whatever the reason.
#
# WHAT IT IS NOT
# It does not care whether the data sources are healthy. That question is
# already answered, with detail, by the workflow itself. This answers only:
# "is anyone still watching?" Keep it that way — a switch that also opines on
# source health is a switch that can cry wolf.
#
# Deliberately deterministic: no LLM, no agent turn. It costs nothing on a
# healthy day and has few failure modes. Delivery goes through openclaw, which
# is the one part that must reach a human.

set -u

PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Do NOT call the `openclaw` shim from launchd. node here is managed by fnm,
# and the shim resolves it via the per-shell $PATH — under launchd that either
# is not there at all, or resolves to a different version, and openclaw dies
# with "Failed to open the plugin state database | statement.columns is not a
# function" (a native better-sqlite3 ABI mismatch). It fails at startup, so
# the switch goes deaf exactly when it matters.
#
# Instead pin the same stable interpreter + entrypoint that
# ai.openclaw.gateway.plist itself uses — that invocation is proven under
# launchd. Keep these in step with the gateway plist on openclaw upgrades;
# `notify` fails loudly (and refuses to stamp the cooldown) if they drift.
NODE_BIN="${NODE_BIN:-/Users/jokull/.local/share/fnm/node-versions/v24.15.0/installation/bin/node}"
OPENCLAW_JS="${OPENCLAW_JS:-/Users/jokull/openclaw/dist/index.js}"

ROOT="/Users/jokull/clawd"
LOG_DIR="$ROOT/logs"
STATE_DIR="$ROOT/state"
LOG_FILE="$LOG_DIR/icelandic-data-dms.log"
ALERT_STAMP="$STATE_DIR/icelandic-data-dms.last-alert"
LOCK_DIR="$STATE_DIR/icelandic-data-dms.lock"

REPO="jokull/icelandic-data"
BRANCH="health-history"

# The workflow runs daily. 36h tolerates one dropped run plus GitHub's
# documented cron drift (observed: a 06:17 slot firing at 07:05) without
# crying wolf. Two consecutive misses will trip it.
#
# Both are env-overridable so the alert path can actually be exercised:
#   MAX_AGE_HOURS=0 ~/clawd/bin/icelandic-data-dms.sh   # force an alert
# An untested dead-man's-switch is decoration.
MAX_AGE_HOURS="${MAX_AGE_HOURS:-36}"
# At most one nag per day while it stays broken.
ALERT_COOLDOWN_HOURS="${ALERT_COOLDOWN_HOURS:-20}"

TELEGRAM_TARGET="461214887"

mkdir -p "$LOG_DIR" "$STATE_DIR"

# Overlap guard, same idiom as mediaserver-healthcheck.sh
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

timestamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { printf '%s %s\n' "$(timestamp)" "$*" >>"$LOG_FILE"; }

notify() {
  local text="$1"
  if [ ! -x "$NODE_BIN" ]; then
    log "ERROR: node missing at $NODE_BIN (fnm version bumped?) — alert NOT delivered"
    return 1
  fi
  if [ ! -f "$OPENCLAW_JS" ]; then
    log "ERROR: openclaw entrypoint missing at $OPENCLAW_JS — alert NOT delivered"
    return 1
  fi
  if "$NODE_BIN" "$OPENCLAW_JS" message send \
      --channel telegram \
      --target "$TELEGRAM_TARGET" \
      --message "$text" >>"$LOG_FILE" 2>&1; then
    log "notified telegram:$TELEGRAM_TARGET"
    return 0
  fi
  # If this ever fires, the switch is deaf and nobody knows. Loud in the log.
  log "ERROR: openclaw message send FAILED — alert not delivered"
  return 1
}

# --- Fetch the branch head -------------------------------------------------
# Unauthenticated on purpose: the repo is public, so this needs no token and
# cannot break when a token expires. One less silent failure mode. Retries
# cover transient blips only.
api_url="https://api.github.com/repos/${REPO}/branches/${BRANCH}"
payload=""
for attempt in 1 2 3; do
  payload="$(curl -fsS --max-time 20 -H "Accept: application/vnd.github+json" "$api_url" 2>>"$LOG_FILE")"
  [ -n "$payload" ] && break
  sleep $((attempt * 5))
done

if [ -z "$payload" ]; then
  # We could not ask the question, so we do not know the answer. Unreachable
  # is not the same as stale — the likeliest cause is this mini's own network,
  # and alerting on that would train you to ignore the alert. Logged, silent.
  log "UNKNOWN: could not reach GitHub API after 3 attempts (mini offline?) — no alert"
  exit 0
fi

# --- Age of the last observation -------------------------------------------
age_hours="$(printf '%s' "$payload" | python3 -c '
import sys, json
from datetime import datetime, timezone
try:
    d = json.load(sys.stdin)
    stamp = d["commit"]["commit"]["committer"]["date"]
    then = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    print(f"{(datetime.now(timezone.utc) - then).total_seconds() / 3600:.2f}")
except Exception as exc:
    print(f"ERR {type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(1)
' 2>>"$LOG_FILE")"

if [ -z "$age_hours" ]; then
  log "ERROR: could not parse branch payload — API shape changed?"
  exit 0
fi

stale="$(python3 -c "print(1 if float('$age_hours') > $MAX_AGE_HOURS else 0)")"

# --- Decide ----------------------------------------------------------------
if [ "$stale" = "0" ]; then
  if [ -f "$ALERT_STAMP" ]; then
    # It was broken and now it isn't. Close the loop, or you're left
    # wondering whether the last alert ever resolved.
    log "RECOVERED: last observation ${age_hours}h old"
    notify "✅ icelandic-data health checks are running again — last observation ${age_hours}h ago."
    rm -f "$ALERT_STAMP"
  else
    log "ok: last observation ${age_hours}h old"
  fi
  exit 0
fi

log "STALE: last observation ${age_hours}h old (limit ${MAX_AGE_HOURS}h)"

# Cooldown: nag once a day, not once a run.
if [ -f "$ALERT_STAMP" ]; then
  last_alert="$(cat "$ALERT_STAMP" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  if [ $(( (now - last_alert) / 3600 )) -lt "$ALERT_COOLDOWN_HOURS" ]; then
    log "  (within ${ALERT_COOLDOWN_HOURS}h cooldown — not re-alerting)"
    exit 0
  fi
fi

if notify "🔴 icelandic-data source-health has gone quiet.

No observation committed to the *${BRANCH}* branch for ${age_hours}h (limit ${MAX_AGE_HOURS}h).

This means the daily check itself stopped — not that a data source is down. Likely causes:
• GitHub dropped the scheduled run (documented, no backfill)
• Scheduled workflow auto-disabled after 60 days of repo inactivity
• The workflow is failing before it records

Check: https://github.com/${REPO}/actions/workflows/source-health.yml"; then
  # Only start the cooldown once someone has actually been told. Stamping on a
  # failed send would suppress retries for ALERT_COOLDOWN_HOURS while nobody
  # knows anything is wrong — the switch would silence itself.
  date +%s >"$ALERT_STAMP"
else
  log "  (not stamping cooldown — will retry next run)"
fi
exit 0
