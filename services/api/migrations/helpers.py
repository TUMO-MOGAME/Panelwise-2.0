"""Shared migration steps (docs/design/deploy.md §6)."""

from alembic import op

# Supabase's Data API roles exist on Supabase only, not in the compose or test Postgres.
_REVOKE = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.{table} FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.{table} FROM authenticated';
  END IF;
END $$;
"""


def lock_down(table: str) -> None:
    """Row-level security on with no policies, and nothing granted to Supabase's public roles.

    Every migration that creates a table calls this for it: Supabase grants those roles every new
    table by default, so the publishable key would otherwise read it through the Data API. The API
    connects as the tables' owner, which RLS does not restrict."""
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(_REVOKE.format(table=table))
