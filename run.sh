#!/bin/bash

export DATABASE_URL=${POSTGRESQL_ADDON_URI}

# Clever Redis addon injects REDIS_HOST / REDIS_PORT / REDIS_PASSWORD (and sometimes
# REDIS_CLI_URL). oTree channels expect REDIS_URL — build it if missing.
if [ -z "${REDIS_URL:-}" ]; then
  if [ -n "${REDIS_CLI_URL:-}" ]; then
    export REDIS_URL="${REDIS_CLI_URL}"
  elif [ -n "${REDIS_HOST:-}" ] && [ -n "${REDIS_PORT:-}" ]; then
    # redis://:password@host:port  (empty username = password-only auth)
    export REDIS_URL="redis://:${REDIS_PASSWORD:-}@${REDIS_HOST}:${REDIS_PORT}"
  fi
fi

# Clever / production notes (see docs/CLEVER_OTREE_SCALING.md):
# - Prefer 1 app instance (vertical scale). Extra instances fight over Session rows.
# - Link Redis to this Python app; run.sh maps Clever vars → REDIS_URL for oTree.
# - Optional bot pacing (browser + CLI). Defaults also live in SESSION_CONFIG_DEFAULTS.
# export OTREE_BOT_SUBMIT_DELAY_MS=1500
# export OTREE_BOT_SUBMIT_JITTER_MS=1000

# Note: otree migrate is not available in this oTree CLI; run ALTER TABLE manually if you add new Player fields.
# Note: otree resetdb fails on PostGIS DBs (cannot drop spatial_ref_sys). To clear data, use truncate_otree_tables.sql or run fix_wide_export_one_session.sql for one session.

otree prodserver 9000
