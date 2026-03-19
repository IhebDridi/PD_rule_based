#!/bin/bash

otree migrate
export DATABASE_URL=${POSTGRESQL_ADDON_URI}

#echo y | otree resetdb
#echo "[INFO] Dropping and recreating public schema…"
#psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO PUBLIC;"

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

