#!/usr/bin/env bash
set -Eeuo pipefail

# M2 owns the first common master-data definitions. M1 keeps this executable
# boundary deliberately empty rather than mixing future data into migrations.
printf 'No M1 common seed data; nothing to apply.\n'

