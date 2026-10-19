#!/bin/sh
# Applies migrations (and optionally seeds) before starting the API.
set -e
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  alembic upgrade head
fi
if [ "${SEED_ON_START:-0}" = "1" ]; then
  python -m app.seed
fi
exec "$@"
