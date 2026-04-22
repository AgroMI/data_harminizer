#!/usr/bin/env bash
set -euo pipefail

python /app/backend/scripts/run_migrations.py
exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
