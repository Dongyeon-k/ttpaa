#!/bin/sh
set -eu

if [ -n "${DATABASE_URL:-}" ]; then
  echo "Waiting for database..."
  python - <<'PY'
import os
import time
from urllib.parse import urlparse

import psycopg

database_url = os.environ["DATABASE_URL"]
parsed = urlparse(database_url)

for attempt in range(30):
    try:
        conn = psycopg.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            dbname=parsed.path.lstrip("/"),
        )
        conn.close()
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("Database connection failed after 30 attempts")
PY
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
