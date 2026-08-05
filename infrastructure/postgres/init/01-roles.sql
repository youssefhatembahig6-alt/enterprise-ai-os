-- Two roles, because Row-Level Security needs a non-owner to act against
-- (research R6, spec FR-009d).
--
--   eaios_owner : owns the schema. PostgreSQL exempts table owners from RLS, which
--                 is what allows migrations and the seed to write both tenants.
--   eaios_app   : used by the API and worker. Non-owner, so every RLS policy
--                 applies. With no app.company_id set it sees zero rows.
--
-- Passwords here are local-only placeholders and match infrastructure/.env.example.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eaios_owner') THEN
        CREATE ROLE eaios_owner LOGIN PASSWORD 'eaios_owner_local_only';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eaios_app') THEN
        -- Deliberately NOT a superuser and NOT BYPASSRLS. Granting either would
        -- silently disable every tenant policy.
        CREATE ROLE eaios_app LOGIN PASSWORD 'eaios_app_local_only';
    END IF;
END
$$;

ALTER DATABASE eaios OWNER TO eaios_owner;

GRANT CONNECT ON DATABASE eaios TO eaios_app;
GRANT USAGE ON SCHEMA public TO eaios_app;
ALTER SCHEMA public OWNER TO eaios_owner;

-- Table-level grants are issued by migration 0002 alongside the RLS policies, so
-- access and isolation are introduced together rather than in separate steps.
