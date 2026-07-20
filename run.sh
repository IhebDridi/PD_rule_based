#!/bin/bash

export DATABASE_URL=${POSTGRESQL_ADDON_URI}

# Clever / production notes (see docs/CLEVER_OTREE_SCALING.md):
# - Prefer 1 app instance (vertical scale). Extra instances fight over Session rows.
# - Attach Redis and expose REDIS_URL for multi-worker / channels.
# - Optional bot pacing (browser + CLI). Defaults also live in SESSION_CONFIG_DEFAULTS.
# export OTREE_BOT_SUBMIT_DELAY_MS=1500
# export OTREE_BOT_SUBMIT_JITTER_MS=1000

# Note: otree migrate is not available in this oTree CLI; run ALTER TABLE manually if you add new Player fields.
# Note: otree resetdb fails on PostGIS DBs (cannot drop spatial_ref_sys). To clear data, use truncate_otree_tables.sql or run fix_wide_export_one_session.sql for one session.

otree prodserver 9000
