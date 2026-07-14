#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${NH_ENVIRONMENT:-}" != "dev" ]]; then
  printf 'dev seed is allowed only when NH_ENVIRONMENT=dev\n' >&2
  exit 64
fi

# M2 owns sample users/departments. This guard exists now so prod(main) can
# never reuse a future dev seed entrypoint by accident.
printf 'No M1 dev seed data; nothing to apply.\n'

