#!/bin/bash

export DATABASE_URL=${POSTGRESQL_ADDON_URI}

# Note: otree migrate is not available in this oTree CLI; run ALTER TABLE manually if you add new Player fields.
# Note: otree resetdb fails on PostGIS DBs (cannot drop spatial_ref_sys). To clear data, use truncate_otree_tables.sql or run fix_wide_export_one_session.sql for one session.
#!/usr/bin/env bash
set -e
yes | otree resetdb

otree prodserver 9000





# DO $$
# DECLARE
#   r RECORD;
# BEGIN
#   FOR r IN
#     SELECT c.relname
#     FROM pg_class c
#     JOIN pg_namespace n ON n.oid = c.relnamespace
#     LEFT JOIN pg_depend d ON d.objid = c.oid AND d.deptype = 'e'
#     LEFT JOIN pg_extension e ON e.oid = d.refobjid AND e.extname = 'postgis'
#     WHERE n.nspname = 'public'
#       AND c.relkind = 'r'
#       AND e.oid IS NULL
#   LOOP
#     EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.relname) || ' CASCADE';
#   END LOOP;
# END $$;

