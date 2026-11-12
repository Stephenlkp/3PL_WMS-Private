#!/bin/sh
set -e
python - <<'PY'
import os
import time

from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL", "")
if url.startswith("sqlite"):
    raise SystemExit(0)
engine = create_engine(url)
for _ in range(30):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        break
    except Exception as exc:
        print("waiting for database", exc)
        time.sleep(1)
else:
    raise SystemExit("database did not become ready")
PY
alembic upgrade head
if [ "${SEED_ON_START}" = "true" ]; then
  python -m app.seed
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
