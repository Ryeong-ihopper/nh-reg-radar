# Database seed boundary

M1 intentionally contains no business or sample seed data. Alembic owns only
database structure. Starting in M2:

- system-required common codes and roles belong to an idempotent common seed;
- sample users and departments belong to a `dev`-only seed;
- `prod(main)` accepts only explicitly approved seed/import inputs;
- operating or customer data must never be embedded in a migration.

The root `scripts/seed-common-data.sh` and `scripts/seed-dev-data.sh` entrypoints
lock this boundary without pre-designing later capability data.

