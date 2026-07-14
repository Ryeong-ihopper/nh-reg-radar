# Database seed boundary

Alembic owns only database structure. M2 defines two explicit seed classes:

- `common.sql` idempotently upserts the fixed roles and M2 common codes;
- `dev.sql` idempotently upserts synthetic users and departments only when the
  guarded `scripts/seed-dev-data.sh` entrypoint runs with `NH_ENVIRONMENT=dev`;
- `prod(main)` accepts only explicitly approved seed/import inputs;
- operating or customer data must never be embedded in a migration.

Both entrypoints require the `app` runtime identity. The dev entrypoint accepts
only `NH_DEV_SEED_PASSWORD_HASH`; it never accepts or stores a plaintext seed
password. No customer data or M3+ capability seed is included.
